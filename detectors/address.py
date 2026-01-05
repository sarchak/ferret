"""
Address Analysis Detection

Analyzes contractor addresses to detect:
- Virtual office / mail drop usage
- Shared addresses between contractors
- Address clustering (related entities)
- Residential addresses for large contracts

What it catches:
- Shell companies
- Related-party schemes
- Front companies
- Pass-through arrangements
"""

from dataclasses import dataclass
from typing import Optional
from collections import defaultdict
import re


# Known virtual office providers and mail centers
VIRTUAL_OFFICE_INDICATORS = [
    'regus', 'wework', 'spaces', 'hq global', 'servcorp',
    'intelligent office', 'davinci', 'opus virtual',
    'mailboxes etc', 'the ups store', 'fedex office',
    'pak mail', 'postal connections', 'postnet',
    'suite', 'ste', 'unit', 'box', 'pmb', 'mailbox',
    '#', 'floor', 'building'
]

# Patterns that suggest residential addresses
RESIDENTIAL_PATTERNS = [
    r'\bapt\b', r'\bapartment\b', r'\bcondo\b', r'\bunit\b\s*\d',
    r'\b\d+\s+(street|st|avenue|ave|road|rd|lane|ln|drive|dr|court|ct|circle|cir)\b',
]


@dataclass
class AddressAnomaly:
    """An address-based anomaly detection result."""
    anomaly_type: str
    severity: str
    description: str
    evidence: dict
    recommendation: str


def normalize_address(address: str) -> str:
    """Normalize address for comparison."""
    if not address:
        return ""
    # Lowercase, remove punctuation, normalize whitespace
    addr = address.lower()
    addr = re.sub(r'[^\w\s]', ' ', addr)
    addr = re.sub(r'\s+', ' ', addr).strip()
    return addr


def detect_virtual_office(address: str) -> Optional[dict]:
    """
    Detect if address appears to be a virtual office or mail drop.
    """
    if not address:
        return None

    addr_lower = address.lower()

    # Check for known virtual office providers
    for indicator in VIRTUAL_OFFICE_INDICATORS[:14]:  # Just company names
        if indicator in addr_lower:
            return {
                'pattern_type': 'VIRTUAL_OFFICE',
                'severity': 'MEDIUM',
                'score': 10,
                'description': f'Address appears to be a virtual office ({indicator})',
                'evidence': {
                    'address': address,
                    'indicator': indicator
                },
                'recommendation': 'Virtual office address - verify actual place of business exists'
            }

    # Check for suite/unit patterns that suggest mail center
    if re.search(r'(pmb|mailbox|p\.?o\.?\s*box)\s*\d+', addr_lower):
        return {
            'pattern_type': 'MAIL_DROP',
            'severity': 'HIGH',
            'score': 15,
            'description': 'Address is a mailbox or PO Box',
            'evidence': {
                'address': address
            },
            'recommendation': 'Mail drop address suggests no physical operations - investigate'
        }

    return None


def detect_residential_address(
    address: str,
    contract_value: float
) -> Optional[dict]:
    """
    Detect if address appears to be residential for large contracts.
    """
    if not address or contract_value < 250000:
        return None

    addr_lower = address.lower()

    for pattern in RESIDENTIAL_PATTERNS:
        if re.search(pattern, addr_lower):
            return {
                'pattern_type': 'RESIDENTIAL_ADDRESS',
                'severity': 'MEDIUM',
                'score': 10,
                'description': f'Address appears residential for ${contract_value:,.0f} contract',
                'evidence': {
                    'address': address,
                    'contract_value': contract_value
                },
                'recommendation': 'Residential address for large contract - verify business operations'
            }

    return None


def detect_shared_addresses(
    entities: list[dict],
    min_shared: int = 2
) -> list[dict]:
    """
    Detect multiple contractors sharing the same address.
    """
    indicators = []

    # Group entities by normalized address
    by_address = defaultdict(list)

    for entity in entities:
        addr = normalize_address(entity.get('address', ''))
        if addr and len(addr) > 10:  # Skip very short addresses
            by_address[addr].append(entity)

    for addr, shared_entities in by_address.items():
        if len(shared_entities) >= min_shared:
            total_value = sum(
                e.get('total_contract_value', 0) or 0
                for e in shared_entities
            )

            indicators.append({
                'pattern_type': 'SHARED_ADDRESS',
                'severity': 'HIGH' if len(shared_entities) >= 3 else 'MEDIUM',
                'score': 15 if len(shared_entities) >= 3 else 10,
                'description': f'{len(shared_entities)} contractors share same address',
                'evidence': {
                    'address': shared_entities[0].get('address', ''),
                    'entity_count': len(shared_entities),
                    'entities': [
                        {
                            'name': e.get('legal_name', 'Unknown'),
                            'uei': e.get('uei', ''),
                            'value': e.get('total_contract_value', 0)
                        }
                        for e in shared_entities[:5]
                    ],
                    'total_value': total_value
                },
                'recommendation': 'Shared address indicates related entities - investigate for pass-through or shell scheme'
            })

    return indicators


