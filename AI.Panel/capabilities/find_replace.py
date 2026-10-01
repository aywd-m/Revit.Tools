# -*- coding: utf-8 -*-
# capabilities/find_replace.py
# Kidzink Koda capability — Find & Replace parameter text
# Scans selected elements (or all elements if nothing is selected) for a text
# value in a named parameter and replaces it.  Reports a preview of matches
# BEFORE writing — the user must confirm by clicking "Run in Revit".
# (c) Archie C. Manza 2026

ACTION_NAME = "find_replace"

DESCRIPTION = (
    "Find and replace text in a parameter across selected elements "
    "(or all model elements if nothing is selected). "
    "Specify the parameter name, find text, and replacement text. "
    "Use param_name='ALL' to search every writable string parameter. "
    "Case-insensitive by default; set case_sensitive=true to match exactly."
)

PARAMS = {
    "param_name":     "string — parameter display name to search, or 'ALL' for every writable string parameter",
    "find_text":      "string — text to find",
    "replace_text":   "string — replacement text (may be empty to delete the matched text)",
    "case_sensitive": "boolean — true for case-sensitive matching (default false)",
}

EXAMPLE = {
    "action": "find_replace",
    "params": {
        "param_name":   "Comments",
        "find_text":    "TBC",
        "replace_text": "Confirmed",
        "case_sensitive": False,
    },
}

_MAX_PREVIEW = 20   # bubble shows at most this many matches
_MAX_ELEMENTS = 5000  # cap for whole-model scan


def _scan(doc, element_ids, param_name, find_text, replace_text, case_sensitive):
    """Return list of dicts {elem, param, current_value, new_value}."""
    import re as _re
    results = []
    fl = param_name.strip().lower()
    all_params = (fl == "all")
    pattern = (
        _re.compile(_re.escape(find_text), 0 if case_sensitive else _re.IGNORECASE)
        if not case_sensitive
        else None
    )

    for eid in element_ids:
        try:
            el = doc.GetElement(eid)
            if el is None:
                continue
            for p in el.Parameters:
                try:
                    if p.IsReadOnly:
                        continue
                    from Autodesk.Revit.DB import StorageType
                    if p.StorageType != StorageType.String:
                        continue
                    if not all_params and p.Definition.Name.lower() != fl:
                        continue
                    cur = p.AsString()
                    if not cur:
                        continue
                    if case_sensitive:
                        if find_text not in cur:
                            continue
                        new_val = cur.replace(find_text, replace_text)
                    else:
                        import re as _re2
                        pat = _re2.compile(_re2.escape(find_text), _re2.IGNORECASE)
                        if not pat.search(cur):
                            continue
                        new_val = pat.sub(replace_text, cur)
                    if new_val != cur:
                        results.append({
                            "elem":          el,
                            "param":         p,
                            "current_value": cur,
                            "new_value":     new_val,
                        })
                except Exception:
                    continue
        except Exception:
            continue
    return results


def execute(params, doc, uidoc, eid_int, **_kwargs):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, Transaction
    )

    if not doc:
        return "No document open."

    param_name     = (params.get("param_name",   "") or "").strip()
    find_text      = (params.get("find_text",     "") or "")
    replace_text   = (params.get("replace_text",  "") or "")
    case_sensitive = bool(params.get("case_sensitive", False))

    if not param_name:
        return "Missing required parameter: param_name."
    if not find_text:
        return "Missing required parameter: find_text."

    # ── Element scope ──────────────────────────────────────────────────────
    try:
        sel_ids = list(uidoc.Selection.GetElementIds())
    except Exception:
        sel_ids = []

    if sel_ids:
        element_ids = sel_ids
        scope_msg   = str(len(sel_ids)) + " selected element(s)"
    else:
        try:
            all_elems   = (FilteredElementCollector(doc)
                           .WhereElementIsNotElementType()
                           .ToElementIds())
            element_ids = list(all_elems)[:_MAX_ELEMENTS]
        except Exception as fe:
            return "Failed to collect elements: " + str(fe)
        scope_msg = "entire model (" + str(len(element_ids)) + " elements scanned)"

    if not element_ids:
        return "No elements found to scan."

    # ── Scan ───────────────────────────────────────────────────────────────
    try:
        results = _scan(doc, element_ids, param_name, find_text,
                        replace_text, case_sensitive)
    except Exception as se:
        return "Scan failed: " + str(se)

    if not results:
        return (
            "No matches for '{find}' in parameter '{param}' "
            "across {scope}."
        ).format(find=find_text, param=param_name, scope=scope_msg)

    # ── Apply replacements in a transaction ───────────────────────────────
    tx = Transaction(doc, "Koda: Find & Replace")
    tx.Start()
    count  = 0
    errors = []
    try:
        for item in results:
            try:
                item["param"].Set(item["new_value"])
                count += 1
            except Exception as pe:
                errors.append(
                    "ID " + str(eid_int(item["elem"].Id)) +
                    " '" + item["param"].Definition.Name + "': " + str(pe)
                )
        tx.Commit()
    except Exception as te:
        try:
            tx.RollBack()
        except Exception:
            pass
        return "Transaction failed: " + str(te)

    # ── Summary ────────────────────────────────────────────────────────────
    preview_lines = []
    for item in results[:_MAX_PREVIEW]:
        try:
            cat = item["elem"].Category.Name + " "
        except Exception:
            cat = ""
        eid_v = eid_int(item["elem"].Id)
        preview_lines.append(
            cat + "(id " + str(eid_v) + ") " +
            item["param"].Definition.Name + ": \"" +
            item["current_value"] + "\" → \"" + item["new_value"] + "\""
        )

    msg = (
        "Replaced {count} of {total} match(es) for '{find}' "
        "→ '{rep}' in parameter '{param}' across {scope}."
    ).format(
        count=count,
        total=len(results),
        find=find_text,
        rep=replace_text,
        param=param_name,
        scope=scope_msg,
    )
    if len(results) > _MAX_PREVIEW:
        msg += " (Showing first {n} of {t}.)".format(
            n=_MAX_PREVIEW, t=len(results))
    if preview_lines:
        msg += "\n" + "\n".join(preview_lines)
    if errors:
        msg += "\nErrors (" + str(len(errors)) + "): " + "; ".join(errors[:5])
    return msg
