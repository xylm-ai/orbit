import { PriceTicker } from "@/components/price-ticker";

export function Topbar() {
  return (
    <header className="bg-slate-900 border-b border-slate-800 px-6 py-3.5 flex items-center justify-between sticky top-0 z-10">
      <h1 className="text-sm font-semibold text-white">Dashboard</h1>
      <div className="flex items-center gap-3">
        <PriceTicker />
        <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />
        <span className="text-xs text-slate-500">Prices live</span>
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-cyan-500 flex items-center justify-center text-[11px] font-bold text-white">RS</div>
      </div>
    </header>
  );
}
