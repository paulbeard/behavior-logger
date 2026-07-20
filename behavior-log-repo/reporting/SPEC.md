# Behavior Log Reporting Suite — Design Spec

**Audience:** an in-house developer implementing this, and the IT reviewer deciding whether to allow it to run.
**Status:** pseudocode + working reference implementation on sample data. Not yet field-tested on real student data.

---

## 1. The ask, in one paragraph (for IT)

This is a single Python file (`report_generator.py`), standard library only — no `pip install`, no
third-party packages, no network calls of any kind. It reads CSV files from one folder on local disk
and writes plain-text/Markdown report files into a subfolder. The only thing it writes outside that
output subfolder is one small JSON file (`.report_state.json`) that remembers which weeks it has
already reported on, so re-running it is safe and idempotent. It does not touch the registry, does not
install anything, does not require admin rights, and can be reviewed end-to-end in a text editor in
under 15 minutes. It's the kind of script you'd approve to run under a standard user account with no
elevation.

If double-clicking a `.py` file is itself blocked by policy, the fallback is: IT runs it once as a
scheduled task pointed at the folder, or the teacher runs it via a desktop shortcut that just calls
`python report_generator.py`. Either way there's nothing to install beyond whatever Python the district
already has (3.9+).

---

## 2. Problem statement

A teacher/observer logs behavior data period-by-period into per-student CSVs (see `BehaviorLog_multi.html`
/ `BehaviorLog_single.html`). Nobody wants to open a CSV and eyeball it. Somebody — not necessarily the
person who logged the data — needs to periodically get a plain-English "here's what happened this week"
report, without:

- Needing to remember to run anything on a schedule
- Getting duplicate or missing weeks if they forget for a while
- Installing software or touching settings

**Core requirement: gap tolerance.** If the tool isn't run for three weeks, running it once produces
all three missed weekly reports, not a single mashed-together summary and not just the most recent week.

---

## 3. Non-goals (explicitly out of scope, keep the IT ask small)

- No email sending (report files are written to disk; a human attaches/sends them)
- No database — CSVs on disk are the only source of truth
- No GUI — command line only, invoked by double-click, shortcut, or scheduled task
- No cloud sync, no telemetry, no update-checking
- No editing of the source CSVs — strictly read-only on input data

---

## 4. Data model (input)

One CSV per student: `<student>_behavior_log.csv`, matching the download filename produced by the
logging tool. Relevant columns (subset — the report generator ignores columns it doesn't need):

| column | meaning |
|---|---|
| `date` | ISO date (YYYY-MM-DD) of the observation |
| `student` | student name |
| `observer` | who logged the entry |
| `period` | class period label |
| `attendance` | On time / Tardy / Absent |
| `intervals` | on-task interval string, e.g. `✓✓✗—✓` |
| `class_duration` | minutes |
| `incident_occurred` | Yes/No |
| `antecedent`, `behavior`, `consequence` | free-text incident fields, present only if `incident_occurred == Yes` |
| `comments_count`, `tasks`, `arguing` | secondary tallies |

New columns appearing over time should not break the parser — read by column *name* (`csv.DictReader`),
never by position.

---

## 5. State tracking

One state file per data folder: `.report_state.json`

```json
{
  "Jordan": { "last_finalized_week_end": "2026-07-12" },
  "Alex":   { "last_finalized_week_end": "2026-07-05" }
}
```

- A week is Monday–Sunday.
- `last_finalized_week_end` is the Sunday date of the most recent week that has already been written
  and will never be rewritten.
- If a student has no entry in the state file, treat `last_finalized_week_end` as "before any data
  exists" — i.e. report from the very first row.

---

## 6. Algorithm (pseudocode)

```
INPUT: data_dir (folder containing <student>_behavior_log.csv files)
OUTPUT: data_dir/reports/<student>/<week_start>_to_<week_end>.md

load state from data_dir/.report_state.json  (empty dict if missing)
today = current_date()

for each file matching "*_behavior_log.csv" in data_dir:
    student = filename without "_behavior_log.csv"
    rows = read_csv(file)                      # list of dicts, keyed by column name
    if rows is empty: continue

    group rows by iso_week(row.date)            # {(year, week_num): [rows]}
    sort weeks chronologically

    last_finalized = state.get(student).last_finalized_week_end   # date or None

    for each week in weeks, chronological order:
        week_start, week_end = monday(week), sunday(week)

        if last_finalized is not None and week_end <= last_finalized:
            continue        # already finalized, never touch again

        report = build_report(student, week_start, week_end, rows_in(week))
        write_file(reports/student/f"{week_start}_to_{week_end}.md", report)

        is_current_week = (week_end >= today - 6 days)   # week containing "today", roughly
        if not is_current_week:
            state[student].last_finalized_week_end = week_end
            # else: leave state alone — this week stays provisional,
            # gets overwritten again next run if new rows land in it

save state to data_dir/.report_state.json
```

Key property: **finalization is derived from the calendar, not from "when did I last run."** That's
what makes it gap-safe — there's no separate "how many runs did I miss" bookkeeping to get wrong.

---

## 7. Report content (per student, per week)

Plain Markdown, human-readable without any tooling:

```
# Jordan — Week of 2026-07-06 to 2026-07-12

Periods logged: 18 / 20 expected (2 missing: Wed P3, Fri P5)
Attendance: 17 on-time, 1 tardy, 0 absent

On-task rate: 78% average across logged intervals
  Mon 82%  Tue 75%  Wed 80%  Thu 71%  Fri 82%

Incidents: 2
  - Tue P4: [antecedent/behavior/consequence, verbatim from CSV]
  - Thu P2: [...]

Notes carried from observer comments:
  - [any free-text comments/observations fields, concatenated by day]
```

The exact shape (what counts as "expected periods," how on-task % is computed from the interval
string) is a decision for whoever implements this against real data — the pseudocode above is
schema-driven, not opinionated about the analysis. Flag this to the implementer explicitly: **don't
guess at behavior-analysis conventions; ask the person who'll read the reports what they actually want
summarized.**

---

## 8. Sample data & how to test it

`sample_data/` contains a small synthetic CSV (`Jordan_behavior_log.csv`) spanning parts of three
different calendar weeks, including one week with no entries at all (simulating a missed week) and one
partial "current" week. Running the script against it should produce:

- Two finalized weekly reports (the older two)
- One provisional report for the most recent week
- A `.report_state.json` with `last_finalized_week_end` set to the Sunday of the second week only

Re-running immediately with no new data should produce byte-identical finalized reports and only
regenerate the provisional one — that idempotency check is the core correctness test.

---

## 9. Suggested pitch to IT (email template)

> Subject: Requesting approval to run a local Python script (no installs, no network)
>
> This is a single-file Python script that reads CSV files from a folder on [teacher]'s machine and
> writes summary text files back into the same folder. It uses only Python's built-in standard library
> — nothing is downloaded or installed, it makes no network connections, and it doesn't modify anything
> outside that one folder except a small status file it writes next to the CSVs. Happy to walk through
> the code line by line, or have it reviewed by IT before it's placed on any machine. Attached: the
> script and a short spec describing exactly what it does.

---

## 10. Open questions for the implementer

1. What counts as "expected periods per day" for the attendance-rate line — fixed schedule, or inferred
   from historical data?
2. Should provisional (current-week) reports be visually marked as "in progress" in the filename or
   header, so nobody mistakes them for final?
3. Where do finished reports go from here — printed, emailed manually, dropped in a shared drive? That
   determines whether output should be Markdown, plain text, or PDF.
