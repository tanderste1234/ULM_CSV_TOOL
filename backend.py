import os
import sys
import calendar
import threading
import tempfile
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd


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


def parse_date_range(start_str, end_str, mode):
    """
    Parses start and end date strings into strict normalized date timestamps (midnight).
    """
    s_str = start_str.strip() if start_str else ""
    e_str = end_str.strip() if end_str else ""

    if not s_str and not e_str:
        return None, None

    s_dt = None
    e_dt = None

    if mode == "YYYY-MM":
        date_format = "%Y-%m"
        if s_str:
            parsed = pd.to_datetime(s_str, format=date_format, errors="coerce")
            if pd.notna(parsed):
                s_dt = parsed.floor("D")
        
        if e_str:
            parsed = pd.to_datetime(e_str, format=date_format, errors="coerce")
            if pd.notna(parsed):
                _, last_day = calendar.monthrange(parsed.year, parsed.month)
                e_dt = pd.Timestamp(year=parsed.year, month=parsed.month, day=last_day).floor("D")

    else:  # DD-MM-YYYY
        date_format = "%d-%m-%Y"
        if s_str:
            parsed = pd.to_datetime(s_str, format=date_format, errors="coerce")
            if pd.notna(parsed):
                s_dt = parsed.floor("D")
        
        if e_str:
            parsed = pd.to_datetime(e_str, format=date_format, errors="coerce")
            if pd.notna(parsed):
                e_dt = parsed.floor("D")

    if s_dt is not None and pd.isna(s_dt):
        s_dt = None
    if e_dt is not None and pd.isna(e_dt):
        e_dt = None

    if s_dt and e_dt and s_dt > e_dt:
        s_dt, e_dt = e_dt, s_dt

    return s_dt, e_dt


# ---------------------------------------------------------------------------
# MAIN STREAMING ENGINE
# ---------------------------------------------------------------------------

