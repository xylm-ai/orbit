"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";

type Row = {
  event_type: string;
  date: string;
  isin?: string;
  security_name?: string;
  quantity?: number;
  price?: number;
  amount: number;
  broker?: string;
  scheme_name?: string;
  scheme_code?: string;
  units?: number;
  nav?: number;
  narration?: string;
  duplicate?: boolean;
  confidence: Record<string, number>;
};

type Extraction = {
  id: string;
  document_id: string;
  extracted_data: Row[];
  review_status: string;
};

const LOW_CONF = 0.7;

export default function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [extractionId, setExtractionId] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ events_written: number; skipped_duplicates: number } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<{ extraction_id: string }>(`/documents/${id}/extraction`)
      .then(({ extraction_id }) => {
        setExtractionId(extraction_id);
        return apiFetch<Extraction>(`/extractions/${extraction_id}/review`);
      })
      .then((e) => setRows(e.extracted_data))
      .catch(() => setError("Could not load extraction."));
  }, [id]);

  function getLowConfFields(row: Row): string[] {
    return Object.entries(row.confidence)
      .filter(([, v]) => v < LOW_CONF)
      .map(([k]) => k);
  }

  function allLowConfTouched(): boolean {
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (row.duplicate) continue;
      for (const field of getLowConfFields(row)) {
        if (!touched.has(`${i}_${field}`)) return false;
      }
    }
    return true;
  }

  function handleFieldChange(rowIdx: number, field: string, value: string) {
    setRows((prev) => {
      const updated = [...prev];
      updated[rowIdx] = { ...updated[rowIdx], [field]: value };
      return updated;
    });
    setTouched((prev) => new Set(prev).add(`${rowIdx}_${field}`));
    if (extractionId) {
      apiFetch(`/extractions/${extractionId}/rows/${rowIdx}`, {
        method: "PUT",
        body: JSON.stringify({ [field]: value }),
      }).catch(console.error);
    }
  }

  async function handleConfirm() {
    if (!extractionId) return;
    setSubmitting(true);
    setError("");
    try {
      const res = await apiFetch<{ events_written: number; skipped_duplicates: number }>(
        `/extractions/${extractionId}/confirm`,
        { method: "POST" }
      );
      setResult(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Confirm failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleReject() {
    if (!extractionId) return;
    setSubmitting(true);
    try {
      await apiFetch(`/extractions/${extractionId}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: rejectReason }),
      });
      router.push("/dashboard/documents");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setSubmitting(false);
    }
  }

  if (result) {
    return (
      <div className="max-w-2xl mx-auto mt-16 text-center space-y-4">
        <div className="text-5xl">✓</div>
        <h1 className="text-2xl font-bold text-white">Extraction Confirmed</h1>
        <p className="text-slate-400">
          {result.events_written} event{result.events_written !== 1 ? "s" : ""} written.
          {result.skipped_duplicates > 0 && ` ${result.skipped_duplicates} duplicate(s) skipped.`}
        </p>
        <button
          onClick={() => router.push("/dashboard/documents")}
          className="mt-4 px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-lg"
        >
          Back to Documents
        </button>
      </div>
    );
  }

  if (!extractionId || rows.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        {error ? (
          <p className="text-red-400">{error}</p>
        ) : (
          <div className="text-slate-500 text-sm">Loading extraction…</div>
        )}
      </div>
    );
  }

  const canConfirm = allLowConfTouched() && !submitting;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Review Extraction</h1>
          <p className="text-slate-400 text-sm mt-1">
            Cells highlighted in amber have low confidence — click to confirm or correct.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => setShowReject(true)}
            className="px-4 py-2 border border-red-700 text-red-400 hover:bg-red-900/30 text-sm font-semibold rounded-lg transition-colors"
          >
            Reject Document
          </button>
          <button
            onClick={handleConfirm}
            disabled={!canConfirm}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {submitting ? "Confirming…" : "Confirm All"}
          </button>
        </div>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {showReject && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 w-96 space-y-4">
            <h3 className="text-white font-semibold">Reject Document</h3>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason (optional)"
              className="w-full bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 h-24 resize-none focus:outline-none focus:ring-2 focus:ring-red-500"
            />
            <div className="flex gap-3 justify-end">
              <button onClick={() => setShowReject(false)} className="px-4 py-2 text-slate-400 text-sm hover:text-white">
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={submitting}
                className="px-4 py-2 bg-red-700 hover:bg-red-600 text-white text-sm font-semibold rounded-lg"
              >
                Confirm Reject
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-800 bg-slate-900/80">
              <th className="px-4 py-3 font-medium">Event</th>
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Security / Scheme</th>
              <th className="px-4 py-3 font-medium">ISIN</th>
              <th className="px-4 py-3 font-medium">Qty</th>
              <th className="px-4 py-3 font-medium">Price</th>
              <th className="px-4 py-3 font-medium">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {rows.map((row, i) => {
              const lowFields = new Set(getLowConfFields(row));
              const isDup = row.duplicate;

              function cell(field: string, value: string | number | undefined) {
                const isLow = lowFields.has(field);
                const isTouched = touched.has(`${i}_${field}`);
                const bgClass = isDup
                  ? "text-slate-600 line-through"
                  : isLow && !isTouched
                  ? "bg-amber-900/40 border border-amber-700/60 rounded"
                  : "";

                if (isDup) {
                  return <span className={bgClass}>{value ?? "—"}</span>;
                }

                return (
                  <input
                    type="text"
                    defaultValue={value !== undefined ? String(value) : ""}
                    onFocus={() => {
                      if (isLow) setTouched((p) => new Set(p).add(`${i}_${field}`));
                    }}
                    onChange={(e) => handleFieldChange(i, field, e.target.value)}
                    className={`bg-transparent text-white w-full px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 rounded text-xs ${bgClass}`}
                  />
                );
              }

              return (
                <tr key={i} className={`${isDup ? "opacity-40" : "hover:bg-slate-800/40"} transition-colors`}>
                  <td className="px-4 py-3 text-xs font-mono text-indigo-300">
                    {row.event_type}
                    {isDup && <span className="ml-2 text-[10px] text-slate-500 font-sans">already ingested</span>}
                  </td>
                  <td className="px-4 py-3">{cell("date", row.date)}</td>
                  <td className="px-4 py-3">{cell("security_name", row.security_name ?? row.scheme_name)}</td>
                  <td className="px-4 py-3 font-mono text-xs">{cell("isin", row.isin)}</td>
                  <td className="px-4 py-3">{cell("quantity", row.quantity ?? row.units)}</td>
                  <td className="px-4 py-3">{cell("price", row.price ?? row.nav)}</td>
                  <td className="px-4 py-3">{cell("amount", row.amount)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
