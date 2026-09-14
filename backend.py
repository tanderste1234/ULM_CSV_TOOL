#©Thomas Edmund Anderson 2026
import os
import sys
import calendar
import threading
import shutil
import gc
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import csv

# ---------------------------------------------------------------------------
# CORE HELPER FUNCTIONS
# ---------------------------------------------------------------------------


def sanitize_text(val):
    """Sanitize string values by stripping whitespace and extra quotes."""
    if pd.isna(val) or val is None:
        return ""
    s = str(val).strip()
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    return s


def get_headers_from_template(template_path="templateFile.csv"):
    """Reads column header names directly from templateFile.csv."""
    if not os.path.exists(template_path):
        return None

    try:
        with open(template_path, mode='r', newline='') as f:
            reader = csv.reader(f)
            template_headers = next(reader)
            return template_headers
    except Exception:
        return None


def parse_date_range(start_str, end_str, date_mode, debug_func=None):
    raw_starts = []
    if start_str:
        for s in start_str.split(","):
            if s.strip():
                raw_starts.append(s.strip())

    raw_ends = []
    if end_str:
        for e in end_str.split(","):
            if e.strip():
                raw_ends.append(e.strip())

    max_len = max(len(raw_starts), len(raw_ends))
    if max_len == 0:
        return []

    # Pad shorter list with empty strings to preserve 1-to-1 pairing
    while len(raw_starts) < max_len:
        raw_starts.append("")
    while len(raw_ends) < max_len:
        raw_ends.append("")

    parsed_ranges = []

    for idx, (c_start, c_end) in enumerate(zip(raw_starts, raw_ends), start=1):
        s_dt = None
        e_dt = None

        if date_mode == "YYYY-MM":
            if c_start:
                # Handle YYYY-MM or YYYY/MM
                clean_s = c_start.replace("/", "-")
                s_dt = pd.to_datetime(
                    clean_s + "-01", format="%Y-%m-%d", errors="coerce")
                if pd.notna(s_dt):
                    s_dt = s_dt.floor("D")
                    if not c_end:
                        e_dt = s_dt + pd.offsets.MonthEnd(1)
                elif debug_func:
                    debug_func(f"WARN: Failed to parse Start Date #{
                               idx} ('{c_start}') in YYYY-MM mode.")

            if c_end:
                clean_e = c_end.replace("/", "-")
                parsed_e = pd.to_datetime(
                    clean_e + "-01", format="%Y-%m-%d", errors="coerce")
                if pd.notna(parsed_e):
                    e_dt = (parsed_e + pd.offsets.MonthEnd(1)).floor("D")
                elif debug_func:
                    debug_func(f"WARN: Failed to parse End Date #{
                               idx} ('{c_end}') in YYYY-MM mode.")

        else:  # DD-MM-YYYY mode
            if c_start:
                # Standardize slashes to dashes
                clean_s = c_start.replace("/", "-")
                s_dt = pd.to_datetime(
                    clean_s, format="%d-%m-%Y", errors="coerce")
                if pd.notna(s_dt):
                    s_dt = s_dt.floor("D")
                elif debug_func:
                    debug_func(f"WARN: Failed to parse Start Date #{
                               idx} ('{c_start}'). Expecting DD-MM-YYYY.")

            if c_end:
                clean_e = c_end.replace("/", "-")
                e_dt = pd.to_datetime(
                    clean_e, format="%d-%m-%Y", errors="coerce")
                if pd.notna(e_dt):
                    e_dt = e_dt.floor("D")
                elif debug_func:
                    debug_func(f"WARN: Failed to parse End Date #{
                               idx} ('{c_end}'). Expecting DD-MM-YYYY.")

        if s_dt is not None or e_dt is not None:
            parsed_ranges.append((s_dt, e_dt))

    if debug_func and parsed_ranges:
        debug_func(
            f"SUCCESS: Active Date Filter Ranges Parsed ({len(parsed_ranges)}):")
        for i, (st, en) in enumerate(parsed_ranges, start=1):
            st_str = st.strftime("%Y-%m-%d") if st is not None else "UNBOUNDED"
            en_str = en.strftime("%Y-%m-%d") if en is not None else "UNBOUNDED"
            debug_func(f"  Range {i}: {st_str}  -->  {en_str}")

    return parsed_ranges

# ---------------------------------------------------------------------------
# MAIN STREAMING ENGINE
# ---------------------------------------------------------------------------


