# -*- coding: utf-8 -*-
# capabilities/list_schedules.py
# Plugin: list all schedules in the model.

ACTION_NAME  = "list_schedules"
DESCRIPTION  = "List all schedule views in the model."
PARAMS       = {}
EXAMPLE      = {
    "action": "list_schedules",
    "params": {},
}


def execute(params, doc, uidoc, **_kwargs):
    from Autodesk.Revit.DB import FilteredElementCollector, ViewSchedule

    if not doc:
        return "No document open."

    schedules = []

    # Lazy iteration - avoids loading all elements into memory at once
    try:
        collector = FilteredElementCollector(doc).OfClass(ViewSchedule)
    except Exception as e:
        return "Failed to collect schedules: " + str(e)

    for s in collector:
        try:
            # Exclude view templates and key schedules
            if not s.IsTemplate and not s.IsKeySchedule:
                schedules.append({
                    "id":   s.Id.IntegerValue,
                    "name": s.Name,
                })
        except Exception as e:
            # Element is corrupt or partially loaded - skip and continue.
            # Uncomment the line below to surface skipped elements during debugging:
            # print("Skipped element {0}: {1}".format(s.Id, e))
            pass

    if not schedules:
        return "No schedules found."

    # Sort alphabetically by name (case-insensitive); ties broken by id
    schedules.sort(key=lambda x: (x["name"].lower(), x["id"]))

    header = "{0} schedule(s) in model:".format(len(schedules))
    lines  = ["  [{0}] {1}".format(s["id"], s["name"]) for s in schedules]

    return header + "\n" + "\n".join(lines)
