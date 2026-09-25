#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pinecone==9.1.0",
#   "typer>=0.15.0",
#   "rich>=13.0.0",
# ]
# ///
"""
List all Pinecone Assistants in the account.

Usage:
    uv run list.py [--json] [--files]

Environment Variables:
    PINECONE_API_KEY: Required Pinecone API key

Output:
    Formatted table or JSON list of assistants with name, status, and host
    Optionally include files for each assistant with --files flag
"""

import os
import sys
import json
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from pinecone import Pinecone

app = typer.Typer()
console = Console()


@app.command()
def main(
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
    files: bool = typer.Option(False, "--files", "-f", help="Include file listing for each assistant"),
):
    """List all Pinecone Assistants in your account."""

    # Check for API key
    api_key = os.environ.get('PINECONE_API_KEY')
    if not api_key:
        console.print("[red]Error: PINECONE_API_KEY environment variable not set[/red]")
        console.print("\nGet your API key from: https://app.pinecone.io/?sessionType=signup")
        raise typer.Exit(1)

    try:
        # Initialize Pinecone client
        pc = Pinecone(api_key=api_key, source_tag="pinecone_skills:assistant")

        # List assistants
        assistants = pc.assistant.list_assistants()

        if not assistants:
            if json_output:
                print(json.dumps({"assistants": [], "count": 0}))
            else:
                console.print("[yellow]No assistants found.[/yellow]\n")
                console.print("Create your first assistant with:")
                console.print("  <<next_create_first>>")
            return

        if json_output:
            # JSON output
            assistants_data = []
            for asst in assistants:
                asst_data = {
                    "name": asst.name,
                    "status": asst.status,
                    "host": getattr(asst, 'host', ''),
                }

                if files:
                    # Get files for this assistant
                    try:
                        # Models from list_assistants() carry a client back-reference,
                        # so list_files() works on them directly and returns a list.
                        # pc.assistants.list_files() returns a Paginator with no __len__.
                        file_list = asst.list_files()
                        asst_data["files"] = [
                            {
                                "name": f.name,
                                "id": f.id,
                                "status": f.status,
                                "metadata": getattr(f, 'metadata', {}),
                            }
                            for f in file_list
                        ]
                        asst_data["file_count"] = len(file_list)
                    except Exception as e:
                        asst_data["files"] = []
                        asst_data["file_count"] = 0
                        asst_data["file_error"] = str(e)

                assistants_data.append(asst_data)

            result = {
                "assistants": assistants_data,
                "count": len(assistants)
            }
            print(json.dumps(result, indent=2))
        else:
            # Rich table output
            console.print(f"\n[bold]Found {len(assistants)} assistant(s):[/bold]\n")

            # Assistants table
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Name", style="green", width=30)
            table.add_column("Status", style="yellow", width=15)
            if files:
                table.add_column("Files", style="magenta", width=10)
            table.add_column("Host", style="dim", width=40 if files else 50)

            for asst in assistants:
                name = asst.name
                status = asst.status
                host = getattr(asst, 'host', '')

                # Color code status. The API returns capitalized values
                # ("Ready", "Initializing"), so compare case-insensitively.
                status_key = (status or '').lower()
                if status_key == 'ready':
                    status_display = f"[green]{status}[/green]"
                elif status_key in ('indexing', 'initializing'):
                    status_display = f"[yellow]{status}[/yellow]"
                else:
                    status_display = status

                if files:
                    # Get file count for this assistant
                    try:
                        # Models from list_assistants() carry a client back-reference,
                        # so list_files() works on them directly and returns a list.
                        # pc.assistants.list_files() returns a Paginator with no __len__.
                        file_list = asst.list_files()
                        file_count = str(len(file_list))
                    except Exception:
                        file_count = "?"

                    table.add_row(name, status_display, file_count, host)
                else:
                    table.add_row(name, status_display, host)

            console.print(table)
            console.print()

            # If --files flag is set, show detailed file listing for each assistant
            if files:
                console.print("[bold]File Details:[/bold]\n")
                for asst in assistants:
                    try:
                        # Models from list_assistants() carry a client back-reference,
                        # so list_files() works on them directly and returns a list.
                        # pc.assistants.list_files() returns a Paginator with no __len__.
                        file_list = asst.list_files()

                        if file_list:
                            # Create a table for this assistant's files
                            file_table = Table(show_header=True, header_style="bold blue", title=f"[cyan]{asst.name}[/cyan]")
                            file_table.add_column("#", style="dim", width=4)
                            file_table.add_column("File Name", style="green", width=50)
                            file_table.add_column("Status", style="yellow", width=15)
                            file_table.add_column("ID", style="dim", width=30)

                            for idx, file_obj in enumerate(file_list, 1):
                                file_name = file_obj.name
                                file_id = file_obj.id
                                file_status = file_obj.status

                                # Color code file status. The API returns
                                # capitalized values ("Available", "Processing",
                                # "ProcessingFailed"), so normalize before comparing.
                                fs_key = (file_status or '').lower()
                                if fs_key == 'available':
                                    file_status_display = f"[green]{file_status}[/green]"
                                elif fs_key == 'processing':
                                    file_status_display = f"[yellow]{file_status}[/yellow]"
                                elif 'failed' in fs_key:
                                    file_status_display = f"[red]{file_status}[/red]"
                                else:
                                    file_status_display = file_status

                                file_table.add_row(str(idx), file_name, file_status_display, file_id)

                            console.print(file_table)
                            console.print()
                        else:
                            console.print(f"[dim]{asst.name}: No files uploaded[/dim]\n")
                    except Exception as e:
                        console.print(f"[red]Error listing files for {asst.name}: {e}[/red]\n")

            # Next steps panel
            next_steps = """[bold]Next steps:[/bold]
<<next_commands>>"""

            console.print(Panel(next_steps, title="Available Commands", border_style="blue"))

    except Exception as e:
        console.print(f"[red]Error listing assistants: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
