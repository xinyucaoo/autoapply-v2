import click
from autoapply.commands.profile import profile
from autoapply.commands.history import history
from autoapply.commands.resolve import resolve_cmd, resolve_batch_cmd


@click.group()
def cli():
    """autoapply — intelligent job application automation."""
    pass


cli.add_command(profile)
cli.add_command(history)
cli.add_command(resolve_cmd, name="resolve")
cli.add_command(resolve_batch_cmd, name="resolve-batch")
