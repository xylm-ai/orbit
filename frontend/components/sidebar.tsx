"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { label: "Overview", href: "/dashboard" },
  { label: "PMS Intelligence", href: "/dashboard/pms" },
  { label: "Direct Equity", href: "/dashboard/equity" },
  { label: "Mutual Funds", href: "/dashboard/mf" },
  { label: "Transactions", href: "/dashboard/transactions" },
  { label: "Alerts", href: "/dashboard/alerts" },
  { label: "Documents", href: "/dashboard/documents" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 bg-slate-900 border-r border-slate-800 flex flex-col h-screen sticky top-0">
      <div className="p-5 border-b border-slate-800">
        <div className="text-lg font-extrabold tracking-widest bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent">ORBIT</div>
        <div className="text-[10px] text-slate-500 tracking-widest mt-0.5">WEALTH INTELLIGENCE</div>
      </div>
      <div className="px-2 py-3 border-b border-slate-800">
        <div className="text-[10px] text-slate-500 px-2 mb-1">ENTITY</div>
        <div className="text-xs text-indigo-400 font-semibold bg-indigo-950 rounded-lg px-3 py-2">All Entities ▾</div>
      </div>
      <nav className="flex-1 px-2 py-3 flex flex-col gap-0.5">
        {NAV.map(item => (
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
    </aside>
  );
}
