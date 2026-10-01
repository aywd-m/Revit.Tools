# -*- coding: utf-8 -*-
# capabilities/create_room_elements.py
# Kidzink Koda capability — Create Walls / Floors / Ceilings from Rooms
# Builds walls and/or a ceiling around each room's boundary, and/or a floor
# filling each room's boundary, using the room's own boundary loops.
# For a single hand-placed wall between two coordinates, use create_wall instead.
# (c) Archie C. Manza 2026

ACTION_NAME = "create_room_elements"

# Edit these to match your firm's standard element types. Used whenever the
# user does not name a specific type for that element kind.
DEFAULT_WALL_TYPE    = "Generic - 200mm"
DEFAULT_FLOOR_TYPE   = "Generic - 300mm"
DEFAULT_CEILING_TYPE = "Compound Ceiling"

DESCRIPTION = (
    "Create building elements automatically from EVERY placed room's boundary in the model "
    "(or a filtered subset of rooms) — walls around the room perimeter, a ceiling over the "
    "room, and/or a floor filling the room. This is the ONLY action for requests like "
    "'create walls based on rooms', 'create walls and ceilings for every room', "
    "'create a floor based on rooms in the model', or 'build ceilings for all rooms with "
    "height 2700'. "
    "Required param: 'elements' — a list containing any of 'wall', 'floor', 'ceiling' "
    "(e.g. ['wall','ceiling'] or ['floor']). "
    "Optional params: 'height_mm' — for 'wall' this is the unconnected wall height in mm "
    "(default 3000); for 'ceiling' this is the ceiling's height above its level in mm "
    "(default 2700); ignored for 'floor'. "
    "'level' — restrict to rooms on this level name; if omitted, ALL levels' rooms are used "
    "and each room's own level is inferred automatically. "
    "'room_filter' — optional list of room Number or Name strings to restrict which rooms "
    "are processed; if omitted, every placed room (Area > 0) in scope is processed. "
    "'use_selection' — boolean, default false. Set this to true whenever the user refers to "
    "'the selected rooms', 'the current selection', 'these rooms', or similar, INSTEAD OF "
    "asking the user to clarify or re-specify which rooms — the currently selected Room "
    "elements in Revit are used directly. If 'use_selection' is true, 'level' and "
    "'room_filter' are ignored. If the current selection contains non-Room elements, this "
    "action will report that and do nothing — it will NOT silently guess; you do not need "
    "to pre-validate the selection type yourself, just set use_selection:true and let the "
    "action report back. Never ask 'are the selected elements rooms?' — set use_selection "
    "and proceed. "
    "'wall_type', 'floor_type', 'ceiling_type' — optional partial-name type overrides; if "
    "omitted, the project defaults ('" + DEFAULT_WALL_TYPE + "', '" + DEFAULT_FLOOR_TYPE +
    "', '" + DEFAULT_CEILING_TYPE + "') are used, falling back to the first available type "
    "of that kind. "
    "This action does NOT take start/end coordinates and does NOT support a 'category' or "
    "'filter' param — never include those. "
    "There is NO separate 'create_walls', 'create_floor', 'create_ceiling', or "
    "'create_room_walls' action — ALL room-based generation of walls, floors, and ceilings "
    "happens through THIS single action by naming the desired kinds in 'elements'. "
    "If the user asks for a single hand-placed wall between two explicit coordinates instead, "
    "use the SEPARATE 'create_wall' action, not this one. Never combine create_room_elements "
    "and create_wall into a single action block."
)

PARAMS = {
    "elements":      "list of strings — any of 'wall', 'floor', 'ceiling' (required)",
    "height_mm":     "number — wall unconnected height (default 3000) or ceiling height "
                     "above level (default 2700). Ignored for floor.",
    "level":         "string — optional level name to restrict which rooms are processed. "
                     "Ignored if use_selection is true.",
    "room_filter":   "list of strings — optional room Number or Name values to restrict "
                     "scope. Ignored if use_selection is true.",
    "use_selection": "boolean — if true, use the currently selected Room elements in Revit "
                     "instead of level/room_filter. Set this whenever the user refers to "
                     "'selected rooms' or 'the selection'.",
    "wall_type":     "string — optional wall type name (partial match)",
    "floor_type":    "string — optional floor type name (partial match)",
    "ceiling_type":  "string — optional ceiling type name (partial match)",
}

