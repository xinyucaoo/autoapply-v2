"""
Fill engine — runs inside `uvx browser-use python --file scripts/fill_engine.py`.

Reads /tmp/autoapply_fill_input.json, fills each field using the appropriate
strategy, and writes results to /tmp/autoapply_fill_output.json.

Available globals (injected by browser-use runtime):
  browser — browser automation object
  json, re, os, Path, asyncio — pre-imported stdlib
"""
import json
import time

INPUT_FILE = "/tmp/autoapply_fill_input.json"
OUTPUT_FILE = "/tmp/autoapply_fill_output.json"


def get_page():
    """Get current Playwright page synchronously."""
    return browser._run(browser._session.get_current_page())


def fill_text(field):
    """Fill a text/textarea/email input by element index."""
    idx = field.get("element_idx")
    value = field["answer"]
    if idx is None:
        return "manual_required", None
    browser.input(idx, value)
    browser.wait(0.15)
    return "success", None


def fill_combobox(field):
    """
    Fill a combobox/autocomplete widget.

    Strategy (type-enter-select):
    1. Input the value directly into the field (works through shadow DOM)
    2. Press Enter to trigger search/filter
    3. Wait 1.0s for filtered options to appear
    4. Find and click matching option via JS (traverses shadow DOM)
       - Works for multi-level dropdowns: Enter filters across all layers
    5. Fall back to pressing Enter again if no option visible yet
    """
    idx = field.get("element_idx")
    value = field["answer"]
    if idx is None:
        return "manual_required", None

    browser.input(idx, value)   # fill shadow DOM input directly
    browser.wait(0.4)
    browser.keys('Enter')       # trigger filter/search
    browser.wait(1.0)           # wait for filtered options to load

    page = get_page()
    js_value = json.dumps(value.lower())

    result = browser._run(page.evaluate(f"""
() => {{
    const val = {js_value};
    function findAndClick(root) {{
        const opts = root.querySelectorAll('[role=option]');
        for (const o of opts) {{
            const label = (o.getAttribute('aria-label') || o.textContent || '').toLowerCase().trim();
            if (label.includes(val)) {{ o.click(); return 'clicked: ' + label; }}
        }}
        for (const el of root.querySelectorAll('*')) {{
            if (el.shadowRoot) {{ const r = findAndClick(el.shadowRoot); if (r) return r; }}
        }}
        return null;
    }}
    return findAndClick(document);
}}
"""))

    if result is None:
        browser.keys('Enter')  # fallback: Enter may have already selected top match

    browser.wait(0.3)
    return "success", None


def fill_native_select(field):
    """Fill a native <select> or custom listbox dropdown."""
    idx = field.get("element_idx")
    value = field["answer"]
    if idx is None:
        return "manual_required", None

    browser.click(idx)
    browser.wait(0.4)

    page = get_page()
    js_value = json.dumps(value.lower())

    result = browser._run(page.evaluate(f"""
() => {{
    const val = {js_value};
    function findAndClick(root) {{
        // Try <li role=option> first (custom dropdowns)
        const listOpts = root.querySelectorAll('li[role=option], [role=listbox] [role=option]');
        for (const o of listOpts) {{
            const label = (o.getAttribute('aria-label') || o.textContent || '').toLowerCase().trim();
            if (label === val || label.includes(val)) {{ o.click(); return 'clicked li: ' + label; }}
        }}
        // Try <option> in <select>
        const selects = root.querySelectorAll('select');
        for (const sel of selects) {{
            for (const opt of sel.options) {{
                if (opt.text.toLowerCase().trim() === val || opt.value.toLowerCase().trim() === val) {{
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return 'selected: ' + opt.text;
                }}
            }}
        }}
        for (const el of root.querySelectorAll('*')) {{
            if (el.shadowRoot) {{ const r = findAndClick(el.shadowRoot); if (r) return r; }}
        }}
        return null;
    }}
    return findAndClick(document);
}}
"""))

    if result is None:
        browser.keys('Enter')  # fallback

    browser.wait(0.3)
    return "success", None


def fill_radio(field):
    """
    Click the correct radio button for yes/no or custom values.

    Traverses shadow DOM. Maps "yes"/"true" -> value=true/yes, "no"/"false" -> value=false/no.
    For other values, does a text-based label match.
    """
    value = field["answer"]
    element_name = field.get("element_name")

    page = get_page()
    js_value = json.dumps(value.lower())
    js_name = json.dumps(element_name or "")

    result = browser._run(page.evaluate(f"""
() => {{
    const val = {js_value};
    const name = {js_name};
    function findRadio(root) {{
        const radios = root.querySelectorAll('input[type=radio]');
        for (const r of radios) {{
            // Filter by name if provided
            if (name && r.name && r.name !== name) continue;
            const rv = (r.value || '').toLowerCase();
            // Yes/true
            if ((val === 'yes' || val === 'true') && (rv === 'true' || rv === 'yes')) {{
                r.click(); return 'clicked yes radio: ' + rv;
            }}
            // No/false
            if ((val === 'no' || val === 'false') && (rv === 'false' || rv === 'no')) {{
                r.click(); return 'clicked no radio: ' + rv;
            }}
            // Generic value match
            if (rv === val) {{
                r.click(); return 'clicked radio by value: ' + rv;
            }}
        }}
        // Try label text match as fallback
        const labels = root.querySelectorAll('label');
        for (const lbl of labels) {{
            const txt = (lbl.textContent || '').toLowerCase().trim();
            if (txt === val || txt.includes(val)) {{
                const input = lbl.querySelector('input[type=radio]') ||
                              (lbl.htmlFor ? root.getElementById(lbl.htmlFor) : null);
                if (input) {{ input.click(); return 'clicked radio by label: ' + txt; }}
                lbl.click(); return 'clicked label: ' + txt;
            }}
        }}
        for (const el of root.querySelectorAll('*')) {{
            if (el.shadowRoot) {{ const r = findRadio(el.shadowRoot); if (r) return r; }}
        }}
        return null;
    }}
    return findRadio(document);
}}
"""))

    browser.wait(0.2)
    if result is None:
        return "failure", f"No radio found for value={value!r} name={element_name!r}"
    return "success", None


