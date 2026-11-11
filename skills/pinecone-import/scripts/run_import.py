#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "typer>=0.12",
#   "pinecone>=6.0",
# ]
# ///
"""Start a Pinecone bulk import and poll it to a terminal status.

The naive import path makes two mistakes:

  1. Treats start_import as synchronous. It returns immediately with an ID; the
     data load and indexing happen server-side afterward.
  2. Queries right after starting and concludes the import failed when results
     are empty. Records take AT LEAST 10 minutes to become queryable after the
     import reports Completed.

This script starts the import, polls describe_import on an interval until the
status is terminal (Completed / Failed / Cancelled), and reports the final
record count and any error. It does NOT wait out the post-completion indexing
window — it tells you when that window starts.

Requires PINECONE_API_KEY in the environment (or a .env via
`uv run --env-file .env ...`). The key is read by the SDK; this script never
prints it.

Usage:

    uv run --script run_import.py \
      --index my-index \
      --uri s3://my-bucket/import_data/ \
      --integration-id <ID>        # omit for a public bucket

`--uri` is the directory prefix that CONTAINS the namespace subdirectories, not
a single file. Run with --help for all flags.
"""

from __future__ import annotations

import os
import time

import typer
from pinecone import Pinecone

app = typer.Typer(add_completion=False)

TERMINAL = {"Completed", "Failed", "Cancelled"}


@app.command()
def main(
    index: str = typer.Option(..., "--index", help="Target serverless index name."),
    uri: str = typer.Option(..., "--uri", help="Directory prefix (s3://… / gs://… / https://…blob…) containing namespace subdirs."),
    integration_id: str = typer.Option(None, "--integration-id", help="Storage integration ID (omit for a public bucket)."),
    error_mode: str = typer.Option("abort", "--error-mode", help="'abort' (stop on first bad record) or 'continue' (skip silently)."),
    poll_interval: float = typer.Option(10.0, "--poll-interval", help="Seconds between status checks."),
    timeout: float = typer.Option(3600.0, "--timeout", help="Max seconds to poll before giving up (import keeps running server-side)."),
    no_wait: bool = typer.Option(False, "--no-wait", help="Start the import and print the ID without polling."),
) -> None:
    if not os.environ.get("PINECONE_API_KEY"):
        typer.secho(
            "PINECONE_API_KEY is not set. Export it, or run with "
            "`uv run --env-file .env run_import.py ...`.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    error_mode = error_mode.lower()
    if error_mode not in ("abort", "continue"):
        typer.secho("--error-mode must be 'abort' or 'continue'", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    pc = Pinecone(source_tag="pinecone_skills:import_run")  # reads PINECONE_API_KEY
    idx = pc.index(index)

    start_kwargs = {"uri": uri, "error_mode": error_mode}
    if integration_id:
        start_kwargs["integration_id"] = integration_id

    try:
        resp = idx.start_import(**start_kwargs)
    except Exception as e:  # noqa: BLE001 — surface the SDK error verbatim
        typer.secho(f"start_import failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    import_id = resp.id
    typer.secho(f"started import {import_id} (error_mode={error_mode})", fg=typer.colors.GREEN)

    if no_wait:
        typer.echo(f"not polling (--no-wait). Check later with describe_import('{import_id}').")
        return

    deadline = time.monotonic() + timeout
    last_pct = -1.0
    while True:
        op = idx.describe_import(import_id)
        pct = float(getattr(op, "percent_complete", 0.0) or 0.0)
        if pct != last_pct:
            typer.echo(f"  {op.status}  {pct:.0f}%  records_imported={getattr(op, 'records_imported', 0)}")
            last_pct = pct
        if op.status in TERMINAL:
            break
        if time.monotonic() > deadline:
            typer.secho(
                f"stopped polling after {timeout:.0f}s; import {import_id} is still "
                f"'{op.status}' and continues server-side.",
                fg=typer.colors.YELLOW,
            )
            raise typer.Exit(2)
        time.sleep(poll_interval)

    if op.status == "Completed":
        typer.secho(
            f"import {import_id} Completed — {getattr(op, 'records_imported', '?')} records. "
            "Allow ~10 min for them to become queryable, then verify with describe_index_stats().",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            f"import {import_id} ended: {op.status} — {getattr(op, 'error', None)}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
