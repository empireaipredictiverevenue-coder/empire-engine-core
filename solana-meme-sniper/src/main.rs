//! Solana Meme Sniper Bot — Production-Grade Entry Point
//!
//! Architecture:
//!   - Real-time WebSocket subscriber (logsSubscribe) for Raydium/Meteora/Pump.fun
//!   - Continuous Blockhash Worker refreshing every 2,000ms
//!   - Anti-Rug Security Matrix (freeze/mint authority, LP lock, supply)
//!   - Jupiter swap + Jito Block Engine bundle execution (atomic swap + tip)
//!
//! Usage:
//!   cargo run --release -- \
//!     --rpc-url https://api.mainnet-beta.solana.com \
//!     --rpc-ws wss://api.mainnet-beta.solana.com \
//!     --keypair /path/to/sniper-wallet.json \
//!     --buy-amount 0.05 \
//!     --jito-tip 0.005

// Allow dead code for future-use fields, constants, and methods.
// The project is under active development — not all subsystems are
// wired yet. Remove this once all code paths are exercised.
#![allow(dead_code)]

use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::commitment_config::CommitmentConfig;
use solana_sdk::signature::{read_keypair_file, Keypair, Signer};
use tokio::signal;
use tokio::sync::{mpsc, Mutex, RwLock};
use tracing::{error, info, warn};
use tracing_subscriber::EnvFilter;

use solana_meme_sniper::sniper;
use solana_meme_sniper::sniper::SniperConfig;
use solana_meme_sniper::security::AntiRugMatrix;
use solana_meme_sniper::jito;
use solana_meme_sniper::jito::{BlockhashWorker, JitoBundleBuilder, JitoConfig, TipOptimizer};
use solana_meme_sniper::tracker;
use solana_meme_sniper::tracker::{SmartMoneyTracker, CopyTradeDetection};
use solana_meme_sniper::config::{DynamicConfig, ConfigWorker};
use solana_meme_sniper::tracker_api;
use solana_meme_sniper::wallet_rotation::WalletRotationPool;

/// CLI arguments parsed from the command line.
#[derive(Debug)]
struct Args {
    rpc_url: String,
    rpc_ws: String,
    jito_endpoint: String,
    keypair_path: PathBuf,
    buy_amount_sol: f64,
    jito_base_tip_sol: f64,
    jito_max_tip_sol: f64,
    creator_bounty_sol: f64,
    copy_trade_sol: f64,
    track_wallets: Vec<String>,
    min_risk_score: u8,
    brain_url: String,
    wallet_pool: Vec<String>,
    tracker_api_port: u16,
    tracker_api_token: String,
}