def execute_huge_file_processing(
    file_path,
    output_path,
    has_header,
    custom_headers_str,
    target_columns,
    year_field_name,
    day_field_name,
    start_date_str,
    end_date_str,
    date_mode,
    chunksize,
    debug_func,
    progress_func
):
    if not os.path.exists(file_path):
        debug_func(f"ERROR: Input file does not exist: {file_path}")
        return False

    r_start, r_end = parse_date_range(start_date_str, end_date_str, date_mode)
    has_date_filter = (r_start is not None) or (r_end is not None)
    
    columns_to_keep = []
    if target_columns and target_columns.strip():
        for c in target_columns.split(","):
            if c.strip():
                columns_to_keep.append(c.strip())

    year_col = year_field_name.strip() if year_field_name else None
    day_col = day_field_name.strip() if day_field_name else None

    if not year_col or not day_col:
        debug_func("ERROR: Both Year field name and Day-of-Year field name must be specified.")
        return False

    custom_names = None
    if not has_header:
        if custom_headers_str and custom_headers_str.strip():
            custom_names = [c.strip() for c in custom_headers_str.split(",") if c.strip()]
        else:
            debug_func("ERROR: 'CSV has no header row' was selected, but no custom headers were provided.")
            return False

    total_rows_processed = 0
    total_rows_written = 0
    write_header = True

    try:
        debug_func("Starting CSV processing stream...")

        read_kwargs = {
            "chunksize": chunksize,
            "dtype": str,
            "low_memory": False,
            "on_bad_lines": "skip"
        }

        if not has_header:
            read_kwargs["header"] = None
            read_kwargs["names"] = custom_names
        else:
            read_kwargs["header"] = 0

        # Context manager ensures file handle is closed promptly
        with pd.read_csv(file_path, **read_kwargs) as reader:
            for chunk_idx, chunk in enumerate(reader):
                total_rows_processed += len(chunk)

                # Clean all column names in the chunk to prevent silent whitespace mismatches
                chunk.columns = [str(c).strip() for c in chunk.columns]

                parsed_dates = pd.Series(index=chunk.index, dtype="datetime64[ns]")

                col_missing = False
                if year_col not in chunk.columns:
                    if chunk_idx == 0:
                        debug_func(f"ERROR: Year column '{year_col}' NOT found in CSV columns: {chunk.columns.tolist()}")
                    col_missing = True
                
                if day_col not in chunk.columns:
                    if chunk_idx == 0:
                        debug_func(f"ERROR: Day column '{day_col}' NOT found in CSV columns: {chunk.columns.tolist()}")
                    col_missing = True

                if not col_missing:
                    clean_yr = chunk[year_col].apply(sanitize_text)
                    clean_day = chunk[day_col].apply(sanitize_text)

                    yr_num = pd.to_numeric(clean_yr, errors="coerce")
                    day_num = pd.to_numeric(clean_day, errors="coerce")

                    valid_mask = yr_num.notna() & day_num.notna() & (day_num >= 1) & (day_num <= 366)

                    if valid_mask.any():
                        yr_str = yr_num[valid_mask].astype(int).astype(str)
                        day_str = day_num[valid_mask].astype(int).astype(str).str.zfill(3)
                        
                        date_strings = yr_str + " " + day_str
                        parsed_dates.loc[valid_mask] = pd.to_datetime(date_strings, format="%Y %j", errors="coerce").dt.floor("D")

                # Always explicitly insert/assign the 'date' column
                chunk.insert(0, "date", parsed_dates.dt.strftime("%d-%m-%Y"))

                if chunk_idx == 0:
                    debug_func("--- CHUNK 0 DIAGNOSTICS ---")
                    debug_func(f"CSV Columns Found: {chunk.columns.tolist()}")
                    debug_func(f"Target Year Col: '{year_col}' | Target Day Col: '{day_col}'")
                    debug_func(f"Filter Mode: {date_mode} | Range: Start={r_start} | End={r_end}")
                    
                    if year_col in chunk.columns and day_col in chunk.columns:
                        debug_func(f"Raw Year Sample: {chunk[year_col].head(3).tolist()}")
                        debug_func(f"Raw Day Sample:  {chunk[day_col].head(3).tolist()}")
                        debug_func(f"Valid Dates Parsed: {parsed_dates.notna().sum()} / {len(chunk)}")
                        if parsed_dates.notna().sum() > 0:
                            debug_func(f"Parsed Sample Dates: {chunk['date'].dropna().head(3).tolist()}")

                # Evaluate filter boundaries strictly against date-only floor timestamps
                if has_date_filter:
                    match_mask = pd.Series(True, index=chunk.index)
                    if r_start is not None:
                        match_mask = match_mask & (parsed_dates >= r_start)
                    if r_end is not None:
                        match_mask = match_mask & (parsed_dates <= r_end)

                    filtered_chunk = chunk[match_mask].copy()
                else:
                    filtered_chunk = chunk.copy()

                # Ensure 'date' column is preserved regardless of user column selection
                if columns_to_keep:
                    existing_cols = [c for c in columns_to_keep if c in filtered_chunk.columns]
                    if "date" not in existing_cols:
                        existing_cols.insert(0, "date")
                    filtered_chunk = filtered_chunk[existing_cols]

                # Output writing: write header once, then continuously append
                if not filtered_chunk.empty:
                    filtered_chunk.to_csv(
                        output_path,
                        mode="w" if write_header else "a",
                        header=write_header,
                        index=False
                    )
                    write_header = False
                    total_rows_written += len(filtered_chunk)

                progress_func(total_rows_processed, total_rows_written)

        if total_rows_written == 0:
            debug_func("WARN: Processing finished, but 0 rows matched your criteria.")
        else:
            debug_func(f"SUCCESS: Written {total_rows_written:,} / {total_rows_processed:,} rows to {output_path}")

        return True

    except Exception as e:
        debug_func(f"EXCEPTION: {str(e)}")
        return False


# ---------------------------------------------------------------------------
# PROCEDURAL UI EVENT HANDLERS & HELPERS
# ---------------------------------------------------------------------------

def debug_log(message):
    debug_text.insert(tk.END, message + "\n")
    debug_text.see(tk.END)


def update_progress(processed, written):
    status_label.config(text=f"Processed: {processed:,} rows | Written: {written:,} rows")


def update_date_labels():
    mode = date_mode_var.get()
    start_label.config(text=f"Start Date ({mode}):")
    end_label.config(text=f"End Date ({mode}):")


def browse_input():
    path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
    if path:
        input_entry.delete(0, tk.END)
        input_entry.insert(0, path)

        if not output_entry.get().strip():
            base, ext = os.path.splitext(path)
            suggested_output = f"{base}_processed{ext}"
            output_entry.delete(0, tk.END)
            output_entry.insert(0, suggested_output)

        if not no_header_var.get():
            load_headers()


def browse_output():
    path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
    if path:
        output_entry.delete(0, tk.END)
        output_entry.insert(0, path)
    else:
        debug_log("Save dialog canceled by user. Output path unchanged.")


def toggle_header_mode():
    if no_header_var.get():
        inspect_btn.config(state=tk.DISABLED)
        header_status_label.config(text="Manual header entry active.")
    else:
        inspect_btn.config(state=tk.NORMAL)
        header_status_label.config(text="No file inspected.")


