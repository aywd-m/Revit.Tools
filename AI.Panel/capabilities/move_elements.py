# -*- coding: utf-8 -*-
# capabilities/move_elements.py
# Kidzink Koda capability — Move Elements
# Moves currently selected elements either to a named level (vertical shift)
# or by a free XYZ offset (in mm).  No UI picking — all parameters from JSON.
# (c) Archie C. Manza 2026

ACTION_NAME = "move_elements"

DESCRIPTION = (
    "Move the currently selected elements. Two modes: "
    "'level' shifts elements vertically so their base aligns with a named level; "
    "'offset' moves elements by a free XYZ vector (values in mm). "
    "Pinned elements are reported but not moved."
)

PARAMS = {
    "mode":         "string — 'level' or 'offset' (default 'offset')",
    "target_level": "string — level name, required when mode='level' (e.g. 'Level 2')",
    "offset_x":     "number — X offset in mm (default 0), used when mode='offset'",
    "offset_y":     "number — Y offset in mm (default 0), used when mode='offset'",
    "offset_z":     "number — Z offset in mm (default 0), used when mode='offset'",
}

EXAMPLE = {
    "action": "move_elements",
    "params": {
        "mode":         "level",
        "target_level": "Level 2",
    },
}

_MM_TO_FT = 1.0 / 304.8


def _eid_val(eid):
    try:
        return eid.Value          # Revit 2026+
    except AttributeError:
        try:
            return eid.IntegerValue   # Revit 2025
        except AttributeError:
            return -1


def execute(params, doc, uidoc, **_kwargs):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, Level,
        Transaction, XYZ, LocationPoint, LocationCurve,
        ElementTransformUtils
    )

    if not doc or not uidoc:
        return "No document open."

    # ── Selection ──────────────────────────────────────────────────────────
    try:
        sel_ids = list(uidoc.Selection.GetElementIds())
    except Exception as e:
        return "Cannot read selection: " + str(e)
    if not sel_ids:
        return "No elements selected. Select elements in Revit first, then ask again."

    mode = (params.get("mode", "offset") or "offset").strip().lower()

    # ── Level mode ─────────────────────────────────────────────────────────
    if mode == "level":
        level_name = (params.get("target_level", "") or "").strip()
        if not level_name:
            return "Missing required parameter: target_level."

        target_level = None
        try:
            levels = (FilteredElementCollector(doc)
                      .OfClass(Level)
                      .WhereElementIsNotElementType()
                      .ToElements())
            for lv in levels:
                if lv.Name == level_name:
                    target_level = lv
                    break
            if target_level is None:
                for lv in levels:
                    if lv.Name.lower() == level_name.lower():
                        target_level = lv
                        break
            if target_level is None:
                for lv in levels:
                    if level_name.lower() in lv.Name.lower():
                        target_level = lv
                        break
        except Exception as le:
            return "Failed to find level: " + str(le)

        if target_level is None:
            try:
                avail = ", ".join(
                    lv.Name for lv in sorted(
                        FilteredElementCollector(doc)
                        .OfClass(Level)
                        .WhereElementIsNotElementType()
                        .ToElements(),
                        key=lambda l: l.Elevation
                    )
                )
            except Exception:
                avail = "unknown"
            return "Level '" + level_name + "' not found. Available levels: " + avail + "."

        target_elev = target_level.Elevation

        tx = Transaction(doc, "Koda: Move Elements to Level")
        tx.Start()
        moved   = 0
        pinned  = []
        skipped = []
        errors  = []
        try:
            for eid in sel_ids:
                try:
                    el = doc.GetElement(eid)
                    if el is None:
                        skipped.append(str(_eid_val(eid)))
                        continue
                    if el.Pinned:
                        pinned.append(str(_eid_val(eid)))
                        continue
                    loc = el.Location
                    if loc is None:
                        skipped.append(str(_eid_val(eid)))
                        continue
                    if isinstance(loc, LocationPoint):
                        cur_z = loc.Point.Z
                    elif isinstance(loc, LocationCurve):
                        cur_z = loc.Curve.GetEndPoint(0).Z
                    else:
                        skipped.append(str(_eid_val(eid)))
                        continue
                    dz = target_elev - cur_z
                    if abs(dz) < 1e-6:
                        skipped.append(str(_eid_val(eid)) + "(already on level)")
                        continue
                    ElementTransformUtils.MoveElement(doc, eid, XYZ(0.0, 0.0, dz))
                    moved += 1
                except Exception as ee:
                    errors.append(str(_eid_val(eid)) + ": " + str(ee))
            tx.Commit()
        except Exception as te:
            try:
                tx.RollBack()
            except Exception:
                pass
            return "Transaction failed: " + str(te)

        msg = (str(moved) + " element(s) moved to '" + target_level.Name + "'.")
        if pinned:
            msg += " Pinned (skipped): " + ", ".join(pinned[:10]) + "."
        if skipped:
            msg += " Skipped (no location or already on level): " + str(len(skipped)) + "."
        if errors:
            msg += " Errors: " + "; ".join(errors[:5]) + "."
        return msg

    # ── Offset mode ────────────────────────────────────────────────────────
    try:
        dx = float(params.get("offset_x", 0) or 0) * _MM_TO_FT
        dy = float(params.get("offset_y", 0) or 0) * _MM_TO_FT
        dz = float(params.get("offset_z", 0) or 0) * _MM_TO_FT
    except (TypeError, ValueError) as ve:
        return "Invalid offset values: " + str(ve)

    if abs(dx) < 1e-9 and abs(dy) < 1e-9 and abs(dz) < 1e-9:
        return "All offsets are zero — nothing to move."

    tx = Transaction(doc, "Koda: Move Elements by Offset")
    tx.Start()
    moved   = 0
    pinned  = []
    errors  = []
    vec = XYZ(dx, dy, dz)
    try:
        for eid in sel_ids:
            try:
                el = doc.GetElement(eid)
                if el is None:
                    continue
                if el.Pinned:
                    pinned.append(str(_eid_val(eid)))
                    continue
                ElementTransformUtils.MoveElement(doc, eid, vec)
                moved += 1
            except Exception as ee:
                errors.append(str(_eid_val(eid)) + ": " + str(ee))
        tx.Commit()
    except Exception as te:
        try:
            tx.RollBack()
        except Exception:
            pass
        return "Transaction failed: " + str(te)

    ox = params.get("offset_x", 0) or 0
    oy = params.get("offset_y", 0) or 0
    oz = params.get("offset_z", 0) or 0
    msg = (
        str(moved) + " element(s) moved by "
        "X=" + str(ox) + " mm, Y=" + str(oy) + " mm, Z=" + str(oz) + " mm."
    )
    if pinned:
        msg += " Pinned (skipped): " + ", ".join(pinned[:10]) + "."
    if errors:
        msg += " Errors: " + "; ".join(errors[:5]) + "."
    return msg
