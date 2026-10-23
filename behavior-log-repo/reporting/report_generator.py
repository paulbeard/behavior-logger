#!/usr/bin/env python3
"""
Behavior Log Reporting Suite -- reference implementation.

Standard library only. No installs, no network access.

Reads "<student>_behavior_log*.csv" files (dated day files, _final copies, numbered repeats, all merged) from a data folder and writes, for each student:

    reports/<student>/daily/YYYY-MM-DD.md                  one report per school day, period by period
    reports/<student>/weekly/YYYY-MM-DD_to_YYYY-MM-DD.md   weekly summary (Monday-Sunday)

Safe to re-run at any time, any number of times, at any interval. Which reports are
written is decided by the data itself, not by "when did I last run this": a day or week
is (re)written whenever its report is missing or the number of entries behind it has
changed since it was last written. Miss three weeks, run once, get everything.

Messy input is expected and handled:
  * Browsers that cannot overwrite a file save repeats as "Jordan_behavior_log (1).csv",
    "(2)", ... All copies for a student are read together and duplicate rows (same
    submitted_at) are dropped.
  * Files combined by hand: header lines pasted into the middle are ignored; dates that
    Excel rewrote as 10/21/2026 are understood.
  * Rows that cannot be read are counted and reported, never silently dropped.

Usage:
    python report_generator.py <data_dir>

See SPEC.md for the full design rationale.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

STATE_FILENAME = "report_state.json"  # visible on purpose; delete it to force a full rebuild

# Matches every name the logger can produce, e.g.
#   Jordan_behavior_log.csv                      (older versions)
#   Jordan_behavior_log_2026-10-22.csv           (one day's periods)
#   Jordan_behavior_log_2026-10-22_final.csv     (end-of-day copy)
#   Jordan_behavior_log_2026-10-22 (1).csv       (browser-numbered repeats)
#   Jordan_behavior_log - Copy.csv
FILENAME_RE = re.compile(
    r"^(?P<student>.+?)_behavior_log"
    r"(?:_\d{4}-\d{2}-\d{2})?(?:_final)?"
    r"(?:\s*\(\d+\)|\s*-\s*Copy(?:\s*\(\d+\))?)?\.csv$",
    re.IGNORECASE,
)

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%m-%d-%Y")


# ---------------------------------------------------------------------------
# State handling
# ---------------------------------------------------------------------------

def load_state(data_dir: Path) -> dict:
    path = data_dir / STATE_FILENAME
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # Unreadable state file: treat as empty. Worst case, reports get rewritten
        # (harmless, same content).
        return {}


def save_state(data_dir: Path, state: dict) -> None:
    with (data_dir / STATE_FILENAME).open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# CSV discovery and reading
# ---------------------------------------------------------------------------

def find_student_files(data_dir: Path) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(data_dir.iterdir()):
        if path.is_file():
            m = FILENAME_RE.match(path.name)
            if m:
                groups[m.group("student")].append(path)
    return groups


def read_csv_rows(csv_path: Path) -> list[dict]:
    rows = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:  # -sig: tolerate Excel's BOM
        for row in csv.DictReader(f):
            date_val = (row.get("date") or "").strip()
            if not date_val or date_val.lower() == "date":
                continue  # blank row, or a header line pasted into the middle of a combined file
            rows.append(row)
    return rows


def row_key(row: dict) -> tuple:
    """Identity of a logged entry. The logger stamps every row with submitted_at."""
    ts = (row.get("submitted_at") or "").strip()
    if ts:
        return ("ts", ts)
    return ("row", tuple(sorted((k, (v or "").strip()) for k, v in row.items() if k)))


def read_student_rows(paths: list[Path]) -> tuple[list[dict], int]:
    seen, rows, dropped = set(), [], 0
    for path in paths:
        for row in read_csv_rows(path):
            key = row_key(row)
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            rows.append(row)
    return rows, dropped


def parse_date(text: str) -> date:
    """Accepts the logger's YYYY-MM-DD plus the formats Excel writes on re-save."""
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date: {text!r}")


def week_bounds(d: date) -> tuple[date, date]:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def group_rows(rows: list[dict]) -> tuple[dict[date, list[dict]], list[str]]:
    """Group rows by day. Returns (days, bad_dates); unreadable dates are reported."""
    days: dict[date, list[dict]] = defaultdict(list)
    bad = []
    for row in rows:
        try:
            d = parse_date(row.get("date", ""))
        except ValueError:
            bad.append(row.get("date", ""))
            continue
        row["date"] = d.isoformat()  # normalise
        days[d].append(row)
    return days, bad


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------

