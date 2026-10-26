"""Public trend context for the Helm advisor. Read-only. Never places orders.

Optional input to ``ai_advisor`` / the OpenAI Agents advisor / scout. The
result is prompt context and metadata on a recommendation dict. It does not
create an ExecutionTicket and it does not call Revolut X.

Sources (each failure is recorded and skipped — numbers are never invented):

- CoinGecko ``/global`` — BTC dominance and 24h total market-cap change. No key.
- alternative.me Fear & Greed. No key.
- CoinDesk RSS headlines. No key.
- X API v2 recent search — GET only, and only when ``X_BEARER_TOKEN`` is set.
  Redirects are disabled so the bearer token is not forwarded. This module
  never posts.

Env (see ``.env.example``):

- ``AURUM_TREND_CONTEXT`` — when true, ``ai_advisor`` loads this automatically.
- ``X_BEARER_TOKEN`` — optional read-only bearer. Not stored on Settings and
  never logged.
- ``X_TREND_QUERY`` — recent-search query. Default is a short English crypto query.

Regime hint rule (also stated in the prompt block):

- ``risk_on`` when 24h market-cap change >= +1% and Fear & Greed >= 55
- ``risk_off`` when 24h market-cap change <= -1% and Fear & Greed <= 40
- otherwise ``unclear`` (including when either input is missing)
- BTC dominance never sets the hint by itself
"""

from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import httpx

from api.core.config import settings

logger = logging.getLogger(__name__)

COINGECKO_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
COINDESK_RSS_URL = "https://www.coindesk.com/arc/outboundfeeds/rss/"
X_RECENT_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

_USER_AGENT = "aurum-os-trend-context/1.0"
_MAX_HEADLINES = 5
_MAX_POSTS = 8
_MAX_TEXT = 180


def _num(value: object) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        try:
            return round(float(value), 2)
        except ValueError:
            return None
    return None


def _as_int(value: object) -> Optional[int]:
    number = _num(value)
    if number is None:
        return None
    return int(round(number))


def _clip(text: object) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= _MAX_TEXT:
        return cleaned
    return cleaned[: _MAX_TEXT - 1].rstrip() + "…"


def _x_bearer_token() -> str:
    """Read the optional X bearer from the environment. Never log the value."""
    return os.environ.get("X_BEARER_TOKEN", "").strip()


def _empty_context() -> dict:
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "sources": [],
        "btc_dominance_pct": None,
        "market_cap_change_24h_pct": None,
        "fear_greed_value": None,
        "fear_greed_label": None,
        "headlines": [],
        "x_posts": [],
        "unavailable": [],
        "regime_hint": "unclear",
    }


def derive_regime(ctx: dict) -> str:
    """Map real fetched inputs to risk_on / risk_off / unclear.

    Dominance is intentionally ignored. Missing market-cap change or Fear &
    Greed yields ``unclear`` rather than a guessed regime.
    """
    change = _num(ctx.get("market_cap_change_24h_pct"))
    fear = _as_int(ctx.get("fear_greed_value"))
    if change is None or fear is None:
        return "unclear"
    if change >= 1.0 and fear >= 55:
        return "risk_on"
    if change <= -1.0 and fear <= 40:
        return "risk_off"
    return "unclear"


