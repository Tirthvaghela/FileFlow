import { AlertTriangle, Info, ShieldAlert } from "lucide-react";

export const SEVERITY_META = {
  info: { Icon: Info, color: "var(--text-muted)", label: "Info" },
  warning: { Icon: AlertTriangle, color: "var(--status-warning)", label: "Warning" },
  high: { Icon: ShieldAlert, color: "var(--status-critical)", label: "High" },
};

export default function RuleConflictCard({ conflict }) {
  const { Icon, color } = SEVERITY_META[conflict.severity] || SEVERITY_META.info;

  return (
    <div className="rounded-lg border border-[var(--border)] p-3">
      <div className="mb-1.5 flex items-center gap-2">
        <Icon className="h-3.5 w-3.5 shrink-0" style={{ color }} />
        <span className="text-xs font-medium text-[var(--text-secondary)]">
          {conflict.rules.map((r) => r.description).join("  vs.  ")}
        </span>
      </div>

      <p className="text-xs text-[var(--text-muted)]">{conflict.message}</p>

      {conflict.example && (conflict.example.filename || conflict.example.destination) && (
        <div className="mt-2 rounded-md bg-[var(--page)] px-2.5 py-1.5 text-xs">
          {conflict.example.filename && (
            <div className="text-[var(--text-secondary)]">
              Example: <span className="font-medium">{conflict.example.filename}</span>
            </div>
          )}
          {conflict.example.destination && (
            <div className="text-[var(--text-secondary)]">
              Result: <span className="font-medium">{conflict.example.destination}</span>
              {conflict.example.winning_rule && (
                <span className="text-[var(--text-muted)]"> ({conflict.example.winning_rule})</span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
