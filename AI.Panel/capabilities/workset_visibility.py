# -*- coding: utf-8 -*-
# Kidzink Koda – Capability: workset_visibility
# Lists all worksets and their visibility state in the active view,
# and can show or hide individual worksets in that view.
#
# Revit API used:
#   WorksetTable        – iterate worksets
#   WorksetVisibility   – Visible / Hidden / UseGlobalSetting
#   WorksetDefaultVisibilitySettings – per-view workset VG override
#   doc.GetWorksetTable()
#   uidoc.ActiveView.SetWorksetVisibility()   (View method, not WorksetTable)
#   Workset.IsOpen, .IsEditable, .Name, .Id

ACTION_NAME = "workset_visibility"

DESCRIPTION = (
    "Lists all user worksets in the model with their current visibility state "
    "(Visible / Hidden / UseGlobalSetting) in the active view, "
    "OR sets a specific workset to Visible or Hidden in the active view, "
    "OR turns ALL worksets on or off at once in the active view. "
    "Params: "
    "  'mode' (required) — 'list' to show all worksets; "
    "'set' to change one workset; 'set_all' to change every workset at once. "
    "  'workset_name' (required for mode='set') — exact or partial name of the workset to change. "
    "  'visibility' (required for mode='set' and mode='set_all') — 'visible', 'hidden', or 'default'. "
    "Do NOT use this action for element visibility — only workset-level VG visibility. "
    "Do NOT invent a workset name — always use a name from the list result or confirmed by the user. "
    "When the user says 'make workset X visible' or 'hide workset X', emit mode='set'. "
    "When the user says 'turn on all worksets', 'show all worksets', 'make all worksets visible', "
    "'enable all worksets', emit mode='set_all' with visibility='visible'. "
    "When the user says 'turn off all worksets', 'hide all worksets', 'make all worksets hidden', "
    "'disable all worksets', emit mode='set_all' with visibility='hidden'. "
    "When the user says 'list worksets', 'show worksets', 'which workset is hidden', "
    "'show me worksets', or 'what worksets exist', emit mode='list'."
)

PARAMS = {
    "mode":         "list | set | set_all",
    "workset_name": "(string, required when mode=set) partial or full name of the workset",
    "visibility":   "(string, required when mode=set or set_all) visible | hidden | default",
}

EXAMPLE = {
    "action": "workset_visibility",
    "params": {"mode": "list"}
}

EXAMPLE_2 = {
    "action": "workset_visibility",
    "params": {"mode": "set", "workset_name": "Architecture", "visibility": "visible"}
}

EXAMPLE_3 = {
    "action": "workset_visibility",
    "params": {"mode": "set", "workset_name": "Shared Levels", "visibility": "hidden"}
}

EXAMPLE_4 = {
    "action": "workset_visibility",
    "params": {"mode": "set_all", "visibility": "visible"}
}


