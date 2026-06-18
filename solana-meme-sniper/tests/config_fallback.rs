//! Integration tests for ConfigWorker brain fallback logic.
//!
//! Uses an axum mock HTTP server to simulate the brain bridge,
//! verifying fallback timing and recovery behavior end-to-end.
//!
//! Time scaling:
//!   - Poll interval: 5s (production default)
//!   - Brain timeout: 1s (set via `with_brain_timeout` for fast tests)
//!   - Total test time: ~20s real time

use std::sync::Arc;
use std::time::Duration;

use axum::response::IntoResponse;
use tokio::sync::{Mutex, RwLock};

use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::commitment_config::CommitmentConfig;
use solana_sdk::pubkey::Pubkey;

use solana_meme_sniper::config::{ConfigWorker, DynamicConfig};

// ══════════════════════════════════════════════════════════════════════════
// Helpers
// ══════════════════════════════════════════════════════════════════════════

/// Start a mock brain HTTP server (runs on the current tokio runtime).
///
/// The `set_healthy` sender controls whether the server returns:
///   - `true`  → 200 OK with a test config
///   - `false` → 503 Service Unavailable (simulates brain outage)
async fn mock_brain_server() -> (String, tokio::sync::watch::Sender<bool>) {
    let (tx, rx) = tokio::sync::watch::channel(true);

    let app = axum::Router::new().route(
        "/api/v1/sniper/dynamic-config",
        axum::routing::get({
            let rx = rx.clone();
            move || {
                let rx = rx.clone();
                async move {
                    if *rx.borrow() {
                        axum::Json(serde_json::json!({
                            "min_risk_score": 50,
                            "buy_amount_sol": 0.1,
                            "market_mode": "aggressive",
                            "generated_by": "test-brain",
                            "reasoning": "Mock brain online"
                        }))
                        .into_response()
                    } else {
                        // Return 503 to simulate brain down
                        (
                            axum::http::StatusCode::SERVICE_UNAVAILABLE,
                            "Simulated brain outage",
                        )
                            .into_response()
                    }
                }
            }
        }),
    );

    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("Failed to bind mock server");
    let addr = listener.local_addr().expect("Failed to get mock server addr");
    let url = format!("http://{}:{}", addr.ip(), addr.port());

    tokio::spawn(async move {
        if let Err(e) = axum::serve(listener, app).await {
            eprintln!("Mock brain server error: {e}");
        }
    });

    (url, tx)
}

/// Create a shared snipe/error counter pair.
fn counters() -> (Arc<Mutex<u64>>, Arc<Mutex<u64>>) {
    (Arc::new(Mutex::new(0)), Arc::new(Mutex::new(0)))
}

// ══════════════════════════════════════════════════════════════════════════
// Tests
// ══════════════════════════════════════════════════════════════════════════

