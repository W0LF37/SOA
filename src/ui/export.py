from __future__ import annotations
import io
from datetime import datetime, timezone
from typing import Any


def generate_pdf_report(
    tasks_data: dict[str, Any],
    risk_report: dict[str, Any] | None,
    summary: dict[str, Any] | None,
) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable, Paragraph, SimpleDocTemplate,
            Spacer, Table, TableStyle,
        )
    except ImportError:
        return _fallback_bytes(tasks_data)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    DARK  = colors.HexColor("#0f172a")
    BLUE  = colors.HexColor("#3b82f6")
    LIGHT = colors.HexColor("#f1f5f9")
    ORANGE= colors.HexColor("#f97316")
    RED   = colors.HexColor("#ef4444")

    title_s = ParagraphStyle("T", parent=styles["Title"],
        textColor=DARK, fontSize=22, spaceAfter=6)
    h2_s = ParagraphStyle("H2", parent=styles["Heading2"],
        textColor=BLUE, fontSize=14, spaceBefore=12, spaceAfter=4)
    body_s = ParagraphStyle("B", parent=styles["Normal"],
        textColor=DARK, fontSize=10, leading=14)
    small_s = ParagraphStyle("S", parent=styles["Normal"],
        textColor=colors.HexColor("#64748b"), fontSize=8)

    story: list[Any] = []
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    model = (summary or {}).get("model", "N/A")

    story += [
        Paragraph("AI Project Manager", title_s),
        Paragraph("Automated Project Plan Report", h2_s),
        Paragraph(f"Generated: {ts}  |  Model: {model}", small_s),
        HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=12),
    ]

    tasks = tasks_data.get("tasks", [])
    fr = sum(1 for t in tasks if t.get("req_type") == "FR")
    nfr = len(tasks) - fr
    total_h = sum(t.get("estimated_hours") or 0 for t in tasks)
    rl = (risk_report or {}).get("risk_level", "N/A")
    cs = (summary or {}).get("critic", {}).get("score")
    cs_s = f"{cs:.0%}" if isinstance(cs, float) else "N/A"

    kpi = Table(
        [["Total Tasks","FR","NFR","Est. Hours","Risk Level","Critic"],
         [str(len(tasks)), str(fr), str(nfr), str(total_h), rl.upper(), cs_s]],
        repeatRows=1)
    kpi.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),BLUE), ("TEXTCOLOR",(0,0),(-1,0),LIGHT),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),10),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[LIGHT,colors.white]),
        ("TOPPADDING",(0,0),(-1,-1),6), ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]))
    story += [Paragraph("Plan Summary", h2_s), kpi, Spacer(1, 0.4*cm)]

    story.append(Paragraph("Task List", h2_s))
    t_rows = [["ID","Title","Type","C","Hours","Dependencies"]]
    for t in tasks:
        deps = ", ".join(t.get("dependencies", [])) or "—"
        t_rows.append([t.get("id",""),
            Paragraph(t.get("title","")[:58], body_s),
            t.get("req_type",""), str(t.get("complexity","")),
            str(t.get("estimated_hours") or "—"), deps])
    tt = Table(t_rows,
        colWidths=[1.2*cm,6.8*cm,1.2*cm,0.8*cm,1.8*cm,3.7*cm], repeatRows=1)
    tt.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),DARK), ("TEXTCOLOR",(0,0),(-1,0),LIGHT),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),9),
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[LIGHT,colors.white]),
        ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story += [tt, Spacer(1, 0.4*cm)]

    if risk_report and risk_report.get("risks"):
        story.append(Paragraph("Risk Register", h2_s))
        sev_c = {"critical":RED,"high":ORANGE,
                 "medium":colors.HexColor("#eab308"),"low":colors.HexColor("#22c55e")}
        r_rows = [["Severity","Category","Message","Mitigation"]]
        for r in risk_report["risks"][:12]:
            r_rows.append([r.get("severity","").upper(), r.get("category",""),
                Paragraph(r.get("message","")[:80], body_s),
                Paragraph(r.get("mitigation","")[:60], small_s)])
        rt = Table(r_rows,
            colWidths=[1.8*cm,2.2*cm,7.3*cm,5.2*cm], repeatRows=1)
        rt.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),DARK), ("TEXTCOLOR",(0,0),(-1,0),LIGHT),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),8),
            ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[LIGHT,colors.white]),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        for i, r in enumerate(risk_report["risks"][:12], 1):
            c = sev_c.get(r.get("severity","low"), colors.gray)
            rt.setStyle(TableStyle([
                ("TEXTCOLOR",(0,i),(0,i),c),
                ("FONTNAME",(0,i),(0,i),"Helvetica-Bold")]))
        story += [rt, Spacer(1, 0.4*cm)]

    sprints = (summary or {}).get("sprint_plan", [])
    if sprints:
        story.append(Paragraph("Sprint Plan", h2_s))
        sp_rows = [["Sprint","Name","Duration","Pts","Hours","Goal"]]
        for s in sprints:
            sp_rows.append([f"Sprint {s.get('sprint','')}", s.get("name",""),
                f"{s.get('duration_weeks','')}w", str(s.get("total_points","")),
                str(s.get("total_estimated_hours","")),
                Paragraph(s.get("goal","")[:60], small_s)])
        spt = Table(sp_rows,
            colWidths=[1.5*cm,3*cm,1.8*cm,1.2*cm,1.5*cm,7.5*cm], repeatRows=1)
        spt.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),BLUE), ("TEXTCOLOR",(0,0),(-1,0),LIGHT),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"), ("FONTSIZE",(0,0),(-1,-1),9),
            ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#cbd5e1")),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[LIGHT,colors.white]),
            ("TOPPADDING",(0,0),(-1,-1),5), ("BOTTOMPADDING",(0,0),(-1,-1),5),
        ]))
        story.append(spt)

    doc.build(story)
    return buffer.getvalue()


def _fallback_bytes(tasks_data: dict[str, Any]) -> bytes:
    tasks = tasks_data.get("tasks", [])
    lines = ["AI Project Manager - Plan Report", "="*50, ""]
    for t in tasks:
        lines.append(f"{t.get('id','')}  [{t.get('req_type','')}]  "
                     f"C{t.get('complexity','')}  {t.get('title','')}")
    return "\n".join(lines).encode("utf-8")
