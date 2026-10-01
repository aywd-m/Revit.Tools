# -*- coding: utf-8 -*-
# capabilities/filter_schedule.py
# Plugin: Apply one or more filters to an existing schedule.

import re as _re  # Fix F5: module-scope import — stdlib survives pyRevit scope clear.

ACTION_NAME  = "filter_schedule"
DESCRIPTION  = (
    "Filter an existing schedule by one or more parameter conditions. "
    "Use this whenever the user says: 'filter [schedule] by [field] = [value]', "
    "'show only rows where [field] equals [value]', 'filter by comment', "
    "'filter by mark', 'filter by level', 'only show where [param] is [value]', "
    "'hide rows where', 'filter the schedule', or any similar phrasing. "
    "Required params: 'schedule_name' (name of the schedule to filter). "
    "For a SINGLE filter use: 'field' (the column/parameter name), "
    "'condition' (equals | not_equal | contains | does_not_contain | "
    "greater_than | less_than | greater_or_equal | less_or_equal), "
    "and 'value' (the value to match). "
    "For MULTIPLE filters use 'filters': a list of {field, condition, value} dicts (max 4, ANDed). "
    "Numeric fields (height, area, length, volume, etc.) accept unit suffixes "
    "in 'value' (e.g. '1000mm', '3 ft', '2.5 m') — conversion to Revit internal units is automatic. "
    "The schedule must already exist — if it does not, call create_schedule first, "
    "then call filter_schedule separately once that completes. "
    "There is NO separate 'filter_rooms', 'filter_walls', or 'apply_filter' action — "
    "filtering always uses THIS action (filter_schedule). "
    "Never merge filter_schedule into a create_schedule action."
)
PARAMS = {
    "schedule_name": "string — name of the existing schedule to filter",
    "field":         "string — parameter field to filter on (e.g. 'Unconnected Height', 'Mark'). "
                     "Use this with 'condition'/'value' for a single filter, OR omit and use 'filters' below.",
    "condition":     "string — 'equals' | 'not_equal' | 'contains' | 'does_not_contain' | "
                     "'greater_than' | 'less_than' | 'greater_or_equal' | 'less_or_equal'",
    "value":         "string — value to compare against (numeric values may include units, e.g. '1000mm')",
    "filters":       "list — optional, for multiple conditions (ANDed together, Revit max 4): "
                     "[{'field': 'Unconnected Height', 'condition': 'greater_than', 'value': '2000mm'}, ...]. "
                     "If provided, this takes precedence over the single field/condition/value params.",
}
EXAMPLE = {
    "action": "filter_schedule",
    "params": {
        "schedule_name": "Wall Schedule",
        "filters": [
            {"field": "Unconnected Height", "condition": "greater_than", "value": "2000mm"},
            {"field": "Level", "condition": "equals", "value": "Level 1"},
        ],
    },
}
# Fix F8: EXAMPLE_2 removed — dispatcher only reads EXAMPLE.

_COND_MAP_KEY = {
    "equals":            "Equal",
    "equal":             "Equal",
    "not_equal":         "NotEqual",
    "notequal":          "NotEqual",
    "contains":          "Contains",
    "does_not_contain":  "NotContains",
    "not_contains":      "NotContains",
    "greater_than":      "GreaterThan",
    "greater_or_equal":  "GreaterThanOrEqual",
    "less_than":         "LessThan",
    "less_or_equal":     "LessThanOrEqual",
}

# Recognized unit suffixes -> Autodesk.Revit.DB.UnitTypeId attribute name.
# Order matters: longer/more-specific suffixes checked before shorter ones.
_UNIT_SUFFIXES = [
    ("mm",    "Millimeters"),
    ("cm",    "Centimeters"),
    ("m2",    "SquareMeters"),
    ("m",     "Meters"),
    ("sqft",  "SquareFeet"),
    ("sq ft", "SquareFeet"),
    ("ft2",   "SquareFeet"),
    ("in",    "Inches"),
    ('"',     "Inches"),
    ("ft",    "Feet"),
    ("'",     "Feet"),
]

MAX_FILTERS = 4  # Revit schedule filter limit


def _parse_numeric_value(raw):
    """Split a value string like '1000mm' into (number, unit_suffix_or_None).

    Fix F5: uses module-scope _re instead of a per-call import.
    """
    s = raw.strip().lower()
    m = _re.match(r'^(-?\d+(?:\.\d+)?)\s*(.*)$', s)
    if not m:
        return None, None
    num_str, suffix = m.group(1), m.group(2).strip()
    try:
        num = float(num_str)
    except Exception:
        return None, None
    return num, suffix if suffix else None


