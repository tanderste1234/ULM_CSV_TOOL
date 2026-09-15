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
        with open(template_path, mode="r", newline="", encoding="utf-8-sig", errors="ignore") as file:
            reader = csv.reader(file)
            headers = next(reader)
            cleaned_headers = []
            for h in headers:
                cleaned_headers.append(h.strip())
            return cleaned_headers
    except Exception:
        return None


def parse_date_range(start_str, end_str, date_mode, debug_func=print):
    """
    Parses comma-separated date strings into a list of (start_date, end_date) tuples
    acting as an explicit whitelist of valid time windows.
    """
    if not start_str and not end_str:
        return []

    raw_starts = []
    if start_str:
        for item in start_str.split(","):
            cleaned = item.strip()
            if cleaned:
                raw_starts.append(cleaned)

    raw_ends = []
    if end_str:
        for item in end_str.split(","):
            cleaned = item.strip()
            if cleaned:
                raw_ends.append(cleaned)

    max_len = len(raw_starts)
    if len(raw_ends) > max_len:
        max_len = len(raw_ends)

    if max_len == 0:
        return []

    while len(raw_starts) < max_len:
        raw_starts.append("")
    while len(raw_ends) < max_len:
        raw_ends.append("")

    parsed_ranges = []

    for idx in range(max_len):
        c_start = raw_starts[idx]
        c_end = raw_ends[idx]

        s_dt = None
        e_dt = None

        if date_mode == "YYYY-MM":
            if c_start:
                clean_s = c_start.replace("/", "-")
                s_dt = pd.to_datetime(clean_s + "-01", format="%Y-%m-%d", errors="coerce")
                if pd.notna(s_dt):
                    s_dt = s_dt.floor("D")
                    if not c_end:
                        e_dt = (s_dt + pd.offsets.MonthEnd(1)).floor("D")

            if c_end:
                clean_e = c_end.replace("/", "-")
                parsed_e = pd.to_datetime(clean_e + "-01", format="%Y-%m-%d", errors="coerce")
                if pd.notna(parsed_e):
                    e_dt = (parsed_e + pd.offsets.MonthEnd(1)).floor("D")
                    if not s_dt:
                        s_dt = pd.Timestamp.min.floor("D")

        else:  # DD-MM-YYYY mode
            if c_start:
                clean_s = c_start.replace("/", "-")
                s_dt = pd.to_datetime(clean_s, format="%d-%m-%Y", errors="coerce")
                if pd.notna(s_dt):
                    s_dt = s_dt.floor("D")

            if c_end:
                clean_e = c_end.replace("/", "-")
                e_dt = pd.to_datetime(clean_e, format="%d-%m-%Y", errors="coerce")
                if pd.notna(e_dt):
                    e_dt = e_dt.floor("D")

        # Fallbacks for open-ended start or end bounds
        if s_dt is not None or e_dt is not None:
            if s_dt is None:
                s_dt = pd.Timestamp.min.floor("D")
            if e_dt is None:
                e_dt = pd.Timestamp.max.floor("D")

            parsed_ranges.append((s_dt, e_dt))

    return parsed_ranges


