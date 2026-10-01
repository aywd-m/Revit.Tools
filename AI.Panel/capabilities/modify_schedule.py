# -*- coding: utf-8 -*-
# capabilities/modify_schedule.py
# Plugin: add or remove fields from an existing schedule.

ACTION_NAME  = "modify_schedule"
DESCRIPTION  = (
    "IMPORTANT: There is NO 'itemize_schedule', 'sort_schedule', or 'group_schedule' action. "
    "Itemizing, sorting, and grouping are ALL handled by THIS action (modify_schedule). "
    "Use modify_schedule whenever the user says: "
    "'itemize', 'itemise', 'itemize each', 'itemize every instance', "
    "'one row per element', 'list each individually', 'detailed list', "
    "'sort by', 'group by', 'add a column', 'remove a column', "
    "or any phrase about changing how an existing schedule looks or behaves. "
    "Modify an existing schedule view. Supports: "
    "adding columns ('fields'), removing columns ('remove_fields'), "
    "sorting and grouping rows ('sort_by'), "
    "toggling itemized-every-instance vs grouped mode ('itemize'), "
    "and adding a Count column ('with_count'). "
    "'schedule_name' is inferred from the active view if omitted -- "
    "when the user says 'itemize each' without naming a schedule, "
    "use the most recently mentioned schedule name from context. "
    "To itemize every instance: pass itemize=true. "
    "To group identical rows: pass itemize=false. "
    "To sort: pass sort_by as field names or dicts with 'field', "
    "'order' (ascending/descending), 'header', 'footer', 'blank_line' bools. "
    "Omit itemize or sort_by to leave existing settings unchanged."
)
PARAMS = {
    "schedule_name": "string  — name of the existing schedule (e.g. 'Room Schedule')",
    "fields":        "list    — field names to ADD as columns (e.g. ['Room Number','Area'])",
    "remove_fields": "list    — field names to REMOVE from the schedule (optional)",
    "with_count":    "boolean — add a Count column (default false, only if not already present)",
    "itemize":       "boolean — true = itemize every instance (one row per element), "
                     "false = group identical rows. Omit to leave unchanged.",
    "sort_by":       (
        "list — fields to sort/group by, applied in order as 'Sort by', 'Then by', ... "
        "Replaces any existing sort/group fields on the schedule. Each item can be a plain "
        "string field name (e.g. 'Level'), or a dict for more control: "
        "{'field': 'Level', 'order': 'ascending'|'descending', 'header': bool, "
        "'footer': bool, 'blank_line': bool}. If a sort field isn't already a column, "
        "it is added as a hidden column automatically so it can be sorted/grouped on. "
        "Omit to leave existing sorting unchanged."
    ),
}
EXAMPLE = {
    "action": "modify_schedule",
    "params": {
        "schedule_name": "Rooms Schedule",
        "itemize": True,
        "sort_by": [{"field": "Level", "order": "ascending", "header": True}],
    },
}

# Fix M8: aliases synced with create_schedule.py — added missing entries.
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


def _resolve_field(fname, by_bip, by_name, field_bip, eid_int, ElementId):
    """Resolve a user-supplied field name to a Revit SchedulableField.

    Fix M2/M7: now mirrors create_schedule._resolve_schedulable_field with the
    full four-stage resolution: BIP fast path → exact name → alias table → fuzzy.
    Deterministic tie-breaking via (score, name) sort key.
    Fix X1: by_name is keyed by GetName(doc).lower() (built in execute()).
    """
    fl = fname.lower()

    # ── 1. BuiltInParameter fast path ────────────────────────────────────────
    bip = field_bip.get(fl)
    if bip is not None:
        try:
            sf = by_bip.get(eid_int(ElementId(bip)))
            if sf is not None:
                return sf
        except Exception:
            pass

    # ── 2. Exact display-name match ──────────────────────────────────────────
    sf = by_name.get(fl)
    if sf is not None:
        return sf

    # ── 3. Alias table ───────────────────────────────────────────────────────
    for alias in _FIELD_ALIASES.get(fl, []):
        sf = by_name.get(alias)
        if sf is not None:
            return sf

    # ── 4. Scored fuzzy match ────────────────────────────────────────────────
    candidates = []
    for n, s in by_name.items():
        if fl not in n and n not in fl:
            continue
        penalty_colon  = 1000 if ":" in n else 0
        penalty_length = len(n)
        is_whole_word  = (
            n == fl
            or n.startswith(fl + " ")
            or n.endswith(" " + fl)
        )
        bonus_word = -50 if is_whole_word else 0
        score = penalty_colon + penalty_length + bonus_word
        candidates.append((score, n, s))
    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]))
        return candidates[0][2]

    return None


