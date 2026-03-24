"""
Fill preparation service — parses browser-use state output and builds fill engine input JSON.

Workflow:
  1. Parse state text to extract {element_id, element_name, aria_label} -> element_idx maps
  2. Match resolver results to DOM elements using token-overlap scoring
  3. Return a fill-engine-ready input dict
"""
from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Semantic synonym table — platform-agnostic label normalization
# ---------------------------------------------------------------------------

# Each entry expands a token to its semantic equivalents.
# Bidirectional: if "school" maps to "university", also add "university" -> "school".
_SYNONYMS: dict[str, frozenset[str]] = {
    "gpa":            frozenset({"grade", "result"}),
    "grade":          frozenset({"gpa", "result"}),
    "result":         frozenset({"gpa", "grade"}),
    "school":         frozenset({"university", "college", "institution"}),
    "university":     frozenset({"school", "college"}),
    "college":        frozenset({"school", "university"}),
    "employer":       frozenset({"company", "organization"}),
    "company":        frozenset({"employer", "organization"}),
    "organization":   frozenset({"employer", "company"}),
    "zip":            frozenset({"postal"}),
    "postal":         frozenset({"zip"}),
    "start":          frozenset({"from", "begin"}),
    "from":           frozenset({"start", "begin"}),
    "end":            frozenset({"finish"}),
    "graduation":     frozenset({"completion"}),
    "phone":          frozenset({"tel", "mobile", "cell", "telephone"}),
    "tel":            frozenset({"phone", "mobile", "cell"}),
    "mobile":         frozenset({"phone", "tel", "cell"}),
    "street":         frozenset({"address"}),
    "authorization":  frozenset({"authorized", "auth"}),
    "authorized":     frozenset({"authorization", "auth"}),
}

_FILLER_WORDS = frozenset({
    "select", "one", "please", "enter", "your", "the", "a", "an",
    "or", "and", "is", "of", "in", "at", "for", "how", "did",
    "you", "us", "have", "will", "are", "do", "does", "was", "were",
    "what", "which", "this", "that", "with", "about", "to",
})

# Minimum overlap score to consider a match valid
_MATCH_THRESHOLD = 0.35


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def _normalize_tokens(s: str) -> frozenset[str]:
    """
    Normalize a human-readable string to a frozenset of meaningful tokens.

    1. Keep parenthetical content as tokens: "Overall Result (GPA)" -> "overall result gpa"
    2. Lowercase, replace non-alphanumeric with spaces
    3. Drop filler words and pure numbers
    4. Expand synonyms
    """
    s = re.sub(r'[()]', ' ', s)
    s = re.sub(r'[^a-z0-9\s]', ' ', s.lower())
    tokens = {t for t in s.split() if t and t not in _FILLER_WORDS and not t.isdigit()}

    expanded = set(tokens)
    for token in tokens:
        expanded.update(_SYNONYMS.get(token, frozenset()))
    return frozenset(expanded)


def _id_to_tokens(elem_id: str) -> frozenset[str]:
    """
    Convert an element id or name to a normalized token set.

    'education-5--schoolName'     -> {'education', 'school', 'name', 'university', ...}
    'name--legalName--firstName'  -> {'name', 'legal', 'first'}
    """
    parts = re.split(r'[-]+', elem_id)
    tokens: set[str] = set()
    for part in parts:
        if not part or part.isdigit():
            continue
        words = re.sub(r'([a-z])([A-Z])', r'\1 \2', part).lower().split()
        tokens.update(w for w in words if w not in _FILLER_WORDS and not w.isdigit())

    expanded = set(tokens)
    for token in tokens:
        expanded.update(_SYNONYMS.get(token, frozenset()))
    return frozenset(expanded)


def _overlap_score(a: frozenset[str], b: frozenset[str]) -> float:
    """Token overlap: |intersection| / min(|a|, |b|). Returns 0 if either set is empty."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# ---------------------------------------------------------------------------
# State parser
# ---------------------------------------------------------------------------

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
    checkbox_idxs: set[int] = set()

    for line in state_text.split("\n"):
        idx_match = re.search(r"\[(\d+)\]", line)
        if not idx_match:
            continue
        idx = int(idx_match.group(1))

        if re.search(r"\btype=checkbox\b", line):
            checkbox_idxs.add(idx)

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

    return {"by_id": by_id, "by_name": by_name, "by_aria_label": by_aria_label, "checkbox_idxs": checkbox_idxs}


# ---------------------------------------------------------------------------
# Field matcher
# ---------------------------------------------------------------------------

def match_field_to_element(field_label: str, widget_type: str | None, elements: dict) -> dict:
    """
    Match a field label to a DOM element using token-overlap scoring.

    Scores all aria-labels, element IDs, and element names against the normalized
    field label tokens. Returns the best match above _MATCH_THRESHOLD.

    Matching signals (checked together, best score wins):
    - aria-label: most reliable — human-readable, direct label text
    - element id: structured but semantic (camelCase segments, synonym-expanded)
    - element name: fallback for elements without id

    Returns:
        {'element_id': str|None, 'element_name': str|None, 'element_idx': int|None}
    """
    label_tokens = _normalize_tokens(field_label)

    best_score = 0.0
    best_idx: int | None = None
    best_elem_id: str | None = None
    best_elem_name: str | None = None

    # 1. Aria-labels (highest signal)
    for aria_label, idx in elements["by_aria_label"].items():
        score = _overlap_score(label_tokens, _normalize_tokens(aria_label))
        if score > best_score:
            best_score = score
            best_idx = idx
            best_elem_id = None
            best_elem_name = None

    # 2. Element IDs
    for elem_id, idx in elements["by_id"].items():
        score = _overlap_score(label_tokens, _id_to_tokens(elem_id))
        if score > best_score:
            best_score = score
            best_idx = idx
            best_elem_id = elem_id
            best_elem_name = next(
                (n for n, nidx in elements["by_name"].items() if nidx == idx), None
            )

    # 3. Element names (last resort)
    for elem_name, idx in elements["by_name"].items():
        score = _overlap_score(label_tokens, _id_to_tokens(elem_name))
        if score > best_score:
            best_score = score
            best_idx = idx
            best_elem_id = None
            best_elem_name = elem_name

    if best_score < _MATCH_THRESHOLD or best_idx is None:
        return {"element_id": None, "element_name": None, "element_idx": None}

    return {
        "element_id": best_elem_id,
        "element_name": best_elem_name,
        "element_idx": best_idx,
    }


# ---------------------------------------------------------------------------
# Fill input builder
# ---------------------------------------------------------------------------

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

        match = match_field_to_element(result["label"], widget_type, elements)
        field.update(match)

        # Auto-detect checkboxes: if the matched element is input[type=checkbox],
        # override widget_type regardless of what the resolver guessed.
        matched_idx = field.get("element_idx")
        if matched_idx is not None and matched_idx in elements.get("checkbox_idxs", ()):
            field["widget_type"] = "checkbox"

        fields.append(field)

    # Convert checkbox_idxs set to list for JSON serialization
    serializable_elements = {**elements, "checkbox_idxs": list(elements["checkbox_idxs"])}

    return {
        "fields": fields,
        "element_map": serializable_elements,
        "ats_platform": ats,
    }
