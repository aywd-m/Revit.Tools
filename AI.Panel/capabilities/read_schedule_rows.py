# -*- coding: utf-8 -*-
# capabilities/read_schedule_rows.py
# Plugin: read the actual cell data from a schedule view.

ACTION_NAME  = "read_schedule_rows"
DESCRIPTION  = (
    "Read the cell data (rows and columns) from an existing schedule view. "
    "Returns the column headers and up to 'max_rows' data rows as a formatted table. "
    "Use this when the user asks to 'show', 'read', 'print', 'display', 'get data from', "
    "'what's in', 'list contents of', or 'export' a schedule. "
    "Also use when the user asks for a count or total from a schedule "
    "('how many doors', 'what is the total area in the rooms schedule'). "
    "The 'name' param supports partial match — 'Doors' matches 'Doors Schedule'. "
    "If multiple schedules match, the first alphabetical match is used and others are listed. "
    "Set 'max_rows' to limit output (default 50, max 500). "
    "Set 'columns' to read only specific column headers (case-insensitive partial match). "
    "This action is READ-ONLY — it never modifies the schedule."
)
PARAMS = {
    "name":     "string — schedule name or partial name to match (required)",
    "max_rows": "integer — maximum data rows to return (default 50, max 500)",
    "columns":  "list   — optional list of column header substrings to include (default: all columns)",
}
EXAMPLE = {
    "action": "read_schedule_rows",
    "params": {
        "name":     "Doors Schedule",
        "max_rows": 50,
    },
}
# Fix R* (equiv of C9): EXAMPLE_2 and EXAMPLE_3 removed — dispatcher reads only EXAMPLE.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_schedule(doc, name_query):
    """Return (best_match_schedule, [other_match_names]) or (None, []).

    Single collector pass — no double scan.
    """
    from Autodesk.Revit.DB import FilteredElementCollector, ViewSchedule

    nl         = name_query.strip().lower()
    candidates = []
    for s in FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements():
        try:
            if s.IsTemplate:
                continue
            if nl in s.Name.lower():
                candidates.append(s)
        except Exception:
            pass

    if not candidates:
        return None, []

    candidates.sort(key=lambda s: s.Name.lower())
    best   = candidates[0]
    others = [s.Name for s in candidates[1:]]
    return best, others


def _col_indices(headers, column_filter):
    """Return list of column indices to include.

    column_filter is a list of substrings (case-insensitive). Empty = all columns.
    """
    if not column_filter:
        return list(range(len(headers)))
    cf = [c.lower() for c in column_filter]
    return [i for i, h in enumerate(headers) if any(sub in h.lower() for sub in cf)]


def _read_rows(sched, doc, max_rows, column_filter):
    """Extract headers + data rows from a ViewSchedule.

    Returns (headers, rows, total_data_rows) where:
      headers         — list of column header strings (filtered by column_filter)
      rows            — list of lists of cell strings (filtered, capped at max_rows)
      total_data_rows — true data row count (body rows excluding the header row)

    Fix R2: Revit's body SectionData row 0 is the column-header row when
            ShowHeaders=True — data rows start at index 1.  We detect this by
            comparing row-0 text against the header section text and skip it when
            they match, so we never include a duplicate header as a data row.
    Fix R3: SectionType enum used instead of magic int constants.
    Fix R6: stale ViewSchedule import-as-load-check removed from this function;
            the import is only needed in execute() where the type is actually used.
    Fix R1: ScheduleField.GetName() (no argument) used in the fallback path —
            GetName(doc) is the SchedulableField overload; the added-column object
            GetName() takes no argument.
    """
    from Autodesk.Revit.DB import SectionType  # Fix R3: use enum, not magic ints.

    st = sched.GetTableData()
    if st is None:
        return [], [], 0

    header_sec = st.GetSectionData(SectionType.Header)
    body_sec   = st.GetSectionData(SectionType.Body)

    if body_sec is None:
        return [], [], 0

    col_count = body_sec.NumberOfColumns

    # ── Collect column headers from the last row of the header section ────────
    raw_headers = []
    if header_sec is not None and header_sec.NumberOfRows > 0:
        last_header_row = header_sec.NumberOfRows - 1
        for c in range(col_count):
            try:
                raw_headers.append(
                    sched.GetCellText(SectionType.Header, last_header_row, c)
                )
            except Exception:
                raw_headers.append("Col" + str(c))
    else:
        # Fallback: read field display names from the schedule definition.
        # Fix R1: ScheduleField (added column) uses GetName() with no argument.
        #         GetName(doc) is the SchedulableField overload — wrong object here.
        defn    = sched.Definition
        sf_list = []
        try:
            for fid in defn.GetFieldOrder():
                try:
                    sf_obj = defn.GetField(fid)
                    sf_list.append(sf_obj.GetName())   # no-arg overload for ScheduleField
                except Exception:
                    sf_list.append("Col" + str(len(sf_list)))
        except Exception:
            pass
        raw_headers = sf_list if sf_list else ["Col" + str(c) for c in range(col_count)]

    col_indices = _col_indices(raw_headers, column_filter)
    headers     = [raw_headers[i] for i in col_indices if i < len(raw_headers)]

    # ── Determine data-row start index ───────────────────────────────────────
    # Fix R2: when ShowHeaders=True Revit includes a column-header row as row 0
    # of the body section.  Detect it by comparing its cell text against the
    # already-collected header text.  Skip it when matched so it does not appear
    # as a data row and so total_data_rows is reported correctly.
    body_total  = body_sec.NumberOfRows
    data_start  = 0
    if body_total > 0 and raw_headers:
        # Read the first body cell and compare to the corresponding header text.
        try:
            first_cell = sched.GetCellText(SectionType.Body, 0, 0)
            if first_cell == raw_headers[0]:
                data_start = 1
        except Exception:
            pass

    total_data_rows = max(0, body_total - data_start)
    cap             = min(total_data_rows, max(1, max_rows))

    rows = []
    for r in range(data_start, data_start + cap):
        row = []
        for c in col_indices:
            if c >= col_count:
                row.append("")
                continue
            try:
                row.append(sched.GetCellText(SectionType.Body, r, c))
            except Exception:
                row.append("")
        rows.append(row)

    return headers, rows, total_data_rows


