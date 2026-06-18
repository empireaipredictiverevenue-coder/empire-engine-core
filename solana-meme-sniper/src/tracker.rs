//! Smart Money Copy-Trading Engine
//!
//! Monitors a thread-safe set of target "insider" wallets via WebSocket
//! transaction log subscription. When a tracked wallet executes a buy
//! swap on any token, the engine detects the token mint and dispatches
//! a copy-trade signal into the existing 3-tx Jito bundle pipeline.
//!
//! Architecture:
//!   WebSocket (logsSubscribe with tracked wallet mentions)
//!     │
//!     ▼
//!   SmartMoneyTracker::process_onchain_transaction()
//!     │  (checks: is signer tracked? is it a buy?)
//!     ▼
//!   CopyTradeDetection → token_tx channel → main.rs execution
//!     │
//!     ▼
//!   build_jupiter_swap() → Jito bundle [bounty → copy swap → tip]

use std::collections::HashSet;
use std::sync::Arc;

use anyhow::{Context, Result};
use futures_util::{SinkExt, StreamExt};
use serde::Deserialize;
use serde_json::Value;
use tokio::net::TcpStream;
use tokio::sync::{mpsc, watch, RwLock};
use tokio_tungstenite::{connect_async, tungstenite::Message, MaybeTlsStream, WebSocketStream};
use tracing::{debug, error, info, warn};

use solana_sdk::pubkey::Pubkey;

// ── Copy Trade Configuration ──────────────────────────────────────────────

/// Default buy amount for copy trades (0.1 SOL).
pub const DEFAULT_COPY_TRADE_SOL: f64 = 0.1;

/// Maximum number of tracked wallets.
pub const MAX_TRACKED_WALLETS: usize = 50;

// ── Copy Trade Detection ──────────────────────────────────────────────────

/// A detected copy-trade opportunity — a tracked wallet just bought a token.
#[derive(Debug, Clone)]
pub struct CopyTradeDetection {
    /// Token mint address to copy-trade.
    pub token_mint: String,
    /// The tracked wallet that triggered the trade.
    pub tracked_wallet: String,
    /// Transaction signature of the source trade.
    pub tx_signature: String,
    /// Unix timestamp of detection (for age-aware sniping).
    pub detected_at_ms: u64,
}

// ── Smart Money Tracker ───────────────────────────────────────────────────

/// Thread-safe copy-trading engine.
///
/// Tracks a set of "smart money" wallet addresses. When any tracked
/// wallet executes a buy swap, the engine extracts the token mint
/// and signals the sniper pipeline to copy-trade immediately.
#[derive(Clone)]
pub struct SmartMoneyTracker {
    /// Set of tracked wallet addresses.
    target_wallets: Arc<RwLock<HashSet<Pubkey>>>,
    /// Copy trade size in lamports.
    copy_trade_size_lamports: u64,
    /// Version counter bumped on every add/remove — notifies the
    /// WebSocket listener to reconnect with the updated wallet list.
    wallet_version: watch::Sender<u64>,
}

impl SmartMoneyTracker {
    /// Create a new tracker with the given copy trade size in SOL.
    ///
    /// Returns (SmartMoneyTracker, watch::Receiver<u64>) — the receiver
    /// must be passed to `listen_wallet_transactions` for dynamic
    /// re-subscription when wallets are added or removed.
    pub fn new(copy_trade_size_sol: f64) -> (Self, watch::Receiver<u64>) {
        let (tx, rx) = watch::channel(0u64);
        (
            Self {
                target_wallets: Arc::new(RwLock::new(HashSet::new())),
                copy_trade_size_lamports: (copy_trade_size_sol * 1e9) as u64,
                wallet_version: tx,
            },
            rx,
        )
    }

    /// Add a wallet to the tracking set.
    ///
    /// Notifies the WebSocket listener to reconnect with the updated
    /// wallet list, so wallets added at runtime are tracked immediately.
    pub async fn add_target_wallet(&self, wallet: Pubkey) -> bool {
        let mut wallets = self.target_wallets.write().await;
        if wallets.len() >= MAX_TRACKED_WALLETS {
            warn!(
                "SmartMoneyTracker: max tracked wallets reached ({MAX_TRACKED_WALLETS})"
            );
            return false;
        }
        let added = wallets.insert(wallet);
        if added {
            info!("🎯 SmartMoneyTracker: now tracking wallet {}", wallet);
            let _ = self.wallet_version.send_modify(|v| *v += 1);
        }
        added
    }

