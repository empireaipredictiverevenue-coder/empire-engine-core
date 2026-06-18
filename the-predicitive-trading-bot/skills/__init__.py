"""Trading Bot Skills & Strategy Package."""
from .base import BaseSkill, SkillInput, SkillOutput, SkillMetrics, SkillContext
from .trading_skills import (
    TRADING_SKILL_CLASSES,
    register_trading_skills,
    get_trading_skill_names,
)
from .strategy import (
    StrategyResult,
    StrategyBase,
    StrategyRegistry,
    BUILTIN_STRATEGIES,
    MomentumStrategy,
    MeanReversionStrategy,
    BreakoutStrategy,
    register_builtin_strategies,
    get_strategy_names,
)
from .indicators import (
    calculate_indicators,
    calc_rsi,
    calc_macd,
    calc_moving_averages,
    calc_bollinger_bands,
    calc_vwap,
    calc_obv,
    calc_stochastic,
    calc_volatility,
    calc_sharpe,
    calc_max_drawdown,
    calc_momentum,
    detect_bollinger_band_patterns,
    detect_rsi_head_shoulders,
)
from .ai_analysis import (
    AI_SKILL_CLASSES,
    AIMarketAnalyzeSkill,
    AISentimentSkill,
    AITradingAdviseSkill,
    get_ai_skill_names,
)
from .risk_management import (
    PortfolioRiskManager,
    PortfolioRiskSkill,
    RiskReport,
    PositionRisk,
)
from .strategy_runner import (
    StrategyRunner,
)
from .strategy_optimizer import (
    StrategyOptimizer,
    HAS_SCIPY as HAS_SCIPY_OPTIMIZER,
)
from .strategy_backtest import (
    StrategyBacktester,
    BacktestResult,
    ComparisonResult,
)
from .market_regime import (
    MarketRegimeDetector,
    REGIME_TRENDING_UP,
    REGIME_TRENDING_DOWN,
    REGIME_RANGING,
    REGIME_VOLATILE,
    REGIME_CALM,
    REGIME_BREAKOUT,
)
from .adaptive_optimizer import (
    AdaptiveOptimizer,
)
from .vector_engine import (
    VectorEngine,
    calc_rsi_2d,
    calc_macd_2d,
    calc_ma_2d,
    calc_bb_2d,
    calc_volatility_2d,
    calc_sharpe_2d,
    calc_momentum_2d,
)
from .public_api import (
    UserStore,
    get_user_store,
    verify_solana_signature,
)
from .websocket_manager import (
    ConnectionManager,
    get_ws_manager,
)
from .sniper_worker import (
    AutoSnipeEngine,
    get_sniper_engine,
)

__all__ = [
    "BaseSkill", "SkillInput", "SkillOutput", "SkillMetrics", "SkillContext",
    "TRADING_SKILL_CLASSES",
    "register_trading_skills",
    "get_trading_skill_names",
    "StrategyResult", "StrategyBase", "StrategyRegistry",
    "BUILTIN_STRATEGIES",
    "MomentumStrategy", "MeanReversionStrategy", "BreakoutStrategy",
    "register_builtin_strategies",
    "get_strategy_names",
    "calculate_indicators", "calc_rsi", "calc_macd", "calc_moving_averages",
    "calc_bollinger_bands", "calc_vwap", "calc_obv", "calc_stochastic",
    "calc_volatility", "calc_sharpe", "calc_max_drawdown", "calc_momentum",
    "detect_bollinger_band_patterns", "detect_rsi_head_shoulders",
    "AI_SKILL_CLASSES",
    "AIMarketAnalyzeSkill", "AISentimentSkill", "AITradingAdviseSkill",
    "get_ai_skill_names",
    "PortfolioRiskManager", "PortfolioRiskSkill", "RiskReport", "PositionRisk",
    "StrategyRunner",
    "StrategyOptimizer",
    "HAS_SCIPY_OPTIMIZER",
    "StrategyBacktester",
    "BacktestResult",
    "ComparisonResult",
    "MarketRegimeDetector",
    "AdaptiveOptimizer",
    "REGIME_TRENDING_UP", "REGIME_TRENDING_DOWN", "REGIME_RANGING",
    "REGIME_VOLATILE", "REGIME_CALM", "REGIME_BREAKOUT",
    "VectorEngine",
    "calc_rsi_2d", "calc_macd_2d", "calc_ma_2d", "calc_bb_2d",
    "calc_volatility_2d", "calc_sharpe_2d", "calc_momentum_2d",
    "UserStore", "get_user_store", "verify_solana_signature",    "ConnectionManager",
    "get_ws_manager",
    "AutoSnipeEngine",
    "get_sniper_engine",
]
