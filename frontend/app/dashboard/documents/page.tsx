"use client";
import { useEffect, useState, useRef } from "react";
import { apiFetch } from "@/lib/api";

type Doc = {
  id: string;
  source: string;
  doc_type: string | null;
  status: string;
  uploaded_at: string;
  failure_reason: string | null;
};

type Entity = {
  id: string;
  name: string;
};

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-slate-700 text-slate-300",
  classifying: "bg-indigo-900 text-indigo-300",
  preprocessing: "bg-indigo-900 text-indigo-300",
  extracting: "bg-indigo-900 text-indigo-300",
  normalizing: "bg-indigo-900 text-indigo-300",
  awaiting_review: "bg-amber-900 text-amber-300",
  ingested: "bg-emerald-900 text-emerald-300",
  failed: "bg-red-900 text-red-300",
  rejected_sender: "bg-red-900 text-red-300",
};

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [selectedEntity, setSelectedEntity] = useState("");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    apiFetch<Doc[]>("/documents").then(setDocs).catch(console.error);
    apiFetch<Entity[]>("/entities").then((es) => {
      setEntities(es);
      if (es.length > 0) setSelectedEntity(es[0].id);
    }).catch(console.error);
  }, []);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file || !selectedEntity) return;
    setUploading(true);
    setError("");
    try {
      const token = localStorage.getItem("orbit_token");
      const form = new FormData();
      form.append("file", file);
      form.append("entity_id", selectedEntity);
      const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const res = await fetch(`${API_BASE}/documents`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error((err as { detail?: string }).detail ?? "Upload failed");
      }
      const doc: Doc = await res.json();
      setDocs((prev) => [doc, ...prev]);
      if (fileRef.current) fileRef.current.value = "";
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white mb-1">Documents</h1>
        <p className="text-slate-400 text-sm">
          Upload statements or forward them to your inbound email address.
        </p>
      </div>

      {/* Upload widget */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">Upload Document</h2>
        <form onSubmit={handleUpload} className="flex flex-col gap-3">
          <select
            value={selectedEntity}
            onChange={(e) => setSelectedEntity(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {entities.map((en) => (
              <option key={en.id} value={en.id}>{en.name}</option>
            ))}
          </select>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg,.xls,.xlsx"
            className="text-sm text-slate-400 file:mr-3 file:py-1.5 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-indigo-600 file:text-white hover:file:bg-indigo-500 cursor-pointer"
          />
          {error && <p className="text-red-400 text-xs">{error}</p>}
          <button
            type="submit"
            disabled={uploading}
            className="self-start px-5 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm font-semibold rounded-lg transition-colors"
          >
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </form>
      </div>

      {/* Documents list */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-800">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest">
            Recent Documents
          </h2>
        </div>
        {docs.length === 0 ? (
          <div className="px-6 py-12 text-center text-slate-500 text-sm">No documents yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-800">
                <th className="px-6 py-3 font-medium">Type</th>
                <th className="px-6 py-3 font-medium">Source</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Uploaded</th>
                <th className="px-6 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {docs.map((doc) => (
                <tr key={doc.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-6 py-3 text-white font-mono text-xs">
                    {doc.doc_type ?? "—"}
                  </td>
                  <td className="px-6 py-3 text-slate-400">{doc.source}</td>
                  <td className="px-6 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${STATUS_COLORS[doc.status] ?? "bg-slate-700 text-slate-300"}`}>
                      {doc.status.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-slate-400 text-xs">
                    {new Date(doc.uploaded_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-3">
                    {doc.status === "awaiting_review" && (
                      <a
                        href={`/dashboard/documents/${doc.id}/review`}
                        className="text-indigo-400 hover:text-indigo-300 text-xs font-semibold"
                      >
                        Review →
                      </a>
                    )}
                    {doc.status === "failed" && doc.failure_reason && (
                      <span className="text-red-400 text-xs" title={doc.failure_reason}>
                        Error
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