    /// Remove a wallet from the tracking set. Returns true if it was tracked.
    ///
    /// Notifies the WebSocket listener to reconnect with the updated list.
    pub async fn remove_target_wallet(&self, wallet: &Pubkey) -> bool {
        let mut wallets = self.target_wallets.write().await;
        let removed = wallets.remove(wallet);
        if removed {
            info!("SmartMoneyTracker: stopped tracking wallet {wallet}");
            let _ = self.wallet_version.send_modify(|v| *v += 1);
        }
        removed
    }

    /// List all currently tracked wallets.
    pub async fn list_targets(&self) -> Vec<Pubkey> {
        let wallets = self.target_wallets.read().await;
        wallets.iter().cloned().collect()
    }

    /// Get the number of tracked wallets.
    pub async fn wallet_count(&self) -> usize {
        self.target_wallets.read().await.len()
    }

    /// Get the copy trade size in lamports.
    pub fn copy_trade_size(&self) -> u64 {
        self.copy_trade_size_lamports
    }

    /// Create a fresh `watch::Receiver` at the current wallet version.
    ///
    /// Use this in reconnect loops instead of cloning an old receiver —
    /// `subscribe()` always returns a receiver at the latest version,
    /// avoiding the stale-version infinite-reconnect bug.
    pub fn subscribe(&self) -> watch::Receiver<u64> {
        self.wallet_version.subscribe()
    }

    /// Process an on-chain transaction: check if the signer is a tracked
    /// wallet, and if so, return a CopyTradeDetection with the token mint.
    ///
    /// The caller is responsible for verifying that this is a BUY (not a sell)
    /// before calling this function — use `is_buy_transaction()` for that.
    ///
    /// Called from the WebSocket listener when a transaction log mentions
    /// a tracked wallet.
    pub async fn process_onchain_transaction(
        &self,
        signer: &Pubkey,
        token_mint: &str,
    ) -> Option<CopyTradeDetection> {
        let watched = self.target_wallets.read().await;

        if !watched.contains(signer) {
            return None;
        }

        info!(
            "💸 SMART MONEY DETECTED: tracked wallet {} buying {}",
            &signer.to_string()[..12],
            &token_mint[..16],
        );

        Some(CopyTradeDetection {
            token_mint: token_mint.to_string(),
            tracked_wallet: signer.to_string(),
            tx_signature: String::new(), // filled by caller
            detected_at_ms: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
        })
    }
}

// ── JSON-RPC types ────────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct RpcSubscriptionResult {
    result: u64,
}

#[derive(Debug, Deserialize)]
struct RpcLogNotification {
    params: LogParams,
}

#[derive(Debug, Deserialize)]
struct LogParams {
    result: LogResult,
    subscription: u64,
}

#[derive(Debug, Deserialize)]
struct LogResult {
    value: LogValue,
}

#[derive(Debug, Deserialize)]
struct LogValue {
    signature: String,
    logs: Vec<String>,
    err: Option<Value>,
}

type WsStream = WebSocketStream<MaybeTlsStream<TcpStream>>;

// ── WebSocket Wallet Transaction Listener ────────────────────────────────

