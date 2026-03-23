import pytest
from autoapply.services.playbooks import detect_ats_platform, lookup_playbook, PLAYBOOK_REGISTRY


# ---------------------------------------------------------------------------
# ATS detection
# ---------------------------------------------------------------------------

def test_detect_workday_myworkdayjobs():
    url = "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/123"
    assert detect_ats_platform(url) == "workday"


def test_detect_workday_myworkday():
    url = "https://company.myworkday.com/wday/authgwy/company/login.htmld"
    assert detect_ats_platform(url) == "workday"


def test_detect_greenhouse():
    url = "https://boards.greenhouse.io/acmecorp/jobs/12345"
    assert detect_ats_platform(url) == "greenhouse"


def test_detect_lever():
    url = "https://jobs.lever.co/acmecorp/abc-123"
    assert detect_ats_platform(url) == "lever"


def test_detect_icims():
    url = "https://acmecorp.icims.com/jobs/1234/apply"
    assert detect_ats_platform(url) == "icims"


def test_detect_smartrecruiters():
    url = "https://jobs.smartrecruiters.com/AcmeCorp/123"
    assert detect_ats_platform(url) == "smartrecruiters"


def test_detect_unknown_returns_none():
    url = "https://careers.acmecorp.com/apply"
    assert detect_ats_platform(url) is None


def test_detect_case_insensitive():
    url = "https://nvidia.WD5.MyWorkdayJobs.com/job/123"
    assert detect_ats_platform(url) == "workday"


# ---------------------------------------------------------------------------
# Playbook lookup
# ---------------------------------------------------------------------------

def test_lookup_workday_combobox():
    recipe = lookup_playbook("workday", "combobox")
    assert recipe is not None
    assert recipe.widget_type == "combobox"
    assert recipe.ats_platform == "workday"
    assert len(recipe.steps) >= 3


def test_lookup_workday_react_virtualized():
    recipe = lookup_playbook("workday", "react_virtualized")
    assert recipe is not None
    assert recipe.widget_type == "react_virtualized"


def test_lookup_workday_date_segmented():
    recipe = lookup_playbook("workday", "date_segmented")
    assert recipe is not None
    assert recipe.widget_type == "date_segmented"


def test_lookup_generic_select():
    recipe = lookup_playbook(None, "select")
    assert recipe is not None
    assert recipe.widget_type == "select"


def test_lookup_generic_radio():
    recipe = lookup_playbook(None, "radio")
    assert recipe is not None
    assert recipe.widget_type == "radio"


def test_lookup_falls_back_to_generic():
    """Unknown ATS with a generic widget type falls back to generic recipe."""
    recipe = lookup_playbook("taleo", "select")
    assert recipe is not None
    assert recipe.widget_type == "select"


def test_lookup_no_match_returns_none():
    """Completely unknown (ats, widget_type) returns None."""
    recipe = lookup_playbook("workday", "unknown_widget_xyz")
    assert recipe is None


def test_lookup_none_ats_uses_generic():
    """ats_platform=None resolves generic recipes."""
    recipe = lookup_playbook(None, "select")
    assert recipe is not None


# ---------------------------------------------------------------------------
# Recipe structure — placeholders
# ---------------------------------------------------------------------------

def test_workday_combobox_steps_use_idx_placeholder():
    """Steps should use {idx} not hardcoded indices."""
    recipe = lookup_playbook("workday", "combobox")
    targets = [s.target for s in recipe.steps]
    assert any("{idx}" in t for t in targets), f"No {{idx}} placeholder in targets: {targets}"


def test_workday_combobox_steps_use_answer_placeholder():
    """Type step should use {answer} for the value to type."""
    recipe = lookup_playbook("workday", "combobox")
    values = [s.value for s in recipe.steps if s.value]
    assert any("{answer}" in v for v in values), f"No {{answer}} placeholder in values: {values}"


def test_all_recipes_have_description():
    """Every registered recipe has a non-empty description."""
    for (ats, widget), recipe in PLAYBOOK_REGISTRY.items():
        assert recipe.description, f"Recipe ({ats}, {widget}) has empty description"


def test_all_recipes_have_steps():
    """Every registered recipe has at least one step."""
    for (ats, widget), recipe in PLAYBOOK_REGISTRY.items():
        assert len(recipe.steps) >= 1, f"Recipe ({ats}, {widget}) has no steps"
