from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from decimal import Decimal

from analytics.business_logic import DashboardAnalytics
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

CACHE_TTL = int(os.getenv("AI_INSIGHTS_CACHE_SECONDS", "900"))  # 15 min for AI results
FALLBACK_CACHE_TTL = 60  # retry the AI soon, but don't hammer a rate-limited API
CACHE_VERSION = "v2"  # bump when the prompt or response shape changes

# Providers that can run without an API key (local or private gateway).
KEYLESS_PROVIDERS = {"ollama"}
OPENCLAW_PROVIDERS = {"openclaw", "crestodian"}
VALID_PRIORITIES = {"high", "medium", "low"}
MAX_RECOMMENDATIONS = 4

ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


# ---------------------------------------------------------------------------
# Formatting helpers (dates and currency are cleaned here, not left to the AI)
# ---------------------------------------------------------------------------
def _to_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _format_date(value):
    d = _to_date(value)
    return f"{d:%B} {d.day}, {d.year}" if d else None


def _period_label(start_date, end_date):
    start, end = _to_date(start_date), _to_date(end_date)
    if start and end:
        if start == end:
            return _format_date(start)
        if start.year == end.year:
            return f"{start:%B} {start.day} – {end:%B} {end.day}, {end.year}"
        return f"{_format_date(start)} – {_format_date(end)}"
    if start:
        return f"From {_format_date(start)}"
    if end:
        return f"Up to {_format_date(end)}"
    return None


def _replace_iso_date(match):
    try:
        d = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return match.group(0)
    return f"{d:%B} {d.day}, {d.year}"


def _humanize_text(value):
    """Make AI text safe to show: readable dates and Philippine peso signs."""
    text = ISO_DATE_RE.sub(_replace_iso_date, str(value))
    return text.replace("$", "₱")