def execute_huge_file_processing(
    file_path,
    output_path,
    target_columns,
    year_field_name,
    day_field_name,
    start_date_str,
    end_date_str,
    date_mode,
    chunksize,
    template_path="templateFile.csv",
    debug_func=print,
    progress_func=lambda p, w: None
):
    if not os.path.exists(file_path):
        debug_func(f"ERROR: Input file does not exist: {file_path}")
        return False

    template_headers = get_headers_from_template(template_path)
    if not template_headers:
        debug_func(f"ERROR: Could not read headers from template file: {
                   template_path}")
        return False

    date_ranges = parse_date_range(
        start_date_str, end_date_str, date_mode, debug_func)
    has_date_filter = len(date_ranges) > 0

    columns_to_keep = []
    if target_columns and target_columns.strip():
        for c in target_columns.split(","):
            clean_col = c.strip()
            if clean_col:
                columns_to_keep.append(clean_col)

    year_col = year_field_name.strip() if year_field_name else None
    day_col = day_field_name.strip() if day_field_name else None

    if not year_col or not day_col:
        debug_func(
            "ERROR: Both Year field name and Day-of-Year field name must be specified.")
        return False

    total_rows_processed = 0
    total_rows_written = 0

    try:
        debug_func("Starting CSV processing stream...")

        read_kwargs = {
            "chunksize": chunksize,
            "dtype": str,
            "low_memory": False,
            "on_bad_lines": "skip",
            "header": None,
            "names": template_headers
        }

        with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as in_file:
            with open(output_path, "w", newline="", encoding="utf-8") as out_file:

                reader = pd.read_csv(in_file, **read_kwargs)
                write_header = True

                for chunk_idx, chunk in enumerate(reader):
                    total_rows_processed += len(chunk)

                    # Explicit loop for stripping whitespace from column names
                    cleaned_columns = []
                    for col in chunk.columns:
                        cleaned_columns.append(str(col).strip())
                    chunk.columns = cleaned_columns

                    parsed_dates = pd.Series(
                        index=chunk.index, dtype="datetime64[ns]")

                    col_missing = False
                    if year_col not in chunk.columns or day_col not in chunk.columns:
                        col_missing = True

                    if not col_missing:
                        yr_num = pd.to_numeric(chunk[year_col].astype(
                            str).str.strip(), errors="coerce")
                        day_num = pd.to_numeric(chunk[day_col].astype(
                            str).str.strip(), errors="coerce")

                        valid_mask = yr_num.notna() & day_num.notna() & (day_num >= 1) & (day_num <= 366)

                        if valid_mask.any():
                            clean_years = yr_num[valid_mask].astype(
                                int).astype(str)
                            clean_days = day_num[valid_mask].astype(int)

                            base_dates = pd.to_datetime(
                                clean_years + "-01-01", format="%Y-%m-%d", errors="coerce")
                            day_offsets = pd.to_timedelta(
                                clean_days - 1, unit="D")

                            parsed_dates.loc[valid_mask] = (
                                base_dates + day_offsets).dt.floor("D")

                    # Insert date column at position 0
                    chunk.insert(
                        0, "date", parsed_dates.dt.strftime("%d-%m-%Y"))

                    # Multi-range vectorized logic (OR masking)
                    if has_date_filter:
                        valid_dates = parsed_dates.notna()
                        combined_match_mask = pd.Series(
                            False, index=chunk.index)

                        for r_start, r_end in date_ranges:
                            range_mask = valid_dates & (
                                parsed_dates >= r_start) & (parsed_dates <= r_end)
                            combined_match_mask = combined_match_mask | range_mask

                        filtered_chunk = chunk[combined_match_mask].copy()
                    else:
                        filtered_chunk = chunk.copy()

                    # Explicit column selection and position-0 date preservation
                    if columns_to_keep:
                        existing_cols = []
                        if "date" in filtered_chunk.columns:
                            existing_cols.append("date")

                        for target in columns_to_keep:
                            target_clean = target.strip()
                            if target_clean in filtered_chunk.columns and target_clean not in existing_cols:
                                existing_cols.append(target_clean)

                        filtered_chunk = filtered_chunk[existing_cols]

                    if not filtered_chunk.empty:
                        filtered_chunk.to_csv(
                            out_file,
                            mode="a",
                            header=write_header,
                            index=False
                        )
                        write_header = False
                        total_rows_written += len(filtered_chunk)

                    progress_func(total_rows_processed, total_rows_written)

                out_file.flush()

        if total_rows_written == 0:
            debug_func(
                "WARN: Processing finished, but 0 rows matched your criteria.")
        else:
            debug_func(f"SUCCESS: Written {
                       total_rows_written:,} / {total_rows_processed:,} rows to target.")

        return True

    except Exception as e:
        debug_func(f"EXCEPTION: {str(e)}")
        return False
    finally:
        gc.collect()

