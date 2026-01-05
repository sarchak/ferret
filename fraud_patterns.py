"""
Federal Contract Fraud Patterns

Defines fraud patterns based on GAO, DOJ, and OIG investigations.
Each pattern has:
- Definition and legal basis
- Required data sources
- Detection logic
- Precision level (how likely a match is true fraud)

Sources:
- GAO-24-105833: Federal government loses $233-521B annually to fraud
- DOJ Procurement Collusion Strike Force: 140+ investigations, 60+ convictions
- GSA OIG Red Flags: https://www.gsaig.gov/red-flags-fraud
- DOD OIG Fraud Detection Resources
- SBA 8(a) Program Audit findings
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class DataSource(Enum):
    """Available data sources for fraud detection."""
    USASPENDING = "usaspending"  # Contract awards and obligations
    SAM_ENTITIES = "sam_entities"  # Entity registrations
    SAM_EXCLUSIONS = "sam_exclusions"  # Debarred/suspended entities
    FSRS = "fsrs"  # Federal Subaward Reporting System
    FPDS = "fpds"  # Federal Procurement Data System
    SEC_EDGAR = "sec_edgar"  # Public company filings
    FINCEN_BOI = "fincen_boi"  # Beneficial Ownership (CTA 2024)


class Precision(Enum):
    """How likely a detection is true fraud vs false positive."""
    CRITICAL = "critical"  # >90% likely fraud, immediate investigation
    HIGH = "high"  # 70-90% likely fraud
    MEDIUM = "medium"  # 40-70% likely fraud
    LOW = "low"  # <40% likely fraud, requires corroboration


@dataclass
class FraudPattern:
    """Definition of a detectable fraud pattern."""
    id: str
    name: str
    description: str
    legal_basis: str  # FAR, USC, or case law reference
    data_sources: list[DataSource]
    detection_logic: str  # Pseudocode for detection
    precision: Precision
    examples: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)


# ============================================================================
# PATTERN DEFINITIONS
# ============================================================================

FRAUD_PATTERNS = {

    # -------------------------------------------------------------------------
    # CRITICAL PRECISION - Clear violations, immediate investigation
    # -------------------------------------------------------------------------

    "EXCLUDED_ACTIVE_CONTRACT": FraudPattern(
        id="EXCLUDED_ACTIVE_CONTRACT",
        name="Excluded Entity Receiving Active Contracts",
        description="""
        An entity on the SAM.gov exclusion list (debarred, suspended, or
        proposed for debarment) is receiving federal contract awards.

        This is a clear FAR violation - agencies are prohibited from awarding
        contracts to excluded entities without a compelling reason determination
        from the agency head.
        """,
        legal_basis="FAR 9.405 - Effect of listing",
        data_sources=[DataSource.SAM_EXCLUSIONS, DataSource.USASPENDING],
        detection_logic="""
        1. Get contract with recipient_uei = X
        2. Look up X in SAM exclusions by EXACT UEI match
        3. If found, compare dates:
           - exclusion.active_date < contract.award_date
           - exclusion.termination_date is null OR > contract.award_date
        4. If both true → VIOLATION
        """,
        precision=Precision.CRITICAL,
        examples=[
            "Contractor debarred for fraud in 2022 receives new $5M contract in 2024",
            "Suspended contractor receives task order on existing IDIQ"
        ],
        red_flags=[
            "Exact UEI match between contract recipient and excluded entity",
            "Contract award date after exclusion active date",
            "No termination date or termination date in future"
        ]
    ),

    "RAPID_REGISTRATION_LARGE_AWARD": FraudPattern(
        id="RAPID_REGISTRATION_LARGE_AWARD",
        name="New Entity Immediately Receives Large Contract",
        description="""
        An entity registers in SAM.gov and within 90 days receives a contract
        exceeding $1M. Legitimate contractors typically have years of history
        before winning major federal contracts.

        This pattern is common in fraud schemes where shell companies are
        created specifically to receive fraudulent awards.
        """,
        legal_basis="FAR 9.104 - Standards for contractor responsibility",
        data_sources=[DataSource.SAM_ENTITIES, DataSource.USASPENDING],
        detection_logic="""
        1. Get contract with value > $1,000,000
        2. Look up recipient in SAM entities
        3. Calculate: contract.award_date - entity.registration_date
        4. If < 90 days → FLAG
        5. Increase severity if:
           - Entity has no website
           - Entity has virtual office address
           - First-time contractor
        """,
        precision=Precision.HIGH,
        examples=[
            "LLC formed 30 days before $2M sole-source award",
            "New entity wins 8(a) set-aside within weeks of certification"
        ],
        red_flags=[
            "SAM registration < 90 days before first contract",
            "No prior contract history",
            "Virtual office address (suite, PMB, PO Box)",
            "No website or minimal web presence"
        ]
    ),

    # -------------------------------------------------------------------------
    # HIGH PRECISION - Strong indicators, likely fraud
    # -------------------------------------------------------------------------

    "ADDRESS_CLUSTER_CONTRACTS": FraudPattern(
        id="ADDRESS_CLUSTER_CONTRACTS",
        name="Multiple Contractors at Same Address Winning Related Contracts",
        description="""
        Multiple entities registered at the same physical address are winning
        contracts from the same agency or for similar services. This suggests
        shell company networks used to create appearance of competition or
        circumvent small business requirements.

        GAO-20-106 found shell corporations facilitate significant DOD fraud.
        """,
        legal_basis="FAR 3.104 - Procurement integrity; 18 USC 1001",
        data_sources=[DataSource.SAM_ENTITIES, DataSource.USASPENDING],
        detection_logic="""
        1. Group entities by normalized address
        2. For address clusters with 3+ entities:
           a. Check if multiple entities won contracts from same agency
           b. Check if contract descriptions overlap
           c. Check if contracts were awarded in similar timeframe
        3. If yes → FLAG as potential bid rigging or shell network
        """,
        precision=Precision.HIGH,
        examples=[
            "5 LLCs at same Chicago address all win GSA contracts",
            "3 'competing' bidders share same registered agent"
        ],
        red_flags=[
            "3+ entities at same normalized address",
            "Contracts awarded by same agency to address cluster",
            "Similar NAICS codes across entities in cluster",
            "Same registered agent or incorporation service"
        ]
    ),

    "PASS_THROUGH_SUBCONTRACTING": FraudPattern(
        id="PASS_THROUGH_SUBCONTRACTING",
        name="Pass-Through Subcontracting Scheme",
        description="""
        A prime contractor (often 8(a), SDVOSB, or HUBZone certified) wins
        set-aside contracts but subcontracts most or all work to an ineligible
        firm. The prime acts as a pass-through, collecting fees without
        performing commercially useful function.

        Treasury 2025 audit of $9B in 8(a) contracts found extensive pass-through.
        """,
        legal_basis="FAR 52.219-14 - Limitations on Subcontracting",
        data_sources=[DataSource.USASPENDING, DataSource.FSRS, DataSource.SAM_ENTITIES],
        detection_logic="""
        1. Get set-aside contract (8(a), SDVOSB, HUBZone, WOSB)
        2. Look up subcontracts in FSRS
        3. Calculate: sum(subcontract_value) / prime_contract_value
        4. If ratio > 50% for services or 85% for manufacturing → FLAG
        5. Check if subcontractor is related party (same address, officers)
        """,
        precision=Precision.HIGH,
        examples=[
            "8(a) firm wins $10M contract, subcontracts $9M to large business",
            "SDVOSB passes work to company owned by non-veteran spouse"
        ],
        red_flags=[
            "Subcontracting ratio exceeds FAR limits",
            "Subcontractor shares address with prime",
            "Prime has minimal employees relative to contract size",
            "Same officers/POCs on prime and subcontractor"
        ]
    ),

    "THRESHOLD_SPLITTING": FraudPattern(
        id="THRESHOLD_SPLITTING",
        name="Contract Splitting to Avoid Thresholds",
        description="""
        A requirement is intentionally split into multiple contracts to keep
        each below procurement thresholds, avoiding competition or oversight.

        Thresholds: $10K micro-purchase, $250K simplified acquisition,
        $750K subcontracting plan, $1M for enhanced oversight.
        """,
        legal_basis="FAR 13.003(c)(2) - Prohibition on splitting",
        data_sources=[DataSource.USASPENDING],
        detection_logic="""
        1. Group contracts by (recipient, agency, similar_description)
        2. Filter groups where:
           - All contracts are 90-99% of a threshold
           - Contracts awarded within 30 days of each other
           - Similar NAICS or PSC codes
        3. Calculate: If sum(values) > threshold but each < threshold → FLAG
        """,
        precision=Precision.HIGH,
        examples=[
            "5 contracts at $247,500 each = $1.24M (avoids $250K threshold)",
            "20 purchases at $9,900 each within one month"
        ],
        red_flags=[
            "Multiple contracts at 90-99% of threshold amount",
            "Same recipient, same agency, similar timeframe",
            "Similar descriptions or PSC codes",
            "Total value exceeds threshold"
        ]
    ),

    # -------------------------------------------------------------------------
    # MEDIUM PRECISION - Suspicious patterns, need corroboration
    # -------------------------------------------------------------------------

    "BID_RIGGING_INDICATORS": FraudPattern(
        id="BID_RIGGING_INDICATORS",
        name="Bid Rigging Indicators",
        description="""
        Patterns suggesting bidders are coordinating rather than competing:
        - Losing bidders become subcontractors
        - Consistent winner rotation
        - Price gap between winner and losers
        - Identical formatting or errors across bids

        DOJ Procurement Collusion Strike Force has 140+ active investigations.
        """,
        legal_basis="15 USC 1 - Sherman Antitrust Act",
        data_sources=[DataSource.USASPENDING, DataSource.FPDS, DataSource.SAM_ENTITIES],
        detection_logic="""
        1. Get competitive contracts with multiple offers
        2. For each winner, check if they appeared as subcontractor
           on contracts won by other bidders
        3. Check for address/officer overlap between bidders
        4. Analyze pricing patterns:
           - Winning bid close to government estimate
           - Large gap between winner and second place
        """,
        precision=Precision.MEDIUM,
        examples=[
            "Same 3 companies always bid together, rotate wins",
            "Losing bidder immediately hired as subcontractor by winner"
        ],
        red_flags=[
            "Losing bidders become subcontractors to winner",
            "Bidders share address, officers, or contact info",
            "Consistent price patterns across competitions",
            "Bid amounts always near government estimate"
        ]
    ),

    "FALSE_CERTIFICATION": FraudPattern(
        id="FALSE_CERTIFICATION",
        name="False Small Business Certification",
        description="""
        Entity falsely certifies as 8(a), SDVOSB, HUBZone, or WOSB to win
        set-aside contracts. Common schemes:
        - "Rent-a-vet": Non-veteran controls SDVOSB
        - Size affiliation: Actually controlled by large business
        - HUBZone fraud: Employees don't live in HUBZone

        SBA announced full audit of 8(a) program in 2025 after DOJ found
        $550M+ in fraudulent contracts.
        """,
        legal_basis="15 USC 645 - False statements; FAR 52.219",
        data_sources=[DataSource.SAM_ENTITIES, DataSource.USASPENDING, DataSource.SEC_EDGAR],
        detection_logic="""
        1. Get set-aside contract recipient
        2. Check certifications claimed vs reality:
           - SDVOSB: Is listed veteran actually in control?
           - HUBZone: Do employees actually reside in zone?
           - 8(a): Is entity actually disadvantaged/small?
        3. Check for affiliation with large businesses:
           - Shared officers with large business
           - Subcontracting to related large business
           - SEC filings showing ownership by public company
        """,
        precision=Precision.MEDIUM,
        examples=[
            "SDVOSB controlled by veteran's non-veteran spouse",
            "8(a) firm actually subsidiary of Fortune 500 company"
        ],
        red_flags=[
            "Veteran/disadvantaged owner has minimal industry experience",
            "Large subcontracts to firms with overlapping officers",
            "SEC filings show ownership by public company",
            "Employee addresses not in claimed HUBZone"
        ]
    ),

    "SOLE_SOURCE_CONCENTRATION": FraudPattern(
        id="SOLE_SOURCE_CONCENTRATION",
        name="Suspicious Sole-Source Concentration",
        description="""
        An entity receives multiple sole-source (no competition) contracts
        from the same agency or contracting officer. While some sole-source
        is legitimate, high concentration suggests potential collusion or
        improper steering.
        """,
        legal_basis="FAR 6.302 - Circumstances permitting other than full competition",
        data_sources=[DataSource.USASPENDING, DataSource.FPDS],
        detection_logic="""
        1. Group contracts by recipient
        2. For each recipient, calculate:
           - sole_source_count / total_contracts
           - sole_source_value / total_value
        3. If ratio > 80% AND total_value > $1M → FLAG
        4. Check if same contracting officer across awards
        """,
        precision=Precision.MEDIUM,
        examples=[
            "Contractor receives 10 consecutive sole-source awards from same CO",
            "All 15 contracts are sole-source, totaling $50M"
        ],
        red_flags=[
            ">80% of contracts are sole-source",
            "Same contracting officer on multiple sole-source awards",
            "Justifications cite unique capability without verification",
            "No evidence of market research"
        ]
    ),

    # -------------------------------------------------------------------------
    # LOW PRECISION - Weak signals, need multiple to be meaningful
    # -------------------------------------------------------------------------

    "VIRTUAL_OFFICE_INDICATORS": FraudPattern(
        id="VIRTUAL_OFFICE_INDICATORS",
        name="Virtual Office Address Indicators",
        description="""
        Entity uses address associated with virtual office providers (Regus,
        WeWork, etc.) or PO Box. While not inherently fraudulent, shell
        companies often use these to appear legitimate.

        Should be combined with other indicators to increase confidence.
        """,
        legal_basis="N/A - Indicator only, not violation",
        data_sources=[DataSource.SAM_ENTITIES],
        detection_logic="""
        1. Parse entity address
        2. Check for virtual office keywords:
           - Suite, Ste, #, Unit, PMB, PO Box
           - Known providers: Regus, WeWork, Spaces
        3. Flag but require corroboration with other signals
        """,
        precision=Precision.LOW,
        examples=[
            "Contractor address is 'Suite 100' in Regus building",
            "Address is PO Box with no physical location"
        ],
        red_flags=[
            "Address contains suite/unit/PMB/box",
            "Address matches known virtual office provider",
            "No physical presence verification possible"
        ]
    ),

    "NO_WEB_PRESENCE": FraudPattern(
        id="NO_WEB_PRESENCE",
        name="No Web or Business Presence",
        description="""
        Entity receiving significant contracts has no website, LinkedIn
        presence, or verifiable business operations. Legitimate contractors
        typically have some web presence.

        Should be combined with other indicators.
        """,
        legal_basis="N/A - Indicator only",
        data_sources=[DataSource.SAM_ENTITIES],
        detection_logic="""
        1. Check if entity_url is blank in SAM data
        2. Search for entity name online
        3. Check LinkedIn for company page
        4. Flag if all checks fail AND contract value > $100K
        """,
        precision=Precision.LOW,
        examples=[
            "$5M contractor has no website or LinkedIn page",
            "Company name returns zero search results"
        ],
        red_flags=[
            "No website in SAM registration",
            "No LinkedIn company page",
            "No news articles or press releases",
            "Domain registered recently if exists"
        ]
    ),
}


def get_pattern(pattern_id: str) -> Optional[FraudPattern]:
    """Get a fraud pattern by ID."""
    return FRAUD_PATTERNS.get(pattern_id)


def get_patterns_by_precision(precision: Precision) -> list[FraudPattern]:
    """Get all patterns with a given precision level."""
    return [p for p in FRAUD_PATTERNS.values() if p.precision == precision]


def get_detectable_patterns(available_sources: list[DataSource]) -> list[FraudPattern]:
    """Get patterns that can be detected with available data sources."""
    detectable = []
    for pattern in FRAUD_PATTERNS.values():
        # Check if we have all required data sources
        if all(src in available_sources for src in pattern.data_sources):
            detectable.append(pattern)
    return detectable


def print_pattern_summary():
    """Print summary of all patterns."""
    print("=" * 70)
    print("FEDERAL CONTRACT FRAUD PATTERNS")
    print("=" * 70)

    for precision in Precision:
        patterns = get_patterns_by_precision(precision)
        if patterns:
            print(f"\n{precision.value.upper()} PRECISION ({len(patterns)} patterns):")
            print("-" * 50)
            for p in patterns:
                sources = ", ".join(s.value for s in p.data_sources)
                print(f"  {p.id}")
                print(f"    {p.name}")
                print(f"    Data: {sources}")
                print()


if __name__ == "__main__":
    print_pattern_summary()
