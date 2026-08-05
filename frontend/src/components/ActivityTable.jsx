import { categoryBadge } from "../utils/categoryMeta.js";

const ACTION_META = {
  moved: { label: "Organized", color: "var(--status-good)" },
  renamed_and_moved: { label: "Organized (renamed)", color: "var(--status-good)" },
  replaced: { label: "Organized (replaced)", color: "var(--status-good)" },
  duplicate_skipped: { label: "Duplicate skipped", color: "var(--status-warning)" },
  archived: { label: "Archived", color: "var(--text-muted)" },
};

function subtitleFor(log) {
  if (log.action === "duplicate_skipped") return `Already exists in ${log.category}`;
  if (log.action === "archived") return `Archived from ${log.category}`;
  return `Moved to ${log.category}`;
}

function formatTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function relativeTime(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return formatTime(iso);
}

function FileBadge({ log }) {
  const meta = ACTION_META[log.action] || { color: "var(--text-muted)" };
  const color = meta.color === "var(--text-muted)" ? "var(--series-1)" : "var(--series-1)";
  return (
    <span
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[9px] font-bold tracking-wide"
      style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}
    >
      {categoryBadge(log.category)}
    </span>
  );
}

export default function ActivityTable({
  logs,
  onUndo,
  showStatusBadge = false,
  onReclassify,
  categories = [],
}) {
  if (!logs.length) {
    return (
      <p className="py-8 text-center text-sm text-[var(--text-muted)]">
        No activity yet — drop a file into the watched folder to see it here.
      </p>
    );
  }

  return (
    <div className="divide-y divide-[var(--border)]">
      {logs.map((log, i) => {
        const meta = ACTION_META[log.action] || { label: log.action, color: "var(--text-muted)" };
        return (
          <div key={log.id} className="flex items-center gap-3 py-3">
            <FileBadge log={log} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-[var(--text-primary)]">
                {log.final_filename}
              </div>
              <div className="text-xs text-[var(--text-muted)]">
                {subtitleFor(log)}
                {log.undone ? " · undone" : ""}
              </div>
            </div>
            <span
              className="text-xs text-[var(--text-muted)]"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {relativeTime(log.timestamp)}
            </span>
            {showStatusBadge && (
              <span
                className="rounded-full px-2.5 py-1 text-xs font-medium"
                style={{
                  color: "var(--status-good)",
                  background: "color-mix(in srgb, var(--status-good) 14%, transparent)",
                }}
              >
                Completed
              </span>
            )}
            {onUndo && i === 0 && !log.undone && (
              <button
                onClick={() => onUndo(log)}
                className="rounded-md border border-[var(--border)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--gridline)]"
              >
                Undo
              </button>
            )}
            {!showStatusBadge && !onUndo && (
              <span
                className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]"
                title={meta.label}
              >
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: meta.color }} />
              </span>
            )}
            {onReclassify && log.destination_path && !log.undone && (
              <select
                value=""
                onChange={(e) => {
                  if (e.target.value) onReclassify(log, e.target.value);
                }}
                title="Move this file to a different category"
                className="max-w-[7.5rem] rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-1.5 py-1 text-xs text-[var(--text-secondary)]"
              >
                <option value="">Move to…</option>
                {categories
                  .filter((c) => c !== log.category)
                  .map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
              </select>
            )}
          </div>
        );
      })}
    </div>
  );
}
