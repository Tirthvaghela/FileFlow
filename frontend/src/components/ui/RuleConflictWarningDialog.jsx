import { AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog.jsx";
import { Button } from "./button.jsx";
import RuleConflictCard from "./RuleConflictCard.jsx";

// Pre-save gate (Feature 5, Phase 12/17): shown only when saving the
// pending rule would leave at least one warning/high-severity conflict in
// place. Purely advisory -- FileFlow's real classifier already decided
// what actually happens; this dialog only explains it before the user
// commits. [Save Anyway] calls the exact same save path [Back & Edit]
// leaves untouched (see Rules.jsx) -- there is no separate "safe save"
// mechanism.
export default function RuleConflictWarningDialog({ open, onOpenChange, conflicts, saving, onBack, onSaveAnyway }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange} disablePointerDismissal>
      <DialogContent showCloseButton={false} className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-base font-semibold text-[var(--text-primary)]">
            <AlertTriangle className="h-4 w-4" style={{ color: "var(--status-warning)" }} />
            Rule Conflict Detected
          </DialogTitle>
          <DialogDescription className="text-sm text-[var(--text-secondary)]">
            This rule overlaps with one you already have. FileFlow won't stop you from saving it --
            here's what would actually happen.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-80 space-y-2 overflow-y-auto">
          {(conflicts || []).map((c, i) => (
            <RuleConflictCard key={i} conflict={c} />
          ))}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onBack} disabled={saving}>
            Back &amp; Edit
          </Button>
          <Button onClick={onSaveAnyway} disabled={saving}>
            {saving ? "Saving…" : "Save Anyway"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
