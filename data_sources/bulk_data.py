"""
Bulk Data Downloads

Downloads and processes bulk data extracts from federal data sources.
These have no API limits and are updated daily.

Data Sources:
- SAM.gov Entity Extracts: https://sam.gov/data-services/entity-registration/public-extracts
- USASpending Award Data: https://www.usaspending.gov/download_center/custom_award_data
- FPDS Contract Data: https://www.fpds.gov/fpdsng_cms/index.php/en/reports
"""

import httpx
import zipfile
import json
import csv
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
import io


DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class BulkDataSource:
    """Information about a bulk data source."""
    name: str
    description: str
    download_url: str
    format: str  # csv, json, xml
    update_frequency: str


# Available bulk data sources
BULK_SOURCES = {
    "sam_entities": BulkDataSource(
        name="SAM.gov Entity Extracts",
        description="All active entity registrations with addresses, business types, POCs",
        download_url="https://sam.gov/data-services/entity-registration/public-extracts",
        format="csv",
        update_frequency="Daily (2AM ET)"
    ),
    "sam_exclusions": BulkDataSource(
        name="SAM.gov Exclusions",
        description="Debarred and suspended entities",
        download_url="https://sam.gov/data-services/exclusions/public-extracts",
        format="csv",
        update_frequency="Daily"
    ),
    "usaspending_contracts": BulkDataSource(
        name="USASpending Contract Awards",
        description="All federal contract awards",
        download_url="https://files.usaspending.gov/generated_downloads/",
        format="csv",
        update_frequency="Daily"
    ),
    "fpds_awards": BulkDataSource(
        name="FPDS Contract Actions",
        description="Detailed contract actions and modifications",
        download_url="https://www.fpds.gov/",
        format="xml",
        update_frequency="Daily"
    )
}


