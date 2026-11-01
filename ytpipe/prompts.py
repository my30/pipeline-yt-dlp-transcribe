"""Tiny stdlib-only interactive prompt helpers."""

from __future__ import annotations

from collections.abc import Sequence

# When True, every prompt silently takes its default (set by --yes).
ASSUME_DEFAULTS = False


def ask(question: str, default: str | None = None) -> str:
    if ASSUME_DEFAULTS and default is not None:
        print(f"{question} -> {default}")
        return default
    suffix = f" [{default}]" if default else ""
    while True:
        answer = input(f"{question}{suffix}: ").strip()
        if answer:
            return answer
        if default is not None:
            return default


def choose(question: str, options: Sequence[tuple[str, str]], default: str | None = None) -> str:
    """Numbered menu. ``options`` is a list of (value, label); returns the chosen value."""
    values = [v for v, _ in options]
    default = default if default in values else values[0]
    if ASSUME_DEFAULTS:
        print(f"{question} -> {default}")
        return default
    print(question)
    for i, (value, label) in enumerate(options, 1):
        mark = " (default)" if value == default else ""
        print(f"  {i}) {label}{mark}")
    while True:
        raw = input(f"Select 1-{len(options)} [{values.index(default) + 1}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return values[int(raw) - 1]
        if raw in values:
            return raw
        print("  Invalid choice, try again.")


def confirm(question: str, default: bool = True) -> bool:
    if ASSUME_DEFAULTS:
        print(f"{question} -> {'yes' if default else 'no'}")
        return default
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{question} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
