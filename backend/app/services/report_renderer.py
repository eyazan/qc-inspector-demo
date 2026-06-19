"""Render the structured final_report into a human-readable Turkish narrative
(brief 0.7 #6). Uses the existing BELGE ANALIZ RAPORU section template and the
result vocabulary; no comparison logic lives here — pure presentation."""

from app.core.constants import RESULT_TR


def render_turkish_narrative(final_report: dict, run_meta: dict | None = None) -> str:
    run_meta = run_meta or {}
    findings = final_report.get("findings", [])
    summary = final_report.get("summary", {})

    lines: list[str] = []
    lines.append("BELGE ANALIZ RAPORU - NIHAI DEGERLENDIRME")
    lines.append("")

    lines.append("1. BELGE TANIMI")
    if run_meta.get("po_number"):
        lines.append(f"- PO: {run_meta['po_number']}")
    if run_meta.get("po_item"):
        lines.append(f"- Kalem: {run_meta['po_item']}")
    if run_meta.get("material"):
        lines.append(f"- Malzeme: {run_meta['material']}")
    if run_meta.get("sap_spec_name"):
        lines.append(f"- Spec Referansi: {run_meta['sap_spec_name']}")
    lines.append("")

    lines.append("2. YONETICI OZETI")
    for result, count in summary.items():
        if count:
            lines.append(f"- {RESULT_TR.get(result, result)}: {count}")
    lines.append(f"- Toplam bulgu: {final_report.get('total_findings', len(findings))}")
    lines.append("")

    lines.append("3. SPEC KARSILASTIRMA BULGULARI")
    for f in findings:
        label = RESULT_TR.get(f.get("result"), f.get("result"))
        section = f.get("spec_section") or "-"
        lines.append(f"- [{f.get('finding_id', '')}] {f.get('parameter')} — {label} (Spec Bolum {section})")
        if f.get("rationale"):
            lines.append(f"  Gerekce: {f['rationale']}")
        cite = _citation(f)
        if cite:
            lines.append(f"  Kanit: {cite}")
    lines.append("")

    notes = final_report.get("reconciliation_notes", [])
    lines.append("4. CAPRAZ BELGE UZLASTIRMA")
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- Uzlastirma gerektiren capraz-belge boslugu yok.")
    lines.append("")

    warnings = final_report.get("referenced_spec_warnings", [])
    if warnings:
        lines.append("5. REFERANS SPEC UYARILARI")
        for w in warnings:
            lines.append(f"- {w.get('message')}")
        lines.append("")

    return "\n".join(lines)


def _citation(finding: dict) -> str:
    parts = []
    if finding.get("vendor_page") is not None:
        parts.append(f"vendor s.{finding['vendor_page']}")
    if finding.get("vendor_region_ids"):
        parts.append("bolge " + ", ".join(finding["vendor_region_ids"]))
    if finding.get("vendor_evidence"):
        parts.append(f"\"{finding['vendor_evidence']}\"")
    return "; ".join(parts)
