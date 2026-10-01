# -*- coding: utf-8 -*-
# capabilities/isolate_elements.py
# Kidzink Koda capability — Isolate Elements (category / in-place / file size)
# (c) Archie C. Manza 2026
#
# Modes
# -----
#   category  : isolate all elements of a named category   (default)
#   inplace   : isolate all in-place family instances
#   filesize  : isolate families whose .rfa meets a size condition
#
# All isolation uses Revit's native Temporary Hide/Isolate mechanism
# (View.IsolateElementsTemporary) — resettable from the View Control Bar.
#
# View routing
# ------------
#   Current view is used when it supports THI (FloorPlan, CeilingPlan,
#   Elevation, Section, ThreeD, Detail, DraftingView).
#   For any other view type (Schedule, Legend, Sheet, Undefined) the tool
#   switches to an existing non-template 3D view, or creates one.

import os
import re

from Autodesk.Revit.DB import (
    FilteredElementCollector, View3D, ViewFamily, ViewType,
    Transaction, ElementId, Family, FamilyInstance
)
from System.Collections.Generic import List

# ── Plugin interface ──────────────────────────────────────────────────────────

ACTION_NAME = "isolate_elements"

DESCRIPTION = (
    "Temporarily isolate elements in the active view using Revit's native "
    "Temporary Hide/Isolate. Four modes: "
    "'category' isolates a named category (e.g. planting, walls, doors); "
    "'inplace' isolates all in-place family instances; "
    "'filesize' isolates families whose .rfa file meets a size condition (e.g. '>= 5mb'); "
    "'parameter' isolates elements where a parameter matches a condition — use this when "
    "user says 'isolate elements with [param] = [value]', 'isolate where [param] contains [value]', "
    "'show only elements where [param] equals [value]', or similar parameter-filter phrasing. "
    "Params: mode (category|inplace|filesize|parameter), "
    "category (string, for mode=category or optionally mode=parameter to pre-filter by category), "
    "size_condition (string, for mode=filesize e.g. '>= 5mb'), "
    "field (string, for mode=parameter — the parameter name e.g. 'Comments', 'Mark', 'Level'), "
    "condition (string, for mode=parameter — one of: equals, not_equal, contains, "
    "does_not_contain, greater_than, less_than, greater_or_equal, less_or_equal), "
    "value (string, for mode=parameter — the value to compare against). "
    "NEVER use mode=category when the user specifies a parameter condition — use mode=parameter instead. "
    "NEVER pass element_id as a param — this action works on parameter values, not element IDs."
)

EXAMPLE = {
    "action": "isolate_elements",
    "params": {"mode": "category", "category": "planting"}
}
EXAMPLE_2 = {
    "action": "isolate_elements",
    "params": {
        "mode":      "parameter",
        "category":  "rooms",
        "field":     "Comments",
        "condition": "equals",
        "value":     "X",
    }
}
# 'isolate element with param comment = X' — no category, any category → mode=parameter, no category key
EXAMPLE_3 = {
    "action": "isolate_elements",
    "params": {
        "mode":      "parameter",
        "field":     "Comments",
        "condition": "equals",
        "value":     "X",
    }
}
# 'isolate all elements where mark contains A' — cross-category parameter filter
EXAMPLE_4 = {
    "action": "isolate_elements",
    "params": {
        "mode":      "parameter",
        "field":     "Mark",
        "condition": "contains",
        "value":     "A",
    }
}

# ── THI-capable view types ────────────────────────────────────────────────────

_THI_VIEW_TYPES = frozenset([
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.Elevation,
    ViewType.Section,
    ViewType.ThreeD,
    ViewType.Detail,
    ViewType.DraftingView,
    ViewType.AreaPlan,
    ViewType.EngineeringPlan,
])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_thi_capable(view):
    """Return True if the view supports Temporary Hide/Isolate."""
    try:
        return view.ViewType in _THI_VIEW_TYPES
    except Exception:
        return False