def format_block(ctx: Optional[dict]) -> str:
    """Render prompt text. Omits any metric that was not actually fetched."""
    if not ctx:
        return ""

    lines = [
        "PUBLIC TREND CONTEXT (read-only, advisory — not a broker order):",
        f"- As of: {ctx.get('as_of') or 'unknown'}",
    ]
    if ctx.get("btc_dominance_pct") is not None:
        lines.append(f"- BTC dominance: {ctx['btc_dominance_pct']}% (CoinGecko /global)")
    if ctx.get("market_cap_change_24h_pct") is not None:
        lines.append(
            "- 24h total market-cap change: "
            f"{ctx['market_cap_change_24h_pct']}% (CoinGecko /global)"
        )
    if ctx.get("fear_greed_value") is not None:
        label = ctx.get("fear_greed_label") or ""
        lines.append(
            f"- Fear & Greed: {ctx['fear_greed_value']} {label}".rstrip()
            + " (alternative.me)"
        )

    lines.append(f"- Regime hint: {ctx.get('regime_hint') or 'unclear'}")
    lines.append(
        "- Regime rule: risk_on only when 24h market-cap change >= +1% AND "
        "Fear & Greed >= 55; risk_off only when 24h market-cap change <= -1% "
        "AND Fear & Greed <= 40; otherwise unclear. BTC dominance never sets "
        "the hint by itself."
    )

    headlines = ctx.get("headlines") or []
    if headlines:
        lines.append("- Headlines:")
        for item in headlines[:_MAX_HEADLINES]:
            title = item.get("title") or ""
            source = item.get("source") or "headline"
            lines.append(f"  - {title} ({source})")

    posts = ctx.get("x_posts") or []
    if posts:
        lines.append("- Public X posts (recent search, read-only; not a recommendation):")
        for post in posts[:_MAX_POSTS]:
            lines.append(f"  - {post.get('text') or ''}")

    unavailable = ctx.get("unavailable") or []
    if unavailable:
        bits = [
            f"{item.get('source')} ({item.get('reason')})"
            for item in unavailable
            if item.get("source")
        ]
        if bits:
            lines.append("- Unavailable (omitted, do not invent): " + "; ".join(bits))

    lines.append(
        "Missing numbers were left out on purpose. Do not invent metrics, "
        "prices, or sentiment. Use this only as context for a spot LONG thesis. "
        "This context does not authorize a broker order, an ExecutionTicket, or a retry. "
        "If no playbook setup exists, return direction=null."
    )
    return "\n".join(lines)


def _mark_unavailable(ctx: dict, source: str, reason: str) -> None:
    ctx["unavailable"].append({"source": source, "reason": reason})


async def _get(client: httpx.AsyncClient, url: str, **kwargs: object) -> httpx.Response:
    """GET helper. Callers must not log the response body (it can echo tokens)."""
    return await client.get(url, **kwargs)  # type: ignore[arg-type]


async def _fill_coingecko(client: httpx.AsyncClient, ctx: dict) -> None:
    source = "coingecko_global"
    try:
        response = await _get(client, COINGECKO_GLOBAL_URL)
    except Exception as exc:
        logger.info("CoinGecko global unavailable: %s", type(exc).__name__)
        _mark_unavailable(ctx, source, "request failed")
        return
    if response.status_code != 200:
        logger.info("CoinGecko global unavailable: HTTP %s", response.status_code)
        _mark_unavailable(ctx, source, f"HTTP {response.status_code}")
        return
    try:
        payload = response.json()
    except Exception:
        _mark_unavailable(ctx, source, "invalid JSON")
        return

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}
    dominance = _num((data.get("market_cap_percentage") or {}).get("btc"))
    change = _num(data.get("market_cap_change_percentage_24h_usd"))
    if dominance is None and change is None:
        _mark_unavailable(ctx, source, "fields missing")
        return
    ctx["btc_dominance_pct"] = dominance
    ctx["market_cap_change_24h_pct"] = change
    ctx["sources"].append(source)


async def _fill_fear_greed(client: httpx.AsyncClient, ctx: dict) -> None:
    source = "fear_greed"
    try:
        response = await _get(client, FEAR_GREED_URL)
    except Exception as exc:
        logger.info("Fear & Greed unavailable: %s", type(exc).__name__)
        _mark_unavailable(ctx, source, "request failed")
        return
    if response.status_code != 200:
        logger.info("Fear & Greed unavailable: HTTP %s", response.status_code)
        _mark_unavailable(ctx, source, f"HTTP {response.status_code}")
        return
    try:
        payload = response.json()
    except Exception:
        _mark_unavailable(ctx, source, "invalid JSON")
        return

    rows = payload.get("data") if isinstance(payload, dict) else None
    row = rows[0] if isinstance(rows, list) and rows else {}
    value = _as_int(row.get("value") if isinstance(row, dict) else None)
    if value is None:
        _mark_unavailable(ctx, source, "fields missing")
        return
    label = row.get("value_classification") if isinstance(row, dict) else None
    ctx["fear_greed_value"] = value
    ctx["fear_greed_label"] = str(label).strip() if label else None
    ctx["sources"].append(source)