def process_single_csv_file(
    file_path,
    output_path,
    template_headers,
    columns_to_keep,
    year_col,
    day_col,
    all_date_ranges,
    chunksize,
    write_header_ref,
    debug_func,
    progress_func,
    overall_processed_ref,
    overall_written_ref
):
    """Processes a headerless CSV file by applying headers loaded strictly from templateFile.csv."""
    if not os.path.exists(file_path):
        if debug_func:
            debug_func(f"ERROR: Input file path invalid or missing: {file_path}")
        return False

    if not template_headers:
        if debug_func:
            debug_func(f"ERROR: Template headers could not be retrieved from template file for {os.path.basename(file_path)}")
        return False

    read_kwargs = {
        "chunksize": chunksize,
        "dtype": str,
        "header": None,
        "names": template_headers,
        "low_memory": False,
        "on_bad_lines": "skip"
    }

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as in_file:
            reader = pd.read_csv(in_file, **read_kwargs)

            for chunk_idx, chunk in enumerate(reader):
                overall_processed_ref[0] += len(chunk)

                # Strip whitespace from column names mapped from the template
                cleaned_columns = []
                for col in chunk.columns:
                    cleaned_columns.append(str(col).strip())
                chunk.columns = cleaned_columns

                parsed_dates = pd.Series(index=chunk.index, dtype="datetime64[ns]")

                if year_col not in chunk.columns or day_col not in chunk.columns:
                    if chunk_idx == 0:
                        if debug_func:
                            debug_func(f"ERROR: Target columns ('{year_col}', '{day_col}') not found in template header set for {os.path.basename(file_path)}")
                            debug_func(f"Available template headers: {list(chunk.columns)}")
                        return False
                else:
                    yr_num = pd.to_numeric(chunk[year_col].astype(str).str.strip(), errors="coerce")
                    day_num = pd.to_numeric(chunk[day_col].astype(str).str.strip(), errors="coerce")

                    valid_mask = yr_num.notna() & day_num.notna() & (day_num >= 1) & (day_num <= 366)

                    if valid_mask.any():
                        clean_years = yr_num[valid_mask].astype(int).astype(str)
                        clean_days = day_num[valid_mask].astype(int)

                        base_dates = pd.to_datetime(clean_years + "-01-01", format="%Y-%m-%d", errors="coerce")
                        day_offsets = pd.to_timedelta(clean_days - 1, unit="D")

                        parsed_dates.loc[valid_mask] = (base_dates + day_offsets).dt.floor("D")

                # Insert parsed date string at column index 0
                chunk.insert(0, "date", parsed_dates.dt.strftime("%d-%m-%Y"))

                # Dynamic chunk date overlap evaluation (Whitelist logic)
                valid_chunk_dates = parsed_dates.dropna()
                active_ranges_for_chunk = []

                if not valid_chunk_dates.empty and all_date_ranges:
                    chunk_min = valid_chunk_dates.min()
                    chunk_max = valid_chunk_dates.max()

                    for r_start, r_end in all_date_ranges:
                        if not (r_end < chunk_min or r_start > chunk_max):
                            active_ranges_for_chunk.append((r_start, r_end))

                if all_date_ranges:
                    if active_ranges_for_chunk:
                        valid_dates = parsed_dates.notna()
                        combined_match_mask = pd.Series(False, index=chunk.index)

                        for r_start, r_end in active_ranges_for_chunk:
                            range_mask = valid_dates & (parsed_dates >= r_start) & (parsed_dates <= r_end)
                            combined_match_mask = combined_match_mask | range_mask

                        filtered_chunk = chunk[combined_match_mask].copy()
                    else:
                        filtered_chunk = chunk.iloc[0:0].copy()
                else:
                    filtered_chunk = chunk.copy()

                # Column target filtering
                if columns_to_keep:
                    existing_cols = []
                    if "date" in filtered_chunk.columns:
                        existing_cols.append("date")

                    for target in columns_to_keep:
                        target_clean = target.strip()
                        if target_clean in filtered_chunk.columns and target_clean not in existing_cols:
                            existing_cols.append(target_clean)

                    filtered_chunk = filtered_chunk[existing_cols]

                # Append chunk to output file
                if not filtered_chunk.empty:
                    filtered_chunk.to_csv(
                        output_path,
                        mode="a",
                        header=write_header_ref[0],
                        index=False
                    )
                    write_header_ref[0] = False
                    overall_written_ref[0] += len(filtered_chunk)

                progress_func(overall_processed_ref[0], overall_written_ref[0])

        return True

    except Exception as err:
        if debug_func:
            debug_func(f"ERROR processing file {file_path}: {str(err)}")
        return False


# ---------------------------------------------------------------------------
# MAIN STREAMING ENGINE
# ---------------------------------------------------------------------------

