//! Tracker REST API — runtime control for the Smart Money Copy-Trading Engine.
//!
//! Provides HTTP endpoints to add/remove/list tracked wallets without
//! restarting the bot. The dynamic subscription automatically reconnects
//! when wallets are added or removed.
//!
//! Endpoints:
//!   POST /api/v1/tracker/add      { "wallet": "<base58>" }
//!   POST /api/v1/tracker/remove   { "wallet": "<base58>" }
//!   POST /api/v1/tracker/bulk     { "wallets": ["<base58>", ...] }
//!   GET  /api/v1/tracker/list     → { "wallets": [...], "count": N }
//!   GET  /api/v1/tracker/health   → { "status": "ok", "tracked": N }

use std::sync::Arc;

use axum::{
    extract::State,
    http::{header, StatusCode},
    middleware::{self, Next},
    response::{Json, Response},
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use solana_sdk::pubkey::Pubkey;
use tracing::info;

use crate::tracker::SmartMoneyTracker;

// ── Request / Response types ─────────────────────────────────────────────

#[derive(Debug, Deserialize, Serialize)]
struct AddRemoveRequest {
    wallet: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct WalletListResponse {
    wallets: Vec<String>,
    count: usize,
}

#[derive(Debug, Deserialize, Serialize)]
struct StatusResponse {
    status: String,
    tracked: usize,
    message: Option<String>,
}

#[derive(Debug, Deserialize)]
struct BulkRequest {
    wallets: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct BulkResponse {
    status: String,
    added: usize,
    skipped: usize,
    invalid: Vec<String>,
    tracked: usize,
}

// ── Handlers ──────────────────────────────────────────────────────────────

/// POST /api/v1/tracker/add
async fn add_wallet(
    State(tracker): State<Arc<SmartMoneyTracker>>,
    Json(body): Json<AddRemoveRequest>,
) -> (StatusCode, Json<StatusResponse>) {
    let pk = match Pubkey::try_from(body.wallet.as_str()) {
        Ok(pk) => pk,
        Err(e) => {
            let tracked = tracker.wallet_count().await;
            return (
                StatusCode::BAD_REQUEST,
                Json(StatusResponse {
                    status: "error".into(),
                    tracked,
                    message: Some(format!("Invalid Solana address: {e}")),
                }),
            );
        }
    };

    let pk_short = pk.to_string();
    let added = tracker.add_target_wallet(pk).await;
    let tracked = tracker.wallet_count().await;

    if added {
        info!("🌐 API: added wallet {} (tracked={tracked})", &pk_short[..12.min(pk_short.len())]);
        (
            StatusCode::OK,
            Json(StatusResponse {
                status: "ok".into(),
                tracked,
                message: Some(format!("Now tracking {pk_short}")),
            }),
        )
    } else {
        (
            StatusCode::CONFLICT,
            Json(StatusResponse {
                status: "duplicate_or_full".into(),
                tracked,
                message: Some(format!(
                    "Wallet already tracked or pool full (max {})",
                    crate::tracker::MAX_TRACKED_WALLETS
                )),
            }),
        )
    }
}

/// POST /api/v1/tracker/remove
async fn remove_wallet(
    State(tracker): State<Arc<SmartMoneyTracker>>,
    Json(body): Json<AddRemoveRequest>,
) -> (StatusCode, Json<StatusResponse>) {
    let pk = match Pubkey::try_from(body.wallet.as_str()) {
        Ok(pk) => pk,
        Err(e) => {
            let tracked = tracker.wallet_count().await;
            return (
                StatusCode::BAD_REQUEST,
                Json(StatusResponse {
                    status: "error".into(),
                    tracked,
                    message: Some(format!("Invalid Solana address: {e}")),
                }),
            );
        }
    };

    let pk_short = pk.to_string();
    let removed = tracker.remove_target_wallet(&pk).await;
    let tracked = tracker.wallet_count().await;

    if removed {
        info!("🌐 API: removed wallet {} (tracked={tracked})", &pk_short[..12.min(pk_short.len())]);
        (
            StatusCode::OK,
            Json(StatusResponse {
                status: "ok".into(),
                tracked,
                message: Some(format!("Stopped tracking {pk_short}")),
            }),
        )
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(StatusResponse {
                status: "not_found".into(),
                tracked,
                message: Some(format!("Wallet {pk_short} was not being tracked")),
            }),
        )
    }
}

/// GET /api/v1/tracker/list
async fn list_wallets(
    State(tracker): State<Arc<SmartMoneyTracker>>,
) -> Json<WalletListResponse> {
    let wallets: Vec<String> = tracker
        .list_targets()
        .await
        .iter()
        .map(|pk| pk.to_string())
        .collect();
    let count = wallets.len();
    Json(WalletListResponse { wallets, count })
}

/// POST /api/v1/tracker/bulk
async fn bulk_add(
    State(tracker): State<Arc<SmartMoneyTracker>>,
    Json(body): Json<BulkRequest>,
) -> (StatusCode, Json<BulkResponse>) {
    let mut added = 0usize;
    let mut skipped = 0usize;
    let mut invalid: Vec<String> = Vec::new();

    for wallet_str in &body.wallets {
        let wallet_str = wallet_str.trim();
        if wallet_str.is_empty() {
            continue;
        }

        let pk = match Pubkey::try_from(wallet_str) {
            Ok(pk) => pk,
            Err(_) => {
                invalid.push(wallet_str.to_string());
                continue;
            }
        };

        if tracker.add_target_wallet(pk).await {
            added += 1;
        } else {
            skipped += 1;
        }
    }

    let tracked = tracker.wallet_count().await;

    if added > 0 || skipped > 0 {
        info!(
            "🌐 API bulk: added {added} wallets, skipped {skipped}, invalid {} (tracked={tracked})",
            invalid.len(),
        );
    }

    (
        StatusCode::OK,
        Json(BulkResponse {
            status: "ok".into(),
            added,
            skipped,
            invalid,
            tracked,
        }),
    )
}
async fn health(
    State(tracker): State<Arc<SmartMoneyTracker>>,
) -> Json<StatusResponse> {
    let tracked = tracker.wallet_count().await;
    Json(StatusResponse {
        status: "ok".into(),
        tracked,
        message: None,
    })
}

// ── Auth middleware ─────────────────────────────────────────────────────

#[derive(Clone)]
struct AuthState {
    token: String,
}

/// Rejects requests without a matching `Authorization: Bearer <token>` header.
async fn auth_middleware(
    State(auth_state): State<AuthState>,
    req: axum::extract::Request,
    next: Next,
) -> Result<Response, StatusCode> {
    let auth_header = req
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|h| h.to_str().ok())
        .and_then(|h| h.strip_prefix("Bearer "));

    match auth_header {
        Some(t) if t == auth_state.token => Ok(next.run(req).await),
        _ => Err(StatusCode::UNAUTHORIZED),
    }
}

// ── Router ────────────────────────────────────────────────────────────────

/// Build the tracker API router ready to be served by axum.
///
/// When `auth_token` is `Some`, the add/remove/bulk POST endpoints require
/// an `Authorization: Bearer <token>` header. Health and list remain public.
pub fn build_router(tracker: Arc<SmartMoneyTracker>, auth_token: Option<String>) -> Router {
    // Public routes — no auth required
    let public_routes = Router::new()
        .route("/api/v1/tracker/list", get(list_wallets))
        .route("/api/v1/tracker/health", get(health));

    // Protected routes — require Bearer token when configured
    let mut protected_routes = Router::new()
        .route("/api/v1/tracker/add", post(add_wallet))
        .route("/api/v1/tracker/remove", post(remove_wallet))
        .route("/api/v1/tracker/bulk", post(bulk_add));

    if let Some(token) = auth_token {
        protected_routes = protected_routes
            .route_layer(middleware::from_fn_with_state(
                AuthState { token },
                auth_middleware,
            ));
    }

    Router::new()
        .merge(public_routes)
        .merge(protected_routes)
        .with_state(tracker)
}

// ── Tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::Body;
    use axum::http::header;
    use http_body_util::BodyExt;
    use solana_sdk::signature::{Keypair, Signer};
    use tower::ServiceExt;

    /// Create a test tracker with a known wallet.
    async fn test_tracker() -> (Arc<SmartMoneyTracker>, String) {
        let (tracker, _rx) = SmartMoneyTracker::new(0.1);
        let tracker = Arc::new(tracker);
        let wallet = Keypair::new();
        let addr = wallet.pubkey().to_string();
        tracker.add_target_wallet(wallet.pubkey()).await;
        (tracker, addr)
    }

    #[tokio::test]
    async fn test_health() {
        let (tracker, _addr) = test_tracker().await;
        let router = build_router(tracker, None);

        let resp = router
            .oneshot(
                axum::http::Request::builder()
                    .uri("/api/v1/tracker/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body = resp.into_body().collect().await.unwrap().to_bytes();
        let json: StatusResponse = serde_json::from_slice(&body).unwrap();
        assert_eq!(json.status, "ok");
        assert_eq!(json.tracked, 1);
    }

    #[tokio::test]
    async fn test_list() {
        let (tracker, addr) = test_tracker().await;
        let router = build_router(tracker, None);

        let resp = router
            .oneshot(
                axum::http::Request::builder()
                    .uri("/api/v1/tracker/list")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body = resp.into_body().collect().await.unwrap().to_bytes();
        let json: WalletListResponse = serde_json::from_slice(&body).unwrap();
        assert_eq!(json.count, 1);
        assert!(json.wallets.contains(&addr));
    }

    #[tokio::test]
    async fn test_add_valid() {
        let (tracker, _addr) = SmartMoneyTracker::new(0.1);
        let tracker = Arc::new(tracker);
        let router = build_router(tracker.clone(), None);

        let new_wallet = Keypair::new().pubkey().to_string();
        let body = serde_json::json!({"wallet": new_wallet});

        let resp = router
            .oneshot(
                axum::http::Request::post("/api/v1/tracker/add")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body_bytes = resp.into_body().collect().await.unwrap().to_bytes();
        let json: StatusResponse = serde_json::from_slice(&body_bytes).unwrap();
        assert_eq!(json.status, "ok");
        assert_eq!(json.tracked, 1);
    }

    #[tokio::test]
    async fn test_add_duplicate() {
        let (tracker, addr) = test_tracker().await;
        let router = build_router(tracker, None);

        let body = serde_json::json!({"wallet": addr});

        let resp = router
            .oneshot(
                axum::http::Request::post("/api/v1/tracker/add")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::CONFLICT);
    }

    #[tokio::test]
    async fn test_add_invalid_address() {
        let (tracker, _rx) = SmartMoneyTracker::new(0.1);
        let tracker = Arc::new(tracker);
        let router = build_router(tracker.clone(), None);

        let body = serde_json::json!({"wallet": "not_a_valid_address"});

        let resp = router
            .oneshot(
                axum::http::Request::post("/api/v1/tracker/add")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
        let body_bytes = resp.into_body().collect().await.unwrap().to_bytes();
        let json: StatusResponse = serde_json::from_slice(&body_bytes).unwrap();
        assert_eq!(json.status, "error");
        assert_eq!(json.tracked, 0);
    }

    #[tokio::test]
    async fn test_remove() {
        let (tracker, addr) = test_tracker().await;
        let router = build_router(tracker, None);

        let body = serde_json::json!({"wallet": addr});

        let resp = router
            .oneshot(
                axum::http::Request::post("/api/v1/tracker/remove")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_remove_not_found() {
        let (tracker, _addr) = test_tracker().await;
        let router = build_router(tracker, None);

        let unknown = Keypair::new().pubkey().to_string();
        let body = serde_json::json!({"wallet": unknown});

        let resp = router
            .oneshot(
                axum::http::Request::post("/api/v1/tracker/remove")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn test_bulk_add_valid() {
        let (tracker, _rx) = SmartMoneyTracker::new(0.1);
        let tracker = Arc::new(tracker);
        let router = build_router(tracker.clone(), None);

        let w1 = Keypair::new().pubkey().to_string();
        let w2 = Keypair::new().pubkey().to_string();
        let w3 = Keypair::new().pubkey().to_string();
        let body = serde_json::json!({"wallets": [w1, w2, w3]});

        let resp = router
            .oneshot(
                axum::http::Request::post("/api/v1/tracker/bulk")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body = resp.into_body().collect().await.unwrap().to_bytes();
        let json: BulkResponse = serde_json::from_slice(&body).unwrap();
        assert_eq!(json.added, 3);
        assert_eq!(json.skipped, 0);
        assert!(json.invalid.is_empty());
        assert_eq!(json.tracked, 3);
    }

    #[tokio::test]
    async fn test_bulk_add_mixed() {
        let (tracker, existing_addr) = test_tracker().await;
        let router = build_router(tracker, None);

        let new_wallet = Keypair::new().pubkey().to_string();
        let body = serde_json::json!({"wallets": [existing_addr, new_wallet, "bad!!address"]});

        let resp = router
            .oneshot(
                axum::http::Request::post("/api/v1/tracker/bulk")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body = resp.into_body().collect().await.unwrap().to_bytes();
        let json: BulkResponse = serde_json::from_slice(&body).unwrap();
        assert_eq!(json.added, 1);
        assert_eq!(json.skipped, 1);  // existing addr skipped (duplicate)
        assert_eq!(json.invalid.len(), 1);  // "bad!!address"
        assert_eq!(json.invalid[0], "bad!!address");
        assert_eq!(json.tracked, 2);  // original + new
    }

    #[tokio::test]
    async fn test_bulk_add_empty() {
        let (tracker, _addr) = test_tracker().await;
        let router = build_router(tracker, None);

        let body = serde_json::json!({"wallets": []});

        let resp = router
            .oneshot(
                axum::http::Request::post("/api/v1/tracker/bulk")
                    .header("content-type", "application/json")
                    .body(Body::from(serde_json::to_vec(&body).unwrap()))
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(resp.status(), StatusCode::OK);
        let body = resp.into_body().collect().await.unwrap().to_bytes();
        let json: BulkResponse = serde_json::from_slice(&body).unwrap();
        assert_eq!(json.added, 0);
        assert_eq!(json.skipped, 0);
        assert!(json.invalid.is_empty());
        assert_eq!(json.tracked, 1);  // unchanged
    }

    // ── Auth tests ────────────────────────────────────────────────

    /// Helper: build a POST request with optional Bearer token.
    fn auth_post(
        uri: &str,
        token: Option<&str>,
        body: serde_json::Value,
    ) -> axum::http::Request<Body> {
        let mut builder = axum::http::Request::post(uri)
            .header("content-type", "application/json");
        if let Some(t) = token {
            builder = builder.header(header::AUTHORIZATION, format!("Bearer {t}"));
        }
        builder
            .body(Body::from(serde_json::to_vec(&body).unwrap()))
            .unwrap()
    }

    #[tokio::test]
    async fn test_auth_no_token_rejected() {
        let (tracker, _rx) = SmartMoneyTracker::new(0.1);
        let tracker = Arc::new(tracker);
        let router = build_router(tracker.clone(), Some("supersecret".into()));

        let wallet = Keypair::new().pubkey().to_string();

        // POST /add without auth header → 401
        let resp = router
            .clone()
            .oneshot(auth_post("/api/v1/tracker/add", None, serde_json::json!({"wallet": wallet})))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        // POST /remove without auth header → 401
        let resp = router
            .clone()
            .oneshot(auth_post("/api/v1/tracker/remove", None, serde_json::json!({"wallet": wallet})))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        // POST /bulk without auth header → 401
        let resp = router
            .clone()
            .oneshot(auth_post("/api/v1/tracker/bulk", None, serde_json::json!({"wallets": [wallet]})))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);

        // GET /health without auth → still 200 (public)
        let resp = router
            .oneshot(
                axum::http::Request::builder()
                    .uri("/api/v1/tracker/health")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_auth_wrong_token_rejected() {
        let (tracker, _rx) = SmartMoneyTracker::new(0.1);
        let tracker = Arc::new(tracker);
        let router = build_router(tracker.clone(), Some("supersecret".into()));

        let wallet = Keypair::new().pubkey().to_string();

        let resp = router
            .oneshot(auth_post(
                "/api/v1/tracker/add",
                Some("wrongtoken"),
                serde_json::json!({"wallet": wallet}),
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_auth_correct_token_accepted() {
        let (tracker, _rx) = SmartMoneyTracker::new(0.1);
        let tracker = Arc::new(tracker);
        let router = build_router(tracker.clone(), Some("supersecret".into()));

        let wallet = Keypair::new().pubkey().to_string();

        let resp = router
            .oneshot(auth_post(
                "/api/v1/tracker/add",
                Some("supersecret"),
                serde_json::json!({"wallet": wallet}),
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn test_auth_disabled_allows_all() {
        // When auth_token is None, all endpoints are open
        let (tracker, _rx) = SmartMoneyTracker::new(0.1);
        let tracker = Arc::new(tracker);
        let router = build_router(tracker.clone(), None);

        let wallet = Keypair::new().pubkey().to_string();

        let resp = router
            .oneshot(auth_post(
                "/api/v1/tracker/add",
                None,
                serde_json::json!({"wallet": wallet}),
            ))
            .await
            .unwrap();
        assert_eq!(resp.status(), StatusCode::OK);
    }
}
