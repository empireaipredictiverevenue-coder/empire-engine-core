//! Dynamic Config Worker — polls the AGI/SI brain bridge every 5 seconds
//! for live-optimized sniper parameters.
//!
//! Architecture:
//!   ConfigWorker (5s tokio loop)
//!     │  GET http://localhost:8055/api/v1/sniper/dynamic-config?wallet_balance_sol=...&snipes_24h=...&failures_24h=...
//!     ▼
//!   Arc<RwLock<DynamicConfig>>  ←  shared with snipe pipeline
//!
//! The Python brain bridge at `empire_sniper_brain.py` can run:
//!   - Static mode (sensible defaults, no LLM)
//!   - AGI mode (AIRouter → Ollama → optimized config based on market conditions)
//!   - Operator override mode (manual config via POST)

use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use serde::Deserialize;
use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::pubkey::Pubkey;
use tokio::sync::{Mutex, RwLock};
use tokio::time::Instant;
use tracing::{debug, info, warn};

// ── Dynamic Config ──────────────────────────────────────────────────────

/// Live-optimized sniper configuration from the AGI/SI brain bridge.
///
/// All fields are optional — the bot falls back to CLI/env defaults
/// when the brain is unavailable or a field is missing from the response.
#[derive(Debug, Clone, Deserialize)]
#[serde(default)]
pub struct DynamicConfig {
    /// Minimum acceptable risk score (0-100). Higher = safer.
    pub min_risk_score: u8,
    /// SOL amount per snipe.
    pub buy_amount_sol: f64,
    /// Base Jito tip in SOL.
    pub jito_base_tip_sol: f64,
    /// Maximum Jito tip in SOL.
    pub jito_max_tip_sol: f64,
    /// SOL amount per copy-trade.
    pub copy_trade_sol: f64,
    /// Maximum slippage in basis points (100 = 1%).
    pub max_slippage_bps: u16,
    /// Market mode: "aggressive", "balanced", or "conservative".
    pub market_mode: String,
    /// Whether to pause all sniping.
    pub pause_sniping: bool,
    /// Tracked wallet addresses for copy-trading.
    #[serde(default)]
    pub tracked_wallets: Vec<String>,
    /// ISO-8601 timestamp of config generation.
    #[serde(default)]
    pub generated_at: String,
    /// Source of the config: "static", "agi", or "operator_override".
    #[serde(default)]
    pub generated_by: String,
    /// Human-readable reasoning for the config.
    #[serde(default)]
    pub reasoning: String,
}

impl Default for DynamicConfig {
    fn default() -> Self {
        Self {
            min_risk_score: 40,
            buy_amount_sol: 0.05,
            jito_base_tip_sol: 0.005,
            jito_max_tip_sol: 0.02,
            copy_trade_sol: 0.1,
            max_slippage_bps: 500,
            market_mode: "balanced".to_string(),
            pause_sniping: false,
            tracked_wallets: Vec::new(),
            generated_at: String::new(),
            generated_by: "static".to_string(),
            reasoning: "Default configuration (brain offline)".to_string(),
        }
    }
}

impl DynamicConfig {
    /// Convert buy_amount_sol to lamports (1 SOL = 1e9 lamports).
    pub fn buy_amount_lamports(&self) -> u64 {
        (self.buy_amount_sol * 1e9) as u64
    }

    /// Convert jito_base_tip_sol to lamports.
    pub fn jito_base_tip_lamports(&self) -> u64 {
        (self.jito_base_tip_sol * 1e9) as u64
    }

    /// Convert jito_max_tip_sol to lamports.
    pub fn jito_max_tip_lamports(&self) -> u64 {
        (self.jito_max_tip_sol * 1e9) as u64
    }

    /// Convert copy_trade_sol to lamports.
    pub fn copy_trade_lamports(&self) -> u64 {
        (self.copy_trade_sol * 1e9) as u64
    }

    /// Returns true if the config came from the AGI brain (not static/override).
    pub fn is_agi_generated(&self) -> bool {
        self.generated_by == "agi"
    }
}

