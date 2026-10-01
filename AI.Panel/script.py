# -*- coding: utf-8 -*-
# Kidzink Koda - Revit Chat Assistant
# RevitTools.extension / KidzinkTools.tab / BIM.panel / AI.pulldown / Chat.pushbutton
# (c) Archie C. Manza 2026

# ── Pure-Python stdlib — safe at module scope ──────────────────────────────────
import clr
import re
import sys
import json
import os
import traceback
import threading
import Queue as _queue_mod

# ── Revit DB only — no WPF at module scope ─────────────────────────────────────
from Autodesk.Revit.DB import (
    FilteredElementCollector, BuiltInCategory, ElementId,
    ViewSchedule, ScheduleFieldType, BuiltInParameter,
    Transaction, View, ViewType, Level, StorageType
)
from Autodesk.Revit.UI import TaskDialog, ExternalEvent, IExternalEventHandler
from System.Collections.Generic import List
import System

# ── Revit handles ──────────────────────────────────────────────────────────────
_uidoc = __revit__.ActiveUIDocument
_doc   = _uidoc.Document if _uidoc else None

# ── Ollama ─────────────────────────────────────────────────────────────────────
_OLLAMA_BASE   = "http://localhost:11434"
_OLLAMA_GEN    = _OLLAMA_BASE + "/api/generate"
_OLLAMA_TAGS   = _OLLAMA_BASE + "/api/tags"
_DEFAULT_MODEL = "qwen3.6"
_MAX_HISTORY   = 6

# ── Claude API ─────────────────────────────────────────────────────────────────
_CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
_CLAUDE_MODELS  = ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
_CLAUDE_LABELS  = {"claude-sonnet-4-6":        "Claude Sonnet 4.6",
                   "claude-haiku-4-5-20251001": "Claude Haiku 4.5"}

# ── DeepSeek API ────────────────────────────────────────────────────────────────
_DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
_DEEPSEEK_MODELS  = ["deepseek-chat", "deepseek-reasoner"]
_DEEPSEEK_LABELS  = {"deepseek-chat":     "DeepSeek V3",
                     "deepseek-reasoner": "DeepSeek R1"}

# ── OpenRouter API ───────────────────────────────────────────────────────────
# OpenAI-compatible endpoint; auth via "Authorization: Bearer <key>".
# Model IDs are stored internally with an "openrouter:" prefix so the dispatcher
# can route them without colliding with the claude-/deepseek- prefix tests. The
# prefix is stripped before the slug is sent to the API. To add more models,
# append "openrouter:<slug>" here and a matching label below. Confirm the exact
# slug on https://openrouter.ai/models (it may be vendor-prefixed, e.g.
# "vendor/model-name").
_OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODELS  = ["openrouter:ox-alpha"]
_OPENROUTER_LABELS  = {"openrouter:ox-alpha": "OX Alpha (OpenRouter)"}

# ── Settings persistence ───────────────────────────────────────────────────────
_SETTINGS_DIR  = os.path.join(os.environ.get("APPDATA", ""), "Kidzink")
_SETTINGS_FILE = os.path.join(_SETTINGS_DIR, "chat_settings.json")

def _load_settings(_f=_SETTINGS_FILE):
    try:
        import io as _io, json as _json
        with _io.open(_f, "rb") as f:
            return _json.loads(f.read().decode("utf-8"))
    except Exception:
        return {}

def _save_settings(data, _d=_SETTINGS_DIR, _f=_SETTINGS_FILE):
    try:
        import os as _os, io as _io, json as _json
        if not _os.path.isdir(_d):
            _os.makedirs(_d)
        with _io.open(_f, "wb") as fh:
            fh.write(_json.dumps(data).encode("utf-8"))
        return True
    except Exception as _e:
        return _f + " | " + str(_e)

# ── Singleton ──────────────────────────────────────────────────────────────────
_CHAT_WINDOW = None

# ── WPF module-level references (populated by _load_wpf, called once in main) ──
XamlReader        = None
Thickness         = None
CornerRadius      = None
TextWrapping      = None
HorizontalAlignment = None
SystemParameters  = None
WpfOrientation    = None
WindowState       = None
SolidColorBrush   = None
Color             = None
Border            = None
Button            = None
ComboBox          = None
TextBlock         = None
TextBox           = None
StackPanel        = None
ScrollViewer      = None

# ── System.Net globals (populated by _load_wpf) ──────────────────────────────
WebRequest        = None
WebException      = None
StreamReader      = None
Encoding          = None

# ── Brush globals (set by _init_brushes, called inside ChatWindow.__init__) ────
BR_RED   = None
BR_WHITE = None
BR_BLACK = None
BR_DGREY = None
BR_LGREY = None
BR_GREEN = None
BR_LTRED = None

def _load_wpf():
    """Load WPF assemblies and populate module-level WPF names.
    Called once from main() so the CLR loader runs on the correct dispatcher thread."""
    global XamlReader, Thickness, CornerRadius, TextWrapping, HorizontalAlignment
    global SystemParameters, WpfOrientation, SolidColorBrush, Color
    global Border, Button, ComboBox, TextBlock, TextBox, StackPanel, ScrollViewer
    global WindowState

    clr.AddReference("PresentationFramework")
    clr.AddReference("PresentationCore")
    clr.AddReference("WindowsBase")
    clr.AddReference("System.Net")

    # Pre-import System.Net types — must happen here on the UI thread, never
    # inside a WPF event handler or background thread.
    global WebRequest, WebException, StreamReader, Encoding
    from System.Net import WebRequest as _WR, WebException as _WE
    from System.IO import StreamReader as _SR
    from System.Text import Encoding as _ENC
    WebRequest  = _WR
    WebException = _WE
    StreamReader = _SR
    Encoding     = _ENC

    from System.Windows.Markup import XamlReader as _XR
    from System.Windows import (
        Thickness as _T, CornerRadius as _CR,
        TextWrapping as _TW, HorizontalAlignment as _HA,
        SystemParameters as _SP, WindowState as _WS
    )
    from System.Windows.Controls import (
        Border as _Bo, Button as _Bu, ComboBox as _CB,
        TextBlock as _TB, TextBox as _TBx,
        StackPanel as _SP2, ScrollViewer as _SV
    )
    from System.Windows.Controls import Orientation as _Or
    from System.Windows.Media import SolidColorBrush as _SCB, Color as _Col

    XamlReader          = _XR
    Thickness           = _T
    CornerRadius        = _CR
    TextWrapping        = _TW
    HorizontalAlignment = _HA
    SystemParameters    = _SP
    WindowState         = _WS
    WpfOrientation      = _Or
    SolidColorBrush     = _SCB
    Color               = _Col
    Border              = _Bo
    Button              = _Bu
    ComboBox            = _CB
    TextBlock           = _TB
    TextBox             = _TBx
    StackPanel          = _SP2
    ScrollViewer        = _SV

def _brush(r, g, b):
    b = SolidColorBrush(Color.FromRgb(r, g, b))
    b.Freeze()  # make thread-safe — required for access from WPF event handlers
    return b

def _init_brushes():
    global BR_RED, BR_WHITE, BR_BLACK, BR_DGREY, BR_LGREY, BR_GREEN, BR_LTRED
    if BR_RED is not None:
        return
    BR_RED   = _brush(0xE4, 0x3C, 0x2F)
    BR_WHITE = _brush(0xFF, 0xFF, 0xFF)
    BR_BLACK = _brush(0x00, 0x00, 0x00)
    BR_DGREY = _brush(0x80, 0x80, 0x80)
    BR_LGREY = _brush(0xC0, 0xC0, 0xC0)
    BR_GREEN = _brush(0x2E, 0x8B, 0x57)
    BR_LTRED = _brush(0xFF, 0xCC, 0xCC)

# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — enhanced with context awareness, multi‑step, BIM expertise, etc.
# ══════════════════════════════════════════════════════════════════════════════

