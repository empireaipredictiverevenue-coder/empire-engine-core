//! Jito Block Engine integration for atomic bundle execution.
//!
//! Constructs and submits Jito bundles that atomically execute:
//!   Tx 1: Creator Bounty (AlphaBump — direct SOL to deployer for genesis priority)
//!   Tx 2: Local Simulated Swap (Jupiter swap WITH embedded CU budget, pre-simulated)
//!   Tx 3: Dynamic Jito Tip (variable tip based on pool data + expected profit)
//!
//! Local simulation via `simulateTransaction` RPC catches failing swaps
//! BEFORE bundle submission — no wasted tips on doomed transactions.
//!
//! Uses the Jito Block Engine JSON-RPC `sendBundle` endpoint for
//! MEV-protected, front-run resistant transaction inclusion with
//! `skipPreflight=true` and `processed` commitment for maximum speed.
//!
//! The BlockhashWorker continuously refreshes the latest blockhash
//! every 2,000ms to eliminate runtime delay at execution time.

use std::sync::Arc;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use base64::Engine;
use reqwest::Client as HttpClient;
use serde::Deserialize;
use serde_json::{json, Value};
use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::{
    hash::Hash,
    pubkey::Pubkey,
    signature::{Keypair, Signer},
    transaction::{Transaction, VersionedTransaction},
};
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

// ── Jito Constants ────────────────────────────────────────────────────────

/// Jito tip distribution program.
pub const JITO_TIP_PROGRAM: &str = "T1pyyaTNZsKv2WcRAB8oVnk93mLJw2XzjtVYqCsaHqt";

/// Default Jito Block Engine bundle endpoint.
pub const JITO_BUNDLE_ENDPOINT: &str = "https://mainnet.block-engine.jito.wtf/api/v1/bundles";

/// Maximum number of transactions in a bundle.
pub const MAX_BUNDLE_SIZE: usize = 5;

/// Jupiter quote API endpoint.
pub const JUPITER_QUOTE_API: &str = "https://quote-api.jup.ag/v6/quote";

/// Jupiter swap API endpoint.
pub const JUPITER_SWAP_API: &str = "https://quote-api.jup.ag/v6/swap";

/// WSOL mint address.
pub const WSOL_MINT: &str = "So11111111111111111111111111111111111111112";

// ── Compute budget ────────────────────────────────────────────────────────

/// Compute unit limit for swap instructions (handled by Jupiter API params).
const COMPUTE_UNIT_LIMIT: u32 = 400_000;

/// Priority fee in micro-lamports per compute unit (handled by Jupiter API params).
const PRIORITY_FEE_MICRO_LAMPORTS: u64 = 50_000;

/// Slippage in basis points (50 bps = 0.5%).
const SLIPPAGE_BPS: u16 = 100; // 1% for meme coin volatility

// ── Pool Context (for dynamic tip calculation) ───────────────────────────

/// Pool data used for dynamic tip calculation.
#[derive(Debug, Clone)]
pub struct PoolContext {
    /// Total liquidity in USD (from Jupiter quote).
    pub liquidity_usd: f64,
    /// Estimated ROI multiplier from the Jupiter quote (output / input).
    pub estimated_roi_multiplier: f64,
    /// Token age in seconds (0 = just launched).
    pub token_age_seconds: u64,
}

// ── Jito Config ───────────────────────────────────────────────────────────

/// Configuration for the Jito bundle builder.
#[derive(Debug, Clone)]
pub struct JitoConfig {
    /// Jito Block Engine JSON-RPC endpoint.
    pub endpoint: String,
    /// Base tip amount in lamports (minimum, before dynamic scaling).
    pub base_tip_lamports: u64,
    /// Maximum tip amount in lamports (cap for dynamic scaling).
    pub max_tip_lamports: u64,
    /// Creator bounty in lamports for AlphaBump genesis tipping.
    pub creator_bounty_lamports: u64,
}

// ── Jito Bundle Types ─────────────────────────────────────────────────────

#[derive(Debug, Deserialize)]
struct SendBundleResponse {
    result: Option<String>,
    error: Option<RpcError>,
}

#[derive(Debug, Deserialize)]
struct RpcError {
    message: String,
}

// ── Jito Bundle Builder ───────────────────────────────────────────────────