impl Args {
    fn parse() -> Result<Self> {
        let args: Vec<String> = std::env::args().collect();

        let mut rpc_url = std::env::var("SOLANA_RPC_URL")
            .unwrap_or_else(|_| "https://api.mainnet-beta.solana.com".to_string());
        let mut rpc_ws = std::env::var("SOLANA_RPC_WS")
            .unwrap_or_else(|_| "wss://api.mainnet-beta.solana.com".to_string());
        let mut jito_endpoint = std::env::var("JITO_ENDPOINT")
            .unwrap_or_else(|_| "https://mainnet.block-engine.jito.wtf/api/v1/bundles".to_string());
        let mut keypair_path = None;
        let mut buy_amount_sol = 0.05;
        let mut jito_base_tip_sol = 0.005;
        let mut jito_max_tip_sol = 0.02;
        let mut creator_bounty_sol = std::env::var("CREATOR_BOUNTY_SOL")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(0.0);
        let mut copy_trade_sol = std::env::var("COPY_TRADE_SOL")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(0.1);
        let mut track_wallets: Vec<String> = std::env::var("TRACK_WALLETS")
            .ok()
            .map(|v| v.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect())
            .unwrap_or_default();
        let mut min_risk_score = 40;
        let mut brain_url = std::env::var("SNIPER_BRAIN_URL")
            .unwrap_or_else(|_| "http://localhost:8055".to_string());
        let mut wallet_pool: Vec<String> = std::env::var("WALLET_POOL")
            .ok()
            .map(|v| v.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect())
            .unwrap_or_default();
        let mut tracker_api_port: u16 = std::env::var("TRACKER_API_PORT")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(8070);
        let mut tracker_api_token = std::env::var("TRACKER_API_TOKEN")
            .unwrap_or_default();

        let mut i = 1;
        while i < args.len() {
            match args[i].as_str() {
                "--rpc-url" => { i += 1; rpc_url = args[i].clone(); }
                "--rpc-ws" => { i += 1; rpc_ws = args[i].clone(); }
                "--jito-endpoint" => { i += 1; jito_endpoint = args[i].clone(); }
                "--keypair" => { i += 1; keypair_path = Some(PathBuf::from(&args[i])); }
                "--buy-amount" => { i += 1; buy_amount_sol = args[i].parse()?; }
                "--jito-base-tip" => { i += 1; jito_base_tip_sol = args[i].parse()?; }
                "--jito-max-tip" => { i += 1; jito_max_tip_sol = args[i].parse()?; }
                "--creator-bounty" => { i += 1; creator_bounty_sol = args[i].parse()?; }
                "--copy-trade" => { i += 1; copy_trade_sol = args[i].parse()?; }
                "--track-wallets" => { i += 1; track_wallets = args[i].split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect(); }
                "--min-risk" => { i += 1; min_risk_score = args[i].parse()?; }
                "--brain-url" => { i += 1; brain_url = args[i].clone(); }
                "--wallet-pool" => { i += 1; wallet_pool = args[i].split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect(); }
                "--tracker-api-port" => { i += 1; tracker_api_port = args[i].parse()?; }
                "--tracker-api-token" => { i += 1; tracker_api_token = args[i].clone(); }
                other => anyhow::bail!("Unknown argument: {other}"),
            }
            i += 1;
        }

        let keypair_path = keypair_path
            .or_else(|| std::env::var("SNIPER_KEYPAIR_PATH").ok().map(PathBuf::from))
            .context("--keypair is required (or set SNIPER_KEYPAIR_PATH env var)")?;

        Ok(Args {
            rpc_url,
            rpc_ws,
            jito_endpoint,
            keypair_path,
            buy_amount_sol,
            jito_base_tip_sol,
            jito_max_tip_sol,
            creator_bounty_sol,
            copy_trade_sol,
            track_wallets,
            min_risk_score,
            brain_url,
            wallet_pool,
            tracker_api_port,
            tracker_api_token,
        })
    }
}

/// Shared application state passed to all subsystems.
struct AppState {
    rpc_client: Arc<RpcClient>,
    sniper_wallet: Arc<Keypair>,
    blockhash: Arc<Mutex<(solana_sdk::hash::Hash, std::time::Instant)>>,
    buy_amount_lamports: u64,
    jito_base_tip_lamports: u64,
    jito_max_tip_lamports: u64,
    creator_bounty_lamports: u64,
    copy_trade_lamports: u64,
    min_risk_score: u8,
    dynamic_config: Arc<RwLock<DynamicConfig>>,
    wallet_pool: Arc<WalletRotationPool>,
    auth_token: Option<String>,
    snipe_count: Arc<Mutex<u64>>,
    error_count: Arc<Mutex<u64>>,
}

