# -*- coding: utf-8 -*-
# Kidzink Koda — AI Chat capability plugin
# capabilities/place_view_on_sheet.py
# (c) Archie C. Manza 2026
#
# Loads automatically via _load_plugins() in Chat/script.py.
# Exposes: ACTION_NAME, DESCRIPTION, EXAMPLE, EXAMPLE_2, EXAMPLE_3, execute()

import os
import sys
import imp

# ── Plugin identity ────────────────────────────────────────────────────────────

ACTION_NAME = "place_view_on_sheet"

DESCRIPTION = (
    "Place an existing Revit view onto a sheet. "
    "Can create a new sheet automatically, or place onto an existing sheet by id or name. "
    "Supports selecting the titleblock by id or name. "
    "Returns sheet number, sheet name, viewport id, and whether the sheet was newly created. "
    "When the view matches multiple results, returns a disambiguation list so the user can "
    "retry with view_id. "
    "Params: view_name (str, required unless view_id given), "
    "view_id (int, optional, overrides view_name), "
    "target_sheet_id (int, optional), "
    "target_sheet_name (str, optional), "
    "titleblock_id (int, optional), "
    "titleblock_name (str, optional), "
    "exact_match (bool, default false)."
)

EXAMPLE = {
    "action": "place_view_on_sheet",
    "params": {"view_name": "Level 1"},
}

EXAMPLE_2 = {
    "action": "place_view_on_sheet",
    "params": {
        "view_name": "Ground Floor Plan",
        "target_sheet_name": "A100",
        "exact_match": True,
    },
}

EXAMPLE_3 = {
    "action": "place_view_on_sheet",
    "params": {
        "view_id": 123456,
        "titleblock_name": "A1 Landscape",
    },
}

# ── Lazy-load the implementation module from the same folder ───────────────────

_impl = None  # will hold the sheet_placement_tool module once loaded

def _get_impl():
    global _impl
    if _impl is not None:
        return _impl
    try:
        # __commandpath__ is the Chat.pushbutton folder; capabilities/ is a
        # subfolder, so the implementation lives in the same capabilities/ dir.
        here = __commandpath__
    except Exception:
        try:
            here = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            here = ""
    impl_path = os.path.join(here, "sheet_placement_tool.py")
    if not os.path.isfile(impl_path):
        raise ImportError("sheet_placement_tool.py not found at: " + impl_path)
    _impl = imp.load_source("sheet_placement_tool", impl_path)
    return _impl

# ── Minimal logger that emits to pyRevit output (print) ───────────────────────

class _Logger(object):
    def _fmt(self, level, msg):
        return "[place_view_on_sheet][" + level + "] " + str(msg)
    def info(self, msg, **_kw):
        print(self._fmt("INFO", msg))
    def warning(self, msg, **_kw):
        print(self._fmt("WARN", msg))
    def error(self, msg, **_kw):
        print(self._fmt("ERROR", msg))
    def debug(self, msg, **_kw):
        pass  # suppress debug spam in production; set to print() for troubleshooting

_logger = _Logger()

# ── execute() ─────────────────────────────────────────────────────────────────

def execute(params, doc=None, uidoc=None,
            resolve_category=None, get_field_bip=None, eid_int=None):
    """
    Entry point called by dispatch_action() in Chat/script.py.

    params keys
    -----------
    view_name        : str   - view to place (fuzzy match unless exact_match=True)
    view_id          : int   - element id of view (overrides view_name)
    target_sheet_id  : int   - place onto this existing sheet (by element id)
    target_sheet_name: str   - place onto this existing sheet (by name or number)
    titleblock_id    : int   - titleblock to use for new sheet (by element id)
    titleblock_name  : str   - titleblock to use for new sheet (by name)
    exact_match      : bool  - require exact name matches (default False)

    Returns a plain-string summary suitable for the chat reply.
    """
    if not doc:
        return "Error: no active Revit document."

    view_name         = params.get("view_name", "")
    view_id           = params.get("view_id", None)
    target_sheet_id   = params.get("target_sheet_id", None)
    target_sheet_name = params.get("target_sheet_name", None)
    titleblock_id     = params.get("titleblock_id", None)
    titleblock_name   = params.get("titleblock_name", None)
    exact_match       = bool(params.get("exact_match", False))

    if not view_name and not view_id:
        return (
            "Error: provide either view_name or view_id. "
            "To find the view id, ask me to list views."
        )

    try:
        impl = _get_impl()
    except Exception as e:
        return "Error loading sheet_placement_tool: " + str(e)

    try:
        result = impl.place_view_on_new_sheet(
            doc,
            view_name         = view_name or "",
            logger            = _logger,
            exact_match       = exact_match,
            view_id           = view_id,
            target_sheet_id   = target_sheet_id,
            target_sheet_name = target_sheet_name,
            titleblock_id     = titleblock_id,
            titleblock_name   = titleblock_name,
        )
    except Exception as e:
        return "Action failed: " + str(e)

    return _format_result(result, params)


