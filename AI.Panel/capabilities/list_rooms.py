# -*- coding: utf-8 -*-
# capabilities/list_rooms.py
# Plugin: list placed rooms with BIP-accurate property reads.
# For a generic element listing use list_elements with category='rooms'.
# This specialist version filters unplaced/unenclosed rooms and reads
# room-specific BIPs (Number, Name, Area, Phase) more reliably.

ACTION_NAME  = "list_rooms"
DESCRIPTION  = (
    "List all placed rooms in the model with number, name, area, level, and phase. "
    "Unplaced and unenclosed rooms (area = 0) are automatically excluded. "
    "Optionally filter by level name (partial match supported). "
    "Use 'limit' to cap rows (default 50, max 200). "
    "For a quick count use list_elements with category='rooms' and count_only=true."
)
PARAMS = {
    "level": "string  — optional level name filter (partial match, e.g. 'Level 1'). Omit for all levels.",
    "limit": "integer — max rows to return (default 50, max 200).",
}
EXAMPLE = {
    "action": "list_rooms",
    "params": {"level": "Level 1"},
}

_MAX_LIMIT = 200


def execute(params, doc, uidoc, eid_int, **_kwargs):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, BuiltInCategory, BuiltInParameter
    )

    if not doc:
        return "No document open."

    level_filter = (params.get("level") or "").strip().lower()

    # Fix LR2: user-controllable limit param.
    raw_limit = params.get("limit")
    limit = min(int(raw_limit) if raw_limit is not None else 50, _MAX_LIMIT)

    try:
        rooms = list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_Rooms)
            .WhereElementIsNotElementType()
            .ToElements()
        )
    except Exception as e:
        return "Failed to collect rooms: " + str(e)

    if not rooms:
        return "No rooms found in the model."

    # ── Filter out unplaced / unenclosed rooms ────────────────────────────────
    # Fix LR3: on exception, skip the room (do not silently include it).
    placed = []
    for r in rooms:
        try:
            if r.Location is None:
                continue
            area_p = r.get_Parameter(BuiltInParameter.ROOM_AREA)
            if area_p is not None and area_p.AsDouble() <= 0:
                continue
            placed.append(r)
        except Exception:
            pass  # skip rooms that throw — do not include unknowns

    if not placed:
        return "No placed rooms found (rooms may be unplaced or not enclosed)."

    # ── Build entries ─────────────────────────────────────────────────────────
    entries = []
    for r in placed:
        # Number
        num = ""
        try:
            p = r.get_Parameter(BuiltInParameter.ROOM_NUMBER)
            if p is not None:
                num = p.AsString() or ""
        except Exception:
            pass

        # Name
        name = ""
        try:
            p = r.get_Parameter(BuiltInParameter.ROOM_NAME)
            if p is not None:
                name = p.AsString() or ""
        except Exception:
            pass

        # Level
        lv_name = ""
        try:
            p = r.get_Parameter(BuiltInParameter.ROOM_LEVEL_ID)
            if p is not None:
                lv_id = p.AsElementId()
                if lv_id is not None and eid_int(lv_id) > 0:
                    lv_el = doc.GetElement(lv_id)
                    if lv_el is not None:
                        lv_name = lv_el.Name
        except Exception:
            pass

        # Fix LR1: partial match for level filter (consistent with other capabilities).
        if level_filter and level_filter not in lv_name.lower():
            continue

        # Area
        area = ""
        try:
            p = r.get_Parameter(BuiltInParameter.ROOM_AREA)
            if p is not None:
                area = p.AsValueString() or ""
        except Exception:
            pass

        # Phase
        phase = ""
        try:
            p = r.get_Parameter(BuiltInParameter.ROOM_PHASE)
            if p is not None:
                vs = p.AsValueString()
                if vs:
                    phase = vs
                else:
                    ph_id = p.AsElementId()
                    if ph_id is not None and eid_int(ph_id) > 0:
                        ph_el = doc.GetElement(ph_id)
                        if ph_el is not None:
                            phase = ph_el.Name
        except Exception:
            pass

        label = (num + " - " + name) if num else name
        if lv_name:
            label += " | Level: " + lv_name
        if area:
            label += " | Area: " + area
        if phase:
            label += " | Phase: " + phase
        entries.append((num or "\xff", label))   # \xff sorts unnumbered rooms last

    if not entries:
        if level_filter:
            return "No rooms found on level matching '" + (params.get("level") or "") + "'."
        return "No placed rooms found."

    entries.sort(key=lambda x: x[0])
    total = len(entries)
    shown = entries[:limit]
    lines = [e[1] for e in shown]

    level_note = (" on '" + (params.get("level") or "") + "'"
                  if level_filter else "")
    header = "{0} placed room(s){1}{2}:".format(
        total,
        level_note,
        " (showing first {0})".format(limit) if total > limit else "",
    )
    return header + "\n" + "\n".join(lines)
