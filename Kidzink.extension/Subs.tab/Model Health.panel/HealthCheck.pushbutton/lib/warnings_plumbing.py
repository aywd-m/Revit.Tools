# -*- coding: utf-8 -*-
"""
Kidzink — Plumbing Warning Library
Warning definitions for the Revit Health Check tool.
Each entry in KNOWN_WARNINGS is one health-score check.
WARNING_EXPLANATIONS provides the grey hint text shown below each type.

Discipline: Plumbing
Standards: ISO 19650, UPC/IPC, Dubai Authority MEP requirements,
           BS EN 806, CIBSE Guide G

This file lives in:
  Kidzink Tools.extension/lib/warnings_plumbing.py

IronPython 2.7 — no type hints, no f-strings.
© Archie C. Manza 2026
"""

WARNING_EXPLANATIONS = {

    # ── Pipes & Fittings ──
    'Pipe is not connected at one or both ends':
        'A pipe segment has an open connector at one or both ends. Connect it to a fitting, fixture, or equipment.',
    'Pipe fitting is not connected':
        'A pipe fitting (elbow, tee, reducer, cap) has an open connector. Join it to the adjacent pipe or fitting.',
    'Pipe has no system type assigned':
        'The pipe is not assigned to a system type (e.g. Domestic Cold Water, Domestic Hot Water, Sanitary). Assign the correct system type.',
    'Pipe slope is insufficient for gravity system':
        'A gravity drainage or sanitary pipe has insufficient slope. Minimum 1% (1:100) slope is required unless otherwise specified by code.',
    'Pipe slope is excessive':
        'The pipe slope exceeds the maximum recommended value for the diameter, which can cause solids to be left behind. Review the gradient.',
    'Pipe diameter is not consistent with calculated flow':
        'The pipe is undersized or oversized relative to the design flow. Resize to match the pressure drop and velocity criteria.',
    'Pipe velocity is outside acceptable range':
        'Calculated flow velocity is too high (erosion risk) or too low (deposition risk) for the pipe material and service. Resize the pipe.',
    'Pipe has no insulation applied':
        'The pipe has no insulation type assigned. Apply insulation per the project energy or condensation specification.',
    'Pipe material is not specified':
        'The pipe type has no material parameter set. Define the material so fabrication and specification schedules are correct.',

    # ── Fixtures & Equipment ──
    'Plumbing fixture is not connected to a pipe system':
        'A plumbing fixture is not connected to any pipe system. Route a pipe to each fixture connector (CW, HW, waste).',
    'Plumbing fixture has no cold water connection':
        'The fixture has an unconnected cold water inlet. Connect it to the domestic cold water system.',
    'Plumbing fixture has no hot water connection':
        'The fixture has an unconnected hot water inlet. Connect it to the domestic hot water system.',
    'Plumbing fixture has no waste connection':
        'The fixture has an unconnected waste/drain outlet. Connect it to the sanitary drainage system.',
    'Plumbing fixture has no vent connection':
        'The fixture trap has no vent pipe assigned. Connect a vent to prevent siphonage and maintain trap seal.',
    'Plumbing equipment is not placed on a valid host':
        'Plumbing equipment (water heater, booster pump) is not properly hosted. Re-place it on the correct level or floor.',
    'Water heater has no cold water inlet':
        'The water heater has an unconnected cold water supply connector. Connect it to the cold water system.',
    'Water heater has no hot water outlet':
        'The water heater has an unconnected hot water outlet connector. Connect it to the hot water distribution system.',
    'Pump has no pipe system connection':
        'A booster or circulation pump has open connectors. Connect it inline within the appropriate pipe system.',

    # ── Systems ──
    'Pipe system has no equipment at root':
        'A domestic water or drainage system has no root equipment (pump, tank, or entry point) defined. Assign or connect the root equipment.',
    'System contains unconnected elements':
        'One or more elements in a pipe system are not fully connected. Trace the system tree to find and close the open connector.',
    'The calculated flow for this system is zero':
        'The pipe system flow is zero. Check fixture unit assignments, flow parameters, and connector directions.',
    'MEP system loop detected':
        'The pipe system has a circular flow path. Remove the loop unless a deliberate ring main or recirculation loop is intended.',
    'The family is not assigned to a system':
        'A plumbing component has no system assignment. Assign it to the appropriate pipe system.',
    'Pipe pressure drop exceeds allowable limit':
        'The calculated pressure drop across this pipe or system branch exceeds the design limit. Upsize the pipe or rebalance the system.',
    'Insulation or lining host is invalid':
        'Pipe insulation references a host that no longer exists or has changed. Remove and reapply the insulation.',

    # ── Drainage & Venting ──
    'Sanitary pipe has no vent riser assigned':
        'A sanitary branch or stack has no vent riser connected. Add a vent riser to prevent trap seal loss.',
    'Drain is below finished floor level without a sump':
        'A drain outlet is below the finished floor level with no sump or ejector pump. Review the drainage design.',
    'Grease trap is not connected to waste system':
        'A grease trap or interceptor has open connectors. Connect inlet and outlet to the kitchen waste and sanitary systems.',
    'Roof drain is not connected to storm system':
        'A roof drain or overflow drain has an open connector. Connect it to the storm water or combined drainage system.',

    # ── General / BIM Housekeeping ──
    'There are identical instances in the same place':
        'Two identical pipe or fixture elements are stacked on top of each other. Delete the duplicate to avoid double-counting.',
    'Constraint is not satisfied':
        'A locked dimension or alignment constraint cannot be maintained. Unlock or adjust the constraint.',
    'Tag has no host':
        'An annotation tag references a pipe or fixture element that has been deleted. Remove the orphaned tag.',
    'Element references a deleted element':
        'An element still points to another element that no longer exists. Purge the broken reference.',
    'Dimension references deleted elements':
        'A dimension string references geometry that has been removed. Delete or re-host the dimension.',
}

KNOWN_WARNINGS = [

    # ── Pipes & Fittings ──
    'Pipe is not connected at one or both ends',
    'Pipe fitting is not connected',
    'Pipe has no system type assigned',
    'Pipe slope is insufficient for gravity system',
    'Pipe slope is excessive',
    'Pipe diameter is not consistent with calculated flow',
    'Pipe velocity is outside acceptable range',
    'Pipe has no insulation applied',
    'Pipe material is not specified',

    # ── Fixtures & Equipment ──
    'Plumbing fixture is not connected to a pipe system',
    'Plumbing fixture has no cold water connection',
    'Plumbing fixture has no hot water connection',
    'Plumbing fixture has no waste connection',
    'Plumbing fixture has no vent connection',
    'Plumbing equipment is not placed on a valid host',
    'Water heater has no cold water inlet',
    'Water heater has no hot water outlet',
    'Pump has no pipe system connection',

    # ── Systems ──
    'Pipe system has no equipment at root',
    'System contains unconnected elements',
    'The calculated flow for this system is zero',
    'MEP system loop detected',
    'The family is not assigned to a system',
    'Pipe pressure drop exceeds allowable limit',
    'Insulation or lining host is invalid',

    # ── Drainage & Venting ──
    'Sanitary pipe has no vent riser assigned',
    'Drain is below finished floor level without a sump',
    'Grease trap is not connected to waste system',
    'Roof drain is not connected to storm system',

    # ── General / BIM Housekeeping ──
    'There are identical instances in the same place',
    'Constraint is not satisfied',
    'Tag has no host',
    'Element references a deleted element',
    'Dimension references deleted elements',
]
