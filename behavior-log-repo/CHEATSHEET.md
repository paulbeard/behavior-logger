# Behavior Log: cheat sheet (no Claude needed)

## Every day

1. Open the page in **Chrome or Edge**. Log the first period.
2. A file dialog appears with a dated name, like `Jordan_behavior_log_2026-10-22.csv`. Save it. (New day, new file, one dialog per day.)
   - "Replace existing file?" → **Replace**. Anything already in it is read first and kept.
   - "Allow this site to edit the file?" → **Edit file**.
3. Under the form you should see **2026-10-22: saving to Jordan_behavior_log_2026-10-22.csv**. Every later period updates that same file.
4. **After the last period (or at early dismissal), press "Finish day: save final copy."** It saves one complete file for that date:
   `Jordan_behavior_log_2026-10-22_final.csv`, and tells you which periods are in it.
5. **Cleanup:** for each date, keep the `_final` file. Everything else with that date can be deleted without looking.

Early dismissal, then a late period gets logged? Log it, press Finish day again. If the browser names the new one `_final (1)`, keep the newest.

## If you forgot "Finish day"

For that date, keep the **newest** file (the highest `(n)`, or the plain dated one in Chrome/Edge). It has the whole day.

## If something looks off

| You see | What it means | Do this |
|---|---|---|
| Red note: "A copy was downloaded instead" | File was open in Excel, or the dialog was cancelled | Close Excel. Click **Change file**, pick the day's CSV again, log the next period. If asked "add rows from this browser?", click **OK**. Don't re-enter the missed period; it's saved in the downloaded copy and the browser's copy. |
| Files named `..._2026-10-22 (1).csv`, `(2)`... | Browser can't save to one file (Firefox/Safari), or the dialog was cancelled | Nothing is lost. The newest copy of the date has the whole day. Use Chrome/Edge to stop it. |
| "This browser has N rows not in the file. Add them?" | You picked an older copy of the day, or the browser has rows the file lacks | **OK** to add them. **Cancel** only if you deliberately deleted those rows from the file. |
| "No periods logged for [date] yet" | Finish day pressed before anything was logged for the date shown in the Date box | Check the Date box, or log a period first. |
| Logged on two computers/browsers | Each browser keeps its own copy | Point both at the same day's file, or collect the files into one folder. The report script merges by timestamp. |

## Reports (at home, where Python runs)

1. Put all `Name_behavior_log*.csv` files in one folder. Dated, `_final`, numbered and older undated files are all fine; combined by hand is fine too.
2. Run: `python report_generator.py <that folder>` (Python 3.8+, nothing to install).
3. Reports appear under `<folder>/reports/<Name>/`:
   - `daily/2026-10-22.md`: one per day, period by period (attendance, on-task intervals, notes, incident detail)
   - `weekly/2026-10-19_to_2026-10-25.md`: weekly summary (on-task by day, incidents). This week's is marked *provisional*.
4. Run it whenever you like, however often. Missed days and weeks are filled in automatically.
   A day or week is rewritten whenever new rows for it appear. Copies of the same day are merged, so you can leave the old ones in.
5. If it prints a **WARNING: ... row(s) skipped**, those rows had a date it couldn't read. Fix the date in the CSV and run again.
6. Reports look out of date? Delete `report_state.json` (a visible file in the data folder) and the `reports` folder,
   then run again. Nothing is lost; everything is rebuilt from the CSVs. (An older hidden `.report_state.json`
   from a previous version is ignored and can be deleted.)
7. For a quick single-day summary, use the **Report** tab in the page and load that day's CSV.

## Basics

- No data leaves the browser. The CSVs are the only record, so **back them up** (copy the `_final` files somewhere weekly).
- Dates are `YYYY-MM-DD`. Each row has a `submitted_at` timestamp; that's how duplicates are detected.
- File names must keep the `Name_behavior_log` part; the date and `_final` after it are what the page adds, and the report script expects them.
- The browser also keeps a running copy of every day it has logged for a student. Clearing site data for the page erases it, so keep the files.