def _resolve_field_value(doc, field, param_field_id, storage_type, condition_key, raw_value):
    """Convert a user-supplied string value into what ScheduleFilter needs.

    Returns (converted_value, note) or (None, error_str).

    Fix F1: Double storage type now cast to System.Double explicitly to resolve
            IronPython 2.7 CLR overload ambiguity between int and double overloads.
    Fix F2: ElementId fields (Level, Phase, etc.) are detected early and an
            explicit, actionable error is returned instead of silently passing
            a string to ScheduleFilter which would cause a confusing TypeError.
    """
    from Autodesk.Revit.DB import StorageType, UnitTypeId, UnitUtils, ElementId
    import System

    # Text-only conditions always compare as strings regardless of storage type.
    if condition_key in ("Contains", "NotContains"):
        return raw_value, None

    if storage_type == StorageType.String:
        return raw_value, None

    if storage_type == StorageType.Integer:
        num, _ = _parse_numeric_value(raw_value)
        if num is None:
            return None, ("value '" + raw_value + "' is not a valid number for an integer field")
        return int(round(num)), None

    if storage_type == StorageType.Double:
        num, suffix = _parse_numeric_value(raw_value)
        if num is None:
            return None, ("value '" + raw_value + "' is not a valid number for a numeric field")

        unit_type_id = None
        if suffix:
            for token, attr_name in _UNIT_SUFFIXES:
                if suffix == token:
                    unit_type_id = getattr(UnitTypeId, attr_name, None)
                    break

        try:
            if unit_type_id is not None:
                internal = UnitUtils.ConvertToInternalUnits(num, unit_type_id)
            else:
                # No recognizable unit suffix — treat as Revit internal units (decimal feet).
                internal = num
            # Fix F1: explicit System.Double cast resolves IronPython CLR overload
            # ambiguity — prevents wrong ScheduleFilter(FieldId, FilterType, int) overload.
            return System.Double(internal), None
        except Exception as e:
            return None, ("could not convert value '" + raw_value + "': " + str(e))

    # Fix F2: ElementId storage (Level, Phase, etc.) cannot be filtered by a
    # plain string — Revit requires an ElementId. Return a clear, actionable error.
    if storage_type == StorageType.ElementId:
        return None, (
            "field stores an ElementId (e.g. Level, Phase) — filtering by display name "
            "is not yet supported. Filter by a text field (e.g. Comments, Mark) instead, "
            "or use a numeric/string field to narrow the results."
        )

    # Unknown storage type: best-effort string pass-through.
    return raw_value, None


def _first_element_of_category(doc, category_id):
    from Autodesk.Revit.DB import FilteredElementCollector
    try:
        it = (FilteredElementCollector(doc)
              .OfCategoryId(category_id)
              .WhereElementIsNotElementType()
              .ToElements())
        for el in it:
            return el
    except Exception:
        pass
    return None


def _build_one_filter(doc, defn, sample_element, field_name, condition, value):
    """Resolve one {field, condition, value} entry into a Revit ScheduleFilter.

    Returns (ScheduleFilter, description_str) or (None, error_str).

    Fix F3: GetName(doc) used throughout for consistent localised display names.
    Fix F6: when sample_element is None and the field name looks numeric, attempt
            a float parse so the value is sent as System.Double rather than string.
    """
    from Autodesk.Revit.DB import (
        ScheduleFilter, ScheduleFilterType, StorageType
    )
    import System

    field_name = (field_name or "").strip()
    condition  = (condition or "").strip().lower()
    value      = (value or "").strip()

    if not field_name or not condition or not value:
        return None, "each filter needs field, condition, and value"

    cond_key = _COND_MAP_KEY.get(condition)
    if cond_key is None:
        return None, ("unsupported condition '" + condition + "'. Use: "
                      + ", ".join(sorted(set(_COND_MAP_KEY.keys()))))
    filter_type = getattr(ScheduleFilterType, cond_key)

    # ── Find the field already added to the schedule ──────────────────────────
    # Filters can only target fields that are already columns in the schedule.
    # Fix X1/F3: GetName(doc) for localised display name comparison.
    field_count = defn.GetFieldCount()
    target_field = None

    # Pass 1: exact match.
    for i in range(field_count):
        try:
            sf = defn.GetField(i)
            if sf.GetName(doc).lower() == field_name.lower():
                target_field = sf
                break
        except Exception:
            continue

    # Pass 2: substring match.
    if target_field is None:
        for i in range(field_count):
            try:
                sf = defn.GetField(i)
                sn = sf.GetName(doc).lower()
                if field_name.lower() in sn or sn in field_name.lower():
                    target_field = sf
                    break
            except Exception:
                continue

    if target_field is None:
        available = []
        for i in range(field_count):
            try:
                available.append(defn.GetField(i).GetName(doc))
            except Exception:
                pass
        return None, ("field '" + field_name + "' not found in schedule. "
                      "Fields present: " + ", ".join(available) + ". "
                      "Add the field to the schedule first, or check the name.")

    # ── Determine storage type ────────────────────────────────────────────────
    storage_type = StorageType.String
    if sample_element is not None:
        try:
            p = sample_element.get_Parameter(target_field.ParameterId)
            if p is not None:
                storage_type = p.StorageType
        except Exception:
            pass
    else:
        # Fix F6: no sample element — heuristic storage-type inference from value.
        # If the value parses as a number and the condition is numeric, treat as Double.
        num, _ = _parse_numeric_value(value)
        if (num is not None
                and cond_key not in ("Contains", "NotContains", "Equal", "NotEqual")):
            storage_type = StorageType.Double

    converted, err = _resolve_field_value(
        doc, target_field, target_field.FieldId,
        storage_type, cond_key, value
    )
    if err is not None:
        return None, ("field '" + field_name + "': " + err)

    # ── Build ScheduleFilter ──────────────────────────────────────────────────
    # Fix F1: numeric values are already cast to System.Double in _resolve_field_value.
    # String values pass through as Python str — CLR bridge handles string overload correctly.
    try:
        sched_filter = ScheduleFilter(target_field.FieldId, filter_type, converted)
    except Exception as e:
        return None, ("could not build filter for '" + field_name + "': " + str(e))

    # Fix F3: use GetName(doc) in the description string too.
    desc = target_field.GetName(doc) + " " + condition + " '" + value + "'"
    return sched_filter, desc


