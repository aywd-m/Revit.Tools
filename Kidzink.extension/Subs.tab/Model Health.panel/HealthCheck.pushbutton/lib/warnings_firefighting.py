# -*- coding: utf-8 -*-
"""
Kidzink — Fire Fighting Warning Library
Warning definitions for the Revit Health Check tool.
Each entry in KNOWN_WARNINGS is one health-score check.
WARNING_EXPLANATIONS provides the grey hint text shown below each type.

Discipline: Fire Fighting / Fire Protection (FP)
Standards: ISO 19650, NFPA 13 / 14 / 20 / 72, BS EN 12845,
           Dubai Civil Defence (DCD) requirements, UAE Fire & Life Safety Code

This file lives in:
  Kidzink Tools.extension/lib/warnings_firefighting.py

IronPython 2.7 — no type hints, no f-strings.
© Archie C. Manza 2026
"""

WARNING_EXPLANATIONS = {

    # ── Sprinkler Pipes & Fittings ──
    'Sprinkler pipe is not connected at one or both ends':
        'A sprinkler pipe segment has an open connector. Connect it to a fitting, sprinkler head, or branch take-off.',
    'Sprinkler pipe fitting is not connected':
        'A sprinkler pipe fitting (elbow, tee, cross) has an open connector. Join it to the adjacent pipe or fitting.',
    'Sprinkler pipe has no system type assigned':
        'The pipe is not assigned to a fire protection system type (e.g. Wet Pipe, Dry Pipe, Pre-Action). Assign the correct FP system.',
    'Sprinkler pipe slope is insufficient for dry or pre-action system':
        'Dry-pipe and pre-action systems require a minimum 1:500 slope to drain. Adjust the pipe slope accordingly.',
    'Sprinkler pipe has no material specified':
        'No pipe material is defined. Specify the material (Schedule 40 steel, CPVC, etc.) for fabrication and specification accuracy.',
    'Sprinkler pipe velocity exceeds design limit':
        'The calculated water velocity in this pipe exceeds the allowable limit (typically 6 m/s). Upsize the pipe to reduce velocity.',
    'Sprinkler pipe has no hanger spacing defined':
        'Hanger spacing parameters are not set on this pipe run. Define hanger spacing per NFPA 13 requirements for the pipe size and material.',
    'Sprinkler pipe pressure drop exceeds system design':
        'Calculated pressure drop on this branch exceeds the hydraulic design limit. Upsize the pipe or rebalance the hydraulic calculation.',

    # ── Sprinkler Heads ──
    'Sprinkler head is not connected to a pipe system':
        'A sprinkler head has an open connector and is not part of any sprinkler system. Connect it to the branch pipe.',
    'Sprinkler head coverage area exceeds maximum':
        'The sprinkler head is protecting more floor area than the maximum allowed per NFPA 13 / DCD for its hazard classification. Add additional heads.',
    'Sprinkler head is too close to an obstruction':
        'A structural beam, duct, or other obstruction falls within the spray deflection zone of this head. Relocate the head or obstruction.',
    'Sprinkler head response type is incorrect for hazard':
        'The head response type (Standard, Quick Response, Extended Coverage) does not match the hazard classification of the space.',
    'Sprinkler head temperature rating is incorrect for environment':
        'The head temperature rating is not appropriate for the ambient temperature of this space (e.g. high-temperature zone needs 79°C or higher rated head).',
    'Sprinkler head has no K-factor defined':
        'No K-factor is set for this sprinkler head. Define the K-factor to enable hydraulic flow calculations.',
    'Upright sprinkler is installed in pendant position':
        'The sprinkler head orientation conflicts with its type. Upright heads must point up; pendant heads must point down.',
    'Sidewall sprinkler is too far from wall':
        'A sidewall sprinkler is installed beyond the maximum distance from the wall per NFPA 13. Relocate it within the specified range.',

    # ── Hose Reels, Hydrants & Standpipes ──
    'Hose reel is not connected to a pipe system':
        'A hose reel cabinet has an open connector. Connect it to the wet riser or hose reel distribution system.',
    'Fire hydrant is not connected to a pipe system':
        'A fire hydrant or landing valve has an open connector. Connect it to the fire main or wet riser.',
    'Standpipe / wet riser has no pump connection':
        'The wet riser or standpipe system has no fire pump or booster pump connected at its base. Connect the pump assembly.',
    'Hose reel coverage radius is not met':
        'Areas of the floor plan fall outside the 25 m hose reel reach. Add additional hose reels or relocate existing ones to achieve full coverage.',
    'Landing valve is at incorrect floor level':
        'A landing valve or hose cabinet is not positioned at the correct floor level offset. Adjust the placement per DCD requirements.',
    'Fire hydrant spacing exceeds maximum':
        'The distance between external hydrants exceeds the maximum spacing (typically 60 m for built-up areas). Add intermediate hydrants.',

    # ── Pumps & Tanks ──
    'Fire pump has no suction pipe connection':
        'The fire pump has an unconnected suction inlet. Connect it to the suction header or fire water storage tank.',
    'Fire pump has no discharge pipe connection':
        'The fire pump has an unconnected discharge outlet. Connect it to the fire main distribution system.',
    'Fire pump has no jockey pump defined':
        'No jockey (pressure maintenance) pump is defined for the fire pump set. Add a jockey pump to maintain system pressure.',
    'Fire water storage tank has no fill connection':
        'The fire water tank has no fill pipe connected. Connect it to the makeup water supply.',
    'Fire water storage tank has no outlet connection':
        'The fire water tank has no suction outlet connected to the pump. Connect the suction pipe.',
    'Fire water storage tank volume is below minimum':
        'The defined tank capacity is less than the minimum required storage for the system duration and flow rate per NFPA / DCD.',
    'Fire pump has no electrical supply defined':
        'No power circuit is assigned to the fire pump. Assign a dedicated supply circuit from the emergency power source.',
    'Fire pump has no diesel backup defined':
        'The fire pump set has no diesel backup pump defined. Add a diesel-driven pump per DCD and NFPA 20 requirements.',

    # ── Gaseous & Special Systems ──
    'FM200 / clean agent cylinder is not connected to nozzle':
        'A clean agent cylinder manifold has an open connector. Connect it to the discharge nozzle network.',
    'Gaseous suppression nozzle is not connected to agent system':
        'A suppression nozzle has no system connection. Connect it to the FM200, CO2, or inert gas pipe network.',
    'Gaseous suppression enclosure is not sealed':
        'The protected enclosure has gaps in its boundary. Seal all penetrations to maintain the agent concentration for the holding period.',
    'Kitchen hood suppression system nozzle not aimed at hazard':
        'A wet chemical nozzle is not correctly aimed at the cooking appliance hazard. Adjust orientation per the system design.',

    # ── Detection & Alarm (Passive) ──
    'Fire alarm device has no circuit assignment':
        'A detector, call point, sounder, or beacon is not assigned to a fire alarm loop or circuit. Assign it before issuing drawings.',
    'Detector spacing exceeds maximum for ceiling height':
        'The distance between smoke or heat detectors exceeds the maximum allowed for the ceiling height per BS 5839 / NFPA 72. Add additional detectors.',
    'Detector is within an excluded zone but not suppressed':
        'A detector is placed in a zone flagged as excluded (e.g. above a suspended ceiling) but is still active. Suppress or remove the device.',
    'Manual call point is obstructed or inaccessible':
        'A manual call point (break glass) is positioned behind an obstruction or above accessible reach height. Relocate it per code.',
    'Fire alarm panel has no power supply circuit':
        'The fire alarm control panel has no mains or emergency power circuit assigned. Define the supply circuit.',

    # ── General / BIM Housekeeping ──
    'There are identical instances in the same place':
        'Two identical fire protection elements are stacked on top of each other. Delete the duplicate to avoid double-counting in schedules.',
    'Constraint is not satisfied':
        'A locked dimension or alignment constraint cannot be maintained. Unlock or adjust the constraint.',
    'Tag has no host':
        'An annotation tag references a fire protection element that has been deleted. Remove the orphaned tag.',
    'Element references a deleted element':
        'An element still points to another element that no longer exists. Purge the broken reference.',
    'Linked file is missing':
        'A Revit link file cannot be found at its saved path. Relink the file or remove the broken reference.',
    'Dimension references deleted elements':
        'A dimension string references geometry that has been removed. Delete or re-host the dimension.',
}