// ── Config Worker ───────────────────────────────────────────────────────

/// Background worker that polls the Python brain bridge for live config.
///
/// Polls `{brain_url}/api/v1/sniper/dynamic-config` every 5 seconds,
/// passing current state as query parameters (wallet balance, snipe count,
/// failure count). Updates the shared `Arc<RwLock<DynamicConfig>>`.
pub struct ConfigWorker {
    /// Base URL of the brain bridge (e.g., "http://localhost:8055").
    brain_url: String,
    /// Shared config that the snipe pipeline reads from.
    config: Arc<RwLock<DynamicConfig>>,
    /// Shared snipe + error counters for reporting to the brain.
    snipe_count: Arc<Mutex<u64>>,
    error_count: Arc<Mutex<u64>>,
    /// RPC client for querying wallet balance.
    rpc_client: Arc<RpcClient>,
    /// The primary sniper wallet pubkey whose balance to report.
    wallet_pubkey: Pubkey,
    /// HTTP client for polling.
    client: reqwest::Client,
    /// How long without a successful brain poll before falling back to static config.
    brain_timeout: Duration,
}

impl ConfigWorker {
    /// Create a new ConfigWorker.
    ///
    /// `brain_url` — base URL of the Python brain bridge (no trailing slash).
    /// `config` — shared RwLock that the execution pipeline reads from.
    pub fn new(
        brain_url: String,
        config: Arc<RwLock<DynamicConfig>>,
        snipe_count: Arc<Mutex<u64>>,
        error_count: Arc<Mutex<u64>>,
        rpc_client: Arc<RpcClient>,
        wallet_pubkey: Pubkey,
    ) -> Self {
        let client = reqwest::Client::builder()
            .timeout(Duration::from_secs(3))
            .connect_timeout(Duration::from_secs(2))
            .build()
            .expect("ConfigWorker: failed to create reqwest client");

        Self {
            brain_url,
            config,
            snipe_count,
            error_count,
            rpc_client,
            wallet_pubkey,
            client,
            brain_timeout: Duration::from_secs(30),
        }
    }

    /// Set a custom brain timeout (shorter for testing).
    pub fn with_brain_timeout(mut self, timeout: Duration) -> Self {
        self.brain_timeout = timeout;
        self
    }

    /// Run the polling loop (blocks until cancellation).
    ///
    /// Spawn this via `tokio::spawn(config_worker.run())`.
    pub async fn run(self) {
        info!(
            "🔄 ConfigWorker: started — polling {} every 5s",
            self.brain_url
        );

        let mut consecutive_failures: u32 = 0;
        let mut last_success: Option<Instant> = None;
        let mut static_fallback_active: bool = false;
        let mut interval = tokio::time::interval(Duration::from_millis(5000));

        loop {
            interval.tick().await;

            // ── Brain health check: fall back to static if down >timeout ──
            if let Some(last) = last_success {
                if last.elapsed() > self.brain_timeout && !static_fallback_active {
                    let outage = last.elapsed().as_secs();
                    warn!(
                        "🧠 BRAIN DOWN: bridge unreachable for {outage}s — FALLING BACK to static config"
                    );
                    static_fallback_active = true;
                    {
                        let mut lock = self.config.write().await;
                        *lock = DynamicConfig {
                            generated_by: "static-fallback".to_string(),
                            reasoning: format!(
                                "Brain bridge unreachable for >30s — using static defaults (last success: {outage}s ago)"
                            ),
                            ..DynamicConfig::default()
                        };
                    }
                }
            }

            match self.poll().await {
                Ok(Some(cfg)) => {
                    consecutive_failures = 0;
                    let was_fallback = static_fallback_active;
                    static_fallback_active = false;

                    let mode = &cfg.market_mode;
                    let risk = cfg.min_risk_score;
                    let paused = if cfg.pause_sniping { "⏸ PAUSED" } else { "▶ LIVE" };

                    if was_fallback {
                        let outage_s = last_success
                            .map(|last| last.elapsed().as_secs_f64())
                            .unwrap_or(0.0);
                        info!(
                            "🧠 BRAIN RECOVERED: bridge back online after {outage_s:.1}s outage — resuming dynamic config ({})",
                            &cfg.generated_by,
                        );
                    }

                    last_success = Some(Instant::now());

                    info!(
                        "📡 ConfigWorker: mode={mode} risk={risk} buy={} SOL tip={}/{} SOL {paused} ({})",
                        cfg.buy_amount_sol,
                        cfg.jito_base_tip_sol,
                        cfg.jito_max_tip_sol,
                        &cfg.generated_by,
                    );

                    let mut lock = self.config.write().await;
                    *lock = cfg;
                }
                Ok(None) => {
                    // Brain returned empty/invalid — keep current config
                    consecutive_failures += 1;
                    debug!(
                        "ConfigWorker: brain returned no config (failure #{consecutive_failures})"
                    );
                }
                Err(e) => {
                    consecutive_failures += 1;
                    if consecutive_failures <= 3 || consecutive_failures % 20 == 0 {
                        warn!(
                            "ConfigWorker: poll failed (#{consecutive_failures}): {e}"
                        );
                    } else {
                        debug!("ConfigWorker: poll failed (#{consecutive_failures}): {e}");
                    }
                }
            }
        }
    }