def fill_file(field):
    """Upload a file at the given path."""
    idx = field.get("element_idx")
    value = field["answer"]  # file path
    if idx is None:
        return "manual_required", None
    browser.upload(idx, value)
    browser.wait(1.5)
    return "success", None


def fill_date_segmented(field):
    """
    Fill a segmented date field (separate month/year inputs).

    Expects field to have element_idx_month and element_idx_year keys,
    and answer to be "YYYY-MM" or "MM/YYYY" or just "YYYY".
    """
    value = field["answer"]  # Expected: "YYYY-MM" or "MM/YYYY"
    idx_month = field.get("element_idx_month")
    idx_year = field.get("element_idx_year")

    # Parse value — support "YYYY-MM", "MM/YYYY", "YYYY"
    month = None
    year = None
    if "-" in value and len(value) >= 7:
        parts = value.split("-")
        if len(parts[0]) == 4:
            year, month = parts[0], parts[1].zfill(2)
        else:
            month, year = parts[0].zfill(2), parts[1]
    elif "/" in value:
        parts = value.split("/")
        month, year = parts[0].zfill(2), parts[1]
    else:
        year = value
        month = "01"

    if idx_month and month:
        browser.click(idx_month)
        browser.wait(0.3)
        browser.keys(month)
    if idx_year and year:
        browser.click(idx_year)
        browser.wait(0.3)
        browser.keys(year)

    return "success", None


def fill_checkbox(field):
    """Check or uncheck a checkbox based on value."""
    idx = field.get("element_idx")
    value = field["answer"].lower().strip()
    should_check = value in ("true", "yes", "1", "on", "checked")

    page = get_page()
    js_idx = json.dumps(idx)
    js_check = "true" if should_check else "false"

    if idx is not None:
        # Try by index first via JS click
        result = browser._run(page.evaluate(f"""
() => {{
    const shouldCheck = {js_check};
    function findCheckbox(root) {{
        const boxes = root.querySelectorAll('input[type=checkbox]');
        if (boxes.length > 0) {{
            const box = boxes[0];
            if (box.checked !== shouldCheck) {{
                box.click();
                return 'toggled checkbox to ' + shouldCheck;
            }}
            return 'checkbox already ' + shouldCheck;
        }}
        for (const el of root.querySelectorAll('*')) {{
            if (el.shadowRoot) {{ const r = findCheckbox(el.shadowRoot); if (r) return r; }}
        }}
        return null;
    }}
    return findCheckbox(document);
}}
"""))
        browser.wait(0.2)
        if result:
            return "success", None

    # Fallback: just click by idx
    if idx is not None:
        browser.click(idx)
        browser.wait(0.2)
        return "success", None

    return "manual_required", None


# --- Dispatch table ---

FILL_STRATEGIES = {
    "text": fill_text,
    "textarea": fill_text,
    "email": fill_text,
    "combobox": fill_combobox,
    "autocomplete": fill_combobox,
    "select": fill_native_select,
    "native_select": fill_native_select,
    "radio": fill_radio,
    "file": fill_file,
    "date_segmented": fill_date_segmented,
    "checkbox": fill_checkbox,
}


def fill_field(field):
    """Dispatch to the appropriate fill strategy and return a result dict."""
    label = field.get("label", "unknown")
    answer = field.get("answer")
    widget_type = field.get("widget_type", "text")

    if answer is None:
        return {"label": label, "status": "skipped", "answer": None}

    strategy = FILL_STRATEGIES.get(widget_type, fill_text)
    try:
        status, error = strategy(field)
        result = {"label": label, "status": status, "answer": answer}
        if error:
            result["error"] = error
        return result
    except Exception as e:
        return {"label": label, "status": "error", "answer": answer, "error": str(e)}


def main():
    # Read input
    with open(INPUT_FILE) as f:
        data = json.load(f)

    fields = data.get("fields", [])
    results = []

    for field in fields:
        result = fill_field(field)
        results.append(result)
        # Small pause between fields to avoid overwhelming the page
        time.sleep(0.05)

    # Build summary
    status_counts = {"success": 0, "failure": 0, "skipped": 0, "manual_required": 0, "error": 0}
    for r in results:
        s = r.get("status", "error")
        if s in status_counts:
            status_counts[s] += 1
        else:
            status_counts["error"] += 1

    summary = {
        "total": len(results),
        "success": status_counts["success"],
        "failure": status_counts["failure"] + status_counts["error"],
        "skipped": status_counts["skipped"],
        "manual_required": status_counts["manual_required"],
    }

    output = {"results": results, "summary": summary}

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Fill engine complete: {summary['success']}/{summary['total']} succeeded, "
          f"{summary['failure']} failed, {summary['skipped']} skipped, "
          f"{summary['manual_required']} manual_required")


main()
