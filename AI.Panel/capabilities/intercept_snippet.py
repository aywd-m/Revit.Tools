# -*- coding: utf-8 -*-
# capabilities/intercept_snippet.py

import re as _re


def execute(user_input, dispatch_plugins, **_kwargs):
    """
    Intercepts known user phrases BEFORE the LLM sees them.
    Returns (message, action) tuple if intercepted, or (None, None) to fall through.
    """

    lower = user_input.lower().strip()

    # -- workset visibility -------------------------------------------
    # Catches workset visibility requests BEFORE the LLM sees them.
    # Prevents hallucinated action names (toggle_worksets, manage_worksets etc.)
    if "workset_visibility" in dispatch_plugins:

        # set_all visible -- catches:
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
                "Making all worksets visible in the active view\n"
                "(Note: Revit workset visibility is per-view -- "
                "repeat for other views if needed)."
            ), action

        # set_all hidden -- catches:
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

        # list worksets -- catches:
        #   "list worksets", "show worksets", "what are the worksets"
        #   "show me workset visibility", "worksets?", "worksets "
        if _re.search(
            r"(?:list|show|display|what|which)\s+(?:are\s+(?:the\s+)?)?worksets?|"
            r"show\s+(?:me\s+)?workset\s+visibility|"
            r"worksets?\s+(?:list|visibility|visible|hidden)|"
            r"(?:show\s+me\s+)?(?:the\s+)?worksets?\s*[?.]?$",
            lower
        ):
            action = {"action": "workset_visibility",
                      "params": {"mode": "list"}}
            return "Listing worksets...", action

        # set single workset visible -- catches:
        #   "make Shared Levels and Grids visible"
        #   "show workset Architecture on"
        #   "enable 'Mechanical' workset"
        m_vis = _re.search(
            r"(?:make|set|turn\s+on|show|enable|unhide)\s+(?:workset\s+)?['\"]?(.+?)['\"]?"
            r"\s+(?:workset\s+)?(?:visible|on|show)",
            lower
        )
        if m_vis:
            ws_name = m_vis.group(1).strip().strip("'\"")
            # Strip leading articles and noise words that leak from the capture group
            ws_name = _re.sub(r"^(the|a|an|workset)\s+", "", ws_name).strip()
            # Guard: skip generic "all" phrases -- should have matched set_all above
            if ws_name not in ("all", "all worksets", "worksets", "the workset"):
                action = {"action": "workset_visibility",
                          "params": {"mode": "set", "workset_name": ws_name,
                                     "visibility": "visible"}}
                return "Making workset '" + ws_name + "' visible...", action

        # set single workset hidden -- catches:
        #   "hide Shared Levels and Grids"
        #   "turn off workset Mechanical"
        #   "disable 'Architecture'"
        # Guard: require the word "workset" somewhere in the phrase to avoid
        # matching unrelated hide commands (e.g. "hide the lights in the model")
        if "workset" in lower:
            m_hid = _re.search(
                r"(?:hide|turn\s+off|disable)\s+(?:workset\s+)?['\"]?(.+?)['\"]?"
                r"(?:\s+workset)?\s*[?.]?$",
                lower
            )
            if m_hid:
                ws_name = m_hid.group(1).strip().strip("'\"")
                # Strip leading articles and noise words
                ws_name = _re.sub(r"^(the|a|an|workset)\s+", "", ws_name).strip()
                if ws_name not in ("all", "all worksets", "worksets", "the workset"):
                    action = {"action": "workset_visibility",
                              "params": {"mode": "set", "workset_name": ws_name,
                                         "visibility": "hidden"}}
                    return "Hiding workset '" + ws_name + "'...", action

    # No pattern matched -- fall through to LLM dispatch
    return None, None
