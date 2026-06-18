//! Anti-Rug Security Matrix for Solana Meme Sniper Bot.
//!
//! Performs comprehensive token safety checks before execution:
//!   1. Freeze authority — can the owner freeze your tokens?
//!   2. Mint authority — can more tokens be minted (dilution)?
//!   3. LP lock status — is the liquidity pool locked?
//!   4. Supply concentration — how concentrated are top holders?
//!
//! Returns a `RiskReport` with a 0-100 score. Lower = safer.

use std::sync::Arc;

use anyhow::{Context, Result};
use solana_client::nonblocking::rpc_client::RpcClient;
use solana_sdk::{
    pubkey::Pubkey,
};
use serde_json::Value;
use tracing::{info, warn};

// ── Risk Report ───────────────────────────────────────────────────────────

/// Result of the anti-rug security check.
#[derive(Debug, Clone)]
pub struct RiskReport {
    /// Overall risk score 0-100. Lower = safer.
    pub score: u8,
    /// Does the token have a freeze authority?
    pub freeze_authority: Option<Pubkey>,
    /// Does the token have a mint authority?
    pub mint_authority: Option<Pubkey>,
    /// Is the LP pool locked (verified)?
    pub lp_locked: bool,
    /// Top holder concentration (as a percentage of total supply).
    pub top_holder_concentration_pct: f64,
    /// Risk verdict: "safe", "caution", "danger".
    pub verdict: RiskVerdict,
    /// Detailed notes on each check.
    pub checks: Vec<String>,
}

impl RiskReport {
    /// Returns true if the token is safe to snipe based on the given threshold.
    pub fn is_safe(&self, threshold: u8) -> bool {
        self.score <= threshold
    }
}

/// Human-readable risk classification.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RiskVerdict {
    Safe,
    Caution,
    Danger,
}

impl RiskVerdict {
    pub fn as_str(&self) -> &'static str {
        match self {
            RiskVerdict::Safe => "safe",
            RiskVerdict::Caution => "caution",
            RiskVerdict::Danger => "danger",
        }
    }
}

impl std::fmt::Display for RiskReport {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "RiskReport(score={}, verdict={}, freeze={}, mint={}, lp_locked={}, top_concentration={:.1}%)",
            self.score,
            self.verdict.as_str(),
            self.freeze_authority.is_some(),
            self.mint_authority.is_some(),
            self.lp_locked,
            self.top_holder_concentration_pct,
        )
    }
}

// ── Anti-Rug Matrix ──────────────────────────────────────────────────────

/// The Anti-Rug Security Matrix performs a battery of on-chain checks
/// to evaluate the safety of a newly launched token.
#[derive(Clone)]
pub struct AntiRugMatrix {
    rpc_client: Arc<RpcClient>,
}

impl AntiRugMatrix {
    /// Create a new security matrix with the given RPC client.
    pub fn new(rpc_client: Arc<RpcClient>) -> Self {
        Self { rpc_client }
    }

