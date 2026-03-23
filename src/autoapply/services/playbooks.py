"""
ATS interaction playbooks — static recipes for known widget types.

The LLM uses these to fill tricky fields (Workday combo-boxes, date segments, etc.)
without trial-and-error. Each recipe uses {idx} and {answer} as placeholders.
"""
from __future__ import annotations
from autoapply.models.history import InteractionRecipe, InteractionStep


# ---------------------------------------------------------------------------
# ATS detection
# ---------------------------------------------------------------------------

def detect_ats_platform(url: str) -> str | None:
    """Detect ATS platform from URL. Returns a short identifier or None."""
    u = url.lower()
    if "myworkdayjobs.com" in u or "myworkday.com" in u or "wd1." in u or "wd5." in u:
        return "workday"
    if "greenhouse.io" in u or "boards.greenhouse" in u:
        return "greenhouse"
    if "lever.co" in u or "jobs.lever" in u:
        return "lever"
    if "icims.com" in u:
        return "icims"
    if "smartrecruiters.com" in u:
        return "smartrecruiters"
    if "taleo.net" in u:
        return "taleo"
    if "ashbyhq.com" in u:
        return "ashby"
    return None


# ---------------------------------------------------------------------------
# Playbook registry
# ---------------------------------------------------------------------------

# Key: (ats_platform, widget_type). Use "generic" as ats for platform-agnostic recipes.
PLAYBOOK_REGISTRY: dict[tuple[str, str], InteractionRecipe] = {}


def _register(ats: str, widget_type: str, recipe: InteractionRecipe) -> None:
    PLAYBOOK_REGISTRY[(ats, widget_type)] = recipe


def lookup_playbook(ats: str | None, widget_type: str) -> InteractionRecipe | None:
    """Find a recipe. Tries (ats, widget_type) first, then ("generic", widget_type)."""
    if ats:
        recipe = PLAYBOOK_REGISTRY.get((ats, widget_type))
        if recipe:
            return recipe
    return PLAYBOOK_REGISTRY.get(("generic", widget_type))


# ---------------------------------------------------------------------------
# Built-in recipes
# ---------------------------------------------------------------------------

# Workday combo-box (state, country, degree, field-of-study, "how did you hear", etc.)
# Pattern: input value → Enter to trigger filter/search → click matching option from results
# Works for multi-level dropdowns: Enter filters across all layers, no need to navigate tree manually
_register("workday", "combobox", InteractionRecipe(
    widget_type="combobox",
    ats_platform="workday",
    description="Input value directly, press Enter to trigger filter, click matching option from results",
    steps=[
        InteractionStep(action="input", target="{idx}", value="{answer}", wait_ms=400, note="Type value directly into field"),
        InteractionStep(action="keys", target="Enter", wait_ms=1000, note="Trigger filter/search — options appear after Enter"),
        InteractionStep(action="click", target="{matching_option_idx}", wait_ms=300, note="Click the matching option from state"),
    ],
))

# Workday ReactVirtualized dropdown (field-of-study, some degree fields)
# These don't respond to fill/type — must type char-by-char via keys then pick from list
_register("workday", "react_virtualized", InteractionRecipe(
    widget_type="react_virtualized",
    ats_platform="workday",
    description="Click to open, type char-by-char via keys, wait for filter, click matching option from state",
    steps=[
        InteractionStep(action="click", target="{idx}", wait_ms=400, note="Open ReactVirtualized dropdown"),
        InteractionStep(action="keys", target="{answer}", wait_ms=600, note="Type char-by-char to filter (use browser-use keys, not type)"),
        InteractionStep(action="keys", target="Enter", wait_ms=300, note="Optionally press Enter"),
    ],
))

# Workday segmented date field (start date, graduation date, etc.)
# Separate month / day / year segments clicked individually
_register("workday", "date_segmented", InteractionRecipe(
    widget_type="date_segmented",
    ats_platform="workday",
    description="Click month segment, type MM, click day segment, type DD, click year segment, type YYYY",
    steps=[
        InteractionStep(action="click", target="{idx_month}", wait_ms=200, note="Click month segment"),
        InteractionStep(action="keys", target="{month}", wait_ms=200, note="Type 2-digit month (MM)"),
        InteractionStep(action="click", target="{idx_day}", wait_ms=200, note="Click day segment"),
        InteractionStep(action="keys", target="{day}", wait_ms=200, note="Type 2-digit day (DD)"),
        InteractionStep(action="click", target="{idx_year}", wait_ms=200, note="Click year segment"),
        InteractionStep(action="keys", target="{year}", wait_ms=200, note="Type 4-digit year (YYYY)"),
    ],
))

# Generic standard HTML <select> element
_register("generic", "select", InteractionRecipe(
    widget_type="select",
    ats_platform=None,
    description="Click to open, select option by text",
    steps=[
        InteractionStep(action="click", target="{idx}", wait_ms=200, note="Open select"),
        InteractionStep(action="select", target="{idx}", value="{answer}", wait_ms=200, note="Select option"),
    ],
))

# Generic radio button group
_register("generic", "radio", InteractionRecipe(
    widget_type="radio",
    ats_platform=None,
    description="Click the radio button whose label matches the answer",
    steps=[
        InteractionStep(action="click", target="{idx}", wait_ms=200, note="Click radio matching answer"),
    ],
))
