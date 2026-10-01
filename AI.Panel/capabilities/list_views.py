# -*- coding: utf-8 -*-
# capabilities/list_views.py
# Plugin: list views OR sheets in the model, optionally filtered by type.
# Absorbs list_sheets.py — list_sheets.py can be removed.

ACTION_NAME  = "list_views"
DESCRIPTION  = (
    "List views or sheets in the model. "
    "This action REPLACES list_sheets — always use list_views for sheets too. "
    "Filter by 'type' param: "
    "  sheets    — all sheets (ViewSheet), with sheet number, name, revision, issue date. "
    "  floorplan — floor plan views. "
    "  ceilingplan — reflected ceiling plan views. "
    "  elevation — elevation views. "
    "  section   — section views. "
    "  threed / 3d — 3D views. "
    "  drafting  — drafting views. "
    "  all       — every non-template view (default). "
    "Use 'limit' to cap the number of rows returned (default 50, max 500). "
    "Use 'search' for a case-insensitive name substring filter."
)
PARAMS = {
    "type":   "string  — sheets | floorplan | ceilingplan | elevation | section | threed | drafting | all (default: all)",
    "limit":  "integer — max rows to return (default 50, max 500)",
    "search": "string  — optional substring to filter view/sheet names (case-insensitive)",
}
EXAMPLE = {
    "action": "list_views",
    "params": {"type": "sheets"},
}
EXAMPLE_VIEWS = {
    "action": "list_views",
    "params": {"type": "floorplan", "limit": 20},
}

_MAX_LIMIT = 500


def _sheet_entry(sh):
    """Build a display string for a ViewSheet row."""
    from Autodesk.Revit.DB import BuiltInParameter

    # Sheet number
    num = ""
    try:
        num = sh.SheetNumber or ""
    except Exception:
        try:
            p = sh.get_Parameter(BuiltInParameter.SHEET_NUMBER)
            if p is not None:
                num = p.AsString() or ""
        except Exception:
            pass

    # Sheet name
    name = ""
    try:
        name = sh.Name or ""
    except Exception:
        try:
            p = sh.get_Parameter(BuiltInParameter.SHEET_NAME)
            if p is not None:
                name = p.AsString() or ""
        except Exception:
            pass

    # Current revision
    rev = ""
    try:
        p = sh.get_Parameter(BuiltInParameter.SHEET_CURRENT_REVISION)
        if p is not None:
            rev = p.AsString() or ""
    except Exception:
        pass

    # Issue date / issued flag
    issued = ""
    try:
        p = sh.get_Parameter(BuiltInParameter.SHEET_ISSUE_DATE)
        if p is not None:
            d = p.AsString() or ""
            if d:
                issued = "Issued: " + d
    except Exception:
        pass
    if not issued:
        try:
            p = sh.get_Parameter(BuiltInParameter.SHEET_ISSUED)
            if p is not None and p.AsInteger() == 1:
                issued = "Issued"
        except Exception:
            pass

    entry = (num + " - " + name) if num else name
    if rev:
        entry += " | Rev: " + rev
    if issued:
        entry += " | " + issued
    return num, entry


def execute(params, doc, uidoc, **_kwargs):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, View, ViewSheet, ViewType
    )

    if not doc:
        return "No document open."

    type_str = (params.get("type") or "all").strip().lower().replace(" ", "")
    search   = (params.get("search") or "").strip().lower()

    raw_limit = params.get("limit")
    limit = min(int(raw_limit) if raw_limit is not None else 50, _MAX_LIMIT)

    # ── Sheets branch ─────────────────────────────────────────────────────────
    if type_str == "sheets":
        try:
            sheets = list(
                FilteredElementCollector(doc)
                .OfClass(ViewSheet)
                .ToElements()
            )
        except Exception as e:
            return "Failed to collect sheets: " + str(e)

        if not sheets:
            return "No sheets found in the model."

        entries = []
        for sh in sheets:
            try:
                num, entry = _sheet_entry(sh)
                if search and search not in entry.lower():
                    continue
                entries.append((num, entry))
            except Exception:
                pass

        if not entries:
            return "No sheets found" + (" matching '" + search + "'" if search else "") + "."

        entries.sort(key=lambda x: x[0])
        total = len(entries)
        lines = [e[1] for e in entries[:limit]]

        header = "{0} sheet(s){1}{2}:".format(
            total,
            " matching '" + search + "'" if search else "",
            " (showing first {0})".format(limit) if total > limit else "",
        )
        return header + "\n" + "\n".join(lines)

    # ── Views branch ──────────────────────────────────────────────────────────
    VT_MAP = {
        "floorplan":   "FloorPlan",
        "ceilingplan": "CeilingPlan",
        "elevation":   "Elevation",
        "section":     "Section",
        "threed":      "ThreeD",
        "3d":          "ThreeD",
        "drafting":    "DraftingView",
    }

    try:
        all_views = [
            v for v in FilteredElementCollector(doc).OfClass(View).ToElements()
            if not v.IsTemplate
        ]
    except Exception as e:
        return "Failed to collect views: " + str(e)

    # Type filter
    if type_str != "all":
        vt_name = VT_MAP.get(type_str)
        if vt_name is None:
            valid = "all, sheets, " + ", ".join(sorted(VT_MAP.keys()))
            return "Unknown view type '" + type_str + "'. Valid types: " + valid + "."
        target_vt = getattr(ViewType, vt_name, None)
        if target_vt is not None:
            all_views = [v for v in all_views if v.ViewType == target_vt]

    # Search filter
    if search:
        all_views = [v for v in all_views if search in v.Name.lower()]

    if not all_views:
        msg = "No views found"
        if type_str != "all":
            msg += " of type '" + type_str + "'"
        if search:
            msg += " matching '" + search + "'"
        return msg + "."

    # Fix LV2: newline-separated output — readable at scale.
    names = sorted(v.Name for v in all_views)
    total = len(names)
    shown = names[:limit]

    header = "{0} view(s){1}{2}{3}:".format(
        total,
        " of type '" + type_str + "'" if type_str != "all" else "",
        " matching '" + search + "'" if search else "",
        " (showing first {0})".format(limit) if total > limit else "",
    )
    return header + "\n" + "\n".join(shown)