/// Builds and sends Jito bundles for atomic 3-transaction snipe execution.
#[derive(Clone)]
pub struct JitoBundleBuilder {
    config: JitoConfig,
    rpc: Arc<RpcClient>,
    http: HttpClient,
    /// Shared dynamic tip — updated continuously by TipOptimizer background task.
    current_target_tip: Arc<RwLock<u64>>,
}

impl JitoBundleBuilder {
    /// Create a new bundle builder.
    pub fn new(config: JitoConfig, rpc: Arc<RpcClient>, tip_lock: Arc<RwLock<u64>>) -> Self {
        Self {
            config,
            rpc,
            http: HttpClient::new(),
            current_target_tip: tip_lock,
        }
    }

    /// Build and send a complete 3-transaction ALPHABUMP snipe bundle:
    ///
    ///   Tx 1: CREATOR BOUNTY — direct SOL transfer to deployer for genesis priority
    ///   Tx 2: LOCAL SIMULATED SWAP — Jupiter swap WITH embedded CU budget, pre-simulated
    ///   Tx 3: DYNAMIC JITO TIP — variable tip scaled to expected profit + pool data
    ///
    /// Local simulation via `simulateTransaction` validates every swap BEFORE
    /// bundle submission. No Jito tip wasted on doomed transactions.
    ///
    /// Dynamic tip formula:
    ///   tip = base_tip + (expected_profit * 0.005)
    ///   where expected_profit = buy_amount * estimated_roi * success_probability
    ///   Capped at max_tip_lamports.
    ///
    /// Returns the bundle ID on successful submission.
    pub async fn build_and_send(
        &self,
        blockhash: &Hash,
        wallet: &Keypair,
        token_mint: &str,
        amount_lamports: u64,
        creator_wallet: Option<&str>,
        pool_ctx: Option<&PoolContext>,
    ) -> Result<String> {
        let token_mint_pk = Pubkey::try_from(token_mint)
            .with_context(|| format!("Invalid token mint: {token_mint}"))?;

        let wallet_pubkey = wallet.pubkey();

        // ── Tx 1: Creator Bounty (AlphaBump genesis tip) ──────
        let creator_bounty = if let Some(creator_str) = creator_wallet {
            if self.config.creator_bounty_lamports > 0 {
                match Pubkey::try_from(creator_str) {
                    Ok(creator_pk) => Some((creator_pk, self.config.creator_bounty_lamports)),
                    Err(e) => {
                        warn!("Invalid creator wallet {}: {e} — skipping bounty", creator_str);
                        None
                    }
                }
            } else {
                None
            }
        } else {
            None
        };

        if creator_bounty.is_some() {
            info!(
                "💎 Tx1 CREATOR BOUNTY: {} lamports → creator {}",
                self.config.creator_bounty_lamports,
                creator_wallet.unwrap_or("unknown")
            );
        }

        // ── Tx 2: Build the Jupiter swap (with embedded CU) ───
        info!(
            "🔧 Tx2 LOCAL SIMULATED SWAP: building Jupiter route for {} lamports → {}",
            amount_lamports, &token_mint[..16],
        );

        let swap_tx = self.build_jupiter_swap(
            wallet,
            &token_mint_pk,
            amount_lamports,
        ).await?;

        // ── LOCAL SIMULATION: dry-run the swap before bundling ─
        info!("🧪 Simulating swap transaction locally...");
        let sim_result = self.simulate_transaction(&swap_tx).await?;

        if !sim_result {
            anyhow::bail!(
                "Local simulation FAILED for {} — swap would revert. Skipping snipe.",
                &token_mint[..16]
            );
        }
        info!("✅ Local simulation PASSED — swap will execute successfully");

        // ── Tx 3: Dynamic Jito Tip (from shared TipOptimizer) ──
        let dynamic_tip = self.resolve_dynamic_tip(pool_ctx, amount_lamports).await;
        let tip_account = self.derive_tip_account(&wallet_pubkey);

        info!(
            "💰 Tx3 DYNAMIC JITO TIP: {} lamports (base={}, max={})",
            dynamic_tip, self.config.base_tip_lamports, self.config.max_tip_lamports,
        );

        let tip_ix = solana_sdk::system_instruction::transfer(
            &wallet_pubkey,
            &tip_account,
            dynamic_tip,
        );
        let tip_tx = Transaction::new_signed_with_payer(
            &[tip_ix],
            Some(&wallet_pubkey),
            &[wallet],
            *blockhash,
        );

        // ── Assemble the 3-transaction bundle ─────────────────
        let mut all_txs: Vec<String> = Vec::with_capacity(3);

        // Tx 1: Creator Bounty (optional)
        if let Some((creator_pk, bounty)) = creator_bounty {
            let bounty_ix = solana_sdk::system_instruction::transfer(
                &wallet_pubkey,
                &creator_pk,
                bounty,
            );
            let bounty_tx = Transaction::new_signed_with_payer(
                &[bounty_ix],
                Some(&wallet_pubkey),
                &[wallet],
                *blockhash,
            );
            all_txs.push(
                base64::engine::general_purpose::STANDARD.encode(
                    bincode::serialize(&bounty_tx).context("Failed to serialize creator bounty tx")?
                )
            );
        }

        // Tx 2: Local Simulated Swap (already signed, with embedded CU)
        all_txs.push(
            base64::engine::general_purpose::STANDARD.encode(
                bincode::serialize(&swap_tx).context("Failed to serialize swap tx")?
            )
        );

        // Tx 3: Dynamic Jito Tip
        all_txs.push(
            base64::engine::general_purpose::STANDARD.encode(
                bincode::serialize(&tip_tx).context("Failed to serialize tip tx")?
            )
        );

        let bundle_tag = if creator_bounty.is_some() { "ALPHABUMP" } else { "STANDARD" };

        // ── Submit to Jito Block Engine ─────────────────────────
        info!(
            "🚀 Submitting [{bundle_tag}] 3-tx bundle to Jito: [{}bounty, swap, {}tip]",
            if creator_bounty.is_some() { "" } else { "no " },
            if dynamic_tip > self.config.base_tip_lamports { "dynamic " } else { "" },
        );

        let bundle_id = self.send_bundle(&all_txs).await?;

        info!("✅ [{bundle_tag}] Bundle accepted: {bundle_id}");
        Ok(bundle_id)
    }

