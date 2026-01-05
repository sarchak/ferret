"""
Federal Contract Fraud Detector

Detects fraud patterns using UEI-first matching and date verification.
Produces verified fraud cases with evidence for investigation.

Key principles:
1. UEI is the unique identifier - never match on name alone
2. Always verify dates - exclusion date vs award date
3. Require multiple corroborating signals for medium/low precision patterns
4. Output includes evidence trail for each detection
"""

import asyncio
import csv
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from data_sources import USASpendingClient
from data_sources.bulk_data import LocalDataStore
from fraud_patterns import FRAUD_PATTERNS, Precision, FraudPattern


@dataclass
class Evidence:
    """Evidence supporting a fraud detection."""
    source: str  # Data source (SAM, USASpending, etc.)
    field: str  # Field name
    value: str  # Actual value found
    expected: Optional[str] = None  # What value would indicate no fraud


@dataclass
class FraudDetection:
    """A detected fraud case with evidence."""
    pattern_id: str
    pattern_name: str
    precision: str
    contract_id: str
    recipient_name: str
    recipient_uei: Optional[str]
    contract_value: float
    awarding_agency: str
    start_date: Optional[str]
    evidence: list[Evidence] = field(default_factory=list)
    risk_score: int = 0

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "precision": self.precision,
            "contract_id": self.contract_id,
            "recipient_name": self.recipient_name,
            "recipient_uei": self.recipient_uei,
            "contract_value": self.contract_value,
            "awarding_agency": self.awarding_agency,
            "start_date": self.start_date,
            "evidence": [asdict(e) for e in self.evidence],
            "risk_score": self.risk_score,
        }


