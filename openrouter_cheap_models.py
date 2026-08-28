#!/usr/bin/env python3
"""
OpenRouter Cheap Models Mapper

Fetches models from OpenRouter and filters those that are free or have a price
<= THRESHOLD_PER_MILLION per million tokens.

Segments results into:
  - Embedding models
  - Text models (chat / completion)
  - Transcription models (speech-to-text)

Usage:
    python openrouter_cheap_models.py
    python openrouter_cheap_models.py --threshold 0.05
    python openrouter_cheap_models.py --output json
"""

import argparse
import json
import sys
from typing import Any

import requests

TEXT_MODELS_URL = "https://openrouter.ai/api/v1/models"
EMBEDDING_MODELS_URL = "https://openrouter.ai/api/v1/embeddings/models"
TRANSCRIPTION_MODELS_URL = "https://openrouter.ai/api/v1/models?output_modalities=transcription"


def fetch_models(url: str) -> list[dict[str, Any]]:
    """Fetch models from an OpenRouter endpoint."""
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data.get("data", [])


def per_token_to_per_million(price_str: str | None) -> float:
    """Convert per-token price string to dollars per million tokens."""
    if price_str is None:
        return float("inf")
    try:
        return float(price_str) * 1_000_000
    except ValueError:
        return float("inf")


def is_cheap(
    model: dict[str, Any],
    min_per_million: float | None = None,
    max_per_million: float | None = None,
) -> bool:
    """Return True if the model is free or within the price range.

    If only max_per_million is provided, behaves as a simple threshold.
    If min_per_million is provided, only models with price >= min are included.
    """
    pricing = model.get("pricing", {})
    prompt_price = per_token_to_per_million(pricing.get("prompt"))
    completion_price = per_token_to_per_million(pricing.get("completion"))
    audio_price_str = pricing.get("audio")

    # Audio models (transcription / speech) use per-second pricing.
    # Include them if they are free or have a defined non-negative price.
    if audio_price_str is not None:
        if audio_price_str == "0":
            return min_per_million is None or min_per_million <= 0
        try:
            audio_val = float(audio_price_str)
        except ValueError:
            return False
        if audio_val < 0:
            return False
        return True

    # Treat negative prices (e.g. -1 for variable pricing) as excluded
    # unless they are explicitly 0 (free).
    prompt_free = pricing.get("prompt") == "0"
    completion_free = pricing.get("completion") == "0"

    if prompt_free and completion_free:
        # Free models pass only if min allows 0 (i.e. min is None or <= 0)
        return min_per_million is None or min_per_million <= 0

    if prompt_price < 0 or completion_price < 0:
        return False

    # Check prompt price
    prompt_ok = True
    if min_per_million is not None:
        prompt_ok = prompt_price >= min_per_million
    if max_per_million is not None:
        prompt_ok = prompt_ok and prompt_price <= max_per_million

    # Check completion price
    completion_ok = True
    if min_per_million is not None:
        completion_ok = completion_price >= min_per_million
    if max_per_million is not None:
        completion_ok = completion_ok and completion_price <= max_per_million

    return prompt_ok or completion_ok


def classify_model(model: dict[str, Any]) -> str:
    """Classify a model based on its output modalities."""
    output_modalities = model.get("architecture", {}).get("output_modalities", [])
    if "embeddings" in output_modalities:
        return "embedding"
    if "transcription" in output_modalities:
        return "transcription"
    return "text"


def format_price(price_str: str | None) -> str:
    """Format a per-token price string as $/1M tokens."""
    if price_str is None:
        return "N/A"
    if price_str == "0":
        return "Free"
    try:
        per_million = float(price_str) * 1_000_000
        return f"${per_million:.4f}/1M"
    except ValueError:
        return price_str


def format_audio_price(price_str: str | None) -> str:
    """Format a per-second audio price string."""
    if price_str is None:
        return "N/A"
    if price_str == "0":
        return "Free"
    try:
        price = float(price_str)
        per_min = price * 60
        per_hr = price * 3600
        if per_hr < 0.01:
            return f"${price:.6f}/sec"
        if per_hr < 1:
            return f"${per_min:.4f}/min"
        return f"${per_hr:.4f}/hr"
    except ValueError:
        return price_str