#[tokio::main]
async fn main() -> Result<()> {
    // ── Load .env BEFORE arg parsing ────────────────────────────────
    let _ = dotenv::dotenv();

    // ── Logging ────────────────────────────────────────────────────
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info,solana_meme_sniper=debug"))
        )
        .with_target(false)
        .init();

    info!("╔══════════════════════════════════════════════╗");
    info!("║   SOLANA MEME SNIPER BOT v1.0.0             ║");
    info!("╚══════════════════════════════════════════════╝");

    // ── Parse CLI args ─────────────────────────────────────────────
    let args = Args::parse()?;
    let sniper_wallet = Arc::new(read_keypair_file(&args.keypair_path)
        .map_err(|e| anyhow::anyhow!("Failed to read keypair from {}: {e}", args.keypair_path.display()))?);

    let wallet_pubkey = sniper_wallet.pubkey();
    info!("Wallet: {}", wallet_pubkey);
    info!("RPC: {}", args.rpc_url);
    info!("RPC WS: {}", args.rpc_ws);
    info!("Jito: {}", args.jito_endpoint);
    info!("Buy amount: {} SOL", args.buy_amount_sol);
    info!("Jito base tip: {} SOL", args.jito_base_tip_sol);
    info!("Jito max tip: {} SOL", args.jito_max_tip_sol);
    if args.creator_bounty_sol > 0.0 {
        info!("💎 Creator bounty: {} SOL", args.creator_bounty_sol);
    } else {
        info!("Creator bounty: disabled");
    }
    if args.copy_trade_sol > 0.0 {
        info!("🎯 Copy-trade size: {} SOL", args.copy_trade_sol);
    } else {
        info!("Copy-trade: disabled");
    }
    info!("Min risk score: {}", args.min_risk_score);
    info!("Brain URL: {}", args.brain_url);
    if !args.wallet_pool.is_empty() {
        info!("🔄 Wallet pool: {} wallets", args.wallet_pool.len());
    }

    // ── Initialize RPC client (processed commitment for speed) ──────
    let rpc_client = Arc::new(RpcClient::new_with_commitment(
        args.rpc_url.clone(),
        CommitmentConfig::processed(),
    ));

    // Fetch wallet balance
    let balance = rpc_client.get_balance(&wallet_pubkey).await?;
    info!("Wallet balance: {:.4} SOL", balance as f64 / 1e9);

    let buy_amount_lamports = (args.buy_amount_sol * 1e9) as u64;
    let jito_base_tip_lamports = (args.jito_base_tip_sol * 1e9) as u64;
    let jito_max_tip_lamports = (args.jito_max_tip_sol * 1e9) as u64;
    let creator_bounty_lamports = (args.creator_bounty_sol * 1e9) as u64;
    let copy_trade_lamports = (args.copy_trade_sol * 1e9) as u64;

    if balance < buy_amount_lamports + jito_max_tip_lamports + creator_bounty_lamports + 10_000_000 {
        warn!(
            "Low balance: {:.4} SOL (need ≥ {:.4} SOL for buy + tip + bounty + rent)",
            balance as f64 / 1e9,
            (buy_amount_lamports + jito_max_tip_lamports + creator_bounty_lamports + 10_000_000) as f64 / 1e9,
        );
    }

    // ── Initialize wallet rotation pool ──────────────────────────
    let wallet_pool: Arc<WalletRotationPool> = if args.wallet_pool.is_empty() {
        Arc::new(WalletRotationPool::from_single(sniper_wallet.clone()))
    } else {
        let extra: Vec<std::path::PathBuf> = args.wallet_pool.iter().map(std::path::PathBuf::from).collect();
        Arc::new(WalletRotationPool::from_existing(sniper_wallet.clone(), &extra)?)
    };

    // ── Shared state ───────────────────────────────────────────────
    let state = Arc::new(AppState {
        rpc_client: rpc_client.clone(),
        sniper_wallet: sniper_wallet.clone(),
        blockhash: Arc::new(Mutex::new((
            solana_sdk::hash::Hash::default(),
            std::time::Instant::now(),
        ))),
        buy_amount_lamports,
        jito_base_tip_lamports,
        jito_max_tip_lamports,
        creator_bounty_lamports,
        copy_trade_lamports,
        min_risk_score: args.min_risk_score,
        dynamic_config: Arc::new(RwLock::new(DynamicConfig::default())),
        wallet_pool: wallet_pool.clone(),
        auth_token: if args.tracker_api_token.is_empty() { None } else { Some(args.tracker_api_token.clone()) },
        snipe_count: Arc::new(Mutex::new(0)),
        error_count: Arc::new(Mutex::new(0)),
    });

    // ── Channel: sniper detection → execution ──────────────────────
    let (token_tx, mut token_rx) = mpsc::unbounded_channel::<sniper::TokenDetection>();

    // ── Spawn blockhash refresh worker ─────────────────────────────
    let blockhash_state = state.clone();
    let blockhash_client = rpc_client.clone();
    tokio::spawn(async move {
        let mut worker = BlockhashWorker::new(blockhash_client, Duration::from_millis(2000));
        let blockhash_arc = blockhash_state.blockhash.clone();
        loop {
            match worker.fetch_blockhash().await {
                Ok(hash) => {
                    let mut guard = blockhash_arc.lock().await;
                    *guard = (hash, std::time::Instant::now());
                }
                Err(e) => {
                    warn!("Blockhash refresh failed: {e}");
                }
            }
        }
    });

    // ── Spawn WebSocket sniper listener ────────────────────────────
    let sniper_ws_url = args.rpc_ws.clone();
    tokio::spawn(async move {
        let config = SniperConfig::default();
        let mut attempt: u32 = 0;
        loop {
            match sniper::listen_pool_creations(&sniper_ws_url, &config, &token_tx).await {
                Ok(()) => info!("WebSocket listener exited cleanly"),
                Err(e) => {
                    attempt += 1;
                    let backoff_ms = sniper::reconnect_backoff_ms(attempt).min(60_000);
                    error!(
                        "WebSocket listener error: {e} — reconnecting in {}s (attempt {attempt})",
                        backoff_ms / 1000,
                    );
                    tokio::time::sleep(Duration::from_millis(backoff_ms)).await;
                }
            }
        }
    });

    // ── Extract jito_endpoint before it's moved into closures ──
    let jito_endpoint = args.jito_endpoint.clone();

    // ── Smart Money Copy-Trading Engine ────────────────────────────
    let (sm_tracker, _wallet_changed) = SmartMoneyTracker::new(args.copy_trade_sol);
    let smart_money_tracker = Arc::new(sm_tracker);

    let (copy_tx, mut copy_rx) = mpsc::unbounded_channel::<CopyTradeDetection>();

    let copy_tracker = smart_money_tracker.clone();
    let copy_ws_url = args.rpc_ws.clone();
    let copy_rpc_url = args.rpc_url.clone();
    tokio::spawn(async move {
        let mut attempt: u32 = 0;
        loop {
            // subscribe() creates a fresh receiver at the CURRENT version —
            // avoids the stale-version infinite-reconnect bug from cloning
            let fresh_rx = copy_tracker.subscribe();
            match tracker::listen_wallet_transactions(
                &copy_ws_url,
                &copy_rpc_url,
                copy_tracker.clone(),
                copy_tx.clone(),
                fresh_rx,
            )
            .await
            {
                Ok(()) => info!("SmartMoneyTracker: listener exited cleanly"),
                Err(e) => {
                    attempt += 1;
                    let backoff_ms = (2000u64 * (1u64 << attempt.min(8))).min(60_000);
                    error!(
                        "SmartMoneyTracker: listener error — reconnecting in {}s (attempt {attempt}): {e}",
                        backoff_ms / 1000,
                    );
                    tokio::time::sleep(Duration::from_millis(backoff_ms)).await;
                }
            }
        }
    });

    // ── Seed tracked wallets from CLI/env ───────────────────────
    for wallet_str in &args.track_wallets {
        match solana_sdk::pubkey::Pubkey::try_from(wallet_str.as_str()) {
            Ok(pk) => {
                smart_money_tracker.add_target_wallet(pk).await;
            }
            Err(e) => {
                warn!("Invalid track-wallet '{}': {e}", wallet_str);
            }
        }
    }

    info!("SmartMoneyTracker: engine online — watching {} wallets",
        smart_money_tracker.wallet_count().await);

    // ── Spawn Tracker REST API ──────────────────────────────────
    let api_tracker = smart_money_tracker.clone();
    let api_port = args.tracker_api_port;
    let api_token = if args.tracker_api_token.is_empty() { None } else { Some(args.tracker_api_token.clone()) };
    tokio::spawn(async move {
        let router = tracker_api::build_router(api_tracker, api_token);
        let addr = format!("0.0.0.0:{api_port}");
        let listener = match tokio::net::TcpListener::bind(&addr).await {
            Ok(l) => l,
            Err(e) => {
                tracing::error!("Tracker API: failed to bind {addr}: {e}");
                return;
            }
        };
        info!("🌐 Tracker API: listening on http://{addr}");
        if let Err(e) = axum::serve(listener, router).await {
            tracing::error!("Tracker API: server error: {e}");
        }
    });

    // ── Spawn ConfigWorker (polls brain bridge every 5s) ──────────
    let config_lock = state.dynamic_config.clone();
    let snipe_count = state.snipe_count.clone();
    let error_count = state.error_count.clone();
    let brain_url = args.brain_url.clone();
    let cw_rpc = state.rpc_client.clone();
    let cw_pubkey = state.sniper_wallet.pubkey();
    tokio::spawn(async move {
        let worker = ConfigWorker::new(
            brain_url, config_lock, snipe_count, error_count,
            cw_rpc, cw_pubkey,
        );
        worker.run().await;
    });
    info!("🧠 ConfigWorker: spawned — polling brain bridge");

    // ── Spawn Copy-Trade Execution Engine ───────────────────────
    let copy_state = state.clone();

    // ── Shared dynamic tip state (updated by TipOptimizer) ──
    let tip_lock: Arc<tokio::sync::RwLock<u64>> = Arc::new(tokio::sync::RwLock::new(jito_base_tip_lamports));

    let copy_tip_lock = tip_lock.clone();
    let je_copy = jito_endpoint.clone();
    tokio::spawn(async move {
        let security_matrix = AntiRugMatrix::new(copy_state.rpc_client.clone());
        let jito_config = JitoConfig {
            endpoint: je_copy.clone(),
            base_tip_lamports: jito_base_tip_lamports,
            max_tip_lamports: jito_max_tip_lamports,
            creator_bounty_lamports: 0, // copy trades don't pay creator bounty
        };
        let jito_builder = JitoBundleBuilder::new(jito_config, copy_state.rpc_client.clone(), copy_tip_lock);

        while let Some(detection) = copy_rx.recv().await {
            let state = copy_state.clone();
            let blockhash_arc = state.blockhash.clone();
            // Rotate wallet for stealth — each copy-trade uses a different wallet
            let wallet = state.wallet_pool.next();
            let security = security_matrix.clone();
            let jito = jito_builder.clone();

            tokio::spawn(async move {
                info!(
                    "🎯 COPY-TRADE: tracked wallet triggered buy on {} (tx: {})",
                    &detection.token_mint[..16],
                    &detection.tx_signature[..16],
                );

                // ── Security check ────────────────────────────────
                let risk = match security.evaluate(&detection.token_mint).await {
                    Ok(score) => score,
                    Err(e) => {
                        error!("Copy-trade security check failed: {e}");
                        let mut errs = state.error_count.lock().await;
                        *errs += 1;
                        return;
                    }
                };

                // ── Dynamic config: read live risk threshold + buy amount ──
                let (min_risk, copy_lamports) = {
                    let cfg = state.dynamic_config.read().await;
                    if cfg.pause_sniping {
                        warn!("⏸ COPY-TRADE SKIPPED: brain paused sniping");
                        return;
                    }
                    (cfg.min_risk_score, cfg.copy_trade_lamports())
                };

                if !risk.is_safe(min_risk) {
                    warn!(
                        "🚫 COPY-TRADE BLOCKED: {} risk {}/100 > threshold {}",
                        &detection.token_mint[..16], risk.score, min_risk,
                    );
                    return;
                }

                info!("✅ Copy-trade security passed — risk {}/100", risk.score);

                // ── Blockhash ─────────────────────────────────────
                let blockhash = {
                    let guard = blockhash_arc.lock().await;
                    guard.0
                };

                if blockhash == solana_sdk::hash::Hash::default() {
                    warn!("Blockhash not yet available — skipping copy-trade");
                    return;
                }

                // ── Execute copy-trade via Jito bundle ───────────
                // No creator bounty on copy trades (deployer already paid by original)
                match jito.build_and_send(
                    &blockhash,
                    &wallet,
                    &detection.token_mint,
                    copy_lamports,
                    None,  // no creator_wallet for copy trades
                    None,  // pool_ctx placeholder
                ).await {
                    Ok(bundle_id) => {
                        info!("🎯 COPY-TRADE EXECUTED! Bundle: {}", bundle_id);
                        let mut count = state.snipe_count.lock().await;
                        *count += 1;
                    }
                    Err(e) => {
                        error!("❌ Copy-trade failed: {e}");
                        let mut errs = state.error_count.lock().await;
                        *errs += 1;
                    }
                }
            });
        }
    });

    // ── Main loop: process token detections ────────────────────────
    let main_state = state.clone();
    info!("Sniper engine online — waiting for pool detections...");

    let je_main = jito_endpoint.clone();
    let engine_handle = tokio::spawn(async move {
        let security_matrix = AntiRugMatrix::new(main_state.rpc_client.clone());
        let jito_config = JitoConfig {
            endpoint: je_main.clone(),
            base_tip_lamports: jito_base_tip_lamports,
            max_tip_lamports: jito_max_tip_lamports,
            creator_bounty_lamports,
        };


        // ── Spawn Shadow Run TipOptimizer (background fee polling) ──
        let tip_optimizer = TipOptimizer::new(
            main_state.rpc_client.clone(),
            tip_lock.clone(),
            jito_base_tip_lamports,
            jito_max_tip_lamports,
        );
        tokio::spawn(async move {
            info!("🔄 TipOptimizer: started (interval=1500ms, base={}, max={})",
                jito_base_tip_lamports, jito_max_tip_lamports);
            tip_optimizer.run().await;
        });

        let jito_builder = JitoBundleBuilder::new(jito_config, main_state.rpc_client.clone(), tip_lock);

        while let Some(detection) = token_rx.recv().await {
            let state = main_state.clone();
            let rpc = state.rpc_client.clone();
            let blockhash_arc = state.blockhash.clone();
            let wallet = state.sniper_wallet.clone();
            let security = security_matrix.clone();
            let jito = jito_builder.clone();

            tokio::spawn(async move {
                info!(
                    "🟡 New pool detected: {} (DEX: {})",
                    &detection.token_mint[..16],
                    detection.dex_name()
                );

                // ── Step 1: Anti-Rug Security Check ────────────────
                let _rpc = rpc;
                let risk = match security.evaluate(&detection.token_mint).await {
                    Ok(score) => score,
                    Err(e) => {
                        error!("Security check failed for {}: {e}", &detection.token_mint[..12]);
                        let mut errs = state.error_count.lock().await;
                        *errs += 1;
                        return;
                    }
                };

                info!(
                    "🔍 Security: {} risk={}/100 freeze_auth={} mint_auth={} lp_locked={}",
                    &detection.token_mint[..16],
                    risk.score,
                    risk.freeze_authority.is_some(),
                    risk.mint_authority.is_some(),
                    risk.lp_locked,
                );

                // ── Dynamic config: read live risk threshold ─────
                let (min_risk, buy_lamports) = {
                    let cfg = state.dynamic_config.read().await;
                    if cfg.pause_sniping {
                        warn!("⏸ SNIPE SKIPPED: brain paused sniping");
                        return;
                    }
                    (cfg.min_risk_score, cfg.buy_amount_lamports())
                };

                if !risk.is_safe(min_risk) {
                    warn!(
                        "🚫 BLOCKED: {} risk {} above threshold {}",
                        &detection.token_mint[..16], risk.score, min_risk
                    );
                    return;
                }

                info!("✅ Security passed — risk score {}/100", risk.score);

                // ── Step 2: Get latest blockhash ───────────────────
                let blockhash = {
                    let guard = blockhash_arc.lock().await;
                    guard.0
                };

                if blockhash == solana_sdk::hash::Hash::default() {
                    warn!("Blockhash not yet available — skipping");
                    return;
                }

                // ── Step 3: Build + send Jito Bundle ───────────────
                // AlphaBump warning for Raydium/Meteora (creator extraction is probabilistic)
                if let Some(ref cw) = detection.creator_wallet {
                    if detection.dex != sniper::Dex::PumpFun && state.creator_bounty_lamports > 0 {
                        warn!(
                            "💎 AlphaBump: creator wallet {} extracted heuristically for {:?} — verify on-chain",
                            &cw[..16], detection.dex
                        );
                    }
                }

                // ── Build pool context for dynamic tip calculation ──
                let pool_ctx = jito::PoolContext {
                    liquidity_usd: 0.0,       // filled by Jupiter quote
                    estimated_roi_multiplier: 1.0, // filled by Jupiter quote
                    token_age_seconds: 0,     // freshly launched
                };

                match jito.build_and_send(
                    &blockhash,
                    &wallet,
                    &detection.token_mint,
                    buy_lamports,
                    detection.creator_wallet.as_deref(),
                    Some(&pool_ctx),
                ).await {
                    Ok(bundle_id) => {
                        info!("🎯 SNIPE EXECUTED! Bundle: {}", bundle_id);
                        let mut count = state.snipe_count.lock().await;
                        *count += 1;
                        info!("📊 Total snipes: {}", *count);
                    }
                    Err(e) => {
                        error!("❌ Snipe failed for {}: {e}", &detection.token_mint[..16]);
                        let mut errs = state.error_count.lock().await;
                        *errs += 1;
                    }
                }
            });
        }
    });

    // ── Graceful shutdown on SIGINT ────────────────────────────────
    tokio::select! {
        _ = signal::ctrl_c() => {
            info!("🛑 Shutting down...");
            let snipe_count = *state.snipe_count.lock().await;
            let error_count = *state.error_count.lock().await;
            info!("📊 Session stats: {} snipes, {} errors", snipe_count, error_count);
        }
        _ = engine_handle => {
            info!("Engine exited");
        }
    }

    Ok(())
}
