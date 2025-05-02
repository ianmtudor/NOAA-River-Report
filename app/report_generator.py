import logging
import os
import shutil
from datetime import datetime
import logging.handlers
import queue
import threading
import requests
from bs4 import BeautifulSoup
import csv
import re
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# Configure thread-safe logging
os.makedirs('logs', exist_ok=True)
logger = logging.getLogger('noaa_river_report')  # Unique logger name
logger.setLevel(logging.INFO)
log_queue = queue.Queue()  # Queue for thread-safe logging
queue_handler = logging.handlers.QueueHandler(log_queue)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
queue_handler.setFormatter(formatter)
logger.addHandler(queue_handler)

# File handler
file_handler = logging.FileHandler(f'logs/report_log_{datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")}.txt')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Start QueueListener for thread-safe logging
listener = logging.handlers.QueueListener(log_queue, file_handler, console_handler)
listener.start()

# File write lock for thread safety
report_lock = threading.Lock()


def get_water_level(url, max_retries=3):
    """
    Fetch water level from the given URL with retry logic.

    Args:
        url (str): URL to fetch data from.
        max_retries (int): Number of retry attempts.

    Returns:
        float: Water level if found, else None.
    """
    session = requests.Session()
    retry = Retry(total=max_retries, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retry))
    session.mount('https://', HTTPAdapter(max_retries=retry))

    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # Robust regex to handle negative numbers and varying decimals
        value = re.search(r'"ObservedPrimary":-?\d+\.\d*', soup.prettify())
        # value = re.search(r'"ObservedPrimary":-?\d+\.\d{1,}', soup.prettify())
        if value:
            return float(value.group().split(':')[1])
        else:
            logger.warning(f"No 'ObservedPrimary' value found at {url}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch data from {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while processing {url}: {e}")
        return None


