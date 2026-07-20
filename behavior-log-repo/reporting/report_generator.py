#!/usr/bin/env python3
"""
Behavior Log Reporting Suite — reference implementation.

Standard library only. No installs, no network access.

Reads "<student>_behavior_log.csv" files from a data folder and writes
weekly Markdown reports to <data_dir>/reports/<student>/. Safe to re-run
at any time, any number of times, at any interval -- it derives which
weeks still need a report from the calendar and from a small state file
(.report_state.json) written next to the CSVs, not from "when did I last
run this."

Usage:
    python report_generator.py <data_dir>

See SPEC.md for the full design rationale.
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

STATE_FILENAME = ".report_state.json"
CSV_SUFFIX = "_behavior_log.csv"


# ---------------------------------------------------------------------------
# State handling
# ---------------------------------------------------------------------------

def load_state(data_dir: Path) -> dict:
    state_path = data_dir / STATE_FILENAME
    if not state_path.exists():
        return {}
    try:
        with state_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable state file: fail safe by treating as empty
        # rather than crashing. Worst case, some already-finalized weeks
        # get rewritten (idempotent, harmless) instead of the run failing.
        return {}


def save_state(data_dir: Path, state: dict) -> None:
    state_path = data_dir / STATE_FILENAME
    with state_path.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------

def read_student_rows(csv_path: Path) -> list[dict]:
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("date"):
                continue  # skip malformed/blank rows rather than crash the run
            rows.append(row)
    return rows


def parse_date(date_str: str) -> date:
    return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# Week bucketing
# ---------------------------------------------------------------------------

def week_bounds(d: date) -> tuple[date, date]:
    """Return (Monday, Sunday) for the calendar week containing d."""
    monday = d - timedelta(days=d.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def group_rows_by_week(rows: list[dict]) -> dict[tuple[date, date], list[dict]]:
    weeks = defaultdict(list)
    for row in rows:
        d = parse_date(row["date"])
        weeks[week_bounds(d)].append(row)
    return weeks


# ---------------------------------------------------------------------------
# Report content
# ---------------------------------------------------------------------------

def on_task_pct(interval_str: str) -> float | None:
    """
    Interval strings use check/cross marks, e.g. '✓✓✗✗✓'. Returns percent
    on-task, ignoring any non-mark characters. Returns None if there's
    nothing to score (e.g. an empty interval string).
    """
    marks = [c for c in interval_str if c in "✓✗"]
    if not marks:
        return None
    on_task = sum(1 for c in marks if c == "✓")
    return round(100 * on_task / len(marks))


def build_report(student: str, week_start: date, week_end: date,
                  rows: list[dict], provisional: bool) -> str:
    rows_by_date = defaultdict(list)
    for row in rows:
        rows_by_date[row["date"]].append(row)

    attendance_counts = defaultdict(int)
    incidents = []
    daily_on_task = {}

    for day, day_rows in sorted(rows_by_date.items()):
        pcts = [on_task_pct(r.get("intervals", "")) for r in day_rows]
        pcts = [p for p in pcts if p is not None]
        if pcts:
            daily_on_task[day] = round(sum(pcts) / len(pcts))

        for r in day_rows:
            attendance_counts[r.get("attendance", "Unknown")] += 1
            if r.get("incident_occurred", "").strip().lower() == "yes":
                incidents.append(r)

    lines = []
    title_suffix = "  _(provisional — week in progress)_" if provisional else ""
    lines.append(f"# {student} — Week of {week_start.isoformat()} to {week_end.isoformat()}{title_suffix}")
    lines.append("")
    lines.append(f"Periods logged: {len(rows)}")

    att_summary = ", ".join(f"{count} {status}" for status, count in sorted(attendance_counts.items()))
    lines.append(f"Attendance: {att_summary}" if att_summary else "Attendance: no data")
    lines.append("")

    if daily_on_task:
        overall = round(sum(daily_on_task.values()) / len(daily_on_task))
        lines.append(f"On-task rate: {overall}% average across logged intervals")
        for day in sorted(daily_on_task):
            lines.append(f"  {day}: {daily_on_task[day]}%")
    else:
        lines.append("On-task rate: no interval data logged this week")
    lines.append("")

    lines.append(f"Incidents: {len(incidents)}")
    for inc in incidents:
        lines.append(f"  - {inc.get('date')} {inc.get('period', '')}:")
        for field in ("antecedent", "behavior", "consequence"):
            val = inc.get(field, "").strip()
            if val:
                lines.append(f"      {field}: {val}")
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def process_student(csv_path: Path, data_dir: Path, state: dict, today: date) -> None:
    student = csv_path.name[: -len(CSV_SUFFIX)]
    rows = read_student_rows(csv_path)
    if not rows:
        return

    weeks = group_rows_by_week(rows)
    student_state = state.setdefault(student, {})
    last_finalized_str = student_state.get("last_finalized_week_end")
    last_finalized = parse_date(last_finalized_str) if last_finalized_str else None

    out_dir = data_dir / "reports" / student
    out_dir.mkdir(parents=True, exist_ok=True)

    current_week_start, _ = week_bounds(today)

    for (week_start, week_end) in sorted(weeks):
        if last_finalized is not None and week_end <= last_finalized:
            continue  # already finalized -- never touch again

        provisional = week_start == current_week_start
        report_text = build_report(student, week_start, week_end, weeks[(week_start, week_end)], provisional)

        out_path = out_dir / f"{week_start.isoformat()}_to_{week_end.isoformat()}.md"
        out_path.write_text(report_text, encoding="utf-8")

        if not provisional:
            student_state["last_finalized_week_end"] = week_end.isoformat()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python report_generator.py <data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1]).resolve()
    if not data_dir.is_dir():
        print(f"Not a folder: {data_dir}")
        sys.exit(1)

    today = date.today()
    state = load_state(data_dir)

    csv_files = sorted(data_dir.glob(f"*{CSV_SUFFIX}"))
    if not csv_files:
        print(f"No *{CSV_SUFFIX} files found in {data_dir}")
        return

    for csv_path in csv_files:
        process_student(csv_path, data_dir, state, today)
        print(f"Processed {csv_path.name}")

    save_state(data_dir, state)
    print(f"Reports written to {data_dir / 'reports'}")


if __name__ == "__main__":
    main()
