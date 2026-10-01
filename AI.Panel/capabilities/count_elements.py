# -*- coding: utf-8 -*-
# capabilities/count_elements.py
# Plugin: count instances of a category in the model.

ACTION_NAME  = "count_elements"
DESCRIPTION  = "Count how many instances of a category exist in the model."
PARAMS = {
    "category": "string — element category (e.g. 'walls', 'doors', 'windows')",
}
EXAMPLE = {
    "action": "count_elements",
    "params": {"category": "walls"},
}


def execute(params, doc, uidoc, resolve_category, **_kwargs):
    from Autodesk.Revit.DB import FilteredElementCollector

    if not doc:
        return "No document open."
    bic = resolve_category(params.get("category", ""))
    if bic is None:
        return "Unknown category: " + params.get("category", "")
    try:
        n = len(list(FilteredElementCollector(doc)
                     .OfCategory(bic)
                     .WhereElementIsNotElementType()
                     .ToElements()))
        return str(n) + " " + params.get("category", "") + " instance(s) in model."
    except Exception as e:
        return "Count failed: " + str(e)
