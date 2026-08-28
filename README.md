# check_opencore_models

Tools for discovering and comparing free/cheap AI models across [OpenCode](https://opencode.ai) (Zen & Go) and [OpenRouter](https://openrouter.ai).

## Scripts

### `opencode_price_estimator.py`

Maps models from OpenCode Zen & Go with pay-as-you-go pricing, filters cheap/free models, and estimates costs between subscription plans.

**Features:**
- Fetches models from OpenCode Zen API
- Scrapes pricing from official docs (Zen + Go)
- Filters models by price threshold (input/output per million tokens)
- Estimates cost for given token usage
- Compares Zen pay-as-you-go vs Go subscription value
- Outputs table or JSON

**Usage:**

```bash
# List all models under $2/1M tokens (default)
python opencode_price_estimator.py

# Set custom threshold
python opencode_price_estimator.py --threshold 1.00

# Filter by provider
python opencode_price_estimator.py --provider zen
python opencode_price_estimator.py --provider go

# Show separate Zen/Go tables
python opencode_price_estimator.py --segment

# Estimate cost for 5M input + 2M output tokens
python opencode_price_estimator.py --estimate 5000000 2000000

# JSON output
python opencode_price_estimator.py --output json

# Update prices from official docs
python opencode_price_estimator.py --update-prices

# Use custom prices file
python opencode_price_estimator.py --prices-file custom_prices.json
```

**Flags:**

| Flag | Description | Default |
|------|-------------|---------|
| `--threshold` | Max $/1M tokens | 2.00 |
| `--min` | Min $/1M tokens (optional) | None |
| `--max` | Max $/1M tokens (overrides threshold) | None |
| `--provider` | Filter: `all`, `zen`, `go` | all |
| `--segment` | Show separate Zen/Go tables | false |
| `--estimate` | Estimate cost: `<input_tokens> <output_tokens>` | None |
| `--output` | Output format: `table`, `json` | table |
| `--update-prices` | Scrape docs and update local JSON | false |
| `--prices-file` | Path to prices JSON | `opencode_prices.json` |
| `--go-value` | Estimated Go monthly value ($) | 60.0 |

---

### `openrouter_cheap_models.py`

Fetches models from OpenRouter and filters free/cheap ones, segmented by type.

**Features:**
- Fetches text, embedding, and transcription models
- Filters by price threshold
- Handles audio (per-second) pricing
- Outputs table or JSON

**Usage:**

```bash
# List models under $0.03/1M tokens (default)
python openrouter_cheap_models.py

# Custom threshold
python openrouter_cheap_models.py --threshold 0.05

# Price range
python openrouter_cheap_models.py --min 0.01 --max 0.10

# JSON output
python openrouter_cheap_models.py --output json
```

**Flags:**

| Flag | Description | Default |
|------|-------------|---------|
| `--threshold` | Max $/1M tokens | 0.03 |
| `--min` | Min $/1M tokens (optional) | None |
| `--max` | Max $/1M tokens (overrides threshold) | None |
| `--output` | Output format: `table`, `json` | table |

---

## Setup

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Dependencies:** `requests==2.32.3`

## Data

`opencode_prices.json` contains scraped pricing data from OpenCode docs. Update it with:

```bash
python opencode_price_estimator.py --update-prices
```

## License

MIT
