"""
SEC EDGAR API Client

Provides access to public company filings from the SEC.
Useful for verifying company legitimacy and finding ownership information.
API Documentation: https://www.sec.gov/search-filings/edgar-search-tools
"""

import httpx
from dataclasses import dataclass
from typing import Optional
import re


# SEC requires a User-Agent header with contact info
USER_AGENT = "FedWatchAI fraud-detection research@example.com"

BASE_URL = "https://www.sec.gov"
DATA_URL = "https://data.sec.gov"
COMPANY_SEARCH_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"


@dataclass
class SECCompany:
    """SEC registered company."""
    cik: str  # Central Index Key
    name: str
    ticker: Optional[str]
    sic_code: str  # Standard Industrial Classification
    sic_description: str
    state_of_incorporation: str
    business_address: str
    mailing_address: str
    fiscal_year_end: str


@dataclass
class SECFiling:
    """SEC filing record."""
    accession_number: str
    form_type: str  # 10-K, 10-Q, 8-K, etc.
    filing_date: str
    description: str
    document_url: str


class SECEdgarClient:
    """Client for SEC EDGAR database."""

    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": USER_AGENT}
        )

    async def search_companies(
        self,
        company_name: str,
        limit: int = 10
    ) -> list[SECCompany]:
        """
        Search for companies in SEC database by name.

        Args:
            company_name: Company name to search
            limit: Max results to return

        Returns:
            List of matching companies
        """
        # Use the company tickers JSON endpoint
        response = await self.client.get(
            f"{BASE_URL}/files/company_tickers.json"
        )

        if response.status_code != 200:
            return []
        response.raise_for_status()
        data = response.json()

        # Search through company names
        search_lower = company_name.lower()
        matches = []

        for entry in data.values():
            name = entry.get("title", "")
            if search_lower in name.lower():
                matches.append({
                    "cik": str(entry.get("cik_str", "")).zfill(10),
                    "name": name,
                    "ticker": entry.get("ticker")
                })
                if len(matches) >= limit:
                    break

        # Get full details for matches
        companies = []
        for match in matches[:limit]:
            try:
                details = await self.get_company_details(match["cik"])
                if details:
                    companies.append(details)
            except Exception:
                # If we can't get details, create basic record
                companies.append(SECCompany(
                    cik=match["cik"],
                    name=match["name"],
                    ticker=match["ticker"],
                    sic_code="",
                    sic_description="",
                    state_of_incorporation="",
                    business_address="",
                    mailing_address="",
                    fiscal_year_end=""
                ))

        return companies

    async def get_company_details(self, cik: str) -> Optional[SECCompany]:
        """
        Get detailed company information by CIK.

        Args:
            cik: Central Index Key (10-digit, zero-padded)

        Returns:
            Company details or None if not found
        """
        # Ensure CIK is zero-padded to 10 digits
        cik = str(cik).zfill(10)

        response = await self.client.get(
            f"{DATA_URL}/submissions/CIK{cik}.json"
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        data = response.json()

        addresses = data.get("addresses", {})
        business = addresses.get("business", {})
        mailing = addresses.get("mailing", {})

        business_addr = f"{business.get('street1', '')} {business.get('street2', '')}, {business.get('city', '')}, {business.get('stateOrCountry', '')} {business.get('zipCode', '')}".strip()
        mailing_addr = f"{mailing.get('street1', '')} {mailing.get('street2', '')}, {mailing.get('city', '')}, {mailing.get('stateOrCountry', '')} {mailing.get('zipCode', '')}".strip()

        return SECCompany(
            cik=cik,
            name=data.get("name", ""),
            ticker=data.get("tickers", [None])[0] if data.get("tickers") else None,
            sic_code=data.get("sic", ""),
            sic_description=data.get("sicDescription", ""),
            state_of_incorporation=data.get("stateOfIncorporation", ""),
            business_address=business_addr,
            mailing_address=mailing_addr,
            fiscal_year_end=data.get("fiscalYearEnd", "")
        )

    async def get_recent_filings(
        self,
        cik: str,
        form_types: Optional[list[str]] = None,
        limit: int = 10
    ) -> list[SECFiling]:
        """
        Get recent SEC filings for a company.

        Args:
            cik: Central Index Key
            form_types: Filter by form type (10-K, 10-Q, 8-K, etc.)
            limit: Max filings to return

        Returns:
            List of recent filings
        """
        cik = str(cik).zfill(10)

        response = await self.client.get(
            f"{DATA_URL}/submissions/CIK{cik}.json"
        )

        if response.status_code == 404:
            return []

        response.raise_for_status()
        data = response.json()

        filings_data = data.get("filings", {}).get("recent", {})
        forms = filings_data.get("form", [])
        dates = filings_data.get("filingDate", [])
        accessions = filings_data.get("accessionNumber", [])
        descriptions = filings_data.get("primaryDocument", [])

        filings = []
        for i in range(min(len(forms), limit * 2)):  # Get more to filter
            form_type = forms[i] if i < len(forms) else ""

            # Filter by form type if specified
            if form_types and form_type not in form_types:
                continue

            accession = accessions[i] if i < len(accessions) else ""
            accession_formatted = accession.replace("-", "")

            filings.append(SECFiling(
                accession_number=accession,
                form_type=form_type,
                filing_date=dates[i] if i < len(dates) else "",
                description=descriptions[i] if i < len(descriptions) else "",
                document_url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession_formatted}/{descriptions[i] if i < len(descriptions) else ''}"
            ))

            if len(filings) >= limit:
                break

        return filings

    async def check_if_public_company(self, company_name: str) -> dict:
        """
        Check if a company is publicly traded (has SEC filings).

        Args:
            company_name: Company name to check

        Returns:
            Dict with is_public, company details, and recent filings
        """
        companies = await self.search_companies(company_name, limit=3)

        if not companies:
            return {
                "is_public": False,
                "company": None,
                "filings": [],
                "note": "No SEC filings found - likely private company"
            }

        # Get the best match
        company = companies[0]

        # Get recent 10-K and 10-Q filings
        filings = await self.get_recent_filings(
            company.cik,
            form_types=["10-K", "10-Q", "8-K"],
            limit=5
        )

        return {
            "is_public": True,
            "company": {
                "cik": company.cik,
                "name": company.name,
                "ticker": company.ticker,
                "sic_code": company.sic_code,
                "sic_description": company.sic_description,
                "state_of_incorporation": company.state_of_incorporation,
                "business_address": company.business_address
            },
            "filings": [
                {
                    "form": f.form_type,
                    "date": f.filing_date,
                    "url": f.document_url
                }
                for f in filings
            ],
            "note": "Public company with SEC filings"
        }

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Example usage
async def demo():
    client = SECEdgarClient()

    # Check if a company is public
    result = await client.check_if_public_company("Lockheed Martin")
    print(f"Is public: {result['is_public']}")
    if result['company']:
        print(f"Name: {result['company']['name']}")
        print(f"Ticker: {result['company']['ticker']}")
        print(f"State: {result['company']['state_of_incorporation']}")

    print(f"\nRecent filings:")
    for f in result['filings'][:3]:
        print(f"  {f['form']} - {f['date']}")

    await client.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())
