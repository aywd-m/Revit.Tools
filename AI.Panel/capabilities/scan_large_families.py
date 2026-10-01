# -*- coding: utf-8 -*-
# capabilities/scan_large_families.py
# Scans the model for loadable families above a size threshold,
# stamps Family Size (MB) / Family EID project parameters on every instance,
# and creates the _LARGE_FAMILY_SIZE schedule.

ACTION_NAME = "scan_large_families"

DESCRIPTION = (
    "Scan every loadable family in the model and report which ones exceed a "
    "size threshold (default 2 MB). "
    "Stamps 'Family Size (MB)' and 'Family EID' project parameters on all "
    "instances, then creates or refreshes the _LARGE_FAMILY_SIZE schedule. "
    "Optional params: "
    "threshold_mb (number, default 2.0), "
    "category (string, default 'All' — pass a Revit family category name to "
    "limit the scan, e.g. 'Furniture' or 'Doors'), "
    "export_pathless (boolean, default false — set true to open and export "
    "families that have no on-disk path so their size can be measured; this "
    "blocks the UI thread and can be slow on large models). "
    "Always run without arguments first; only set export_pathless=true when "
    "the user explicitly asks for pathless families to be measured. "
    "There is NO separate export_pathless_families, measure_families, or "
    "scan_families action — all options are params of THIS action. "
    "There is NO 'filter' param — use 'category' to limit scope."
)

PARAMS = {
    "threshold_mb":    "number  — minimum family size in MB to flag (default 2.0)",
    "category":        "string  — family category filter, or 'All' (default 'All')",
    "export_pathless": "boolean — open and export pathless families to measure them (default false)",
}

EXAMPLE = {
    "action": "scan_large_families",
    "params": {
        "threshold_mb":    2.0,
        "category":        "All",
        "export_pathless": False,
    },
}

# ── Module-scope constants (pure Python — safe) ────────────────────────────
_SCHEDULE_NAME    = "_LARGE_FAMILY_SIZE"
_PARAM_NAME       = "Family Size (MB)"
_PARAM_EID        = "Family EID"
_GUID_SIZE        = "7a3c1f2e-4b5d-4e6f-8a9b-0c1d2e3f4a5b"
_GUID_EID         = "9b2d3e4f-5a6b-7c8d-9e0f-1a2b3c4d5e6f"
_CACHE_TTL        = 86400   # seconds — 24 h
_BATCH_SIZE       = 500
_MAX_PREVIEW      = 20


# ── Helpers ────────────────────────────────────────────────────────────────

def _eid_int(eid):
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def _model_mtime(doc):
    import os as _os
    try:
        path = doc.PathName
        if path and _os.path.exists(path):
            return _os.path.getmtime(path)
    except Exception:
        pass
    return 0.0


# ── Step 1 — collect family sizes ─────────────────────────────────────────

