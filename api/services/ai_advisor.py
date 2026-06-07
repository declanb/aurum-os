"""
AI Advisor — generates trade recommendations by analyzing market trends,
technical indicators, and price action using GPT-4.

Returns actionable trade suggestions with entry, stop, target, and thesis.
All recommendations are advisory only — Guardian validation still required.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

from api.core.config import settings
from api.services import market_data
from api.services.playbooks import Playbook, get_playbook, format_briefing
from api.services.personal_edge import format_edge_block, score_match

logger = logging.getLogger(__name__)


def _calculate_indicators(candles: list[dict]) -> dict:
    """Calculate basic technical indicators from OHLC candles."""
    if not candles:
        return {}
    
    closes = [c["close"] for c in candles if c.get("close")]
    if not closes:
        return {}
    
    # Simple Moving Averages
    sma_20 = sum(closes[-20:]) / min(20, len(closes)) if len(closes) >= 20 else None
    sma_50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 50 else None
    
    # Price momentum
    current = closes[-1]
    prev_20 = closes[-20] if len(closes) >= 20 else closes[0]
    momentum_20 = ((current - prev_20) / prev_20) * 100 if prev_20 else 0
    
    # Recent volatility (std dev of last 20 closes)
    if len(closes) >= 20:
        recent = closes[-20:]
        mean = sum(recent) / len(recent)
        variance = sum((x - mean) ** 2 for x in recent) / len(recent)
        volatility = variance ** 0.5
    else:
        volatility = 0
    
    # Support/Resistance (simple: recent lows/highs)
    recent_candles = candles[-20:] if len(candles) >= 20 else candles
    recent_lows = [c["low"] for c in recent_candles if c.get("low")]
    recent_highs = [c["high"] for c in recent_candles if c.get("high")]
    
    return {
        "current_price": current,
        "sma_20": round(sma_20, 2) if sma_20 else None,
        "sma_50": round(sma_50, 2) if sma_50 else None,
        "momentum_20d_pct": round(momentum_20, 2),
        "volatility": round(volatility, 2),
        "support": round(min(recent_lows), 2) if recent_lows else None,
        "resistance": round(max(recent_highs), 2) if recent_highs else None,
        "trend": "bullish" if sma_20 and sma_50 and sma_20 > sma_50 else 
                 "bearish" if sma_20 and sma_50 and sma_20 < sma_50 else "neutral",
    }


async def generate_recommendations(
    symbols: Optional[list[str]] = None,
    max_recommendations: int = 3,
    playbook_id: Optional[str] = None,
    edge_fingerprint: Optional[dict] = None,
) -> list[dict]:
    """
    Analyze market data and generate AI-powered trade recommendations.

    The LLM is biased by:
      - A named trader playbook (Wyckoff, ICT, trend-follower, macro, Livermore).
      - The user's personal edge fingerprint (their own approved-trade history).

    Returns a list of recommendation dicts with:
    - symbol, direction, confidence_score (0-100)
    - entry_price, stop_price, target_price
    - thesis, reasoning, timeframe
    - playbook_used, edge_match_score (when available)
    """
    if symbols is None:
        symbols = ["BTC-USD", "ETH-USD", "SOL-USD"]

    playbook = get_playbook(playbook_id)

    # Check if either GitHub Models or OpenAI is available
    api_key = settings.OPENAI_API_KEY
    github_token = settings.GITHUB_TOKEN
    has_openai = api_key and api_key != "sk-..." and not api_key.startswith("sk-...")
    
    if not github_token and not has_openai:
        logger.warning("Neither GITHUB_TOKEN nor OPENAI_API_KEY configured — returning mock recommendations")
        return _decorate_mock(
            _generate_mock_recommendations(symbols[:max_recommendations]),
            playbook,
            edge_fingerprint,
        )

    recommendations = []

    for symbol in symbols[:max_recommendations]:
        try:
            # Fetch market data
            price_data = await market_data.get_price(symbol)
            candles_1h = await market_data.get_candles(symbol, timeframe="1h", count=100)
            candles_4h = await market_data.get_candles(symbol, timeframe="4h", count=50)

            if not candles_1h or not price_data:
                logger.warning(f"Insufficient data for {symbol}, skipping")
                continue

            # Calculate indicators
            indicators_1h = _calculate_indicators(candles_1h)
            indicators_4h = _calculate_indicators(candles_4h)

            # Analyze with GPT-4
            recommendation = await _analyze_with_gpt(
                symbol=symbol,
                price_data=price_data,
                indicators_1h=indicators_1h,
                indicators_4h=indicators_4h,
                candles_1h=candles_1h[-10:],  # Last 10 candles for context
                playbook=playbook,
                edge_fingerprint=edge_fingerprint,
            )

            if recommendation:
                recommendation["playbook_used"] = {
                    "id": playbook["id"],
                    "name": playbook["name"],
                    "trader": playbook["trader"],
                }
                recommendation["edge_match_score"] = score_match(recommendation, edge_fingerprint)
                recommendations.append(recommendation)

        except Exception as exc:
            logger.error(f"Failed to generate recommendation for {symbol}: {exc}")
            continue

    # If GPT returned no setups, that's a VALID signal ("no opportunities right now").
    # Only fall back to mock when there's no API key at all (handled at top of function).
    if not recommendations:
        logger.info(f"GPT found no high-confidence setups across {len(symbols)} symbols with {playbook['id']} playbook")

    return recommendations


def _decorate_mock(mocks: list[dict], playbook: Playbook, edge: Optional[dict]) -> list[dict]:
    """Attach playbook + edge-match metadata to mock recommendations."""
    for rec in mocks:
        rec["playbook_used"] = {
            "id": playbook["id"],
            "name": playbook["name"],
            "trader": playbook["trader"],
        }
        rec["edge_match_score"] = score_match(rec, edge)
    return mocks


async def _analyze_with_gpt(
    symbol: str,
    price_data: dict,
    indicators_1h: dict,
    indicators_4h: dict,
    candles_1h: list[dict],
    playbook: Playbook,
    edge_fingerprint: Optional[dict] = None,
) -> Optional[dict]:
    """Call GPT-4 to analyze market data and generate a trade recommendation."""
    try:
        from openai import AsyncOpenAI

        # GitHub Models (free with Copilot Enterprise) → OpenAI fallback → fail
        if settings.GITHUB_TOKEN:
            client = AsyncOpenAI(
                base_url="https://models.inference.ai.azure.com",
                api_key=settings.GITHUB_TOKEN,
            )
            logger.info(f"Using GitHub Models for {symbol}")
        else:
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            logger.info(f"Using OpenAI for {symbol}")

        # Build analysis prompt
        prompt = _build_analysis_prompt(symbol, price_data, indicators_1h, indicators_4h, candles_1h)

        system_blocks = [
            (
                "You are an expert crypto trading analyst for Aurum OS. "
                "Analyze market data and provide ONE actionable trade recommendation "
                "with specific entry, stop-loss, and take-profit levels. "
                "Focus on risk management: R:R must be \u22651.5. "
                "Return ONLY valid JSON matching the schema below.\n\n"
                "Schema:\n"
                "{\n"
                '  "symbol": "BTC-USD",\n'
                '  "direction": "LONG" | "SHORT" | null,\n'
                '  "confidence_score": 0-100,\n'
                '  "entry_price": number,\n'
                '  "stop_price": number,\n'
                '  "target_price": number,\n'
                '  "timeframe": "1h" | "4h" | "1d",\n'
                '  "thesis": "string (50-200 chars)",\n'
                '  "reasoning": "string (detailed analysis)",\n'
                '  "invalidation": "string (what proves this wrong)"\n'
                "}\n\n"
                "If no clear trade setup exists, return direction=null and confidence_score=0.\n\n"
                "EXECUTION CONSTRAINT (spot-only broker): Only LONG setups are actionable. "
                "If the only edge you see is a SHORT, return direction=null instead — do NOT "
                "force a LONG against the trend. Better to surface no setup than a bad one."
            ),
            format_briefing(playbook),
        ]
        edge_block = format_edge_block(edge_fingerprint)
        if edge_block:
            system_blocks.append(edge_block)

        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,  # Defaults to gpt-4o-mini (cost protection)
            messages=[
                {"role": "system", "content": "\n\n".join(system_blocks)},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        
        content = response.choices[0].message.content
        if not content:
            return None
        
        result = json.loads(content)
        
        # Validate and filter low-confidence recommendations
        if not result.get("direction") or result.get("confidence_score", 0) < 50:
            logger.info(f"{symbol}: No high-confidence setup (confidence={result.get('confidence_score')})")
            return None
        
        # Calculate R:R
        entry = result.get("entry_price", 0)
        stop = result.get("stop_price", 0)
        target = result.get("target_price", 0)
        risk = abs(entry - stop)
        reward = abs(target - entry)
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0
        
        result["risk_reward"] = rr_ratio
        result["generated_at"] = datetime.utcnow().isoformat()
        
        logger.info(
            f"Generated {result['direction']} recommendation for {symbol} "
            f"(confidence={result['confidence_score']}, R:R={rr_ratio})"
        )
        
        return result
        
    except Exception as exc:
        logger.error(f"GPT analysis failed for {symbol}: {exc}")
        return None


def _build_analysis_prompt(
    symbol: str,
    price_data: dict,
    indicators_1h: dict,
    indicators_4h: dict,
    candles_1h: list[dict],
) -> str:
    """Build the analysis prompt for GPT-4."""
    return f"""Analyze {symbol} and recommend a trade setup.

