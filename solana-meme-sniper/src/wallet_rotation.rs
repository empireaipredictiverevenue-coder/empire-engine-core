//! Wallet Rotation Pool — conceals copy-trading footprint.
//!
//! Other bots watching the blockchain can detect pattern: "wallet X always
//! buys the same tokens as smart-money wallet Y moments after Y trades."
//! This module breaks that pattern by rotating through a pool of execution
//! wallets so each copy-trade comes from a different address.
//!
//! Strategy: round-robin via atomic counter. Each copy-trade uses the
//! next wallet in the pool, making it appear as independent traders.
//!
//! Usage:
//!   --wallet-pool /path/to/w1.json,/path/to/w2.json,/path/to/w3.json
//!   or
//!   WALLET_POOL=/path/to/w1.json,/path/to/w2.json

use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

use anyhow::Result;
use solana_sdk::signature::{read_keypair_file, Keypair, Signer};
use tracing::{debug, info};

// ── Wallet Rotation Pool ──────────────────────────────────────────────────

/// Thread-safe wallet pool for round-robin copy-trade execution.
///
/// Each call to `next()` returns the next wallet in the pool, wrapping
/// around to the start. The atomic counter is lock-free — zero contention
/// even under high-frequency copy-trade dispatch.
#[derive(Clone)]
pub struct WalletRotationPool {
    /// Pool wallets in rotation order.
    wallets: Arc<Vec<Arc<Keypair>>>,
    /// Atomic round-robin counter.
    counter: Arc<AtomicUsize>,
}

impl WalletRotationPool {
    /// Create a single-wallet pool from an existing keypair.
    ///
    /// Used as a fallback when no --wallet-pool is specified — the primary
    /// sniper wallet is the only wallet in the pool.
    pub fn from_single(wallet: Arc<Keypair>) -> Self {
        let pubkey = wallet.pubkey();
        info!("🔄 WalletRotationPool: single-wallet mode ({})", pubkey);
        Self {
            wallets: Arc::new(vec![wallet]),
            counter: Arc::new(AtomicUsize::new(0)),
        }
    }

    /// Create a pool from a pre-loaded primary wallet and additional
    /// keypair file paths (loaded from disk on demand).
    ///
    /// Avoids re-reading the primary keypair from disk — the pool's
    /// first wallet IS the passed `primary` `Arc<Keypair>`, so it
    /// shares the same heap allocation as `AppState::sniper_wallet`.
    pub fn from_existing(primary: Arc<Keypair>, extra_paths: &[PathBuf]) -> Result<Self> {
        let pubkey = primary.pubkey();
        let mut wallets: Vec<Arc<Keypair>> = vec![primary];

        for path in extra_paths {
            let keypair = read_keypair_file(path)
                .map_err(|e| anyhow::anyhow!(
                    "Failed to read wallet keypair from {}: {}", path.display(), e
                ))?;
            let pk = keypair.pubkey();
            info!("🔄 WalletRotationPool: loaded wallet {} from {}", pk, path.display());
            wallets.push(Arc::new(keypair));
        }

        info!(
            "🔄 WalletRotationPool: {} wallets loaded (incl. primary {})",
            wallets.len(), pubkey,
        );

        Ok(Self {
            wallets: Arc::new(wallets),
            counter: Arc::new(AtomicUsize::new(0)),
        })
    }

    /// Get the next wallet in round-robin order.
    ///
    /// Thread-safe, lock-free. Bumps the atomic counter on each call.
    /// Wraps around to the start after exhausting the pool.
    pub fn next(&self) -> Arc<Keypair> {
        let idx = self.counter.fetch_add(1, Ordering::Relaxed) % self.wallets.len();
        let wallet = self.wallets[idx].clone();

        debug!(
            "🔄 WalletRotationPool: rotated to wallet {}/{} ({})",
            idx + 1,
            self.wallets.len(),
            &wallet.pubkey().to_string()[..12],
        );

        wallet
    }

    /// Number of wallets in the pool.
    pub fn len(&self) -> usize {
        self.wallets.len()
    }

    /// Whether the pool has more than one wallet (i.e., rotation is active).
    pub fn is_rotating(&self) -> bool {
        self.wallets.len() > 1
    }

    /// Get a reference to all wallets in the pool.
    pub fn wallets(&self) -> &[Arc<Keypair>] {
        &self.wallets
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use solana_sdk::signature::Keypair;
    use std::sync::Arc;

    #[test]
    fn test_single_wallet_pool() {
        let kp = Arc::new(Keypair::new());
        let pool = WalletRotationPool::from_single(kp.clone());
        assert_eq!(pool.len(), 1);
        assert!(!pool.is_rotating());

        // Should always return the same wallet
        let w1 = pool.next();
        let w2 = pool.next();
        assert_eq!(w1.pubkey(), w2.pubkey());
    }

    #[test]
    fn test_round_robin_rotation() {
        let wallets: Vec<Arc<Keypair>> = (0..3)
            .map(|_| Arc::new(Keypair::new()))
            .collect();

        let pool = WalletRotationPool {
            wallets: Arc::new(wallets.clone()),
            counter: Arc::new(AtomicUsize::new(0)),
        };

        assert_eq!(pool.len(), 3);
        assert!(pool.is_rotating());

        // Round 1
        let w0 = pool.next();
        let w1 = pool.next();
        let w2 = pool.next();
        assert_eq!(w0.pubkey(), wallets[0].pubkey());
        assert_eq!(w1.pubkey(), wallets[1].pubkey());
        assert_eq!(w2.pubkey(), wallets[2].pubkey());

        // Round 2 — should wrap around
        let w3 = pool.next();
        assert_eq!(w3.pubkey(), wallets[0].pubkey());
    }

    #[test]
    fn test_concurrent_rotation() {
        use std::thread;

        let wallets: Vec<Arc<Keypair>> = (0..5)
            .map(|_| Arc::new(Keypair::new()))
            .collect();

        let pool = WalletRotationPool {
            wallets: Arc::new(wallets.clone()),
            counter: Arc::new(AtomicUsize::new(0)),
        };

        // Spawn threads that each call next() 20 times
        let mut handles = vec![];
        for _ in 0..4 {
            let pool_clone = pool.clone();
            handles.push(thread::spawn(move || {
                for _ in 0..20 {
                    let _w = pool_clone.next();
                }
            }));
        }

        for h in handles {
            h.join().unwrap();
        }

        // 4 threads × 20 calls = 80 total rotations
        // Counter should be at 80
        assert_eq!(pool.counter.load(Ordering::Relaxed), 80);
    }
}
