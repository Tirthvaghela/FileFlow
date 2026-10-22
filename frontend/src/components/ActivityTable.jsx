import { useState } from "react";
import { Activity, ChevronDown, ChevronUp } from "lucide-react";
import EmptyState from "./EmptyState.jsx";
import { categoryBadge } from "../utils/categoryMeta.js";

// Labels the explanation's own match_type (rules/classifier.py's
// MATCH_TYPE_PRIORITY) as the short, human-facing "Match" line -- kept
// separate from rule_name, which already describes the specific rule.
const MATCH_TYPE_LABEL = {
  keyword: "Keyword",
  regex: "Regex",
  content_keyword: "File content",
  extension: "Extension",
  large_file: "Large file",
  date: "File age",
  category: "Category",
  auto_extension: "Automatic grouping",
  default: "Default category",
};

function ExplanationDetails({ explanation }) {
  if (!explanation || explanation.match_type === "default") {
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        No matching rule — this file was placed in the account's default category.
      </p>
    );
  }
  return (
    <ul className="space-y-1 text-xs text-[var(--text-secondary)]">
      {explanation.rule_name && (
        <li>
          <span className="text-[var(--text-muted)]">Rule:</span> {explanation.rule_name}
        </li>
      )}
      <li>
        <span className="text-[var(--text-muted)]">Match type:</span>{" "}
        {MATCH_TYPE_LABEL[explanation.match_type] || explanation.match_type}
      </li>
      {explanation.matched_value && (
        <li>
          <span className="text-[var(--text-muted)]">Matched:</span> "{explanation.matched_value}"
        </li>
      )}
      <li>
        <span className="text-[var(--text-muted)]">Destination:</span> {explanation.destination}
      </li>
      {explanation.priority != null && (
        <li>
          <span className="text-[var(--text-muted)]">Rule priority:</span> {explanation.priority}
        </li>
      )}
    </ul>
  );
}

const ACTION_META = {
  moved: { label: "Organized", color: "var(--status-good)" },
  renamed_and_moved: { label: "Organized (renamed)", color: "var(--status-good)" },
  replaced: { label: "Organized (replaced)", color: "var(--status-good)" },
  duplicate_skipped: { label: "Duplicate skipped", color: "var(--status-warning)" },
  archived: { label: "Archived", color: "var(--text-muted)" },
  deleted: { label: "Deleted", color: "var(--status-critical)" },
};

// Mirrors the backend's UNDOABLE_ACTIONS (automation/organizer.py) -- a row
// whose action isn't in this list will always fail server-side (e.g. no
// destination_path to move back), so it's left off every row's controls
// rather than showing a button that can only ever error.
const UNDOABLE_ACTIONS = ["moved", "renamed_and_moved", "replaced", "archived", "reclassified"];

