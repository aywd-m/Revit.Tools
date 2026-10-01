# -*- coding: utf-8 -*-
# capabilities/get_current_view_info.py
# Plugin: return detailed info about the active view, plus optional level list.

ACTION_NAME  = "get_current_view_info"
DESCRIPTION  = (
    "Return detailed information about the currently active view: "
    "name, type, scale, phase, associated level, view template, "
    "crop status, and detail level. "
    "Set include_levels=true to also list all levels in the model — "
    "useful when the user asks 'what levels exist' or 'show me all levels'."
)
PARAMS = {
    "include_levels": "boolean — when true, append a list of all model levels (default false)",
}
EXAMPLE = {
    "action": "get_current_view_info",
    "params": {},
}
EXAMPLE_LEVELS = {
    "action": "get_current_view_info",
    "params": {"include_levels": True},
}


def execute(params, doc, uidoc, eid_int, **_kwargs):
    from Autodesk.Revit.DB import BuiltInParameter, FilteredElementCollector, Level

    if not doc or not uidoc:
        return "No document open."
    try:
        av = uidoc.ActiveView
    except Exception:
        return "Cannot read active view."
    if av is None:
        return "No active view."

    lines = ["View: " + av.Name]

    # Fix GCV2: ViewType.ToString() — avoids raw enum int in IronPython 2.7.
    try:
        lines.append("Type: " + av.ViewType.ToString())
    except Exception:
        pass

    # Scale
    try:
        lines.append("Scale: 1:" + str(av.Scale))
    except Exception:
        pass

    # Fix GCV3: DetailLevel.ToString() — same reason as GCV2.
    try:
        lines.append("Detail Level: " + av.DetailLevel.ToString())
    except Exception:
        pass

    # Phase
    try:
        p = av.get_Parameter(BuiltInParameter.VIEW_PHASE)
        if p is not None and p.AsValueString():
            lines.append("Phase: " + p.AsValueString())
    except Exception:
        pass

    # Associated level
    try:
        lp = av.get_Parameter(BuiltInParameter.PLAN_VIEW_LEVEL)
        if lp is not None:
            lv_id = lp.AsElementId()
            if lv_id is not None and eid_int(lv_id) > 0:
                lv_el = doc.GetElement(lv_id)
                if lv_el is not None:
                    lines.append("Level: " + lv_el.Name)
    except Exception:
        pass

    # View template
    try:
        vt_id = av.ViewTemplateId
        if vt_id is not None and eid_int(vt_id) > 0:
            vt_el = doc.GetElement(vt_id)
            if vt_el is not None:
                lines.append("View Template: " + vt_el.Name)
        else:
            lines.append("View Template: <none>")
    except Exception:
        pass

    # Crop box
    try:
        if av.CropBoxActive:
            lines.append("Crop: Active" + (" (visible)" if av.CropBoxVisible else " (hidden)"))
        else:
            lines.append("Crop: Inactive")
    except Exception:
        pass

    # Is template notice
    try:
        if av.IsTemplate:
            lines.append("(This is a view template, not a placeable view)")
    except Exception:
        pass

    # Fix GCV1: optional level list.
    include_levels = bool(params.get("include_levels", False))
    if include_levels:
        try:
            lvls = sorted(
                [lv.Name for lv in
                 FilteredElementCollector(doc).OfClass(Level).ToElements()],
                key=lambda n: n.lower()
            )
            if lvls:
                lines.append("\nLevels in model ({0}):".format(len(lvls)))
                lines.extend("  " + n for n in lvls)
            else:
                lines.append("\nNo levels found in model.")
        except Exception as e:
            lines.append("\nCould not read levels: " + str(e))

    return "\n".join(lines)
