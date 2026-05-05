from __future__ import annotations

import html
import json
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import networkx as nx
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.core.runtime_paths import (
    iter_readable_shared_input_paths,
    prepare_writable_directory_path,
    prepare_writable_file_path,
    resolve_writable_shared_input_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TASKS_PATH   = prepare_writable_file_path(PROJECT_ROOT, "data/processed/tasks.json")
GRAPH_PATH   = prepare_writable_file_path(PROJECT_ROOT, "storage/graph/dependency_graph.json")
RISK_PATH    = prepare_writable_file_path(PROJECT_ROOT, "data/processed/risk_report.json")
SUMMARY_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/plan_summary.json")
MONITOR_PATH = prepare_writable_file_path(PROJECT_ROOT, "data/processed/monitor_report.json")
TEMP_INPUT   = resolve_writable_shared_input_path(PROJECT_ROOT)
DEFAULT_SAMPLE_INPUT = PROJECT_ROOT / "data" / "raw" / "docs" / "project_brief_sample.txt"
HISTORY_DIR  = prepare_writable_directory_path(PROJECT_ROOT, "storage/run_history")
DEFAULT_REPO_PATH = PROJECT_ROOT

_DARK_LAYOUT = dict(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font={"color": "#f1f5f9"},
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        try:
            display = path.relative_to(PROJECT_ROOT)
        except ValueError:
            display = path
        st.warning(f"Missing: {display}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        st.warning(f"Parse error {path.name}: {exc}")
        return None


def task_rows(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": t.get("id",""), "title": t.get("title",""),
             "req_type": t.get("req_type",""),
             "complexity": t.get("complexity",""),
             "estimated_hours": t.get("estimated_hours") or 0,
             "team_size": t.get("recommended_team_size") or 0}
            for t in tasks]


def metric_row(items: list[tuple[str, Any]]) -> None:
    cols = st.columns(len(items))
    for col, (label, val) in zip(cols, items):
        col.metric(label, val)


def risk_color(level: str) -> str:
    return {"low":"#22c55e","medium":"#eab308",
            "high":"#f97316","critical":"#ef4444"}.get(level.lower(),"#94a3b8")


def dependency_maps(graph: dict) -> tuple[dict, dict]:
    deps: dict[str, list[str]] = defaultdict(list)
    dnts: dict[str, list[str]] = defaultdict(list)
    for e in graph.get("edges", []):
        s, t = str(e.get("source","")), str(e.get("target",""))
        if s and t:
            deps[t].append(s)
            dnts[s].append(t)
    return deps, dnts


def _append_run_history(meta: dict[str, Any]) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = meta["timestamp"].replace(":", "-").replace(" ", "_")
    p = HISTORY_DIR / f"run_{ts}.json"
    p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_run_history() -> list[dict[str, Any]]:
    if not HISTORY_DIR.exists():
        return []
    records = []
    for f in sorted(HISTORY_DIR.glob("run_*.json"), reverse=True)[:10]:
        try:
            records.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return records


def _read_json_silent(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_pipeline_input_text() -> str:
    for candidate in iter_readable_shared_input_paths(PROJECT_ROOT):
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8").strip()
            if text:
                return text

    summary = _read_json_silent(SUMMARY_PATH)
    input_file = summary.get("input_file")
    if isinstance(input_file, str) and input_file.strip():
        candidate = Path(input_file)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        if candidate.exists():
            text = candidate.read_text(encoding="utf-8").strip()
            if text:
                return text

    if DEFAULT_SAMPLE_INPUT.exists():
        return DEFAULT_SAMPLE_INPUT.read_text(encoding="utf-8").strip()

    return ""


def render_hero_banner(role: str) -> None:
    tasks_data = _read_json_silent(TASKS_PATH)
    summary = _read_json_silent(SUMMARY_PATH)
    risk_report = _read_json_silent(RISK_PATH)

    tasks = tasks_data.get("tasks", [])
    task_count = len(tasks) if isinstance(tasks, list) else 0
    critic_score = summary.get("critic", {}).get("score")
    critic_text = f"{critic_score:.0%}" if isinstance(critic_score, (int, float)) else "N/A"
    risk_level = str(risk_report.get("risk_level", "unknown")).upper()
    domain = (
        summary.get("plan_highlights", {}).get("domain")
        or summary.get("plan_highlights", {}).get("likely_domain")
        or summary.get("committee_brief", {}).get("domain")
        or "Inferred from current plan"
    )
    risk_bg = {
        "LOW": "#166534",
        "MEDIUM": "#854d0e",
        "HIGH": "#c2410c",
        "CRITICAL": "#991b1b",
    }.get(risk_level, "#475569")
    role_bg = "#2563eb" if role == "Supervisor" else "#16a34a"

    st.markdown(
        f"""
        <div style="border:1px solid #334155;border-radius:10px;padding:18px 20px;margin:12px 0 18px 0;
                    background:linear-gradient(135deg,#0f172a 0%,#1e293b 60%,#0f172a 100%);">
          <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap;">
            <div>
              <div style="font-size:0.8rem;color:#93c5fd;font-weight:700;text-transform:uppercase;letter-spacing:0;">
                CritiPlan Project Command Center
              </div>
              <div style="font-size:1.45rem;color:#f8fafc;font-weight:800;margin-top:4px;">
                AI Project Manager Dashboard
              </div>
              <div style="color:#cbd5e1;margin-top:4px;max-width:850px;">{html.escape(str(domain))}</div>
            </div>
            <div style="background:{role_bg};color:white;border-radius:999px;padding:7px 12px;font-weight:700;">
              {html.escape(role)}
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:10px;margin-top:16px;">
            <div style="background:#020617;border:1px solid #334155;border-radius:8px;padding:10px;">
              <div style="color:#94a3b8;font-size:0.78rem;">Tasks</div>
              <div style="color:#f8fafc;font-size:1.35rem;font-weight:800;">{task_count}</div>
            </div>
            <div style="background:#020617;border:1px solid #334155;border-radius:8px;padding:10px;">
              <div style="color:#94a3b8;font-size:0.78rem;">Critic Score</div>
              <div style="color:#22c55e;font-size:1.35rem;font-weight:800;">{critic_text}</div>
            </div>
            <div style="background:#020617;border:1px solid #334155;border-radius:8px;padding:10px;">
              <div style="color:#94a3b8;font-size:0.78rem;">Risk Level</div>
              <div style="display:inline-block;background:{risk_bg};color:white;border-radius:6px;padding:3px 8px;margin-top:4px;font-weight:800;">
                {html.escape(risk_level)}
              </div>
            </div>
            <div style="background:#020617;border:1px solid #334155;border-radius:8px;padding:10px;">
              <div style="color:#94a3b8;font-size:0.78rem;">Artifacts</div>
              <div style="color:#f8fafc;font-size:1.35rem;font-weight:800;">JSON + Graph</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Charts (all dark-aware)
# ─────────────────────────────────────────────────────────────────────────────

def render_task_charts(rows: list[dict]) -> None:
    if not rows:
        st.info("No tasks match filters.")
        return
    c1, c2, c3 = st.columns(3)

    counts = {rt: sum(1 for r in rows if r["req_type"] == rt) for rt in ("FR","NFR")}
    fig1 = go.Figure(go.Pie(labels=list(counts.keys()), values=list(counts.values()),
        hole=0.35, marker={"colors":["#3b82f6","#f97316"]}))
    fig1.update_layout(title="FR vs NFR", margin={"l":10,"r":10,"t":50,"b":10}, **_DARK_LAYOUT)
    c1.plotly_chart(fig1, use_container_width=True)

    ccounts = {lv: sum(1 for r in rows if str(r["complexity"])==str(lv)) for lv in range(1,6)}
    fig2 = go.Figure(go.Bar(x=list(ccounts.keys()), y=list(ccounts.values()),
        marker_color="#22c55e"))
    fig2.update_layout(title="Complexity Distribution", xaxis_title="Complexity",
        yaxis_title="Tasks", margin={"l":10,"r":10,"t":50,"b":30}, **_DARK_LAYOUT)
    c2.plotly_chart(fig2, use_container_width=True)

    top = sorted(rows, key=lambda r: r["estimated_hours"], reverse=True)[:10]
    fig3 = go.Figure(go.Bar(x=[r["estimated_hours"] for r in top],
        y=[r["title"] for r in top], orientation="h", marker_color="#a855f7"))
    fig3.update_layout(title="Top Effort Tasks", xaxis_title="Hours",
        yaxis={"autorange":"reversed"}, margin={"l":10,"r":10,"t":50,"b":30}, **_DARK_LAYOUT)
    c3.plotly_chart(fig3, use_container_width=True)


def render_risk_charts(report: dict) -> None:
    score = float(report.get("risk_score", 0) or 0)
    gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        number={"valueformat":".2f"},
        gauge={"axis":{"range":[0,1]}, "bar":{"color":"#3b82f6"},
               "steps":[{"range":[0,.25],"color":"#166534"},
                        {"range":[.25,.5],"color":"#854d0e"},
                        {"range":[.5,.75],"color":"#c2410c"},
                        {"range":[.75,1],"color":"#991b1b"}]},
        title={"text":"Risk Score", "font":{"color":"#f1f5f9"}}))
    gauge.update_layout(height=260, margin={"l":20,"r":20,"t":50,"b":10}, **_DARK_LAYOUT)
    st.plotly_chart(gauge, use_container_width=True)

    sev_order = ["critical","high","medium","low"]
    sev_counts = {s: sum(1 for r in report.get("risks",[])
                         if r.get("severity","").lower()==s) for s in sev_order}
    fig = go.Figure(go.Bar(x=sev_order,
        y=[sev_counts[s] for s in sev_order],
        marker_color=["#991b1b","#c2410c","#eab308","#22c55e"]))
    fig.update_layout(title="Risks by Severity",
        margin={"l":10,"r":10,"t":50,"b":30}, **_DARK_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)


def render_sprint_timeline(sprint_plan: list[dict]) -> None:
    if not sprint_plan:
        return
    palette = ["#3b82f6","#22c55e","#f97316","#a855f7","#ef4444"]
    fig = go.Figure(go.Bar(
        x=[1]*len(sprint_plan),
        y=[s.get("name",f"Sprint {i+1}") for i,s in enumerate(sprint_plan)],
        base=list(range(len(sprint_plan))),
        orientation="h",
        marker_color=[palette[i % len(palette)] for i in range(len(sprint_plan))],
        hovertext=[f"<b>{s.get('name','')}</b><br>Hours: {s.get('total_estimated_hours','')}<br>"
                   f"Tasks: {', '.join(s.get('tasks',[]))}" for s in sprint_plan],
        hoverinfo="text",
        text=[f"{s.get('total_estimated_hours',0)}h" for s in sprint_plan],
        textposition="inside"))
    fig.update_layout(title="Sprint Timeline", xaxis_title="Sprint index",
        yaxis={"autorange":"reversed"},
        height=max(260, 80+len(sprint_plan)*60),
        margin={"l":10,"r":10,"t":50,"b":40}, **_DARK_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────────────────────────────────────

def render_tasks_tab() -> None:
    data = load_json(TASKS_PATH)
    if data is None:
        return
    tasks = data.get("tasks", [])
    req_type   = st.sidebar.selectbox("Requirement type", ["All","FR","NFR"])
    complexity = st.sidebar.selectbox("Complexity", ["All","1","2","3","4","5"])
    filtered = [t for t in tasks
                if (req_type=="All" or t.get("req_type")==req_type)
                and (complexity=="All" or str(t.get("complexity"))==complexity)]
    rows = task_rows(filtered)
    total_h = sum(r["estimated_hours"] for r in rows)
    metric_row([("Tasks", len(rows)), ("Estimated Hours", total_h)])
    st.dataframe(rows, use_container_width=True, hide_index=True)
    render_task_charts(rows)


def render_graph_tab() -> None:
    graph = load_json(GRAPH_PATH)
    if graph is None:
        return
    nodes = graph.get("nodes", [])
    deps, dnts = dependency_maps(graph)
    if not nodes:
        st.info("No graph nodes found.")
        return

    G = nx.DiGraph()
    for n in nodes:
        tid = str(n.get("id",""))
        if tid:
            G.add_node(tid, **n)
    for e in graph.get("edges", []):
        s, t = str(e.get("source","")), str(e.get("target",""))
        if s and t:
            G.add_edge(s, t)

    try:
        cp = set(nx.dag_longest_path(G))
    except nx.NetworkXUnfeasible:
        cp = set()

    pos = nx.spring_layout(G, seed=42)
    ex, ey = [], []
    for s, t in G.edges():
        x0,y0 = pos[s]; x1,y1 = pos[t]
        ex += [x0,x1,None]; ey += [y0,y1,None]

    edge_trace = go.Scatter(x=ex, y=ey, mode="lines",
        line={"width":1.5,"color":"#475569"}, hoverinfo="skip")

    nx_, ny_, nlabels, ncolors, hover = [], [], [], [], []
    for tid in G.nodes():
        x, y = pos[tid]
        n = G.nodes[tid]
        d = deps.get(tid, [])
        dnt = dnts.get(tid, [])
        color = ("#f97316" if tid in cp else "#22c55e" if not d
                 else "#ef4444" if len(dnt)>=2 else "#3b82f6")
        nx_.append(x); ny_.append(y); nlabels.append(tid); ncolors.append(color)
        hover.append(f"<b>{tid}</b><br>{n.get('title','')}<br>"
                     f"Complexity: {n.get('complexity','n/a')}<br>"
                     f"Deps: {len(d)}  Dependents: {len(dnt)}")

    node_trace = go.Scatter(x=nx_, y=ny_, mode="markers+text",
        text=nlabels, textposition="top center",
        hovertext=hover, hoverinfo="text",
        marker={"size":20,"color":ncolors,"line":{"width":1.5,"color":"#1e293b"}})

    fig = go.Figure(data=[edge_trace, node_trace])
    fig.update_layout(title="Dependency Network", showlegend=False, height=680,
        margin={"l":10,"r":10,"t":50,"b":10},
        xaxis={"showgrid":False,"zeroline":False,"showticklabels":False},
        yaxis={"showgrid":False,"zeroline":False,"showticklabels":False},
        **_DARK_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("🟢 root  🔴 bottleneck  🟠 critical path  🔵 normal")


def render_gantt_tab() -> None:
    data    = load_json(TASKS_PATH)
    summary = load_json(SUMMARY_PATH)
    if data is None or summary is None:
        st.info("Run the pipeline first.")
        return

    tasks      = data.get("tasks", [])
    sprint_map = {tid: sp.get("sprint", 1)
                  for sp in summary.get("sprint_plan", [])
                  for tid in sp.get("tasks", [])}
    cp_ids     = set(summary.get("graph_analytics",{}).get("critical_path",{}).get("task_ids",[]))

    start_date = st.date_input("Project start date", value=date.today())
    sprint_weeks = st.slider("Sprint duration (weeks)", 1, 4, 2)

    if not tasks:
        st.info("No tasks available.")
        return

    sprint_offsets: dict[int, int] = {}
    cum = 0
    for sp in sorted({sprint_map.get(t.get("id",""), 1) for t in tasks}):
        sprint_offsets[sp] = cum
        cum += sprint_weeks * 7

    fig = go.Figure()
    colors = {"FR": "#3b82f6", "NFR": "#f97316"}
    for task in tasks:
        tid   = task.get("id", "")
        sp    = sprint_map.get(tid, 1)
        off   = sprint_offsets.get(sp, 0)
        days  = task.get("estimated_days") or max(1, (task.get("estimated_hours") or 8) // 8)
        t_start = start_date + timedelta(days=off)
        t_end   = t_start + timedelta(days=days)
        bar_color = "#ef4444" if tid in cp_ids else colors.get(task.get("req_type","FR"), "#3b82f6")
        fig.add_trace(go.Bar(
            x=[days], y=[f"{tid}: {task.get('title','')[:35]}"],
            base=[(t_start - date(1970,1,1)).days * 86400000],
            orientation="h",
            marker_color=bar_color,
            marker_line={"width": 2 if tid in cp_ids else 0.5,
                         "color": "#fbbf24" if tid in cp_ids else "#1e293b"},
            hovertemplate=(f"<b>{tid}</b><br>{task.get('title','')}<br>"
                           f"Start: {t_start}<br>End: {t_end}<br>"
                           f"Days: {days}  Hours: {task.get('estimated_hours','?')}"
                           f"{'<br><b>⚠ CRITICAL PATH</b>' if tid in cp_ids else ''}"
                           "<extra></extra>"),
            showlegend=False))

    fig.update_layout(
        title="Gantt Chart — Task Timeline",
        barmode="overlay", height=max(400, 60 + len(tasks)*35),
        xaxis={"type":"date", "title":"Date",
               "tickformat":"%b %d", "gridcolor":"#334155"},
        yaxis={"autorange":"reversed", "tickfont":{"size":10}},
        margin={"l":10,"r":10,"t":60,"b":40},
        **_DARK_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("🔵 FR  🟠 NFR  🔴+border Critical Path")


def render_gantt_tab() -> None:
    data = load_json(TASKS_PATH)
    summary = load_json(SUMMARY_PATH)
    if data is None or summary is None:
        st.info("Run the pipeline first.")
        return

    tasks = data.get("tasks", [])
    sprints = sorted(
        summary.get("sprint_plan", []),
        key=lambda item: int(item.get("sprint", 0) or 0),
    )
    if not tasks:
        st.info("No tasks available.")
        return

    start_date = st.date_input("Project start date", value=date.today())
    cp_ids = set(
        summary.get("graph_analytics", {})
        .get("critical_path", {})
        .get("task_ids", [])
    )

    sprint_offsets: dict[int, int] = {}
    sprint_meta: dict[int, dict[str, Any]] = {}
    sprint_summary_rows: list[dict[str, Any]] = []
    offset_days = 0
    for index, sprint in enumerate(sprints, 1):
        sprint_no = int(sprint.get("sprint", index) or index)
        duration_weeks = int(sprint.get("duration_weeks", 2) or 2)
        duration_days = max(1, duration_weeks * 7)
        sprint_start = start_date + timedelta(days=offset_days)
        sprint_end = sprint_start + timedelta(days=duration_days)
        sprint_offsets[sprint_no] = offset_days
        sprint_meta[sprint_no] = {
            "name": sprint.get("name", f"Sprint {sprint_no}"),
            "duration_weeks": duration_weeks,
            "start": sprint_start,
            "end": sprint_end,
            "hours": sprint.get("total_estimated_hours", 0),
            "roles": ", ".join(sprint.get("owner_roles", []) or ["Unassigned"]),
        }
        sprint_summary_rows.append({
            "sprint": sprint.get("name", f"Sprint {sprint_no}"),
            "start": sprint_start.isoformat(),
            "end": sprint_end.isoformat(),
            "duration_weeks": duration_weeks,
            "tasks": ", ".join(sprint.get("tasks", [])),
            "hours": sprint.get("total_estimated_hours", 0),
            "roles": ", ".join(sprint.get("owner_roles", []) or ["Unassigned"]),
        })
        offset_days += duration_days

    if not sprint_meta:
        sprint_meta[1] = {
            "name": "Sprint 1",
            "duration_weeks": 2,
            "start": start_date,
            "end": start_date + timedelta(days=14),
            "hours": sum(task.get("estimated_hours") or 0 for task in tasks),
            "roles": "Unassigned",
        }
        sprint_offsets[1] = 0

    sprint_map = {
        tid: int(sprint.get("sprint", 1) or 1)
        for sprint in sprints
        for tid in sprint.get("tasks", [])
    }

    rows: list[dict[str, Any]] = []
    for task in tasks:
        tid = str(task.get("id", ""))
        sprint_no = sprint_map.get(tid, 1)
        meta = sprint_meta.get(sprint_no, sprint_meta[1])
        task_start = meta["start"]
        days = int(task.get("estimated_days") or max(1, round((task.get("estimated_hours") or 8) / 8)))
        task_finish = task_start + timedelta(days=max(1, days))
        rows.append({
            "task_id": tid,
            "task": f"{tid}: {task.get('title', '')}",
            "title": task.get("title", ""),
            "start": task_start,
            "finish": task_finish,
            "sprint": meta["name"],
            "sprint_no": sprint_no,
            "hours": task.get("estimated_hours") or 0,
            "role": task.get("suggested_owner_role") or "Unassigned",
            "kind": "Critical Path" if tid in cp_ids else task.get("req_type", "FR"),
        })

    fig = px.timeline(
        rows,
        x_start="start",
        x_end="finish",
        y="task",
        color="kind",
        color_discrete_map={
            "FR": "#3b82f6",
            "NFR": "#f97316",
            "Critical Path": "#ef4444",
        },
        custom_data=["task_id", "title", "sprint", "hours", "role"],
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>%{customdata[1]}<br>"
            "Sprint: %{customdata[2]}<br>"
            "Hours: %{customdata[3]}<br>"
            "Role: %{customdata[4]}<extra></extra>"
        )
    )

    for meta in sprint_meta.values():
        start_x = meta["start"].isoformat()
        end_x = meta["end"].isoformat()
        fig.add_shape(
            type="line",
            x0=start_x,
            x1=start_x,
            y0=0,
            y1=1,
            xref="x",
            yref="paper",
            line={"width": 1, "dash": "dot", "color": "#94a3b8"},
        )
        fig.add_annotation(
            x=start_x,
            y=1.02,
            xref="x",
            yref="paper",
            text=meta["name"],
            showarrow=False,
            font={"color": "#f1f5f9", "size": 10},
            xanchor="left",
        )
        fig.add_shape(
            type="line",
            x0=end_x,
            x1=end_x,
            y0=0,
            y1=1,
            xref="x",
            yref="paper",
            line={"width": 1, "dash": "dash", "color": "#475569"},
        )

    fig.update_layout(
        title="Gantt Chart - Task Timeline",
        height=max(420, 60 + len(rows) * 34),
        xaxis_title="Date",
        yaxis_title="",
        xaxis={"tickformat": "%b %d", "gridcolor": "#334155"},
        yaxis={"autorange": "reversed", "tickfont": {"size": 10}},
        legend_title_text="Track",
        margin={"l":10,"r":10,"t":60,"b":40},
        **_DARK_LAYOUT,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Sprint Summary")
    if sprint_summary_rows:
        st.dataframe(sprint_summary_rows, use_container_width=True, hide_index=True)


def render_risks_tab() -> None:
    report = load_json(RISK_PATH)
    if report is None:
        return
    level = str(report.get("risk_level","unknown"))
    color = risk_color(level)
    st.markdown(f"<h3 style='color:{color}'>Risk: {level.upper()}</h3>",
                unsafe_allow_html=True)
    metric_row([("Risk Score", report.get("risk_score",0)),
                ("Risk Items", report.get("total_risks",0))])
    render_risk_charts(report)
    risks = report.get("risks", [])
    if not risks:
        st.info("No risks found.")
        return
    for r in risks:
        affected = ", ".join(r.get("affected_tasks") or []) or "none"
        with st.expander(f"{r.get('category','?')} | {r.get('severity','?')}"):
            st.write(r.get("message",""))
            st.write(f"**Affected tasks:** {affected}")
            st.write(f"**Mitigation:** {r.get('mitigation','n/a')}")


def render_summary_tab() -> None:
    summary     = load_json(SUMMARY_PATH)
    risk_report = load_json(RISK_PATH)
    if summary is None:
        return

    graph    = summary.get("graph_analytics", {})
    effort   = summary.get("effort_summary", {})
    team     = summary.get("team_allocation", [])
    sprints  = summary.get("sprint_plan", [])
    rl       = str((risk_report or {}).get("risk_level","unknown")).upper()

    metric_row([("Total Hours", effort.get("total_estimated_hours",0)),
                ("Team size", len(team)), ("Sprints", len(sprints)), ("Risk Level", rl)])
    metric_row([("FR", graph.get("fr_count",0)),
                ("NFR", graph.get("nfr_count",0)),
                ("Optional", graph.get("optional_task_count",0))])

    cp = graph.get("critical_path", {})
    st.subheader("Critical Path")
    for i, (tid, title) in enumerate(
            zip(cp.get("task_ids",[]), cp.get("titles",[])), 1):
        st.write(f"{i}. **{tid}** — {title}")

    sprint_rows = [{"sprint": s.get("name",f"Sprint {s.get('sprint','')}"),
                    "tasks": ", ".join(s.get("tasks",[])),
                    "hours": s.get("total_estimated_hours",0)}
                   for s in sprints]
    st.subheader("Sprint Plan")
    if sprint_rows:
        st.dataframe(sprint_rows, use_container_width=True, hide_index=True)
        render_sprint_timeline(sprints)

    # PDF Export
    st.subheader("Export")
    if st.button("Generate PDF Report"):
        try:
            from src.ui.export import generate_pdf_report
            tasks_data   = load_json(TASKS_PATH) or {}
            risk_data    = load_json(RISK_PATH)
            pdf_bytes    = generate_pdf_report(tasks_data, risk_data, summary)
            st.download_button(
                label="Download PDF",
                data=pdf_bytes,
                file_name="project_plan.pdf",
                mime="application/pdf")
        except Exception as exc:
            st.error(f"PDF generation failed: {exc}")


def _render_monitor_tab_basic() -> None:
    st.subheader("Git Progress Monitor")
    repo_path = st.text_input("Git repository path",
                               value=str(DEFAULT_REPO_PATH), key="monitor_repo")
    if st.button("Analyze Progress", key="monitor_run"):
        tasks_data = load_json(TASKS_PATH)
        if tasks_data is None:
            st.warning("Run the pipeline first.")
            return
        try:
            from src.agents.monitor import MonitorAgent
            from src.core.schemas import TaskList
            task_list = TaskList.model_validate(tasks_data)
            agent = MonitorAgent()
            report = agent.track_progress(task_list, repo_path=repo_path)

            st.progress(report.overall_progress,
                        text=f"Overall progress: {report.overall_progress:.0%}")
            metric_row([("Commits Analyzed", report.commits_analyzed),
                        ("Completed", report.tasks_completed),
                        ("In Progress", report.tasks_in_progress),
                        ("Not Started", report.tasks_not_started)])

            if report.behind_schedule:
                st.warning(f"Behind schedule: {', '.join(report.behind_schedule)}")

            status_icon = {"completed":"✅","in_progress":"🔄","not_started":"⬜"}
            rows_m = [{"status": status_icon.get(tp.status, "?"),
                       "task_id": tp.task_id,
                       "title": tp.task_title,
                       "commits": len(tp.matched_commits),
                       "completion": f"{tp.completion_estimate:.0%}"}
                      for tp in report.task_progress]
            st.dataframe(rows_m, use_container_width=True, hide_index=True)

            if report.task_progress:
                prog_vals = [tp.completion_estimate for tp in report.task_progress]
                labels    = [tp.task_id for tp in report.task_progress]
                fig = go.Figure(go.Bar(x=labels, y=prog_vals,
                    marker_color=["#22c55e" if v==1 else "#3b82f6" if v>0 else "#475569"
                                  for v in prog_vals],
                    text=[f"{v:.0%}" for v in prog_vals], textposition="outside"))
                fig.update_layout(title="Per-Task Completion",
                    yaxis={"range":[0,1.1],"tickformat":".0%"},
                    margin={"l":10,"r":10,"t":50,"b":30}, **_DARK_LAYOUT)
                st.plotly_chart(fig, use_container_width=True)

            # Save report
            MONITOR_PATH.parent.mkdir(parents=True, exist_ok=True)
            MONITOR_PATH.write_text(report.model_dump_json(indent=2), encoding="utf-8")
            st.success("Monitor report saved.")
        except Exception as exc:
            st.error(f"Monitor failed: {exc}")

def render_monitor_tab() -> None:
    st.subheader("Git Progress Monitor")
    repo_path = st.text_input("Git repository path",
                               value=str(DEFAULT_REPO_PATH), key="monitor_repo")
    if not st.button("Analyze Progress", key="monitor_run"):
        return

    tasks_data = load_json(TASKS_PATH)
    if tasks_data is None:
        st.warning("Run the pipeline first.")
        return

    try:
        import subprocess

        from src.agents.monitor import MonitorAgent
        from src.core.schemas import TaskList

        task_list = TaskList.model_validate(tasks_data)
        tasks_by_id = {task.id: task for task in task_list.tasks}
        agent = MonitorAgent()
        report = agent.track_progress(task_list, repo_path=repo_path)

        MONITOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        MONITOR_PATH.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        progress_pct = int(round(report.overall_progress * 100))
        progress_color = (
            "#22c55e" if report.overall_progress >= 0.75
            else "#f97316" if report.overall_progress >= 0.45
            else "#ef4444"
        )
        st.markdown(
            f"""
            <div style="margin:0.5rem 0 1rem 0;">
              <div style="display:flex;justify-content:space-between;margin-bottom:0.35rem;">
                <span style="font-weight:700;color:#f1f5f9;">Overall Progress</span>
                <span style="font-weight:700;color:{progress_color};">{progress_pct}%</span>
              </div>
              <div style="height:22px;background:#1e293b;border-radius:999px;overflow:hidden;border:1px solid #334155;">
                <div style="height:100%;width:{progress_pct}%;background:{progress_color};"></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        metric_row([("Commits Analyzed", report.commits_analyzed),
                    ("Completed", report.tasks_completed),
                    ("In Progress", report.tasks_in_progress),
                    ("Not Started", report.tasks_not_started)])

        if report.behind_schedule:
            st.warning(f"Behind schedule: {', '.join(report.behind_schedule)}")

        status_colors = {
            "completed": "#22c55e",
            "in_progress": "#3b82f6",
            "not_started": "#64748b",
        }
        rows_m = [{"status": tp.status,
                   "task_id": tp.task_id,
                   "title": tp.task_title,
                   "commits": len(tp.matched_commits),
                   "completion": f"{tp.completion_estimate:.0%}"}
                  for tp in report.task_progress]
        st.dataframe(rows_m, use_container_width=True, hide_index=True)

        sha_to_tasks: dict[str, list[str]] = defaultdict(list)
        task_status: dict[str, str] = {}
        for tp in report.task_progress:
            task_status[tp.task_id] = tp.status
            for sha in tp.matched_commits:
                sha_to_tasks[sha].append(tp.task_id)

        commit_rows: list[dict[str, str]] = []
        git_log = subprocess.run(
            ["git", "log", "--format=%H|||%h|||%s|||%an|||%ae|||%ci", "-n", "200"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if git_log.returncode == 0:
            for line in git_log.stdout.splitlines():
                parts = line.split("|||")
                if len(parts) < 6:
                    continue
                sha, short_sha, message, author, email, date_text = parts[:6]
                badges = []
                for task_id in sorted(set(sha_to_tasks.get(sha, []))):
                    color = status_colors.get(task_status.get(task_id, ""), "#64748b")
                    badges.append(
                        f"<span style='display:inline-block;background:{color};color:white;"
                        f"border-radius:999px;padding:2px 8px;margin:1px;font-size:0.75rem;'>{task_id}</span>"
                    )
                commit_rows.append({
                    "sha": html.escape(short_sha),
                    "message": html.escape(message),
                    "author": html.escape(author or email),
                    "date": html.escape(date_text[:19]),
                    "badges": "".join(badges) or "<span style='color:#94a3b8;'>unmatched</span>",
                })

        if commit_rows:
            st.subheader("Commit Evidence")
            rows_html = "\n".join(
                "<tr>"
                f"<td style='padding:8px;border-bottom:1px solid #334155;'><code>{row['sha']}</code></td>"
                f"<td style='padding:8px;border-bottom:1px solid #334155;'>{row['message']}</td>"
                f"<td style='padding:8px;border-bottom:1px solid #334155;'>{row['author']}</td>"
                f"<td style='padding:8px;border-bottom:1px solid #334155;'>{row['date']}</td>"
                f"<td style='padding:8px;border-bottom:1px solid #334155;'>{row['badges']}</td>"
                "</tr>"
                for row in commit_rows
            )
            st.markdown(
                f"""
                <div style="max-height:420px;overflow:auto;border:1px solid #334155;border-radius:8px;">
                  <table style="width:100%;border-collapse:collapse;font-size:0.9rem;">
                    <thead style="position:sticky;top:0;background:#0f172a;">
                      <tr>
                        <th style="text-align:left;padding:8px;border-bottom:1px solid #334155;">SHA</th>
                        <th style="text-align:left;padding:8px;border-bottom:1px solid #334155;">Message</th>
                        <th style="text-align:left;padding:8px;border-bottom:1px solid #334155;">Author</th>
                        <th style="text-align:left;padding:8px;border-bottom:1px solid #334155;">Date</th>
                        <th style="text-align:left;padding:8px;border-bottom:1px solid #334155;">Tasks</th>
                      </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                  </table>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.subheader("Task Progress")
        cards = st.columns(3)
        for idx, tp in enumerate(report.task_progress):
            color = status_colors.get(tp.status, "#64748b")
            task = tasks_by_id.get(tp.task_id)
            skill = task.skill_required if task else "unknown"
            hours = task.estimated_hours if task else "n/a"
            width = int(round(tp.completion_estimate * 100))
            with cards[idx % 3]:
                st.markdown(
                    f"""
                    <div style="border:1px solid #334155;border-radius:8px;padding:12px;margin-bottom:10px;background:#1e293b;">
                      <div style="display:flex;justify-content:space-between;gap:8px;">
                        <strong style="color:#f1f5f9;">{html.escape(tp.task_id)}</strong>
                        <span style="color:{color};font-weight:700;">{html.escape(tp.status.replace('_', ' '))}</span>
                      </div>
                      <div style="min-height:44px;color:#cbd5e1;margin:8px 0;">{html.escape(tp.task_title)}</div>
                      <div style="height:8px;background:#0f172a;border-radius:999px;overflow:hidden;">
                        <div style="height:100%;width:{width}%;background:{color};"></div>
                      </div>
                      <div style="display:flex;justify-content:space-between;margin-top:8px;color:#94a3b8;font-size:0.8rem;">
                        <span>{html.escape(str(skill or 'unknown'))}</span>
                        <span>{html.escape(str(hours))}h</span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if report.task_progress:
            prog_vals = [tp.completion_estimate for tp in report.task_progress]
            labels = [tp.task_id for tp in report.task_progress]
            fig = go.Figure(go.Bar(
                x=labels,
                y=prog_vals,
                marker_color=[status_colors.get(tp.status, "#64748b") for tp in report.task_progress],
                text=[f"{value:.0%}" for value in prog_vals],
                textposition="outside",
            ))
            fig.update_layout(title="Per-Task Completion",
                yaxis={"range":[0,1.1],"tickformat":".0%"},
                margin={"l":10,"r":10,"t":50,"b":30}, **_DARK_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)

            skills = sorted({
                (tasks_by_id.get(tp.task_id).skill_required if tasks_by_id.get(tp.task_id) else "unknown") or "unknown"
                for tp in report.task_progress
            })
            fig_skill = go.Figure()
            for status in ("completed", "in_progress", "not_started"):
                fig_skill.add_trace(go.Bar(
                    name=status.replace("_", " ").title(),
                    x=skills,
                    y=[
                        sum(
                            1 for tp in report.task_progress
                            if tp.status == status
                            and ((tasks_by_id.get(tp.task_id).skill_required if tasks_by_id.get(tp.task_id) else "unknown") or "unknown") == skill
                        )
                        for skill in skills
                    ],
                    marker_color=status_colors[status],
                ))
            fig_skill.update_layout(title="Skill Breakdown by Status",
                barmode="stack", yaxis_title="Tasks",
                margin={"l":10,"r":10,"t":50,"b":30}, **_DARK_LAYOUT)
            st.plotly_chart(fig_skill, use_container_width=True)

        st.success("Monitor report saved.")
    except Exception as exc:
        st.error(f"Monitor failed: {exc}")


def render_run_pipeline_tab() -> None:
    if "pipeline_requirements" not in st.session_state:
        st.session_state["pipeline_requirements"] = _load_pipeline_input_text()

    req_text = st.text_area("Project Requirements", height=200,
        key="pipeline_requirements",
        placeholder="Paste your project requirements here...")
    c1, c2 = st.columns(2)
    with c1:
        fmt    = st.selectbox("Input Format", ["brief","template"])
    with c2:
        use_kb = st.checkbox("Use Knowledge Base (RAG)", value=True)

    if not st.button("Generate Plan"):
        history = _load_run_history()
        if history:
            with st.expander("Run History (last 10 runs)"):
                hist_rows = [{"time": r.get("timestamp",""), "tasks": r.get("task_count","?"),
                              "critic": r.get("critic_score","?"),
                              "risk": r.get("risk_level","?"),
                              "elapsed_s": r.get("elapsed_seconds","?")}
                             for r in history]
                st.dataframe(hist_rows, use_container_width=True, hide_index=True)
        return

    if not req_text.strip():
        st.error("Requirements cannot be empty.")
        return

    log_placeholder = st.empty()
    captured_lines: list[str] = []

    try:
        from src.pipelines.doc_to_tasks import run_doc_to_tasks_pipeline
        from src.ui.log_capture import LogCapture

        TEMP_INPUT.parent.mkdir(parents=True, exist_ok=True)
        TEMP_INPUT.write_text(req_text.strip(), encoding="utf-8")

        started = time.perf_counter()
        with LogCapture() as lc:
            run_doc_to_tasks_pipeline(
                input_path=TEMP_INPUT,
                input_format=fmt,
                force_fallback=False,
                allow_fallback=True,
                use_kb=use_kb,
            )
            captured_lines = lc.drain()
        elapsed = time.perf_counter() - started

        log_placeholder.code("\n".join(captured_lines[-40:]), language="text")

        tasks_data  = load_json(TASKS_PATH) or {}
        summary     = load_json(SUMMARY_PATH) or {}
        risk_report = load_json(RISK_PATH) or {}
        tasks       = tasks_data.get("tasks", [])
        rows        = task_rows(tasks)
        critic_score = summary.get("critic",{}).get("score","n/a")
        risk_level   = risk_report.get("risk_level","unknown")

        st.success(f"✓ Generated {len(rows)} tasks in {elapsed:.1f}s")
        metric_row([("Tasks", len(rows)), ("Critic Score", critic_score),
                    ("Risk Level", str(risk_level).upper())])
        st.dataframe(rows, use_container_width=True, hide_index=True)

        _append_run_history({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "input_snippet": req_text.strip()[:200],
            "task_count": len(rows),
            "critic_score": critic_score,
            "risk_level": risk_level,
            "elapsed_seconds": round(elapsed, 2),
        })

        if st.button("Refresh Dashboard"):
            st.rerun()

    except SystemExit as exc:
        st.error(f"Pipeline rejected plan: {exc}")
    except Exception as exc:
        st.error(f"Pipeline failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def render_communication_tab() -> None:
    from streamlit_autorefresh import st_autorefresh

    from src.ui.communication import (
        approve_plan,
        get_messages,
        get_plan_status,
        reject_plan,
        send_message,
    )

    role = st.session_state.get("comm_role", "Student")
    st_autorefresh(interval=10000, key="comm_refresh")

    status = get_plan_status()
    status_color = {
        "approved": "#22c55e",
        "rejected": "#ef4444",
        "pending": "#f97316",
    }.get(status, "#94a3b8")
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;
                    border:1px solid #334155;border-radius:8px;padding:12px;background:#1e293b;margin-bottom:12px;">
          <div>
            <div style="color:#94a3b8;font-size:0.8rem;">Collaboration Room</div>
            <div style="color:#f1f5f9;font-weight:800;">Student / Supervisor Plan Review</div>
          </div>
          <div style="background:{status_color};color:white;border-radius:999px;padding:6px 12px;font-weight:800;">
            {html.escape(status.upper())}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    messages = get_messages()
    st.subheader("Messages")
    if not messages:
        st.info("No messages yet.")
    else:
        wall_html = []
        for message in messages[-80:]:
            msg_role = str(message.get("role", "Student"))
            msg_type = str(message.get("type", "message"))
            bg = "#1d4ed8" if msg_role == "Supervisor" else "#15803d"
            if msg_type == "approval":
                bg = "#16a34a"
            elif msg_type == "rejection":
                bg = "#dc2626"
            align = "flex-end" if msg_role == "Supervisor" else "flex-start"
            created = str(message.get("created_at", ""))[:19].replace("T", " ")
            wall_html.append(
                f"""
                <div style="display:flex;justify-content:{align};margin:8px 0;">
                  <div style="max-width:72%;background:{bg};color:white;border-radius:10px;padding:10px 12px;">
                    <div style="font-size:0.78rem;opacity:0.85;font-weight:700;">
                      {html.escape(msg_role)} | {html.escape(msg_type)} | {html.escape(created)}
                    </div>
                    <div style="margin-top:4px;white-space:pre-wrap;">{html.escape(str(message.get("text", "")))}</div>
                  </div>
                </div>
                """
            )
        st.markdown(
            f"""
            <div style="max-height:520px;overflow:auto;border:1px solid #334155;border-radius:8px;
                        padding:10px;background:#020617;">
              {''.join(wall_html)}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.subheader("Send")
    if role == "Student":
        with st.form("student_message_form", clear_on_submit=True):
            text = st.text_area("Question", height=110,
                                placeholder="Ask your supervisor about scope, risks, timeline, or task details...")
            submitted = st.form_submit_button("Send Question")
            if submitted:
                try:
                    send_message("Student", text)
                    st.success("Question sent.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    else:
        with st.form("supervisor_message_form", clear_on_submit=True):
            comment = st.text_area("Supervisor Comment", height=110,
                                   placeholder="Write feedback, approval notes, or requested changes...")
            c1, c2, c3 = st.columns(3)
            send = c1.form_submit_button("Send Comment")
            approve = c2.form_submit_button("Approve Plan")
            reject = c3.form_submit_button("Reject Plan")
            try:
                if send:
                    send_message("Supervisor", comment)
                    st.success("Comment sent.")
                    st.rerun()
                if approve:
                    approve_plan("Supervisor", comment)
                    st.success("Plan approved.")
                    st.rerun()
                if reject:
                    reject_plan("Supervisor", comment)
                    st.success("Plan rejected.")
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def main() -> None:
    st.set_page_config(page_title="AI Project Manager", layout="wide",
                       page_icon="🧠")
    st.title("🧠 AI Project Manager")
    st.caption("CritiPlan — Multi-Agent Requirements Engineering Framework")

    role = st.sidebar.selectbox("Role", ["Student", "Supervisor"], key="comm_role")
    render_hero_banner(role)

    tabs = st.tabs(["Tasks", "Dependency Graph", "Gantt", "Risks",
                    "Summary", "Monitor", "Communication", "Run Pipeline"])

    with tabs[0]: render_tasks_tab()
    with tabs[1]: render_graph_tab()
    with tabs[2]: render_gantt_tab()
    with tabs[3]: render_risks_tab()
    with tabs[4]: render_summary_tab()
    with tabs[5]: render_monitor_tab()
    with tabs[6]: render_communication_tab()
    with tabs[7]: render_run_pipeline_tab()


if __name__ == "__main__":
    main()
