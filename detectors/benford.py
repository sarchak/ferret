"""
Benford's Law Anomaly Detection

Natural financial data follows Benford's Law - first digits appear with
specific frequencies (1 appears ~30%, 9 appears ~5%). Fraudulent or
manipulated numbers often deviate from this distribution.

What it catches:
- Fabricated invoices
- Rounded-up estimates
- Manipulated pricing
"""

from dataclasses import dataclass
from collections import Counter
from typing import Optional
import math


# Expected Benford's Law distribution
BENFORD_EXPECTED = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046
}

# Chi-square critical value for df=8 at p=0.05
CHI_SQUARE_CRITICAL = 15.51


@dataclass
class BenfordAnomaly:
    """Result of Benford's Law analysis."""
    chi_square: float
    p_value_approx: str  # "< 0.05", "> 0.05", etc.
    is_anomalous: bool
    observed_distribution: dict[int, float]
    expected_distribution: dict[int, float]
    sample_size: int
    most_deviant_digit: int
    deviation_description: str


def get_first_digit(n: float) -> Optional[int]:
    """Extract first significant digit from a number."""
    if n <= 0:
        return None
    # Handle scientific notation and get first digit
    s = f"{n:.10e}"
    for char in s:
        if char.isdigit() and char != '0':
            return int(char)
    return None


def analyze_benfords_law(amounts: list[float], min_samples: int = 50) -> Optional[BenfordAnomaly]:
    """
    Apply Benford's Law analysis to a set of financial amounts.

    Args:
        amounts: List of dollar amounts to analyze
        min_samples: Minimum sample size for meaningful analysis

    Returns:
        BenfordAnomaly if analysis possible, None if insufficient data
    """
    # Extract first digits
    first_digits = []
    for amount in amounts:
        digit = get_first_digit(amount)
        if digit:
            first_digits.append(digit)

    if len(first_digits) < min_samples:
        return None

    # Calculate observed distribution
    digit_counts = Counter(first_digits)
    total = len(first_digits)

    observed = {}
    for digit in range(1, 10):
        observed[digit] = digit_counts.get(digit, 0) / total

    # Calculate chi-square statistic
    chi_square = 0.0
    max_deviation = 0.0
    most_deviant = 1

    for digit in range(1, 10):
        obs = observed[digit]
        exp = BENFORD_EXPECTED[digit]

        # Chi-square contribution
        chi_square += ((obs - exp) ** 2) / exp * total

        # Track most deviant digit
        deviation = abs(obs - exp)
        if deviation > max_deviation:
            max_deviation = deviation
            most_deviant = digit

    # Determine if anomalous
    is_anomalous = chi_square > CHI_SQUARE_CRITICAL

    # Approximate p-value description
    if chi_square > 26.12:  # p < 0.001
        p_value = "< 0.001"
    elif chi_square > 20.09:  # p < 0.01
        p_value = "< 0.01"
    elif chi_square > CHI_SQUARE_CRITICAL:  # p < 0.05
        p_value = "< 0.05"
    else:
        p_value = "> 0.05"

    # Build description
    if is_anomalous:
        obs_pct = observed[most_deviant] * 100
        exp_pct = BENFORD_EXPECTED[most_deviant] * 100
        if obs_pct > exp_pct:
            description = f"Digit {most_deviant} appears {obs_pct:.1f}% (expected {exp_pct:.1f}%) - overrepresented"
        else:
            description = f"Digit {most_deviant} appears {obs_pct:.1f}% (expected {exp_pct:.1f}%) - underrepresented"
    else:
        description = "Distribution follows Benford's Law - no anomaly detected"

    return BenfordAnomaly(
        chi_square=chi_square,
        p_value_approx=p_value,
        is_anomalous=is_anomalous,
        observed_distribution=observed,
        expected_distribution=BENFORD_EXPECTED.copy(),
        sample_size=total,
        most_deviant_digit=most_deviant,
        deviation_description=description
    )


def analyze_contractor_amounts(contracts: list, contractor_uei: str) -> Optional[dict]:
    """
    Analyze a specific contractor's contract amounts for Benford violations.

    Returns fraud indicator if anomalous.
    """
    amounts = [c.total_obligation for c in contracts
               if c.recipient_uei == contractor_uei and c.total_obligation > 0]

    if len(amounts) < 30:  # Need sufficient sample
        return None

    result = analyze_benfords_law(amounts)

    if result and result.is_anomalous:
        return {
            'pattern_type': 'BENFORDS_LAW_VIOLATION',
            'severity': 'MEDIUM',
            'score': 10,
            'description': f"Contract amounts deviate from Benford's Law (chi-square={result.chi_square:.1f})",
            'evidence': {
                'chi_square': result.chi_square,
                'p_value': result.p_value_approx,
                'sample_size': result.sample_size,
                'most_deviant_digit': result.most_deviant_digit,
                'deviation': result.deviation_description
            },
            'recommendation': 'Review pricing methodology - amounts may be artificially constructed'
        }

    return None


def analyze_agency_amounts(contracts: list, agency: str) -> Optional[dict]:
    """
    Analyze an agency's contract amounts for systemic Benford violations.
    """
    amounts = [c.total_obligation for c in contracts
               if c.agency == agency and c.total_obligation > 0]

    result = analyze_benfords_law(amounts, min_samples=100)

    if result and result.is_anomalous:
        return {
            'agency': agency,
            'anomaly': result,
            'recommendation': 'Agency-wide pricing patterns warrant review'
        }

    return None
