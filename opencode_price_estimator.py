#!/usr/bin/env python3
"""
OpenCode Price Estimator

Maps models from OpenCode Zen & Go with their pay-as-you-go pricing and filters
those that are free or have a price <= THRESHOLD_PER_MILLION per million tokens.

Also estimates cost for OpenCode Go subscription vs Zen pay-as-you-go.

Usage:
    python opencode_price_estimator.py
    python opencode_price_estimator.py --threshold 1.00
    python opencode_price_estimator.py --provider go
    python opencode_price_estimator.py --output json
    python opencode_price_estimator.py --estimate 5000000 2000000
    python opencode_price_estimator.py --update-prices
"""

import argparse
import json
import os
import re
import sys
from typing import Any

import requests

ZEN_MODELS_URL = "https://opencode.ai/zen/v1/models"
ZEN_DOCS_URL = "https://opencode.ai/docs/zen"
GO_DOCS_URL = "https://opencode.ai/docs/go/"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PRICES_FILE = os.path.join(SCRIPT_DIR, "opencode_prices.json")

GO_SUBSCRIPTION_PRICE = 10.0
GO_MODELS_MULTIPLIER = 6.0

ZEN_PRICING_CATALOG: dict[str, dict[str, Any]] = {
    "gpt-5.6-luna": {"input": 0.20, "output": 1.20, "context": 128000, "source": "both"},
    "gpt-5.6-terra": {"input": 2.00, "output": 12.00, "context": 128000, "source": "zen"},
    "gpt-5.6-sol": {"input": 2.00, "output": 10.00, "context": 128000, "source": "zen"},
    "gpt-5.5": {"input": 5.00, "output": 30.00, "context": 256000, "source": "zen"},
    "gpt-5.5-pro": {"input": 30.00, "output": 180.00, "context": 256000, "source": "zen"},
    "gpt-5.4": {"input": 2.50, "output": 15.00, "context": 256000, "source": "zen"},
    "gpt-5.4-pro": {"input": 30.00, "output": 180.00, "context": 256000, "source": "zen"},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50, "context": 256000, "source": "zen"},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25, "context": 128000, "source": "zen"},
    "gpt-5.3-codex": {"input": 1.75, "output": 14.00, "context": 256000, "source": "zen"},
    "gpt-5.3-codex-spark": {"input": 1.75, "output": 14.00, "context": 256000, "source": "zen"},
    "gpt-5.2": {"input": 1.75, "output": 14.00, "context": 256000, "source": "zen"},
    "gpt-5.2-codex": {"input": 1.75, "output": 14.00, "context": 256000, "source": "zen"},
    "gpt-5.1": {"input": 1.07, "output": 8.50, "context": 256000, "source": "zen"},
    "gpt-5.1-codex": {"input": 1.07, "output": 8.50, "context": 256000, "source": "zen"},
    "gpt-5.1-codex-max": {"input": 1.25, "output": 10.00, "context": 256000, "source": "zen"},
    "gpt-5.1-codex-mini": {"input": 0.25, "output": 2.00, "context": 256000, "source": "zen"},
    "gpt-5": {"input": 1.07, "output": 8.50, "context": 256000, "source": "zen"},
    "gpt-5-codex": {"input": 1.07, "output": 8.50, "context": 256000, "source": "zen"},
    "gpt-5-nano": {"input": 0.05, "output": 0.40, "context": 128000, "source": "zen"},
    "claude-haiku-4.5": {"input": 1.00, "output": 5.00, "context": 200000, "source": "zen"},
    "claude-sonnet-4.5": {"input": 3.00, "output": 15.00, "context": 200000, "source": "zen"},
    "claude-sonnet-4.6": {"input": 3.00, "output": 15.00, "context": 200000, "source": "zen"},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00, "context": 200000, "source": "zen"},
    "claude-opus-4.5": {"input": 5.00, "output": 25.00, "context": 200000, "source": "zen"},
    "claude-opus-4.6": {"input": 5.00, "output": 25.00, "context": 200000, "source": "zen"},
    "claude-opus-4.7": {"input": 5.00, "output": 25.00, "context": 200000, "source": "zen"},
    "claude-opus-4.8": {"input": 5.00, "output": 25.00, "context": 200000, "source": "zen"},
    "claude-opus-5": {"input": 5.00, "output": 25.00, "context": 200000, "source": "zen"},
    "claude-fable-5": {"input": 10.00, "output": 50.00, "context": 1000000, "source": "zen"},
    "gemini-3-flash": {"input": 0.50, "output": 3.00, "context": 1000000, "source": "zen"},
    "gemini-3.5-flash": {"input": 1.50, "output": 9.00, "context": 1000000, "source": "zen"},
    "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50, "context": 1000000, "source": "zen"},
    "gemini-3.6-flash": {"input": 1.50, "output": 7.50, "context": 1000000, "source": "zen"},
    "gemini-3.7-flash": {"input": 1.50, "output": 7.50, "context": 1000000, "source": "zen"},
    "gemini-3.1-pro": {"input": 2.00, "output": 12.00, "context": 2000000, "source": "zen"},
    "deepseek-v4-flash": {"input": 0.22, "output": 0.66, "context": 1000000, "source": "both"},
    "deepseek-v4-flash-vision": {"input": 0.22, "output": 0.66, "context": 1000000, "source": "go"},
    "deepseek-v4-pro": {"input": 0.66, "output": 1.98, "context": 1000000, "source": "both"},
    "minimax-m2.7": {"input": 0.30, "output": 1.20, "context": 1000000, "source": "both"},
    "minimax-m3": {"input": 0.30, "output": 1.20, "context": 1000000, "source": "go"},
    "glm-5": {"input": 1.00, "output": 3.20, "context": 202752, "source": "zen"},
    "glm-5.1": {"input": 1.40, "output": 4.40, "context": 202752, "source": "both"},
    "glm-5.2": {"input": 1.40, "output": 4.40, "context": 1000000, "source": "both"},
    "glm-5.3": {"input": 1.40, "output": 4.40, "context": 1000000, "source": "go"},
    "muse-spark-1.2": {"input": 1.25, "output": 4.25, "context": 1050000, "source": "zen"},
    "mimo-v2.5": {"input": 0.14, "output": 0.28, "context": 256000, "source": "both"},
    "mimo-v2.5-pro": {"input": 0.435, "output": 0.87, "context": 256000, "source": "go"},
    "hy3": {"input": 0.14, "output": 0.58, "context": 128000, "source": "both"},
    "big-pickle": {"input": 0.0, "output": 0.0, "context": 200000, "source": "zen"},
    "ox-alpha-free": {"input": 0.0, "output": 0.0, "context": 128000, "source": "go"},
    "laguna-s-2.1": {"input": 0.0, "output": 0.0, "context": 128000, "source": "zen"},
    "north-mini-code-free": {"input": 0.0, "output": 0.0, "context": 128000, "source": "zen"},
    "nemotron-3-ultra-free": {"input": 0.0, "output": 0.0, "context": 128000, "source": "zen"},
    "nemotron-3.5-lightning-free": {"input": 0.0, "output": 0.0, "context": 128000, "source": "zen"},
    "muse-spark-1.2-contributor-free": {"input": 0.0, "output": 0.0, "context": 1050000, "source": "zen"},
    "grok-4.5": {"input": 2.00, "output": 6.00, "context": 128000, "source": "go"},
    "grok-4.6": {"input": 2.00, "output": 6.00, "context": 128000, "source": "zen"},
    "grok-build-0.1": {"input": 1.00, "output": 2.00, "context": 128000, "source": "zen"},
    "qwen3.5-plus": {"input": 0.20, "output": 1.20, "context": 128000, "source": "zen"},
    "qwen3.6-plus": {"input": 0.50, "output": 3.00, "context": 128000, "source": "both"},
    "qwen3.7-plus": {"input": 0.40, "output": 1.60, "context": 128000, "source": "both"},
    "qwen3.7-max": {"input": 2.50, "output": 7.50, "context": 128000, "source": "both"},
    "qwen3.8-max": {"input": 2.00, "output": 6.00, "context": 128000, "source": "go"},
    "kimi-k2.5": {"input": 0.60, "output": 3.00, "context": 256000, "source": "zen"},
    "kimi-k2.6": {"input": 0.95, "output": 4.00, "context": 256000, "source": "both"},
    "kimi-k2.7-code": {"input": 0.95, "output": 4.00, "context": 256000, "source": "both"},
    "kimi-k3": {"input": 3.00, "output": 15.00, "context": 256000, "source": "both"},
    "longcat-2.0": {"input": 0.30, "output": 1.20, "context": 128000, "source": "go"},
}