def detect_address_cluster(
    target_entity: dict,
    all_entities: list[dict],
    proximity_threshold: float = 0.8
) -> Optional[dict]:
    """
    Detect if entity's address is suspiciously similar to many others.
    """
    target_addr = normalize_address(target_entity.get('address', ''))

    if not target_addr or len(target_addr) < 15:
        return None

    # Simple similarity: shared prefix
    prefix_len = int(len(target_addr) * 0.6)
    target_prefix = target_addr[:prefix_len]

    similar_entities = []
    for entity in all_entities:
        if entity.get('uei') == target_entity.get('uei'):
            continue

        other_addr = normalize_address(entity.get('address', ''))
        if other_addr.startswith(target_prefix):
            similar_entities.append(entity)

    if len(similar_entities) >= 3:
        return {
            'pattern_type': 'ADDRESS_CLUSTER',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'{len(similar_entities)} entities at similar addresses',
            'evidence': {
                'base_address': target_entity.get('address', ''),
                'similar_count': len(similar_entities),
                'similar_entities': [
                    {
                        'name': e.get('legal_name', ''),
                        'address': e.get('address', '')
                    }
                    for e in similar_entities[:3]
                ]
            },
            'recommendation': 'Address cluster may indicate related shell companies'
        }

    return None


def detect_address_changes(
    current_address: str,
    previous_addresses: list[dict],
    contracts: list
) -> Optional[dict]:
    """
    Detect frequent or suspicious address changes.
    """
    if len(previous_addresses) < 2:
        return None

    # Sort by date
    try:
        sorted_addrs = sorted(
            previous_addresses,
            key=lambda x: x.get('change_date', ''),
            reverse=True
        )
    except (TypeError, KeyError):
        return None

    # Count recent changes
    recent_changes = []
    for addr in sorted_addrs:
        change_date = addr.get('change_date', '')
        if change_date and change_date > (sorted_addrs[-1].get('change_date', '') if sorted_addrs else ''):
            recent_changes.append(addr)

    if len(recent_changes) >= 3:  # 3+ address changes
        return {
            'pattern_type': 'FREQUENT_ADDRESS_CHANGES',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'{len(recent_changes)} address changes on record',
            'evidence': {
                'current_address': current_address,
                'change_count': len(recent_changes),
                'addresses': [
                    {
                        'address': a.get('address', ''),
                        'date': a.get('change_date', '')
                    }
                    for a in recent_changes[:5]
                ]
            },
            'recommendation': 'Frequent address changes may indicate instability or evasion'
        }

    return None


def detect_geographic_mismatch(
    entity_address: str,
    contract_place_of_performance: str,
    entity_state: str = None,
    pop_state: str = None
) -> Optional[dict]:
    """
    Detect if contractor is far from where work is performed.
    """
    if not entity_state or not pop_state:
        # Try to extract state from addresses
        state_pattern = r'\b([A-Z]{2})\s+\d{5}'

        if entity_address:
            match = re.search(state_pattern, entity_address.upper())
            if match:
                entity_state = match.group(1)

        if contract_place_of_performance:
            match = re.search(state_pattern, contract_place_of_performance.upper())
            if match:
                pop_state = match.group(1)

    if not entity_state or not pop_state:
        return None

    if entity_state != pop_state:
        return {
            'pattern_type': 'GEOGRAPHIC_MISMATCH',
            'severity': 'LOW',
            'score': 5,
            'description': f'Contractor in {entity_state} performing work in {pop_state}',
            'evidence': {
                'entity_state': entity_state,
                'performance_state': pop_state,
                'entity_address': entity_address,
                'pop_address': contract_place_of_performance
            },
            'recommendation': 'Geographic mismatch - may indicate subcontracting or travel issues'
        }

    return None


def analyze_contractor_address(
    entity: dict,
    all_entities: list[dict],
    contracts: list
) -> list[dict]:
    """
    Comprehensive address analysis for a contractor.
    """
    indicators = []

    address = entity.get('address', '') or entity.get('physical_address', '')

    if not address:
        return indicators

    # Check virtual office
    result = detect_virtual_office(address)
    if result:
        indicators.append(result)

    # Check residential for high-value contractors
    total_value = sum(
        c.total_obligation for c in contracts
        if c.recipient_uei == entity.get('uei', '')
    )

    result = detect_residential_address(address, total_value)
    if result:
        indicators.append(result)

    # Check for address cluster
    result = detect_address_cluster(entity, all_entities)
    if result:
        indicators.append(result)

    return indicators
