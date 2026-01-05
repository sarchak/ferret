"""
Employee-to-Revenue Ratio Analysis

Compares reported employee counts against contract values to detect:
- Shell companies (no real employees)
- Pass-through schemes (heavy subcontracting)
- Inflated contracts
- Employee count fraud

What it catches:
- Shell companies
- Pass-through arrangements
- False small business claims
- Labor capacity fraud
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta


# Industry benchmarks for revenue per employee (approximate)
REVENUE_PER_EMPLOYEE_BENCHMARKS = {
    'professional_services': 200000,  # Consulting, IT services
    'construction': 300000,
    'manufacturing': 400000,
    'staffing': 150000,
    'default': 250000
}


@dataclass
class EmployeeRevenueAnomaly:
    """Employee/revenue ratio anomaly result."""
    anomaly_type: str
    severity: str
    description: str
    evidence: dict
    recommendation: str


def detect_no_employees(entity: dict) -> Optional[dict]:
    """
    Detect contractors with no reported employees.
    """
    employee_count = entity.get('employee_count') or entity.get('employees', 0)

    if employee_count == 0 or employee_count is None:
        return {
            'pattern_type': 'NO_EMPLOYEES_REPORTED',
            'severity': 'HIGH',
            'score': 15,
            'description': 'No employees reported in SAM.gov registration',
            'evidence': {
                'employee_count': 0,
                'legal_name': entity.get('legal_name', 'Unknown')
            },
            'recommendation': 'Entity with no employees may be a shell company - verify operations'
        }

    return None


def detect_high_revenue_per_employee(
    entity: dict,
    annual_contract_value: float,
    industry_type: str = 'default'
) -> Optional[dict]:
    """
    Detect implausible revenue per employee ratios.
    """
    employee_count = entity.get('employee_count') or entity.get('employees', 0)

    if not employee_count or employee_count == 0:
        return None

    revenue_per_employee = annual_contract_value / employee_count
    benchmark = REVENUE_PER_EMPLOYEE_BENCHMARKS.get(industry_type, REVENUE_PER_EMPLOYEE_BENCHMARKS['default'])

    # Very high ratio (> 2x benchmark)
    if revenue_per_employee > benchmark * 2:
        return {
            'pattern_type': 'HIGH_REVENUE_PER_EMPLOYEE',
            'severity': 'HIGH' if revenue_per_employee > benchmark * 3 else 'MEDIUM',
            'score': 15 if revenue_per_employee > benchmark * 3 else 10,
            'description': f'${revenue_per_employee:,.0f} revenue per employee ({revenue_per_employee/benchmark:.1f}x benchmark)',
            'evidence': {
                'employees': employee_count,
                'annual_contract_value': annual_contract_value,
                'revenue_per_employee': revenue_per_employee,
                'benchmark': benchmark,
                'ratio_to_benchmark': revenue_per_employee / benchmark
            },
            'recommendation': 'Revenue per employee suggests heavy subcontracting - verify work is performed in-house'
        }

    return None


def detect_insufficient_employees(
    entity: dict,
    contract_value: float,
    contract_description: str = ''
) -> Optional[dict]:
    """
    Detect if employee count is insufficient for contract scope.
    """
    employee_count = entity.get('employee_count') or entity.get('employees', 0)

    if not employee_count:
        return None

    # Estimate FTE requirements based on contract value
    # Rough heuristic: $150K-200K per FTE for services
    estimated_fte = contract_value / 175000

    if estimated_fte > employee_count * 2 and estimated_fte > 5:
        return {
            'pattern_type': 'INSUFFICIENT_EMPLOYEES',
            'severity': 'HIGH',
            'score': 15,
            'description': f'Contract requires ~{estimated_fte:.0f} FTE but entity has {employee_count} employees',
            'evidence': {
                'employees': employee_count,
                'contract_value': contract_value,
                'estimated_fte_needed': estimated_fte,
                'shortfall': estimated_fte - employee_count
            },
            'recommendation': 'Cannot perform contract with stated workforce - subcontracting or pass-through likely'
        }

    return None


def detect_employee_count_change(
    current_count: int,
    historical_count: int,
    months_between: int = 12
) -> Optional[dict]:
    """
    Detect suspicious changes in employee count.
    """
    if not historical_count or historical_count == 0:
        return None

    change_pct = (current_count - historical_count) / historical_count

    # Dramatic increase (> 300% growth in a year)
    if change_pct > 3.0 and months_between <= 12:
        return {
            'pattern_type': 'RAPID_EMPLOYEE_GROWTH',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'Employee count grew {change_pct:.0%} in {months_between} months',
            'evidence': {
                'previous_count': historical_count,
                'current_count': current_count,
                'growth_pct': change_pct,
                'months': months_between
            },
            'recommendation': 'Rapid employee growth - may be inflating numbers to qualify for contracts'
        }

    # Dramatic decrease (> 70% drop)
    if change_pct < -0.7 and months_between <= 12:
        return {
            'pattern_type': 'RAPID_EMPLOYEE_DECLINE',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f'Employee count dropped {abs(change_pct):.0%} in {months_between} months',
            'evidence': {
                'previous_count': historical_count,
                'current_count': current_count,
                'decline_pct': abs(change_pct)
            },
            'recommendation': 'Major employee decline while holding contracts - may affect performance capability'
        }

    return None


def detect_size_standard_mismatch(
    entity: dict,
    claimed_size: str,
    naics_code: str = ''
) -> Optional[dict]:
    """
    Detect potential false small business claims.

    Note: Requires SBA size standards data for NAICS codes.
    """
    # This would require SBA size standards lookup
    # Placeholder for future implementation

    employee_count = entity.get('employee_count') or entity.get('employees', 0)
    revenue = entity.get('annual_revenue', 0)

    # Simple heuristic checks
    if 'small' in claimed_size.lower():
        # Most small business size standards are under 500-1500 employees
        if employee_count and employee_count > 1500:
            return {
                'pattern_type': 'SIZE_STANDARD_VIOLATION',
                'severity': 'HIGH',
                'score': 20,
                'description': f'Claims small business status with {employee_count} employees',
                'evidence': {
                    'claimed_size': claimed_size,
                    'employee_count': employee_count
                },
                'recommendation': 'Verify small business eligibility - employee count exceeds typical thresholds'
            }

    return None


def analyze_employee_revenue_ratio(
    entity: dict,
    contracts: list,
    contractor_uei: str
) -> list[dict]:
    """
    Comprehensive employee/revenue analysis for a contractor.
    """
    indicators = []

    # Check for no employees
    result = detect_no_employees(entity)
    if result:
        indicators.append(result)
        return indicators  # If no employees, other checks don't apply

    # Calculate annual contract value
    one_year_ago = datetime.now() - timedelta(days=365)
    recent_contracts = []

    for c in contracts:
        if c.recipient_uei != contractor_uei:
            continue
        try:
            award_date = datetime.strptime(c.start_date, "%Y-%m-%d")
            if award_date >= one_year_ago:
                recent_contracts.append(c)
        except (ValueError, TypeError):
            continue

    annual_value = sum(c.total_obligation for c in recent_contracts)

    if annual_value > 0:
        result = detect_high_revenue_per_employee(entity, annual_value)
        if result:
            indicators.append(result)

    # Check individual large contracts
    for contract in recent_contracts:
        if contract.total_obligation > 500000:
            result = detect_insufficient_employees(
                entity,
                contract.total_obligation,
                getattr(contract, 'description', '')
            )
            if result:
                result['contract_id'] = contract.contract_id
                indicators.append(result)
                break  # One finding is enough

    return indicators
