---
name: fraud-investigator
description: Investigate federal contracts and contractors for fraud indicators. Use when analyzing government spending, contractor behavior, shell companies, conflicts of interest, or pricing anomalies.
allowed-tools:
  - Bash
  - Read
  - Write
  - WebSearch
  - WebFetch
---

# FERRET Fraud Investigator Skill

## Purpose
Conduct thorough investigations of federal contracts and contractors to identify fraud indicators, document evidence, and generate actionable reports.

## Data Sources

### Primary APIs
- **USASpending.gov**: Contract data, award amounts, recipients, agencies
- **SAM.gov Entity API**: Contractor registrations, addresses, officers
- **SAM.gov Exclusions API**: Debarred/suspended contractors

### Web Research
- Company websites and age verification
- LinkedIn employee counts
- News and litigation searches
- Address verification (virtual office detection)
- Officer background research

## Fraud Detection Patterns

### 1. Shell Company Indicators
| Signal | How to Check | Risk Level |
|--------|--------------|------------|
| SAM registration < 90 days before award | SAM.gov registration_date | High |
| Virtual office address (Regus, UPS Store) | WebSearch address | High |
| No website or website < 6 months old | WebSearch + WHOIS | Medium |
| LinkedIn shows < 5 employees | WebSearch LinkedIn | Medium |
| Shared address with 5+ contractors | SAM.gov address analysis | High |

### 2. Conflict of Interest Indicators
| Signal | How to Check | Risk Level |
|--------|--------------|------------|
| Officer was agency employee | LinkedIn + news search | High |
| Left agency within 2 years of award | LinkedIn timeline | High |
| Officer on multiple contractors | SAM.gov cross-reference | Medium |
| Political donations to relevant officials | FEC data (future) | Medium |

### 3. Pricing Anomalies
| Signal | How to Check | Risk Level |
|--------|--------------|------------|
| Sole source without justification | Contract competition_type | Medium |
| Only 1 offer received | Contract number_of_offers | Medium |
| Excessive modifications (>50% original) | USASpending modifications | High |
| Price > 150% of similar contracts | USASpending comparison | High |

## Investigation Workflow

### Step 1: Contract Data Retrieval
```bash
# Get contract details
cd /path/to/project && uv run python -c "
import asyncio
from data_sources import USASpendingClient

async def get():
    client = USASpendingClient()
    contract = await client.get_contract_details('CONTRACT_ID')
    await client.close()
    # Print contract details...

asyncio.run(get())
"
```

### Step 2: Contractor Verification
```bash
# Check SAM.gov registration
cd /path/to/project && uv run python -c "
import asyncio
from data_sources import SAMGovClient

async def check():
    client = SAMGovClient()
    entity = await client.get_entity_by_uei('UEI')
    exclusions = await client.check_exclusions(uei='UEI')
    await client.close()
    # Print registration and exclusion status...

asyncio.run(check())
"
```

### Step 3: Web Research
Use WebSearch for each of these:
1. `"{company_name}" website` - Verify web presence
2. `"{company_name}" linkedin employees` - Check employee count
3. `"{company_name}" fraud lawsuit scandal` - Check for issues
4. `"{address}" virtual office mailbox` - Verify address
5. `"{officer_name}" federal government` - Check for revolving door

### Step 4: Evidence Documentation
For each finding, record:
- What was found
- Source URL
- Date accessed
- Relevance to fraud indicators

### Step 5: Risk Scoring
Calculate overall risk score (0-100):
- Each high-risk indicator: +15-25 points
- Each medium-risk indicator: +5-10 points
- Mitigating factors: -5-10 points

## Output Format

```markdown
# FRAUD RISK ASSESSMENT

## Contract Summary
- **Contract ID**: [ID]
- **Contractor**: [Name]
- **UEI**: [Unique Entity ID]
- **Value**: $[Amount]
- **Agency**: [Awarding Agency]
- **Period**: [Start] to [End]

## Risk Score: [0-100] / 100

## Red Flags Identified

### [Flag Category]
**Severity**: High/Medium/Low
**Finding**: [Description]
**Evidence**: [URL or data source]

[Repeat for each flag]

## Contractor Profile
- SAM Registration Date: [Date]
- Physical Address: [Address]
- Address Type: [Commercial/Virtual/Residential]
- LinkedIn Employees: [Count]
- Website Age: [Age or N/A]
- Other Federal Contracts: [Count]

## Investigation Trail
1. [Step taken and result]
2. [Step taken and result]
...

## Recommendation
- [ ] Clear - No significant concerns
- [ ] Monitor - Minor flags, watch future contracts
- [ ] Investigate - Significant flags warrant deeper review
- [ ] Refer to IG - Strong fraud indicators present

## Evidence Archive
| Finding | Source | Date |
|---------|--------|------|
| [Finding] | [URL] | [Date] |
```

## Examples

### Example: Shell Company Detection
**Scenario**: Contract for $5M IT services to "TechSolutions LLC"

**Investigation revealed**:
- SAM registration: 45 days before award (🚩)
- Address: "123 Main St Suite 456" = Regus virtual office (🚩)
- LinkedIn: 2 employees listed (🚩)
- Website: Domain registered 2 months ago (🚩)
- Officer: Previously worked at awarding agency (🚩🚩)

**Risk Score**: 85/100 - Refer to IG

### Example: Legitimate Contractor
**Scenario**: Contract for $10M construction to "Established Builders Inc"

**Investigation revealed**:
- SAM registration: 15 years active
- Address: Verified commercial facility with equipment yard
- LinkedIn: 450 employees
- Website: Established 2005, extensive project portfolio
- Multiple past contracts with good performance

**Risk Score**: 10/100 - Clear

## Best Practices

1. **Be thorough**: Follow every lead
2. **Document everything**: URLs, dates, screenshots
3. **Cross-reference**: Verify information across multiple sources
4. **Be objective**: Report findings, not conclusions
5. **Escalate appropriately**: High-risk findings go to humans
