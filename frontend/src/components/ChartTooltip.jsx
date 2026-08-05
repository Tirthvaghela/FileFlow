export default function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-3 py-2 text-sm shadow-sm">
      <p className="font-medium text-[var(--text-primary)]">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey} className="text-[var(--text-secondary)]">
          {entry.value} files
        </p>
      ))}
    </div>
  );
}