def execute_huge_file_processing(
    file_path,
    output_path,
    target_columns="",
    year_field_name="",
    day_field_name="",
    start_date_str="",
    end_date_str="",
    date_mode="YYYY-MM",
    chunksize=100000,
    template_path="templateFile.csv",
    debug_func=print,
    progress_func=lambda p, w: None
):
    """
    Main processing entry point for headerless files. Strictly uses templateFile.csv headers.
    """
    if debug_func:
        debug_func("Backend execution initiated...")

    file_list = []
    if isinstance(file_path, list):
        file_list = file_path
    elif isinstance(file_path, str) and file_path.strip():
        for f in file_path.split(","):
            clean_f = f.strip()
            if clean_f:
                file_list.append(clean_f)

    if not file_list:
        if debug_func:
            debug_func("ERROR: No valid input files specified.")
        return False

    all_date_ranges = parse_date_range(start_date_str, end_date_str, date_mode, debug_func)

    columns_to_keep = []
    if target_columns and target_columns.strip():
        for c in target_columns.split(","):
            clean_col = c.strip()
            if clean_col:
                columns_to_keep.append(clean_col)

    year_col = year_field_name.strip() if year_field_name else None
    day_col = day_field_name.strip() if day_field_name else None

    if not year_col or not day_col:
        if debug_func:
            debug_func("ERROR: Year field and Day-of-Year field names must be specified.")
        return False

    # Retrieve headers strictly from templateFile.csv
    template_headers = get_headers_from_template(template_path)
    if debug_func:
        if template_headers:
            debug_func(f"Loaded {len(template_headers)} template headers from '{template_path}'.")
        else:
            debug_func(f"ERROR: Unable to read template file '{template_path}'. Processing aborted.")
            return False

    try:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            pass
    except Exception as e:
        if debug_func:
            debug_func(f"ERROR: Cannot create output file target: {str(e)}")
        return False

    write_header_ref = [True]
    overall_processed_ref = [0]
    overall_written_ref = [0]

    for idx, single_file in enumerate(file_list):
        if debug_func:
            debug_func(f"Processing File [{idx + 1}/{len(file_list)}]: {os.path.basename(single_file)}")

        process_single_csv_file(
            file_path=single_file,
            output_path=output_path,
            template_headers=template_headers,
            columns_to_keep=columns_to_keep,
            year_col=year_col,
            day_col=day_col,
            all_date_ranges=all_date_ranges,
            chunksize=chunksize,
            write_header_ref=write_header_ref,
            debug_func=debug_func,
            progress_func=progress_func,
            overall_processed_ref=overall_processed_ref,
            overall_written_ref=overall_written_ref
        )

    if debug_func:
        debug_func(f"BATCH COMPLETE: Total written = {overall_written_ref[0]:,} / Total processed = {overall_processed_ref[0]:,}")

    gc.collect()
    return overall_written_ref[0] > 0


# ---------------------------------------------------------------------------
# PROCEDURAL UI EVENT HANDLERS & HELPERS
# ---------------------------------------------------------------------------

input_entries = []
debug_visible = False


def log_message(message):
    """Thread-safe proxy for logging to the debug console widget."""
    debug_log(message)


def debug_log(message):
    debug_text.insert(tk.END, str(message) + "\n")
    debug_text.see(tk.END)


def update_progress(processed, written):
    status_label.config(text=f"Processed: {processed:,} rows | Written: {written:,} rows")


def update_date_labels():
    mode = date_mode_var.get()
    start_label.config(text=f"Start Date ({mode}):")
    end_label.config(text=f"End Date ({mode}):")


def browse_specific_input(entry_widget):
    path = filedialog.askopenfilename(
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
    )
    if path:
        entry_widget.delete(0, tk.END)
        entry_widget.insert(0, path)

        if not output_entry.get().strip():
            base, ext = os.path.splitext(path)
            suggested_output = f"{base}_processed{ext}"
            output_entry.delete(0, tk.END)
            output_entry.insert(0, suggested_output)