#[tokio::test]
async fn test_fallback_triggers_and_recovers() {
    // ── Start mock brain server ────────────────────────────────────
    let (brain_url, set_healthy) = mock_brain_server().await;

    // ── Shared state ───────────────────────────────────────────────
    let config: Arc<RwLock<DynamicConfig>> = Arc::new(RwLock::new(DynamicConfig::default()));
    let (snipe_count, error_count) = counters();

    // RPC client with a dummy endpoint — wallet balance fetch will fail
    // gracefully (logs a warning, uses 0.0 SOL).
    let rpc_client = Arc::new(RpcClient::new_with_commitment(
        "http://127.0.0.1:1".to_string(),
        CommitmentConfig::processed(),
    ));
    let dummy_pubkey = Pubkey::new_unique();

    // ── Create ConfigWorker with 1s brain timeout (fast test) ─────
    let worker = ConfigWorker::new(
        brain_url,
        config.clone(),
        snipe_count,
        error_count,
        rpc_client,
        dummy_pubkey,
    )
    .with_brain_timeout(Duration::from_secs(1));

    // ── Spawn worker ───────────────────────────────────────────────
    tokio::spawn(worker.run());

    // ── Phase 1: Brain is online — verify initial poll succeeds ────
    // The first poll fires immediately, then every 5s.
    // Wait 3s to ensure at least one poll completes.
    tokio::time::sleep(Duration::from_secs(3)).await;

    {
        let cfg = config.read().await;
        assert_eq!(
            cfg.generated_by, "test-brain",
            "Config should be from mock brain after initial poll"
        );
        assert_eq!(
            cfg.min_risk_score, 50,
            "Brain config should override default risk score"
        );
        assert_eq!(
            cfg.buy_amount_sol, 0.1,
            "Brain config buy amount should be applied"
        );
        assert_eq!(
            cfg.market_mode, "aggressive",
            "Brain config market mode should be applied"
        );
    }

    // ── Phase 2: Brain goes down — verify fallback ─────────────────
    set_healthy.send(false).unwrap();

    // Wait 8s: 1s timeout + 5s poll + 2s margin.
    // Poll at T+5s will fail (last_success at T+0s, elapsed=5s > 1s → fallback)
    tokio::time::sleep(Duration::from_secs(8)).await;

    {
        let cfg = config.read().await;
        assert_eq!(
            cfg.generated_by, "static-fallback",
            "Should fall back to static config after brain timeout"
        );
        assert!(
            cfg.reasoning.contains("static defaults"),
            "Reasoning should mention static defaults: {}",
            cfg.reasoning
        );

        // All other fields should revert to defaults
        assert_eq!(
            cfg.min_risk_score, 40,
            "Fallback should use default risk score"
        );
        assert_eq!(
            cfg.buy_amount_sol, 0.05,
            "Fallback should use default buy amount"
        );
        assert_eq!(
            cfg.market_mode, "balanced",
            "Fallback should use default market mode"
        );
    }

    // ── Phase 3: Brain recovers — verify config resumes ────────────
    set_healthy.send(true).unwrap();

    // Wait 8s: next poll at T+10s or T+15s (depends on timing)
    tokio::time::sleep(Duration::from_secs(8)).await;

    {
        let cfg = config.read().await;
        assert_eq!(
            cfg.generated_by, "test-brain",
            "Config should recover to brain values after brain comes back"
        );
        assert_eq!(
            cfg.min_risk_score, 50,
            "Recovered config should have brain's risk score"
        );
        assert_eq!(
            cfg.buy_amount_sol, 0.1,
            "Recovered config should have brain's buy amount"
        );
    }
}

#[tokio::test]
async fn test_fallback_never_triggers_if_brain_never_replied() {
    // If the brain never returns a successful response, last_success stays None,
    // so the fallback check is skipped. The config remains at the initial default
    // (generated_by="static", not "static-fallback").

    // Start mock brain in unhealthy state (503)
    let (brain_url, set_healthy) = mock_brain_server().await;
    set_healthy.send(false).unwrap();
    // Give the server a moment to accept the unhealthy state
    tokio::time::sleep(Duration::from_millis(200)).await;

    let config: Arc<RwLock<DynamicConfig>> = Arc::new(RwLock::new(DynamicConfig::default()));
    let (snipe_count, error_count) = counters();

    let rpc_client = Arc::new(RpcClient::new_with_commitment(
        "http://127.0.0.1:1".to_string(),
        CommitmentConfig::processed(),
    ));
    let dummy_pubkey = Pubkey::new_unique();

    let worker = ConfigWorker::new(
        brain_url,
        config.clone(),
        snipe_count,
        error_count,
        rpc_client,
        dummy_pubkey,
    )
    .with_brain_timeout(Duration::from_secs(1));

    tokio::spawn(worker.run());

    // Wait 12s: polls at T+0s, T+5s, T+10s all fail (503).
    // All polls fail before the 1s timeout is reached from last_success=None.
    tokio::time::sleep(Duration::from_secs(12)).await;

    {
        let cfg = config.read().await;
        // Config should remain at initial default since brain never replied
        assert_eq!(
            cfg.generated_by, "static",
            "Brain never replied — config should stay at initial static default, not static-fallback"
        );
        assert_eq!(
            cfg.reasoning,
            "Default configuration (brain offline)",
            "Reasoning should remain the initial default"
        );
        assert_eq!(cfg.min_risk_score, 40);
    }
}