def generate_reports(path, river_name):
    """
    Generate a water level report for a specified river and save it as a CSV file.

    Reads a CSV file containing gauge URLs for the given river, fetches current water
    levels using get_water_level, and writes the results to a timestamped CSV file in
    the reports/ directory. Caches water levels to avoid redundant requests for duplicate
    URLs within the same river. Logs the process and any errors encountered.

    Args:
        path (str): Directory path to the input CSV files (e.g., 'program/app/src/').
        river_name (str): Name of the river (e.g., 'ilr', 'umr', 'mor').

    Returns:
        None: The function writes output to a CSV file and logs results.
    """
    if not path or not river_name:
        logger.error("Path or river_name cannot be empty")
        return

    file = path + river_name + '_src.csv'
    if not os.path.exists(file):
        logger.error(f"Input CSV file {file} not found")
        return

    report = []
    url_cache = {}  # Cache water levels by URL within this river
    empty_url_count = 0  # Track empty URLs
    try:
        with open(file, newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            if not reader.fieldnames or not {'URL', 'Gauge'}.issubset(reader.fieldnames):
                logger.error(f"Invalid or missing headers in {file}")
                return
            
            for row in reader:
                if row['URL']:
                    # Check cache for URL
                    if row['URL'] in url_cache:
                        # logger.info(f"Using cached water level for {row['URL']}")
                        current_level = url_cache[row['URL']]
                    else:
                        current_level = get_water_level(row['URL'])
                        url_cache[row['URL']] = current_level
                    row['Current'] = current_level if current_level is not None else "No Data"
                    if current_level is None:
                        logger.warning(f"Could not retrieve data for {row['Gauge']} {row['URL']}")
                else:
                    logger.warning(f"No URL provided for {row['Gauge']}")
                    row['Current'] = "No Data"
                    empty_url_count += 1
                report.append(row)
            
            if not report:
                logger.error(f"No data processed for {river_name} report")
                return
            
            # Log cache and empty URL statistics
            cache_hits = sum(1 for row in report if row['URL'] in url_cache and row['URL'])
            logger.info(f"{river_name.upper()}: {cache_hits} URL hits")
            if empty_url_count > 0:
                logger.warning(f"Found {empty_url_count} rows with empty URLs in {river_name} report")
            
            # Write report to CSV; rely on make_csv for logging
            make_csv(report, river_name, reader)
    except csv.Error as e:
        logger.error(f"Error processing CSV file: {e}")


def make_csv(report_file, river_name, reader):
    """
    Write the report data to a timestamped CSV file and archive older CSVs.

    Writes the report to a new CSV in 'reports/csv/'. Moves all older CSVs for the same
    river to 'reports/csv/archive/', keeping only the newest CSV in 'reports/csv/'.

    Args:
        report_file (list): List of dictionaries containing report data.
        river_name (str): Name of the river (e.g., 'ilr', 'umr', 'mor').
        reader (csv.DictReader): CSV reader object with fieldnames.

    Returns:
        None: The function writes the CSV file, moves older CSVs, and logs results.
    """
    logger.info(f"Starting CSV writing process for {river_name.upper()}")
    try:
        # os.makedirs('reports/csv', exist_ok=True)
        os.makedirs('reports/csv/archive', exist_ok=True)
        output_filename = f'reports/csv/{river_name}_{datetime.now().strftime("%Y-%m-%d_%Hh%Mm%Ss")}.csv'
        
        # Write new CSV
        with report_lock:  # Ensure thread-safe file writing
            with open(output_filename, 'w', newline='') as csvfile:
                headers = reader.fieldnames + ['Current']
                writer = csv.DictWriter(csvfile, fieldnames=headers)
                writer.writeheader()
                writer.writerows(report_file)
            logger.info(f"Success - {river_name.upper()} CSV written to {output_filename}")
            
            # Find and move older CSVs for this river
            csv_dir = 'reports/csv/'
            archive_dir = 'reports/csv/archive/'
            pattern = f'{river_name}_*.csv'  # Match CSVs like 'mor_2025-05-02_12h00m00s.csv'
            csv_files = [f for f in os.listdir(csv_dir) if f.startswith(f'{river_name}_') and f.endswith('.csv')]
            
            if csv_files:
                # Sort files by creation time (newest first)
                csv_files = sorted(
                    [(f, os.path.getctime(os.path.join(csv_dir, f))) for f in csv_files],
                    key=lambda x: x[1],
                    reverse=True
                )
                newest_file = csv_files[0][0]  # Keep the newest file
                logger.debug(f"Newest CSV for {river_name.upper()}: {newest_file}")
                
                # Move older files to archive
                for file, _ in csv_files[1:]:  # Skip the newest
                    src_path = os.path.join(csv_dir, file)
                    dest_path = os.path.join(archive_dir, file)
                    try:
                        os.rename(src_path, dest_path)
                        logger.info(f"Archived {river_name.upper()} CSV: {file} to {dest_path}")
                    except OSError as e:
                        logger.error(f"Failed to archive {file} to {dest_path}: {e}")
            
    except Exception as e:
        logger.error(f"Failed to write CSV for {river_name.upper()}: {e}")


def main():
    """
    Main function to process water level data for multiple rivers concurrently.

    Creates threads to generate reports for each river ('ilr', 'umr', 'mor'), starts them,
    and waits for completion. Logs the process and ensures proper cleanup.

    Returns:
        None
    """
    print('Now running the NOAA River Report Application')
    
    # Define source directory and list of rivers to process
    src_location = 'program/app/src/'  # Path to input CSV files
    rivers = ['ilr', 'umr', 'mor']    # River codes for processing

    # Configurable thread timeout
    timeout = int(os.getenv("THREAD_TIMEOUT", 60))

    # Create and start threads for each river
    threads = []  # Initialize empty list for thread objects
    thread_rivers = []  # Track river names for debugging
    for river in rivers:
        logger.info(f"-------Obtaining {river.upper()} river data-------")
        try:
            thread = threading.Thread(target=generate_reports, args=(src_location, river))
            threads.append(thread)
            thread_rivers.append(river)  # Associate thread with river
            thread.start()  # Start thread execution
        except Exception as e:
            logger.error(f"Failed to create/start thread for {river.upper()}: {e}")

    # Wait for all threads to complete with timeout
    for thread, river in zip(threads, thread_rivers):
        thread.join(timeout=timeout)  # Wait up to configured timeout
        if thread.is_alive():
            logger.error(f"Thread for river {river.upper()} timed out")
    
    listener.stop()  # Stop logging listener and ensure buffers are flushed
    log_queue.join()  # Wait for queue to empty
    logging.shutdown()


if __name__ == "__main__":
    main()