def _collect_sizes(doc, threshold_mb, category_filter, export_pathless, eid_int_fn):
    import os as _os, tempfile as _tmp, time as _time
    from Autodesk.Revit.DB import (
        FilteredElementCollector, Family, FamilySymbol, SaveAsOptions
    )

    family_sizes  = {}   # fid_int -> float MB
    family_names  = {}   # fid_int -> str
    family_objs   = {}   # fid_int -> Family
    pathless_fids = []
    skipped       = []   # [(name, reason)]
    t0            = _time.time()
    model_mt      = _model_mtime(doc)

    for fam in FilteredElementCollector(doc).OfClass(Family):
        try:
            if fam.IsInPlace:
                continue
            sym_ids = list(fam.GetFamilySymbolIds())
            if not sym_ids:
                continue
            if not isinstance(doc.GetElement(sym_ids[0]), FamilySymbol):
                continue
            if category_filter and category_filter.lower() != "all":
                cat = fam.FamilyCategory
                if cat is None or cat.Name.lower() != category_filter.lower():
                    continue
        except Exception:
            continue

        fid = eid_int_fn(fam.Id)
        family_names[fid] = fam.Name
        family_objs[fid]  = fam

        try:
            path = None
            try:
                raw = fam.GetOriginalFilePath()
                if raw:
                    path = raw.rstrip("\x00").strip()
            except Exception:
                pass

            if path and _os.path.exists(path):
                family_sizes[fid] = _os.path.getsize(path) / 1048576.0
            else:
                pathless_fids.append(fid)
        except Exception as ex:
            skipped.append((fam.Name, "unexpected: " + str(ex)))

    # ── Pathless families ──────────────────────────────────────────────────
    for fid in pathless_fids:
        tmp_path = _os.path.join(
            _tmp.gettempdir(), "kidzink_sz_%d.rfa" % fid)

        # Check cache first
        if _os.path.exists(tmp_path):
            mt  = _os.path.getmtime(tmp_path)
            age = _time.time() - mt
            if age < _CACHE_TTL and not (model_mt > 0.0 and model_mt > mt):
                try:
                    family_sizes[fid] = _os.path.getsize(tmp_path) / 1048576.0
                    continue
                except Exception:
                    pass
            # Cache stale — remove
            try:
                _os.remove(tmp_path)
            except Exception:
                pass

        if not export_pathless:
            skipped.append((family_names[fid],
                            "no on-disk path (set export_pathless=true to measure)"))
            continue

        # Export via EditFamily + SaveAs
        try:
            fam_obj = family_objs.get(fid)
            if fam_obj is None:
                skipped.append((family_names[fid], "not found on re-query"))
                continue
            fam_doc = doc.EditFamily(fam_obj)
            if fam_doc is None:
                skipped.append((family_names[fid], "EditFamily returned None"))
                continue
            opts = SaveAsOptions()
            opts.OverwriteExistingFile = True
            fam_doc.SaveAs(tmp_path, opts)
            fam_doc.Close(False)
            if _os.path.exists(tmp_path):
                family_sizes[fid] = _os.path.getsize(tmp_path) / 1048576.0
            else:
                skipped.append((family_names[fid], "export produced no file"))
        except Exception as ex:
            skipped.append((family_names[fid], "export error: " + str(ex)))

    large_fids = {fid for fid, sz in family_sizes.items() if sz >= threshold_mb}
    return family_sizes, family_names, large_fids, skipped, _time.time() - t0


# ── Step 2 — ensure project parameters exist ──────────────────────────────

def _write_sp_file(path, params_def):
    lines = [
        "# This is a Revit shared parameter file.\n",
        "# Do not edit manually!\n",
        "*META\tVERSION\tMINVERSION\n",
        "META\t2\t1\n",
        "*GROUP\tID\tNAME\n",
        "GROUP\t1\tKidzink\n",
        "*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\t"
        "DESCRIPTION\tUSERMODIFIABLE\tHIDEWHENNOVALUE\n",
    ]
    for guid_str, name, datatype in params_def:
        lines.append("PARAM\t%s\t%s\t%s\t\t1\t1\t\t1\t0\n"
                     % (guid_str, name, datatype))
    content = "".join(lines)
    with open(path, "wb") as f:
        f.write(content.encode("utf-8"))


