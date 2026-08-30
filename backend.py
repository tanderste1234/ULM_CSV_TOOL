from http.server import HTTPServer, HTTPStatus, BaseHTTPRequestHandler
import threading
import logging
import json
import webbrowser
import os
import pandas as pd
import re
import time
import sys

CHUNK_SIZE = 50_000


def clean_header_string(header_val):
    """Strips quotes, spaces, and UTF-8 BOM characters from column headers."""
    if not isinstance(header_val, str):
        header_val = str(header_val)
    return header_val.replace('\ufeff', '').strip().strip('"').strip("'")


def parse_input_list(raw_input):
    """Converts input (list, comma-separated string, or newline-separated string) into a clean list."""
    if isinstance(raw_input, str):
        items = re.split(r'[,\n\r]+', raw_input)
    elif isinstance(raw_input, list):
        items = []
        for item in raw_input:
            if isinstance(item, str):
                items.extend(re.split(r'[,\n\r]+', item))
            else:
                items.append(str(item))
    else:
        items = [str(raw_input)]

    cleaned = []
    for item in items:
        val = clean_header_string(item)
        if val:
            cleaned.append(val)
    return cleaned


def execute_processing_task(payload_data):
    input_file = payload_data.get('input_file', '')
    output_file = payload_data.get('output_file', '')
    date_field_name = clean_header_string(payload_data.get('date_field_name', ''))

    raw_dates = payload_data.get('dates', [])
    raw_fields = payload_data.get('fields', [])

    clean_dates_list = parse_input_list(raw_dates)
    clean_fields_list = parse_input_list(raw_fields)

    # Ensure the date field is also included in the target output fields if provided
    desired_output_fields = list(clean_fields_list)
    if date_field_name and date_field_name not in desired_output_fields:
        desired_output_fields.append(date_field_name)

    logging.info("--- Payload Pre-processing Setup Complete ---")
    logging.info(f"Cleaned Dates List ({len(clean_dates_list)} items): {clean_dates_list}")
    logging.info(f"Cleaned Fields List ({len(clean_fields_list)} items): {clean_fields_list}")
    logging.info(f"Date Filter Field Name: '{date_field_name}'")

    # Clear/create the output file upfront once
    with open(output_file, 'w', encoding='utf-8') as f:
        pass

    header_written = False
    total_chunks = 0
    total_rows_written = 0

    # Process file in chunks
    for chunk in pd.read_csv(input_file, chunksize=CHUNK_SIZE, dtype=str):
        total_chunks += 1

        # 1. Map lowercase cleaned headers -> actual CSV column header string
        col_map_lower = {
            clean_header_string(col).lower(): col 
            for col in chunk.columns
        }
        
        # 2. Map lowercased target fields to actual CSV header names
        desired_fields_lower = [f.lower() for f in desired_output_fields]

        # Debug header matching on the first chunk
        if total_chunks == 1:
            all_csv_headers = [clean_header_string(c) for c in chunk.columns]
            matched = [f for f in desired_output_fields if f.lower() in col_map_lower]
            missing = [f for f in desired_output_fields if f.lower() not in col_map_lower]
            
            logging.info("================ CSV HEADER AUDIT ================")
            logging.info(f"Actual CSV Headers Found ({len(all_csv_headers)}): {all_csv_headers[:10]}...")
            logging.info(f"Requested Fields MATCHED: {matched}")
            if missing:
                logging.warning(f"Requested Fields NOT MATCHED (Check spelling/case): {missing}")
            logging.info("==================================================")

        # 3. Extract CSV columns for OUTPUT (maintaining exact left-to-right CSV order)
        requested_csv_cols = [
            original_col for original_col in chunk.columns
            if clean_header_string(original_col).lower() in desired_fields_lower
        ]

        if not requested_csv_cols:
            continue

        # 4. Slice chunk data directly containing all target output columns
        sub_df = chunk[requested_csv_cols].copy()

        # 5. Filter rows vertically by date condition (if date field exists in data)
        if date_field_name and date_field_name.lower() in col_map_lower:
            actual_date_col = col_map_lower[date_field_name.lower()]
            if actual_date_col in sub_df.columns and clean_dates_list:
                clean_date_series = sub_df[actual_date_col].astype(str).str.strip()
                sub_df = sub_df[clean_date_series.isin(clean_dates_list)]

        # 6. Clean output header strings
        sub_df.columns = [clean_header_string(c) for c in sub_df.columns]

        # 7. Append matching rows to disk
        if not sub_df.empty:
            sub_df.to_csv(
                output_file,
                mode='a',
                index=False,
                header=not header_written
            )
            header_written = True
            total_rows_written += len(sub_df)

    logging.info("--- Processing Complete ---")
    logging.info(f"Processed {total_chunks} chunk(s). Wrote {total_rows_written} matching row(s) to '{output_file}'.")


