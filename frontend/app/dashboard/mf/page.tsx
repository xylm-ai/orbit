"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { StatStrip } from "@/components/stat-strip";
import type { HoldingItem, SummaryResponse } from "@/lib/types";

function fmt(n: number | null | undefined): string {
  if (n == null) return "—";
  const abs = Math.abs(n);
  const sign = n < 0 ? "-" : "";
  if (abs >= 1e7) return `${sign}₹${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}₹${(abs / 1e5).toFixed(2)}L`;
  return `${sign}₹${abs.toLocaleString("en-IN")}`;
}

export default function MFPage() {
  const [holdings, setHoldings] = useState<HoldingItem[]>([]);
  const [xirr, setXirr] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiFetch<HoldingItem[]>("/dashboard/holdings/mf"),
      apiFetch<SummaryResponse>("/dashboard/summary"),
    ])
      .then(([h, s]) => {
        setHoldings(h);
        const mf = s.entities.flatMap((e) => e.portfolios.filter((p) => p.portfolio_type === "mf"));
        setXirr(mf.find((p) => p.xirr != null)?.xirr ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const totalNav = holdings.reduce((s, h) => s + (h.current_value ?? 0), 0);
  const totalInvested = holdings.reduce((s, h) => s + h.total_cost, 0);
  const totalUnrealPnl = holdings.reduce((s, h) => s + (h.unrealized_pnl ?? 0), 0);
  const pnlPct = totalInvested > 0 ? (totalUnrealPnl / totalInvested) * 100 : 0;

  if (error) return <div className="text-red-400 text-sm">{error}</div>;

  return (
    <div>
      <h1 className="text-base font-bold text-slate-200 mb-5 tracking-tight">Mutual Funds</h1>
      <StatStrip items={[
        { label: "NAV Value", value: fmt(totalNav) },
        { label: "Invested", value: fmt(totalInvested) },
        {
          label: "Unrealized P&L",
          value: `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(1)}%`,
          sub: fmt(totalUnrealPnl),
          valueClass: totalUnrealPnl >= 0 ? "text-emerald-400" : "text-red-400",
        },
        {
          label: "XIRR",
          value: xirr != null ? `${(xirr * 100).toFixed(1)}%` : "—",
          valueClass: xirr != null && xirr >= 0 ? "text-emerald-400" : "text-red-400",
        },
      ]} />
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-xs text-slate-300">
          <thead>
            <tr className="bg-slate-900 text-slate-500 uppercase tracking-widest">
              {["Scheme Name", "Units", "NAV", "Current Value", "Invested", "P&L", "P&L %"].map((h) => (
                <th key={h} className="px-3 py-2.5 text-left font-medium text-[10px]">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => {
              const pnl = h.unrealized_pnl ?? 0;
              const pct = h.total_cost > 0 ? (pnl / h.total_cost) * 100 : 0;
              return (
                <tr key={`${h.portfolio_id}-${h.identifier}`} className="border-t border-slate-800 hover:bg-slate-800/40 transition-colors">
                  <td className="px-3 py-2 font-medium text-slate-200">{h.security_name}</td>
                  <td className="px-3 py-2 text-slate-400">{h.quantity.toFixed(3)}</td>
                  <td className="px-3 py-2 text-slate-400">{h.current_price != null ? `₹${h.current_price.toFixed(2)}` : <span className="text-slate-600">—</span>}</td>
                  <td className="px-3 py-2 font-medium">{h.current_value != null ? fmt(h.current_value) : <span className="text-slate-600">—</span>}</td>
                  <td className="px-3 py-2 text-slate-400">{fmt(h.total_cost)}</td>
                  <td className={`px-3 py-2 font-medium ${pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>{fmt(pnl)}</td>
                  <td className={`px-3 py-2 font-medium ${pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                    {pct >= 0 ? "+" : ""}{pct.toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