def build_model_info(model: dict[str, Any]) -> dict[str, Any]:
    """Extract relevant fields for display/export."""
    pricing = model.get("pricing", {})
    return {
        "id": model.get("id"),
        "name": model.get("name"),
        "context_length": model.get("context_length"),
        "modality": model.get("architecture", {}).get("modality"),
        "prompt_price": format_price(pricing.get("prompt")),
        "completion_price": format_price(pricing.get("completion")),
        "audio_price": format_audio_price(pricing.get("audio")),
        "prompt_price_raw": pricing.get("prompt"),
        "completion_price_raw": pricing.get("completion"),
        "audio_price_raw": pricing.get("audio"),
    }


def print_table(title: str, models: list[dict[str, Any]]) -> None:
    """Print a nicely aligned table of models."""
    if not models:
        print(f"\n{title}\n  (no models found)\n")
        return

    print(f"\n{title} ({len(models)} models)")
    print("-" * 120)
    header = f"{'ID':<50} {'Prompt':<15} {'Completion':<15} {'Context':<10} {'Name'}"
    print(header)
    print("-" * 120)
    for m in models:
        print(
            f"{m['id']:<50} {m['prompt_price']:<15} {m['completion_price']:<15} "
            f"{str(m['context_length']):<10} {m['name']}"
        )
    print("-" * 120)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map free or cheap OpenRouter models, segmented by embedding, text, and transcription."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.03,
        help="Maximum price in dollars per million tokens (default: 0.03).",
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
    args = parser.parse_args()

    # Determine min/max range
    min_price = args.min_price
    max_price = args.max_price if args.max_price is not None else args.threshold

    if min_price is not None and max_price is not None and min_price > max_price:
        print("Error: --min cannot be greater than --max/--threshold.", file=sys.stderr)
        return 1

    range_label = f"${min_price}/1M" if min_price is not None else "Free"
    range_label += f" to ${max_price}/1M"
    print(f"Fetching models from OpenRouter ({range_label})...", file=sys.stderr)

    try:
        text_models = fetch_models(TEXT_MODELS_URL)
        embedding_models = fetch_models(EMBEDDING_MODELS_URL)
        transcription_models = fetch_models(TRANSCRIPTION_MODELS_URL)
    except requests.RequestException as exc:
        print(f"Error fetching models: {exc}", file=sys.stderr)
        return 1

    all_models = text_models + embedding_models + transcription_models

    cheap_models = [m for m in all_models if is_cheap(m, min_price, max_price)]

    embedding_cheap = [build_model_info(m) for m in cheap_models if classify_model(m) == "embedding"]
    text_cheap = [build_model_info(m) for m in cheap_models if classify_model(m) == "text"]
    transcription_cheap = [build_model_info(m) for m in cheap_models if classify_model(m) == "transcription"]

    # Sort by price (free first, then ascending)
    def sort_key(m: dict[str, Any]) -> float:
        raw = m.get("audio_price_raw")
        if raw is not None:
            if raw == "0":
                return -1.0
            try:
                return float(raw)
            except ValueError:
                return float("inf")
        raw = m.get("prompt_price_raw")
        if raw == "0":
            return -1.0
        try:
            return float(raw or "inf")
        except ValueError:
            return float("inf")

    embedding_cheap.sort(key=sort_key)
    text_cheap.sort(key=sort_key)
    transcription_cheap.sort(key=sort_key)

    if args.output == "json":
        result = {
            "min_per_million": min_price,
            "max_per_million": max_price,
            "embedding_models": embedding_cheap,
            "text_models": text_cheap,
            "transcription_models": transcription_cheap,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_table("EMBEDDING MODELS", embedding_cheap)
        print_table("TEXT MODELS", text_cheap)
        print_table("TRANSCRIPTION MODELS", transcription_cheap)
        print(f"\nTotal cheap models found: {len(cheap_models)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
