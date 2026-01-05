"""
FERRET Console - Bloomberg Terminal Style Output

Provides colorful, sci-fi themed console output for FERRET operations.
"""

import logging
import sys
from datetime import datetime
from enum import Enum
from typing import Optional

# ANSI color codes for Bloomberg-terminal style
class Colors:
    # Core colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background colors
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    # Styles
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    REVERSE = "\033[7m"

    # Reset
    RESET = "\033[0m"


# Bloomberg-style theme
class Theme:
    # Primary accent (Bloomberg orange/amber)
    ACCENT = Colors.BRIGHT_YELLOW
    # Secondary accent (cyan for data)
    DATA = Colors.BRIGHT_CYAN
    # Success indicators
    SUCCESS = Colors.BRIGHT_GREEN
    # Warning indicators
    WARNING = Colors.YELLOW
    # Error/Critical
    ERROR = Colors.BRIGHT_RED
    CRITICAL = Colors.BRIGHT_RED + Colors.BOLD
    # Info/Debug
    INFO = Colors.WHITE
    DEBUG = Colors.BRIGHT_BLACK
    # Headers
    HEADER = Colors.BRIGHT_WHITE + Colors.BOLD
    # Dividers
    DIVIDER = Colors.BRIGHT_BLACK
    # Values
    VALUE = Colors.BRIGHT_WHITE
    # Labels
    LABEL = Colors.CYAN
    # Timestamps
    TIMESTAMP = Colors.BRIGHT_BLACK


FERRET_ASCII = r"""
{accent}╔═══════════════════════════════════════════════════════════════════════════════╗
║                                                                                   ║
║  {white}███████╗███████╗██████╗ ██████╗ ███████╗████████╗{accent}                             ║
║  {white}██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝╚══██╔══╝{accent}                             ║
║  {white}█████╗  █████╗  ██████╔╝██████╔╝█████╗     ██║{accent}                                ║
║  {white}██╔══╝  ██╔══╝  ██╔══██╗██╔══██╗██╔══╝     ██║{accent}                                ║
║  {white}██║     ███████╗██║  ██║██║  ██║███████╗   ██║{accent}                                ║
║  {white}╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝   ╚═╝{accent}                                ║
║                                                                                   ║
║  {cyan}Federal Expenditure Review and Risk Evaluation Tool{accent}                          ║
║  {dim}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{accent}  ║
║                                                                                   ║
║  {label}VERSION{reset}  {value}1.0.0{accent}          {label}STATUS{reset}  {success}● ONLINE{accent}          {label}MODE{reset}  {value}SCAN{accent}            ║
║                                                                                   ║
╚═══════════════════════════════════════════════════════════════════════════════════╝{reset}
"""

FERRET_MINI = r"""
{accent}┌─────────────────────────────────────────────────────────────────┐
│ {white}█▀▀ █▀▀ █▀▄ █▀▄ █▀▀ ▀█▀{accent}  {cyan}Federal Expenditure Review{accent}            │
│ {white}█▀  █▀  █▀▄ █▀▄ █▀   █{accent}   {cyan}and Risk Evaluation Tool{accent}             │
│ {white}▀   ▀▀▀ ▀ ▀ ▀ ▀ ▀▀▀  ▀{accent}   {dim}v1.0.0{accent}                                │
└─────────────────────────────────────────────────────────────────┘{reset}
"""

FERRET_TINY = "{accent}◆ FERRET{reset} {dim}│{reset} {cyan}Federal Expenditure Review and Risk Evaluation Tool{reset}"


def format_banner(style: str = "full") -> str:
    """Format the FERRET banner with colors."""
    if style == "full":
        template = FERRET_ASCII
    elif style == "mini":
        template = FERRET_MINI
    else:
        template = FERRET_TINY

    return template.format(
        accent=Theme.ACCENT,
        white=Colors.BRIGHT_WHITE,
        cyan=Theme.DATA,
        dim=Colors.DIM,
        label=Theme.LABEL,
        value=Theme.VALUE,
        success=Theme.SUCCESS,
        reset=Colors.RESET
    )