def execute(params, doc=None, uidoc=None, **_kwargs):
    if doc is None:
        return "No document open."
    if not doc.IsWorkshared:
        return "This model is not workshared — worksets are not enabled."

    # Imports deferred to execute() so they never run at module scope
    # (IronPython 2.7 CLR constraint: no WPF/CLR types at module import time).
    try:
        from Autodesk.Revit.DB import (
            WorksetTable, WorksetKind, WorksetVisibility,
            FilteredWorksetCollector, Transaction
        )
    except Exception as _ie:
        return "Import error: " + str(_ie)

    mode = (params.get("mode") or "list").lower().strip()

    # ── LIST ─────────────────────────────────────────────────────────────────
    if mode == "list":
        try:
            active_view = uidoc.ActiveView if uidoc else None

            collector = FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
            worksets  = list(collector.ToWorksets())

            if not worksets:
                return "No user worksets found in this model."

            def _vis_label(ws):
                if active_view is None:
                    return "Unknown"
                try:
                    vis = active_view.GetWorksetVisibility(ws.Id)
                    if vis == WorksetVisibility.Visible:
                        return "Visible"
                    elif vis == WorksetVisibility.Hidden:
                        return "Hidden"
                    else:
                        return "Default"
                except Exception:
                    return "Unknown"

            lines = [
                "Worksets (" + str(len(worksets)) + ") in view '"
                + (active_view.Name if active_view else "?") + "':",
                "-" * 48,
            ]
            for ws in sorted(worksets, key=lambda w: w.Name):
                vis     = _vis_label(ws)
                open_s  = "Open" if ws.IsOpen else "Closed"
                lines.append(
                    ws.Name
                    + " | " + vis
                    + " | " + open_s
                )
            lines.append("-" * 48)
            lines.append(
                "To change visibility say: "
                "'make workset [name] visible' or 'hide workset [name]'"
            )
            return "\n".join(lines)

        except Exception as ex:
            return "List worksets failed: " + str(ex)

    # ── SET ──────────────────────────────────────────────────────────────────
    elif mode == "set":
        ws_name_target = (params.get("workset_name") or "").strip()
        vis_target     = (params.get("visibility") or "").lower().strip()

        if not ws_name_target:
            return "workset_name is required for mode='set'."
        if vis_target not in ("visible", "hidden", "default"):
            return (
                "visibility must be 'visible', 'hidden', or 'default'. "
                "Got: '" + vis_target + "'."
            )

        active_view = uidoc.ActiveView if uidoc else None
        if active_view is None:
            return "No active view — cannot set workset visibility."

        try:
            collector = FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
            worksets  = list(collector.ToWorksets())
        except Exception as ex:
            return "Could not collect worksets: " + str(ex)

        # Case-insensitive substring match — prefer exact match over partial
        target_lower = ws_name_target.lower()
        exact   = [w for w in worksets if w.Name.lower() == target_lower]
        partial = [w for w in worksets if target_lower in w.Name.lower()]

        matches = exact if exact else partial
        if not matches:
            avail = ", ".join(sorted(w.Name for w in worksets))
            return (
                "No workset found matching '" + ws_name_target + "'. "
                "Available: " + avail
            )
        if len(matches) > 1 and not exact:
            names = ", ".join("'" + w.Name + "'" for w in matches)
            return (
                "Ambiguous workset name '" + ws_name_target + "' — "
                "matches: " + names + ". Please be more specific."
            )

        target_ws = matches[0]

        # Map string → WorksetVisibility enum value
        if vis_target == "visible":
            vis_enum = WorksetVisibility.Visible
            vis_label = "Visible"
        elif vis_target == "hidden":
            vis_enum = WorksetVisibility.Hidden
            vis_label = "Hidden"
        else:
            vis_enum  = WorksetVisibility.UseGlobalSetting
            vis_label = "Default (global setting)"

        try:
            tx = Transaction(doc, "Chat: Set Workset Visibility")
            tx.Start()
            try:
                active_view.SetWorksetVisibility(target_ws.Id, vis_enum)
                tx.Commit()
            except Exception as ex:
                tx.RollbackToCheckpoint() if hasattr(tx, "RollbackToCheckpoint") else tx.RollBack()
                return "Failed to set workset visibility: " + str(ex)
        except Exception as ex:
            return "Transaction error: " + str(ex)

        return (
            "Workset '" + target_ws.Name + "' is now set to "
            + vis_label + " in view '" + active_view.Name + "'."
        )

    # ── SET ALL ──────────────────────────────────────────────────────────────
    elif mode == "set_all":
        vis_target = (params.get("visibility") or "").lower().strip()
        if vis_target not in ("visible", "hidden", "default"):
            return (
                "visibility must be 'visible', 'hidden', or 'default'. "
                "Got: '" + vis_target + "'."
            )

        active_view = uidoc.ActiveView if uidoc else None
        if active_view is None:
            return "No active view — cannot set workset visibility."

        if vis_target == "visible":
            vis_enum  = WorksetVisibility.Visible
            vis_label = "Visible"
        elif vis_target == "hidden":
            vis_enum  = WorksetVisibility.Hidden
            vis_label = "Hidden"
        else:
            vis_enum  = WorksetVisibility.UseGlobalSetting
            vis_label = "Default (global setting)"

        try:
            collector = FilteredWorksetCollector(doc).OfKind(WorksetKind.UserWorkset)
            worksets  = list(collector.ToWorksets())
        except Exception as ex:
            return "Could not collect worksets: " + str(ex)

        if not worksets:
            return "No user worksets found in this model."

        failed = []
        try:
            tx = Transaction(doc, "Chat: Set All Worksets " + vis_label)
            tx.Start()
            try:
                for ws in worksets:
                    try:
                        active_view.SetWorksetVisibility(ws.Id, vis_enum)
                    except Exception as ex:
                        failed.append(ws.Name + " (" + str(ex) + ")")
                tx.Commit()
            except Exception as ex:
                try:
                    tx.RollBack()
                except Exception:
                    pass
                return "Transaction failed: " + str(ex)
        except Exception as ex:
            return "Transaction error: " + str(ex)

        msg = (
            "All " + str(len(worksets)) + " worksets set to "
            + vis_label + " in view '" + active_view.Name + "'."
        )
        if failed:
            msg += " Could not set: " + ", ".join(failed)
        return msg

    else:
        return "Unknown mode '" + mode + "'. Use 'list', 'set', or 'set_all'."
