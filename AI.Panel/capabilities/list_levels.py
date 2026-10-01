# -*- coding: utf-8 -*-
# capabilities/list_levels.py
# Plugin: list all levels in the model with elevation and building story status.

ACTION_NAME  = "list_levels"
DESCRIPTION  = (
    "List all levels in the model with their name, elevation, and whether "
    "they are marked as a Building Story."
)
PARAMS       = {}
EXAMPLE      = {
    "action": "list_levels",
    "params": {},
}


def execute(params, doc, uidoc, **_kwargs):
    from Autodesk.Revit.DB import FilteredElementCollector, Level, BuiltInParameter

    if not doc:
        return "No document open."
    try:
        levels = sorted(
            FilteredElementCollector(doc).OfClass(Level).ToElements(),
            key=lambda l: l.Elevation
        )
        if not levels:
            return "No levels found in the model."
        lines = []
        for lv in levels:
            name = lv.Name
            # Elevation as value string (uses project units)
            elev = ""
            try:
                p = lv.get_Parameter(BuiltInParameter.LEVEL_ELEV)
                if p is not None:
                    elev = p.AsValueString() or str(round(lv.Elevation, 4)) + " ft"
                else:
                    elev = str(round(lv.Elevation, 4)) + " ft"
            except Exception:
                elev = str(round(lv.Elevation, 4)) + " ft"
            # Building Story flag
            story = ""
            try:
                bp = lv.get_Parameter(BuiltInParameter.LEVEL_IS_BUILDING_STORY)
                if bp is not None:
                    story = " (Building Story)" if bp.AsInteger() == 1 else ""
            except Exception:
                pass
            lines.append(name + ": " + elev + story)
        return str(len(levels)) + " level(s):\n" + "\n".join(lines)
    except Exception as e:
        return "Failed to list levels: " + str(e)