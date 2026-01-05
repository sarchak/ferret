"""
Daily Contract Fraud Scanner - AI-Native Autonomous Investigation

Fetches contracts awarded in the last N days from USASpending.gov,
runs them through fraud detection patterns, and AUTOMATICALLY INVESTIGATES
any HIGH or CRITICAL risk contracts using web research.

This is an AI-native agent that autonomously:
- Detects suspicious patterns
- Researches contractors via web search
- Verifies company legitimacy
- Generates investigation reports with evidence

Detection Categories:
1. Exclusion Match - Debarred/suspended contractors receiving awards
2. Pricing Anomalies - Statistical outliers in contract prices
3. Contract Splitting - Threshold avoidance patterns
4. Shell Company Networks - Related entities at same address
5. Set-Aside Fraud - False certification, excessive subcontracting
6. Bid Rigging Indicators - Collusion patterns
7. Performance Red Flags - Cost growth, timing anomalies

Usage:
    # Full autonomous scan with auto-investigation of HIGH/CRITICAL alerts
    uv run python daily_scan.py --days 3

    # Quick scan without auto-investigation (just flagging)
    uv run python daily_scan.py --days 3 --no-investigate

    # Scan specific agency
    uv run python daily_scan.py --agency "Department of Defense" --days 3

    # Save investigation reports
    uv run python daily_scan.py --days 3 --output reports/
"""

import asyncio
import argparse
import json
import csv
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional
from collections import defaultdict

from data_sources import USASpendingClient, Contract
from data_sources.bulk_data import LocalDataStore
from tools import FedWatchTools
from fraud_patterns import FRAUD_PATTERNS, Precision
from detectors.comprehensive_detector import ComprehensiveFraudDetector, FraudIndicator
from console import (
    logger, print_scan_header, print_scan_results, print_investigation_start,
    print_footer, info, success, warning, error, loading, Theme, Colors
)


@dataclass
class FraudAlert:
    """A flagged contract with fraud indicators."""
    contract_id: str
    recipient_name: str
    recipient_uei: str
    award_date: str
    contract_value: float
    agency: str
    description: str
    risk_score: int
    risk_level: str
    fraud_patterns: list[str]
    flags: list[dict]
    exclusion_match: bool
    registration_age_days: Optional[int]
    virtual_office: bool
    shared_address_count: int
    recommendation: str
    # New fields for comprehensive analysis
    category_scores: dict = field(default_factory=dict)
    indicator_details: list[dict] = field(default_factory=list)


@dataclass
class InvestigationReport:
    """Complete investigation report for a flagged contract."""
    contract_id: str
    contractor_name: str
    contractor_uei: str
    contract_value: float
    agency: str
    risk_level: str
    risk_score: int
    flags: list[dict]

    # Investigation findings
    web_research_summary: str
    company_verified: bool
    news_findings: list[str]
    red_flags_confirmed: list[str]
    mitigating_factors: list[str]

    # Final assessment
    final_risk_level: str  # May differ from initial after investigation
    confidence: str  # LOW, MEDIUM, HIGH
    recommendation: str
    evidence_urls: list[str]
    investigated_at: str


