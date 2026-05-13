"""Rich output formatting for ARIA CLI.

ANSI color codes, table rendering, progress bars, and structured output
helpers. Supports both human-readable (default) and JSON output modes.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any


# ════════════════════════════════════════════════════════════════
#  ANSI COLOR CODES
# ════════════════════════════════════════════════════════════════

def _supports_color() -> bool:
    """Detect whether the terminal supports color output."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_COLOR = _supports_color()


class Color:
    """ANSI escape sequences for terminal colors."""

    RESET = "\033[0m" if _COLOR else ""
    BOLD = "\033[1m" if _COLOR else ""
    DIM = "\033[2m" if _COLOR else ""
    UNDERLINE = "\033[4m" if _COLOR else ""

    # Foreground
    RED = "\033[31m" if _COLOR else ""
    GREEN = "\033[32m" if _COLOR else ""
    YELLOW = "\033[33m" if _COLOR else ""
    BLUE = "\033[34m" if _COLOR else ""
    MAGENTA = "\033[35m" if _COLOR else ""
    CYAN = "\033[36m" if _COLOR else ""
    WHITE = "\033[37m" if _COLOR else ""

    # Bright foreground
    BRIGHT_RED = "\033[91m" if _COLOR else ""
    BRIGHT_GREEN = "\033[92m" if _COLOR else ""
    BRIGHT_YELLOW = "\033[93m" if _COLOR else ""
    BRIGHT_BLUE = "\033[94m" if _COLOR else ""
    BRIGHT_MAGENTA = "\033[95m" if _COLOR else ""
    BRIGHT_CYAN = "\033[96m" if _COLOR else ""

    # Background
    BG_RED = "\033[41m" if _COLOR else ""
    BG_GREEN = "\033[42m" if _COLOR else ""
    BG_YELLOW = "\033[43m" if _COLOR else ""
    BG_BLUE = "\033[44m" if _COLOR else ""


# ════════════════════════════════════════════════════════════════
#  TEXT HELPERS
# ════════════════════════════════════════════════════════════════

def bold(text: str) -> str:
    return f"{Color.BOLD}{text}{Color.RESET}"


def dim(text: str) -> str:
    return f"{Color.DIM}{text}{Color.RESET}"


def colored(text: str, color: str) -> str:
    return f"{color}{text}{Color.RESET}"


def success(text: str) -> str:
    return colored(text, Color.BRIGHT_GREEN)


def warning(text: str) -> str:
    return colored(text, Color.BRIGHT_YELLOW)


def error(text: str) -> str:
    return colored(text, Color.BRIGHT_RED)


def info(text: str) -> str:
    return colored(text, Color.BRIGHT_CYAN)


def status_indicator(ok: bool) -> str:
    """Return a colored check or cross mark."""
    if ok:
        return success("OK")
    return error("FAIL")


def status_dot(ok: bool) -> str:
    if ok:
        return colored("*", Color.GREEN)
    return colored("*", Color.RED)


# ════════════════════════════════════════════════════════════════
#  BANNER & HEADER
# ════════════════════════════════════════════════════════════════

ARIA_BANNER = r"""
    _    ____  ___    _
   / \  |  _ \|_ _|  / \
  / _ \ | |_) || |  / _ \
 / ___ \|  _ < | | / ___ \
/_/   \_\_| \_\___/_/   \_\
"""


def print_banner() -> None:
    """Print the ARIA ASCII banner."""
    print(colored(ARIA_BANNER, Color.BRIGHT_CYAN))
    print(dim("  Autonomous Reasoning & Intelligence for Astronautics"))
    print()


def print_header(title: str, width: int = 64) -> None:
    """Print a section header with box drawing characters."""
    border = colored("=" * width, Color.DIM)
    print(f"\n{border}")
    print(f"  {bold(title)}")
    print(f"{border}\n")


def print_subheader(title: str, width: int = 64) -> None:
    """Print a subsection header."""
    line = colored("-" * width, Color.DIM)
    print(f"\n{line}")
    print(f"  {title}")
    print(f"{line}\n")


def print_kv(key: str, value: Any, indent: int = 2) -> None:
    """Print a key-value pair with alignment."""
    prefix = " " * indent
    print(f"{prefix}{dim(str(key) + ':'):30s} {value}")


# ════════════════════════════════════════════════════════════════
#  TABLE RENDERING
# ════════════════════════════════════════════════════════════════