def fetch_models() -> list[dict[str, Any]]:
    """Fetch models from OpenCode Zen API."""
    response = requests.get(ZEN_MODELS_URL, timeout=60)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        return data.get("data", [])
    return data if isinstance(data, list) else []


def _parse_price(value: str) -> float:
    """Parse a price string like $1.25 or Free into float."""
    value = value.strip()
    if value.lower() == "free":
        return 0.0
    m = re.search(r"[\d.]+", value)
    if m:
        return float(m.group())
    return 0.0


def _clean_model_name(name: str) -> str:
    """Convert display name to model ID slug."""
    name = re.sub(r"\s*\([^)]+\)", "", name)
    name = name.strip().lower()
    name = re.sub(r"[\s.]+", "-", name)
    return name


def _extract_model_ids(html: str) -> dict[str, str]:
    """Extract mapping from display name to model ID from endpoints table."""
    mapping: dict[str, str] = {}
    pattern = re.compile(
        r"<table[^>]*>.*?<th>Model</th>\s*<th>Model ID</th>.*?</thead>\s*<tbody>(.*?)</tbody>\s*</table>",
        re.S | re.I,
    )
    m = pattern.search(html)
    if not m:
        return mapping
    tbody = m.group(1)
    rows = re.findall(r"<tr>(.*?)</tr>", tbody, re.S)
    for row in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(tds) >= 2:
            display_name = re.sub(r"<[^>]+>", "", tds[0]).strip()
            model_id = re.sub(r"<[^>]+>", "", tds[1]).strip()
            if display_name and model_id:
                mapping[display_name.lower()] = model_id
    return mapping


