# Behavior Log Reporting Suite — Design Spec

**Audience:** an in-house developer implementing this, and the IT reviewer deciding whether to allow it to run.
**Status:** pseudocode + working reference implementation (`report_generator.py`), tested on synthetic sample data. Not yet field-tested on real student data.

---

## 0. Before you build this in Google Forms instead

If you're reading this because you're about to start logging behavior data and you're tempted to just
spin up a Google Form — read this first. It's the mistake this whole toolchain exists to undo.

A Form feels like the fast option: no IT approval needed, everyone already has a Google account, done
in ten minutes. The mess shows up later, and it compounds:

- **Every time you need a new field, you either edit the live form or start a new one.** Editing a live
  form after responses exist doesn't rewrite old rows — reordering or retyping a question can silently
  shift which column your old answers land in when you export. Starting a new form instead means you
  now have two (then three) response spreadsheets with slightly different columns, and merging them
  later is its own project.
- **A year of data ends up spread across several exports that don't line up.** What should have been
  one clean CSV becomes a stitching exercise — matching columns by name, resolving rows where a field
  existed in form 2 but not form 1, figuring out which version was authoritative for a given week.
- **The response spreadsheet lives in whoever's Drive created the form**, syncing through whatever
  Excel/OneDrive/Drive combination the school uses — which is its own separate failure mode (files that
  work for weeks and then break on a random reboot, conflicted copies, macros that stop being trusted).
- **None of this shows up as a problem on day one.** It shows up months in, when you actually need the
  whole year's data to mean something at once — for a meeting, a report, or a complaint — and discover
  the record isn't as complete or as consistent as the day-to-day logging felt like it was.

The tools in this repo exist specifically because a year of exactly that (several sequential Forms
instruments, merged after the fact with pandas) is what came before them. A fixed-schema CSV file per
student per day, saved straight from the browser with no cloud step in between, is deliberately boring
by comparison — nothing to reboot, nothing to sync, no second form to reconcile with the first. If you
take one thing from this document before touching Forms: **decide your fields once, before you start
logging, because changing them later is where the real cost hides.**

---

## 1. The ask, in one paragraph (for IT)

This is a single Python file (`report_generator.py`), standard library only — no `pip install`, no
third-party packages, no network calls of any kind. It reads CSV files from one folder on local disk
and writes plain-text/Markdown report files into a `reports/` subfolder. The only thing it writes outside
that subfolder is one small, visible JSON file (`report_state.json`) that remembers how many entries
stood behind each report it has written, so re-running it is safe and idempotent. It does not touch the
registry, does not install anything, does not require admin rights, and can be reviewed end-to-end in a
text editor in under 15 minutes. It's the kind of script you'd approve to run under a standard user
account with no elevation.

If double-clicking a `.py` file is itself blocked by policy, the fallback is: IT runs it once as a
scheduled task pointed at the folder, or the teacher runs it via a desktop shortcut that just calls
`python report_generator.py`. Either way there's nothing to install beyond whatever Python the district
already has (3.8+). The logging pages themselves (`BehaviorLog_*.html`) need no Python at all; they run
in the browser, so the script can live on a different machine from the one used in the classroom.

---

## 2. Problem statement

A teacher/observer logs behavior data period-by-period into CSV files (see `BehaviorLog_multi.html` /
`BehaviorLog_single.html`). Nobody wants to open a CSV and eyeball it. Somebody — not necessarily the
person who logged the data — needs to periodically get a plain-English "here's what happened" report,
without:

- Needing to remember to run anything on a schedule
- Getting duplicate or missing days or weeks if they forget for a while
- Installing software or touching settings
- Having to tidy up the CSV files first

**Two outputs:** one report per **day** (period by period, with incident detail), and one **weekly
summary** built from the same rows.

**Core requirement: gap tolerance.** If the tool isn't run for three weeks, running it once produces
every missed daily report and all three weekly summaries, not a single mashed-together summary and not
just the most recent week.

**Core requirement: messy-input tolerance.** The files that arrive are not tidy: a day may exist as
several partial copies, a final copy, and browser-numbered repeats; someone may combine files by hand in
Excel. The generator must give the same answer regardless.

---

## 3. Non-goals (explicitly out of scope, keep the IT ask small)

- No email sending (report files are written to disk; a human attaches/sends them)
- No database — CSVs on disk are the only source of truth
- No GUI — command line only, invoked by double-click, shortcut, or scheduled task
- No cloud sync, no telemetry, no update-checking
- No editing of the source CSVs — strictly read-only on input data

---

## 4. Data model (input)

### 4.1 Files

The logging page writes one CSV per student per day. All of the following belong to student `Jordan`
and are read together:

