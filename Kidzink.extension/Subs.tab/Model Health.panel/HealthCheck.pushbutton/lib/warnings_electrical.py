# -*- coding: utf-8 -*-
"""
Kidzink — Electrical Warning Library
Warning definitions for the Revit Health Check tool.
Each entry in KNOWN_WARNINGS is one health-score check.
WARNING_EXPLANATIONS provides the grey hint text shown below each type.

Discipline: Electrical (LV Power, Lighting, ELV)
Standards: ISO 19650, IEC 60364, BS 7671, NEC 2023,
           Dubai Authority MEP requirements, DEWA regulations

This file lives in:
  Kidzink Tools.extension/lib/warnings_electrical.py

IronPython 2.7 — no type hints, no f-strings.
© Archie C. Manza 2026
"""

WARNING_EXPLANATIONS = {

    # ── Circuits ──
    'Circuit is not defined':
        'An electrical device or fixture is not assigned to an electrical circuit. Assign it to a panel circuit before issuing drawings.',
    'Circuit has no load':
        'An electrical circuit exists but has no connected load. Add devices or remove the empty circuit from the panel.',
    'Circuit is overloaded':
        'The total connected load on the circuit exceeds the breaker rating or the NEC/IEC 80% continuous load rule. Redistribute loads or upsize the breaker.',
    'Circuit voltage drop exceeds limit':
        'The calculated voltage drop on the circuit exceeds 3% (branch) or 5% (total) per IEC/NEC recommendations. Upsize conductors or reduce circuit length.',
    'Circuit has no wire size specified':
        'No conductor size is set for this circuit. Define the wire gauge/CSA so conduit fill and voltage drop calculations are correct.',
    'Circuit has no conduit type specified':
        'The circuit has no conduit or wiring method assigned. Define the raceway type to complete specifications and coordination drawings.',
    'Phase balance is not within acceptable range':
        'Load distribution across phases A, B, C is unbalanced beyond the 10% tolerance. Redistribute single-phase circuits to balance the panel.',
    'Circuit length exceeds recommended maximum for gauge':
        'The circuit run is too long for the conductor size, resulting in excessive voltage drop. Upsize the wire or add a sub-distribution board closer to the load.',
    'Neutral conductor is missing from circuit':
        'A circuit requiring a neutral (single-phase loads, dimming systems) has no neutral defined. Add the neutral conductor to the circuit properties.',

    # ── Panels & Distribution ──
    'Panel schedule cannot be generated because the assigned distribution system is missing':
        'A panel has no distribution system defined. Define the voltage, phase, and wiring configuration in the panel electrical properties.',
    'Panel has exceeded its maximum number of circuits':
        'The panel has more circuits than its rated number of poles allows. Add a sub-panel or use a larger distribution board.',
    'Panel has no main breaker defined':
        'The main circuit breaker or incoming supply is not defined for this panel. Set the main device rating in the panel properties.',
    'Panel has no supply circuit':
        'The distribution board has no incoming feeder circuit connecting it to the upstream panel or transformer. Define the supply circuit.',
    'Transformer has no primary circuit':
        'The transformer has no primary (high-voltage side) circuit assigned. Connect it to the upstream distribution system.',
    'Transformer has no secondary circuit':
        'The transformer secondary is not connected to any downstream panel. Connect it to the LV distribution board.',
    'Distribution board is not connected to a power source':
        'A DB or MDB has no supply path to a generator, utility connection, or upstream panel. Trace and close the supply chain.',
    'UPS has no bypass or maintenance circuit':
        'The UPS has no bypass or maintenance supply defined. Add a static or manual bypass circuit per design standards.',

    # ── Devices & Fixtures ──
    'Lighting fixture is not assigned to a circuit':
        'A lighting fixture has no circuit assignment. Assign it to a lighting circuit on the appropriate panel.',
    'Lighting fixture has no switch control defined':
        'The fixture has no switching control (switch, occupancy sensor, or DALI group) assigned. Define the control in the fixture or circuit properties.',
    'Power device is not connected to a circuit':
        'A socket outlet, data point, or power device is unassigned. Connect it to a circuit before issuing construction documents.',
    'Device load exceeds single circuit capacity':
        'The load of this device exceeds the capacity of a single circuit. Provide a dedicated circuit or check the equipment schedule.',
    'Emergency lighting fixture has no emergency circuit':
        'An emergency or exit light is not connected to an emergency or UPS-backed circuit. Reassign it to the correct emergency circuit.',
    'ELV device has no system assignment':
        'A data, comms, AV, or security device is not assigned to an ELV system. Assign it to the appropriate system (data, CCTV, BMS, etc.).',
    'Lighting fixture has no space assignment':
        'A luminaire is placed but not associated with an MEP space. Place the fixture within a properly bounded space for lux calculations.',

    # ── Containment & Routing ──
    'Cable tray is not connected at one or both ends':
        'A cable tray segment has an open end. Connect it to a fitting, junction, or termination point.',
    'Cable tray fitting is not connected':
        'A cable tray fitting has an open connector. Join it to the adjacent tray or fitting.',
    'Conduit is not connected at one or both ends':
        'A conduit run has an open end. Connect it to a conduit fitting, pull box, or junction box.',
    'Cable tray fill exceeds maximum allowable':
        'The total cable fill in this tray section exceeds 40% of usable tray width (NEC/IEC standard). Add a parallel tray or increase tray width.',
    'Cable tray has no system type assigned':
        'The cable tray has no system type (Power, ELV, Fire, Data). Assign the correct system type to enforce separation rules.',

    # ── Earthing & Protection ──
    'Earthing conductor is not defined for panel':
        'No protective earth (PE) conductor is defined for this panel. Define the earthing conductor size per IEC 60364 / BS 7671.',
    'RCD protection is missing from circuit':
        'A circuit serving wet areas, outdoor loads, or socket outlets does not have RCD/GFCI protection assigned. Add an RCD to the circuit or panel.',
    'Surge protection device is missing from distribution board':
        'The DB has no SPD defined. Include a Type 1 or Type 2 SPD per IEC 62305 / local authority requirement.',

    # ── General / BIM Housekeeping ──
    'There are identical instances in the same place':
        'Two identical electrical elements are stacked on top of each other. Delete the duplicate to avoid double-counting in schedules.',
    'Constraint is not satisfied':
        'A locked dimension or alignment constraint cannot be maintained. Unlock or adjust the constraint.',
    'Tag has no host':
        'An annotation tag references a device or fixture that has been deleted. Remove the orphaned tag.',
    'Element references a deleted element':
        'An element still points to another element that no longer exists. Purge the broken reference.',
    'Linked file is missing':
        'A Revit link file cannot be found at its saved path. Relink the file or remove the broken reference.',
    'Dimension references deleted elements':
        'A dimension string references geometry that has been removed. Delete or re-host the dimension.',
}

