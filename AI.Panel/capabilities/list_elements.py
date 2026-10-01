# -*- coding: utf-8 -*-
# capabilities/list_elements.py
# List or count elements in the model by category, with optional property display.
# Absorbs count_elements — count_elements.py can be removed.

ACTION_NAME = "list_elements"

DESCRIPTION = (
    "List or count elements in the model for a given category and report their key properties. "
    "Use this when the user wants to see, count, or inspect elements — for example: "
    "'list all walls', 'show me the doors on Level 1', 'how many windows are there', "
    "'count furniture on Level 2', 'list rooms', 'show rooms on Level 1'. "
    "This action REPLACES count_elements — always use list_elements for counting too. "
    "Set count_only=true to return just the element count with no property rows. "
    "Specify category (required) and an optional level filter. "
    "Optional param 'properties' is a list of parameter display names to include per element "
    "(e.g. ['Mark', 'Comments', 'Family and Type']). Defaults to a sensible set per category. "
    "Optional param 'limit' caps the number of rows returned (default 30, max 100). "
    "For large family size queries use scan_large_families instead — it measures file sizes. "
    "This action reads only — it never creates or modifies anything."
)

PARAMS = {
    "category":   "string  — element category (e.g. 'walls', 'doors', 'furniture', 'rooms')",
    "level":      "string  — optional level name filter (e.g. 'Level 1')",
    "properties": "list    — optional parameter names to display per element (default: auto)",
    "limit":      "integer — max rows to return (default 30, max 100). Ignored when count_only=true.",
    "count_only": "boolean — when true return only the element count, no property rows (default false). "
                  "Use for 'how many X' queries.",
}

EXAMPLE = {
    "action": "list_elements",
    "params": {
        "category":   "doors",
        "level":      "Level 1",
        "properties": ["Mark", "Family and Type", "Comments"],
        "limit":      30,
    },
}

EXAMPLE_COUNT = {
    "action": "list_elements",
    "params": {
        "category":   "walls",
        "count_only": True,
    },
}

# Default property columns per category.
_DEFAULT_PROPS = {
    "walls":              ["Family and Type", "Unconnected Height", "Length", "Level"],
    "doors":              ["Mark", "Family and Type", "Level", "Comments"],
    "windows":            ["Mark", "Family and Type", "Level", "Comments"],
    "floors":             ["Family and Type", "Level", "Area"],
    "furniture":          ["Mark", "Family and Type", "Level", "Comments"],
    "rooms":              ["Name", "Number", "Level", "Area"],
    "ceilings":           ["Family and Type", "Level", "Area"],
    "columns":            ["Family and Type", "Level", "Comments"],
    "structural columns": ["Family and Type", "Base Level", "Comments"],
    "casework":           ["Mark", "Family and Type", "Level", "Comments"],
    "generic models":     ["Mark", "Family and Type", "Level", "Comments"],
}
_DEFAULT_FALLBACK = ["Mark", "Family and Type", "Level", "Comments"]
_MAX_LIMIT        = 100

# Fix LE4: StorageType imported at module scope — not re-imported on every
# _get_prop call. Safe because this module is loaded once per session.
# Actual CLR import deferred to first execute() call via lazy initialisation
# flag to avoid module-scope Revit API access under IronPython 2.7.
_StorageType = None


def _ensure_imports():
    global _StorageType
    if _StorageType is None:
        from Autodesk.Revit.DB import StorageType
        _StorageType = StorageType


def _get_prop(el, name):
    """Try LookupParameter by name, then built-in Name/Category/Level fallbacks.

    Fix LE4: uses module-cached _StorageType instead of importing inside the loop.
    """
    _ensure_imports()
    try:
        p = el.LookupParameter(name)
        if p is not None:
            st = p.StorageType
            if st == _StorageType.String:
                v = p.AsString()
                return v if v else ""
            if st == _StorageType.Double:
                return "{:.3f}".format(p.AsDouble())
            if st == _StorageType.Integer:
                return str(p.AsInteger())
            return p.AsValueString() or ""
    except Exception:
        pass

    # Fallbacks for virtual / computed properties.
    nl = name.lower()
    if nl in ("family and type", "type name", "family name"):
        try:
            return el.Name
        except Exception:
            pass
    if nl == "category":
        try:
            return el.Category.Name
        except Exception:
            pass
    if nl == "level":
        try:
            from Autodesk.Revit.DB import Level
            lv = el.Document.GetElement(el.LevelId)
            if isinstance(lv, Level):
                return lv.Name
        except Exception:
            pass
    return ""


