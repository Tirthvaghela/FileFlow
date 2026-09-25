import { Link } from "react-router-dom";
import { AlertTriangle, HeartPulse } from "lucide-react";
import { Button } from "./button.jsx";
import { formatBytes } from "../../utils/categoryMeta.js";

function plural(n, noun) {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

function formatUpdatedAt(iso) {
  try {
    return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  } catch {
    return null;
  }
}

// A compact, deterministic overview of FileFlow's existing capabilities --
// classification coverage, duplicate groups, rule conflicts, and recent
// activity. Every number here is read straight from GET
// /api/health/organization (backend/services/health_service.py), which
// only ever aggregates Features 1-7's own already-computed results. This
// component never calls AI, never triggers a duplicate/rule scan itself,
// and never offers a destructive action -- it only links to the existing
// features that already do those things.
export default function HealthDashboard({
  data,
  loading,
  error,
  refreshing,
  onRefresh,
  onReviewUnclassified,
  onReviewDuplicates,
}) {
  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <HeartPulse className="h-4 w-4 text-[var(--brand)]" />
          <h2 className="text-sm font-medium text-[var(--text-primary)]">FileFlow Health</h2>
          {data?.generated_at && (
            <span className="text-xs text-[var(--text-muted)]">
              Updated {formatUpdatedAt(data.generated_at) ?? "just now"}
            </span>
          )}
        </div>
        <Button
          variant="outline"
          onClick={onRefresh}
          disabled={loading || refreshing}
          className="!px-3 !py-1.5 !text-xs"
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {loading && !data && (
        <p className="py-6 text-center text-sm text-[var(--text-muted)]">Loading workspace health…</p>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-lg bg-[var(--status-critical)]/10 px-3 py-2 text-xs font-medium text-[var(--status-critical)]">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {data && !error && (
        <HealthSections
          data={data}
          onReviewUnclassified={onReviewUnclassified}
          onReviewDuplicates={onReviewDuplicates}
        />
      )}
    </div>
  );
}

function SectionCard({ title, children }) {
  return (
    <div className="rounded-xl border border-[var(--border)] p-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">{title}</h3>
      {children}
    </div>
  );
}

function Unavailable({ message }) {
  return <p className="text-xs text-[var(--text-muted)]">{message || "Not available right now."}</p>;
}

function HealthSections({ data, onReviewUnclassified, onReviewDuplicates }) {
  const { files, duplicates, rules, activity } = data;

  const needsAttention = [];
  if (files.status === "available" && files.unclassified > 0) {
    needsAttention.push({
      key: "unclassified",
      label: `${plural(files.unclassified, "unclassified file")}`,
      actionLabel: "Review Unclassified",
      onClick: onReviewUnclassified,
    });
  }
  if (files.status === "available" && files.errors > 0) {
    needsAttention.push({
      key: "errors",
      label: `${plural(files.errors, "file")} couldn't be read during the last scan`,
    });
  }
  if (rules.status === "available" && rules.conflicts_total > 0) {
    needsAttention.push({
      key: "conflicts",
      label:
        rules.conflicts_high > 0
          ? `${plural(rules.conflicts_total, "rule conflict")} (${rules.conflicts_high} high severity)`
          : plural(rules.conflicts_total, "rule conflict"),
      actionLabel: "Review Rules",
      to: "/app/rules",
    });
  }
  if (duplicates.status === "available" && duplicates.groups > 0) {
    needsAttention.push({
      key: "duplicates",
      label: plural(duplicates.groups, "duplicate group"),
      actionLabel: "Review Duplicates",
      onClick: onReviewDuplicates,
    });
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SectionCard title="Classification">
          {files.status === "unavailable" ? (
            <Unavailable message={files.message} />
          ) : (
            <>
              <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-[var(--gridline)]">
                <div
                  className="h-full rounded-full bg-[var(--brand)]"
                  style={{ width: `${files.classification_coverage_percent ?? 0}%` }}
                />
              </div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {files.classification_coverage_percent != null
                  ? `${files.classification_coverage_percent}% classified`
                  : "No eligible files yet"}
              </p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                {plural(files.classified, "classified file")}, {plural(files.unclassified, "unclassified file")}
                {files.errors > 0 && `, ${plural(files.errors, "error")}`}
              </p>
              <button
                type="button"
                onClick={onReviewUnclassified}
                className="mt-2 text-xs font-medium text-[var(--brand)] hover:underline"
              >
                Review Unclassified
              </button>
            </>
          )}
        </SectionCard>

        <SectionCard title="Duplicates">
          {duplicates.status === "unavailable" ? (
            <Unavailable message={duplicates.message} />
          ) : (
            <>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {plural(duplicates.groups, "group")}
              </p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                {plural(duplicates.duplicate_files, "duplicate file")} ·{" "}
                {formatBytes(duplicates.potential_redundant_bytes)} potentially redundant
              </p>
              <button
                type="button"
                onClick={onReviewDuplicates}
                className="mt-2 text-xs font-medium text-[var(--brand)] hover:underline"
              >
                Review Duplicates
              </button>
            </>
          )}
        </SectionCard>

        <SectionCard title="Rules">
          {rules.status === "unavailable" ? (
            <Unavailable message={rules.message} />
          ) : (
            <>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {plural(rules.active, "active rule")}
              </p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                {rules.disabled > 0 && `${plural(rules.disabled, "disabled rule")} · `}
                {rules.conflicts_total > 0
                  ? plural(rules.conflicts_total, "conflict")
                  : "No conflicts detected"}
              </p>
              <Link to="/app/rules" className="mt-2 inline-block text-xs font-medium text-[var(--brand)] hover:underline">
                Review Rules
              </Link>
            </>
          )}
        </SectionCard>

        <SectionCard title="Recent Organization">
          {activity.status === "unavailable" ? (
            <Unavailable message={activity.message} />
          ) : (
            <>
              <p className="text-sm font-semibold text-[var(--text-primary)]">
                {activity.last_7_days.organized} organized (7d)
              </p>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                {activity.last_24_hours.organized} today · {activity.last_7_days.skipped} skipped (7d)
              </p>
              <Link
                to="/app/activity"
                className="mt-2 inline-block text-xs font-medium text-[var(--brand)] hover:underline"
              >
                View History
              </Link>
            </>
          )}
        </SectionCard>
      </div>

      {needsAttention.length > 0 && (
        <div className="rounded-xl border border-[var(--status-warning)]/30 bg-[var(--status-warning)]/5 p-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--status-warning)]">
            Needs Attention
          </h3>
          <ul className="space-y-1.5">
            {needsAttention.map((item) => (
              <li key={item.key} className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <span className="text-[var(--text-secondary)]">
                  <span aria-hidden="true">⚠</span> {item.label}
                </span>
                {item.to && (
                  <Link to={item.to} className="font-medium text-[var(--brand)] hover:underline">
                    {item.actionLabel}
                  </Link>
                )}
                {item.onClick && (
                  <button
                    type="button"
                    onClick={item.onClick}
                    className="font-medium text-[var(--brand)] hover:underline"
                  >
                    {item.actionLabel}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
