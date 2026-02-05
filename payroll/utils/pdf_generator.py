"""
Payslip PDF generation using ReportLab.

Generates professional payslip PDFs with company branding and detailed breakdown.
"""
import os
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def generate_payslip_pdf(payroll):
    """
    Generate a PDF payslip for a weekly payroll record.
    
    Args:
        payroll: WeeklyPayroll instance
        
    Returns:
        HttpResponse with PDF content
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                          rightMargin=0.5*inch, leftMargin=0.5*inch,
                          topMargin=0.5*inch, bottomMargin=0.5*inch)
    
    # Container for PDF elements
    elements = []
    
    # Fonts and currency symbol
    font_name = "Helvetica"
    currency_symbol = "PHP "
    font_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "assets",
            "fonts",
            "DejaVuSans.ttf",
        )
    )
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))
            font_name = "DejaVuSans"
            currency_symbol = "₱"
        except Exception:
            font_name = "Helvetica"
            currency_symbol = "PHP "

    print(f"Using font: {font_name}, Currency symbol: {currency_symbol}")

    def format_currency(value: float) -> str:
        return f"{currency_symbol}{value:,.2f}"

    # Styles
    styles = getSampleStyleSheet()
    styles['Normal'].fontName = font_name
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=4,
        alignment=TA_CENTER,
        fontName=font_name,
    )
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        spaceAfter=8,
        alignment=TA_CENTER,
        fontName=font_name,
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=4,
        spaceBefore=8,
        fontName=font_name,
    )
    
    # Company Header
    elements.append(Paragraph("<b>RVDC Ref and Aircon Repair Shop</b>", title_style))
    elements.append(Paragraph(
        "A-02 MRL Building, Mc. Arthur Hiway, Mabiga, Mabalacat City, Pampanga",
        subtitle_style
    ))
    elements.append(Spacer(1, 0.12*inch))
    
    # Payslip Title
    elements.append(Paragraph("PAYROLL SLIP", title_style))
    elements.append(Spacer(1, 0.08*inch))
    
    # Employee Information
    employee_data = [
        ['Employee Information', ''],
        ['Name:', payroll.employee.get_full_name()],
        ['Role:', payroll.employee.role.capitalize()],
        ['Pay Period:', f"{payroll.week_start.strftime('%b %d')} - {payroll.week_end.strftime('%b %d, %Y')}"],
    ]
    
    employee_table = Table(employee_data, colWidths=[2*inch, 5.5*inch])
    employee_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e7ff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('SPAN', (0, 0), (-1, 0)),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (1, -1), 'LEFT'),
    ]))
    elements.append(employee_table)
    elements.append(Spacer(1, 0.12*inch))
    
    # Hours Breakdown
    elements.append(Paragraph("Hours Breakdown", heading_style))
    regular_hours_amount = float(payroll.regular_hours) * float(payroll.hourly_rate)
    hours_data = [
        ['Description', 'Hours', 'Rate', 'Amount'],
        ['Regular Hours', f"{float(payroll.regular_hours):.2f}", 
            format_currency(float(payroll.hourly_rate)),
            format_currency(regular_hours_amount)],
    ]
    
    if float(payroll.approved_ot_hours or 0) > 0:
        hours_data.append([
            'Overtime Hours',
            f"{float(payroll.approved_ot_hours):.2f}",
            format_currency(float(payroll.hourly_rate * Decimal(str(payroll.overtime_multiplier)))),
            format_currency(float(payroll.approved_ot_pay))
        ])
    
    if float(payroll.night_diff_hours or 0) > 0:
        hours_data.append([
            'Night Differential',
            f"{float(payroll.night_diff_hours):.2f}",
            '-',
            format_currency(float(payroll.night_diff_pay))
        ])
    
    if float(payroll.holiday_pay_total or 0) > 0:
        hours_data.append([
            'Holiday Pay',
            '-',
            '-',
            format_currency(float(payroll.holiday_pay_total))
        ])
    
    hours_table = Table(hours_data, colWidths=[3.5*inch, 1.2*inch, 1.5*inch, 1.3*inch])
    hours_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e7ff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
    ]))
    elements.append(hours_table)
    elements.append(Spacer(1, 0.1*inch))
    
    # Additional Earnings
    if float(payroll.allowances or 0) > 0 or float(payroll.additional_earnings_total or 0) > 0:
        elements.append(Paragraph("Additional Earnings", heading_style))
        earnings_data = [['Description', 'Amount']]
        
        if float(payroll.allowances or 0) > 0:
            earnings_data.append(['Allowances', format_currency(float(payroll.allowances))])
        
        if float(payroll.additional_earnings_total or 0) > 0:
            earnings_data.append(['Other Earnings', format_currency(float(payroll.additional_earnings_total))])
        
        earnings_table = Table(earnings_data, colWidths=[5.5*inch, 2*inch])
        earnings_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e0e7ff')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ]))
        elements.append(earnings_table)
        elements.append(Spacer(1, 0.1*inch))
    
    # Deductions
    if payroll.deductions and isinstance(payroll.deductions, dict):
        elements.append(Paragraph("Deductions", heading_style))
        deductions_data = [['Description', 'Amount']]
        
        for key, value in payroll.deductions.items():
            if float(value) > 0:
                # Format the key to be more readable
                readable_key = key.replace('_', ' ').title()
                deductions_data.append([readable_key, format_currency(float(value))])
        
        if len(deductions_data) > 1:  # Only create table if there are deductions
            deductions_table = Table(deductions_data, colWidths=[5.5*inch, 2*inch])
            deductions_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fee2e2')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#991b1b')),
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                ('TOPPADDING', (0, 0), (-1, 0), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ]))
            elements.append(deductions_table)
            elements.append(Spacer(1, 0.1*inch))
    
    # Summary Totals
    gross_pay = float(payroll.gross_pay) + float(payroll.additional_earnings_total or 0) + \
                float(payroll.allowances or 0) + float(payroll.approved_ot_pay or 0) + \
                float(payroll.night_diff_pay or 0) + float(payroll.holiday_pay_total or 0)
    
    summary_data = [
        ['Gross Pay', format_currency(gross_pay)],
        ['Total Deductions', format_currency(float(payroll.total_deductions))],
        ['Net Pay', format_currency(float(payroll.net_pay))],
    ]
    
    summary_table = Table(summary_data, colWidths=[5.5*inch, 2*inch])
    summary_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('BACKGROUND', (0, 0), (-1, -2), colors.white),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#dcfce7')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#166534')),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Footer
    elements.append(Spacer(1, 0.08*inch))
    footer_text = "This is a system-generated payslip. No signature required."
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        alignment=TA_CENTER,
        fontName=font_name,
    )
    elements.append(Paragraph(footer_text, footer_style))

    # Developer Note
    elements.append(Spacer(1, 0.1*inch))
    developer_note = ParagraphStyle(
        'DevNote',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.grey,
        alignment=TA_CENTER,
        fontName=font_name,
    )
    developer_tag = ParagraphStyle(
        'DevTag',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#1e40af'),
        alignment=TA_CENTER,
        fontName=font_name,
    )
    elements.append(Paragraph("Developed by Ronald Vergel Dela Cruz", developer_note))
    elements.append(Paragraph("&lt;rnldvrgl /&gt;", developer_tag))
    
    # Build PDF
    doc.build(elements)
    
    # Get PDF data
    pdf = buffer.getvalue()
    buffer.close()
    
    # Create response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="payslip_{payroll.employee.username}_{payroll.week_start}.pdf"'
    response.write(pdf)
    
    return response
