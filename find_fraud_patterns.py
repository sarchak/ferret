"""
Fraud Pattern Scanner

Scans recent contracts for suspicious patterns:
1. Threshold clustering - contracts just below simplified acquisition thresholds
2. Sole-source concentration - companies winning many no-competition contracts
3. Shell company indicators - new registrations, virtual offices, no web presence
4. Split awards - multiple contracts to same vendor just below thresholds
"""

import asyncio
from collections import defaultdict
from datetime import datetime
from data_sources import USASpendingClient
from data_sources.bulk_data import LocalDataStore

# Key thresholds in federal contracting
THRESHOLDS = {
    10000: "Micro-purchase",
    250000: "Simplified Acquisition",
    750000: "Subcontracting Plan Required",
    1000000: "Million Dollar",
}

# Virtual office indicators
VIRTUAL_OFFICE_KEYWORDS = [
    "suite", "ste", "box", "pmb", "mailbox", "#", "unit",
    "regus", "wework", "spaces", "executive suite"
]


async def scan_threshold_clustering(client: USASpendingClient, days: int = 30):
    """Find contracts clustered just below acquisition thresholds."""
    print("\n" + "="*60)
    print("THRESHOLD CLUSTERING ANALYSIS")
    print("="*60)

    suspicious = []

    for threshold, name in THRESHOLDS.items():
        # Look for contracts between 90-99% of threshold
        lower = threshold * 0.90
        upper = threshold * 0.99

        result = await client.search_contracts(
            min_value=lower,
            max_value=upper,
            limit=50
        )

        if result.contracts:
            print(f"\n{name} Threshold (${threshold:,}):")
            print(f"  Found {len(result.contracts)} contracts in ${lower:,.0f} - ${upper:,.0f} range")

            # Group by recipient
            by_recipient = defaultdict(list)
            for c in result.contracts:
                by_recipient[c.recipient_name].append(c)

            # Flag recipients with multiple contracts near threshold
            for recipient, contracts in by_recipient.items():
                if len(contracts) >= 2:
                    total = sum(c.total_obligation for c in contracts)
                    print(f"\n  ⚠️  {recipient[:50]}")
                    print(f"      {len(contracts)} contracts totaling ${total:,.0f}")
                    for c in contracts[:3]:
                        print(f"      - {c.contract_id}: ${c.total_obligation:,.0f}")
                    suspicious.append({
                        "pattern": "THRESHOLD_CLUSTERING",
                        "threshold": name,
                        "recipient": recipient,
                        "contracts": len(contracts),
                        "total_value": total
                    })

    return suspicious


async def scan_sole_source(client: USASpendingClient, days: int = 30):
    """Find companies winning many sole-source (no competition) contracts."""
    print("\n" + "="*60)
    print("SOLE-SOURCE CONCENTRATION ANALYSIS")
    print("="*60)

    # Get recent contracts with a specific value range to avoid API errors
    result = await client.search_contracts(min_value=100000, max_value=500000, limit=100)

    # Group by recipient
    by_recipient = defaultdict(list)
    for c in result.contracts:
        by_recipient[c.recipient_name].append(c)

    suspicious = []

    # Find recipients with multiple contracts
    print(f"\nAnalyzing {len(result.contracts)} contracts from {len(by_recipient)} vendors...")

    for recipient, contracts in sorted(by_recipient.items(), key=lambda x: len(x[1]), reverse=True):
        if len(contracts) >= 3:
            total = sum(c.total_obligation for c in contracts)
            # Check for sole-source indicators (no offers field or 0/1 offers)
            sole_source = [c for c in contracts if c.number_of_offers <= 1]

            if len(sole_source) >= 2:
                print(f"\n⚠️  {recipient[:50]}")
                print(f"   {len(contracts)} total contracts, {len(sole_source)} sole-source")
                print(f"   Total value: ${total:,.0f}")
                suspicious.append({
                    "pattern": "SOLE_SOURCE_CONCENTRATION",
                    "recipient": recipient,
                    "total_contracts": len(contracts),
                    "sole_source_contracts": len(sole_source),
                    "total_value": total
                })

    return suspicious


