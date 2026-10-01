# -*- coding: utf-8 -*-
# capabilities/list_sheets.py
# Plugin: list all sheets in the model with key properties.

ACTION_NAME  = "list_sheets"
DESCRIPTION  = (
    "List all sheets in the model with sheet number, name, "
    "current revision, and issued/not-issued status."
)
PARAMS       = {}
EXAMPLE      = {
    "action": "list_sheets",
    "params": {},
}


def execute(params, doc, uidoc, **_kwargs):
    from Autodesk.Revit.DB import (
        FilteredElementCollector, ViewSheet, BuiltInParameter
    )

    if not doc:
        return "No document open."
    try:
        sheets = list(
            FilteredElementCollector(doc)
            .OfClass(ViewSheet)
            .ToElements()
        )
    except Exception as e:
        return "Failed to collect sheets: " + str(e)

    if not sheets:
        return "No sheets found in the model."

    entries = []
    for sh in sheets:
        # Sheet number
        num = ""
        try:
            num = sh.SheetNumber or ""
        except Exception:
            try:
                p = sh.get_Parameter(BuiltInParameter.SHEET_NUMBER)
                if p is not None:
                    num = p.AsString() or ""
            except Exception:
                pass

        # Sheet name
        name = ""
        try:
            name = sh.Name or ""
        except Exception:
            try:
                p = sh.get_Parameter(BuiltInParameter.SHEET_NAME)
                if p is not None:
                    name = p.AsString() or ""
            except Exception:
                pass

        # Current revision
        rev = ""
        try:
            p = sh.get_Parameter(BuiltInParameter.SHEET_CURRENT_REVISION)
            if p is not None:
                rev = p.AsString() or ""
        except Exception:
            pass

        # Issued status
        issued = ""
        try:
            p = sh.get_Parameter(BuiltInParameter.SHEET_ISSUE_DATE)
            if p is not None:
                d = p.AsString() or ""
                if d:
                    issued = "Issued: " + d
        except Exception:
            pass
        if not issued:
            try:
                p = sh.get_Parameter(BuiltInParameter.SHEET_ISSUED)
                if p is not None:
                    if p.AsInteger() == 1:
                        issued = "Issued"
            except Exception:
                pass

        entry = num + " - " + name
        if rev:
            entry += " | Rev: " + rev
        if issued:
            entry += " | " + issued
        entries.append((num, entry))

    # Sort by sheet number
    entries.sort(key=lambda x: x[0])
    lines = [e[1] for e in entries]

    if len(lines) > 30:
        return (str(len(lines)) + " sheet(s) (showing first 30):\n"
                + "\n".join(lines[:30]))
    return str(len(lines)) + " sheet(s):\n" + "\n".join(lines)