def add_input_file_field():
    row_idx = len(input_entries) + 1

    label = ttk.Label(inputs_container_frame, text=f"Input CSV {row_idx}:")
    label.grid(row=row_idx, column=0, sticky=tk.W, pady=2)

    entry = ttk.Entry(inputs_container_frame, width=50)
    entry.grid(row=row_idx, column=1, padx=5, pady=2, sticky=tk.EW)

    btn = ttk.Button(
        inputs_container_frame,
        text="Browse...",
        command=lambda e=entry: browse_specific_input(e)
    )
    btn.grid(row=row_idx, column=2, pady=2, sticky=tk.W)

    input_entries.append(entry)


def browse_output():
    path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
    )
    if path:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, path)


def toggle_debug_window():
    global debug_visible
    if not debug_visible:
        root.geometry("750x680")
        debug_frame.pack(fill=tk.BOTH, expand=True, pady=4)
        debug_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        debug_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        debug_toggle_btn.config(text="Hide Debug Window")
        debug_visible = True
    else:
        debug_frame.pack_forget()
        root.geometry("750x460")
        debug_toggle_btn.config(text="Show Debug Window")
        debug_visible = False


def run_job_thread(
    file_in,
    file_out,
    target_cols,
    year_field,
    day_field,
    start_dates,
    end_dates,
    date_mode,
    chunk_size=100000
):
    """Worker thread target that safely invokes the CSV processing engine."""
    try:
        log_message("Initializing background processing job...")

        success = execute_huge_file_processing(
            file_path=file_in,
            output_path=file_out,
            target_columns=target_cols,
            year_field_name=year_field,
            day_field_name=day_field,
            start_date_str=start_dates,
            end_date_str=end_dates,
            date_mode=date_mode,
            chunksize=chunk_size,
            debug_func=log_message,
            progress_func=update_progress
        )

        if success:
            log_message("Job execution completed successfully.")
        else:
            log_message("Job execution finished with warnings or zero matching records.")

    except Exception as err:
        log_message(f"CRITICAL WORKER THREAD ERROR: {str(err)}")
    finally:
        root.after(0, lambda: start_button.config(state="normal"))


def start_processing():
    """Reads input fields from Tkinter controls and spawns run_job_thread."""
    file_in_list = []
    for entry_widget in input_entries:
        val = entry_widget.get().strip()
        if val:
            file_in_list.append(val)

    file_in = ",".join(file_in_list)
    file_out = output_entry.get().strip()

    target_cols = target_cols_entry.get().strip()
    year_field = year_field_entry.get().strip()
    day_field = day_field_entry.get().strip()
    start_dates = start_date_entry.get().strip()
    end_dates = end_date_entry.get().strip()
    date_mode = date_mode_var.get()

    if not file_in or not file_out:
        log_message("ERROR: Both input and output file paths must be selected.")
        messagebox.showerror("Error", "Please specify both input and output file paths.")
        return

    if not year_field or not day_field:
        log_message("ERROR: Year field and Day-of-Year field names are required.")
        messagebox.showerror("Error", "Please provide Year and Day-of-Year field names.")
        return

    start_button.config(state="disabled")

    worker = threading.Thread(
        target=run_job_thread,
        args=(
            file_in,
            file_out,
            target_cols,
            year_field,
            day_field,
            start_dates,
            end_dates,
            date_mode,
        ),
        daemon=True
    )
    worker.start()


# ---------------------------------------------------------------------------
# APPLICATION INITIALIZATION & LAYOUT
# ---------------------------------------------------------------------------

root = tk.Tk()
root.title("ULM CSV Tool v2.0.0")
root.geometry("750x460")
root.minsize(650, 460)

main_frame = ttk.Frame(root, padding="8")
main_frame.pack(fill=tk.BOTH, expand=True)

# 1. File Options
file_frame = ttk.LabelFrame(main_frame, text="File Options", padding="6")
file_frame.pack(fill=tk.X, pady=2)

inputs_container_frame = ttk.Frame(file_frame)
inputs_container_frame.pack(fill=tk.X, expand=True)
inputs_container_frame.columnconfigure(1, weight=1)

add_input_file_field()

add_row_btn_frame = ttk.Frame(file_frame)
add_row_btn_frame.pack(fill=tk.X, pady=(2, 6))

ttk.Button(
    add_row_btn_frame,
    text="+ Add Input File",
    command=add_input_file_field
).pack(side=tk.LEFT)

