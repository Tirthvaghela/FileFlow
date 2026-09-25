import { Info, ShieldCheck } from "lucide-react";
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

const DUPLICATE_TYPE_LABEL = {
  exact_content_duplicate: "Exact content duplicates",
};

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

// Review-only detail view (Phase 20): every copy, its location, and an
// explicit confirmation that nothing has been deleted. No delete/move/
// rename/replace action is ever offered here or anywhere in this dialog.
export default function DuplicateGroupDetailDialog({ open, onOpenChange, group, groupNumber, onClose }) {
  if (!group) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange} disablePointerDismissal>
      <DialogContent showCloseButton={false} className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle className="font-display text-base font-semibold text-[var(--text-primary)]">
            Duplicate Group #{groupNumber}
          </DialogTitle>
          <DialogDescription className="text-sm text-[var(--text-secondary)]">
            {DUPLICATE_TYPE_LABEL[group.duplicate_type] || group.duplicate_type}
          </DialogDescription>
        </DialogHeader>

        <div className="text-xs text-[var(--text-muted)]">
          {group.file_count} files · {formatBytes(group.total_size_bytes)} total
        </div>

        <div className="max-h-64 space-y-2 overflow-y-auto">
          {group.files.map((f, i) => (
            // Same reasoning as DuplicateGroupsDialog: relative_path alone can repeat
            // across an account's watch folders.
            <div key={`${f.relative_path}-${i}`} className="rounded-lg border border-[var(--border)] p-2.5">
              <div className="truncate text-sm font-medium text-[var(--text-primary)]">{f.filename}</div>
              <div className="text-xs text-[var(--text-muted)]">{f.relative_path}</div>
              <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--text-muted)]">
                <span>{formatBytes(f.size_bytes)}</span>
                <span>·</span>
                <span>{formatDate(f.modified_at)}</span>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-start gap-2 rounded-lg bg-[var(--page)] px-3 py-2 text-xs text-[var(--text-secondary)]">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            Why? All {group.file_count} files have identical SHA-256 content hashes.
            <br />
            Potential redundant storage: {formatBytes(group.potential_redundant_bytes)}.
          </span>
        </div>

        <div className="flex items-center gap-2 rounded-lg bg-[var(--status-good)]/10 px-3 py-2 text-xs font-medium text-[var(--status-good)]">
          <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
          <span>No files have been deleted.</span>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
