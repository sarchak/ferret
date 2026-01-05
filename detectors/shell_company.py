"""
Shell Company Detection

Identifies indicators that a federal contractor may be a shell company
set up specifically to win contracts.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from data_sources import Contract, EntityRegistration
from data_sources.web_research import check_virtual_office_keywords


@dataclass
class ShellCompanyIndicator:
    """A single indicator of shell company activity."""
    name: str
    description: str
    severity: str  # "high", "medium", "low"
    points: int  # Risk points (0-25)
    evidence: str


@dataclass
class ShellCompanyAssessment:
    """Assessment of shell company indicators for a contractor."""
    contractor_name: str
    uei: str
    indicators: list[ShellCompanyIndicator]
    total_score: int
    risk_level: str  # "low", "medium", "high", "critical"
    summary: str


def calculate_registration_age_risk(
    registration_date: str,
    award_date: str
) -> Optional[ShellCompanyIndicator]:
    """
    Check if SAM.gov registration was suspiciously close to award date.

    Red flag: Registration < 90 days before award
    """
    if not registration_date or not award_date:
        return None

    try:
        reg_date = datetime.strptime(registration_date, "%Y-%m-%d")
        awd_date = datetime.strptime(award_date, "%Y-%m-%d")
        days_before = (awd_date - reg_date).days

        if days_before < 0:
            return None  # Registration after award (data issue)

        if days_before < 30:
            return ShellCompanyIndicator(
                name="Very Recent SAM Registration",
                description=f"Registered only {days_before} days before award",
                severity="high",
                points=25,
                evidence=f"Registration: {registration_date}, Award: {award_date}"
            )
        elif days_before < 90:
            return ShellCompanyIndicator(
                name="Recent SAM Registration",
                description=f"Registered {days_before} days before award",
                severity="medium",
                points=15,
                evidence=f"Registration: {registration_date}, Award: {award_date}"
            )

    except ValueError:
        pass

    return None


def check_virtual_office_address(
    address: str,
    city: str,
    state: str
) -> Optional[ShellCompanyIndicator]:
    """
    Check if the business address appears to be a virtual office or mailbox.
    """
    indicators = check_virtual_office_keywords(address)

    if indicators:
        return ShellCompanyIndicator(
            name="Virtual Office Address",
            description=f"Address contains virtual office indicators: {', '.join(indicators)}",
            severity="high",
            points=20,
            evidence=f"{address}, {city}, {state}"
        )

    return None


def check_shared_address(
    address: str,
    city: str,
    state: str,
    other_contractors_at_address: int
) -> Optional[ShellCompanyIndicator]:
    """
    Check if multiple federal contractors share the same address.
    """
    if other_contractors_at_address >= 10:
        return ShellCompanyIndicator(
            name="Heavily Shared Address",
            description=f"{other_contractors_at_address} other contractors at same address",
            severity="high",
            points=20,
            evidence=f"{address}, {city}, {state}"
        )
    elif other_contractors_at_address >= 5:
        return ShellCompanyIndicator(
            name="Shared Address",
            description=f"{other_contractors_at_address} other contractors at same address",
            severity="medium",
            points=10,
            evidence=f"{address}, {city}, {state}"
        )

    return None


def check_employee_count(
    linkedin_employees: Optional[int],
    contract_value: float
) -> Optional[ShellCompanyIndicator]:
    """
    Check if employee count is suspiciously low for contract value.
    """
    if linkedin_employees is None:
        return ShellCompanyIndicator(
            name="No LinkedIn Presence",
            description="Company has no detectable LinkedIn presence",
            severity="medium",
            points=10,
            evidence="LinkedIn search returned no results"
        )

    # Rough heuristic: $100k revenue per employee is low-end
    expected_min_employees = int(contract_value / 500000)  # $500k per employee

    if linkedin_employees < 3:
        return ShellCompanyIndicator(
            name="Minimal Employees",
            description=f"Only {linkedin_employees} employees on LinkedIn",
            severity="high",
            points=20,
            evidence=f"LinkedIn shows {linkedin_employees} employees for ${contract_value:,.0f} contract"
        )
    elif linkedin_employees < expected_min_employees:
        return ShellCompanyIndicator(
            name="Low Employee Count",
            description=f"{linkedin_employees} employees seems low for ${contract_value:,.0f} contract",
            severity="medium",
            points=10,
            evidence=f"Expected at least {expected_min_employees} employees"
        )

    return None


def check_website_age(
    website_age_days: Optional[int]
) -> Optional[ShellCompanyIndicator]:
    """
    Check if company website is suspiciously new.
    """
    if website_age_days is None:
        return ShellCompanyIndicator(
            name="No Website Found",
            description="Company has no detectable website",
            severity="medium",
            points=15,
            evidence="Web search found no company website"
        )

    if website_age_days < 90:
        return ShellCompanyIndicator(
            name="Very New Website",
            description=f"Website is only {website_age_days} days old",
            severity="high",
            points=20,
            evidence=f"Domain registration: {website_age_days} days ago"
        )
    elif website_age_days < 180:
        return ShellCompanyIndicator(
            name="New Website",
            description=f"Website is only {website_age_days} days old",
            severity="medium",
            points=10,
            evidence=f"Domain registration: {website_age_days} days ago"
        )

    return None


def assess_shell_company_risk(
    contract: Contract,
    entity: Optional[EntityRegistration],
    linkedin_employees: Optional[int] = None,
    website_age_days: Optional[int] = None,
    other_contractors_at_address: int = 0
) -> ShellCompanyAssessment:
    """
    Comprehensive shell company risk assessment.
    """
    indicators = []

    # Registration age check
    if entity:
        indicator = calculate_registration_age_risk(
            entity.registration_date,
            contract.start_date
        )
        if indicator:
            indicators.append(indicator)

        # Virtual office check
        indicator = check_virtual_office_address(
            entity.physical_address,
            entity.physical_city,
            entity.physical_state
        )
        if indicator:
            indicators.append(indicator)

        # Shared address check
        indicator = check_shared_address(
            entity.physical_address,
            entity.physical_city,
            entity.physical_state,
            other_contractors_at_address
        )
        if indicator:
            indicators.append(indicator)

    # Employee count check
    indicator = check_employee_count(linkedin_employees, contract.total_obligation)
    if indicator:
        indicators.append(indicator)

    # Website age check
    indicator = check_website_age(website_age_days)
    if indicator:
        indicators.append(indicator)

    # Calculate total score
    total_score = sum(i.points for i in indicators)

    # Determine risk level
    if total_score >= 60:
        risk_level = "critical"
    elif total_score >= 40:
        risk_level = "high"
    elif total_score >= 20:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Generate summary
    high_severity = [i for i in indicators if i.severity == "high"]
    if high_severity:
        summary = f"Found {len(high_severity)} high-severity shell company indicators"
    elif indicators:
        summary = f"Found {len(indicators)} potential shell company indicators"
    else:
        summary = "No significant shell company indicators detected"

    return ShellCompanyAssessment(
        contractor_name=contract.recipient_name,
        uei=contract.recipient_uei,
        indicators=indicators,
        total_score=total_score,
        risk_level=risk_level,
        summary=summary
    )