def _needs_3d(view):
    """Return True if the view is non-isolatable and we must route to 3D."""
    try:
        return view.ViewType not in _THI_VIEW_TYPES
    except Exception:
        return True


def _get_or_create_3d(doc, uidoc):
    """
    Return (view, switched) where view is a usable non-template 3D view
    and switched=True means the active view was changed.
    """
    # Try to find an existing non-template 3D view
    try:
        views3d = (FilteredElementCollector(doc)
                   .OfClass(View3D)
                   .WhereElementIsNotElementType()
                   .ToElements())
        for v in views3d:
            if not v.IsTemplate:
                uidoc.ActiveView = v
                return v, True
    except Exception:
        pass

    # Create one
    try:
        vft = doc.GetDefaultViewFamilyType(ViewFamily.ThreeDimensional)
        if vft is None:
            return None, False
        username = os.environ.get("USERNAME", "User")
        tx_v = Transaction(doc, "Koda: Create 3D View")
        tx_v.Start()
        try:
            v3d = View3D.CreateIsometric(doc, vft.Id)
            v3d.Name = "Koda 3D - {0}".format(username)
            tx_v.Commit()
            uidoc.ActiveView = v3d
            return v3d, True
        except Exception as ve:
            tx_v.RollBack()
            return None, False
    except Exception:
        return None, False


def _parse_size(text):
    """
    Parse a natural-language size condition.
    Returns (op, bytes) or (None, None).
    Examples: '>= 5mb'  '< 500kb'  '2gb'
    """
    text = (text or "").lower().strip()
    m = re.search(r'([<>]=?|=)?\s*([\d.]+)\s*(mb|kb|gb|b)', text, re.IGNORECASE)
    if not m:
        return None, None
    op    = m.group(1) if m.group(1) else ">="
    value = float(m.group(2))
    unit  = m.group(3).lower()
    mult  = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}.get(unit, 1)
    return op, value * mult


def _meets_size(size_bytes, op, threshold):
    if op == ">=": return size_bytes >= threshold
    if op == ">":  return size_bytes >  threshold
    if op == "<=": return size_bytes <= threshold
    if op == "<":  return size_bytes <  threshold
    if op == "=":  return abs(size_bytes - threshold) < 1
    return size_bytes >= threshold


def _apply_thi(view, ids):
    """Apply IsolateElementsTemporary. Returns (ok, error_str)."""
    try:
        net_ids = List[ElementId](ids)
        view.IsolateElementsTemporary(net_ids)
        return True, None
    except Exception as e:
        return False, str(e)


# ── Mode implementations ──────────────────────────────────────────────────────