class FraudDetector:
    """Detects fraud patterns in federal contracts."""

    def __init__(self):
        self.store = LocalDataStore()
        self.client = None  # Lazy init
        self._exclusions_by_uei = None  # Lazy loaded index

    def _load_exclusions_index(self):
        """Build index of exclusions by UEI for fast lookup."""
        if self._exclusions_by_uei is not None:
            return

        self._exclusions_by_uei = {}
        exclusions_file = self.store._find_exclusions_file()
        if not exclusions_file:
            print("WARNING: No exclusions file found")
            return

        with open(exclusions_file, newline='', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            for row in reader:
                uei = row.get("Unique Entity ID", "").strip()
                if uei:
                    self._exclusions_by_uei[uei] = {
                        "name": row.get("Name", ""),
                        "active_date": row.get("Active Date", ""),
                        "termination_date": row.get("Termination Date", ""),
                        "excluding_agency": row.get("Excluding Agency", ""),
                        "exclusion_type": row.get("Exclusion Type", ""),
                        "ct_code": row.get("CT Code", ""),
                    }

        print(f"Loaded {len(self._exclusions_by_uei)} exclusions indexed by UEI")

    def check_exclusion_by_uei(self, uei: str) -> Optional[dict]:
        """Check if a UEI is on the exclusion list (EXACT match only)."""
        self._load_exclusions_index()
        return self._exclusions_by_uei.get(uei)

    def is_excluded_at_date(self, uei: str, check_date: str) -> tuple[bool, Optional[dict]]:
        """
        Check if UEI was excluded at a specific date.

        Args:
            uei: The Unique Entity Identifier
            check_date: Date to check in YYYY-MM-DD format

        Returns:
            (is_excluded, exclusion_record)
        """
        exclusion = self.check_exclusion_by_uei(uei)
        if not exclusion:
            return False, None

        # Parse dates
        try:
            check = datetime.strptime(check_date, "%Y-%m-%d")
        except:
            return False, None

        # Parse active date
        active_date_str = exclusion.get("active_date", "")
        if not active_date_str:
            return False, None

        try:
            # Try different date formats
            for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%Y%m%d"]:
                try:
                    active = datetime.strptime(active_date_str, fmt)
                    break
                except:
                    continue
            else:
                return False, None
        except:
            return False, None

        # Check if active before check date
        if active > check:
            return False, None

        # Check termination date
        term_date_str = exclusion.get("termination_date", "")
        if term_date_str and term_date_str.lower() != "indefinite":
            try:
                for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%Y%m%d"]:
                    try:
                        term = datetime.strptime(term_date_str, fmt)
                        break
                    except:
                        continue
                else:
                    term = None

                if term and term < check:
                    # Exclusion ended before check date
                    return False, None
            except:
                pass

        return True, exclusion

    async def detect_excluded_active_contracts(
        self,
        min_value: float = 50000,
        limit: int = 500,
        start_date: str = "2022-01-01",
        end_date: str = "2024-12-31"
    ) -> list[FraudDetection]:
        """
        Detect contracts awarded to excluded entities.
        Uses EXACT UEI matching and date verification.
        """
        if not self.client:
            self.client = USASpendingClient()

        detections = []

        # Get contracts in date range
        result = await self.client.search_contracts(
            min_value=min_value,
            limit=limit,
            start_date=start_date,
            end_date=end_date
        )

        for contract in result.contracts:
            if not contract.recipient_uei:
                continue

            # Check exclusion by EXACT UEI match
            is_excluded, exclusion = self.is_excluded_at_date(
                contract.recipient_uei,
                contract.start_date or datetime.now().strftime("%Y-%m-%d")
            )

            if is_excluded:
                detection = FraudDetection(
                    pattern_id="EXCLUDED_ACTIVE_CONTRACT",
                    pattern_name="Excluded Entity Receiving Active Contracts",
                    precision=Precision.CRITICAL.value,
                    contract_id=contract.contract_id,
                    recipient_name=contract.recipient_name,
                    recipient_uei=contract.recipient_uei,
                    contract_value=contract.total_obligation,
                    awarding_agency=contract.agency,
                    start_date=contract.start_date,
                    evidence=[
                        Evidence(
                            source="SAM Exclusions",
                            field="Unique Entity ID",
                            value=contract.recipient_uei,
                            expected="Not on exclusion list"
                        ),
                        Evidence(
                            source="SAM Exclusions",
                            field="Active Date",
                            value=exclusion.get("active_date", ""),
                            expected=f"After {contract.start_date}"
                        ),
                        Evidence(
                            source="SAM Exclusions",
                            field="Excluding Agency",
                            value=exclusion.get("excluding_agency", ""),
                        ),
                        Evidence(
                            source="SAM Exclusions",
                            field="Exclusion Type",
                            value=exclusion.get("exclusion_type", ""),
                        ),
                    ],
                    risk_score=100,
                )
                detections.append(detection)

        return detections

    async def detect_rapid_registration(
        self,
        days_threshold: int = 90,
        min_value: float = 500000,
        limit: int = 500,
        start_date: str = "2022-01-01",
        end_date: str = "2024-12-31"
    ) -> list[FraudDetection]:
        """
        Detect entities that received large contracts shortly after registration.
        """
        if not self.client:
            self.client = USASpendingClient()

        detections = []

        # Get high-value contracts in date range
        result = await self.client.search_contracts(
            min_value=min_value,
            limit=limit,
            start_date=start_date,
            end_date=end_date
        )

        for contract in result.contracts:
            if not contract.recipient_uei:
                continue

            # Look up entity in local SAM data
            entity = self.store.get_entity_by_uei(contract.recipient_uei)
            if not entity:
                continue

            reg_date_str = entity.get("registration_date", "")
            if not reg_date_str:
                continue

            # Parse dates
            try:
                reg_date = datetime.strptime(reg_date_str, "%Y%m%d")
                award_date = datetime.strptime(contract.start_date, "%Y-%m-%d")
            except:
                continue

            # Calculate days between registration and award
            days_diff = (award_date - reg_date).days

            if 0 < days_diff <= days_threshold:
                evidence = [
                    Evidence(
                        source="SAM Entities",
                        field="registration_date",
                        value=reg_date_str,
                    ),
                    Evidence(
                        source="USASpending",
                        field="start_date",
                        value=contract.start_date,
                    ),
                    Evidence(
                        source="Calculated",
                        field="days_between",
                        value=str(days_diff),
                        expected=f">{days_threshold}"
                    ),
                ]

                # Check for additional red flags
                if not entity.get("entity_url"):
                    evidence.append(Evidence(
                        source="SAM Entities",
                        field="entity_url",
                        value="MISSING",
                        expected="Valid website"
                    ))

                addr = entity.get("address", "").lower()
                if any(kw in addr for kw in ["suite", "ste ", " box", "pmb"]):
                    evidence.append(Evidence(
                        source="SAM Entities",
                        field="address",
                        value=entity.get("address", ""),
                        expected="Physical address (not virtual)"
                    ))

                detection = FraudDetection(
                    pattern_id="RAPID_REGISTRATION_LARGE_AWARD",
                    pattern_name="New Entity Immediately Receives Large Contract",
                    precision=Precision.HIGH.value,
                    contract_id=contract.contract_id,
                    recipient_name=contract.recipient_name,
                    recipient_uei=contract.recipient_uei,
                    contract_value=contract.total_obligation,
                    awarding_agency=contract.agency,
                    start_date=contract.start_date,
                    evidence=evidence,
                    risk_score=70 if days_diff > 30 else 85,
                )
                detections.append(detection)

        return detections

    async def detect_threshold_splitting(
        self,
        limit: int = 500,
        start_date: str = "2022-01-01",
        end_date: str = "2024-12-31"
    ) -> list[FraudDetection]:
        """
        Detect potential contract splitting to avoid thresholds.
        """
        if not self.client:
            self.client = USASpendingClient()

        # Define thresholds - focus on simplified acquisition
        thresholds = [
            (250000, "simplified acquisition"),
        ]

        detections = []

        for threshold, name in thresholds:
            # Get contracts in the 90-99% range of threshold
            lower = threshold * 0.90
            upper = threshold * 0.99

            try:
                result = await self.client.search_contracts(
                    min_value=lower,
                    limit=limit,
                    start_date=start_date,
                    end_date=end_date
                )
            except Exception as e:
                print(f"    Error searching {name} threshold: {e}")
                continue

            # Filter to values below threshold
            contracts = [c for c in result.contracts if c.total_obligation < threshold]

            # Group by recipient + agency
            from collections import defaultdict
            groups = defaultdict(list)
            for c in contracts:
                key = (c.recipient_uei or c.recipient_name, c.agency)
                groups[key].append(c)

            # Flag groups with 3+ contracts
            for (recipient_id, agency), contracts in groups.items():
                if len(contracts) >= 3:
                    total_value = sum(c.total_obligation for c in contracts)
                    if total_value > threshold:
                        # This is suspicious - sum exceeds threshold
                        first = contracts[0]
                        detection = FraudDetection(
                            pattern_id="THRESHOLD_SPLITTING",
                            pattern_name=f"Contract Splitting ({name} threshold)",
                            precision=Precision.HIGH.value,
                            contract_id=", ".join(c.contract_id for c in contracts[:5]),
                            recipient_name=first.recipient_name,
                            recipient_uei=first.recipient_uei,
                            contract_value=total_value,
                            awarding_agency=agency,
                            start_date=first.start_date,
                            evidence=[
                                Evidence(
                                    source="USASpending",
                                    field="contract_count",
                                    value=str(len(contracts)),
                                    expected="<3 near threshold"
                                ),
                                Evidence(
                                    source="USASpending",
                                    field="total_value",
                                    value=f"${total_value:,.0f}",
                                    expected=f"<${threshold:,}"
                                ),
                                Evidence(
                                    source="Calculated",
                                    field="threshold",
                                    value=f"${threshold:,} ({name})",
                                ),
                                Evidence(
                                    source="USASpending",
                                    field="contract_values",
                                    value=", ".join(f"${c.total_obligation:,.0f}" for c in contracts[:5]),
                                ),
                            ],
                            risk_score=75,
                        )
                        detections.append(detection)

        return detections

    async def run_all_detections(
        self,
        start_date: str = "2022-01-01",
        end_date: str = "2024-12-31"
    ) -> list[FraudDetection]:
        """Run all fraud detection patterns for a date range."""
        all_detections = []

        print(f"Date range: {start_date} to {end_date}")

        print("\nRunning EXCLUDED_ACTIVE_CONTRACT detection...")
        detections = await self.detect_excluded_active_contracts(
            start_date=start_date, end_date=end_date
        )
        print(f"  Found {len(detections)} detections")
        all_detections.extend(detections)

        print("\nRunning RAPID_REGISTRATION_LARGE_AWARD detection...")
        detections = await self.detect_rapid_registration(
            start_date=start_date, end_date=end_date
        )
        print(f"  Found {len(detections)} detections")
        all_detections.extend(detections)

        print("\nRunning THRESHOLD_SPLITTING detection...")
        detections = await self.detect_threshold_splitting(
            start_date=start_date, end_date=end_date
        )
        print(f"  Found {len(detections)} detections")
        all_detections.extend(detections)

        return all_detections

    async def close(self):
        if self.client:
            await self.client.close()


def export_detections(detections: list[FraudDetection], output_dir: Path):
    """Export detections to CSV and JSON for investigation."""
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # CSV for spreadsheet analysis
    csv_path = output_dir / f"fraud_detections_{timestamp}.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Pattern", "Precision", "Risk Score", "Contract ID", "Recipient",
            "UEI", "Value", "Agency", "Start Date", "Evidence Summary"
        ])
        for d in sorted(detections, key=lambda x: x.risk_score, reverse=True):
            evidence_summary = "; ".join(
                f"{e.field}={e.value}" for e in d.evidence[:3]
            )
            writer.writerow([
                d.pattern_id, d.precision, d.risk_score, d.contract_id,
                d.recipient_name, d.recipient_uei, d.contract_value,
                d.awarding_agency, d.start_date, evidence_summary
            ])

    # JSON for full evidence
    json_path = output_dir / f"fraud_detections_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump([d.to_dict() for d in detections], f, indent=2)

    print(f"\nExported to:")
    print(f"  CSV: {csv_path}")
    print(f"  JSON: {json_path}")

    return csv_path, json_path