def _format_table(headers, rows, total_rows, max_rows, sched_name, others):
    """Format headers + rows as a readable plain-text table."""
    if not headers and not rows:
        return "Schedule '" + sched_name + "' contains no data."

    lines = []

    # Disambiguation notice when multiple schedules matched the query.
    if others:
        lines.append(
            "Multiple schedules matched — showing '" + sched_name + "'. "
            "Others: " + ", ".join(others) + "."
        )

    lines.append("Schedule: " + sched_name)

    # Column widths: max of header width and widest cell in that column.
    col_count = len(headers)
    widths    = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                widths[i] = max(widths[i], len(cell))

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt_row(cells):
        parts = []
        for i, w in enumerate(widths):
            cell = cells[i] if i < len(cells) else ""
            parts.append(" " + cell.ljust(w) + " ")
        return "|" + "|".join(parts) + "|"

    lines.append(sep)
    lines.append(fmt_row(headers))
    lines.append(sep)
    for row in rows:
        lines.append(fmt_row(row))
    lines.append(sep)

    shown   = len(rows)
    summary = "Showing {0} of {1} rows.".format(shown, total_rows)
    if total_rows > max_rows:
        summary += " {0} rows truncated — increase max_rows to see more.".format(
            total_rows - max_rows
        )
    lines.append(summary)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def execute(params, doc, uidoc, **_kwargs):
    from Autodesk.Revit.DB import FilteredElementCollector, ViewSchedule

    if not doc:
        return "No document open."

    name_query = (params.get("name") or "").strip()
    if not name_query:
        return (
            "Please specify a schedule name. "
            "Use list_schedules to see all available schedules."
        )

    raw_max = params.get("max_rows", 50)
    try:
        max_rows = max(1, min(500, int(raw_max)))
    except (TypeError, ValueError):
        max_rows = 50

    column_filter = params.get("columns") or []
    if isinstance(column_filter, str):
        column_filter = [column_filter]

    # ── Find schedule ─────────────────────────────────────────────────────────
    try:
        sched, others = _find_schedule(doc, name_query)
    except Exception as e:
        return "Failed to search schedules: " + str(e)

    if sched is None:
        all_names = []
        try:
            all_names = sorted(
                s.Name for s in
                FilteredElementCollector(doc).OfClass(ViewSchedule).ToElements()
                if not s.IsTemplate
            )
        except Exception:
            pass
        msg = "No schedule matching '" + name_query + "' found."
        if all_names:
            msg += " Available schedules: " + ", ".join(all_names) + "."
        else:
            msg += " No schedules exist in this model."
        return msg

    # ── Read rows ─────────────────────────────────────────────────────────────
    try:
        headers, rows, total_rows = _read_rows(sched, doc, max_rows, column_filter)
    except Exception as e:
        return "Failed to read schedule '" + sched.Name + "': " + str(e)

    return _format_table(headers, rows, total_rows, max_rows, sched.Name, others)