def _isolate_category(params, doc, uidoc, resolve_category):
    cat_name = (params.get("category") or "").strip()
    if not cat_name:
        return "No category specified. Example: {\"mode\": \"category\", \"category\": \"planting\"}"

    bic = resolve_category(cat_name)
    if bic is None:
        return (
            "Unknown category: '{0}'. "
            "Try: planting, walls, doors, windows, floors, ceilings, "
            "furniture, lighting fixtures, mechanical equipment."
        ).format(cat_name)

    # ── Resolve view ─────────────────────────────────────────────────────────
    switched_msg = ""
    try:
        active_view = uidoc.ActiveView
    except Exception:
        return "Cannot read active view."

    if _needs_3d(active_view):
        view, switched = _get_or_create_3d(doc, uidoc)
        if view is None:
            return "Current view does not support isolation and no 3D view could be found or created."
        switched_msg = " (switched to 3D view '{0}')".format(view.Name)
    else:
        view = active_view

    # ── Collect matching elements ─────────────────────────────────────────────
    try:
        ids = list(
            FilteredElementCollector(doc, view.Id)
            .OfCategory(bic)
            .WhereElementIsNotElementType()
            .ToElementIds()
        )
    except Exception as ce:
        return "Failed to collect '{0}' elements: {1}".format(cat_name, str(ce))

    if not ids:
        return (
            "No '{0}' elements found in view '{1}'{2}. "
            "Check the category is visible and elements exist in this view."
        ).format(cat_name, view.Name, switched_msg)

    # ── Apply THI ─────────────────────────────────────────────────────────────
    tx = Transaction(doc, "Koda: Isolate {0}".format(cat_name.title()))
    tx.Start()
    try:
        ok, err = _apply_thi(view, ids)
        if not ok:
            tx.RollBack()
            return "Isolation failed: " + (err or "unknown error")
        tx.Commit()
    except Exception as te:
        try:
            tx.RollBack()
        except Exception:
            pass
        return "Transaction failed: " + str(te)

    # ── Select ────────────────────────────────────────────────────────────────
    try:
        uidoc.Selection.SetElementIds(List[ElementId](ids))
    except Exception:
        pass
    try:
        uidoc.RefreshActiveView()
    except Exception:
        pass

    return (
        "{0} '{1}' element(s) temporarily isolated in '{2}'{3}. "
        "Reset via View Control Bar → Temporary Hide/Isolate → Reset."
    ).format(len(ids), cat_name, view.Name, switched_msg)


def _isolate_inplace(params, doc, uidoc):
    # ── Resolve view ─────────────────────────────────────────────────────────
    switched_msg = ""
    try:
        active_view = uidoc.ActiveView
    except Exception:
        return "Cannot read active view."

    if _needs_3d(active_view):
        view, switched = _get_or_create_3d(doc, uidoc)
        if view is None:
            return "Current view does not support isolation and no 3D view could be found or created."
        switched_msg = " (switched to 3D view '{0}')".format(view.Name)
    else:
        view = active_view

    # ── Collect in-place instances ────────────────────────────────────────────
    # In-place families: FamilyInstance where instance.Symbol.Family.IsInPlace == True
    # They can belong to ANY category — do not filter by category name.
    ids = []
    try:
        instances = (FilteredElementCollector(doc, view.Id)
                     .OfClass(FamilyInstance)
                     .WhereElementIsNotElementType()
                     .ToElements())
        for inst in instances:
            try:
                fam = inst.Symbol.Family
                if fam is not None and fam.IsInPlace:
                    ids.append(inst.Id)
            except Exception:
                continue
    except Exception as ce:
        return "Failed to collect in-place families: " + str(ce)

    if not ids:
        return (
            "No in-place family instances found in view '{0}'{1}. "
            "In-place families are created with the 'In-Place Family' command "
            "and may belong to any category."
        ).format(view.Name, switched_msg)

    # ── Apply THI ─────────────────────────────────────────────────────────────
    tx = Transaction(doc, "Koda: Isolate In-Place Families")
    tx.Start()
    try:
        ok, err = _apply_thi(view, ids)
        if not ok:
            tx.RollBack()
            return "Isolation failed: " + (err or "unknown error")
        tx.Commit()
    except Exception as te:
        try:
            tx.RollBack()
        except Exception:
            pass
        return "Transaction failed: " + str(te)

    # ── Select ────────────────────────────────────────────────────────────────
    try:
        uidoc.Selection.SetElementIds(List[ElementId](ids))
    except Exception:
        pass
    try:
        uidoc.RefreshActiveView()
    except Exception:
        pass

    # Summarise by category for the user
    cat_counts = {}
    try:
        for eid in ids:
            el = doc.GetElement(eid)
            if el is not None and el.Category is not None:
                cname = el.Category.Name
                cat_counts[cname] = cat_counts.get(cname, 0) + 1
    except Exception:
        pass

    summary = ""
    if cat_counts:
        parts = ["{0} {1}".format(v, k) for k, v in sorted(cat_counts.items())]
        summary = " ({0})".format(", ".join(parts))

    return (
        "{0} in-place family instance(s){1} temporarily isolated in '{2}'{3}. "
        "Reset via View Control Bar → Temporary Hide/Isolate → Reset."
    ).format(len(ids), summary, view.Name, switched_msg)


