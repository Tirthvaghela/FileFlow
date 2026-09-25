import { AlertTriangle, CheckCircle2, Copy, HelpCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog.jsx";
import { Button } from "./button.jsx";

const STATUS_META = {
  ready: { label: "Ready to move", color: "var(--status-good)", icon: CheckCircle2 },
  duplicate: { label: "Skipped", color: "var(--status-warning)", icon: Copy },
  no_match: { label: "No matching rule", color: "var(--text-muted)", icon: HelpCircle },
  error: { label: "Error", color: "var(--status-critical)", icon: AlertTriangle },
};

const SECTION_ORDER = [
  { status: "ready", heading: "Ready to move" },
  { status: "duplicate", heading: "Skipped" },
  { status: "no_match", heading: "No match" },
  { status: "error", heading: "Errors" },
];

function PreviewItemRow({ item }) {
  const meta = STATUS_META[item.status] || STATUS_META.error;
  const Icon = meta.icon;
  return (
    <div className="flex items-start gap-2.5 py-2">
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: meta.color }} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-[var(--text-primary)]">
          {item.filename}
        </div>
        {item.status === "ready" && item.category && (
          <div className="truncate text-xs text-[var(--text-muted)]">→ {item.category}</div>
        )}
        {item.status === "duplicate" && (
          <div className="text-xs text-[var(--text-muted)]">
            Duplicate — already exists in {item.category || "the destination folder"}
          </div>
        )}
        {item.status === "no_match" && (
          <div className="text-xs text-[var(--text-muted)]">
            No matching rule{item.category ? ` — will go to ${item.category}` : ""}
          </div>
        )}
        {item.status === "error" && (
          <div className="text-xs text-[var(--status-critical)]">{item.error}</div>
        )}
        {item.explanation?.rule_name && (
          <div className="text-xs text-[var(--text-muted)]">Why: {item.explanation.rule_name}</div>
        )}
      </div>
    </div>
  );
}

export default function OrganizePreviewDialog({
  open,
  onOpenChange,
  loading,
  waitingForAgent = false,
  error,
  preview,
  confirming,
  onCancel,
  onConfirm,
}) {
  const busy = loading || waitingForAgent;
  const items = preview?.items ?? [];
  const byStatus = SECTION_ORDER.map(({ status, heading }) => ({
    heading,
    status,
    items: items.filter((i) => i.status === status),
  })).filter((section) => section.items.length > 0);

  // Duplicates and errors are the only two outcomes where a file genuinely
  // does not get moved -- a "no match" file still lands in the account's
  // default category, so it counts toward what confirming will actually do.
  const actionable = preview ? preview.total - preview.duplicates - preview.errors : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange} disablePointerDismissal>
      <DialogContent
        showCloseButton={false}
        className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[560px]"
      >
        <DialogHeader>
          <DialogTitle className="font-display text-base font-semibold text-[var(--text-primary)]">
            Organization Preview
          </DialogTitle>
          <DialogDescription className="text-sm text-[var(--text-secondary)]">
            {waitingForAgent
              ? "Waiting for your agent to scan the watch folder…"
              : loading
                ? "Scanning your watch folder…"
                : error
                  ? " "
                  : preview
                    ? `${preview.total} file${preview.total === 1 ? "" : "s"} detected. Nothing has been moved yet.`
                    : " "}
          </DialogDescription>
        </DialogHeader>

        {busy && <p className="py-8 text-center text-sm text-[var(--text-muted)]">Loading…</p>}

        {error && !busy && (
          <p className="rounded-lg bg-[var(--status-critical)]/10 px-3 py-2 text-xs font-medium text-[var(--status-critical)]">
            {error}
          </p>
        )}

        {!busy && !error && preview && preview.total === 0 && (
          <p className="py-8 text-center text-sm text-[var(--text-muted)]">
            Nothing to organize — the watch folder has no loose files right now.
          </p>
        )}

        {!busy && !error && preview && preview.total > 0 && (
          <>
            <div className="max-h-80 overflow-y-auto rounded-lg border border-[var(--border)] px-3">
              {byStatus.map((section) => (
                <div key={section.status}>
                  <div className="sticky top-0 bg-[var(--surface-1)] py-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                    {section.heading} ({section.items.length})
                  </div>
                  <div className="divide-y divide-[var(--border)]">
                    {section.items.map((item) => (
                      <PreviewItemRow key={item.source_path} item={item} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <p className="text-xs text-[var(--text-muted)]">
              {preview.total} total · {preview.ready} ready · {preview.duplicates} skipped ·{" "}
              {preview.no_match} no match
              {preview.errors > 0 && ` · ${preview.errors} error${preview.errors === 1 ? "" : "s"}`}
            </p>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={confirming}>
            Cancel
          </Button>
          <Button
            onClick={onConfirm}
            disabled={busy || !!error || confirming || !preview || actionable === 0}
          >
            {confirming ? "Organizing…" : `Organize ${actionable} File${actionable === 1 ? "" : "s"}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
