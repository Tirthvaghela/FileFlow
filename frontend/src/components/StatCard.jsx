export default function StatCard({
  label,
  value,
  icon: Icon,
  iconColor = "var(--series-1)",
  badge,
  badgeColor = "var(--status-good)",
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm transition-shadow hover:shadow-md">
      <div className="mb-3 flex items-center justify-between">
        {Icon ? (
          <span
            className="flex h-9 w-9 items-center justify-center rounded-lg"
            style={{
              color: iconColor,
              background: `color-mix(in srgb, ${iconColor} 14%, transparent)`,
            }}
          >
            <Icon width={18} height={18} />
          </span>
        ) : (
          <span />
        )}
        {badge && (
          <span
            className="rounded-full px-2 py-0.5 text-xs font-medium"
            style={{
              color: badgeColor,
              background: `color-mix(in srgb, ${badgeColor} 14%, transparent)`,
            }}
          >
            {badge}
          </span>
        )}
      </div>
      <p className="text-2xl font-semibold text-[var(--text-primary)]">{value}</p>
      <p className="mt-1 text-sm text-[var(--text-muted)]">{label}</p>
    </div>
  );
}