def _build_key_metrics(snapshot):
    """Exact numbers for the dashboard card, taken from data (never from the AI)."""
    revenue = snapshot.get("revenue", {}) or {}
    outstanding = snapshot.get("outstanding", {}) or {}
    return {
        "total_revenue": _as_float(revenue.get("total_revenue")),
        "net_income": _as_float(revenue.get("net_income")),
        "collection_rate": _as_float(revenue.get("payment_collection_rate")),
        "outstanding": _as_float(outstanding.get("total_outstanding")),
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def generate_business_insights(start_date=None, end_date=None, stall=None):
    """Build business insights from dashboard metrics and optional AI provider."""
    snapshot = DashboardAnalytics.get_dashboard_summary(start_date, end_date, stall)

    # Key includes the snapshot, so new data produces a fresh result.
    cache_key = f"ai_insights:{CACHE_VERSION}:" + hashlib.sha256(
        json.dumps(
            {
                "s": str(start_date),
                "e": str(end_date),
                "stall": getattr(stall, "pk", None),
                "snap": snapshot,
            },
            default=str,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    cached = _cache_get(cache_key)
    if cached:
        return cached

    result = _call_ai_provider(snapshot, start_date, end_date, stall)
    if result:
        ttl = CACHE_TTL
    else:
        result = _build_fallback_insights(snapshot)
        ttl = FALLBACK_CACHE_TTL

    result["snapshot"] = snapshot
    result["metrics"] = _build_key_metrics(snapshot)
    result["period_label"] = _period_label(start_date, end_date)

    _cache_set(cache_key, result, ttl)
    return result


def _cache_get(key):
    try:
        return cache.get(key)
    except Exception:  # a cache outage must never break the dashboard
        logger.warning("AI insights: cache read failed", exc_info=True)
        return None


def _cache_set(key, value, ttl):
    try:
        cache.set(key, value, ttl)
    except Exception:
        logger.warning("AI insights: cache write failed", exc_info=True)


# ---------------------------------------------------------------------------
# AI provider
# ---------------------------------------------------------------------------
def _provider_config(provider):
    """Return (base_url, model, extra_headers) for the selected provider."""
    extra_headers = {}

    if provider == "ollama":
        base_url = os.getenv("AI_INSIGHTS_BASE_URL", "http://host.docker.internal:11434/v1")
        model = os.getenv("AI_INSIGHTS_MODEL", "llama3.1:8b")
    elif provider in OPENCLAW_PROVIDERS:
        # OpenClaw treats `model` as an agent target (e.g. "openclaw:main").
        # To pick the backing LLM, send it in the x-openclaw-model header.
        base_url = os.getenv("AI_INSIGHTS_BASE_URL", "http://host.docker.internal:18789/v1")
        model = os.getenv("AI_INSIGHTS_MODEL", "openclaw:main")
        backend_model = os.getenv("AI_INSIGHTS_BACKEND_MODEL")
        if backend_model:
            extra_headers["x-openclaw-model"] = backend_model
    elif provider in {"gemini", "google"}:
        base_url = os.getenv(
            "AI_INSIGHTS_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta/openai",
        )
        model = os.getenv("AI_INSIGHTS_MODEL", "gemini-3.5-flash-lite")
    else:
        # Any other OpenAI-compatible provider (OpenAI, Groq, OpenRouter, ...).
        base_url = os.getenv("AI_INSIGHTS_BASE_URL", "https://api.openai.com/v1")
        model = os.getenv("AI_INSIGHTS_MODEL", "gpt-4o-mini")

    return base_url.rstrip("/"), model, extra_headers


SYSTEM_PROMPT = (
    "You are a business analyst for RVDC, a repair, sales, and service shop in the Philippines. "
    "Your reader is the shop owner, who wants a quick, plain-language read, not a report. "
    "Use only the provided facts. "
    "Return JSON only with this shape: "
    "{\"headline\": string, \"summary\": string, "
    "\"recommendations\": [{\"title\": string, \"reason\": string, \"action\": string, \"priority\": \"high\"|\"medium\"|\"low\"}], "
    "\"risks\": [string], \"opportunities\": [string], \"confidence\": \"High\"|\"Medium\"|\"Low\"}. "
    "Rules: "
    "1) All money is Philippine peso. Write amounts with the ₱ sign, never $ or USD. "
    "2) Use short figures such as ₱2.4M, ₱802K or ₱1,250 instead of long exact amounts, and round percentages to whole numbers. "
    "3) Write dates like September 27, 2026. Never write dates like 2026-09-27. "
    "4) Keep it short. headline: 8 words or fewer. summary: one sentence, 20 words or fewer. "
    "At most 3 recommendations, ordered by priority; each title 6 words or fewer, "
    "reason 14 words or fewer, action 14 words or fewer and starting with a verb. "
    "At most 3 risks and 3 opportunities, each 10 words or fewer. "
    "5) Use plain words. No jargon, no repeating the same number in several places. "
    "Focus on sales growth, collections, inventory, and service throughput."
)


def _call_ai_provider(snapshot, start_date, end_date, stall):
    provider = os.getenv("AI_INSIGHTS_PROVIDER", "openai").strip().lower()
    api_key = os.getenv("AI_INSIGHTS_API_KEY")

    needs_key = provider not in KEYLESS_PROVIDERS and provider not in OPENCLAW_PROVIDERS
    if needs_key and not api_key:
        logger.warning("AI insights: AI_INSIGHTS_API_KEY is not set for provider '%s'", provider)
        return None

    base_url, model, extra_headers = _provider_config(provider)
    timeout = float(os.getenv("AI_INSIGHTS_TIMEOUT", "30"))

    payload = {
        "model": model,
        "temperature": 0.25,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "period": _period_label(start_date, end_date),
                        "stall": getattr(stall, "name", None),
                        "currency": "Philippine peso (₱)",
                        "dashboard": snapshot,
                    },
                    default=str,
                ),
            },
        ],
    }

    headers = {"Content-Type": "application/json", **extra_headers}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # must come before URLError (it is a subclass)
        try:
            body = exc.read()[:300].decode("utf-8", errors="replace")
        except Exception:
            body = ""
        logger.warning("AI insights: HTTP %s from %s (model %s): %s", exc.code, provider, model, body)
        return None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning("AI insights: request to %s failed: %s", provider, exc)
        return None

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"] or ""
        parsed = _extract_json_object(content)
    except (KeyError, IndexError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        logger.warning("AI insights: unparseable response from %s: %s", provider, exc)
        return None

    if not isinstance(parsed, dict):
        logger.warning("AI insights: %s did not return a JSON object", provider)
        return None

    normalized = _normalize_response(parsed)
    if not normalized:
        logger.warning("AI insights: response from %s had no usable recommendations", provider)
        return None

    normalized["source"] = "ai"
    normalized["model"] = model
    normalized["provider"] = provider
    normalized["generated_at"] = timezone.now().isoformat()
    return normalized


# ---------------------------------------------------------------------------
# Rules-based fallback
# ---------------------------------------------------------------------------
def _build_fallback_insights(snapshot):
    revenue = snapshot.get("revenue", {})
    outstanding = snapshot.get("outstanding", {})
    services = snapshot.get("services", {})
    inventory = snapshot.get("inventory", {})

    total_sales = _as_float(revenue.get("sales", {}).get("revenue"))
    service_revenue = _as_float(revenue.get("services", {}).get("revenue"))
    total_revenue = _as_float(revenue.get("total_revenue"))
    net_income = _as_float(revenue.get("net_income"))
    total_outstanding = _as_float(outstanding.get("total_outstanding"))
    payment_collection_rate = _as_float(revenue.get("payment_collection_rate"))
    service_completion_rate = _as_float(services.get("completion_rate"))
    low_stock_items = int(inventory.get("low_stock_count", 0) or inventory.get("low_stock_items", 0) or 0)
    no_stock_items = int(inventory.get("out_of_stock_count", 0) or inventory.get("no_stock_items", 0) or 0)
    top_item = revenue.get("top_selling_item", {}) or {}
    top_item_name = top_item.get("name")
    top_item_quantity = _as_float(top_item.get("quantity"))
    new_clients = int(revenue.get("new_clients", 0) or 0)
    active_services = int(services.get("active_services", 0) or 0)

    # A collection rate of 0 usually means "no data", so only treat it as weak
    # when it is a real, non-zero number below the target.
    weak_collection = bool(payment_collection_rate) and payment_collection_rate < 90

    recommendations = []
    risks = []
    opportunities = []

    if low_stock_items or no_stock_items:
        recommendations.append(
            {
                "title": "Restock fast-moving items",
                "reason": f"{low_stock_items + no_stock_items} stock alerts can cut sales on high-demand parts.",
                "action": "Review low-stock parts, prioritize top sellers, and reorder before stockouts hit.",
                "priority": "high" if no_stock_items else "medium",
            }
        )
        risks.append("Inventory gaps may be blocking sales on products customers already want.")
        opportunities.append("Reorder and bundle top items to lift repeat sales.")

    if total_outstanding > 0 or weak_collection:
        recommendations.append(
            {
                "title": "Tighten collection follow-up",
                "reason": f"Outstanding balance is ₱{total_outstanding:,.0f} and collection rate is {payment_collection_rate:.1f}%.",
                "action": "Prioritize unpaid and partial accounts, then follow up clients with a clear collection schedule.",
                "priority": "high" if total_outstanding > max(total_sales, service_revenue) * 0.2 else "medium",
            }
        )
        risks.append("Cash flow weakens when receivables grow faster than collections.")
        opportunities.append("Faster collection raises working capital without extra sales.")

    if total_revenue > 0 and net_income < total_revenue * 0.15:
        recommendations.append(
            {
                "title": "Review margin pressure",
                "reason": f"Net income is only ₱{net_income:,.0f} against ₱{total_revenue:,.0f} revenue.",
                "action": "Audit expenses, discounting, and unit costs to protect margin.",
                "priority": "high",
            }
        )
        risks.append("Revenue may be growing without healthy profit conversion.")

    if service_completion_rate and service_completion_rate < 85:
        recommendations.append(
            {
                "title": "Improve service throughput",
                "reason": f"Service completion rate is {service_completion_rate:.1f}% with {active_services} active jobs.",
                "action": "Clear bottlenecks, reassign technicians, and close pending jobs faster.",
                "priority": "medium",
            }
        )
        risks.append("Slow job completion can delay billing and customer satisfaction.")

    if new_clients < 3:
        recommendations.append(
            {
                "title": "Push new customer acquisition",
                "reason": f"Only {new_clients} new clients were recorded in the selected period.",
                "action": "Use referral offers, post-service follow-ups, and repeat-sale bundles to bring in new buyers.",
                "priority": "medium",
            }
        )
        opportunities.append("More lead generation can raise future parts and service volume.")

    if top_item_name:
        recommendations.append(
            {
                "title": f"Promote {top_item_name}",
                "reason": f"It is the current top seller with {top_item_quantity:.0f} units moved.",
                "action": "Keep it visible, bundle it with services, and protect availability.",
                "priority": "low",
            }
        )

    if not recommendations:
        recommendations.append(
            {
                "title": "Use data to guide next move",
                "reason": "Current snapshot does not show critical warnings, so keep watching trends and test small promos.",
                "action": "Run a weekly review of revenue, collections, and stock to catch weak spots early.",
                "priority": "low",
            }
        )

    headline = "Business looks stable"
    if no_stock_items or total_outstanding > 0 or weak_collection:
        headline = "Business needs follow-up on stock and cash flow"
    if net_income < 0:
        headline = "Business is losing money right now"

    summary = " ".join(
        part
        for part in [
            f"Sales at ₱{total_sales:,.0f}." if total_sales else None,
            f"Service revenue at ₱{service_revenue:,.0f}." if service_revenue else None,
            f"Outstanding balances at ₱{total_outstanding:,.0f}." if total_outstanding else None,
            f"Net income at ₱{net_income:,.0f}." if total_revenue else None,
        ]
        if part
    )

    return {
        "source": "rules",
        "headline": headline,
        "summary": summary or "No critical issues detected in selected period.",
        "recommendations": recommendations[:MAX_RECOMMENDATIONS],
        "risks": risks[:3],
        "opportunities": opportunities[:3],
        "confidence": "medium",
        "generated_at": timezone.now().isoformat(),
        "model": None,
    }


# ---------------------------------------------------------------------------
# Response cleaning
# ---------------------------------------------------------------------------
def _normalize_response(payload):
    recommendations = []
    for item in payload.get("recommendations", []) or []:
        if not isinstance(item, dict):
            continue
        priority = str(item.get("priority", "medium")).strip().lower()
        if priority not in VALID_PRIORITIES:
            priority = "medium"
        recommendations.append(
            {
                "title": _humanize_text(item.get("title", "Recommendation")),
                "reason": _humanize_text(item.get("reason", "")),
                "action": _humanize_text(item.get("action", "")),
                "priority": priority,
            }
        )

    if not recommendations:
        return None

    risks = [_humanize_text(item) for item in payload.get("risks", []) or [] if item]
    opportunities = [_humanize_text(item) for item in payload.get("opportunities", []) or [] if item]

    return {
        "headline": _humanize_text(payload.get("headline") or payload.get("summary") or "Business insights"),
        "summary": _humanize_text(payload.get("summary") or ""),
        "recommendations": recommendations[:MAX_RECOMMENDATIONS],
        "risks": risks[:3],
        "opportunities": opportunities[:3],
        "confidence": str(payload.get("confidence") or "medium"),
    }


def _extract_json_object(content):
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])
    return None


def _as_float(value):
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
