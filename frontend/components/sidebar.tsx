"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";

const NAV = [
  { label: "Overview", href: "/dashboard" },
  { label: "PMS Intelligence", href: "/dashboard/pms" },
  { label: "Direct Equity", href: "/dashboard/equity" },
  { label: "Mutual Funds", href: "/dashboard/mf" },
  { label: "Transactions", href: "/dashboard/transactions" },
  { label: "Alerts", href: "/dashboard/alerts" },
  { label: "Documents", href: "/dashboard/documents" },
];

interface EntityOption {
  entity_id: string;
  entity_name: string;
  entity_type: string;
}

const TYPE_LABEL: Record<string, string> = {
  individual: "Individual",
  huf: "HUF",
  company: "Company",
  trust: "Trust",
};

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [entities, setEntities] = useState<EntityOption[]>([]);
  const [selected, setSelected] = useState<EntityOption | null>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiFetch<{ entities: EntityOption[] }>("/dashboard/summary")
      .then((d) => setEntities(d.entities))
      .catch(() => {});
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <aside className="w-56 bg-slate-900 border-r border-slate-800 flex flex-col h-screen sticky top-0">
      <div className="p-5 border-b border-slate-800">
        <div className="text-lg font-extrabold tracking-widest bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent">ORBIT</div>
        <div className="text-[10px] text-slate-500 tracking-widest mt-0.5">WEALTH INTELLIGENCE</div>
      </div>

      {/* Entity selector */}
      <div className="px-2 py-3 border-b border-slate-800" ref={dropdownRef}>
        <div className="text-[10px] text-slate-500 px-2 mb-1">ENTITY</div>
        <button
          onClick={() => setOpen((o) => !o)}
          className="w-full text-left text-xs text-indigo-400 font-semibold bg-indigo-950 hover:bg-indigo-900 rounded-lg px-3 py-2 flex items-center justify-between transition-colors"
        >
          <span className="truncate">{selected ? selected.entity_name : "All Entities"}</span>
          <svg
            className={`w-3 h-3 ml-1 flex-shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {open && (
          <div className="mt-1 bg-slate-800 border border-slate-700 rounded-lg overflow-hidden shadow-xl">
            {/* All Entities option */}
            <button
              onClick={() => { setSelected(null); setOpen(false); }}
              className={`w-full text-left px-3 py-2 text-xs transition-colors ${
                selected === null
                  ? "text-indigo-400 bg-indigo-950"
                  : "text-slate-300 hover:bg-slate-700"
              }`}
            >
              All Entities
            </button>
            {entities.map((e) => (
              <button
                key={e.entity_id}
                onClick={() => { setSelected(e); setOpen(false); }}
                className={`w-full text-left px-3 py-2 text-xs transition-colors border-t border-slate-700/50 ${
                  selected?.entity_id === e.entity_id
                    ? "text-indigo-400 bg-indigo-950"
                    : "text-slate-300 hover:bg-slate-700"
                }`}
              >
                <div className="font-medium truncate">{e.entity_name}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{TYPE_LABEL[e.entity_type] ?? e.entity_type}</div>
              </button>
            ))}
          </div>
        )}
      </div>

      <nav className="flex-1 px-2 py-3 flex flex-col gap-0.5">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`text-sm px-3 py-2 rounded-lg transition-colors ${
              pathname === item.href
                ? "bg-indigo-950 text-indigo-400 font-semibold border-l-2 border-indigo-500"
                : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      {/* Logout */}
      <div className="px-2 py-3 border-t border-slate-800">
        <button
          onClick={() => {
            localStorage.removeItem("orbit_token");
            router.push("/login");
          }}
          className="w-full flex items-center gap-2 text-xs text-slate-500 hover:text-red-400 px-3 py-2 rounded-lg hover:bg-slate-800 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
          Sign out
        </button>
      </div>
    </aside>
  );
}