def process_large_file(payload_data):
    try:
        execute_processing_task(payload_data)
        logging.info("Task completed successfully.")
    except Exception as e:
        logging.error(f"Error executing processing task: {e}", exc_info=True)


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# Example usage when opening your browser:
def open_browser():
    html_path = get_resource_path("index.html")
    logging.info(f"Opening browser to: file://{html_path}")
    webbrowser.open(f"file://{html_path}")

def shutdown_server(server_instance):
    """Waits 1 second to ensure final HTTP response reaches frontend, then halts server and kills CLI process."""
    time.sleep(1)
    logging.info("Shutting down server instance...")
    server_instance.shutdown()
    logging.info("Exiting Python process...")
    os._exit(0)  # Forces immediate exit of the entire Python CLI process

def handle_request(request):
    path = request.path
    method = request.command

    # 1. Handle OPTIONS preflight requests (CORS)
    if method == 'OPTIONS':
        logging.debug(f"Handling OPTIONS preflight for path: {path}")
        request.send_response(HTTPStatus.OK)
        request.send_header('Access-Control-Allow-Origin', '*')
        request.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        request.send_header('Access-Control-Allow-Headers', 'Content-Type')
        request.end_headers()
        return

    # 2. Handle POST submissions from frontend
    if method == 'POST' and path == '/api/submit':
        try:
            content_length = int(request.headers.get('Content-Length', 0))
            post_data = request.rfile.read(content_length)
            payload_data = json.loads(post_data.decode('utf-8'))

            logging.info("Received POST /api/submit payload. Spawning worker thread...")

            processing_thread = threading.Thread(
                target=process_large_file,
                args=(payload_data,),
                daemon=True
            )
            processing_thread.start()

            response_payload = json.dumps({
                "status": "processing",
                "message": "Background job started successfully!"
            }).encode('utf-8')

            request.send_response(HTTPStatus.ACCEPTED)
            request.send_header('Content-Type', 'application/json')
            request.send_header('Access-Control-Allow-Origin', '*')
            request.end_headers()
            request.wfile.write(response_payload)
        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode JSON payload: {e}")
            request.send_response(HTTPStatus.BAD_REQUEST)
            request.end_headers()
        except Exception as e:
            logging.error(f"Unexpected error processing request: {e}")
            request.send_response(HTTPStatus.INTERNAL_SERVER_ERROR)
            request.end_headers()

    # 3. Handle Quit / Shutdown request
    elif method == 'POST' and path == '/api/quit':
        logging.info("Received POST /api/quit request. Preparing server shutdown...")

        response_payload = json.dumps({
            "status": "success",
            "message": "Server shutting down..."
        }).encode('utf-8')

        request.send_response(HTTPStatus.OK)
        request.send_header('Content-Type', 'application/json')
        request.send_header('Access-Control-Allow-Origin', '*')
        request.end_headers()
        request.wfile.write(response_payload)

        # Trigger shutdown on background thread to let request finish cleanly
        threading.Thread(
            target=shutdown_server,
            args=(request.server,),
            daemon=True
        ).start()

    else:
        logging.warning(f"404 Not Found - {method} {path}")
        request.send_response(HTTPStatus.NOT_FOUND)
        request.end_headers()
def run_server(port=5000):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    BaseHTTPRequestHandler.do_OPTIONS = handle_request
    BaseHTTPRequestHandler.do_POST = handle_request

    server_address = ('', port)
    httpd = HTTPServer(server_address, BaseHTTPRequestHandler)

    logging.info(f"Server initialized on http://localhost:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("Server stopped by user.")


if __name__ == '__main__':
    run_server(5000)
