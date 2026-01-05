"""
Pricing Anomaly Detection

Analyzes contract amounts for:
- Round numbers (fabricated amounts)
- Threshold clustering (splitting to avoid oversight)
- Statistical outliers (above/below market)
- Suspicious modification patterns

What it catches:
- Contract splitting
- Threshold avoidance
- Inflated estimates
- Price manipulation
"""

from dataclasses import dataclass
from typing import Optional
from collections import defaultdict
import statistics


# FAR and acquisition thresholds
THRESHOLDS = {
    'micro_purchase': 10000,
    'simplified_acquisition': 250000,
    'commercial_item': 750000,
    'cost_accounting': 7500000,
    'enhanced_oversight': 1000000,
}


@dataclass
class PricingAnomaly:
    """A pricing-based anomaly detection result."""
    anomaly_type: str
    contract_id: str
    severity: str
    description: str
    evidence: dict
    recommendation: str


def detect_round_number(amount: float) -> Optional[dict]:
    """
    Detect suspiciously round contract amounts.

    Real procurement amounts from competitive bidding are rarely exactly round.
    """
    if amount <= 0:
        return None

    patterns = [
        (amount % 1000000 == 0 and amount >= 1000000, 'EXACT_MILLION', 'HIGH'),
        (amount % 100000 == 0 and amount >= 100000 and amount % 1000000 != 0, 'EXACT_HUNDRED_THOUSAND', 'MEDIUM'),
        (amount % 10000 == 0 and amount >= 50000 and amount % 100000 != 0, 'EXACT_TEN_THOUSAND', 'LOW'),
    ]

    for is_round, pattern_type, severity in patterns:
        if is_round:
            return {
                'pattern_type': f'ROUND_NUMBER_{pattern_type}',
                'severity': severity,
                'score': 5,  # Low score - needs corroboration
                'description': f'Contract amount ${amount:,.0f} is suspiciously round',
                'evidence': {
                    'amount': amount,
                    'pattern': pattern_type
                },
                'recommendation': 'Round amounts suggest estimates rather than competitive pricing - verify price was negotiated'
            }

    return None


def detect_threshold_proximity(amount: float) -> Optional[dict]:
    """
    Detect amounts just under regulatory thresholds.
    """
    for threshold_name, threshold_value in THRESHOLDS.items():
        lower_bound = threshold_value * 0.90
        upper_bound = threshold_value * 0.999

        if lower_bound <= amount < upper_bound:
            pct = amount / threshold_value * 100

            return {
                'pattern_type': 'THRESHOLD_PROXIMITY',
                'severity': 'MEDIUM',
                'score': 10,
                'description': f'Amount ${amount:,.0f} is {pct:.1f}% of ${threshold_value:,} threshold',
                'evidence': {
                    'amount': amount,
                    'threshold_name': threshold_name,
                    'threshold_value': threshold_value,
                    'pct_of_threshold': pct
                },
                'recommendation': f'Amount structured to stay under {threshold_name.replace("_", " ")} threshold - check for related awards'
            }

    return None


def detect_contract_splitting(
    contracts: list,
    contractor_uei: str,
    agency: str,
    lookback_days: int = 180
) -> list[dict]:
    """
    Detect potential contract splitting to avoid thresholds.

    Pattern: Multiple contracts just under threshold, same agency, similar timing.
    """
    from datetime import datetime, timedelta

    indicators = []
    cutoff_date = datetime.now() - timedelta(days=lookback_days)

    # Filter to contractor + agency + recent
    relevant = []
    for c in contracts:
        if c.recipient_uei != contractor_uei or c.agency != agency:
            continue
        try:
            award_date = datetime.strptime(c.start_date, "%Y-%m-%d")
            if award_date >= cutoff_date:
                relevant.append(c)
        except (ValueError, TypeError):
            continue

    if len(relevant) < 3:
        return indicators

    # Check each threshold
    for threshold_name, threshold_value in THRESHOLDS.items():
        lower_bound = threshold_value * 0.85
        upper_bound = threshold_value * 0.999

        near_threshold = [c for c in relevant
                         if lower_bound <= c.total_obligation < upper_bound]

        if len(near_threshold) >= 3:
            total_value = sum(c.total_obligation for c in near_threshold)
            avg_value = total_value / len(near_threshold)

            # Check timing clustering
            dates = []
            for c in near_threshold:
                try:
                    dates.append(datetime.strptime(c.start_date, "%Y-%m-%d"))
                except (ValueError, TypeError):
                    continue

            if len(dates) >= 2:
                dates.sort()
                avg_gap = sum((dates[i+1] - dates[i]).days
                             for i in range(len(dates)-1)) / (len(dates) - 1)

                if avg_gap < 45:  # Awards within ~6 weeks
                    indicators.append({
                        'pattern_type': 'CONTRACT_SPLITTING',
                        'severity': 'HIGH',
                        'score': 20,
                        'description': f'{len(near_threshold)} contracts at 85-99% of ${threshold_value:,} threshold',
                        'evidence': {
                            'threshold': threshold_name,
                            'threshold_value': threshold_value,
                            'contract_count': len(near_threshold),
                            'average_value': avg_value,
                            'total_value': total_value,
                            'average_gap_days': avg_gap,
                            'contract_ids': [c.contract_id for c in near_threshold[:5]]
                        },
                        'recommendation': 'Investigate for FAR 13.003(c)(2) violation - requirements may have been improperly split'
                    })

    return indicators