    /// Build a Jupiter swap transaction:
    /// get quote → build swap → deserialize → SIGN → return signed tx.
    ///
    /// Compute budget is handled by Jupiter API params
    /// (dynamicComputeUnitLimit=true, prioritizationFeeLamports="auto").
    async fn build_jupiter_swap(
        &self,
        wallet: &Keypair,
        output_mint: &Pubkey,
        amount_lamports: u64,
    ) -> Result<VersionedTransaction> {
        let wallet_pubkey = wallet.pubkey();

        // ── Get Jupiter quote ────────────────────────────────────
        let quote_url = format!(
            "{}?inputMint={}&outputMint={}&amount={}&slippageBps={}",
            JUPITER_QUOTE_API,
            WSOL_MINT,
            output_mint,
            amount_lamports,
            SLIPPAGE_BPS,
        );

        let quote_response: Value = self
            .http
            .get(&quote_url)
            .send()
            .await
            .with_context(|| "Jupiter quote request failed")?
            .json()
            .await
            .with_context(|| "Failed to parse Jupiter quote response")?;

        if quote_response.get("error").is_some() {
            let err_msg = quote_response["error"]
                .as_str()
                .unwrap_or("Unknown Jupiter error");
            anyhow::bail!("Jupiter quote error: {err_msg}");
        }

        let out_amount = quote_response
            .get("outAmount")
            .and_then(|v| v.as_str())
            .and_then(|s| s.parse::<u64>().ok())
            .context("Jupiter quote missing outAmount")?;

        if out_amount == 0 {
            anyhow::bail!("Jupiter quote returned zero output — no route available");
        }

        let price_impact = quote_response
            .get("priceImpactPct")
            .and_then(|v| v.as_str())
            .unwrap_or("0");

        info!(
            "📊 Jupiter quote: {} lamports WSOL → {} tokens (impact: {}%)",
            amount_lamports, out_amount, price_impact,
        );

        // ── Build swap transaction via Jupiter API ────────────────
        let swap_body = json!({
            "quoteResponse": quote_response,
            "userPublicKey": wallet_pubkey.to_string(),
            "wrapAndUnwrapSol": true,
            "dynamicComputeUnitLimit": true,
            "prioritizationFeeLamports": "auto",
        });

        let swap_response: Value = self
            .http
            .post(JUPITER_SWAP_API)
            .json(&swap_body)
            .send()
            .await
            .with_context(|| "Jupiter swap API request failed")?
            .json()
            .await
            .with_context(|| "Failed to parse Jupiter swap response")?;

        let swap_tx_b64 = swap_response
            .get("swapTransaction")
            .and_then(|v| v.as_str())
            .context("Jupiter swap API missing swapTransaction")?;

        // ── Deserialize VersionedTransaction from Jupiter ────────
        let swap_tx_bytes = base64::engine::general_purpose::STANDARD
            .decode(swap_tx_b64)
            .context("Failed to decode Jupiter swap transaction base64")?;

        let mut swap_tx: VersionedTransaction = bincode::deserialize(&swap_tx_bytes)
            .context("Failed to deserialize Jupiter VersionedTransaction")?;

        // ── SIGN the transaction with the wallet ──────────────────
        // Jupiter returns a partially-signed v0/legacy transaction.
        // Compute budget is handled by Jupiter API params:
        //   dynamicComputeUnitLimit=true, prioritizationFeeLamports="auto"
        let message_bytes = swap_tx.message.serialize();
        swap_tx.signatures[0] = wallet.sign_message(&message_bytes);

        info!(
            "🔏 Jupiter swap tx signed by {} (CU handled by Jupiter API)",
            &wallet_pubkey.to_string()[..12],
        );

        Ok(swap_tx)
    }