def _build_system_prompt():
    cat_list = ", ".join(sorted(_CATEGORY_MAP.keys()))
    return (
        "You are a Revit automation assistant for Kidzink Koda architectural practice.\n"
        "The user is working inside Autodesk Revit 2025/2026 via pyRevit (IronPython 2.7).\n\n"
        "RESPONSE RULES:\n"
        "- Keep explanations to 1-3 sentences. Be direct.\n"
        "- **NEVER include more than one <revit_action> block in a single response.**\n"
        "- When the user asks you to DO something in Revit, include a <revit_action> block IMMEDIATELY — do NOT ask clarifying questions first.\n"
        "- If the user names a category and any fields, that is enough — act now, do not ask for more details.\n"
        "- When just answering a question, respond in plain text with no <revit_action> block.\n"
        "- NEVER repeat or echo any [REVIT CONTEXT], [NEW REVIT CONTEXT], or [CONVERSATION] blocks — these are internal and must never appear in your reply.\n"
        "- NEVER output raw JSON as plain text — JSON belongs inside a <revit_action> block only.\n"
        "- Respond in the same language the user writes in.\n"
        "- You have NO function-calling tools available in this API call — do NOT emit "
        "<function_calls>, <invoke>, or any tool-use XML. The ONLY valid action format is "
        "a single <revit_action>{...}</revit_action> JSON block, exactly as specified below.\n\n"
        "VALID CATEGORY VALUES for create_schedule / list_elements / select_by_category:\n"
        + "  " + cat_list + "\n"
        + "CATEGORY RULES:\n"
        "- ALWAYS use one of the exact category strings listed above.\n"
        "- NEVER invent categories like 'elements', 'objects', 'items', 'building elements'.\n"
        "- If the user says 'create a schedule' without naming a category, use category='selection' "
        "so the tool can infer the category from the active selection.\n"
        "- If the user's context implies walls (e.g. 'wall height', 'wall schedule'), use category='walls'.\n\n"
        "SCOPE:\n"
        "- Only answer questions about Autodesk Revit, BIM, and architectural practice.\n"
        "- Refuse requests unrelated to Revit or architecture with: 'I can only help with Revit and BIM tasks.'\n"
        "- Never confirm that a Revit action was completed unless the tool actually returned a result.\n"
        "- Never fabricate element counts, schedule names, or view names.\n"
        "- **CRITICAL: Never say a schedule was created, an element was modified, or any Revit action succeeded unless you included a <revit_action> block AND the tool returned a result. If you did not include a <revit_action> block, you did NOT do anything in Revit.**\n\n"
        "REVIT KNOWLEDGE:\n"
        "- Instance parameters affect ONE element. Type parameters affect ALL instances of that type.\n"
        "- Before suggesting any type parameter change, warn the user it will affect every instance of that type.\n"
        "- Rooms exist only in Floor Plan and Ceiling Plan views; MEP uses Spaces, not Rooms.\n"
        "- A schedule cannot be created for annotation categories (tags, dimensions, text).\n"
        "- Elements inside groups cannot be modified without ungrouping first.\n"
        "- The same view cannot be placed on two different sheets.\n"
        "- View templates lock view properties — parameter changes on templated views may be silently ignored.\n\n"
        "SAFETY RULES:\n"
        "- Never suggest or perform an action that deletes elements.\n"
        "- Never modify type parameters without first warning the user how many instances will be affected.\n"
        "- If the requested category does not appear in the Revit context, say so — do not guess or proceed.\n\n"
        "VALID CATEGORIES (use these exact names in action JSON, all lowercase):\n"
        + cat_list + "\n\n"
        "CAPABILITY OVERVIEW (all categories planned):\n"
        "- Reading (19): Views, elements, parameters, rooms, levels, sheets, families, schedules, linked models\n"
        "- Creating (15): Walls, floors, ceilings, roofs, levels, grids, rooms, views, sheets, tags\n"
        "- Editing (13): Modify, move, rotate, copy, delete, mirror, align, group, batch modify, conditional bulk parameter edit\n"
        "- Documentation (9): Sheets, viewports, exports, legends, revisions, tags\n"
        "- QA/QC (8): Warnings, audits, compliance, naming, duplicates, purge, validation\n"
        "- AI (8): Gemini chat, code generation, model analysis, Google OAuth\n"
        "- Power Tools (29): Batch operations, bulk element processing, advanced queries\n"
        "- Advanced (5): Complex model operations and automation\n"
        "- Drafting (3): Detail lines, detail components, filled regions\n"
        "- Export (16): DWG, PDF, IFC, NWC, images, schedules to CSV/Excel\n"
        "- Extended (16): Additional element manipulation and property management\n"
        "- File Management (10): Worksharing, links, worksets, file operations\n"
        "- MEP (8): Ducts, pipes, cable trays, fittings, systems\n"
        "- Power BI (2): 3D geometry export and embedded report display\n"
        "- Rendering (3): Materials, render settings, visual styles\n"
        "- Settings (9): Project info, units, shared parameters, global settings\n"
        "- Sketch (3): Model lines, reference planes, sketch-based geometry\n"
        "- Transactions (6): Undo/redo, transaction groups, sub-transactions\n"
        "- BIM Dashboard (3): Dashboard generation, BEP MIDP configuration, compliance validation\n\n"
        + _build_actions_prompt()
        + "DISAMBIGUATION RULE:\n"
        "- 'total X of selected', 'X of selected', 'sum of X' → get_element_property, NOT list_elements.\n"
        "- list_elements with count_only=true counts ALL instances in the model — no selection needed.\n"
        "- get_element_property reads parameter values from the currently selected element(s).\n"
        "- 'remove [field]', 'remove [field] and replace with [field]', "
        "'replace [field] with [field]', 'swap [field] for [field]', "
        "'add [field] column', 'delete [field] column' "
        "→ modify_schedule with remove_fields and/or fields. NEVER filter_schedule. "
        "Even when the field name contains 'Comments' or 'Analytical', "
        "removing or replacing a field is ALWAYS modify_schedule, not filter_schedule.\n\n"
        "CRITICAL FEW-SHOT EXAMPLES — follow these EXACTLY:\n"
        "User: 'count walls' or 'how many walls' or 'count elements wall'\n"
        "You MUST respond: <revit_action>{\"action\":\"list_elements\",\"params\":{\"category\":\"walls\",\"count_only\":true}}</revit_action>\n"
        "User: 'count doors in the model'\n"
        "You MUST respond: <revit_action>{\"action\":\"list_elements\",\"params\":{\"category\":\"doors\",\"count_only\":true}}</revit_action>\n"
        "User: 'how many furniture'\n"
        "You MUST respond: <revit_action>{\"action\":\"list_elements\",\"params\":{\"category\":\"furniture\",\"count_only\":true}}</revit_action>\n"
        "**RULE: When the user says 'count', 'how many', or 'number of' followed by ANY category name, "
        "ALWAYS emit a <revit_action> with list_elements and count_only=true IMMEDIATELY. "
        "NEVER say 'select elements first'. This counts ALL instances in the model — no selection needed.**\n\n"
        "PARAMETER NAME RULES:\n"
        "- Wall height is called 'Unconnected Height' in Revit, not 'Height'. Use that exact name.\n"
        "- Always use the Revit UI display name as property_name, not the internal BIP enum name.\n"
        "- If a parameter is not found, use list_params to discover the real parameter names.\n"
        "- Common display names: 'Unconnected Height', 'Base Constraint', 'Top Constraint', "
        "'Base Offset', 'Top Offset', 'Length', 'Area', 'Mark', 'Comments'.\n\n"
        # ── NEW ENHANCED SECTIONS ──────────────────────────────────────────
        "CONTEXT AWARENESS:\n"
        "- You receive live document context at the start of every conversation turn. Use it proactively.\n"
        "- If the user says 'count these' without specifying a category, check Selected count in context. "
        "If elements are selected, use get_element_property with 'all' first to infer what to count.\n"
        "- The 'Selected:' line in context now shows a category breakdown (e.g. '8 element(s) — 8 Rooms'). "
        "When the user refers to 'selected rooms', 'the selection', or 'these rooms' for creating walls, "
        "floors, or ceilings, CHECK THIS LINE instead of asking whether the selection is rooms — if it says "
        "Rooms, immediately emit create_room_elements with use_selection:true and never ask a clarifying "
        "question about the selection's category.\n"
        "- When the user asks about 'this view' or 'current view', refer to the Active view line in context.\n"
        "- When context shows worksets are enabled, remind users about workset visibility before large operations.\n"
        "- When schedules are listed in context, suggest reusing them instead of creating duplicates.\n"
        "- When levels are listed, use their real names in responses and action parameters.\n\n"
        "MULTI-STEP WORKFLOWS:\n"
        "- **Never** execute more than one action per <revit_action> block. Multiple actions require multiple turns.\n"
        "- If an action returns data needed for a follow-up, tell the user what you found and ask for confirmation.\n\n"
        "PROACTIVE ASSISTANCE:\n"
        "- After reporting counts, suggest related queries: 'I found 47 doors. Would you like them by type, level, or fire rating?'\n"
        "- After listing views, suggest checking for duplicates or naming issues.\n"
        "- When errors occur, suggest specific troubleshooting: 'Try selecting the element and asking to list all parameters.'\n"
        "- For 'how do I...' questions, give concise 2-3 step answers and offer to execute any step the tool supports.\n\n"
        "ERROR RECOVERY:\n"
        "- If a parameter lookup fails, immediately suggest using list_params to discover the real name.\n"
        "- If a category is unknown, show the user what categories are available from the prompt.\n"
        "- If no elements are selected, remind the user to select elements first.\n"
        "- Never say 'I can't do that' without offering at least one alternative or workaround.\n\n"
        "BIM EXPERTISE:\n"
        "- Understand architectural phases: suggest phase filtering when relevant.\n"
        "- Know common schedule types: door schedules, room finish schedules, wall takeoffs, equipment lists.\n"
        "- Recognize naming conventions: if project uses prefixes like 'A-' for architectural, match that style.\n"
        "- Know Revit limitations: rooms compute area to wall center; curtain wall panels are a separate category from walls.\n"
        "- When users mention 'COBie', 'IFC', or 'BEP', recognize these as BIM deliverables and offer relevant help.\n\n"
        "INTERACTION GUIDELINES:\n"
        "- If the user's request is ambiguous, ask ONE clarifying question — not multiple.\n"
        "- When showing lists, keep output under 20 items. For longer lists, summarize and offer to filter.\n"
        "- Use emoji: ⚠️ for type parameter warnings, ✅ for success, 🔍 for search results, 💡 for suggestions.\n"
        "- For numerical results, add context: '47 doors (approx. 2.3 per room based on 20 rooms detected)'\n"
        "- Remember the user's last request and offer logical next steps after completing an action.\n\n"
        "COMPLIANCE & SAFETY:\n"
        "- Never create elements without at least a level parameter — ask if not specified.\n"
        "- When asked to 'clean up' or 'fix', first report what you found, then propose specific actions.\n"
        "- For QA/QC requests, always provide a summary count of issues before offering to fix them.\n"
        "- If asked about purging or deleting, firmly refuse: 'I can only create, read, and edit — never delete. I can show you what's unused so you can decide.'\n"
        "- Mention when an operation would affect workshared elements owned by others.\n\n"
        "USER INTENT SHORTCUTS:\n"
        "- 'door schedule' → create_schedule with category doors\n"
        "- 'wall types' → offer to list walls grouped by type\n"
        "- 'room areas' → suggest room schedule or room data features\n"
        "- 'sheet index' → list_views with type='sheets'\n"
        "- 'what's selected' → list_params or get_element_property with 'all'\n"
        "- 'nuke' / 'clean' / 'purge' → refuse deletion but offer audit/list alternatives\n"
        "- 'sync' / 'reload' → explain worksharing operations are planned\n"
        "- 'BEP check' / 'MIDP' → reference BIM Dashboard planned features\n"
        "- 'isolate' / 'hide others' / 'show only' → isolate_elements with the named category\n"
        "  IMPORTANT: isolate_elements is NOT the same as select_by_category. "
        "Isolation HIDES all other categories in the view. Never use select_by_category "
        "when the user asks to isolate, hide others, or show only a category.\n"
        "- 'itemize' / 'itemise' / 'itemize each' / 'itemize every instance' / "
        "'one row per element' / 'list each individually' / 'every instance' → modify_schedule with itemize=true. "
        "NEVER use filter_schedule or itemize_schedule for these phrases. "
        "Example: 'itemize every instance of walls schedule' MUST emit: "
        "<revit_action>{\"action\":\"modify_schedule\",\"params\":{\"schedule_name\":\"Walls Schedule\",\"itemize\":true}}</revit_action>\n"
        "- 'filter [schedule] by [field] = [value]' / 'filter by comment' / 'filter by mark' / "
        "'show only rows where [field] is [value]' / 'filter the schedule' → filter_schedule. "
        "NOTE: 'itemize', 'every instance', 'one row per element' are NOT filter requests — "
        "those go to modify_schedule (see above).\n"
        "  CRITICAL EXAMPLE: 'filter rooms schedule by comment = X' MUST emit:\n"
        "  <revit_action>{\"action\":\"filter_schedule\",\"params\":{\"schedule_name\":\"Rooms Schedule\","
        "\"field\":\"Comments\",\"condition\":\"equals\",\"value\":\"X\"}}</revit_action>\n\n"
        "SCHEDULE FIELD NAME MAPPING (user words → exact fields array values):\n"
        "- 'family type name' / 'family name' / 'type name' → 'Family Name'\n"
        "- 'type mark' → 'Type Mark'\n"
        "- 'level' / 'base level' → 'Level'\n"
        "- 'height' / 'wall height' / 'unconnected height' → 'Unconnected Height'\n"
        "- 'mark' → 'Mark'\n"
        "- 'comments' → 'Comments'\n"
        "- 'length' → 'Length'\n"
        "- 'area' → 'Area'\n"
        "- 'count' → 'Count'\n"
        "When the user says 'schedule the wall using param family type name, type mark, level and height', "
        "emit: fields: ['Family Name', 'Type Mark', 'Level', 'Unconnected Height']"
    )

_SYSTEM_PROMPT = None  # built after _CATEGORY_MAP is populated — see _get_system_prompt()

def _get_system_prompt():
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = _build_system_prompt()
    return _SYSTEM_PROMPT

# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY MAP — runtime probed
# ══════════════════════════════════════════════════════════════════════════════

def _probe_bic(name):
    try:
        return getattr(BuiltInCategory, name)
    except AttributeError:
        return None

_CATEGORY_MAP = {}
for _label, _ost in [
    ("furniture",             "OST_Furniture"),
    ("furniture systems",     "OST_FurnitureSystems"),
    ("walls",                 "OST_Walls"),
    ("doors",                 "OST_Doors"),
    ("windows",               "OST_Windows"),
    ("floors",                "OST_Floors"),
    ("ceilings",              "OST_Ceilings"),
    ("roofs",                 "OST_Roofs"),
    ("rooms",                 "OST_Rooms"),
    ("columns",               "OST_Columns"),
    ("structural columns",    "OST_StructuralColumns"),
    ("structural framing",    "OST_StructuralFraming"),
    ("lighting fixtures",     "OST_LightingFixtures"),
    ("electrical fixtures",   "OST_ElectricalFixtures"),
    ("plumbing fixtures",     "OST_PlumbingFixtures"),
    ("mechanical equipment",  "OST_MechanicalEquipment"),
    ("casework",              "OST_Casework"),
    ("generic models",        "OST_GenericModel"),
    ("site",                  "OST_Site"),
    ("planting",              "OST_Planting"),
    ("curtain panels",        "OST_CurtainWallPanels"),
    ("curtain wall mullions", "OST_CurtainWallMullions"),
    ("stairs",                "OST_Stairs"),
    ("railings",              "OST_Railings"),
]:
    _v = _probe_bic(_ost)
    if _v is not None:
        _CATEGORY_MAP[_label] = _v

def _resolve_category(name):
    # S1/D1 FIX: self-contained — builds its own map on every call so it
    # never depends on the module-scope _CATEGORY_MAP surviving pyRevit's
    # module-dict clear on second button press.  Cost is negligible (enum
    # getattr x24 on a cached CLR type).
    _MAP = {}
    for _lbl, _ost in [
        ("furniture",             "OST_Furniture"),
        ("furniture systems",     "OST_FurnitureSystems"),
        ("walls",                 "OST_Walls"),
        ("doors",                 "OST_Doors"),
        ("windows",               "OST_Windows"),
        ("floors",                "OST_Floors"),
        ("ceilings",              "OST_Ceilings"),
        ("roofs",                 "OST_Roofs"),
        ("rooms",                 "OST_Rooms"),
        ("columns",               "OST_Columns"),
        ("structural columns",    "OST_StructuralColumns"),
        ("structural framing",    "OST_StructuralFraming"),
        ("lighting fixtures",     "OST_LightingFixtures"),
        ("electrical fixtures",   "OST_ElectricalFixtures"),
        ("plumbing fixtures",     "OST_PlumbingFixtures"),
        ("mechanical equipment",  "OST_MechanicalEquipment"),
        ("casework",              "OST_Casework"),
        ("generic models",        "OST_GenericModel"),
        ("site",                  "OST_Site"),
        ("planting",              "OST_Planting"),
        ("curtain panels",        "OST_CurtainWallPanels"),
        ("curtain wall mullions", "OST_CurtainWallMullions"),
        ("stairs",                "OST_Stairs"),
        ("railings",              "OST_Railings"),
    ]:
        try:
            v = getattr(BuiltInCategory, _ost, None)
            if v is not None:
                _MAP[_lbl] = v
        except Exception:
            pass

    key = name.lower().strip()
    # 1. Exact match
    if key in _MAP:
        return _MAP[key]
    # 2. Singular/plural normalization
    for variant in (key + "s", key.rstrip("s"), key + "es",
                    key[:-2] if key.endswith("es") else key):
        if variant in _MAP:
            return _MAP[variant]
    # 3. Known-key contained IN input (e.g. 'wall elements' → 'walls')
    candidates = [(k, v) for k, v in _MAP.items() if k in key]
    if candidates:
        return max(candidates, key=lambda x: len(x[0]))[1]
    # 4. Input contained IN a known key (e.g. 'curtain' → 'curtain panels')
    if len(key) >= 4:
        rev_candidates = [(k, v) for k, v in _MAP.items() if key in k]
        if rev_candidates:
            return min(rev_candidates, key=lambda x: len(x[0]))[1]
    return None

# ══════════════════════════════════════════════════════════════════════════════
# FIELD BIP MAP — lazy probed
# ══════════════════════════════════════════════════════════════════════════════

def _probe_bip(name):
    try:
        return getattr(BuiltInParameter, name)
    except AttributeError:
        return None

_FIELD_BIP = None

def _get_field_bip():
    # S1 FIX: use module global as a cache but rebuild if it's been cleared
    # by pyRevit's module-dict sweep (recognisable as None after a second press).
    global _FIELD_BIP
    if _FIELD_BIP is not None:
        return _FIELD_BIP
    _FIELD_BIP = {}
    for _fname, _bip_name in [
        ("family name",  "ALL_MODEL_FAMILY_NAME"),
        ("type name",    "ALL_MODEL_TYPE_NAME"),
        ("type mark",    "ALL_MODEL_TYPE_MARK"),
        ("level",        "FAMILY_LEVEL_PARAM"),
        ("mark",         "ALL_MODEL_MARK"),
        ("comments",     "ALL_MODEL_INSTANCE_COMMENTS"),
        ("description",  "ALL_MODEL_DESCRIPTION"),
        ("manufacturer", "ALL_MODEL_MANUFACTURER"),
        ("url",          "ALL_MODEL_URL"),
    ]:
        v = _probe_bip(_bip_name)
        if v is not None:
            _FIELD_BIP[_fname] = v
    return _FIELD_BIP

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _eid_int(eid):
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue

