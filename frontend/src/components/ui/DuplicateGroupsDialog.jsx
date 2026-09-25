import { AlertTriangle, Copy, Database } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog.jsx";
import { Button } from "./button.jsx";
import { formatBytes } from "../../utils/categoryMeta.js";

function DuplicateGroupCard({ group, index, onReviewGroup }) {
  const perFileSize = group.total_size_bytes / group.file_count;

  return (
    <div className="rounded-lg border border-[var(--border)] p-3">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-[var(--text-primary)]">
          Duplicate Group #{index + 1}
        </span>
        <span className="shrink-0 text-xs text-[var(--text-muted)]">
          {group.file_count} identical files · {formatBytes(perFileSize)} each
        </span>
      </div>

      <div className="space-y-1">
        {group.files.map((f, i) => (
          // relative_path is relative to each watch folder, so the same sub-path can
          // exist under two of an account's folders -- the position keeps keys unique.
          <div key={`${f.relative_path}-${i}`} className="truncate text-xs text-[var(--text-secondary)]">
            <span className="font-medium text-[var(--text-primary)]">{f.filename}</span>{" "}
            <span className="text-[var(--text-muted)]">— {f.relative_path}</span>
          </div>
        ))}
      </div>

      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-xs text-[var(--text-muted)]">
          Potential redundant storage: {formatBytes(group.potential_redundant_bytes)}
        </span>
        <Button size="sm" variant="outline" onClick={() => onReviewGroup(group, index)}>
          Review Group
        </Button>
      </div>
    </div>
  );
}

export default function DuplicateGroupsDialog({
  open,
  onOpenChange,
  loading,
  waitingForAgent = false,
  error,
  result,
  onRefresh,
  onReviewGroup,
  onClose,
}) {
  const busy = loading || waitingForAgent;

  return (
    <Dialog open={open} onOpenChange={onOpenChange} disablePointerDismissal>
      <DialogContent showCloseButton={false} className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-base font-semibold text-[var(--text-primary)]">
            <Copy className="h-4 w-4" />
            Duplicate Files
          </DialogTitle>
          <DialogDescription className="text-sm text-[var(--text-secondary)]">
            {waitingForAgent
              ? "Waiting for your agent to scan the watch folder…"
              : loading
                ? "Looking for files with identical content…"
                : error
                  ? " "
                  : result && !result.queued
                    ? `${result.duplicate_groups} duplicate group${result.duplicate_groups === 1 ? "" : "s"} · ${result.duplicate_files} duplicate file${result.duplicate_files === 1 ? "" : "s"}`
                    : " "}
          </DialogDescription>
        </DialogHeader>

        {busy && <p className="py-8 text-center text-sm text-[var(--text-muted)]">Loading…</p>}

        {error && !busy && (
          <div className="flex items-start gap-2 rounded-lg bg-[var(--status-critical)]/10 px-3 py-2 text-xs font-medium text-[var(--status-critical)]">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!busy && !error && result && !result.queued && result.duplicate_groups > 0 && (
          <>
            <div className="flex items-center gap-2 rounded-lg bg-[var(--page)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              <Database className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
              <span>
                Potential redundant storage:{" "}
                <span className="font-medium text-[var(--text-primary)]">
                  {formatBytes(result.potential_redundant_bytes)}
                </span>
              </span>
            </div>
            {result.files_with_errors > 0 && (
              <p className="text-xs text-[var(--text-muted)]">
                {result.files_with_errors} file(s) couldn't be read and were skipped.
              </p>
            )}
            <div className="max-h-80 space-y-2 overflow-y-auto">
              {result.groups.map((g, i) => (
                <DuplicateGroupCard key={g.group_id} group={g} index={i} onReviewGroup={onReviewGroup} />
              ))}
              {result.truncated && (
                <p className="pt-1 text-center text-xs text-[var(--text-muted)]">
                  Showing the first {result.groups.length} of {result.duplicate_groups} groups.
                </p>
              )}
            </div>
          </>
        )}

        {!busy && !error && result && !result.queued && result.duplicate_groups === 0 && (
          <p className="py-8 text-center text-sm text-[var(--text-muted)]">
            No duplicate files found — every file's content is unique.
          </p>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button onClick={onRefresh} disabled={busy}>
            Refresh
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
