"""
SAM.gov API Client

Provides access to federal contractor registration and exclusion data.
Entity API: https://open.gsa.gov/api/entity-api/
Exclusions API: https://open.gsa.gov/api/exclusions-api/
"""

import httpx
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import os


ENTITY_API_BASE = "https://api.sam.gov/entity-information/v3/entities"
EXCLUSIONS_API_BASE = "https://api.sam.gov/entity-information/v4/exclusions"


@dataclass
class EntityRegistration:
    """SAM.gov entity registration record."""
    uei: str  # Unique Entity ID
    legal_name: str
    dba_name: str
    cage_code: str
    registration_date: str
    expiration_date: str
    active_date: str
    physical_address: str
    physical_city: str
    physical_state: str
    physical_zip: str
    mailing_address: str
    mailing_city: str
    mailing_state: str
    mailing_zip: str
    business_types: list[str]
    naics_codes: list[str]
    psc_codes: list[str]
    organization_structure: str
    state_of_incorporation: str
    country_of_incorporation: str
    congressional_district: str
    entity_url: str

    # Points of contact
    gov_business_poc_name: str
    gov_business_poc_email: str
    electronic_business_poc_name: str
    electronic_business_poc_email: str


@dataclass
class Exclusion:
    """SAM.gov exclusion (debarment) record."""
    uei: str
    name: str
    exclusion_type: str  # Ineligible, Prohibition/Restriction, etc.
    exclusion_program: str  # Reciprocal, NonProcurement, Procurement
    agency: str
    ct_code: str  # Cause and Treatment code
    active_date: str
    termination_date: str
    description: str
    address: str
    city: str
    state: str
    zip_code: str


@dataclass
class EntitySearchResult:
    """Search result from SAM.gov Entity API."""
    entities: list[EntityRegistration]
    total_count: int
    has_next: bool


