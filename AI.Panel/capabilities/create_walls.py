# -*- coding: utf-8 -*-
# capabilities/create_walls.py
# Kidzink Koda capability — Create Wall (point-to-point)
# Creates a single straight wall between two XY coordinates on a named level.
# For walls generated automatically from room boundaries, see
# capabilities/create_room_elements.py (action "create_room_elements") instead.
# (c) Archie C. Manza 2026

ACTION_NAME = "create_wall"

# Edit this to match your firm's standard wall type name. Used whenever the
# user does not specify 'wall_type'.
DEFAULT_WALL_TYPE = "Generic - 200mm"

DESCRIPTION = (
    "Create ONE straight wall between two explicit XY coordinates on a named level. "
    "Use this ONLY when the user gives specific points/coordinates for a single wall "
    "(e.g. 'wall from 0,0 to 5000,0'). "
    "Params: 'start_x', 'start_y', 'end_x', 'end_y' (mm from project origin, required), "
    "'level' (level name, required), 'height_mm' (unconnected height in mm, default 3000), "
    "'wall_type' (optional partial name match — if omitted, the default project wall type "
    "'" + DEFAULT_WALL_TYPE + "' is used, falling back to the first available wall type). "
    "There is NO separate 'create_walls' (plural) action for this — coordinate-based single "
    "walls always use this 'create_wall' action. "
    "Do NOT use this action for 'create walls based on rooms' or 'create walls around every "
    "room' requests — those use the SEPARATE action 'create_room_elements' instead, which "
    "builds walls (and optionally floors/ceilings) automatically from room boundaries and "
    "does not take start/end coordinates. Never merge create_wall and create_room_elements "
    "into a single action block."
)

PARAMS = {
    "start_x":    "number — X coordinate of wall start point in mm",
    "start_y":    "number — Y coordinate of wall start point in mm",
    "end_x":      "number — X coordinate of wall end point in mm",
    "end_y":      "number — Y coordinate of wall end point in mm",
    "level":      "string — name of the level to host the wall (e.g. 'Level 1')",
    "height_mm":  "number — unconnected wall height in mm (default 3000)",
    "wall_type":  "string — optional wall type name (partial match). Omit to use the "
                  "project default wall type.",
}

EXAMPLE = {
    "action": "create_wall",
    "params": {
        "start_x":   0,
        "start_y":   0,
        "end_x":     5000,
        "end_y":     0,
        "level":     "Level 1",
        "height_mm": 3000,
    },
}

# Minimal / short-form case — user just gives two points and a level, no
# height or type. execute() fills in the height (3000mm) and default type.
EXAMPLE_2 = {
    "action": "create_wall",
    "params": {
        "start_x": 0,
        "start_y": 0,
        "end_x":   4000,
        "end_y":   3000,
        "level":   "Level 1",
    },
}

# Revit internal unit is decimal feet. 1 mm = 1/304.8 ft.
_MM_TO_FT = 1.0 / 304.8


def _find_level(doc, level_name):
    from Autodesk.Revit.DB import FilteredElementCollector, Level
    levels = (FilteredElementCollector(doc)
              .OfClass(Level)
              .WhereElementIsNotElementType()
              .ToElements())
    for lv in levels:
        if lv.Name == level_name:
            return lv
    for lv in levels:
        if lv.Name.lower() == level_name.lower():
            return lv
    if level_name:
        for lv in levels:
            if level_name.lower() in lv.Name.lower():
                return lv
    if levels:
        return sorted(levels, key=lambda l: l.Elevation)[0]
    return None


def _find_wall_type(doc, wtype_name):
    from Autodesk.Revit.DB import FilteredElementCollector, WallType
    wtypes = list(FilteredElementCollector(doc).OfClass(WallType).ToElements())
    if not wtypes:
        return None

    wanted = (wtype_name or "").strip().lower()
    if wanted:
        for wt in wtypes:
            if wt.Name.lower() == wanted:
                return wt
        for wt in wtypes:
            if wanted in wt.Name.lower():
                return wt

    # Fall back to the firm default type name.
    default_lower = DEFAULT_WALL_TYPE.lower()
    for wt in wtypes:
        if wt.Name.lower() == default_lower:
            return wt
    for wt in wtypes:
        if default_lower in wt.Name.lower():
            return wt

    return wtypes[0]


def execute(params, doc, uidoc, eid_int, **_kwargs):
    from Autodesk.Revit.DB import Transaction, Line, XYZ

    if not doc:
        return "No document open."

    try:
        sx = float(params.get("start_x", 0)) * _MM_TO_FT
        sy = float(params.get("start_y", 0)) * _MM_TO_FT
        ex = float(params.get("end_x",   0)) * _MM_TO_FT
        ey = float(params.get("end_y",   0)) * _MM_TO_FT
    except (TypeError, ValueError) as ve:
        return "Invalid coordinates: " + str(ve)

    if abs(ex - sx) < 1e-6 and abs(ey - sy) < 1e-6:
        return "Start and end points are identical — cannot create a zero-length wall."

    level_name = (params.get("level", "") or "").strip()
    level = _find_level(doc, level_name)
    if level is None:
        return "No levels found in the model. Add a level before creating walls."

    wall_type = _find_wall_type(doc, params.get("wall_type", ""))
    if wall_type is None:
        return "No wall types found in the model."

    try:
        height_ft = float(params.get("height_mm", 3000)) * _MM_TO_FT
    except (TypeError, ValueError):
        height_ft = 3000.0 * _MM_TO_FT

    if height_ft < 0.1:
        return "Wall height is too small (minimum ~30 mm)."

    tx = Transaction(doc, "Koda: Create Wall")
    tx.Start()
    try:
        line = Line.CreateBound(XYZ(sx, sy, 0.0), XYZ(ex, ey, 0.0))
        wall = Wall_Create(doc, line, wall_type.Id, level.Id, height_ft, 0.0, False, False)
        tx.Commit()
        try:
            from System.Collections.Generic import List
            from Autodesk.Revit.DB import ElementId
            sel_ids = List[ElementId]()
            sel_ids.Add(wall.Id)
            uidoc.Selection.SetElementIds(sel_ids)
        except Exception:
            pass
        return (
            "Wall created on '{level}' using type '{wtype}'. "
            "Height: {h:.0f} mm. "
            "Start: ({sx:.0f}, {sy:.0f}) mm, End: ({ex:.0f}, {ey:.0f}) mm. "
            "Element ID: {eid}."
        ).format(
            level=level.Name,
            wtype=wall_type.Name,
            h=height_ft / _MM_TO_FT,
            sx=params.get("start_x", 0),
            sy=params.get("start_y", 0),
            ex=params.get("end_x",   0),
            ey=params.get("end_y",   0),
            eid=eid_int(wall.Id),
        )
    except Exception as e:
        try:
            if tx.HasStarted():
                tx.RollBack()
        except Exception:
            pass
        return "Failed to create wall: " + str(e)


def Wall_Create(doc, line, type_id, level_id, height_ft, offset, flip, structural):
    from Autodesk.Revit.DB import Wall
    return Wall.Create(doc, line, type_id, level_id, height_ft, offset, flip, structural)