def _extract_pricing_table(html: str) -> list[dict[str, Any]]:
    """Extract pricing rows from HTML table."""
    pattern = re.compile(
        r"<table[^>]*>.*?<th>Model</th>\s*<th>Input</th>\s*<th>Output</th>.*?</thead>\s*<tbody>(.*?)</tbody>\s*</table>",
        re.S | re.I,
    )
    m = pattern.search(html)
    if not m:
        return []
    tbody = m.group(1)
    rows = re.findall(r"<tr>(.*?)</tr>", tbody, re.S)
    results = []
    for row in rows:
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        if len(tds) < 3:
            continue
        display_name = re.sub(r"<[^>]+>", "", tds[0]).strip()
        input_price = _parse_price(re.sub(r"<[^>]+>", "", tds[1]).strip())
        output_price = _parse_price(re.sub(r"<[^>]+>", "", tds[2]).strip())
        results.append({
            "display_name": display_name,
            "input": input_price,
            "output": output_price,
        })
    return results


def scrape_zen_prices() -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Scrape current prices from OpenCode Zen docs. Returns (catalog, model_ids)."""
    print(f"Fetching pricing from {ZEN_DOCS_URL}...", file=sys.stderr)
    resp = requests.get(ZEN_DOCS_URL, timeout=60)
    resp.raise_for_status()
    html = resp.text
    model_ids = _extract_model_ids(html)
    rows = _extract_pricing_table(html)

    catalog: dict[str, dict[str, Any]] = {}
    for row in rows:
        display_name = row["display_name"]
        model_id = model_ids.get(display_name.lower()) or _clean_model_name(display_name)
        if model_id in catalog:
            catalog[model_id]["input"] = min(catalog[model_id]["input"], row["input"])
            catalog[model_id]["output"] = min(catalog[model_id]["output"], row["output"])
        else:
            catalog[model_id] = {
                "input": row["input"],
                "output": row["output"],
                "context": None,
                "source": "zen",
            }
    return catalog, set(model_ids.values())


def scrape_go_prices() -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Scrape current prices from OpenCode Go docs. Returns (catalog, model_ids)."""
    print(f"Fetching pricing from {GO_DOCS_URL}...", file=sys.stderr)
    resp = requests.get(GO_DOCS_URL, timeout=60)
    resp.raise_for_status()
    html = resp.text
    model_ids = _extract_model_ids(html)
    rows = _extract_pricing_table(html)

    catalog: dict[str, dict[str, Any]] = {}
    for row in rows:
        display_name = row["display_name"]
        model_id = model_ids.get(display_name.lower()) or _clean_model_name(display_name)
        if model_id in catalog:
            catalog[model_id]["input"] = min(catalog[model_id]["input"], row["input"])
            catalog[model_id]["output"] = min(catalog[model_id]["output"], row["output"])
        else:
            catalog[model_id] = {
                "input": row["input"],
                "output": row["output"],
                "context": None,
                "source": "go",
            }
    return catalog, set(model_ids.values())