def _isolate_filesize(params, doc, uidoc):
    size_condition = params.get("size_condition", "").strip()
    if not size_condition:
        return (
            "No size_condition specified. "
            "Example: {\"mode\": \"filesize\", \"size_condition\": \">= 5mb\"}"
        )

    op, threshold = _parse_size(size_condition)
    if op is None:
        return (
            "Could not parse size condition '{0}'. "
            "Use a format like '>= 5mb', '< 500kb', '> 2mb'."
        ).format(size_condition)

    # File-size isolation requires a 3D view — always route there
    switched_msg = ""
    try:
        active_view = uidoc.ActiveView
        is_3d = (active_view.ViewType == ViewType.ThreeD)
    except Exception:
        is_3d = False

    if is_3d:
        view = active_view
    else:
        view, switched = _get_or_create_3d(doc, uidoc)
        if view is None:
            return "Could not find or create a 3D view required for file-size isolation."
        switched_msg = " (switched to 3D view '{0}')".format(view.Name)

    # ── Collect families that meet the size condition ─────────────────────────
    # Build symbol_id -> True map for fast lookup
    matching_sym_ids = set()
    matched_families = []
    try:
        families = (FilteredElementCollector(doc)
                    .OfClass(Family)
                    .ToElements())
        for fam in families:
            try:
                fpath = fam.GetFamilySourceFilePath()
                if not fpath or not os.path.isfile(fpath):
                    continue
                sz = os.path.getsize(fpath)
                if _meets_size(sz, op, threshold):
                    matched_families.append(fam.Name)
                    for sym_id in fam.GetFamilySymbolIds():
                        try:
                            matching_sym_ids.add(sym_id.Value)
                        except AttributeError:
                            matching_sym_ids.add(sym_id.IntegerValue)
            except Exception:
                continue
    except Exception as fe:
        return "Failed to scan families: " + str(fe)

    if not matching_sym_ids:
        return (
            "No families with .rfa file {0} found "
            "(only loadable families with a resolvable file path are checked)."
        ).format(size_condition)

    # ── Collect instances of matching families in the view (single pass) ──────
    ids = []
    try:
        instances = (FilteredElementCollector(doc, view.Id)
                     .OfClass(FamilyInstance)
                     .WhereElementIsNotElementType()
                     .ToElements())
        for inst in instances:
            try:
                try:
                    sym_int = inst.Symbol.Id.Value
                except AttributeError:
                    sym_int = inst.Symbol.Id.IntegerValue
                if sym_int in matching_sym_ids:
                    ids.append(inst.Id)
            except Exception:
                continue
    except Exception as ie:
        return "Failed to collect instances: " + str(ie)

    if not ids:
        return (
            "{0} matching famil{1} found ({2}) but no instances visible "
            "in view '{3}'{4}."
        ).format(
            len(matched_families),
            "y" if len(matched_families) == 1 else "ies",
            ", ".join(matched_families[:5]) + ("..." if len(matched_families) > 5 else ""),
            view.Name,
            switched_msg
        )

    # ── Apply THI ─────────────────────────────────────────────────────────────
    tx = Transaction(doc, "Koda: Isolate by File Size {0}".format(size_condition))
    tx.Start()
    try:
        ok, err = _apply_thi(view, ids)
        if not ok:
            tx.RollBack()
            return "Isolation failed: " + (err or "unknown error")
        tx.Commit()
    except Exception as te:
        try:
            tx.RollBack()
        except Exception:
            pass
        return "Transaction failed: " + str(te)

    # ── Select ────────────────────────────────────────────────────────────────
    try:
        uidoc.Selection.SetElementIds(List[ElementId](ids))
    except Exception:
        pass
    try:
        uidoc.RefreshActiveView()
    except Exception:
        pass

    fam_preview = ", ".join(matched_families[:5])
    if len(matched_families) > 5:
        fam_preview += " +{0} more".format(len(matched_families) - 5)

    return (
        "{0} instance(s) from {1} famil{2} ({3}) temporarily isolated "
        "in '{4}'{5}. "
        "Reset via View Control Bar → Temporary Hide/Isolate → Reset."
    ).format(
        len(ids),
        len(matched_families),
        "y" if len(matched_families) == 1 else "ies",
        fam_preview,
        view.Name,
        switched_msg
    )


