import json
from autoapply.config import PROFILE_FILE, AUTOAPPLY_DIR
from autoapply.models.profile import Profile


def load_profile() -> Profile:
    if not PROFILE_FILE.exists():
        return Profile()
    with open(PROFILE_FILE) as f:
        data = json.load(f)
    return Profile.model_validate(data)


def save_profile(profile: Profile) -> None:
    AUTOAPPLY_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_FILE, "w") as f:
        json.dump(profile.model_dump(), f, indent=2)


def get_value(profile: Profile, dotpath: str):
    """Get a value by dot-notation path e.g. 'personal.email'"""
    parts = dotpath.split(".")
    obj = profile.model_dump()
    for part in parts:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    return obj


def set_value(profile: Profile, dotpath: str, value) -> Profile:
    """Set a value by dot-notation path, returns updated profile."""
    data = profile.model_dump()
    parts = dotpath.split(".")
    obj = data
    for part in parts[:-1]:
        if isinstance(obj, dict):
            if obj.get(part) is None:
                obj[part] = {}
            obj = obj[part]
        elif isinstance(obj, list):
            obj = obj[int(part)]
    last = parts[-1]
    if isinstance(obj, dict):
        obj[last] = value
    elif isinstance(obj, list):
        obj[int(last)] = value
    return Profile.model_validate(data)
