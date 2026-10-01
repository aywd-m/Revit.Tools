# -*- coding: utf-8 -*-
# capabilities/create_schedule.py
# Plugin: create a Revit schedule for a given category.

ACTION_NAME  = "create_schedule"
DESCRIPTION  = (
    "Create a new schedule view for a category. "
    "Specify category, field names, whether to include a count column, "
    "an optional title, optional sort/group-by fields, and whether to itemize every instance. "
    "Supports 'itemize' param (boolean, default false): "
    "when true each element instance appears as its own row (IsItemized=True); "
    "when false rows are grouped/counted (IsItemized=False). "
    "Use 'itemize': true when the user says 'itemize each', 'itemize every', "
    "'itemize all', 'itemise', 'every instance', 'one row per element', "
    "'list each individually', 'detailed list', or any phrase containing 'itemize'. "
    "There is NO separate itemize_schedule action — itemize is a param of THIS action. "
    "IMPORTANT: This action creates the schedule only. "
    "It does NOT support a 'filter' param — never include one. "
    "If the user also wants to filter the schedule, "
    "call filter_schedule in a SEPARATE action after this one completes. "
    "Never combine create_schedule and filter_schedule into a single action block."
)
PARAMS = {
    "category":   "string  — element category (e.g. 'furniture', 'walls', 'doors')",
    "fields":     "list    — parameter display names to add as columns (e.g. ['Family Name','Mark'])",
    "with_count": "boolean — include a Count column (default true)",
    "title":      "string  — schedule name (defaults to '<Category> Schedule')",
    "itemize":    "boolean — when true each element instance gets its own row (default false). "
                 "Use when user says 'itemize', 'every instance', 'one row per element'.",
    "sort_by":    (
        "list — fields to sort/group by, applied in order as 'Sort by', 'Then by', ... "
        "Each item can be a plain string field name (e.g. 'Level'), or a dict for more "
        "control: {'field': 'Level', 'order': 'ascending'|'descending', "
        "'header': bool, 'footer': bool, 'blank_line': bool}. "
        "If a sort field wasn't also requested in 'fields', it is added as a hidden column "
        "automatically so it can be sorted/grouped on."
    ),
}
EXAMPLE = {
    "action": "create_schedule",
    "params": {
        "category":   "doors",
        "fields":     ["Type Mark", "Level"],
        "with_count": True,
        "itemize":    False,
        "title":      "Doors Schedule",
        "sort_by":    [{"field": "Level", "order": "ascending", "header": True}],
    },
}

_FIELD_ALIASES = {
    "type name":          ["family and type", "type", "wall type", "type name"],
    "family name":        ["family and type", "family", "family name"],
    "family type name":   ["family and type", "family name", "type name"],
    "family type":        ["family and type"],
    "family and type":    ["family and type"],
    "unconnected height": ["unconnected height", "height"],
    "height":             ["unconnected height", "height"],
    "wall height":        ["unconnected height", "height"],
    "base constraint":    ["base constraint", "base level"],
    "top constraint":     ["top constraint"],
    "base offset":        ["base offset"],
    "top offset":         ["top offset"],
    "length":             ["length"],
    "area":               ["area"],
    "volume":             ["volume"],
    "mark":               ["mark"],
    "comments":           ["comments"],   # exact only — do NOT fuzzy-match "Analytical: Comments"
    "description":        ["description"],
    "count":              ["count"],
    "type mark":          ["type mark"],
    "manufacturer":       ["manufacturer"],
    "structural usage":   ["structural usage"],
    "function":           ["function"],
    "width":              ["width"],
    "thickness":          ["width", "thickness"],
    "level":              ["level", "base constraint", "base level", "schedule level"],
    "base level":         ["base constraint", "level"],
    # Room fields
    "room number":        ["number"],
    "room name":          ["name"],
    "room area":          ["area"],
    "room level":         ["level"],
    "room phase":         ["phase"],
    "room department":    ["department"],
    # Sheet fields
    "sheet number":       ["number", "sheet number"],
    "sheet name":         ["name", "sheet name"],
    "sheet issue date":   ["issue date"],
    # Door / window fields
    "door number":        ["number", "mark"],
    "window number":      ["number", "mark"],
    # Level fields
    "level name":         ["name"],
    "level elevation":    ["elevation"],
    # Generic fallbacks
    "number":             ["number", "mark"],
    "name":               ["name"],
    "phase":              ["phase"],
}