KNOWN_WARNINGS = [

    # ── Circuits ──
    'Circuit is not defined',
    'Circuit has no load',
    'Circuit is overloaded',
    'Circuit voltage drop exceeds limit',
    'Circuit has no wire size specified',
    'Circuit has no conduit type specified',
    'Phase balance is not within acceptable range',
    'Circuit length exceeds recommended maximum for gauge',
    'Neutral conductor is missing from circuit',

    # ── Panels & Distribution ──
    'Panel schedule cannot be generated because the assigned distribution system is missing',
    'Panel has exceeded its maximum number of circuits',
    'Panel has no main breaker defined',
    'Panel has no supply circuit',
    'Transformer has no primary circuit',
    'Transformer has no secondary circuit',
    'Distribution board is not connected to a power source',
    'UPS has no bypass or maintenance circuit',

    # ── Devices & Fixtures ──
    'Lighting fixture is not assigned to a circuit',
    'Lighting fixture has no switch control defined',
    'Power device is not connected to a circuit',
    'Device load exceeds single circuit capacity',
    'Emergency lighting fixture has no emergency circuit',
    'ELV device has no system assignment',
    'Lighting fixture has no space assignment',

    # ── Containment & Routing ──
    'Cable tray is not connected at one or both ends',
    'Cable tray fitting is not connected',
    'Conduit is not connected at one or both ends',
    'Cable tray fill exceeds maximum allowable',
    'Cable tray has no system type assigned',

    # ── Earthing & Protection ──
    'Earthing conductor is not defined for panel',
    'RCD protection is missing from circuit',
    'Surge protection device is missing from distribution board',

    # ── General / BIM Housekeeping ──
    'There are identical instances in the same place',
    'Constraint is not satisfied',
    'Tag has no host',
    'Element references a deleted element',
    'Linked file is missing',
    'Dimension references deleted elements',
]