def execute(params, doc, uidoc, resolve_category, get_field_bip, eid_int, **_kwargs):
    # Fix M2: resolve_category, get_field_bip, eid_int now injected so
    # _resolve_field has the same BIP-keyed fast path as create_schedule.
    from Autodesk.Revit.DB import (
        FilteredElementCollector, ViewSchedule, ScheduleFieldType,
        Transaction, ElementId, ScheduleSortGroupField, ScheduleSortOrder
    )

    if not doc:
        return "No document open."

    sched_name = params.get("schedule_name", "").strip()
    add_fields = params.get("fields", []) or []
    rm_fields  = params.get("remove_fields", []) or []
    with_count = params.get("with_count", False)
    itemize    = params.get("itemize", None)   # None = leave unchanged
    sort_by    = params.get("sort_by", None)   # None = leave unchanged

    # Infer schedule from active view when name is omitted.
    if not sched_name:
        try:
            av = uidoc.ActiveView if uidoc else None
            if av is not None and av.ViewType.ToString() == "Schedule":
                sched_name = av.Name
        except Exception:
            pass
    if not sched_name:
        return ("Missing required parameter: schedule_name. "
                "Open a schedule view first or provide the schedule name.")
    if not add_fields and not rm_fields and not with_count and itemize is None and not sort_by:
        return "Nothing to do — provide 'fields', 'remove_fields', 'with_count', 'itemize', or 'sort_by'."

    # ── Find the schedule ─────────────────────────────────────────────────────
    sched      = None
    all_scheds = []
    for s in FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements():
        try:
            if s.IsTemplate:
                continue
            all_scheds.append(s.Name)
            if s.Name == sched_name:
                sched = s
                break
        except Exception:
            continue

    # Fuzzy fallback
    if sched is None:
        sl = sched_name.lower()
        for s in FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements():
            try:
                if s.IsTemplate:
                    continue
                if sl in s.Name.lower():
                    sched = s
                    break
            except Exception:
                continue

    if sched is None:
        hint = ", ".join(sorted(set(all_scheds))[:15]) if all_scheds else "none"
        return ("Schedule '" + sched_name + "' not found. "
                "Available schedules: " + hint + ".")

    defn = sched.Definition

    # ── Build lookup of schedulable fields ────────────────────────────────────
    # Fix C1/X1: each entry individually guarded; GetName(doc) for localised names.
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

    field_bip = get_field_bip()

    # ── Build lookup of already-added fields (by display name -> ScheduleField) ──
    # Fix X1: use GetName(doc) for the added-column display name.
    def _refresh_existing():
        ef = {}
        for i in range(defn.GetFieldCount()):
            try:
                f = defn.GetField(i)
                ef[f.GetName(doc).lower()] = f
            except Exception:
                pass
        return ef

    existing_fields      = _refresh_existing()
    existing_field_names = set(existing_fields.keys())

    # ── Apply changes in a transaction ────────────────────────────────────────
    tx = Transaction(doc, "Chat: Modify Schedule")
    tx.Start()
    try:
        added   = []
        skipped = []

        # ── Add fields ────────────────────────────────────────────────────────
        for fname in add_fields:
            fl = fname.lower()

            if fl == "count":
                if "count" in existing_field_names:
                    skipped.append("Count(already present)")
                    continue
                csf = [sf for sf in defn.GetSchedulableFields()
                       if sf.FieldType == ScheduleFieldType.Count]
                if csf:
                    added_f = defn.AddField(csf[0])
                    added.append("Count")
                    existing_fields["count"] = added_f
                    existing_field_names.add("count")
                else:
                    skipped.append("Count(not available)")
                continue

            if fl in existing_field_names:
                skipped.append(fname + "(already present)")
                continue

            # Check aliases — the field may already exist under Revit's display name.
            already = False
            for alias in _FIELD_ALIASES.get(fl, []):
                if alias in existing_field_names:
                    skipped.append(fname + "(already present as '" + alias + "')")
                    already = True
                    break
            if already:
                continue

            sf = _resolve_field(fname, by_bip, by_name, field_bip, eid_int, ElementId)
            if sf:
                try:
                    added_f = defn.AddField(sf)
                    added.append(fname)
                    existing_fields[fl] = added_f
                    existing_field_names.add(fl)
                except Exception as fe:
                    skipped.append(fname + "(" + str(fe) + ")")
            else:
                skipped.append(fname + "(not found)")

        # ── Count column via with_count flag ──────────────────────────────────
        if with_count and "count" not in existing_field_names:
            csf = [sf for sf in defn.GetSchedulableFields()
                   if sf.FieldType == ScheduleFieldType.Count]
            if csf:
                added_f = defn.AddField(csf[0])
                added.append("Count")
                existing_fields["count"] = added_f
                existing_field_names.add("count")

        # ── Itemize toggle ────────────────────────────────────────────────────
        itemize_msg = ""
        if itemize is not None:
            was_itemized = defn.IsItemized
            defn.IsItemized = bool(itemize)
            if bool(itemize) != was_itemized:
                itemize_msg = ("Switched to itemized (every instance)."
                               if itemize else "Switched to grouped mode.")
            else:
                itemize_msg = ("Already itemized (every instance)."
                               if itemize else "Already in grouped mode.")

        # ── Remove fields ─────────────────────────────────────────────────────
        # Fix M1: collect FieldIds first, then remove by ID — avoids index-shift
        # corruption that occurs when removing while iterating by index.
        removed    = []
        rm_skipped = []
        for fname in rm_fields:
            fl = fname.lower()
            # Collect all candidate FieldIds matching this name (exact + aliases).
            target_ids = []
            for i in range(defn.GetFieldCount()):
                try:
                    sf = defn.GetField(i)
                    # Fix X1: GetName(doc) for comparison.
                    sn = sf.GetName(doc).lower()
                    if sn == fl or sn in _FIELD_ALIASES.get(fl, []):
                        target_ids.append(sf.FieldId)
                except Exception:
                    continue

            if not target_ids:
                rm_skipped.append(fname + "(not in schedule)")
                continue

            for fid in target_ids:
                try:
                    defn.RemoveField(fid)
                except Exception:
                    pass
            removed.append(fname)
            existing_field_names.discard(fl)
            existing_fields.pop(fl, None)

        # ── Sorting / grouping ───────────────────────────────────────────────
        # Fix M3: refresh existing_fields after add/remove so hidden sort-only
        # fields added above are visible to the sort resolver.
        sorted_applied = []
        sort_skipped   = []
        if sort_by:
            existing_fields = _refresh_existing()

            # Fix X2: preserve grand-total and blank-line-after-last-group flags
            # before clearing sort/group fields, then restore after.
            grand_total      = None
            blank_after_last = None
            try:
                grand_total = defn.ShowGrandTotal
            except Exception:
                pass
            try:
                blank_after_last = defn.ShowBlankLineAfterLastGroup
            except Exception:
                pass

            # Replace existing sort/group fields entirely.
            try:
                for existing_sort in list(defn.GetSortGroupFields()):
                    defn.RemoveSortGroupField(existing_sort)
            except Exception:
                pass

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

                sched_field = existing_fields.get(sl)
                # Check aliases against already-added fields.
                if sched_field is None:
                    for alias in _FIELD_ALIASES.get(sl, []):
                        sched_field = existing_fields.get(alias)
                        if sched_field is not None:
                            break

                if sched_field is None:
                    # Not a column yet — resolve and add hidden so it can be sorted.
                    sf = _resolve_field(sfield, by_bip, by_name, field_bip, eid_int, ElementId)
                    if sf is None:
                        sort_skipped.append(sfield + "(not found)")
                        continue
                    try:
                        sched_field = defn.AddField(sf)
                        try:
                            sched_field.IsHidden = True
                        except Exception:
                            pass
                        existing_fields[sl] = sched_field
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

            # Fix X2: restore preserved definition-level flags.
            if grand_total is not None:
                try:
                    defn.ShowGrandTotal = grand_total
                except Exception:
                    pass
            if blank_after_last is not None:
                try:
                    defn.ShowBlankLineAfterLastGroup = blank_after_last
                except Exception:
                    pass

        tx.Commit()

        # Fix M5: guard against uidoc being None (non-UI / batch contexts).
        if uidoc is not None:
            try:
                uidoc.ActiveView = sched
            except Exception:
                pass

        # ── Build response message ────────────────────────────────────────────
        parts = ["Schedule '" + sched.Name + "' updated."]
        if itemize_msg:
            parts.append(itemize_msg)
        if added:
            parts.append("Added: " + ", ".join(added) + ".")
        if removed:
            parts.append("Removed: " + ", ".join(removed) + ".")
        if skipped:
            parts.append("Skipped: " + ", ".join(skipped) + ".")
            if any("not found" in s for s in skipped):
                available = sorted(by_name.keys())[:20]
                parts.append("Available fields include: " + ", ".join(available) + ".")
        if rm_skipped:
            parts.append("Could not remove: " + ", ".join(rm_skipped) + ".")
        if sorted_applied:
            parts.append("Sorted by: " + ", ".join(sorted_applied) + ".")
        if sort_skipped:
            parts.append("Sort fields skipped: " + ", ".join(sort_skipped) + ".")
        if (not added and not removed and not itemize_msg and not skipped
                and not rm_skipped and not sorted_applied and not sort_skipped):
            parts.append("No changes were needed.")
        return " ".join(parts)

    except Exception as e:
        try:
            if tx.HasStarted():
                tx.RollBack()
        except Exception:
            pass
        return "Failed: " + str(e)