    /// Run the full anti-rug evaluation on a token mint address.
    ///
    /// Returns a `RiskReport` with a 0-100 risk score.
    pub async fn evaluate(&self, token_mint_str: &str) -> Result<RiskReport> {
        let token_mint = Pubkey::try_from(token_mint_str)
            .with_context(|| format!("Invalid token mint address: {token_mint_str}"))?;

        let mut score: u8 = 0;
        let mut checks: Vec<String> = Vec::new();

        // ── Check 1: Mint Account Analysis ──────────────────────────
        let (freeze_auth, mint_auth) = self.check_token_mint(&token_mint).await?;

        // Freeze authority: +25 risk if present
        if freeze_auth.is_some() {
            score += 25;
            checks.push(format!(
                "FREEZE: Token can be frozen by {}",
                freeze_auth.unwrap()
            ));
            warn!("🔴 FREEZE AUTHORITY: {} has freeze_auth={}", token_mint_str, freeze_auth.unwrap());
        } else {
            checks.push("OK: No freeze authority".to_string());
        }

        // Mint authority: +30 risk if present (can mint more tokens → dilution)
        if mint_auth.is_some() {
            score += 30;
            checks.push(format!(
                "MINT: New tokens can be minted by {}",
                mint_auth.unwrap()
            ));
            warn!("🔴 MINT AUTHORITY: {} has mint_auth={}", token_mint_str, mint_auth.unwrap());
        } else {
            checks.push("OK: Mint authority revoked".to_string());
        }

        // ── Check 2: LP Lock Verification ───────────────────────────
        let lp_locked = self.check_lp_locked(&token_mint).await?;

        if !lp_locked {
            score += 20;
            checks.push("LP_UNLOCKED: Liquidity can be removed by owner".to_string());
            warn!("🔴 UNLOCKED LP: {} has no verified LP lock", token_mint_str);
        } else {
            checks.push("OK: LP verified locked".to_string());
        }

        // ── Check 3: Supply Concentration ───────────────────────────
        let concentration = self.check_supply_concentration(&token_mint).await?;

        if concentration > 80.0 {
            score += 20;
            checks.push(format!(
                "CONCENTRATION: Top holders control {concentration:.1}% of supply"
            ));
            warn!("🔴 HIGH CONCENTRATION: {concentration:.1}% in top holders");
        } else if concentration > 50.0 {
            score += 10;
            checks.push(format!(
                "CONCENTRATION: Top holders at {concentration:.1}% (elevated)"
            ));
            warn!("🟡 ELEVATED CONCENTRATION: {concentration:.1}% in top holders");
        } else {
            checks.push("OK: Reasonable supply distribution".to_string());
        }

        // Cap score at 100
        score = score.min(100);

        // ── Determine verdict ────────────────────────────────────────
        let verdict = if score <= 30 {
            RiskVerdict::Safe
        } else if score <= 60 {
            RiskVerdict::Caution
        } else {
            RiskVerdict::Danger
        };

        let report = RiskReport {
            score,
            freeze_authority: freeze_auth,
            mint_authority: mint_auth,
            lp_locked,
            top_holder_concentration_pct: concentration,
            verdict,
            checks,
        };

        info!("🔍 {} → {}", token_mint_str, report);
        Ok(report)
    }

    // ── Individual checks ────────────────────────────────────────────

    /// Fetch and analyze the SPL Token Mint account for freeze and mint
    /// authority fields using RPC jsonParsed encoding (avoids Pack trait version conflicts).
    async fn check_token_mint(
        &self,
        mint: &Pubkey,
    ) -> Result<(Option<Pubkey>, Option<Pubkey>)> {
        let result: Value = self
            .rpc_client
            .send(
                solana_client::rpc_request::RpcRequest::Custom {
                    method: "getAccountInfo",
                },
                serde_json::json!([
                    mint.to_string(),
                    { "encoding": "jsonParsed" }
                ]),
            )
            .await
            .with_context(|| format!("Failed to fetch mint account for {mint}"))?;

        let parsed = result
            .get("value")
            .and_then(|v| v.get("data"))
            .and_then(|d| d.get("parsed"))
            .and_then(|p| p.get("info"))
            .context("Failed to parse mint account data")?;

        // Extract mint authority
        let mint_auth = parsed
            .get("mintAuthority")
            .and_then(|v| v.as_str())
            .and_then(|s| Pubkey::try_from(s).ok());

        // Extract freeze authority
        let freeze_auth = parsed
            .get("freezeAuthority")
            .and_then(|v| v.as_str())
            .and_then(|s| Pubkey::try_from(s).ok());

        Ok((freeze_auth, mint_auth))
    }