class FerretLogger(logging.Logger):
    """Custom logger with Bloomberg-terminal style formatting."""

    def __init__(self, name: str = "ferret", level: int = logging.INFO):
        super().__init__(name, level)
        self._setup_handler()

    def _setup_handler(self):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(FerretFormatter())
        self.addHandler(handler)

    def banner(self, style: str = "mini"):
        """Print the FERRET banner."""
        print(format_banner(style))

    def section(self, title: str):
        """Print a section header."""
        width = 70
        line = "━" * width
        print(f"\n{Theme.DIVIDER}{line}{Colors.RESET}")
        print(f"{Theme.HEADER}  {title.upper()}{Colors.RESET}")
        print(f"{Theme.DIVIDER}{line}{Colors.RESET}\n")

    def metric(self, label: str, value: str, unit: str = "", status: str = ""):
        """Print a metric in Bloomberg style."""
        status_color = ""
        if status == "good":
            status_color = Theme.SUCCESS
        elif status == "warning":
            status_color = Theme.WARNING
        elif status == "bad":
            status_color = Theme.ERROR

        unit_str = f" {Colors.DIM}{unit}{Colors.RESET}" if unit else ""
        print(f"  {Theme.LABEL}{label:.<30}{Colors.RESET} {status_color}{Theme.VALUE}{value}{Colors.RESET}{unit_str}")

    def table_header(self, columns: list[str], widths: list[int]):
        """Print a table header."""
        header = ""
        for col, width in zip(columns, widths):
            header += f"{Theme.HEADER}{col:<{width}}{Colors.RESET} "
        print(f"  {header}")
        total_width = sum(widths) + len(widths) - 1
        print(f"  {Theme.DIVIDER}{'─' * total_width}{Colors.RESET}")

    def table_row(self, values: list[str], widths: list[int], highlight: bool = False):
        """Print a table row."""
        color = Theme.ACCENT if highlight else Theme.VALUE
        row = ""
        for val, width in zip(values, widths):
            row += f"{color}{str(val):<{width}}{Colors.RESET} "
        print(f"  {row}")

    def progress(self, current: int, total: int, prefix: str = "", width: int = 40):
        """Print a progress bar."""
        percent = current / total if total > 0 else 0
        filled = int(width * percent)
        bar = "█" * filled + "░" * (width - filled)
        pct_str = f"{percent*100:5.1f}%"

        print(f"\r  {Theme.LABEL}{prefix}{Colors.RESET} {Theme.DATA}[{bar}]{Colors.RESET} {Theme.VALUE}{pct_str}{Colors.RESET} {Colors.DIM}({current}/{total}){Colors.RESET}", end="", flush=True)
        if current >= total:
            print()

    def alert(self, level: str, message: str, contract_id: str = "", value: float = 0):
        """Print an alert in Bloomberg style."""
        level_colors = {
            "CRITICAL": (Colors.BG_RED + Colors.BRIGHT_WHITE, "🔴"),
            "HIGH": (Theme.ERROR, "🟠"),
            "MEDIUM": (Theme.WARNING, "🟡"),
            "LOW": (Theme.DATA, "🔵"),
        }

        color, icon = level_colors.get(level, (Theme.INFO, "⚪"))
        value_str = f"${value:,.0f}" if value else ""

        print(f"  {color}{icon} {level:8}{Colors.RESET} │ {Theme.VALUE}{contract_id:20}{Colors.RESET} │ {Theme.DATA}{value_str:>15}{Colors.RESET} │ {message}")

    def status(self, message: str, status: str = "info"):
        """Print a status message."""
        icons = {
            "info": ("ℹ", Theme.INFO),
            "success": ("✓", Theme.SUCCESS),
            "warning": ("⚠", Theme.WARNING),
            "error": ("✗", Theme.ERROR),
            "loading": ("◐", Theme.DATA),
        }

        icon, color = icons.get(status, ("•", Theme.INFO))
        timestamp = datetime.now().strftime("%H:%M:%S")

        print(f"  {Theme.TIMESTAMP}[{timestamp}]{Colors.RESET} {color}{icon}{Colors.RESET} {message}")

    def divider(self, char: str = "─", width: int = 70):
        """Print a divider line."""
        print(f"  {Theme.DIVIDER}{char * width}{Colors.RESET}")


class FerretFormatter(logging.Formatter):
    """Custom formatter for FERRET logs."""

    FORMATS = {
        logging.DEBUG: f"{Theme.DEBUG}DBG{Colors.RESET}",
        logging.INFO: f"{Theme.INFO}INF{Colors.RESET}",
        logging.WARNING: f"{Theme.WARNING}WRN{Colors.RESET}",
        logging.ERROR: f"{Theme.ERROR}ERR{Colors.RESET}",
        logging.CRITICAL: f"{Theme.CRITICAL}CRT{Colors.RESET}",
    }

    def format(self, record):
        level_str = self.FORMATS.get(record.levelno, "???")
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        return f"  {Theme.TIMESTAMP}{timestamp}{Colors.RESET} {level_str} {record.getMessage()}"


