import os
import re
import csv
import calendar
import threading
import unicodedata
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox, scrolledtext


def sanitize_text(val):
    if val is None:
        return ""

    val = unicodedata.normalize('NFKD', str(val))
    val = (
        val.replace('\ufeff', '')
           .replace('\x00', '')
           .replace('\xa0', ' ')
           .replace('\r', '')
    )
    val = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', val)
    return val.strip().strip('"').strip("'").strip()


def parse_input_list(raw_input):
    if not raw_input:
        return []

    if isinstance(raw_input, str):
        items = re.split(r'[\s,\t\n\r]+', raw_input.strip())
    elif isinstance(raw_input, list):
        items = []
        for item in raw_input:
            if isinstance(item, str):
                split_items = re.split(r'[\s,\t\n\r]+', item.strip())
                for sub_item in split_items:
                    items.append(sub_item)
            else:
                items.append(str(item))
    else:
        items = [str(raw_input)]

    cleaned = []
    for x in items:
        sanitized = sanitize_text(x)
        if sanitized:
            cleaned.append(sanitized)

    return cleaned


def parse_year_month_to_range(month_year_str):
    if not month_year_str:
        return None

    cleaned = sanitize_text(month_year_str)
    formats = ["%Y-%m", "%m/%Y", "%Y/%m", "%m-%Y"]

    dt = None
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            break
        except ValueError:
            pass

    if not dt:
        return None

    year = dt.year
    month = dt.month

    start_dt = datetime(year, month, 1, 0, 0, 0)
    _, last_day = calendar.monthrange(year, month)
    end_dt = datetime(year, month, last_day, 23, 59, 59)

    return start_dt, end_dt


def resolve_ordinal_date(year_val, day_of_year_val):
    try:
        year_str = sanitize_text(year_val)
        day_str = sanitize_text(day_of_year_val)

        if not year_str or not day_str:
            return None

        year = int(year_str)
        day_of_year = int(day_str)

        if day_of_year < 1 or day_of_year > 366:
            return None

        base_date = datetime(year, 1, 1)
        return base_date + timedelta(days=day_of_year - 1)

    except (ValueError, TypeError):
        return None


def build_month_year_range_pairs(start_months_raw, end_months_raw):
    start_str_list = parse_input_list(start_months_raw)
    end_str_list = parse_input_list(end_months_raw)

    parsed_ranges = []
    max_len = max(len(start_str_list), len(end_str_list))

    for i in range(max_len):
        start_str = None
        if i < len(start_str_list):
            start_str = start_str_list[i]

        end_str = None
        if i < len(end_str_list):
            end_str = end_str_list[i]

        start_bounds = parse_year_month_to_range(start_str)
        end_bounds = parse_year_month_to_range(end_str)

        if start_bounds and not end_bounds:
            end_bounds = start_bounds
        elif end_bounds and not start_bounds:
            start_bounds = end_bounds

        if start_bounds and end_bounds:
            range_start = start_bounds[0]
            range_end = end_bounds[1]

            if range_start > range_end:
                range_start, range_end = end_bounds[0], start_bounds[1]

            parsed_ranges.append((range_start, range_end))

    return parsed_ranges


