import os
import shutil
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT
import logging

logger = logging.getLogger('noaa_river_report')

class GeneratePDF:
    # Class-level storage for report_data of each river
    _river_data = {'ilr': None, 'umr': None, 'mor': None}
    _last_timestamp = None

    @staticmethod
    def create_pdf_report(report_data, river):
        """
        Collect report data for a river and generate a combined PDF when all rivers are received.

        Stores report_data for one river ('ilr', 'umr', 'mor') in a class-level dictionary.
        When data for all three rivers is collected, generates a single PDF with separate tables
        for each river, matching the format of individual river reports. Ensures text wrapping
        for the Reach column in 'mor' reports using Paragraph objects. Saves the combined PDF
        to 'reports/pdf/' and archives older PDFs to 'reports/pdf/archive/'. Logs the process
        and any errors.

        Args:
            report_data (list): List of dictionaries containing water level data for one river.
            river (str): Name of the river ('ilr', 'umr', 'mor').

        Returns:
            None
        """
        # Validate inputs
        if not report_data or not isinstance(report_data, list):
            logger.error(f"No valid report data provided for {river.upper()} PDF")
            return
        if river not in ['ilr', 'umr', 'mor']:
            logger.error(f"Invalid river name: {river}")
            return

        # Store report_data
        GeneratePDF._river_data[river] = report_data

        # Check if all rivers' data are collected
        if all(data is not None for data in GeneratePDF._river_data.values()):
            # Generate combined PDF
            GeneratePDF._generate_combined_pdf()
            # Reset stored data
            GeneratePDF._river_data = {'ilr': None, 'umr': None, 'mor': None}

    @staticmethod
    def _generate_combined_pdf():
        """
        Generate a single PDF containing tables for all three rivers.

        Creates a PDF with separate sections for 'ilr', 'umr', and 'mor', each with a table
        matching the format of individual reports. Ensures text wrapping for 'mor' Reach column.
        Saves the PDF to 'reports/pdf/' and archives older PDFs.
        """
        # Create directories
        os.makedirs('reports/pdf', exist_ok=True)
        os.makedirs('reports/pdf/archive', exist_ok=True)

        # Timestamp for title and filename
        now = datetime.now()
        timestamp = now.strftime("%m/%d/%Y %H:%M")
        filename_timestamp = now.strftime("%Y-%m-%d_%Hh%Mm%Ss")

        # Initialize PDF document
        output_path = f"reports/pdf/combined_rivers_{filename_timestamp}_report.pdf"
        doc = SimpleDocTemplate(
            output_path,
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
        reach_style = ParagraphStyle(
            'ReachStyle',
            parent=styles['Normal'],
            fontSize=8,
            leading=9,
            alignment=TA_LEFT,
            wordWrap='CJK'
        )

        # Title and timestamp
        elements.append(Paragraph(f"Report Generated: {timestamp}", right_aligned_style))
        elements.append(Paragraph("WWM NOAA River Report", title_style))
        elements.append(Spacer(1, 12))

        # Process each river
        for river in ['ilr', 'umr', 'mor']:
            report_data = GeneratePDF._river_data[river]
            if not report_data:
                logger.warning(f"No data available for {river.upper()} in combined report")
                continue

            # Add river section header
            elements.append(Paragraph(f"{river.upper()} Water Levels", normal_style))
            elements.append(Spacer(1, 6))

            # Define headers
            region_column = {'ilr': 'Zone', 'umr': 'Pool', 'mor': 'Reach'}[river]
            headers = [region_column, 'Gauge', 'LowAction', 'LowWatch', 'Normal', 'HighWatch', 'HighAction', 'Current']

            # Prepare table data
            data = [headers]
            region_groups = []
            current_region = None
            start_row = 1
            region_phases = {}

            for row in report_data:
                region = row.get(region_column, '')
                if region != current_region:
                    if current_region is not None:
                        region_groups.append((current_region, start_row, len(data)))
                    current_region = region
                    start_row = len(data)

                table_row = [''] * len(headers)
                table_row[0] = Paragraph(region, reach_style) if river == 'mor' and region else region
                table_row[1] = row.get('Gauge', '')
                table_row[7] = str(row.get('Current', 'No Data'))

                if river == 'umr':
                    table_row[4] = row.get('Normal', '')
                    table_row[5] = row.get('Watch', '')
                    table_row[6] = row.get('Action', '')
                else:
                    table_row[2] = row.get('Low Action', '')
                    table_row[3] = row.get('Low Watch', '')
                    table_row[4] = row.get('Normal', '')
                    table_row[5] = row.get('High Watch', '')
                    table_row[6] = row.get('High Action', '')

                phase = 'neutral'
                current_str = table_row[7]
                if current_str != 'No Data' and current_str.strip():
                    try:
                        current = float(current_str)
                        if river == 'umr':
                            normal = table_row[4]
                            watch = table_row[5]
                            action = table_row[6]
                            normal_val = float(normal) if normal.strip() else None
                            action_val = float(action) if action.strip() else None
                            watch_range = watch.split(' - ') if watch and '-' in watch else [watch, watch]
                            watch_min = float(watch_range[0]) if watch_range[0].strip() else None
                            watch_max = float(watch_range[1]) if len(watch_range) > 1 and watch_range[1].strip() else watch_min

                            if action_val and current >= action_val:
                                phase = 'red'
                            elif watch_min and watch_max and watch_min <= current <= watch_max:
                                phase = 'yellow'
                            elif normal_val and current <= normal_val:
                                phase = 'green'
                        else:
                            thresholds = [
                                (table_row[2], 'red', lambda c, t: c <= t),
                                (table_row[3], 'yellow', lambda c, t: c <= t),
                                (table_row[4], 'green', lambda c, t: c <= t),
                                (table_row[5], 'yellow', lambda c, t: c <= t),
                                (table_row[6], 'red', lambda c, t: c >= t)
                            ]
                            for thresh, color, compare in thresholds:
                                if thresh and '-' in thresh:
                                    low, high = map(float, thresh.split(' - '))
                                    if low <= current <= high:
                                        phase = color
                                        break
                                elif thresh.strip():
                                    thresh_val = float(thresh)
                                    if compare(current, thresh_val):
                                        phase = color
                                        break
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Row {len(data)}: Failed to determine phase for {table_row[1]} - Current={current_str}, Error={e}")

                if region:
                    current_phase = region_phases.get(region, 'neutral')
                    phase_priority = {'red': 3, 'yellow': 2, 'green': 1, 'neutral': 0}
                    if phase_priority.get(phase, 0) > phase_priority.get(current_phase, 0):
                        region_phases[region] = phase

                data.append(table_row)

            if current_region is not None:
                region_groups.append((current_region, start_row, len(data)))

            # Define table
            if river == 'mor':
                col_widths = [90, 100, 55, 55, 55, 55, 55, 60]
            else:
                col_widths = [70, 120, 55, 55, 55, 55, 55, 60]
            max_width = 540
            if sum(col_widths) > max_width:
                scale_factor = max_width / sum(col_widths)
                col_widths = [w * scale_factor for w in col_widths]

            table = Table(data, colWidths=col_widths)
            table_styles = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('TEXTWRAP', (0, 0), (-1, -1), True),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ]

            for r in range(1, len(data)):
                table_styles.append(('BACKGROUND', (0, r), (-1, r), colors.white if r % 2 == 1 else colors.lightgrey))

            for region, start, end in region_groups:
                if end > start:
                    table_styles.append(('SPAN', (0, start), (0, end - 1)))
                    for r in range(start + 1, end):
                        data[r][0] = ''
                phase = region_phases.get(region, 'neutral')
                color = {
                    'red': colors.red,
                    'yellow': colors.yellow,
                    'green': colors.green,
                    'neutral': colors.transparent
                }.get(phase, colors.transparent)
                table_styles.append(('BACKGROUND', (0, start), (0, end - 1), color))

            for r, row in enumerate(data[1:], 1):
                current_str = row[7]
                if current_str != 'No Data' and current_str.strip():
                    try:
                        current = float(current_str)
                        if river == 'umr':
                            normal = row[4]
                            watch = row[5]
                            action = row[6]
                            normal_val = float(normal) if normal.strip() else None
                            action_val = float(action) if action.strip() else None
                            watch_range = watch.split(' - ') if watch and '-' in watch else [watch, watch]
                            watch_min = float(watch_range[0]) if watch_range[0].strip() else None
                            watch_max = float(watch_range[1]) if len(watch_range) > 1 and watch_range[1].strip() else watch_min

                            if action_val and current >= action_val:
                                table_styles.append(('BACKGROUND', (6, r), (6, r), colors.red))
                            elif watch_min and watch_max and watch_min <= current <= watch_max:
                                table_styles.append(('BACKGROUND', (5, r), (5, r), colors.yellow))
                            elif normal_val and current <= normal_val:
                                table_styles.append(('BACKGROUND', (4, r), (4, r), colors.green))
                        else:
                            thresholds = [
                                (2, row[2], 'red', lambda c, t: c <= t),
                                (3, row[3], 'yellow', lambda c, t: c <= t),
                                (4, row[4], 'green', lambda c, t: c <= t),
                                (5, row[5], 'yellow', lambda c, t: c <= t),
                                (6, row[6], 'red', lambda c, t: c >= t)
                            ]
                            for col_idx, thresh, color, compare in thresholds:
                                if thresh and '-' in thresh:
                                    low, high = map(float, thresh.split(' - '))
                                    if low <= current <= high:
                                        table_styles.append(('BACKGROUND', (col_idx, r), (col_idx, r), {
                                            'red': colors.red,
                                            'yellow': colors.yellow,
                                            'green': colors.green
                                        }[color]))
                                        break
                                elif thresh.strip():
                                    thresh_val = float(thresh)
                                    if compare(current, thresh_val):
                                        table_styles.append(('BACKGROUND', (col_idx, r), (col_idx, r), {
                                            'red': colors.red,
                                            'yellow': colors.yellow,
                                            'green': colors.green
                                        }[color]))
                                        break
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Row {r}: Failed to apply phase color for {row[1]} - Current={current_str}, Error={e}")

            table.setStyle(TableStyle(table_styles))
            elements.append(table)
            elements.append(Spacer(1, 12))

        # Add notes
        elements.append(Spacer(1, 12))
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

        # Build PDF
        try:
            doc.build(elements)
            logger.info(f"Combined rivers PDF generated successfully at {output_path}")

            # Archive older PDFs
            pdf_dir = 'reports/pdf/'
            archive_dir = 'reports/pdf/archive/'
            pdf_files = [f for f in os.listdir(pdf_dir) if f.startswith('combined_rivers_') and f.endswith('.pdf')]
            if pdf_files:
                pdf_files = sorted(
                    [(f, os.path.getctime(os.path.join(pdf_dir, f))) for f in pdf_files],
                    key=lambda x: x[1],
                    reverse=True
                )
                newest_file = pdf_files[0][0]
                for file, _ in pdf_files[1:]:
                    src_path = os.path.join(pdf_dir, file)
                    dest_path = os.path.join(archive_dir, file)
                    try:
                        os.rename(src_path, dest_path)
                        logger.info(f"Archived combined rivers PDF: {file} to {dest_path}")
                    except OSError as e:
                        logger.error(f"Failed to archive {file} to {dest_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to generate combined rivers PDF: {e}")