# Global logger instance
logger = FerretLogger()


def print_scan_header(days: int, min_value: float, deep: bool = False):
    """Print the scan header."""
    logger.banner("mini")
    logger.section("SCAN CONFIGURATION")
    logger.metric("Time Range", f"Last {days} day(s)")
    logger.metric("Minimum Value", f"${min_value:,.0f}")
    logger.metric("Analysis Mode", "DEEP" if deep else "STANDARD")
    logger.metric("Timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print()


def print_scan_results(
    total_scanned: int,
    flagged: int,
    critical: int,
    high: int,
    medium: int,
    low: int
):
    """Print scan results summary."""
    logger.section("SCAN RESULTS")

    flag_rate = (flagged / total_scanned * 100) if total_scanned > 0 else 0

    logger.metric("Contracts Scanned", f"{total_scanned:,}", status="good")
    logger.metric("Contracts Flagged", f"{flagged:,}", f"({flag_rate:.1f}%)",
                  status="warning" if flagged > 0 else "good")

    print()
    logger.divider()
    print(f"  {Theme.HEADER}RISK BREAKDOWN{Colors.RESET}")
    logger.divider()

    if critical > 0:
        print(f"  {Colors.BG_RED}{Colors.BRIGHT_WHITE}  CRITICAL  {Colors.RESET}  {Theme.VALUE}{critical:>5}{Colors.RESET}")
    else:
        print(f"  {Colors.DIM}  CRITICAL  {Colors.RESET}  {Colors.DIM}{critical:>5}{Colors.RESET}")

    if high > 0:
        print(f"  {Theme.ERROR}  HIGH      {Colors.RESET}  {Theme.VALUE}{high:>5}{Colors.RESET}")
    else:
        print(f"  {Colors.DIM}  HIGH      {Colors.RESET}  {Colors.DIM}{high:>5}{Colors.RESET}")

    if medium > 0:
        print(f"  {Theme.WARNING}  MEDIUM    {Colors.RESET}  {Theme.VALUE}{medium:>5}{Colors.RESET}")
    else:
        print(f"  {Colors.DIM}  MEDIUM    {Colors.RESET}  {Colors.DIM}{medium:>5}{Colors.RESET}")

    print(f"  {Theme.DATA}  LOW       {Colors.RESET}  {Theme.VALUE}{low:>5}{Colors.RESET}")

    logger.divider()
    print()


def print_investigation_start(contract_id: str, contractor: str, value: float):
    """Print investigation start banner."""
    print()
    logger.divider("═")
    print(f"  {Theme.ACCENT}⚡ INITIATING INVESTIGATION{Colors.RESET}")
    logger.divider("═")
    logger.metric("Contract ID", contract_id)
    logger.metric("Contractor", contractor)
    logger.metric("Value", f"${value:,.0f}")
    print()


def print_footer():
    """Print the footer."""
    print()
    logger.divider("═")
    print(f"  {Colors.DIM}FERRET v1.0.0 │ theaishift.dev │ github.com/sarchak/ferret{Colors.RESET}")
    logger.divider("═")
    print()


# Export convenience functions
def info(msg: str): logger.status(msg, "info")
def success(msg: str): logger.status(msg, "success")
def warning(msg: str): logger.status(msg, "warning")
def error(msg: str): logger.status(msg, "error")
def loading(msg: str): logger.status(msg, "loading")


if __name__ == "__main__":
    # Demo the console
    logger.banner("full")
    print_scan_header(days=7, min_value=25000, deep=True)

    logger.section("DATA LOADING")
    logger.status("Fetching contracts from USASpending...", "loading")
    logger.status("Loaded 1,234 contracts", "success")
    logger.status("Loading entity index from cache...", "loading")
    logger.status("868,090 entities loaded", "success")

    logger.section("ANALYSIS")
    for i in range(0, 101, 10):
        logger.progress(i, 100, "Analyzing contracts", 40)
        import time
        time.sleep(0.1)

    print_scan_results(
        total_scanned=1234,
        flagged=45,
        critical=2,
        high=5,
        medium=12,
        low=26
    )

    logger.section("ALERTS")
    logger.alert("CRITICAL", "Shell company indicators", "W912DY-23-C-0042", 5_200_000)
    logger.alert("HIGH", "Virtual office address", "FA8620-24-C-1234", 1_800_000)
    logger.alert("MEDIUM", "Recent registration", "N00024-24-D-5678", 450_000)
    logger.alert("LOW", "Single offer competition", "W91238-23-C-9012", 125_000)

    print_footer()
