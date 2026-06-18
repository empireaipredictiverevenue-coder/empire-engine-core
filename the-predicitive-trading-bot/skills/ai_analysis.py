"""
PREDICITIVE TRADING BOT · AI/LLM ANALYSIS SKILLS
==================================================
AI-powered market analysis skills adapted from QuantMuse.

Uses OpenAI-compatible APIs for:
  - Market regime analysis (trend, volatility, risk)
  - Sentiment scoring from news/text
  - Consolidated trading advice

No LangChain dependency — direct HTTP calls to OpenAI API.
Graceful fallback to heuristic analysis when no API key is set.

Architecture:
  - _AIClient: shared HTTP client for LLM API calls
  - AIMarketAnalyzeSkill: LLM-powered market analysis
  - AISentimentSkill: sentiment from news headlines/text
  - AITradingAdviseSkill: consolidated AI trading advice
"""

import json
import time
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional, Any

import httpx

from .base import BaseSkill, SkillInput, SkillOutput, SkillMetrics

log = logging.getLogger("trading.ai")


# ═════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o-mini")  # default: fast + cheap
AI_MAX_TOKENS = int(os.environ.get("AI_MAX_TOKENS", "500"))
AI_TEMPERATURE = float(os.environ.get("AI_TEMPERATURE", "0.3"))
AI_TIMEOUT_SEC = int(os.environ.get("AI_TIMEOUT_SEC", "30"))


# ═════════════════════════════════════════════════════════════════════════
# AI CLIENT
# ═════════════════════════════════════════════════════════════════════════