/// Connect to the Solana RPC WebSocket and subscribe to transaction
/// logs that mention any of the tracked wallets. When a tracked wallet
/// executes a buy swap, the token mint is extracted and dispatched
/// through `copy_tx` to the main execution pipeline.
///
/// Uses `logsSubscribe` with the tracked wallet addresses in the
/// `mentions` filter. Reconnects with exponential backoff on failure.
pub async fn listen_wallet_transactions(
    ws_url: &str,
    rpc_url: &str,
    tracker: Arc<SmartMoneyTracker>,
    copy_tx: mpsc::UnboundedSender<CopyTradeDetection>,
    mut wallet_changed: watch::Receiver<u64>,
) -> Result<()> {
    info!("SmartMoneyTracker: connecting WebSocket for wallet monitoring...");

    let (mut ws, _) = connect_async(ws_url)
        .await
        .with_context(|| format!("Failed to connect to WebSocket at {ws_url}"))?;

    // Subscribe to logs mentioning tracked wallets
    let tracked_wallets: Vec<String> = tracker
        .list_targets()
        .await
        .iter()
        .map(|pk| pk.to_string())
        .collect();

    if tracked_wallets.is_empty() {
        info!("SmartMoneyTracker: no wallets to track — waiting for additions...");
        // Wait for wallet_changed notification, then reconnect
        let _ = wallet_changed.changed().await;
        return Ok(()); // trigger reconnect with updated list
    }

    info!(
        "SmartMoneyTracker: subscribing to logs for {} wallets...",
        tracked_wallets.len()
    );

    let request = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "logsSubscribe",
        "params": [
            { "mentions": tracked_wallets },
            { "commitment": "processed" }
        ]
    });

    ws.send(Message::Text(request.to_string().into()))
        .await
        .context("Failed to send logsSubscribe for tracked wallets")?;

    // Read subscription response
    if let Some(Ok(Message::Text(text))) = ws.next().await {
        let _response: RpcSubscriptionResult = serde_json::from_str(&text)
            .with_context(|| format!("Failed to parse subscription response: {text}"))?;
        info!("SmartMoneyTracker: subscribed — listening for smart money moves");
    }

    // Process incoming transaction logs with dynamic re-subscription.
    // Uses tokio::select! to simultaneously watch for:
    //   - WebSocket messages (wallet transactions)
    //   - Wallet version changes (add/remove triggers reconnect)
    loop {
        tokio::select! {
            msg = ws.next() => {
                let msg = match msg {
                    Some(m) => m.context("WebSocket receive error")?,
                    None => {
                        info!("SmartMoneyTracker: WebSocket stream ended — reconnecting");
                        return Ok(());
                    }
                };

                match msg {
                    Message::Text(text) => {
                        if text.contains("\"id\":") && !text.contains("\"params\"") {
                            continue;
                        }

                        let notification = match serde_json::from_str::<RpcLogNotification>(&text) {
                            Ok(n) => n,
                            Err(_) => continue,
                        };

                        let logs = &notification.params.result.value.logs;
                        let signature = &notification.params.result.value.signature;
                        let has_err = notification.params.result.value.err.is_some();

                        if has_err {
                            debug!("SmartMoneyTracker: tx {signature} failed — skipping");
                            continue;
                        }

                        let tracked = tracker.target_wallets.read().await;
                        if let Some((signer, token_mint)) = extract_swap_info(logs, &tracked) {
                            let signer_pk = match Pubkey::try_from(signer.as_str()) {
                                Ok(pk) => pk,
                                Err(_) => continue,
                            };

                            let token_mint_pk = match Pubkey::try_from(token_mint.as_str()) {
                                Ok(m) => m,
                                Err(_) => continue,
                            };

                            // ── Direction detection via getTransaction ──
                            let is_buy = match is_buy_transaction(
                                rpc_url, signature, &signer_pk, &token_mint_pk,
                            ).await {
                                Ok(buy) => buy,
                                Err(e) => {
                                    debug!("is_buy_transaction failed for {signature}: {e} — assuming buy");
                                    true
                                }
                            };

                            if !is_buy {
                                debug!("SmartMoneyTracker: tracked wallet SOLD {} — skipping", &token_mint[..12]);
                                continue;
                            }

                            let mut detection = match tracker
                                .process_onchain_transaction(&signer_pk, &token_mint)
                                .await
                            {
                                Some(d) => d,
                                None => continue,
                            };

                            detection.tx_signature = signature.clone();

                            let token_mint_snip = detection.token_mint[..16.min(detection.token_mint.len())].to_string();
                            let tx_sig_snip = detection.tx_signature[..16.min(detection.tx_signature.len())].to_string();
                            let wallet_snip = detection.tracked_wallet[..12.min(detection.tracked_wallet.len())].to_string();

                            if let Err(e) = copy_tx.send(detection) {
                                error!("SmartMoneyTracker: failed to dispatch copy-trade: {e}");
                            } else {
                                info!(
                                    "🎯 COPY-TRADE DISPATCHED: {} → {} (wallet: {})",
                                    token_mint_snip, tx_sig_snip, wallet_snip,
                                );
                            }
                        }
                    }
                    Message::Ping(data) => {
                        if ws.send(Message::Pong(data)).await.is_err() {
                            warn!("SmartMoneyTracker: failed to send pong — reconnecting");
                            return Ok(());
                        }
                    }
                    Message::Close(_) => {
                        info!("SmartMoneyTracker: WebSocket closed — reconnecting");
                        return Ok(());
                    }
                    _ => {}
                }
            }
            _ = wallet_changed.changed() => {
                info!("SmartMoneyTracker: wallet list changed — reconnecting with updated set");
                return Ok(());
            }
        }
    }
}

// ── Swap instruction extraction ──────────────────────────────────────────

