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

function describeCondition(rule) {
  if (!rule) return null;
  switch (rule.rule_type) {
    case "keyword":
      return `Filename contains "${rule.keyword}"`;
    case "content_keyword":
      return `File content contains "${rule.keyword}"`;
    case "regex":
      return `Filename matches pattern ${rule.pattern}`;
    case "extension":
      return `File extension is ${rule.keyword}`;
    case "date":
      return `File is older than ${rule.older_than_days} day${rule.older_than_days === 1 ? "" : "s"}`;
    case "large_file":
      return `File is larger than ${rule.threshold_mb} MB`;
    default:
      return null;
  }
}

function SuggestionCard({ suggestion, creating, onCreateRule, onIgnore }) {
  const extra = suggestion.files_affected - 1;
  const hasRule = suggestion.suggestion_status === "ready" || suggestion.suggestion_status === "low_confidence";

  return (
    <div className="rounded-lg border border-[var(--border)] p-3">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium text-[var(--text-primary)]">
          {suggestion.file_names[0]}
          {extra > 0 && (
            <span className="ml-1 text-xs font-normal text-[var(--text-muted)]">
              + {extra} more
            </span>
          )}
        </span>
        {suggestion.suggestion_status === "low_confidence" && (
          <span className="shrink-0 rounded-full bg-[var(--status-warning)]/10 px-2 py-0.5 text-[10px] font-semibold text-[var(--status-warning)]">
            Low confidence
          </span>
        )}
      </div>

      {hasRule ? (
        <>
          {suggestion.suggested_category && (
            <div className="text-xs text-[var(--text-muted)]">
              Possible type:{" "}
              <span className="font-medium text-[var(--text-secondary)]">
                {suggestion.suggested_category}
              </span>
            </div>
          )}
          {suggestion.suggested_destination && (
            <div className="text-xs text-[var(--text-muted)]">
              Suggested destination:{" "}
              <span className="font-medium text-[var(--text-secondary)]">
                {suggestion.suggested_destination}
              </span>
            </div>
          )}
          {suggestion.reason?.length > 0 && (
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-[var(--text-muted)]">
              {suggestion.reason.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
          {suggestion.suggested_rule && (
            <div className="mt-1 text-xs text-[var(--text-muted)]">
              Suggested rule:{" "}
              <span className="font-medium text-[var(--text-secondary)]">
                {TYPE_LABEL[suggestion.suggested_rule.rule_type]} —{" "}
                {describeCondition(suggestion.suggested_rule)}
              </span>
            </div>
          )}
        </>
      ) : (
        <div className="flex items-start gap-2 text-xs text-[var(--text-muted)]">
          <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{suggestion.message}</span>
        </div>
      )}

      <div className="mt-2 flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={() => onIgnore(suggestion)} disabled={!!creating}>
          Ignore
        </Button>
        {hasRule && suggestion.suggested_rule && (
          <Button
            size="sm"
            onClick={() => onCreateRule(suggestion)}
            disabled={!!creating}
          >
            {creating === suggestion.group_key ? "Creating…" : "Create Rule"}
          </Button>
        )}
      </div>
    </div>
  );
}

export default function UnclassifiedSuggestionsDialog({
  open,
  onOpenChange,
  loading,
  waitingForAgent = false,
  error,
  result,
  ignoredKeys,
  creatingKey,
  onCreateRule,
  onIgnore,
  onClose,
}) {
  const busy = loading || waitingForAgent;
  const visible = (result?.suggestions ?? []).filter((s) => !ignoredKeys?.has(s.group_key));

  return (
    <Dialog open={open} onOpenChange={onOpenChange} disablePointerDismissal>
      <DialogContent
        showCloseButton={false}
        className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[560px]"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-base font-semibold text-[var(--text-primary)]">
            <Sparkles className="h-4 w-4" />
            AI Suggestions
          </DialogTitle>
          <DialogDescription className="text-sm text-[var(--text-secondary)]">
            {waitingForAgent
              ? "Waiting for your agent to scan the watch folder…"
              : loading
                ? "Looking at files with no matching rule…"
                : error
                  ? " "
                  : result
                    ? `${result.unclassified} file${result.unclassified === 1 ? "" : "s"} with no matching rule out of ${result.total} scanned.`
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

        {!busy && !error && result && result.message && (
          <div className="flex items-start gap-2 rounded-lg bg-[var(--status-critical)]/10 px-3 py-2 text-xs font-medium text-[var(--status-critical)]">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{result.message}</span>
          </div>
        )}

        {!busy && !error && result && !result.message && result.unclassified === 0 && (
          <p className="py-8 text-center text-sm text-[var(--text-muted)]">
            Nothing unclassified right now — every file matches a rule.
          </p>
        )}

        {!busy && !error && result && visible.length > 0 && (
          <div className="max-h-96 space-y-2 overflow-y-auto">
            {visible.map((s) => (
              <SuggestionCard
                key={s.group_key}
                suggestion={s}
                creating={creatingKey}
                onCreateRule={onCreateRule}
                onIgnore={onIgnore}
              />
            ))}
          </div>
        )}

        {!busy && !error && result && !result.message && result.unclassified > 0 && visible.length === 0 && (
          <p className="py-8 text-center text-sm text-[var(--text-muted)]">
            All suggestions dismissed.
          </p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
