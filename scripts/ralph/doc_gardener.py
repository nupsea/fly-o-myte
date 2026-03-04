"""Doc gardener: checks that key docs/ files are accurate and up to date.

Runs after each ralph iteration. Two check types:
  1. Recency — file modified in last 10 commits (catches forgotten docs)
  2. Content — specific items from source code appear in the docs

Always exits 0 (advisory). Prints a clear summary of what needs fixing.

Run: python scripts/ralph/doc_gardener.py
"""

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
PKG = REPO_ROOT / "fly_o_myte"

WATCHED_DOCS = [
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/generated/db-schema.md",
    "docs/QUALITY_SCORE.md",
    "docs/exec-plans/tech-debt-tracker.md",
]

warnings: list[str] = []


# ─── Recency check ────────────────────────────────────────────────────────────


def was_modified_recently(filepath: str, n_commits: int = 10) -> bool:
    """Return True if the file was modified in the last n_commits commits."""
    result = subprocess.run(
        ["git", "log", "--oneline", f"HEAD~{n_commits}..HEAD", "--", filepath],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    if result.returncode == 0:
        return bool(result.stdout.strip())
    result = subprocess.run(
        ["git", "log", "--oneline", "--", filepath],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    return bool(result.stdout.strip())


# ─── Content checks ───────────────────────────────────────────────────────────


def check_cli_commands_in_readme() -> None:
    """Every @app.command() in cli.py should appear in README.md CLI reference."""
    cli_src = (PKG / "cli.py").read_text()
    readme = (REPO_ROOT / "README.md").read_text()

    # Extract function names decorated with @app.command()
    commands = re.findall(r"@app\.command\(\)\s+(?:@\w+[^\n]*\n)*def (\w+)\(", cli_src)
    # Convert snake_case to hyphen-case (fom sub_command → sub-command)
    for fn in commands:
        cmd = fn.replace("_", "-")
        # Check for the command name in README
        if f"fom {cmd}" not in readme:
            warnings.append(
                f"README.md: 'fom {cmd}' not found in CLI reference section "
                f"(defined in cli.py as def {fn})"
            )


def check_db_tables_in_schema_doc() -> None:
    """Every SQLModel table=True class in db/sqlite.py should appear in db-schema.md."""
    sqlite_src = (PKG / "db" / "sqlite.py").read_text()
    schema_doc = (REPO_ROOT / "docs" / "generated" / "db-schema.md").read_text()

    tables = re.findall(r"class (\w+)\(SQLModel,\s*table=True\)", sqlite_src)
    for table in tables:
        # Schema doc uses the lowercase table name (SQLModel convention)
        table_name = table.lower()
        if table_name not in schema_doc.lower():
            warnings.append(
                f"docs/generated/db-schema.md: table '{table_name}' "
                f"(class {table}) not documented"
            )


def check_modules_in_architecture() -> None:
    """Every top-level .py module in fly_o_myte/ should appear in ARCHITECTURE.md."""
    arch = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text()

    # Top-level modules only (not subpackages or __init__)
    skip = {"__init__", "tui"}
    modules = [
        p.stem for p in PKG.glob("*.py")
        if p.stem not in skip
    ]
    # Also check price_sources/ plugins
    ps_dir = PKG / "price_sources"
    if ps_dir.exists():
        modules += [
            f"price_sources/{p.stem}" for p in ps_dir.glob("*.py")
            if p.stem != "__init__"
        ]

    for mod in sorted(modules):
        # Check for the bare module name (e.g. "airports", "planner")
        short = mod.split("/")[-1]
        if short not in arch:
            warnings.append(
                f"docs/ARCHITECTURE.md: module '{mod}' not listed in package layout"
            )


def check_phase_status_in_readme() -> None:
    """Phase status table in README.md should not list completed phases as 'Planned'."""
    import json
    prd_path = REPO_ROOT / "scripts" / "ralph" / "prd.json"
    if not prd_path.exists():
        return

    with open(prd_path) as f:
        prd = json.load(f)

    # Count passes per phase
    phase_totals: dict[int, int] = {}
    phase_passes: dict[int, int] = {}
    for story in prd["stories"]:
        if story.get("type") == "demo-review":
            continue
        ph = story.get("phase", 0)
        phase_totals[ph] = phase_totals.get(ph, 0) + 1
        if story.get("passes"):
            phase_passes[ph] = phase_passes.get(ph, 0) + 1

    readme = (REPO_ROOT / "README.md").read_text()
    for ph, total in phase_totals.items():
        done = phase_passes.get(ph, 0)
        if done == total and f"Phase {ph}" in readme:
            # Phase fully done — check README doesn't still say "Planned" or "In progress"
            # Find the line mentioning this phase
            for line in readme.splitlines():
                if f"Phase {ph}" in line and ("Planned" in line or "In progress" in line):
                    warnings.append(
                        f"README.md: Phase {ph} is fully complete in prd.json "
                        f"but still marked '{('Planned' if 'Planned' in line else 'In progress')}' — update the phase status table"
                    )
                    break


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    # 1. Recency
    for doc in WATCHED_DOCS:
        if not was_modified_recently(doc):
            warnings.append(
                f"STALE: {doc} not updated in last 10 commits — "
                f"review and update to reflect current implementation"
            )

    # 2. Content
    check_cli_commands_in_readme()
    check_db_tables_in_schema_doc()
    check_modules_in_architecture()
    check_phase_status_in_readme()

    if warnings:
        print(f"doc_gardener: {len(warnings)} issue(s) found:\n")
        for w in warnings:
            print(f"  - {w}")
        print()
    else:
        print("doc_gardener: all watched docs are accurate and up to date.")

    return 0  # advisory only — never block the build


if __name__ == "__main__":
    sys.exit(main())