def print_table(
    headers: list[str],
    rows: list[list[Any]],
    col_widths: list[int] | None = None,
    indent: int = 2,
) -> None:
    """Render a formatted table with headers and rows.

    Args:
        headers: Column header strings.
        rows: List of row data (each row is a list of cell values).
        col_widths: Optional explicit column widths. Auto-calculated if None.
        indent: Left indentation spaces.
    """
    if not headers:
        return

    num_cols = len(headers)

    # Auto-calculate widths if not provided
    if col_widths is None:
        col_widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row[:num_cols]):
                col_widths[i] = max(col_widths[i], len(_strip_ansi(str(cell))))
        # Add padding
        col_widths = [w + 2 for w in col_widths]

    prefix = " " * indent

    # Header row
    header_line = ""
    for i, h in enumerate(headers):
        header_line += bold(str(h).ljust(col_widths[i]))
    print(f"{prefix}{header_line}")

    # Separator
    sep = ""
    for w in col_widths:
        sep += dim("-" * w)
    print(f"{prefix}{sep}")

    # Data rows
    for row in rows:
        line = ""
        for i, cell in enumerate(row[:num_cols]):
            cell_str = str(cell)
            # Account for ANSI codes in padding
            visible_len = len(_strip_ansi(cell_str))
            padding = col_widths[i] - visible_len
            line += cell_str + " " * max(padding, 1)
        print(f"{prefix}{line}")

    print()


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes for width calculation."""
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


# ════════════════════════════════════════════════════════════════
#  PROGRESS BAR
# ════════════════════════════════════════════════════════════════

class ProgressBar:
    """Simple terminal progress bar for long-running operations."""

    def __init__(self, total: int, label: str = "", width: int = 40) -> None:
        self.total = max(total, 1)
        self.label = label
        self.width = width
        self.current = 0
        self._start_time = time.time()

    def update(self, current: int | None = None) -> None:
        """Update progress bar display."""
        if current is not None:
            self.current = current
        else:
            self.current += 1

        fraction = min(self.current / self.total, 1.0)
        filled = int(self.width * fraction)
        bar = colored("█" * filled, Color.BRIGHT_CYAN) + dim("░" * (self.width - filled))

        elapsed = time.time() - self._start_time
        if fraction > 0 and fraction < 1.0:
            eta = elapsed / fraction * (1.0 - fraction)
            time_str = f"ETA {eta:.0f}s"
        elif fraction >= 1.0:
            time_str = f"{elapsed:.1f}s"
        else:
            time_str = "..."

        pct = f"{fraction * 100:5.1f}%"
        label = f"{self.label}: " if self.label else ""

        sys.stdout.write(f"\r  {label}|{bar}| {pct} ({self.current}/{self.total}) {time_str}  ")
        sys.stdout.flush()

        if self.current >= self.total:
            sys.stdout.write("\n")
            sys.stdout.flush()

    def finish(self) -> None:
        """Force completion."""
        self.update(self.total)


# ════════════════════════════════════════════════════════════════
#  JSON OUTPUT
# ════════════════════════════════════════════════════════════════

def print_json(data: Any) -> None:
    """Print data as formatted JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


# ════════════════════════════════════════════════════════════════
#  OUTPUT CONTEXT
# ════════════════════════════════════════════════════════════════

class OutputContext:
    """Tracks global output preferences (json mode, verbosity, etc.)."""

    def __init__(
        self,
        output_format: str = "text",
        verbose: bool = False,
        config_path: str | None = None,
    ) -> None:
        self.output_format = output_format
        self.verbose = verbose
        self.config_path = config_path

    @property
    def is_json(self) -> bool:
        return self.output_format == "json"

    def print(self, text: str) -> None:
        """Print text only in non-JSON mode."""
        if not self.is_json:
            print(text)

    def debug(self, text: str) -> None:
        """Print text only in verbose mode."""
        if self.verbose and not self.is_json:
            print(dim(f"  [debug] {text}"))

    def json_output(self, data: Any) -> None:
        """Print JSON output if in JSON mode."""
        if self.is_json:
            print_json(data)

    def result(self, text_output: str, json_data: Any) -> None:
        """Print either text or JSON depending on mode."""
        if self.is_json:
            print_json(json_data)
        else:
            print(text_output)


# Shared global context — set by main dispatcher
_ctx = OutputContext()


def get_context() -> OutputContext:
    return _ctx


def set_context(ctx: OutputContext) -> None:
    global _ctx
    _ctx = ctx
