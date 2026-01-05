"""
Contract Modification Pattern Detection

Analyzes modification patterns to detect:
- Excessive value growth (lowball bid strategy)
- Suspicious timing patterns
- Frequent modifications (poor planning or fraud)
- Late modifications near contract end

What it catches:
- Lowball bid fraud
- Scope creep exploitation
- Unauthorized changes
- Budget manipulation
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict


@dataclass
class ModificationAnomaly:
    """A modification-based anomaly detection result."""
    anomaly_type: str
    contract_id: str
    severity: str
    description: str
    evidence: dict
    recommendation: str


def detect_excessive_modifications(
    modification_count: int,
    contract_duration_months: int,
    contract_value: float
) -> Optional[dict]:
    """
    Detect if a contract has excessive modification frequency.
    """
    if contract_duration_months <= 0:
        return None

    mods_per_month = modification_count / contract_duration_months

    # More than 2 mods per month is suspicious
    if mods_per_month > 2 and modification_count >= 6:
        return {
            'pattern_type': 'EXCESSIVE_MODIFICATIONS',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'{modification_count} modifications over {contract_duration_months} months ({mods_per_month:.1f}/month)',
            'evidence': {
                'modification_count': modification_count,
                'contract_duration_months': contract_duration_months,
                'modifications_per_month': mods_per_month,
                'contract_value': contract_value
            },
            'recommendation': 'High modification frequency suggests poor initial planning or deliberate underbidding'
        }

    return None


def detect_value_growth_pattern(
    original_value: float,
    current_value: float,
    modification_history: list[dict]
) -> Optional[dict]:
    """
    Detect concerning patterns in contract value growth.

    Args:
        original_value: Initial award amount
        current_value: Current total value
        modification_history: List of mods with 'amount' and 'date' keys
    """
    if original_value <= 0 or not modification_history:
        return None

    total_growth = (current_value - original_value) / original_value

    # Check if growth happened mostly through one modification
    if len(modification_history) >= 2:
        amounts = [m.get('amount', 0) for m in modification_history]
        total_mods = sum(amounts)

        if total_mods > 0:
            max_mod = max(amounts)
            concentration = max_mod / total_mods

            if concentration > 0.7 and total_growth > 0.5:
                return {
                    'pattern_type': 'CONCENTRATED_MOD_GROWTH',
                    'severity': 'HIGH',
                    'score': 15,
                    'description': f'{concentration:.0%} of growth came from single modification',
                    'evidence': {
                        'original_value': original_value,
                        'current_value': current_value,
                        'total_growth': total_growth,
                        'max_modification': max_mod,
                        'concentration': concentration
                    },
                    'recommendation': 'Large single modification - verify scope justification and competition consideration'
                }

    # Very high total growth
    if total_growth > 2.0:  # More than tripled
        return {
            'pattern_type': 'EXTREME_VALUE_GROWTH',
            'severity': 'HIGH',
            'score': 20,
            'description': f'Contract value grew {total_growth:.0%} from ${original_value:,.0f} to ${current_value:,.0f}',
            'evidence': {
                'original_value': original_value,
                'current_value': current_value,
                'growth_percentage': total_growth * 100,
                'modification_count': len(modification_history)
            },
            'recommendation': 'Contract more than tripled - strong indicator of lowball bid fraud or scope creep'
        }

    return None


def detect_late_modifications(
    contract_end_date: str,
    modification_date: str,
    modification_amount: float,
    contract_value: float
) -> Optional[dict]:
    """
    Detect large modifications made near contract end date.
    """
    try:
        end_date = datetime.strptime(contract_end_date, "%Y-%m-%d")
        mod_date = datetime.strptime(modification_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    days_before_end = (end_date - mod_date).days

    if days_before_end < 0:
        return None  # Mod after contract end - different issue

    mod_pct = modification_amount / contract_value if contract_value > 0 else 0

    # Large modification within 30 days of contract end
    if days_before_end <= 30 and mod_pct > 0.15:
        return {
            'pattern_type': 'LATE_LARGE_MODIFICATION',
            'severity': 'HIGH',
            'score': 15,
            'description': f'{mod_pct:.0%} value increase only {days_before_end} days before contract end',
            'evidence': {
                'contract_end_date': contract_end_date,
                'modification_date': modification_date,
                'days_before_end': days_before_end,
                'modification_amount': modification_amount,
                'modification_pct': mod_pct
            },
            'recommendation': 'Late significant modification - may be budget dumping or unauthorized extension'
        }

    return None


def detect_modification_timing_cluster(
    modifications: list[dict]
) -> Optional[dict]:
    """
    Detect if modifications cluster at suspicious times (fiscal year end).
    """
    if len(modifications) < 5:
        return None

    # Parse modification dates
    mod_dates = []
    for mod in modifications:
        try:
            date = datetime.strptime(mod.get('date', ''), "%Y-%m-%d")
            mod_dates.append(date)
        except (ValueError, TypeError):
            continue

    if len(mod_dates) < 5:
        return None

    # Count September modifications
    sept_mods = [d for d in mod_dates if d.month == 9]
    sept_ratio = len(sept_mods) / len(mod_dates)

    if sept_ratio > 0.40:  # More than 40% in September
        return {
            'pattern_type': 'YEAREND_MODIFICATION_CLUSTER',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'{sept_ratio:.0%} of modifications occurred in September',
            'evidence': {
                'september_modifications': len(sept_mods),
                'total_modifications': len(mod_dates),
                'september_ratio': sept_ratio
            },
            'recommendation': 'Modifications clustered at fiscal year-end - may indicate budget manipulation'
        }

    return None


def detect_option_exercise_pattern(
    base_value: float,
    option_values: list[float],
    exercised_options: int
) -> Optional[dict]:
    """
    Detect suspicious option exercise patterns.
    """
    if not option_values or exercised_options == 0:
        return None

    total_options = len(option_values)
    exercise_rate = exercised_options / total_options

    total_option_value = sum(option_values[:exercised_options])

    # All options exercised and options exceed base
    if exercise_rate == 1.0 and total_option_value > base_value:
        return {
            'pattern_type': 'FULL_OPTION_EXERCISE',
            'severity': 'LOW',
            'score': 5,
            'description': f'All {total_options} options exercised, totaling ${total_option_value:,.0f}',
            'evidence': {
                'base_value': base_value,
                'total_option_value': total_option_value,
                'options_exercised': exercised_options,
                'total_options': total_options
            },
            'recommendation': 'All options exercised - verify initial estimate adequacy'
        }

    return None


def detect_change_order_pattern(
    change_orders: list[dict],
    original_value: float
) -> Optional[dict]:
    """
    Detect patterns in change orders that suggest fraud.
    """
    if len(change_orders) < 3:
        return None

    # Check for many small change orders (staying under approval thresholds)
    amounts = [co.get('amount', 0) for co in change_orders]

    # Count change orders in certain ranges
    under_10k = sum(1 for a in amounts if 0 < a < 10000)
    under_25k = sum(1 for a in amounts if 0 < a < 25000)

    # If most change orders are just under thresholds
    if len(amounts) >= 5:
        small_order_ratio = under_25k / len(amounts)

        if small_order_ratio > 0.7 and sum(amounts) > original_value * 0.3:
            return {
                'pattern_type': 'THRESHOLD_AVOIDANCE_CHANGES',
                'severity': 'HIGH',
                'score': 15,
                'description': f'{small_order_ratio:.0%} of change orders under approval threshold, totaling ${sum(amounts):,.0f}',
                'evidence': {
                    'change_order_count': len(amounts),
                    'under_10k_count': under_10k,
                    'under_25k_count': under_25k,
                    'total_change_value': sum(amounts),
                    'original_value': original_value,
                    'growth_from_changes': sum(amounts) / original_value
                },
                'recommendation': 'Change orders structured to avoid approval thresholds - investigate for FAR violation'
            }

    return None


def analyze_contractor_modifications(
    contracts: list,
    contractor_uei: str
) -> list[dict]:
    """
    Comprehensive modification analysis for a contractor.
    """
    contractor_contracts = [c for c in contracts if c.recipient_uei == contractor_uei]
    indicators = []

    for contract in contractor_contracts:
        # Get modification info if available
        mod_count = getattr(contract, 'modification_count', 0) or 0
        original_value = getattr(contract, 'base_exercised_options_value', 0) or getattr(contract, 'base_and_all_options_value', 0) or 0
        current_value = contract.total_obligation

        if not original_value:
            original_value = current_value

        # Calculate contract duration
        duration_months = 12  # Default
        try:
            start = datetime.strptime(contract.start_date, "%Y-%m-%d")
            end_str = getattr(contract, 'end_date', None) or getattr(contract, 'period_of_performance_current_end_date', None)
            if end_str:
                end = datetime.strptime(end_str, "%Y-%m-%d")
                duration_months = max(1, (end - start).days // 30)
        except (ValueError, TypeError):
            pass

        # Check excessive modifications
        if mod_count > 0:
            result = detect_excessive_modifications(mod_count, duration_months, current_value)
            if result:
                result['contract_id'] = contract.contract_id
                indicators.append(result)

        # Check value growth
        if original_value > 0 and current_value > original_value * 1.5:
            growth = (current_value - original_value) / original_value
            indicators.append({
                'pattern_type': 'SIGNIFICANT_VALUE_GROWTH',
                'severity': 'MEDIUM' if growth < 2.0 else 'HIGH',
                'score': 10 if growth < 2.0 else 15,
                'contract_id': contract.contract_id,
                'description': f'Contract grew {growth:.0%} from original value',
                'evidence': {
                    'original_value': original_value,
                    'current_value': current_value,
                    'growth_percentage': growth * 100
                },
                'recommendation': 'Review modification justifications for scope creep or lowball bid indicators'
            })

    return indicators
