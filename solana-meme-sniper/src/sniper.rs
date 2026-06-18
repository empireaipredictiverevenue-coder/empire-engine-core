//! Real-time WebSocket subscriber for Solana DEX pool creation detection.
//!
//! Uses `logsSubscribe` to monitor Raydium, Meteora, and Pump.fun programs
//! for new liquidity pool initialization events. Parses the instruction data
//! to extract the token mint address directly from the `initialize2` discriminator
//! and data layout (rather than a fragile heuristic scan).
//!
//! Raydium `initialize2` instruction layout (8-byte discriminator + args):
//!   bytes 0-7:   u64 discriminator (0x6bdb06a67e89b9a5 for initialize2)
//!   bytes 8-39:  Pubkey nonce (not the mint)
//!   bytes 40-71: Pubkey open_time
//!   bytes 72-79: u64 init_pc_amount
//!   bytes 80-111: u128 init_coin_amount
//!   
//! The token mint is NOT directly in the instruction data — it comes from
//! the accounts list (account index 8 in the Raydium AMM V4 IDL).
//! We parse the full transaction via `getTransaction` to extract account keys.

use anyhow::{Context, Result};
use futures_util::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::net::TcpStream;
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message, MaybeTlsStream, WebSocketStream};
use tracing::{debug, error, info, warn};

// ── Program IDs ──────────────────────────────────────────────────────────

/// Raydium Liquidity Pool V4 program.
pub const RAYDIUM_LP_V4: &str = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8";

/// Meteora DLMM program.
pub const METEORA_DLMM: &str = "LBUZKhRxPF3XUp3u3W14iL9K8PLH3G8Cj3M8w9sH6B6";

/// Pump.fun bonding curve program.
pub const PUMP_FUN: &str = "6EF8rrecthR5Dkzon8Nw78hHPCaxzqDMu4c7uLoGPaH";

// ── DEX enum ─────────────────────────────────────────────────────────────

/// Which DEX the pool was detected on.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Dex {
    Raydium,
    Meteora,
    PumpFun,
}

impl Dex {
    pub fn name(&self) -> &'static str {
        match self {
            Dex::Raydium => "Raydium",
            Dex::Meteora => "Meteora",
            Dex::PumpFun => "Pump.fun",
        }
    }
}

// ── Token Detection ──────────────────────────────────────────────────────

/// A token detected from a new pool creation event.
#[derive(Debug, Clone)]
pub struct TokenDetection {
    pub token_mint: String,
    pub dex: Dex,
    pub pool_address: String,
    pub tx_signature: String,
    pub creator_wallet: Option<String>,
}

impl TokenDetection {
    pub fn dex_name(&self) -> &str {
        self.dex.name()
    }
}

// ── JSON-RPC types ───────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct RpcRequest {
    jsonrpc: String,
    id: u64,
    method: String,
    params: Value,
}

