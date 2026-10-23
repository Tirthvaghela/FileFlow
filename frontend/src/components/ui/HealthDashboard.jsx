import { Link } from "react-router-dom";
import Stamp from "./Stamp.jsx";
import Kicker from "../Kicker.jsx";
import { formatBytes } from "../../utils/categoryMeta.js";

function plural(n, noun) {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

export function formatUpdatedAt(iso) {
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch {
    return null;
  }
}

// Header controls for the health view: "Updated 6:44" + Refresh. Rendered
// inside the panel when standalone, or in the dialog header when the
// panel is shown from the Dashboard's "Organization health" tile.
export function HealthHeaderControls({ data, loading, refreshing, onRefresh }) {
  return (
    <div className="flex shrink-0 items-center gap-2.5">
      {data?.generated_at && (
        <span className="font-mono-data text-[11px] text-[var(--ink-muted)]">
          Updated {formatUpdatedAt(data.generated_at) ?? "just now"}
        </span>
      )}
      <button type="button" onClick={onRefresh} disabled={loading || refreshing} className="ff-btn ff-btn-tertiary ff-btn-sm">
        {refreshing ? "Refreshing…" : "Refresh"}
      </button>
    </div>
  );
}

// A compact, deterministic overview of FileFlow's existing capabilities --
// classification coverage, duplicate groups, rule conflicts, and recent
// activity. Every number is read straight from GET /api/health/organization.
// This component never calls AI, never triggers a scan itself, and never
// offers a destructive action -- it only links to the features that do.
export default function HealthDashboard({
  data,
  loading,
  error,
  refreshing,
  onRefresh,
  onReviewUnclassified,
  onReviewDuplicates,
  headerless = false,
}) {
  return (
    <div className="flex flex-col gap-3">
      {!headerless && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="ff-caps m-0 text-[15px]">FileFlow Health</h2>
          <HealthHeaderControls data={data} loading={loading} refreshing={refreshing} onRefresh={onRefresh} />
        </div>
      )}

      {loading && !data && <p className="py-6 text-center text-sm text-[var(--ink-muted)]">Loading workspace health…</p>}

      {error && (
        <div role="alert" className="rounded-[4px] border-[1.5px] border-dashed border-[var(--stamp)] p-3.5 text-[13px] text-[var(--stamp)]">
          {error}
        </div>
      )}

      {data && !error && (
        <HealthSections data={data} onReviewUnclassified={onReviewUnclassified} onReviewDuplicates={onReviewDuplicates} />
      )}
    </div>
  );
}

function ActionButton({ children, onClick, to }) {
  if (to) {
    return (
      <Link to={to} className="ff-btn ff-btn-outline ff-btn-sm no-underline">
        {children}
      </Link>
    );
  }
  return (
    <button type="button" onClick={onClick} className="ff-btn ff-btn-outline ff-btn-sm">
      {children}
    </button>
  );
}

function CheckRow({ stamp, tone, title, children, action }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3.5 gap-y-2 border-b border-dashed border-[var(--rule-2)] py-3">
      <span className="flex w-[84px] shrink-0 justify-center">
        <Stamp tone={tone} size="lg" className="w-[84px]">
          {stamp}
        </Stamp>
      </span>
      <span className="flex min-w-0 flex-[1_1_240px] flex-col gap-0.5">
        <b className="text-[13.5px]">{title}</b>
        <span className="text-[12.5px] text-[var(--ink-2)]">{children}</span>
      </span>
      {action}
    </li>
  );
}

