#!/usr/bin/env python3
# Pinned exactly, not floating. These install at CI job time in a job that holds a
# write token for the plugin repos, so a compromised release would run there. The
# same floating-lower-bound habit is what let pinecone 9 break every skill script.
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pyyaml==6.0.3",
#   "typer==0.27.1",
# ]
# ///
"""Diff a rendered target tree against the live plugin repo.

    uv run tools/reconcile.py --target cursor --clone ../plugin-cursor
    uv run tools/reconcile.py --target claude-code --clone ../plugin-claude --diff

Once the sync pipeline is running this is a steady-state assertion: live and
rendered agree, exit 0. Before the first sync it is a migration report, and the
three buckets are not interchangeable —

    MISSING   in rendered, not live       sync adds it
    EXTRA     in live, not rendered       `rsync --delete` REMOVES it
    DIFFERS   in both, contents disagree  sync overwrites live

EXTRA is the one to read carefully. A file only the target has is either
vestigial or a downstream edit that was never back-ported, and `--delete` cannot
tell the difference. Same for DIFFERS: base is not automatically right.
`create.py` in the Claude plugin was ahead of base for months.

Reads live content from a git ref rather than the working tree, so a dirty clone
or a stale checkout cannot quietly change the answer.
"""

from __future__ import annotations

import difflib
import subprocess
from pathlib import Path
from typing import Any

import typer
import yaml

app = typer.Typer(add_completion=False, pretty_exceptions_enable=False)

REPO = Path(__file__).resolve().parent.parent
TARGETS_DIR = REPO / "targets"
DIST_DIR = REPO / "dist"

BINARY = "\0<binary>"


def load_manifest(target: str) -> dict[str, Any]:
    path = TARGETS_DIR / f"{target}.yaml"
    if not path.exists():
        raise typer.BadParameter(f"no manifest at {path.relative_to(REPO)}")
    return yaml.safe_load(path.read_text())


def git(clone: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(clone), *args],
        capture_output=True, text=True, check=False, errors="replace",
    )
    if result.returncode != 0:
        raise typer.BadParameter(f"git {' '.join(args)} failed in {clone}:\n{result.stderr.strip()}")
    return result.stdout


def live_files(clone: Path, ref: str, skills_path: str) -> dict[str, str]:
    """Map path-relative-to-skills_path -> contents, read from `ref`."""
    listing = git(clone, "ls-tree", "-r", "--name-only", "-z", ref, "--", skills_path)
    files: dict[str, str] = {}
    for name in listing.split("\0"):
        if not name:
            continue
        rel = name[len(skills_path):].lstrip("/")
        blob = git(clone, "show", f"{ref}:{name}")
        files[rel] = BINARY if "\0" in blob else blob
    return files


def rendered_files(target: str, skills_path: str) -> dict[str, str]:
    root = DIST_DIR / target / skills_path
    if not root.is_dir():
        raise typer.BadParameter(f"{root.relative_to(REPO)} does not exist — run tools/build.py first")
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        try:
            files[rel] = path.read_text()
        except UnicodeDecodeError:
            files[rel] = BINARY
    return files


@app.command()
def main(
    target: str = typer.Option(..., "--target", "-t", help="Target manifest name, e.g. cursor."),
    clone: Path = typer.Option(..., "--clone", "-c", help="Path to a local clone of the target repo."),
    ref: str = typer.Option("origin/main", "--ref", help="Git ref in the clone to compare against."),
    diff: bool = typer.Option(False, "--diff", help="Print a unified diff for every DIFFERS file."),
):
    """Compare dist/<target>/ against the live target repo."""
    manifest = load_manifest(target)
    skills_path = manifest["skills_path"]

    live = live_files(clone.resolve(), ref, skills_path)
    built = rendered_files(target, skills_path)

    missing = sorted(set(built) - set(live))
    extra = sorted(set(live) - set(built))
    differs = sorted(k for k in set(built) & set(live) if built[k] != live[k])

    typer.echo(f"{target}  vs  {manifest['repo']} @ {ref}")
    typer.echo(f"  rendered {len(built)} files, live {len(live)} files\n")

    for label, items, note in [
        ("MISSING", missing, "sync will add"),
        ("EXTRA", extra, "rsync --delete will REMOVE"),
        ("DIFFERS", differs, "sync will overwrite"),
    ]:
        typer.echo(f"{label} ({len(items)}) — {note}")
        for item in items:
            typer.echo(f"    {item}")
        typer.echo("")

    if diff:
        for key in differs:
            typer.echo(f"--- diff {key} " + "-" * max(0, 60 - len(key)))
            if BINARY in (live[key], built[key]):
                typer.echo("    (binary)")
            else:
                for line in difflib.unified_diff(
                    live[key].splitlines(), built[key].splitlines(),
                    fromfile=f"live/{key}", tofile=f"built/{key}", lineterm="",
                ):
                    typer.echo(line)
            typer.echo("")

    total = len(missing) + len(extra) + len(differs)
    typer.echo(f"{total} discrepancies" if total else "in sync")
    raise typer.Exit(1 if total else 0)


if __name__ == "__main__":
    app()
