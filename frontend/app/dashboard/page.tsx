"use client";
import { useEffect, useState, useRef, useCallback } from "react";
import { apiFetch, createPriceFeed } from "@/lib/api";
import type { SummaryResponse, HoldingItem, AlertItem } from "@/lib/types";

function fmt(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

function pnlClass(n: number) {
  return n >= 0 ? "text-emerald-400" : "text-red-400";
}

export default function OverviewPage() {
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [allHoldings, setAllHoldings] = useState<HoldingItem[]>([]);
  const [alertCount, setAlertCount] = useState(0);
  const [lastUpdate, setLastUpdate] = useState<string | null>(null);
  const [error, setError] = useState("");
  const wsRef = useRef<WebSocket | null>(null);
  const throttleRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [s, eq, pms, al] = await Promise.all([
        apiFetch<SummaryResponse>("/dashboard/summary"),
        apiFetch<HoldingItem[]>("/dashboard/holdings/equity"),
        apiFetch<HoldingItem[]>("/dashboard/holdings/pms"),
        apiFetch<AlertItem[]>("/dashboard/alerts"),
      ]);
      setSummary(s);
      setAllHoldings([...eq, ...pms]);
      setAlertCount(al.length);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    fetchData();
    const token = localStorage.getItem("orbit_token");
    if (token) {
      const ws = createPriceFeed(token);
      wsRef.current = ws;
      ws.onmessage = () => {
        setLastUpdate(new Date().toLocaleTimeString("en-IN", { timeStyle: "short" }));
        if (!throttleRef.current) {
          throttleRef.current = setTimeout(() => {
            fetchData();
            throttleRef.current = null;
          }, 30_000);
        }
      };
      ws.onerror = () => ws.close();
    }
    return () => {
      wsRef.current?.close();
      if (throttleRef.current) clearTimeout(throttleRef.current);
    };
  }, [fetchData]);

  const movers = [...allHoldings]
    .filter((h) => h.day_change_pct !== null)
    .sort((a, b) => Math.abs(b.day_change_pct!) - Math.abs(a.day_change_pct!))
    .slice(0, 5);

  if (error) return <div className="text-red-400 text-sm p-2">{error}</div>;
  if (!summary) return <div className="text-slate-500 text-sm animate-pulse p-2">Loading…</div>;

  const allPortfolios = summary.entities.flatMap((e) => e.portfolios);
  const pnl = summary.total_unrealized_pnl;
  const xirr = allPortfolios.find((p) => p.xirr != null)?.xirr ?? null;
  const pmsValue = allPortfolios.filter((p) => p.portfolio_type === "pms").reduce((s, p) => s + p.current_value, 0);
  const eqValue = allPortfolios.filter((p) => p.portfolio_type === "equity").reduce((s, p) => s + p.current_value, 0);
  const mfValue = allPortfolios.filter((p) => p.portfolio_type === "mf").reduce((s, p) => s + p.current_value, 0);

  return (
    <div>
      {/* Hero Banner */}
      <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-2xl border border-slate-700 p-6 mb-6 flex justify-between items-start">
        <div>
          <div className="text-[11px] text-slate-500 uppercase tracking-widest mb-1 font-medium">Family Net Worth</div>
          <div className="text-4xl font-extrabold text-slate-100 tracking-tight">{fmt(summary.total_net_worth)}</div>
          <div className="flex items-center gap-5 mt-2">
            {xirr !== null && (
              <span className="text-sm text-slate-400">
                XIRR <span className={`font-semibold ${pnlClass(xirr)}`}>{(xirr * 100).toFixed(1)}%</span>
              </span>
            )}
            <span className={`text-sm font-medium ${pnlClass(pnl)}`}>
              {pnl >= 0 ? "↑" : "↓"} {fmt(Math.abs(pnl))} unrealized
            </span>
          </div>
          {lastUpdate && (
            <div className="text-[11px] text-slate-600 mt-2">Prices updated {lastUpdate}</div>
          )}
        </div>
        <a
          href="/dashboard/alerts"
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold border transition-colors ${
            alertCount > 0
              ? "bg-amber-950 border-amber-700 text-amber-400 hover:bg-amber-900"
              : "bg-slate-800 border-slate-700 text-slate-500 hover:border-slate-600"
          }`}
        >
          {alertCount > 0 ? `⚠ ${alertCount} Alert${alertCount !== 1 ? "s" : ""}` : "✓ No Alerts"}
        </a>
      </div>

      {/* 4 Stat Tiles */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { label: "PMS", value: fmt(pmsValue) },
          { label: "Direct Equity", value: fmt(eqValue) },
          { label: "Mutual Funds", value: fmt(mfValue) },
          {
            label: "Active Alerts",
            value: String(alertCount),
            cls: alertCount > 0 ? "text-amber-400" : "text-slate-100",
          },
        ].map((t) => (
          <div key={t.label} className="bg-slate-900 rounded-xl p-4 border border-slate-800">
            <div className="text-[11px] text-slate-500 uppercase tracking-widest mb-1.5 font-medium">{t.label}</div>
            <div className={`text-2xl font-bold tracking-tight ${"cls" in t ? t.cls : "text-slate-100"}`}>{t.value}</div>
          </div>
        ))}
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-2 gap-5">
        {/* Entity Cards */}
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-5">
          <div className="text-[11px] text-slate-500 uppercase tracking-widest mb-3 font-medium">Entities</div>
          <div className="flex flex-col gap-2">
            {summary.entities.map((e) => {
              const pct = summary.total_net_worth > 0
                ? (e.total_value / summary.total_net_worth * 100).toFixed(1)
                : "0";
              return (
                <div key={e.entity_id} className="flex justify-between items-center bg-slate-800 rounded-lg px-3 py-2.5">
                  <div>
                    <div className="text-sm text-slate-200 font-medium">{e.entity_name}</div>
                    <div className="text-[11px] text-slate-500 capitalize mt-0.5">{e.entity_type.replace("_", " ")}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold text-slate-100">{fmt(e.total_value)}</div>
                    <div className="text-[11px] text-slate-500 mt-0.5">{pct}% of family</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Live Movers */}
        <div className="bg-slate-900 rounded-xl border border-slate-800 p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="text-[11px] text-slate-500 uppercase tracking-widest font-medium">Live Movers</div>
            {lastUpdate && <div className="text-[10px] text-slate-600">{lastUpdate}</div>}
          </div>
          {movers.length === 0 ? (
            <div className="text-slate-600 text-sm text-center py-8 leading-relaxed">
              No price data yet<br />
              <span className="text-[11px]">Refreshes during market hours</span>
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {movers.map((h) => {
                const chg = h.day_change_pct!;
                return (
                  <div key={h.identifier} className="flex justify-between items-center bg-slate-800 rounded-lg px-3 py-2.5">
                    <div>
                      <div className="text-sm text-slate-200 font-medium">{h.security_name}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">{h.identifier}</div>
                    </div>
                    <div className="text-right">
                      <div className={`text-sm font-bold ${pnlClass(chg)}`}>
                        {chg >= 0 ? "+" : ""}{chg.toFixed(2)}%
                      </div>
                      {h.current_price !== null && (
                        <div className="text-[11px] text-slate-500 mt-0.5">₹{h.current_price.toLocaleString("en-IN")}</div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