/// Extract swap information from transaction logs using intersection matching.
///
/// Since `logsSubscribe` is filtered with `mentions` containing tracked
/// wallet addresses, we know a tracked wallet IS present in the logs.
/// Strategy:
///   1. Find a DEX program invocation to confirm this is a swap.
///   2. Extract all Solana addresses from the logs.
///   3. The tracked wallet is whichever address matches the subscription filter.
///   4. The token mint is the first non-program, non-WSOL address after
///      filtering out known base addresses.
///
/// Returns (signer, token_mint) if a swap involving a tracked wallet is detected.
///
/// Direction (buy vs sell) is determined separately by `is_buy_transaction()`
/// which calls `getTransaction` with `jsonParsed` encoding and compares
/// preTokenBalances vs postTokenBalances for the tracked wallet's ATA.
fn extract_swap_info(
    logs: &[String],
    tracked: &HashSet<Pubkey>,
) -> Option<(String, String)> {
    // 1. Confirm this is a DEX swap transaction
    let has_dex = logs.iter().any(|log| {
        DEX_PROGRAMS.iter().any(|prog| log.contains(prog))
            || log.contains("Instruction: Swap")
            || log.contains("Instruction: Route")
    });

    if !has_dex {
        return None;
    }

    // 2. Extract all unique Solana addresses from logs
    let mut addresses: Vec<String> = Vec::new();
    let mut seen = HashSet::new();

    for log in logs {
        for word in log.split_whitespace() {
            let word = word.trim_matches(|c: char| !c.is_alphanumeric());
            if is_solana_address(word) && !seen.contains(word) {
                seen.insert(word.to_string());
                addresses.push(word.to_string());
            }
        }
    }

    // 3. Find the tracked wallet (intersection with our watchlist)
    let signer = addresses.iter().find(|addr| {
        Pubkey::try_from(addr.as_str())
            .map(|pk| tracked.contains(&pk))
            .unwrap_or(false)
    })?;

    // 4. Extract token mint: first non-skip address that isn't the signer
    let token_mint = addresses.iter().find(|addr| {
        *addr != signer
            && !SKIP_ADDRESSES.contains(&addr.as_str())
            && !DEX_PROGRAMS.contains(&addr.as_str())
    })?;

    Some((signer.clone(), token_mint.clone()))
}


/// Known DEX/router program IDs.
const DEX_PROGRAMS: &[&str] = &[
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4",  // Jupiter v6
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",  // Raydium AMM v4
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP",  // Orca Swap
];

/// Addresses to skip when extracting token mints from logs.
const SKIP_ADDRESSES: &[&str] = &[
    "11111111111111111111111111111111",
    "So11111111111111111111111111111111111111112",  // WSOL
    "ComputeBudget111111111111111111111111111111",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "SysvarRent111111111111111111111111111111111",
];

// ── Direction Detection (Buy vs Sell) ─────────────────────────────────────

/// Determine if a transaction is a BUY by calling `getTransaction` with
/// `jsonParsed` encoding and comparing `preTokenBalances` vs `postTokenBalances`
/// for the tracked wallet's token account of the given mint.
///
/// Logic:
///   - Find the token mint + tracked wallet owner in pre/post balance arrays.
///   - If post > pre: wallet received tokens → BUY (return true).
///   - If post ≤ pre: wallet sent or held tokens → SELL/HOLD (return false).
///   - If the token isn't in either array (can't determine): default true.
///
/// Uses a raw JSON-RPC call via reqwest to avoid heavy Solana type imports.
/// Adds ~100-300ms latency per detection — acceptable for copy-trade verification.
async fn is_buy_transaction(
    rpc_url: &str,
    signature: &str,
    tracked_wallet: &Pubkey,
    token_mint: &Pubkey,
) -> Result<bool> {
    let client = reqwest::Client::new();

    let payload = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTransaction",
        "params": [
            signature,
            {
                "encoding": "jsonParsed",
                "commitment": "confirmed",
                "maxSupportedTransactionVersion": 0
            }
        ]
    });

    let resp: serde_json::Value = client
        .post(rpc_url)
        .json(&payload)
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
        .context("is_buy_transaction: HTTP request failed")?
        .json()
        .await
        .context("is_buy_transaction: JSON parse failed")?;

    // Transaction not found or null result → assume buy (conservative)
    let result = &resp["result"];
    if result.is_null() {
        debug!("is_buy_transaction: tx {signature} not found — assuming buy");
        return Ok(true);
    }

    let meta = &result["meta"];
    if meta.is_null() {
        debug!("is_buy_transaction: tx {signature} has no meta — assuming buy");
        return Ok(true);
    }

    let mint_str = token_mint.to_string();
    let wallet_str = tracked_wallet.to_string();

    // Find this (mint, owner) pair in preTokenBalances
    let pre_amount: f64 = meta["preTokenBalances"]
        .as_array()
        .and_then(|arr| {
            arr.iter().find(|b| {
                b["mint"].as_str() == Some(&mint_str)
                    && b["owner"].as_str() == Some(&wallet_str)
            })
        })
        .and_then(|b| b["uiTokenAmount"]["amount"].as_str())
        .and_then(|s| s.parse().ok())
        .unwrap_or(0.0);

    // Find this (mint, owner) pair in postTokenBalances
    let post_amount: f64 = meta["postTokenBalances"]
        .as_array()
        .and_then(|arr| {
            arr.iter().find(|b| {
                b["mint"].as_str() == Some(&mint_str)
                    && b["owner"].as_str() == Some(&wallet_str)
            })
        })
        .and_then(|b| b["uiTokenAmount"]["amount"].as_str())
        .and_then(|s| s.parse().ok())
        .unwrap_or(0.0);

    // If token absent from both arrays (brand-new ATA, not yet indexed),
    // default to true (conservative — don't miss a buy).
    if pre_amount == 0.0 && post_amount == 0.0 {
        debug!(
            "is_buy_transaction: {} {} not in either balance array — assuming buy",
            &signature[..12], &mint_str[..12],
        );
        return Ok(true);
    }

    let is_buy = post_amount > pre_amount;

    debug!(
        "is_buy_transaction: {} {} pre={pre_amount} post={post_amount} → {}",
        &signature[..12],
        &mint_str[..12],
        if is_buy { "BUY" } else { "SELL" },
    );

    Ok(is_buy)
}