class _AIClient:
    """Lightweight OpenAI-compatible client shared across AI skills.

    No LangChain dependency — direct HTTP calls.
    """

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=AI_TIMEOUT_SEC)
        self._available = bool(OPENAI_API_KEY)

    @property
    def available(self) -> bool:
        return self._available

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Send a chat completion request. Returns response text or None."""
        if not self._available:
            return None

        temp = temperature if temperature is not None else AI_TEMPERATURE
        tokens = max_tokens if max_tokens is not None else AI_MAX_TOKENS

        try:
            r = await self._http.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temp,
                    "max_tokens": tokens,
                },
            )
            if r.status_code != 200:
                log.warning(f"[ai] API error {r.status_code}: {r.text[:200]}")
                return None

            data = r.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else None

        except Exception as e:
            log.warning(f"[ai] chat request failed: {e}")
            return None

    async def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> Optional[dict]:
        """Send a chat request expecting JSON response. Returns parsed dict or None."""
        text = await self.chat(
            system_prompt=system_prompt + "\nRespond ONLY with valid JSON, no markdown.",
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=AI_MAX_TOKENS * 2,
        )
        if not text:
            return None

        # Strip markdown code fences if present (handles ```json, ```, etc.)
        text = text.strip()
        if text.startswith("```"):
            # Remove opening fence line (``` or ```json)
            first_newline = text.find("\n")
            if first_newline != -1:
                text = text[first_newline + 1:]
            else:
                text = text[3:]
            # Remove closing fence
            if text.rstrip().endswith("```"):
                text = text.rstrip()[:-3]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            log.warning(f"[ai] failed to parse JSON response: {text[:200]}")
            return None

    async def close(self):
        await self._http.aclose()


_client: Optional[_AIClient] = None


def _get_ai() -> _AIClient:
    global _client
    if _client is None:
        _client = _AIClient()
    return _client


# ═════════════════════════════════════════════════════════════════════════
# HEURISTIC FALLBACKS (when no API key / API fails)
# ═════════════════════════════════════════════════════════════════════════


def _heuristic_market_analysis(symbol: str, market: str = "crypto") -> dict:
    """Simple heuristic market analysis when AI is unavailable."""
    return {
        "regime": "neutral",
        "trend": "mixed",
        "volatility": "medium",
        "risk_level": "medium",
        "key_drivers": [
            "Macro conditions",
            "Liquidity flows",
            "Market structure",
        ],
        "attention_points": [
            "Monitor volume for breakout confirmation",
            "Watch funding rates for positioning extremes",
        ],
        "opportunity_score": 50,
        "confidence": 0.5,
        "mode": "heuristic",
    }


def _heuristic_sentiment(text: str) -> dict:
    """Simple keyword-based sentiment when AI is unavailable.

    Adapted from QuantMuse's financial keyword dictionary.
    """
    positive_words = {
        "bullish", "breakout", "surge", "rally", "upgrade", "outperform",
        "strong", "growth", "profit", "buy", "long", "accumulate",
        "positive", "beat", "exceed", "record", "high",
    }
    negative_words = {
        "bearish", "crash", "dump", "selloff", "downgrade", "underperform",
        "weak", "decline", "loss", "sell", "short", "distribution",
        "negative", "miss", "low", "fear", "panic", "risk",
    }

    text_lower = text.lower()
    words = set(text_lower.split())

    pos_count = len(words & positive_words)
    neg_count = len(words & negative_words)
    total = pos_count + neg_count

    if total == 0:
        score = 0.0
    else:
        score = (pos_count - neg_count) / total

    return {
        "sentiment_score": round(score, 3),
        "confidence": round(min(1.0, max(0.0, total / 10)), 4),
        "keywords": list(words & (positive_words | negative_words)),
        "mode": "heuristic",
    }


# ═════════════════════════════════════════════════════════════════════════
# 1. AI MARKET ANALYZE SKILL
# ═════════════════════════════════════════════════════════════════════════


class AIMarketAnalyzeSkill(BaseSkill):
    """AI-powered market analysis using LLM.

    Adapted from QuantMuse LangChainAgent's market_analysis tool.
    """
    name = "trading.ai.market.analyze"
    version = "1.0.0"
    description = "AI-powered market analysis — regime, trend, volatility, risk, opportunities"
    tags = ["domain:trading", "mode:analysis", "ai:enhanced", "ai:market"]
    timeout_seconds = 35.0

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("symbol"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        _started = time.time()
        symbol = input.params["symbol"]
        market = input.params.get("market", "crypto")
        context = input.params.get("context", "")

        ai = _get_ai()

        if ai.available:
            system = (
                "You are an expert financial analyst and quantitative trader. "
                "Analyze the given market/symbol and return a JSON object with: "
                "regime (string: bull/bear/neutral), trend (string: upward/downward/mixed), "
                "volatility (string: low/medium/high/extreme), risk_level (string), "
                "key_drivers (array of 3-5 strings), attention_points (array of 2-4 strings), "
                "opportunity_score (int 0-100), confidence (float 0-1). "
                "Be concise and data-driven."
            )
            user = f"Analyze {symbol} in the {market} market."
            if context:
                user += f"\nAdditional context: {context}"

            result = await ai.chat_json(system, user)
            if result:
                result["mode"] = "ai"
                result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
                elapsed_ms = int((time.time() - _started) * 1000)
                return SkillOutput(
                    success=True,
                    data=result,
                    metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=1),
                )

        # Fallback to heuristic
        result = _heuristic_market_analysis(symbol, market)
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        elapsed_ms = int((time.time() - _started) * 1000)
        return SkillOutput(
            success=True,
            data=result,
            metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=0),
        )


# ═════════════════════════════════════════════════════════════════════════
# 2. AI SENTIMENT SKILL
# ═════════════════════════════════════════════════════════════════════════


class AISentimentSkill(BaseSkill):
    """AI-powered sentiment analysis from news text or headlines.

    Adapted from QuantMuse SentimentAnalyzer.
    """
    name = "trading.ai.sentiment"
    version = "1.0.0"
    description = "AI sentiment analysis — score, confidence, keywords from news/text"
    tags = ["domain:trading", "mode:analysis", "ai:enhanced", "ai:sentiment"]
    timeout_seconds = 30.0

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("text"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        _started = time.time()
        text = input.params["text"]
        symbol = input.params.get("symbol", "")

        ai = _get_ai()

        if ai.available:
            system = (
                "You are a financial sentiment analyst. "
                "Analyze the given text and return a JSON object with: "
                "sentiment_score (float -1 to 1, where -1=very negative, 1=very positive), "
                "confidence (float 0-1), keywords (array of important financial terms), "
                "market_impact (short string describing potential impact), "
                "summary (one-sentence summary). "
                "Focus on market-moving information."
            )
            symbol_hint = f" for {symbol}" if symbol else ""
            user = f"Analyze sentiment{symbol_hint}:\n\n{text[:2000]}"

            result = await ai.chat_json(system, user)
            if result:
                result["mode"] = "ai"
                result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
                if symbol:
                    result["symbol"] = symbol
                elapsed_ms = int((time.time() - _started) * 1000)
                return SkillOutput(
                    success=True,
                    data=result,
                    metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=1),
                )

        # Fallback to keyword-based
        result = _heuristic_sentiment(text)
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        if symbol:
            result["symbol"] = symbol
        elapsed_ms = int((time.time() - _started) * 1000)
        return SkillOutput(
            success=True,
            data=result,
            metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=0),
        )


# ═════════════════════════════════════════════════════════════════════════
# 3. AI TRADING ADVISE SKILL
# ═════════════════════════════════════════════════════════════════════════


class AITradingAdviseSkill(BaseSkill):
    """Consolidated AI trading advice — signals, risk, portfolio guidance.

    Adapted from QuantMuse LangChainAgent's strategy_recommendation flow.
    """
    name = "trading.ai.advise"
    version = "1.0.0"
    description = "AI trading advice — consolidated signals, risk, portfolio guidance"
    tags = ["domain:trading", "mode:analysis", "ai:enhanced", "ai:advisory"]
    timeout_seconds = 35.0

    async def validate(self, input: SkillInput) -> bool:
        return bool(input.params.get("symbol"))

    async def execute(self, input: SkillInput) -> SkillOutput:
        _started = time.time()
        symbol = input.params["symbol"]
        market_analysis = input.params.get("market_analysis", {})
        indicators = input.params.get("indicators", {})
        risk_profile = input.params.get("risk_profile", "moderate")

        ai = _get_ai()

        if ai.available:
            # Build context from available data
            context_parts = [f"Symbol: {symbol}"]
            if market_analysis:
                context_parts.append(
                    f"Market: regime={market_analysis.get('regime','unknown')}, "
                    f"trend={market_analysis.get('trend','unknown')}"
                )
            if indicators:
                rsi = indicators.get("RSI", {}).get("value", "N/A")
                macd = indicators.get("MACD", {}).get("signal_text", "N/A")
                context_parts.append(f"Technical: RSI={rsi}, MACD={macd}")
            context_parts.append(f"Risk profile: {risk_profile}")

            system = (
                "You are an expert trading advisor. Based on the provided context, "
                "return a JSON object with: "
                "action (string: buy/sell/hold), confidence (float 0-1), "
                "reasoning (1-2 sentence summary), risk_warnings (array of strings), "
                "position_suggestion (string: e.g. '10-15% of portfolio'), "
                "key_levels (object with support/resistance as arrays of numbers), "
                "time_horizon (string: scalping/swing/position). "
                "Be conservative — prioritize capital preservation."
            )
            user = "\n".join(context_parts)

            result = await ai.chat_json(system, user)
            if result:
                result["mode"] = "ai"
                result["symbol"] = symbol
                result["advised_at"] = datetime.now(timezone.utc).isoformat()
                elapsed_ms = int((time.time() - _started) * 1000)
                return SkillOutput(
                    success=True,
                    data=result,
                    metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=1),
                )

        # Fallback heuristic advice
        advice = {
            "action": "hold",
            "confidence": 0.5,
            "reasoning": "AI unavailable — returning conservative default. "
                         "Monitor market structure and await confirmation signals.",
            "risk_warnings": [
                "AI analysis unavailable — manual review recommended",
                "Defaulting to capital preservation posture",
            ],
            "position_suggestion": "5% of portfolio",
            "key_levels": {"support": [], "resistance": []},
            "time_horizon": "swing",
            "mode": "heuristic",
            "symbol": symbol,
            "advised_at": datetime.now(timezone.utc).isoformat(),
        }
        elapsed_ms = int((time.time() - _started) * 1000)
        return SkillOutput(
            success=True,
            data=advice,
            metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=0),
        )


# ═════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL SKILL LIST (for registration)
# ═════════════════════════════════════════════════════════════════════════

AI_SKILL_CLASSES = [
    AIMarketAnalyzeSkill,
    AISentimentSkill,
    AITradingAdviseSkill,
]


def get_ai_skill_names() -> list[str]:
    """Return all AI skill names."""
    return [cls.name for cls in AI_SKILL_CLASSES]