def execute(params, doc, uidoc, resolve_category, eid_int, **_kwargs):
    from Autodesk.Revit.DB import FilteredElementCollector, Level, ElementId

    if not doc:
        return "No document open."

    cat_name = (params.get("category") or "").strip()
    if not cat_name:
        return "Missing required parameter: category."

    bic = resolve_category(cat_name)
    if bic is None:
        return (
            "Unknown category: '" + cat_name + "'. "
            "Valid categories: walls, doors, windows, floors, furniture, "
            "columns, structural columns, rooms, ceilings, casework, generic models."
        )

    level_filter = (params.get("level") or "").strip().lower()
    count_only   = bool(params.get("count_only", False))

    # Fix LE1: explicit None check so limit=0 is honoured rather than
    # falling through to the default (0 is falsy, "or 30" would give 30).
    raw_limit = params.get("limit")
    limit = min(int(raw_limit) if raw_limit is not None else 30, _MAX_LIMIT)

    props = params.get("properties") or _DEFAULT_PROPS.get(
                cat_name.lower(), _DEFAULT_FALLBACK)

    # ── Resolve level name to a Level ElementId ───────────────────────────────
    # Fix LE2: single collector pass — exact match first, partial fallback in
    # the same loop — no second full scan.
    level_id       = None
    level_name_out = ""
    if level_filter:
        partial_match = None
        partial_name  = ""
        for lv in FilteredElementCollector(doc).OfClass(Level).ToElements():
            try:
                lv_name = lv.Name
                if lv_name.lower() == level_filter:
                    level_id       = lv.Id
                    level_name_out = lv_name
                    break
                if partial_match is None and level_filter in lv_name.lower():
                    partial_match = lv.Id
                    partial_name  = lv_name
            except Exception:
                pass
        if level_id is None and partial_match is not None:
            level_id       = partial_match
            level_name_out = partial_name

    # ── Collect elements ──────────────────────────────────────────────────────
    # Fix LE3: unified ElementId(int(bic)) pattern with fallback — same as
    # list_elements already used; count_elements used OfCategory(bic) directly.
    # Fix LE6: FamilyInstance import removed — was never used.
    try:
        try:
            cat_id = ElementId(int(bic))
        except Exception:
            cat_id = ElementId(bic)

        elems = list(
            FilteredElementCollector(doc)
            .OfCategoryId(cat_id)
            .WhereElementIsNotElementType()
            .ToElements()
        )
    except Exception as ex:
        return "Failed to collect elements: " + str(ex)

    # ── Level filter ──────────────────────────────────────────────────────────
    if level_id is not None:
        filtered = []
        for el in elems:
            try:
                if el.LevelId == level_id:
                    filtered.append(el)
                    continue
            except Exception:
                pass
            try:
                lv_param = el.LookupParameter("Level")
                if lv_param and lv_param.AsElementId() == level_id:
                    filtered.append(el)
            except Exception:
                pass
        elems = filtered

    total = len(elems)

    # ── count_only: return count string and stop ──────────────────────────────
    if count_only:
        msg = str(total) + " " + cat_name + " instance(s)"
        if level_name_out:
            msg += " on '" + level_name_out + "'"
        msg += " in model."
        return msg

    # ── Full listing ──────────────────────────────────────────────────────────
    elems = elems[:limit]

    if not elems:
        msg = "No " + cat_name + " elements found"
        if level_name_out:
            msg += " on level '" + level_name_out + "'"
        return msg + "."

    # Build table rows.
    col_headers = ["ID"] + list(props)
    rows        = []
    for el in elems:
        row = [str(eid_int(el.Id))]
        for prop in props:
            row.append(_get_prop(el, prop) or "-")
        rows.append(row)

    # Fix LE5: column widths driven by actual content, not a fixed 80-char cap.
    widths = [len(h) for h in col_headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(cell))

    sep     = "  |  "
    header  = sep.join(h.ljust(widths[i]) for i, h in enumerate(col_headers))
    divider = "-" * len(header)

    lines = [header, divider]
    for row in rows:
        lines.append(sep.join(
            (row[i] if i < len(row) else "-").ljust(widths[i])
            for i in range(len(col_headers))
        ))

    level_note = (" on '" + level_name_out + "'" if level_name_out else "")
    summary = "Showing {shown} of {total} {cat} element(s){level}.".format(
        shown=len(elems),
        total=total,
        cat=cat_name,
        level=level_note,
    )
    if total > limit:
        summary += " Use limit param (max {0}) to see more.".format(_MAX_LIMIT)

    return summary + "\n" + "\n".join(lines)
