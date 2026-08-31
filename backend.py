import os
import re
import csv
import threading
import unicodedata
import tkinter as tk
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
                items.extend(re.split(r'[\s,\t\n\r]+', item.strip()))
            else:
                items.append(str(item))
    else:
        items = [str(raw_input)]

    cleaned = [sanitize_text(x) for x in items]
    return [x for x in cleaned if x]


def execute_huge_file_processing(payload_data):
    input_file = payload_data.get('input_file', '')
    output_file = payload_data.get('output_file', '')
    date_field_name = sanitize_text(payload_data.get('date_field_name', ''))

    clean_dates_list = parse_input_list(payload_data.get('dates', []))
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

        clean_headers = [sanitize_text(h) for h in raw_headers]
        headers_lower_map = {h.lower(): idx for idx,
                             h in enumerate(clean_headers)}

        target_indices = []
        if clean_fields_list:
            for field in clean_fields_list:
                f_lower = field.lower()
                if f_lower in headers_lower_map:
                    target_indices.append(headers_lower_map[f_lower])

        date_col_idx = None
        if date_field_name:
            if date_field_name.lower() in headers_lower_map:
                date_col_idx = headers_lower_map[date_field_name.lower()]
                if target_indices and date_col_idx not in target_indices:
                    target_indices.append(date_col_idx)

        if not target_indices:
            target_indices = list(range(len(clean_headers)))
        else:
            # Sort indices numerical order so output columns match the original file layout
            target_indices = sorted(list(set(target_indices)))

        out_headers = [clean_headers[i] for i in target_indices]
        writer.writerow(out_headers)

        date_patterns = [re.compile(re.escape(d), re.IGNORECASE)
                         for d in clean_dates_list]

        for row in reader:
            total_read += 1
            keep_row = True

            if date_col_idx is not None and clean_dates_list:
                if date_col_idx < len(row):
                    raw_cell = row[date_col_idx]
                    cell_val = sanitize_text(raw_cell)
                    matched = False

                    cell_val_lower = cell_val.lower()
                    for d in clean_dates_list:
                        target_d = d.lower()
                        if target_d == cell_val_lower or target_d in cell_val_lower:
                            matched = True
                            break

                    if not matched:
                        for pattern in date_patterns:
                            if pattern.search(cell_val):
                                matched = True
                                break

                    keep_row = matched
                else:
                    keep_row = False

            if keep_row:
                out_row = [row[i] if i < len(
                    row) else "" for i in target_indices]
                writer.writerow(out_row)
                total_written += 1

    return total_written, total_read


class LocalApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CSV Stream Processor")

        main_frame = tk.Frame(self, padx=15, pady=15)
        main_frame.pack(fill="both", expand=True)

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

        tk.Label(main_frame, text="Target Fields (leave blank to keep all):", font=(
            'Helvetica', 9, 'bold')).pack(anchor="w")
        self.fields_entry = tk.Entry(main_frame)
        self.fields_entry.pack(fill="x", pady=(2, 8))

        tk.Label(main_frame, text="Date Filter Field Name (optional):",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        self.date_field_entry = tk.Entry(main_frame)
        self.date_field_entry.pack(fill="x", pady=(2, 8))

        tk.Label(main_frame, text="Dates to Filter (optional):",
                 font=('Helvetica', 9, 'bold')).pack(anchor="w")
        self.dates_entry = tk.Entry(main_frame)
        self.dates_entry.pack(fill="x", pady=(2, 12))

        self.run_button = tk.Button(main_frame, text="Submit", command=self.start_thread, font=(
            'Helvetica', 10, 'bold'), height=2)
        self.run_button.pack(fill="x")

        self.update_idletasks()
        req_height = self.winfo_reqheight()
        self.geometry(f"540x{req_height}")
        self.minsize(540, req_height)

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
            'dates': self.dates_entry.get().strip()
        }

        if not payload['input_file'] or not payload['output_file']:
            messagebox.showerror(
                "Missing Information", "Please select both input and output file paths.")
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
