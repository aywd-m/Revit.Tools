# -*- coding: utf-8 -*-
"""
Kidzink — Structural Warning Library
Warning definitions for the Revit Health Check tool.
Each entry in KNOWN_WARNINGS is one health-score check.
WARNING_EXPLANATIONS provides the grey hint text shown below each type.

This file lives in:
  Kidzink Tools.extension/lib/warnings_str.py

IronPython 2.7 — no type hints, no f-strings.
© Archie C. Manza 2026
"""

WARNING_EXPLANATIONS = {
    # ── Structural Connections & Joins ──
    'Beam/column join has invalid geometry':
        'The beam-column connection produced an invalid geometric result. Adjust the connection or the member profiles to fix it.',
    'Coping cannot be applied to the highlighted elements':
        'Coping (cutback) failed for these structural elements. Check the member profiles, connection order, or remove the coping and reapply.',
    'The cut length of the rebar is out of the standard range':
        'Reinforcing bar cut length exceeds the standard fabrication range. Shorten the bar or split into lapped segments.',
    'Rebar cannot maintain cover on both sides':
        'The reinforcement bar cannot satisfy the specified concrete cover on opposing faces simultaneously. Adjust bar position, cover settings, or host geometry.',

    # ── Analytical Model ──
    'Analytical model is inconsistent with the physical model':
        'The structural analytical model does not match the physical geometry. Realign or update the analytical model to ensure correct analysis results.',
    'Analytical model has no support':
        'An analytical member has no structural support at one or both ends. Add a support condition or connect it to another member.',
    'Analytical model alignment is not set':
        'The analytical alignment rule is missing. Set the analytical adjustment method so the analysis line matches the physical centreline.',

    # ── Reinforcement ──
    'Reinforcement boundaries are not closed':
        'Rebar boundary lines do not form a closed loop. Close the shape for the reinforcement host to function correctly.',
    'Rebar set has inconsistent constraints':
        'A rebar set has conflicting host-face or spacing constraints. Review and correct the constraints so the bars distribute evenly.',
    'Rebar hooks overlap':
        'Two rebar hooks occupy the same space inside the host. Adjust hook orientation, bar spacing, or hook type to eliminate the clash.',

    # ── Structural Geometry ──
    'Beam or brace is not joined to any support':
        'A beam or brace end is floating — not connected to a column, wall, or foundation. Extend or join it to a supporting element.',
    'Foundation is not associated with a structural column':
        'An isolated foundation has no column above it. Place a column or reassociate the foundation.',
    'Structural framing member is slightly off axis and may cause inaccuracies':
        'A beam or brace is fractionally off a clean angle. Straighten it to ensure correct analytical results and avoid join errors.',

    # ── Overlaps ──
    'There are identical instances in the same place':
        'Two identical elements are stacked on top of each other. Delete the duplicate to reduce model size.',
    'Highlighted walls overlap':
        'Two walls occupy the same space, causing doubled geometry and incorrect room boundaries.',
    'Highlighted floors overlap':
        'Floor slabs intersect or overlap each other, which can cause area/volume miscalculations.',

    # ── General / Cross-discipline (model warnings only — no worksharing) ──
    'Constraint is not satisfied':
        'A locked dimension or alignment constraint cannot be maintained. Unlock or adjust the constraint.',
    'Tag has no host':
        'An annotation tag references an element that has been deleted. Remove the orphaned tag.',
    'Element references a deleted element':
        'An element still points to another element that no longer exists. Purge the broken reference.',
    'Linked file is missing':
        'A Revit link file cannot be found at its saved path. Relink the file or remove the broken reference.',
    'Dimension references deleted elements':
        'A dimension string references geometry that has been removed. Delete or re-host the dimension.',
}

KNOWN_WARNINGS = [
    # ── Structural Connections & Joins ──
    'Beam/column join has invalid geometry',
    'Coping cannot be applied to the highlighted elements',
    'The cut length of the rebar is out of the standard range',
    'Rebar cannot maintain cover on both sides',

    # ── Analytical Model ──
    'Analytical model is inconsistent with the physical model',
    'Analytical model has no support',
    'Analytical model alignment is not set',

    # ── Reinforcement ──
    'Reinforcement boundaries are not closed',
    'Rebar set has inconsistent constraints',
    'Rebar hooks overlap',

    # ── Structural Geometry ──
    'Beam or brace is not joined to any support',
    'Foundation is not associated with a structural column',
    'Structural framing member is slightly off axis and may cause inaccuracies',

    # ── Overlaps ──
    'There are identical instances in the same place',
    'Highlighted walls overlap',
    'Highlighted floors overlap',

    # ── General / Cross-discipline ──
    'Constraint is not satisfied',
    'Tag has no host',
    'Element references a deleted element',
    'Linked file is missing',
    'Dimension references deleted elements',
]