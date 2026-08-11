# -*- coding: utf-8 -*-
# suppress the blank pyRevit output pane — MUST be first executable line
# temporarily DISABLED to capture error traceback — re-enable after diagnosis
# try:
#     __window__.hide()
# except Exception:
#     pass

"""
Kidzink — Revit Health Check
Exports a branded HTML report of all model warnings,
grouped by type, with clipboard-copy IDs and a model health gauge.
Includes linked models (pinned status) and large families (>=1 MB).
IronPython 2.7 / Revit 2025-2026
"""

import os
import sys
import base64
import tempfile
import datetime
import subprocess
import math
import time
import re

from Autodesk.Revit.DB import (
    FilteredElementCollector, ElementId, RevitLinkType,
    RevitLinkInstance, Family, ImportInstance,
    BuiltInCategory, BuiltInParameter,
    View3D, ViewFamilyType, ViewFamily,
    Transaction, ImageExportOptions, ZoomFitType,
    FitDirectionType, ImageResolution, ImageFileType,
    ExportRange, ModelPathUtils
)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
LOGO_PATH = os.path.join(os.environ.get("APPDATA", ""), "Kidzink", "kzk_logo.png")
MIN_FAMILY_SIZE = 1048576          # 1 MB
VIEW_3D_NAME = "_3DView_ModelHealthCheck"
# Health scoring — pass/fail per check
# Score = (Passed Checks / Total Evaluated Checks) × 100
# Each known warning type is one check. 0 issues = pass, >0 = fail.
# Ungrouped warning types also count as failed checks.

# Explanation text shown in grey below each warning type
WARNING_EXPLANATIONS = {
    'Elements have duplicate "Number" values':
        'Two or more sheets or rooms share the same number. Renumber duplicates so each element has a unique identifier.',
    'Elements have duplicate "Type Mark" values':
        'Multiple family types share the same Type Mark. Assign unique Type Marks or clear unused ones.',
    'Elements have duplicate "Mark" values':
        'Instance Mark values are duplicated within the same category. Clear or reassign marks to remove ambiguity.',
    'There are identical instances in the same place':
        'Two identical elements are stacked on top of each other. Delete the duplicate to reduce model size and avoid double-counting.',
    'Room Tag is outside of its Room':
        'A room tag has been moved or the room boundary changed so the tag no longer sits inside its room.',
    'One element is completely inside another':
        'A wall, floor, or other element is fully enclosed by another of the same type, causing geometry overlap.',
    'Highlighted floors overlap':
        'Floor slabs intersect or overlap each other, which can cause area/volume miscalculations.',
    'Room is not in a properly enclosed region':
        'Room-bounding walls or separation lines do not form a closed loop. Close the gap so the room can calculate area.',
    'Multiple Rooms are in the same enclosed region':
        'More than one room element exists inside a single enclosed boundary. Delete the extra room or add a separation line.',
    'Area is not in a properly enclosed region':
        'Area boundary lines do not form a closed loop. Close the gap in the area plan.',
    'Room separation line is slightly off axis and may cause inaccuracies':
        'A room separation line is rotated by a fraction of a degree from the nearest axis. Straighten it to fix area calculations.',
    'Wall is slightly off axis and may cause inaccuracies':
        'A wall is not aligned to the project grid or nearest 45° angle. Snap it to axis to avoid join and area errors.',
    'Line is slightly off axis':
        'A model or detail line is fractionally off a clean angle. Straighten to avoid downstream geometry issues.',
    'Highlighted walls overlap':
        'Two walls occupy the same space, causing doubled geometry and incorrect room boundaries.',
    'Highlighted roofs overlap':
        'Roof elements intersect, leading to geometry conflicts and potential rendering issues.',
    'Highlighted ceilings overlap':
        'Ceiling elements overlap, which can cause doubled area values and visual artefacts.',
    'Area boundary line is slightly off axis':
        'An area boundary line is fractionally off axis. Straighten it to prevent area calculation gaps.',
    'Multiple Areas are in the same enclosed region':
        'More than one area element shares a single enclosed boundary. Delete the duplicate or add a boundary line.',
    'Area Tag is outside of its Area':
        'An area tag has been moved outside its area boundary. Drag it back inside or reassociate it.',
    'Space is not in a properly enclosed region':
        'MEP space boundaries are not closed. Close the gap so the space can calculate volume and airflow.',
    'Space Tag is outside of its Space':
        'A space tag sits outside its associated space boundary.',
    'Dimension references deleted elements':
        'A dimension string references geometry that has been removed. Delete or re-host the dimension.',
    'Constraint is not satisfied':
        'A locked dimension or alignment constraint cannot be maintained. Unlock or adjust the constraint.',
    'Tag has no host':
        'An annotation tag references an element that has been deleted. Remove the orphaned tag.',
    'View is not on a Sheet':
        'A view exists in the project but has not been placed on any sheet. Place it or delete if unused.',
    'The same view appears on more than one sheet':
        'A view is placed on multiple sheets simultaneously. Remove the duplicate placement.',
    'Linked file is missing':
        'A Revit link file cannot be found at its saved path. Relink the file or remove the broken reference.',
    'Element references a deleted element':
        'An element still points to another element that no longer exists. Purge the broken reference.',
}

KNOWN_WARNINGS = [
    'Elements have duplicate "Number" values',
    'Elements have duplicate "Type Mark" values',
    'Elements have duplicate "Mark" values',
    'There are identical instances in the same place',
    'Room Tag is outside of its Room',
    'One element is completely inside another',
    'Highlighted floors overlap',
    'Room is not in a properly enclosed region',
    'Multiple Rooms are in the same enclosed region',
    'Area is not in a properly enclosed region',
    'Room separation line is slightly off axis and may cause inaccuracies',
    'Wall is slightly off axis and may cause inaccuracies',
    'Line is slightly off axis',
    'Highlighted walls overlap',
    'Highlighted roofs overlap',
    'Highlighted ceilings overlap',
    'Area boundary line is slightly off axis',
    'Multiple Areas are in the same enclosed region',
    'Area Tag is outside of its Area',
    'Space is not in a properly enclosed region',
    'Space Tag is outside of its Space',
    'Dimension references deleted elements',
    'Constraint is not satisfied',
    'Tag has no host',
    'View is not on a Sheet',
    'The same view appears on more than one sheet',
    'Linked file is missing',
    'Element references a deleted element',
]

# Pre‑lowercase known warnings for faster matching
KNOWN_WARNINGS_LOW = {w.lower(): w for w in KNOWN_WARNINGS}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _bring_revit_forward():
    try:
        from Autodesk.Windows import ComponentManager
        hWnd = ComponentManager.ApplicationWindow.Handle
        import ctypes
        ctypes.windll.user32.SetForegroundWindow(hWnd)
    except Exception:
        pass


def _get_logo_b64():
    if not os.path.isfile(LOGO_PATH):
        return ""
    try:
        with open(LOGO_PATH, "rb") as f:
            data = f.read()
        ext = os.path.splitext(LOGO_PATH)[1].lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        b64 = base64.b64encode(data).decode("ascii")
        return "data:image/{0};base64,{1}".format(ext, b64)
    except Exception:
        return ""


def get_eid_int(element_id):
    try:
        return element_id.Value
    except AttributeError:
        return element_id.IntegerValue


def _get_element_level_name(doc, elem):
    """
    Return the level name for an element, or None if not determinable.
    Tries LevelId parameter, then Level property, then host's level.
    """
    try:
        p = elem.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM)
        if p and p.AsElementId() and get_eid_int(p.AsElementId()) > 0:
            lvl = doc.GetElement(p.AsElementId())
            if lvl and lvl.Name:
                return lvl.Name
    except Exception:
        pass
    try:
        lvl = getattr(elem, 'Level', None)
        if lvl and lvl.Name:
            return lvl.Name
    except Exception:
        pass
    try:
        p = elem.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM)
        if p and p.AsElementId() and get_eid_int(p.AsElementId()) > 0:
            lvl = doc.GetElement(p.AsElementId())
            if lvl and lvl.Name:
                return lvl.Name
    except Exception:
        pass
    try:
        host = getattr(elem, 'Host', None)
        if host:
            lvl = getattr(host, 'Level', None)
            if lvl and lvl.Name:
                return lvl.Name
    except Exception:
        pass
    return None


def _build_level_elev_map(doc):
    """
    Return a dict {level_name: elevation} built from a single Level collector pass.
    Used to sort level groups without repeated collector calls per element.
    """
    result = {}
    try:
        from Autodesk.Revit.DB import Level
        for lvl in FilteredElementCollector(doc).OfClass(Level):
            try:
                result[lvl.Name] = lvl.Elevation
            except Exception:
                pass
    except Exception:
        pass
    return result


