"""
Competition Quality Detection

Analyzes the quality of competition in contract awards:
- Low offer counts in "competitive" awards
- Single offer competitions
- Bid rigging indicators
- Incumbent advantage patterns

What it catches:
- Fake competitions
- Bid rigging / collusion
- Wired specifications
- Barriers to entry
"""

from dataclasses import dataclass
from typing import Optional
from collections import defaultdict, Counter


@dataclass
class CompetitionAnomaly:
    """Competition quality anomaly result."""
    anomaly_type: str
    severity: str
    description: str
    evidence: dict
    recommendation: str


def detect_single_offer_competitive(contract) -> Optional[dict]:
    """
    Detect "competitive" awards with only one offer.
    """
    # Check if marked as competitive
    competitive_types = ['FULL AND OPEN', 'COMPETED', 'FULL AND OPEN COMPETITION']
    is_competitive = any(
        comp_type in str(contract.competition_type).upper()
        for comp_type in competitive_types
    )

    if not is_competitive:
        return None

    offers = getattr(contract, 'number_of_offers', 0) or 0

    if offers == 1:
        return {
            'pattern_type': 'SINGLE_OFFER_COMPETITIVE',
            'severity': 'MEDIUM',
            'score': 10,
            'description': '"Competitive" award received only 1 offer',
            'evidence': {
                'contract_id': contract.contract_id,
                'competition_type': contract.competition_type,
                'offers_received': 1,
                'value': contract.total_obligation
            },
            'recommendation': 'Single offer in competitive procurement - investigate barriers to competition'
        }

    return None


def detect_low_competition(
    contract,
    expected_offers: int = 5
) -> Optional[dict]:
    """
    Detect below-expected offer counts.
    """
    offers = getattr(contract, 'number_of_offers', 0) or 0

    if offers == 0:
        return None

    if offers < expected_offers * 0.3:  # Less than 30% of expected
        return {
            'pattern_type': 'LOW_COMPETITION',
            'severity': 'LOW',
            'score': 5,
            'description': f'Only {offers} offers received (expected ~{expected_offers})',
            'evidence': {
                'offers_received': offers,
                'expected_offers': expected_offers,
                'ratio': offers / expected_offers
            },
            'recommendation': 'Below-expected competition - check for overly restrictive requirements'
        }

    return None


def detect_sole_source_concentration(
    contracts: list,
    contractor_uei: str
) -> Optional[dict]:
    """
    Detect contractors with unusually high sole-source rate.
    """
    contractor_contracts = [c for c in contracts if c.recipient_uei == contractor_uei]

    if len(contractor_contracts) < 5:
        return None

    sole_source = [c for c in contractor_contracts
                   if getattr(c, 'number_of_offers', 0) == 1 or
                   'NOT COMPETED' in str(getattr(c, 'competition_type', '')).upper() or
                   'SOLE SOURCE' in str(getattr(c, 'competition_type', '')).upper()]

    sole_source_ratio = len(sole_source) / len(contractor_contracts)

    if sole_source_ratio > 0.80:
        total_sole_source_value = sum(c.total_obligation for c in sole_source)

        return {
            'pattern_type': 'SOLE_SOURCE_CONCENTRATION',
            'severity': 'HIGH' if sole_source_ratio > 0.90 else 'MEDIUM',
            'score': 15 if sole_source_ratio > 0.90 else 10,
            'description': f'{sole_source_ratio:.0%} of contracts are sole-source',
            'evidence': {
                'sole_source_count': len(sole_source),
                'total_contracts': len(contractor_contracts),
                'sole_source_ratio': sole_source_ratio,
                'sole_source_value': total_sole_source_value
            },
            'recommendation': 'Very high sole-source rate - review justifications for improper steering'
        }

    return None


def detect_repeated_bidder_pairs(
    contracts: list,
    contractor_uei: str,
    min_occurrences: int = 3
) -> list[dict]:
    """
    Detect if same pairs of bidders repeatedly compete (collusion indicator).

    Note: This requires bid data which may not be available in basic contract data.
    This is a placeholder for when bid-level data is accessible.
    """
    # This would require bid-level data from SAM.gov or agency-specific sources
    # Placeholder for future implementation
    return []


def detect_incumbent_always_wins(
    contracts: list,
    contractor_uei: str
) -> Optional[dict]:
    """
    Detect if contractor always wins recompetes (captured relationship).
    """
    contractor_contracts = [c for c in contracts if c.recipient_uei == contractor_uei]

    if len(contractor_contracts) < 5:
        return None

    # Group by description similarity (proxy for same requirement)
    # Simple approach: look for contracts with similar NAICS/agency patterns

    by_agency_naics = defaultdict(list)
    for c in contractor_contracts:
        key = (c.agency, getattr(c, 'naics_code', ''))
        by_agency_naics[key].append(c)

    for (agency, naics), agency_contracts in by_agency_naics.items():
        if len(agency_contracts) >= 3:
            # Check if contractor won all in this category
            # This is a simplified check - real implementation would track recompetes

            return {
                'pattern_type': 'INCUMBENT_ADVANTAGE',
                'severity': 'MEDIUM',
                'score': 10,
                'description': f'Won {len(agency_contracts)} contracts in same agency/NAICS over time',
                'evidence': {
                    'agency': agency,
                    'naics': naics,
                    'consecutive_wins': len(agency_contracts),
                    'total_value': sum(c.total_obligation for c in agency_contracts)
                },
                'recommendation': 'Persistent incumbent - verify recompetes are genuinely competitive'
            }

    return None


def detect_co_contractor_concentration(
    contracts: list,
    contractor_uei: str
) -> Optional[dict]:
    """
    Detect if contracts come disproportionately from one contracting officer.

    Note: Requires CO name in contract data which may not always be available.
    """
    contractor_contracts = [c for c in contracts if c.recipient_uei == contractor_uei]

    if len(contractor_contracts) < 10:
        return None

    # Get CO names if available
    co_names = [getattr(c, 'awarding_office', None) or getattr(c, 'contracting_officer', None)
                for c in contractor_contracts]
    co_names = [co for co in co_names if co]

    if not co_names:
        return None

    co_counts = Counter(co_names)
    most_common_co, count = co_counts.most_common(1)[0]

    concentration = count / len(contractor_contracts)

    if concentration > 0.60 and count >= 5:
        return {
            'pattern_type': 'CO_CONCENTRATION',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'{concentration:.0%} of contracts from same contracting office',
            'evidence': {
                'contracting_office': most_common_co,
                'contracts_from_office': count,
                'total_contracts': len(contractor_contracts),
                'concentration': concentration
            },
            'recommendation': 'High concentration from single office - check for favoritism'
        }

    return None


def analyze_contractor_competition(contracts: list, contractor_uei: str) -> list[dict]:
    """
    Comprehensive competition analysis for a contractor.
    """
    indicators = []

    contractor_contracts = [c for c in contracts if c.recipient_uei == contractor_uei]

    # Check individual contracts
    for contract in contractor_contracts:
        result = detect_single_offer_competitive(contract)
        if result:
            indicators.append(result)

        result = detect_low_competition(contract)
        if result:
            indicators.append(result)

    # Check aggregate patterns
    result = detect_sole_source_concentration(contracts, contractor_uei)
    if result:
        indicators.append(result)

    result = detect_incumbent_always_wins(contracts, contractor_uei)
    if result:
        indicators.append(result)

    result = detect_co_contractor_concentration(contracts, contractor_uei)
    if result:
        indicators.append(result)

    return indicators
