"""
Fill preparation service — parses browser-use state output and builds fill engine input JSON.

Workflow:
  1. Parse state text to extract {element_id, element_name, aria_label} -> element_idx maps
  2. Match resolver results to DOM elements using heuristics
  3. Return a fill-engine-ready input dict
"""
from __future__ import annotations

import re
from typing import Any


def parse_state_elements(state_text: str) -> dict:
    """
    Parse browser-use state output to build element lookup maps.

    Handles lines like:
      [711]<input type=text id=name--legalName--firstName name=legalName--firstName required=true />
      [757]<button aria-label=State Select One name=countryRegion id=address--countryRegion />
      |SHADOW(open)|[898]<input placeholder=Search autocomplete=off id=source--source required=true />

    Returns:
        {
            'by_id': {element_id: idx, ...},
            'by_name': {element_name: idx, ...},
            'by_aria_label': {aria_label_lower: idx, ...},
        }
    """
    by_id: dict[str, int] = {}
    by_name: dict[str, int] = {}
    by_aria_label: dict[str, int] = {}

    for line in state_text.split("\n"):
        idx_match = re.search(r"\[(\d+)\]", line)
        if not idx_match:
            continue
        idx = int(idx_match.group(1))

        id_match = re.search(r"\bid=([^\s/>]+)", line)
        if id_match:
            by_id[id_match.group(1)] = idx

        name_match = re.search(r"\bname=([^\s/>]+)", line)
        if name_match:
            by_name[name_match.group(1)] = idx

        # aria-label may have spaces; capture until the next known attribute or end of tag
        aria_match = re.search(r"aria-label=([^/>]+?)(?=\s+\w+=|\s*/>|\s*>)", line)
        if aria_match:
            by_aria_label[aria_match.group(1).strip().lower()] = idx

    return {"by_id": by_id, "by_name": by_name, "by_aria_label": by_aria_label}


def _camel_to_words(s: str) -> str:
    """Convert camelCase or PascalCase to lowercase words. e.g. 'firstName' -> 'first name'."""
    # Insert space before uppercase letters that follow lowercase
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    return s.lower().strip()


def match_field_to_element(field_label: str, widget_type: str | None, elements: dict) -> dict:
    """
    Try to match a field label to a DOM element using heuristics.

    Matching priority:
    1. Exact aria-label match (case-insensitive)
    2. Partial aria-label match (label is substring of aria-label, or aria-label starts with label)
    3. ID suffix matching — last segment of element id converted from camelCase to words

    Returns:
        {'element_id': str|None, 'element_name': str|None, 'element_idx': int|None}
    """
    label_lower = field_label.lower().strip()
    result: dict[str, Any] = {"element_id": None, "element_name": None, "element_idx": None}

    # 1. Exact aria-label match
    if label_lower in elements["by_aria_label"]:
        idx = elements["by_aria_label"][label_lower]
        result["element_idx"] = idx
        return result

    # 2. Partial aria-label match
    for aria_label, idx in elements["by_aria_label"].items():
        if label_lower in aria_label or aria_label.startswith(label_lower):
            result["element_idx"] = idx
            return result

    # 3. ID suffix matching (e.g., "firstName" -> "first name" ~ "First Name")
    for elem_id, idx in elements["by_id"].items():
        # Take the last segment after '--' (or the full id if no separator)
        suffix = elem_id.split("--")[-1]
        words = _camel_to_words(suffix)
        if label_lower in words or words in label_lower:
            result["element_id"] = elem_id
            result["element_idx"] = idx
            # Also try to find element_name for this element_id
            # by_name values are the same idx
            for name, nidx in elements["by_name"].items():
                if nidx == idx:
                    result["element_name"] = name
                    break
            return result

    # 4. Name-based matching as last resort (camelCase to words)
    for elem_name, idx in elements["by_name"].items():
        words = _camel_to_words(elem_name)
        if label_lower in words or words in label_lower:
            result["element_name"] = elem_name
            result["element_idx"] = idx
            return result

    return result


def build_fill_input(
    resolver_results: list[dict],
    state_text: str,
    ats: str = "workday",
) -> dict:
    """
    Build fill engine input JSON from resolver output + browser state.

    Args:
        resolver_results: list of resolve_batch result dicts (label, answer, policy,
                          interaction_recipe, ...)
        state_text: raw text output from `uvx browser-use state`
        ats: ATS platform identifier (workday, greenhouse, etc.)

    Returns:
        dict suitable for writing to /tmp/autoapply_fill_input.json
    """
    elements = parse_state_elements(state_text)

    fields = []
    for result in resolver_results:
        if result.get("answer") is None:
            continue
        if result.get("policy") == "ask_user":
            continue

        recipe = result.get("interaction_recipe") or {}
        widget_type = recipe.get("widget_type", "text")

        field: dict[str, Any] = {
            "label": result["label"],
            "answer": result["answer"],
            "widget_type": widget_type,
            "element_id": None,
            "element_name": None,
            "element_idx": None,
        }

        # Try to match to DOM element
        match = match_field_to_element(result["label"], widget_type, elements)
        field.update(match)

        fields.append(field)

    return {
        "fields": fields,
        "element_map": elements,
        "ats_platform": ats,
    }