class DailyFraudScanner:
    """
    AI-Native Autonomous Fraud Scanner.

    This agent autonomously:
    1. Fetches recent contract awards
    2. Runs fraud pattern detection
    3. AUTOMATICALLY INVESTIGATES HIGH/CRITICAL alerts via web research
    4. Generates evidence-based investigation reports

    Detection hierarchy:
    1. CRITICAL: Excluded entity receiving contracts (UEI-based match)
    2. HIGH: Rapid registration + large award, threshold splitting, shell networks
    3. MEDIUM: Competition anomalies, timing patterns
    4. LOW: Virtual office, no web presence (require corroboration)
    """

    def __init__(self, verbose: bool = False, deep_analysis: bool = False, auto_investigate: bool = True):
        self.usaspending = USASpendingClient()
        self.local_data = LocalDataStore()
        self.tools = FedWatchTools()
        self.comprehensive_detector = ComprehensiveFraudDetector()
        self.verbose = verbose
        self.deep_analysis = deep_analysis
        self.auto_investigate = auto_investigate

        # Cache for contractor analysis (avoid re-analyzing same contractor)
        self._contractor_cache: dict[str, dict] = {}

        # Cache for entity lookups and shared address counts
        self._entity_cache: dict[str, dict] = {}
        self._shared_address_cache: dict[str, int] = {}
        self._address_index: dict[str, list[str]] = {}  # address -> list of UEIs
        self._address_index_built = False

        # Store investigation reports
        self.investigation_reports: list[InvestigationReport] = []

    async def fetch_contracts(
        self,
        days: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_value: float = 25000,
        agency: Optional[str] = None,
        limit: int = 1000
    ) -> list[Contract]:
        """
        Fetch contracts awarded in a given time frame.

        Args:
            days: Number of days to look back (alternative to start/end dates)
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            min_value: Minimum contract value
            agency: Filter by agency name
            limit: Maximum contracts to fetch (default 1000)
        """
        # Determine date range
        if start_date and end_date:
            pass  # Use provided dates
        elif days:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        else:
            # Default to last 1 day
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        if self.verbose:
            logger.metric("Date Range", f"{start_date} to {end_date}")
            logger.metric("Minimum Value", f"${min_value:,.0f}")
            if agency:
                logger.metric("Agency Filter", agency)
            logger.metric("Max Contracts", str(limit))

        # Fetch in batches (API limit is 100 per page)
        all_contracts = []
        page = 1
        max_pages = (limit + 99) // 100  # Ceiling division

        while True:
            logger.progress(len(all_contracts), limit, "Fetching contracts")

            result = await self.usaspending.search_contracts(
                start_date=start_date,
                end_date=end_date,
                min_value=min_value,
                agency=agency,
                page=page,
                limit=100
            )

            all_contracts.extend(result.contracts)

            if not result.has_next or len(all_contracts) >= limit:
                break
            page += 1

        # Trim to limit if we fetched more
        all_contracts = all_contracts[:limit]

        success(f"Fetched {len(all_contracts)} contracts from {page} page(s)")

        return all_contracts

    def check_exclusion(self, uei: str) -> dict:
        """Check if contractor UEI is on exclusion list."""
        return self.local_data.check_exclusion(uei=uei)

    def check_registration_age(self, uei: str) -> Optional[int]:
        """Get registration age in days from local SAM data."""
        entity = self._get_entity_cached(uei)
        if not entity:
            return None

        reg_date_str = entity.get("registration_date")
        if not reg_date_str:
            return None

        try:
            # SAM bulk data uses YYYYMMDD format
            reg_date = datetime.strptime(reg_date_str, "%Y%m%d")
            return (datetime.now() - reg_date).days
        except ValueError:
            return None

    def check_virtual_office(self, uei: str) -> tuple[bool, list[str]]:
        """Check for virtual office address indicators."""
        entity = self._get_entity_cached(uei)
        if not entity:
            return False, []

        address = entity.get("address", "").upper()

        indicators = [
            "SUITE", "STE ", "STE.", "#", "UNIT", "PMB", "P.O. BOX", "PO BOX",
            "REGUS", "WEWORK", "SPACES", "EXECUTIVE SUITE", "VIRTUAL"
        ]

        found = [ind for ind in indicators if ind in address]
        return len(found) > 0, found

    def _get_entity_cached(self, uei: str) -> dict:
        """Get entity with caching."""
        if uei not in self._entity_cache:
            self._entity_cache[uei] = self.local_data.get_entity_by_uei(uei) or {}
        return self._entity_cache[uei]

    def _build_address_index(self, contracts: list[Contract]) -> None:
        """Build address index for fast shared-address lookups."""
        if self._address_index_built:
            return

        # Get unique UEIs from contracts
        ueis = list(set(c.recipient_uei for c in contracts if c.recipient_uei))
        total = len(ueis)

        # Build index: address -> list of UEIs at that address
        for i, uei in enumerate(ueis):
            if (i + 1) % 50 == 0:
                logger.progress(i + 1, total, "Indexing addresses")

            entity = self._get_entity_cached(uei)
            if entity:
                address = entity.get("address", "")
                if address:
                    addr_key = address.lower().strip()
                    if addr_key not in self._address_index:
                        self._address_index[addr_key] = []
                    self._address_index[addr_key].append(uei)

        # Count shared addresses
        shared_count = sum(1 for addrs in self._address_index.values() if len(addrs) > 1)
        success(f"Indexed {total} contractors, {shared_count} shared addresses found")

        self._address_index_built = True

    def check_shared_address(self, uei: str) -> int:
        """Count other contractors at same address (with caching)."""
        # Check cache first
        if uei in self._shared_address_cache:
            return self._shared_address_cache[uei]

        entity = self._get_entity_cached(uei)
        if not entity:
            self._shared_address_cache[uei] = 0
            return 0

        address = entity.get("address", "")
        if not address:
            self._shared_address_cache[uei] = 0
            return 0

        # Normalize address for comparison
        addr_key = address.lower().strip()

        # Use address index if available
        if addr_key in self._address_index:
            count = len([u for u in self._address_index[addr_key] if u != uei])
        else:
            count = 0

        self._shared_address_cache[uei] = count
        return count

    async def analyze_contract(self, contract: Contract) -> Optional[FraudAlert]:
        """
        Analyze a single contract for fraud indicators.
        Returns FraudAlert if suspicious, None if clean.

        If deep_analysis is enabled, uses the comprehensive detector for
        additional pattern detection (pricing, splitting, set-aside, etc.)
        """
        flags = []
        fraud_patterns = []
        category_scores = {}
        indicator_details = []

        # Skip contracts without UEI (can't verify)
        if not contract.recipient_uei:
            return None

        uei = contract.recipient_uei

        # 1. CRITICAL: Check exclusion list (UEI-based only)
        exclusion = self.check_exclusion(uei)
        exclusion_match = exclusion.get("is_excluded", False)

        if exclusion_match:
            flags.append({
                "severity": "CRITICAL",
                "pattern": "EXCLUDED_ACTIVE_CONTRACT",
                "description": "Contractor is on SAM.gov exclusion list",
                "evidence": f"Found {exclusion.get('count', 0)} exclusion record(s)"
            })
            fraud_patterns.append("EXCLUDED_ACTIVE_CONTRACT")

        # 2. HIGH: Check registration age (shell company indicator)
        reg_age = self.check_registration_age(uei)

        if reg_age is not None and reg_age < 90 and contract.total_obligation >= 1_000_000:
            flags.append({
                "severity": "HIGH",
                "pattern": "RAPID_REGISTRATION_LARGE_AWARD",
                "description": f"Entity registered only {reg_age} days ago, received ${contract.total_obligation:,.0f} contract",
                "evidence": f"Registration age: {reg_age} days"
            })
            fraud_patterns.append("RAPID_REGISTRATION_LARGE_AWARD")
        elif reg_age is not None and reg_age < 180 and contract.total_obligation >= 500_000:
            flags.append({
                "severity": "MEDIUM",
                "pattern": "RAPID_REGISTRATION_LARGE_AWARD",
                "description": f"Entity registered {reg_age} days ago, received large contract",
                "evidence": f"Registration age: {reg_age} days, value: ${contract.total_obligation:,.0f}"
            })

        # 3. Check virtual office indicators
        is_virtual, virtual_indicators = self.check_virtual_office(uei)

        if is_virtual:
            flags.append({
                "severity": "LOW",
                "pattern": "VIRTUAL_OFFICE_INDICATORS",
                "description": "Address appears to be a virtual office",
                "evidence": f"Indicators found: {', '.join(virtual_indicators)}"
            })

        # 4. Check shared address (shell company network indicator)
        shared_count = self.check_shared_address(uei)

        if shared_count >= 5:
            flags.append({
                "severity": "HIGH",
                "pattern": "ADDRESS_CLUSTER_CONTRACTS",
                "description": f"Address shared with {shared_count} other contractors",
                "evidence": f"Potential shell company network"
            })
            fraud_patterns.append("ADDRESS_CLUSTER_CONTRACTS")
        elif shared_count >= 3:
            flags.append({
                "severity": "MEDIUM",
                "pattern": "ADDRESS_CLUSTER_CONTRACTS",
                "description": f"Address shared with {shared_count} other contractors",
                "evidence": "Multiple entities at same address"
            })

        # 5. DEEP ANALYSIS: Run comprehensive fraud detection if enabled
        if self.deep_analysis:
            # Check cache first
            if uei not in self._contractor_cache:
                try:
                    # Get all contracts for this contractor
                    contractor_contracts = await self._get_contractor_contracts(uei, contract.recipient_name)

                    # Run comprehensive analysis
                    risk_profile = await self.comprehensive_detector.analyze_contractor(
                        uei=uei,
                        contracts=contractor_contracts,
                        include_network_analysis=True
                    )

                    self._contractor_cache[uei] = {
                        'risk_profile': risk_profile,
                        'contracts': contractor_contracts
                    }
                except Exception as e:
                    if self.verbose:
                        warning(f"Deep analysis failed for {uei}: {e}")
                    self._contractor_cache[uei] = None

            cached = self._contractor_cache.get(uei)
            if cached and cached.get('risk_profile'):
                risk_profile = cached['risk_profile']

                # Add comprehensive indicators to flags
                for indicator in risk_profile.indicators:
                    # Skip if we already have this pattern
                    if indicator.pattern_type in fraud_patterns:
                        continue

                    flags.append({
                        "severity": indicator.severity,
                        "pattern": indicator.pattern_type,
                        "description": indicator.description,
                        "evidence": json.dumps(indicator.evidence) if isinstance(indicator.evidence, dict) else str(indicator.evidence),
                        "recommendation": indicator.recommendation
                    })
                    fraud_patterns.append(indicator.pattern_type)

                    indicator_details.append({
                        "category": indicator.category,
                        "pattern": indicator.pattern_type,
                        "severity": indicator.severity,
                        "score": indicator.score,
                        "description": indicator.description,
                        "evidence": indicator.evidence
                    })

                # Store category scores
                category_scores = risk_profile.category_scores

        # Calculate risk score
        severity_scores = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 10, "LOW": 5}
        risk_score = sum(severity_scores.get(f["severity"], 0) for f in flags)

        # Cap at 100
        risk_score = min(risk_score, 100)

        # Determine risk level
        if risk_score >= 50 or exclusion_match:
            risk_level = "CRITICAL"
        elif risk_score >= 30:
            risk_level = "HIGH"
        elif risk_score >= 15:
            risk_level = "MEDIUM"
        elif risk_score > 0:
            risk_level = "LOW"
        else:
            return None  # No flags, skip

        # Generate recommendation based on highest severity
        if risk_level == "CRITICAL":
            recommendation = "IMMEDIATE: Refer to Inspector General for investigation. Suspend pending contract actions."
        elif risk_level == "HIGH":
            recommendation = "URGENT: Conduct enhanced due diligence. Verify contractor legitimacy before proceeding."
        elif risk_level == "MEDIUM":
            recommendation = "REVIEW: Perform additional verification. Check past performance and references."
        else:
            recommendation = "MONITOR: Note for ongoing observation. Combine with other signals."

        return FraudAlert(
            contract_id=contract.contract_id,
            recipient_name=contract.recipient_name,
            recipient_uei=uei,
            award_date=contract.start_date,
            contract_value=contract.total_obligation,
            agency=contract.agency,
            description=contract.description[:200] if contract.description else "",
            risk_score=risk_score,
            risk_level=risk_level,
            fraud_patterns=fraud_patterns,
            flags=flags,
            exclusion_match=exclusion_match,
            registration_age_days=reg_age,
            virtual_office=is_virtual,
            shared_address_count=shared_count,
            recommendation=recommendation,
            category_scores=category_scores,
            indicator_details=indicator_details
        )

    async def _get_contractor_contracts(self, uei: str, name: str) -> list[Contract]:
        """Fetch all contracts for a contractor (cached)."""
        try:
            result = await self.usaspending.search_contracts(
                recipient_name=name,
                limit=50
            )
            return result.contracts
        except Exception:
            return []

    async def investigate_contractor(self, alert: FraudAlert) -> InvestigationReport:
        """
        Autonomously investigate a flagged contractor using web research.

        This uses the Claude agent to:
        1. Search for the company online
        2. Look for news about fraud, lawsuits, scandals
        3. Verify the company exists and is legitimate
        4. Check for any public records issues
        """
        from claude_agent_sdk import query, ClaudeAgentOptions
        from pathlib import Path

        print_investigation_start(alert.contract_id, alert.recipient_name, alert.contract_value)

        # Build investigation prompt
        flags_summary = "\n".join([
            f"  - [{f['severity']}] {f['pattern']}: {f['description']}"
            for f in alert.flags
        ])

        prompt = f"""You are investigating a federal contractor flagged for potential fraud indicators.

## Contract Information
- Contract ID: {alert.contract_id}
- Contractor: {alert.recipient_name}
- UEI: {alert.recipient_uei}
- Value: ${alert.contract_value:,.0f}
- Agency: {alert.agency}
- Initial Risk Score: {alert.risk_score}/100 ({alert.risk_level})

## Flags Detected
{flags_summary}

## Your Investigation Tasks

Use WebSearch to research this contractor and determine if these flags indicate actual fraud:

1. **Verify Company Existence**
   - Search for "{alert.recipient_name}" company
   - Look for official website, LinkedIn page, physical presence
   - Check if they have real employees and operations

2. **Check for Red Flags**
   - Search for "{alert.recipient_name}" fraud OR lawsuit OR scandal
   - Look for any news about legal issues, debarment, investigations
   - Check if there are complaints or negative reviews

3. **Verify Legitimacy**
   - Does the company appear to be a real operating business?
   - Do they have a track record in this industry?
   - Are there signs this could be a shell company?

4. **Assess the Flags**
   - For each flag detected, determine if it's a false positive or concerning
   - Look for mitigating factors (e.g., virtual office is ok for consulting firms)

## Required Output Format

After your research, provide your findings in EXACTLY this format:

```
INVESTIGATION SUMMARY:
[2-3 sentence summary of what you found]

COMPANY VERIFIED: [YES/NO]
[Brief explanation]

NEWS FINDINGS:
- [List any relevant news articles or findings]
- [Use "None found" if no concerning news]

RED FLAGS CONFIRMED:
- [List which initial flags are confirmed as concerning after research]
- [Use "None" if all flags appear to be false positives]

MITIGATING FACTORS:
- [List any factors that reduce concern]
- [Use "None" if no mitigating factors found]

FINAL RISK ASSESSMENT: [LOW/MEDIUM/HIGH/CRITICAL]
CONFIDENCE: [LOW/MEDIUM/HIGH]

RECOMMENDATION:
[Specific recommendation based on findings]

EVIDENCE URLS:
- [List URLs of sources you found]
```
"""

        # Run the investigation using Claude agent with web search
        investigation_result = ""
        try:
            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    cwd=str(Path(__file__).parent),
                    allowed_tools=["WebSearch", "WebFetch"],
                    permission_mode="bypassPermissions",
                    max_turns=10
                )
            ):
                if hasattr(message, 'result'):
                    investigation_result = message.result
        except Exception as e:
            investigation_result = f"Investigation failed: {str(e)}"

        # Parse the investigation result
        report = self._parse_investigation_result(alert, investigation_result)
        self.investigation_reports.append(report)

        # Print summary using alert-style output
        level = report.final_risk_level
        if report.red_flags_confirmed:
            msg = f"Confirmed: {', '.join(report.red_flags_confirmed[:2])}"
        else:
            msg = report.web_research_summary[:80]
        logger.alert(level, msg, report.contract_id, report.contract_value)

        return report

    def _parse_investigation_result(self, alert: FraudAlert, result: str) -> InvestigationReport:
        """Parse the investigation result into a structured report."""
        import re

        # Default values
        web_summary = "Investigation completed"
        company_verified = False
        news_findings = []
        red_flags_confirmed = []
        mitigating_factors = []
        final_risk_level = alert.risk_level
        confidence = "MEDIUM"
        recommendation = alert.recommendation
        evidence_urls = []

        try:
            # Parse INVESTIGATION SUMMARY
            summary_match = re.search(r'INVESTIGATION SUMMARY:\s*\n(.+?)(?=\n\nCOMPANY|$)', result, re.DOTALL)
            if summary_match:
                web_summary = summary_match.group(1).strip()

            # Parse COMPANY VERIFIED
            verified_match = re.search(r'COMPANY VERIFIED:\s*(YES|NO)', result, re.IGNORECASE)
            if verified_match:
                company_verified = verified_match.group(1).upper() == "YES"

            # Parse NEWS FINDINGS
            news_match = re.search(r'NEWS FINDINGS:\s*\n((?:- .+\n?)+)', result)
            if news_match:
                news_findings = [line.strip('- ').strip() for line in news_match.group(1).strip().split('\n') if line.strip() and 'none' not in line.lower()]

            # Parse RED FLAGS CONFIRMED
            flags_match = re.search(r'RED FLAGS CONFIRMED:\s*\n((?:- .+\n?)+)', result)
            if flags_match:
                red_flags_confirmed = [line.strip('- ').strip() for line in flags_match.group(1).strip().split('\n') if line.strip() and 'none' not in line.lower()]

            # Parse MITIGATING FACTORS
            mitigating_match = re.search(r'MITIGATING FACTORS:\s*\n((?:- .+\n?)+)', result)
            if mitigating_match:
                mitigating_factors = [line.strip('- ').strip() for line in mitigating_match.group(1).strip().split('\n') if line.strip() and 'none' not in line.lower()]

            # Parse FINAL RISK ASSESSMENT
            risk_match = re.search(r'FINAL RISK ASSESSMENT:\s*(LOW|MEDIUM|HIGH|CRITICAL)', result, re.IGNORECASE)
            if risk_match:
                final_risk_level = risk_match.group(1).upper()

            # Parse CONFIDENCE
            conf_match = re.search(r'CONFIDENCE:\s*(LOW|MEDIUM|HIGH)', result, re.IGNORECASE)
            if conf_match:
                confidence = conf_match.group(1).upper()

            # Parse RECOMMENDATION
            rec_match = re.search(r'RECOMMENDATION:\s*\n(.+?)(?=\n\nEVIDENCE|$)', result, re.DOTALL)
            if rec_match:
                recommendation = rec_match.group(1).strip()

            # Parse EVIDENCE URLS
            urls_match = re.search(r'EVIDENCE URLS:\s*\n((?:- .+\n?)+)', result)
            if urls_match:
                evidence_urls = [line.strip('- ').strip() for line in urls_match.group(1).strip().split('\n') if line.strip().startswith('http')]

        except Exception:
            pass  # Use defaults if parsing fails

        return InvestigationReport(
            contract_id=alert.contract_id,
            contractor_name=alert.recipient_name,
            contractor_uei=alert.recipient_uei,
            contract_value=alert.contract_value,
            agency=alert.agency,
            risk_level=alert.risk_level,
            risk_score=alert.risk_score,
            flags=alert.flags,
            web_research_summary=web_summary,
            company_verified=company_verified,
            news_findings=news_findings,
            red_flags_confirmed=red_flags_confirmed,
            mitigating_factors=mitigating_factors,
            final_risk_level=final_risk_level,
            confidence=confidence,
            recommendation=recommendation,
            evidence_urls=evidence_urls,
            investigated_at=datetime.now().isoformat()
        )

    async def scan(
        self,
        days: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_value: float = 25000,
        agency: Optional[str] = None,
        threshold: str = "LOW",
        limit: int = 1000
    ) -> tuple[list[FraudAlert], int]:
        """
        Scan contracts and return flagged alerts.

        Args:
            days: Number of days to look back (alternative to start/end dates)
            start_date: Start date YYYY-MM-DD (use with end_date)
            end_date: End date YYYY-MM-DD (use with start_date)
            min_value: Minimum contract value to check
            agency: Optional agency filter
            threshold: Minimum risk level to return (LOW, MEDIUM, HIGH, CRITICAL)
            limit: Maximum number of contracts to analyze

        Returns:
            Tuple of (List of FraudAlert objects sorted by risk score, total contracts scanned)
        """
        import sys

        logger.section("DATA LOADING")

        # Fetch contracts
        if start_date and end_date:
            loading(f"Fetching contracts from {start_date} to {end_date}...")
        else:
            days = days or 1
            loading(f"Fetching contracts from last {days} day(s)...")

        contracts = await self.fetch_contracts(
            days=days,
            start_date=start_date,
            end_date=end_date,
            min_value=min_value,
            agency=agency,
            limit=limit
        )
        total_scanned = len(contracts)

        if not contracts:
            return [], 0

        # Build address index for fast shared-address lookups
        loading("Building address index...")
        self._build_address_index(contracts)

        logger.section("ANALYSIS")
        if self.deep_analysis:
            info("Deep analysis mode enabled - comprehensive detection active")

        # Analyze contracts in parallel with concurrency limit
        threshold_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        threshold_idx = threshold_levels.index(threshold.upper())

        # Use semaphore to limit concurrent analysis (avoid overwhelming APIs)
        concurrency = 20 if not self.deep_analysis else 10
        semaphore = asyncio.Semaphore(concurrency)
        completed = [0]  # Use list for mutable counter in closure
        flagged = [0]

        async def analyze_with_progress(contract: Contract) -> Optional[FraudAlert]:
            async with semaphore:
                result = await self.analyze_contract(contract)
                completed[0] += 1
                if result:
                    flagged[0] += 1
                # Update progress every 10 or when flagged
                if completed[0] % 10 == 0 or result:
                    logger.progress(completed[0], total_scanned, "Analyzing contracts")
                return result

        info(f"Running {concurrency} parallel analyzers...")
        results = await asyncio.gather(*[analyze_with_progress(c) for c in contracts])

        # Filter results
        alerts = [
            r for r in results
            if r and threshold_levels.index(r.risk_level) >= threshold_idx
        ]

        # Show final analysis status
        print()  # Clear progress line
        success(f"Analyzed {total_scanned} contracts, flagged {len(alerts)}")

        # Sort by risk score (highest first)
        alerts.sort(key=lambda x: x.risk_score, reverse=True)

        # AUTO-INVESTIGATE HIGH/CRITICAL alerts
        if self.auto_investigate:
            high_critical = [a for a in alerts if a.risk_level in ["HIGH", "CRITICAL"]]
            if high_critical:
                logger.section("AUTONOMOUS INVESTIGATION")
                info(f"Investigating {len(high_critical)} HIGH/CRITICAL alerts...")

                for alert in high_critical:
                    await self.investigate_contractor(alert)

                success(f"Investigation complete. {len(self.investigation_reports)} reports generated.")

        return alerts, total_scanned

    async def close(self):
        """Cleanup resources."""
        await self.usaspending.close()
        await self.tools.close()
        await self.comprehensive_detector.close()