def _score(grouped, ungrouped):
    """Score = (Passed Checks / Total Evaluated Checks) × 100.
    Each known warning type = 1 check. Ungrouped types = extra failed checks."""
    total_checks = len(KNOWN_WARNINGS) + len(ungrouped)
    failed = sum(1 for v in grouped.values() if len(v) > 0) + len(ungrouped)
    passed = total_checks - failed
    if total_checks == 0:
        score = 100
    else:
        score = int(round(passed * 100.0 / total_checks))
    # Grade label + colour from score
    if score >= 90:
        return score, "Excellent", "#3B6D11", passed, total_checks
    if score >= 75:
        return score, "Good", "#639922", passed, total_checks
    if score >= 50:
        return score, "Fair — needs attention", "#BA7517", passed, total_checks
    if score >= 25:
        return score, "Poor — action required", "#E43C2F", passed, total_checks
    return score, "Critical — urgent action required", "#A00000", passed, total_checks


def _needle_coords(score):
    """
    Gauge arc: 180deg (left, score=0) to 0deg (right, score=100).
    Centre = (150, 140), radius = 95.
    """
    angle_deg = 180.0 - (score / 100.0 * 180.0)
    angle_rad = math.radians(angle_deg)
    cx, cy, r = 150, 140, 95
    x2 = cx + r * math.cos(angle_rad)
    y2 = cy - r * math.sin(angle_rad)
    return round(x2, 1), round(y2, 1)


# ---------------------------------------------------------------------------
# COLLECT WARNINGS
# ---------------------------------------------------------------------------
def collect_warnings(doc):
    # Use int sets for O(1) dedup — CLR ElementId equality is unreliable
    # under IronPython 2.7 for the `in` operator on plain lists.
    grouped      = {w: [] for w in KNOWN_WARNINGS}
    grouped_seen = {w: set() for w in KNOWN_WARNINGS}  # int sets
    ungrouped      = {}
    ungrouped_seen = {}  # desc -> set of int
    total = 0

    for w in doc.GetWarnings():
        total += 1
        desc = w.GetDescriptionText().strip()
        if desc.endswith("."):
            desc = desc[:-1]
        desc_low = desc.lower()

        ids = list(w.GetFailingElements())

        matched = False
        for known_low, known_name in KNOWN_WARNINGS_LOW.items():
            if known_low in desc_low or desc_low in known_low:
                seen = grouped_seen[known_name]
                for eid in ids:
                    iv = get_eid_int(eid)
                    if iv not in seen:
                        seen.add(iv)
                        grouped[known_name].append(eid)
                matched = True
                break

        if not matched:
            if desc not in ungrouped:
                ungrouped[desc] = []
                ungrouped_seen[desc] = set()
            seen = ungrouped_seen[desc]
            for eid in ids:
                iv = get_eid_int(eid)
                if iv not in seen:
                    seen.add(iv)
                    ungrouped[desc].append(eid)

    return grouped, ungrouped, total


def count_model_elements(doc):
    return FilteredElementCollector(doc)\
        .WhereElementIsNotElementType()\
        .GetElementCount()


# ---------------------------------------------------------------------------
# COLLECT LINKED MODELS (FIXED – deduplicate by type ID)
# ---------------------------------------------------------------------------
def collect_linked_models(doc):
    """
    Return list of (name, instance_count, is_pinned) for every distinct
    Revit link type in doc.
    instance_count > 1 means the same model is placed multiple times
    (duplicated link). is_pinned reflects the first instance found.
    Unloaded links are included with count=0 and pinned=False.
    """
    type_counts = {}
    type_pinned = {}
    type_names  = {}

    instances = list(FilteredElementCollector(doc).OfClass(RevitLinkInstance))
    for inst in instances:
        try:
            type_id = inst.GetTypeId()
            if not type_id:
                continue
            tid = get_eid_int(type_id)
            type_counts[tid] = type_counts.get(tid, 0) + 1
            if tid not in type_pinned:
                type_pinned[tid] = inst.Pinned
            if tid not in type_names:
                name = u""
                try:
                    name = inst.Name or u""
                except Exception:
                    pass
                if not name:
                    rlt = doc.GetElement(type_id)
                    if rlt:
                        try:
                            name = rlt.Name or u""
                        except Exception:
                            pass
                if not name:
                    try:
                        link_doc = inst.GetLinkDocument()
                        if link_doc and link_doc.PathName:
                            name = os.path.basename(link_doc.PathName)
                    except Exception:
                        pass
                type_names[tid] = name or u"Unknown"
        except Exception:
            continue

    link_types = list(FilteredElementCollector(doc).OfClass(RevitLinkType))
    for rlt in link_types:
        try:
            tid = get_eid_int(rlt.Id)
            if tid in type_counts:
                continue
            try:
                name = rlt.Name or u"Unloaded Link (ID: {0})".format(tid)
            except Exception:
                name = u"Unloaded Link (ID: {0})".format(tid)
            type_names[tid]  = name
            type_counts[tid] = 0
            type_pinned[tid] = False
        except Exception:
            continue

    result = []
    for tid, name in sorted(type_names.items(), key=lambda x: x[1].lower()):
        result.append((name, type_counts.get(tid, 0), type_pinned.get(tid, False)))
    return result


# ---------------------------------------------------------------------------
# COLLECT LARGE FAMILIES (>= 1 MB) — EditFamily + SaveAs to temp
# ---------------------------------------------------------------------------
# Strategy: for each loadable family, open its editor document via
# app.EditFamily(), SaveAs to a temp file, measure size, then close.
# This is the only method that works regardless of where the model lives
# (local, network, ACC/BIM 360, renamed after load, cloud storage, etc.).
# The family editor window is suppressed because we never call UIApplication
# — we go through Application.EditFamily() which returns a Document object
# without opening a visible editor window in the UI.

def _is_system_family(fam):
    """
    System families (Walls, Floors, Ceilings…) cannot be saved as RFA.
    They are in-place families or have no FamilyCategory.
    Annotation/tag families are NOT system families.
    """
    try:
        if fam.IsInPlace:
            return True
    except Exception:
        pass
    try:
        if fam.FamilyCategory is None:
            return True
    except Exception:
        pass
    return False


def _collect_family_instance_data(doc):
    """
    Single FamilyInstance collector pass shared by collect_large_families and
    collect_in_place_families.  Returns (fam_instance_counts, in_place_list):
      fam_instance_counts : dict {family_name: int}  — all loadable + in-place
      in_place_list       : list of (fam_name, cat_name, eid_int, level_name)
    """
    from Autodesk.Revit.DB import FamilyInstance
    fam_instance_counts = {}
    in_place_list = []
    try:
        for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
            try:
                sym = fi.Symbol
                if not sym:
                    continue
                fam = sym.Family
                if not fam:
                    continue
                fn = fam.Name or u""
                if fn:
                    fam_instance_counts[fn] = fam_instance_counts.get(fn, 0) + 1
                # Check in-place
                try:
                    is_ip = fam.IsInPlace
                except Exception:
                    is_ip = False
                if is_ip and fn:
                    cat_name = u""
                    try:
                        if fam.FamilyCategory and fam.FamilyCategory.Name:
                            cat_name = fam.FamilyCategory.Name
                    except Exception:
                        pass
                    eid_int = get_eid_int(fi.Id)
                    level_name = _get_element_level_name(doc, fi) or u"No Level"
                    in_place_list.append((fn, cat_name, eid_int, level_name))
            except Exception:
                pass
    except Exception:
        pass
    return fam_instance_counts, in_place_list


