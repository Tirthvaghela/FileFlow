import { Inbox } from "lucide-react";

export default function EmptyState({ icon: Icon = Inbox, message, action }) {
  return (
    <div className="flex h-[260px] flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-[var(--border)] bg-[var(--surface-1)]/40 px-6 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[var(--gridline)] text-[var(--text-muted)]">
        <Icon className="h-5 w-5" />
      </span>
      <p className="max-w-xs text-sm text-[var(--text-muted)]">{message}</p>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="text-sm font-medium text-[var(--brand)] hover:underline"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