def update_prices_file(prices_file: str) -> None:
    """Scrape docs and save prices to JSON file with source tags."""
    zen_catalog, zen_ids = scrape_zen_prices()
    go_catalog, go_ids = scrape_go_prices()

    # Merge catalogs: zen first, then go
    combined: dict[str, dict[str, Any]] = {}
    for model_id, pricing in zen_catalog.items():
        combined[model_id] = dict(pricing)

    for model_id, pricing in go_catalog.items():
        if model_id in combined:
            # Model exists in both -> mark as both, keep cheapest price
            combined[model_id]["source"] = "both"
            combined[model_id]["input"] = min(combined[model_id]["input"], pricing["input"])
            combined[model_id]["output"] = min(combined[model_id]["output"], pricing["output"])
        else:
            combined[model_id] = dict(pricing)

    # Add context lengths from fallback catalog if available
    for model_id, pricing in combined.items():
        if pricing.get("context") is None and model_id in ZEN_PRICING_CATALOG:
            pricing["context"] = ZEN_PRICING_CATALOG[model_id].get("context")

    data = {
        "source": "OpenCode docs (auto-scraped)",
        "zen_url": ZEN_DOCS_URL,
        "go_url": GO_DOCS_URL,
        "updated_at": requests.get(ZEN_DOCS_URL, timeout=10).headers.get("date", "unknown"),
        "models": combined,
    }

    with open(prices_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Stats
    zen_only = sum(1 for p in combined.values() if p.get("source") == "zen")
    go_only = sum(1 for p in combined.values() if p.get("source") == "go")
    both = sum(1 for p in combined.values() if p.get("source") == "both")
    print(f"Saved {len(combined)} models to {prices_file}", file=sys.stderr)
    print(f"  Zen only: {zen_only} | Go only: {go_only} | Both: {both}", file=sys.stderr)


def load_prices(prices_file: str) -> dict[str, dict[str, Any]]:
    """Load prices from JSON file or fallback to embedded catalog."""
    if os.path.exists(prices_file):
        with open(prices_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        models = data.get("models", {})
        if models:
            zen_only = sum(1 for p in models.values() if p.get("source") == "zen")
            go_only = sum(1 for p in models.values() if p.get("source") == "go")
            both = sum(1 for p in models.values() if p.get("source") == "both")
            print(
                f"Loaded {len(models)} models from {prices_file} "
                f"(Zen: {zen_only}, Go: {go_only}, Both: {both})",
                file=sys.stderr,
            )
            return models

    print(f"Using embedded catalog ({len(ZEN_PRICING_CATALOG)} models)", file=sys.stderr)
    return ZEN_PRICING_CATALOG


def enrich_with_catalog(models: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge API model list with pricing catalog."""
    enriched = []
    for m in models:
        model_id = m.get("id", "")
        if model_id in catalog:
            cat = catalog[model_id]
            m["pricing"] = {"input": cat["input"], "output": cat["output"]}
            m["source"] = cat.get("source", "zen")
            if cat.get("context"):
                m["context_length"] = cat["context"]
            enriched.append(m)

    api_ids = {m.get("id") for m in models}
    for model_id, cat in catalog.items():
        if model_id not in api_ids:
            enriched.append({
                "id": model_id,
                "object": "model",
                "owned_by": "opencode",
                "pricing": {"input": cat["input"], "output": cat["output"]},
                "context_length": cat.get("context"),
                "source": cat.get("source", "zen"),
            })
    return enriched


def is_cheap(
    model: dict[str, Any],
    min_per_million: float | None = None,
    max_per_million: float | None = None,
) -> bool:
    """Return True if the model is free or within the price range."""
    pricing = model.get("pricing", {})
    input_price = float(pricing.get("input", float("inf")))
    output_price = float(pricing.get("output", float("inf")))

    is_free = input_price == 0.0 and output_price == 0.0
    if is_free:
        return min_per_million is None or min_per_million <= 0

    input_ok = True
    if min_per_million is not None:
        input_ok = input_price >= min_per_million
    if max_per_million is not None:
        input_ok = input_ok and input_price <= max_per_million

    output_ok = True
    if min_per_million is not None:
        output_ok = output_price >= min_per_million
    if max_per_million is not None:
        output_ok = output_ok and output_price <= max_per_million

    return input_ok or output_ok


def format_price(price: float) -> str:
    """Format a per-1M price."""
    if price == 0.0:
        return "Free"
    return f"${price:.4f}/1M"


def build_model_info(model: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant fields for display/export."""
    pricing = model.get("pricing", {})
    return {
        "id": model.get("id"),
        "name": model.get("name") or model.get("id"),
        "context_length": model.get("context_length") or model.get("context"),
        "input_price": format_price(float(pricing.get("input", 0))),
        "output_price": format_price(float(pricing.get("output", 0))),
        "input_price_raw": float(pricing.get("input", 0)),
        "output_price_raw": float(pricing.get("output", 0)),
        "provider": model.get("provider", "opencode"),
        "source": model.get("source", "zen"),
    }


def estimate_cost(input_tokens: int, output_tokens: int, model: dict[str, Any]) -> dict[str, Any]:
    """Estimate cost for a given token usage on a specific model."""
    info = build_model_info(model)
    input_price_per_mil = info["input_price_raw"]
    output_price_per_mil = info["output_price_raw"]

    input_cost = (input_tokens / 1_000_000) * input_price_per_mil
    output_cost = (output_tokens / 1_000_000) * output_price_per_mil
    total_cost = input_cost + output_cost

    go_equivalent = total_cost / GO_MODELS_MULTIPLIER if GO_MODELS_MULTIPLIER > 0 else 0

    return {
        "model_id": info["id"],
        "model_name": info["name"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "input_cost": round(input_cost, 4),
        "output_cost": round(output_cost, 4),
        "total_cost": round(total_cost, 4),
        "go_equivalent": round(go_equivalent, 4),
        "source": info["source"],
    }


def print_table(title: str, models: list[dict[str, Any]], show_source: bool = True) -> None:
    """Print a nicely aligned table of models."""
    if not models:
        print(f"\n{title}\n  (no models found)\n")
        return

    print(f"\n{title} ({len(models)} models)")
    if show_source:
        print("-" * 130)
        header = f"{'ID':<42} {'Input':<14} {'Output':<14} {'Context':<10} {'Plan':<8} {'Name'}"
        print(header)
        print("-" * 130)
        for m in models:
            ctx = str(m.get("context_length") or "N/A")
            src = m.get("source", "zen")
            print(
                f"{m['id']:<42} {m['input_price']:<14} {m['output_price']:<14} "
                f"{ctx:<10} {src:<8} {m['name']}"
            )
        print("-" * 130)
    else:
        print("-" * 120)
        header = f"{'ID':<45} {'Input':<15} {'Output':<15} {'Context':<12} {'Name'}"
        print(header)
        print("-" * 120)
        for m in models:
            ctx = str(m.get("context_length") or "N/A")
            print(
                f"{m['id']:<45} {m['input_price']:<15} {m['output_price']:<15} "
                f"{ctx:<12} {m['name']}"
            )
        print("-" * 120)


def print_estimate_table(estimates: list[dict[str, Any]], input_tokens: int, output_tokens: int) -> None:
    """Print cost estimation table."""
    if not estimates:
        print("\nNo estimates available.\n")
        return

    print(f"\nCOST ESTIMATES ({input_tokens:,} input + {output_tokens:,} output tokens)")
    print("-" * 105)
    header = f"{'Model':<38} {'Plan':<7} {'Zen Total':<12} {'Go Equiv':<12} {'Savings':<12} {'Name'}"
    print(header)
    print("-" * 105)
    for e in estimates:
        savings = e["total_cost"] - e["go_equivalent"]
        savings_pct = (savings / e["total_cost"] * 100) if e["total_cost"] > 0 else 0
        savings_str = f"${savings:.4f} ({savings_pct:.0f}%)" if savings > 0 else "N/A"
        src = e.get("source", "zen")
        print(
            f"{e['model_id']:<38} {src:<7} ${e['total_cost']:<11.4f} ${e['go_equivalent']:<11.4f} "
            f"{savings_str:<12} {e['model_name'][:28]}"
        )
    print("-" * 105)
    print(f"\nOpenCode Go subscription: ${GO_SUBSCRIPTION_PRICE}/month")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map free or cheap OpenCode Zen/Go models and estimate costs."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=2.00,
        help="Maximum price in dollars per million tokens (default: 2.00).",
    )
    parser.add_argument(
        "--min",
        type=float,
        dest="min_price",
        default=None,
        help="Minimum price in dollars per million tokens (optional).",
    )
    parser.add_argument(
        "--max",
        type=float,
        dest="max_price",
        default=None,
        help="Maximum price in dollars per million tokens (overrides --threshold if set).",
    )
    parser.add_argument(
        "--output",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table).",
    )
    parser.add_argument(
        "--estimate",
        nargs=2,
        type=int,
        metavar=("INPUT_TOKENS", "OUTPUT_TOKENS"),
        help="Estimate cost for given token counts across all cheap models.",
    )
    parser.add_argument(
        "--go-value",
        type=float,
        default=GO_SUBSCRIPTION_PRICE * GO_MODELS_MULTIPLIER,
        help="Estimated monthly value included in Go subscription (default: 60.0).",
    )
    parser.add_argument(
        "--update-prices",
        action="store_true",
        help="Scrape OpenCode docs and update local prices JSON.",
    )
    parser.add_argument(
        "--prices-file",
        type=str,
        default=DEFAULT_PRICES_FILE,
        help=f"Path to prices JSON file (default: {DEFAULT_PRICES_FILE}).",
    )
    parser.add_argument(
        "--provider",
        choices=["all", "zen", "go"],
        default="all",
        help="Filter models by provider/plan (default: all).",
    )
    parser.add_argument(
        "--segment",
        action="store_true",
        help="In table mode, show separate tables for Zen and Go models.",
    )
    args = parser.parse_args()

    if args.update_prices:
        try:
            update_prices_file(args.prices_file)
            return 0
        except Exception as exc:
            print(f"Error updating prices: {exc}", file=sys.stderr)
            return 1

    catalog = load_prices(args.prices_file)

    min_price = args.min_price
    max_price = args.max_price if args.max_price is not None else args.threshold
    go_monthly_value = args.go_value

    if min_price is not None and max_price is not None and min_price > max_price:
        print("Error: --min cannot be greater than --max/--threshold.", file=sys.stderr)
        return 1

    range_label = f"${min_price}/1M" if min_price is not None else "Free"
    range_label += f" to ${max_price}/1M"
    provider_label = f" [{args.provider.upper()}]" if args.provider != "all" else ""
    print(f"Fetching models from OpenCode{provider_label} ({range_label})...", file=sys.stderr)

    try:
        models = fetch_models()
    except requests.RequestException as exc:
        print(f"Error fetching models: {exc}", file=sys.stderr)
        return 1

    models = enrich_with_catalog(models, catalog)

    if not models:
        print("No models available.", file=sys.stderr)
        return 1

    # Filter by provider before price filter
    if args.provider == "zen":
        models = [m for m in models if m.get("source") in ("zen", "both")]
    elif args.provider == "go":
        models = [m for m in models if m.get("source") in ("go", "both")]

    cheap_models = [m for m in models if is_cheap(m, min_price, max_price)]
    model_infos = [build_model_info(m) for m in cheap_models]

    def sort_key(m: dict[str, Any]) -> float:
        raw = m.get("input_price_raw", 0)
        if raw == 0.0:
            return -1.0
        return float(raw)

    model_infos.sort(key=sort_key)

    if args.estimate:
        input_tokens, output_tokens = args.estimate
        estimates = []
        for m in cheap_models:
            est = estimate_cost(input_tokens, output_tokens, m)
            estimates.append(est)
        estimates.sort(key=lambda x: x["total_cost"])

        if args.output == "json":
            print(json.dumps({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "go_subscription": GO_SUBSCRIPTION_PRICE,
                "go_monthly_value": go_monthly_value,
                "provider_filter": args.provider,
                "estimates": estimates,
            }, indent=2, ensure_ascii=False))
        else:
            print_estimate_table(estimates, input_tokens, output_tokens)
        return 0

    if args.output == "json":
        result = {
            "source": "OpenCode",
            "api_url": ZEN_MODELS_URL,
            "min_per_million": min_price,
            "max_per_million": max_price,
            "provider_filter": args.provider,
            "go_subscription": {
                "monthly_price": GO_SUBSCRIPTION_PRICE,
                "estimated_monthly_value": go_monthly_value,
                "models_multiplier": GO_MODELS_MULTIPLIER,
            },
            "models": model_infos,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if args.segment and args.provider == "all":
            zen_models = [m for m in model_infos if m.get("source") in ("zen", "both")]
            go_models = [m for m in model_infos if m.get("source") in ("go", "both")]
            print_table("ZEN MODELS", zen_models, show_source=True)
            print_table("GO MODELS", go_models, show_source=True)
            total = len(model_infos)
            zen_count = len(zen_models)
            go_count = len(go_models)
            both_count = sum(1 for m in model_infos if m.get("source") == "both")
            print(f"\nTotal: {total} (Zen only: {zen_count - both_count}, Go only: {go_count - both_count}, Both: {both_count})")
        else:
            title = "OPENCODE MODELS"
            if args.provider == "zen":
                title = "ZEN MODELS"
            elif args.provider == "go":
                title = "GO MODELS"
            print_table(title, model_infos, show_source=(args.provider == "all"))
            print(f"\nTotal models found: {len(model_infos)}")

        print(f"OpenCode Go subscription: ${GO_SUBSCRIPTION_PRICE}/month")
        print(f"Go estimated value: ~${go_monthly_value:.0f}/month worth of Zen usage")
        print("\nTip: Use --estimate <input_tokens> <output_tokens> to compare costs.")
        print("      Use --update-prices to refresh from official docs.")
        print("      Use --segment to show separate Zen/Go tables.")
        print("      Use --provider zen|go to filter by plan.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
