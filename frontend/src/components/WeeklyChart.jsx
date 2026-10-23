// v5 "This week" bars: 116px tall, value above every bar (zeros too),
// today's bar last and in stamp red, ink baseline, mono day labels.
// Data is stats.last_7_days ([{ date: "YYYY-MM-DD", count }]).
function dayLabel(value) {
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { weekday: "short" });
}

export default function WeeklyChart({ data, height = 116 }) {
  const days = [...(data || [])].sort((a, b) => a.date.localeCompare(b.date)).slice(-7);
  if (!days.length) return <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">No activity in the last 7 days.</p>;
  const max = Math.max(1, ...days.map((d) => d.count));
  const last = days.length - 1;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-end gap-1.5 border-b-[1.5px] border-[var(--ink)]" style={{ height }}>
        {days.map((d, i) => (
          <div
            key={d.date}
            title={`${dayLabel(d.date)}: ${d.count} files`}
            className="flex h-full flex-1 flex-col items-center justify-end gap-[3px]"
          >
            <span className="font-mono-data text-[10.5px] font-semibold">{d.count}</span>
            <span
              className="ff-in w-full rounded-[2px_2px_0_0]"
              style={{
                height: `${(d.count / max) * (height - 22)}px`,
                minHeight: d.count > 0 ? 2 : 0,
                background: i === last ? "var(--stamp)" : "var(--ink)",
                animationDelay: `${i * 40}ms`,
              }}
            />
          </div>
        ))}
      </div>
      <div className="flex gap-1.5">
        {days.map((d) => (
          <span key={d.date} className="flex-1 text-center font-mono-data text-[10.5px] text-[var(--ink-muted)]">
            {dayLabel(d.date)}
          </span>
        ))}
      </div>
    </div>
  );
}
