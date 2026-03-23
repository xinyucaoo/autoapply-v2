"""CLI command: `autoapply fill-prep`

Builds fill engine input JSON from browser-use state text + resolve-batch output.
"""
import json
import sys
import click
from pathlib import Path

from autoapply.services.fill_prep import build_fill_input


@click.command("fill-prep")
@click.option(
    "--state",
    "state_file",
    required=True,
    help="Path to browser-use state text file",
)
@click.option(
    "--resolver",
    "resolver_file",
    required=True,
    help="Path to resolve-batch JSON output",
)
@click.option(
    "--ats",
    default=None,
    help="ATS platform (workday, greenhouse, etc.)",
)
@click.option(
    "--output",
    "output_file",
    default="/tmp/autoapply_fill_input.json",
    show_default=True,
    help="Output path for fill engine input JSON",
)
def fill_prep_cmd(state_file, resolver_file, ats, output_file):
    """Build fill engine input JSON from state text + resolver output.

    Example:
        autoapply fill-prep --state /tmp/page_state.txt --resolver /tmp/resolver_output.json
    """
    state_path = Path(state_file)
    resolver_path = Path(resolver_file)

    if not state_path.exists():
        click.echo(f"Error: state file not found: {state_file}", err=True)
        sys.exit(1)
    if not resolver_path.exists():
        click.echo(f"Error: resolver file not found: {resolver_file}", err=True)
        sys.exit(1)

    state_text = state_path.read_text()

    try:
        resolver_results = json.loads(resolver_path.read_text())
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing resolver JSON: {e}", err=True)
        sys.exit(1)

    if not isinstance(resolver_results, list):
        click.echo("Error: resolver file must contain a JSON array", err=True)
        sys.exit(1)

    result = build_fill_input(resolver_results, state_text, ats or "workday")

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))

    click.echo(f"Fill input written to {output_file} ({len(result['fields'])} fields)")
