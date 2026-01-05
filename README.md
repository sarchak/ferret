# FERRET

**Federal Expenditure Review and Risk Evaluation Tool**

An AI-native agent that autonomously investigates federal contracts for fraud indicators. Built as part of [The AI Shift](https://theaishift.dev) newsletter series on AI-native development.

**📬 Subscribe to [theaishift.dev](https://theaishift.dev) for weekly deep-dives on building AI-native systems.**

> **Educational Project**: This demonstrates AI-native architecture patterns. The detectors have false positives—a flagged contract may be completely legitimate. This is not production fraud detection software.

## What Makes This AI-Native?

Most "AI features" look like this:
```
User Input → LLM Call → Response → Done
```

FERRET is different:
```
Trigger → Agent Loop → [Tool → Reason → Decide → Tool → ...] → Complete
```

The agent doesn't just respond—it **investigates**. It decides what to search, follows leads, pivots when it finds something interesting, and stops when it has enough evidence.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/sarchak/ferret.git
cd ferret

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env
# Edit .env with your API keys (optional - see below)

# Run a scan of recent contracts
uv run python daily_scan.py --days 2

# Investigate a specific contract
uv run python agent.py investigate CONTRACT_ID
```

### API Keys

| Key | Required | Purpose |
|-----|----------|---------|
| `ANTHROPIC_API_KEY` | Only for standalone scripts | Not needed with Claude Code CLI |
| `SAM_GOV_API_KEY` | No | Increases rate limit (10/min → 1000/day) |

USASpending.gov requires no API key.

## What It Does

FERRET scans federal contracts and flags suspicious patterns:

```
$ uv run python daily_scan.py --days 2

Fetching contracts from last 2 day(s)...
  Fetched 290 contracts from 3 page(s)
Loading entity index from cache... 868,090 entities loaded
Analyzing contracts for fraud indicators...
  Running 20 parallel analyzers...
  Completed: 290 contracts analyzed, 53 flagged

FRAUD SCAN REPORT - 2026-01-04
Period: last 2 day(s)

CONTRACTS SCANNED: 290
CONTRACTS FLAGGED: 53 (18.3%)

RISK BREAKDOWN:
  CRITICAL:   0
  HIGH:       0
  MEDIUM:     0
  LOW:       53
```

When it flags HIGH or CRITICAL risks, it **automatically investigates**—searching the web, verifying companies exist, and building evidence.

## Detection Categories

| Detector | What It Finds |
|----------|---------------|
| `benford.py` | Statistically suspicious pricing patterns |
| `temporal.py` | Weekend awards, fiscal year-end rushes |
| `pricing.py` | Threshold avoidance, contract splitting |
| `competition.py` | Single-offer "competitions," bid rigging signals |
| `employee_revenue.py` | Shell companies (0 employees, millions in contracts) |
| `modifications.py` | Lowball-then-modify schemes |
| `registration.py` | Entities created right before winning |
| `address.py` | Virtual offices, shared address networks |

## Project Structure

```
ferret/
├── agent.py                 # Main agent with investigation capabilities
├── daily_scan.py            # Batch scanning with parallel processing
├── data_sources/
│   ├── usaspending.py       # USASpending.gov API client
│   ├── sam_gov.py           # SAM.gov API client
│   ├── bulk_data.py         # Bulk data downloads (875K+ entities)
│   └── web_research.py      # Web search prompts and templates
├── detectors/
│   ├── comprehensive_detector.py  # Orchestrates all detectors
│   ├── benford.py           # Benford's Law analysis
│   ├── temporal.py          # Timing pattern detection
│   ├── pricing.py           # Pricing anomaly detection
│   ├── competition.py       # Competition analysis
│   ├── employee_revenue.py  # Shell company detection
│   ├── modifications.py     # Modification pattern detection
│   ├── registration.py      # Registration timing analysis
│   └── address.py           # Address verification
├── skills/
│   └── fraud-investigator/
│       └── SKILL.md         # Investigation skill for Claude
├── data/                    # Bulk data (gitignored, download separately)
├── outputs/                 # Scan results (gitignored)
└── reports/                 # Investigation reports (gitignored)
```

## Build in Public: The AI Shift Series

This project is being built in public over 7 weeks as part of The AI Shift newsletter:

| Week | Topic | What Ships |
|------|-------|------------|
| 1 | What AI-Native Actually Means | Basic agent architecture |
| 2 | Autonomous Investigation | Investigation with web search |
| 3 | Skills as Domain Expertise | Fraud investigator skill |
| 4 | Multi-Source Data Integration | USASpending + SAM.gov + Web |
| 5 | Pattern Detection and Judgment | 8 fraud detectors |
| 6 | Scaling Autonomous Investigations | Parallel batch scanning |
| 7 | When to Build AI-Native | Complete system, decision framework |

Each week has a corresponding git tag: `week-1`, `week-2`, etc.

**Subscribe:** [theaishift.dev](https://theaishift.dev)

## Commands

```bash
# Scan recent contracts
uv run python daily_scan.py --days 7

# Scan with date range
uv run python daily_scan.py --start-date 2025-01-01 --end-date 2025-01-31

# Deep analysis (pricing, bid rigging, contract splitting)
uv run python daily_scan.py --days 2 --deep

# Filter by agency
uv run python daily_scan.py --days 7 --agency "Department of Defense"

# Investigate specific contract
uv run python agent.py investigate W912DY-23-C-0042

# Investigate contractor by name
uv run python agent.py entity "COMPANY NAME"

# Export results
uv run python daily_scan.py --days 7 --format json --output ./reports
```

## Bulk Data Setup

For full entity lookups (875K+ contractors), download SAM.gov bulk data:

1. Go to [sam.gov/data-services](https://sam.gov/data-services/entity-registration/public-extracts)
2. Sign in with Login.gov
3. Download "SAM Entity Management Public Extract"
4. Extract to `data/sam_entities/`

The first run builds a pickle index (~160MB). Subsequent runs load instantly.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FERRET Agent                            │
├─────────────────────────────────────────────────────────────┤
│  Trigger: Schedule or Manual                                │
│     ↓                                                       │
│  Fetch: USASpending API → Recent contracts                  │
│     ↓                                                       │
│  Detect: 8 pattern detectors → Risk scores                  │
│     ↓                                                       │
│  Investigate (if HIGH/CRITICAL):                            │
│     ┌──────────────────────────────────────────┐            │
│     │  Agent Loop (up to 10 turns)             │            │
│     │    → WebSearch: Verify company           │            │
│     │    → WebSearch: Check for fraud/lawsuits │            │
│     │    → WebFetch: Gather evidence           │            │
│     │    → Reason: Assess findings             │            │
│     │    → Decide: Continue or conclude        │            │
│     └──────────────────────────────────────────┘            │
│     ↓                                                       │
│  Report: Evidence-based investigation report                │
└─────────────────────────────────────────────────────────────┘
```

## Data Sources

All data sources are **free and public**:

| Source | Purpose | Rate Limit | Key Required |
|--------|---------|------------|--------------|
| [USASpending.gov](https://api.usaspending.gov/) | Contract data | Generous | No |
| [SAM.gov](https://sam.gov/) | Contractor info | 10/min (1000/day with key) | Optional |
| Web Search | News, verification | Via Claude | N/A |

## Contributing

This is an educational project. Contributions welcome:

- New detection patterns
- False positive analysis
- Documentation improvements
- Test cases

## License

MIT

## Disclaimer

**This is an educational project demonstrating AI-native development patterns.**

- Flagged contracts may be completely legitimate
- Detection patterns have false positives
- Not intended for actual fraud prosecution
- Use responsibly and ethically

The goal is showing *how* AI-native systems work—autonomous reasoning, tool use, and judgment—not building production fraud detection.