def _ensure_params(doc):
    import os as _os, tempfile as _tmp
    from Autodesk.Revit.DB import Transaction, CategorySet

    existing = set()
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        existing.add(it.Key.Name)

    needed = []
    if _PARAM_NAME not in existing:
        needed.append((_GUID_SIZE, _PARAM_NAME, "NUMBER"))
    if _PARAM_EID not in existing:
        needed.append((_GUID_EID,  _PARAM_EID,  "INTEGER"))
    if not needed:
        return []

    sp_file_path = _os.path.join(_tmp.gettempdir(), "kidzink_largefam_sp.txt")
    prev_sp = doc.Application.SharedParametersFilename
    errors  = []
    try:
        _write_sp_file(sp_file_path, needed)
        tx = Transaction(doc, "Koda: Add Large Family Params")
        tx.Start()
        try:
            cat_set = CategorySet()
            for cat in doc.Settings.Categories:
                try:
                    if cat.AllowsBoundParameters:
                        cat_set.Insert(cat)
                except Exception:
                    pass
            binding = doc.Application.Create.NewInstanceBinding(cat_set)
            doc.Application.SharedParametersFilename = sp_file_path
            spf = doc.Application.OpenSharedParameterFile()
            grp = spf.Groups.get_Item("Kidzink")
            for _, name, _ in needed:
                try:
                    ext_def = grp.Definitions.get_Item(name)
                    doc.ParameterBindings.Insert(ext_def, binding)
                except Exception as ex:
                    errors.append(name + ": " + str(ex))
            tx.Commit()
        except Exception as ex:
            try:
                tx.RollBack()
            except Exception:
                pass
            errors.append("param transaction failed: " + str(ex))
    except Exception as ex:
        errors.append("sp file error: " + str(ex))
    finally:
        try:
            doc.Application.SharedParametersFilename = prev_sp if prev_sp else ""
        except Exception:
            pass
        try:
            if _os.path.exists(sp_file_path):
                _os.remove(sp_file_path)
        except Exception:
            pass
    return errors


# ── Step 3 — stamp parameters ─────────────────────────────────────────────

def _resolve_param_defs(doc):
    target = {
        _GUID_SIZE.lower(): "size",
        _GUID_EID.lower():  "eid",
    }
    result = {"size": None, "eid": None}
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        defn = it.Key
        try:
            g = str(defn.GUID).lower()
            if g in target:
                result[target[g]] = defn
        except Exception:
            pass
    return result["size"], result["eid"]


def _get_param(inst, defn, fallback_name):
    if defn is not None:
        try:
            p = inst.get_Parameter(defn)
            if p is not None:
                return p
        except Exception:
            pass
    return inst.LookupParameter(fallback_name)


def _stamp_params(doc, large_fids, family_sizes, eid_int_fn):
    from Autodesk.Revit.DB import FilteredElementCollector, FamilyInstance, Transaction

    defn_size, defn_eid = _resolve_param_defs(doc)
    all_insts = list(
        FilteredElementCollector(doc)
        .OfClass(FamilyInstance)
        .WhereElementIsNotElementType()
    )

    # Pass A — clear
    cleared = 0
    for i in range(0, max(1, len(all_insts)), _BATCH_SIZE):
        batch = all_insts[i: i + _BATCH_SIZE]
        tx = Transaction(doc, "Koda: Clear Family Size")
        tx.Start()
        try:
            for inst in batch:
                try:
                    p = _get_param(inst, defn_size, _PARAM_NAME)
                    if p and not p.IsReadOnly:
                        p.Set(0.0)
                        cleared += 1
                    p2 = _get_param(inst, defn_eid, _PARAM_EID)
                    if p2 and not p2.IsReadOnly:
                        p2.Set(-1)
                except Exception:
                    pass
            tx.Commit()
        except Exception as ex:
            try:
                tx.RollBack()
            except Exception:
                pass
            return 0, cleared, "clear transaction failed: " + str(ex)

    # Pass B — stamp large ones
    large_insts = []
    for inst in all_insts:
        try:
            sym = inst.Symbol
            if sym and sym.Family and eid_int_fn(sym.Family.Id) in large_fids:
                large_insts.append(inst)
        except Exception:
            pass

    stamped = 0
    for i in range(0, max(1, len(large_insts)), _BATCH_SIZE):
        batch = large_insts[i: i + _BATCH_SIZE]
        tx = Transaction(doc, "Koda: Stamp Family Size")
        tx.Start()
        try:
            for inst in batch:
                try:
                    fid = eid_int_fn(inst.Symbol.Family.Id)
                    ok  = False
                    p   = _get_param(inst, defn_size, _PARAM_NAME)
                    if p and not p.IsReadOnly:
                        p.Set(family_sizes[fid])
                        ok = True
                    p2  = _get_param(inst, defn_eid, _PARAM_EID)
                    if p2 and not p2.IsReadOnly:
                        p2.Set(eid_int_fn(inst.Id))
                        ok = True
                    if ok:
                        stamped += 1
                except Exception:
                    pass
            tx.Commit()
        except Exception as ex:
            try:
                tx.RollBack()
            except Exception:
                pass
            return stamped, cleared, "stamp transaction failed: " + str(ex)

    return stamped, cleared, None


