"""
Comprehensive Fraud Detection Module

Orchestrates all fraud detection patterns from the modular detectors:
1. Pricing Anomalies - Statistical outliers, thresholds, splitting
2. Temporal Patterns - Weekend awards, fiscal year-end, timing
3. Competition Quality - Single offer, sole-source concentration
4. Entity Analysis - Registration, address, employee/revenue
5. Modification Patterns - Value growth, timing, change orders
6. Statistical Analysis - Benford's Law violations

Based on:
- GAO-24-105833: Federal government loses $233-521B annually to fraud
- DOJ Procurement Collusion Strike Force: 140+ investigations, 60+ convictions
- GSA OIG Red Flags: https://www.gsaig.gov/red-flags-fraud
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
import statistics

from data_sources import Contract, USASpendingClient
from data_sources.bulk_data import LocalDataStore

# Import modular detectors
from . import benford
from . import temporal
from . import pricing
from . import competition
from . import employee_revenue
from . import modifications
from . import registration
from . import address as address_detector


@dataclass
class FraudIndicator:
    """A single fraud indicator with evidence."""
    category: str  # PRICING, TEMPORAL, COMPETITION, ENTITY, MODIFICATION, STATISTICAL
    pattern_type: str  # Specific pattern detected
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    score: int  # Risk points (0-30)
    description: str
    evidence: dict
    recommendation: str


@dataclass
class ContractorRiskProfile:
    """Comprehensive risk profile for a contractor."""
    uei: str
    legal_name: str
    indicators: list[FraudIndicator]
    total_score: int
    risk_level: str  # NONE, LOW, MEDIUM, HIGH, CRITICAL
    category_scores: dict[str, int]
    summary: str
    analyzed_at: str


class ComprehensiveFraudDetector:
    """
    Comprehensive fraud detection engine that orchestrates all modular detectors.
    """

    def __init__(self):
        self.local_data = LocalDataStore()
        self.usaspending = USASpendingClient()

    def _convert_to_indicator(self, result: dict, category: str) -> FraudIndicator:
        """Convert a detector result dict to a FraudIndicator."""
        return FraudIndicator(
            category=category,
            pattern_type=result.get('pattern_type', 'UNKNOWN'),
            severity=result.get('severity', 'LOW'),
            score=result.get('score', 5),
            description=result.get('description', ''),
            evidence=result.get('evidence', {}),
            recommendation=result.get('recommendation', '')
        )

    # =========================================================================
    # Category 1: Pricing Analysis
    # =========================================================================

    async def detect_pricing_anomalies(
        self,
        contracts: list[Contract],
        contractor_uei: str
    ) -> list[FraudIndicator]:
        """
        Run all pricing-related detection.
        """
        indicators = []

        # Use modular pricing detector
        pricing_results = pricing.analyze_contractor_pricing(contracts, contractor_uei)
        for result in pricing_results:
            indicators.append(self._convert_to_indicator(result, 'PRICING'))

        # Price outlier detection for large contracts
        large_contracts = [c for c in contracts if c.total_obligation >= 100000 and c.recipient_uei == contractor_uei]
        if large_contracts:
            all_amounts = [c.total_obligation for c in contracts if c.total_obligation > 0]
            if len(all_amounts) >= 10:
                for contract in large_contracts[:3]:
                    result = pricing.detect_price_outlier(contract.total_obligation, all_amounts)
                    if result:
                        result['contract_id'] = contract.contract_id
                        indicators.append(self._convert_to_indicator(result, 'PRICING'))

        return indicators

    # =========================================================================
    # Category 2: Temporal Analysis
    # =========================================================================

    def detect_temporal_anomalies(
        self,
        contracts: list[Contract],
        contractor_uei: str
    ) -> list[FraudIndicator]:
        """
        Run all timing-related detection.
        """
        indicators = []

        # Use modular temporal detector
        timing_results = temporal.analyze_contractor_timing(contracts, contractor_uei)
        for result in timing_results:
            indicators.append(self._convert_to_indicator(result, 'TEMPORAL'))

        return indicators

    # =========================================================================
    # Category 3: Competition Analysis
    # =========================================================================

    def detect_competition_issues(
        self,
        contracts: list[Contract],
        contractor_uei: str
    ) -> list[FraudIndicator]:
        """
        Run all competition quality detection.
        """
        indicators = []

        # Use modular competition detector
        competition_results = competition.analyze_contractor_competition(contracts, contractor_uei)
        for result in competition_results:
            indicators.append(self._convert_to_indicator(result, 'COMPETITION'))

        return indicators

    # =========================================================================
    # Category 4: Entity Analysis (Registration, Address, Employee/Revenue)
    # =========================================================================

    def detect_entity_anomalies(
        self,
        entity: dict,
        contracts: list[Contract],
        all_entities: list[dict],
        contractor_uei: str
    ) -> list[FraudIndicator]:
        """
        Run all entity-related detection.
        """
        indicators = []

        # Registration analysis
        reg_results = registration.analyze_entity_registration(entity, contracts, contractor_uei)
        for result in reg_results:
            indicators.append(self._convert_to_indicator(result, 'ENTITY'))

        # Address analysis
        addr_results = address_detector.analyze_contractor_address(entity, all_entities, contracts)
        for result in addr_results:
            indicators.append(self._convert_to_indicator(result, 'ENTITY'))

        # Employee/revenue analysis
        emp_results = employee_revenue.analyze_employee_revenue_ratio(entity, contracts, contractor_uei)
        for result in emp_results:
            indicators.append(self._convert_to_indicator(result, 'ENTITY'))

        return indicators

    # =========================================================================
    # Category 5: Modification Analysis
    # =========================================================================

    def detect_modification_issues(
        self,
        contracts: list[Contract],
        contractor_uei: str
    ) -> list[FraudIndicator]:
        """
        Run all modification pattern detection.
        """
        indicators = []

        # Use modular modifications detector
        mod_results = modifications.analyze_contractor_modifications(contracts, contractor_uei)
        for result in mod_results:
            indicators.append(self._convert_to_indicator(result, 'MODIFICATION'))

        return indicators

    # =========================================================================
    # Category 6: Statistical Analysis (Benford's Law)
    # =========================================================================

    def detect_statistical_anomalies(
        self,
        contracts: list[Contract],
        contractor_uei: str
    ) -> list[FraudIndicator]:
        """
        Run Benford's Law and other statistical analysis.
        """
        indicators = []

        # Benford's Law analysis
        benford_result = benford.analyze_contractor_amounts(contracts, contractor_uei)
        if benford_result:
            indicators.append(self._convert_to_indicator(benford_result, 'STATISTICAL'))

        return indicators

    # =========================================================================
    # Category 7: Exclusion and Critical Checks
    # =========================================================================

    def detect_exclusions(self, uei: str, legal_name: str) -> list[FraudIndicator]:
        """
        Check for SAM.gov exclusions - critical priority.
        """
        indicators = []

        exclusion = self.local_data.check_exclusion(uei=uei)
        if exclusion.get('is_excluded'):
            indicators.append(FraudIndicator(
                category='EXCLUSION',
                pattern_type='EXCLUDED_ENTITY',
                severity='CRITICAL',
                score=30,
                description='Contractor is on SAM.gov exclusion list',
                evidence={
                    'exclusion_count': exclusion.get('count', 0),
                    'exclusions': exclusion.get('exclusions', [])[:3]
                },
                recommendation='STOP: Do not award contracts to excluded entities. FAR 9.405'
            ))

        # Also check by name
        exclusion_by_name = self.local_data.check_exclusion(name=legal_name)
        if exclusion_by_name.get('is_excluded') and not exclusion.get('is_excluded'):
            indicators.append(FraudIndicator(
                category='EXCLUSION',
                pattern_type='EXCLUDED_ENTITY_NAME_MATCH',
                severity='HIGH',
                score=25,
                description=f'Name "{legal_name}" matches excluded entity',
                evidence={
                    'exclusions': exclusion_by_name.get('exclusions', [])[:3]
                },
                recommendation='Verify identity - name matches excluded entity'
            ))

        return indicators

    # =========================================================================
    # Category 8: Shell Company Network Detection
    # =========================================================================

    def detect_shell_network(
        self,
        entity: dict,
        all_entities: list[dict],
        contracts: list[Contract]
    ) -> list[FraudIndicator]:
        """
        Detect shell company networks using address clustering.
        """
        indicators = []

        # Get shared address entities
        shared = address_detector.detect_shared_addresses(all_entities, min_shared=2)
        for result in shared:
            # Check if our entity is involved
            entity_uei = entity.get('uei', '')
            involved_ueis = [e['uei'] for e in result.get('evidence', {}).get('entities', [])]

            if entity_uei in involved_ueis:
                indicators.append(self._convert_to_indicator(result, 'SHELL_COMPANY'))

        return indicators

    # =========================================================================
    # Main Analysis Function
    # =========================================================================

    async def analyze_contractor(
        self,
        uei: str,
        contracts: Optional[list[Contract]] = None,
        include_network_analysis: bool = True,
        deep_analysis: bool = False
    ) -> ContractorRiskProfile:
        """
        Run comprehensive fraud analysis on a contractor.

        Args:
            uei: Unique Entity Identifier
            contracts: Pre-fetched contracts (optional)
            include_network_analysis: Whether to analyze entity network
            deep_analysis: Run additional deep checks (slower)

        Returns:
            Complete risk profile with all detected indicators
        """
        all_indicators = []

        # Get entity details from local data
        entity = self.local_data.get_entity_by_uei(uei)
        legal_name = entity.get('legal_name', 'Unknown') if entity else 'Unknown'

        # CRITICAL: Check exclusions first
        exclusion_indicators = self.detect_exclusions(uei, legal_name)
        all_indicators.extend(exclusion_indicators)

        # Get contracts if not provided
        if contracts is None:
            try:
                result = await self.usaspending.search_contracts(
                    recipient_name=legal_name,
                    limit=100 if deep_analysis else 50
                )
                contracts = result.contracts
            except Exception:
                contracts = []

        # Get all entities for network analysis
        all_entities = []
        if include_network_analysis and entity:
            state = entity.get('state', '')
            if state:
                all_entities = self.local_data.search_entities(state=state, limit=1000)

        # Run all detection categories
        if contracts:
            # 1. Pricing analysis
            pricing_indicators = await self.detect_pricing_anomalies(contracts, uei)
            all_indicators.extend(pricing_indicators)

            # 2. Temporal analysis
            temporal_indicators = self.detect_temporal_anomalies(contracts, uei)
            all_indicators.extend(temporal_indicators)

            # 3. Competition analysis
            competition_indicators = self.detect_competition_issues(contracts, uei)
            all_indicators.extend(competition_indicators)

            # 4. Modification analysis
            mod_indicators = self.detect_modification_issues(contracts, uei)
            all_indicators.extend(mod_indicators)

            # 5. Statistical analysis (Benford's Law)
            if deep_analysis or len([c for c in contracts if c.recipient_uei == uei]) >= 30:
                stat_indicators = self.detect_statistical_anomalies(contracts, uei)
                all_indicators.extend(stat_indicators)

        # Entity analysis
        if entity:
            entity_indicators = self.detect_entity_anomalies(
                entity, contracts or [], all_entities, uei
            )
            all_indicators.extend(entity_indicators)

            # Shell company network
            if include_network_analysis and all_entities:
                network_indicators = self.detect_shell_network(
                    entity, all_entities, contracts or []
                )
                all_indicators.extend(network_indicators)

        # Deduplicate indicators by pattern_type
        seen_patterns = set()
        unique_indicators = []
        for indicator in all_indicators:
            key = (indicator.category, indicator.pattern_type)
            if key not in seen_patterns:
                seen_patterns.add(key)
                unique_indicators.append(indicator)

        all_indicators = unique_indicators

        # Calculate scores
        total_score = min(100, sum(i.score for i in all_indicators))

        category_scores = defaultdict(int)
        for indicator in all_indicators:
            category_scores[indicator.category] += indicator.score

        # Determine risk level
        has_critical = any(i.severity == 'CRITICAL' for i in all_indicators)
        has_high = any(i.severity == 'HIGH' for i in all_indicators)

        if has_critical or total_score >= 50:
            risk_level = 'CRITICAL'
        elif total_score >= 35 or (has_high and total_score >= 25):
            risk_level = 'HIGH'
        elif total_score >= 20:
            risk_level = 'MEDIUM'
        elif total_score > 0:
            risk_level = 'LOW'
        else:
            risk_level = 'NONE'

        # Generate summary
        critical_count = sum(1 for i in all_indicators if i.severity == 'CRITICAL')
        high_count = sum(1 for i in all_indicators if i.severity == 'HIGH')
        categories_flagged = list(category_scores.keys())

        if critical_count > 0:
            summary = f"CRITICAL: {critical_count} critical issue(s) - {', '.join(categories_flagged)}"
        elif high_count > 0:
            summary = f"HIGH RISK: {high_count} high-severity issue(s) in {len(categories_flagged)} categories"
        elif all_indicators:
            summary = f"FLAGGED: {len(all_indicators)} indicator(s) across {len(categories_flagged)} categories"
        else:
            summary = "No significant fraud indicators detected"

        return ContractorRiskProfile(
            uei=uei,
            legal_name=legal_name,
            indicators=all_indicators,
            total_score=total_score,
            risk_level=risk_level,
            category_scores=dict(category_scores),
            summary=summary,
            analyzed_at=datetime.now().isoformat()
        )

    async def analyze_contract(
        self,
        contract: Contract,
        deep_analysis: bool = False
    ) -> ContractorRiskProfile:
        """
        Analyze a single contract's contractor.

        Convenience method that wraps analyze_contractor.
        """
        return await self.analyze_contractor(
            uei=contract.recipient_uei,
            contracts=[contract],
            include_network_analysis=deep_analysis,
            deep_analysis=deep_analysis
        )

    async def close(self):
        """Cleanup resources."""
        await self.usaspending.close()
