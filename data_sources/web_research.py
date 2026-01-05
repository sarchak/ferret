"""
Web Research Module

Provides web search and verification capabilities for contractor investigation.
Uses Claude's built-in WebSearch and WebFetch tools when run through the agent.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class CompanyResearch:
    """Compiled research about a company."""
    name: str
    website: Optional[str]
    website_age_days: Optional[int]
    linkedin_url: Optional[str]
    linkedin_employee_count: Optional[int]
    news_mentions: list[dict]  # [{title, url, date, snippet}]
    lawsuit_mentions: list[dict]
    fraud_mentions: list[dict]
    address_verification: Optional[dict]  # {is_virtual_office, is_residential, notes}
    officers: list[dict]  # [{name, title, linkedin_url}]


@dataclass
class OfficerResearch:
    """Research about a company officer."""
    name: str
    title: str
    linkedin_url: Optional[str]
    previous_employers: list[str]
    federal_agency_employment: list[dict]  # [{agency, title, dates}]
    other_companies: list[str]


# Search query templates for different investigation types
SEARCH_QUERIES = {
    "company_existence": [
        '"{company}" company',
        '"{company}" LLC OR Inc OR Corp',
        '"{company}" {state} business'
    ],
    "company_fraud": [
        '"{company}" fraud OR scandal OR lawsuit',
        '"{company}" federal contractor investigation',
        '"{company}" whistleblower OR "false claims"',
        '"{company}" debarred OR suspended'
    ],
    "company_news": [
        '"{company}" news',
        '"{company}" press release',
        '"{company}" award OR contract'
    ],
    "officer_background": [
        '"{name}" "{company}"',
        '"{name}" federal government OR agency',
        '"{name}" linkedin'
    ],
    "officer_conflicts": [
        '"{name}" {agency} employee OR worked',
        '"{name}" federal procurement OR contracting',
        '"{name}" revolving door'
    ],
    "address_verification": [
        '"{address}" virtual office OR mailbox',
        '"{address}" coworking OR "registered agent"',
        '"{address}" office building'
    ]
}


def build_search_queries(
    query_type: str,
    **kwargs
) -> list[str]:
    """
    Build search queries for a specific investigation type.

    Args:
        query_type: Type of search (company_existence, company_fraud, etc.)
        **kwargs: Variables to substitute (company, name, state, address, agency)

    Returns:
        List of formatted search queries
    """
    templates = SEARCH_QUERIES.get(query_type, [])
    queries = []

    for template in templates:
        try:
            query = template.format(**kwargs)
            queries.append(query)
        except KeyError:
            # Skip if required variable not provided
            continue

    return queries


def format_investigation_prompt(
    contractor_name: str,
    contractor_address: str,
    contractor_state: str,
    contract_value: float,
    agency: str
) -> str:
    """
    Format a prompt for Claude to investigate a contractor.

    This prompt guides the agent through a systematic investigation
    using web search and verification.
    """
    return f"""Investigate the federal contractor "{contractor_name}" for fraud indicators.

## Contract Context
- Contractor: {contractor_name}
- Address: {contractor_address}, {contractor_state}
- Contract Value: ${contract_value:,.0f}
- Awarding Agency: {agency}

## Investigation Steps

### 1. Verify Company Existence
Use WebSearch to verify the company exists and is legitimate:
- Search for company website and LinkedIn page
- Check when the website was created (recent = suspicious)
- Look for employee count on LinkedIn (< 5 employees for large contract = suspicious)

### 2. Check for Prior Fraud/Scandals
Search for any history of fraud, lawsuits, or investigations:
- Federal contractor fraud cases
- False Claims Act settlements
- Whistleblower complaints
- Debarment or suspension

### 3. Verify Physical Address
Determine if the business address is legitimate:
- Is it a virtual office or mailbox service?
- Is it a residential address?
- Are there other federal contractors at the same address?

### 4. Research Officers
If officer names are available:
- Check for prior federal government employment (revolving door)
- Look for involvement in other federal contractors
- Search for any personal legal issues

