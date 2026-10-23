# Behavior Log

Single-file HTML/CSS/JS tools for period-by-period classroom behavior observation. No build step, no dependencies, no server — open the file in a browser (or host it on GitHub Pages) and log.

Each entry captures attendance, on-task intervals, disruptive behavior detail, task completion, and incident/ABC notes for one class period, then exports to CSV. A second mode in the same file reads that CSV back in and generates a daily report plus a ready-to-paste email summary.

Two versions are included, built for different observation setups.

## `BehaviorLog_single.html`

For the original use case: one student, one observer, logged consistently over time.

- Student name is read from the URL path (e.g. hosting at `/students/Jordan/BehaviorLog.html` labels the page "Jordan" automatically) — useful for a one-folder-per-student GitHub Pages setup.
- Local tracker shows which periods have been logged today.
- Data and exported CSV are scoped to that one student by default.

## `BehaviorLog_multi.html`

Same form, with **Student** and **Observer** added as plain editable fields rather than inferred from the URL. This supports either of two situations without needing separate versions:

- **One observer, multiple students** — switch the Student field between periods; each student's data and tracker stay separate (keyed internally by student name).
- **One student, multiple observers** — switch the Observer field; all entries still roll up under the same student.

Also adds an **on-task interval grid**: set the class duration and it generates 5-minute interval checkboxes (✓ on-task / ✗ off-task / — N/A), matching the interval row on the paper observation sheet (`observation_sheet_v0_4`) used in the OSPI complaint exhibit.

The Report tab includes a student filter, and will warn (rather than silently merge) if a CSV contains more than one student for the same date, or if a period has entries from more than one observer.

## `BehaviorLog_paper.pdf`

A printable, free-form companion sheet for whoever doesn't want a tablet in hand — covering for someone unfamiliar with the digital form, a sub, or just a preference for paper in the moment. One sheet per period.

It keeps the same fields as `_multi.html` (Student, Observer, Date, Period, attendance, class duration). Opportunities sits on the On-task intervals line since they're the same count. The interval row is 11 plain blank boxes (enough for a 55-minute period; use a second sheet for anything longer) — no preprinted symbols, so mark them however's fastest in the moment (check, X, shading, slash). Rather than guess at a fixed list of behavior categories, there's an open ruled area for behavior notes (frequency, timing, antecedent/response — whatever's relevant that day) plus a separate Observations/context block.

Transcribing a paper sheet into `_multi.html` afterward is a straightforward 1:1 mapping — same fields, same symbols.

## How it works

- Entries go in through the form in **Log** mode. Each student gets one file per day, named `Name_behavior_log_YYYY-MM-DD.csv`.
  - In **Chrome or Edge** you pick that day's file once (a save dialog on the first log of the day) and every later log updates it. One file per day, no clutter.
  - In other browsers each log downloads a complete copy of the day so far (the browser numbers repeats `(1)`, `(2)`...; the newest has everything).
- **Finish day: save final copy** (button under the form), pressed after the last period or at early dismissal, saves one complete `Name_behavior_log_YYYY-MM-DD_final.csv` for the date and lists the periods in it. Keep that file; the other copies for that date can be deleted.
- The browser also keeps a running copy of every day it has logged, as a safety net. Clearing site data for the page erases it, so keep the files.
- Switch to **Report** mode, load a saved CSV (or drag-and-drop it), pick a date, and it builds a per-period summary plus a plain-text email body you can copy and send.
- No data leaves the browser — there's no backend. CSVs are the only persistence layer, so back them up like any other file you care about.

See [`CHEATSHEET.md`](./CHEATSHEET.md) for the daily routine and what to do when something looks off.

## Reports over many days

[`reporting/report_generator.py`](./reporting/report_generator.py) (Python standard library only) reads every CSV for a student, however they are named or numbered, merges them, and writes a **daily report** per day and a **weekly summary** per week. It can be run whenever, however rarely: missed days and weeks are filled in. Design notes and an IT-approval pitch are in [`reporting/SPEC.md`](./reporting/SPEC.md); `reporting/sample_data/` is a synthetic, deliberately messy set to try it on:

```
python reporting/report_generator.py reporting/sample_data
```

## Hosting

Both files are static and self-contained. They work:
- Opened directly from disk
- Hosted on GitHub Pages (single file or one-folder-per-student, depending on version)
- Dropped into any static file host

No npm install, no build, no server-side code.
