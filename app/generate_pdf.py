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
    @staticmethod
    def create_pdf_report(report_data, river):
        """
        Generate a PDF report for a river's water level data with a styled table.

        Creates a PDF with a title, timestamp, and a table of water level data, color-coded
        based on WAP phases. Processes a list of dictionaries for one river ('ilr', 'umr', 'mor'),
        mapping columns to a standard table format with the region column (Reach/Zone/Pool) first.
        Ensures text wrapping for the Reach column in 'mor' reports using Paragraph objects.
        Saves the PDF to 'reports/pdf/' and archives older PDFs to 'reports/pdf/archive/'.
        Logs the process and any errors.

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

        # Create directories
        os.makedirs('reports/pdf', exist_ok=True)
        os.makedirs('reports/pdf/archive', exist_ok=True)

        # Timestamp for title and filename
        now = datetime.now()
        timestamp = now.strftime("%m/%d/%Y %H:%M")
        filename_timestamp = now.strftime("%Y-%m-%d_%Hh%Mm%Ss")

        # Initialize PDF document
        output_path = f"reports/pdf/{river}_{filename_timestamp}_report.pdf"
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
        # Style for Reach column text wrapping
        reach_style = ParagraphStyle(
            'ReachStyle',
            parent=styles['Normal'],
            fontSize=8,
            leading=9,
            alignment=TA_LEFT,
            wordWrap='CJK'  # Ensures wrapping for long strings
        )

        # Title and timestamp
        elements.append(Paragraph(f"Report Generated: {timestamp}", right_aligned_style))
        elements.append(Paragraph(f"WWM Brief {river.upper()}", title_style))
        elements.append(Spacer(1, 12))

        # Define standard headers with region column first
        region_column = {'ilr': 'Zone', 'umr': 'Pool', 'mor': 'Reach'}[river]
        headers = [region_column, 'Gauge', 'LowAction', 'LowWatch', 'Normal', 'HighWatch', 'HighAction', 'Current']

        # Prepare table data
        data = [headers]  # Headers as plain strings
        region_groups = []
        current_region = None
        start_row = 1  # After header
        region_phases = {}  # Track most critical phase per region

        for row in report_data:
            # Track region for grouping
            region = row.get(region_column, '')
            if region != current_region:
                if current_region is not None:
                    region_groups.append((current_region, start_row, len(data)))
                current_region = region
                start_row = len(data)

            # Initialize table row
            table_row = [''] * len(headers)
            # Use Paragraph for Reach in 'mor' to ensure wrapping
            table_row[0] = Paragraph(region, reach_style) if river == 'mor' and region else region
            table_row[1] = row.get('Gauge', '')
            table_row[7] = str(row.get('Current', 'No Data'))

            # Map thresholds based on river
            if river == 'umr':
                table_row[4] = row.get('Normal', '')
                table_row[5] = row.get('Watch', '')
                table_row[6] = row.get('Action', '')
            else:  # ilr, mor
                table_row[2] = row.get('Low Action', '')
                table_row[3] = row.get('Low Watch', '')
                table_row[4] = row.get('Normal', '')
                table_row[5] = row.get('High Watch', '')
                table_row[6] = row.get('High Action', '')

            # Determine WAP phase
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
                    else:  # ilr, mor
                        thresholds = [
                            (table_row[2], 'red', lambda c, t: c <= t),  # LowAction
                            (table_row[3], 'yellow', lambda c, t: c <= t),  # LowWatch
                            (table_row[4], 'green', lambda c, t: c <= t),  # Normal
                            (table_row[5], 'yellow', lambda c, t: c <= t),  # HighWatch
                            (table_row[6], 'red', lambda c, t: c >= t)  # HighAction
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

            # Update region phase (red > yellow > green > neutral)
            if region:
                current_phase = region_phases.get(region, 'neutral')
                phase_priority = {'red': 3, 'yellow': 2, 'green': 1, 'neutral': 0}
                if phase_priority.get(phase, 0) > phase_priority.get(current_phase, 0):
                    region_phases[region] = phase

            data.append(table_row)

        if current_region is not None:
            region_groups.append((current_region, start_row, len(data)))

        # Define table with adjusted column widths for 'mor' to support Reach text wrapping
        if river == 'mor':
            col_widths = [70, 90, 55, 55, 55, 55, 55, 60]  # Wider Reach column for 'mor'
        else:
            col_widths = [50, 130, 55, 55, 55, 55, 55, 60]  # Standard for 'ilr', 'umr'
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
            ('TEXTWRAP', (0, 0), (-1, -1), True),  # Fallback text wrapping
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),  # Left-align Region
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),  # Left-align Gauge
        ]

        # Alternating row colors
        for r in range(1, len(data)):
            table_styles.append(('BACKGROUND', (0, r), (-1, r), colors.white if r % 2 == 1 else colors.lightgrey))

        # Merge region cells and apply phase colors
        for region, start, end in region_groups:
            if end > start:  # Merge if multiple rows
                table_styles.append(('SPAN', (0, start), (0, end - 1)))
                for r in range(start + 1, end):
                    data[r][0] = ''
            # Apply region phase color
            phase = region_phases.get(region, 'neutral')
            color = {
                'red': colors.red,
                'yellow': colors.yellow,
                'green': colors.green,
                'neutral': colors.transparent
            }.get(phase, colors.transparent)
            table_styles.append(('BACKGROUND', (0, start), (0, end - 1), color))

        # Apply WAP phase colors to threshold cells
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
                    else:  # ilr, mor
                        thresholds = [
                            (2, row[2], 'red', lambda c, t: c <= t),  # LowAction
                            (3, row[3], 'yellow', lambda c, t: c <= t),  # LowWatch
                            (4, row[4], 'green', lambda c, t: c <= t),  # Normal
                            (5, row[5], 'yellow', lambda c, t: c <= t),  # HighWatch
                            (6, row[6], 'red', lambda c, t: c >= t)  # HighAction
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
            logger.info(f"{river.upper()} PDF report generated successfully at {output_path}")

            # Archive older PDFs
            pdf_dir = 'reports/pdf/'
            archive_dir = 'reports/pdf/archive/'
            pdf_files = [f for f in os.listdir(pdf_dir) if f.startswith(f'{river}_') and f.endswith('.pdf')]
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
                        logger.info(f"Archived {river.upper()} PDF: {file} to {dest_path}")
                    except OSError as e:
                        logger.error(f"Failed to archive {file} to {dest_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to generate PDF for {river.upper()}: {e}")