def _parse_headlines(xml_text: str) -> list[dict]:
    if len(xml_text) > 200_000:
        xml_text = xml_text[:200_000]
    root = ET.fromstring(xml_text)
    headlines: list[dict] = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag != "item":
            continue
        title = ""
        link = ""
        for child in list(element):
            child_tag = child.tag.rsplit("}", 1)[-1]
            if child_tag == "title" and child.text:
                title = _clip(child.text)
            elif child_tag == "link" and child.text:
                link = child.text.strip()
        if title:
            headlines.append({"title": title, "url": link, "source": "coindesk"})
        if len(headlines) >= _MAX_HEADLINES:
            break
    return headlines


async def _fill_headlines(client: httpx.AsyncClient, ctx: dict) -> None:
    source = "coindesk_rss"
    try:
        response = await _get(
            client,
            COINDESK_RSS_URL,
            headers={"Accept": "application/rss+xml, application/xml, text/xml, */*"},
        )
    except Exception as exc:
        logger.info("Headline feed unavailable: %s", type(exc).__name__)
        _mark_unavailable(ctx, source, "request failed")
        return
    if response.status_code != 200:
        logger.info("Headline feed unavailable: HTTP %s", response.status_code)
        _mark_unavailable(ctx, source, f"HTTP {response.status_code}")
        return
    try:
        headlines = _parse_headlines(response.text)
    except ET.ParseError:
        _mark_unavailable(ctx, source, "invalid XML")
        return
    if not headlines:
        _mark_unavailable(ctx, source, "no items")
        return
    ctx["headlines"] = headlines
    ctx["sources"].append(source)


async def _fill_x(client: httpx.AsyncClient, ctx: dict) -> None:
    source = "x_recent_search"
    token = _x_bearer_token()
    if not token:
        _mark_unavailable(ctx, source, "X_BEARER_TOKEN unset")
        return

    query = (settings.X_TREND_QUERY or "").strip()
    if not query:
        _mark_unavailable(ctx, source, "X_TREND_QUERY empty")
        return

    try:
        # follow_redirects stays off so the bearer header cannot leave api.twitter.com.
        response = await _get(
            client,
            X_RECENT_SEARCH_URL,
            params={
                "query": query,
                "max_results": 10,
                "tweet.fields": "created_at",
            },
            headers={"Authorization": f"Bearer {token}"},
            follow_redirects=False,
        )
    except Exception as exc:
        logger.info("X recent search unavailable: %s", type(exc).__name__)
        _mark_unavailable(ctx, source, "request failed")
        return

    if response.status_code != 200:
        logger.info("X recent search unavailable: HTTP %s", response.status_code)
        _mark_unavailable(ctx, source, f"HTTP {response.status_code}")
        return

    try:
        payload = response.json()
    except Exception:
        _mark_unavailable(ctx, source, "invalid JSON")
        return

    rows = payload.get("data") if isinstance(payload, dict) else None
    posts: list[dict] = []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            text = _clip(row.get("text"))
            if not text:
                continue
            post_id = str(row.get("id") or "").strip()
            url = f"https://x.com/i/web/status/{post_id}" if post_id else ""
            posts.append({"text": text, "url": url})
            if len(posts) >= _MAX_POSTS:
                break
    if not posts:
        _mark_unavailable(ctx, source, "no posts")
        return
    ctx["x_posts"] = posts
    ctx["sources"].append(source)


async def load(client: Optional[httpx.AsyncClient] = None) -> dict:
    """Fetch public trend context. Network errors degrade to an empty read.

    Pass ``client`` in tests. Production creates a short-lived client.
    """
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(8.0, connect=4.0),
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
    try:
        ctx = _empty_context()
        await _fill_coingecko(client, ctx)
        await _fill_fear_greed(client, ctx)
        await _fill_headlines(client, ctx)
        await _fill_x(client, ctx)
        ctx["regime_hint"] = derive_regime(ctx)
        return ctx
    finally:
        if owns_client:
            await client.aclose()
