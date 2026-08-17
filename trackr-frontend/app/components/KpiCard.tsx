export function KpiCard({
  label,
  value,
  sublabel,
  subValue,
  subClass = "text-navy-400",
}: {
  label: string;
  value: string;
  sublabel?: string;
  subValue?: string;
  subClass?: string;
}) {
  return (
    <div className="glass-card glass-card-hover animate-fade-in-up rounded-xl border border-navy-100 p-5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-navy-400">{label}</p>
      <p className="mt-2 font-heading text-2xl text-navy-900 tabular-nums">{value}</p>
      {sublabel && (
        <p className={`mt-1 text-xs ${subClass}`}>
          {subValue && <span className="font-medium">{subValue} </span>}
          {sublabel}
        </p>
      )}
    </div>
  );
}
