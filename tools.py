"""
FedWatch AI Tools

High-level tools for the fraud investigation agent.
These abstract the underlying APIs (USASpending, SAM.gov, web) into
clean, purpose-built functions for investigation.
"""

import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Optional, Literal
from enum import Enum

from data_sources import USASpendingClient, SAMGovClient, SECEdgarClient, Contract, EntityRegistration
from data_sources.bulk_data import LocalDataStore
from data_sources.web_research import build_search_queries, VIRTUAL_OFFICE_INDICATORS


# ============================================================================
# Data Types
# ============================================================================

class SearchType(str, Enum):
    NAME = "NAME"
    UEI = "UEI"
    DUNS = "DUNS"
    CAGE = "CAGE"


class RelationshipType(str, Enum):
    PARENT = "PARENT"
    SUBSIDIARY = "SUBSIDIARY"
    SHARED_ADDRESS = "SHARED_ADDRESS"
    SHARED_AGENT = "SHARED_AGENT"
    SHARED_EXECUTIVE = "SHARED_EXECUTIVE"


class AnalysisType(str, Enum):
    PRICE_DISTRIBUTION = "PRICE_DISTRIBUTION"
    TIMING = "TIMING"
    THRESHOLD_CLUSTERING = "THRESHOLD_CLUSTERING"
    COMPETITION = "COMPETITION"
    MODIFICATIONS = "MODIFICATIONS"


class ReportType(str, Enum):
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    INVESTIGATION = "INVESTIGATION"
    DUE_DILIGENCE = "DUE_DILIGENCE"
    ANOMALY = "ANOMALY"


@dataclass
class EntitySummary:
    """Summarized entity information."""
    entity_id: str  # UEI
    name: str
    dba_name: str
    cage_code: str
    address: str
    city: str
    state: str
    zip_code: str
    registration_date: str
    status: str
    business_types: list[str]


@dataclass
class Relationship:
    """Relationship between entities."""
    source_entity_id: str
    target_entity_id: str
    target_name: str
    relationship_type: str
    confidence: float
    evidence: str


@dataclass
class RiskFactor:
    """Individual risk factor with scoring."""
    name: str
    category: str  # ENTITY | AWARD | PERFORMANCE | RELATIONSHIP
    score: int  # 0-25
    max_score: int
    severity: str  # LOW | MEDIUM | HIGH | CRITICAL
    description: str
    evidence: str


@dataclass
class RiskScore:
    """Comprehensive risk assessment."""
    entity_id: str
    entity_name: str
    total_score: int
    max_possible: int
    risk_level: str  # LOW | MEDIUM | HIGH | CRITICAL
    factors: list[RiskFactor]
    summary: str
    generated_at: str


@dataclass
class ContractPattern:
    """Statistical pattern in contract awards."""
    pattern_type: str
    description: str
    significance: str  # LOW | MEDIUM | HIGH
    data: dict
    anomaly_detected: bool


# ============================================================================
# Tool Implementations
# ============================================================================

