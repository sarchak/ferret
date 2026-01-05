"""
Temporal Anomaly Detection

Analyzes timing patterns in contract awards to detect:
- Weekend/after-hours awards (bypass oversight)
- Fiscal year-end rush (use-it-or-lose-it fraud)
- Unusually fast awards (predetermined winner)
- Short response windows (exclude competitors)

What it catches:
- Rushed awards to favored contractors
- Year-end budget dumping
- Wired contracts
- Fake competitions
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict


@dataclass
class TemporalAnomaly:
    """A timing-based anomaly detection result."""
    anomaly_type: str
    contract_id: str
    severity: str  # LOW, MEDIUM, HIGH
    description: str
    evidence: dict
    recommendation: str


def detect_weekend_award(contract) -> Optional[TemporalAnomaly]:
    """Detect contracts awarded on weekends."""
    if not contract.start_date:
        return None

    try:
        award_date = datetime.strptime(contract.start_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    if award_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return TemporalAnomaly(
            anomaly_type='WEEKEND_AWARD',
            contract_id=contract.contract_id,
            severity='MEDIUM',
            description=f"Contract awarded on {award_date.strftime('%A')}",
            evidence={
                'award_date': contract.start_date,
                'day_of_week': award_date.strftime('%A')
            },
            recommendation='Weekend awards may bypass normal oversight - verify approval chain'
        )
    return None


def detect_fiscal_yearend(contract) -> Optional[TemporalAnomaly]:
    """Detect fiscal year-end awards (September)."""
    if not contract.start_date:
        return None

    try:
        award_date = datetime.strptime(contract.start_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    # Last day of fiscal year
    if award_date.month == 9 and award_date.day == 30:
        return TemporalAnomaly(
            anomaly_type='FISCAL_YEAR_END_AWARD',
            contract_id=contract.contract_id,
            severity='MEDIUM',
            description='Contract awarded on last day of fiscal year',
            evidence={
                'award_date': contract.start_date,
                'fiscal_year': award_date.year
            },
            recommendation='Year-end spending pressure increases fraud risk - verify urgency was legitimate'
        )

    # Last week of fiscal year
    if award_date.month == 9 and award_date.day >= 24:
        return TemporalAnomaly(
            anomaly_type='FISCAL_YEAR_END_RUSH',
            contract_id=contract.contract_id,
            severity='LOW',
            description='Contract awarded in last week of fiscal year',
            evidence={
                'award_date': contract.start_date,
                'days_before_fy_end': 30 - award_date.day
            },
            recommendation='Year-end rush period - verify proper competition and oversight'
        )

    return None


def detect_award_velocity(
    contract,
    solicitation_date: Optional[str] = None,
    benchmark_days: int = 60
) -> Optional[TemporalAnomaly]:
    """
    Detect unusually fast awards that may indicate predetermined winner.

    Args:
        contract: Contract object
        solicitation_date: Date solicitation was posted (if available)
        benchmark_days: Typical days from solicitation to award
    """
    if not solicitation_date or not contract.start_date:
        return None

    try:
        sol_date = datetime.strptime(solicitation_date, "%Y-%m-%d")
        award_date = datetime.strptime(contract.start_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    days_to_award = (award_date - sol_date).days

    if days_to_award < 0:
        return None  # Data issue

    # Very fast award (< 10 days)
    if days_to_award < 10:
        return TemporalAnomaly(
            anomaly_type='UNUSUALLY_FAST_AWARD',
            contract_id=contract.contract_id,
            severity='HIGH',
            description=f'Award made only {days_to_award} days after solicitation',
            evidence={
                'solicitation_date': solicitation_date,
                'award_date': contract.start_date,
                'days_to_award': days_to_award,
                'benchmark': benchmark_days
            },
            recommendation='Extremely fast award - verify competition was genuine, not predetermined'
        )

    # Fast award (< 20% of benchmark)
    if days_to_award < benchmark_days * 0.2:
        return TemporalAnomaly(
            anomaly_type='FAST_AWARD',
            contract_id=contract.contract_id,
            severity='MEDIUM',
            description=f'Award made in {days_to_award} days (benchmark: {benchmark_days})',
            evidence={
                'days_to_award': days_to_award,
                'benchmark': benchmark_days,
                'pct_of_benchmark': days_to_award / benchmark_days
            },
            recommendation='Faster than typical - verify adequate competition period'
        )

    return None


def detect_yearend_concentration(contracts: list) -> list[TemporalAnomaly]:
    """
    Analyze if a contractor has suspiciously high year-end award concentration.
    """
    anomalies = []

    # Group by month
    by_month = defaultdict(list)
    for c in contracts:
        if c.start_date:
            try:
                month = datetime.strptime(c.start_date, "%Y-%m-%d").month
                by_month[month].append(c)
            except (ValueError, TypeError):
                continue

    total = len(contracts)
    if total < 10:
        return anomalies

    # Check September concentration
    sept_count = len(by_month.get(9, []))
    sept_ratio = sept_count / total

    if sept_ratio > 0.35:  # More than 35% in September
        sept_value = sum(c.total_obligation for c in by_month.get(9, []))
        total_value = sum(c.total_obligation for c in contracts)

        anomalies.append(TemporalAnomaly(
            anomaly_type='SEPTEMBER_CONCENTRATION',
            contract_id='AGGREGATE',
            severity='MEDIUM' if sept_ratio > 0.5 else 'LOW',
            description=f'{sept_ratio:.0%} of contracts awarded in September',
            evidence={
                'september_count': sept_count,
                'total_count': total,
                'september_ratio': sept_ratio,
                'september_value': sept_value,
                'total_value': total_value
            },
            recommendation='High year-end concentration suggests budget-driven rather than mission-driven awards'
        ))

    return anomalies


def detect_modification_timing(
    base_award_date: str,
    modification_date: str,
    modification_amount: float,
    original_value: float
) -> Optional[TemporalAnomaly]:
    """
    Detect suspiciously early or large modifications.
    """
    try:
        base_date = datetime.strptime(base_award_date, "%Y-%m-%d")
        mod_date = datetime.strptime(modification_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    days_to_mod = (mod_date - base_date).days

    # Early large modification (< 30 days, > 20% of original)
    if days_to_mod < 30 and modification_amount > original_value * 0.2:
        return TemporalAnomaly(
            anomaly_type='EARLY_LARGE_MODIFICATION',
            contract_id='',  # Filled by caller
            severity='HIGH',
            description=f'Large modification ({modification_amount/original_value:.0%} of original) only {days_to_mod} days after award',
            evidence={
                'days_to_modification': days_to_mod,
                'modification_amount': modification_amount,
                'original_value': original_value,
                'pct_increase': modification_amount / original_value
            },
            recommendation='Early large modification suggests lowball bid strategy - review original pricing'
        )

    return None


def analyze_contract_timing(contract) -> list[TemporalAnomaly]:
    """
    Run all temporal anomaly checks on a single contract.
    """
    anomalies = []

    # Check weekend
    result = detect_weekend_award(contract)
    if result:
        anomalies.append(result)

    # Check fiscal year-end
    result = detect_fiscal_yearend(contract)
    if result:
        anomalies.append(result)

    return anomalies


def analyze_contractor_timing(contracts: list, contractor_uei: str) -> list[dict]:
    """
    Analyze timing patterns for a specific contractor.
    Returns list of fraud indicators.
    """
    contractor_contracts = [c for c in contracts if c.recipient_uei == contractor_uei]

    if len(contractor_contracts) < 5:
        return []

    indicators = []

    # Check year-end concentration
    concentration = detect_yearend_concentration(contractor_contracts)
    for anomaly in concentration:
        indicators.append({
            'pattern_type': anomaly.anomaly_type,
            'severity': anomaly.severity,
            'score': 10 if anomaly.severity == 'MEDIUM' else 5,
            'description': anomaly.description,
            'evidence': anomaly.evidence,
            'recommendation': anomaly.recommendation
        })

    # Check individual contracts
    for contract in contractor_contracts:
        for anomaly in analyze_contract_timing(contract):
            indicators.append({
                'pattern_type': anomaly.anomaly_type,
                'severity': anomaly.severity,
                'score': 10 if anomaly.severity == 'MEDIUM' else 5,
                'description': anomaly.description,
                'evidence': anomaly.evidence,
                'recommendation': anomaly.recommendation
            })

    return indicators