EXAMPLE = {
    "action": "create_room_elements",
    "params": {
        "elements":  ["wall", "ceiling"],
        "height_mm": 2700,
        "level":     "Level 1",
    },
}

# Minimal / short-form case — "create a floor based on the rooms in the model"
EXAMPLE_2 = {
    "action": "create_room_elements",
    "params": {
        "elements": ["floor"],
    },
}

# "generate a ceiling for the selected rooms with 3m high" — no level or
# room_filter needed; use_selection reads directly from the Revit selection.
EXAMPLE_3 = {
    "action": "create_room_elements",
    "params": {
        "elements":  ["ceiling"],
        "height_mm": 3000,
        "use_selection": True,
    },
}

# Revit internal unit is decimal feet. 1 mm = 1/304.8 ft.
_MM_TO_FT = 1.0 / 304.8


# ── Type lookup helpers ─────────────────────────────────────────────────────

def _find_type(doc, of_class, wanted_name, default_name):
    from Autodesk.Revit.DB import FilteredElementCollector
    types = list(FilteredElementCollector(doc).OfClass(of_class).ToElements())
    if not types:
        return None

    wanted = (wanted_name or "").strip().lower()
    if wanted:
        for t in types:
            if t.Name.lower() == wanted:
                return t
        for t in types:
            if wanted in t.Name.lower():
                return t

    default_lower = default_name.lower()
    for t in types:
        if t.Name.lower() == default_lower:
            return t
    for t in types:
        if default_lower in t.Name.lower():
            return t

    return types[0]


def _find_level(doc, level_name):
    from Autodesk.Revit.DB import FilteredElementCollector, Level
    levels = (FilteredElementCollector(doc)
              .OfClass(Level)
              .WhereElementIsNotElementType()
              .ToElements())
    if not level_name:
        return None
    for lv in levels:
        if lv.Name == level_name:
            return lv
    for lv in levels:
        if lv.Name.lower() == level_name.lower():
            return lv
    for lv in levels:
        if level_name.lower() in lv.Name.lower():
            return lv
    return None


# ── Room collection ──────────────────────────────────────────────────────────

def _collect_selected_rooms(doc, uidoc):
    """Return (rooms, error_message). error_message is None on success.
    If the current selection contains non-Room elements, refuses and
    reports rather than silently ignoring them."""
    try:
        sel_ids = list(uidoc.Selection.GetElementIds())
    except Exception:
        return None, "Could not read the current Revit selection."

    if not sel_ids:
        return None, "Nothing is currently selected. Select room(s) first, then ask again."

    rooms, non_rooms = [], []
    for eid in sel_ids:
        try:
            el = doc.GetElement(eid)
        except Exception:
            el = None
        if el is None:
            continue
        # Check by category name (safer than isinstance in IronPython 2.7)
        is_room = False
        try:
            cat = el.Category
            if cat and cat.Name == "Rooms":
                is_room = True
        except Exception:
            pass
        
        if is_room:
            try:
                if el.Area > 0:
                    rooms.append(el)
            except Exception:
                pass
        else:
            try:
                non_rooms.append(el.Category.Name if el.Category else "Unknown")
            except Exception:
                non_rooms.append("Unknown")

    if not rooms:
        kinds = ", ".join(sorted(set(non_rooms))) if non_rooms else "unknown elements"
        return None, (
            "The current selection doesn't contain any rooms (it has: " + kinds + "). "
            "Select the room(s) you want and ask again."
        )
    if non_rooms:
        kinds = ", ".join(sorted(set(non_rooms)))
        # Proceed with just the rooms, but flag the mismatch in the summary later.
        return rooms, "PARTIAL:" + kinds

    return rooms, None


def _collect_rooms(doc, level, room_filter):
    from Autodesk.Revit.DB.Architecture import Room
    from Autodesk.Revit.DB import FilteredElementCollector

    try:
        all_rooms = list(FilteredElementCollector(doc).OfClass(Room).ToElements())
    except Exception:
        return []
    
    rooms = []
    for r in all_rooms:
        try:
            if r.Area <= 0:
                continue  # unplaced room
        except Exception:
            continue
        if level is not None:
            try:
                if r.LevelId != level.Id:
                    continue
            except Exception:
                continue
        if room_filter:
            try:
                num  = r.Number if r.Number else ""
                name = r.Name if r.Name else ""
            except Exception:
                num, name = "", ""
            match = False
            for f in room_filter:
                fl = str(f).strip().lower()
                if fl and (fl == str(num).lower() or fl == str(name).lower()
                           or fl in str(name).lower()):
                    match = True
                    break
            if not match:
                continue
        rooms.append(r)
    return rooms


