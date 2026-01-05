"""
Registration and Entity Timing Analysis

Analyzes SAM.gov registration patterns to detect:
- New registrations quickly winning contracts
- Registration gaps and reactivations
- Entity type changes
- Suspicious timing patterns

What it catches:
- Shell companies created for specific contracts
- Front companies
- Entity restructuring to avoid scrutiny
- New entity fraud
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional


@dataclass
class RegistrationAnomaly:
    """A registration-based anomaly detection result."""
    anomaly_type: str
    severity: str
    description: str
    evidence: dict
    recommendation: str


def detect_new_entity_winning(
    registration_date: str,
    first_award_date: str,
    first_award_value: float
) -> Optional[dict]:
    """
    Detect entities winning contracts very soon after SAM registration.
    """
    try:
        reg_date = datetime.strptime(registration_date, "%Y-%m-%d")
        award_date = datetime.strptime(first_award_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    days_to_first_award = (award_date - reg_date).days

    if days_to_first_award < 0:
        return None  # Award before registration - data issue

    # Very fast first award (< 30 days)
    if days_to_first_award < 30:
        severity = 'HIGH' if first_award_value > 100000 else 'MEDIUM'
        score = 20 if first_award_value > 100000 else 15

        return {
            'pattern_type': 'RAPID_FIRST_AWARD',
            'severity': severity,
            'score': score,
            'description': f'First contract awarded only {days_to_first_award} days after SAM registration',
            'evidence': {
                'registration_date': registration_date,
                'first_award_date': first_award_date,
                'days_to_first_award': days_to_first_award,
                'first_award_value': first_award_value
            },
            'recommendation': 'New entity quickly winning contracts suggests pre-arrangement or created for specific opportunity'
        }

    # Quick first award (30-90 days)
    if days_to_first_award < 90 and first_award_value > 500000:
        return {
            'pattern_type': 'FAST_FIRST_AWARD',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'First contract (${first_award_value:,.0f}) awarded within {days_to_first_award} days of registration',
            'evidence': {
                'registration_date': registration_date,
                'first_award_date': first_award_date,
                'days_to_first_award': days_to_first_award,
                'first_award_value': first_award_value
            },
            'recommendation': 'New entity winning large contract quickly - verify established business operations'
        }

    return None


def detect_registration_age(
    registration_date: str,
    total_contract_value: float
) -> Optional[dict]:
    """
    Detect entities with very recent registrations holding significant value.
    """
    try:
        reg_date = datetime.strptime(registration_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    age_days = (datetime.now() - reg_date).days
    age_months = age_days / 30

    # Very new entity with significant contracts
    if age_months < 12 and total_contract_value > 1000000:
        return {
            'pattern_type': 'NEW_ENTITY_HIGH_VALUE',
            'severity': 'HIGH',
            'score': 15,
            'description': f'Entity registered {age_months:.0f} months ago holds ${total_contract_value:,.0f} in contracts',
            'evidence': {
                'registration_date': registration_date,
                'age_months': age_months,
                'total_contract_value': total_contract_value,
                'value_per_month': total_contract_value / max(1, age_months)
            },
            'recommendation': 'New entity with rapid contract accumulation - verify legitimate operations'
        }

    # New entity
    if age_months < 6 and total_contract_value > 250000:
        return {
            'pattern_type': 'VERY_NEW_ENTITY',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'Entity only {age_months:.1f} months old with ${total_contract_value:,.0f} in contracts',
            'evidence': {
                'registration_date': registration_date,
                'age_months': age_months,
                'total_contract_value': total_contract_value
            },
            'recommendation': 'Very new contractor - perform due diligence on business history'
        }

    return None


def detect_registration_gaps(
    registration_history: list[dict]
) -> Optional[dict]:
    """
    Detect gaps in SAM registration that may indicate problems.

    Args:
        registration_history: List of {'status': 'ACTIVE'/'INACTIVE', 'date': 'YYYY-MM-DD'} entries
    """
    if len(registration_history) < 2:
        return None

    # Sort by date
    try:
        sorted_history = sorted(
            registration_history,
            key=lambda x: datetime.strptime(x['date'], "%Y-%m-%d")
        )
    except (ValueError, TypeError, KeyError):
        return None

    # Find gaps
    gaps = []
    last_active_end = None

    for entry in sorted_history:
        date = datetime.strptime(entry['date'], "%Y-%m-%d")
        status = entry.get('status', '').upper()

        if status == 'INACTIVE' and last_active_end:
            # Gap started
            pass
        elif status == 'ACTIVE':
            if last_active_end:
                gap_days = (date - last_active_end).days
                if gap_days > 30:
                    gaps.append({
                        'start': last_active_end.strftime("%Y-%m-%d"),
                        'end': date.strftime("%Y-%m-%d"),
                        'days': gap_days
                    })
            last_active_end = date

    if gaps and len(gaps) >= 1:
        total_gap_days = sum(g['days'] for g in gaps)

        return {
            'pattern_type': 'REGISTRATION_GAPS',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'{len(gaps)} registration gap(s) totaling {total_gap_days} days',
            'evidence': {
                'gap_count': len(gaps),
                'total_gap_days': total_gap_days,
                'gaps': gaps[:5]  # First 5 gaps
            },
            'recommendation': 'Registration gaps may indicate business problems or strategic re-registration'
        }

    return None


def detect_reactivation_pattern(
    last_inactive_date: str,
    reactivation_date: str,
    award_after_reactivation: Optional[dict] = None
) -> Optional[dict]:
    """
    Detect suspicious reactivation patterns.
    """
    try:
        inactive_date = datetime.strptime(last_inactive_date, "%Y-%m-%d")
        reactive_date = datetime.strptime(reactivation_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    gap_days = (reactive_date - inactive_date).days

    if gap_days < 0:
        return None

    # Reactivation followed quickly by award
    if award_after_reactivation:
        try:
            award_date = datetime.strptime(award_after_reactivation['date'], "%Y-%m-%d")
            days_to_award = (award_date - reactive_date).days

            if days_to_award < 60 and gap_days > 180:
                return {
                    'pattern_type': 'SUSPICIOUS_REACTIVATION',
                    'severity': 'HIGH',
                    'score': 15,
                    'description': f'Inactive {gap_days} days, reactivated, won contract in {days_to_award} days',
                    'evidence': {
                        'inactive_period_days': gap_days,
                        'days_to_award_after_reactivation': days_to_award,
                        'award_value': award_after_reactivation.get('value', 0)
                    },
                    'recommendation': 'Long-dormant entity reactivated for specific contract - investigate relationship'
                }
        except (ValueError, TypeError, KeyError):
            pass

    return None


def detect_entity_type_change(
    current_type: str,
    previous_type: str,
    change_date: str,
    contracts_before_change: int,
    contracts_after_change: int
) -> Optional[dict]:
    """
    Detect suspicious entity type changes.
    """
    if not current_type or not previous_type:
        return None

    current = current_type.upper()
    previous = previous_type.upper()

    # Small business to large business transition
    if 'SMALL' in previous and 'LARGE' in current:
        return {
            'pattern_type': 'SIZE_STATUS_CHANGE',
            'severity': 'LOW',
            'score': 5,
            'description': f'Entity changed from {previous_type} to {current_type}',
            'evidence': {
                'previous_type': previous_type,
                'current_type': current_type,
                'change_date': change_date,
                'contracts_before': contracts_before_change,
                'contracts_after': contracts_after_change
            },
            'recommendation': 'Verify set-aside compliance for contracts awarded before size change'
        }

    # Large to small (potential false claim)
    if 'LARGE' in previous and 'SMALL' in current:
        return {
            'pattern_type': 'SUSPICIOUS_SIZE_CHANGE',
            'severity': 'HIGH',
            'score': 15,
            'description': f'Entity changed from large to small business classification',
            'evidence': {
                'previous_type': previous_type,
                'current_type': current_type,
                'change_date': change_date
            },
            'recommendation': 'Unusual size status change - verify small business eligibility thoroughly'
        }

    return None


def detect_exclusion_timing(
    exclusion_date: str,
    registration_date: str,
    contracts_during_exclusion: list
) -> Optional[dict]:
    """
    Detect if entity received contracts during or near exclusion periods.
    """
    try:
        excl_date = datetime.strptime(exclusion_date, "%Y-%m-%d")
        reg_date = datetime.strptime(registration_date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None

    # Contracts awarded during exclusion period
    if contracts_during_exclusion:
        total_value = sum(c.get('value', 0) for c in contracts_during_exclusion)

        return {
            'pattern_type': 'CONTRACTS_DURING_EXCLUSION',
            'severity': 'CRITICAL',
            'score': 30,
            'description': f'{len(contracts_during_exclusion)} contracts totaling ${total_value:,.0f} awarded during exclusion',
            'evidence': {
                'exclusion_date': exclusion_date,
                'contract_count': len(contracts_during_exclusion),
                'total_value': total_value,
                'contracts': contracts_during_exclusion[:5]
            },
            'recommendation': 'URGENT: Contracts awarded to excluded entity - investigate awarding offices'
        }

    return None


def analyze_entity_registration(
    entity: dict,
    contracts: list,
    entity_uei: str
) -> list[dict]:
    """
    Comprehensive registration analysis for an entity.
    """
    indicators = []

    # Get entity registration info
    registration_date = entity.get('registration_date') or entity.get('sam_registration_date')
    entity_contracts = [c for c in contracts if c.recipient_uei == entity_uei]

    if not registration_date or not entity_contracts:
        return indicators

    # Sort contracts by date
    try:
        sorted_contracts = sorted(
            entity_contracts,
            key=lambda c: datetime.strptime(c.start_date, "%Y-%m-%d") if c.start_date else datetime.max
        )
    except (ValueError, TypeError):
        sorted_contracts = entity_contracts

    if sorted_contracts:
        first_contract = sorted_contracts[0]
        first_value = first_contract.total_obligation
        first_date = first_contract.start_date

        # Check new entity winning quickly
        result = detect_new_entity_winning(registration_date, first_date, first_value)
        if result:
            indicators.append(result)

    # Check registration age
    total_value = sum(c.total_obligation for c in entity_contracts)
    result = detect_registration_age(registration_date, total_value)
    if result:
        indicators.append(result)

    return indicators
