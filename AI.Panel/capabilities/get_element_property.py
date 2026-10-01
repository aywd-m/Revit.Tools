# -*- coding: utf-8 -*-
# capabilities/get_element_property.py
# Plugin: read parameter values from the currently selected element(s).
# Absorbs get_element_ids — get_element_ids.py can be removed.

ACTION_NAME  = "get_element_property"
DESCRIPTION  = (
    "Read a parameter value from the currently selected element(s). "
    "No element_id needed — reads from the active Revit selection. "
    "This action REPLACES get_element_ids — use property_name='id' to get element IDs. "
    "Use property_name='all' to list every readable parameter on the first selected element. "
    "Reads up to 5 selected elements and reports the value for each."
)
PARAMS = {
    "property_name": (
        "string — Revit UI display name of the parameter, e.g. 'Unconnected Height', "
        "'Mark', 'Comments', 'Level'. "
        "Use 'all' to dump every parameter. "
        "Use 'id' to return the element IDs of the selected elements."
    ),
}
EXAMPLE = {
    "action": "get_element_property",
    "params": {"property_name": "Unconnected Height"},
}
EXAMPLE_IDS = {
    "action": "get_element_property",
    "params": {"property_name": "id"},
}

_MAX_ELEMENTS = 5   # max elements read per query
_MAX_ALL_PARAMS = 50  # max params shown in 'all' mode

_BIP_ALIASES = {
    "unconnected height": ["WALL_USER_HEIGHT_PARAM", "INSTANCE_FREE_HOST_OFFSET_PARAM"],
    "height":             ["WALL_USER_HEIGHT_PARAM", "INSTANCE_FREE_HOST_OFFSET_PARAM",
                           "DOOR_HEIGHT", "WINDOW_HEIGHT", "ROOM_HEIGHT",
                           "STAIRS_ACTUAL_RISER_HEIGHT", "FAMILY_HEIGHT_PARAM"],
    "width":              ["DOOR_WIDTH", "WINDOW_WIDTH", "WALL_ATTR_WIDTH_PARAM", "FAMILY_WIDTH_PARAM"],
    "thickness":          ["WALL_ATTR_WIDTH_PARAM"],
    "length":             ["CURVE_ELEM_LENGTH", "INSTANCE_LENGTH_PARAM"],
    "area":               ["HOST_AREA_COMPUTED", "ROOM_AREA"],
    "volume":             ["HOST_VOLUME_COMPUTED", "ROOM_VOLUME"],
    "base constraint":    ["WALL_BASE_CONSTRAINT"],
    "top constraint":     ["WALL_HEIGHT_TYPE"],
    "base offset":        ["WALL_BASE_OFFSET"],
    "top offset":         ["WALL_TOP_OFFSET"],
    "level":              ["FAMILY_LEVEL_PARAM", "WALL_BASE_CONSTRAINT", "ROOM_LEVEL_ID"],
    "mark":               ["ALL_MODEL_MARK"],
    "comments":           ["ALL_MODEL_INSTANCE_COMMENTS"],
    "type name":          ["ALL_MODEL_TYPE_NAME"],
    "family name":        ["ALL_MODEL_FAMILY_NAME"],
    "type mark":          ["ALL_MODEL_TYPE_MARK"],
    "description":        ["ALL_MODEL_DESCRIPTION"],
    "manufacturer":       ["ALL_MODEL_MANUFACTURER"],
    "fire rating":        ["DOOR_FIRE_RATING"],
    "room name":          ["ROOM_NAME"],
    "room number":        ["ROOM_NUMBER"],
    "structural usage":   ["WALL_STRUCTURAL_USAGE_PARAM"],
}


def _read_param(p, doc, eid_int):
    """Convert a Parameter object to a display string.

    Fix GEP3: Integer branch no longer calls AsElementId() — that method does
    not exist on Integer-storage params in IronPython 2.7; ElementId resolution
    now only runs on StorageType.ElementId params.
    """
    from Autodesk.Revit.DB import StorageType
    try:
        if not p.HasValue:
            return None
        st = p.StorageType
        if st == StorageType.String:
            s = p.AsString()
            return s if s else None
        if st == StorageType.Double:
            vs = p.AsValueString()
            return vs if vs else (str(round(p.AsDouble(), 4)) + " ft")
        if st == StorageType.Integer:
            # Fix GEP3: Integer params — no AsElementId() attempt.
            vs = p.AsValueString()
            return vs if vs else str(p.AsInteger())
        if st == StorageType.ElementId:
            eid = p.AsElementId()
            if eid is not None and eid_int(eid) > 0:
                el = doc.GetElement(eid)
                if el is not None:
                    try:
                        return el.Name
                    except Exception:
                        return str(eid_int(eid))
            vs = p.AsValueString()
            return vs if vs else "<none>"
        vs = p.AsValueString()
        return vs if vs else None
    except Exception:
        return None


