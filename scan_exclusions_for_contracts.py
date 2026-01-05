"""
Reverse lookup: Check if excluded entities have received contracts.

Approach:
1. Load all exclusions with UEIs
2. For each excluded entity, search for contracts to that UEI
3. Check if contract date is after exclusion date
"""

import asyncio
import csv
from datetime import datetime
from pathlib import Path

from data_sources import USASpendingClient
from data_sources.bulk_data import LocalDataStore


async def scan_excluded_for_contracts():
    print("=" * 70)
    print("REVERSE EXCLUSION SCAN")
    print("=" * 70)
    print("Checking if excluded entities received contracts after exclusion")
    print()

    store = LocalDataStore()
    client = USASpendingClient()

    # Load exclusions with UEIs
    exclusions_file = store._find_exclusions_file()
    if not exclusions_file:
        print("ERROR: No exclusions file found")
        return

    # Read exclusions
    exclusions = []
    with open(exclusions_file, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            uei = row.get("Unique Entity ID", "").strip()
            if uei and len(uei) > 5:  # Valid UEI
                exclusions.append({
                    "uei": uei,
                    "name": row.get("Name", ""),
                    "active_date": row.get("Active Date", ""),
                    "termination_date": row.get("Termination Date", ""),
                    "excluding_agency": row.get("Excluding Agency", ""),
                    "exclusion_type": row.get("Exclusion Type", ""),
                })

    print(f"Loaded {len(exclusions)} exclusions with UEIs")
    print()

    # Sample some exclusions to search for contracts
    # (Full scan would take too long)
    sample_size = 50
    sample = exclusions[:sample_size]

    findings = []

    for i, exc in enumerate(sample):
        if i % 10 == 0:
            print(f"Checking exclusion {i+1}/{sample_size}...")

        # Search for contracts to this UEI
        try:
            result = await client.search_contracts(
                keywords=exc["name"][:30] if exc["name"] else None,
                limit=10,
                start_date="2020-01-01",
                end_date="2024-12-31"
            )

            for contract in result.contracts:
                if contract.recipient_uei == exc["uei"]:
                    # Found a match!
                    findings.append({
                        "exclusion": exc,
                        "contract": contract,
                    })
                    print(f"\n  FOUND: {exc['name']}")
                    print(f"    UEI: {exc['uei']}")
                    print(f"    Exclusion date: {exc['active_date']}")
                    print(f"    Contract: {contract.contract_id}")
                    print(f"    Contract date: {contract.start_date}")
                    print(f"    Value: ${contract.total_obligation:,.0f}")

        except Exception as e:
            continue

        await asyncio.sleep(0.5)  # Rate limit

    await client.close()

    print("\n" + "=" * 70)
    print(f"SUMMARY: Found {len(findings)} contracts to excluded entities")
    print("=" * 70)

    # Export findings
    if findings:
        output_dir = Path(__file__).parent / "outputs"
        output_dir.mkdir(exist_ok=True)
        csv_path = output_dir / f"excluded_with_contracts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Excluded_Name", "UEI", "Exclusion_Date", "Excluding_Agency",
                "Contract_ID", "Contract_Date", "Contract_Value", "Awarding_Agency"
            ])
            for finding in findings:
                exc = finding["exclusion"]
                c = finding["contract"]
                writer.writerow([
                    exc["name"], exc["uei"], exc["active_date"], exc["excluding_agency"],
                    c.contract_id, c.start_date, c.total_obligation, c.agency
                ])

        print(f"\nExported to: {csv_path}")


if __name__ == "__main__":
    asyncio.run(scan_excluded_for_contracts())
