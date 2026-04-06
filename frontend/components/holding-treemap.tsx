"use client";
import { Treemap, ResponsiveContainer } from "recharts";
import type { HoldingItem } from "@/lib/types";

function cellColor(pnlPct: number): string {
  if (pnlPct >= 10) return "#166534";
  if (pnlPct >= 0) return "#15803d";
  if (pnlPct >= -10) return "#991b1b";
  return "#7f1d1d";
}

function textColor(pnlPct: number): string {
  return pnlPct >= 0 ? "#86efac" : "#fca5a5";
}

function CustomContent(props: {
  x?: number; y?: number; width?: number; height?: number;
  name?: string; pnl_pct?: number;
}) {
  const { x = 0, y = 0, width = 0, height = 0, name = "", pnl_pct = 0 } = props;
  const bg = cellColor(pnl_pct);
  const fg = textColor(pnl_pct);
  const label = name.length > 12 ? name.substring(0, 12) + "…" : name;
  const sign = pnl_pct >= 0 ? "+" : "";
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={bg} stroke="#0f1117" strokeWidth={2} rx={4} />
      {width > 50 && height > 30 && (
        <>
          <text x={x + width / 2} y={y + height / 2 - 7} textAnchor="middle" fill={fg} fontSize={11} fontWeight={600}>
            {label}
          </text>
          <text x={x + width / 2} y={y + height / 2 + 9} textAnchor="middle" fill={fg} fontSize={10}>
            {sign}{pnl_pct.toFixed(1)}%
          </text>
        </>
      )}
    </g>
  );
}

export function HoldingTreemap({ holdings }: { holdings: HoldingItem[] }) {
  const data = holdings
    .filter((h) => (h.current_value ?? 0) > 0)
    .map((h) => ({
      name: h.security_name,
      size: h.current_value ?? 0,
      pnl_pct: h.total_cost > 0
        ? (((h.current_value ?? 0) - h.total_cost) / h.total_cost) * 100
        : 0,
    }));

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[280px] bg-slate-900 rounded-xl border border-slate-800 text-slate-500 text-sm mb-6">
        No holdings with current prices
      </div>
    );
  }

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden mb-6">
      <div className="px-4 py-2.5 border-b border-slate-800 flex items-center gap-4">
        <span className="text-xs text-slate-500 uppercase tracking-wider font-medium">Heatmap</span>
        <span className="text-xs text-slate-600">size = value · colour = unrealized P&amp;L</span>
        <span className="ml-auto flex gap-3 text-[10px] text-slate-500">
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-green-800 inline-block" />+10%+</span>
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-green-700 inline-block" />0–10%</span>
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-red-800 inline-block" />0–10% loss</span>
          <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-red-900 inline-block" />10%+ loss</span>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <Treemap
          data={data}
          dataKey="size"
          content={<CustomContent />}
        />
      </ResponsiveContainer>
    </div>
  );
}
