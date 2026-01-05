"""Fraud detection modules."""

from .shell_company import (
    ShellCompanyIndicator,
    ShellCompanyAssessment,
    assess_shell_company_risk
)

from .comprehensive_detector import (
    FraudIndicator,
    ContractorRiskProfile,
    ComprehensiveFraudDetector
)

# New modular detectors
from .benford import (
    BenfordAnomaly,
    analyze_benfords_law,
    analyze_contractor_amounts,
    analyze_agency_amounts
)

from .temporal import (
    TemporalAnomaly,
    detect_weekend_award,
    detect_fiscal_yearend,
    detect_award_velocity,
    detect_yearend_concentration,
    analyze_contract_timing,
    analyze_contractor_timing
)

from .pricing import (
    PricingAnomaly,
    detect_round_number,
    detect_threshold_proximity,
    detect_contract_splitting,
    detect_price_outlier,
    detect_modification_growth,
    analyze_contractor_pricing
)

from .competition import (
    CompetitionAnomaly,
    detect_single_offer_competitive,
    detect_low_competition,
    detect_sole_source_concentration,
    detect_incumbent_always_wins,
    detect_co_contractor_concentration,
    analyze_contractor_competition
)

from .employee_revenue import (
    EmployeeRevenueAnomaly,
    detect_no_employees,
    detect_high_revenue_per_employee,
    detect_insufficient_employees,
    detect_employee_count_change,
    detect_size_standard_mismatch,
    analyze_employee_revenue_ratio
)

from .modifications import (
    ModificationAnomaly,
    detect_excessive_modifications,
    detect_value_growth_pattern,
    detect_late_modifications,
    detect_modification_timing_cluster,
    detect_change_order_pattern,
    analyze_contractor_modifications
)

from .registration import (
    RegistrationAnomaly,
    detect_new_entity_winning,
    detect_registration_age,
    detect_registration_gaps,
    detect_reactivation_pattern,
    detect_entity_type_change,
    detect_exclusion_timing,
    analyze_entity_registration
)

from .address import (
    AddressAnomaly,
    detect_virtual_office,
    detect_residential_address,
    detect_shared_addresses,
    detect_address_cluster,
    detect_geographic_mismatch,
    analyze_contractor_address
)

__all__ = [
    # Shell company detection
    "ShellCompanyIndicator",
    "ShellCompanyAssessment",
    "assess_shell_company_risk",
    # Comprehensive detection
    "FraudIndicator",
    "ContractorRiskProfile",
    "ComprehensiveFraudDetector",
    # Benford's Law
    "BenfordAnomaly",
    "analyze_benfords_law",
    "analyze_contractor_amounts",
    "analyze_agency_amounts",
    # Temporal
    "TemporalAnomaly",
    "detect_weekend_award",
    "detect_fiscal_yearend",
    "detect_award_velocity",
    "detect_yearend_concentration",
    "analyze_contract_timing",
    "analyze_contractor_timing",
    # Pricing
    "PricingAnomaly",
    "detect_round_number",
    "detect_threshold_proximity",
    "detect_contract_splitting",
    "detect_price_outlier",
    "detect_modification_growth",
    "analyze_contractor_pricing",
    # Competition
    "CompetitionAnomaly",
    "detect_single_offer_competitive",
    "detect_low_competition",
    "detect_sole_source_concentration",
    "detect_incumbent_always_wins",
    "detect_co_contractor_concentration",
    "analyze_contractor_competition",
    # Employee/Revenue
    "EmployeeRevenueAnomaly",
    "detect_no_employees",
    "detect_high_revenue_per_employee",
    "detect_insufficient_employees",
    "detect_employee_count_change",
    "detect_size_standard_mismatch",
    "analyze_employee_revenue_ratio",
    # Modifications
    "ModificationAnomaly",
    "detect_excessive_modifications",
    "detect_value_growth_pattern",
    "detect_late_modifications",
    "detect_modification_timing_cluster",
    "detect_change_order_pattern",
    "analyze_contractor_modifications",
    # Registration
    "RegistrationAnomaly",
    "detect_new_entity_winning",
    "detect_registration_age",
    "detect_registration_gaps",
    "detect_reactivation_pattern",
    "detect_entity_type_change",
    "detect_exclusion_timing",
    "analyze_entity_registration",
    # Address
    "AddressAnomaly",
    "detect_virtual_office",
    "detect_residential_address",
    "detect_shared_addresses",
    "detect_address_cluster",
    "detect_geographic_mismatch",
    "analyze_contractor_address",
]
