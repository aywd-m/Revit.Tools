# -*- coding: utf-8 -*-
"""
Kidzink — Architectural / Interior Design Warning Library
Warning definitions for the Revit Health Check tool.
Each entry in KNOWN_WARNINGS is one health-score check.
WARNING_EXPLANATIONS provides the grey hint text shown below each type.

This file lives in:
  Kidzink Tools.extension/lib/warnings_arc.py

IronPython 2.7 — no type hints, no f-strings.
© Archie C. Manza 2026
"""

WARNING_EXPLANATIONS = {
    # ── Duplicates ──
    'Elements have duplicate "Number" values':
        'Two or more sheets or rooms share the same number. Renumber duplicates so each element has a unique identifier.',
    'Elements have duplicate "Type Mark" values':
        'Multiple family types share the same Type Mark. Assign unique Type Marks or clear unused ones.',
    'Elements have duplicate "Mark" values':
        'Instance Mark values are duplicated within the same category. Clear or reassign marks to remove ambiguity.',

    # ── Overlaps & Identical ──
    'There are identical instances in the same place':
        'Two identical elements are stacked on top of each other. Delete the duplicate to reduce model size and avoid double-counting.',
    'One element is completely inside another':
        'A wall, floor, or other element is fully enclosed by another of the same type, causing geometry overlap.',
    'Highlighted floors overlap':
        'Floor slabs intersect or overlap each other, which can cause area/volume miscalculations.',
    'Highlighted walls overlap':
        'Two walls occupy the same space, causing doubled geometry and incorrect room boundaries.',
    'Highlighted roofs overlap':
        'Roof elements intersect, leading to geometry conflicts and potential rendering issues.',
    'Highlighted ceilings overlap':
        'Ceiling elements overlap, which can cause doubled area values and visual artefacts.',

    # ── Rooms ──
    'Room Tag is outside of its Room':
        'A room tag has been moved or the room boundary changed so the tag no longer sits inside its room.',
    'Room is not in a properly enclosed region':
        'Room-bounding walls or separation lines do not form a closed loop. Close the gap so the room can calculate area.',
    'Multiple Rooms are in the same enclosed region':
        'More than one room element exists inside a single enclosed boundary. Delete the extra room or add a separation line.',
    'Room separation line is slightly off axis and may cause inaccuracies':
        'A room separation line is rotated by a fraction of a degree from the nearest axis. Straighten it to fix area calculations.',

    # ── Areas ──
    'Area is not in a properly enclosed region':
        'Area boundary lines do not form a closed loop. Close the gap in the area plan.',
    'Multiple Areas are in the same enclosed region':
        'More than one area element shares a single enclosed boundary. Delete the duplicate or add a boundary line.',
    'Area Tag is outside of its Area':
        'An area tag has been moved outside its area boundary. Drag it back inside or reassociate it.',
    'Area boundary line is slightly off axis':
        'An area boundary line is fractionally off axis. Straighten it to prevent area calculation gaps.',

    # ── MEP Spaces (kept for cross-discipline overlap) ──
    'Space is not in a properly enclosed region':
        'MEP space boundaries are not closed. Close the gap so the space can calculate volume and airflow.',
    'Space Tag is outside of its Space':
        'A space tag sits outside its associated space boundary.',

    # ── Off-Axis ──
    'Wall is slightly off axis and may cause inaccuracies':
        'A wall is not aligned to the project grid or nearest 45° angle. Snap it to axis to avoid join and area errors.',
    'Line is slightly off axis':
        'A model or detail line is fractionally off a clean angle. Straighten to avoid downstream geometry issues.',

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
    # ── Duplicates ──
    'Elements have duplicate "Number" values',
    'Elements have duplicate "Type Mark" values',
    'Elements have duplicate "Mark" values',

    # ── Overlaps & Identical ──
    'There are identical instances in the same place',
    'One element is completely inside another',
    'Highlighted floors overlap',
    'Highlighted walls overlap',
    'Highlighted roofs overlap',
    'Highlighted ceilings overlap',

    # ── Rooms ──
    'Room Tag is outside of its Room',
    'Room is not in a properly enclosed region',
    'Multiple Rooms are in the same enclosed region',
    'Room separation line is slightly off axis and may cause inaccuracies',

    # ── Areas ──
    'Area is not in a properly enclosed region',
    'Multiple Areas are in the same enclosed region',
    'Area Tag is outside of its Area',
    'Area boundary line is slightly off axis',

    # ── MEP Spaces ──
    'Space is not in a properly enclosed region',
    'Space Tag is outside of its Space',

    # ── Off-Axis ──
    'Wall is slightly off axis and may cause inaccuracies',
    'Line is slightly off axis',

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