| file name | what it is |
|---|---|
| `Jordan_behavior_log_2026-10-22.csv` | that day's periods, rewritten after every log (Chrome/Edge) |
| `Jordan_behavior_log_2026-10-22 (1).csv`, `(2)`… | repeats from browsers that can only download; each holds the whole day so far |
| `Jordan_behavior_log_2026-10-22_final.csv` | the end-of-day copy saved by the "Finish day" button |
| `Jordan_behavior_log.csv` | older versions of the tool wrote one cumulative file per student |

The generator does **not** need to know which file is newest or final. Every file for a student is read,
and a row is identified by its `submitted_at` timestamp (the logger stamps every entry), so a row that
appears in five files counts once. Cleaning up (keeping the `_final` file per date) is for the humans'
benefit and is optional for the reports.

### 4.2 Columns

Relevant columns (subset — the generator ignores columns it doesn't need):

| column | meaning |
|---|---|
| `date` | observation date, `YYYY-MM-DD` (Excel's `M/D/YYYY` re-save format is also accepted) |
| `student` | student name |
| `observer` | who logged the entry |
| `period` | class period label |
| `attendance` | Present / Late / Skipped / Absent/sick |
| `arrival_time` | when attendance is Late |
| `intervals` | on-task intervals, space separated: `✓ ✓ ✗ — ✓` (✓ on-task, ✗ off-task, — N/A, blank unmarked) |
| `class_duration` | minutes |
| `phone`, `phone_log`, `sounds`, `sound_*`, `comments*`, `tasks`, `arguing`, `task_narrative`, `observations` | secondary fields shown in the daily report when filled |
| `incident_occurred` | `Yes` when an incident was logged |
| `regulation`, `elopement_time`, `incident_time`, `antecedent`, `behavior`, `consequence` | incident detail, present only if `incident_occurred == Yes` |
| `submitted_at` | ISO timestamp the entry was saved; the row's identity |

Read by column *name* (`csv.DictReader`), never by position, so new columns appearing over time don't
break the parser.

### 4.3 Things that go wrong, and what the generator does

| situation | behavior |
|---|---|
| same entry in several files | counted once (`submitted_at`) |
| a header line pasted into the middle of a hand-combined file | ignored |
| dates rewritten by Excel (`10/21/2026`) | understood, normalised to ISO |
| a date that can't be read at all | row skipped **and reported** in a `WARNING:` line; never silently dropped |
| file saved by Excel with a byte-order mark or CRLF line endings | read normally |

---

## 5. State tracking

One state file per data folder: `report_state.json` (deliberately visible, not a dotfile: it's the thing
you delete to force a rebuild).

```json
{
  "Jordan": {
    "day_row_counts":  { "2026-10-21": 1, "2026-10-22": 3 },
    "week_row_counts": { "2026-10-12": 4, "2026-10-19": 4 }
  }
}
```

- A week is Monday–Sunday.
- The state records, per day and per week, **how many entries were behind the report last written**.
- A day or week is rewritten when its report file is missing or its current entry count differs from the
  recorded count. The week containing "today" is always rewritten and marked *provisional*.
- Deleting `report_state.json` (and optionally `reports/`) is always safe: everything is rebuilt from the
  CSVs. The state is an optimisation and a change-detector, never the source of truth.

An earlier version of this design recorded a "last finalized week" and never revisited older weeks. That
silently froze a week's report whenever rows for it arrived late (a forgotten period, files combined
after the fact). Counting entries instead fixes that class of problem.

---

## 6. Algorithm (pseudocode)

```
INPUT:  data_dir
OUTPUT: data_dir/reports/<student>/daily/<YYYY-MM-DD>.md
        data_dir/reports/<student>/weekly/<week_start>_to_<week_end>.md

state = load data_dir/report_state.json          (empty if missing or unreadable)
today = current_date()

group every "<student>_behavior_log*.csv" in data_dir by student
    (name pattern: <student>_behavior_log [_YYYY-MM-DD] [_final] [ (n) | - Copy ] .csv)

for each student:
    rows = []
    for each file of the student:
        for each row in read_csv(file):            # utf-8-sig, DictReader
            skip if date is blank or the literal header text "date"
            skip if row.submitted_at already seen   # duplicate across files
            rows.append(row)

    days = group rows by parse_date(row.date)       # unreadable dates -> warning, row skipped
    if days is empty: continue

    for day in days (chronological):
        path = reports/student/daily/day.md
        if file exists and state.day_row_counts[day] == len(days[day]): continue
        write build_daily(day, rows of the day)
        state.day_row_counts[day] = len(days[day])

    for week in group days by monday(day):
        n = total rows in week
        provisional = (week contains today)
        path = reports/student/weekly/week.md
        if file exists and not provisional and state.week_row_counts[week] == n: continue
        write build_weekly(week, days in the week, provisional)
        state.week_row_counts[week] = n

save state
```

Key property: **what gets written is derived from the data, not from "when did I last run."** That's what
makes it gap-safe and merge-safe — there's no separate "how many runs did I miss" bookkeeping to get
wrong, and running it twice in a row writes nothing new except the provisional week.

---

## 7. Report content

Plain Markdown, human-readable without any tooling.

### 7.1 Daily (`daily/2026-10-14.md`)

```
# Jordan -- Wednesday 2026-10-14

2 period(s) logged | on-task 100% | 1 incident(s)

## P1 -- Ms. Reyes

- Attendance: Present
- On-task intervals, 50 min: ✓ ✓ ✓ ✓ ✓  (100%)

## P2 -- Ms. Reyes

- Attendance: Present
- On-task intervals, 50 min: ✓ ✓ ✓ ✓ ✓  (100%)

**Incident**

- Antecedent: Peer commented on his work
- Behavior: Loud verbal outburst
- Consequence: Removed to hallway 5 min, calm on return
```

Fields appear only when filled: arrival time, phone use and interaction, disruptive sounds (with counts),
disruptive comments, tasks completed, arguing, task notes, observations, and the incident block
(regulation, elopement time, incident time, antecedent/behavior/consequence). Periods are ordered by
period number.

### 7.2 Weekly (`weekly/2026-10-12_to_2026-10-18.md`)

```
# Jordan -- Weekly summary, 2026-10-12 to 2026-10-18

Days with entries: 3 | Periods logged: 4
Attendance: 1 Late, 3 Present

On-task rate for the week: 95%

| Day | Periods | On-task | Incidents |
|---|---|---|---|
| Mon 2026-10-12 | 1 | 100% | 0 |
| Tue 2026-10-13 | 1 | 80% | 0 |
| Wed 2026-10-14 | 2 | 100% | 1 |

Incidents: 1
- 2026-10-14 P2: Loud verbal outburst

Daily detail: see the daily/ folder (2026-10-12, 2026-10-13, 2026-10-14).
```

The week containing "today" carries `_(provisional -- week in progress)_` in its title.

### 7.3 Choices made that a reader may want changed

- **On-task percentage** is pooled: every scored (✓/✗) interval in the period, day or week counts equally;
  N/A and unmarked intervals are excluded. (Averaging per-period percentages instead would weight a
  short period the same as a long one.)
- **No "expected periods" line.** The generator reports what was logged, not what should have been; it
  has no schedule to compare against.

These are analysis decisions, not engineering ones. **Don't guess at behavior-analysis conventions; ask
the person who'll read the reports what they actually want summarized.**

---

## 8. Sample data & how to test it

`sample_data/` is a deliberately messy synthetic set for student "Jordan": 13 files covering 8 days over
3 calendar weeks, with a missed week in between. It includes a day with a partial copy, a numbered repeat
and a `_final` copy; a day with a plain copy next to its `_final`; and a current day with no `_final` yet.

```
python report_generator.py sample_data
```

should report `10 entries on 8 day(s) (13 files merged, 7 duplicate rows dropped)` and write 8 daily
and 3 weekly reports. Correctness checks worth keeping in any reimplementation:

1. **Idempotency:** running again immediately changes no daily report and no finished weekly report
   (only the provisional week is rewritten).
2. **Late data:** append a row dated inside an old week to any file and re-run. That day and that week are
   rewritten.
3. **Old or missing state:** delete `report_state.json`, or drop in the hidden `.report_state.json` an
   earlier version of the tool wrote. The old file is ignored and everything is rebuilt from the CSVs.
4. **Hand-combined input:** save a combined file through Excel (dates become `M/D/YYYY`, a header line
   lands mid-file). Entries are still found; any unreadable date produces a warning.

---

## 9. Suggested pitch to IT (email template)

> Subject: Requesting approval to run a local Python script (no installs, no network)
>
> This is a single-file Python script that reads CSV files from a folder on [teacher]'s machine and
> writes summary text files back into the same folder. It uses only Python's built-in standard library
> — nothing is downloaded or installed, it makes no network connections, and it doesn't modify anything
> outside that one folder except a small status file (`report_state.json`) it writes next to the CSVs.
> Happy to walk through the code line by line, or have it reviewed by IT before it's placed on any
> machine. Attached: the script and a short spec describing exactly what it does.
>
> (The classroom logging page is a separate static HTML file that runs entirely in the browser; it does
> not use Python and does not need the script to be installed on the classroom machine.)

---

## 10. Open questions for the implementer

1. Does the reader want an "expected periods" comparison (needs a bell schedule as input), or is "what
   was logged" enough?
2. On-task rate: pooled intervals (current) or average of per-period percentages?
3. Where do finished reports go from here — printed, emailed manually, dropped in a shared drive? That
   determines whether output should be Markdown, plain text, or PDF.
4. Several students in one folder works today (one report tree per student); is a cross-student summary
   ever wanted? It would need a decision about privacy before it is built.