def detect_price_outlier(
    amount: float,
    historical_amounts: list[float],
    z_threshold: float = 2.5
) -> Optional[dict]:
    """
    Detect if a contract price is a statistical outlier.
    """
    if len(historical_amounts) < 10:
        return None

    try:
        median = statistics.median(historical_amounts)
        stdev = statistics.stdev(historical_amounts)

        if stdev == 0:
            return None

        z_score = (amount - median) / stdev

        if z_score > z_threshold:
            return {
                'pattern_type': 'PRICE_OUTLIER_HIGH',
                'severity': 'HIGH' if z_score > 3 else 'MEDIUM',
                'score': 15 if z_score > 3 else 10,
                'description': f'Contract price is {z_score:.1f} std deviations above median',
                'evidence': {
                    'amount': amount,
                    'median': median,
                    'z_score': z_score,
                    'sample_size': len(historical_amounts)
                },
                'recommendation': 'Review pricing justification - significantly above market'
            }
        elif z_score < -z_threshold:
            return {
                'pattern_type': 'PRICE_OUTLIER_LOW',
                'severity': 'MEDIUM',
                'score': 10,
                'description': f'Contract price is {abs(z_score):.1f} std deviations below median',
                'evidence': {
                    'amount': amount,
                    'median': median,
                    'z_score': z_score
                },
                'recommendation': 'Suspiciously low - may be lowball bid with planned modifications'
            }

    except statistics.StatisticsError:
        pass

    return None


def detect_modification_growth(
    original_value: float,
    current_value: float,
    modification_count: int
) -> Optional[dict]:
    """
    Detect excessive contract value growth through modifications.
    """
    if original_value <= 0:
        return None

    growth_rate = (current_value - original_value) / original_value

    if growth_rate > 1.0:  # More than doubled
        return {
            'pattern_type': 'EXCESSIVE_CONTRACT_GROWTH',
            'severity': 'HIGH',
            'score': 15,
            'description': f'Contract value increased {growth_rate:.0%} from ${original_value:,.0f} to ${current_value:,.0f}',
            'evidence': {
                'original_value': original_value,
                'current_value': current_value,
                'growth_rate': growth_rate,
                'modification_count': modification_count
            },
            'recommendation': 'Contract more than doubled - review modification justifications for scope creep fraud'
        }
    elif growth_rate > 0.5:  # More than 50% growth
        return {
            'pattern_type': 'SIGNIFICANT_CONTRACT_GROWTH',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'Contract value increased {growth_rate:.0%}',
            'evidence': {
                'original_value': original_value,
                'current_value': current_value,
                'growth_rate': growth_rate
            },
            'recommendation': 'Significant value increase - verify modifications were in scope'
        }

    return None


def analyze_contractor_pricing(contracts: list, contractor_uei: str) -> list[dict]:
    """
    Comprehensive pricing analysis for a contractor.
    """
    contractor_contracts = [c for c in contracts if c.recipient_uei == contractor_uei]
    indicators = []

    for contract in contractor_contracts:
        # Round number check
        result = detect_round_number(contract.total_obligation)
        if result:
            result['contract_id'] = contract.contract_id
            indicators.append(result)

        # Threshold proximity check
        result = detect_threshold_proximity(contract.total_obligation)
        if result:
            result['contract_id'] = contract.contract_id
            indicators.append(result)

    # Contract splitting check (per agency)
    agencies = set(c.agency for c in contractor_contracts if c.agency)
    for agency in agencies:
        splitting = detect_contract_splitting(contracts, contractor_uei, agency)
        indicators.extend(splitting)

    return indicators