async def main():
    print("=" * 70)
    print("FEDERAL CONTRACT FRAUD DETECTOR")
    print("=" * 70)
    print(f"Scan time: {datetime.now().isoformat()}")
    print("\nUsing UEI-first matching with date verification")
    print("Scanning contracts from 2022-2024\n")

    detector = FraudDetector()

    try:
        detections = await detector.run_all_detections(
            start_date="2022-01-01",
            end_date="2024-12-31"
        )

        # Print summary
        print("\n" + "=" * 70)
        print("DETECTION SUMMARY")
        print("=" * 70)

        by_pattern = {}
        for d in detections:
            if d.pattern_id not in by_pattern:
                by_pattern[d.pattern_id] = []
            by_pattern[d.pattern_id].append(d)

        total_value = 0
        for pattern_id, pattern_detections in sorted(by_pattern.items()):
            pattern_value = sum(d.contract_value for d in pattern_detections)
            total_value += pattern_value
            precision = pattern_detections[0].precision
            print(f"\n{pattern_id} ({precision}):")
            print(f"  Detections: {len(pattern_detections)}")
            print(f"  Total value: ${pattern_value:,.0f}")

        print(f"\n{'='*70}")
        print(f"TOTAL: {len(detections)} detections, ${total_value:,.0f} at risk")
        print("=" * 70)

        # Print top detections
        print("\nTOP 10 DETECTIONS (by risk score):")
        print("-" * 70)
        for d in sorted(detections, key=lambda x: x.risk_score, reverse=True)[:10]:
            print(f"\n[{d.precision}] {d.pattern_id}")
            print(f"  Contract: {d.contract_id}")
            print(f"  Recipient: {d.recipient_name}")
            print(f"  UEI: {d.recipient_uei}")
            print(f"  Value: ${d.contract_value:,.0f}")
            print(f"  Agency: {d.awarding_agency}")
            print("  Evidence:")
            for e in d.evidence[:3]:
                print(f"    - {e.field}: {e.value}")

        # Export
        output_dir = Path(__file__).parent / "outputs"
        export_detections(detections, output_dir)

    finally:
        await detector.close()


if __name__ == "__main__":
    asyncio.run(main())