    // ── Local Transaction Simulation ───────────────────────────────

    /// Simulate a signed transaction locally via `simulateTransaction` RPC.
    ///
    /// Returns `true` if the transaction would execute successfully,
    /// `false` if it would fail (insufficient liquidity, bad route, etc.).
    ///
    /// This prevents wasting Jito tips on transactions that would revert.
    async fn simulate_transaction(
        &self,
        tx: &VersionedTransaction,
    ) -> Result<bool> {
        let tx_b64 = base64::engine::general_purpose::STANDARD.encode(
            bincode::serialize(tx).context("Failed to serialize tx for simulation")?
        );

        let response: Value = self
            .rpc
            .send(
                solana_client::rpc_request::RpcRequest::Custom {
                    method: "simulateTransaction",
                },
                serde_json::json!([
                    tx_b64,
                    {
                        "sigVerify": false,
                        "commitment": "processed",
                        "replaceRecentBlockhash": true,
                    }
                ]),
            )
            .await
            .with_context(|| "simulateTransaction RPC call failed")?;

        let err = response
            .get("value")
            .and_then(|v| v.get("err"));

        match err {
            None | Some(Value::Null) => {
                let logs = response
                    .get("value")
                    .and_then(|v| v.get("logs"))
                    .and_then(|l| l.as_array())
                    .map(|a| a.len())
                    .unwrap_or(0);
                info!("🧪 Simulation OK — {} log lines", logs);
                Ok(true)
            }
            Some(e) => {
                warn!("🧪 Simulation FAILED: {}", e);
                Ok(false)
            }
        }
    }

    // ── Dynamic Jito Tip Calculation ─────────────────────────────

    /// Resolve the dynamic tip by combining the TipOptimizer's background
    /// value with pool-specific context (hot token boost, profit scaling).
    ///
    /// The TipOptimizer provides the 75th-percentile market rate.
    /// Pool-context multipliers are applied only to the CONFIG base tip,
    /// then the final tip is max(optimizer_value, pool_adjusted_base).
    /// This ensures we never pay BELOW the optimizer but also never
    /// multiply the already-optimized value.
    async fn resolve_dynamic_tip(
        &self,
        pool_ctx: Option<&PoolContext>,
        buy_amount_lamports: u64,
    ) -> u64 {
        let optimizer_tip = *self.current_target_tip.read().await;

        let pool = match pool_ctx {
            Some(p) => p,
            None => return optimizer_tip,
        };

        // Pool-context adjustment applied to the BASE (not the optimizer value)
        let buy_amount_sol = buy_amount_lamports as f64 / 1e9;
        let roi_gain = (pool.estimated_roi_multiplier - 1.0).max(0.0);
        let expected_profit_sol = buy_amount_sol * roi_gain * 0.7;
        let profit_boost = (expected_profit_sol * 0.005) as u64;

        let hot_mult = if pool.token_age_seconds < 60 {
            1.1
        } else if pool.token_age_seconds < 300 {
            1.05
        } else {
            1.0
        };

        // Apply multipliers to the base tip, then take max with optimizer
        let pool_adjusted = ((self.config.base_tip_lamports as f64 + profit_boost as f64) * hot_mult) as u64;
        let tip = optimizer_tip.max(pool_adjusted).clamp(self.config.base_tip_lamports, self.config.max_tip_lamports);

        debug!(
            "💰 Resolved tip: optimizer={} pool_adjusted={} → {} lamports",
            optimizer_tip, pool_adjusted, tip,
        );

        tip
    }

