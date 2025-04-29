import requests
from bs4 import BeautifulSoup
import csv
import re
import logging
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from time import sleep


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='water_level_log.txt',
    filemode='w'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)


def get_water_level(url, max_retries=3):
    """
    Fetch water level from the given URL with retry logic.

    :param url: URL to fetch data from
    :param max_retries: Number of retry attempts
    :return: Water level as float or None if data couldn't be retrieved
    """
    """
    Fetch water level from the given URL with retry logic.

    :param url: URL to fetch data from
    :param max_retries: Number of retry attempts
    :return: Water level as float or None if data couldn't be retrieved
    """
    session = requests.Session()
    retry = Retry(total=max_retries, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    session.mount('http://', HTTPAdapter(max_retries=retry))
    session.mount('https://', HTTPAdapter(max_retries=retry))

    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()  # Will raise an HTTPError for bad responses

        soup = BeautifulSoup(response.text, 'html.parser')
        value = re.search(r'"ObservedPrimary":\d+\.\d+', soup.prettify())
        if value:
            return float(value.group().split(':')[1])
        else:
            logging.warning(f"No 'ObservedPrimary' value found at {url}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch data from {url}: {e}")
    except Exception as e:
        logging.error(f"Unexpected error while processing {url}: {e}")
    return None


def create_pdf_report(report_data, filename):
    now = datetime.now().strftime("%m/%d/%Y %H:%M")
    river_name = filename.split('_')[0]
    doc = SimpleDocTemplate(
        river_name + "_report.pdf",
        pagesize=letter,
        leftMargin=54, rightMargin=54, topMargin=36, bottomMargin=36
    )
    elements = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    normal_style = styles['Normal']
    right_aligned_style = ParagraphStyle(
        'RightAligned',
        parent=styles['Normal'],
        alignment=TA_RIGHT
    )

    # Title and Generated Row
    title = Paragraph(f"WWM Brief MOR", title_style)
    generated = Paragraph(f"Report Generated: {now}", right_aligned_style)
    
    # Add title and generated text
    elements.append(generated)  # This will appear below the title, right-aligned
    elements.append(title)
    elements.append(Paragraph("<br/><br/>", normal_style))  # Space before table

    # Prepare table data
    headers = ['Reach', 'Gauge', 'Low Action', 'Low Watch', 'Normal', 'High Watch', 'High Action', 'Current Level']
    data = [headers]
    current_reach = None

    for row in report_data:
        if row['Reach'] != current_reach:
            if current_reach is not None:
                data.append([''] * len(headers))
            current_reach = row['Reach']
        data.append([
            row['Reach'], row['Gauge'], row.get('LowAction', ''),
            row.get('LowWatch', ''), row.get('Normal', ''),
            row.get('HighWatch', ''), row.get('HighAction', ''),
            str(row['Current'])
        ])

    if data[-1] == [''] * len(headers):
        data.pop()

    # Dynamic column widths
    col_widths = [75, 90, 55, 55, 55, 55, 55, 60]
    max_width = 540  # Adjusted for new margins (612 - 54 - 54 = 504, but keeping 540 for consistency)
    if sum(col_widths) > max_width:
        scale_factor = max_width / sum(col_widths)
        col_widths = [w * scale_factor for w in col_widths]

    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        *[(('BACKGROUND', (0, r), (-1, r), colors.white if r % 2 == 1 else colors.lightgrey))
          for r in range(1, len(data)) if data[r] != [''] * len(headers)],
        *[(('BACKGROUND', (0, r), (-1, r), colors.black))
          for r in range(1, len(data)) if data[r] == [''] * len(headers)],
        *[(('ROWHEIGHT', (0, r), (-1, r), 5))
          for r in range(1, len(data)) if data[r] == [''] * len(headers)],
        ('WORDWRAP', (0, 0), (-1, -1), True),
        ('ALIGN', (0, 0), (1, -1), 'LEFT'),
    ]))
    
    # color highlight based on current value
    for r, row in enumerate(data[1:], 1):  # Skip header row
        
        if row == [''] * len(headers):  # Skip separator rows
            continue
        
        current_str = row[7]  # Current Level column
        
        if current_str != "No Data" and current_str.strip():  # Ensure not empty
            try:
                # logging.debug(f"Row {r}: Current={current}, LowAction={row[2]}, LowWatch={row[3]}, Normal={row[4]}, HighWatch={row[5]}, HighAction={row[6]}")
                if current_str == 'No Data':
                    continue
                current = float(current_str)
                if row[2]: # 'Low Action' column
                    low_action = float(row[2])
                else: 
                    low_action = None
                if row[3]: # 'Low Watch' column
                    low_watch = row[3].split(' - ')
                    low_watch = float(low_watch[1])
                else:
                    low_watch = None
                
                if row[4]: # normal column
                    if len(row[4]) <= 5:
                        normal = float(row[4])
                    else:
                        normal = row[4].split(' - ')
                        normal = float(normal[1])
                
                if row[5]: # high watch column
                    high_watch = row[5].split(' - ')
                    high_watch = float(high_watch[1])
                
                if row[6]: # high action column
                    high_action = float(row[6])

                # Check thresholds and highlight the corresponding column
                if low_action and current <= low_action:
                    table.setStyle([('BACKGROUND', (2, r), (2, r), colors.red)])  # Red for 'Low Action'
                    # logging.info(f"Row {r}: Applied Red to Low Action - Current={current} <= LowAction={low_action}")
                    
                elif low_watch and current <= low_watch:
                    table.setStyle([('BACKGROUND', (3, r), (3, r), colors.yellow)])  # Yellow for 'Low Watch'
                    
                elif normal:
                    if isinstance(normal, float): # check if normal is a float
                        if current <= normal:
                            table.setStyle([('BACKGROUND', (4, r), (4, r), colors.green)]) # Green for 'Normal'              
                    else: # if normal is a list
                        if current <= normal[1]:
                            table.setStyle([('BACKGROUND', (4, r), (4, r), colors.green)]) # Green for 'Normal'
                    # logging.info(f"Row {r}: Applied Green to Normal - Current={current}")
                    
                elif high_watch:
                    if current <= high_watch:
                        table.setStyle([('BACKGROUND', (5, r), (5, r), colors.yellow)]) # Yellow for 'High Watch'
                        # logging.info(f"Row {r}: Applied Yellow to High Watch - Current={current} >= HighWatch={high_watch}")
                        
                elif high_action:
                    if current >= high_action:
                        table.setStyle([('BACKGROUND', (6, r), (6, r), colors.red)]) # Red for 'High Action'
                        # logging.info(f"Row {r}: Applied Red to High Action - Current={current} >= HighAction={row[6]}")

            except ValueError as e:
                logging.warning(f"Row {r}: Failed to convert values - Current={current_str}, Error={e}")
            
            
    elements.append(table)
    
    # Add note strings below the table
    elements.append(Paragraph("<br/>", normal_style))  # Space after table
    footer_text = [
        "Notes:",
        "1. All levels are in feet unless otherwise specified.",
        "2. The color coding is Green = Normal, Yellow = Watch, and Red = Action WAP phases.",
        "3. Colors in each row indicate the WAP phase for the individual gauge.",
        "4. The entire reach is placed in the most critical phase any one of its gauges is in.",
        "5. The reach's phase is indicated by the coloring in the Reach column.",
        "6. Data is sourced from automated gauges and may contain errors."
    ]
    for line in footer_text:
        elements.append(Paragraph(line, normal_style))

    try:
        doc.build(elements)
        logging.info(f"{river_name.upper()} PDF report generated successfully.")
    except Exception as e:
        logging.error(f"Failed to generate PDF: {e}")


def generate_report(file):
    report = []
    try:
        with open(file, newline='') as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                if row['URL']:
                    current_level = get_water_level(row['URL'])
                    if current_level is not None:
                        row['Current'] = current_level
                    else:
                        row['Current'] = "No Data"
                        logging.warning(f"Could not retrieve data for {row['Gauge']} {row['URL']}")
                    report.append(row)
                # handle duplicate URLs for other reach areas
                else:
                    if current_level == None:
                        logging.warning(f"Could not retrieve data for {row['Gauge']} {row['URL']}")
                    row['Current'] = current_level
                    report.append(row)

        # After collecting data, create the PDF
        create_pdf_report(report, file)

    except FileNotFoundError:
        logging.error("CSV file not found.")
    except csv.Error as e:
        logging.error(f"Error processing CSV file: {e}")


if __name__ == "__main__":
    generate_report('mor_src.csv')