"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { PaginatedTransactions, TransactionItem } from "@/lib/types";

const EVENT_LABELS: Record<string, { label: string; cls: string }> = {
  SecurityBought:     { label: "Buy",     cls: "bg-emerald-950 text-emerald-400" },
  SecuritySold:       { label: "Sell",    cls: "bg-red-950 text-red-400" },
  DividendReceived:   { label: "Div",     cls: "bg-indigo-950 text-indigo-400" },
  MFUnitsPurchased:   { label: "MF Buy",  cls: "bg-emerald-950 text-emerald-400" },
  MFUnitsRedeemed:    { label: "MF Sell", cls: "bg-red-950 text-red-400" },
  BankEntryRecorded:  { label: "Bank",    cls: "bg-slate-800 text-slate-400" },
  OpeningBalanceSet:  { label: "Opening", cls: "bg-slate-800 text-slate-400" },
};

function fmt(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
  return `₹${n.toLocaleString("en-IN")}`;
}

function extractAmount(item: TransactionItem): string {
  const p = item.payload as Record<string, unknown>;
  const amount = p["amount"] ?? p["total_value"];
  if (amount != null) return fmt(Number(amount));
  return "—";
}

function extractSecurity(item: TransactionItem): string {
  const p = item.payload as Record<string, unknown>;
  return String(p["security_name"] ?? p["scheme_name"] ?? "—");
}

export default function TransactionsPage() {
  const [data, setData] = useState<PaginatedTransactions | null>(null);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<PaginatedTransactions>(`/dashboard/transactions?page=${page}&page_size=50`)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [page]);

  if (error) return <div className="text-red-400 text-sm">{error}</div>;
  if (!data) return <div className="text-slate-500 text-sm animate-pulse">Loading…</div>;

  const totalPages = Math.ceil(data.total / data.page_size);

  return (
    <div>
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-base font-bold text-slate-200 tracking-tight">Transactions</h1>
        <span className="text-[11px] text-slate-500">{data.total.toLocaleString("en-IN")} total</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full text-xs text-slate-300">
          <thead>
            <tr className="bg-slate-900 text-slate-500 uppercase tracking-widest">
              {["Date", "Type", "Security / Scheme", "Amount"].map((h) => (
                <th key={h} className="px-3 py-2.5 text-left font-medium text-[10px]">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => {
              const ev = EVENT_LABELS[item.event_type] ?? { label: item.event_type, cls: "bg-slate-800 text-slate-400" };
              return (
                <tr key={item.event_id} className="border-t border-slate-800 hover:bg-slate-800/40 transition-colors">
                  <td className="px-3 py-2 text-slate-500 tabular-nums">{item.event_date}</td>
                  <td className="px-3 py-2">
                    <span className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-md ${ev.cls}`}>
                      {ev.label}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-slate-200 font-medium">{extractSecurity(item)}</td>
                  <td className="px-3 py-2 font-medium tabular-nums">{extractAmount(item)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex justify-between items-center mt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="text-xs text-slate-400 disabled:text-slate-700 hover:text-slate-200 px-3 py-1.5 border border-slate-700 rounded-lg disabled:border-slate-800 transition-colors"
          >
            ← Previous
          </button>
          <span className="text-xs text-slate-500">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="text-xs text-slate-400 disabled:text-slate-700 hover:text-slate-200 px-3 py-1.5 border border-slate-700 rounded-lg disabled:border-slate-800 transition-colors"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