def _room_boundary_curves(room):
    """Return the outer boundary loop of a room as a list of Curve objects."""
    from Autodesk.Revit.DB import SpatialElementBoundaryOptions
    opts = SpatialElementBoundaryOptions()
    loops = room.GetBoundarySegments(opts)
    if not loops:
        return None
    # First loop returned is the outer (largest) loop for a simple room.
    outer = loops[0]
    curves = []
    for seg in outer:
        try:
            curves.append(seg.GetCurve())
        except Exception:
            pass
    return curves if curves else None


def _curve_loop_from_curves(curves):
    from Autodesk.Revit.DB import CurveLoop
    loop = CurveLoop()
    for c in curves:
        loop.Append(c)
    return loop


# ── Element builders (each returns True/False for one room) ─────────────────

def _build_walls(doc, room, level, wall_type, height_ft, made, errors):
    from Autodesk.Revit.DB import Wall
    curves = _room_boundary_curves(room)
    if not curves:
        errors.append("Room '{0}': could not read boundary curves".format(_room_label(room)))
        return False
    ok_any = False
    for c in curves:
        try:
            Wall.Create(doc, c, wall_type.Id, level.Id, height_ft, 0.0, False, False)
            ok_any = True
        except Exception as we:
            errors.append("Room '{0}' wall segment: {1}".format(_room_label(room), str(we)))
    if ok_any:
        made["wall"] += 1
    return ok_any


def _build_floor(doc, room, level, floor_type, made, errors):
    from Autodesk.Revit.DB import Floor, CurveLoop
    from System.Collections.Generic import List
    curves = _room_boundary_curves(room)
    if not curves:
        errors.append("Room '{0}': could not read boundary curves".format(_room_label(room)))
        return False
    try:
        loop = _curve_loop_from_curves(curves)
        loop_list = List[CurveLoop]()
        loop_list.Add(loop)
        Floor.Create(doc, loop_list, floor_type.Id, level.Id)
        made["floor"] += 1
        return True
    except Exception as fe:
        errors.append("Room '{0}' floor: {1}".format(_room_label(room), str(fe)))
        return False


def _build_ceiling(doc, room, level, ceiling_type, height_ft, made, errors):
    """Build one ceiling from room boundary. Appends error string to errors[] on failure."""
    from Autodesk.Revit.DB import CurveLoop
    from System.Collections.Generic import List

    curves = _room_boundary_curves(room)
    if not curves:
        errors.append("Room '{0}': could not read boundary curves".format(
            _room_label(room)))
        return False

    try:
        loop = _curve_loop_from_curves(curves)
        loop_list = List[CurveLoop]()
        loop_list.Add(loop)
    except Exception as le:
        errors.append("Room '{0}': curve loop error — {1}".format(
            _room_label(room), str(le)))
        return False

    # Try Ceiling.Create (Revit 2022+)
    ceiling = None
    create_err = None
    try:
        from Autodesk.Revit.DB import Ceiling
        ceiling = Ceiling.Create(doc, loop_list, ceiling_type.Id, level.Id)
    except Exception as ce:
        create_err = str(ce)

    # Fallback: FilledRegion or direct element creation is not available for ceilings.
    # If Ceiling.Create is missing (pre-2022), report clearly rather than silently failing.
    if ceiling is None:
        errors.append(
            "Room '{0}': Ceiling.Create failed — {1}. "
            "Confirm Revit version is 2022 or newer and the ceiling type '{2}' is valid.".format(
                _room_label(room), create_err or "unknown error", ceiling_type.Name))
        return False

    # Set height above level
    try:
        from Autodesk.Revit.DB import BuiltInParameter
        p = ceiling.get_Parameter(BuiltInParameter.CEILING_HEIGHTABOVELEVEL_PARAM)
        if p is not None and not p.IsReadOnly:
            p.Set(height_ft)
    except Exception:
        pass  # Height is a nice-to-have; don't fail the whole ceiling over it

    made["ceiling"] += 1
    return True


def _room_label(room):
    try:
        return str(room.Number) + " " + str(room.Name)
    except Exception:
        return "?"


# ── Entry point ───────────────────────────────────────────────────────────