**Current Price Data:**
- Bid: {price_data.get('bid')}
- Ask: {price_data.get('ask')}
- Last: {price_data.get('last')}
- Spread: {price_data.get('spread')}

**1H Indicators:**
- Current: {indicators_1h.get('current_price')}
- SMA(20): {indicators_1h.get('sma_20')}
- SMA(50): {indicators_1h.get('sma_50')}
- Momentum (20d): {indicators_1h.get('momentum_20d_pct')}%
- Trend: {indicators_1h.get('trend')}
- Support: {indicators_1h.get('support')}
- Resistance: {indicators_1h.get('resistance')}

**4H Indicators:**
- Current: {indicators_4h.get('current_price')}
- SMA(20): {indicators_4h.get('sma_20')}
- SMA(50): {indicators_4h.get('sma_50')}
- Trend: {indicators_4h.get('trend')}

**Recent 1H Candles (last 10):**
{_format_candles(candles_1h)}

**Task:**
1. Identify trend alignment across timeframes
2. Look for support/resistance levels being tested
3. Check momentum and volatility
4. If a clear setup exists with R:R ≥ 1.5, provide entry/stop/target
5. If no clear setup, return direction=null

Focus on high-probability setups with clear invalidation."""


def _format_candles(candles: list[dict]) -> str:
    """Format candles for prompt context."""
    lines = []
    for c in candles[-10:]:
        lines.append(
            f"  O:{c.get('open'):.2f} H:{c.get('high'):.2f} "
            f"L:{c.get('low'):.2f} C:{c.get('close'):.2f}"
        )
    return "\n".join(lines)


def _generate_mock_recommendations(symbols: list[str]) -> list[dict]:
    """Generate mock recommendations when OpenAI API is not configured."""
    now = datetime.utcnow().isoformat()
    
    mock_data = [
        {
            "symbol": "BTC-USD",
            "direction": "LONG",
            "confidence_score": 75,
            "entry_price": 68500,
            "stop_price": 67200,
            "target_price": 71000,
            "timeframe": "4h",
            "thesis": "Bullish engulfing on 4H with momentum shift above SMA(50)",
            "reasoning": "Price bounced off key support at $67k with increasing volume. 4H SMA(20) crossed above SMA(50). RSI showing bullish divergence.",
            "invalidation": "Close below $67,000 invalidates the setup",
            "risk_reward": 1.92,
            "generated_at": now,
        },
        {
            "symbol": "ETH-USD",
            "direction": "SHORT",
            "confidence_score": 68,
            "entry_price": 3420,
            "stop_price": 3500,
            "target_price": 3260,
            "timeframe": "1h",
            "thesis": "Rejection at resistance with bearish divergence on 1H",
            "reasoning": "Failed to break $3,450 resistance three times. 1H momentum weakening with lower highs.",
            "invalidation": "Break and close above $3,500",
            "risk_reward": 2.0,
            "generated_at": now,
        },
        {
            "symbol": "SOL-USD",
            "direction": "LONG",
            "confidence_score": 82,
            "entry_price": 145,
            "stop_price": 141,
            "target_price": 153,
            "timeframe": "4h",
            "thesis": "Breakout above consolidation range with volume confirmation",
            "reasoning": "SOL broke above $143 resistance with 40% above-average volume. Strong momentum on 4H timeframe.",
            "invalidation": "Re-entry into range below $143",
            "risk_reward": 2.0,
            "generated_at": now,
        },
    ]
    
    return [rec for rec in mock_data if rec["symbol"] in symbols]
