"""
USASpending.gov API Client

Provides access to federal contract, grant, and spending data.
API Documentation: https://api.usaspending.gov/
"""

import httpx
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta


BASE_URL = "https://api.usaspending.gov/api/v2"


@dataclass
class Contract:
    """Federal contract award."""
    contract_id: str
    piid: str  # Procurement Instrument Identifier
    agency: str
    agency_code: str
    recipient_name: str
    recipient_uei: str  # Unique Entity ID (replaced DUNS)
    recipient_address: str
    recipient_city: str
    recipient_state: str
    recipient_zip: str
    total_obligation: float
    base_and_all_options: float
    start_date: str
    end_date: str
    description: str
    naics_code: str
    naics_description: str
    psc_code: str  # Product Service Code
    competition_type: str
    number_of_offers: int
    contract_type: str
    awarding_office: str


@dataclass
class ContractSearchResult:
    """Search result from USASpending."""
    contracts: list[Contract]
    total_count: int
    page: int
    has_next: bool


class USASpendingClient:
    """Client for USASpending.gov API."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=30.0,
            headers={"Content-Type": "application/json"}
        )

    async def search_contracts(
        self,
        keywords: Optional[str] = None,
        agency: Optional[str] = None,
        recipient_name: Optional[str] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        naics_codes: Optional[list[str]] = None,
        page: int = 1,
        limit: int = 100,
    ) -> ContractSearchResult:
        """
        Search for federal contracts.

        Args:
            keywords: Search terms
            agency: Agency name or code
            recipient_name: Contractor name
            min_value: Minimum contract value
            max_value: Maximum contract value
            start_date: Award date start (YYYY-MM-DD)
            end_date: Award date end (YYYY-MM-DD)
            naics_codes: NAICS industry codes
            page: Page number
            limit: Results per page

        Returns:
            ContractSearchResult with matching contracts
        """
        filters = {"award_type_codes": ["A", "B", "C", "D"]}  # Contracts only

        if keywords:
            filters["keywords"] = [keywords]
        if agency:
            filters["agencies"] = [{"type": "awarding", "tier": "toptier", "name": agency}]
        if recipient_name:
            filters["recipient_search_text"] = recipient_name
        if min_value or max_value:
            filters["award_amounts"] = [
                {"lower_bound": min_value or 0, "upper_bound": max_value or 999999999999}
            ]
        if start_date or end_date:
            filters["time_period"] = [{
                "start_date": start_date or "2000-01-01",
                "end_date": end_date or datetime.now().strftime("%Y-%m-%d")
            }]
        if naics_codes:
            filters["naics_codes"] = naics_codes

        # Always require a time period to avoid empty filter errors
        if "time_period" not in filters:
            filters["time_period"] = [{
                "start_date": start_date or "2020-01-01",
                "end_date": end_date or datetime.now().strftime("%Y-%m-%d")
            }]

        payload = {
            "filters": filters,
            "fields": [
                "Award ID", "Recipient Name", "Recipient UEI",
                "Award Amount", "Total Outlays", "Description",
                "Start Date", "End Date", "Awarding Agency", "Awarding Sub Agency",
                "recipient_id", "Place of Performance City", "Place of Performance State"
            ],
            "page": page,
            "limit": limit,
            "sort": "Award Amount",
            "order": "desc"
        }

        response = await self.client.post("/search/spending_by_award/", json=payload)

        # Handle API errors gracefully
        if response.status_code in (400, 422):
            return ContractSearchResult(contracts=[], total_count=0, page=page, has_next=False)

        response.raise_for_status()
        data = response.json()

        contracts = []
        for result in data.get("results", []):
            contracts.append(Contract(
                contract_id=result.get("Award ID", ""),
                piid=result.get("Award ID", ""),
                agency=result.get("Awarding Agency", ""),
                agency_code="",
                recipient_name=result.get("Recipient Name", ""),
                recipient_uei=result.get("Recipient UEI", ""),
                recipient_address="",
                recipient_city=result.get("Place of Performance City", ""),
                recipient_state=result.get("Place of Performance State", ""),
                recipient_zip="",
                total_obligation=float(result.get("Award Amount", 0) or 0),
                base_and_all_options=0,
                start_date=result.get("Start Date", ""),
                end_date=result.get("End Date", ""),
                description=result.get("Description", ""),
                naics_code="",
                naics_description="",
                psc_code="",
                competition_type="",
                number_of_offers=0,
                contract_type="",
                awarding_office=""
            ))

        return ContractSearchResult(
            contracts=contracts,
            total_count=data.get("page_metadata", {}).get("total", 0),
            page=page,
            has_next=data.get("page_metadata", {}).get("hasNext", False)
        )

    async def get_contract_details(self, award_id: str) -> Optional[Contract]:
        """Get detailed information about a specific contract."""
        # First try direct lookup (requires internal ID)
        response = await self.client.get(f"/awards/{award_id}/")
        if response.status_code == 404 or response.status_code == 400:
            # Fall back to searching by Award ID (PIID)
            result = await self.search_contracts(keywords=award_id, limit=1)
            if result.contracts:
                return result.contracts[0]
            return None
        response.raise_for_status()
        data = response.json()

        recipient = data.get("recipient", {})
        location = recipient.get("location", {})

        return Contract(
            contract_id=data.get("id", ""),
            piid=data.get("piid", ""),
            agency=data.get("awarding_agency", {}).get("toptier_agency", {}).get("name", ""),
            agency_code=data.get("awarding_agency", {}).get("toptier_agency", {}).get("code", ""),
            recipient_name=recipient.get("recipient_name", ""),
            recipient_uei=recipient.get("recipient_uei", ""),
            recipient_address=location.get("address_line1", ""),
            recipient_city=location.get("city_name", ""),
            recipient_state=location.get("state_code", ""),
            recipient_zip=location.get("zip5", ""),
            total_obligation=float(data.get("total_obligation", 0) or 0),
            base_and_all_options=float(data.get("base_and_all_options_value", 0) or 0),
            start_date=data.get("period_of_performance_start_date", ""),
            end_date=data.get("period_of_performance_current_end_date", ""),
            description=data.get("description", ""),
            naics_code=data.get("naics", ""),
            naics_description=data.get("naics_description", ""),
            psc_code=data.get("psc_code", ""),
            competition_type=data.get("type_of_contract_pricing", ""),
            number_of_offers=data.get("number_of_offers_received", 0) or 0,
            contract_type=data.get("type", ""),
            awarding_office=data.get("awarding_agency", {}).get("office_agency_name", "")
        )

    async def get_recipient_awards(self, recipient_uei: str, limit: int = 50) -> list[Contract]:
        """Get all awards to a specific recipient by UEI."""
        return (await self.search_contracts(
            recipient_name=recipient_uei,
            limit=limit
        )).contracts

    async def get_recent_contracts(
        self,
        days: int = 7,
        min_value: float = 100000,
        agency: Optional[str] = None
    ) -> list[Contract]:
        """Get contracts awarded in the last N days."""
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        result = await self.search_contracts(
            start_date=start_date,
            end_date=end_date,
            min_value=min_value,
            agency=agency,
            limit=100
        )
        return result.contracts

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Example usage
async def demo():
    client = USASpendingClient()

    # Search for recent DOD contracts
    contracts = await client.get_recent_contracts(
        days=7,
        min_value=1000000,
        agency="Department of Defense"
    )

    print(f"Found {len(contracts)} contracts")
    for c in contracts[:5]:
        print(f"  {c.contract_id}: {c.recipient_name} - ${c.total_obligation:,.0f}")

    await client.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())
