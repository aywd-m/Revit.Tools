# -*- coding: utf-8 -*-
# capabilities/create_door_schedule.py
# Kidzink Koda capability — Create Door Schedule
# Thin wrapper around create_schedule that hardcodes category=doors and
# supplies sensible door-specific default fields.
# (c) Archie C. Manza 2026

ACTION_NAME = "create_door_schedule"

DESCRIPTION = (
    "Create a door schedule. Optionally specify field columns, a title, "
    "and sort/group-by fields. Defaults to Family Name, Type Mark, Level, "
    "Mark, and Fire Rating if no fields are supplied."
)

PARAMS = {
    "fields":     "list   — column names to include (default: Family Name, Type Mark, Level, Mark, Fire Rating)",
    "title":      "string — schedule name (default: 'Door Schedule')",
    "with_count": "boolean — include a Count column (default false)",
    "sort_by":    (
        "list — fields to sort/group by. Each item is a plain string field name "
        "or a dict: {'field': 'Level', 'order': 'ascending'|'descending', "
        "'header': bool, 'footer': bool, 'blank_line': bool}."
    ),
}

EXAMPLE = {
    "action": "create_door_schedule",
    "params": {
        "fields":     ["Family Name", "Type Mark", "Level", "Mark", "Fire Rating"],
        "title":      "Door Schedule",
        "with_count": False,
        "sort_by":    [{"field": "Level", "order": "ascending", "header": True}],
    },
}

_DEFAULT_FIELDS = ["Family Name", "Type Mark", "Level", "Mark", "Fire Rating"]

_FIELD_ALIASES = {
    "type name":          ["family and type", "type", "type name"],
    "family name":        ["family and type", "family", "family name"],
    "family and type":    ["family and type"],
    "mark":               ["mark"],
    "type mark":          ["type mark"],
    "level":              ["level", "base constraint", "schedule level"],
    "fire rating":        ["fire rating"],
    "comments":           ["comments"],
    "width":              ["width"],
    "height":             ["height", "door height"],
    "count":              ["count"],
    "from room":          ["from room"],
    "to room":            ["to room"],
    "manufacturer":       ["manufacturer"],
    "description":        ["description"],
}


def _resolve_field(fl, by_bip, by_name, field_bip, eid_int, ElementId):
    sf = None
    bip = field_bip.get(fl)
    if bip is not None:
        try:
            sf = by_bip.get(eid_int(ElementId(bip)))
        except Exception:
            pass
    if sf is None:
        sf = by_name.get(fl)
    if sf is None:
        for alias in _FIELD_ALIASES.get(fl, []):
            sf = by_name.get(alias)
            if sf is not None:
                break
    if sf is None:
        candidates = [(len(n), n, s) for n, s in by_name.items()
                      if fl in n or n in fl]
        if candidates:
            candidates.sort()
            sf = candidates[0][2]
    return sf