def _format_result(result, params):
    """Convert the result dict from sheet_placement_tool into a readable chat reply."""
    if not isinstance(result, dict):
        return str(result)

    status = result.get("status", "")

    # ── Success ────────────────────────────────────────────────────────────────
    if status == "success":
        view_type    = result.get("view_type", "View")
        view_name    = result.get("view_name", "")
        sheet_num    = result.get("sheet_number", "")
        sheet_name   = result.get("sheet_name", "")
        sheet_id     = result.get("sheet_id", "")
        vp_id        = result.get("viewport_id", "")
        was_created  = result.get("sheet_was_created", False)
        tb           = result.get("titleblock_used", {})

        if was_created:
            tb_label = tb.get("label") or tb.get("type_name") or tb.get("family_name") or ""
            reply = (
                "Placed '{view}' ({vtype}) on new sheet {num} — {sname} "
                "(sheet id {sid}, viewport id {vpid})."
            ).format(
                view=view_name, vtype=view_type,
                num=sheet_num, sname=sheet_name,
                sid=sheet_id, vpid=vp_id,
            )
            if tb_label:
                reply += " Titleblock used: {}.".format(tb_label)
        else:
            reply = (
                "Placed '{view}' ({vtype}) on existing sheet {num} — {sname} "
                "(sheet id {sid}, viewport id {vpid})."
            ).format(
                view=view_name, vtype=view_type,
                num=sheet_num, sname=sheet_name,
                sid=sheet_id, vpid=vp_id,
            )
        return reply

    # ── Multiple view matches ──────────────────────────────────────────────────
    if status == "multiple_matches":
        msg   = result.get("message", "Multiple matches found.")
        views = result.get("matching_views", [])
        sheets = result.get("matching_sheets", [])
        tbs    = result.get("matching_titleblocks", [])

        lines = [msg]
        if views:
            lines.append("Matching views:")
            for v in views:
                lines.append("  id={id}  [{type}]  \"{name}\"".format(**v))
            lines.append("Retry with view_id to disambiguate.")
        elif sheets:
            lines.append("Matching sheets:")
            for s in sheets:
                lines.append("  id={id}  {number}  \"{name}\"".format(**s))
            lines.append("Retry with target_sheet_id to disambiguate.")
        elif tbs:
            lines.append("Matching titleblocks:")
            for t in tbs:
                lines.append("  id={id}  {label}".format(**t))
            lines.append("Retry with titleblock_id to disambiguate.")
        return "\n".join(lines)

    # ── Error ──────────────────────────────────────────────────────────────────
    msg = result.get("message", "Unknown error.")

    # Enrich common error cases with hints
    if "already placed" in msg or "already_on_sheet" in msg:
        already = result.get("already_on_sheet") or {}
        if already:
            msg += (
                " The view is currently on sheet {number} — {name} (id {id}).".format(**already)
                + " Use target_sheet_id to move it, or choose a different view."
            )
        else:
            msg += " To add this view to another sheet, use a duplicate or dependent view."

    elif "No views found" in msg:
        msg += " Try listing views first: 'list all views'."

    elif "No sheets found" in msg:
        msg += " Try listing sheets: 'list all sheets'."

    elif "No titleblock" in msg:
        msg += " Try listing titleblocks: list_family_types with category 'Title Blocks'."

    return "Error: " + msg
