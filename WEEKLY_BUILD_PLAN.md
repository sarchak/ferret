# FERRET: Weekly Build Plan

This document outlines what ships each week as part of The AI Shift newsletter series.

## Philosophy

Each week delivers:
1. **Working code** you can clone and run
2. **A newsletter issue** explaining the concepts
3. **Git tag** (`week-1`, `week-2`, etc.) for that week's snapshot

The code builds incrementally. Week 1 is minimal. Week 7 is the complete system.

---

## Week 1: What AI-Native Actually Means

**Newsletter:** The distinction between AI-powered and AI-native

**Code Ships:**
```
ferret/
├── agent.py              # Basic agent with simple contract lookup
├── data_sources/
│   └── usaspending.py    # USASpending API client
├── pyproject.toml
├── README.md
└── .env.example
```

**What It Does:**
- Fetch a contract by ID
- Display contract details
- Basic agent structure (no investigation yet)

**Key Concepts:**
- Agent loop architecture
- Tool-based interaction
- Why prompt→response isn't enough

**Run It:**
```bash
uv run python agent.py lookup CONTRACT_ID
```

---

## Week 2: Autonomous Investigation

**Newsletter:** How agents follow leads and make decisions

**Code Ships:**
```
ferret/
├── agent.py              # + investigate_contract() with WebSearch
├── data_sources/
│   ├── usaspending.py
│   └── web_research.py   # NEW: Search query templates
└── ...
```

**What It Does:**
- Investigate a flagged contract
- Agent decides what to search
- Follow leads autonomously
- Generate investigation report

**Key Concepts:**
- Reasoning chains
- Tool chaining
- When to stop investigating

**Run It:**
```bash
uv run python agent.py investigate CONTRACT_ID
```

---

## Week 3: Skills as Domain Expertise

**Newsletter:** Encoding investigator knowledge

**Code Ships:**
```
ferret/
├── skills/
│   └── fraud-investigator/
│       └── SKILL.md      # NEW: Investigation skill
├── agent.py              # Updated to use skill
└── ...
```

**What It Does:**
- Skill-driven investigation
- Encoded fraud detection patterns
- Structured output format

**Key Concepts:**
- Skills vs raw prompts
- Encoding judgment (not rules)
- Skill composition

**Run It:**
```bash
# With Claude Code CLI
cc "investigate contractor ACME Corp for fraud indicators"
```

---

## Week 4: Multi-Source Data Integration

**Newsletter:** Connecting real-world APIs

**Code Ships:**
```
ferret/
├── data_sources/
│   ├── usaspending.py    # Enhanced with more endpoints
│   ├── sam_gov.py        # NEW: SAM.gov API client
│   ├── bulk_data.py      # NEW: Bulk data downloads
│   └── web_research.py
└── ...
```

**What It Does:**
- Cross-reference USASpending + SAM.gov
- Load bulk entity data (875K+ contractors)
- Combine structured data with web research

**Key Concepts:**
- API rate limiting
- Caching strategies
- Combining structured/unstructured data

**Run It:**
```bash
uv run python agent.py entity "COMPANY NAME"
```

---

## Week 5: Pattern Detection and Judgment

**Newsletter:** Where AI shines over rules

**Code Ships:**
```
ferret/
├── detectors/
│   ├── __init__.py
│   ├── comprehensive_detector.py  # NEW: Orchestrator
│   ├── benford.py        # NEW: Benford's Law
│   ├── temporal.py       # NEW: Timing patterns
│   ├── pricing.py        # NEW: Pricing anomalies
│   ├── competition.py    # NEW: Competition analysis
│   ├── employee_revenue.py  # NEW: Shell company detection
│   ├── modifications.py  # NEW: Modification patterns
│   ├── registration.py   # NEW: Registration timing
│   └── address.py        # NEW: Address verification
└── ...
```

**What It Does:**
- 8 specialized fraud detectors
- Risk scoring (0-100)
- Combine signals into assessment

**Key Concepts:**
- Signals vs rules
- Fuzzy pattern matching
- Human-in-the-loop design

**Run It:**
```bash
uv run python -c "from detectors import ComprehensiveFraudDetector; ..."
```

---

## Week 6: Scaling Autonomous Investigations

**Newsletter:** From single contract to batch scanning

**Code Ships:**
```
ferret/
├── daily_scan.py         # NEW: Batch scanner
├── agent.py              # Updated with daily-scan command
└── ...
```

**What It Does:**
- Scan thousands of contracts
- Parallel processing (20 workers)
- Auto-investigate HIGH/CRITICAL alerts
- Progress logging

**Key Concepts:**
- Prioritization strategies
- Cost optimization
- Alert system design

**Run It:**
```bash
uv run python daily_scan.py --days 7 --deep
```

---

## Week 7: When to Build AI-Native

**Newsletter:** Decision framework and lessons learned

**Code Ships:**
- Complete system documentation
- Decision framework guide
- Performance benchmarks
- Future roadmap

**What It Does:**
- Everything from weeks 1-6
- Production-ready (educational) system

**Key Concepts:**
- Criteria for AI-native applications
- Cost/benefit analysis
- What we learned

---

## Git Workflow

```bash
# After each week's work
git tag -a week-1 -m "Week 1: Basic agent architecture"
git push origin week-1

# Users can checkout any week
git checkout week-1  # Minimal version
git checkout week-7  # Complete system
```

## Skills Used

Throughout the series, we use Claude Code with these tools:

| Tool | Purpose |
|------|---------|
| `WebSearch` | Search for company information |
| `WebFetch` | Retrieve specific web pages |
| `Read` | Read local files and data |
| `Bash` | Run Python scripts |
| `Skill` | Invoke fraud-investigator skill |

The key insight: **the agent decides how to use these tools.** We don't script the sequence—we give goals and let the agent reason.

## Credential Safety Checklist

Before each week's push:

- [ ] `.env` is gitignored (contains real API keys)
- [ ] `data/` is gitignored (bulk data, 160MB+)
- [ ] `outputs/` is gitignored (may contain contractor info)
- [ ] `reports/` is gitignored (investigation reports)
- [ ] `.claude/settings.local.json` is gitignored
- [ ] No hardcoded API keys in source files
- [ ] `.env.example` has placeholder values only

## Newsletter + Code Sync

| Week | Newsletter Issue | Git Tag | Key File |
|------|-----------------|---------|----------|
| 1 | What AI-Native Actually Means | `week-1` | `agent.py` |
| 2 | Autonomous Investigation | `week-2` | `web_research.py` |
| 3 | Skills as Domain Expertise | `week-3` | `skills/fraud-investigator/SKILL.md` |
| 4 | Multi-Source Data Integration | `week-4` | `data_sources/*.py` |
| 5 | Pattern Detection and Judgment | `week-5` | `detectors/*.py` |
| 6 | Scaling Autonomous Investigations | `week-6` | `daily_scan.py` |
| 7 | When to Build AI-Native | `week-7` | Full system |
