# check_opencore_models

Tools for discovering and comparing free/cheap AI models across [OpenCode](https://opencode.ai) (Zen & Go plans) and [OpenRouter](https://openrouter.ai).

## Overview

| Script | Provider | Purpose |
|--------|----------|---------|
| `opencode_price_estimator.py` | OpenCode Zen/Go | List cheap models, compare Zen vs Go plans, estimate costs |
| `openrouter_cheap_models.py` | OpenRouter | List cheap models by category (text, embedding, transcription) |
| `token_usage_checker.py` | OpenCode Go | Check subscription quota usage (rolling, weekly, monthly) |
| `openrouter_usage_checker.py` | OpenRouter | Check credit balance, usage by period, and cost projections |

---

## `opencode_price_estimator.py`

Fetches models from the OpenCode Zen API, enriches them with pricing scraped from official docs, and filters/estimates costs.

**Data sources:**
- API: `https://opencode.ai/zen/v1/models`
- Zen docs: `https://opencode.ai/docs/zen`
- Go docs: `https://opencode.ai/docs/go/`
- Local cache: `opencode_prices.json`

**What it does:**
- Lists all models with input/output pricing per million tokens
- Filters by price range (min/max)
- Segments by provider: Zen (pay-as-you-go), Go (subscription), or both
- Estimates cost for a given token usage (input + output)
- Compares Zen pay-as-you-go vs Go subscription value ($10/mo, ~$60 estimated usage)
- Scrapes and saves updated pricing to local JSON

### Examples

```bash
# List all models under $2/1M tokens
python opencode_price_estimator.py

# Only free models
python opencode_price_estimator.py --threshold 0.00

# Only Zen models, max $1/1M
python opencode_price_estimator.py --provider zen --threshold 1.00

# Show Zen and Go tables separately
python opencode_price_estimator.py --segment

# Estimate cost: 5M input tokens + 2M output tokens
python opencode_price_estimator.py --estimate 5000000 2000000

# JSON output for scripting
python opencode_price_estimator.py --output json

# Refresh prices from OpenCode docs
python opencode_price_estimator.py --update-prices
```

### Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--threshold` | Max price ($/1M tokens) | `2.00` |
| `--min` | Min price ($/1M tokens) | — |
| `--max` | Max price ($/1M tokens, overrides `--threshold`) | — |
| `--provider` | Filter: `all`, `zen`, `go` | `all` |
| `--segment` | Show separate Zen/Go tables | `false` |
| `--estimate` | Cost estimate: `<input_tokens> <output_tokens>` | — |
| `--output` | Format: `table`, `json` | `table` |
| `--update-prices` | Scrape docs and update `opencode_prices.json` | `false` |
| `--prices-file` | Custom prices JSON path | `opencode_prices.json` |
| `--go-value` | Estimated Go monthly usage value ($) | `60.0` |

---

## `openrouter_cheap_models.py`

Fetches models from OpenRouter API and filters cheap/free ones. Results are segmented by modality.

**Data sources:**
- Text models: `https://openrouter.ai/api/v1/models`
- Embedding models: `https://openrouter.ai/api/v1/embeddings/models`
- Transcription models: `https://openrouter.ai/api/v1/models?output_modalities=transcription`

**What it does:**
- Lists text, embedding, and transcription models with pricing
- Handles per-token pricing (text/embedding) and per-second pricing (audio/transcription)
- Filters by price range (min/max)
- Free models and negative prices (variable pricing) are handled specially

### Examples

```bash
# List models under $0.03/1M tokens
python openrouter_cheap_models.py

# Only free models
python openrouter_cheap_models.py --threshold 0.00

# Models between $0.01 and $0.10/1M
python openrouter_cheap_models.py --min 0.01 --max 0.10

# JSON output
python openrouter_cheap_models.py --output json
```

### Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--threshold` | Max price ($/1M tokens) | `0.03` |
| `--min` | Min price ($/1M tokens) | — |
| `--max` | Max price ($/1M tokens, overrides `--threshold`) | — |
| `--output` | Format: `table`, `json` | `table` |

---

## `token_usage_checker.py`

Comprehensive token usage report with rich terminal UI, cost projections, and efficiency analysis.

**Data sources:**
- API: `https://opencode.ai/zen/go/v1/usage` (Go quota)
- Database: `~/.local/share/opencode/opencode.db` (historical usage)
- Auth: `~/.local/share/opencode/auth.json`

**What it does:**
- Checks OpenCode Go subscription quota (rolling/weekly/monthly) with visual progress bars
- Reads historical token usage from local database
- Shows usage breakdown by model with efficiency analysis (output/input ratio)
- Calculates cost projections (daily, monthly, yearly)
- Displays usage patterns by hour (peak detection)
- Shows budget alerts and remaining balance
- Lists recent sessions with duration and token counts

### Examples

```bash
# Full detailed report
python token_usage_checker.py

# With budget limit ($50/month)
python token_usage_checker.py --budget 50

# Summary only (one line)
python token_usage_checker.py --summary-only

# JSON output for scripting
python token_usage_checker.py --output json

# Last 7 days only
python token_usage_checker.py --days 7

# Use custom files
python token_usage_checker.py --auth-file /path/to/auth.json --db-file /path/to/opencode.db
```

### Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--auth-file` | Path to auth.json file | `~/.local/share/opencode/auth.json` |
| `--db-file` | Path to OpenCode database | `~/.local/share/opencode/opencode.db` |
| `--output` | Format: `table`, `json` | `table` |
| `--days` | Days to include in history | `30` |
| `--summary-only` | Show only summary line | `false` |
| `--budget` | Monthly budget in USD for alerts | `0` (no limit) |
| `--key-name` | Key name in auth.json | `opencode-go` |

### Report Sections

1. **Cuota OpenCode Go** - Rolling (24h), weekly, monthly percentages with progress bars
2. **Resumen Total** - All-time token counts, costs, and budget status
3. **Eficiencia por Modelo** - Output/input ratio, cost per session, avg duration
4. **Patrones de Uso** - Activity by hour with peak detection
5. **Proyeccion de Costos** - Daily avg, monthly/yearly projections, budget comparison
6. **Tendencia Diaria** - Usage trends with visual bars
7. **Sesiones Recientes** - Last 10 sessions with details

### Visual Features (using rich)

- Color-coded progress bars (green/yellow/orange/red)
- Tables with borders and styling
- Panels for section separation
- Budget status indicators
- Peak hour detection

### Limitations

- **OpenCode Zen**: Balance is not available via API. Use the web console at https://opencode.ai/workspace/ to check your balance.
- **OpenRouter**: Not supported (no API key configured).

### Setup

1. Install dependencies:
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Get your API key from https://opencode.ai/workspace/

3. Ensure `~/.local/share/opencode/auth.json` contains your key:
   ```json
   {
     "opencode-go": {
       "type": "api",
       "key": "YOUR_KEY_HERE"
     }
   }
   ```

4. Run the script

---

## `openrouter_usage_checker.py`

Comprehensive usage report for OpenRouter API with rich terminal UI.

**Data sources:**
- API: `https://openrouter.ai/api/v1/key` (key usage)
- API: `https://openrouter.ai/api/v1/credits` (balance, requires management key)
- Auth: `~/.local/share/opencode/auth.json` or `OPENROUTER_API_KEY` env var

**What it does:**
- Checks key info (label, tier, limits)
- Shows credit balance and remaining
- Displays usage by period (daily, weekly, monthly)
- Calculates cost projections
- Budget alerts and status

### Examples

```bash
# Full report
python openrouter_usage_checker.py

# With budget limit
python openrouter_usage_checker.py --budget 20

# Summary only
python openrouter_usage_checker.py --summary-only

# JSON output
python openrouter_usage_checker.py --output json

# Direct API key
python openrouter_usage_checker.py --api-key sk-or-v1-xxx
```

### Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--auth-file` | Path to auth.json file | `~/.local/share/opencode/auth.json` |
| `--output` | Format: `table`, `json` | `table` |
| `--budget` | Monthly budget in USD for alerts | `0` (no limit) |
| `--summary-only` | Show only summary line | `false` |
| `--api-key` | API key directly (overrides auth.json) | — |

### Report Sections

1. **Info de Key** - Label, tier (Free/Paid), key limit
2. **Saldo y Créditos** - Total purchased, used, remaining
3. **Uso por Período** - Daily, weekly, monthly with visual bars
4. **Proyección de Costos** - Daily avg, monthly/yearly projections
5. **Estado del Presupuesto** - Budget status and remaining
6. **Límites de Key** - Key-specific limits and reset info

### Authentication

Priority order:
1. `--api-key` parameter
2. `OPENROUTER_API_KEY` environment variable
3. `auth.json` → `"openrouter"` → `"key"`
4. `auth.json` → first key with `sk-or` prefix

### Setup

1. Get your API key from https://openrouter.ai/keys

2. Add to `~/.local/share/opencode/auth.json`:
   ```json
   {
     "opencode-go": { ... },
     "openrouter": {
       "type": "api",
       "key": "sk-or-v1-YOUR_KEY"
     }
   }
   ```

3. Run the script

### Notes

- **Management Key**: Needed for `/credits` endpoint (full balance)
- **Normal Key**: Only shows key-level usage and limits
- **Credits vs Key Limit**: Credits = account balance, Key limit = per-key spending cap

---

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Dependencies:** `requests==2.32.3`, `rich>=13.0.0`

## Data

`opencode_prices.json` is auto-generated by `opencode_price_estimator.py --update-prices`. It contains scraped pricing with source tags (`zen`, `go`, `both`) and context lengths.

## License

MIT