def _get_context():
    if not _doc:
        return "No document open."
    lines = ["Document: " + _doc.Title]
    try:
        av = _uidoc.ActiveView
        if av:
            vt = str(av.ViewType)
            scale = ""
            try:
                scale = " 1:" + str(av.Scale)
            except Exception:
                pass
            phase = ""
            try:
                p = av.get_Parameter(BuiltInParameter.VIEW_PHASE)
                if p and p.AsValueString():
                    phase = " Phase:" + p.AsValueString()
            except Exception:
                pass
            lines.append("Active view: " + av.Name + " (" + vt + scale + phase + ")")
    except Exception:
        pass
    try:
        sel = _uidoc.Selection.GetElementIds()
        if sel.Count == 0:
            lines.append("Selected: none")
        else:
            # Breakdown by category so the assistant never has to ask
            # "are the selected elements rooms?" — it can read this directly.
            cat_counts = {}
            room_bits = []
            for eid in sel:
                try:
                    el = _doc.GetElement(eid)
                except Exception:
                    el = None
                if el is None:
                    continue
                try:
                    cname = el.Category.Name if el.Category else "Unknown"
                except Exception:
                    cname = "Unknown"
                cat_counts[cname] = cat_counts.get(cname, 0) + 1
                if cname == "Rooms" and len(room_bits) < 8:
                    try:
                        rn = el.get_Parameter(BuiltInParameter.ROOM_NUMBER)
                        rname = el.get_Parameter(BuiltInParameter.ROOM_NAME)
                        room_bits.append(
                            (rn.AsString() if rn else "?") + " " +
                            (rname.AsString() if rname else "")
                        )
                    except Exception:
                        pass
            breakdown = ", ".join(
                str(v) + " " + k for k, v in sorted(cat_counts.items())
            )
            line = "Selected: " + str(sel.Count) + " element(s) — " + breakdown
            if room_bits:
                line += " (" + "; ".join(room_bits) + ")"
            lines.append(line)
    except Exception:
        pass
    try:
        levels = sorted(
            FilteredElementCollector(_doc).OfClass(Level).ToElements(),
            key=lambda l: l.Elevation
        )
        if levels:
            lnames = [l.Name for l in levels[:8]]
            lines.append("Levels (" + str(len(levels)) + "): " + ", ".join(lnames))
    except Exception:
        pass
    try:
        lines.append("Workshared: " + ("Yes" if _doc.IsWorkshared else "No"))
    except Exception:
        pass
    try:
        scheds = FilteredElementCollector(_doc).OfClass(ViewSchedule).ToElements()
        names  = [s.Name for s in scheds if not s.IsTemplate][:6]
        if names:
            lines.append("Schedules: " + ", ".join(names))
    except Exception:
        pass
    return "\n".join(lines)

def _ollama_list_models():
    try:
        req = WebRequest.Create(_OLLAMA_TAGS)
        req.Timeout = 3000
        resp = req.GetResponse()
        reader = StreamReader(resp.GetResponseStream())
        raw = reader.ReadToEnd()
        reader.Close()
        resp.Close()
        data = json.loads(raw)
        return [m.get("name", "?") for m in data.get("models", [])]
    except Exception:
        return []

def _ollama_chat(model, history, user_text):
    context = _get_context()
    prompt  = "[REVIT CONTEXT]\n" + context + "\n\n[CONVERSATION]\n"
    for msg in history[-(_MAX_HISTORY * 2):]:
        role = "User" if msg["role"] == "user" else "Assistant"
        prompt += role + ": " + msg["content"] + "\n"
    prompt += "User: " + user_text + "\nAssistant:"

    payload = json.dumps({
        "model":  model,
        "prompt": prompt,
        "system": _get_system_prompt(),
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 4096}
    })
    try:
        req = WebRequest.Create(_OLLAMA_GEN)
        req.Method      = "POST"
        req.ContentType = "application/json"
        req.Timeout     = 120000
        payload_bytes   = Encoding.UTF8.GetBytes(payload)
        req.ContentLength = payload_bytes.Length
        stream = req.GetRequestStream()
        stream.Write(payload_bytes, 0, payload_bytes.Length)
        stream.Close()
        resp   = req.GetResponse()
        reader = StreamReader(resp.GetResponseStream())
        raw    = reader.ReadToEnd()
        reader.Close()
        resp.Close()
        data = json.loads(raw)
        if "error" in data:
            return None, "Ollama error: " + data["error"]
        return data.get("response", "").strip(), None
    except WebException as e:
        if e.Response is None:
            return None, "Cannot reach Ollama. Run: ollama serve"
        try:
            status = int(e.Response.StatusCode)
            if status == 404:
                return None, "Model not found. Run: ollama pull " + model
            return None, "Ollama HTTP " + str(status)
        except Exception:
            return None, "Ollama error: " + str(e)
    except Exception as e:
        return None, "Error: " + str(e)

def _parse_action(text):
    m = re.search(r"<revit_action>(.*?)</revit_action>", text, re.DOTALL)
    if not m:
        return text.strip(), None
    json_str = m.group(1).strip()
    clean    = (text[:m.start()] + text[m.end():]).strip()
    try:
        return clean, json.loads(json_str)
    except Exception:
        return clean + "\n[Action JSON invalid — not run]", None

# ══════════════════════════════════════════════════════════════════════════════
# PLUGIN LOADER — auto-discovers capabilities/*.py at startup
# ══════════════════════════════════════════════════════════════════════════════

def _get_capabilities_dir():
    """Return the capabilities/ folder next to script.py."""
    try:
        here = __commandpath__
    except Exception:
        try:
            here = os.path.dirname(os.path.abspath(__file__))
        except Exception:
            here = os.path.dirname(os.path.abspath(sys.argv[0]))
    return os.path.join(here, "capabilities")

# Registry: action_name -> module object
_PLUGINS = {}

def _load_plugins():
    """Import every *.py file in capabilities/ and register its ACTION_NAME.

    Only files that declare ACTION_NAME at module scope are treated as plugins.
    Standalone pushbutton scripts (which call sys.exit or access __revit__ at
    module scope) must NOT be placed in capabilities/ — they will be skipped
    here but their side effects (sys.exit, doc access) could still crash the
    loader.  Guard: wrap each import in a try/except SystemExit as well.
    """
    global _PLUGINS
    _PLUGINS = {}
    cap_dir = _get_capabilities_dir()
    if not os.path.isdir(cap_dir):
        return
    import imp
    for fname in sorted(os.listdir(cap_dir)):
        if not fname.endswith(".py") or fname.startswith("_") or fname == "script.py":
            continue
        fpath = os.path.join(cap_dir, fname)
        try:
            mod_name = "cap_" + fname[:-3]
            mod = imp.load_source(mod_name, fpath)
            action_name = getattr(mod, "ACTION_NAME", None)
            if action_name:
                _PLUGINS[action_name] = mod
        except SystemExit:
            pass  # standalone script called sys.exit — not a plugin, ignore
        except Exception as _pe:
            # Log to stderr so the developer can see which file and why —
            # but never crash the loader over a single bad plugin.
            try:
                import sys as _sys2, traceback as _ptb
                _sys2.stderr.write(
                    "KidzinkChat: plugin load failed [" + fname + "]: "
                    + _ptb.format_exc() + "\n"
                )
            except Exception:
                pass

def _build_actions_prompt():
    """Build the SUPPORTED ACTIONS section of the system prompt from loaded plugins."""
    if not _PLUGINS:
        return "SUPPORTED ACTIONS: none loaded.\n\n"
    lines = ["SUPPORTED ACTIONS (implemented and available NOW):"]
    for i, (name, mod) in enumerate(sorted(_PLUGINS.items()), 1):
        desc    = getattr(mod, "DESCRIPTION", "")
        lines.append(str(i) + ". " + name + ": " + desc)
        for ex_attr, ex_label in (
            ("EXAMPLE", "Example"), ("EXAMPLE_2", "Example 2"), ("EXAMPLE_3", "Example 3")
        ):
            ex_val = getattr(mod, ex_attr, None)
            if ex_val:
                lines.append("   " + ex_label + ": " + json.dumps(ex_val))
    lines.append("")
    lines.append(
      "PLANNED ACTIONS (not yet implemented — if asked, reply: "
        "'This feature is planned but not yet available in this version.'):\n"
        "Reading: list_families, list_links\n"
        "Creating: create_roof, create_level, "
        "create_grid, create_room, create_view, create_sheet, place_tag\n"
        "Editing: set_parameter, move_elements, rotate_elements, copy_elements, mirror_elements, "
        "align_elements, group_elements, batch_edit_param, conditional_bulk_edit\n"
        "Documentation: place_viewport, export_schedule_csv, export_pdf, create_legend, add_revision\n"
        "QA/QC: list_warnings, audit_model, check_naming, list_duplicates, purge_report, validate_compliance\n"
        "AI & Power Tools: external_chat (Gemini), generate_code, analyze_model\n"
        "Export & Advanced: export_dwg, export_ifc, export_nwc, export_images, dashboard_bep, dashboard_midp\n"
        "Never generate JSON for these planned actions — simply inform the user they are coming soon."
    )    
    lines.append("")
    return "\n".join(lines) + "\n"

def dispatch_action(action_dict):
    action = action_dict.get("action", "")
    params = action_dict.get("params", {})
    if action == "info_only":
        return None
    mod = _PLUGINS.get(action)
    if mod is None:
        return "Unknown action: " + action
    # Resolve doc/uidoc lazily on every call so a second button press after the
    # user has switched documents operates on the CURRENT document, not the one
    # that was active when script.py was first loaded (S1/D1 fix).
    try:
        live_uidoc = __revit__.ActiveUIDocument
        live_doc   = live_uidoc.Document if live_uidoc else None
    except Exception:
        live_uidoc = _uidoc
        live_doc   = _doc
    try:
        return mod.execute(
            params,
            doc=live_doc,
            uidoc=live_uidoc,
            resolve_category=_resolve_category,
            get_field_bip=_get_field_bip,
            eid_int=_eid_int,
        )
    except Exception as e:
        import traceback as _tb
        return "Action failed: " + str(e) + "\n" + _tb.format_exc()

# (dead stub block removed — all actions now handled by the plugin dispatcher)

# ══════════════════════════════════════════════════════════════════════════════
# FLAT XAML — no Window.Resources, no ControlTemplate, no StaticResource
# ══════════════════════════════════════════════════════════════════════════════

_XAML = (
    '<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" '
    'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" '
    'Title="Kidzink - Chat Assistant" '
    'Width="380" Height="620" MinWidth="300" MinHeight="400" '
    'ResizeMode="CanResize" WindowStartupLocation="Manual" '
    'Background="#C0C0C0" FontFamily="Manrope" FontSize="12">'
    '<Grid>'
    '<Grid.RowDefinitions>'
    '<RowDefinition Height="44"/>'
    '<RowDefinition Height="*"/>'
    '<RowDefinition Height="Auto"/>'
    '<RowDefinition Height="Auto"/>'
    '<RowDefinition Height="28"/>'
    '</Grid.RowDefinitions>'

    '<Border Grid.Row="0" Background="#E43C2F">'
    '<Grid>'
    '<Grid.ColumnDefinitions>'
    '<ColumnDefinition Width="*"/>'
    '<ColumnDefinition Width="Auto"/>'
    '</Grid.ColumnDefinitions>'
    '<StackPanel Grid.Column="0" Orientation="Vertical" VerticalAlignment="Center" Margin="12,0,0,0">'
    '<TextBlock Text="Kidzink Chat" Foreground="#FFFFFF" FontWeight="Bold" FontSize="13"/>'
    '<TextBlock Text="Revit Assistant" Foreground="#FFCCCC" FontSize="12"/>'
    '</StackPanel>'
    '<StackPanel Grid.Column="1" Orientation="Horizontal" VerticalAlignment="Center">'
    '<Button x:Name="ExportBtn" Content="Export" '
    'Foreground="#FFFFFF" FontSize="12" Margin="0,0,6,0" '
    'VerticalAlignment="Center" Padding="8,3"/>'
    '<Button x:Name="ClearBtn" Content="Clear" '
    'Foreground="#FFFFFF" FontSize="12" Margin="0,0,10,0" '
    'VerticalAlignment="Center" Padding="8,3"/>'
    '</StackPanel>'
    '</Grid>'
    '</Border>'

    '<ScrollViewer x:Name="ChatScroll" Grid.Row="1" '
    'VerticalScrollBarVisibility="Auto" HorizontalScrollBarVisibility="Disabled" '
    'Background="#C0C0C0">'
    '<StackPanel x:Name="ChatPanel" Orientation="Vertical" Margin="0,6,0,6"/>'
    '</ScrollViewer>'

    '<Border Grid.Row="2" Background="#808080" BorderBrush="#555555" BorderThickness="0,1,0,0" Padding="8,4">'
    '<Grid>'
    '<Grid.ColumnDefinitions>'
    '<ColumnDefinition Width="Auto"/>'
    '<ColumnDefinition Width="*"/>'
    '<ColumnDefinition Width="Auto"/>'
    '<ColumnDefinition Width="Auto"/>'
    '</Grid.ColumnDefinitions>'
    '<TextBlock Grid.Column="0" Text="Model:" Foreground="#FFFFFF" FontSize="12" '
    'VerticalAlignment="Center" Margin="0,0,6,0"/>'
    '<ComboBox x:Name="ModelCombo" Grid.Column="1" FontSize="12" Height="22" '
    'VerticalContentAlignment="Center"/>'
    '<TextBlock x:Name="StatusDot" Grid.Column="2" Text="&#x25CF; Checking..." '
    'Foreground="#FFCC00" FontSize="12" VerticalAlignment="Center" Margin="8,0,0,0"/>'
    '<Button x:Name="KeyBtn" Grid.Column="3" Content="Key" '
    'FontSize="12" Padding="4,2" Margin="4,0,0,0" VerticalAlignment="Center" '
    'ToolTip="Set API Keys (Claude / DeepSeek / OpenRouter)"/>'
    '</Grid>'
    '</Border>'

    '<Border Grid.Row="3" Background="#FFFFFF" BorderBrush="#C0C0C0" BorderThickness="0,1,0,0" Padding="8,8">'
    '<Grid>'
    '<Grid.ColumnDefinitions>'
    '<ColumnDefinition Width="*"/>'
    '<ColumnDefinition Width="8"/>'
    '<ColumnDefinition Width="Auto"/>'
    '</Grid.ColumnDefinitions>'
    '<Grid Grid.Column="0">'
    '<TextBox x:Name="InputBox" '
    'BorderBrush="#C0C0C0" BorderThickness="1" '
    'Padding="8,6" FontSize="12" TextWrapping="Wrap" '
    'AcceptsReturn="False" MaxHeight="80" Background="Transparent" '
    'VerticalScrollBarVisibility="Auto"/>'
    '<TextBlock x:Name="PlaceholderText" Text="Ask Revit anything..." '
    'Foreground="#808080" FontSize="12" '
    'Margin="10,7,8,7" IsHitTestVisible="False" '
    'VerticalAlignment="Top"/>'
    '</Grid>'
    '<Button x:Name="SendBtn" Grid.Column="2" Content="Go" '
    'FontWeight="Bold" FontSize="12" Width="38" Height="34" Padding="0"/>'
    '</Grid>'
    '</Border>'

    '<Border Grid.Row="4" Background="#C0C0C0" BorderBrush="#808080" BorderThickness="0,1,0,0">'
    '<Grid>'
    '<TextBlock x:Name="WebLink" Text="www.kidzink.com" '
    'HorizontalAlignment="Center" VerticalAlignment="Center" '
    'Foreground="#E43C2F" FontSize="12" Cursor="Hand"/>'
    '<TextBlock HorizontalAlignment="Right" VerticalAlignment="Center" '
    'Foreground="#000000" FontSize="12" Margin="0,0,10,0">&#169; Archie C. Manza 2026</TextBlock>'
    '</Grid>'
    '</Border>'

    '</Grid>'
    '</Window>'
)