class FedWatchTools:
    """
    Tool implementations for the FedWatch fraud investigation agent.

    These tools are designed to be called by an LLM agent, returning
    structured data that can be reasoned over.
    """

    def __init__(self):
        self.usaspending = USASpendingClient()
        self.sam = SAMGovClient()
        self.sec = SECEdgarClient()
        self.local = LocalDataStore()  # Local bulk data fallback

    async def search_entities(
        self,
        query: str,
        search_type: SearchType = SearchType.NAME,
        limit: int = 10
    ) -> list[EntitySummary]:
        """
        Search for contractor entities by name, UEI, DUNS, or CAGE code.

        Args:
            query: Search string
            search_type: Type of search (NAME, UEI, DUNS, CAGE)
            limit: Maximum results to return

        Returns:
            List of matching entities
        """
        kwargs = {"size": limit}

        if search_type == SearchType.NAME:
            kwargs["legal_name"] = query
        elif search_type == SearchType.UEI:
            kwargs["uei"] = query
        elif search_type == SearchType.CAGE:
            kwargs["cage_code"] = query
        # DUNS is deprecated, search by name as fallback
        elif search_type == SearchType.DUNS:
            kwargs["legal_name"] = query

        result = await self.sam.search_entities(**kwargs)

        return [
            EntitySummary(
                entity_id=e.uei,
                name=e.legal_name,
                dba_name=e.dba_name,
                cage_code=e.cage_code,
                address=e.physical_address,
                city=e.physical_city,
                state=e.physical_state,
                zip_code=e.physical_zip,
                registration_date=e.registration_date,
                status="Active" if e.expiration_date > datetime.now().strftime("%Y-%m-%d") else "Expired",
                business_types=e.business_types
            )
            for e in result.entities[:limit]
        ]

    async def get_entity_details(self, entity_id: str) -> Optional[dict]:
        """
        Get full details for a specific entity including registration,
        classifications, and basic risk factors.
        Uses local bulk data (no API calls).

        Args:
            entity_id: UEI or internal entity ID

        Returns:
            Complete entity details or None if not found
        """
        # Use local data first (no API calls)
        entity = self.local.get_entity_by_uei(entity_id)
        if not entity:
            return None

        # Check for exclusions (also local)
        exclusion_result = self.local.check_exclusion(uei=entity_id)

        # Calculate registration age
        reg_age_days = None
        if entity.get("registration_date"):
            try:
                reg_date = datetime.strptime(entity["registration_date"], "%Y%m%d")
                reg_age_days = (datetime.now() - reg_date).days
            except ValueError:
                pass

        # Check for virtual office indicators
        address = entity.get("address", "")
        virtual_office_flags = [
            ind for ind in VIRTUAL_OFFICE_INDICATORS
            if ind.lower() in address.lower()
        ]

        return {
            "entity": entity,
            "exclusions": exclusion_result.get("exclusions", []),
            "registration_age_days": reg_age_days,
            "virtual_office_indicators": virtual_office_flags,
            "source": "Local bulk data",
            "quick_flags": {
                "is_excluded": exclusion_result.get("is_excluded", False),
                "recent_registration": reg_age_days and reg_age_days < 365,
                "possible_virtual_office": len(virtual_office_flags) > 0
            }
        }

    async def get_entity_contracts(
        self,
        entity_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_value: Optional[float] = None,
        agency_code: Optional[str] = None,
        recipient_name: Optional[str] = None
    ) -> dict:
        """
        Get all federal contracts for an entity.

        Args:
            entity_id: UEI
            start_date: Filter contracts after this date (YYYY-MM-DD)
            end_date: Filter contracts before this date (YYYY-MM-DD)
            min_value: Minimum contract value
            agency_code: Filter by agency
            recipient_name: Optional entity name (skips SAM.gov lookup if provided)

        Returns:
            Contract summary with list of contracts
        """
        # Get entity name for search (use local data, no API calls)
        if not recipient_name:
            entity = self.local.get_entity_by_uei(entity_id)
            recipient_name = entity["legal_name"] if entity else entity_id

        result = await self.usaspending.search_contracts(
            recipient_name=recipient_name,
            start_date=start_date,
            end_date=end_date,
            min_value=min_value,
            agency=agency_code,
            limit=100
        )

        total_value = sum(c.total_obligation for c in result.contracts)
        agencies = list(set(c.agency for c in result.contracts if c.agency))

        return {
            "entity_id": entity_id,
            "entity_name": recipient_name,
            "total_contracts": result.total_count,
            "total_value": total_value,
            "agencies": agencies,
            "contracts": [
                {
                    "contract_id": c.contract_id,
                    "agency": c.agency,
                    "value": c.total_obligation,
                    "description": c.description[:200] if c.description else "",
                    "start_date": c.start_date,
                    "end_date": c.end_date,
                    "competition_type": c.competition_type,
                    "number_of_offers": c.number_of_offers
                }
                for c in result.contracts
            ]
        }

    async def get_entity_relationships(
        self,
        entity_id: str,
        relationship_types: Optional[list[RelationshipType]] = None
    ) -> list[Relationship]:
        """
        Get known relationships for an entity.
        Uses local bulk data (no API calls).

        Args:
            entity_id: UEI
            relationship_types: Filter by relationship type

        Returns:
            List of relationships
        """
        relationships = []
        entity = self.local.get_entity_by_uei(entity_id)

        if not entity:
            return relationships

        # Check for shared address relationships using local data
        if not relationship_types or RelationshipType.SHARED_ADDRESS in relationship_types:
            # Search for entities at the same address
            address = entity.get("address", "")
            city = entity.get("city", "")
            state = entity.get("state", "")

            if address and state:
                # Search local data for entities in the same state with matching address
                same_state = self.local.search_entities(state=state, limit=500)
                for other in same_state:
                    if other["uei"] != entity_id and other.get("address", "").lower() == address.lower():
                        relationships.append(Relationship(
                            source_entity_id=entity_id,
                            target_entity_id=other["uei"],
                            target_name=other["legal_name"],
                            relationship_type="SHARED_ADDRESS",
                            confidence=1.0,
                            evidence=f"Both registered at {address}, {city}, {state}"
                        ))

        # Note: Parent/Subsidiary and Shared Executive relationships would require
        # additional data sources (SEC filings, state records) not yet implemented

        return relationships

    async def search_by_address(
        self,
        address: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None
    ) -> list[EntitySummary]:
        """
        Find all entities registered at a specific address.
        Uses local bulk data (no API calls).

        Args:
            address: Full or partial address
            city: City (optional)
            state: State code (optional)
            zip_code: ZIP code (optional)

        Returns:
            List of entities at the address
        """
        if not state:
            return []

        # Use local data
        results = self.local.search_entities(state=state, limit=1000)

        matches = []
        address_lower = address.lower()

        for entity in results:
            if address_lower in entity.get("address", "").lower():
                if city and city.lower() != entity.get("city", "").lower():
                    continue
                if zip_code and zip_code != entity.get("zip", ""):
                    continue

                matches.append(EntitySummary(
                    entity_id=entity["uei"],
                    name=entity["legal_name"],
                    dba_name=entity.get("dba_name", ""),
                    cage_code=entity.get("cage_code", ""),
                    address=entity.get("address", ""),
                    city=entity.get("city", ""),
                    state=entity.get("state", ""),
                    zip_code=entity.get("zip", ""),
                    registration_date=entity.get("registration_date", ""),
                    status="Active" if entity.get("registration_status") == "A" else "Inactive",
                    business_types=[]
                ))

        return matches

    async def get_exclusions(
        self,
        entity_id: str,
        entity_name: Optional[str] = None,
        include_principals: bool = True
    ) -> dict:
        """
        Check for debarments, suspensions, and exclusions.
        Uses local bulk data first (faster, no rate limits), API as backup.

        Args:
            entity_id: UEI
            entity_name: Optional entity name for local data lookup
            include_principals: Also check executives

        Returns:
            Exclusion status and details
        """
        # Use local bulk data first (faster, no rate limits)
        local_result = self.local.check_exclusion(uei=entity_id, name=entity_name)
        if local_result["is_excluded"]:
            return {
                "entity_id": entity_id,
                "is_excluded": True,
                "exclusion_count": local_result["count"],
                "source": "Local bulk data",
                "exclusions": [
                    {
                        "name": e.get("Name", "") or f"{e.get('First', '')} {e.get('Last', '')}",
                        "type": e.get("Exclusion Type", ""),
                        "program": e.get("Exclusion Program", ""),
                        "agency": e.get("Excluding Agency", ""),
                        "active_date": e.get("Active Date", ""),
                        "termination_date": e.get("Termination Date", ""),
                        "description": e.get("Additional Comments", "")
                    }
                    for e in local_result["exclusions"]
                ]
            }

        # Local data says not excluded - that's our answer
        # (Skip API call since it's rate limited and local data is comprehensive)
        return {
            "entity_id": entity_id,
            "is_excluded": False,
            "exclusion_count": 0,
            "source": "Local bulk data",
            "exclusions": []
        }

    async def analyze_contract_patterns(
        self,
        entity_id: str,
        analysis_types: Optional[list[AnalysisType]] = None,
        recipient_name: Optional[str] = None
    ) -> list[ContractPattern]:
        """
        Run statistical analysis on contract award patterns.

        Args:
            entity_id: UEI
            analysis_types: Types of analysis to run
            recipient_name: Optional entity name (avoids SAM.gov lookup)

        Returns:
            List of pattern analyses
        """
        if analysis_types is None:
            analysis_types = list(AnalysisType)

        # Get contracts for analysis
        contracts_data = await self.get_entity_contracts(entity_id, recipient_name=recipient_name)
        contracts = contracts_data.get("contracts", [])

        if not contracts:
            return []

        patterns = []

        # Threshold Clustering Analysis
        if AnalysisType.THRESHOLD_CLUSTERING in analysis_types:
            thresholds = [250000, 750000, 1000000]  # Common simplified acquisition thresholds

            for threshold in thresholds:
                # Count contracts just below threshold (within 5%)
                lower_bound = threshold * 0.95
                near_threshold = [
                    c for c in contracts
                    if lower_bound <= c["value"] < threshold
                ]

                if len(near_threshold) >= 3:
                    patterns.append(ContractPattern(
                        pattern_type="THRESHOLD_CLUSTERING",
                        description=f"{len(near_threshold)} contracts clustered just below ${threshold:,} threshold",
                        significance="HIGH" if len(near_threshold) >= 5 else "MEDIUM",
                        data={
                            "threshold": threshold,
                            "count_near_threshold": len(near_threshold),
                            "contracts": [c["contract_id"] for c in near_threshold]
                        },
                        anomaly_detected=True
                    ))

        # Price Distribution Analysis
        if AnalysisType.PRICE_DISTRIBUTION in analysis_types:
            values = [c["value"] for c in contracts if c["value"] > 0]
            if values:
                avg_value = sum(values) / len(values)
                max_value = max(values)
                min_value = min(values)

                patterns.append(ContractPattern(
                    pattern_type="PRICE_DISTRIBUTION",
                    description=f"Contract values range from ${min_value:,.0f} to ${max_value:,.0f}",
                    significance="LOW",
                    data={
                        "min": min_value,
                        "max": max_value,
                        "average": avg_value,
                        "count": len(values)
                    },
                    anomaly_detected=False
                ))

        # Timing Analysis (fiscal year-end clustering)
        if AnalysisType.TIMING in analysis_types:
            # Count contracts in September (end of federal fiscal year)
            sept_contracts = [
                c for c in contracts
                if c.get("start_date") and c["start_date"][5:7] == "09"
            ]

            sept_ratio = len(sept_contracts) / len(contracts) if contracts else 0

            if sept_ratio > 0.25:  # More than 25% in September is suspicious
                patterns.append(ContractPattern(
                    pattern_type="TIMING",
                    description=f"{sept_ratio*100:.0f}% of contracts awarded in September (fiscal year-end)",
                    significance="MEDIUM" if sept_ratio > 0.35 else "LOW",
                    data={
                        "september_count": len(sept_contracts),
                        "total_count": len(contracts),
                        "september_ratio": sept_ratio
                    },
                    anomaly_detected=sept_ratio > 0.35
                ))

        # Competition Analysis
        if AnalysisType.COMPETITION in analysis_types:
            sole_source = [c for c in contracts if c.get("number_of_offers", 0) == 1]
            sole_source_ratio = len(sole_source) / len(contracts) if contracts else 0

            if sole_source_ratio > 0.5:
                patterns.append(ContractPattern(
                    pattern_type="COMPETITION",
                    description=f"{sole_source_ratio*100:.0f}% of contracts are sole-source (single offer)",
                    significance="HIGH" if sole_source_ratio > 0.7 else "MEDIUM",
                    data={
                        "sole_source_count": len(sole_source),
                        "total_count": len(contracts),
                        "sole_source_ratio": sole_source_ratio
                    },
                    anomaly_detected=True
                ))

        return patterns

    async def calculate_risk_score(
        self,
        entity_id: str,
        include_factors: bool = True,
        entity_name: Optional[str] = None
    ) -> RiskScore:
        """
        Calculate comprehensive risk score for an entity.

        Args:
            entity_id: UEI
            include_factors: Return detailed factor breakdown
            entity_name: Optional company name (used if SAM.gov unavailable)

        Returns:
            Risk score with factors
        """
        factors = []
        sam_available = False

        # Try to get entity details from SAM.gov
        details = await self.get_entity_details(entity_id)

        if details and details.get("entity"):
            sam_available = True
            entity = details["entity"]
            entity_name = entity.get("legal_name", entity_name or "Unknown")
        else:
            # SAM.gov unavailable - try to get name from contracts
            if not entity_name:
                contracts = await self.get_entity_contracts(entity_id)
                entity_name = contracts.get("entity_name", "Unknown")
            details = {"entity": {}, "exclusions": [], "virtual_office_indicators": []}

        # If we have a company name, check SEC EDGAR
        if entity_name and entity_name != "Unknown":
            try:
                sec_result = await self.sec.check_if_public_company(entity_name)
                if sec_result["is_public"]:
                    # Public company - generally lower risk (more transparency)
                    factors.append(RiskFactor(
                        name="Public Company (SEC Registered)",
                        category="ENTITY",
                        score=-10,  # Negative = reduces risk
                        max_score=0,
                        severity="LOW",
                        description=f"Publicly traded company with SEC filings",
                        evidence=f"Ticker: {sec_result['company'].get('ticker', 'N/A')}, CIK: {sec_result['company'].get('cik', 'N/A')}"
                    ))
                else:
                    # Not a public company - neutral, but note it
                    factors.append(RiskFactor(
                        name="Private Company",
                        category="ENTITY",
                        score=0,
                        max_score=0,
                        severity="LOW",
                        description="No SEC filings found - likely private company",
                        evidence="SEC EDGAR search returned no results"
                    ))
            except Exception as e:
                pass  # SEC check failed, continue without it

        entity = details.get("entity", {})

        # Factor 1: Registration Age
        reg_age = details.get("registration_age_days")
        if reg_age is not None:
            if reg_age < 90:
                factors.append(RiskFactor(
                    name="Very Recent Registration",
                    category="ENTITY",
                    score=20,
                    max_score=20,
                    severity="HIGH",
                    description=f"Registered only {reg_age} days ago",
                    evidence=f"Registration date: {entity.get('registration_date')}"
                ))
            elif reg_age < 365:
                factors.append(RiskFactor(
                    name="Recent Registration",
                    category="ENTITY",
                    score=10,
                    max_score=20,
                    severity="MEDIUM",
                    description=f"Registered {reg_age} days ago",
                    evidence=f"Registration date: {entity.get('registration_date')}"
                ))

        # Factor 2: Virtual Office
        if details.get("virtual_office_indicators"):
            factors.append(RiskFactor(
                name="Virtual Office Address",
                category="ENTITY",
                score=15,
                max_score=15,
                severity="HIGH",
                description="Address appears to be a virtual office or mailbox",
                evidence=f"Indicators found: {', '.join(details['virtual_office_indicators'])}"
            ))

        # Factor 3: Exclusions
        if details.get("exclusions"):
            factors.append(RiskFactor(
                name="Active Exclusions",
                category="ENTITY",
                score=25,
                max_score=25,
                severity="CRITICAL",
                description=f"{len(details['exclusions'])} active exclusion(s) found",
                evidence="Entity is debarred or suspended from federal contracting"
            ))

        # Factor 4: Contract Patterns
        try:
            patterns = await self.analyze_contract_patterns(entity_id)
            for pattern in patterns:
                if pattern.anomaly_detected:
                    severity = pattern.significance
                    score = {"HIGH": 15, "MEDIUM": 10, "LOW": 5}.get(severity, 5)
                    factors.append(RiskFactor(
                        name=f"Anomaly: {pattern.pattern_type}",
                        category="AWARD",
                        score=score,
                        max_score=15,
                        severity=severity,
                        description=pattern.description,
                        evidence=json.dumps(pattern.data)
                    ))
        except Exception:
            pass  # Skip pattern analysis if it fails

        # Factor 5: Shared Address
        try:
            relationships = await self.get_entity_relationships(entity_id, [RelationshipType.SHARED_ADDRESS])
            if len(relationships) >= 3:
                factors.append(RiskFactor(
                    name="Shared Address Network",
                    category="RELATIONSHIP",
                    score=15,
                    max_score=15,
                    severity="HIGH",
                    description=f"Address shared with {len(relationships)} other contractors",
                    evidence=", ".join([r.target_name for r in relationships[:5]])
                ))
        except Exception:
            pass  # Skip relationship analysis if it fails

        # Calculate total score
        total_score = sum(f.score for f in factors)
        max_possible = 100

        # Determine risk level
        if total_score >= 60:
            risk_level = "CRITICAL"
        elif total_score >= 40:
            risk_level = "HIGH"
        elif total_score >= 20:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Generate summary
        high_factors = [f for f in factors if f.severity in ["HIGH", "CRITICAL"]]
        data_note = "" if sam_available else " (SAM.gov unavailable, using SEC/USASpending)"

        if high_factors:
            summary = f"Found {len(high_factors)} high-severity risk factors: {', '.join(f.name for f in high_factors)}{data_note}"
        elif factors:
            summary = f"Found {len(factors)} risk factors with no critical concerns{data_note}"
        else:
            summary = f"No significant risk factors identified{data_note}"

        return RiskScore(
            entity_id=entity_id,
            entity_name=entity_name,
            total_score=total_score,
            max_possible=max_possible,
            risk_level=risk_level,
            factors=factors if include_factors else [],
            summary=summary,
            generated_at=datetime.now().isoformat()
        )

    async def search_news(
        self,
        entity_name: str,
        days_back: int = 365
    ) -> dict:
        """
        Search news and media for entity mentions.

        Note: This returns search queries for the agent to execute via WebSearch.
        Full implementation would require a news API integration.

        Args:
            entity_name: Company name to search
            days_back: Days of news to search

        Returns:
            Search queries and instructions
        """
        queries = build_search_queries("company_news", company=entity_name)
        queries.extend(build_search_queries("company_fraud", company=entity_name))

        return {
            "entity_name": entity_name,
            "days_back": days_back,
            "suggested_queries": queries,
            "instruction": "Use WebSearch tool with these queries to find news about the entity"
        }

    async def generate_report(
        self,
        entity_id: str,
        findings: dict,
        report_type: ReportType = ReportType.RISK_ASSESSMENT
    ) -> str:
        """
        Generate a formatted investigation report.

        Args:
            entity_id: Primary entity being investigated
            findings: Structured findings to include
            report_type: Type of report to generate

        Returns:
            Formatted markdown report
        """
        # Get entity details and risk score
        details = await self.get_entity_details(entity_id)
        risk_score = await self.calculate_risk_score(entity_id)
        contracts = await self.get_entity_contracts(entity_id)

        entity = details.get("entity", {}) if details else {}

        report = f"""# {report_type.value} REPORT

## Entity Summary

| Field | Value |
|-------|-------|
| **Name** | {entity.get('legal_name', 'Unknown')} |
| **UEI** | {entity_id} |
| **CAGE Code** | {entity.get('cage_code', 'N/A')} |
| **Address** | {entity.get('physical_address', 'N/A')}, {entity.get('physical_city', '')}, {entity.get('physical_state', '')} {entity.get('physical_zip', '')} |
| **Registration Date** | {entity.get('registration_date', 'N/A')} |
| **Business Types** | {', '.join(entity.get('business_types', [])[:3]) or 'N/A'} |

## Risk Assessment

**Risk Score: {risk_score.total_score} / {risk_score.max_possible}**

**Risk Level: {risk_score.risk_level}**

{risk_score.summary}

### Risk Factors

"""
        for factor in risk_score.factors:
            report += f"""#### {factor.name}
- **Severity:** {factor.severity}
- **Score:** {factor.score}/{factor.max_score}
- **Description:** {factor.description}
- **Evidence:** {factor.evidence}

"""

        report += f"""## Contract Summary

- **Total Contracts:** {contracts.get('total_contracts', 0)}
- **Total Value:** ${contracts.get('total_value', 0):,.0f}
- **Agencies:** {', '.join(contracts.get('agencies', [])[:5])}

### Recent Contracts

| Contract ID | Agency | Value | Date |
|-------------|--------|-------|------|
"""
        for c in contracts.get("contracts", [])[:10]:
            report += f"| {c['contract_id'][:20]} | {c['agency'][:20]} | ${c['value']:,.0f} | {c['start_date']} |\n"

        report += f"""

## Findings

{json.dumps(findings, indent=2) if findings else 'No additional findings provided.'}

## Recommendations

"""
        if risk_score.risk_level == "CRITICAL":
            report += "- **IMMEDIATE ACTION REQUIRED:** Refer to Inspector General for investigation\n"
            report += "- Suspend any pending contract actions\n"
            report += "- Conduct full due diligence review\n"
        elif risk_score.risk_level == "HIGH":
            report += "- Conduct enhanced due diligence before any new awards\n"
            report += "- Verify address and business legitimacy\n"
            report += "- Review past performance reports\n"
        elif risk_score.risk_level == "MEDIUM":
            report += "- Standard due diligence recommended\n"
            report += "- Monitor for pattern changes\n"
        else:
            report += "- No special action required\n"
            report += "- Continue standard monitoring\n"

        report += f"""
---
*Report generated: {datetime.now().isoformat()}*
*FERRET - Federal Expenditure Review and Risk Evaluation Tool*
"""

        return report

    async def close(self):
        """Close all API clients."""
        await self.usaspending.close()
        await self.sam.close()
        await self.sec.close()


