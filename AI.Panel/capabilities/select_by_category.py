# -*- coding: utf-8 -*-
# capabilities/select_by_category.py
# Plugin: select all elements of a category in the active view.

ACTION_NAME  = "select_by_category"
DESCRIPTION  = "Select all elements of a category in the active view."
PARAMS = {
    "category": "string — element category (e.g. 'doors', 'structural columns')",
}
EXAMPLE = {
    "action": "select_by_category",
    "params": {"category": "doors"},
}


def execute(params, doc, uidoc, resolve_category, **_kwargs):
    from Autodesk.Revit.DB import FilteredElementCollector, ElementId
    from System.Collections.Generic import List

    if not doc or not uidoc:
        return "No document open."
    bic = resolve_category(params.get("category", ""))
    if bic is None:
        return "Unknown category."
    try:
        av  = uidoc.ActiveView
        ids = List[ElementId](
            FilteredElementCollector(doc, av.Id)
            .OfCategory(bic)
            .WhereElementIsNotElementType()
            .ToElementIds()
        )
        uidoc.Selection.SetElementIds(ids)
        return "Selected " + str(ids.Count) + " " + params.get("category", "") + " element(s)."
    except Exception as e:
        return "Select failed: " + str(e)