# ── Parameter-filter mode ────────────────────────────────────────────────────

_PARAM_COND_MAP = {
    "equals":            lambda a, b: a == b,
    "equal":             lambda a, b: a == b,
    "not_equal":         lambda a, b: a != b,
    "notequal":          lambda a, b: a != b,
    "contains":          lambda a, b: b in a,
    "does_not_contain":  lambda a, b: b not in a,
    "not_contains":      lambda a, b: b not in a,
    "greater_than":      lambda a, b: _num(a) is not None and _num(b) is not None and _num(a) >  _num(b),
    "less_than":         lambda a, b: _num(a) is not None and _num(b) is not None and _num(a) <  _num(b),
    "greater_or_equal":  lambda a, b: _num(a) is not None and _num(b) is not None and _num(a) >= _num(b),
    "less_or_equal":     lambda a, b: _num(a) is not None and _num(b) is not None and _num(a) <= _num(b),
}


def _num(s):
    """Try to parse s as float; return None if not numeric."""
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


def _read_param_str(elem, field_name):
    """
    Read a parameter value from elem as a plain string.
    Tries exact name match first, then case-insensitive, then substring.
    Returns the string value or None if not found / no value.
    """
    fl = field_name.lower()
    best = None
    try:
        for p in elem.Parameters:
            try:
                pname = p.Definition.Name
                if pname.lower() == fl:
                    # exact match — read and return immediately
                    if p.HasValue:
                        v = p.AsValueString() or p.AsString()
                        if v:
                            return v.strip()
                    return None
                if fl in pname.lower() and best is None:
                    best = p
            except Exception:
                continue
    except Exception:
        pass
    if best is not None:
        try:
            if best.HasValue:
                v = best.AsValueString() or best.AsString()
                return v.strip() if v else None
        except Exception:
            pass
    return None