def _resolve_param(elem, prop_lower, doc, eid_int):
    """Resolve a param name to (display_name, value_str) or (prop_lower, None).

    Fix GEP1: single pass over elem.Parameters — exact match, BIP fast path,
    and fuzzy candidate collection all happen in one iteration.
    Fix GEP5: returns resolved name without mutating any outer state.
    """
    from Autodesk.Revit.DB import BuiltInParameter

    # ── 1. BuiltInParameter fast path ────────────────────────────────────────
    bip_names = list(_BIP_ALIASES.get(prop_lower, []))
    bip_names.append(prop_lower.upper().replace(" ", "_"))
    for bip_name in bip_names:
        try:
            bip = getattr(BuiltInParameter, bip_name, None)
            if bip is None:
                continue
            p = elem.get_Parameter(bip)
            if p is not None:
                v = _read_param(p, doc, eid_int)
                if v is not None:
                    return p.Definition.Name, v
        except Exception:
            continue

    # ── 2. Single-pass over Parameters: exact match + fuzzy candidates ────────
    # Fix GEP1: previously two separate loops; now one.
    exact_result   = None
    fuzzy_candidates = []   # (name_len, display_name, value)
    try:
        for p in elem.Parameters:
            try:
                pname    = p.Definition.Name
                pname_lo = pname.lower()
                if pname_lo == prop_lower:
                    v = _read_param(p, doc, eid_int)
                    if v is not None:
                        exact_result = (pname, v)
                        break   # exact match wins immediately
                elif prop_lower in pname_lo:
                    v = _read_param(p, doc, eid_int)
                    if v is not None:
                        fuzzy_candidates.append((len(pname_lo), pname, v))
            except Exception:
                continue
    except Exception:
        pass

    if exact_result:
        return exact_result

    if fuzzy_candidates:
        fuzzy_candidates.sort(key=lambda x: x[0])
        return fuzzy_candidates[0][1], fuzzy_candidates[0][2]

    # ── 3. LookupParameter with name variants ────────────────────────────────
    prop_display = prop_lower  # best we have at this point
    for variant in [prop_lower, prop_lower.title(), prop_lower.upper(),
                    prop_lower.replace(" ", "")]:
        try:
            p = elem.LookupParameter(variant)
            if p is not None:
                v = _read_param(p, doc, eid_int)
                if v is not None:
                    return p.Definition.Name, v
        except Exception:
            continue

    return prop_display, None


def execute(params, doc, uidoc, eid_int, **_kwargs):
    if not doc or not uidoc:
        return "No document open."

    prop = (params.get("property_name") or "").strip()
    if not prop:
        return "No property_name specified."

    try:
        ids = list(uidoc.Selection.GetElementIds())
    except Exception as e:
        return "Cannot read selection: " + str(e)
    if not ids:
        return "No elements selected. Select an element in Revit first, then ask again."

    prop_lower = prop.lower()

    # ── 'id' shortcut — absorbed from get_element_ids ────────────────────────
    if prop_lower == "id":
        lines = []
        for eid in ids:
            try:
                elem  = doc.GetElement(eid)
                eid_v = eid_int(eid)
                cat   = ""
                try:
                    cat = elem.Category.Name + " " if elem else ""
                except Exception:
                    pass
                name = ""
                try:
                    name = (elem.Name or "") if elem else ""
                except Exception:
                    pass
                lines.append(cat + "ID: " + str(eid_v) + (" — " + name if name else ""))
            except Exception as ex:
                lines.append("Error: " + str(ex))
        return str(len(ids)) + " selected element(s):\n" + "\n".join(lines)

    # ── 'all' — dump every readable parameter on the first element ───────────
    if prop_lower == "all":
        try:
            elem = doc.GetElement(ids[0])
            if elem is None:
                return "Element not found."
            cat = ""
            try:
                cat = elem.Category.Name + " "
            except Exception:
                pass
            # Fix GEP2: collect all params (HasValue or not), report total count.
            lines = []
            for p in elem.Parameters:
                try:
                    v = _read_param(p, doc, eid_int)
                    if v is not None:
                        lines.append(p.Definition.Name + " = " + v)
                except Exception:
                    continue
            lines.sort()
            total = len(lines)
            shown = lines[:_MAX_ALL_PARAMS]
            header = cat + "{0} readable parameter(s){1}:".format(
                total,
                " (showing first {0})".format(_MAX_ALL_PARAMS) if total > _MAX_ALL_PARAMS else "",
            )
            return header + "\n" + "\n".join(shown)
        except Exception as ex:
            return "Error reading parameters: " + str(ex)

    # ── Named property — read from up to _MAX_ELEMENTS selected elements ──────
    # Fix GEP4: tell the user how many elements were checked vs selected.
    target_ids = ids[:_MAX_ELEMENTS]
    results    = []
    for eid in target_ids:
        try:
            elem = doc.GetElement(eid)
            if elem is None:
                continue
            # Fix GEP5: _resolve_param returns its own resolved name per element;
            # no shared prop_display mutation across iterations.
            resolved_name, val = _resolve_param(elem, prop_lower, doc, eid_int)
            cat = ""
            try:
                cat = elem.Category.Name + " "
            except Exception:
                pass
            eid_v = eid_int(eid)
            if val is not None:
                results.append(cat + "(id " + str(eid_v) + "): "
                                + resolved_name + " = " + val)
            else:
                results.append(cat + "(id " + str(eid_v) + "): '"
                                + prop + "' not found")
        except Exception as ex:
            results.append("Element error: " + str(ex))

    if not results:
        return "No readable elements in selection."

    header = ""
    if len(ids) > _MAX_ELEMENTS:
        header = ("({0} elements selected — reading first {1})\n".format(
            len(ids), _MAX_ELEMENTS))
    return header + "\n".join(results)
