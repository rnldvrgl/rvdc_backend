from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from decimal import Decimal

from analytics.business_logic import DashboardAnalytics
from django.utils import timezone


def generate_business_insights(start_date=None, end_date=None, stall=None):
    """Build business insights from dashboard metrics and optional AI provider."""
    snapshot = DashboardAnalytics.get_dashboard_summary(start_date, end_date, stall)

    provider_payload = _call_ai_provider(snapshot, start_date, end_date, stall)
    if provider_payload:
        provider_payload["snapshot"] = snapshot
        return provider_payload

    fallback = _build_fallback_insights(snapshot)
    fallback["snapshot"] = snapshot
    return fallback


def _call_ai_provider(snapshot, start_date, end_date, stall):
    provider = os.getenv("AI_INSIGHTS_PROVIDER", "openai").strip().lower()
    api_key = os.getenv("AI_INSIGHTS_API_KEY")

    if provider == "openai" and not api_key:
        return None

    if provider in {"ollama"}:
        base_url = os.getenv("AI_INSIGHTS_BASE_URL", "http://host.docker.internal:11434/v1").rstrip("/")
        model = os.getenv("AI_INSIGHTS_MODEL", "llama3.1:8b")
    elif provider in {"openclaw", "crestodian"}:
        base_url = os.getenv("AI_INSIGHTS_BASE_URL", "http://127.0.0.1:18789/v1").rstrip("/")
        model = os.getenv("AI_INSIGHTS_MODEL", "openai/gpt-5.6")
    else:
        base_url = os.getenv("AI_INSIGHTS_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.getenv("AI_INSIGHTS_MODEL", "gpt-4o-mini")

    timeout = float(os.getenv("AI_INSIGHTS_TIMEOUT", "20"))

    system_prompt = (
        "You are a business analyst for RVDC, a repair, sales, and service business. "
        "Use only provided facts. Return JSON only with this shape: "
        "{\"headline\": string, \"summary\": string, \"recommendations\": [{\"title\": string, \"reason\": string, \"action\": string, \"priority\": \"high\"|\"medium\"|\"low\"}], \"risks\": [string], \"opportunities\": [string], \"confidence\": string}. "
        "Be specific, practical, and focused on sales growth, collections, inventory, and service throughput."
    )

    payload = {
        "model": model,
        "temperature": 0.25,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "start_date": str(start_date) if start_date else None,
                        "end_date": str(end_date) if end_date else None,
                        "stall": getattr(stall, "name", None),
                        "dashboard": snapshot,
                    },
                    default=str,
                ),
            },
        ],
    }

    headers = {"Content-Type": "application/json"}
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
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
        parsed = _extract_json_object(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None

    normalized = _normalize_response(parsed)
    if not normalized:
        return None

    normalized["source"] = "ai"
    normalized["model"] = model
    normalized["provider"] = provider
    normalized["generated_at"] = timezone.now().isoformat()
    return normalized


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

    if total_outstanding > 0 or payment_collection_rate and payment_collection_rate < 90:
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
    if no_stock_items or total_outstanding > 0 or payment_collection_rate < 90:
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
        "recommendations": recommendations[:5],
        "risks": risks[:3],
        "opportunities": opportunities[:3],
        "confidence": "medium",
        "generated_at": timezone.now().isoformat(),
        "model": None,
    }


def _normalize_response(payload):
    recommendations = []
    for item in payload.get("recommendations", []):
        if not isinstance(item, dict):
            continue
        recommendations.append(
            {
                "title": str(item.get("title", "Recommendation")),
                "reason": str(item.get("reason", "")),
                "action": str(item.get("action", "")),
                "priority": str(item.get("priority", "medium")),
            }
        )

    if not recommendations:
        return None

    risks = [str(item) for item in payload.get("risks", []) if item]
    opportunities = [str(item) for item in payload.get("opportunities", []) if item]

    return {
        "headline": str(payload.get("headline") or payload.get("summary") or "Business insights"),
        "summary": str(payload.get("summary") or ""),
        "recommendations": recommendations[:5],
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