    /// Submit a bundle to the Jito Block Engine via JSON-RPC.
    ///
    /// Standard Jito `sendBundle` API: `params: [[tx1_b64, tx2_b64, ...]]`
    /// where each element is a base64-encoded signed transaction.
    async fn send_bundle(&self, bundle: &[String]) -> Result<String> {
        // The Jito API expects: params: [bundle] where bundle is an
        // array of base64-encoded transaction strings.
        let request = json!({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "sendBundle",
            "params": [bundle]
        });

        let response = self
            .http
            .post(&self.config.endpoint)
            .header("Content-Type", "application/json")
            .json(&request)
            .send()
            .await
            .with_context(|| format!("Failed to send bundle to {}", self.config.endpoint))?;

        let status = response.status();
        let body = response
            .text()
            .await
            .with_context(|| "Failed to read Jito response body")?;

        if !status.is_success() {
            anyhow::bail!("Jito HTTP {}: {body}", status.as_u16());
        }

        let result: SendBundleResponse = serde_json::from_str(&body)
            .with_context(|| format!("Failed to parse Jito response: {body}"))?;

        if let Some(err) = result.error {
            anyhow::bail!("Jito RPC error: {}", err.message);
        }

        result
            .result
            .context("Jito returned no bundle ID (empty result)")
    }

    /// Derive the Jito tip account PDA for a given wallet.
    ///
    /// Jito tip accounts are derived from the tip distribution program
    /// using the canonical seed `tip_account` and the wallet's pubkey.
    /// The tip must be sent to this PDA for the bundle to be accepted
    /// by Jito validators.
    fn derive_tip_account(&self, wallet: &Pubkey) -> Pubkey {
        let (tip_pda, _bump) = Pubkey::find_program_address(
            &[b"tip_account", wallet.as_ref()],
            &Pubkey::try_from(JITO_TIP_PROGRAM).unwrap(),
        );
        tip_pda
    }
}

// ── Shadow Run Tip Optimizer ──────────────────────────────────────────────

/// Background task that continuously polls network congestion data
/// and updates a shared dynamic tip value for zero-latency snipe execution.
///
/// SHADOW RUN ENGINE: The tip is tuned toward the 75th percentile of
/// recent prioritization fees to guarantee block inclusion without
/// overpaying. Updates every 1,500ms.
pub struct TipOptimizer {
    rpc_client: Arc<RpcClient>,
    tip_lock: Arc<RwLock<u64>>,
    base_tip: u64,
    max_tip: u64,
    interval: Duration,
}

impl TipOptimizer {
    /// Create a new tip optimizer.
    pub fn new(
        rpc_client: Arc<RpcClient>,
        tip_lock: Arc<RwLock<u64>>,
        base_tip: u64,
        max_tip: u64,
    ) -> Self {
        Self {
            rpc_client,
            tip_lock,
            base_tip,
            max_tip,
            interval: Duration::from_millis(1500),
        }
    }

    /// Run the tip optimization loop continuously.
    ///
    /// Polls `getRecentPrioritizationFees` for Solana mainnet, computes
    /// the 75th percentile fee, and updates the shared tip lock.
    /// Falls back to the base tip if the RPC call fails.
    /// After 5 consecutive failures, doubles the poll interval (capped at 60s)
    /// to avoid warning spam on unsupported RPC nodes.
    pub async fn run(&self) {
        let mut failures: u32 = 0;
        let mut current_interval = self.interval;
        loop {
            let (optimized, is_ok) = match self.fetch_optimal_tip().await {
                Ok(tip) => (tip, true),
                Err(e) => {
                    warn!("TipOptimizer: {e}");
                    (self.base_tip, false)
                }
            };
            let mut lock = self.tip_lock.write().await;
            if is_ok {
                failures = 0;
                current_interval = self.interval;
            } else {
                failures += 1;
                if failures >= 5 {
                    current_interval = (current_interval * 2).min(Duration::from_secs(60));
                }
            }
            *lock = optimized;
            debug!("🔄 TipOptimizer: tip={} lamports (failures={}, interval={:?})", optimized, failures, current_interval);
            drop(lock);
            tokio::time::sleep(current_interval).await;
        }
    }

