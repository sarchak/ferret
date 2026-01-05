# FERRET - Federal Expenditure Review and Risk Evaluation Tool

## Problem Statement

**The U.S. government spends $700+ billion annually on contracts, but detects only a fraction of fraud.**

| Reality | Data |
|---------|------|
| Annual federal contract spending | $700+ billion |
| Confirmed DOD fraud (7 years) | $11 billion — "a small fraction" of actual fraud |
| Fraud recoveries (FY2024) | $2.9 billion |
| Largest single settlement | $428 million |

### Why It's Hard Today

1. **Volume**: Thousands of contracts awarded daily
2. **Manual investigation**: Each case takes investigators weeks
3. **Siloed data**: Contract data, company records, court filings, news — all separate
4. **Reactive**: Fraud discovered after the money is gone

### The Solution

An **autonomous AI agent** that continuously monitors federal contracts, investigates contractors, and flags fraud indicators — before the money is spent.

```
Today:     Contract awarded → Years pass → Whistleblower → Investigation → Recovery
           (fraud already happened)

With Agent: Contract awarded → Agent investigates → Flags risk → Human reviews → Prevented
            (catch it early)
```

---

## What Makes This AI-Native

This **requires** an autonomous agent because:

| Requirement | Why Agent Loop is Necessary |
|-------------|----------------------------|
| Multi-source data | Must pull from USASpending, SAM.gov, SEC, web, news |
| Judgment calls | Is this address suspicious? Is this pricing unusual? |
| Follow leads | If company X looks off, research their subsidiaries |
| Unpredictable paths | Every investigation is different |
| Tool use | APIs, web search, document analysis |

**This is NOT possible with prompt → response.** The agent must autonomously decide what to investigate next.

---

## Data Sources (All Free/Public)

### Tier 1: Core Federal Data

| Source | Data | API |
|--------|------|-----|
| USASpending.gov | All contracts, grants, loans | https://api.usaspending.gov/ |
| SAM.gov Entity API | Contractor registrations | https://open.gsa.gov/api/entity-api/ |
| SAM.gov Exclusions API | Debarred contractors | https://open.gsa.gov/api/exclusions-api/ |
| FPDS | Detailed procurement data | SOAP/XML |
| SEC EDGAR | Public company filings | https://www.sec.gov/developer |

### Tier 2: Investigation Data

| Source | Data |
|--------|------|
| State SOS databases | Business registrations, officers |
| OpenCorporates | Company registry data |
| OFAC Sanctions List | Sanctioned entities |
| Google Maps | Address verification |
| LinkedIn | Company/officer info |
| News sources | Lawsuits, scandals, financial trouble |

---

## Fraud Detection Patterns

### 1. Shell Company Indicators

| Signal | Data Source |
|--------|-------------|
| Recent incorporation (< 6 months before award) | State SOS |
| Recent SAM registration (< 90 days before award) | SAM.gov |
| Known shell company registered agent | State SOS |
| Address shared with 5+ other contractors | SAM.gov + analysis |
| Virtual office / mailbox address | Google Maps |
| No website or website < 6 months old | Web research |
| Minimal LinkedIn presence (< 5 employees) | LinkedIn |

### 2. Conflict of Interest Indicators

| Signal | Data Source |
|--------|-------------|
| Officer was employee of awarding agency | LinkedIn + news |
| Officer left agency within 2 years of award | LinkedIn |
| Officer appears on multiple federal contractors | SAM.gov + analysis |
| Political donations to relevant officials | FEC data |

### 3. Pricing Anomalies

| Signal | Data Source |
|--------|-------------|
| Price > 150% of similar contracts | USASpending analysis |
| Modifications > 50% of original value | USASpending |
| Sole source without clear justification | Contract data |
| Unusual payment patterns | USASpending |

### 4. Subcontracting Red Flags

| Signal | Data Source |
|--------|-------------|
| Pass-through arrangements (prime does no work) | FSRS + investigation |
| Related party subcontracts | Officer analysis |
| Excessive subcontractor concentration | FSRS |
| Subcontractor is also prime on related contracts | USASpending |

---

