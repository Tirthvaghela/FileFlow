import { AlertTriangle, HelpCircle, Sparkles } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog.jsx";
import { Button } from "./button.jsx";

const TYPE_LABEL = {
  keyword: "Filename keyword",
  content_keyword: "Content keyword",
  regex: "Regex pattern",
  extension: "Extension",
  date: "File age",
  large_file: "File size",
};

// Purely a display-side rendering of the proposal's own fields -- nothing
// here is guessed or re-interpreted, it's the same data the [Save Rule]
// button acts on. Kept visually and conceptually distinct from Feature 1's
// per-file "Why did this go here?" explanation (ActivityTable.jsx): this is
// "what did the AI turn my request into", not "why did a specific file
// match".
function describeCondition(proposal) {
  switch (proposal.rule_type) {
    case "keyword":
      return `Filename contains "${proposal.keyword}"`;
    case "content_keyword":
      return `File content contains "${proposal.keyword}"`;
    case "regex":
      return `Filename matches pattern ${proposal.pattern}`;
    case "extension":
      return `File extension is ${proposal.keyword}`;
    case "date":
      return `File is older than ${proposal.older_than_days} day${proposal.older_than_days === 1 ? "" : "s"}`;
    case "large_file":
      return `File is larger than ${proposal.threshold_mb} MB`;
    default:
      return null;
  }
}

const inputClass =
  "w-full rounded-md border border-[var(--border)] bg-[var(--page)] px-2.5 py-1.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)]";

export default function AIRuleGeneratorDialog({
  open,
  onOpenChange,
  prompt,
  onPromptChange,
  generating,
  result,
  error,
  saving,
  impact,
  checkingImpact,
  onGenerate,
  onCheckImpact,
  onEditRequest,
  onEdit,
  onReject,
  onSaveRule,
}) {
  const showForm = !result && !error;
  const proposal = result?.status === "ready" ? result.proposal : null;

  function handleClose(next) {
    if (!next) onReject();
    onOpenChange(next);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-base font-semibold text-[var(--text-primary)]">
            <Sparkles className="h-4 w-4" />
            Create rule with AI
          </DialogTitle>
          <DialogDescription className="text-sm text-[var(--text-secondary)]">
            Describe what you want FileFlow to do. This only proposes a rule -- nothing is saved
            until you review it.
          </DialogDescription>
        </DialogHeader>

        {showForm && (
          <div>
            <textarea
              value={prompt}
              onChange={(e) => onPromptChange(e.target.value)}
              placeholder="Put invoices containing GST into Finance/Invoices"
              rows={3}
              disabled={generating}
              className={`${inputClass} resize-none`}
            />
            <p className="mt-1 text-xs text-[var(--text-muted)]">
              FileFlow can match on filename keyword, file content keyword, regex pattern,
              extension, file age, or file size.
            </p>
          </div>
        )}

        {generating && (
          <p className="py-6 text-center text-sm text-[var(--text-muted)]">
            Interpreting your request…
          </p>
        )}

        {error && !generating && (
          <div className="rounded-lg bg-[var(--status-critical)]/10 px-3 py-2 text-xs font-medium text-[var(--status-critical)]">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{error}</span>
            </div>
          </div>
        )}

        {!generating && result && result.status !== "ready" && (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--page)] p-3 text-sm">
            <div className="flex items-start gap-2 text-[var(--text-primary)]">
              <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
              <span>{result.message}</span>
            </div>
            {result.status === "needs_clarification" && result.questions?.length > 0 && (
              <ul className="mt-2 list-disc space-y-1 pl-8 text-xs text-[var(--text-muted)]">
                {result.questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            )}
          </div>
        )}

        {!generating && proposal && (
          <div className="space-y-3">
            <div className="rounded-lg border border-[var(--border)] bg-[var(--page)] p-3 text-xs text-[var(--text-muted)]">
              <span className="font-medium text-[var(--text-secondary)]">You asked:</span> "{prompt}"
              <div className="mt-1">
                <span className="font-medium text-[var(--text-secondary)]">Interpreted as:</span>{" "}
                {describeCondition(proposal)} → moves to{" "}
                <span className="font-medium text-[var(--text-primary)]">{proposal.destination}</span>
              </div>
            </div>

            <div className="rounded-lg border border-[var(--border)] p-3">
              <div className="mb-2 text-sm font-semibold text-[var(--text-primary)]">
                {proposal.name}
              </div>
              <div className="space-y-1 text-xs">
                <div className="text-[var(--text-muted)]">
                  Type:{" "}
                  <span className="font-medium text-[var(--text-secondary)]">
                    {TYPE_LABEL[proposal.rule_type] || proposal.rule_type}
                  </span>
                </div>
                <div className="text-[var(--text-muted)]">
                  Condition:{" "}
                  <span className="font-medium text-[var(--text-secondary)]">
                    {describeCondition(proposal)}
                  </span>
                </div>
                <div className="text-[var(--text-muted)]">
                  Destination:{" "}
                  <span className="font-medium text-[var(--text-secondary)]">
                    {proposal.destination}
                  </span>
                </div>
              </div>
            </div>

            <div>
              <button
                type="button"
                onClick={onCheckImpact}
                disabled={checkingImpact}
                className="text-xs font-medium text-[var(--text-secondary)] underline decoration-dotted underline-offset-2 hover:text-[var(--text-primary)] disabled:opacity-50"
              >
                {checkingImpact ? "Checking impact…" : "Check impact before saving"}
              </button>
              {impact && (
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  {impact.error
                    ? "Couldn't check impact."
                    : impact.compared_count - impact.unchanged_count === 0
                      ? `No changes to your last ${impact.compared_count} organized file${impact.compared_count === 1 ? "" : "s"}.`
                      : `${impact.compared_count - impact.unchanged_count} of ${impact.compared_count} recent files would be reclassified differently.`}
                </p>
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          {showForm || generating ? (
            <Button onClick={onGenerate} disabled={generating || !prompt.trim()}>
              {generating ? "Generating…" : "Generate Rule"}
            </Button>
          ) : proposal ? (
            <>
              <Button variant="outline" onClick={onReject} disabled={saving}>
                Reject
              </Button>
              <Button variant="outline" onClick={() => onEdit(proposal)} disabled={saving}>
                Edit
              </Button>
              <Button onClick={() => onSaveRule(proposal)} disabled={saving}>
                {saving ? "Saving…" : "Save Rule"}
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={onEditRequest}>
              Edit request
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