    /// Check if the token's liquidity pool LP tokens are locked.
    ///
    /// NOTE: Full on-chain LP lock verification requires correct pool address
    /// derivation which differs per DEX (Raydium uses OpenBook markets, Meteora
    /// uses DLMM pools, Pump.fun uses bonding curves). For the MVP, LP lock
    /// status defaults to `false` (conservative) and tokens with unlocked LP
    /// receive +20 risk points. Production should integrate RugCheck.xyz or
    /// SolSniffer API for comprehensive LP verification.
    async fn check_lp_locked(&self, _token_mint: &Pubkey) -> Result<bool> {
        // Conservative default: treat LP as unlocked until verified.
        // This ensures the risk matrix errs on the side of caution.
        Ok(false)
    }

    /// Check the supply concentration among top holders.
    ///
    /// Fetches the largest token accounts and computes what percentage
    /// of total supply is controlled by the top 10 holders.
    async fn check_supply_concentration(&self, mint: &Pubkey) -> Result<f64> {
        // Fetch largest token accounts via RPC
        let result: serde_json::Value = self
            .rpc_client
            .send(
                solana_client::rpc_request::RpcRequest::Custom {
                    method: "getTokenLargestAccounts",
                },
                serde_json::json!([mint.to_string()]),
            )
            .await
            .context("Failed to fetch token largest accounts")?;

        let accounts = result
            .get("value")
            .and_then(|v| v.as_array())
            .context("Unexpected response format from getTokenLargestAccounts")?;

        if accounts.is_empty() {
            return Ok(0.0);
        }

        // Sum the amount held by top N holders
        let top_n = accounts.len().min(10);
        let top_amount: f64 = accounts[..top_n]
            .iter()
            .filter_map(|a| {
                a.get("amount")
                    .and_then(|v| v.as_str())
                    .and_then(|s| s.parse::<f64>().ok())
            })
            .sum();

        // Fetch total supply from mint via jsonParsed RPC
        let mint_result: Value = self
            .rpc_client
            .send(
                solana_client::rpc_request::RpcRequest::Custom {
                    method: "getAccountInfo",
                },
                serde_json::json!([
                    mint.to_string(),
                    { "encoding": "jsonParsed" }
                ]),
            )
            .await
            .context("Failed to fetch mint account for supply")?;

        let total_supply: f64 = mint_result
            .get("value")
            .and_then(|v| v.get("data"))
            .and_then(|d| d.get("parsed"))
            .and_then(|p| p.get("info"))
            .and_then(|i| i.get("supply"))
            .and_then(|s| s.as_str())
            .and_then(|s| s.parse().ok())
            .unwrap_or(0.0);

        if total_supply == 0.0 {
            return Ok(0.0);
        }

        let concentration = (top_amount / total_supply) * 100.0;
        Ok((concentration * 100.0).round() / 100.0)
    }
}

// Local copy of the Raydium program ID for pool derivation
const RAYDIUM_LP_V4_PROGRAM: &str = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_risk_report_is_safe_threshold() {
        let report = RiskReport {
            score: 35,
            freeze_authority: None,
            mint_authority: None,
            lp_locked: true,
            top_holder_concentration_pct: 30.0,
            verdict: RiskVerdict::Caution,
            checks: vec![],
        };
        assert!(report.is_safe(40));
        assert!(!report.is_safe(30));
    }

    #[test]
    fn test_risk_report_danger_verdict() {
        let report = RiskReport {
            score: 75,
            freeze_authority: Some(Pubkey::new_unique()),
            mint_authority: Some(Pubkey::new_unique()),
            lp_locked: false,
            top_holder_concentration_pct: 85.0,
            verdict: RiskVerdict::Danger,
            checks: vec![],
        };
        assert!(!report.is_safe(60));
        assert_eq!(report.verdict, RiskVerdict::Danger);
    }

    #[test]
    fn test_serde_json_value_type() {
        // Verify serde_json Value type is available (used for RPC parsing)
        let v = serde_json::json!({"supply": "1000000000"});
        let supply = v.get("supply").and_then(|s| s.as_str()).unwrap();
        assert_eq!(supply, "1000000000");
    }
}
