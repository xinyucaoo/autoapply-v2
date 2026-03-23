import json
import sys
import click
from autoapply.services.profile_store import load_profile, save_profile, set_value, get_value
from autoapply.models.profile import Profile


@click.group()
def profile():
    """Manage your applicant profile."""
    pass


@profile.command("show")
@click.argument("section", required=False)
def show(section):
    """Show the full profile or a specific section."""
    p = load_profile()
    data = p.model_dump()
    if section:
        data = data.get(section)
        if data is None:
            click.echo(f"Section '{section}' not found.", err=True)
            sys.exit(1)
    click.echo(json.dumps(data, indent=2))


@profile.command("set")
@click.argument("dotpath")
@click.argument("value")
def set_cmd(dotpath, value):
    """Set a profile field by dot-notation path."""
    p = load_profile()
    # Only convert booleans; let Pydantic coerce numeric strings for int fields
    parsed: object = value
    if value.lower() == "true":
        parsed = True
    elif value.lower() == "false":
        parsed = False
    p = set_value(p, dotpath, parsed)
    save_profile(p)
    click.echo(f"Set {dotpath} = {parsed}")


@profile.command("add")
@click.argument("array_path")
@click.argument("json_value")
def add_cmd(array_path, json_value):
    """Append a JSON object to an array field (e.g., education, experience)."""
    p = load_profile()
    data = p.model_dump()
    parts = array_path.split(".")
    obj = data
    for part in parts:
        obj = obj[part]
    if not isinstance(obj, list):
        click.echo(f"'{array_path}' is not a list field.", err=True)
        sys.exit(1)
    obj.append(json.loads(json_value))
    p = Profile.model_validate(data)
    save_profile(p)
    click.echo(f"Added item to {array_path}")


@profile.command("remove")
@click.argument("array_path")
@click.argument("index", type=int)
def remove_cmd(array_path, index):
    """Remove an item by index from an array field."""
    p = load_profile()
    data = p.model_dump()
    parts = array_path.split(".")
    obj = data
    for part in parts:
        obj = obj[part]
    if not isinstance(obj, list):
        click.echo(f"'{array_path}' is not a list field.", err=True)
        sys.exit(1)
    removed = obj.pop(index)
    p = Profile.model_validate(data)
    save_profile(p)
    click.echo(f"Removed item {index} from {array_path}: {removed}")


@profile.command("init")
@click.option("--force", is_flag=True, help="Overwrite existing profile")
def init(force):
    """Create an empty profile.json."""
    from autoapply.config import PROFILE_FILE, AUTOAPPLY_DIR
    if PROFILE_FILE.exists() and not force:
        click.echo(f"Profile already exists at {PROFILE_FILE}. Use --force to overwrite.")
        return
    AUTOAPPLY_DIR.mkdir(parents=True, exist_ok=True)
    p = Profile()
    save_profile(p)
    click.echo(f"Created profile at {PROFILE_FILE}")


@profile.command("import")
@click.argument("file", type=click.Path(exists=True))
def import_cmd(file):
    """Import profile from a JSON file."""
    with open(file) as f:
        data = json.load(f)
    p = Profile.model_validate(data)
    save_profile(p)
    click.echo(f"Profile imported from {file}")


@profile.command("export")
@click.argument("file", required=False)
def export_cmd(file):
    """Export profile to stdout or a file."""
    p = load_profile()
    output = json.dumps(p.model_dump(), indent=2)
    if file:
        with open(file, "w") as f:
            f.write(output)
        click.echo(f"Profile exported to {file}")
    else:
        click.echo(output)
