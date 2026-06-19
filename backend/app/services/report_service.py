"""
Report Service — compliance sonuclarini PDF rapora cevirir.

Inspector'in export edebilecegi, gerekceli, kritiklik seviyeli,
override'lari yansitan resmi denetim raporu uretir.
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.core.logging import get_logger

logger = get_logger(__name__)

_STATUS_COLORS = {
    "COMPLIANT": colors.HexColor("#1a7f37"),
    "PARTIAL": colors.HexColor("#bf8700"),
    "NON_COMPLIANT": colors.HexColor("#cf222e"),
    "MISSING": colors.HexColor("#8250df"),
    "NOT_COVERED": colors.HexColor("#57606a"),
}

_STATUS_LABEL = {
    "COMPLIANT": "UYUMLU",
    "PARTIAL": "SINIRDA",
    "NON_COMPLIANT": "UYUMSUZ",
    "MISSING": "EKSIK",
    "NOT_COVERED": "KAPSAM DISI",
}


def build_compliance_pdf(run: dict, findings: list[dict]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "QCTitle", parent=styles["Title"], fontSize=18, spaceAfter=6
    )
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=14)
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=10, alignment=TA_LEFT)

    story = []
    story.append(Paragraph("KALITE KONTROL UYGUNLUK RAPORU", title_style))

    header_bits = []
    if run.get("po_number"):
        header_bits.append(f"PO: {run['po_number']}")
    if run.get("po_item"):
        header_bits.append(f"Kalem: {run['po_item']}")
    if run.get("material"):
        header_bits.append(f"Malzeme: {run['material']}")
    header_bits.append(f"Rapor No: {run.get('id', '-')}")
    header_bits.append(f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    story.append(Paragraph(" &nbsp;|&nbsp; ".join(header_bits), meta_style))
    story.append(Spacer(1, 10))

    # Ozet sayaclari
    summary = _summarize(findings)
    story.append(Paragraph("1. YONETICI OZETI", h2))
    summary_data = [["Durum", "Adet"]]
    for status, count in summary.items():
        summary_data.append([_STATUS_LABEL.get(status, status), str(count)])
    summary_table = Table(summary_data, colWidths=[6 * cm, 3 * cm])
    summary_table.setStyle(_summary_table_style())
    story.append(summary_table)
    story.append(Spacer(1, 14))

    # Detayli bulgular
    story.append(Paragraph("2. DETAYLI BULGULAR", h2))
    table_data = [[
        Paragraph("<b>Parametre</b>", cell_style),
        Paragraph("<b>Spec</b>", cell_style),
        Paragraph("<b>Vendor</b>", cell_style),
        Paragraph("<b>Durum</b>", cell_style),
        Paragraph("<b>Kritiklik</b>", cell_style),
        Paragraph("<b>Bolum</b>", cell_style),
    ]]
    for f in findings:
        table_data.append([
            Paragraph(_esc(f.get("parameter", "")), cell_style),
            Paragraph(_esc(f.get("spec_value", "") or "-"), cell_style),
            Paragraph(_esc(f.get("vendor_value", "") or "-"), cell_style),
            Paragraph(_status_html(f.get("status", "")), cell_style),
            Paragraph(_esc(f.get("severity", "") or "-"), cell_style),
            Paragraph(_esc(f.get("spec_section", "") or "-"), cell_style),
        ])
    findings_table = Table(
        table_data,
        colWidths=[4 * cm, 3 * cm, 3 * cm, 2.2 * cm, 1.8 * cm, 1.8 * cm],
        repeatRows=1,
    )
    findings_table.setStyle(_findings_table_style())
    story.append(findings_table)

    # Gerekceler
    story.append(Spacer(1, 14))
    story.append(Paragraph("3. GEREKCELER VE NOTLAR", h2))
    for f in findings:
        if f.get("rationale") or f.get("override_note"):
            line = f"<b>{_esc(f.get('parameter',''))}:</b> {_esc(f.get('rationale','') or '')}"
            if f.get("override_note"):
                line += f" <i>(Denetci notu: {_esc(f['override_note'])})</i>"
            story.append(Paragraph(line, cell_style))
            story.append(Spacer(1, 4))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


def _summarize(findings: list[dict]) -> dict:
    counts = {}
    for f in findings:
        status = f.get("status", "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1
    return counts


_STATUS_HEX = {
    "COMPLIANT": "#1a7f37",
    "PARTIAL": "#bf8700",
    "NON_COMPLIANT": "#cf222e",
    "MISSING": "#8250df",
    "NOT_COVERED": "#57606a",
}


def _status_html(status: str) -> str:
    hex_color = _STATUS_HEX.get(status, "#000000")
    label = _STATUS_LABEL.get(status, status)
    return f'<font color="{hex_color}"><b>{label}</b></font>'


def _esc(text) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _summary_table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24292f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ])


def _findings_table_style():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24292f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7de")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fa")]),
    ])