# ============================================================================
# Tool Registry for Agent
# ============================================================================

TOOL_DEFINITIONS = [
    {
        "name": "search_entities",
        "description": "Search for contractor entities by name, UEI, DUNS, or CAGE code",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search string (name, UEI, DUNS, or CAGE)"},
                "search_type": {"type": "string", "enum": ["NAME", "UEI", "DUNS", "CAGE"], "default": "NAME"},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results to return"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_entity_details",
        "description": "Get full details for a specific entity including registration, classifications, and risk factors",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "UEI or internal entity ID"}
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "get_entity_contracts",
        "description": "Get all federal contracts for an entity",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "UEI"},
                "start_date": {"type": "string", "description": "Filter contracts after this date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "Filter contracts before this date (YYYY-MM-DD)"},
                "min_value": {"type": "number", "description": "Minimum contract value"},
                "agency_code": {"type": "string", "description": "Filter by awarding agency"}
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "get_entity_relationships",
        "description": "Get known relationships for an entity (shared addresses, executives, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "UEI"},
                "relationship_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["PARENT", "SUBSIDIARY", "SHARED_ADDRESS", "SHARED_AGENT", "SHARED_EXECUTIVE"]},
                    "description": "Filter by relationship type"
                }
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "search_by_address",
        "description": "Find all entities registered at a specific address",
        "parameters": {
            "type": "object",
            "properties": {
                "address": {"type": "string", "description": "Full or partial address"},
                "city": {"type": "string", "description": "City"},
                "state": {"type": "string", "description": "State code"},
                "zip": {"type": "string", "description": "ZIP code"}
            },
            "required": ["address"]
        }
    },
    {
        "name": "get_exclusions",
        "description": "Check for debarments, suspensions, and exclusions",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "UEI"},
                "include_principals": {"type": "boolean", "default": True}
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "analyze_contract_patterns",
        "description": "Run statistical analysis on contract award patterns (pricing, timing, thresholds, competition)",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "UEI"},
                "analysis_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["PRICE_DISTRIBUTION", "TIMING", "THRESHOLD_CLUSTERING", "COMPETITION", "MODIFICATIONS"]}
                }
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "calculate_risk_score",
        "description": "Calculate comprehensive risk score for an entity (0-100 with factor breakdown)",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "UEI"},
                "include_factors": {"type": "boolean", "default": True}
            },
            "required": ["entity_id"]
        }
    },
    {
        "name": "search_news",
        "description": "Get search queries for news and media mentions of an entity",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {"type": "string", "description": "Company name"},
                "days_back": {"type": "integer", "default": 365}
            },
            "required": ["entity_name"]
        }
    },
    {
        "name": "generate_report",
        "description": "Generate a formatted investigation report",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "Primary entity UEI"},
                "findings": {"type": "object", "description": "Structured findings to include"},
                "report_type": {"type": "string", "enum": ["RISK_ASSESSMENT", "INVESTIGATION", "DUE_DILIGENCE", "ANOMALY"], "default": "RISK_ASSESSMENT"}
            },
            "required": ["entity_id"]
        }
    }
]


# Example usage
async def demo():
    tools = FedWatchTools()

    # Search for an entity
    entities = await tools.search_entities("Lockheed", SearchType.NAME, limit=5)
    print(f"Found {len(entities)} entities")

    if entities:
        # Get risk score for first entity
        entity_id = entities[0].entity_id
        risk = await tools.calculate_risk_score(entity_id)
        print(f"\nRisk Score for {risk.entity_name}: {risk.total_score}/100 ({risk.risk_level})")

        # Analyze patterns
        patterns = await tools.analyze_contract_patterns(entity_id)
        print(f"\nFound {len(patterns)} contract patterns")
        for p in patterns:
            print(f"  - {p.pattern_type}: {p.description}")

    await tools.close()


if __name__ == "__main__":
    asyncio.run(demo())