def format_console_report(
    alerts: list[FraudAlert],
    date_desc: str = "last 1 day(s)",
    deep_analysis: bool = False,
    total_scanned: int = 0,
    min_value: float = 0,
    investigation_reports: list[InvestigationReport] = None
) -> str:
    """Format alerts using Bloomberg-style console output."""
    import io
    import sys

    # Capture output to string
    old_stdout = sys.stdout
    sys.stdout = buffer = io.StringIO()

    try:
        # Summary by risk level
        critical = sum(1 for a in alerts if a.risk_level == "CRITICAL")
        high = sum(1 for a in alerts if a.risk_level == "HIGH")
        medium = sum(1 for a in alerts if a.risk_level == "MEDIUM")
        low = sum(1 for a in alerts if a.risk_level == "LOW")

        # Print scan results summary
        print_scan_results(total_scanned, len(alerts), critical, high, medium, low)

        if not alerts:
            success("No suspicious contracts detected.")
            print_footer()
            return buffer.getvalue()

        # Critical alerts
        if critical > 0:
            logger.section("CRITICAL ALERTS")
            for alert in alerts:
                if alert.risk_level == "CRITICAL":
                    logger.alert("CRITICAL", alert.fraud_patterns[0] if alert.fraud_patterns else "Multiple indicators",
                               alert.contract_id, alert.contract_value)
                    logger.metric("Recipient", alert.recipient_name)
                    logger.metric("UEI", alert.recipient_uei)
                    logger.metric("Risk Score", f"{alert.risk_score}/100", status="bad")
                    if alert.exclusion_match:
                        print(f"  {Colors.BG_RED}{Colors.BRIGHT_WHITE}  EXCLUSION MATCH: DEBARRED/SUSPENDED  {Colors.RESET}")
                    for flag in alert.flags:
                        print(f"  {Theme.ERROR}▸ [{flag['severity']}]{Colors.RESET} {flag['description']}")
                    print(f"  {Theme.ACCENT}⚡ {alert.recommendation}{Colors.RESET}")
                    logger.divider()

        # High alerts
        if high > 0:
            logger.section("HIGH RISK ALERTS")
            for alert in alerts:
                if alert.risk_level == "HIGH":
                    logger.alert("HIGH", alert.fraud_patterns[0] if alert.fraud_patterns else "Multiple indicators",
                               alert.contract_id, alert.contract_value)
                    print(f"    {Theme.LABEL}Recipient:{Colors.RESET} {alert.recipient_name}")
                    for flag in alert.flags[:3]:
                        print(f"    {Theme.WARNING}▸{Colors.RESET} {flag['description'][:60]}")
                    print()

        # Medium/Low summary table
        other = [a for a in alerts if a.risk_level in ["MEDIUM", "LOW"]]
        if other:
            logger.section(f"OTHER FLAGS ({len(other)} contracts)")
            logger.table_header(["LEVEL", "CONTRACT", "RECIPIENT", "VALUE"], [8, 22, 28, 14])
            for alert in other[:15]:
                logger.table_row(
                    [alert.risk_level, alert.contract_id[:20], alert.recipient_name[:26], f"${alert.contract_value:,.0f}"],
                    [8, 22, 28, 14],
                    highlight=(alert.risk_level == "MEDIUM")
                )
            if len(other) > 15:
                print(f"  {Colors.DIM}... and {len(other) - 15} more{Colors.RESET}")

        # Investigation Results
        if investigation_reports:
            logger.section("INVESTIGATION RESULTS")

            for report in investigation_reports:
                logger.divider("═")
                print(f"  {Theme.HEADER}{report.contract_id}{Colors.RESET} │ {Theme.VALUE}{report.contractor_name}{Colors.RESET}")
                print(f"  {Theme.DATA}${report.contract_value:,.0f}{Colors.RESET} │ {report.agency}")
                logger.divider()

                # Company verification
                verified_icon = "✓" if report.company_verified else "✗"
                verified_color = Theme.SUCCESS if report.company_verified else Theme.ERROR
                print(f"  {verified_color}{verified_icon} Company Verified{Colors.RESET}")

                # Red flags confirmed
                if report.red_flags_confirmed:
                    print(f"  {Theme.ERROR}Confirmed Issues:{Colors.RESET}")
                    for flag in report.red_flags_confirmed[:3]:
                        print(f"    {Theme.ERROR}▸{Colors.RESET} {flag[:65]}")

                # Mitigating factors
                if report.mitigating_factors:
                    print(f"  {Theme.SUCCESS}Mitigating Factors:{Colors.RESET}")
                    for factor in report.mitigating_factors[:2]:
                        print(f"    {Theme.SUCCESS}+{Colors.RESET} {factor[:65]}")

                # Final assessment
                level_colors = {
                    "CRITICAL": Colors.BG_RED + Colors.BRIGHT_WHITE,
                    "HIGH": Theme.ERROR,
                    "MEDIUM": Theme.WARNING,
                    "LOW": Theme.DATA
                }
                level_color = level_colors.get(report.final_risk_level, Theme.INFO)
                print(f"\n  {level_color}▐ FINAL: {report.final_risk_level} (Confidence: {report.confidence}){Colors.RESET}")
                print(f"  {Theme.ACCENT}⚡ {report.recommendation[:80]}{Colors.RESET}")
                print()

        print_footer()

    finally:
        sys.stdout = old_stdout

    return buffer.getvalue()


