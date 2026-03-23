import json
import click
from autoapply.services.resolver import resolve


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
