"""
FERRET Interactive Console - Agentic REPL

An always-on interactive console that shows the agent's thinking process
and allows natural language interaction with the fraud detection system.
"""

import asyncio
import sys
import signal
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from console import (
    logger, Colors, Theme, format_banner,
    info, success, warning, error, loading
)


class AgentState(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING = "waiting"


@dataclass
class ThinkingStep:
    """Represents a step in the agent's reasoning."""
    step_type: str  # "observation", "reasoning", "decision", "action"
    content: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class FerretREPL:
    """Interactive REPL for FERRET with visible agent thinking."""

    def __init__(self):
        self.state = AgentState.IDLE
        self.thinking_steps: list[ThinkingStep] = []
        self.running = True
        self.current_task: Optional[asyncio.Task] = None

        # Animation frames for thinking indicator
        self.thinking_frames = ["◐", "◓", "◑", "◒"]
        self.frame_idx = 0

        # Store context for follow-up queries
        self.last_entities: list[dict] = []
        self.last_alerts: list = []

    def print_banner(self):
        """Print the FERRET banner and welcome message."""
        print(format_banner("mini"))
        print()
        logger.divider("═")
        print(f"  {Theme.ACCENT}FERRET INTERACTIVE CONSOLE{Colors.RESET}")
        print(f"  {Colors.DIM}Type commands or ask questions in natural language{Colors.RESET}")
        logger.divider("═")
        print()
        self._print_help()
        print()

    def _print_help(self):
        """Print available commands."""
        print(f"  {Theme.HEADER}COMMANDS{Colors.RESET}")
        print(f"  {Theme.DATA}scan{Colors.RESET} [days]       - Scan recent contracts for fraud")
        print(f"  {Theme.DATA}investigate{Colors.RESET} <id>  - Deep investigation of a contract")
        print(f"  {Theme.DATA}entity{Colors.RESET} <name>     - Look up a contractor in SAM.gov")
        print(f"  {Theme.DATA}contracts{Colors.RESET} [uei]   - Show contracts for an entity")
        print(f"  {Theme.DATA}research{Colors.RESET} <name>   - Web research on a contractor")
        print(f"  {Theme.DATA}status{Colors.RESET}            - Show current system status")
        print(f"  {Theme.DATA}help{Colors.RESET}              - Show this help")
        print(f"  {Theme.DATA}quit{Colors.RESET}              - Exit FERRET")
        print()
        print(f"  {Colors.DIM}Or type naturally: \"Find suspicious DOD contracts from last week\"{Colors.RESET}")

    def think(self, step_type: str, content: str):
        """Record and display a thinking step."""
        step = ThinkingStep(step_type, content)
        self.thinking_steps.append(step)

        # Format based on step type
        icons = {
            "observation": ("👁", Theme.DATA),
            "reasoning": ("💭", Theme.LABEL),
            "decision": ("⚡", Theme.ACCENT),
            "action": ("▶", Theme.SUCCESS),
            "result": ("✓", Theme.SUCCESS),
            "error": ("✗", Theme.ERROR),
        }

        icon, color = icons.get(step_type, ("•", Theme.INFO))
        timestamp = step.timestamp.strftime("%H:%M:%S")

        print(f"  {Colors.DIM}[{timestamp}]{Colors.RESET} {color}{icon}{Colors.RESET} {content}")

    async def animate_thinking(self, message: str = "Thinking"):
        """Show animated thinking indicator."""
        self.state = AgentState.THINKING
        try:
            while self.state == AgentState.THINKING:
                frame = self.thinking_frames[self.frame_idx % len(self.thinking_frames)]
                sys.stdout.write(f"\r  {Theme.DATA}{frame}{Colors.RESET} {Colors.DIM}{message}...{Colors.RESET}  ")
                sys.stdout.flush()
                self.frame_idx += 1
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            # Clear the line
            sys.stdout.write("\r" + " " * 60 + "\r")
            sys.stdout.flush()

    def stop_thinking(self):
        """Stop the thinking animation."""
        self.state = AgentState.ACTING

    async def handle_scan(self, args: str):
        """Handle scan command."""
        # Parse days from args
        days = 1
        if args:
            try:
                days = int(args.split()[0])
            except ValueError:
                days = 1

        logger.section("INITIATING SCAN")

        # Show agent thinking process
        self.think("observation", f"User requested scan of last {days} day(s)")
        await asyncio.sleep(0.3)

        self.think("reasoning", "Need to fetch contracts from USASpending.gov API")
        await asyncio.sleep(0.2)

        self.think("reasoning", "Will analyze for shell companies, pricing anomalies, exclusions")
        await asyncio.sleep(0.2)

        self.think("decision", f"Proceeding with {days}-day scan, minimum $25,000 threshold")
        await asyncio.sleep(0.2)

        self.think("action", "Connecting to USASpending.gov...")

        # Start thinking animation
        thinking_task = asyncio.create_task(self.animate_thinking("Fetching contracts"))

        try:
            # Import and run actual scan
            from daily_scan import DailyFraudScanner

            scanner = DailyFraudScanner(verbose=False, auto_investigate=False)

            self.stop_thinking()
            thinking_task.cancel()
            try:
                await thinking_task
            except asyncio.CancelledError:
                pass

            self.think("action", "Fetching contracts from API...")

            # Run the scan with visible progress
            alerts, total = await scanner.scan(
                days=days,
                min_value=25000,
                threshold="MEDIUM",
                limit=500
            )

            await scanner.close()

            # Store alerts for follow-up queries
            self.last_alerts = alerts

            # Report results
            self.think("result", f"Scan complete: {total} contracts analyzed")

            if alerts:
                critical = sum(1 for a in alerts if a.risk_level == "CRITICAL")
                high = sum(1 for a in alerts if a.risk_level == "HIGH")

                print()
                logger.section("FINDINGS")

                if critical > 0:
                    self.think("observation", f"Found {critical} CRITICAL alerts requiring immediate attention")
                if high > 0:
                    self.think("observation", f"Found {high} HIGH risk contracts")

                # Show top alerts
                print()
                print(f"  {Theme.HEADER}TOP ALERTS{Colors.RESET}")
                logger.divider()

                for alert in alerts[:5]:
                    logger.alert(
                        alert.risk_level,
                        alert.fraud_patterns[0] if alert.fraud_patterns else "Suspicious patterns",
                        alert.contract_id,
                        alert.contract_value
                    )

                if len(alerts) > 5:
                    print(f"  {Colors.DIM}... and {len(alerts) - 5} more{Colors.RESET}")

                print()
                self.think("decision", "Recommend investigating CRITICAL and HIGH alerts")
                print(f"\n  {Theme.ACCENT}💡 Type 'investigate <contract_id>' to deep dive{Colors.RESET}\n")
            else:
                self.think("result", "No suspicious contracts detected")
                success("All contracts appear clean")

        except Exception as e:
            self.stop_thinking()
            thinking_task.cancel()
            self.think("error", f"Scan failed: {str(e)}")

    async def handle_investigate(self, args: str):
        """Handle investigate command."""
        if not args:
            warning("Please provide a contract ID to investigate")
            print(f"  {Colors.DIM}Example: investigate W912DY-23-C-0042{Colors.RESET}")
            return

        contract_id = args.split()[0]

        logger.section("INITIATING INVESTIGATION")

        self.think("observation", f"User requested investigation of contract {contract_id}")
        await asyncio.sleep(0.2)

        self.think("reasoning", "Will conduct deep web research on contractor")
        await asyncio.sleep(0.2)

        self.think("reasoning", "Need to verify company legitimacy, check for news, lawsuits")
        await asyncio.sleep(0.2)

        self.think("decision", "Launching autonomous investigation agent")

        # Start investigation
        thinking_task = asyncio.create_task(self.animate_thinking("Researching contractor"))

        try:
            from claude_agent_sdk import query, ClaudeAgentOptions
            from pathlib import Path

            prompt = f"""Investigate federal contract {contract_id}.

Use WebSearch to:
1. Find information about the contractor
2. Check for any fraud allegations, lawsuits, or scandals
3. Verify the company is legitimate

Report your findings concisely."""

            self.stop_thinking()
            thinking_task.cancel()
            try:
                await thinking_task
            except asyncio.CancelledError:
                pass

            print()
            print(f"  {Theme.HEADER}AGENT ACTIVITY{Colors.RESET}")
            logger.divider()

            async for message in query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    cwd=str(Path(__file__).parent),
                    allowed_tools=["WebSearch", "WebFetch"],
                    permission_mode="bypassPermissions",
                    max_turns=8
                )
            ):
                # Show agent actions
                if hasattr(message, 'tool_use'):
                    tool = message.tool_use
                    if tool.name == "WebSearch":
                        self.think("action", f"Searching: {tool.input.get('query', '')[:50]}...")
                elif hasattr(message, 'result'):
                    print()
                    logger.section("INVESTIGATION REPORT")
                    # Print result with formatting
                    lines = message.result.split('\n')
                    for line in lines:
                        if line.strip():
                            print(f"  {line}")
                    print()

        except Exception as e:
            self.stop_thinking()
            thinking_task.cancel()
            self.think("error", f"Investigation failed: {str(e)}")

    async def handle_entity(self, args: str):
        """Handle entity lookup command."""
        if not args:
            warning("Please provide a contractor name")
            print(f"  {Colors.DIM}Example: entity \"Acme Defense Corp\"{Colors.RESET}")
            return

        name = args.strip().strip('"').strip("'")

        logger.section("ENTITY RESEARCH")

        self.think("observation", f"Researching contractor: {name}")
        await asyncio.sleep(0.2)

        self.think("action", "Checking SAM.gov registration database...")

        # Check local data
        from data_sources.bulk_data import LocalDataStore
        local = LocalDataStore()

        results = local.search_entities(name, limit=5)

        if results:
            self.think("result", f"Found {len(results)} matching entities")
            print()

            logger.table_header(["UEI", "NAME", "STATE", "REG DATE"], [12, 35, 6, 12])
            for entity in results:
                name = entity.get("legal_name") or entity.get("dba_name") or "Unknown"
                logger.table_row([
                    entity.get("uei", "N/A")[:10],
                    name[:33],
                    entity.get("state", "??"),
                    entity.get("registration_date", "Unknown")[:10]
                ], [12, 35, 6, 12])

            print()

            # Check each entity for additional info
            for entity in results:
                uei = entity.get("uei")
                name = entity.get("legal_name") or entity.get("dba_name") or "Unknown"

                # Check exclusion status
                exclusion = local.check_exclusion(uei=uei)
                if exclusion.get("is_excluded"):
                    self.think("observation", f"{Colors.BG_RED}{Colors.BRIGHT_WHITE} EXCLUDED {Colors.RESET} {name} is on the exclusion list!")

                # Check registration age
                reg_date_str = entity.get("registration_date", "")
                if reg_date_str:
                    try:
                        from datetime import datetime
                        reg_date = datetime.strptime(reg_date_str, "%Y%m%d")
                        age_days = (datetime.now() - reg_date).days
                        if age_days < 180:
                            self.think("observation", f"{Theme.WARNING}Recent registration:{Colors.RESET} {name} registered {age_days} days ago")
                    except ValueError:
                        pass

            self.think("decision", "Check exclusion status and contract history")

            # Store last searched entities for follow-up
            self.last_entities = results

            # Show available actions
            print()
            print(f"  {Theme.ACCENT}💡 Next actions:{Colors.RESET}")
            print(f"     {Theme.DATA}contracts{Colors.RESET} <UEI>  - Show contracts for this entity")
            print(f"     {Theme.DATA}research{Colors.RESET} <name>  - Web research on this contractor")
            print()
        else:
            self.think("observation", "No exact matches in SAM.gov database")
            self.think("reasoning", "Entity may be new, use different name, or not registered")

    async def handle_contracts(self, args: str):
        """Fetch contracts for an entity."""
        if not args:
            # Check if we have last searched entities
            if self.last_entities:
                uei = self.last_entities[0].get("uei")
                name = self.last_entities[0].get("legal_name", "Unknown")
                self.think("reasoning", f"Using last searched entity: {name}")
            else:
                warning("Please provide a UEI or search for an entity first")
                return
        else:
            uei = args.split()[0].upper()
            name = uei

        logger.section("CONTRACT HISTORY")

        self.think("observation", f"Fetching contracts for UEI: {uei}")
        self.think("action", "Querying USASpending.gov API...")

        thinking_task = asyncio.create_task(self.animate_thinking("Fetching contracts"))

        try:
            from data_sources import USASpendingClient

            client = USASpendingClient()
            result = await client.search_contracts(recipient_uei=uei, limit=20)
            await client.close()

            self.stop_thinking()
            thinking_task.cancel()
            try:
                await thinking_task
            except asyncio.CancelledError:
                pass

            contracts = result.contracts

            if contracts:
                self.think("result", f"Found {len(contracts)} contracts")

                # Calculate totals
                total_value = sum(c.total_obligation for c in contracts)
                agencies = set(c.agency for c in contracts)

                print()
                logger.metric("Total Contracts", str(len(contracts)))
                logger.metric("Total Value", f"${total_value:,.0f}")
                logger.metric("Agencies", str(len(agencies)))
                print()

                # Show contracts table
                logger.table_header(["DATE", "CONTRACT ID", "VALUE", "AGENCY"], [10, 24, 14, 20])
                for c in contracts[:10]:
                    logger.table_row([
                        c.start_date[:10] if c.start_date else "N/A",
                        c.contract_id[:22],
                        f"${c.total_obligation:,.0f}",
                        c.agency[:18] if c.agency else "N/A"
                    ], [10, 24, 14, 20])

                if len(contracts) > 10:
                    print(f"  {Colors.DIM}... and {len(contracts) - 10} more{Colors.RESET}")

                print()
                self.think("decision", "Review large contracts or recent awards for investigation")
            else:
                self.think("observation", "No contracts found for this entity")

        except Exception as e:
            self.stop_thinking()
            thinking_task.cancel()
            self.think("error", f"Failed to fetch contracts: {str(e)}")

    async def handle_research(self, args: str):
        """Web research on a contractor."""
        if not args:
            if self.last_entities:
                name = self.last_entities[0].get("legal_name", "")
                if not name:
                    warning("Please provide a contractor name")
                    return
            else:
                warning("Please provide a contractor name")
                return
        else:
            name = args.strip().strip('"').strip("'")

        logger.section("WEB RESEARCH")

        self.think("observation", f"Researching: {name}")
        self.think("reasoning", "Will search for news, fraud allegations, company info")
        self.think("action", "Initiating web search...")

        thinking_task = asyncio.create_task(self.animate_thinking("Searching"))

        try:
            from claude_agent_sdk import query as claude_query, ClaudeAgentOptions
            from pathlib import Path

            prompt = f"""Research the federal contractor "{name}".

Search for:
1. Company background and legitimacy
2. Any fraud allegations, lawsuits, or scandals
3. News articles mentioning the company
4. Government contract performance issues

Provide a concise summary of findings. Flag any red flags found."""

            self.stop_thinking()
            thinking_task.cancel()
            try:
                await thinking_task
            except asyncio.CancelledError:
                pass

            print()
            print(f"  {Theme.HEADER}RESEARCH ACTIVITY{Colors.RESET}")
            logger.divider()

            async for message in claude_query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    cwd=str(Path(__file__).parent),
                    allowed_tools=["WebSearch", "WebFetch"],
                    permission_mode="bypassPermissions",
                    max_turns=8
                )
            ):
                if hasattr(message, 'tool_use'):
                    tool = message.tool_use
                    if tool.name == "WebSearch":
                        query_text = tool.input.get('query', '')[:50]
                        self.think("action", f"Searching: {query_text}...")
                elif hasattr(message, 'result'):
                    print()
                    logger.section("RESEARCH FINDINGS")
                    lines = message.result.split('\n')
                    for line in lines:
                        if line.strip():
                            # Highlight red flags
                            if 'fraud' in line.lower() or 'lawsuit' in line.lower() or 'scandal' in line.lower():
                                print(f"  {Theme.ERROR}{line}{Colors.RESET}")
                            else:
                                print(f"  {line}")
                    print()

        except Exception as e:
            self.stop_thinking()
            thinking_task.cancel()
            self.think("error", f"Research failed: {str(e)}")

    async def handle_natural_language(self, query: str):
        """Handle natural language queries using Claude agent."""
        logger.section("PROCESSING REQUEST")

        self.think("observation", f"User query: \"{query}\"")

        # Build context from recent activity
        context_parts = []
        if self.last_entities:
            entities_info = [f"- {e.get('legal_name', 'Unknown')} (UEI: {e.get('uei', 'N/A')}, State: {e.get('state', '??')})"
                           for e in self.last_entities[:3]]
            context_parts.append(f"Recently searched entities:\n" + "\n".join(entities_info))

        if self.last_alerts:
            alerts_info = [f"- {a.contract_id}: {a.recipient_name} (${a.contract_value:,.0f}, {a.risk_level})"
                          for a in self.last_alerts[:5]]
            context_parts.append(f"Recent scan alerts:\n" + "\n".join(alerts_info))

        context = "\n\n".join(context_parts) if context_parts else "No recent activity."

        self.think("reasoning", "Interpreting request and planning actions...")

        thinking_task = asyncio.create_task(self.animate_thinking("Processing"))

        try:
            from claude_agent_sdk import query as claude_query, ClaudeAgentOptions
            from pathlib import Path

            prompt = f"""You are FERRET, an AI-native federal contract fraud detection agent.

## Context
{context}

## User Request
"{query}"

## Available Tools
You have access to:
- **WebSearch**: Search the web for news, company info, fraud allegations
- **WebFetch**: Fetch and read web pages
- **Bash**: Run Python scripts in this directory:
  - `uv run python daily_scan.py --days N` - Scan recent contracts
  - `uv run python agent.py investigate CONTRACT_ID` - Investigate a contract

## Instructions
1. Understand what the user wants
2. Take action using the tools available
3. Report findings concisely

If the user refers to "this entity" or "this contractor", use the context above.
Be autonomous - take action, don't just explain what you would do."""

            self.stop_thinking()
            thinking_task.cancel()
            try:
                await thinking_task
            except asyncio.CancelledError:
                pass

            print()
            print(f"  {Theme.HEADER}AGENT ACTIVITY{Colors.RESET}")
            logger.divider()

            async for message in claude_query(
                prompt=prompt,
                options=ClaudeAgentOptions(
                    cwd=str(Path(__file__).parent),
                    allowed_tools=["WebSearch", "WebFetch", "Bash"],
                    permission_mode="bypassPermissions",
                    max_turns=10
                )
            ):
                if hasattr(message, 'tool_use'):
                    tool = message.tool_use
                    if tool.name == "WebSearch":
                        query_text = tool.input.get('query', '')[:50]
                        self.think("action", f"Searching: {query_text}...")
                    elif tool.name == "Bash":
                        cmd = tool.input.get('command', '')[:60]
                        self.think("action", f"Running: {cmd}...")
                    elif tool.name == "WebFetch":
                        url = tool.input.get('url', '')[:50]
                        self.think("action", f"Fetching: {url}...")
                elif hasattr(message, 'result'):
                    print()
                    logger.section("FINDINGS")
                    lines = message.result.split('\n')
                    for line in lines:
                        if line.strip():
                            # Highlight important findings
                            lower_line = line.lower()
                            if any(word in lower_line for word in ['fraud', 'lawsuit', 'scandal', 'critical', 'warning']):
                                print(f"  {Theme.ERROR}{line}{Colors.RESET}")
                            elif any(word in lower_line for word in ['found', 'contract', 'million', 'awarded']):
                                print(f"  {Theme.DATA}{line}{Colors.RESET}")
                            else:
                                print(f"  {line}")
                    print()

        except Exception as e:
            self.stop_thinking()
            thinking_task.cancel()
            self.think("error", f"Failed to process: {str(e)}")

    async def handle_status(self):
        """Show system status."""
        logger.section("SYSTEM STATUS")

        from data_sources.bulk_data import LocalDataStore
        local = LocalDataStore()

        # Check data status
        logger.metric("SAM.gov Entities", f"{local.entity_count:,}" if hasattr(local, 'entity_count') else "Loading...", status="good")
        logger.metric("Exclusion Records", f"{local.exclusion_count:,}" if hasattr(local, 'exclusion_count') else "Loading...", status="good")
        logger.metric("Agent Status", "ONLINE", status="good")
        logger.metric("Last Scan", "N/A")
        print()

    def prompt(self) -> str:
        """Show the command prompt."""
        state_indicator = {
            AgentState.IDLE: f"{Theme.SUCCESS}●{Colors.RESET}",
            AgentState.THINKING: f"{Theme.DATA}◐{Colors.RESET}",
            AgentState.ACTING: f"{Theme.ACCENT}▶{Colors.RESET}",
            AgentState.WAITING: f"{Theme.WARNING}○{Colors.RESET}",
        }

        indicator = state_indicator.get(self.state, "●")
        return f"{indicator} {Theme.ACCENT}FERRET{Colors.RESET} ❯ "

    async def run(self):
        """Main REPL loop."""
        self.print_banner()

        while self.running:
            try:
                # Get user input
                self.state = AgentState.IDLE
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input(self.prompt())
                )

                user_input = user_input.strip()

                if not user_input:
                    continue

                # Parse command
                parts = user_input.split(maxsplit=1)
                command = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                # Handle commands
                if command in ("quit", "exit", "q"):
                    print()
                    info("Shutting down FERRET...")
                    self.running = False

                elif command == "help":
                    print()
                    self._print_help()

                elif command == "scan":
                    await self.handle_scan(args)

                elif command == "investigate":
                    await self.handle_investigate(args)

                elif command == "entity":
                    await self.handle_entity(args)

                elif command == "contracts":
                    await self.handle_contracts(args)

                elif command == "research":
                    await self.handle_research(args)

                elif command == "status":
                    await self.handle_status()

                elif command == "clear":
                    print("\033[2J\033[H")  # Clear screen
                    self.print_banner()

                else:
                    # Treat as natural language query
                    await self.handle_natural_language(user_input)

            except KeyboardInterrupt:
                print()
                warning("Interrupted. Type 'quit' to exit.")

            except EOFError:
                print()
                self.running = False

            except Exception as e:
                error(f"Error: {str(e)}")

        # Cleanup
        print()
        logger.divider("═")
        print(f"  {Colors.DIM}FERRET session ended{Colors.RESET}")
        logger.divider("═")
        print()


async def main():
    """Entry point for the FERRET REPL."""
    repl = FerretREPL()
    await repl.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