def save_json_report(alerts: list[FraudAlert], output_path: Path, total_scanned: int = 0):
    """Save alerts as JSON for downstream processing."""
    data = {
        "scan_timestamp": datetime.now().isoformat(),
        "total_contracts_scanned": total_scanned,
        "alert_count": len(alerts),
        "flag_rate": (len(alerts) / total_scanned * 100) if total_scanned else 0,
        "summary": {
            "critical": sum(1 for a in alerts if a.risk_level == "CRITICAL"),
            "high": sum(1 for a in alerts if a.risk_level == "HIGH"),
            "medium": sum(1 for a in alerts if a.risk_level == "MEDIUM"),
            "low": sum(1 for a in alerts if a.risk_level == "LOW")
        },
        "alerts": [asdict(a) for a in alerts]
    }

    output_path.write_text(json.dumps(data, indent=2))


def save_csv_report(alerts: list[FraudAlert], output_path: Path):
    """Save alerts as CSV for spreadsheet analysis."""
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            "risk_level", "risk_score", "contract_id", "recipient_name",
            "recipient_uei", "contract_value", "agency", "award_date",
            "exclusion_match", "registration_age_days", "virtual_office",
            "shared_address_count", "fraud_patterns", "recommendation"
        ])

        for a in alerts:
            writer.writerow([
                a.risk_level, a.risk_score, a.contract_id, a.recipient_name,
                a.recipient_uei, a.contract_value, a.agency, a.award_date,
                a.exclusion_match, a.registration_age_days, a.virtual_office,
                a.shared_address_count, "|".join(a.fraud_patterns), a.recommendation
            ])


