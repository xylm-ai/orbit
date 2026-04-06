"use client";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import type { AlertItem } from "@/lib/types";

const SEVERITY_CARD: Record<string, string> = {
  critical: "bg-red-950 border-red-800",
  warning:  "bg-amber-950 border-amber-800",
};

const SEVERITY_BADGE: Record<string, string> = {
  critical: "bg-red-900 text-red-300",
  warning:  "bg-amber-900 text-amber-300",
};

const SEVERITY_TEXT: Record<string, string> = {
  critical: "text-red-300",
  warning:  "text-amber-300",
};

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState("");
  const [dismissing, setDismissing] = useState<string | null>(null);

  const load = () =>
    apiFetch<AlertItem[]>("/dashboard/alerts")
      .then(setAlerts)
      .catch((e: Error) => setError(e.message));

  useEffect(() => { load(); }, []);

  const dismiss = async (id: string) => {
    setDismissing(id);
    try {
      await apiFetch(`/dashboard/alerts/${id}/dismiss`, { method: "POST" });
      setAlerts((prev) => prev.filter((a) => a.id !== id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to dismiss");
    } finally {
      setDismissing(null);
    }
  };

  const threshold = alerts.filter((a) => a.source === "threshold");
  const recon = alerts.filter((a) => a.source === "reconciliation");

  if (error) return <div className="text-red-400 text-sm">{error}</div>;

  return (
    <div>
      <h1 className="text-base font-bold text-slate-200 mb-6 tracking-tight">Alerts</h1>

      {alerts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="w-12 h-12 rounded-full bg-emerald-950 border border-emerald-800 flex items-center justify-center mb-4">
            <span className="text-emerald-400 text-xl">✓</span>
          </div>
          <div className="text-slate-300 font-medium">No active alerts</div>
          <div className="text-slate-600 text-sm mt-1">All portfolios look healthy</div>
        </div>
      )}

      {threshold.length > 0 && (
        <section className="mb-8">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest mb-3">Portfolio Alerts</div>
          <div className="flex flex-col gap-2.5">
            {threshold.map((a) => (
              <div
                key={a.id}
                className={`rounded-xl border p-4 flex justify-between items-start gap-4 ${SEVERITY_CARD[a.severity] ?? SEVERITY_CARD.warning}`}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className={`text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-md ${SEVERITY_BADGE[a.severity]}`}>
                      {a.severity}
                    </span>
                    <span className="text-[10px] text-slate-600 uppercase tracking-wider">{a.alert_type.replace(/_/g, " ")}</span>
                  </div>
                  <div className={`text-sm font-medium leading-snug ${SEVERITY_TEXT[a.severity]}`}>{a.message}</div>
                  <div className="text-[11px] text-slate-600 mt-1.5">
                    {new Date(a.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                  </div>
                </div>
                <button
                  onClick={() => dismiss(a.id)}
                  disabled={dismissing === a.id}
                  className="shrink-0 text-xs text-slate-500 hover:text-slate-300 border border-slate-700 hover:border-slate-500 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-40"
                >
                  {dismissing === a.id ? "…" : "Dismiss"}
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {recon.length > 0 && (
        <section>
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-widest mb-3">Reconciliation Flags</div>
          <div className="flex flex-col gap-2.5">
            {recon.map((a) => (
              <div key={a.id} className="rounded-xl border border-amber-800 bg-amber-950 p-4">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-md bg-amber-900 text-amber-300">recon</span>
                  <span className="text-[10px] text-slate-600 uppercase tracking-wider">Bank mismatch</span>
                </div>
                <div className="text-sm font-medium text-amber-300 leading-snug">{a.message}</div>
                <div className="text-[11px] text-slate-600 mt-1.5">
                  {new Date(a.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