function HealthSections({ data, onReviewUnclassified, onReviewDuplicates }) {
  const { files, duplicates, rules, activity } = data;

  const needsAttention = [];
  if (files.status === "available" && files.unclassified > 0) {
    needsAttention.push(plural(files.unclassified, "unclassified file"));
  }
  if (files.status === "available" && files.errors > 0) {
    needsAttention.push(`${plural(files.errors, "file")} couldn't be read during the last scan`);
  }
  if (rules.status === "available" && rules.conflicts_total > 0) {
    needsAttention.push(
      rules.conflicts_high > 0
        ? `${plural(rules.conflicts_total, "rule conflict")} (${rules.conflicts_high} high severity)`
        : plural(rules.conflicts_total, "rule conflict"),
    );
  }
  if (duplicates.status === "available" && duplicates.groups > 0) {
    needsAttention.push(plural(duplicates.groups, "duplicate group"));
  }

  return (
    <div className="flex flex-col gap-3">
      {needsAttention.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-[4px] border-l-[3px] border-[var(--warn)] bg-[var(--sheet-2)] px-3 py-2.5">
          <span className="ff-kicker">Needs attention</span>
          <span className="text-[12.5px] text-[var(--ink-2)]">{needsAttention.join(" · ")}</span>
        </div>
      )}

      <Kicker>Checks</Kicker>
      <ol className="m-0 flex list-none flex-col p-0">
        {files.status === "unavailable" ? (
          <CheckRow stamp="N/A" tone="muted" title="Classification">
            {files.message || "Not available right now."}
          </CheckRow>
        ) : (
          <CheckRow
            stamp={files.unclassified > 0 ? "Review" : "OK"}
            tone={files.unclassified > 0 ? "warn" : "ok"}
            title={
              files.classification_coverage_percent != null
                ? `${files.classification_coverage_percent}% classified`
                : "No eligible files yet"
            }
            action={<ActionButton onClick={onReviewUnclassified}>Review Unclassified</ActionButton>}
          >
            {plural(files.classified, "classified file")}, {plural(files.unclassified, "unclassified file")}
            {files.errors > 0 && `, ${plural(files.errors, "error")}`}
          </CheckRow>
        )}

        {duplicates.status === "unavailable" ? (
          <CheckRow stamp="N/A" tone="muted" title="Duplicates">
            {duplicates.message || "Not available right now."}
          </CheckRow>
        ) : (
          <CheckRow
            stamp={duplicates.groups > 0 ? "Review" : "OK"}
            tone={duplicates.groups > 0 ? "warn" : "ok"}
            title={plural(duplicates.groups, "group")}
            action={<ActionButton onClick={onReviewDuplicates}>Review Duplicates</ActionButton>}
          >
            {plural(duplicates.duplicate_files, "duplicate file")} · {formatBytes(duplicates.potential_redundant_bytes)}{" "}
            potentially redundant
          </CheckRow>
        )}

        {rules.status === "unavailable" ? (
          <CheckRow stamp="N/A" tone="muted" title="Rules">
            {rules.message || "Not available right now."}
          </CheckRow>
        ) : (
          <CheckRow
            stamp={rules.conflicts_total > 0 ? "Conflict" : "OK"}
            tone={rules.conflicts_total > 0 ? "error" : "ok"}
            title={plural(rules.active, "active rule")}
            action={<ActionButton to="/app/rules">Review Rules</ActionButton>}
          >
            {rules.disabled > 0 && `${plural(rules.disabled, "disabled rule")} · `}
            {rules.conflicts_total > 0 ? plural(rules.conflicts_total, "conflict") : "No conflicts detected"}
          </CheckRow>
        )}

        {activity.status === "unavailable" ? (
          <CheckRow stamp="N/A" tone="muted" title="Recent organization">
            {activity.message || "Not available right now."}
          </CheckRow>
        ) : (
          <CheckRow
            stamp="Logged"
            tone="ink"
            title={`${activity.last_7_days.organized} organized (7d)`}
            action={<ActionButton to="/app/activity">View History</ActionButton>}
          >
            {activity.last_24_hours.organized} today · {activity.last_7_days.skipped} skipped (7d)
          </CheckRow>
        )}

        <CheckRow
          stamp={data.agent_connected ? "Online" : "Local"}
          tone={data.agent_connected ? "ok" : "muted"}
          title={data.agent_connected ? "Remote agent connected" : "No remote agent"}
        >
          {data.agent_connected
            ? "Files are sorted on your own PC; some checks run there."
            : "FileFlow is sorting the folder on this server."}
        </CheckRow>
      </ol>
    </div>
  );
}