output_container_frame = ttk.Frame(file_frame)
output_container_frame.pack(fill=tk.X, expand=True)
output_container_frame.columnconfigure(1, weight=1)

ttk.Label(output_container_frame, text="Output CSV:").grid(
    row=0, column=0, sticky=tk.W, pady=1
)
output_entry = ttk.Entry(output_container_frame, width=50)
output_entry.grid(row=0, column=1, padx=5, pady=1, sticky=tk.EW)
ttk.Button(output_container_frame, text="Browse...", command=browse_output).grid(
    row=0, column=2, pady=1, sticky=tk.W
)

# 2. Filtering Settings
config_frame = ttk.LabelFrame(
    main_frame, text="Filtering & Column Settings", padding="6"
)
config_frame.pack(fill=tk.X, pady=2)

config_frame.columnconfigure(2, weight=1)

ttk.Label(config_frame, text="Columns to Keep:").grid(
    row=0, column=0, sticky=tk.W, pady=1
)
target_cols_entry = ttk.Entry(config_frame)
target_cols_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

ttk.Label(config_frame, text="Year Column:").grid(
    row=1, column=0, sticky=tk.W, pady=1
)
year_field_entry = ttk.Entry(config_frame, width=20)
year_field_entry.grid(row=1, column=1, padx=5, pady=1, sticky=tk.W)

ttk.Label(config_frame, text="Day Column:").grid(
    row=2, column=0, sticky=tk.W, pady=1
)
day_field_entry = ttk.Entry(config_frame, width=20)
day_field_entry.grid(row=2, column=1, padx=5, pady=1, sticky=tk.W)

ttk.Label(config_frame, text="Date Format:").grid(
    row=3, column=0, sticky=tk.W, pady=1
)
date_mode_var = tk.StringVar(value="YYYY-MM")

toggle_frame = ttk.Frame(config_frame)
toggle_frame.grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=5, pady=1)

ttk.Radiobutton(
    toggle_frame,
    text="YYYY-MM",
    variable=date_mode_var,
    value="YYYY-MM",
    command=update_date_labels
).pack(side=tk.LEFT, padx=(0, 10))

ttk.Radiobutton(
    toggle_frame,
    text="DD-MM-YYYY",
    variable=date_mode_var,
    value="DD-MM-YYYY",
    command=update_date_labels
).pack(side=tk.LEFT)

start_label = ttk.Label(config_frame, text="Start Date (YYYY-MM):")
start_label.grid(row=4, column=0, sticky=tk.W, pady=1)
start_date_entry = ttk.Entry(config_frame)
start_date_entry.grid(
    row=4, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW
)

end_label = ttk.Label(config_frame, text="End Date (YYYY-MM):")
end_label.grid(row=5, column=0, sticky=tk.W, pady=1)
end_date_entry = ttk.Entry(config_frame)
end_date_entry.grid(
    row=5, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW
)

# 3. Action Controls
control_frame = ttk.Frame(main_frame, padding="4")
control_frame.pack(fill=tk.X, pady=4)

start_button = ttk.Button(
    control_frame, text="Start Processing", command=start_processing
)
start_button.pack(side=tk.LEFT, padx=5)

debug_toggle_btn = ttk.Button(
    control_frame, text="Show Debug Window", command=toggle_debug_window
)
debug_toggle_btn.pack(side=tk.LEFT, padx=5)

status_label = ttk.Label(control_frame, text="Status: Ready")
status_label.pack(side=tk.LEFT, padx=10)

# 4. Debug Console Frame
debug_frame = ttk.LabelFrame(
    main_frame, text="Debug Console Diagnostics", padding="4"
)
debug_text = tk.Text(
    debug_frame, wrap=tk.WORD, height=8, bg="#1e1e1e", fg="#00ff00"
)
debug_scrollbar = ttk.Scrollbar(
    debug_frame, orient=tk.VERTICAL, command=debug_text.yview
)
debug_text.configure(yscrollcommand=debug_scrollbar.set)

if __name__ == "__main__":
    root.mainloop()