class SAMGovClient:
    """Client for SAM.gov APIs."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SAM_GOV_API_KEY")

        # SAM.gov requires API key in X-API-Key header
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        self.entity_client = httpx.AsyncClient(
            timeout=30.0,
            headers=headers
        )
        self.exclusions_client = httpx.AsyncClient(
            timeout=30.0,
            headers=headers
        )

    async def search_entities(
        self,
        uei: Optional[str] = None,
        legal_name: Optional[str] = None,
        cage_code: Optional[str] = None,
        state: Optional[str] = None,
        naics_code: Optional[str] = None,
        registration_status: str = "A",  # A=Active
        page: int = 0,
        size: int = 100
    ) -> EntitySearchResult:
        """
        Search for registered entities in SAM.gov.

        Args:
            uei: Unique Entity ID
            legal_name: Entity legal name (partial match)
            cage_code: CAGE code
            state: State code (e.g., "CA")
            naics_code: NAICS code
            registration_status: A=Active, E=Expired, W=Work in Progress
            page: Page number (0-indexed)
            size: Results per page

        Returns:
            EntitySearchResult with matching entities
        """
        params = {
            "registrationStatus": registration_status,
            "page": page,
            "size": size
        }
        if uei:
            params["ueiSAM"] = uei
        if legal_name:
            params["legalBusinessName"] = legal_name
        if cage_code:
            params["cageCode"] = cage_code
        if state:
            params["physicalAddressStateOrProvinceCode"] = state
        if naics_code:
            params["naicsCode"] = naics_code

        response = await self.entity_client.get(ENTITY_API_BASE, params=params)

        # Handle API errors gracefully
        if response.status_code in (400, 401, 403, 429):
            # Return empty result if bad request, API key invalid, or rate limited
            return EntitySearchResult(entities=[], total_count=0, has_next=False)

        response.raise_for_status()
        data = response.json()

        # Check for rate limit in response body (SAM.gov returns 200 with error)
        if isinstance(data, dict) and data.get("code") == "900804":
            return EntitySearchResult(entities=[], total_count=0, has_next=False)

        entities = []
        for entity in data.get("entityData", []):
            core = entity.get("coreData", {})
            registration = core.get("entityInformation", {})
            physical = core.get("physicalAddress", {})
            mailing = core.get("mailingAddress", {})
            business = entity.get("assertions", {}).get("businessTypes", {}).get("businessTypeList", [])
            pocs = entity.get("pointsOfContact", {})

            entities.append(EntityRegistration(
                uei=registration.get("ueiSAM", ""),
                legal_name=registration.get("legalBusinessName", ""),
                dba_name=registration.get("dbaName", ""),
                cage_code=registration.get("cageCode", ""),
                registration_date=registration.get("registrationDate", ""),
                expiration_date=registration.get("expirationDate", ""),
                active_date=registration.get("activeDate", ""),
                physical_address=physical.get("addressLine1", ""),
                physical_city=physical.get("city", ""),
                physical_state=physical.get("stateOrProvinceCode", ""),
                physical_zip=physical.get("zipCode", ""),
                mailing_address=mailing.get("addressLine1", ""),
                mailing_city=mailing.get("city", ""),
                mailing_state=mailing.get("stateOrProvinceCode", ""),
                mailing_zip=mailing.get("zipCode", ""),
                business_types=[b.get("businessTypeDescription", "") for b in business],
                naics_codes=self._extract_naics(entity),
                psc_codes=self._extract_psc(entity),
                organization_structure=registration.get("organizationStructure", ""),
                state_of_incorporation=registration.get("stateOfIncorporation", ""),
                country_of_incorporation=registration.get("countryOfIncorporation", ""),
                congressional_district=physical.get("congressionalDistrict", ""),
                entity_url=registration.get("entityURL", ""),
                gov_business_poc_name=pocs.get("governmentBusinessPOC", {}).get("firstName", "") + " " + pocs.get("governmentBusinessPOC", {}).get("lastName", ""),
                gov_business_poc_email=pocs.get("governmentBusinessPOC", {}).get("email", ""),
                electronic_business_poc_name=pocs.get("electronicBusinessPOC", {}).get("firstName", "") + " " + pocs.get("electronicBusinessPOC", {}).get("lastName", ""),
                electronic_business_poc_email=pocs.get("electronicBusinessPOC", {}).get("email", "")
            ))

        return EntitySearchResult(
            entities=entities,
            total_count=data.get("totalRecords", 0),
            has_next=len(entities) == size
        )

    def _extract_naics(self, entity: dict) -> list[str]:
        """Extract NAICS codes from entity data."""
        goods = entity.get("assertions", {}).get("goodsAndServices", {})
        naics_list = goods.get("naicsList", [])
        return [n.get("naicsCode", "") for n in naics_list]

    def _extract_psc(self, entity: dict) -> list[str]:
        """Extract PSC codes from entity data."""
        goods = entity.get("assertions", {}).get("goodsAndServices", {})
        psc_list = goods.get("pscList", [])
        return [p.get("pscCode", "") for p in psc_list]

    async def get_entity_by_uei(self, uei: str) -> Optional[EntityRegistration]:
        """Get a specific entity by UEI."""
        result = await self.search_entities(uei=uei)
        return result.entities[0] if result.entities else None

    async def check_exclusions(
        self,
        uei: Optional[str] = None,
        name: Optional[str] = None,
        cage_code: Optional[str] = None
    ) -> list[Exclusion]:
        """
        Check if an entity is excluded (debarred) from federal contracting.

        Args:
            uei: Unique Entity ID
            name: Entity name (partial match)
            cage_code: CAGE code

        Returns:
            List of active exclusions
        """
        params = {}

        if uei:
            params["ueiSAM"] = uei
        if name:
            params["q"] = name
        if cage_code:
            params["cageCode"] = cage_code

        response = await self.exclusions_client.get(EXCLUSIONS_API_BASE, params=params)

        # Handle API errors gracefully
        if response.status_code in (400, 401, 403, 404, 429):
            return []

        response.raise_for_status()
        data = response.json()

        # Check for rate limit in response body (SAM.gov returns 200 with error)
        if isinstance(data, dict) and data.get("code") == "900804":
            return []

        exclusions = []
        for exc in data.get("results", []):
            exclusions.append(Exclusion(
                uei=exc.get("ueiSAM", ""),
                name=exc.get("name", ""),
                exclusion_type=exc.get("exclusionType", ""),
                exclusion_program=exc.get("exclusionProgram", ""),
                agency=exc.get("excludingAgency", ""),
                ct_code=exc.get("ctCode", ""),
                active_date=exc.get("activeDate", ""),
                termination_date=exc.get("terminationDate", ""),
                description=exc.get("description", ""),
                address=exc.get("addressLine1", ""),
                city=exc.get("city", ""),
                state=exc.get("stateOrProvince", ""),
                zip_code=exc.get("zipCode", "")
            ))

        return exclusions

    async def get_registration_age_days(self, uei: str) -> Optional[int]:
        """Get how many days ago an entity registered in SAM.gov."""
        entity = await self.get_entity_by_uei(uei)
        if not entity or not entity.registration_date:
            return None

        reg_date = datetime.strptime(entity.registration_date, "%Y-%m-%d")
        return (datetime.now() - reg_date).days

    async def find_shared_address_entities(
        self,
        address: str,
        city: str,
        state: str
    ) -> list[EntityRegistration]:
        """Find all entities registered at the same address."""
        # Note: SAM.gov API doesn't support direct address search
        # This would require iterating through results - simplified version
        result = await self.search_entities(state=state, size=1000)

        return [
            e for e in result.entities
            if e.physical_address.lower() == address.lower()
            and e.physical_city.lower() == city.lower()
        ]

    async def close(self):
        """Close HTTP clients."""
        await self.entity_client.aclose()
        await self.exclusions_client.aclose()


# Example usage
async def demo():
    client = SAMGovClient()

    # Search for entities
    result = await client.search_entities(
        legal_name="Lockheed",
        state="MD"
    )

    print(f"Found {result.total_count} entities")
    for entity in result.entities[:5]:
        print(f"  {entity.uei}: {entity.legal_name}")
        print(f"    Address: {entity.physical_address}, {entity.physical_city}, {entity.physical_state}")
        print(f"    Registered: {entity.registration_date}")

    # Check exclusions
    exclusions = await client.check_exclusions(name="test")
    print(f"\nFound {len(exclusions)} exclusions")

    await client.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())