### 5. Check News Coverage
Look for recent news about the company:
- Press releases
- Industry coverage
- Any concerning mentions

## Output Format
Provide findings in this structure:

**Company Legitimacy Score:** [1-10, 10 = clearly legitimate]
**Fraud Risk Score:** [1-10, 10 = high risk]

**Key Findings:**
- [Bullet points of significant findings]

**Red Flags Identified:**
- [Any fraud indicators found]

**Evidence:**
- [URLs and sources for findings]

**Recommendation:**
- [Further investigation needed / Clear / Refer to human reviewer]
"""


def format_officer_investigation_prompt(
    officer_name: str,
    company_name: str,
    awarding_agency: str
) -> str:
    """Format a prompt to investigate potential conflicts of interest for an officer."""
    return f"""Investigate "{officer_name}" from "{company_name}" for potential conflicts of interest.

## Context
- Officer: {officer_name}
- Company: {company_name}
- Awarding Agency: {awarding_agency}

## Investigation Steps

### 1. LinkedIn Research
Search for their LinkedIn profile to find:
- Current position at {company_name}
- Previous employment history
- Any federal government positions

### 2. Revolving Door Check
Look for evidence they worked at {awarding_agency} or related agencies:
- Federal employee records
- News mentions of government service
- Press releases about hiring

### 3. Other Federal Contractors
Search for their involvement in other companies:
- Officer positions at other contractors
- Board memberships
- Ownership stakes

### 4. Conflicts Assessment
Determine if there's a potential conflict:
- Did they award contracts to their future employer?
- Did they leave government and immediately get contracts from former agency?
- Are they connected to decision-makers at the agency?

## Output Format

**Conflict of Interest Risk:** [Low / Medium / High]

**Employment Timeline:**
- [Chronological employment history]

**Government Connections:**
- [Any identified connections to awarding agency]

**Other Contractor Involvement:**
- [Other federal contractors they're associated with]

**Evidence:**
- [URLs and sources]

**Recommendation:**
- [No conflict apparent / Potential conflict - needs review / Clear conflict - escalate]
"""


def format_address_verification_prompt(
    address: str,
    city: str,
    state: str,
    company_name: str
) -> str:
    """Format a prompt to verify a business address."""
    return f"""Verify the business address for "{company_name}".

## Address to Verify
{address}
{city}, {state}

## Verification Steps

### 1. Google Maps Check
Use WebFetch to check Google Maps for this address:
- What type of building is it?
- Does it look like a commercial office?
- Is it a residential property?

### 2. Virtual Office Check
Search for this address to determine if it's:
- A Regus, WeWork, or other coworking space
- A UPS Store or mailbox service
- A registered agent address

### 3. Other Tenants
Search for other companies at this exact address:
- Are there other federal contractors here?
- How many businesses share this address?

### 4. Street View Analysis
If available, describe what you see:
- Building type and size
- Signage
- Parking lot / commercial area

## Output Format

**Address Type:** [Commercial Office / Virtual Office / Residential / Mailbox Service / Unknown]

**Legitimacy Assessment:** [Legitimate / Suspicious / Requires verification]

**Findings:**
- [Description of what was found]

**Other Businesses at Address:**
- [List any other companies found at this address]

**Evidence:**
- [URLs and sources]

**Risk Factors:**
- [Any concerns about the address]
"""


# Common virtual office and mailbox service indicators
VIRTUAL_OFFICE_INDICATORS = [
    "regus",
    "wework",
    "spaces",
    "industrious",
    "ups store",
    "the ups store",
    "mailboxes etc",
    "postal connections",
    "pak mail",
    "postnet",
    "suite",
    "pmb",
    "box",
    "virtual office",
    "business center",
    "executive suite"
]


def check_virtual_office_keywords(address: str) -> list[str]:
    """Check if address contains virtual office indicators."""
    address_lower = address.lower()
    return [indicator for indicator in VIRTUAL_OFFICE_INDICATORS if indicator in address_lower]
