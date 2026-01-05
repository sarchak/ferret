# FERRET

**Federal Expenditure Review and Risk Evaluation Tool**

An AI-native agent that autonomously investigates federal contracts for fraud indicators.

## Project Overview

This is a **truly AI-native application** — the agent autonomously:
- Pulls data from multiple APIs (USASpending, SAM.gov)
- Researches contractors via web search
- Makes judgment calls about suspicious patterns
- Follows leads when something looks off
- Generates investigation reports with evidence

**This cannot be done with prompt → response.** It requires an agent loop with tool use.

## Quick Start

```bash
# Install dependencies
uv sync

# Set API keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# Scan recent contracts
uv run python daily_scan.py --days 2

# Investigate a single contract
uv run python agent.py investigate CONTRACT_ID

# Generate report
uv run python agent.py report CONTRACT_ID
```

## Project Structure

```
ferret/
├── agent.py                 # Main agent using Claude SDK
├── daily_scan.py            # Batch scanning with parallel processing
├── data_sources/
│   ├── usaspending.py       # USASpending.gov API client
│   ├── sam_gov.py           # SAM.gov API client
│   ├── bulk_data.py         # Bulk data downloads
│   └── web_research.py      # Web search and verification
├── detectors/
│   ├── comprehensive_detector.py  # Orchestrates all detectors
│   ├── benford.py           # Benford's Law analysis
│   ├── temporal.py          # Timing pattern detection
│   ├── pricing.py           # Pricing anomaly detection
│   └── ...                  # 8 total detectors
├── skills/
│   └── fraud-investigator/
│       └── SKILL.md         # Investigation skill for Claude
├── data/                    # Bulk data (gitignored)
├── outputs/                 # Scan results (gitignored)
├── reports/                 # Investigation reports (gitignored)
├── SPEC.md                  # Full specification
└── CLAUDE.md                # This file
```

## Data Sources

All data sources are **free and public**:

| Source | Purpose | Rate Limit |
|--------|---------|------------|
| USASpending.gov | Contract data | Generous |
| SAM.gov | Contractor info | 1000/day |
| Web Search | News, company research | Via Claude |

## Key Commands

```bash
# Scan recent contracts
uv run python daily_scan.py --days 7

# Deep analysis mode
uv run python daily_scan.py --days 2 --deep

# Investigate specific contract
uv run python agent.py investigate W912DY-23-C-0042

# Scan DOD contracts from last week
uv run python agent.py scan --agency DOD --days 7

# Check a specific contractor
uv run python agent.py entity "COMPANY NAME"

# Generate full report
uv run python agent.py report W912DY-23-C-0042 --output reports/
```

## Fraud Detection Patterns

The agent looks for:

1. **Shell Company Indicators**
   - Recent incorporation/registration
   - Shared addresses with other contractors
   - Virtual office addresses
   - Minimal web/LinkedIn presence

2. **Pricing Anomalies**
   - Benford's Law violations
   - Threshold avoidance
   - Excessive modifications

3. **Competition Issues**
   - Single-offer "competitions"
   - Bid rigging signals

4. **Timing Red Flags**
   - Weekend awards
   - Fiscal year-end rushes
   - Rapid first award after registration

## Development

```bash
# Run tests
uv run pytest

# Type check
uv run mypy .

# Format code
uv run ruff format .
```

## Environment Variables

```bash
ANTHROPIC_API_KEY=your-api-key
SAM_GOV_API_KEY=your-sam-key  # Optional, increases rate limit
```

## Disclaimer

This is an educational project demonstrating AI-native development patterns. The detectors have false positives—a flagged contract may be completely legitimate.