def execute(params, doc, uidoc, **_kwargs):
    from Autodesk.Revit.DB import FilteredElementCollector, ViewSchedule, Transaction

    if not doc:
        return "No document open."

    sched_name = params.get("schedule_name", "").strip()
    if not sched_name:
        return "Missing required parameter: schedule_name."

    # ── Normalise input: 'filters' list takes precedence ─────────────────────
    raw_filters = params.get("filters") or []
    if not raw_filters:
        field_name = params.get("field", "").strip()
        condition  = params.get("condition", "").strip()
        value      = params.get("value", "").strip()
        if not field_name or not condition or not value:
            return ("Missing required parameters: provide either 'filters' (a list), "
                    "or 'schedule_name' + 'field' + 'condition' + 'value'.")
        raw_filters = [{"field": field_name, "condition": condition, "value": value}]

    truncated_note = ""
    if len(raw_filters) > MAX_FILTERS:
        truncated_note = (" (Revit allows a maximum of " + str(MAX_FILTERS)
                          + " filters per schedule — only the first "
                          + str(MAX_FILTERS) + " were applied.)")
        raw_filters = raw_filters[:MAX_FILTERS]

    # ── Find the schedule — single pass ──────────────────────────────────────
    # Fix F7: one collector pass collects all schedules into a dict;
    # avoids double scan (exact then fuzzy) with two separate API calls.
    all_by_name  = {}   # exact name -> schedule
    all_names    = []
    for s in FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements():
        try:
            if s.IsTemplate:
                continue
            all_by_name[s.Name] = s
            all_names.append(s.Name)
        except Exception:
            continue

    sched = all_by_name.get(sched_name)
    if sched is None:
        # Fuzzy fallback: substring match, first alphabetical hit.
        sl = sched_name.lower()
        for name in sorted(all_by_name.keys()):
            if sl in name.lower():
                sched = all_by_name[name]
                break

    if sched is None:
        hint = ", ".join(sorted(set(all_names))[:15]) if all_names else "none"
        return "Schedule '" + sched_name + "' not found. Available schedules: " + hint + "."

    defn           = sched.Definition
    sample_element = _first_element_of_category(doc, defn.CategoryId)

    # ── Build all ScheduleFilter objects before opening a transaction ─────────
    built  = []
    errors = []
    for entry in raw_filters:
        if not isinstance(entry, dict):
            errors.append("skipped invalid filter entry: " + str(entry))
            continue
        sf, result = _build_one_filter(
            doc, defn, sample_element,
            entry.get("field", ""), entry.get("condition", ""), entry.get("value", "")
        )
        if sf is None:
            errors.append(result)
        else:
            built.append((sf, result))

    if not built:
        msg = "Could not apply any filters."
        if errors:
            msg += " " + " | ".join(errors)
        return msg

    # ── Apply in a transaction ────────────────────────────────────────────────
    tx = Transaction(doc, "Chat: Filter Schedule")
    tx.Start()
    try:
        # Fix F4: RemoveFilter expects an index (int), not a filter object.
        # Remove all existing filters by iterating indices in reverse so
        # removal of index i does not shift remaining lower indices.
        existing_count = len(list(defn.GetFilters()))
        for i in reversed(range(existing_count)):
            try:
                defn.RemoveFilter(i)
            except Exception:
                pass

        for sf, _desc in built:
            defn.AddFilter(sf)

        tx.Commit()
    except Exception as e:
        try:
            tx.RollBack()
        except Exception:
            pass
        return "Failed to apply filter(s): " + str(e)

    applied_desc = "; ".join(d for _sf, d in built)
    msg = "Filter(s) applied to '" + sched.Name + "': " + applied_desc + "." + truncated_note
    if errors:
        msg += " Some filters were skipped: " + " | ".join(errors) + "."
    return msg