def _resolve_schedulable_field(fl, by_bip, by_name, field_bip, eid_int, ElementId):
    """Resolve a lowercased field name to a Revit SchedulableField using
    BuiltInParameter lookup, exact name match, alias table, then fuzzy match.

    Fix C1: BIP lookup uses individual try/except so one bad ParameterId does
            not silently discard all subsequent valid entries.
    Fix C2/C7: fuzzy sort key is (score, name) for deterministic tie-breaking;
               word-boundary bonus applies only when fl matches a complete token.
    Fix X1: GetName(doc) used via by_name which is already built with GetName(doc).
    """
    sf = None

    # ── 1. BuiltInParameter fast path ────────────────────────────────────────
    bip = field_bip.get(fl)
    if bip is not None:
        try:
            sf = by_bip.get(eid_int(ElementId(bip)))
        except Exception:
            pass

    # ── 2. Exact display-name match ──────────────────────────────────────────
    if sf is None:
        sf = by_name.get(fl)

    # ── 3. Alias table ───────────────────────────────────────────────────────
    if sf is None:
        for alias in _FIELD_ALIASES.get(fl, []):
            sf = by_name.get(alias)
            if sf is not None:
                break

    # ── 4. Scored fuzzy match ────────────────────────────────────────────────
    # Lower score = better candidate.
    # Penalise names containing ":" (e.g. "Analytical: Comments").
    # Prefer shorter names. Prefer whole-word matches via bonus.
    if sf is None:
        candidates = []
        for n, s in by_name.items():
            if fl not in n and n not in fl:
                continue
            penalty_colon  = 1000 if ":" in n else 0
            penalty_length = len(n)
            # Whole-word bonus: fl must be the entire name or a complete space-
            # delimited token at the start or end, not just an embedded substring.
            is_whole_word = (
                n == fl
                or n.startswith(fl + " ")
                or n.endswith(" " + fl)
            )
            bonus_word = -50 if is_whole_word else 0
            score = penalty_colon + penalty_length + bonus_word
            # Secondary key = name for deterministic ordering when scores tie.
            candidates.append((score, n, s))
        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1]))
            sf = candidates[0][2]

    return sf


def execute(params, doc, uidoc, resolve_category, get_field_bip, eid_int, **_kwargs):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, ViewSchedule, ScheduleFieldType,
        Transaction, ElementId, ScheduleSortGroupField, ScheduleSortOrder
    )

    if not doc:
        return "No document open."

    cat_name   = params.get("category", "selection")
    fields     = params.get("fields", [])
    if not fields:
        if cat_name.lower() in ("walls", "wall"):
            fields = ["Family Name", "Type Name", "Unconnected Height"]
        else:
            fields = ["Family Name", "Type Name"]
    with_count = params.get("with_count", True)
    sort_by    = params.get("sort_by", []) or []

    # Fix C3: treat an explicit null/None the same as omitted — do not let
    # params["itemize"] = null override the inference logic.
    itemize_raw = params.get("itemize")
    itemize_explicit = (itemize_raw is not None)
    itemize = bool(itemize_raw) if itemize_explicit else False

    # ── Infer category from selection when model sends 'selection' or unknown ──
    bic = resolve_category(cat_name)
    if bic is None:
        if uidoc is not None:
            try:
                sel_ids = list(uidoc.Selection.GetElementIds())
                if sel_ids:
                    el = doc.GetElement(sel_ids[0])
                    if el is not None and el.Category is not None:
                        inferred = el.Category.Name.lower()
                        bic = resolve_category(inferred)
                        if bic is not None:
                            cat_name = el.Category.Name
            except Exception:
                pass
        if bic is None:
            return ("Unknown category: '" + cat_name + "'. "
                    "Valid categories: walls, doors, windows, floors, "
                    "furniture, columns, structural columns, rooms, ceilings, roofs, casework. "
                    "Select elements in Revit first so the category can be inferred.")

    title = params.get("title", cat_name.title() + " Schedule")

    # ── Auto-increment name to avoid duplicates ───────────────────────────────
    # Fix C6: collector failure leaves existing_names empty (safe — worst case
    # we create a duplicate-named schedule and Revit appends its own suffix).
    existing_names = set()
    try:
        collector = FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements()
        for s in collector:
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

    tx = Transaction(doc, "Chat: Create Schedule")
    tx.Start()
    try:
        try:
            sched = ViewSchedule.CreateSchedule(doc, ElementId(int(bic)))
        except Exception:
            sched = ViewSchedule.CreateSchedule(doc, ElementId(bic))
        sched.Name = unique_title
        defn = sched.Definition

        # ── IsItemized logic ─────────────────────────────────────────────────
        # Fix C3/C4:
        #   itemize explicitly provided (and non-null) → honour it directly.
        #   Omitted or null:
        #     with_count=True (default)  → grouped (IsItemized=False)
        #     with_count=False           → itemized (IsItemized=True)
        if itemize_explicit:
            defn.IsItemized = itemize
        else:
            defn.IsItemized = not with_count

        # ── Build field lookup dicts ─────────────────────────────────────────
        # Fix C1: each ParameterId lookup is individually guarded so a bad ID
        # (e.g. ParameterType.Invalid fields) does not skip subsequent entries.
        # Fix X1: GetName(doc) used for localised display names.
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

        field_bip    = get_field_bip()
        added        = []
        skipped      = []
        # Track added ScheduleField objects keyed by lowercase name for sort_by reuse.
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

            sf = _resolve_schedulable_field(fl, by_bip, by_name, field_bip, eid_int, ElementId)
            if sf:
                try:
                    sched_field = defn.AddField(sf)
                    added.append(fname)
                    added_fields[fl] = sched_field
                except Exception as fe:
                    skipped.append(fname + "(" + str(fe) + ")")
            else:
                skipped.append(fname + "(not found)")

        # ── Sorting / grouping ───────────────────────────────────────────────
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
                # Not already a visible column — resolve and add hidden so it
                # can be sorted/grouped on without appearing in the view.
                sf = _resolve_schedulable_field(sl, by_bip, by_name, field_bip, eid_int, ElementId)
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

        # Fix C5: guard against uidoc being None (non-UI / batch contexts).
        if uidoc is not None:
            try:
                uidoc.ActiveView = sched
            except Exception:
                pass

        itemize_state = "itemized" if defn.IsItemized else "grouped"
        msg = "Schedule '" + unique_title + "' created (" + itemize_state + ")."
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
