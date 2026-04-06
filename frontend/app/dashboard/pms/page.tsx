"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { HoldingTreemap } from "@/components/holding-treemap";
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

function pnlClass(n: number | null): string {
  if (n == null) return "text-slate-400";
  return n >= 0 ? "text-emerald-400" : "text-red-400";
}

function HoldingsTable({ holdings }: { holdings: HoldingItem[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800">
      <table className="w-full text-xs text-slate-300">
        <thead>
          <tr className="bg-slate-900 text-slate-500 uppercase tracking-widest">
            {["Security", "Sector", "Qty", "Avg Cost", "LTP", "Value", "P&L", "Day %"].map((h) => (
              <th key={h} className="px-3 py-2.5 text-left font-medium text-[10px]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {holdings.map((h) => {
            const pnl = h.unrealized_pnl ?? 0;
            const pnlPct = h.total_cost > 0 ? (pnl / h.total_cost) * 100 : 0;
            const dayChg = h.day_change_pct;
            return (
              <tr key={`${h.portfolio_id}-${h.identifier}`} className="border-t border-slate-800 hover:bg-slate-800/40 transition-colors">
                <td className="px-3 py-2 font-medium text-slate-200">{h.security_name}</td>
                <td className="px-3 py-2 text-slate-500">{h.sector ?? "—"}</td>
                <td className="px-3 py-2 text-slate-400">{h.quantity.toLocaleString("en-IN")}</td>
                <td className="px-3 py-2 text-slate-400">₹{h.avg_cost_per_unit.toLocaleString("en-IN")}</td>
                <td className="px-3 py-2">{h.current_price != null ? `₹${h.current_price.toLocaleString("en-IN")}` : <span className="text-slate-600">—</span>}</td>
                <td className="px-3 py-2 font-medium">{h.current_value != null ? fmt(h.current_value) : <span className="text-slate-600">—</span>}</td>
                <td className={`px-3 py-2 font-medium ${pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {pnl >= 0 ? "+" : ""}{pnlPct.toFixed(1)}%
                </td>
                <td className={`px-3 py-2 font-medium ${dayChg != null ? pnlClass(dayChg) : "text-slate-600"}`}>
                  {dayChg != null ? `${dayChg >= 0 ? "+" : ""}${dayChg.toFixed(2)}%` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function PMSPage() {
  const [holdings, setHoldings] = useState<HoldingItem[]>([]);
  const [providerNames, setProviderNames] = useState<Record<string, string>>({});
  const [xirr, setXirr] = useState<number | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      apiFetch<HoldingItem[]>("/dashboard/holdings/pms"),
      apiFetch<SummaryResponse>("/dashboard/summary"),
    ])
      .then(([h, s]) => {
        setHoldings(h);
        const pmsPortfolios = s.entities.flatMap((e) => e.portfolios.filter((p) => p.portfolio_type === "pms"));
        setXirr(pmsPortfolios.find((p) => p.xirr != null)?.xirr ?? null);
        const names: Record<string, string> = {};
        pmsPortfolios.forEach((p) => { names[p.portfolio_id] = p.provider_name; });
        setProviderNames(names);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const totalValue = holdings.reduce((s, h) => s + (h.current_value ?? 0), 0);
  const totalCost = holdings.reduce((s, h) => s + h.total_cost, 0);
  const totalUnrealPnl = holdings.reduce((s, h) => s + (h.unrealized_pnl ?? 0), 0);

  // Group by portfolio_id
  const byPortfolio: Record<string, HoldingItem[]> = {};
  holdings.forEach((h) => {
    if (!byPortfolio[h.portfolio_id]) byPortfolio[h.portfolio_id] = [];
    byPortfolio[h.portfolio_id].push(h);
  });

  if (error) return <div className="text-red-400 text-sm">{error}</div>;

  return (
    <div>
      <h1 className="text-base font-bold text-slate-200 mb-5 tracking-tight">PMS Intelligence</h1>
      <StatStrip items={[
        { label: "Current Value", value: fmt(totalValue) },
        { label: "Invested", value: fmt(totalCost) },
        { label: "Unrealized P&L", value: fmt(totalUnrealPnl), valueClass: pnlClass(totalUnrealPnl) },
        { label: "XIRR", value: xirr != null ? `${(xirr * 100).toFixed(1)}%` : "—", valueClass: pnlClass(xirr) },
      ]} />
      <HoldingTreemap holdings={holdings} />
      {Object.entries(byPortfolio).map(([portfolioId, items]) => (
        <div key={portfolioId} className="mb-6">
          <div className="text-[11px] font-semibold text-indigo-400 uppercase tracking-widest mb-2 px-1">
            {providerNames[portfolioId] ?? "Portfolio"}
          </div>
          <HoldingsTable holdings={items} />
          <div className="flex justify-end text-[11px] text-slate-500 mt-1.5 px-1">
            Subtotal: <span className="ml-1 font-medium text-slate-400">{fmt(items.reduce((s, h) => s + (h.current_value ?? 0), 0))}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