def execute_huge_file_processing(payload_data, logger_func=None):
    def log(msg):
        if logger_func:
            logger_func(msg)

    input_file = payload_data.get('input_file', '')
    output_file = payload_data.get('output_file', '')
    has_headers = payload_data.get('has_headers', True)
    custom_headers_raw = payload_data.get('custom_headers', '')

    year_field_name = sanitize_text(payload_data.get('year_field_name', ''))
    day_field_name = sanitize_text(payload_data.get('day_field_name', ''))

    log("Parsing target month date ranges...")
    date_ranges = build_month_year_range_pairs(
        payload_data.get('start_dates', ''),
        payload_data.get('end_dates', '')
    )
    if date_ranges:
        for r_start, r_end in date_ranges:
            log(f"  Filtering Range: {r_start.strftime(
                '%Y-%m-%d')} to {r_end.strftime('%Y-%m-%d')}")
    else:
        log("No valid date range filters supplied. All rows will pass date evaluation.")

    clean_fields_list = parse_input_list(payload_data.get('fields', []))
    if clean_fields_list:
        log(f"Target fields specified: {clean_fields_list}")
    else:
        log("No target fields specified. Retaining all available columns.")

    out_dir = os.path.dirname(output_file)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)
        log(f"Created output directory path: {out_dir}")

    encoding_to_use = 'utf-8-sig'
    try:
        with open(input_file, 'rb') as f_bytes:
            head = f_bytes.read(4)
            if head.startswith(b'\xff\xfe') or head.startswith(b'\xfe\xff'):
                encoding_to_use = 'utf-16'
    except Exception as e:
        log(f"Warning during encoding inspection: {e}")

    log(f"Selected file encoding: {encoding_to_use}")

    delimiter = ','
    try:
        with open(input_file, 'r', encoding=encoding_to_use, errors='ignore') as f_sample:
            sample = f_sample.read(32768)
            if '\t' in sample:
                delimiter = '\t'
            elif ';' in sample:
                delimiter = ';'
            elif '|' in sample:
                delimiter = '|'
    except Exception as e:
        log(f"Warning during delimiter auto-detection: {e}")

    log(f"Detected delimiter: repr({repr(delimiter)})")

    total_read = 0
    total_written = 0

    with open(input_file, 'r', encoding=encoding_to_use, errors='ignore', buffering=1024*1024) as infile, \
            open(output_file, 'w', encoding='utf-8', newline='', buffering=1024*1024) as outfile:

        reader = csv.reader(infile, delimiter=delimiter)
        writer = csv.writer(outfile)

        clean_headers = []

        if has_headers:
            try:
                raw_headers = next(reader)
            except StopIteration:
                raise ValueError("The selected input file is empty.")
            for h in raw_headers:
                clean_headers.append(sanitize_text(h))
            log(f"Read header row from file ({
                len(clean_headers)} columns): {clean_headers}")
        else:
            custom_list = parse_input_list(custom_headers_raw)
            if not custom_list:
                raise ValueError(
                    "Custom headers must be provided when 'File contains header row' is unchecked.")
            clean_headers = custom_list
            log(f"Using user-defined header list ({
                len(clean_headers)} columns): {clean_headers}")

        headers_lower_map = {}
        for idx, h in enumerate(clean_headers):
            headers_lower_map[h.lower()] = idx

        if year_field_name.lower() not in headers_lower_map:
            raise ValueError(
                f"Year field '{year_field_name}' was not found in defined headers.")
        if day_field_name.lower() not in headers_lower_map:
            raise ValueError(
                f"Day field '{day_field_name}' was not found in defined headers.")

        year_col_idx = headers_lower_map[year_field_name.lower()]
        day_col_idx = headers_lower_map[day_field_name.lower()]

        log(f"Mapped Year column '{year_field_name}' to index {year_col_idx}")
        log(f"Mapped Day column '{day_field_name}' to index {day_col_idx}")

        requested_targets = set()
        if clean_fields_list:
            for field in clean_fields_list:
                requested_targets.add(field.lower())
            requested_targets.add(year_field_name.lower())
            requested_targets.add(day_field_name.lower())

        target_indices = []
        for idx, header in enumerate(clean_headers):
            h_lower = header.lower()
            if not requested_targets or h_lower in requested_targets:
                target_indices.append(idx)

        out_headers = []
        for i in target_indices:
            out_headers.append(clean_headers[i])

        log(f"Final output column indices (in original sequence): {
            target_indices}")
        log(f"Final output headers written: {out_headers}")

        writer.writerow(out_headers)

        log("Beginning row processing loop...")
        for row in reader:
            total_read += 1
            keep_row = True

            if date_ranges:
                if year_col_idx < len(row) and day_col_idx < len(row):
                    year_val = row[year_col_idx]
                    day_val = row[day_col_idx]

                    cell_date = resolve_ordinal_date(year_val, day_val)

                    if cell_date:
                        matched_range = False
                        for start, end in date_ranges:
                            if start <= cell_date <= end:
                                matched_range = True
                                break
                        keep_row = matched_range
                    else:
                        keep_row = False
                else:
                    keep_row = False

            if keep_row:
                out_row = []
                for i in target_indices:
                    if i < len(row):
                        out_row.append(row[i])
                    else:
                        out_row.append("")
                writer.writerow(out_row)
                total_written += 1

            if total_read % 250000 == 0:
                log(f"Progress checkpoint: {total_read:,} rows read | {
                    total_written:,} rows matched and written")

    log(f"Processing completed successfully. Total read: {
        total_read:,} | Total written: {total_written:,}")
    return total_written, total_read


class LocalApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV Stream Processor (Ordinal Dates)")

        self.main_frame = tk.Frame(self, padx=15, pady=15)
        self.main_frame.pack(fill="both", expand=True)

        # File Inputs
        tk.Label(self.main_frame, text="Input CSV File:",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        input_frame = tk.Frame(self.main_frame)
        input_frame.pack(fill="x", pady=(2, 8))
        self.input_entry = tk.Entry(input_frame)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(input_frame, text="Browse...",
                  command=self.browse_input).pack(side="right")

        tk.Label(self.main_frame, text="Output CSV File:",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        output_frame = tk.Frame(self.main_frame)
        output_frame.pack(fill="x", pady=(2, 8))
        self.output_entry = tk.Entry(output_frame)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(output_frame, text="Browse...",
                  command=self.browse_output).pack(side="right")

        # Header Mode Selection
        self.has_headers_var = tk.BooleanVar(value=True)
        self.headers_check = tk.Checkbutton(
            self.main_frame,
            text="File contains header row",
            variable=self.has_headers_var,
            command=self.toggle_header_entry,
            font=('Helvetica', 9, 'bold')
        )
        self.headers_check.pack(anchor="w", pady=(2, 4))

        tk.Label(self.main_frame, text="All Column Names (if file has NO header row):", font=(
            'Helvetica', 9, 'bold')).pack(anchor="w")
        self.custom_headers_entry = tk.Entry(self.main_frame, state="disabled")
        self.custom_headers_entry.pack(fill="x", pady=(2, 8))

        # Target Fields Selection
        tk.Label(self.main_frame, text="Target Fields (leave blank to keep all):", font=(
            'Helvetica', 9, 'bold')).pack(anchor="w")
        self.fields_entry = tk.Entry(self.main_frame)
        self.fields_entry.pack(fill="x", pady=(2, 8))

        tk.Label(self.main_frame, text="Year Field Name in CSV (e.g. Year, YYYY):", font=(
            'Helvetica', 9, 'bold')).pack(anchor="w")
        self.year_field_entry = tk.Entry(self.main_frame)
        self.year_field_entry.pack(fill="x", pady=(2, 8))

        tk.Label(self.main_frame, text="Day Field Name in CSV (Day of Year 1-365):",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        self.day_field_entry = tk.Entry(self.main_frame)
        self.day_field_entry.pack(fill="x", pady=(2, 8))

        # Date Filters
        tk.Label(self.main_frame, text="Start Target Months (e.g. 2024-01, 2024-06):",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        self.start_dates_entry = tk.Entry(self.main_frame)
        self.start_dates_entry.pack(fill="x", pady=(2, 8))

        tk.Label(self.main_frame, text="End Target Months (e.g. 2024-03, 2024-08):",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        self.end_dates_entry = tk.Entry(self.main_frame)
        self.end_dates_entry.pack(fill="x", pady=(2, 8))

        # Debug Console Toggle Checkbox
        self.show_debug_var = tk.BooleanVar(value=False)
        self.debug_check = tk.Checkbutton(
            self.main_frame,
            text="Show Debug Console",
            variable=self.show_debug_var,
            command=self.toggle_debug_console,
            font=('Helvetica', 9, 'bold')
        )
        self.debug_check.pack(anchor="w", pady=(2, 8))

        # Collapsible Console Container Frame
        self.console_frame = tk.Frame(self.main_frame)
        self.console_text = scrolledtext.ScrolledText(
            self.console_frame,
            height=10,
            font=('Courier', 9),
            bg="#1e1e1e",
            fg="#00ff00",
            insertbackground="white"
        )
        self.console_text.pack(fill="both", expand=True)

        # Submit Action Button
        self.run_button = tk.Button(self.main_frame, text="Submit", command=self.start_thread, font=(
            'Helvetica', 10, 'bold'), height=2)
        self.run_button.pack(fill="x", pady=(4, 0))

        self.update_idletasks()
        self.base_height = self.winfo_reqheight()
        self.geometry(f"560x{self.base_height}")
        self.minsize(560, self.base_height)

    def log_to_console(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted_msg = f"[{timestamp}] {msg}\n"
        self.after(0, self._append_console_text, formatted_msg)

    def _append_console_text(self, text):
        self.console_text.config(state="normal")
        self.console_text.insert(tk.END, text)
        self.console_text.see(tk.END)

    def toggle_debug_console(self):
        if self.show_debug_var.get():
            self.console_frame.pack(
                fill="both", expand=True, pady=(2, 8), before=self.run_button)
            self.update_idletasks()
            new_height = self.base_height + 180
            self.geometry(f"{self.winfo_width()}x{new_height}")
            self.minsize(560, new_height)
            self.log_to_console("--- Debug Console Opened ---")
        else:
            self.console_frame.pack_forget()
            self.update_idletasks()
            self.geometry(f"{self.winfo_width()}x{self.base_height}")
            self.minsize(560, self.base_height)

    def toggle_header_entry(self):
        if self.has_headers_var.get():
            self.custom_headers_entry.config(state="disabled")
        else:
            self.custom_headers_entry.config(state="normal")

    def browse_input(self):
        filename = filedialog.askopenfilename(
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")])
        if filename:
            self.input_entry.delete(0, tk.END)
            self.input_entry.insert(0, filename)

    def browse_output(self):
        filename = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[
                                                ("CSV Files", "*.csv"), ("All Files", "*.*")])
        if filename:
            self.output_entry.delete(0, tk.END)
            self.output_entry.insert(0, filename)

    def start_thread(self):
        payload = {
            'input_file': self.input_entry.get().strip(),
            'output_file': self.output_entry.get().strip(),
            'has_headers': self.has_headers_var.get(),
            'custom_headers': self.custom_headers_entry.get().strip(),
            'year_field_name': self.year_field_entry.get().strip(),
            'day_field_name': self.day_field_entry.get().strip(),
            'fields': self.fields_entry.get().strip(),
            'start_dates': self.start_dates_entry.get().strip(),
            'end_dates': self.end_dates_entry.get().strip()
        }

        if not payload['input_file'] or not payload['output_file']:
            messagebox.showerror(
                "Missing Information", "Please select both input and output file paths.")
            return

        if not payload['has_headers'] and not payload['custom_headers']:
            messagebox.showerror(
                "Missing Headers", "Please provide column names for files without headers.")
            return

        if not payload['year_field_name']:
            messagebox.showerror("Missing Field Name",
                                 "Please specify the Year field name.")
            return

        if not payload['day_field_name']:
            messagebox.showerror("Missing Field Name",
                                 "Please specify the Day-of-Year field name.")
            return

        self.run_button.config(state="disabled", text="Processing...")
        self.log_to_console("--- Starting Processing Task ---")

        threading.Thread(target=self.run_process_async,
                         args=(payload,), daemon=True).start()

    def run_process_async(self, payload):
        try:
            written, total = execute_huge_file_processing(
                payload, logger_func=self.log_to_console)
            self.after(0, lambda: messagebox.showinfo("Task Complete", f"Processed {
                       total:,} row(s).\nWrote {written:,} row(s) to:\n{payload['output_file']}"))
        except Exception as e:
            self.log_to_console(f"ERROR: Task aborted due to exception -> {e}")
            self.after(0, lambda: messagebox.showerror(
                "Error", f"An error occurred while processing:\n{e}"))
        finally:
            self.after(0, self.reset_ui)

    def reset_ui(self):
        self.run_button.config(state="normal", text="Submit")


if __name__ == '__main__':
    app = LocalApp()
    app.mainloop()