def _isolate_parameter(params, doc, uidoc, resolve_category):
    """Isolate elements where a named parameter matches a condition/value."""
    field_name = (params.get("field") or "").strip()
    condition  = (params.get("condition") or "equals").lower().strip()
    value      = (params.get("value") or "").strip()
    cat_name   = (params.get("category") or "").strip()

    if not field_name:
        return ("Missing required param: field (the parameter name to filter on). "
                "Example: mode=parameter, field=Comments, condition=equals, value=X")
    if not value:
        return "Missing required param: 'value' (the value to compare against)."

    cond_fn = _PARAM_COND_MAP.get(condition)
    if cond_fn is None:
        return ("Unsupported condition '{0}'. Use: ".format(condition)
                + ", ".join(sorted(set(_PARAM_COND_MAP.keys()))))

    # ── Resolve view ─────────────────────────────────────────────────────────
    switched_msg = ""
    try:
        active_view = uidoc.ActiveView
    except Exception:
        return "Cannot read active view."

    if _needs_3d(active_view):
        view, switched = _get_or_create_3d(doc, uidoc)
        if view is None:
            return "Current view does not support isolation and no 3D view could be found."
        switched_msg = " (switched to 3D view '{0}')".format(view.Name)
    else:
        view = active_view

    # ── Collect candidates (optionally pre-filtered by category) ─────────────
    try:
        if cat_name:
            bic = resolve_category(cat_name)
            if bic is not None:
                candidates = list(
                    FilteredElementCollector(doc, view.Id)
                    .OfCategory(bic)
                    .WhereElementIsNotElementType()
                    .ToElements()
                )
            else:
                # Unknown category — fall through to full view scan
                candidates = list(
                    FilteredElementCollector(doc, view.Id)
                    .WhereElementIsNotElementType()
                    .ToElements()
                )
        else:
            candidates = list(
                FilteredElementCollector(doc, view.Id)
                .WhereElementIsNotElementType()
                .ToElements()
            )
    except Exception as ce:
        return "Failed to collect elements: " + str(ce)

    # ── Filter by parameter condition ─────────────────────────────────────────
    matched_ids = []
    for elem in candidates:
        try:
            param_val = _read_param_str(elem, field_name)
            if param_val is None:
                continue
            if cond_fn(param_val, value):
                matched_ids.append(elem.Id)
        except Exception:
            continue

    if not matched_ids:
        scope = ("'{0}' ".format(cat_name) if cat_name else "") + "elements"
        return (
            "No {0} found where '{1}' {2} '{3}' in view '{4}'{5}."
        ).format(scope, field_name, condition, value, view.Name, switched_msg)

    # ── Apply THI ─────────────────────────────────────────────────────────────
    tx = Transaction(doc, "Koda: Isolate by Parameter")
    tx.Start()
    try:
        ok, err = _apply_thi(view, matched_ids)
        if not ok:
            tx.RollBack()
            return "Isolation failed: " + (err or "unknown error")
        tx.Commit()
    except Exception as te:
        try:
            tx.RollBack()
        except Exception:
            pass
        return "Transaction failed: " + str(te)

    # ── Select ────────────────────────────────────────────────────────────────
    try:
        uidoc.Selection.SetElementIds(List[ElementId](matched_ids))
    except Exception:
        pass
    try:
        uidoc.RefreshActiveView()
    except Exception:
        pass

    scope = ("'{0}' ".format(cat_name) if cat_name else "")
    return (
        "{0} {1}element(s) where '{2}' {3} '{4}' temporarily isolated "
        "in '{5}'{6}. "
        "Reset via View Control Bar -> Temporary Hide/Isolate -> Reset."
    ).format(len(matched_ids), scope, field_name, condition, value, view.Name, switched_msg)


# ── Entry point ───────────────────────────────────────────────────────────────

_BOGUS_CATEGORIES = frozenset(["all", "any", "every", "everything", "elements",
                                "all elements", "any elements", "selection", ""])


def execute(params, doc, uidoc, resolve_category, get_field_bip, eid_int, **_kwargs):
    if not doc or not uidoc:
        return "No document open."

    mode     = (params.get("mode") or "category").lower().strip()
    cat_raw  = (params.get("category") or "").lower().strip()
    has_field = bool((params.get("field") or "").strip())
    has_value = bool((params.get("value") or "").strip())

    # ── Llama mis-routing guard ───────────────────────────────────────────────
    # If model sent mode=category but also supplied field+value, or sent a
    # bogus/catch-all category (e.g. "all", "any", "everything") → reroute to
    # parameter mode.  This covers: "isolate element with param comment = X"
    # where llama forgets to set mode=parameter.
    if mode == "category" and (has_field and has_value):
        mode = "parameter"
    elif mode == "category" and cat_raw in _BOGUS_CATEGORIES:
        if has_field and has_value:
            mode = "parameter"
        else:
            return (
                "Please specify a valid category (e.g. walls, doors, furniture) "
                "or use mode=parameter with field and value to filter by a parameter."
            )

    if mode == "inplace":
        return _isolate_inplace(params, doc, uidoc)
    elif mode == "filesize":
        return _isolate_filesize(params, doc, uidoc)
    elif mode == "parameter":
        return _isolate_parameter(params, doc, uidoc, resolve_category)
    else:
        return _isolate_category(params, doc, uidoc, resolve_category)
