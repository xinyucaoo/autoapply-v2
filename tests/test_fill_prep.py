"""Tests for autoapply.services.fill_prep."""
import pytest
from autoapply.services.fill_prep import (
    parse_state_elements,
    match_field_to_element,
    build_fill_input,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_STATE = """
[711]<input type=text id=name--legalName--firstName name=legalName--firstName required=true />
[714]<input type=text id=name--legalName--lastName name=legalName--lastName required=true />
[720]<input type=email id=email--email name=email required=true />
[757]<button aria-label=State Select One name=countryRegion id=address--countryRegion />
[760]<input type=text id=address--city name=city required=true />
"""

SHADOW_STATE = """
[711]<input type=text id=name--legalName--firstName name=legalName--firstName required=true />
|SHADOW(open)|[898]<input placeholder=Search autocomplete=off id=source--source required=true />
[905]<button aria-label=Country Select One name=country id=address--country />
"""


# ---------------------------------------------------------------------------
# parse_state_elements
# ---------------------------------------------------------------------------

def test_parse_state_elements_basic():
    """Extracts by_id, by_name, by_aria_label from a simple state text."""
    elements = parse_state_elements(SAMPLE_STATE)

    # by_id
    assert elements["by_id"]["name--legalName--firstName"] == 711
    assert elements["by_id"]["name--legalName--lastName"] == 714
    assert elements["by_id"]["email--email"] == 720
    assert elements["by_id"]["address--countryRegion"] == 757
    assert elements["by_id"]["address--city"] == 760

    # by_name
    assert elements["by_name"]["legalName--firstName"] == 711
    assert elements["by_name"]["legalName--lastName"] == 714
    assert elements["by_name"]["email"] == 720
    assert elements["by_name"]["countryRegion"] == 757
    assert elements["by_name"]["city"] == 760

    # by_aria_label (from the button element)
    assert elements["by_aria_label"]["state select one"] == 757


def test_parse_state_elements_shadow_dom():
    """Lines with |SHADOW(open)| prefix still extract element idx correctly."""
    elements = parse_state_elements(SHADOW_STATE)

    # Shadow DOM line still parsed
    assert elements["by_id"]["source--source"] == 898

    # Regular lines still work
    assert elements["by_id"]["name--legalName--firstName"] == 711

    # aria-label from shadow context
    assert elements["by_aria_label"]["country select one"] == 905


def test_parse_state_elements_empty():
    """Empty state text returns empty maps."""
    elements = parse_state_elements("")
    assert elements["by_id"] == {}
    assert elements["by_name"] == {}
    assert elements["by_aria_label"] == {}


def test_parse_state_elements_no_idx_lines_ignored():
    """Lines without [idx] are silently skipped."""
    state = "Some random text without an element index\n[100]<input id=myfield />"
    elements = parse_state_elements(state)
    assert elements["by_id"] == {"myfield": 100}


# ---------------------------------------------------------------------------
# match_field_to_element
# ---------------------------------------------------------------------------

def test_match_field_exact_aria_label():
    """Exact aria-label match sets element_idx."""
    state = "[42]<button aria-label=State Select One name=region />"
    elements = parse_state_elements(state)

    # "state select one" exact match
    result = match_field_to_element("state select one", "combobox", elements)
    assert result["element_idx"] == 42


def test_match_field_partial_aria_label():
    """'State' matches aria-label='State Select One' via partial match."""
    state = "[757]<button aria-label=State Select One name=countryRegion id=address--countryRegion />"
    elements = parse_state_elements(state)

    result = match_field_to_element("State", "combobox", elements)
    assert result["element_idx"] == 757


def test_match_field_id_suffix():
    """'First Name' matches id='name--legalName--firstName' via camelCase->words conversion."""
    state = "[711]<input type=text id=name--legalName--firstName name=legalName--firstName />"
    elements = parse_state_elements(state)

    result = match_field_to_element("First Name", "text", elements)
    assert result["element_idx"] == 711
    assert result["element_id"] == "name--legalName--firstName"


def test_match_field_id_suffix_city():
    """'City' matches id='address--city' suffix 'city'."""
    state = "[760]<input type=text id=address--city name=city />"
    elements = parse_state_elements(state)

    result = match_field_to_element("City", "text", elements)
    assert result["element_idx"] == 760


def test_match_field_no_match():
    """Returns all None if no element matches."""
    state = "[711]<input id=name--firstName />"
    elements = parse_state_elements(state)

    result = match_field_to_element("Completely Unknown XYZ Field", "text", elements)
    assert result["element_idx"] is None
    assert result["element_id"] is None
    assert result["element_name"] is None


def test_match_field_case_insensitive():
    """Matching is case-insensitive for aria-labels."""
    state = "[50]<button aria-label=Email Address name=email />"
    elements = parse_state_elements(state)

    result = match_field_to_element("email address", "text", elements)
    assert result["element_idx"] == 50


# ---------------------------------------------------------------------------
# build_fill_input
# ---------------------------------------------------------------------------

SAMPLE_RESOLVER_OUTPUT = [
    {
        "label": "First Name",
        "answer": "Jane",
        "source": "profile",
        "profile_path": "personal.first_name",
        "confidence": "high",
        "policy": "autofill",
        "suggestion": None,
        "interaction_recipe": {"widget_type": "text"},
    },
    {
        "label": "State",
        "answer": "California",
        "source": "profile",
        "profile_path": "personal.address.state",
        "confidence": "high",
        "policy": "autofill",
        "suggestion": None,
        "interaction_recipe": {"widget_type": "combobox"},
    },
    {
        "label": "Email",
        "answer": "jane@example.com",
        "source": "profile",
        "profile_path": "personal.email",
        "confidence": "high",
        "policy": "autofill",
        "suggestion": None,
        "interaction_recipe": None,  # no recipe -> defaults to "text"
    },
]


def test_build_fill_input_basic():
    """End-to-end: resolver output + state text -> fill input with matched elements."""
    state = (
        "[711]<input type=text id=name--legalName--firstName name=legalName--firstName />\n"
        "[757]<button aria-label=State Select One name=countryRegion id=address--countryRegion />\n"
        "[720]<input type=email id=email--email name=email />\n"
    )
    result = build_fill_input(SAMPLE_RESOLVER_OUTPUT, state, ats="workday")

    assert result["ats_platform"] == "workday"
    assert "fields" in result
    assert "element_map" in result
    assert len(result["fields"]) == 3

    # First Name field
    first_name = result["fields"][0]
    assert first_name["label"] == "First Name"
    assert first_name["answer"] == "Jane"
    assert first_name["widget_type"] == "text"
    assert first_name["element_idx"] == 711

    # State field (combobox)
    state_field = result["fields"][1]
    assert state_field["label"] == "State"
    assert state_field["answer"] == "California"
    assert state_field["widget_type"] == "combobox"
    assert state_field["element_idx"] == 757

    # Email field (no recipe, defaults to text)
    email_field = result["fields"][2]
    assert email_field["widget_type"] == "text"
    assert email_field["answer"] == "jane@example.com"


def test_build_fill_input_skips_null_answers():
    """Fields with answer=None are excluded from output."""
    resolver = [
        {"label": "First Name", "answer": "Jane", "policy": "autofill",
         "interaction_recipe": None},
        {"label": "Unknown Field", "answer": None, "policy": "ask_user",
         "interaction_recipe": None},
    ]
    result = build_fill_input(resolver, "", ats="workday")

    labels = [f["label"] for f in result["fields"]]
    assert "First Name" in labels
    assert "Unknown Field" not in labels


def test_build_fill_input_skips_ask_user_policy():
    """Fields with policy='ask_user' are excluded from output even if answer is present."""
    resolver = [
        {"label": "First Name", "answer": "Jane", "policy": "autofill",
         "interaction_recipe": None},
        {"label": "Custom Question", "answer": "Some answer", "policy": "ask_user",
         "interaction_recipe": None},
    ]
    result = build_fill_input(resolver, "", ats="workday")

    labels = [f["label"] for f in result["fields"]]
    assert "First Name" in labels
    assert "Custom Question" not in labels


def test_build_fill_input_includes_widget_type():
    """widget_type from interaction_recipe is included in output fields."""
    resolver = [
        {
            "label": "Work Authorization",
            "answer": "Yes",
            "policy": "autofill",
            "interaction_recipe": {"widget_type": "radio"},
        },
    ]
    result = build_fill_input(resolver, "", ats="greenhouse")

    assert result["fields"][0]["widget_type"] == "radio"
    assert result["ats_platform"] == "greenhouse"


def test_build_fill_input_defaults_widget_type_to_text():
    """When interaction_recipe is None or missing widget_type, defaults to 'text'."""
    resolver = [
        {"label": "Some Field", "answer": "value", "policy": "autofill",
         "interaction_recipe": None},
        {"label": "Other Field", "answer": "value2", "policy": "autofill",
         "interaction_recipe": {}},
    ]
    result = build_fill_input(resolver, "", ats="workday")

    assert result["fields"][0]["widget_type"] == "text"
    assert result["fields"][1]["widget_type"] == "text"


def test_build_fill_input_suggest_only_included():
    """Fields with suggest_only policy ARE included (they have confirmed answers)."""
    resolver = [
        {"label": "Gender", "answer": "Female", "policy": "suggest_only",
         "interaction_recipe": {"widget_type": "select"}},
    ]
    result = build_fill_input(resolver, "", ats="workday")

    assert len(result["fields"]) == 1
    assert result["fields"][0]["label"] == "Gender"
