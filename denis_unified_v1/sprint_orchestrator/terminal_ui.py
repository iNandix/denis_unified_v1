"""Simple terminal UI helpers (no external dependencies)."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import sys
from typing import Iterable


@dataclass(frozen=True)
class Palette:
    title: str = "36"      # cyan
    success: str = "32"    # green
    warning: str = "33"    # yellow
    error: str = "31"      # red
    muted: str = "90"      # gray
    accent: str = "35"     # magenta


PALETTE = Palette()


def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def color(text: str, code: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def h1(text: str) -> str:
    return color(text, PALETTE.title)


def ok(text: str) -> str:
    return color(text, PALETTE.success)


def warn(text: str) -> str:
    return color(text, PALETTE.warning)


def err(text: str) -> str:
    return color(text, PALETTE.error)


def muted(text: str) -> str:
    return color(text, PALETTE.muted)


def gray_dark(text: str) -> str:
    return color(text, "90")


def gray_light(text: str) -> str:
    return color(text, "37")


def accent(text: str) -> str:
    return color(text, PALETTE.accent)


def done_tick() -> str:
    return color("✅", PALETTE.success)


def term_width(default: int = 120) -> int:
    try:
        return shutil.get_terminal_size((default, 40)).columns
    except Exception:
        return default


def line(char: str = "-") -> str:
    return char * min(term_width(), 120)


def _fit(value: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(value) <= width:
        return value.ljust(width)
    if width <= 3:
        return value[:width]
    return (value[: width - 3] + "...")


def render_table(headers: list[str], rows: Iterable[list[str]], widths: list[int] | None = None) -> str:
    rows_list = [list(r) for r in rows]
    if not widths:
        widths = [len(h) for h in headers]
        for row in rows_list:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = min(50, max(widths[i], len(cell)))

    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    out: list[str] = [border]
    out.append("| " + " | ".join(_fit(h, widths[i]) for i, h in enumerate(headers)) + " |")
    out.append(border)
    for row in rows_list:
        out.append("| " + " | ".join(_fit(row[i] if i < len(row) else "", widths[i]) for i in range(len(widths))) + " |")
    out.append(border)
    return "\n".join(out)


def status_badge(status: str) -> str:
    lowered = status.lower()
    if lowered in {"ok", "success", "active"}:
        return ok(status)
    if lowered in {"warn", "warning", "blocked", "partial"}:
        return warn(status)
    if lowered in {"error", "failed", "fail"}:
        return err(status)
    return muted(status)


def panel(title: str, lines: list[str], border_char: str = "=") -> str:
    width = min(term_width(), 120)
    top = h1(border_char * width)
    title_line = h1(title[:width])
    body = "\n".join(lines)
    return f"{top}\n{title_line}\n{body}\n{top}"


def clear_screen() -> None:
    if not sys.stdout.isatty():
        return
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
