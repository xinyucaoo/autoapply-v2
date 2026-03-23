import json
import pytest
from autoapply.models.profile import Profile, Personal, Address, Education, WorkAuthorization
from autoapply.services.profile_store import load_profile, save_profile, get_value, set_value


def test_load_profile_returns_empty_when_no_file():
    """load_profile() returns a default empty Profile when no file exists."""
    p = load_profile()
    assert isinstance(p, Profile)
    assert p.personal.first_name == ""
    assert p.education == []


def test_save_and_load_roundtrip(sample_profile):
    """save_profile() + load_profile() produces identical data."""
    save_profile(sample_profile)
    loaded = load_profile()
    assert loaded.personal.first_name == "Jane"
    assert loaded.personal.last_name == "Doe"
    assert loaded.personal.email == "jane@example.com"
    assert len(loaded.education) == 1
    assert loaded.education[0].school == "MIT"


def test_save_creates_directory(tmp_path, monkeypatch):
    """save_profile() creates the ~/.autoapply directory if it doesn't exist."""
    import autoapply.services.profile_store as ps
    new_dir = tmp_path / "new_autoapply_dir"
    ps.AUTOAPPLY_DIR = new_dir
    ps.PROFILE_FILE = new_dir / "profile.json"
    p = Profile()
    save_profile(p)
    assert ps.PROFILE_FILE.exists()


def test_get_value_simple_dotpath(sample_profile):
    """get_value() retrieves a simple top-level field."""
    assert get_value(sample_profile, "personal.first_name") == "Jane"
    assert get_value(sample_profile, "personal.email") == "jane@example.com"


def test_get_value_nested_dotpath(sample_profile):
    """get_value() retrieves a deeply nested field."""
    assert get_value(sample_profile, "personal.address.city") == "San Francisco"
    assert get_value(sample_profile, "personal.address.state") == "CA"


def test_get_value_list_index(sample_profile):
    """get_value() retrieves a value from a list by index."""
    assert get_value(sample_profile, "education.0.school") == "MIT"
    assert get_value(sample_profile, "education.0.gpa") == "3.8"


def test_get_value_missing_returns_none(sample_profile):
    """get_value() returns None for missing fields."""
    result = get_value(sample_profile, "personal.nonexistent_field")
    assert result is None


def test_get_value_out_of_bounds_list():
    """get_value() returns None for out-of-bounds list access."""
    p = Profile()
    result = get_value(p, "education.0.school")
    assert result is None


def test_set_value_simple(sample_profile):
    """set_value() updates a simple field correctly."""
    updated = set_value(sample_profile, "personal.first_name", "Alice")
    assert updated.personal.first_name == "Alice"
    # Original unchanged
    assert sample_profile.personal.first_name == "Jane"


def test_set_value_nested(sample_profile):
    """set_value() updates a nested field correctly."""
    updated = set_value(sample_profile, "personal.address.city", "New York")
    assert updated.personal.address.city == "New York"


def test_set_value_boolean(sample_profile):
    """set_value() can store boolean values."""
    updated = set_value(sample_profile, "work_authorization.sponsorship_needed", True)
    assert updated.work_authorization.sponsorship_needed is True


def test_set_value_in_list(sample_profile):
    """set_value() can update an item inside a list."""
    updated = set_value(sample_profile, "education.0.school", "Stanford")
    assert updated.education[0].school == "Stanford"


def test_set_value_persists_when_saved(sample_profile):
    """set_value() change survives save and reload."""
    updated = set_value(sample_profile, "personal.phone", "999-000-0000")
    save_profile(updated)
    reloaded = load_profile()
    assert reloaded.personal.phone == "999-000-0000"


def test_profile_with_education_list():
    """Profile correctly stores and validates a list of Education entries."""
    p = Profile(
        education=[
            Education(school="MIT", degree="BS", field="CS", graduation_date="2020-05"),
            Education(school="Stanford", degree="MS", field="AI", graduation_date="2022-05"),
        ]
    )
    save_profile(p)
    loaded = load_profile()
    assert len(loaded.education) == 2
    assert loaded.education[1].school == "Stanford"


def test_load_profile_validates_file_content(tmp_path):
    """load_profile() validates JSON from disk with Pydantic."""
    import autoapply.services.profile_store as ps
    ps.AUTOAPPLY_DIR = tmp_path / ".autoapply"
    ps.AUTOAPPLY_DIR.mkdir(parents=True)
    ps.PROFILE_FILE = ps.AUTOAPPLY_DIR / "profile.json"
    # Write a partial profile JSON
    data = {"personal": {"first_name": "Bob", "last_name": "Smith"}}
    ps.PROFILE_FILE.write_text(json.dumps(data))
    p = load_profile()
    assert p.personal.first_name == "Bob"
    assert p.personal.last_name == "Smith"
    # Defaults applied for missing fields
    assert p.personal.email == ""
