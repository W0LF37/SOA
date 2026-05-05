import React, { useEffect, useMemo, useState } from "react";
import { Network } from "lucide-react";
import {
  ReactFlow as ReactFlowBase,
  Background, Controls, MiniMap,
  type Node, type Edge, useNodesState, useEdgesState,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useAppStore } from "../lib/store";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ReactFlow = ReactFlowBase as unknown as React.ComponentType<any>;

function TaskNode({ data }: { data: Record<string, unknown> }) {
  const isCritical = Boolean(data.is_critical);
  const reqType = data.req_type as string;
  const bg = isCritical ? "#3b0000" : reqType === "NFR" ? "#2d1200" : "#001a3b";
  const border = isCritical ? "#ef4444" : reqType === "NFR" ? "#f97316" : "#3b82f6";

  return (
    <div style={{
      background: bg,
      border: `2px solid ${border}`,
      borderRadius: 10,
      padding: "10px 14px",
      minWidth: 220,
      maxWidth: 260,
      fontSize: 12,
      color: "#f1f5f9",
      boxShadow: isCritical ? "0 0 16px rgba(239,68,68,0.35)" : "0 4px 12px rgba(0,0,0,0.4)",
    }}>
      <div style={{ fontWeight: 800, fontSize: 11, color: border, marginBottom: 3 }}>
        {String(data.id ?? "")}{isCritical ? " ⚡" : ""}
      </div>
      <div style={{ fontWeight: 600, lineHeight: 1.3, marginBottom: 6 }}>
        {(String(data.title ?? "")).slice(0, 55)}{(String(data.title ?? "")).length > 55 ? "..." : ""}
      </div>
      <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
        {[reqType, `C${data.complexity}`, `${data.estimated_hours ?? "?"}h`].map(tag => (
          <span key={tag} style={{
            background: "rgba(255,255,255,0.08)",
            borderRadius: 4, padding: "1px 6px", fontSize: 10,
          }}>{tag}</span>
        ))}
      </div>
      <div style={{ fontSize: 10, color: "#64748b", marginTop: 4 }}>
        👤 {String(data.suggested_owner_role ?? "—")}
      </div>
    </div>
  );
}

const nodeTypes = { task: TaskNode };