async def scan_shell_companies(client: USASpendingClient, store: LocalDataStore, days: int = 30):
    """Find potential shell company indicators."""
    print("\n" + "="*60)
    print("SHELL COMPANY INDICATOR SCAN")
    print("="*60)

    # Get recent contracts
    result = await client.search_contracts(min_value=50000, max_value=500000, limit=100)

    suspicious = []

    for c in result.contracts:
        flags = []
        entity = None

        # Look up entity in local data
        if c.recipient_uei:
            entity = store.get_entity_by_uei(c.recipient_uei)

        if entity:
            # Check registration age
            reg_date = entity.get("registration_date", "")
            if reg_date:
                try:
                    reg = datetime.strptime(reg_date, "%Y%m%d")
                    age_days = (datetime.now() - reg).days
                    if age_days < 365:
                        flags.append(f"New registration ({age_days} days)")
                    elif age_days < 730:
                        flags.append(f"Recent registration ({age_days} days)")
                except:
                    pass

            # Check for virtual office indicators
            address = entity.get("address", "").lower()
            for keyword in VIRTUAL_OFFICE_KEYWORDS:
                if keyword in address:
                    flags.append(f"Virtual office indicator: '{keyword}'")
                    break

            # Check if no website
            if not entity.get("entity_url"):
                flags.append("No website registered")
        else:
            flags.append("Entity not found in SAM.gov data")

        # Check exclusions
        exclusion = store.check_exclusion(name=c.recipient_name[:30])
        if exclusion.get("is_excluded"):
            flags.append("⛔ NAME MATCHES EXCLUSION LIST")

        if flags:
            suspicious.append({
                "pattern": "SHELL_COMPANY_INDICATORS",
                "contract_id": c.contract_id,
                "recipient": c.recipient_name,
                "value": c.total_obligation,
                "uei": c.recipient_uei,
                "flags": flags
            })

    # Print results
    print(f"\nScanned {len(result.contracts)} contracts")
    print(f"Found {len(suspicious)} with potential shell company indicators:\n")

    for s in sorted(suspicious, key=lambda x: len(x["flags"]), reverse=True)[:15]:
        print(f"⚠️  {s['recipient'][:45]}")
        print(f"   Contract: {s['contract_id']} | Value: ${s['value']:,.0f}")
        for flag in s["flags"]:
            print(f"   🚩 {flag}")
        print()

    return suspicious


async def scan_split_awards(client: USASpendingClient, days: int = 30):
    """Find potential contract splitting to avoid thresholds."""
    print("\n" + "="*60)
    print("SPLIT AWARD ANALYSIS")
    print("="*60)

    # Get contracts in the $50K-$250K range
    result = await client.search_contracts(min_value=50000, max_value=250000, limit=200)

    # Group by recipient and agency
    by_recipient_agency = defaultdict(list)
    for c in result.contracts:
        key = (c.recipient_name, c.agency)
        by_recipient_agency[key].append(c)

    suspicious = []

    print(f"\nAnalyzing {len(result.contracts)} contracts...")

    for (recipient, agency), contracts in by_recipient_agency.items():
        if len(contracts) >= 3:
            total = sum(c.total_obligation for c in contracts)
            # If total exceeds threshold but individual contracts don't
            if total > 250000:
                print(f"\n⚠️  Potential Split: {recipient[:40]}")
                print(f"   Agency: {agency[:30]}")
                print(f"   {len(contracts)} contracts totaling ${total:,.0f}")
                print(f"   (Individual contracts under $250K, combined over)")
                for c in contracts[:5]:
                    print(f"   - {c.contract_id[:20]}: ${c.total_obligation:,.0f}")

                suspicious.append({
                    "pattern": "SPLIT_AWARD",
                    "recipient": recipient,
                    "agency": agency,
                    "contracts": len(contracts),
                    "total_value": total
                })

    return suspicious


async def main():
    print("="*60)
    print("FERRET FRAUD PATTERN SCANNER")
    print("="*60)
    print(f"Scan time: {datetime.now().isoformat()}")

    client = USASpendingClient()
    store = LocalDataStore()

    all_suspicious = []

    # Run all scans
    all_suspicious.extend(await scan_threshold_clustering(client))
    all_suspicious.extend(await scan_sole_source(client))
    all_suspicious.extend(await scan_shell_companies(client, store))
    all_suspicious.extend(await scan_split_awards(client))

    await client.close()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    by_pattern = defaultdict(list)
    for s in all_suspicious:
        by_pattern[s["pattern"]].append(s)

    for pattern, items in by_pattern.items():
        print(f"\n{pattern}: {len(items)} findings")

    print(f"\nTotal suspicious patterns found: {len(all_suspicious)}")

    return all_suspicious


if __name__ == "__main__":
    asyncio.run(main())
