"""
COVID-Era Child Nutrition and Childcare Fraud Scanner

Searches for suspicious patterns in federal meal programs and childcare contracts,
similar to the Minnesota childcare fraud scheme ($250M+ stolen).

Red flags:
- Recent entity registrations receiving large contracts
- No website registered
- Virtual office addresses (suite, PO box)
- Not registered in SAM.gov
- On exclusion list but still receiving funds
"""

import asyncio
import csv
from datetime import datetime
from pathlib import Path
from data_sources import USASpendingClient
from data_sources.bulk_data import LocalDataStore


# Keywords related to child nutrition and childcare programs
SEARCH_KEYWORDS = [
    "child nutrition",
    "school lunch",
    "summer meals",
    "SNAP",
    "WIC",
    "child care",
    "daycare",
    "head start",
    "early childhood",
    "meal program",
    "food service",
]


async def scan_program_contracts(client: USASpendingClient, store: LocalDataStore, keyword: str):
    """Scan contracts for a specific program keyword."""
    suspicious = []

    # Retry logic for flaky API
    for attempt in range(3):
        try:
            result = await client.search_contracts(
                keywords=keyword,
                min_value=50000,
                limit=30
            )
            break
        except Exception as e:
            if attempt < 2:
                print(f"    Retry {attempt + 1} for {keyword}...")
                await asyncio.sleep(2)
            else:
                print(f"    Failed to fetch {keyword}: {e}")
                return []

    for c in result.contracts:
        flags = []

        # Check entity registration
        if c.recipient_uei:
            entity = store.get_entity_by_uei(c.recipient_uei)
            if entity:
                # Check registration age
                reg_date = entity.get("registration_date", "")
                if reg_date:
                    try:
                        reg = datetime.strptime(reg_date, "%Y%m%d")
                        age_days = (datetime.now() - reg).days
                        if age_days < 730:  # Less than 2 years
                            flags.append(f"NEW REG ({age_days}d)")
                        elif age_days < 1095:  # Less than 3 years
                            flags.append(f"RECENT REG ({age_days}d)")
                    except:
                        pass

                # No website
                if not entity.get("entity_url"):
                    flags.append("NO WEBSITE")

                # Virtual office indicators
                addr = entity.get("address", "").lower()
                if any(x in addr for x in ["suite", "ste ", " box", "pmb", "mailbox"]):
                    flags.append("SUITE/BOX ADDR")

            else:
                flags.append("NOT IN SAM")
        else:
            flags.append("NO UEI")

        # Check exclusions (critical - like NATIVE HEALTH)
        exclusion = store.check_exclusion(name=c.recipient_name[:30])
        if exclusion.get("is_excluded"):
            flags.append("EXCLUDED!")

        if flags:
            suspicious.append({
                "contract": c,
                "flags": flags,
                "keyword": keyword,
                "flag_count": len(flags)
            })

    return suspicious


async def main():
    print("=" * 70)
    print("COVID-ERA CHILD NUTRITION / CHILDCARE FRAUD SCANNER")
    print("=" * 70)
    print(f"Scan time: {datetime.now().isoformat()}")
    print("\nSearching for patterns similar to Minnesota childcare fraud...")
    print("(Empty facilities receiving funds, fake providers, recent registrations)\n")

    client = USASpendingClient()
    store = LocalDataStore()

    # Run all keyword searches in parallel
    print("Scanning all keywords in parallel...")
    tasks = [scan_program_contracts(client, store, kw) for kw in SEARCH_KEYWORDS]
    results_list = await asyncio.gather(*tasks)
    all_suspicious = [item for sublist in results_list for item in sublist]

    await client.close()

    # Deduplicate by contract ID
    seen = set()
    unique = []
    for item in all_suspicious:
        cid = item["contract"].contract_id
        if cid not in seen:
            seen.add(cid)
            unique.append(item)

    # Sort by flag count (most suspicious first)
    unique.sort(key=lambda x: x["flag_count"], reverse=True)

    print("\n" + "=" * 70)
    print(f"SUSPICIOUS CONTRACTS FOUND: {len(unique)}")
    print("=" * 70)

    # Group by severity
    critical = [x for x in unique if "EXCLUDED!" in x["flags"]]
    high = [x for x in unique if "NOT IN SAM" in x["flags"] and x not in critical]
    medium = [x for x in unique if x not in critical and x not in high]

    if critical:
        print("\n CRITICAL - EXCLUDED ENTITIES RECEIVING FUNDS:")
        print("-" * 50)
        for item in critical:
            c = item["contract"]
            print(f"\n  CONTRACT ID: {c.contract_id}")
            print(f"  Recipient: {c.recipient_name[:50]}")
            print(f"  UEI: {c.recipient_uei or 'N/A'}")
            print(f"  Value: ${c.total_obligation:,.0f}")
            print(f"  Agency: {c.agency}")
            print(f"  Program: {item['keyword']}")
            print(f"  Flags: {' | '.join(item['flags'])}")

    if high:
        print("\n\n HIGH - NOT REGISTERED IN SAM.GOV:")
        print("-" * 50)
        for item in high[:10]:
            c = item["contract"]
            print(f"\n  CONTRACT ID: {c.contract_id}")
            print(f"  Recipient: {c.recipient_name[:50]}")
            print(f"  UEI: {c.recipient_uei or 'N/A'}")
            print(f"  Value: ${c.total_obligation:,.0f}")
            print(f"  Agency: {c.agency}")
            print(f"  Program: {item['keyword']}")
            print(f"  Flags: {' | '.join(item['flags'])}")

    if medium:
        print("\n\n MEDIUM - OTHER RED FLAGS:")
        print("-" * 50)
        for item in medium[:10]:
            c = item["contract"]
            print(f"\n  CONTRACT ID: {c.contract_id}")
            print(f"  Recipient: {c.recipient_name[:50]}")
            print(f"  UEI: {c.recipient_uei or 'N/A'}")
            print(f"  Value: ${c.total_obligation:,.0f}")
            print(f"  Agency: {c.agency}")
            print(f"  Program: {item['keyword']}")
            print(f"  Flags: {' | '.join(item['flags'])}")

    # Summary
    print("\n\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total suspicious contracts: {len(unique)}")
    print(f"  - CRITICAL (excluded but funded): {len(critical)}")
    print(f"  - HIGH (not in SAM): {len(high)}")
    print(f"  - MEDIUM (other flags): {len(medium)}")

    total_value = sum(x["contract"].total_obligation for x in unique)
    print(f"\nTotal suspicious contract value: ${total_value:,.0f}")

    # Export to CSV for investigation
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / f"covid_fraud_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Severity", "Contract_ID", "Recipient", "UEI", "Value",
            "Agency", "Program_Keyword", "Flags"
        ])
        for item in unique:
            c = item["contract"]
            severity = "CRITICAL" if "EXCLUDED!" in item["flags"] else \
                       "HIGH" if "NOT IN SAM" in item["flags"] else "MEDIUM"
            writer.writerow([
                severity,
                c.contract_id,
                c.recipient_name,
                c.recipient_uei or "",
                c.total_obligation,
                c.agency,
                item["keyword"],
                " | ".join(item["flags"])
            ])

    print(f"\nExported to: {csv_path}")

    return unique


if __name__ == "__main__":
    asyncio.run(main())