# ---------------------------------------------------------------------------
# PROCEDURAL UI EVENT HANDLERS & HELPERS
# ---------------------------------------------------------------------------


def debug_log(message):
    debug_text.insert(tk.END, message + "\n")
    debug_text.see(tk.END)


def update_progress(processed, written):
    status_label.config(text=f"Processed: {
                        processed:,} rows | Written: {written:,} rows")


def update_date_labels():
    mode = date_mode_var.get()
    start_label.config(text=f"Start Date ({mode}):")
    end_label.config(text=f"End Date ({mode}):")


def browse_input():
    path = filedialog.askopenfilename(
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
    if path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, path)

        if not output_entry.get().strip():
            base, ext = os.path.splitext(path)
            suggested_output = f"{base}_processed{ext}"
            output_entry.delete(0, tk.END)
            output_entry.insert(0, suggested_output)


def browse_output():
    path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[
                                        ("CSV Files", "*.csv"), ("All Files", "*.*")])
    if path:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, path)


def toggle_debug_window():
    global debug_visible
    if not debug_visible:
        root.geometry("750x640")
        debug_frame.pack(fill=tk.BOTH, expand=True, pady=4)
        debug_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        debug_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        debug_toggle_btn.config(text="Hide Debug Window")
        debug_visible = True
    else:
        debug_frame.pack_forget()
        root.geometry("750x420")
        debug_toggle_btn.config(text="Show Debug Window")
        debug_visible = False


def start_processing():
    input_file = input_entry.get().strip()
    output_file = output_entry.get().strip()

    if not input_file or not output_file:
        messagebox.showerror(
            "Error", "Please specify both Input and Output CSV paths.")
        return

    abs_input = os.path.realpath(os.path.abspath(input_file))
    abs_output = os.path.realpath(os.path.abspath(output_file))

    if os.path.isdir(abs_output):
        messagebox.showerror(
            "Error", "Output path is a directory, not a file.")
        return

    if abs_input == abs_output:
        messagebox.showerror(
            "Path Error",
            "Output file path cannot be identical to the Input file path!\n\n"
            "Please select a different file name or destination for the Output CSV."
        )
        return

    run_button.config(state=tk.DISABLED)
    debug_text.delete(1.0, tk.END)
    debug_log("Starting job execution...")

    threading.Thread(
        target=run_job_thread,
        args=(abs_input, abs_output),
        daemon=True
    ).start()


def run_job_thread(input_file, output_file):
    temp_path = output_file + ".tmp"

    if os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass

    debug_log(f"Streaming data safely to temporary buffer: {temp_path}")

    success = execute_huge_file_processing(
        file_path=input_file,
        output_path=temp_path,
        target_columns=cols_entry.get(),
        year_field_name=year_col_entry.get(),
        day_field_name=day_col_entry.get(),
        start_date_str=start_date_entry.get(),
        end_date_str=end_date_entry.get(),
        date_mode=date_mode_var.get(),
        chunksize=100000,
        template_path="templateFile.csv",
        debug_func=debug_log,
        progress_func=update_progress
    )

    if success:
        try:
            if os.path.exists(output_file):
                os.remove(output_file)
            shutil.move(temp_path, output_file)

            status_label.config(text="Status: Completed Successfully")
            debug_log(f"Final output written to: {output_file}")
            messagebox.showinfo("Success", "File processing complete!")
        except Exception as e:
            status_label.config(text="Status: File Replacement Failed")
            debug_log(f"ERROR: Could not finalize file move: {str(e)}")
            messagebox.showerror(
                "Error", f"Could not replace target file: {str(e)}")
    else:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        status_label.config(text="Status: Failed")
        messagebox.showerror(
            "Error", "Processing encountered an error. Check debug logs.")

    run_button.config(state=tk.NORMAL)


# ---------------------------------------------------------------------------
# APPLICATION INITIALIZATION & LAYOUT
# ---------------------------------------------------------------------------

root = tk.Tk()
root.title("ULM CSV Tool v1.0")
root.geometry("750x420")
root.minsize(650, 420)

debug_visible = False

main_frame = ttk.Frame(root, padding="8")
main_frame.pack(fill=tk.BOTH, expand=True)