async def main():
    parser = argparse.ArgumentParser(
        description="FERRET - Federal Expenditure Review and Risk Evaluation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic daily scan (last 1 day)
    python daily_scan.py

    # Scan last 7 days
    python daily_scan.py --days 7

    # Scan specific date range
    python daily_scan.py --start-date 2024-01-01 --end-date 2024-01-31

    # Scan Q4 FY2024 (Oct-Dec 2023)
    python daily_scan.py --start-date 2023-10-01 --end-date 2023-12-31 --limit 5000

    # Scan DOD contracts over $1M
    python daily_scan.py --days 30 --agency "Department of Defense" --min-value 1000000

    # Only show HIGH and CRITICAL alerts
    python daily_scan.py --threshold HIGH

    # Fetch up to 5000 contracts
    python daily_scan.py --days 30 --limit 5000

    # Output JSON for automated processing
    python daily_scan.py --format json --output /var/log/fraud-alerts/
        """
    )

    # Date range options
    parser.add_argument("--days", "-d", type=int, default=None,
                        help="Number of days to scan (default: 1, ignored if --start-date used)")
    parser.add_argument("--start-date", type=str, default=None,
                        help="Start date YYYY-MM-DD (use with --end-date)")
    parser.add_argument("--end-date", type=str, default=None,
                        help="End date YYYY-MM-DD (use with --start-date)")

    # Filter options
    parser.add_argument("--min-value", "-m", type=float, default=25000,
                        help="Minimum contract value to scan (default: 25000)")
    parser.add_argument("--agency", "-a", type=str, default=None,
                        help="Filter by awarding agency")
    parser.add_argument("--limit", "-l", type=int, default=1000,
                        help="Maximum contracts to fetch (default: 1000)")
    parser.add_argument("--threshold", "-t", type=str, default="LOW",
                        choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                        help="Minimum risk level to report (default: LOW)")
    parser.add_argument("--format", "-f", type=str, default="console",
                        choices=["console", "json", "csv"],
                        help="Output format (default: console)")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output directory for reports")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--deep", action="store_true",
                        help="Enable deep analysis (slower but more comprehensive)")
    parser.add_argument("--no-investigate", action="store_true",
                        help="Disable auto-investigation (just flag, don't research)")

    args = parser.parse_args()

    # Validate date arguments
    if (args.start_date and not args.end_date) or (args.end_date and not args.start_date):
        parser.error("--start-date and --end-date must be used together")

    # Default to 1 day if no date args provided
    if not args.start_date and args.days is None:
        args.days = 1

    # Show FERRET banner and scan configuration
    print_scan_header(
        days=args.days or 0,
        min_value=args.min_value,
        deep=args.deep
    )

    # Run scanner
    auto_investigate = not args.no_investigate
    scanner = DailyFraudScanner(
        verbose=args.verbose,
        deep_analysis=args.deep,
        auto_investigate=auto_investigate
    )

    try:
        alerts, total_scanned = await scanner.scan(
            days=args.days,
            start_date=args.start_date,
            end_date=args.end_date,
            min_value=args.min_value,
            agency=args.agency,
            threshold=args.threshold,
            limit=args.limit
        )

        # Build date description for report
        if args.start_date:
            date_desc = f"{args.start_date} to {args.end_date}"
        else:
            date_desc = f"last {args.days} day(s)"

        # Output results
        if args.format == "console":
            print(format_console_report(
                alerts,
                date_desc=date_desc,
                deep_analysis=args.deep,
                total_scanned=total_scanned,
                min_value=args.min_value,
                investigation_reports=scanner.investigation_reports
            ))

        elif args.format == "json":
            if args.output:
                output_dir = Path(args.output)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"fraud_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                save_json_report(alerts, output_file, total_scanned=total_scanned)
                print(f"Report saved to: {output_file}")
            else:
                print(json.dumps([asdict(a) for a in alerts], indent=2))

        elif args.format == "csv":
            if args.output:
                output_dir = Path(args.output)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"fraud_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                save_csv_report(alerts, output_file)
                print(f"Report saved to: {output_file}")
            else:
                # Print CSV to stdout
                import sys
                writer = csv.writer(sys.stdout)
                writer.writerow(["risk_level", "contract_id", "recipient", "value", "flags"])
                for a in alerts:
                    writer.writerow([a.risk_level, a.contract_id, a.recipient_name, a.contract_value, len(a.flags)])

        # Exit with code based on findings
        if any(a.risk_level == "CRITICAL" for a in alerts):
            exit(2)  # Critical findings
        elif any(a.risk_level == "HIGH" for a in alerts):
            exit(1)  # High risk findings
        else:
            exit(0)  # OK

    finally:
        await scanner.close()


if __name__ == "__main__":
    asyncio.run(main())