class BulkDataManager:
    """Manages bulk data downloads and local storage."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 min timeout for large files

    def list_sources(self) -> list[BulkDataSource]:
        """List available bulk data sources."""
        return list(BULK_SOURCES.values())

    def get_local_data_path(self, source_name: str) -> Path:
        """Get path to local data file for a source."""
        return self.data_dir / source_name

    def get_last_download_time(self, source_name: str) -> Optional[datetime]:
        """Get when data was last downloaded."""
        path = self.get_local_data_path(source_name)
        meta_file = path / "metadata.json"
        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
                return datetime.fromisoformat(meta.get("downloaded_at", ""))
        return None

    async def download_sam_exclusions(self) -> Path:
        """
        Download SAM.gov exclusions data.

        The exclusions list is smaller and available as direct download.
        """
        source_dir = self.get_local_data_path("sam_exclusions")
        source_dir.mkdir(parents=True, exist_ok=True)

        # SAM.gov provides exclusions as a downloadable file
        # Note: Actual URL requires authentication, this is a placeholder
        url = "https://sam.gov/api/prod/fileextractservices/v1/api/download/Exclusion/CSV"

        try:
            response = await self.client.get(url)
            response.raise_for_status()

            # Save the file
            output_file = source_dir / "exclusions.csv"
            output_file.write_bytes(response.content)

            # Save metadata
            self._save_metadata(source_dir, {
                "source": "SAM.gov Exclusions",
                "downloaded_at": datetime.now().isoformat(),
                "file": str(output_file)
            })

            return output_file

        except Exception as e:
            print(f"Error downloading SAM exclusions: {e}")
            return None

    async def download_usaspending_monthly(self, year: int, month: int) -> Path:
        """
        Download USASpending monthly contract data.

        USASpending provides pre-generated monthly files.
        """
        source_dir = self.get_local_data_path("usaspending_contracts")
        source_dir.mkdir(parents=True, exist_ok=True)

        # USASpending monthly archive URL pattern
        filename = f"FY{year}_{month:02d}_Contracts_Full.zip"
        url = f"https://files.usaspending.gov/generated_downloads/{filename}"

        try:
            print(f"Downloading {url}...")
            response = await self.client.get(url)
            response.raise_for_status()

            # Save the zip file
            zip_path = source_dir / filename
            zip_path.write_bytes(response.content)

            # Extract CSV files
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(source_dir)

            # Save metadata
            self._save_metadata(source_dir, {
                "source": "USASpending Monthly Contracts",
                "downloaded_at": datetime.now().isoformat(),
                "year": year,
                "month": month,
                "file": str(zip_path)
            })

            return source_dir

        except Exception as e:
            print(f"Error downloading USASpending data: {e}")
            return None

    def _save_metadata(self, source_dir: Path, metadata: dict):
        """Save download metadata."""
        meta_file = source_dir / "metadata.json"
        with open(meta_file, "w") as f:
            json.dump(metadata, f, indent=2)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


class LocalDataStore:
    """Query local bulk data files."""

    # SAM Entity file field positions (pipe-delimited)
    ENTITY_FIELDS = {
        "uei": 0,
        "duns": 1,
        "cage_code": 4,
        "registration_status": 5,
        "registration_type": 6,
        "registration_date": 7,
        "expiration_date": 8,
        "last_update_date": 9,
        "activation_date": 10,
        "legal_name": 11,
        "dba_name": 12,
        "address1": 15,
        "address2": 16,
        "city": 17,
        "state": 18,
        "zip": 19,
        "zip_ext": 20,
        "country": 21,
        "congressional_district": 22,
        "entity_start_date": 24,
        "fiscal_year_end": 25,
        "entity_url": 26,
        "entity_structure": 27,
        "state_of_incorporation": 28,
        "country_of_incorporation": 29,
    }

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DATA_DIR
        self._entity_index: dict[str, dict] = {}  # UEI -> entity dict
        self._entity_index_loaded = False
        self._exclusions_index: dict[str, list] = {}  # UEI -> exclusions
        self._exclusions_loaded = False

    def _get_index_cache_path(self) -> Path:
        """Get path to pickled entity index."""
        return self.data_dir / "entity_index.pkl"

    def _load_entity_index(self) -> None:
        """Load entity index from pickle cache or build from source."""
        import pickle

        if self._entity_index_loaded:
            return

        cache_path = self._get_index_cache_path()
        entity_file = self._find_entity_file()

        # Check if cache exists and is newer than source
        if cache_path.exists() and entity_file:
            cache_mtime = cache_path.stat().st_mtime
            source_mtime = entity_file.stat().st_mtime
            if cache_mtime > source_mtime:
                try:
                    print("Loading entity index from cache...", end="", flush=True)
                    with open(cache_path, 'rb') as f:
                        self._entity_index = pickle.load(f)
                    print(f" {len(self._entity_index):,} entities loaded")
                    self._entity_index_loaded = True
                    return
                except Exception as e:
                    print(f" cache invalid ({e}), rebuilding...")
                    pass  # Fall through to rebuild

        # Build index from source file
        if not entity_file:
            self._entity_index_loaded = True
            return

        print("Building entity index (one-time operation)...", end="", flush=True)
        count = 0
        with open(entity_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                entity = self._parse_entity_line(line)
                if entity and entity.get("uei"):
                    self._entity_index[entity["uei"]] = entity
                    count += 1
                    if count % 100000 == 0:
                        print(f" {count//1000}K...", end="", flush=True)

        print(f" {count} entities indexed")

        # Save to pickle cache
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(self._entity_index, f)
            print(f"  Index cached to {cache_path}")
        except Exception as e:
            print(f"  Warning: Could not cache index: {e}")

        self._entity_index_loaded = True

    def _find_entity_file(self) -> Optional[Path]:
        """Find the most recent entity data file."""
        entity_dir = self.data_dir / "sam_entities"
        if not entity_dir.exists():
            return None
        # Find most recent .dat file
        dat_files = sorted(entity_dir.glob("SAM_PUBLIC_MONTHLY_V2_*.dat"), reverse=True)
        return dat_files[0] if dat_files else None

    def _find_exclusions_file(self) -> Optional[Path]:
        """Find the exclusions CSV file."""
        exclusions_dir = self.data_dir / "sam_exclusions"
        if not exclusions_dir.exists():
            return None
        # Look for any CSV file matching the pattern
        for f in exclusions_dir.glob("SAM_Exclusions*.CSV"):
            return f
        for f in exclusions_dir.glob("*.csv"):
            return f
        return None

    def _parse_entity_line(self, line: str) -> Optional[dict]:
        """Parse a single entity line from the DAT file."""
        if line.startswith("BOF ") or not line.strip():
            return None
        # Remove the !end marker
        line = line.replace("!end", "").strip()
        fields = line.split("|")
        if len(fields) < 30:
            return None

        return {
            "uei": fields[self.ENTITY_FIELDS["uei"]],
            "cage_code": fields[self.ENTITY_FIELDS["cage_code"]],
            "legal_name": fields[self.ENTITY_FIELDS["legal_name"]],
            "dba_name": fields[self.ENTITY_FIELDS["dba_name"]] if len(fields) > 12 else "",
            "registration_status": fields[self.ENTITY_FIELDS["registration_status"]],
            "registration_date": fields[self.ENTITY_FIELDS["registration_date"]],
            "expiration_date": fields[self.ENTITY_FIELDS["expiration_date"]],
            "address": fields[self.ENTITY_FIELDS["address1"]],
            "city": fields[self.ENTITY_FIELDS["city"]],
            "state": fields[self.ENTITY_FIELDS["state"]],
            "zip": fields[self.ENTITY_FIELDS["zip"]],
            "country": fields[self.ENTITY_FIELDS["country"]],
            "entity_url": fields[self.ENTITY_FIELDS["entity_url"]] if len(fields) > 26 else "",
            "state_of_incorporation": fields[self.ENTITY_FIELDS["state_of_incorporation"]] if len(fields) > 28 else "",
        }

    def search_entities(self, name: Optional[str] = None, uei: Optional[str] = None,
                        cage_code: Optional[str] = None, state: Optional[str] = None,
                        limit: int = 10) -> list[dict]:
        """Search local entity data."""
        entity_file = self._find_entity_file()
        if not entity_file:
            return []

        results = []
        name_lower = name.lower() if name else None

        with open(entity_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                entity = self._parse_entity_line(line)
                if not entity:
                    continue

                # Filter by UEI (exact match)
                if uei and entity["uei"] != uei:
                    continue

                # Filter by CAGE code (exact match)
                if cage_code and entity["cage_code"] != cage_code:
                    continue

                # Filter by state (exact match)
                if state and entity["state"] != state:
                    continue

                # Filter by name (partial match)
                if name_lower:
                    entity_name = entity["legal_name"].lower()
                    dba = entity.get("dba_name", "").lower()
                    if name_lower not in entity_name and name_lower not in dba:
                        continue

                results.append(entity)
                if len(results) >= limit:
                    break

        return results

    def get_entity_by_uei(self, uei: str) -> Optional[dict]:
        """Get a specific entity by UEI (O(1) lookup from index)."""
        self._load_entity_index()
        return self._entity_index.get(uei)

    def search_exclusions(self, name: Optional[str] = None, uei: Optional[str] = None, limit: int = 100) -> list[dict]:
        """Search local exclusions data."""
        exclusions_file = self._find_exclusions_file()
        if not exclusions_file:
            return []

        results = []
        with open(exclusions_file, newline='', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Check by name (can be in Name, First+Last, or various name fields)
                if name:
                    name_lower = name.lower()
                    row_name = row.get("Name", "").lower()
                    first_last = f"{row.get('First', '')} {row.get('Last', '')}".lower().strip()
                    if name_lower in row_name or name_lower in first_last:
                        results.append(row)
                        if len(results) >= limit:
                            break
                        continue
                # Check by UEI
                if uei:
                    if uei == row.get("Unique Entity ID", ""):
                        results.append(row)
                        if len(results) >= limit:
                            break

        return results

    def check_exclusion(self, name: Optional[str] = None, uei: Optional[str] = None) -> dict:
        """Check if an entity is excluded."""
        results = self.search_exclusions(name=name, uei=uei, limit=10)
        return {
            "is_excluded": len(results) > 0,
            "count": len(results),
            "exclusions": results
        }

    def search_contracts(
        self,
        recipient_name: Optional[str] = None,
        agency: Optional[str] = None,
        min_value: Optional[float] = None
    ) -> list[dict]:
        """Search local contract data."""
        contracts_dir = self.data_dir / "usaspending_contracts"
        if not contracts_dir.exists():
            return []

        results = []

        # Find all CSV files
        for csv_file in contracts_dir.glob("*.csv"):
            with open(csv_file, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Apply filters
                    if recipient_name:
                        if recipient_name.lower() not in row.get("recipient_name", "").lower():
                            continue
                    if agency:
                        if agency.lower() not in row.get("awarding_agency_name", "").lower():
                            continue
                    if min_value:
                        try:
                            if float(row.get("total_obligation", 0)) < min_value:
                                continue
                        except ValueError:
                            continue

                    results.append(row)

                    # Limit results
                    if len(results) >= 1000:
                        return results

        return results


# Quick reference for manual bulk downloads
DOWNLOAD_INSTRUCTIONS = """
# Bulk Data Download Instructions

## SAM.gov Entity Data (Recommended for entity lookups)
1. Go to: https://sam.gov/data-services/entity-registration/public-extracts
2. Sign in with Login.gov
3. Download "SAM Entity Management Public Extract" (updated daily)
4. Extract to: data/sam_entities/

## SAM.gov Exclusions (Debarred entities)
1. Go to: https://sam.gov/data-services/exclusions/public-extracts
2. Download the CSV file
3. Save to: data/sam_exclusions/exclusions.csv

## USASpending Contract Data
1. Go to: https://www.usaspending.gov/download_center/custom_award_data
2. Select "Contracts" and desired filters
3. Download and extract to: data/usaspending_contracts/

## FPDS Detailed Contract Data
1. Go to: https://www.fpds.gov/fpdsng_cms/index.php/en/reports.html
2. Generate ATOM feed or use bulk data
3. Save to: data/fpds/

After downloading, the LocalDataStore class can query the local files.
"""


def print_download_instructions():
    """Print instructions for manual bulk data download."""
    print(DOWNLOAD_INSTRUCTIONS)


if __name__ == "__main__":
    print_download_instructions()
