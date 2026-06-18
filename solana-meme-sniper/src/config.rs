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
use tokio::sync::{Mutex, RwLock};
use tracing::{debug, error, info, warn};

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
    /// HTTP client for polling.
    client: reqwest::Client,
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
            client,
        }
    }

    /// Run the polling loop (blocks until cancellation).
    ///
    /// Spawn this via `tokio::spawn(config_worker.run())`.
    pub async fn run(mut self) {
        info!(
            "🔄 ConfigWorker: started — polling {} every 5s",
            self.brain_url
        );

        let mut consecutive_failures: u32 = 0;
        let mut interval = tokio::time::interval(Duration::from_millis(5000));

        loop {
            interval.tick().await;

            match self.poll().await {
                Ok(Some(cfg)) => {
                    consecutive_failures = 0;
                    let mode = &cfg.market_mode;
                    let risk = cfg.min_risk_score;
                    let paused = if cfg.pause_sniping { "⏸ PAUSED" } else { "▶ LIVE" };

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

        let url = format!(
            "{}/api/v1/sniper/dynamic-config?wallet_balance_sol=0&snipes_24h={}&failures_24h={}&optimize=true",
            self.brain_url, snipes, failures,
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
