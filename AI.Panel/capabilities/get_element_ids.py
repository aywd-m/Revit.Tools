# -*- coding: utf-8 -*-
# capabilities/get_element_ids.py
# Plugin: return element IDs of currently selected elements.

ACTION_NAME  = "get_element_ids"
DESCRIPTION  = (
    "Return the element IDs of the currently selected elements. "
    "Use this when the user asks for element IDs, IDs of selection, or wants to identify selected elements."
)
PARAMS       = {}
EXAMPLE      = {
    "action": "get_element_ids",
    "params": {},
}


def execute(params, doc, uidoc, eid_int, **_kwargs):
    if not doc or not uidoc:
        return "No document open."
    try:
        ids = list(uidoc.Selection.GetElementIds())
    except Exception as e:
        return "Cannot read selection: " + str(e)
    if not ids:
        return "No elements selected. Select elements in Revit first, then ask again."

    lines = []
    for eid in ids:
        try:
            elem  = doc.GetElement(eid)
            eid_v = eid_int(eid)
            if elem is None:
                lines.append("ID: " + str(eid_v))
                continue
            cat = ""
            try:
                cat = elem.Category.Name + " "
            except Exception:
                pass
            try:
                name = elem.Name or ""
            except Exception:
                name = ""
            lines.append(cat + "ID: " + str(eid_v) + (" — " + name if name else ""))
        except Exception as ex:
            lines.append("Error: " + str(ex))

    return str(len(ids)) + " selected element(s):\n" + "\n".join(lines)
