import json
import sys
import click
from autoapply.services.history_store import (
    load_history, save_history, add_record, search_qa, lookup_answer
)
from autoapply.models.history import ApplicationHistory, ApplicationRecord, QAPair


@click.group()
def history():
    """Manage application history."""
    pass


@history.command("list")
def list_cmd():
    """List all applications."""
    h = load_history()
    if not h.applications:
        click.echo("No applications recorded.")
        return
    for app in h.applications:
        click.echo(f"{app.id[:8]}  {app.applied_at[:10]}  {app.status:<12}  {app.company} — {app.job_title}")


@history.command("show")
@click.argument("id")
def show_cmd(id):
    """Show a full application record."""
    h = load_history()
    for app in h.applications:
        if app.id.startswith(id):
            click.echo(json.dumps(app.model_dump(), indent=2))
            return
    click.echo(f"No application found with id starting '{id}'", err=True)
    sys.exit(1)


@history.command("search")
@click.argument("query")
@click.option("--company", default=None)
def search_cmd(query, company):
    """Search Q&A pairs by question text."""
    h = load_history()
    results = search_qa(h, query, company=company)
    if not results:
        click.echo("No matching Q&A pairs found.")
        return
    for qa in results:
        click.echo(json.dumps(qa.model_dump(), indent=2))


@history.command("lookup")
@click.argument("question")
@click.option("--company", default=None)
@click.option("--verified-only", is_flag=True)
def lookup_cmd(question, company, verified_only):
    """Find the best matching answer from history. Outputs JSON."""
    h = load_history()
    result = lookup_answer(h, question, company=company, verified_only=verified_only)
    if result:
        click.echo(json.dumps(result.model_dump(), indent=2))
    else:
        click.echo("null")


@history.command("add")
@click.argument("json_value")
def add_cmd(json_value):
    """Add a full application record (JSON). Returns the record id."""
    h = load_history()
    data = json.loads(json_value)
    record = ApplicationRecord.model_validate(data)
    h = add_record(h, record)
    save_history(h)
    click.echo(record.id)


@history.command("stats")
def stats_cmd():
    """Show application statistics."""
    h = load_history()
    total = len(h.applications)
    by_status: dict[str, int] = {}
    for app in h.applications:
        by_status[app.status] = by_status.get(app.status, 0) + 1
    click.echo(f"Total applications: {total}")
    for status, count in sorted(by_status.items()):
        click.echo(f"  {status}: {count}")
