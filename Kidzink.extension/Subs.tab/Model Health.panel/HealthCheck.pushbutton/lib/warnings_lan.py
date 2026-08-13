# -*- coding: utf-8 -*-
"""
Kidzink — Landscape / Infrastructure Warning Library
Warning definitions for the Revit Health Check tool.
Each entry in KNOWN_WARNINGS is one health-score check.
WARNING_EXPLANATIONS provides the grey hint text shown below each type.

This file lives in:
  Kidzink Tools.extension/lib/warnings_lan.py

IronPython 2.7 — no type hints, no f-strings.
© Archie C. Manza 2026
"""

WARNING_EXPLANATIONS = {
    # ── Topography & Site ──
    'Toposolid points are too close or overlapping':
        'Two or more toposolid points are extremely close together or occupying the same location. Adjust or delete the duplicate points to avoid geometry issues.',

    # ── Off-Axis ──
    'Wall is slightly off axis and may cause inaccuracies':
        'A retaining wall or site wall is not aligned to the project grid or nearest 45° angle. Snap it to axis to avoid join and area errors.',
    'Line is slightly off axis':
        'A model or detail line is fractionally off a clean angle. Straighten to avoid downstream geometry issues.',

    # ── Overlaps & Identical ──
    'There are identical instances in the same place':
        'Two identical elements are stacked on top of each other. Delete the duplicate to reduce model size and avoid double-counting.',
    'One element is completely inside another':
        'A wall, floor, or other element is fully enclosed by another of the same type, causing geometry overlap.',
    'Highlighted floors overlap':
        'Floor slabs or hardscape elements intersect or overlap each other, which can cause area/volume miscalculations.',
    'Highlighted walls overlap':
        'Two walls occupy the same space, causing doubled geometry and incorrect boundaries.',

    # ── Duplicates ──
    'Elements have duplicate "Mark" values':
        'Instance Mark values are duplicated within the same category. Clear or reassign marks to remove ambiguity in schedules and tags.',

    # ── Annotations & Views ──
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

    # ── Links & References ──
    'Linked file is missing':
        'A Revit link file cannot be found at its saved path. Relink the file or remove the broken reference.',
    'Element references a deleted element':
        'An element still points to another element that no longer exists. Purge the broken reference.',
}

KNOWN_WARNINGS = [
    # ── Topography & Site ──
    'Toposolid points are too close or overlapping',

    # ── Off-Axis ──
    'Wall is slightly off axis and may cause inaccuracies',
    'Line is slightly off axis',

    # ── Overlaps & Identical ──
    'There are identical instances in the same place',
    'One element is completely inside another',
    'Highlighted floors overlap',
    'Highlighted walls overlap',

    # ── Duplicates ──
    'Elements have duplicate "Mark" values',

    # ── Annotations & Views ──
    'Dimension references deleted elements',
    'Constraint is not satisfied',
    'Tag has no host',
    'View is not on a Sheet',
    'The same view appears on more than one sheet',

    # ── Links & References ──
    'Linked file is missing',
    'Element references a deleted element',
]