def val(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def one_line(text: str) -> str:
    return " ".join(text.split())


def period_sort_key(row: dict) -> tuple:
    p = val(row, "period")
    m = re.search(r"\d+", p)
    return (int(m.group()) if m else 999, p, val(row, "submitted_at"))


def on_task_pct(intervals: str) -> int | None:
    """Intervals look like '✓ ✓ ✗ — ✓' (— = N/A, blank = not marked).
    Percent on-task over scored (✓/✗) intervals; None if nothing to score."""
    marks = [c for c in (intervals or "") if c in "✓✗"]
    if not marks:
        return None
    return round(100 * sum(1 for c in marks if c == "✓") / len(marks))


def day_on_task(rows: list[dict]) -> int | None:
    """Day figure = pooled over all scored intervals that day (every interval counts equally)."""
    marks = [c for r in rows for c in val(r, "intervals") if c in "✓✗"]
    if not marks:
        return None
    return round(100 * sum(1 for c in marks if c == "✓") / len(marks))


def is_incident(row: dict) -> bool:
    return val(row, "incident_occurred").lower() == "yes"


def sound_summary(row: dict) -> str:
    parts = []
    for key, label in (("sound_clapping", "Clapping"), ("sound_vocalization", "Vocalizations"),
                       ("sound_blurts", "Blurts")):
        if val(row, key).lower() == "yes":
            n = val(row, key + "_count")
            parts.append(f"{label} x{n}" if n else label)
    if val(row, "sound_other").lower() == "yes":
        parts.append(val(row, "sound_other_desc") or "Other")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------

def build_daily(student: str, day: date, rows: list[dict]) -> str:
    rows = sorted(rows, key=period_sort_key)
    pct = day_on_task(rows)
    incidents = sum(1 for r in rows if is_incident(r))

    out = [f"# {student} -- {day.strftime('%A')} {day.isoformat()}", ""]
    summary = [f"{len(rows)} period(s) logged"]
    if pct is not None:
        summary.append(f"on-task {pct}%")
    summary.append(f"{incidents} incident(s)")
    out += [" | ".join(summary), ""]

    for r in rows:
        header = f"## {val(r, 'period') or 'Period ?'}"
        if val(r, "observer"):
            header += f" -- {val(r, 'observer')}"
        out += [header, ""]

        att = val(r, "attendance") or "Unknown"
        if val(r, "arrival_time"):
            att += f" (arrived {val(r, 'arrival_time')})"
        out.append(f"- Attendance: {att}")

        iv = val(r, "intervals")
        if iv:
            p = on_task_pct(iv)
            dur = f", {val(r, 'class_duration')} min" if val(r, "class_duration") else ""
            out.append(f"- On-task intervals{dur}: {iv}" + (f"  ({p}%)" if p is not None else ""))

        for label, key in (("Phone use", "phone"), ("Phone interaction", "phone_log")):
            if val(r, key):
                out.append(f"- {label}: {one_line(val(r, key))}")
        sounds = val(r, "sounds")
        detail = sound_summary(r)
        if sounds or detail:
            out.append(f"- Disruptive sounds: {sounds}" + (f" ({detail})" if detail else ""))
        if val(r, "comments") or val(r, "comments_count"):
            n = f" (count: {val(r, 'comments_count')})" if val(r, "comments_count") else ""
            out.append(f"- Disruptive comments: {val(r, 'comments') or '-'}{n}")
        if val(r, "comments_log"):
            out.append(f"- Comments logged: {one_line(val(r, 'comments_log'))}")
        if val(r, "tasks"):
            out.append(f"- Tasks completed: {val(r, 'tasks')}")
        if val(r, "arguing"):
            out.append(f"- Arguing: {val(r, 'arguing')}")
        if val(r, "task_narrative"):
            out.append(f"- Task notes: {one_line(val(r, 'task_narrative'))}")
        if val(r, "observations"):
            out.append(f"- Observations: {one_line(val(r, 'observations'))}")

        if is_incident(r):
            out += ["", "**Incident**", ""]
            for label, key in (("Emotional regulation", "regulation"), ("Elopement time", "elopement_time"),
                               ("Incident time", "incident_time"), ("Antecedent", "antecedent"),
                               ("Behavior", "behavior"), ("Consequence", "consequence")):
                if val(r, key):
                    out.append(f"- {label}: {one_line(val(r, key))}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Weekly summary
# ---------------------------------------------------------------------------

def build_weekly(student: str, start: date, end: date,
                 days: dict[date, list[dict]], provisional: bool) -> str:
    all_rows = [r for d in sorted(days) for r in days[d]]
    suffix = "  _(provisional -- week in progress)_" if provisional else ""
    out = [f"# {student} -- Weekly summary, {start.isoformat()} to {end.isoformat()}{suffix}", ""]

    att = defaultdict(int)
    for r in all_rows:
        att[val(r, "attendance") or "Unknown"] += 1
    att_text = ", ".join(f"{n} {k}" for k, n in sorted(att.items()))
    out += [f"Days with entries: {len(days)} | Periods logged: {len(all_rows)}",
            f"Attendance: {att_text or 'no data'}", ""]

    pooled = day_on_task(all_rows)
    out.append(f"On-task rate for the week: {pooled}%" if pooled is not None
               else "On-task rate: no interval data logged this week")
    out += ["", "| Day | Periods | On-task | Incidents |", "|---|---|---|---|"]
    for d in sorted(days):
        p = day_on_task(days[d])
        out.append(f"| {d.strftime('%a')} {d.isoformat()} | {len(days[d])} | "
                   f"{'-' if p is None else str(p) + '%'} | {sum(1 for r in days[d] if is_incident(r))} |")
    out.append("")

    incidents = [(d, r) for d in sorted(days) for r in sorted(days[d], key=period_sort_key) if is_incident(r)]
    out.append(f"Incidents: {len(incidents)}")
    for d, r in incidents:
        what = one_line(val(r, "behavior")) or "(no behavior recorded)"
        out.append(f"- {d.isoformat()} {val(r, 'period')}: {what}")
    out += ["", f"Daily detail: see the daily/ folder ({', '.join(d.isoformat() for d in sorted(days))})."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def process_student(student: str, paths: list[Path], data_dir: Path, state: dict, today: date) -> None:
    rows, dropped = read_student_rows(paths)
    note = f"{len(paths)} files merged, {dropped} duplicate rows dropped" if len(paths) > 1 else "1 file"
    days, bad_dates = group_rows(rows)
    print(f"  {student}: {sum(len(v) for v in days.values())} entries on {len(days)} day(s) ({note})")
    if bad_dates:
        shown = ", ".join(sorted(set(bad_dates))[:5])
        print(f"  WARNING: {len(bad_dates)} row(s) skipped, date not readable (e.g. {shown})")
    if not days:
        return

    st = state.setdefault(student, {})
    day_counts = st.setdefault("day_row_counts", {})
    week_counts = st.setdefault("week_row_counts", {})
    base = data_dir / "reports" / student
    (base / "daily").mkdir(parents=True, exist_ok=True)
    (base / "weekly").mkdir(parents=True, exist_ok=True)

    written_days = written_weeks = 0
    for d in sorted(days):
        path = base / "daily" / f"{d.isoformat()}.md"
        if path.exists() and day_counts.get(d.isoformat()) == len(days[d]):
            continue
        path.write_text(build_daily(student, d, days[d]), encoding="utf-8")
        day_counts[d.isoformat()] = len(days[d])
        written_days += 1

    weeks: dict[tuple[date, date], dict[date, list[dict]]] = defaultdict(dict)
    for d, rs in days.items():
        weeks[week_bounds(d)][d] = rs
    current_week = week_bounds(today)[0]
    for (start, end) in sorted(weeks):
        n = sum(len(v) for v in weeks[(start, end)].values())
        provisional = start == current_week
        path = base / "weekly" / f"{start.isoformat()}_to_{end.isoformat()}.md"
        if path.exists() and not provisional and week_counts.get(start.isoformat()) == n:
            continue
        path.write_text(build_weekly(student, start, end, weeks[(start, end)], provisional), encoding="utf-8")
        week_counts[start.isoformat()] = n
        written_weeks += 1

    print(f"    wrote {written_days} daily and {written_weeks} weekly report(s)")


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python report_generator.py <data_dir>")
        sys.exit(1)
    data_dir = Path(sys.argv[1]).resolve()
    if not data_dir.is_dir():
        print(f"Not a folder: {data_dir}")
        sys.exit(1)

    groups = find_student_files(data_dir)
    if not groups:
        print(f"No '<student>_behavior_log*.csv' files found in {data_dir}")
        return

    today = date.today()
    state = load_state(data_dir)
    print(f"Reading {data_dir}")
    for student, paths in sorted(groups.items()):
        process_student(student, paths, data_dir, state, today)
    save_state(data_dir, state)
    print(f"Reports in {data_dir / 'reports'}")


if __name__ == "__main__":
    main()