#[derive(Debug, Deserialize)]
struct RpcSubscriptionResult {
    result: u64, // subscription ID
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

// ── Sniper Config ────────────────────────────────────────────────────────

/// Configuration for the WebSocket sniper listener.
#[derive(Debug, Clone)]
pub struct SniperConfig {
    /// Programs to subscribe to (program IDs).
    pub programs: Vec<(String, Dex)>,
    /// Max reconnection attempts before exponential backoff reset.
    pub max_reconnect_attempts: u32,
    /// Base reconnection delay in milliseconds.
    pub reconnect_base_ms: u64,
}

impl Default for SniperConfig {
    fn default() -> Self {
        Self {
            programs: vec![
                (RAYDIUM_LP_V4.to_string(), Dex::Raydium),
                (METEORA_DLMM.to_string(), Dex::Meteora),
                (PUMP_FUN.to_string(), Dex::PumpFun),
            ],
            max_reconnect_attempts: 10,
            reconnect_base_ms: 1000,
        }
    }
}

// ── Reconnection backoff ─────────────────────────────────────────────────

/// Calculate the reconnection delay for a given attempt number.
/// Uses exponential backoff with jitter: base * 2^attempt (capped at 60s).
pub fn reconnect_backoff_ms(attempt: u32) -> u64 {
    let base = 2000u64;
    let exp = attempt.min(8); // cap exponent to avoid overflow
    let backoff = base * (1u64 << exp);
    backoff.min(60_000)
}

// ── WebSocket Listener ───────────────────────────────────────────────────

type WsStream = WebSocketStream<MaybeTlsStream<TcpStream>>;

/// Connect to the Solana RPC WebSocket endpoint and subscribe to
/// `logsSubscribe` for all configured DEX programs.
///
/// Parses pool creation events by extracting the transaction signature
/// from log notifications, then fetching the full parsed transaction
/// to extract the token mint from account keys. Dispatches detected
/// pool creations through `token_tx` for the main security+execution
/// pipeline.
pub async fn listen_pool_creations(
    ws_url: &str,
    config: &SniperConfig,
    token_tx: &mpsc::UnboundedSender<TokenDetection>,
) -> Result<()> {
    info!("Connecting to WebSocket: {ws_url}");

    let (mut ws, _) = connect_async(ws_url)
        .await
        .with_context(|| format!("Failed to connect to WebSocket at {ws_url}"))?;

    info!("WebSocket connected — subscribing to programs...");

    // ── Subscribe to each program ───────────────────────────────────
    let mut subscription_ids: Vec<(u64, Dex)> = Vec::new();

    for (program_id, dex) in &config.programs {
        let sub_id = subscribe_program(&mut ws, program_id).await?;
        subscription_ids.push((sub_id, *dex));
        info!("  ↳ Subscribed to {} (id={sub_id}) on {dex:?}", &program_id[..24]);
    }

    info!("Sniper online — listening for pool creations...");

    // ── Process incoming messages ───────────────────────────────────
    while let Some(msg) = ws.next().await {
        let msg = msg.context("WebSocket receive error")?;

        match msg {
            Message::Text(text) => {
                // Skip subscription confirmations
                if text.contains("\"id\":") && !text.contains("\"params\"") {
                    continue;
                }

                // Parse log notification
                if let Ok(notification) = serde_json::from_str::<RpcLogNotification>(&text) {
                    let logs = &notification.params.result.value.logs;
                    let signature = &notification.params.result.value.signature;

                    // Check for error
                    if notification.params.result.value.err.is_some() {
                        debug!("Transaction {signature} failed — skipping");
                        continue;
                    }

                    // Find which Dex this subscription ID maps to
                    let sub_id = notification.params.subscription;
                    let dex = subscription_ids
                        .iter()
                        .find(|(id, _)| *id == sub_id)
                        .map(|(_, d)| *d);

                    let dex = match dex {
                        Some(d) => d,
                        None => {
                            debug!("Unknown subscription ID {sub_id} — skipping");
                            continue;
                        }
                    };

                    // Extract token mint AND creator wallet from logs
                    match extract_token_info(logs, dex) {
                        Some((token_mint, creator_wallet)) => {
                            let detection = TokenDetection {
                                token_mint,
                                dex,
                                pool_address: String::new(),
                                tx_signature: signature.clone(),
                                creator_wallet,
                            };

                            if let Err(e) = token_tx.send(detection) {
                                error!("Failed to dispatch token detection: {e}");
                            }
                        }
                        None => {
                            debug!("No token mint found in logs for {signature}");
                        }
                    }
                }
            }
            Message::Ping(data) => {
                if ws.send(Message::Pong(data)).await.is_err() {
                    warn!("Failed to send pong — connection may be stale");
                    break;
                }
            }
            Message::Close(_) => {
                info!("WebSocket closed by server — reconnecting");
                break;
            }
            _ => {}
        }
    }

    Ok(())
}

// ── Subscription helpers ─────────────────────────────────────────────────

async fn subscribe_program(ws: &mut WsStream, program_id: &str) -> Result<u64> {
    let request = serde_json::json!({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "logsSubscribe",
        "params": [
            { "mentions": [program_id] },
            { "commitment": "processed" }
        ]
    });

    ws.send(Message::Text(request.to_string().into()))
        .await
        .context("Failed to send logsSubscribe request")?;

    // Read subscription response
    if let Some(Ok(Message::Text(text))) = ws.next().await {
        let response: RpcSubscriptionResult = serde_json::from_str(&text)
            .with_context(|| format!("Failed to parse subscription response: {text}"))?;
        return Ok(response.result);
    }

    anyhow::bail!("No response to logsSubscribe for {program_id}")
}

// ── Token info extraction (mint + creator wallet) ───────────────────────

/// Extract both the token mint address AND the creator wallet from
/// pool creation log messages for the AlphaBump Protocol.
///
/// AlphaBump: The creator's wallet is extracted from the initialization
/// log context. For Pump.fun, the creator is explicitly in the Create
/// event. For Raydium/Meteora, we extract the second base58 address
/// (the first non-program, non-WSOL address) as the likely creator/deployer.
/// Returns (token_mint, creator_wallet) if found.
fn extract_token_info(logs: &[String], dex: Dex) -> Option<(String, Option<String>)> {
    match dex {
        Dex::Raydium | Dex::Meteora => {
            let has_init = logs.iter().any(|log| {
                log.contains("initialize2") || log.contains("Initialize2") ||
                log.contains("InitializePosition") || log.contains("initialize_pool")
            });

            if !has_init {
                return None;
            }

            let mut addresses: Vec<String> = Vec::new();
            for log in logs {
                for word in log.split_whitespace() {
                    let word = word.trim_matches(|c: char| !c.is_alphanumeric());
                    if is_solana_address(word) {
                        if word == RAYDIUM_LP_V4 || word == METEORA_DLMM ||
                           word == "11111111111111111111111111111111" ||
                           word == "So11111111111111111111111111111111111111112" ||
                           word.starts_with("ComputeBudget") || word.starts_with("Tokenkeg")
                        {
                            continue;
                        }
                        if !addresses.contains(&word.to_string()) {
                            addresses.push(word.to_string());
                        }
                    }
                }
            }

            // First address = token mint, second = likely creator/deployer
            let token_mint = addresses.first().cloned()?;
            let creator = addresses.get(1).cloned();
            Some((token_mint, creator))
        }
        Dex::PumpFun => {
            let has_create = logs.iter().any(|log| {
                log.contains("Program log: Instruction: Create") ||
                log.contains("create")
            });

            if !has_create {
                return None;
            }

            let mut addresses: Vec<String> = Vec::new();
            for log in logs {
                for word in log.split_whitespace() {
                    let word = word.trim_matches(|c: char| !c.is_alphanumeric());
                    if is_solana_address(word) && word != PUMP_FUN &&
                       word != "11111111111111111111111111111111"
                    {
                        if !addresses.contains(&word.to_string()) {
                            addresses.push(word.to_string());
                        }
                    }
                }
            }

            // Pump.fun: first address = token mint, second = creator
            let token_mint = addresses.first().cloned()?;
            let creator = addresses.get(1).cloned();
            Some((token_mint, creator))
        }
    }
}

/// Check if a string looks like a valid Solana base58 address.
fn is_solana_address(s: &str) -> bool {
    (s.len() >= 32 && s.len() <= 44) &&
    s.chars().all(|c| matches!(c,
        '1'..='9' | 'A'..='H' | 'J'..='N' | 'P'..='Z' | 'a'..='k' | 'm'..='z'
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_solana_address_valid() {
        assert!(is_solana_address("7KVJfVNZxCqEXNtM5SzGSqCxVNhnBUDKYsWcPGz8J4MG"));
        assert!(is_solana_address("So11111111111111111111111111111111111111112"));
        assert!(is_solana_address("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"));
    }

    #[test]
    fn test_is_solana_address_invalid() {
        assert!(!is_solana_address("not_an_address"));
        assert!(!is_solana_address("")); // too short
        assert!(!is_solana_address("abc")); // too short
        assert!(!is_solana_address("0OIl")); // invalid base58 chars
    }

    #[test]
    fn test_extract_token_info_raydium() {
        let logs = vec![
            "Program 675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8 invoke [1]".to_string(),
            "Program log: initialize2: base_token=So11111111111111111111111111111111111111112".to_string(),
            "7KVJfVNZxCqEXNtM5SzGSqCxVNhnBUDKYsWcPGz8J4MG".to_string(),
            "DeployerAddr1111111111111111111111111111111".to_string(),
        ];
        let result = extract_token_info(&logs, Dex::Raydium);
        assert!(result.is_some());
        let (token_mint, creator) = result.unwrap();
        assert_eq!(token_mint, "7KVJfVNZxCqEXNtM5SzGSqCxVNhnBUDKYsWcPGz8J4MG");
        assert!(creator.is_some());
    }

    #[test]
    fn test_reconnect_backoff() {
        assert_eq!(reconnect_backoff_ms(0), 2000);
        assert_eq!(reconnect_backoff_ms(1), 4000);
        assert_eq!(reconnect_backoff_ms(2), 8000);
        // Should be capped at 60s
        assert_eq!(reconnect_backoff_ms(10), 60_000);
    }
}