export default function GraphPage() {
  const data = useAppStore(s => s.data);
  const [filter, setFilter] = useState<"all"|"critical"|"FR"|"NFR">("all");

  const { initialNodes, initialEdges } = useMemo(() => {
    const tasks = data?.tasks?.tasks ?? [];
    const cpIds = new Set<string>(data?.summary?.graph_analytics?.critical_path?.task_ids ?? []);
    const COL_W = 320;
    const ROW_H = 160;

    const placed = new Set<string>();
    const cols: string[][] = [];
    while (placed.size < tasks.length) {
      const col = tasks.filter(
        t => !placed.has(t.id ?? "") && (t.dependencies ?? []).every(d => placed.has(d))
      );
      if (!col.length) break;
      cols.push(col.map(t => t.id ?? ""));
      col.forEach(t => placed.add(t.id ?? ""));
    }

    const initialNodes: Node[] = tasks.map(t => {
      const colIdx = cols.findIndex(c => c.includes(t.id ?? ""));
      const rowIdx = colIdx >= 0 ? cols[colIdx].indexOf(t.id ?? "") : 0;
      const maxColHeight = Math.max(1, ...cols.map(c => c.length)) * ROW_H;
      const colHeight = (cols[colIdx]?.length ?? 1) * ROW_H;
      const startY = (maxColHeight - colHeight) / 2;
      return {
        id: t.id ?? "",
        type: "task",
        position: {
          x: Math.max(0, colIdx) * COL_W + 60,
          y: startY + rowIdx * ROW_H + 60,
        },
        data: { ...t, is_critical: cpIds.has(t.id ?? "") },
      };
    });

    const initialEdges: Edge[] = [];
    for (const t of tasks) {
      for (const dep of t.dependencies ?? []) {
        const isCp = cpIds.has(t.id ?? "") && cpIds.has(dep);
        initialEdges.push({
          id: `${dep}-${t.id}`,
          source: dep,
          target: t.id ?? "",
          animated: isCp,
          style: { stroke: isCp ? "#ef4444" : "#94a3b8", strokeWidth: isCp ? 2.5 : 2 },
          markerEnd: isCp ? "url(#task-graph-arrow-critical)" : "url(#task-graph-arrow-default)",
        });
      }
    }

    return { initialNodes, initialEdges };
  }, [data]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => {
    setNodes(initialNodes);
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, setEdges, setNodes]);

  const visibleNodeIds = new Set(
    initialNodes
      .filter(n => {
        if (filter === "critical") return (n.data as any).is_critical;
        if (filter === "FR") return (n.data as any).req_type === "FR";
        if (filter === "NFR") return (n.data as any).req_type === "NFR";
        return true;
      })
      .map(n => n.id)
  );
  const filteredNodes = nodes.filter(n => visibleNodeIds.has(n.id));
  const filteredEdges = edges.filter(e => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target));

  if (!data?.tasks?.tasks?.length) {
    return (
      <div style={{ padding: 60, textAlign: "center", color: "#475569" }}>
        <Network size={48} style={{ margin: "0 auto 16px", opacity: 0.4 }} />
        <p style={{ fontSize: 16 }}>Run the pipeline first to see the dependency graph.</p>
      </div>
    );
  }

  return (
    <div className="fade-up">
      <h1 className="page-title"><Network size={22} /> Dependency Graph</h1>
      <p className="page-sub">Task dependencies and critical path - drag nodes to rearrange</p>

      <div style={{ display: "flex", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        {[
          { color: "#3b82f6", label: "Functional (FR)" },
          { color: "#f97316", label: "Non-Functional (NFR)" },
          { color: "#ef4444", label: "Critical Path ⚡" },
        ].map(({ color, label }) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <div style={{ width: 12, height: 12, borderRadius: 3, background: color }} />
            <span style={{ color: "#94a3b8" }}>{label}</span>
          </div>
        ))}
      </div>

      <div style={{ display:"flex", gap:8, marginBottom:12, alignItems:"center" }}>
        {(["all","critical","FR","NFR"] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{
            padding: "5px 14px", borderRadius: 20, fontSize: 12, cursor: "pointer", border: "none",
            background: filter===f ? "#3b82f6" : "#1e293b",
            color: filter===f ? "#fff" : "#94a3b8",
          }}>
            {f === "critical" ? "⚡ Critical" : f === "all" ? "All" : f}
          </button>
        ))}
        <span style={{ color:"#475569", fontSize:12 }}>{filteredNodes.length} tasks</span>
      </div>

      <div style={{ height: 620, borderRadius: 14, overflow: "hidden", border: "1px solid #1e293b" }}>
        <ReactFlow
          nodes={filteredNodes}
          edges={filteredEdges}
          defaultEdgeOptions={{
            markerEnd: "url(#task-graph-arrow-default)",
            style: { strokeWidth: 2, stroke: "#94a3b8" },
          }}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          style={{ background: "#080d1a" }}
        >
          <svg width="0" height="0" style={{ position: "absolute" }}>
            <defs>
              <marker
                id="task-graph-arrow-default"
                viewBox="0 0 16 16"
                refX="13"
                refY="8"
                markerWidth="16"
                markerHeight="16"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M2 2 L14 8 L2 14 Z" fill="#94a3b8" />
              </marker>
              <marker
                id="task-graph-arrow-critical"
                viewBox="0 0 16 16"
                refX="13"
                refY="8"
                markerWidth="16"
                markerHeight="16"
                orient="auto"
                markerUnits="strokeWidth"
              >
                <path d="M2 2 L14 8 L2 14 Z" fill="#ef4444" />
              </marker>
            </defs>
          </svg>
          <Background variant={BackgroundVariant.Dots} color="#1e293b" gap={20} size={1} />
          <Controls style={{ background: "#1e293b", border: "1px solid #334155" }} />
          <MiniMap
            nodeColor={n => (n.data as any).is_critical ? "#ef4444"
              : (n.data as any).req_type === "NFR" ? "#f97316" : "#3b82f6"}
            style={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 10 }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
