"""
Travo layer dependency linter.

Enforces the forward-only dependency rule:
  Layer 0 — types (FlightOffer, HolidayContext, TrueCostBreakdown)
  Layer 1 — config, db/sqlite, db/duckdb
  Layer 2 — fees, calendar  (load embedded data; import only config)
  Layer 3 — recommender, true_cost  (pure logic; import only types + fees)
  Layer 4 — price_sources/hookspecs, price_sources/tequila, price_sources/amadeus
  Layer 5 — tracker, scout, analytics, insights, notifier  (orchestration)
  Layer 6 — display  (Rich output; imports from orchestration)
  Layer 7 — cli  (Typer entry-point; may import anything)

A module at layer N must never import from a module at layer > N
(except that cli at layer 7 may import anything).

Run with:
    uv run python tools/layer_linter.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# ─── Layer assignments ─────────────────────────────────────────────────────────

# Maps a dotted module fragment → layer number.
# More specific fragments take precedence (checked longest-first).
LAYER_MAP: dict[str, int] = {
    # Layer 0 — domain types embedded in hookspecs and recommender
    "price_sources.hookspecs": 0,
    # Layer 1 — config and storage
    "config": 1,
    "db.sqlite": 1,
    "db.duckdb": 1,
    "db": 1,
    # Layer 2 — static data loaders
    "fees": 2,
    "calendar": 2,
    "currency": 2,
    "airports": 2,
    # Layer 3 — pure logic (no I/O)
    "recommender": 3,
    "true_cost": 3,
    # Layer 4 — external I/O (price source plugins)
    "price_sources.serpapi": 4,
    "price_sources.tequila": 4,
    "price_sources.amadeus": 4,
    "price_sources": 4,
    # Layer 5 — orchestration
    "tracker": 5,
    "scout": 5,
    "analytics": 5,
    "insights": 5,
    "notifier": 5,
    "planner": 5,
    # Layer 6 — presentation
    "display": 6,
    # Layer 7 — CLI entry point (imports anything)
    "cli": 7,
}


APP_PKG = "fly_o_myte"
APP_DIR = Path(__file__).parent.parent / "fly_o_myte"


def _module_fragment(path: Path) -> str:
    """Convert a file path inside travo/ to a dotted fragment."""
    rel = path.relative_to(APP_DIR)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def _get_layer(fragment: str) -> int | None:
    """Return layer for a module fragment, checking longest match first."""
    for key in sorted(LAYER_MAP, key=len, reverse=True):
        if fragment == key or fragment.startswith(key + "."):
            return LAYER_MAP[key]
    return None


def _imported_travo_fragments(source: str) -> list[str]:
    """Extract all `travo.*` module fragments imported by a Python source file."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    fragments: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(f"{APP_PKG}."):
                    fragments.append(alias.name[len(APP_PKG) + 1 :])
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith(f"{APP_PKG}."):
                fragments.append(module[len(APP_PKG) + 1 :])
            elif module == APP_PKG:
                # from travo import X — treat X as a top-level module
                for alias in node.names:
                    fragments.append(alias.name)
    return fragments


def lint() -> list[str]:
    """
    Run the layer linter over all travo/*.py files.
    Returns a list of violation strings (empty = pass).
    """
    violations: list[str] = []

    py_files = [p for p in APP_DIR.rglob("*.py") if "__pycache__" not in str(p)]

    for path in sorted(py_files):
        fragment = _module_fragment(path)
        src_layer = _get_layer(fragment)
        if src_layer is None:
            continue  # Unknown module — skip

        imports = _imported_travo_fragments(path.read_text(encoding="utf-8"))
        for imp in imports:
            imp_layer = _get_layer(imp)
            if imp_layer is None:
                continue
            if imp_layer > src_layer:
                violations.append(
                    f"Layer violation: travo.{fragment} (layer {src_layer}) "
                    f"imports travo.{imp} (layer {imp_layer})"
                )

    return violations


if __name__ == "__main__":
    issues = lint()
    if issues:
        print("Layer linter FAILED:")
        for v in issues:
            print(f"  {v}")
        sys.exit(1)
    else:
        print(f"Layer linter OK — {len(list(APP_DIR.rglob('*.py')))} files checked")
        sys.exit(0)