def load_headers():
    input_path = input_entry.get().strip()
    if not input_path or not os.path.exists(input_path):
        messagebox.showwarning("Warning", "Please select a valid input CSV file first.")
        return

    try:
        df_head = pd.read_csv(input_path, nrows=0)
        headers = [str(c).strip() for c in df_head.columns]
        
        custom_headers_entry.delete(0, tk.END)
        custom_headers_entry.insert(0, ", ".join(headers))

        header_status_label.config(text=f"Loaded {len(headers)} columns from file.")
        debug_log(f"Inspected CSV Headers: {headers}")
    except Exception as e:
        messagebox.showerror("Header Error", f"Could not read headers: {str(e)}")


def toggle_debug_window():
    global debug_visible
    if not debug_visible:
        root.geometry("750x740")
        debug_frame.pack(fill=tk.BOTH, expand=True, pady=4)
        debug_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        debug_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        debug_toggle_btn.config(text="Hide Debug Window")
        debug_visible = True
    else:
        debug_frame.pack_forget()
        root.geometry("750x520")
        debug_toggle_btn.config(text="Show Debug Window")
        debug_visible = False


def start_processing():
    input_file = input_entry.get().strip()
    output_file = output_entry.get().strip()

    if not input_file or not output_file:
        messagebox.showerror("Error", "Please specify both Input and Output CSV paths.")
        return

    abs_input = os.path.realpath(os.path.abspath(input_file))
    abs_output = os.path.realpath(os.path.abspath(output_file))

    if os.path.isdir(abs_output):
        messagebox.showerror("Error", "Output path is a directory, not a file.")
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
    has_header = not no_header_var.get()

    output_dir = os.path.dirname(output_file)
    
    # Use NamedTemporaryFile and explicitly close handle before passing to writer
    temp_file = tempfile.NamedTemporaryFile(dir=output_dir if output_dir else None, suffix=".tmp", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    debug_log(f"Streaming data safely to temporary buffer: {temp_path}")

    success = execute_huge_file_processing(
        file_path=input_file,
        output_path=temp_path,
        has_header=has_header,
        custom_headers_str=custom_headers_entry.get(),
        target_columns=cols_entry.get(),
        year_field_name=year_col_entry.get(),
        day_field_name=day_col_entry.get(),
        start_date_str=start_date_entry.get(),
        end_date_str=end_date_entry.get(),
        date_mode=date_mode_var.get(),
        chunksize=100000,
        debug_func=debug_log,
        progress_func=update_progress
    )

    if success:
        if os.path.exists(output_file):
            os.remove(output_file)
        shutil.move(temp_path, output_file)

        status_label.config(text="Status: Completed Successfully")
        debug_log(f"Final output written to: {output_file}")
        messagebox.showinfo("Success", "File processing complete!")
    else:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        status_label.config(text="Status: Failed")
        messagebox.showerror("Error", "Processing encountered an error. Check debug logs.")

    run_button.config(state=tk.NORMAL)


# ---------------------------------------------------------------------------
# APPLICATION INITIALIZATION & LAYOUT
# ---------------------------------------------------------------------------

root = tk.Tk()
root.title("ULM CSV Tool v1.0")
root.geometry("750x520")
root.minsize(650, 520)

debug_visible = False

main_frame = ttk.Frame(root, padding="8")
main_frame.pack(fill=tk.BOTH, expand=True)

# 1. File Options
file_frame = ttk.LabelFrame(main_frame, text="File Options", padding="6")
file_frame.pack(fill=tk.X, pady=2)

ttk.Label(file_frame, text="Input CSV:").grid(row=0, column=0, sticky=tk.W, pady=1)
input_entry = ttk.Entry(file_frame, width=50)
input_entry.grid(row=0, column=1, padx=5, pady=1, sticky=tk.EW)
ttk.Button(file_frame, text="Browse...", command=browse_input).grid(row=0, column=2, pady=1)

ttk.Label(file_frame, text="Output CSV:").grid(row=1, column=0, sticky=tk.W, pady=1)
output_entry = ttk.Entry(file_frame, width=50)
output_entry.grid(row=1, column=1, padx=5, pady=1, sticky=tk.EW)
ttk.Button(file_frame, text="Browse...", command=browse_output).grid(row=1, column=2, pady=1)

file_frame.columnconfigure(1, weight=1)

# 2. Header Configuration
header_frame = ttk.LabelFrame(main_frame, text="Header Configuration", padding="6")
header_frame.pack(fill=tk.X, pady=2)

no_header_var = tk.BooleanVar(value=False)
no_header_check = ttk.Checkbutton(
    header_frame, 
    text="CSV has no header row (manually define below)", 
    variable=no_header_var,
    command=toggle_header_mode
)
no_header_check.pack(anchor=tk.W, pady=1)

ttk.Label(header_frame, text="Manual / Defined Headers (comma-separated):").pack(anchor=tk.W, pady=(1, 1))
custom_headers_entry = ttk.Entry(header_frame, width=70)
custom_headers_entry.pack(fill=tk.X, pady=1)

header_btn_frame = ttk.Frame(header_frame)
header_btn_frame.pack(fill=tk.X, pady=2)

inspect_btn = ttk.Button(header_btn_frame, text="Inspect CSV Headers", command=load_headers)
inspect_btn.pack(side=tk.LEFT, padx=2)

header_status_label = ttk.Label(header_btn_frame, text="No file inspected.")
header_status_label.pack(side=tk.LEFT, padx=5)

# 3. Filtering Settings
config_frame = ttk.LabelFrame(main_frame, text="Filtering & Column Settings", padding="6")
config_frame.pack(fill=tk.X, pady=2)

ttk.Label(config_frame, text="Columns to Keep (comma-separated):").grid(row=0, column=0, sticky=tk.W, pady=1)
cols_entry = ttk.Entry(config_frame, width=50)
cols_entry.grid(row=0, column=1, columnspan=2, padx=5, pady=1, sticky=tk.EW)

ttk.Label(config_frame, text="Year Column Name:").grid(row=1, column=0, sticky=tk.W, pady=1)
year_col_entry = ttk.Entry(config_frame, width=30)
year_col_entry.grid(row=1, column=1, padx=5, pady=1, sticky=tk.W)

ttk.Label(config_frame, text="Day of Year Column Name (1-365):").grid(row=2, column=0, sticky=tk.W, pady=1)
day_col_entry = ttk.Entry(config_frame, width=30)
day_col_entry.grid(row=2, column=1, padx=5, pady=1, sticky=tk.W)

# Date Format Toggle Radio Buttons
ttk.Label(config_frame, text="Date Format Selection:").grid(row=3, column=0, sticky=tk.W, pady=1)
date_mode_var = tk.StringVar(value="YYYY-MM")

toggle_frame = ttk.Frame(config_frame)
toggle_frame.grid(row=3, column=1, columnspan=2, sticky=tk.W, padx=5, pady=1)

ttk.Radiobutton(
    toggle_frame, text="YYYY-MM Mode", variable=date_mode_var, value="YYYY-MM", command=update_date_labels
).pack(side=tk.LEFT, padx=(0, 10))

ttk.Radiobutton(
    toggle_frame, text="DD-MM-YYYY Mode", variable=date_mode_var, value="DD-MM-YYYY", command=update_date_labels
).pack(side=tk.LEFT)

# Start / End Date Inputs
start_label = ttk.Label(config_frame, text="Start Date (YYYY-MM):")
start_label.grid(row=4, column=0, sticky=tk.W, pady=1)
start_date_entry = ttk.Entry(config_frame, width=30)
start_date_entry.grid(row=4, column=1, padx=5, pady=1, sticky=tk.W)

end_label = ttk.Label(config_frame, text="End Date (YYYY-MM):")
end_label.grid(row=5, column=0, sticky=tk.W, pady=1)
end_date_entry = ttk.Entry(config_frame, width=30)
end_date_entry.grid(row=5, column=1, padx=5, pady=1, sticky=tk.W)

config_frame.columnconfigure(1, weight=1)

# 4. Action Controls
control_frame = ttk.Frame(main_frame, padding="4")
control_frame.pack(fill=tk.X, pady=4)

run_button = ttk.Button(control_frame, text="Start Processing", command=start_processing)
run_button.pack(side=tk.LEFT, padx=5)

debug_toggle_btn = ttk.Button(control_frame, text="Show Debug Window", command=toggle_debug_window)
debug_toggle_btn.pack(side=tk.LEFT, padx=5)

status_label = ttk.Label(control_frame, text="Status: Ready")
status_label.pack(side=tk.LEFT, padx=10)

# 5. Debug Console Frame
debug_frame = ttk.LabelFrame(main_frame, text="Debug Console Diagnostics", padding="4")
debug_text = tk.Text(debug_frame, wrap=tk.WORD, height=8, bg="#1e1e1e", fg="#00ff00")
debug_scrollbar = ttk.Scrollbar(debug_frame, orient=tk.VERTICAL, command=debug_text.yview)
debug_text.configure(yscrollcommand=debug_scrollbar.set)

if __name__ == "__main__":
    root.mainloop()
