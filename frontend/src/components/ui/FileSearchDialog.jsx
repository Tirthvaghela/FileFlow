import { AlertTriangle, HelpCircle, Search } from "lucide-react";
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

function formatDate(iso) {
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return iso;
  }
}

function SearchResultCard({ item }) {
  return (
    <div className="rounded-lg border border-[var(--border)] p-3">
      <div className="truncate text-sm font-medium text-[var(--text-primary)]">{item.filename}</div>
      <div className="text-xs text-[var(--text-muted)]">{item.relative_path}</div>
      <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--text-muted)]">
        <span>{formatBytes(item.size_bytes)}</span>
        <span>·</span>
        <span>{formatDate(item.modified_at)}</span>
        {item.category && (
          <>
            <span>·</span>
            <span>{item.category}</span>
          </>
        )}
      </div>
      {item.match_reasons?.length > 0 && (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-xs text-[var(--text-muted)]">
          {item.match_reasons.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

// A compact search surface -- natural language in, deterministic results
// out. Deliberately not a chatbot: one input, one button, a checklist of
// what was interpreted, and a plain list of matched files.
export default function FileSearchDialog({
  open,
  onOpenChange,
  prompt,
  onPromptChange,
  searching,
  waitingForAgent = false,
  result,
  error,
  onSearch,
  onClear,
  onClose,
}) {
  const busy = searching || waitingForAgent;

  function handleSubmit(e) {
    e.preventDefault();
    if (!busy && prompt.trim()) onSearch();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange} disablePointerDismissal>
      <DialogContent showCloseButton={false} className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-base font-semibold text-[var(--text-primary)]">
            <Search className="h-4 w-4" />
            Search your files
          </DialogTitle>
          <DialogDescription className="text-sm text-[var(--text-secondary)]">
            Search by filename, type, size, date, or location -- FileFlow doesn't read file
            contents.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            placeholder="Find PDF invoices from August"
            disabled={busy}
            className="w-full rounded-md border border-[var(--border)] bg-[var(--page)] px-2.5 py-1.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)]"
          />
          <Button type="submit" disabled={busy || !prompt.trim()}>
            {busy ? "Searching…" : "Search"}
          </Button>
        </form>

        {waitingForAgent && (
          <p className="py-4 text-center text-sm text-[var(--text-muted)]">
            Waiting for your agent to search the watch folder…
          </p>
        )}
        {searching && !waitingForAgent && (
          <p className="py-4 text-center text-sm text-[var(--text-muted)]">Searching…</p>
        )}

        {error && !busy && (
          <div className="flex items-start gap-2 rounded-lg bg-[var(--status-critical)]/10 px-3 py-2 text-xs font-medium text-[var(--status-critical)]">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!busy && !error && result && result.status !== "ready" && (
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

        {!busy && !error && result && result.status === "ready" && !result.queued && (
          <>
            {result.interpretation?.length > 0 && (
              <div className="rounded-lg border border-[var(--border)] bg-[var(--page)] p-3 text-xs">
                <div className="mb-1 font-medium text-[var(--text-secondary)]">Search interpretation:</div>
                <ul className="space-y-0.5 text-[var(--text-muted)]">
                  {result.interpretation.map((line, i) => (
                    <li key={i}>✓ {line}</li>
                  ))}
                </ul>
              </div>
            )}

            {result.total_matches === 0 ? (
              <p className="py-6 text-center text-sm text-[var(--text-muted)]">
                No files matched your search.
              </p>
            ) : (
              <>
                <div className="text-xs text-[var(--text-muted)]">
                  {result.total_matches} result{result.total_matches === 1 ? "" : "s"}
                </div>
                <div className="max-h-80 space-y-2 overflow-y-auto">
                  {result.results.map((item, i) => (
                    // relative_path is relative to each watch folder, so it can repeat
                    // across an account's watch folders -- the position keeps keys unique.
                    <SearchResultCard key={`${item.relative_path}-${i}`} item={item} />
                  ))}
                  {result.truncated && (
                    <p className="pt-1 text-center text-xs text-[var(--text-muted)]">
                      Showing the first {result.returned} of {result.total_matches} results.
                    </p>
                  )}
                </div>
              </>
            )}
          </>
        )}

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClear} disabled={busy}>
            Clear Search
          </Button>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