def execute(params, doc, uidoc, resolve_category, get_field_bip, eid_int, **_kwargs):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, ViewSchedule, ScheduleFieldType,
        Transaction, ElementId, ScheduleSortGroupField, ScheduleSortOrder,
        BuiltInCategory
    )

    if not doc:
        return "No document open."

    fields     = params.get("fields", []) or _DEFAULT_FIELDS
    title      = params.get("title", "Door Schedule")
    with_count = params.get("with_count", False)
    sort_by    = params.get("sort_by", []) or []

    bic = BuiltInCategory.OST_Doors

    # Auto-increment name to avoid duplicates
    existing_names = set()
    try:
        for s in FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements():
            try:
                existing_names.add(s.Name)
            except Exception:
                pass
    except Exception:
        pass
    unique_title = title
    if unique_title in existing_names:
        counter = 2
        while (unique_title + " " + str(counter)) in existing_names:
            counter += 1
        unique_title = unique_title + " " + str(counter)

    tx = Transaction(doc, "Koda: Create Door Schedule")
    tx.Start()
    try:
        try:
            sched = ViewSchedule.CreateSchedule(doc, ElementId(int(bic)))
        except Exception:
            sched = ViewSchedule.CreateSchedule(doc, ElementId(bic))
        sched.Name = unique_title
        defn = sched.Definition
        defn.IsItemized = not with_count

        by_bip  = {}
        by_name = {}
        for sf in defn.GetSchedulableFields():
            try:
                by_bip[eid_int(sf.ParameterId)] = sf
            except Exception:
                pass
            try:
                by_name[sf.GetName(doc).lower()] = sf
            except Exception:
                pass

        field_bip   = get_field_bip()
        added       = []
        skipped     = []
        added_fields = {}

        for fname in fields:
            fl = fname.lower()
            if fl == "count":
                csf = [sf for sf in defn.GetSchedulableFields()
                       if sf.FieldType == ScheduleFieldType.Count]
                if csf:
                    sched_field = defn.AddField(csf[0])
                    added.append("Count")
                    added_fields["count"] = sched_field
                else:
                    skipped.append("Count(not available)")
                continue
            sf = _resolve_field(fl, by_bip, by_name, field_bip, eid_int, ElementId)
            if sf:
                try:
                    sched_field = defn.AddField(sf)
                    added.append(fname)
                    added_fields[fl] = sched_field
                except Exception as fe:
                    skipped.append(fname + "(" + str(fe) + ")")
            else:
                skipped.append(fname + "(not found)")

        # Sorting / grouping
        sorted_applied = []
        sort_skipped   = []
        for entry in sort_by:
            if isinstance(entry, dict):
                sfield = entry.get("field", "")
                order  = str(entry.get("order", "ascending")).lower()
                header = bool(entry.get("header", False))
                footer = bool(entry.get("footer", False))
                blank  = bool(entry.get("blank_line", False))
            else:
                sfield = str(entry)
                order  = "ascending"
                header = False
                footer = False
                blank  = False
            if not sfield:
                continue
            sl = sfield.lower()
            sched_field = added_fields.get(sl)
            if sched_field is None:
                sf = _resolve_field(sl, by_bip, by_name, field_bip, eid_int, ElementId)
                if sf is None:
                    sort_skipped.append(sfield + "(not found)")
                    continue
                try:
                    sched_field = defn.AddField(sf)
                    try:
                        sched_field.IsHidden = True
                    except Exception:
                        pass
                    added_fields[sl] = sched_field
                except Exception as fe:
                    sort_skipped.append(sfield + "(" + str(fe) + ")")
                    continue
            try:
                ssf = ScheduleSortGroupField(sched_field.FieldId)
                ssf.SortOrder = (ScheduleSortOrder.Descending
                                  if order.startswith("desc")
                                  else ScheduleSortOrder.Ascending)
                try:
                    ssf.ShowHeader = header
                except Exception:
                    pass
                try:
                    ssf.ShowFooter = footer
                except Exception:
                    pass
                try:
                    ssf.ShowBlankLine = blank
                except Exception:
                    pass
                defn.AddSortGroupField(ssf)
                sorted_applied.append(sfield + (" (desc)" if order.startswith("desc") else ""))
            except Exception as se:
                sort_skipped.append(sfield + "(" + str(se) + ")")

        tx.Commit()
        try:
            uidoc.ActiveView = sched
        except Exception:
            pass

        msg = "Door schedule '" + unique_title + "' created."
        if unique_title != title:
            msg += " (renamed — '" + title + "' already existed)."
        if added:
            msg += " Fields added: " + ", ".join(added) + "."
        if skipped:
            available = sorted(by_name.keys())[:20]
            msg += " Skipped (not found): " + ", ".join(skipped) + "."
            msg += " Available fields include: " + ", ".join(available) + "."
        if sorted_applied:
            msg += " Sorted by: " + ", ".join(sorted_applied) + "."
        if sort_skipped:
            msg += " Sort fields skipped: " + ", ".join(sort_skipped) + "."
        return msg

    except Exception as e:
        try:
            if tx.HasStarted():
                tx.RollBack()
        except Exception:
            pass
        return "Failed: " + str(e)
