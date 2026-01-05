"""
FERRET - Federal Expenditure Review and Risk Evaluation Tool

An AI-native agent that autonomously investigates federal contracts for fraud indicators.
Uses Claude Agent SDK with specialized tools for investigation.
"""

import asyncio
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import asdict

from claude_agent_sdk import query, ClaudeAgentOptions
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from data_sources import USASpendingClient
from tools import FedWatchTools, TOOL_DEFINITIONS

load_dotenv()

console = Console()
PROJECT_ROOT = Path(__file__).parent


def format_tool_results(tools: FedWatchTools) -> str:
    """Format tool definitions for the agent prompt."""
    tool_docs = []
    for tool in TOOL_DEFINITIONS:
        params = tool["parameters"]["properties"]
        param_str = ", ".join([
            f"{k}: {v.get('type', 'any')}"
            for k, v in params.items()
        ])
        tool_docs.append(f"- **{tool['name']}**({param_str}): {tool['description']}")
    return "\n".join(tool_docs)


async def investigate_contract(contract_id: str, output_dir: Optional[Path] = None) -> dict:
    """
    Investigate a single federal contract for fraud indicators.

    This is the core AI-native function. The Claude agent autonomously:
    1. Fetches contract data
    2. Researches the contractor
    3. Analyzes fraud patterns
    4. Generates a risk assessment report
    """
    console.print(f"\n[bold blue]Investigating contract:[/bold blue] {contract_id}\n")

    # Initialize tools
    tools = FedWatchTools()

    # Get initial contract data
    usaspending = USASpendingClient()
    contract = await usaspending.get_contract_details(contract_id)
    await usaspending.close()

    if not contract:
        console.print(f"[red]Contract {contract_id} not found[/red]")
        return {"error": "Contract not found"}

    # Show contract summary
    table = Table(title="Contract Details")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Contract ID", contract.contract_id)
    table.add_row("Recipient", contract.recipient_name)
    table.add_row("UEI", contract.recipient_uei or "N/A")
    table.add_row("Value", f"${contract.total_obligation:,.0f}")
    table.add_row("Agency", contract.agency)
    table.add_row("Description", (contract.description or "")[:100] + "...")
    console.print(table)

    # If we have a UEI, do automated analysis first
    if contract.recipient_uei:
        console.print("\n[yellow]Running automated risk analysis...[/yellow]")

        risk_score = await tools.calculate_risk_score(contract.recipient_uei)
        patterns = await tools.analyze_contract_patterns(contract.recipient_uei)
        relationships = await tools.get_entity_relationships(contract.recipient_uei)
        exclusions = await tools.get_exclusions(contract.recipient_uei)

        # Show risk score
        risk_color = {
            "CRITICAL": "red",
            "HIGH": "red",
            "MEDIUM": "yellow",
            "LOW": "green"
        }.get(risk_score.risk_level, "white")

        console.print(Panel(
            f"[{risk_color}]Risk Score: {risk_score.total_score}/100 ({risk_score.risk_level})[/{risk_color}]\n\n{risk_score.summary}",
            title="Automated Risk Assessment"
        ))

        # Prepare context for agent
        context = {
            "contract": {
                "id": contract.contract_id,
                "recipient": contract.recipient_name,
                "uei": contract.recipient_uei,
                "value": contract.total_obligation,
                "agency": contract.agency,
                "description": contract.description,
                "competition": contract.competition_type,
                "offers": contract.number_of_offers
            },
            "risk_score": {
                "score": risk_score.total_score,
                "level": risk_score.risk_level,
                "factors": [asdict(f) for f in risk_score.factors]
            },
            "patterns": [asdict(p) for p in patterns],
            "relationships": [asdict(r) for r in relationships],
            "exclusions": exclusions
        }
    else:
        context = {
            "contract": {
                "id": contract.contract_id,
                "recipient": contract.recipient_name,
                "value": contract.total_obligation,
                "agency": contract.agency,
                "description": contract.description
            }
        }

    # Now use the agent for deeper investigation
    prompt = f"""You are investigating federal contract {contract_id} for fraud indicators.

## Initial Analysis Results

{json.dumps(context, indent=2)}

## Your Investigation Tasks

Based on the automated analysis above, conduct a deeper investigation:

1. **If high-risk factors were found:**
   - Use WebSearch to verify company existence and legitimacy
   - Search for news about fraud, lawsuits, or scandals
   - Verify the address (is it a virtual office?)

2. **If relationships were found:**
   - Investigate the related entities
   - Look for pass-through or shell company patterns

3. **If no UEI was available:**
   - Search for the company by name
   - Try to find their SAM.gov registration

4. **Generate your final assessment:**
   - Summarize all findings
   - Assign a final risk rating
   - Provide specific recommendations

## Output Format

```
=== INVESTIGATION REPORT ===

Contract: {contract_id}
Contractor: [name]
Value: $[amount]

AUTOMATED RISK SCORE: [score]/100 ([level])

INVESTIGATION FINDINGS:
[Your detailed findings from web research]

RED FLAGS:
- [List each red flag with evidence]

MITIGATING FACTORS:
- [Any factors that reduce concern]

FINAL RISK ASSESSMENT: [LOW/MEDIUM/HIGH/CRITICAL]

RECOMMENDATIONS:
- [Specific actions to take]

EVIDENCE:
- [URLs and sources]
```
"""

    result_text = ""

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Agent investigating...", total=None)

        async for message in query(
            prompt=prompt,
            options=ClaudeAgentOptions(
                cwd=str(PROJECT_ROOT),
                allowed_tools=["WebSearch", "WebFetch"],
                permission_mode="bypassPermissions"
            )
        ):
            if hasattr(message, 'result'):
                result_text = message.result

    await tools.close()

    # Display result
    console.print(Panel(result_text, title="Investigation Complete"))

    # Save report if output directory specified
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{contract_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_path.write_text(result_text)
        console.print(f"\n[green]Report saved to:[/green] {report_path}")

    return {"contract_id": contract_id, "report": result_text}


async def investigate_entity(entity_name: str) -> dict:
    """
    Investigate a specific contractor/entity for fraud indicators.
    """
    console.print(f"\n[bold blue]Investigating entity:[/bold blue] {entity_name}\n")

    tools = FedWatchTools()

    # Search for the entity
    console.print("[yellow]Searching for entity...[/yellow]")
    entities = await tools.search_entities(entity_name, limit=5)

    if not entities:
        console.print(f"[red]No entities found matching '{entity_name}'[/red]")
        await tools.close()
        return {"error": "Entity not found"}

    # Show matches
    table = Table(title="Matching Entities")
    table.add_column("UEI", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Location", style="yellow")
    table.add_column("Status", style="green")

    for e in entities:
        table.add_row(e.entity_id, e.name[:40], f"{e.city}, {e.state}", e.status)

    console.print(table)

    # Investigate the first match
    entity = entities[0]
    console.print(f"\n[yellow]Investigating {entity.name}...[/yellow]")

    # Get comprehensive data
    details = await tools.get_entity_details(entity.entity_id)
    contracts = await tools.get_entity_contracts(entity.entity_id)
    risk_score = await tools.calculate_risk_score(entity.entity_id)
    patterns = await tools.analyze_contract_patterns(entity.entity_id)
    relationships = await tools.get_entity_relationships(entity.entity_id)

    # Generate report
    report = await tools.generate_report(
        entity.entity_id,
        findings={
            "patterns": [asdict(p) for p in patterns],
            "relationships": [asdict(r) for r in relationships]
        }
    )

    await tools.close()

    console.print(Panel(report, title="Entity Investigation Report"))

    return {"entity_id": entity.entity_id, "report": report}


async def scan_recent_contracts(
    days: int = 7,
    min_value: float = 1000000,
    agency: Optional[str] = None,
    limit: int = 10
) -> list[dict]:
    """
    Scan recent contracts and flag suspicious ones.
    """
    console.print(f"\n[bold blue]Scanning contracts from last {days} days[/bold blue]")
    console.print(f"Minimum value: ${min_value:,.0f}")
    if agency:
        console.print(f"Agency: {agency}")

    # Fetch recent contracts
    client = USASpendingClient()
    contracts = await client.get_recent_contracts(
        days=days,
        min_value=min_value,
        agency=agency
    )
    await client.close()

    console.print(f"\nFound [bold]{len(contracts)}[/bold] contracts matching criteria\n")

    if not contracts:
        return []

    # Show contracts in a table
    table = Table(title="Recent High-Value Contracts")
    table.add_column("ID", style="cyan")
    table.add_column("Recipient", style="white")
    table.add_column("Value", style="green", justify="right")
    table.add_column("Agency", style="yellow")

    for c in contracts[:limit]:
        table.add_row(
            c.contract_id[:20],
            c.recipient_name[:30],
            f"${c.total_obligation:,.0f}",
            c.agency[:25]
        )

    console.print(table)

    # Run risk assessment on each
    console.print("\n[yellow]Running risk assessments...[/yellow]\n")

    tools = FedWatchTools()
    results = []

    for c in contracts[:limit]:
        if c.recipient_uei:
            try:
                risk = await tools.calculate_risk_score(c.recipient_uei, entity_name=c.recipient_name)
                results.append({
                    "contract_id": c.contract_id,
                    "recipient": c.recipient_name,
                    "value": c.total_obligation,
                    "risk_score": risk.total_score,
                    "risk_level": risk.risk_level,
                    "flags": len(risk.factors)
                })

                color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(risk.risk_level, "white")
                console.print(f"  [{color}]{c.recipient_name[:30]:30} | Risk: {risk.total_score:3}/100 ({risk.risk_level:8}) | {len(risk.factors)} flags[/{color}]")
            except Exception as e:
                console.print(f"  [dim]{c.recipient_name[:30]:30} | Error: {str(e)[:30]}[/dim]")

    await tools.close()

    # Summary
    high_risk = [r for r in results if r["risk_level"] in ["HIGH", "CRITICAL"]]
    if high_risk:
        console.print(f"\n[red bold]⚠ Found {len(high_risk)} high-risk contracts requiring investigation[/red bold]")
        for r in high_risk:
            console.print(f"  - {r['contract_id']}: {r['recipient']} (Score: {r['risk_score']})")

    return results


async def generate_report(contract_id: str, output_dir: str = "reports") -> Path:
    """Generate a formal investigation report for a contract."""
    result = await investigate_contract(contract_id, output_dir=Path(output_dir))
    return result


def main():
    parser = argparse.ArgumentParser(
        description="FERRET - Federal Expenditure Review and Risk Evaluation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Investigate a single contract:
    python agent.py investigate W912DY-23-C-0042

  Investigate a contractor by name:
    python agent.py entity "ACME CORP"

  Scan recent high-value contracts:
    python agent.py scan --days 7 --min-value 1000000

  Scan specific agency:
    python agent.py scan --agency "Department of Defense"

  Generate a report:
    python agent.py report W912DY-23-C-0042 --output reports/
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Investigate command
    investigate_parser = subparsers.add_parser("investigate", help="Investigate a specific contract")
    investigate_parser.add_argument("contract_id", help="Contract ID to investigate")
    investigate_parser.add_argument("--output", "-o", help="Output directory for report")

    # Entity command
    entity_parser = subparsers.add_parser("entity", help="Investigate a contractor by name")
    entity_parser.add_argument("name", help="Contractor name to investigate")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Scan recent contracts for fraud indicators")
    scan_parser.add_argument("--days", "-d", type=int, default=7, help="Days to look back")
    scan_parser.add_argument("--min-value", "-m", type=float, default=1000000, help="Minimum contract value")
    scan_parser.add_argument("--agency", "-a", help="Filter by agency")
    scan_parser.add_argument("--limit", "-l", type=int, default=10, help="Max contracts to screen")

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate an investigation report")
    report_parser.add_argument("contract_id", help="Contract ID")
    report_parser.add_argument("--output", "-o", default="reports", help="Output directory")

    # Daily scan command
    daily_parser = subparsers.add_parser("daily-scan", help="Scan recent contracts for fraud (bulk)")
    daily_parser.add_argument("--days", "-d", type=int, default=1, help="Days to look back (default: 1)")
    daily_parser.add_argument("--min-value", "-m", type=float, default=25000, help="Minimum contract value")
    daily_parser.add_argument("--agency", "-a", help="Filter by agency")
    daily_parser.add_argument("--threshold", "-t", default="LOW",
                              choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                              help="Minimum risk level to report")
    daily_parser.add_argument("--format", "-f", default="console",
                              choices=["console", "json", "csv"],
                              help="Output format")
    daily_parser.add_argument("--output", "-o", help="Output directory for reports")
    daily_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    daily_parser.add_argument("--deep", action="store_true",
                              help="Enable deep analysis (pricing, splitting, set-aside, bid rigging)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Run the appropriate command
    if args.command == "investigate":
        asyncio.run(investigate_contract(args.contract_id, args.output))
    elif args.command == "entity":
        asyncio.run(investigate_entity(args.name))
    elif args.command == "scan":
        asyncio.run(scan_recent_contracts(
            days=args.days,
            min_value=args.min_value,
            agency=args.agency,
            limit=args.limit
        ))
    elif args.command == "report":
        asyncio.run(generate_report(args.contract_id, args.output))
    elif args.command == "daily-scan":
        from daily_scan import DailyFraudScanner, format_console_report, save_json_report, save_csv_report
        from pathlib import Path

        async def run_daily_scan():
            scanner = DailyFraudScanner(verbose=args.verbose, deep_analysis=args.deep)
            if args.deep:
                console.print("[yellow]Deep analysis enabled - this may take longer[/yellow]")
            try:
                alerts, total_scanned = await scanner.scan(
                    days=args.days,
                    min_value=args.min_value,
                    agency=args.agency,
                    threshold=args.threshold
                )

                if args.format == "console":
                    console.print(format_console_report(
                        alerts,
                        args.days,
                        deep_analysis=args.deep,
                        total_scanned=total_scanned,
                        min_value=args.min_value
                    ))
                elif args.format == "json":
                    if args.output:
                        output_dir = Path(args.output)
                        output_dir.mkdir(parents=True, exist_ok=True)
                        output_file = output_dir / f"fraud_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                        save_json_report(alerts, output_file)
                        console.print(f"[green]Report saved to:[/green] {output_file}")
                    else:
                        import json as json_mod
                        from dataclasses import asdict
                        print(json_mod.dumps([asdict(a) for a in alerts], indent=2))
                elif args.format == "csv":
                    if args.output:
                        output_dir = Path(args.output)
                        output_dir.mkdir(parents=True, exist_ok=True)
                        output_file = output_dir / f"fraud_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                        save_csv_report(alerts, output_file)
                        console.print(f"[green]Report saved to:[/green] {output_file}")

                # Summary
                critical = sum(1 for a in alerts if a.risk_level == "CRITICAL")
                high = sum(1 for a in alerts if a.risk_level == "HIGH")
                if critical:
                    console.print(f"\n[red bold]⚠ {critical} CRITICAL alerts require immediate action[/red bold]")
                if high:
                    console.print(f"[yellow]{high} HIGH risk contracts flagged[/yellow]")

            finally:
                await scanner.close()

        asyncio.run(run_daily_scan())


if __name__ == "__main__":
    main()
