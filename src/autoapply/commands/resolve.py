import json
import sys
import click
from autoapply.services.resolver import resolve, resolve_batch


@click.command("resolve")
@click.argument("field_label")
@click.option("--type", "field_type", default="text", help="Field type: text, select, radio, etc.")
@click.option("--options", default=None, help="Comma-separated list of options for selection fields")
@click.option("--company", default=None, help="Company name for scoped history lookup")
def resolve_cmd(field_label, field_type, options, company):
    """Resolve a form field label to an answer from profile/history.

    Outputs JSON with: answer, source, profile_path, confidence, policy, suggestion.
    """
    options_list = [o.strip() for o in options.split(",")] if options else None
    result = resolve(
        label=field_label,
        field_type=field_type,
        options=options_list,
        company=company,
    )
    output = {
        "answer": result.answer,
        "source": result.source,
        "profile_path": result.profile_path,
        "confidence": result.confidence,
        "policy": result.policy,
        "suggestion": result.suggestion,
    }
    click.echo(json.dumps(output, indent=2))


@click.command("resolve-batch")
@click.option("--fields", required=True, help="JSON array of field objects: [{label, type, options}]")
@click.option("--company", default=None, help="Company name for scoped history lookup")
def resolve_batch_cmd(fields, company):
    """Resolve multiple form fields at once from profile/history (single subprocess, single file load).

    --fields expects a JSON array: '[{"label":"First Name","type":"text"},{"label":"Email","type":"text"}]'

    Outputs a JSON array with one result per field.
    """
    try:
        fields_list = json.loads(fields)
    except json.JSONDecodeError as e:
        click.echo(f"Error parsing --fields JSON: {e}", err=True)
        sys.exit(1)
    if not isinstance(fields_list, list):
        click.echo("--fields must be a JSON array", err=True)
        sys.exit(1)
    results = resolve_batch(fields_list, company=company)
    click.echo(json.dumps(results, indent=2))