# ── Step 4 — delete old schedule ──────────────────────────────────────────

def _delete_schedule(doc, uidoc, sched_name):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, ViewSchedule, ScheduleSheetInstance,
        View, ViewType, Transaction
    )

    existing = [v for v in FilteredElementCollector(doc).OfClass(ViewSchedule)
                if v.Name == sched_name
                or v.Name == _SCHEDULE_NAME
                or v.Name.startswith(_SCHEDULE_NAME + "_")]
    if not existing:
        return

    existing_ids = {v.Id for v in existing}

    # Switch away from the schedule if it is the active view
    try:
        _active_view = None
        try:
            if uidoc:
                _active_view = uidoc.ActiveView
        except Exception:
            pass
        if _active_view is not None and _active_view.Id in existing_ids:
            fallback = next(
                (v for v in FilteredElementCollector(doc).OfClass(View)
                 if not v.IsTemplate
                 and v.ViewType not in (ViewType.Schedule, ViewType.DrawingSheet)
                 and v.CanBePrinted),
                None)
            if fallback:
                try:
                    uidoc.RequestViewChange(fallback)
                except AttributeError:
                    uidoc.ActiveView = fallback
    except Exception:
        pass

    ssi_map = {}
    for ssi in FilteredElementCollector(doc).OfClass(ScheduleSheetInstance):
        try:
            if ssi.ScheduleId in existing_ids:
                ssi_map.setdefault(ssi.ScheduleId, []).append(ssi.Id)
        except Exception:
            pass

    tx = Transaction(doc, "Koda: Delete Old Schedule")
    tx.Start()
    try:
        for v in existing:
            for ssi_id in ssi_map.get(v.Id, []):
                try:
                    doc.Delete(ssi_id)
                except Exception:
                    pass
            try:
                doc.Delete(v.Id)
            except Exception:
                pass
        tx.Commit()
    except Exception as ex:
        try:
            tx.RollBack()
        except Exception:
            pass


# ── Step 5 — create schedule ──────────────────────────────────────────────

def _create_schedule(doc, uidoc, sched_name, threshold_mb):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, ViewSchedule, Transaction,
        ElementId, BuiltInCategory,
        ScheduleFilter, ScheduleFilterType,
        ScheduleSortGroupField, ScheduleSortOrder,
    )

    tx = Transaction(doc, "Koda: Create " + sched_name)
    tx.Start()
    try:
        # Rename any surviving same-name schedule so we can claim the name
        _TEMP = "__kzk_old_%s__" % sched_name
        stale = []
        for v in FilteredElementCollector(doc).OfClass(ViewSchedule):
            if v.Name == sched_name:
                try:
                    v.Name = _TEMP
                    stale.append(v.Id)
                except Exception:
                    pass

        sched      = ViewSchedule.CreateSchedule(doc, ElementId(BuiltInCategory.INVALID))
        sched.Name = sched_name
        defn       = sched.Definition

        for sid in stale:
            try:
                doc.Delete(sid)
            except Exception:
                pass

        try:
            defn.IsItemized = False
        except Exception:
            pass

        # Field map
        fm = {}
        for sf in defn.GetSchedulableFields():
            try:
                name = sf.GetName(doc)
                if name not in fm:
                    fm[name] = sf
            except Exception:
                pass

        def _add(sf, label=None):
            if sf is None:
                return None
            try:
                fld = defn.AddField(sf)
                if label:
                    fld.ColumnHeading = label
                return fld
            except Exception:
                return None

        def _sort(fld, header=False, blank=False, desc=False):
            if fld is None:
                return
            try:
                order = ScheduleSortOrder.Descending if desc else ScheduleSortOrder.Ascending
                sg = ScheduleSortGroupField(fld.FieldId, order)
                sg.ShowHeader    = header
                sg.ShowFooter    = False
                sg.ShowBlankLine = blank
                defn.AddSortGroupField(sg)
            except Exception:
                pass

        fld_level  = _add(fm.get("Level"))
        fld_cat    = _add(fm.get("Category"),     "Category")
        fld_family = _add(fm.get("Family"),       "Family Name")
        fld_size   = _add(fm.get(_PARAM_NAME),    "Family Size (MB)")
        _add(fm.get(_PARAM_EID),                  "Element ID")
        _add(fm.get("Room: Name"),                "Room Name")
        _add(fm.get("Room: Number"),              "Room Number")
        _add(fm.get("Count"),                     "Count")

        if fld_level:
            try:
                fld_level.IsHidden = True
            except Exception:
                pass

        if fld_size:
            try:
                defn.AddFilter(ScheduleFilter(
                    fld_size.FieldId,
                    ScheduleFilterType.GreaterThanOrEqual,
                    float(threshold_mb)
                ))
            except Exception:
                pass

        _sort(fld_size,  desc=True)
        _sort(fld_level, header=True, blank=True)
        _sort(fld_family)

        tx.Commit()

        try:
            if uidoc:
                uidoc.ActiveView = sched
        except Exception:
            pass

    except Exception as ex:
        try:
            tx.RollBack()
        except Exception:
            pass
        return str(ex)
    return None


