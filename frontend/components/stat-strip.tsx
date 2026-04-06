interface StatItem {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}

export function StatStrip({ items }: { items: StatItem[] }) {
  return (
    <div
      className="grid gap-4 mb-6"
      style={{ gridTemplateColumns: `repeat(${items.length}, 1fr)` }}
    >
      {items.map((item) => (
        <div key={item.label} className="bg-slate-900 rounded-xl p-4 border border-slate-800">
          <div className="text-[11px] text-slate-500 uppercase tracking-widest mb-1.5 font-medium">{item.label}</div>
          <div className={`text-xl font-bold tracking-tight ${item.valueClass ?? "text-slate-100"}`}>{item.value}</div>
          {item.sub && <div className="text-xs text-slate-500 mt-0.5">{item.sub}</div>}
        </div>
      ))}
    </div>
  );
}