# 1. File Options
file_frame = ttk.LabelFrame(main_frame, text="File Options", padding="6")
file_frame.pack(fill=tk.X, pady=2)

ttk.Label(file_frame, text="Input CSV:").grid(
    row=0, column=0, sticky=tk.W, pady=1)
input_entry = ttk.Entry(file_frame, width=50)
input_entry.grid(row=0, column=1, padx=5, pady=1, sticky=tk.EW)
ttk.Button(file_frame, text="Browse...", command=browse_input).grid(
    row=0, column=2, pady=1)

ttk.Label(file_frame, text="Output CSV:").grid(
    row=1, column=0, sticky=tk.W, pady=1)
output_entry = ttk.Entry(file_frame, width=50)
output_entry.grid(row=1, column=1, padx=5, pady=1, sticky=tk.EW)
ttk.Button(file_frame, text="Browse...", command=browse_output).grid(
    row=1, column=2, pady=1)

file_frame.columnconfigure(1, weight=1)

# 2. Filtering Settings
config_frame = ttk.LabelFrame(
    main_frame, text="Filtering & Column Settings", padding="6")
config_frame.pack(fill=tk.X, pady=2)

config_frame.columnconfigure(2, weight=1)

# Columns to Keep
ttk.Label(config_frame, text="Columns to Keep:").grid(
    row=0, column=0, sticky=tk.W, pady=1)
cols_entry = ttk.Entry(config_frame)
cols_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

# Year Column
ttk.Label(config_frame, text="Year Column:").grid(
    row=1, column=0, sticky=tk.W, pady=1)
year_col_entry = ttk.Entry(config_frame, width=20)
year_col_entry.grid(row=1, column=1, padx=5, pady=1, sticky=tk.W)

# Day Column
ttk.Label(config_frame, text="Day Column:").grid(
    row=2, column=0, sticky=tk.W, pady=1)
day_col_entry = ttk.Entry(config_frame, width=20)
day_col_entry.grid(row=2, column=1, padx=5, pady=1, sticky=tk.W)

# Date Format Selection
ttk.Label(config_frame, text="Date Format:").grid(
    row=3, column=0, sticky=tk.W, pady=1)
date_mode_var = tk.StringVar(value="YYYY-MM")

toggle_frame = ttk.Frame(config_frame)
toggle_frame.grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=5, pady=1)

ttk.Radiobutton(
    toggle_frame, text="YYYY-MM", variable=date_mode_var, value="YYYY-MM", command=update_date_labels
).pack(side=tk.LEFT, padx=(0, 10))

ttk.Radiobutton(
    toggle_frame, text="DD-MM-YYYY", variable=date_mode_var, value="DD-MM-YYYY", command=update_date_labels
).pack(side=tk.LEFT)

# Start Date
start_label = ttk.Label(config_frame, text="Start Date:")
start_label.grid(row=4, column=0, sticky=tk.W, pady=1)
start_date_entry = ttk.Entry(config_frame)
start_date_entry.grid(row=4, column=1, columnspan=2,
                      padx=5, pady=1, sticky=tk.EW)

# End Date
end_label = ttk.Label(config_frame, text="End Date:")
end_label.grid(row=5, column=0, sticky=tk.W, pady=1)
end_date_entry = ttk.Entry(config_frame)
end_date_entry.grid(row=5, column=1, columnspan=2,
                    padx=5, pady=1, sticky=tk.EW)

# 3. Action Controls
control_frame = ttk.Frame(main_frame, padding="4")
control_frame.pack(fill=tk.X, pady=4)

run_button = ttk.Button(
    control_frame, text="Start Processing", command=start_processing)
run_button.pack(side=tk.LEFT, padx=5)

debug_toggle_btn = ttk.Button(
    control_frame, text="Show Debug Window", command=toggle_debug_window)
debug_toggle_btn.pack(side=tk.LEFT, padx=5)

status_label = ttk.Label(control_frame, text="Status: Ready")
status_label.pack(side=tk.LEFT, padx=10)

# 4. Debug Console Frame
debug_frame = ttk.LabelFrame(
    main_frame, text="Debug Console Diagnostics", padding="4")
debug_text = tk.Text(debug_frame, wrap=tk.WORD, height=8,
                     bg="#1e1e1e", fg="#00ff00")
debug_scrollbar = ttk.Scrollbar(
    debug_frame, orient=tk.VERTICAL, command=debug_text.yview)
debug_text.configure(yscrollcommand=debug_scrollbar.set)

if __name__ == "__main__":
    root.mainloop()
