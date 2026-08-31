import os
import re
import csv
import calendar
import threading
import unicodedata
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox


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
    """
    Parses inputs like '2024-01', '01/2024', '2024/01', '01-2024'
    and returns a datetime range covering the entire month:
    (Start of 1st day, End of last day)
    """
    if not month_year_str:
        return None

    cleaned = sanitize_text(month_year_str)

    formats = [
        "%Y-%m", "%m/%Y", "%Y/%m", "%m-%Y"
    ]

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

    # First day of the month at midnight
    start_dt = datetime(year, month, 1, 0, 0, 0)

    # Last day of the month at 23:59:59
    _, last_day = calendar.monthrange(year, month)
    end_dt = datetime(year, month, last_day, 23, 59, 59)

    return start_dt, end_dt


def parse_date_safely(date_str):
    """Parses daily row timestamps from the CSV."""
    if not date_str:
        return None

    cleaned = sanitize_text(date_str)
    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"
    ]

    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass

    return None


def build_month_year_range_pairs(start_months_raw, end_months_raw):
    """
    Pairs start and end month/year inputs by list position and converts 
    them to full datetime range windows.
    """
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


def execute_huge_file_processing(payload_data):
    input_file = payload_data.get('input_file', '')
    output_file = payload_data.get('output_file', '')
    date_field_name = sanitize_text(payload_data.get('date_field_name', ''))

    date_ranges = build_month_year_range_pairs(
        payload_data.get('start_dates', ''),
        payload_data.get('end_dates', '')
    )
    clean_fields_list = parse_input_list(payload_data.get('fields', []))

    out_dir = os.path.dirname(output_file)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    encoding_to_use = 'utf-8'
    try:
        with open(input_file, 'rb') as f_bytes:
            head = f_bytes.read(4)
            if head.startswith(b'\xff\xfe') or head.startswith(b'\xfe\xff'):
                encoding_to_use = 'utf-16'
    except Exception:
        pass

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
    except Exception:
        delimiter = ','

    total_read = 0
    total_written = 0

    with open(input_file, 'r', encoding=encoding_to_use, errors='ignore', buffering=1024*1024) as infile, \
            open(output_file, 'w', encoding='utf-8', newline='', buffering=1024*1024) as outfile:

        reader = csv.reader(infile, delimiter=delimiter)
        writer = csv.writer(outfile)

        try:
            raw_headers = next(reader)
        except StopIteration:
            raise ValueError("The selected input file is empty.")

        clean_headers = []
        for h in raw_headers:
            clean_headers.append(sanitize_text(h))

        headers_lower_map = {}
        for idx, h in enumerate(clean_headers):
            headers_lower_map[h.lower()] = idx

        if date_field_name.lower() not in headers_lower_map:
            raise ValueError(
                f"Date field '{date_field_name}' not found in file headers.")

        date_col_idx = headers_lower_map[date_field_name.lower()]

        target_indices = []
        if clean_fields_list:
            for field in clean_fields_list:
                f_lower = field.lower()
                if f_lower in headers_lower_map:
                    target_indices.append(headers_lower_map[f_lower])

        if target_indices and date_col_idx not in target_indices:
            target_indices.append(date_col_idx)

        if not target_indices:
            target_indices = list(range(len(clean_headers)))
        else:
            unique_indices = set(target_indices)
            target_indices = sorted(list(unique_indices))

        out_headers = []
        for i in target_indices:
            out_headers.append(clean_headers[i])

        writer.writerow(out_headers)

        for row in reader:
            total_read += 1
            keep_row = True

            if date_ranges:
                if date_col_idx < len(row):
                    cell_date = parse_date_safely(row[date_col_idx])
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

    return total_written, total_read


class LocalApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV Stream Processor")

        main_frame = tk.Frame(self, padx=15, pady=15)
        main_frame.pack(fill="both", expand=True)

        # File Inputs
        tk.Label(main_frame, text="Input CSV File:", font=(
            'Helvetica', 9, 'bold')).pack(anchor="w")
        input_frame = tk.Frame(main_frame)
        input_frame.pack(fill="x", pady=(2, 8))
        self.input_entry = tk.Entry(input_frame)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(input_frame, text="Browse...",
                  command=self.browse_input).pack(side="right")

        tk.Label(main_frame, text="Output CSV File:", font=(
            'Helvetica', 9, 'bold')).pack(anchor="w")
        output_frame = tk.Frame(main_frame)
        output_frame.pack(fill="x", pady=(2, 8))
        self.output_entry = tk.Entry(output_frame)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(output_frame, text="Browse...",
                  command=self.browse_output).pack(side="right")

        # Configurations
        tk.Label(main_frame, text="Target Fields (leave blank to keep all):", font=(
            'Helvetica', 9, 'bold')).pack(anchor="w")
        self.fields_entry = tk.Entry(main_frame)
        self.fields_entry.pack(fill="x", pady=(2, 8))

        tk.Label(main_frame, text="Date Filter Field Name (Required):",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        self.date_field_entry = tk.Entry(main_frame)
        self.date_field_entry.pack(fill="x", pady=(2, 8))

        # Separate Lists for Start and End Year-Months
        tk.Label(main_frame, text="Start Months (e.g. 2024-01, 2024-06):",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        self.start_dates_entry = tk.Entry(main_frame)
        self.start_dates_entry.pack(fill="x", pady=(2, 8))

        tk.Label(main_frame, text="End Months (e.g. 2024-03, 2024-08):",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        self.end_dates_entry = tk.Entry(main_frame)
        self.end_dates_entry.pack(fill="x", pady=(2, 12))

        # Submit Button
        self.run_button = tk.Button(main_frame, text="Submit", command=self.start_thread, font=(
            'Helvetica', 10, 'bold'), height=2)
        self.run_button.pack(fill="x")

        self.update_idletasks()
        req_height = self.winfo_reqheight()
        self.geometry(f"560x{req_height}")
        self.minsize(560, req_height)

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
            'date_field_name': self.date_field_entry.get().strip(),
            'fields': self.fields_entry.get().strip(),
            'start_dates': self.start_dates_entry.get().strip(),
            'end_dates': self.end_dates_entry.get().strip()
        }

        if not payload['input_file'] or not payload['output_file']:
            messagebox.showerror(
                "Missing Information", "Please select both input and output file paths.")
            return

        if not payload['date_field_name']:
            messagebox.showerror("Missing Information",
                                 "Please enter the Date Filter Field Name.")
            return

        self.run_button.config(state="disabled", text="Processing...")

        threading.Thread(target=self.run_process_async,
                         args=(payload,), daemon=True).start()

    def run_process_async(self, payload):
        try:
            written, total = execute_huge_file_processing(payload)
            self.after(0, lambda: messagebox.showinfo("Task Complete", f"Processed {
                       total:,} row(s).\nWrote {written:,} row(s) to:\n{payload['output_file']}"))
        except Exception as e:
            self.after(0, lambda: messagebox.showerror(
                "Error", f"An error occurred while processing:\n{e}"))
        finally:
            self.after(0, self.reset_ui)

    def reset_ui(self):
        self.run_button.config(state="normal", text="Submit")


if __name__ == '__main__':
    app = LocalApp()
    app.mainloop()