def execute(params, doc, uidoc, **_kwargs):
    from Autodesk.Revit.DB import Transaction, WallType, FloorType, CeilingType

    if not doc:
        return "No document open."

    try:
        elements = params.get("elements", [])
        if isinstance(elements, str):
            elements = [elements]
        elements = [str(e).strip().lower() for e in (elements or [])]
        elements = [e for e in elements if e in ("wall", "floor", "ceiling")]
        if not elements:
            return "No valid 'elements' given. Specify one or more of: wall, floor, ceiling."

        try:
            height_mm = float(params.get("height_mm", 0) or 0)
        except (TypeError, ValueError):
            height_mm = 0.0

        wall_height_ft    = (height_mm if height_mm > 0 else 3000.0) * _MM_TO_FT
        ceiling_height_ft = (height_mm if height_mm > 0 else 2700.0) * _MM_TO_FT

        use_selection = bool(params.get("use_selection", False))
        partial_warning = None
        level = None

        if use_selection:
            rooms, err = _collect_selected_rooms(doc, uidoc)
            if err and err.startswith("PARTIAL:"):
                partial_warning = (
                    "Note: the selection also included non-room elements (" +
                    err[len("PARTIAL:"):] + ") which were skipped."
                )
            elif err:
                return err
        else:
            level = _find_level(doc, (params.get("level", "") or "").strip())
            room_filter = params.get("room_filter", None)
            rooms = _collect_rooms(doc, level, room_filter)
            if not rooms:
                scope = "level '{0}'".format(level.Name) if level is not None else "the model"
                return "No placed rooms found in " + scope + ". Add/place rooms first."
    except Exception as early_err:
        return "Setup error: " + str(early_err)

    wall_type = floor_type = ceiling_type = None
    if "wall" in elements:
        wall_type = _find_type(doc, WallType, params.get("wall_type", ""), DEFAULT_WALL_TYPE)
        if wall_type is None:
            return "No wall types found in the model."
    if "floor" in elements:
        floor_type = _find_type(doc, FloorType, params.get("floor_type", ""), DEFAULT_FLOOR_TYPE)
        if floor_type is None:
            return "No floor types found in the model."
    if "ceiling" in elements:
        ceiling_type = _find_type(doc, CeilingType, params.get("ceiling_type", ""), DEFAULT_CEILING_TYPE)
        if ceiling_type is None:
            return "No ceiling types found in the model."

    made = {"wall": 0, "floor": 0, "ceiling": 0}
    errors = []
    room_count = 0

    tx = None
    try:
        tx = Transaction(doc, "Koda: Create Room Elements")
        tx.Start()
        for room in rooms:
            room_level = level
            if room_level is None:
                try:
                    room_level = doc.GetElement(room.LevelId)
                except Exception:
                    room_level = None
            if room_level is None:
                errors.append("Room '{0}': no level found, skipped".format(_room_label(room)))
                continue

            room_count += 1
            if "wall" in elements:
                _build_walls(doc, room, room_level, wall_type, wall_height_ft, made, errors)
            if "floor" in elements:
                _build_floor(doc, room, room_level, floor_type, made, errors)
            if "ceiling" in elements:
                _build_ceiling(doc, room, room_level, ceiling_type, ceiling_height_ft, made, errors)

        if tx and tx.HasStarted():
            tx.Commit()
    except Exception as e:
        if tx:
            try:
                if tx.HasStarted():
                    tx.RollBack()
            except Exception:
                pass
        return "Failed to create room elements: " + str(e)

    parts = []
    if "wall" in elements:
        parts.append("{0}/{1} room(s) got walls (type '{2}', height {3:.0f} mm)".format(
            made["wall"], room_count, wall_type.Name, wall_height_ft / _MM_TO_FT))
    if "floor" in elements:
        parts.append("{0}/{1} floor(s) created (type '{2}')".format(
            made["floor"], room_count, floor_type.Name))
    if "ceiling" in elements:
        parts.append("{0}/{1} ceiling(s) created (type '{2}', height {3:.0f} mm above level)".format(
            made["ceiling"], room_count, ceiling_type.Name, ceiling_height_ft / _MM_TO_FT))

    result = "Processed {0} room(s). {1}.".format(room_count, "; ".join(parts))
    if partial_warning:
        result += " " + partial_warning
    # Surface up to 3 errors so the user can see what actually failed
    if errors:
        result += " Errors ({0}): {1}".format(
            len(errors), " | ".join(errors[:3]))
        if len(errors) > 3:
            result += " ... and {0} more.".format(len(errors) - 3)
    return result