/// Check if a string looks like a valid Solana base58 address.
fn is_solana_address(s: &str) -> bool {
    (s.len() >= 32 && s.len() <= 44)
        && s
            .chars()
            .all(|c| matches!(c, '1'..='9' | 'A'..='H' | 'J'..='N' | 'P'..='Z' | 'a'..='k' | 'm'..='z'))
}

// ── Tests ─────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_solana_address_valid() {
        assert!(is_solana_address(
            "7KVJfVNZxCqEXNtM5SzGSqCxVNhnBUDKYsWcPGz8J4MG"
        ));
        assert!(is_solana_address(
            "So11111111111111111111111111111111111111112"
        ));
    }

    #[test]
    fn test_is_solana_address_invalid() {
        assert!(!is_solana_address("not_an_address"));
        assert!(!is_solana_address(""));
        assert!(!is_solana_address("0OIl"));
    }

    #[test]
    fn test_extract_swap_info_jupiter_buy() {
        let logs = vec![
            "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 invoke [1]".to_string(),
            "Program log: Instruction: Route".to_string(),
            "7KVJfVNZxCqEXNtM5SzGSqCxVNhnBUDKYsWcPGz8J4MG".to_string(),
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v".to_string(),
            "So11111111111111111111111111111111111111112".to_string(),
        ];
        let tracked: HashSet<Pubkey> = HashSet::new();  // empty set for test
        let result = extract_swap_info(&logs, &tracked);
        // With empty tracked set, no wallet matches → returns None
        assert!(result.is_none());
    }

    #[test]
    fn test_extract_swap_info_jupiter_buy_with_tracked() {
        let tracked_wallet = Pubkey::try_from("7KVJfVNZxCqEXNtM5SzGSqCxVNhnBUDKYsWcPGz8J4MG").unwrap();
        let mut tracked: HashSet<Pubkey> = HashSet::new();
        tracked.insert(tracked_wallet);

        let logs = vec![
            "Program JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4 invoke [1]".to_string(),
            "Program log: Instruction: Route".to_string(),
            "7KVJfVNZxCqEXNtM5SzGSqCxVNhnBUDKYsWcPGz8J4MG".to_string(),
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v".to_string(),
            "So11111111111111111111111111111111111111112".to_string(),
        ];
        let result = extract_swap_info(&logs, &tracked);
        assert!(result.is_some());
        let (signer, token_mint) = result.unwrap();
        assert_eq!(signer, "7KVJfVNZxCqEXNtM5SzGSqCxVNhnBUDKYsWcPGz8J4MG");
        assert!(!token_mint.is_empty());
        // Direction is now determined by is_buy_transaction(), not extract_swap_info
    }

        #[test]
    fn test_extract_swap_info_no_swap_returns_none() {
        let logs = vec![
            "Program 11111111111111111111111111111111 invoke [1]".to_string(),
            "Transfer 1000 lamports".to_string(),
        ];
        let tracked: HashSet<Pubkey> = HashSet::new();
        assert!(extract_swap_info(&logs, &tracked).is_none());
    }
}
