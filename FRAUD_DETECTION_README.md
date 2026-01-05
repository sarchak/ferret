# Federal Contract Fraud Detection System

## Overview

This system detects fraud patterns in federal contracts using data from USASpending.gov and SAM.gov. It uses **UEI-first matching** to avoid false positives from name-based matching.

## Key Insight: Why UEI-First Matching Matters

Our initial detector falsely flagged "NATIVE HEALTH" (a legitimate 45-year-old nonprofit) as excluded because:
- Name matching found "NATIVE HEALTH" in exclusion list
- But the actual excluded entity was "ALTERNATIVE HEALTH CARE SERVICE" (contained "health")
- The UEIs did not match

**Solution**: Only flag entities where the **exact UEI** matches the exclusion list, not just the name.

## Fraud Patterns Detected

### 1. EXCLUDED_ACTIVE_CONTRACT (CRITICAL)
- **What**: Excluded entity (by UEI) receiving contracts after exclusion date
- **Precision**: Critical - clear FAR violation
- **Data**: SAM exclusions + USASpending contracts
- **Status**: Working - found 0 false positives

### 2. RAPID_REGISTRATION_LARGE_AWARD (HIGH)
- **What**: Entity receives large contract within 90 days of SAM registration
- **Precision**: High - suggests shell company or fraud scheme
- **Data**: SAM entities + USASpending contracts
- **Status**: Working

### 3. THRESHOLD_SPLITTING (HIGH)
- **What**: Multiple contracts just below thresholds ($10K, $250K)
- **Precision**: High - suggests intentional avoidance of competition
- **Data**: USASpending contracts
- **Status**: Working

### 4. ADDRESS_CLUSTER_CONTRACTS (HIGH)
- **What**: Multiple entities at same address winning contracts
- **Precision**: High - suggests shell company network
- **Data**: SAM entities
- **Status**: Found 11,917 clusters (see shell_networks output)

## Files

| File | Purpose |
|------|---------|
| `fraud_patterns.py` | Defines all fraud patterns with legal basis |
| `fraud_detector.py` | Main detector with UEI-first matching |
| `find_shell_networks.py` | Detects address clusters |
| `find_fraud_patterns.py` | Legacy threshold/shell scanning |
| `scan_exclusions_for_contracts.py` | Reverse lookup: excluded → contracts |

## Data Sources

| Source | File | Records |
|--------|------|---------|
| SAM Exclusions | `data/sam_exclusions/SAM_Exclusions_*.CSV` | 7,333 with UEIs |
| SAM Entities | `data/sam_entities/SAM_PUBLIC_MONTHLY_V2_*.dat` | 875,536 entities |
| USASpending | API | Real-time queries |

## Running the Detector

```bash
# Full 2022-2024 scan
uv run python fraud_detector.py

# Shell company network detection
uv run python find_shell_networks.py

# Threshold clustering scan
uv run python find_fraud_patterns.py
```

## Output Files

Outputs are saved to `outputs/` directory:
- `fraud_detections_YYYYMMDD_HHMMSS.csv` - Detections for spreadsheet
- `fraud_detections_YYYYMMDD_HHMMSS.json` - Full evidence trail
- `shell_networks_YYYYMMDD_HHMMSS.csv` - Address cluster data

## Key Findings

### Shell Company Networks (from address clustering)
| Address | Entities | Pattern |
|---------|----------|---------|
| 1212 HAGAN ST, CHAMPAIGN, IL | 237 | DONATO SOLAR LLCs |
| 1 N WACKER DR, CHICAGO, IL | 134 | GSA-related LLCs |
| 200 E MAIN ST, ENTERPRISE, OR | 122 | Housing LLCs |

### Exclusion List Insights
- 7,333 exclusions have UEIs
- Most are HHS/OPM healthcare program exclusions
- Many are old (1990s-2000s)
- OFAC sanctions are mostly international individuals

## Research Sources

- [GAO-24-105833](https://www.gao.gov/products/gao-24-105833): $233-521B annual fraud
- [DOJ FY2024 False Claims Act](https://www.hklaw.com/en/insights/publications/2025/02/government-contracts-enforcement-doj-publishes-fy-2024): $2.9B recovered
- [GSA OIG Red Flags](https://www.gsaig.gov/red-flags-fraud): Fraud indicators
- [SBA 8(a) Audit 2025](https://www.hklaw.com/en/insights/publications/2025/07/sba-announces-full-scale-audit-of-8a-program): $550M+ fraud

## Next Steps

1. **Get newer exclusions data** - Current file is from 2022
2. **Add FSRS subcontract data** - Detect pass-through schemes
3. **Add beneficial ownership** - Corporate Transparency Act (2024)
4. **Add officer/POC matching** - Detect related parties
