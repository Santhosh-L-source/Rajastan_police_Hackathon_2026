"""
PDF report generator using ReportLab.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from pathlib import Path
from datetime import datetime
from typing import Dict, List

def generate_report(case) -> Path:
    """
    Generate PDF report for a case.

    Args:
        case: Case object from database

    Returns:
        Path to generated PDF
    """
    output_dir = Path("./reports")
    output_dir.mkdir(exist_ok=True)

    report_path = output_dir / f"{case.case_id}_report.pdf"

    doc = SimpleDocTemplate(
        str(report_path),
        pagesize=A4,
        rightMargin=0.75*inch,
        leftMargin=0.75*inch,
        topMargin=1*inch,
        bottomMargin=0.75*inch
    )

    story = []
    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=12,
        alignment=TA_CENTER
    )

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor("#2c3e50"),
        spaceAfter=10,
        spaceBefore=15
    )

    # Title
    story.append(Paragraph("TraceFreeze Analysis Report", title_style))
    story.append(Spacer(1, 0.2*inch))

    # Case summary
    story.append(Paragraph("Case Summary", heading_style))

    summary_data = [
        ["Case ID:", case.case_id],
        ["Title:", case.title or "N/A"],
        ["Created:", case.created_at.strftime("%Y-%m-%d %H:%M") if case.created_at else "N/A"],
        ["Analyzed:", case.analyzed_at.strftime("%Y-%m-%d %H:%M") if case.analyzed_at else "N/A"],
        ["Victim Account:", case.victim_account or "Auto-detected"],
    ]

    summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
    summary_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONT', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#555")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))

    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))

    # Statistics
    if case.graph_data:
        story.append(Paragraph("Transaction Network Statistics", heading_style))

        stats = case.graph_data.get("stats", {})
        trace_stats = case.trace_data or {}

        stats_data = [
            ["Total Accounts:", str(stats.get("num_accounts", 0))],
            ["Total Transactions:", str(stats.get("num_transactions", 0))],
            ["Total Money Flow:", f"₹{stats.get('total_flow', 0):,.2f}"],
            ["Traced Accounts:", str(trace_stats.get("num_accounts", 0))],
            ["Traced Amount:", f"₹{trace_stats.get('total_traced', 0):,.2f}"],
        ]

        stats_table = Table(stats_data, colWidths=[2.5*inch, 3.5*inch])
        stats_table.setStyle(TableStyle([
            ('FONT', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONT', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f0f0f0")),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))

        story.append(stats_table)
        story.append(Spacer(1, 0.3*inch))

    # Top suspicious accounts
    if case.suspects_data:
        story.append(Paragraph("Top Suspicious Accounts", heading_style))

        suspects = case.suspects_data[:10]  # Top 10

        suspect_data = [["Rank", "Account", "Score", "Risk", "Explanation"]]

        for i, suspect in enumerate(suspects):
            suspect_data.append([
                str(i + 1),
                suspect["account"][:20],
                f"{suspect['suspicion_score']:.1f}",
                suspect["risk_level"],
                suspect["explanation"][:60] + "..." if len(suspect["explanation"]) > 60 else suspect["explanation"]
            ])

        suspect_table = Table(suspect_data, colWidths=[0.5*inch, 1.5*inch, 0.7*inch, 0.8*inch, 3*inch])
        suspect_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONT', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (3, -1), 'CENTER'),
            ('ALIGN', (4, 0), (4, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
        ]))

        story.append(suspect_table)
        story.append(Spacer(1, 0.3*inch))

    # Freeze priority
    if case.freeze_rankings:
        story.append(PageBreak())
        story.append(Paragraph("Freeze Priority Recommendations", heading_style))

        story.append(Paragraph(
            "Accounts ranked by estimated recovery potential. Freeze these accounts in order to maximize fund recovery.",
            styles['Normal']
        ))
        story.append(Spacer(1, 0.2*inch))

        rankings = case.freeze_rankings[:15]  # Top 15

        freeze_data = [["Priority", "Account", "Est. Recovery", "Time Critical", "Suspicion"]]

        for i, ranking in enumerate(rankings):
            freeze_data.append([
                str(i + 1),
                ranking["account"][:20],
                f"₹{ranking['estimated_recovery']:,.0f}",
                f"{ranking['time_criticality']:.2f}",
                f"{ranking['suspicion_score']:.1f}"
            ])

        freeze_table = Table(freeze_data, colWidths=[0.7*inch, 2*inch, 1.5*inch, 1.2*inch, 1*inch])
        freeze_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONT', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e74c3c")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#fff5f5")]),
        ]))

        story.append(freeze_table)
        story.append(Spacer(1, 0.3*inch))

    # Draft freeze request letter
    story.append(PageBreak())
    story.append(Paragraph("Draft Freeze Request Letter", heading_style))

    letter_text = f"""
    <b>To,</b><br/>
    The Branch Manager<br/>
    [Bank Name]<br/>
    [Branch Address]<br/>
    <br/>
    <b>Subject: Request to Freeze Bank Account - Cyber Fraud Investigation</b><br/>
    <br/>
    Sir/Madam,<br/>
    <br/>
    This is in reference to FIR No. [FIR_NUMBER] dated [DATE] registered at [POLICE_STATION] regarding a cyber fraud case.
    <br/><br/>
    During the course of investigation in the above case (Case ID: {case.case_id}), it has come to notice that the following
    bank account(s) have been used for layering of fraudulently obtained funds:
    <br/><br/>
    """

    if case.freeze_rankings:
        letter_text += "<b>Accounts to be frozen (in priority order):</b><br/>"
        for i, ranking in enumerate(case.freeze_rankings[:5]):
            letter_text += f"{i+1}. Account: {ranking['account']} (Estimated recoverable: ₹{ranking['estimated_recovery']:,.2f})<br/>"

    letter_text += """
    <br/>
    You are therefore requested to immediately freeze the above account(s) and provide account details, transaction history,
    and KYC documents of the account holder(s) for further investigation.
    <br/><br/>
    This is an urgent matter as the funds may be withdrawn or transferred if not frozen immediately.
    <br/><br/>
    Thanking you,<br/>
    <br/>
    <b>[INVESTIGATING OFFICER NAME]</b><br/>
    [DESIGNATION]<br/>
    [POLICE STATION]<br/>
    Date: """ + datetime.now().strftime("%Y-%m-%d")

    story.append(Paragraph(letter_text, styles['Normal']))

    # Build PDF
    doc.build(story)

    return report_path