# ── Main execute ───────────────────────────────────────────────────────────

def execute(params, doc, uidoc, eid_int, **_kwargs):
    import time as _time

    if not doc:
        return "No document open."

    threshold_mb    = float(params.get("threshold_mb", 2.0) or 2.0)
    category_filter = (params.get("category") or "All").strip()
    export_pathless = bool(params.get("export_pathless", False))

    t0 = _time.time()

    # 1 — sizes
    family_sizes, family_names, large_fids, skipped, dt_scan = _collect_sizes(
        doc, threshold_mb, category_filter, export_pathless, eid_int)

    if not large_fids and not family_names:
        return "No loadable families found in the model."

    # 2 — params
    param_errors = _ensure_params(doc)

    # 3 — stamp (always, to clear stale values)
    stamped, cleared, stamp_err = _stamp_params(doc, large_fids, family_sizes, eid_int)

    # 4 + 5 — schedule
    sched_name = "%s_%s" % (_SCHEDULE_NAME, category_filter or "All")
    _delete_schedule(doc, uidoc, sched_name)
    sched_err = _create_schedule(doc, uidoc, sched_name, threshold_mb)

    dt_total = _time.time() - t0

    # ── Build summary ──────────────────────────────────────────────────────
    lines = [
        "Large family scan complete. Threshold: %.1f MB. Scope: %s."
        % (threshold_mb, category_filter),
        "Families scanned: %d. Large (>= %.1f MB): %d."
        % (len(family_names), threshold_mb, len(large_fids)),
        "Instances cleared: %d. Instances stamped: %d."
        % (cleared, stamped),
        "Schedule '%s' created." % sched_name,
        "Total time: %.1f s (scan %.1f s)." % (dt_total, dt_scan),
    ]

    if large_fids:
        top = sorted(
            [(family_sizes[fid], family_names[fid])
             for fid in large_fids if fid in family_sizes],
            reverse=True
        )[:_MAX_PREVIEW]
        lines.append("")
        lines.append("Top large families:")
        for sz, name in top:
            lines.append("  %.2f MB  %s" % (sz, name))

    if skipped:
        lines.append("")
        lines.append("Could not measure (%d):" % len(skipped))
        for name, reason in skipped[:10]:
            lines.append("  " + name + " — " + reason)
        if len(skipped) > 10:
            lines.append("  ... and %d more." % (len(skipped) - 10))

    if param_errors:
        lines.append("Parameter errors: " + "; ".join(param_errors))
    if stamp_err:
        lines.append("Stamp error: " + stamp_err)
    if sched_err:
        lines.append("Schedule error: " + sched_err)

    return "\n".join(lines)