## Agent Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FERRET AGENT                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  TRIGGER: New contracts from USASpending API (daily/weekly scan)            │
│                                                                              │
│  FOR EACH CONTRACT:                                                          │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 1. FETCH CONTRACT DATA                                               │    │
│  │    • Contract details (USASpending)                                  │    │
│  │    • Contractor entity info (SAM.gov)                                │    │
│  │    • Historical awards to same contractor                            │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 2. INVESTIGATE CONTRACTOR                                            │    │
│  │    • State incorporation records                                     │    │
│  │    • Physical address verification                                   │    │
│  │    • Web presence analysis                                           │    │
│  │    • Officer background research                                     │    │
│  │    • News/litigation search                                          │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 3. DETECT FRAUD PATTERNS                                             │    │
│  │    • Shell company signals                                           │    │
│  │    • Conflict of interest signals                                    │    │
│  │    • Pricing anomalies                                               │    │
│  │    • Subcontracting red flags                                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                              ↓                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 4. GENERATE REPORT                                                   │    │
│  │    • Risk score (0-100)                                              │    │
│  │    • Evidence summary                                                │    │
│  │    • Recommended actions                                             │    │
│  │    • Full investigation trail                                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  OUTPUT: Prioritized list of flagged contracts for human review             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Technical Implementation

### Claude Agent SDK Usage

```python
from claude_agent_sdk import query, ClaudeAgentOptions

async def investigate_contract(contract_id: str):
    async for message in query(
        prompt=f"""Investigate federal contract {contract_id} for fraud indicators.

1. Fetch contract details from USASpending API
2. Research the contractor:
   - SAM.gov registration
   - State incorporation records
   - Physical address verification
   - Web presence
   - Officer backgrounds
3. Check for fraud patterns:
   - Shell company indicators
   - Conflict of interest
   - Pricing anomalies
4. Generate a risk assessment report with evidence

Use the available tools to gather data and make your investigation thorough.""",
        options=ClaudeAgentOptions(
            cwd="/path/to/project",
            allowed_tools=["Read", "Bash", "WebSearch", "WebFetch"],
            permission_mode="bypassPermissions"
        )
    ):
        if hasattr(message, 'result'):
            return message.result
```

### Tools the Agent Uses

| Tool | Purpose |
|------|---------|
| `Bash` | Call APIs (curl), run Python scripts |
| `WebSearch` | Search for news, company info |
| `WebFetch` | Fetch web pages, verify addresses |
| `Read` | Read cached data, previous reports |
| `Write` | Save investigation reports |

---

## Target Customers

| Customer | Pain Point | Value Proposition | Price Point |
|----------|------------|-------------------|-------------|
| Inspectors General (OIGs) | Mandated to find fraud, limited staff | 10x investigation throughput | $100k-500k/year |
| Prime contractors | Must vet subcontractors | Avoid liability, protect reputation | $50k-200k/year |
| Qui Tam law firms | Find whistleblower cases | Automated lead generation | Revenue share (15-30%) |
| Investigative journalists | Stories on waste/fraud | Research automation | $5k-20k/year |
| Government affairs consultants | Client due diligence | Risk assessment reports | Per-report pricing |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Contracts analyzed per day | 1,000+ |
| False positive rate | < 20% |
| Time to investigate one contract | < 5 minutes |
| Fraud indicators detected (vs manual) | 10x more coverage |
| Cost per investigation | < $1 (API + compute) |

---

## Implementation Phases

### Phase 1: MVP (Weeks 1-2)
- [ ] USASpending API client
- [ ] SAM.gov API client
- [ ] Basic shell company detection
- [ ] Single contract investigation flow
- [ ] CLI interface

### Phase 2: Core Detection (Weeks 3-4)
- [ ] All fraud detection patterns
- [ ] Web research integration
- [ ] Batch processing (analyze multiple contracts)
- [ ] Report generation

### Phase 3: Scale (Weeks 5-6)
- [ ] Daily automated scanning
- [ ] Dashboard/UI
- [ ] Alert notifications
- [ ] Historical analysis

### Phase 4: Production (Weeks 7-8)
- [ ] API for external integration
- [ ] User authentication
- [ ] Audit trail
- [ ] Performance optimization

---

## References

- [USASpending API Documentation](https://api.usaspending.gov/)
- [SAM.gov API Documentation](https://open.gsa.gov/api/)
- [GSA Procurement Fraud Handbook](https://www.gsaig.gov/sites/default/files/misc-reports/ProcurementFraudHandbook_0.pdf)
- [DOJ False Claims Act Settlements](https://www.justice.gov/civil/false-claims-act)
- [GAO Reports on Contracting Fraud](https://www.gao.gov/)