function subtitleFor(log) {
  if (log.action === "duplicate_skipped") return `Already exists in ${log.category}`;
  if (log.action === "archived") return `Archived from ${log.category}`;
  if (log.action === "deleted") return `Deleted from ${log.category}`;
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

const STATUS_BADGE_META = {
  pending: { label: "Waiting for agent…", color: "var(--status-warning)" },
  failed: { label: "Failed", color: "var(--status-critical)" },
  completed: { label: "Completed", color: "var(--status-good)" },
};

// commandStatusByLogId correlates this row's own log.id with the most
// recent undo/reclassify agent command it triggered (see
// useCommandStatusByLogId.js) -- when one exists, its real, current
// status replaces the otherwise-unconditional "Completed" placeholder.
// success===false (not falsy/undefined) specifically means the command
// row is fully "done" with a real failure, distinct from "not started
// yet" (pending, success still null) -- never reinterpreted beyond that.
function agentCommandBadge(command) {
  if (!command) return STATUS_BADGE_META.completed;
  if (command.status === "pending") return STATUS_BADGE_META.pending;
  if (command.success === false) return STATUS_BADGE_META.failed;
  return STATUS_BADGE_META.completed;
}

function FileBadge({ log }) {
  const meta = ACTION_META[log.action] || { color: "var(--text-muted)" };
  const color = meta.color;
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
  undoing = false,
  undoingId = null,
  allowAnyRowUndo = false,
  showStatusBadge = false,
  commandStatusByLogId = {},
  onReclassify,
  categories = [],
  selectable = false,
  selectedIds = null,
  onToggleSelect = null,
}) {
  const [expandedId, setExpandedId] = useState(null);

  if (!logs.length) {
    return (
      <EmptyState
        icon={Activity}
        message="No activity yet — drop a file into the watched folder to see it here."
      />
    );
  }

  return (
    <div className="divide-y divide-[var(--border)]">
      {logs.map((log, i) => {
        const meta = ACTION_META[log.action] || { label: log.action, color: "var(--text-muted)" };
        const badge = agentCommandBadge(commandStatusByLogId[log.id]);
        const expanded = expandedId === log.id;
        return (
          <div key={log.id} className="py-3">
          {/* flex-wrap: on a narrow viewport, the filename takes its own
              full-width row first (basis-full), then the timestamp/badge/
              actions wrap onto their own line below it rather than forcing
              this row -- and the whole page -- wider than the viewport. */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
            {selectable && !log.undone && (
              <input
                type="checkbox"
                checked={selectedIds?.has(log.id) ?? false}
                onChange={() => onToggleSelect?.(log.id)}
                className="h-4 w-4 shrink-0 rounded border-[var(--border)] accent-[var(--brand)]"
                aria-label={`Select ${log.final_filename}`}
              />
            )}
            {selectable && log.undone && <span className="w-4 shrink-0" />}
            <FileBadge log={log} />
            <div className="min-w-0 flex-1 basis-full sm:basis-0">
              <div className="truncate text-sm font-medium text-[var(--text-primary)]">
                {log.final_filename}
              </div>
              <div className="text-xs text-[var(--text-muted)]">
                {subtitleFor(log)}
                {log.undone ? " · undone" : ""}
              </div>
            </div>
            <span
              className="shrink-0 text-xs text-[var(--text-muted)]"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {relativeTime(log.timestamp)}
            </span>
            {showStatusBadge && (
              <span
                className="rounded-full px-2.5 py-1 text-xs font-medium"
                style={{
                  color: badge.color,
                  background: `color-mix(in srgb, ${badge.color} 14%, transparent)`,
                }}
              >
                {badge.label}
              </span>
            )}
            {onUndo &&
              !log.undone &&
              (allowAnyRowUndo ? UNDOABLE_ACTIONS.includes(log.action) : i === 0) && (
                <button
                  onClick={() => onUndo(log)}
                  disabled={allowAnyRowUndo ? undoingId === log.id : undoing}
                  className="rounded-md border border-[var(--border)] px-2.5 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--gridline)] disabled:opacity-50"
                >
                  {(allowAnyRowUndo ? undoingId === log.id : undoing) ? "Undoing…" : "Undo"}
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
            {log.explanation && (
              <button
                onClick={() => setExpandedId(expanded ? null : log.id)}
                aria-expanded={expanded}
                aria-label={`Why was ${log.final_filename} placed here?`}
                className="flex shrink-0 items-center gap-0.5 rounded-md px-1.5 py-1 text-xs font-medium text-[var(--text-muted)] hover:bg-[var(--gridline)] hover:text-[var(--text-primary)]"
              >
                Why?
                {expanded ? (
                  <ChevronUp className="h-3 w-3" />
                ) : (
                  <ChevronDown className="h-3 w-3" />
                )}
              </button>
            )}
          </div>
          {expanded && log.explanation && (
            <div className="ml-12 mt-2 rounded-lg border border-[var(--border)] bg-[var(--page)] px-3 py-2">
              <ExplanationDetails explanation={log.explanation} />
            </div>
          )}
          </div>
        );
      })}
    </div>
  );
}