    /// Poll the brain bridge once.
    ///
    /// Returns `Ok(Some(config))` on success, `Ok(None)` if the response
    /// was invalid/missing, or `Err` on network/HTTP errors.
    async fn poll(&self) -> Result<Option<DynamicConfig>> {
        // Read real snipe/failure counts for the brain
        let snipes = *self.snipe_count.lock().await;
        let failures = *self.error_count.lock().await;

        // Fetch the real wallet balance from the RPC
        let wallet_balance_sol = match self.rpc_client.get_balance(&self.wallet_pubkey).await {
            Ok(lamports) => lamports as f64 / 1e9,
            Err(e) => {
                warn!("ConfigWorker: failed to fetch wallet balance: {e} — using 0");
                0.0
            }
        };

        let url = format!(
            "{}/api/v1/sniper/dynamic-config?wallet_balance_sol={}&snipes_24h={}&failures_24h={}&optimize=true",
            self.brain_url, wallet_balance_sol, snipes, failures,
        );

        let resp = self
            .client
            .get(&url)
            .send()
            .await
            .context("ConfigWorker: HTTP request failed")?;

        if !resp.status().is_success() {
            let status = resp.status();
            let body = resp.text().await.unwrap_or_default();
            anyhow::bail!("ConfigWorker: HTTP {status}: {body:.200}");
        }

        let config: DynamicConfig = resp
            .json()
            .await
            .context("ConfigWorker: failed to parse JSON response")?;

        Ok(Some(config))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config_has_expected_values() {
        let cfg = DynamicConfig::default();
        assert_eq!(cfg.min_risk_score, 40, "default risk");
        assert_eq!(cfg.buy_amount_sol, 0.05, "default buy amount");
        assert_eq!(cfg.jito_base_tip_sol, 0.005, "default base tip");
        assert_eq!(cfg.jito_max_tip_sol, 0.02, "default max tip");
        assert_eq!(cfg.copy_trade_sol, 0.1, "default copy trade");
        assert_eq!(cfg.max_slippage_bps, 500, "default slippage");
        assert_eq!(cfg.market_mode, "balanced", "default market mode");
        assert!(!cfg.pause_sniping, "default not paused");
        assert!(cfg.tracked_wallets.is_empty(), "default no tracked wallets");
        assert_eq!(cfg.generated_by, "static", "default generated_by");
        assert_eq!(cfg.reasoning, "Default configuration (brain offline)", "default reasoning");
    }

    #[test]
    fn test_is_agi_generated_various_modes() {
        let mut cfg = DynamicConfig::default();
        assert!(!cfg.is_agi_generated(), "static should not be AGI");

        cfg.generated_by = "agi".to_string();
        assert!(cfg.is_agi_generated(), "agi should be AGI");

        cfg.generated_by = "static-fallback".to_string();
        assert!(!cfg.is_agi_generated(), "static-fallback should not be AGI");

        cfg.generated_by = "operator_override".to_string();
        assert!(!cfg.is_agi_generated(), "operator_override should not be AGI");

        cfg.generated_by = "test-brain".to_string();
        assert!(!cfg.is_agi_generated(), "unknown mode should not be AGI");

        cfg.generated_by = "".to_string();
        assert!(!cfg.is_agi_generated(), "empty should not be AGI");
    }

    #[test]
    fn test_lamports_conversions() {
        // Default: 0.05 SOL buy, 0.005 base tip, 0.02 max tip, 0.1 copy
        let cfg = DynamicConfig::default();
        assert_eq!(cfg.buy_amount_lamports(), 50_000_000);
        assert_eq!(cfg.jito_base_tip_lamports(), 5_000_000);
        assert_eq!(cfg.jito_max_tip_lamports(), 20_000_000);
        assert_eq!(cfg.copy_trade_lamports(), 100_000_000);

        // Custom values
        let cfg = DynamicConfig {
            buy_amount_sol: 1.5,
            jito_base_tip_sol: 0.01,
            jito_max_tip_sol: 0.05,
            copy_trade_sol: 2.0,
            ..DynamicConfig::default()
        };
        assert_eq!(cfg.buy_amount_lamports(), 1_500_000_000);
        assert_eq!(cfg.jito_base_tip_lamports(), 10_000_000);
        assert_eq!(cfg.jito_max_tip_lamports(), 50_000_000);
        assert_eq!(cfg.copy_trade_lamports(), 2_000_000_000);
    }

    #[test]
    fn test_fallback_config_structure() {
        // Simulate what the run() method writes when fallback triggers:
        // DynamicConfig { generated_by: "static-fallback", reasoning: ..., ..DynamicConfig::default() }
        let outage_secs = 34u64;
        let fallback = DynamicConfig {
            generated_by: "static-fallback".to_string(),
            reasoning: format!(
                "Brain bridge unreachable for >30s — using static defaults (last success: {outage_secs}s ago)"
            ),
            ..DynamicConfig::default()
        };

        // Config identity: generated_by + reasoning are specific
        assert_eq!(fallback.generated_by, "static-fallback");
        assert!(fallback.reasoning.contains("Brain bridge unreachable"));
        assert!(fallback.reasoning.contains("34s"));

        // All other fields should match defaults
        let default = DynamicConfig::default();
        assert_eq!(fallback.min_risk_score, default.min_risk_score);
        assert_eq!(fallback.buy_amount_sol, default.buy_amount_sol);
        assert_eq!(fallback.jito_base_tip_sol, default.jito_base_tip_sol);
        assert_eq!(fallback.jito_max_tip_sol, default.jito_max_tip_sol);
        assert_eq!(fallback.copy_trade_sol, default.copy_trade_sol);
        assert_eq!(fallback.max_slippage_bps, default.max_slippage_bps);
        assert_eq!(fallback.market_mode, default.market_mode);
        assert_eq!(fallback.pause_sniping, default.pause_sniping);
        assert!(fallback.tracked_wallets.is_empty());
    }

    #[test]
    fn test_serde_deserialize() {
        // Ensure DynamicConfig can be deserialized from a partial JSON response
        let json = r#"{
            "min_risk_score": 60,
            "buy_amount_sol": 0.2,
            "market_mode": "conservative",
            "generated_by": "agi",
            "reasoning": "High volatility detected"
        }"#;

        let cfg: DynamicConfig = serde_json::from_str(json).unwrap();
        assert_eq!(cfg.min_risk_score, 60);
        assert_eq!(cfg.buy_amount_sol, 0.2);
        assert_eq!(cfg.market_mode, "conservative");
        assert_eq!(cfg.generated_by, "agi");
        assert!(cfg.reasoning.contains("High volatility"));

        // Fields not in JSON should use serde defaults
        assert_eq!(cfg.jito_base_tip_sol, 0.005, "unset field uses default");
        assert_eq!(cfg.max_slippage_bps, 500);
        assert!(!cfg.pause_sniping);
    }
}