KNOWN_WARNINGS = [

    # ── Sprinkler Pipes & Fittings ──
    'Sprinkler pipe is not connected at one or both ends',
    'Sprinkler pipe fitting is not connected',
    'Sprinkler pipe has no system type assigned',
    'Sprinkler pipe slope is insufficient for dry or pre-action system',
    'Sprinkler pipe has no material specified',
    'Sprinkler pipe velocity exceeds design limit',
    'Sprinkler pipe has no hanger spacing defined',
    'Sprinkler pipe pressure drop exceeds system design',

    # ── Sprinkler Heads ──
    'Sprinkler head is not connected to a pipe system',
    'Sprinkler head coverage area exceeds maximum',
    'Sprinkler head is too close to an obstruction',
    'Sprinkler head response type is incorrect for hazard',
    'Sprinkler head temperature rating is incorrect for environment',
    'Sprinkler head has no K-factor defined',
    'Upright sprinkler is installed in pendant position',
    'Sidewall sprinkler is too far from wall',

    # ── Hose Reels, Hydrants & Standpipes ──
    'Hose reel is not connected to a pipe system',
    'Fire hydrant is not connected to a pipe system',
    'Standpipe / wet riser has no pump connection',
    'Hose reel coverage radius is not met',
    'Landing valve is at incorrect floor level',
    'Fire hydrant spacing exceeds maximum',

    # ── Pumps & Tanks ──
    'Fire pump has no suction pipe connection',
    'Fire pump has no discharge pipe connection',
    'Fire pump has no jockey pump defined',
    'Fire water storage tank has no fill connection',
    'Fire water storage tank has no outlet connection',
    'Fire water storage tank volume is below minimum',
    'Fire pump has no electrical supply defined',
    'Fire pump has no diesel backup defined',

    # ── Gaseous & Special Systems ──
    'FM200 / clean agent cylinder is not connected to nozzle',
    'Gaseous suppression nozzle is not connected to agent system',
    'Gaseous suppression enclosure is not sealed',
    'Kitchen hood suppression system nozzle not aimed at hazard',

    # ── Detection & Alarm (Passive) ──
    'Fire alarm device has no circuit assignment',
    'Detector spacing exceeds maximum for ceiling height',
    'Detector is within an excluded zone but not suppressed',
    'Manual call point is obstructed or inaccessible',
    'Fire alarm panel has no power supply circuit',

    # ── General / BIM Housekeeping ──
    'There are identical instances in the same place',
    'Constraint is not satisfied',
    'Tag has no host',
    'Element references a deleted element',
    'Linked file is missing',
    'Dimension references deleted elements',
]
