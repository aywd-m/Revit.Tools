# -*- coding: utf-8 -*-
"""
Kidzink — Mechanical (HVAC) Warning Library
Warning definitions for the Revit Health Check tool.
Each entry in KNOWN_WARNINGS is one health-score check.
WARNING_EXPLANATIONS provides the grey hint text shown below each type.

Discipline: Mechanical / HVAC
Standards: ISO 19650, ASHRAE 90.1, SMACNA, Dubai Authority MEP requirements

This file lives in:
  Kidzink Tools.extension/lib/warnings_mechanical.py

IronPython 2.7 — no type hints, no f-strings.
© Archie C. Manza 2026
"""

WARNING_EXPLANATIONS = {

    # ── Spaces / Zones ──
    'Space is not in a properly enclosed region':
        'MEP space boundaries are not closed. Close the gap so the space can calculate volume and airflow correctly.',
    'Space Tag is outside of its Space':
        'A space tag sits outside its associated space boundary. Move the tag inside the space.',
    'Multiple Spaces are in the same enclosed region':
        'More than one MEP space element exists inside a single enclosed boundary. Delete the duplicate or add a separation line.',
    'Space has no upper limit':
        'The space upper limit is not set or references a deleted level. Set a valid upper limit level and offset.',
    'Space volume is not computed':
        'Volume computation is disabled in Area and Volume Computations. Enable it so airflow and load calculations are valid.',
    'Space is not placed in a zone':
        'The space has no zone assignment. Assign it to an HVAC zone so system sizing and energy analysis are accurate.',
    'Zone has no assigned spaces':
        'A zone object exists with no spaces assigned to it. Assign spaces or delete the empty zone.',

    # ── Ducts & Fittings ──
    'Duct is not connected at one or both ends':
        'A duct segment has an open connector at one or both ends. Connect it to a fitting, terminal, or equipment.',
    'Duct fitting is not connected':
        'A duct fitting (elbow, tee, transition, cap) has an open connector. Join it to the adjacent duct or fitting.',
    'Duct has no system type assigned':
        'The duct segment is not assigned to a duct system type (e.g. Supply Air, Return Air, Exhaust Air). Assign the correct system type.',
    'Duct flow direction is inconsistent with system':
        'Flow direction on the duct does not match the parent system. Check connector flow direction in the family and system type.',
    'Duct is undersized for design flow':
        'Calculated velocity or pressure drop exceeds acceptable limits for the duct size. Resize the duct to meet design criteria.',
    'Flexible duct length exceeds maximum':
        'A flexible duct segment is longer than the recommended maximum (typically 1.8 m / 6 ft per SMACNA). Shorten or replace with rigid duct.',
    'Duct static pressure is not within acceptable range':
        'The calculated static pressure for this duct branch is outside the system design range. Review duct sizing and system balancing.',
    'Duct has no insulation applied':
        'The duct segment has no insulation type assigned. Apply insulation per the project energy specification.',

    # ── Air Terminals & Equipment ──
    'Air terminal is not connected to a duct system':
        'An air terminal (diffuser, grille, register) is not connected to any duct. Connect it to a supply, return, or exhaust duct.',
    'Air terminal flow does not match space requirement':
        'The designed flow on the air terminal does not match the calculated space airflow requirement. Adjust the terminal flow or space load.',
    'Mechanical equipment has no system connection':
        'An AHU, FCU, or other mechanical unit has unconnected duct connectors. Connect all supply, return, and exhaust openings.',
    'Mechanical equipment is not placed on a valid host':
        'Equipment intended for a floor or ceiling is not properly hosted. Re-place it on the correct level or host element.',
    'Mechanical equipment has no electrical load defined':
        'Power consumption for this unit is not set. Define the electrical load so panel scheduling and energy calculations are correct.',
    'Fan coil unit has no hydronic connection':
        'An FCU has open hydronic (chilled water / heating water) connectors. Connect them to the pipe system.',

    # ── Systems ──
    'The calculated flow for this system is zero':
        'The duct system flow is zero. Check that equipment design values, terminal flows, and connector directions are set correctly.',
    'System contains unconnected elements':
        'One or more elements in a duct system are not fully connected. Trace the system to find and close the open connector.',
    'MEP system loop detected':
        'The duct system has a circular flow path. Remove the loop so system sizing and pressure calculations work correctly.',
    'Duct system has no air handling unit assigned':
        'The supply or return system has no AHU or fan equipment at its root. Assign or connect the correct equipment.',
    'Insulation or lining host is invalid':
        'Duct insulation or lining references a host that no longer exists or has changed. Remove and reapply the insulation or lining.',
    'The family is not assigned to a system':
        'A mechanical component has no system assignment. Assign it to the appropriate duct system.',

    # ── General / BIM Housekeeping ──
    'There are identical instances in the same place':
        'Two identical duct or equipment elements are stacked on top of each other. Delete the duplicate to avoid double-counting in schedules.',
    'Constraint is not satisfied':
        'A locked dimension or alignment constraint cannot be maintained. Unlock or adjust the constraint.',
    'Tag has no host':
        'An annotation tag references a duct or equipment element that has been deleted. Remove the orphaned tag.',
    'Element references a deleted element':
        'An element still points to another element that no longer exists. Purge the broken reference.',
    'Dimension references deleted elements':
        'A dimension string references geometry that has been removed. Delete or re-host the dimension.',
}

KNOWN_WARNINGS = [

    # ── Spaces / Zones ──
    'Space is not in a properly enclosed region',
    'Space Tag is outside of its Space',
    'Multiple Spaces are in the same enclosed region',
    'Space has no upper limit',
    'Space volume is not computed',
    'Space is not placed in a zone',
    'Zone has no assigned spaces',

    # ── Ducts & Fittings ──
    'Duct is not connected at one or both ends',
    'Duct fitting is not connected',
    'Duct has no system type assigned',
    'Duct flow direction is inconsistent with system',
    'Duct is undersized for design flow',
    'Flexible duct length exceeds maximum',
    'Duct static pressure is not within acceptable range',
    'Duct has no insulation applied',

    # ── Air Terminals & Equipment ──
    'Air terminal is not connected to a duct system',
    'Air terminal flow does not match space requirement',
    'Mechanical equipment has no system connection',
    'Mechanical equipment is not placed on a valid host',
    'Mechanical equipment has no electrical load defined',
    'Fan coil unit has no hydronic connection',

    # ── Systems ──
    'The calculated flow for this system is zero',
    'System contains unconnected elements',
    'MEP system loop detected',
    'Duct system has no air handling unit assigned',
    'Insulation or lining host is invalid',
    'The family is not assigned to a system',

    # ── General / BIM Housekeeping ──
    'There are identical instances in the same place',
    'Constraint is not satisfied',
    'Tag has no host',
    'Element references a deleted element',
    'Dimension references deleted elements',
]
