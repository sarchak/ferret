"""
Multi-Signal Fraud Scorer

Combines multiple fraud indicators into a single risk score:

SIGNAL WEIGHTS (higher = more suspicious):
- Excluded but receiving funds: 100 (critical - immediate investigation)
- Not in SAM registry: 50
- Address cluster (3+ entities): 30
- Recent registration (<2 years): 25
- Virtual office indicator: 20
- No website: 15
- Threshold clustering: 40
- Sole-source concentration: 35

Final score interpretation:
- 0-25: Low risk
- 26-50: Medium risk
- 51-75: High risk
- 76+: Critical risk
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import csv


@dataclass
class FraudScore:
    """Fraud risk score for a contract/entity."""
    entity_name: str
    contract_id: Optional[str]
    uei: Optional[str]
    total_score: int
    signals: list[tuple[str, int]]  # (signal_name, points)
    risk_level: str
    value: float = 0.0

    def to_dict(self) -> dict:
        return {
            "entity_name": self.entity_name,
            "contract_id": self.contract_id,
            "uei": self.uei,
            "total_score": self.total_score,
            "risk_level": self.risk_level,
            "value": self.value,
            "signals": "; ".join([f"{s[0]}({s[1]})" for s in self.signals])
        }


class FraudScorer:
    """Scores entities/contracts based on multiple fraud indicators."""

    # Signal weights
    WEIGHTS = {
        "EXCLUDED": 100,  # On exclusion list but receiving funds
        "NOT_IN_SAM": 50,  # Not registered in SAM.gov
        "ADDRESS_CLUSTER": 30,  # 3+ entities at same address
        "ADDRESS_CLUSTER_LARGE": 50,  # 10+ entities at same address
        "RECENT_REGISTRATION": 25,  # Registered < 2 years
        "NEW_REGISTRATION": 40,  # Registered < 1 year
        "VIRTUAL_OFFICE": 20,  # Suite/box/PMB address
        "NO_WEBSITE": 15,  # No website registered
        "THRESHOLD_CLUSTER": 40,  # Multiple contracts just below threshold
        "SOLE_SOURCE": 35,  # Multiple sole-source contracts
        "RAPID_GROWTH": 45,  # Sudden increase in contract volume
    }

    def __init__(self, address_clusters: Optional[dict] = None):
        """
        Initialize scorer.

        Args:
            address_clusters: Dict mapping normalized address to entity count
        """
        self.address_clusters = address_clusters or {}

    def load_address_clusters(self, csv_path: Path):
        """Load address clusters from shell network scan output."""
        self.address_clusters = {}
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = f"{row['Address']}|{row['City']}|{row['State']}|{row['Zip']}"
                self.address_clusters[key] = int(row["Cluster_Size"])
        print(f"Loaded {len(self.address_clusters)} address clusters")

    def score_entity(
        self,
        name: str,
        uei: Optional[str] = None,
        contract_id: Optional[str] = None,
        is_excluded: bool = False,
        in_sam: bool = True,
        registration_date: Optional[str] = None,
        has_website: bool = True,
        address: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        zip_code: Optional[str] = None,
        sole_source_contracts: int = 0,
        threshold_cluster_count: int = 0,
        value: float = 0.0,
    ) -> FraudScore:
        """Calculate fraud risk score for an entity."""
        signals = []

        # Critical: Excluded but receiving funds
        if is_excluded:
            signals.append(("EXCLUDED", self.WEIGHTS["EXCLUDED"]))

        # Not in SAM registry
        if not in_sam:
            signals.append(("NOT_IN_SAM", self.WEIGHTS["NOT_IN_SAM"]))

        # Registration age
        if registration_date:
            try:
                reg = datetime.strptime(registration_date, "%Y%m%d")
                age_days = (datetime.now() - reg).days
                if age_days < 365:
                    signals.append(("NEW_REGISTRATION", self.WEIGHTS["NEW_REGISTRATION"]))
                elif age_days < 730:
                    signals.append(("RECENT_REGISTRATION", self.WEIGHTS["RECENT_REGISTRATION"]))
            except:
                pass

        # No website
        if not has_website:
            signals.append(("NO_WEBSITE", self.WEIGHTS["NO_WEBSITE"]))

        # Virtual office indicators
        if address:
            addr_lower = address.lower()
            if any(kw in addr_lower for kw in ["suite", "ste ", " box", "pmb", "mailbox"]):
                signals.append(("VIRTUAL_OFFICE", self.WEIGHTS["VIRTUAL_OFFICE"]))

        # Address cluster check
        if address and city and state and zip_code:
            key = f"{address}|{city}|{state}|{zip_code[:5]}"
            cluster_size = self.address_clusters.get(key, 0)
            if cluster_size >= 10:
                signals.append(("ADDRESS_CLUSTER_LARGE", self.WEIGHTS["ADDRESS_CLUSTER_LARGE"]))
            elif cluster_size >= 3:
                signals.append(("ADDRESS_CLUSTER", self.WEIGHTS["ADDRESS_CLUSTER"]))

        # Sole-source concentration
        if sole_source_contracts >= 3:
            signals.append(("SOLE_SOURCE", self.WEIGHTS["SOLE_SOURCE"]))

        # Threshold clustering
        if threshold_cluster_count >= 2:
            signals.append(("THRESHOLD_CLUSTER", self.WEIGHTS["THRESHOLD_CLUSTER"]))

        # Calculate total score
        total = sum(s[1] for s in signals)

        # Determine risk level
        if total >= 76:
            risk_level = "CRITICAL"
        elif total >= 51:
            risk_level = "HIGH"
        elif total >= 26:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return FraudScore(
            entity_name=name,
            contract_id=contract_id,
            uei=uei,
            total_score=total,
            signals=signals,
            risk_level=risk_level,
            value=value,
        )


async def lookup_entity_contracts(entity_name: str) -> list[dict]:
    """Look up all contracts for an entity from USASpending."""
    from data_sources import USASpendingClient

    client = USASpendingClient()
    result = await client.search_contracts(keywords=entity_name, limit=50)
    await client.close()

    # Filter to exact matches
    contracts = []
    search_term = entity_name.split()[0].upper()
    for c in result.contracts:
        if search_term in c.recipient_name.upper():
            contracts.append({
                "contract_id": c.contract_id,
                "recipient": c.recipient_name,
                "value": c.total_obligation,
                "agency": c.agency,
            })
    return contracts


async def demo():
    """Demo the fraud scorer with example cases and contract lookups."""
    print("=" * 70)
    print("MULTI-SIGNAL FRAUD SCORER")
    print("=" * 70)
    print(f"Scan time: {datetime.now().isoformat()}\n")

    scorer = FraudScorer()

    # Load address clusters if available
    output_dir = Path(__file__).parent / "outputs"
    cluster_files = list(output_dir.glob("shell_networks_*.csv"))
    if cluster_files:
        scorer.load_address_clusters(cluster_files[-1])

    # Suspicious entities to investigate
    suspicious_entities = [
        {
            "name": "NATIVE HEALTH",
            "flags": {"is_excluded": True},
            "reason": "On SAM.gov exclusion list but receiving HHS contracts",
        },
        {
            "name": "OAK VIEW REHABILITATION",
            "flags": {"in_sam": False},
            "reason": "Not registered in SAM.gov but receiving VA contracts",
        },
        {
            "name": "CAPEWELL AERIAL SYSTEMS",
            "flags": {"threshold_cluster_count": 5},
            "reason": "5 contracts at exactly $247,500 (threshold clustering)",
        },
        {
            "name": "ACCELGOV",
            "flags": {"has_website": False, "address": "STE 100"},
            "reason": "Virtual office, no website, $100M+ in contracts",
        },
    ]

    for entity in suspicious_entities:
        print(f"\n{'='*70}")
        print(f"ENTITY: {entity['name']}")
        print(f"REASON: {entity['reason']}")
        print("=" * 70)

        # Look up all contracts
        print("\nLooking up contracts...")
        contracts = await lookup_entity_contracts(entity["name"])

        if not contracts:
            print("  No contracts found")
            continue

        # Score and display
        total_value = sum(c["value"] for c in contracts)
        print(f"\nTotal contracts: {len(contracts)}")
        print(f"Total value: ${total_value:,.0f}")

        # Score the entity
        score = scorer.score_entity(
            name=entity["name"],
            value=total_value,
            **entity["flags"]
        )
        print(f"\nFRAUD SCORE: {score.total_score} ({score.risk_level})")
        print("Signals:")
        for signal, points in score.signals:
            print(f"  - {signal}: +{points}")

        # List all contracts
        print(f"\n{'CONTRACT ID':<25} {'VALUE':>15} {'AGENCY':<30}")
        print("-" * 70)
        for c in sorted(contracts, key=lambda x: x["value"], reverse=True):
            print(f"{c['contract_id']:<25} ${c['value']:>14,.0f} {c['agency'][:30]}")


def main():
    """Entry point."""
    import asyncio
    asyncio.run(demo())


if __name__ == "__main__":
    main()