def _measure_family_size(app, fam):
    """
    Open the family document via app.EditFamily(), SaveAs to a temp file,
    measure the file size, then close without saving.
    Returns size in bytes, or None on any failure.

    app.EditFamily() returns a Document without opening a visible UI window
    (unlike UIApplication.OpenAndActivateDocument).  The family editor pane
    does NOT appear — this is safe to call in a batch loop.
    """
    tmp_path = None
    fam_doc = None
    try:
        tmp_dir = tempfile.gettempdir()
        # Sanitise the family name for use as a filename
        safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', u'_', fam.Name or u"family")
        tmp_path = os.path.join(tmp_dir, u"kzk_famsz_" + safe_name + u".rfa")

        # Open the family editor document (no visible UI window)
        fam_doc = app.EditFamily(fam)
        if fam_doc is None:
            return None

        # SaveAs to temp — overwrites without confirmation because it is a
        # new path and the family document owns no open transaction.
        from Autodesk.Revit.DB import SaveAsOptions
        sao = SaveAsOptions()
        sao.OverwriteExistingFile = True
        fam_doc.SaveAs(tmp_path, sao)

        sz = os.path.getsize(tmp_path)
        return sz

    except Exception:
        return None

    finally:
        # Always close the family document and remove the temp file
        if fam_doc is not None:
            try:
                fam_doc.Close(False)  # False = do not save
            except Exception:
                pass
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def collect_large_families(doc, app, fi_data=None):
    """
    Collect all loadable families in the model and report those >= 1 MB.
    Uses EditFamily() + SaveAs to temp to measure each family's RFA size —
    works for local, network, ACC/BIM 360 and any other model location.

    fi_data: optional pre-built tuple (fam_instance_counts, in_place_list)
    from _collect_family_instance_data() — avoids a duplicate FamilyInstance sweep.
    """
    if fi_data is not None:
        fam_instance_counts = fi_data[0]
    else:
        from Autodesk.Revit.DB import FamilyInstance
        fam_instance_counts = {}
        try:
            for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
                try:
                    sym = fi.Symbol
                    if sym and sym.Family:
                        fn = sym.Family.Name
                        if fn:
                            fam_instance_counts[fn] = fam_instance_counts.get(fn, 0) + 1
                except Exception:
                    pass
        except Exception:
            pass

    results = []
    try:
        collector = list(FilteredElementCollector(doc).OfClass(Family))
        for fam in collector:
            try:
                name = fam.Name or u"Unknown"
                if _is_system_family(fam):
                    continue
                sz = _measure_family_size(app, fam)
                if sz is None or sz < MIN_FAMILY_SIZE:
                    continue
                inst_count = fam_instance_counts.get(name, 0)
                results.append((name, sz, inst_count))
            except Exception:
                pass
    except Exception:
        pass

    return sorted(results, key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# COLLECT IMPORTED CAD
# ---------------------------------------------------------------------------
def collect_imported_cad(doc):
    cads = []
    try:
        collector = list(FilteredElementCollector(doc).OfClass(ImportInstance))
        for imp in collector:
            try:
                name = "Unknown"
                try:
                    if imp.Category and imp.Category.Name:
                        name = imp.Category.Name
                except Exception:
                    pass
                try:
                    p = imp.get_Parameter(BuiltInParameter.IMPORT_SYMBOL_NAME)
                    if p and p.AsString():
                        name = p.AsString()
                except Exception:
                    pass
                if name == "Unknown":
                    try:
                        if imp.Name:
                            name = imp.Name
                    except Exception:
                        pass
                eid = get_eid_int(imp.Id)
                cads.append((name, eid))
            except Exception:
                pass
    except Exception:
        pass
    return cads


# ---------------------------------------------------------------------------
# COLLECT LINKED CAD
# ---------------------------------------------------------------------------
def collect_linked_cad(doc):
    """
    Return list of (name, instance_count, element_ids) for all linked
    (not imported) CAD files in the model.
    Uses CADLinkType + ImportInstance.IsLinked to distinguish linked from
    imported. Each distinct CAD link type is one row; count shows how many
    times it has been placed (duplicated links > 1).
    """
    from Autodesk.Revit.DB import CADLinkType
    type_counts = {}   # type_id_int -> count
    type_names  = {}   # type_id_int -> name
    type_eids   = {}   # type_id_int -> [eid, ...]

    try:
        instances = list(FilteredElementCollector(doc).OfClass(ImportInstance))
        for imp in instances:
            try:
                # IsLinked distinguishes linked CAD from imported CAD
                try:
                    if not imp.IsLinked:
                        continue
                except Exception:
                    continue

                type_id = imp.GetTypeId()
                if not type_id:
                    continue
                tid = get_eid_int(type_id)
                eid = get_eid_int(imp.Id)

                type_counts[tid] = type_counts.get(tid, 0) + 1
                if tid not in type_eids:
                    type_eids[tid] = []
                type_eids[tid].append(eid)

                if tid not in type_names:
                    name = u""
                    # Try CADLinkType name
                    try:
                        clt = doc.GetElement(type_id)
                        if clt:
                            name = clt.Name or u""
                    except Exception:
                        pass
                    # Fallback to ImportInstance parameter
                    if not name:
                        try:
                            p = imp.get_Parameter(BuiltInParameter.IMPORT_SYMBOL_NAME)
                            if p and p.AsString():
                                name = p.AsString()
                        except Exception:
                            pass
                    if not name:
                        try:
                            name = imp.Category.Name if imp.Category else u""
                        except Exception:
                            pass
                    type_names[tid] = name or u"Unknown CAD Link"
            except Exception:
                continue
    except Exception:
        pass

    result = []
    for tid, name in sorted(type_names.items(), key=lambda x: x[1].lower()):
        result.append((name, type_counts.get(tid, 1), type_eids.get(tid, [])))
    return result


def _linked_cad_html(linked_cads):
    if not linked_cads:
        return (u'<div class="section-head">Linked CAD</div>'
                u'<div class="acc-item acc-ok">'
                u'<div class="acc-header acc-header-ok">'
                u'<div class="acc-left"><div class="acc-title acc-title-ok">\u2713 No linked CAD found</div></div>'
                u'<span class="acc-badge acc-badge-ok">0</span>'
                u'</div></div>')

    total_instances = sum(c for _n, c, _e in linked_cads)
    all_eids = []
    for _n, _c, eids in linked_cads:
        all_eids.extend(eids)
    id_list = u",".join([str(e) for e in all_eids])

    rows = u""
    for name, count, eids in linked_cads:
        if count > 1:
            count_str = u'<span class="link-count link-count-dup">' + str(count) + u' \u26a0</span>'
        else:
            count_str = u'<span class="link-count">' + str(count) + u'</span>'
        row_ids = u",".join([str(e) for e in eids])
        rows += (u'<div class="warn-row link-row">'
                 u'<span class="link-name">' + name + u'</span>'
                 + count_str +
                 u'<button class="action-btn" style="padding:2px 8px;font-size:11px;" onclick="copyIds(this,\''
                 + row_ids + u'\')"  >Copy IDs</button>'
                 u'</div>')

    return (u'<div class="section-head">Linked CAD</div>'
            u'<div class="acc-item acc-danger">'
            u'<div class="acc-header acc-header-danger">'
            u'<div class="acc-left"><div class="acc-title acc-title-danger">Linked CAD Files</div></div>'
            u'<div class="acc-right">'
            u'<span class="acc-badge acc-badge-danger">' + str(len(linked_cads)) + u' Files / ' + str(total_instances) + u' Instances</span>'
            u'<button class="action-btn" onclick="copyIds(this,\''
            + id_list + u'\')" >Copy All IDs</button>'
            u'</div></div>'
            u'<div class="warn-rows">'
            u'<div class="col-head"><span>CAD File Name</span><span class="col-count">Count</span><span style="float:right">IDs</span></div>'
            + rows +
            u'</div></div>')


# ---------------------------------------------------------------------------
# COLLECT GENERIC MODELS
# ---------------------------------------------------------------------------
def collect_generic_models(doc):
    generics = []
    try:
        collector = list(
            FilteredElementCollector(doc)
            .OfCategory(BuiltInCategory.OST_GenericModel)
            .WhereElementIsNotElementType()
        )
        for elem in collector:
            try:
                name = "Unknown"
                try:
                    if elem.Name:
                        name = elem.Name
                except Exception:
                    pass
                try:
                    fam_name = elem.Symbol.Family.Name
                    type_name = elem.Name
                    name = fam_name + " : " + type_name
                except Exception:
                    pass
                eid = get_eid_int(elem.Id)
                generics.append((name, eid))
            except Exception:
                pass
    except Exception:
        pass
    return generics


def _fmt_size(size_bytes):
    mb = size_bytes / 1048576.0
    if mb >= 100:
        return "{0:.0f} MB".format(mb)
    return "{0:.1f} MB".format(mb)


# ---------------------------------------------------------------------------
# HTML BUILDING BLOCKS
# ---------------------------------------------------------------------------
def _warn_group_html(desc, eids, show_zero=True, doc=None, level_elev_map=None):
    count = len(eids)
    expl = WARNING_EXPLANATIONS.get(desc, u"")

    if count == 0:
        if not show_zero:
            return u""
        return (u'<div class="acc-item acc-ok">'
                u'<div class="acc-header acc-header-ok">'
                u'<div class="acc-left">'
                u'<div class="acc-title acc-title-ok">\u2713 ' + desc + u'</div>'
                + (u'<div class="acc-desc">' + expl + u'</div>' if expl else u'') +
                u'</div>'
                u'<span class="acc-badge acc-badge-ok">0 Issues</span>'
                u'</div></div>')

    id_list = u",".join([str(get_eid_int(eid)) for eid in eids])

    # Group element IDs by level when doc is available
    rows_html = u""
    if doc is not None:
        # level_elev_map is pre-built once per report; fall back to empty dict
        elev_lookup = level_elev_map if level_elev_map is not None else {}

        # Build level -> [eid_int, ...] mapping
        level_map = {}   # level_name -> list of eid_int
        for eid in eids:
            eid_int = get_eid_int(eid)
            level_name = None
            try:
                elem = doc.GetElement(eid)
                if elem:
                    level_name = _get_element_level_name(doc, elem)
            except Exception:
                pass
            if not level_name:
                level_name = u"No Level"
            if level_name not in level_map:
                level_map[level_name] = []
            level_map[level_name].append(eid_int)

        # Sort levels by elevation ascending; No Level sorts to top
        sorted_levels = sorted(
            level_map.keys(),
            key=lambda n: elev_lookup.get(n, -999999.0) if n != u"No Level" else -999999.0
        )

        for level_name in sorted_levels:
            level_eids = level_map[level_name]
            rows_html += (u'<div class="warn-level-head">'
                          + level_name +
                          u' <span class="warn-level-count">(' + str(len(level_eids)) + u')</span>'
                          u'</div>')
            for eid_int in level_eids:
                rows_html += (u'<div class="warn-row">'
                              u'<input type="checkbox" class="resolve-cb" onchange="toggleResolved(this)"/>'
                              u'<span class="eid">' + str(eid_int) + u'</span>'
                              u'<button class="action-btn" style="padding:1px 7px;font-size:10px;margin-left:10px;" '
                              u'onclick="copyIds(this,\'' + str(eid_int) + u'\')">Copy ID</button>'
                              u'</div>')
    else:
        # Fallback: flat list (no doc)
        for eid in eids:
            eid_int = get_eid_int(eid)
            rows_html += (u'<div class="warn-row">'
                          u'<input type="checkbox" class="resolve-cb" onchange="toggleResolved(this)"/>'
                          u'<span class="eid">' + str(eid_int) + u'</span>'
                          u'<button class="action-btn" style="padding:1px 7px;font-size:10px;margin-left:10px;" '
                          u'onclick="copyIds(this,\'' + str(eid_int) + u'\')">Copy ID</button>'
                          u'</div>')

    return (u'<div class="acc-item acc-danger">'
            u'<div class="acc-header acc-header-danger">'
            u'<div class="acc-left">'
            u'<div class="acc-title acc-title-danger">\u26a0\ufe0f ' + desc + u'</div>'
            + (u'<div class="acc-desc">' + expl + u'</div>' if expl else u'') +
            u'</div>'
            u'<div class="acc-right">'
            u'<span class="acc-badge acc-badge-danger">' + str(count) + u' Elements</span>'
            u'<button class="action-btn" onclick="copyIds(this,\''
            + id_list + u'\')">Copy IDs</button>'
            u'</div>'
            u'</div>'
            u'<div class="warn-rows">'
            u'<div class="col-head"><span>Level / Element ID</span></div>'
            + rows_html +
            u'</div></div>')


def _linked_models_html(links):
    if not links:
        return (u'<div class="section-head">Linked Models</div>'
                u'<div class="acc-item acc-ok">'
                u'<div class="acc-header acc-header-ok">'
                u'<div class="acc-left"><div class="acc-title acc-title-ok">\u2713 No linked models found</div></div>'
                u'<span class="acc-badge acc-badge-ok">0</span>'
                u'</div></div>')

    rows = u""
    for name, count, pinned in links:
        if count == 0:
            count_str = u'<span class="link-count link-count-unloaded">\u2014</span>'
        elif count > 1:
            count_str = u'<span class="link-count link-count-dup">' + str(count) + u' \u26a0</span>'
        else:
            count_str = u'<span class="link-count">' + str(count) + u'</span>'
        if pinned:
            status = u'<span class="link-status pinned">\u25cf Pinned</span>'
        else:
            status = u'<span class="link-status unpinned">\u25cf Unpinned</span>'
        rows += (u'<div class="warn-row link-row">'
                 u'<span class="link-name">' + name + u'</span>'
                 + count_str +
                 status + u'</div>')
    return (u'<div class="section-head">Linked Models</div>'
            u'<div class="acc-item acc-danger">'
            u'<div class="acc-header acc-header-danger">'
            u'<div class="acc-left"><div class="acc-title acc-title-danger">Linked Revit Models</div></div>'
            u'<span class="acc-badge acc-badge-danger">' + str(len(links)) + u'</span>'
            u'</div>'
            u'<div class="warn-rows">'
            u'<div class="col-head"><span>Model Name</span><span class="col-count">Count</span><span style="float:right">Status</span></div>'
            + rows +
            u'</div></div>')


def _large_families_html(families):
    if not families:
        return (u'<div class="section-head">Large Families (\u2265 1 MB)</div>'
                u'<div class="acc-item acc-ok">'
                u'<div class="acc-header acc-header-ok">'
                u'<div class="acc-left"><div class="acc-title acc-title-ok">\u2713 No families \u2265 1 MB found</div></div>'
                u'<span class="acc-badge acc-badge-ok">0</span>'
                u'</div></div>')

    rows = u""
    for name, size, inst_count in families:
        if inst_count > 1:
            count_cell = u'<span class="link-count link-count-dup">' + str(inst_count) + u'</span>'
        elif inst_count == 1:
            count_cell = u'<span class="link-count">' + str(inst_count) + u'</span>'
        else:
            count_cell = u'<span class="link-count link-count-unloaded">\u2014</span>'
        rows += (u'<div class="warn-row fam-row">'
                 u'<span class="fam-name">' + name + u'</span>'
                 + count_cell +
                 u'<span class="fam-size">' + _fmt_size(size) + u'</span>'
                 u'</div>')
    return (u'<div class="section-head">Large Families (\u2265 1 MB)</div>'
            u'<div class="acc-item acc-danger">'
            u'<div class="acc-header acc-header-danger">'
            u'<div class="acc-left"><div class="acc-title acc-title-danger">Families \u2265 1 MB \u2014 sorted by file size</div></div>'
            u'<span class="acc-badge acc-badge-danger">' + str(len(families)) + u'</span>'
            u'</div>'
            u'<div class="warn-rows">'
            u'<div class="col-head">'
            u'<span>Family Name</span>'
            u'<span class="col-count">Count</span>'
            u'<span style="float:right">Size</span>'
            u'</div>'
            + rows +
            u'</div></div>')


def _imported_cad_html(cads):
    if not cads:
        return (u'<div class="section-head">Imported CAD</div>'
                u'<div class="acc-item acc-ok">'
                u'<div class="acc-header acc-header-ok">'
                u'<div class="acc-left"><div class="acc-title acc-title-ok">\u2713 No imported CAD found</div></div>'
                u'<span class="acc-badge acc-badge-ok">0</span>'
                u'</div></div>')

    id_list = ",".join([str(eid) for _n, eid in cads])
    rows = u""
    for name, eid in cads:
        rows += (u'<div class="warn-row link-row">'
                 u'<span class="link-name">' + name + u'</span>'
                 u'<span style="margin-left:auto;display:flex;align-items:center;gap:10px;flex-shrink:0;">'
                 u'<span class="eid" style="font-family:monospace;color:#444;">' + str(eid) + u'</span>'
                 u'<button class="action-btn" style="padding:1px 7px;font-size:10px;" '
                 u'onclick="copyIds(this,\'' + str(eid) + u'\')">Copy ID</button>'
                 u'</span>'
                 u'</div>')
    return (u'<div class="section-head">Imported CAD</div>'
            u'<div class="acc-item acc-danger">'
            u'<div class="acc-header acc-header-danger">'
            u'<div class="acc-left"><div class="acc-title acc-title-danger">Imported CAD Instances</div></div>'
            u'<div class="acc-right">'
            u'<span class="acc-badge acc-badge-danger">' + str(len(cads)) + u'</span>'
            u'<button class="action-btn" onclick="copyIds(this,\'' + id_list + u'\')">Copy IDs</button>'
            u'</div></div>'
            u'<div class="warn-rows">'
            u'<div class="col-head"><span>CAD Name</span><span style="float:right">Element ID</span></div>'
            + rows +
            u'</div></div>')


def _generic_models_html(generics):
    if not generics:
        return (u'<div class="section-head">Generic Models</div>'
                u'<div class="acc-item acc-ok">'
                u'<div class="acc-header acc-header-ok">'
                u'<div class="acc-left"><div class="acc-title acc-title-ok">\u2713 No generic models found</div></div>'
                u'<span class="acc-badge acc-badge-ok">0</span>'
                u'</div></div>')

    id_list = u",".join([str(eid) for _n, eid in generics])
    rows = u""
    for name, eid in generics:
        rows += (u'<div class="warn-row link-row">'
                 u'<span class="link-name">' + name + u'</span>'
                 u'<span style="margin-left:auto;display:flex;align-items:center;gap:10px;flex-shrink:0;">'
                 u'<span class="eid">' + str(eid) + u'</span>'
                 u'<button class="action-btn" style="padding:1px 7px;font-size:10px;" '
                 u'onclick="copyIds(this,\'' + str(eid) + u'\')">Copy ID</button>'
                 u'</span>'
                 u'</div>')
    return (u'<div class="section-head">Generic Models</div>'
            u'<div class="acc-item acc-danger">'
            u'<div class="acc-header acc-header-danger">'
            u'<div class="acc-left"><div class="acc-title acc-title-danger">Generic Model Instances</div></div>'
            u'<div class="acc-right">'
            u'<span class="acc-badge acc-badge-danger">' + str(len(generics)) + u'</span>'
            u'<button class="action-btn" onclick="copyIds(this,\'' + id_list + u'\')">Copy IDs</button>'
            u'</div></div>'
            u'<div class="warn-rows">'
            u'<div class="col-head"><span>Family : Type</span><span style="float:right">Element ID</span></div>'
            + rows +
            u'</div></div>')


# ---------------------------------------------------------------------------
# COLLECT IN-PLACE FAMILIES
# ---------------------------------------------------------------------------
def collect_in_place_families(doc, fi_data=None):
    """
    Collect all in-place family instances in the model.
    Returns list of (family_name, category_name, eid_int, level_name).
    fi_data: optional pre-built tuple (fam_instance_counts, in_place_list)
    from _collect_family_instance_data() — avoids a duplicate FamilyInstance sweep.
    """
    if fi_data is not None:
        return fi_data[1]

    # Fallback: do our own sweep
    from Autodesk.Revit.DB import FamilyInstance
    results = []
    try:
        for fi in FilteredElementCollector(doc).OfClass(FamilyInstance):
            try:
                sym = fi.Symbol
                if not sym:
                    continue
                fam = sym.Family
                if not fam:
                    continue
                try:
                    if not fam.IsInPlace:
                        continue
                except Exception:
                    continue
                fam_name = fam.Name or u"Unknown"
                cat_name = u""
                try:
                    if fam.FamilyCategory and fam.FamilyCategory.Name:
                        cat_name = fam.FamilyCategory.Name
                except Exception:
                    pass
                eid_int = get_eid_int(fi.Id)
                level_name = _get_element_level_name(doc, fi) or u"No Level"
                results.append((fam_name, cat_name, eid_int, level_name))
            except Exception:
                pass
    except Exception:
        pass
    return results


def _in_place_families_html(in_place, doc, level_elev_map=None):
    """
    Render the In-Place Families section.
    Groups instances by level (sorted by elevation), then by family name within each level.
    Shows count per family name and a Copy All IDs button.
    level_elev_map is pre-built once per report; pass it in to avoid repeated collector calls.
    """
    if not in_place:
        return (u'<div class="section-head">In-Place Families</div>'
                u'<div class="acc-item acc-ok">'
                u'<div class="acc-header acc-header-ok">'
                u'<div class="acc-left"><div class="acc-title acc-title-ok">\u2713 No in-place families found</div></div>'
                u'<span class="acc-badge acc-badge-ok">0</span>'
                u'</div></div>')

    total_count = len(in_place)
    all_eids = [str(eid) for _fn, _cn, eid, _ln in in_place]
    id_list = u",".join(all_eids)

    elev_lookup = level_elev_map if level_elev_map is not None else {}

    # Group by level
    level_map = {}   # level_name -> list of (fam_name, cat_name, eid_int)
    for fam_name, cat_name, eid_int, level_name in in_place:
        if level_name not in level_map:
            level_map[level_name] = []
        level_map[level_name].append((fam_name, cat_name, eid_int))

    sorted_levels = sorted(
        level_map.keys(),
        key=lambda n: elev_lookup.get(n, -999999.0) if n != u"No Level" else -999999.0
    )

    rows = u""
    for level_name in sorted_levels:
        entries = level_map[level_name]
        # Sub-group by family name within the level for count display
        fam_counts = {}
        for fam_name, cat_name, eid_int in entries:
            key = fam_name
            if key not in fam_counts:
                fam_counts[key] = {'cat': cat_name, 'eids': []}
            fam_counts[key]['eids'].append(eid_int)

        rows += (u'<div class="warn-level-head">'
                 + level_name +
                 u' <span class="warn-level-count">(' + str(len(entries)) + u')</span>'
                 u'</div>')

        # Sort family groups alphabetically within level
        for fam_name in sorted(fam_counts.keys()):
            fdata = fam_counts[fam_name]
            cat_label = (u' \u2014 ' + fdata['cat']) if fdata['cat'] else u""
            fam_eids = fdata['eids']
            fam_id_str = u",".join([str(e) for e in fam_eids])
            inst_count = len(fam_eids)

            if inst_count > 1:
                count_cell = u'<span class="link-count link-count-dup">' + str(inst_count) + u'</span>'
            else:
                count_cell = u'<span class="link-count">' + str(inst_count) + u'</span>'

            rows += (u'<div class="warn-row link-row">'
                     u'<span class="link-name">'
                     + fam_name + u'<span style="color:#64748b;font-weight:400;">' + cat_label + u'</span>'
                     u'</span>'
                     + count_cell +
                     u'<button class="action-btn" style="padding:2px 8px;font-size:11px;" '
                     u'onclick="copyIds(this,\'' + fam_id_str + u'\')">Copy IDs</button>'
                     u'</div>')

    return (u'<div class="section-head">In-Place Families</div>'
            u'<div class="acc-item acc-danger">'
            u'<div class="acc-header acc-header-danger">'
            u'<div class="acc-left"><div class="acc-title acc-title-danger">In-Place Family Instances</div></div>'
            u'<div class="acc-right">'
            u'<span class="acc-badge acc-badge-danger">' + str(total_count) + u'</span>'
            u'<button class="action-btn" onclick="copyIds(this,\'' + id_list + u'\')">Copy All IDs</button>'
            u'</div></div>'
            u'<div class="warn-rows">'
            u'<div class="col-head">'
            u'<span>Family Name \u2014 Category</span>'
            u'<span class="col-count">Count</span>'
            u'<span style="float:right">IDs</span>'
            u'</div>'
            + rows +
            u'</div></div>')


# ---------------------------------------------------------------------------
# 3D VIEW — create / export for health check report
# ---------------------------------------------------------------------------
def _safe_img_type(name, fallback):
    try:
        return getattr(ImageFileType, name)
    except AttributeError:
        return fallback


def _safe_dpi(name, fallback):
    try:
        return getattr(ImageResolution, name)
    except AttributeError:
        return fallback


def _get_3d_view_family_type(doc):
    collector = FilteredElementCollector(doc).OfClass(ViewFamilyType)
    for vft in collector:
        try:
            if vft.ViewFamily == ViewFamily.ThreeDimensional:
                return vft
        except Exception:
            pass
    return None


def _create_or_get_3d_view(doc):
    collector = FilteredElementCollector(doc).OfClass(View3D)
    for v in collector:
        try:
            if v.Name == VIEW_3D_NAME and not v.IsTemplate:
                return v
        except Exception:
            pass

    vft = _get_3d_view_family_type(doc)
    if vft is None:
        return None

    tx = Transaction(doc, "Create Health Check 3D View")
    try:
        tx.Start()
        view3d = View3D.CreateIsometric(doc, vft.Id)
        view3d.Name = VIEW_3D_NAME

        try:
            from Autodesk.Revit.DB import DisplayStyle
            view3d.get_Parameter(
                BuiltInParameter.MODEL_GRAPHICS_STYLE).Set(int(DisplayStyle.Shading))
        except Exception:
            try:
                view3d.get_Parameter(
                    BuiltInParameter.MODEL_GRAPHICS_STYLE).Set(3)
            except Exception:
                pass

        try:
            view3d.AreAnnotationCategoriesHidden = True
        except Exception:
            pass

        try:
            cat_lines = doc.Settings.Categories.get_Item(
                BuiltInCategory.OST_Lines)
            if cat_lines:
                view3d.SetCategoryHidden(cat_lines.Id, True)
        except Exception:
            pass

        for bic in [BuiltInCategory.OST_ImportObjectStyles,
                     BuiltInCategory.OST_RvtLinks]:
            try:
                cat = doc.Settings.Categories.get_Item(bic)
                if cat:
                    view3d.SetCategoryHidden(cat.Id, True)
            except Exception:
                pass

        tx.Commit()
        return view3d
    except Exception:
        try:
            tx.RollBack()
        except Exception:
            pass
        return None


def _export_3d_view_image(doc, view3d):
    if view3d is None:
        return u""

    out_dir = tempfile.gettempdir()
    base_name = "KZK_HealthCheck3D_{0}".format(int(time.time() * 1000))
    # Build a full path without extension
    file_path = os.path.join(out_dir, base_name)

    # Clean up old exports (any leftover from previous runs with same prefix)
    for f in os.listdir(out_dir):
        if f.startswith("KZK_HealthCheck3D") and f.lower().endswith(".png"):
            try:
                os.remove(os.path.join(out_dir, f))
            except Exception:
                pass

    try:
        opts = ImageExportOptions()
        opts.ZoomType = ZoomFitType.FitToPage
        opts.FitDirection = FitDirectionType.Horizontal
        opts.PixelSize = 1024
        opts.FilePath = file_path

        dpi = _safe_dpi("DPI_150", _safe_dpi("DPI150", None))
        if dpi:
            opts.ImageResolution = dpi

        png_type = _safe_img_type("PNG", None)
        if png_type:
            opts.HLRandWFViewsFileType = png_type
            opts.ShadowViewsFileType = png_type

        try:
            opts.ExportRange = ExportRange.SetOfViews
        except Exception:
            try:
                opts.ExportRange = 4
            except Exception:
                pass

        from System.Collections.Generic import List
        view_ids = List[ElementId]()
        view_ids.Add(view3d.Id)
        opts.SetViewsAndSheets(view_ids)

        doc.ExportImage(opts)

        # Wait for file to appear (poll up to 5 seconds)
        exported = None
        for _ in range(50):  # 50 * 0.1s = 5s
            for f in os.listdir(out_dir):
                if f.lower().endswith(".png") and f.startswith(base_name):
                    fpath = os.path.join(out_dir, f)
                    if os.path.isfile(fpath):
                        exported = fpath
                        break
            if exported:
                break
            time.sleep(0.1)

        if exported and os.path.isfile(exported):
            with open(exported, "rb") as fh:
                data = fh.read()
            if len(data) > 100:
                b64 = base64.b64encode(data).decode("ascii")
                try:
                    os.remove(exported)
                except Exception:
                    pass
                return u"data:image/png;base64," + b64
    except Exception:
        pass
    return u""


# ---------------------------------------------------------------------------
# GAUGE SVG — multicolour arc (green / amber / red) with needle
# ---------------------------------------------------------------------------
def _needle_label_coords(score):
    angle_deg = 180.0 - (score / 100.0 * 180.0)
    angle_rad = math.radians(angle_deg)
    cx, cy, r = 150, 140, 108
    x = cx + r * math.cos(angle_rad)
    y = cy - r * math.sin(angle_rad)
    return round(x, 1), round(y, 1)


def _gauge_svg(score):
    """
    Semicircular gauge: coloured arc fills only up to score position;
    the remainder of the arc is light grey (#C0C0C0).
    A vertical limit line marks the score position on the arc edge.

    Arc path: M 10 50 A 40 40 0 0 1 90 50  (r=40, cx=50, cy=50)
    Total half-circumference = pi * 40 = 125.664
    Score fraction maps left→right: 0% = left end, 100% = right end.
    Colour bands (filled portion only):
      red    0–33%   #ef4444
      yellow 33–66%  #eab308
      green  66–100% #22c55e
    """
    import math as _math
    arc_total = _math.pi * 40.0          # 125.664
    third = arc_total / 3.0              # 41.888
    score_len = arc_total * (score / 100.0)

    # Which colour bands are visible, and how much of each
    # Band 0: red   0 .. third
    # Band 1: yellow third .. 2*third
    # Band 2: green 2*third .. arc_total
    bands = [
        (u'#ef4444',  0.0,          third),
        (u'#eab308',  third,        third * 2),
        (u'#22c55e',  third * 2,    arc_total),
    ]

    # Score text colour = colour of the band the score falls in
    if score >= 66:
        score_colour = u'#22c55e'
    elif score >= 33:
        score_colour = u'#eab308'
    else:
        score_colour = u'#ef4444'

    # Needle / limit-line position on the arc
    # Arc angle: score=0 → 180° (left), score=100 → 0° (right)
    # cx=50, cy=50, r=40
    cx, cy, r = 50.0, 50.0, 40.0
    needle_angle_deg = 180.0 - (score / 100.0 * 180.0)
    needle_rad = _math.radians(needle_angle_deg)
    # Inner and outer edge of the stroke (stroke-width=10, so ±5 from r)
    r_inner = r - 7.0
    r_outer = r + 7.0
    nx_inner = round(cx + r_inner * _math.cos(needle_rad), 2)
    ny_inner = round(cy - r_inner * _math.sin(needle_rad), 2)
    nx_outer = round(cx + r_outer * _math.cos(needle_rad), 2)
    ny_outer = round(cy - r_outer * _math.sin(needle_rad), 2)

    # Build SVG
    # Background grey track (full arc)
    svg = (
        u'<svg viewBox="0 0 100 60" xmlns="http://www.w3.org/2000/svg"'
        u' style="width:100%;height:auto;display:block;overflow:visible;">'
        u'<path d="M 10 50 A 40 40 0 0 1 90 50" fill="none"'
        u' stroke="#C0C0C0" stroke-width="10" stroke-linecap="butt"/>'
    )

    # Coloured filled segments — only up to score_len
    for colour, band_start, band_end in bands:
        # How much of this band is filled?
        seg_start = band_start
        seg_end   = min(band_end, score_len)
        if seg_end <= seg_start:
            break   # score is below this band entirely
        seg_len = seg_end - seg_start
        # dasharray: draw seg_len, then gap the rest
        # dashoffset: negative offset to skip band_start
        svg += (
            u'<path d="M 10 50 A 40 40 0 0 1 90 50" fill="none"'
            u' stroke="' + colour + u'" stroke-width="10" stroke-linecap="butt"'
            u' stroke-dasharray="' + u'{0:.3f} {1:.3f}'.format(seg_len, arc_total) + u'"'
            u' stroke-dashoffset="' + u'{0:.3f}'.format(-seg_start) + u'"/>'
        )

    # Limit line at the score position (white line across arc width)
    svg += (
        u'<line x1="' + str(nx_inner) + u'" y1="' + str(ny_inner) + u'"'
        u' x2="' + str(nx_outer) + u'" y2="' + str(ny_outer) + u'"'
        u' stroke="#ffffff" stroke-width="1.8" stroke-linecap="round"/>'
    )

    # Score percentage text
    svg += (
        u'<text x="50" y="48" text-anchor="middle" dominant-baseline="auto"'
        u' font-family="Manrope,sans-serif" font-size="22" font-weight="800"'
        u' fill="' + score_colour + u'">' + str(score) + u'%</text>'
        u'</svg>'
    )
    return svg


# ---------------------------------------------------------------------------
# FULL HTML
# ---------------------------------------------------------------------------
def build_html(doc, grouped, ungrouped, total_warnings, links, large_fams,
               imported_cads, linked_cads, generic_models, in_place_fams, view_b64=""):
    app = __revit__.Application
    username = app.Username or "Unknown"
    pcname = os.environ.get("COMPUTERNAME", "Unknown")
    rvt_version = str(app.VersionNumber)
    doc_path = doc.PathName

    # Prefer central model path/name for workshared models
    try:
        central_model_path = doc.GetWorksharingCentralModelPath()
        central_path_str = ModelPathUtils.ConvertModelPathToUserVisiblePath(central_model_path)
        doc_name = os.path.basename(central_path_str) if central_path_str else (os.path.basename(doc_path) if doc_path else "Unsaved model")
        central_path_display = central_path_str or doc_path or ""
    except Exception:
        doc_name = os.path.basename(doc_path) if doc_path else "Unsaved model"
        central_path_display = doc_path or ""

    project_name = doc_name  # show central filename (without extension) as subtitle
    # Strip .rvt extension for the header subtitle
    if project_name.lower().endswith(".rvt"):
        project_name = project_name[:-4]

    now = datetime.datetime.now()
    export_date = now.strftime("%d %b %Y  %H:%M")

    total_elements = count_model_elements(doc)
    file_size_str = ""
    try:
        # Candidate 1 & 2: central path, then doc.PathName.
        # For ACC/BIM 360 both are cloud URIs (Autodesk Docs://...) so
        # os.path.isfile() returns False for both — fall through to candidate 3.
        _size_path = None
        for _candidate in [central_path_display, doc_path]:
            if _candidate and os.path.isfile(_candidate):
                _size_path = _candidate
                break

        # Candidate 3: CollaborationCache — used when the model is on ACC/BIM 360.
        # Revit caches a local copy at:
        #   %LOCALAPPDATA%\Autodesk\Revit\Autodesk Revit <year>\CollaborationCache\
        # We walk that tree and match by filename (doc.Title + ".rvt").
        if _size_path is None:
            try:
                _title = (doc.Title or u"").strip()
                if _title:
                    _collab_root = os.path.join(
                        os.environ.get("LOCALAPPDATA", ""),
                        "Autodesk", "Revit",
                        "Autodesk Revit {0}".format(rvt_version),
                        "CollaborationCache"
                    )
                    _target_name = (_title.lower() + ".rvt")
                    if os.path.isdir(_collab_root):
                        for _dirpath, _dirnames, _filenames in os.walk(_collab_root):
                            for _fname in _filenames:
                                if _fname.lower() == _target_name:
                                    _candidate = os.path.join(_dirpath, _fname)
                                    if os.path.isfile(_candidate):
                                        _size_path = _candidate
                                        break
                            if _size_path:
                                break
            except Exception:
                pass

        if _size_path:
            sz = os.path.getsize(_size_path)
            if sz >= 1073741824:
                file_size_str = "{0:.1f} GB".format(sz / 1073741824.0)
            elif sz >= 1048576:
                file_size_str = "{0:.0f} MB".format(sz / 1048576.0)
            elif sz >= 1024:
                file_size_str = "{0:.0f} KB".format(sz / 1024.0)
            else:
                file_size_str = str(sz) + " B"
    except Exception:
        pass

    affected = sum(len(v) for v in grouped.values()) + \
               sum(len(v) for v in ungrouped.values())

    score, grade_label, grade_colour, passed_checks, total_checks = _score(grouped, ungrouped)
    type_count = sum(1 for v in grouped.values() if len(v) > 0) + len(ungrouped)

    logo_uri = _get_logo_b64()
    if logo_uri:
        logo_slot_inner = u'<img id="logoImg" src="' + logo_uri + u'" alt="Logo"/>'
    else:
        logo_slot_inner = u'<div class="logo-ph">Add logo</div>'

    logo_html = (u'<div class="logo-slot" title="Click to upload your logo">'
                 + logo_slot_inner +
                 u'<input type="file" accept="image/*" onchange="loadLogo(event)"/>'
                 u'</div>')

    # Build level elevation map ONCE — reused by all level-grouped sections
    level_elev_map = _build_level_elev_map(doc)

    groups_html = u""
    for desc in KNOWN_WARNINGS:
        eids = grouped.get(desc, [])
        groups_html += _warn_group_html(desc, eids, show_zero=True, doc=doc,
                                        level_elev_map=level_elev_map)
    for desc, eids in ungrouped.items():
        groups_html += _warn_group_html(desc, eids, show_zero=False, doc=doc,
                                        level_elev_map=level_elev_map)

    links_html = _linked_models_html(links)
    fams_html = _large_families_html(large_fams)
    cad_html = _imported_cad_html(imported_cads)
    linked_cad_html = _linked_cad_html(linked_cads)
    generic_html = _generic_models_html(generic_models)
    in_place_html = _in_place_families_html(in_place_fams, doc,
                                            level_elev_map=level_elev_map)
    gauge_svg = _gauge_svg(score)

    if view_b64:
        view_img_html = u'<img src="' + view_b64 + u'" alt=""/>'
    else:
        view_img_html = u''

    tw = str(total_warnings)
    tc = str(type_count)
    aff = str(affected)
    tel = str(total_elements)

    path_bar_html = u''  # kept for compatibility (no longer used as separate bar)
    if central_path_display:
        _esc_path = central_path_display.replace(u"'", u"\\'")
        path_strip_html = (u'<div>Path: <span class="path-box">' + central_path_display + u'</span>'
                           u'<button class="path-copy-btn" onclick="copyPath(this,\''
                           + _esc_path + u'\')">Copy Path</button>'
                           u'</div>')
    else:
        path_strip_html = u''

    # KPI 4: health score — gauge SVG
    kpi4_colour = grade_colour
    kpi4_style = u'color:' + kpi4_colour + u';'
    gauge_svg = _gauge_svg(score)

    html = (
        u'<!DOCTYPE html><html lang="en"><head>'
        u'<meta charset="UTF-8"/>'
        u'<meta name="viewport" content="width=device-width, initial-scale=1.0"/>'
        u'<title>Kidzink \u2014 Revit Health Check \u2014 ' + project_name + u'</title>'
        u'<style>'
        u"@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');"
        u'*{box-sizing:border-box;margin:0;padding:0;}'
        u"body{font-family:'Manrope',sans-serif;font-size:13px;color:#1e293b;background:#f8fafc;padding:24px;}"
        u'.page{width:100%;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 16px rgba(0,0,0,0.10);}'
        u'.kzk-header{background:#E43C2F;color:#fff;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;gap:16px;}'
        u'.header-left{display:flex;align-items:center;gap:16px;}'
        u'.logo-slot{height:44px;display:flex;align-items:center;justify-content:center;cursor:pointer;flex-shrink:0;position:relative;}'
        u'.logo-slot img{max-height:44px;width:auto;height:auto;object-fit:contain;}'
        u'.logo-slot input{position:absolute;inset:0;opacity:0;cursor:pointer;}'
        u'.logo-ph{font-size:11px;color:rgba(255,255,255,0.75);pointer-events:none;border:1px dashed rgba(255,255,255,0.5);border-radius:4px;padding:6px 12px;}'
        u'.header-title h1{font-size:20px;font-weight:600;margin:0;}'
        u'.header-title p{font-size:13px;color:rgba(255,255,255,0.82);margin-top:2px;}'
        u'.header-meta{text-align:right;font-size:12px;color:rgba(255,255,255,0.85);line-height:1.7;}'
        u'.header-meta strong{color:#fff;}'
        u'.file-strip{background:#1e293b;color:#cbd5e1;padding:10px 24px;font-size:13px;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #334155;flex-wrap:wrap;gap:8px;}'
        u'.file-strip strong{color:#fff;}'
        u'.path-box{font-family:monospace;background:rgba(0,0,0,0.25);padding:3px 8px;border-radius:4px;color:#93c5fd;font-size:12px;word-break:break-all;}'
        u'.path-copy-btn{background:#334155;color:#fff;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:11px;white-space:nowrap;margin-left:8px;}'
        u'.path-copy-btn:hover{background:#475569;}'
        u'.path-copy-btn.copied{background:#3B6D11;}'
        u'.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;padding:20px 24px;background:#f8fafc;}'
        u'.kpi-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.05);}'
        u'.kpi-title{font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;}'
        u'.kpi-value{font-size:36px;font-weight:700;margin:8px 0 0;color:#1e293b;}'
        u'.kpi-value.danger{color:#ef4444;}'
        u'.kpi-sub{font-size:11px;color:#64748b;margin-top:4px;}'
        u'.gauge-card{background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:20px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.05);display:flex;flex-direction:column;align-items:center;justify-content:center;}'
        u'.gauge-title{font-size:11px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:10px;}'
        u'.gauge-wrap{width:100%;max-width:180px;position:relative;}'
        u'.gauge-grade{font-size:15px;font-weight:700;margin-top:10px;}'
        u'.gauge-sub{font-size:11px;color:#64748b;margin-top:3px;}'
        u'.view-strip{padding:0 24px 16px;background:#f8fafc;}'
        u'.view-box{background:#fff;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden;display:flex;align-items:center;justify-content:center;width:100%;}'
        u'.view-box img{width:100%;height:auto;display:block;object-fit:contain;}'
        u'.section-head{font-size:11px;font-weight:700;color:#64748b;letter-spacing:0.5px;text-transform:uppercase;margin:8px 24px 10px;}'
        u'.section-head:first-of-type{margin-top:4px;}'
        u'.acc-item{border-radius:6px;border:1px solid #e2e8f0;margin:0 24px 10px;overflow:hidden;}'
        u'.acc-item.acc-ok{border-left:5px solid #10b981;}'
        u'.acc-item.acc-danger{border-left:5px solid #ef4444;}'
        u'.acc-header{padding:14px 18px;display:flex;justify-content:space-between;align-items:center;gap:12px;}'
        u'.acc-header.acc-header-ok{background:#f0fdf4;}'
        u'.acc-header.acc-header-danger{background:#fef2f2;}'
        u'.acc-left{flex:1;}'
        u'.acc-right{display:flex;align-items:center;gap:8px;flex-shrink:0;}'
        u'.acc-title{font-weight:600;font-size:14px;margin-bottom:3px;}'
        u'.acc-title.acc-title-ok{color:#166534;}'
        u'.acc-title.acc-title-danger{color:#991b1b;}'
        u'.acc-desc{font-size:12px;color:#64748b;margin:0;}'
        u'.acc-badge{padding:3px 12px;border-radius:12px;font-weight:700;font-size:12px;white-space:nowrap;}'
        u'.acc-badge.acc-badge-ok{background:#dcfce7;color:#166534;}'
        u'.acc-badge.acc-badge-danger{background:#fee2e2;color:#991b1b;}'
        u'.action-btn{background:#ef4444;color:#fff;border:none;padding:5px 14px;border-radius:4px;font-weight:600;font-size:12px;cursor:pointer;white-space:nowrap;}'
        u'.action-btn:hover{background:#dc2626;}'
        u'.action-btn.copied{background:#3B6D11;}'
        u'.warn-rows{background:#fafafa;}'
        u'.col-head{padding:4px 14px;background:#f1f5f9;font-size:10px;color:#475569;font-weight:600;text-transform:uppercase;letter-spacing:0.04em;border-top:1px solid #e2e8f0;}'
        u'.warn-row{padding:5px 14px;border-bottom:0.5px solid #e2e8f0;font-size:11px;display:flex;align-items:center;gap:8px;}'
        u'.warn-row .eid{font-family:monospace;color:#475569;}'
        u'.resolve-cb{width:14px;height:14px;accent-color:#10b981;cursor:pointer;flex-shrink:0;}'
        u'.warn-row.resolved{background:#f0fdf4;text-decoration:line-through;color:#999;}'
        u'.warn-row.resolved .eid{color:#999;}'
        u'.warn-level-head{padding:4px 14px;background:#f1f5f9;font-size:10px;font-weight:700;color:#334155;text-transform:uppercase;letter-spacing:0.05em;border-top:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;}'
        u'.warn-level-count{font-weight:500;color:#64748b;}'
        u'.link-row{display:flex;align-items:center;justify-content:space-between;}'
        u'.link-name{font-size:12px;color:#1e293b;}'
        u'.link-status{font-size:12px;font-weight:600;}'
        u'.link-status.pinned{color:#10b981;}'
        u'.link-status.unpinned{color:#ef4444;}'
        u'.col-count{position:absolute;left:50%;transform:translateX(-50%);text-align:center;}'
        u'.link-row{position:relative;}'
        u'.link-count{font-size:12px;font-weight:600;color:#1e293b;position:absolute;left:50%;transform:translateX(-50%);}'
        u'.link-count-dup{color:#ef4444!important;}'
        u'.link-count-unloaded{color:#808080!important;font-style:italic;}'
        u'.fam-row{display:flex;align-items:center;justify-content:space-between;}'
        u'.fam-name{font-size:12px;color:#1e293b;}'
        u'.fam-size{font-size:12px;font-weight:600;color:#ef4444;font-family:monospace;}'
        u'.footer-bar{display:flex;justify-content:center;align-items:center;position:relative;padding:14px 24px;border-top:1px solid #e2e8f0;margin-top:16px;}'
        u'.footer-bar a{color:#E43C2F;font-size:12px;font-weight:500;text-decoration:none;}'
        u'.footer-copy{color:#64748b;font-size:10px;position:absolute;right:24px;}'
        u"#toast{display:none;position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#1e293b;color:#fff;padding:8px 20px;border-radius:4px;font-size:12px;z-index:999;font-family:'Manrope',sans-serif;}"
        u'#toast.show{display:block;}'
        u'@media print{body{background:#fff;padding:0;}.page{box-shadow:none;border-radius:0;}.action-btn{display:none;}.path-copy-btn{display:none;}#toast{display:none!important;}.resolve-cb{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}'
        u'</style></head><body><div class="page">'
        u'<div class="kzk-header">'
        u'<div class="header-left">'
        + logo_html +
        u'<div class="header-title">'
        u'<h1>Revit Health Check</h1>'
        u'<p>' + project_name + u'</p>'
        u'</div></div>'
        u'<div class="header-meta">'
        u'Exported: <strong>' + export_date + u'</strong><br>'
        u'@' + username + u' | ' + pcname + u' | Revit ' + rvt_version +
        u'</div></div>'
        u'<div class="file-strip">'
        u'<div>Model: <strong>' + doc_name + u'</strong>'
        + (u' (' + file_size_str + u')' if file_size_str else u'') +
        u'</div>'
        + path_strip_html +
        u'</div>'
        u'<div class="kpi-grid">'
        u'<div class="kpi-card"><div class="kpi-title">Total Warnings</div>'
        u'<div class="kpi-value danger">' + tw + u'</div></div>'
        u'<div class="kpi-card"><div class="kpi-title">Warning Types</div>'
        u'<div class="kpi-value">' + tc + u'</div></div>'
        u'<div class="kpi-card"><div class="kpi-title">Affected Elements</div>'
        u'<div class="kpi-value">' + aff + u'</div></div>'
        u'<div class="gauge-card"><div class="gauge-title">Model Health Score</div>'
        u'<div class="gauge-wrap">' + gauge_svg + u'</div>'
        u'<div class="gauge-grade" style="color:' + grade_colour + u';">' + grade_label + u'</div>'
        u'<div class="gauge-sub">' + str(passed_checks) + u' / ' + str(total_checks) + u' Checks Passed</div>'
        u'</div></div>'
        + (u'<div class="view-strip"><div class="view-box"><img src="' + view_b64 + u'" alt=""/></div></div>'
           if view_b64 else u'') +
        u'<div class="section-head">Warning details \u2014 grouped by type</div>'
        + groups_html
        + links_html
        + fams_html
        + cad_html
        + linked_cad_html
        + generic_html
        + in_place_html +
        u'<div class="footer-bar">'
        u'<a href="https://www.kidzink.com" target="_blank">www.kidzink.com</a>'
        u'<span class="footer-copy">\u00a9 Archie C. Manza 2026</span>'
        u'</div>'
        u'</div>'
        u'<div id="toast">IDs copied \u2014 paste into Revit Select by ID</div>'
        u'<script>'
        u'function loadLogo(e){'
        u'var file=e.target.files[0];if(!file)return;'
        u'var reader=new FileReader();'
        u'reader.onload=function(ev){'
        u"var slot=e.target.parentNode;var existing=slot.querySelector('img');"
        u'if(existing){existing.src=ev.target.result;}else{'
        u"var img=document.createElement('img');img.id='logoImg';"
        u"img.src=ev.target.result;img.alt='Logo';"
        u'slot.insertBefore(img,e.target);}'
        u"var ph=slot.querySelector('.logo-ph');if(ph)ph.style.display='none';"
        u'};reader.readAsDataURL(file);}'
        u'function _doCopy(text,btn,label){'
        u'if(navigator.clipboard&&navigator.clipboard.writeText){'
        u'navigator.clipboard.writeText(text).then(function(){_flash(btn,label);});'
        u"}else{var ta=document.createElement('textarea');"
        u"ta.value=text;ta.style.position='fixed';ta.style.opacity='0';"
        u"document.body.appendChild(ta);ta.select();document.execCommand('copy');"
        u'document.body.removeChild(ta);_flash(btn,label);}}'
        u'function copyIds(btn,ids){_doCopy(ids,btn,"\\u2713 Copied!");}'
        u'function copyPath(btn,path){_doCopy(path,btn,"\\u2713 Copied!");}'
        u'function _flash(btn,label){'
        u"var orig=btn.innerHTML;btn.innerHTML=label;"
        u"btn.classList.add('copied');"
        u"var t=document.getElementById('toast');t.classList.add('show');"
        u'setTimeout(function(){'
        u"btn.innerHTML=orig;btn.classList.remove('copied');"
        u"t.classList.remove('show');},2200);}"
        u'function toggleResolved(cb){'
        u"var row=cb.parentNode;if(cb.checked){row.classList.add('resolved');}else{row.classList.remove('resolved');}}"
        u'</script></body></html>'
    )

    return html


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    doc = __revit__.ActiveUIDocument.Document

    if doc.IsFamilyDocument:
        _bring_revit_forward()
        from pyrevit.forms import alert
        alert("Health Check is not available for Family documents.",
              title="Kidzink - Health Check")
        sys.exit(0)

    # collect
    grouped, ungrouped, total_warnings = collect_warnings(doc)
    links = collect_linked_models(doc)
    # Single FamilyInstance sweep shared by large-families and in-place checks
    fi_data = _collect_family_instance_data(doc)
    large_fams = collect_large_families(doc, __revit__.Application, fi_data=fi_data)
    imported_cads = collect_imported_cad(doc)
    linked_cads   = collect_linked_cad(doc)
    generic_models = collect_generic_models(doc)
    in_place_fams = collect_in_place_families(doc, fi_data=fi_data)

    # create / find 3D view and export image
    view3d = _create_or_get_3d_view(doc)
    view_b64 = _export_3d_view_image(doc, view3d)

    # build html
    html = build_html(doc, grouped, ungrouped, total_warnings,
                      links, large_fams, imported_cads,
                      linked_cads, generic_models, in_place_fams, view_b64)

    # ask user for save location
    model_name = doc.Title or "UnsavedModel"
    model_name = re.sub(r'[<>:"/\\|?*]', '_', model_name)
    time_stamp = datetime.datetime.now().strftime("%y%m%d_%H%M")
    fname = model_name + "_" + time_stamp + ".html"
    import clr
    clr.AddReference("System.Windows.Forms")
    from System.Windows.Forms import SaveFileDialog, DialogResult

    dlg = SaveFileDialog()
    dlg.Title = "Kidzink - Save Health Check Report"
    dlg.FileName = fname
    dlg.Filter = "HTML File (*.html)|*.html"
    dlg.DefaultExt = "html"
    dlg.OverwritePrompt = True

    try:
        if doc.PathName:
            dlg.InitialDirectory = os.path.dirname(doc.PathName)
        else:
            dlg.InitialDirectory = os.path.join(
                os.environ.get("USERPROFILE", ""), "Desktop")
    except Exception:
        pass

    if dlg.ShowDialog() != DialogResult.OK:
        return

    outpath = dlg.FileName

    with open(outpath, "wb") as f:
        f.write(html.encode("utf-8"))

    subprocess.Popen('start "" "' + outpath + '"', shell=True)


try:
    main()
except Exception as _kzk_err:
    import traceback as _tb
    print("=== KIDZINK HEALTH CHECK ERROR ===")
    print(_tb.format_exc())
    raise