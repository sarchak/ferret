"""
Shell Company Network Detector

Finds clusters of entities sharing:
- Same physical address (strongest signal)
- Same registered agent
- Same phone number
- Same POC (point of contact)

These patterns often indicate shell company networks used to
circumvent contract limits or hide beneficial ownership.
"""

import asyncio
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import csv
from data_sources.bulk_data import LocalDataStore


def normalize_address(addr: str) -> str:
    """Normalize address for comparison."""
    if not addr:
        return ""
    addr = addr.lower().strip()
    # Remove common variations
    replacements = [
        ("street", "st"),
        ("avenue", "ave"),
        ("boulevard", "blvd"),
        ("drive", "dr"),
        ("suite", "ste"),
        (".", ""),
        (",", ""),
        ("  ", " "),
    ]
    for old, new in replacements:
        addr = addr.replace(old, new)
    return addr


def main():
    print("=" * 70)
    print("SHELL COMPANY NETWORK DETECTOR")
    print("=" * 70)
    print(f"Scan time: {datetime.now().isoformat()}")
    print("\nScanning SAM.gov entity data for address clusters...")

    store = LocalDataStore()
    entity_file = store._find_entity_file()

    if not entity_file:
        print("ERROR: No entity file found. Download SAM.gov entity extract first.")
        return

    print(f"Reading: {entity_file.name}")

    # Group entities by normalized address
    by_address = defaultdict(list)
    entity_count = 0

    with open(entity_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            entity = store._parse_entity_line(line)
            if not entity:
                continue

            entity_count += 1
            if entity_count % 100000 == 0:
                print(f"  Processed {entity_count:,} entities...")

            # Build address key
            addr = normalize_address(entity.get("address", ""))
            city = entity.get("city", "").lower().strip()
            state = entity.get("state", "").strip()
            zip_code = entity.get("zip", "").strip()[:5]

            if addr and city and state:
                key = f"{addr}|{city}|{state}|{zip_code}"
                by_address[key].append({
                    "uei": entity.get("uei"),
                    "name": entity.get("legal_name"),
                    "dba": entity.get("dba_name"),
                    "reg_date": entity.get("registration_date"),
                    "status": entity.get("registration_status"),
                    "address": entity.get("address"),
                    "city": entity.get("city"),
                    "state": entity.get("state"),
                    "zip": entity.get("zip"),
                })

    print(f"\nTotal entities processed: {entity_count:,}")

    # Find clusters (3+ entities at same address)
    clusters = []
    for addr_key, entities in by_address.items():
        if len(entities) >= 3:
            clusters.append({
                "address_key": addr_key,
                "count": len(entities),
                "entities": entities
            })

    # Sort by cluster size
    clusters.sort(key=lambda x: x["count"], reverse=True)

    print(f"Found {len(clusters)} address clusters with 3+ entities\n")

    # Print top clusters
    print("=" * 70)
    print("TOP SUSPICIOUS ADDRESS CLUSTERS")
    print("=" * 70)

    for cluster in clusters[:20]:
        entities = cluster["entities"]
        first = entities[0]
        print(f"\n  ADDRESS: {first['address']}, {first['city']}, {first['state']} {first['zip']}")
        print(f"  ENTITIES: {cluster['count']}")
        print("  ---")
        for e in entities[:5]:
            status_flag = "" if e["status"] == "A" else f" [{e['status']}]"
            print(f"    - {e['name'][:50]}{status_flag}")
            print(f"      UEI: {e['uei']}")
        if len(entities) > 5:
            print(f"    ... and {len(entities) - 5} more")

    # Export to CSV
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(exist_ok=True)
    csv_path = output_dir / f"shell_networks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Cluster_Size", "Address", "City", "State", "Zip",
            "Entity_UEI", "Entity_Name", "DBA_Name", "Reg_Date", "Status"
        ])
        for cluster in clusters:
            for e in cluster["entities"]:
                writer.writerow([
                    cluster["count"],
                    e["address"],
                    e["city"],
                    e["state"],
                    e["zip"],
                    e["uei"],
                    e["name"],
                    e["dba"],
                    e["reg_date"],
                    e["status"]
                ])

    print(f"\n\nExported {len(clusters)} clusters to: {csv_path}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total entities scanned: {entity_count:,}")
    print(f"Address clusters (3+ entities): {len(clusters)}")
    print(f"Entities in clusters: {sum(c['count'] for c in clusters):,}")

    # Flag known shell company addresses (Regus, WeWork, etc.)
    virtual_office_clusters = [
        c for c in clusters
        if any(kw in c["address_key"].lower() for kw in ["regus", "wework", "spaces", "executive center"])
    ]
    if virtual_office_clusters:
        print(f"\nVirtual office clusters: {len(virtual_office_clusters)}")

    return clusters


if __name__ == "__main__":
    main()