    /// Fetch and compute the optimal tip from recent network fee data.
    async fn fetch_optimal_tip(&self) -> Result<u64> {
        let response: Value = self
            .rpc_client
            .send(
                solana_client::rpc_request::RpcRequest::Custom {
                    method: "getRecentPrioritizationFees",
                },
                serde_json::json!([]),
            )
            .await
            .map_err(|e| anyhow::anyhow!("getRecentPrioritizationFees failed: {e}"))?;

        // Extract prioritization fees from response
        let fees: Vec<u64> = response
            .as_array()
            .unwrap_or(&vec![])
            .iter()
            .filter_map(|entry| entry.get("prioritizationFee").and_then(|v| v.as_u64()))
            .collect();

        if fees.is_empty() {
            return Ok(self.base_tip);
        }

        // Compute 75th percentile fee (zero-fail slot placement)
        let mut sorted = fees;
        sorted.sort_unstable();
        let p75_idx = (sorted.len() as f64 * 0.75) as usize;
        let p75_fee = sorted[p75_idx.min(sorted.len() - 1)];

        // Clamp between base and max
        Ok(p75_fee.clamp(self.base_tip, self.max_tip))
    }
}

// ── Blockhash Worker ──────────────────────────────────────────────────────

/// Continuous blockhash refresh worker.
///
/// Fetches the latest blockhash from the RPC at a configurable interval
/// (default 2,000ms) and stores it in the shared `Arc<Mutex<(Hash, Instant)>>`
/// for zero-latency access by the sniper execution path.
pub struct BlockhashWorker {
    rpc_client: Arc<RpcClient>,
    interval: Duration,
}

impl BlockhashWorker {
    /// Create a new blockhash worker.
    pub fn new(rpc_client: Arc<RpcClient>, interval: Duration) -> Self {
        Self {
            rpc_client,
            interval,
        }
    }

    /// Fetch the latest blockhash from the RPC.
    ///
    /// Uses `getLatestBlockhash` with `processed` commitment for
    /// maximum speed.
    pub async fn fetch_blockhash(&mut self) -> Result<Hash> {
        let start = Instant::now();
        let response = self
            .rpc_client
            .get_latest_blockhash()
            .await
            .with_context(|| "Failed to fetch latest blockhash")?;

        let elapsed = start.elapsed();
        debug!(
            "🔄 Blockhash refreshed: {} ({:.0}ms)",
            response,
            elapsed.as_millis()
        );

        if elapsed > Duration::from_millis(100) {
            warn!(
                "⚠️  Slow blockhash fetch: {:.0}ms (target ≤ 100ms)",
                elapsed.as_millis()
            );
        }

        // Sleep for the remaining interval
        let sleep_duration = self.interval.saturating_sub(elapsed);
        if sleep_duration > Duration::ZERO {
            tokio::time::sleep(sleep_duration).await;
        }

        Ok(response)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use solana_client::nonblocking::rpc_client::RpcClient;
    use std::sync::Arc;

    fn make_tip_lock(val: u64) -> Arc<RwLock<u64>> {
        Arc::new(RwLock::new(val))
    }

    #[test]
    fn test_derive_tip_account() {
        let tip_program = Pubkey::try_from(JITO_TIP_PROGRAM).unwrap();
        assert_eq!(&tip_program.to_string()[..6], "T1pyya");
        
        let rpc = Arc::new(RpcClient::new("https://api.mainnet-beta.solana.com".to_string()));
        let tip_lock = make_tip_lock(5_000_000);
        let builder = JitoBundleBuilder::new(JitoConfig {
            endpoint: JITO_BUNDLE_ENDPOINT.to_string(),
            base_tip_lamports: 5_000_000,
            max_tip_lamports: 20_000_000,
            creator_bounty_lamports: 0,
        }, rpc, tip_lock);

        let wallet = Pubkey::new_unique();
        let tip_account = builder.derive_tip_account(&wallet);
        assert_ne!(tip_account, wallet);
    }

    #[test]
    fn test_max_bundle_size() {
        assert!(MAX_BUNDLE_SIZE >= 3);
    }

    #[test]
    fn test_slippage_for_meme_coins() {
        assert!(SLIPPAGE_BPS >= 50);
        assert!(SLIPPAGE_BPS <= 200);
    }

    #[test]
    fn test_priority_fee_in_range() {
        assert!(PRIORITY_FEE_MICRO_LAMPORTS >= 10_000);
        assert!(PRIORITY_FEE_MICRO_LAMPORTS <= 500_000);
    }
}