# ══════════════════════════════════════════════════════════════════════════════
# EXTERNAL EVENT HANDLER — runs actions in valid Revit API context
# ══════════════════════════════════════════════════════════════════════════════

class _ChatActionHandler(IExternalEventHandler):
    """Executes Revit actions from the non-modal chat window.
    Write operations (Transaction) only work inside ExternalEvent.Raise()."""

    def __init__(self):
        self.action_dict = None
        self.result      = None
        self.callback    = None  # set by ChatWindow to receive results

    def Execute(self, app):
        try:
            self.result = dispatch_action(self.action_dict)
        except Exception as e:
            self.result = "Action failed: " + str(e)
        if self.callback:
            try:
                self.callback(self.result)
            except Exception:
                pass

    def GetName(self):
        return "KidzinkChatAction"

# ══════════════════════════════════════════════════════════════════════════════
# CHAT WINDOW
# ══════════════════════════════════════════════════════════════════════════════

class ChatWindow(object):

    def __init__(self):
        _init_brushes()
        self._history = []
        self._model   = _DEFAULT_MODEL

        # Store module-level refs on self — pyRevit clears the module scope
        # after script.py returns, but the WPF window stays alive.
        self._BR_RED   = BR_RED
        self._BR_WHITE = BR_WHITE
        self._BR_BLACK = BR_BLACK
        self._BR_DGREY = BR_DGREY
        self._BR_LGREY = BR_LGREY
        self._BR_GREEN = BR_GREEN
        self._BR_LTRED = BR_LTRED
        self._Thickness         = Thickness
        self._CornerRadius      = CornerRadius
        self._TextWrapping      = TextWrapping
        self._HorizontalAlignment = HorizontalAlignment
        self._WpfOrientation    = WpfOrientation
        self._Border            = Border
        self._Button            = Button
        self._TextBlock         = TextBlock
        self._StackPanel        = StackPanel
        from System.Windows import FontWeights as _FW
        self._FontWeights       = _FW

        # Store module-level functions/modules that event handlers need
        # (_ollama_chat, _parse_action defined as closures above)
        self._queue_mod    = _queue_mod
        self._traceback    = traceback
        self._threading    = threading
        self._load_settings = _load_settings
        self._save_settings = _save_settings
        self._claude_models   = _CLAUDE_MODELS
        self._claude_labels   = _CLAUDE_LABELS
        self._deepseek_models = _DEEPSEEK_MODELS
        self._deepseek_labels = _DEEPSEEK_LABELS
        self._openrouter_models = _OPENROUTER_MODELS
        self._openrouter_labels = _OPENROUTER_LABELS

        # ── Import WPF context menu & clipboard types ──────────────────────
        from System.Windows.Controls import ContextMenu as _CM, MenuItem as _MI
        from System.Windows import Clipboard as _Clip
        import System as _Sys
        import System.Threading as _ST
        import System.Runtime.InteropServices as _RI
        self._ContextMenu    = _CM
        self._MenuItem       = _MI
        self._Clipboard      = _Clip
        self._System         = _Sys
        self._SysThreading   = _ST
        self._SysCOMException = _RI.COMException

        # ── Closure-capture all module-level values needed by event handlers ──
        # pyRevit clears the module __dict__ after script.py returns, which
        # kills every free-variable lookup in functions defined at module scope.
        # Closures defined HERE capture values in __init__'s local scope and
        # survive independently of the module dict.
        _doc_ref   = _doc
        _uidoc_ref = _uidoc
        _fec       = FilteredElementCollector
        _vs        = ViewSchedule
        _lvl       = Level
        _bip       = BuiltInParameter
        _json      = json
        _re        = re
        _wr        = WebRequest
        _we        = WebException
        _sr        = StreamReader
        _enc       = Encoding
        _gen_url   = _OLLAMA_GEN
        _sys_prompt = _get_system_prompt()  # resolve NOW — function ref dies when module scope is cleared
        _max_hist  = _MAX_HISTORY
        _claude_url   = _CLAUDE_API_URL
        _deepseek_url = _DEEPSEEK_API_URL
        _openrouter_url = _OPENROUTER_API_URL
        _load_s    = _load_settings
        _save_s    = _save_settings
        # ── capture constants needed by ollama list models ────────────────
        _ollama_tags_url = _OLLAMA_TAGS
        _ollama_gen_url  = _OLLAMA_GEN

        def _ctx():
            # Lazily resolve the CURRENT document on every call — the user may
            # have switched documents since the window was created (S1 fix).
            try:
                live_uidoc = __revit__.ActiveUIDocument
                live_doc   = live_uidoc.Document if live_uidoc else None
            except Exception:
                live_uidoc = _uidoc_ref
                live_doc   = _doc_ref
            if not live_doc:
                return "No document open."
            lines = ["Document: " + live_doc.Title]
            try:
                av = live_uidoc.ActiveView
                if av:
                    vt = str(av.ViewType)
                    scale = ""
                    try:
                        scale = " 1:" + str(av.Scale)
                    except Exception:
                        pass
                    phase = ""
                    try:
                        p = av.get_Parameter(_bip.VIEW_PHASE)
                        if p and p.AsValueString():
                            phase = " Phase:" + p.AsValueString()
                    except Exception:
                        pass
                    lines.append("Active view: " + av.Name + " (" + vt + scale + phase + ")")
            except Exception:
                pass
            try:
                sel = live_uidoc.Selection.GetElementIds()
                if sel.Count == 0:
                    lines.append("Selected: none")
                else:
                    # Full category breakdown — lets the LLM answer "are these rooms?"
                    # without a clarifying question (mirrors _get_context()).
                    cat_counts = {}
                    room_bits  = []
                    for eid in sel:
                        try:
                            el = live_doc.GetElement(eid)
                        except Exception:
                            el = None
                        if el is None:
                            continue
                        try:
                            cname = el.Category.Name if el.Category else "Unknown"
                        except Exception:
                            cname = "Unknown"
                        cat_counts[cname] = cat_counts.get(cname, 0) + 1
                        if cname == "Rooms" and len(room_bits) < 8:
                            try:
                                rn    = el.get_Parameter(_bip.ROOM_NUMBER)
                                rname = el.get_Parameter(_bip.ROOM_NAME)
                                room_bits.append(
                                    (rn.AsString() if rn else "?") + " " +
                                    (rname.AsString() if rname else "")
                                )
                            except Exception:
                                pass
                    breakdown = ", ".join(
                        str(v) + " " + k for k, v in sorted(cat_counts.items())
                    )
                    line = "Selected: " + str(sel.Count) + " element(s) — " + breakdown
                    if room_bits:
                        line += " (" + "; ".join(room_bits) + ")"
                    lines.append(line)
            except Exception:
                pass
            try:
                levels = sorted(
                    _fec(live_doc).OfClass(_lvl).ToElements(),
                    key=lambda l: l.Elevation
                )
                if levels:
                    lnames = [l.Name for l in levels[:8]]
                    lines.append("Levels (" + str(len(levels)) + "): " + ", ".join(lnames))
            except Exception:
                pass
            try:
                lines.append("Workshared: " + ("Yes" if live_doc.IsWorkshared else "No"))
            except Exception:
                pass
            try:
                scheds = _fec(live_doc).OfClass(_vs).ToElements()
                names  = [s.Name for s in scheds if not s.IsTemplate][:6]
                if names:
                    lines.append("Schedules: " + ", ".join(names))
            except Exception:
                pass
            return "\n".join(lines)

        def _chat_ollama(model, history, user_text):
            context = _ctx()
            prompt = "[REVIT CONTEXT]\n" + context + "\n\n[CONVERSATION]\n"
            for msg in history[-(_max_hist * 2):]:
                role = "User" if msg["role"] == "user" else "Assistant"
                prompt += role + ": " + msg["content"] + "\n"
            prompt += "User: " + user_text + "\nAssistant:"
            payload = _json.dumps({
                "model": model, "prompt": prompt,
                "system": _sys_prompt, "stream": False,
                "options": {"temperature": 0.3, "num_ctx": 4096}
            })
            try:
                import urllib2
                payload_bytes = payload.encode("utf-8")
                req = urllib2.Request(
                    _ollama_gen_url,
                    data=payload_bytes,
                    headers={"Content-Type": "application/json"}
                )
                resp = urllib2.urlopen(req, timeout=120)
                raw  = resp.read()
                resp.close()
                data = _json.loads(raw)
                if "error" in data:
                    return None, "Ollama error: " + str(data["error"])
                return data.get("response", "").strip(), None
            except Exception as e:
                msg = str(e)
                if "Connection refused" in msg or "urlopen error" in msg or "actively refused" in msg:
                    return None, (
                        "No AI backend available.\n"
                        "To use Ollama: run  ollama serve  then reload.\n"
                        "To use Claude: click the Key button and enter your Anthropic API key."
                    )
                if "404" in msg:
                    return None, "Model not found. Run: ollama pull " + model
                return None, "Ollama error: " + msg

        def _chat_claude(model, history, user_text):
            try:
                settings = _load_s()
            except Exception as _le:
                return None, "Failed to load settings: " + str(_le)
            api_key = settings.get("claude_api_key", "")
            if not api_key:
                import os as _os2
                _appdata = _os2.environ.get("APPDATA", "NO_APPDATA")
                _fpath = _os2.path.join(_appdata, "Kidzink", "chat_settings.json")
                _exists = _os2.path.isfile(_fpath)
                _keys = list(settings.keys())
                return None, (
                    "No API key found.\n"
                    "File: " + _fpath + "\n"
                    "Exists: " + str(_exists) + "\n"
                    "Keys in settings: " + str(_keys)
                )
            messages = []
            trimmed = history[-(_max_hist * 2):]
            for msg in trimmed:
                messages.append({"role": msg["role"], "content": msg["content"]})
            # Inject live Revit context on every turn — selection may change
            # between messages so always use the latest snapshot.
            context = _ctx()
            current_content = "[REVIT CONTEXT]\n" + context + "\n\n" + user_text
            messages.append({"role": "user", "content": current_content})
            payload = _json.dumps({
                "model": model,
                "max_tokens": 1024,
                "system": _sys_prompt,
                "messages": messages
            })
            try:
                req = _wr.Create(_claude_url)
                req.Method      = "POST"
                req.ContentType = "application/json"
                req.Timeout     = 60000
                req.Headers.Add("x-api-key", api_key)
                req.Headers.Add("anthropic-version", "2023-06-01")
                pb = _enc.UTF8.GetBytes(payload)
                req.ContentLength = pb.Length
                st = req.GetRequestStream()
                st.Write(pb, 0, pb.Length)
                st.Close()
                resp   = req.GetResponse()
                reader = _sr(resp.GetResponseStream())
                raw    = reader.ReadToEnd()
                reader.Close()
                resp.Close()
                data = _json.loads(raw)
                if "error" in data:
                    return None, "Claude error: " + data["error"].get("message", str(data["error"]))
                # Extract text from content blocks
                text_parts = []
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                return "\n".join(text_parts).strip(), None
            except _we as e:
                if e.Response is not None:
                    try:
                        reader = _sr(e.Response.GetResponseStream())
                        body = reader.ReadToEnd()
                        reader.Close()
                        err = _json.loads(body)
                        msg = err.get("error", {}).get("message", body[:200])
                        return None, "Claude API: " + msg
                    except Exception:
                        pass
                return None, "Cannot reach Claude API."
            except Exception as e:
                return None, "Claude error: " + str(e)

        def _chat_deepseek(model, history, user_text):
            try:
                settings = _load_s()
            except Exception as _le:
                return None, "Failed to load settings: " + str(_le)
            api_key = settings.get("deepseek_api_key", "")
            if not api_key:
                return None, (
                    "No DeepSeek API key found.\n"
                    "Click the Key button and enter your DeepSeek API key."
                )
            messages = []
            trimmed = history[-(_max_hist * 2):]
            for msg in trimmed:
                messages.append({"role": msg["role"], "content": msg["content"]})
            context = _ctx()
            current_content = "[REVIT CONTEXT]\n" + context + "\n\n" + user_text
            messages.append({"role": "user", "content": current_content})
            payload = _json.dumps({
                "model": model,
                "max_tokens": 1024,
                "messages": [{"role": "system", "content": _sys_prompt}] + messages,
                "temperature": 0.3,
            })
            try:
                req = _wr.Create(_deepseek_url)
                req.Method      = "POST"
                req.ContentType = "application/json"
                req.Timeout     = 60000
                req.Headers.Add("Authorization", "Bearer " + api_key)
                pb = _enc.UTF8.GetBytes(payload)
                req.ContentLength = pb.Length
                st = req.GetRequestStream()
                st.Write(pb, 0, pb.Length)
                st.Close()
                resp   = req.GetResponse()
                reader = _sr(resp.GetResponseStream())
                raw    = reader.ReadToEnd()
                reader.Close()
                resp.Close()
                data = _json.loads(raw)
                if "error" in data:
                    return None, "DeepSeek error: " + str(data["error"].get("message", data["error"]))
                try:
                    text = data["choices"][0]["message"]["content"]
                    return text.strip(), None
                except (KeyError, IndexError) as _ke:
                    return None, "DeepSeek: unexpected response format — " + str(_ke)
            except _we as e:
                if e.Response is not None:
                    try:
                        reader = _sr(e.Response.GetResponseStream())
                        body = reader.ReadToEnd()
                        reader.Close()
                        err = _json.loads(body)
                        msg = err.get("error", {}).get("message", body[:200])
                        return None, "DeepSeek API: " + msg
                    except Exception:
                        pass
                return None, "Cannot reach DeepSeek API."
            except Exception as e:
                return None, "DeepSeek error: " + str(e)

        def _chat_openrouter(model, history, user_text):
            try:
                settings = _load_s()
            except Exception as _le:
                return None, "Failed to load settings: " + str(_le)
            api_key = settings.get("openrouter_api_key", "")
            if not api_key:
                return None, (
                    "No OpenRouter API key found.\n"
                    "Click the Key button and enter your OpenRouter API key."
                )
            # Strip the internal "openrouter:" routing prefix — send the bare slug.
            slug = model
            if slug.startswith("openrouter:"):
                slug = slug[len("openrouter:"):]
            messages = []
            trimmed = history[-(_max_hist * 2):]
            for msg in trimmed:
                messages.append({"role": msg["role"], "content": msg["content"]})
            context = _ctx()
            current_content = "[REVIT CONTEXT]\n" + context + "\n\n" + user_text
            messages.append({"role": "user", "content": current_content})
            payload = _json.dumps({
                "model": slug,
                "max_tokens": 1024,
                "messages": [{"role": "system", "content": _sys_prompt}] + messages,
                "temperature": 0.3,
            })
            try:
                req = _wr.Create(_openrouter_url)
                req.Method      = "POST"
                req.ContentType = "application/json"
                req.Timeout     = 60000
                req.Headers.Add("Authorization", "Bearer " + api_key)
                # Optional OpenRouter attribution headers (safe to send).
                req.Headers.Add("HTTP-Referer", "https://www.kidzink.com")
                req.Headers.Add("X-Title", "Kidzink Koda")
                pb = _enc.UTF8.GetBytes(payload)
                req.ContentLength = pb.Length
                st = req.GetRequestStream()
                st.Write(pb, 0, pb.Length)
                st.Close()
                resp   = req.GetResponse()
                reader = _sr(resp.GetResponseStream())
                raw    = reader.ReadToEnd()
                reader.Close()
                resp.Close()
                data = _json.loads(raw)
                if "error" in data:
                    return None, "OpenRouter error: " + str(data["error"].get("message", data["error"]))
                try:
                    text = data["choices"][0]["message"]["content"]
                    return text.strip(), None
                except (KeyError, IndexError) as _ke:
                    return None, "OpenRouter: unexpected response format — " + str(_ke)
            except _we as e:
                if e.Response is not None:
                    try:
                        reader = _sr(e.Response.GetResponseStream())
                        body = reader.ReadToEnd()
                        reader.Close()
                        err = _json.loads(body)
                        msg = err.get("error", {}).get("message", body[:200])
                        return None, "OpenRouter API: " + msg
                    except Exception:
                        pass
                return None, "Cannot reach OpenRouter API."
            except Exception as e:
                return None, "OpenRouter error: " + str(e)

        def _chat(model, history, user_text):
            if model.startswith("claude-"):
                return _chat_claude(model, history, user_text)
            if model.startswith("deepseek-"):
                return _chat_deepseek(model, history, user_text)
            if model.startswith("openrouter:"):
                return _chat_openrouter(model, history, user_text)
            return _chat_ollama(model, history, user_text)

        # Phrases that claim a Revit action completed. If these appear
        # WITHOUT a real <revit_action> tag having been parsed, the model
        # is fabricating a result — nothing was ever dispatched to Revit.
        # Stored on self so _on_poll reuses the compiled object.
        _COMPLETION_CLAIM_RE = re.compile(
            r"(schedule (has been |is )?created|i'?ve (generated|created|added|updated|deleted)|"
            r"successfully (created|added|updated|deleted|generated|isolated)|"
            r"has been (created|added|updated|isolated)|"
            r"is now (open in your (model|project)|isolated)|"
            r"elements? (are|have been) (now )?isolated|"
            r"are now isolated|have been isolated|\u2705)",
            re.IGNORECASE
        )
        self._completion_claim_re = _COMPLETION_CLAIM_RE
        # Anthropic's own tool-call pseudo-XML. This backend sends no `tools`
        # param, so this can never be a real tool call — it's Claude
        # pattern-matching to its native format instead of our custom tag.
        _FAKE_TOOLCALL_RE = re.compile(
            r"<function_calls>.*?(</function_calls>|$)", re.DOTALL | re.IGNORECASE
        )
        # Raw JSON action blob without a tag — model forgot the wrapper.
        # Regex can't match nested braces, so we use a brace-depth scanner.
        def _extract_json_objects(s):
            """Yield (start, end, parsed_dict) for every top-level {...} in s."""
            depth = 0
            start = None
            for i, ch in enumerate(s):
                if ch == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and start is not None:
                        blob = s[start:i + 1]
                        try:
                            obj = _json.loads(blob)
                            if isinstance(obj, dict):
                                yield start, i + 1, obj
                        except Exception:
                            pass
                        start = None
        # Context echo headers — Llama sometimes parrots back its own prompt,
        # including the full [REVIT CONTEXT] block and everything that follows
        # up to the first real assistant reply.
        # FIX B1: The old regex stopped at the next blank line, which left the
        # rest of the echoed block (level list, schedule list, conversation turn)
        # in `text` and it rendered as a bot bubble.  The new pattern strips
        # EVERYTHING from the first header marker to just before any
        # <revit_action> tag or the end of string, whichever comes first.
        _CTX_ECHO_RE = re.compile(
            r"\[(?:REVIT CONTEXT|NEW REVIT CONTEXT|CONVERSATION)\]"
            r".*?"
            r"(?=<revit_action>|\Z)",
            re.DOTALL | re.IGNORECASE
        )
        # Secondary pass: strip any standalone header line that survived.
        _CTX_HDR_RE = re.compile(
            r"^\s*\[(?:REVIT CONTEXT|NEW REVIT CONTEXT|CONVERSATION)\][^\n]*\n?",
            re.MULTILINE | re.IGNORECASE
        )

        # Opening/closing revit_action tags — tolerate optional whitespace
        # inside the tag name e.g. "</revit_action >" (FIX B3).
        _RA_OPEN_RE  = re.compile(r"<\s*revit_action\s*>",  re.IGNORECASE)
        _RA_CLOSE_RE = re.compile(r"</\s*revit_action\s*>", re.IGNORECASE)

        # Blocked action names — never dispatch, show a clear refusal instead
        _BLOCKED_ACTIONS = frozenset(["run_script", "exec", "execute_script",
                                      "run_python", "eval", "shell"])

        def _parse(text):
            # ── Strip echoed context headers (Llama parrot) ─────────────
            # B1: strip full echoed block up to any <revit_action> tag
            text = _CTX_ECHO_RE.sub("", text)
            # B1b: strip any surviving bare header lines
            text = _CTX_HDR_RE.sub("", text).strip()

            # ── Rescue raw JSON action blob (model forgot <revit_action> tag) ──
            # If there is no <revit_action> tag but a bare {"action":...} JSON
            # blob is present, treat it as an implicit action block.
            # B2 FIX: suppress only meaningless surrounding prose (< 8 chars),
            # so useful text before/after the blob is still shown.
            if not _RA_OPEN_RE.search(text):
                for jstart, jend, candidate in _extract_json_objects(text):
                    if "action" in candidate:
                        prose = (text[:jstart] + text[jend:]).strip()
                        if prose and len(prose) < 8:
                            prose = None
                        return prose or None, candidate

            # ── Guard: hallucinated native tool-call syntax ─────────────
            fake_toolcall = _FAKE_TOOLCALL_RE.search(text)
            if fake_toolcall:
                text = (text[:fake_toolcall.start()] + text[fake_toolcall.end():]).strip()
                if not text or _COMPLETION_CLAIM_RE.search(text):
                    return ("I wasn't able to run that — my last response used an "
                            "invalid action format. Please try rephrasing your request."), None

            # ── Extract <revit_action> / <info_only> tags ────────────────
            # B3 FIX: use compiled regexes so whitespace variants in the tag
            # name (e.g. "</revit_action >") are tolerated.
            action = None
            _io_open_re  = re.compile(r"<\s*info_only\s*>",  re.IGNORECASE)
            _io_close_re = re.compile(r"</\s*info_only\s*>", re.IGNORECASE)
            for tag, open_re, close_re in (
                ("revit_action", _RA_OPEN_RE,  _RA_CLOSE_RE),
                ("info_only",    _io_open_re,  _io_close_re),
            ):
                om = open_re.search(text)
                if not om:
                    continue
                si     = om.start()
                si_end = om.end()
                cm = close_re.search(text, si_end)
                if cm:
                    json_str = text[si_end:cm.start()].strip()
                    text = (text[:si] + text[cm.end():]).strip()
                else:
                    # B3b: no closing tag — consume to end of string
                    json_str = text[si_end:].strip()
                    text = text[:si].strip()
                if tag == "revit_action":
                    try:
                        action = _json.loads(json_str)
                    except Exception:
                        # JSON parse failed — surface raw content so the user
                        # can see what the model emitted
                        text = (text + "\n" + json_str).strip()
                elif tag == "info_only":
                    try:
                        data = _json.loads(json_str)
                        parts = []
                        for k, v in data.items():
                            parts.append(str(k) + ": " + str(v))
                        text = (text + "\n" + ", ".join(parts)).strip()
                    except Exception:
                        text = (text + "\n" + json_str).strip()
                break

            # B4 FIX: scrub any residual raw tag fragments that survived
            # (e.g. a second <revit_action> block or a mangled unclosed tag).
            text = _RA_OPEN_RE.sub("", text)
            text = _RA_CLOSE_RE.sub("", text).strip()

            # ── Guard: premature completion claim on a pending action ──
            if action is not None and text and _COMPLETION_CLAIM_RE.search(text):
                text = _COMPLETION_CLAIM_RE.sub("", text).strip()
                if not text:
                    text = "Ready to run this in Revit — click below to confirm."

            return text or None, action

        # ── List models closure (replaces _ollama_list_models) ─────────────
        def _list_models():
            try:
                import urllib2 as _ul2
                resp = _ul2.urlopen(_ollama_tags_url, timeout=3)
                raw  = resp.read()
                resp.close()
                data = _json.loads(raw)
                return [m.get("name", "?") for m in data.get("models", [])]
            except Exception:
                return []
        self._ollama_list_models    = _list_models
        self._combo_change_handler  = None   # cleaned up by _refresh_models
        self._combo_index_to_model  = []     # index → model ID, built by _refresh_models

        self._chat_fn      = _chat   # unified dispatcher — handles both Claude and Ollama
        self._parse_action = _parse
        self._dispatch_action = dispatch_action  # actions use Transaction etc. at call time
        self._dispatch_plugins = set(_PLUGINS.keys())  # live set of known action names
        self._blocked_actions  = _BLOCKED_ACTIONS      # actions never permitted to run
        self._resolve_category = _resolve_category     # for keyword interceptor
        self._category_keys    = set(_CATEGORY_MAP.keys())  # known category names

        # ── Minimal survival dict ─────────────────────────────────────────
        # pyRevit clears the module __dict__ after script.py returns. The only
        # names dispatch_action._globals needs are __revit__ (for lazy doc
        # resolution) and the helpers it calls. dict(globals()) was wasteful
        # (pulled in all WPF objects + dead stubs); this is the exact minimal set.
        self._saved_globals = {
            "__revit__":         __revit__,
            "_PLUGINS":          _PLUGINS,
            "_resolve_category": _resolve_category,
            "_get_field_bip":    _get_field_bip,
            "_eid_int":          _eid_int,
            "dispatch_action":   dispatch_action,
        }

        # ExternalEvent for write operations in valid Revit API context
        self._ext_handler = _ChatActionHandler()
        self._ext_handler.callback = self._on_action_result
        self._ext_event = ExternalEvent.Create(self._ext_handler)

        # ── Survival copies ────────────────────────────────────────────────
        # pyRevit clears the module __dict__ after script.py returns, but the
        # WPF window stays alive. Every WPF type, brush, and module ref that
        # an event handler needs MUST be stored on self here — importing inside
        # a live WPF callback is unreliable after module-scope is cleared.
        # If you add a new WPF type to any event handler, add it here too.
        from System.Windows import Visibility, WindowState as _WinState
        from System.Windows.Input import Key, Cursors as _Cursors
        from System.Windows.Threading import DispatcherTimer, Dispatcher, DispatcherPriority
        from System import TimeSpan
        self._Visibility         = Visibility
        self._WindowState        = _WinState
        self._Key                = Key
        self._Dispatcher         = Dispatcher
        self._DispatcherPriority = DispatcherPriority
        self._HandCursor         = _Cursors.Hand
        # self._System already captured as _Sys during the ContextMenu import block above

        # Thread-safe queue for background thread results
        self._result_queue = _queue_mod.Queue()
        self._poll_count = 0
        self._poll_timer = DispatcherTimer()
        self._poll_timer.Interval = TimeSpan.FromMilliseconds(250)
        self._poll_timer.Tick += self._on_poll

        try:
            self.window = XamlReader.Parse(_XAML)
        except Exception as xe:
            raise RuntimeError("XAML parse failed: " + str(xe))

        self._chat_panel  = self.window.FindName("ChatPanel")
        self._chat_scroll = self.window.FindName("ChatScroll")
        self._input_box   = self.window.FindName("InputBox")
        self._send_btn    = self.window.FindName("SendBtn")
        self._model_combo = self.window.FindName("ModelCombo")
        self._status_dot  = self.window.FindName("StatusDot")
        self._clear_btn   = self.window.FindName("ClearBtn")
        self._export_btn  = self.window.FindName("ExportBtn")
        self._weblink     = self.window.FindName("WebLink")
        self._key_btn     = self.window.FindName("KeyBtn")

        # Style buttons in Python — avoids ControlTemplate in XAML
        self._send_btn.Background        = self._BR_RED
        self._send_btn.Foreground        = self._BR_WHITE
        self._send_btn.BorderThickness   = self._Thickness(0)
        self._clear_btn.Background       = self._BR_RED
        self._clear_btn.Foreground       = self._BR_WHITE
        self._clear_btn.BorderThickness  = self._Thickness(0)
        if self._export_btn:
            self._export_btn.Background      = self._BR_RED
            self._export_btn.Foreground      = self._BR_WHITE
            self._export_btn.BorderThickness = self._Thickness(0)

        # Placeholder overlay — toggled by TextChanged, no focus events needed
        self._placeholder = self.window.FindName("PlaceholderText")
        self._input_box.TextChanged += self._on_text_changed

        # Events — no ghost/focus events; plain Click and KeyDown only
        self._send_btn.Click    += self._on_send
        self._clear_btn.Click   += self._on_clear
        self._input_box.KeyDown += self._on_key_down
        self._weblink.MouseLeftButtonUp += self._on_web_click
        if self._key_btn:
            self._key_btn.Click += self._on_key_click
        if self._export_btn:
            self._export_btn.Click += self._on_export

        # Position bottom-right of primary screen
        try:
            sw = SystemParameters.PrimaryScreenWidth
            sh = SystemParameters.PrimaryScreenHeight
            self.window.Left = sw - 400
            self.window.Top  = sh - 660
        except Exception:
            pass

        try:
            self._refresh_models()
        except Exception:
            try:
                self._model_combo.Items.Add("(none — run: ollama pull qwen3.6)")
                self._model_combo.SelectedIndex = 0
                self._status_dot.Text       = "● Offline"
                self._status_dot.Foreground = self._BR_RED
            except Exception:
                pass
        # ── Welcome message with canned prompts + capability chips ────────
        self._add_bot(u"Hello! I can help you with Revit tasks. What do you need?")

        # Canned prompt chips — left-click pastes text into the input box
        # so the user can edit or append before sending.
        self._add_bot(
            u"Quick starts \u2014 click any chip to paste it into the input box:"
        )
        _CANNED = [
            (u"Count walls",                   u"count walls"),
            (u"Count doors",                   u"count doors"),
            (u"Count furniture",               u"count furniture"),
            (u"List views",                    u"list views"),
            (u"List sheets",                   u"list sheets"),
            (u"List schedules",                u"list schedules"),
            (u"Door schedule",                 u"create a door schedule with Family Name, Type Mark, Mark, Level, and Comments"),
            (u"Room schedule",                 u"create a room schedule with Room Number, Room Name, Level, Area, and Comments"),
            (u"Wall schedule",                 u"create a wall schedule with Family Name, Type Mark, Length, and Unconnected Height"),
            (u"List selected parameters",      u"list all parameters of the selected element"),
            (u"Select all furniture in view",  u"select all furniture in the active view"),
            (u"Isolate doors in view",         u"isolate doors in the active view"),
        ]
        for _lbl, _prompt in _CANNED:
            self._add_canned_prompt_bubble(_lbl, _prompt)

        cap_names = sorted(_PLUGINS.keys())
        if cap_names:
            self._add_bot(
                u"Loaded capabilities (" + str(len(cap_names)) + u"):"
                u"\nClick a chip to paste its name \u2014 or just describe what you need!"
            )
            for cname in cap_names:
                self._add_capability_bubble(cname)
        else:
            self._add_bot(
                u"No capabilities found in the capabilities/ folder. "
                u"Add .py files there to extend what I can do."
            )

    # ── Placeholder visibility ──────────────────────────────────────────────

    def _on_text_changed(self, s, e):
        try:
            has_text = bool(self._input_box.Text)
            self._placeholder.Visibility = (
                self._Visibility.Collapsed if has_text else self._Visibility.Visible
            )
        except Exception as _ex:
            self._add_result("[TEXT_CHANGED ERROR] " + self._traceback.format_exc(), error=True)

    # ── Key handler ─────────────────────────────────────────────────────────

    def _on_key_down(self, s, e):
        try:
            if e.Key == self._Key.Return:
                e.Handled = True
                self._on_send(None, None)
        except Exception:
            pass

    # ── Web link ────────────────────────────────────────────────────────────

    def _on_web_click(self, s, e):
        try:
            import subprocess
            subprocess.Popen(["cmd", "/c", "start", "", "https://www.kidzink.com"])
        except Exception:
            pass

    # ── Model refresh ───────────────────────────────────────────────────────

    def _refresh_models(self, force_has_key=False):
        # Unsubscribe any old SelectionChanged handler — we no longer need one
        # at all, but clean up in case a previous version registered one.
        if hasattr(self, "_combo_change_handler") and self._combo_change_handler is not None:
            try:
                self._model_combo.SelectionChanged -= self._combo_change_handler
            except Exception:
                pass
            self._combo_change_handler = None

        models = self._ollama_list_models()
        self._model_combo.Items.Clear()

        # _combo_index_to_model maps each combo index → actual model ID string.
        # None entries are separators / invalid selections.
        index_map = []

        settings = self._load_settings()
        has_claude_key     = force_has_key or bool(settings.get("claude_api_key", ""))
        has_deepseek_key   = bool(settings.get("deepseek_api_key", ""))
        has_openrouter_key = bool(settings.get("openrouter_api_key", ""))

        for cid in self._claude_models:
            label = self._claude_labels.get(cid, cid)
            if not has_claude_key:
                label += " (set key)"
            self._model_combo.Items.Add(label)
            index_map.append(cid)

        self._model_combo.Items.Add("--- DeepSeek ---")
        index_map.append(None)
        for did in self._deepseek_models:
            label = self._deepseek_labels.get(did, did)
            if not has_deepseek_key:
                label += " (set key)"
            self._model_combo.Items.Add(label)
            index_map.append(did)

        self._model_combo.Items.Add("--- OpenRouter ---")
        index_map.append(None)
        for oid in self._openrouter_models:
            label = self._openrouter_labels.get(oid, oid)
            if not has_openrouter_key:
                label += " (set key)"
            self._model_combo.Items.Add(label)
            index_map.append(oid)

        has_key = has_claude_key or has_deepseek_key or has_openrouter_key

        ollama_start = None
        if models:
            self._model_combo.Items.Add("--- Ollama ---")
            index_map.append(None)  # separator
            ollama_start = len(index_map)  # index of first Ollama model
            for m in models:
                self._model_combo.Items.Add(m)
                index_map.append(m)

        self._combo_index_to_model = index_map

        # Default to qwen3.6 (any tag) if Ollama has it, else first Ollama
        # model, else Claude (index 0). Match by prefix so "qwen3.6:latest"
        # matches _DEFAULT_MODEL = "qwen3.6".
        default_idx = 0
        if models and ollama_start is not None:
            default_idx = ollama_start  # fallback: first Ollama model
            for i, m in enumerate(models):
                if m == _DEFAULT_MODEL or m.startswith(_DEFAULT_MODEL + ":"):
                    default_idx = ollama_start + i
                    break
        self._model_combo.SelectedIndex = default_idx

        if models or has_key:
            self._status_dot.Text       = "Ready"
            self._status_dot.Foreground = self._BR_GREEN
        else:
            self._status_dot.Text       = "No backend"
            self._status_dot.Foreground = self._BR_RED

    # ── API Key ──────────────────────────────────────────────────────────────

    def _on_key_click(self, s, e):
        try:
            from System.Windows import Window as _Win, WindowStartupLocation
            from System.Windows.Controls import TextBox as _TB2, Label as _Lbl
            from System.Windows.Controls import StackPanel as _SP3

            dlg = _Win()
            dlg.Title  = "Kidzink - API Keys"
            dlg.Width  = 380
            dlg.Height = 320
            dlg.WindowStartupLocation = WindowStartupLocation.CenterOwner
            dlg.Owner  = self.window
            dlg.Background = self._BR_LGREY

            def _mask(v):
                if v and len(v) > 12:
                    return v[:4] + "..." + v[-4:]
                return v or ""

            sp = _SP3()
            sp.Margin = self._Thickness(12, 12, 12, 12)

            settings = self._load_settings()

            # ── Anthropic / Claude ──────────────────────────────────────────
            lbl_claude = _Lbl()
            lbl_claude.Content    = "Anthropic (Claude) API key:"
            lbl_claude.Foreground = self._BR_BLACK
            lbl_claude.FontSize   = 12
            sp.Children.Add(lbl_claude)

            tb_claude = _TB2()
            tb_claude.FontSize = 12
            tb_claude.Padding  = self._Thickness(6, 4, 6, 4)
            _cur_claude        = settings.get("claude_api_key", "")
            tb_claude.Text     = _mask(_cur_claude)
            tb_claude.Tag      = _cur_claude
            sp.Children.Add(tb_claude)

            # ── DeepSeek ────────────────────────────────────────────────────
            lbl_ds = _Lbl()
            lbl_ds.Content    = "DeepSeek API key:"
            lbl_ds.Foreground = self._BR_BLACK
            lbl_ds.FontSize   = 12
            lbl_ds.Margin     = self._Thickness(0, 10, 0, 0)
            sp.Children.Add(lbl_ds)

            tb_ds = _TB2()
            tb_ds.FontSize = 12
            tb_ds.Padding  = self._Thickness(6, 4, 6, 4)
            _cur_ds        = settings.get("deepseek_api_key", "")
            tb_ds.Text     = _mask(_cur_ds)
            tb_ds.Tag      = _cur_ds
            sp.Children.Add(tb_ds)

            # ── OpenRouter ──────────────────────────────────────────────────
            lbl_or = _Lbl()
            lbl_or.Content    = "OpenRouter API key:"
            lbl_or.Foreground = self._BR_BLACK
            lbl_or.FontSize   = 12
            lbl_or.Margin     = self._Thickness(0, 10, 0, 0)
            sp.Children.Add(lbl_or)

            tb_or = _TB2()
            tb_or.FontSize = 12
            tb_or.Padding  = self._Thickness(6, 4, 6, 4)
            _cur_or        = settings.get("openrouter_api_key", "")
            tb_or.Text     = _mask(_cur_or)
            tb_or.Tag      = _cur_or
            sp.Children.Add(tb_or)

            # ── Save button ─────────────────────────────────────────────────
            btn = self._Button()
            btn.Content    = "Save"
            btn.Background = self._BR_RED
            btn.Foreground = self._BR_WHITE
            btn.FontSize   = 12
            btn.Padding    = self._Thickness(14, 5, 14, 5)
            btn.Margin     = self._Thickness(0, 14, 0, 0)

            def _save(s2, e2):
                new_claude = tb_claude.Text.strip()
                new_ds     = tb_ds.Text.strip()
                new_or     = tb_or.Text.strip()

                # Resolve masked values — if the text still contains "..." the
                # user didn't edit it, so keep the original key unchanged.
                if "..." in new_claude:
                    new_claude = tb_claude.Tag or ""
                if "..." in new_ds:
                    new_ds = tb_ds.Tag or ""
                if "..." in new_or:
                    new_or = tb_or.Tag or ""

                cfg = self._load_settings()
                changed = []
                if new_claude:
                    cfg["claude_api_key"] = new_claude
                    changed.append("Claude")
                if new_ds:
                    cfg["deepseek_api_key"] = new_ds
                    changed.append("DeepSeek")
                if new_or:
                    cfg["openrouter_api_key"] = new_or
                    changed.append("OpenRouter")

                dlg.Close()

                if changed:
                    result = self._save_settings(cfg)
                    if result is True:
                        def _deferred_refresh():
                            self._refresh_models(force_has_key=bool(new_claude))
                            self._add_bot(
                                "API key(s) saved: " + ", ".join(changed) + ". "
                                "Models are now available."
                            )
                        self._Dispatcher.CurrentDispatcher.BeginInvoke(
                            self._DispatcherPriority.Background,
                            self._System.Action(_deferred_refresh)
                        )
                    else:
                        self._add_result("Failed to save API key(s): " + str(result), error=True)
                else:
                    self._add_bot("API keys unchanged.")

            btn.Click += _save
            sp.Children.Add(btn)

            dlg.Content = sp
            dlg.ShowDialog()
        except Exception as ex:
            self._add_result("Key dialog error: " + str(ex), error=True)

    # ── Bubble builders ─────────────────────────────────────────────────────

    def _make_border(self, bg_brush, margin_left, margin_right, align, corner=6):
        b = self._Border()
        b.Background          = bg_brush
        b.CornerRadius        = self._CornerRadius(corner)
        b.Padding             = self._Thickness(10, 7, 10, 7)
        b.Margin              = self._Thickness(margin_left, 3, margin_right, 3)
        b.MaxWidth            = 270
        b.HorizontalAlignment = align
        return b

    def _make_textblock(self, text, fg_brush):
        tb = self._TextBlock()
        tb.Text        = text
        tb.Foreground  = fg_brush
        tb.FontSize    = 12
        tb.TextWrapping = self._TextWrapping.Wrap

        # ── Right-click context menu to copy text ──────────────────────────
        cm = self._ContextMenu()
        copy_item = self._MenuItem()
        copy_item.Header = "Copy"
        copy_item.Click += lambda s, e: self._copy_to_clipboard(tb.Text)
        cm.Items.Add(copy_item)
        tb.ContextMenu = cm
        # ───────────────────────────────────────────────────────────────────

        return tb

    def _copy_to_clipboard(self, text):
        # Windows clipboard is a shared, single-owner resource — another
        # process (or even a prior WPF drag/paste op) can hold a transient
        # lock, which raises a COMException on SetText. Retry briefly.
        # NOTE: all System refs are pre-captured on self during __init__
        # because pyRevit clears the module scope after script.py returns,
        # making `import System` inside a WPF callback unreliable.
        last_exc = None
        for _attempt in range(4):
            try:
                self._Clipboard.SetText(text if text else " ")
                return True
            except Exception as _ex:
                last_exc = _ex
                try:
                    # Sleep 60ms between retries — handles transient COM lock
                    self._SysThreading.Thread.Sleep(60)
                except Exception:
                    pass
        try:
            self._add_result(
                "Copy failed: " + str(last_exc)[:120] + " — try again.", error=True
            )
        except Exception:
            pass
        return False

    def _add_user(self, text):
        b = self._make_border(self._BR_RED, 48, 6, self._HorizontalAlignment.Right, corner=10)
        b.Child = self._make_textblock(text, self._BR_WHITE)
        self._chat_panel.Children.Add(b)
        self._scroll_bottom()
        return b

    def _add_bot(self, text):
        b = self._make_border(self._BR_WHITE, 6, 48, self._HorizontalAlignment.Left, corner=10)
        b.Child = self._make_textblock(text, self._BR_BLACK)
        self._chat_panel.Children.Add(b)
        self._scroll_bottom()
        return b

    def _add_thinking(self):
        # Returns the border widget so _remove() can find and delete it.
        return self._add_bot(u"Thinking\u2026")

    def _remove(self, widget):
        try:
            self._chat_panel.Children.Remove(widget)
        except Exception:
            pass

    def _add_run_bubble(self, action_dict):
        sp = self._StackPanel()
        sp.Orientation = self._WpfOrientation.Vertical

        label = self._make_textblock(
            "Action ready: " + action_dict.get("action", "").replace("_", " ").title(),
            self._BR_GREEN
        )
        sp.Children.Add(label)

        btn = self._Button()
        btn.Content    = "Run in Revit"
        btn.Background = self._BR_RED
        btn.Foreground = self._BR_WHITE
        btn.FontSize   = 12
        btn.Padding    = self._Thickness(12, 5, 12, 5)
        btn.Margin     = self._Thickness(0, 6, 0, 0)
        btn.Tag        = action_dict

        def _run(s, e):
            self._execute(s.Tag)
        btn.Click += _run
        sp.Children.Add(btn)

        b = self._make_border(self._BR_WHITE, 6, 48, self._HorizontalAlignment.Left)
        b.BorderBrush     = self._BR_GREEN
        b.BorderThickness = self._Thickness(3, 0, 0, 0)
        b.Child = sp
        self._chat_panel.Children.Add(b)
        self._scroll_bottom()

    def _paste_to_input(self, text):
        """Paste text into the input box and focus it so the user can finish the prompt."""
        try:
            self._input_box.Text = text
            self._input_box.CaretIndex = len(text)
            self._input_box.Focus()
        except Exception:
            pass

    def _add_capability_bubble(self, name):
        """Capability chip — left-click pastes name to input, right-click copies."""
        b = self._Border()
        b.Background          = self._BR_WHITE
        b.CornerRadius        = self._CornerRadius(4)
        b.Padding             = self._Thickness(10, 5, 10, 5)
        b.Margin              = self._Thickness(14, 2, 80, 2)
        b.HorizontalAlignment = self._HorizontalAlignment.Left
        b.BorderBrush         = self._BR_LGREY
        b.BorderThickness     = self._Thickness(1)
        b.Cursor              = self._HandCursor

        tb = self._TextBlock()
        tb.Text         = name
        tb.Foreground   = self._BR_RED
        tb.FontSize     = 12
        tb.FontWeight   = self._FontWeights.SemiBold
        tb.TextWrapping = self._TextWrapping.NoWrap

        cm = self._ContextMenu()
        paste_item = self._MenuItem()
        paste_item.Header = "Paste to input"
        paste_item.Click += lambda s, e: self._paste_to_input(name)
        copy_item = self._MenuItem()
        copy_item.Header = "Copy"
        copy_item.Click += lambda s, e: self._copy_to_clipboard(name)
        cm.Items.Add(paste_item)
        cm.Items.Add(copy_item)
        b.ContextMenu = cm

        # Single left-click pastes the capability name into the input box so
        # the user can append parameters and send (e.g. "list_schedules" → go)
        b.MouseLeftButtonUp += lambda s, e: self._paste_to_input(name)

        b.Child = tb
        self._chat_panel.Children.Add(b)

    def _add_canned_prompt_bubble(self, label, prompt_text):
        """Canned-prompt chip — left-click pastes prompt_text to input, user can edit before send."""
        b = self._Border()
        b.Background          = self._BR_LGREY
        b.CornerRadius        = self._CornerRadius(4)
        b.Padding             = self._Thickness(10, 5, 10, 5)
        b.Margin              = self._Thickness(14, 2, 60, 2)
        b.HorizontalAlignment = self._HorizontalAlignment.Left
        b.BorderBrush         = self._BR_DGREY
        b.BorderThickness     = self._Thickness(1)
        b.Cursor              = self._HandCursor

        tb = self._TextBlock()
        tb.Text         = label
        tb.Foreground   = self._BR_BLACK
        tb.FontSize     = 12
        tb.TextWrapping = self._TextWrapping.NoWrap

        cm = self._ContextMenu()
        paste_item = self._MenuItem()
        paste_item.Header = "Paste to input"
        paste_item.Click += lambda s, e: self._paste_to_input(prompt_text)
        copy_item = self._MenuItem()
        copy_item.Header = "Copy prompt"
        copy_item.Click += lambda s, e: self._copy_to_clipboard(prompt_text)
        cm.Items.Add(paste_item)
        cm.Items.Add(copy_item)
        b.ContextMenu = cm

        b.MouseLeftButtonUp += lambda s, e: self._paste_to_input(prompt_text)

        b.Child = tb
        self._chat_panel.Children.Add(b)

    def _add_result(self, text, error=False):
        b = self._make_border(self._BR_WHITE, 6, 48, self._HorizontalAlignment.Left)
        b.BorderBrush     = self._BR_RED if error else self._BR_GREEN
        b.BorderThickness = self._Thickness(3, 0, 0, 0)
        fg = self._BR_RED if error else self._BR_GREEN
        b.Child = self._make_textblock(text, fg)
        self._chat_panel.Children.Add(b)
        self._scroll_bottom()
        return b

    def _scroll_bottom(self):
        try:
            self._chat_scroll.ScrollToBottom()
        except Exception:
            pass

    def _get_selected_model(self):
        """Read the model ID directly from the combo's current SelectedIndex.
        This is the only source of truth — no SelectionChanged handler needed."""
        try:
            idx = self._model_combo.SelectedIndex
            index_map = getattr(self, "_combo_index_to_model", [])
            if 0 <= idx < len(index_map) and index_map[idx] is not None:
                return index_map[idx]
        except Exception:
            pass
        # Fallback: prefer Ollama if available, else whichever cloud key is set
        try:
            s = self._load_settings()
            has_claude_key     = bool(s.get("claude_api_key", ""))
            has_deepseek_key   = bool(s.get("deepseek_api_key", ""))
            has_openrouter_key = bool(s.get("openrouter_api_key", ""))
            index_map = getattr(self, "_combo_index_to_model", [])
            # Prefer first Ollama model
            for m in index_map:
                if (m and not m.startswith("claude-")
                        and not m.startswith("deepseek-")
                        and not m.startswith("openrouter:")):
                    return m
            if has_deepseek_key:
                return self._deepseek_models[0]
            if has_openrouter_key:
                return self._openrouter_models[0]
            if has_claude_key:
                return self._claude_models[0]
        except Exception:
            pass
        return self._claude_models[0]

    # ── Keyword interceptor — bypass LLM for obvious requests ─────────────

    def _try_intercept(self, text):
        """If `text` is an obvious action request, return (prose, action_dict).
        Otherwise return None and let the LLM handle it."""
        import re as _re  # re is stdlib — safe to import here; cached by Python
        lower = text.lower().strip()

        # ── count [category] ──────────────────────────────────────────────
        m = _re.search(
            r"(?:count|how many|number of)\s+(?:elements?\s+)?(.+?)"
            r"(?:\s+in\s+(?:the\s+)?(?:model|view|project|active\s+view))?$",
            lower
        )
        if m:
            cat_str = m.group(1).strip().rstrip("s?. ")
            if self._resolve_category(cat_str) is not None:
                # Route to list_elements with count_only — count_elements removed.
                action = {"action": "list_elements",
                          "params": {"category": cat_str, "count_only": True}}
                return "Counting " + cat_str + " in the model...", action

        # ── create wall(s)/floor(s)/ceiling(s) for the selected rooms ──────
        # Handles requests like "generate a ceiling for the selected rooms
        # with 3m high" or "the current selected rooms" as a follow-up to a
        # prior create_room_elements clarification, entirely without the LLM
        # — this is the interaction most likely to trip up a small model.
        if "create_room_elements" in self._dispatch_plugins:
            wants_selection = bool(_re.search(
                r"(?:the\s+)?(?:current(?:ly)?\s+)?select(?:ed|ion)\b", lower
            ))
            found_kinds = []
            for kind, pats in (
                ("wall",    (r"\bwalls?\b",)),
                ("floor",   (r"\bfloors?\b",)),
                ("ceiling", (r"\bceilings?\b",)),
            ):
                if any(_re.search(p, lower) for p in pats):
                    found_kinds.append(kind)

            # Case A: a full request naming both an element kind and "selected/selection".
            if wants_selection and found_kinds:
                height_mm = None
                hm = _re.search(
                    r"(\d+(?:\.\d+)?)\s*(mm|millimet(?:er|re)s?|m|met(?:er|re)s?)?"
                    r"\s*(?:high|height|tall)?",
                    lower[lower.find(found_kinds[0]):] if found_kinds[0] in lower else lower
                )
                if hm:
                    try:
                        val = float(hm.group(1))
                        unit = (hm.group(2) or "mm").lower()
                        height_mm = val if unit.startswith("mm") or unit.startswith("millimet") else val * 1000.0
                    except (TypeError, ValueError):
                        height_mm = None
                action_params = {"elements": found_kinds, "use_selection": True}
                if height_mm:
                    action_params["height_mm"] = height_mm
                action = {"action": "create_room_elements", "params": action_params}
                return (
                    "Creating " + " and ".join(found_kinds) + " for the selected room(s)..."
                ), action

            # Case B: user is ONLY confirming "the selected rooms" (a reply to a
            # clarifying question) — reuse the element kind(s) from the last
            # thing the user asked for, if we can find it in recent history.
            if wants_selection and not found_kinds and "room" in lower:
                # Limit to last 4 messages — prevents matching a kind from an
                # old unrelated conversation turn (TI4 fix).
                for prev in reversed(self._history[-5:-1]):
                    if prev.get("role") != "user":
                        continue
                    prev_lower = prev.get("content", "").lower()
                    prev_kinds = [
                        k for k, p in (
                            ("wall", r"\bwalls?\b"),
                            ("floor", r"\bfloors?\b"),
                            ("ceiling", r"\bceilings?\b"),
                        ) if _re.search(p, prev_lower)
                    ]
                    if prev_kinds:
                        hm = _re.search(
                            r"(\d+(?:\.\d+)?)\s*(mm|millimet(?:er|re)s?|m|met(?:er|re)s?)?"
                            r"\s*(?:high|height|tall)?",
                            prev_lower
                        )
                        height_mm = None
                        if hm:
                            try:
                                val = float(hm.group(1))
                                unit = (hm.group(2) or "mm").lower()
                                height_mm = val if unit.startswith("mm") or unit.startswith("millimet") else val * 1000.0
                            except (TypeError, ValueError):
                                height_mm = None
                        action_params = {"elements": prev_kinds, "use_selection": True}
                        if height_mm:
                            action_params["height_mm"] = height_mm
                        action = {"action": "create_room_elements", "params": action_params}
                        return (
                            "Creating " + " and ".join(prev_kinds) + " for the selected room(s)..."
                        ), action

        # ── select [category] ─────────────────────────────────────────────
        m = _re.search(r"(?:select|pick)\s+(?:all\s+)?(.+?)(?:\s+in\s+(?:the\s+)?(?:view|model))?$", lower)
        if m:
            cat_str = m.group(1).strip().rstrip("s?. ")
            if self._resolve_category(cat_str) is not None:
                action = {"action": "select_by_category", "params": {"category": cat_str}}
                return "Selecting " + cat_str + " in the active view...", action

        # ── list views / list sheets / list schedules ─────────────────────
        if _re.search(r"^(?:list|show)\s+views", lower):
            return "Listing views...", {"action": "list_views", "params": {"view_type": "all"}}
        if _re.search(r"^(?:list|show)\s+sheets", lower):
            # list_sheets removed — list_views with type=sheets covers this.
            return "Listing sheets...", {"action": "list_views", "params": {"type": "sheets"}}
        if _re.search(r"^(?:list|show)\s+schedules", lower):
            return "Listing schedules...", {"action": "list_schedules", "params": {}}

        # ── remove / replace field(s) in a schedule → modify_schedule ───────
        # Must sit BEFORE the filter intercept — field names like "comments"
        # would otherwise trip the filter regex and misroute to filter_schedule.
        if "modify_schedule" in self._dispatch_plugins:
            # "remove X [field] [and replace with Y] [from/in/for <sched>]"
            rm = _re.search(
                r"remove\s+(.+?)\s+(?:field\s+)?(?:and\s+replace\s+(?:it\s+)?with\s+(.+?)\s+)?(?:from|in|for|on)\s+(?:the\s+)?(.+?)(?:\s+schedule)?$",
                lower
            )
            if rm:
                rm_field   = rm.group(1).strip()
                add_field  = (rm.group(2) or "").strip()
                sched_name = rm.group(3).strip()
                p = {"schedule_name": sched_name, "remove_fields": [rm_field]}
                if add_field:
                    p["fields"] = [add_field]
                action = {"action": "modify_schedule", "params": p}
                prose = "Removing '" + rm_field + "'"
                if add_field:
                    prose += " and adding '" + add_field + "'"
                prose += " in '" + sched_name + "' schedule..."
                return prose, action

            # "replace [the] X with|to Y [in/for <sched>]"
            rp = _re.search(
                r"replace\s+(?:the\s+)?(.+?)\s+(?:with|to)\s+(.+?)\s+(?:in|for|on)\s+(?:the\s+)?(.+?)(?:\s+schedule)?$",
                lower
            )
            # "<sched> schedule replace [the] X with|to Y"  (schedule name first)
            rp2 = _re.search(
                r"(.+?)\s+schedule\s+replace\s+(?:the\s+)?(.+?)\s+(?:with|to)\s+(.+)$",
                lower
            ) if not rp else None
            if rp or rp2:
                if rp:
                    old_field  = rp.group(1).strip()
                    new_field  = rp.group(2).strip()
                    sched_name = rp.group(3).strip()
                else:
                    sched_name = rp2.group(1).strip()
                    old_field  = rp2.group(2).strip()
                    new_field  = rp2.group(3).strip()
                action = {
                    "action": "modify_schedule",
                    "params": {
                        "schedule_name": sched_name,
                        "remove_fields": [old_field],
                        "fields":        [new_field],
                    },
                }
                return (
                    "Replacing '" + old_field + "' with '" + new_field
                    + "' in '" + sched_name + "' schedule..."
                ), action

        # ── filter [schedule name] by [field] [=|equals] [value] ─────────
        # Pattern: 'filter <name> by <field> = <value>'  or
        #          'filter <name> by <field> equals <value>'
        m = _re.search(
            r"filter\s+(.+?)\s+by\s+(.+?)\s*(?:=|equals|is)\s*(.+)",
            lower
        )
        if m and "filter_schedule" in self._dispatch_plugins:
            sched_name = m.group(1).strip()
            field_name = m.group(2).strip()
            value      = m.group(3).strip().rstrip(".?!,;:")
            action = {
                "action": "filter_schedule",
                "params": {
                    "schedule_name": sched_name,
                    "field":         field_name,
                    "condition":     "equals",
                    "value":         value,
                },
            }
            return ("Filtering '" + sched_name + "' where " + field_name
                    + " = " + value + "..."), action

        # ── workset visibility ────────────────────────────────────────────
        # Catches workset visibility requests BEFORE the LLM sees them.
        # Prevents hallucinated action names (toggle_worksets, manage_worksets etc.)
        if "workset_visibility" in self._dispatch_plugins:

            # set_all visible — catches:
            #   "make all workset(s) visible [in all views]"
            #   "turn on all worksets", "show all worksets", "enable all worksets"
            #   "all worksets visible/on", "turn all worksets on"
            #   "make worksets visible"
            if _re.search(
                r"make\s+all\s+worksets?\s+visible|"
                r"(?:turn\s+on|enable|show|unhide)\s+all\s+worksets?|"
                r"all\s+worksets?\s+(?:on|visible)|"
                r"turn\s+all\s+worksets?\s+on|"
                r"make\s+worksets?\s+(?:all\s+)?visible",
                lower
            ):
                action = {"action": "workset_visibility",
                          "params": {"mode": "set_all", "visibility": "visible"}}
                return (
                    "Making all worksets visible in the active view "
                    "(Revit workset visibility is per-view)."
                ), action

            # set_all hidden — catches:
            #   "turn off all worksets", "hide all worksets", "disable all worksets"
            #   "all worksets hidden/off", "turn all worksets off"
            if _re.search(
                r"(?:turn\s+off|disable|hide)\s+all\s+worksets?|"
                r"all\s+worksets?\s+(?:off|hidden)|"
                r"turn\s+all\s+worksets?\s+off|"
                r"make\s+all\s+worksets?\s+hidden",
                lower
            ):
                action = {"action": "workset_visibility",
                          "params": {"mode": "set_all", "visibility": "hidden"}}
                return "Hiding all worksets in the active view...", action

            # list worksets
            if _re.search(
                r"(?:list|show|display|what|which)\s+(?:are\s+(?:the\s+)?)?worksets?|"
                r"worksets?\s+(?:list|visibility|visible|hidden)|"
                r"(?:show\s+me\s+)?(?:the\s+)?worksets?$",
                lower
            ):
                action = {"action": "workset_visibility",
                          "params": {"mode": "list"}}
                return "Listing worksets...", action

            # set single workset visible
            m_vis = _re.search(
                r"(?:make|set|turn\s+on|show|enable|unhide)\s+(?:workset\s+)?['\"]?(.+?)['\"]?"
                r"\s+(?:workset\s+)?(?:visible|on|show)",
                lower
            )
            if m_vis:
                ws_name = m_vis.group(1).strip().strip("'\"")
                if ws_name not in ("all", "all worksets", "worksets", "the workset"):
                    action = {"action": "workset_visibility",
                              "params": {"mode": "set", "workset_name": ws_name,
                                         "visibility": "visible"}}
                    return "Making workset '" + ws_name + "' visible...", action

            # set single workset hidden
            m_hid = _re.search(
                r"(?:hide|turn\s+off|disable)\s+(?:workset\s+)?['\"]?(.+?)['\"]?"
                r"(?:\s+workset)?$",
                lower
            )
            if m_hid:
                ws_name = m_hid.group(1).strip().strip("'\"")
                if ws_name not in ("all", "all worksets", "worksets", "the workset"):
                    action = {"action": "workset_visibility",
                              "params": {"mode": "set", "workset_name": ws_name,
                                         "visibility": "hidden"}}
                    return "Hiding workset '" + ws_name + "'...", action

        return None

    # ── Send ────────────────────────────────────────────────────────────────

    def _on_send(self, s, e):
        try:
            text = self._input_box.Text.strip()
            if not text:
                return

            self._input_box.Text = ""
            self._add_user(text)
            self._history.append({"role": "user", "content": text})

            # ── Keyword shortcut — skip LLM for obvious requests ──────────
            intercept = self._try_intercept(text)
            if intercept is not None:
                prose, action = intercept
                self._add_bot(prose)
                self._history.append({"role": "assistant", "content": prose})
                if action and action.get("action") in self._dispatch_plugins:
                    self._add_run_bubble(action)
                return

            self._thinking_widget = self._add_thinking()
            self._send_btn.IsEnabled  = False
            self._input_box.IsEnabled = False

            model = self._get_selected_model()
            history_snapshot = list(self._history[:-1])
            result_queue = self._result_queue  # local ref for closure
            chat_fn = self._chat_fn  # local ref — module scope may be dead

            def _bg():
                try:
                    response, error = chat_fn(model, history_snapshot, text)
                    result_queue.put((response, error))
                except Exception as bg_ex:
                    result_queue.put((None, "Thread error: " + str(bg_ex)))

            t = self._threading.Thread(target=_bg)
            t.daemon = True
            t.start()
            self._poll_count = 0
            self._poll_timer.Start()

        except Exception as _ex:
            try:
                self._add_result("Send error: " + str(_ex), error=True)
            except Exception:
                pass

    def _on_poll(self, s, e):
        self._poll_count += 1
        try:
            response, error = self._result_queue.get_nowait()
        except self._queue_mod.Empty:
            # Timeout guard — stop after ~130 seconds
            if self._poll_count > 520:
                self._poll_timer.Stop()
                self._remove(self._thinking_widget)
                self._send_btn.IsEnabled  = True
                self._input_box.IsEnabled = True
                self._add_result(
                    u"Timed out waiting for AI backend. "
                    u"Check Ollama is running or your API key is set.",
                    error=True
                )
                self.window.Title = "Kidzink - Chat Assistant"
                # Discard any late result arriving after timeout so it cannot
                # bleed into the next message's response (SP2 fix).
                try:
                    self._result_queue.get_nowait()
                except Exception:
                    pass
            return

        self._poll_timer.Stop()

        try:
            self._remove(self._thinking_widget)
            self._send_btn.IsEnabled  = True
            self._input_box.IsEnabled = True
            self._input_box.Focus()

            if error:
                self._add_result(error, error=True)
                return

            clean, action = self._parse_action(response)

            # Guard: if model claimed success but returned no action block,
            # it's hallucinating — replace with a correction message.
            # _completion_claim_re is compiled once in __init__ and stored on self.
            _claim_re = self._completion_claim_re

            if action is None and clean and _claim_re.search(clean):
                clean = (
                    "I described what I would do but didn't generate an action. "
                    "Please try again — I'll include a Run button this time."
                )

            if clean:
                self._add_bot(clean)
            elif action:
                # Model returned only an action block with no text
                act_name = action.get("action", "").replace("_", " ").title()
                if act_name and act_name.lower() != "info only":
                    self._add_bot("Got it. Ready to " + act_name + ".")
            else:
                self._add_bot(response.strip() if response else "(no response)")

            self._history.append({"role": "assistant", "content": response})
            if len(self._history) > 12:
                self._history = self._history[-12:]

            if action and action.get("action") not in ("info_only", None):
                act_key = action.get("action", "")
                if act_key in self._blocked_actions:
                    self._add_result(
                        "Blocked: '" + act_key + "' is not a permitted action. "
                        "I can only run pre-approved Revit operations.",
                        error=True
                    )
                elif act_key in self._dispatch_plugins:
                    self._add_run_bubble(action)
                else:
                    # Find the closest known action by character-overlap score so
                    # the user gets an actionable hint rather than just "try rephrasing".
                    suggestion = ""
                    try:
                        ak = act_key.lower().replace("_", "")
                        best_score, best_name = 0, ""
                        for known in self._dispatch_plugins:
                            kn = known.lower().replace("_", "")
                            # Score = number of matching characters at shared positions
                            # plus a bonus for common prefix length
                            overlap = sum(1 for a, b in zip(ak, kn) if a == b)
                            prefix  = 0
                            for a, b in zip(ak, kn):
                                if a == b:
                                    prefix += 1
                                else:
                                    break
                            score = overlap + prefix
                            if score > best_score:
                                best_score, best_name = score, known
                        if best_name and best_score >= 2:
                            suggestion = " Did you mean: '" + best_name + "'?"
                    except Exception:
                        pass
                    self._add_result(
                        "Assistant suggested an unsupported action: '"
                        + act_key + "'." + suggestion
                        + " Try rephrasing your request.",
                        error=True
                    )

        except Exception as _ex:
            self._add_result("[POLL ERROR] " + str(_ex), error=True)

    # ── Execute ─────────────────────────────────────────────────────────────

    def _execute(self, action_dict):
        # Restore module globals for action functions (pyRevit cleared them)
        try:
            self._dispatch_action.__globals__.update(self._saved_globals)
        except Exception:
            pass
        self._ext_handler.action_dict = action_dict
        self._ext_event.Raise()

    def _on_action_result(self, result):
        if result is not None:
            r = str(result).lower()
            # Prefix-pattern detection avoids false-positives on legitimate
            # result strings that happen to contain "error" or "unknown"
            # (e.g. "Unknown count: 0 elements" or "Error tolerance: OK").
            is_err = (
                r.startswith("action failed") or
                r.startswith("unknown action") or
                r.startswith("blocked:") or
                r.startswith("error:") or
                "traceback (most recent" in r
            )
            self._add_result(str(result), error=is_err)
        else:
            self._add_result(u"Done \u2713")

    # ── Export ──────────────────────────────────────────────────────────────

    def _on_export(self, s, e):
        try:
            path = self._export_chat()
            self._add_result(u"Chat exported \u2713  " + path)
        except Exception as _ex:
            self._add_result("Export failed: " + str(_ex), error=True)

    def _export_chat(self):
        """Walk chat panel children, classify each bubble, write plain-text
        transcript to Desktop as KidzinkChat_<timestamp>.txt.

        Classification uses existing visual properties — no Tag needed:
          User bubble   : HorizontalAlignment.Right               → "You: <text>"
          Bot bubble    : white bg, Left, no left border          → "Koda: <text>"
          Result/Error  : Left, coloured left border              → "[Result]" / "[Error]"
          Action bubble : StackPanel child (Run button)           → "[Action] <text>"
          Chips         : grey background (LGREY/DGREY)           → skipped
        """
        import io as _io
        import os as _os
        import datetime as _dt

        lines = []
        lines.append("Kidzink Koda — Chat Export")
        lines.append("Exported: " + _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        lines.append("=" * 60)
        lines.append("")

        _HA_Right = self._HorizontalAlignment.Right
        _HA_Left  = self._HorizontalAlignment.Left
        _zero     = self._Thickness(0)

        for child in self._chat_panel.Children:
            try:
                child_content = getattr(child, "Child", None)
                if child_content is None:
                    continue

                # StackPanel child → action run bubble
                from System.Windows.Controls import StackPanel as _SPC
                if isinstance(child_content, _SPC):
                    from System.Windows.Controls import TextBlock as _TBC
                    for sp_child in child_content.Children:
                        if isinstance(sp_child, _TBC) and sp_child.Text:
                            lines.append("[Action] " + sp_child.Text)
                            break
                    continue

                from System.Windows.Controls import TextBlock as _TBC2
                if not isinstance(child_content, _TBC2):
                    continue
                raw_text = child_content.Text
                if not raw_text:
                    continue

                # Skip capability/canned-prompt chips (grey background)
                bg = getattr(child, "Background", None)
                if bg is not None:
                    try:
                        c = bg.Color
                        if (c.R == c.G == c.B) and c.R in (0xC0, 0x80):
                            continue
                    except Exception:
                        pass

                align = getattr(child, "HorizontalAlignment", None)
                if align == _HA_Right:
                    lines.append("You: " + raw_text)
                elif align == _HA_Left:
                    bt = getattr(child, "BorderThickness", _zero)
                    if bt.Left > 0:
                        bb = getattr(child, "BorderBrush", None)
                        is_error = False
                        if bb is not None:
                            try:
                                c = bb.Color
                                is_error = (c.R > 0xC0 and c.G < 0x80)
                            except Exception:
                                pass
                        prefix = "[Error]  " if is_error else "[Result] "
                        lines.append(prefix + raw_text)
                    else:
                        lines.append("Koda: " + raw_text)
            except Exception:
                continue

        lines.append("")
        lines.append("=" * 60)
        lines.append("End of export")

        import datetime as _dt2
        ts      = _dt2.datetime.now().strftime("%Y%m%d_%H%M%S")
        desktop = _os.path.join(_os.environ.get("USERPROFILE", ""), "Desktop")
        if not _os.path.isdir(desktop):
            desktop = _os.environ.get("USERPROFILE", _os.getcwd())
        fpath   = _os.path.join(desktop, "KidzinkChat_" + ts + ".txt")

        with _io.open(fpath, "w", encoding="utf-8") as fh:
            fh.write(u"\r\n".join(lines))
        return fpath

    # ── Clear ───────────────────────────────────────────────────────────────

    def _on_clear(self, s, e):
        self._chat_panel.Children.Clear()
        self._history = []
        self._add_bot("Chat cleared. How can I help?")

    def show(self):
        if self.window.IsLoaded:
            self.window.Activate()
        else:
            self.window.Show()

# ══════════════════════════════════════════════════════════════════════════════
# ENTRY
# ══════════════════════════════════════════════════════════════════════════════

_SINGLETON_KEY = "kidzink_koda_chat_window_v1"

def main():
    global _CHAT_WINDOW
    # Load WPF assemblies now — safe on the dispatcher thread, never at module scope.
    _load_wpf()
    # Load capability plugins now — deferred here so no WPF/CLR object construction
    # happens at module scope (which causes CLR 0xe0434352 crashes on second invocation).
    _load_plugins()

    # __revit__ is a stable CLR UIApplication object that persists for the
    # entire Revit session — more reliable than sys.modules which pyRevit may
    # reload or sandbox differently per script execution.
    existing = getattr(__revit__, _SINGLETON_KEY, None)
    if existing is not None:
        try:
            win = existing.window
            if win.IsLoaded:
                _WinState = WindowState  # already loaded by _load_wpf()
                if not win.IsVisible:
                    win.Show()
                if win.WindowState == _WinState.Minimized:
                    win.WindowState = _WinState.Normal
                win.Topmost = True
                win.Activate()
                win.Focus()
                win.Topmost = False
                _CHAT_WINDOW = existing
                return
        except Exception:
            pass
        # Stale — window was closed; clear and fall through to create
        try:
            setattr(__revit__, _SINGLETON_KEY, None)
        except Exception:
            pass

    _CHAT_WINDOW = ChatWindow()
    try:
        setattr(__revit__, _SINGLETON_KEY, _CHAT_WINDOW)
    except Exception:
        # Fallback to sys.modules if __revit__ doesn't accept dynamic attrs
        sys.modules[_SINGLETON_KEY] = _CHAT_WINDOW
    _CHAT_WINDOW.window.Show()

try:
    main()
except Exception as _ex:
    import traceback as _tb
    _msg = _tb.format_exc()
    try:
        td = TaskDialog("Kidzink Chat - Error")
        td.MainContent = _msg
        td.Show()
    except Exception:
        sys.stderr.write("KIDZINK CHAT CRASH:\n" + _msg)