//! ConfigWorker Fallback Test — e2e brain health check
//!
//! Runs only the ConfigWorker polling loop (no sniper, no security, no Jito)
//! so we can test the brain fallback in isolation.
//!
//! Usage:
//!   cargo run --example config_worker_test -- --brain-url http://localhost:8055
//!
//! Then kill the brain process, wait ~35s, and observe:
//!   - "BRAIN DOWN" warning log
//!   - Config defaulting to `generated_by: static-fallback`

use std::sync::Arc;
use std::time::Duration;

use solana_sdk::pubkey::Pubkey;
use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::commitment_config::CommitmentConfig;
use tokio::sync::{Mutex, RwLock};
use tracing_subscriber::EnvFilter;

// Re-use the project's modules
use solana_meme_sniper::config::{ConfigWorker, DynamicConfig};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| EnvFilter::new("info,solana_meme_sniper=debug")),
        )
        .with_target(false)
        .init();

    let args: Vec<String> = std::env::args().collect();

    let brain_url = if let Some(pos) = args.iter().position(|a| a == "--brain-url") {
        args.get(pos + 1).cloned().unwrap_or_else(|| "http://localhost:8055".to_string())
    } else {
        std::env::var("SNIPER_BRAIN_URL").unwrap_or_else(|_| "http://localhost:8055".to_string())
    };

    // Use mainnet-beta RPC — wallet balance fetch can fail gracefully
    let rpc_url = std::env::var("SOLANA_RPC_URL")
        .unwrap_or_else(|_| "https://api.mainnet-beta.solana.com".to_string());
    let rpc_client = Arc::new(RpcClient::new_with_commitment(
        rpc_url,
        CommitmentConfig::processed(),
    ));

    // Dummy pubkey — the RPC will just return 0 balance
    let dummy_pubkey = Pubkey::new_unique();

    let shared_config: Arc<RwLock<DynamicConfig>> = Arc::new(RwLock::new(DynamicConfig::default()));
    let snipe_count = Arc::new(Mutex::new(0u64));
    let error_count = Arc::new(Mutex::new(0u64));

    tracing::info!(
        "🧪 ConfigWorker Test: brain={brain_url} rpc=mainnet-beta pubkey={dummy_pubkey}"
    );
    tracing::info!("📍 To test fallback: start the brain, wait 10s, kill the brain, wait 35s");
    tracing::info!("   Watch for '🧠 BRAIN DOWN' warning followed by generated_by=static-fallback");

    let worker = ConfigWorker::new(
        brain_url,
        shared_config.clone(),
        snipe_count,
        error_count,
        rpc_client,
        dummy_pubkey,
    );

    // Spawn the worker
    let config_watch = shared_config.clone();
    let handle = tokio::spawn(worker.run());

    // Monitor config changes every 2 seconds
    let monitor = tokio::spawn(async move {
        let mut last_generated_by = String::new();
        loop {
            tokio::time::sleep(Duration::from_secs(2)).await;
            let cfg = config_watch.read().await;
            let gb = cfg.generated_by.clone();
            if gb != last_generated_by {
                tracing::info!(
                    "📋 Config update: generated_by={gb} reasoning={}",
                    &cfg.reasoning
                );
                last_generated_by = gb;
            }
        }
    });

    tokio::select! {
        _ = handle => {}
        _ = monitor => {}
        _ = tokio::signal::ctrl_c() => {
            tracing::info!("🛑 Shutting down test");
        }
    }

    Ok(())
}
