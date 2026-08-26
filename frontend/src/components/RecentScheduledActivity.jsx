import { useEffect, useState } from "react";
import { getAgentCommands } from "../services/api.js";

function statusLabel(command) {
  if (command.status === "pending") return "Waiting for agent…";
  if (command.success === false) return "Failed";
  return "Completed";
}

function countCell(command, field) {
  // A pending command, or a completed one whose agent never sent a result
  // (e.g. an older command from before this was tracked), has no count to
  // show -- "--" rather than 0, since 0 is a real, meaningful value for a
  // completed run that genuinely organized nothing.
  if (command.status !== "done") return "—";
  const value = command.result?.[field];
  return value === undefined || value === null ? "—" : value;
}

export default function RecentScheduledActivity() {
  const [commands, setCommands] = useState(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // source: "scheduled" filters out the exact same command type dispatched
    // by a manual "Organize existing files now" click (routes.py) -- both
    // use type "organize_existing", distinguished only by payload.source
    // (see archive_scheduler.py's own comment on why that tag exists).
    getAgentCommands({ type: "organize_existing", source: "scheduled", limit: 10 })
      .then((data) => {
        if (!cancelled) setCommands(data);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) {
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        Couldn't load recent scheduled activity.
      </p>
    );
  }

  if (commands === null) {
    return <p className="text-xs text-[var(--text-muted)]">Loading…</p>;
  }

  if (commands.length === 0) {
    return (
      <p className="text-xs text-[var(--text-secondary)]">
        No scheduled organize activity yet.
      </p>
    );
  }

  return (
    <table className="w-full text-xs" data-testid="recent-scheduled-activity">
      <thead>
        <tr className="text-left text-[var(--text-muted)]">
          <th className="pb-2 pr-4 font-normal">Time</th>
          <th className="pb-2 pr-4 font-normal">Status</th>
          <th className="pb-2 pr-4 font-normal">Organized</th>
          <th className="pb-2 pr-4 font-normal">Duplicates</th>
          <th className="pb-2 font-normal">Errors</th>
        </tr>
      </thead>
      <tbody>
        {commands.map((command) => (
          <tr key={command.id} className="border-t border-[var(--border)]">
            <td className="py-2 pr-4 text-[var(--text-secondary)]">
              {new Date(command.created_at).toLocaleString()}
            </td>
            <td className="py-2 pr-4 text-[var(--text-primary)]">{statusLabel(command)}</td>
            <td className="py-2 pr-4 text-[var(--text-secondary)]">
              {countCell(command, "organized")}
            </td>
            <td className="py-2 pr-4 text-[var(--text-secondary)]">
              {countCell(command, "duplicates")}
            </td>
            <td className="py-2 text-[var(--text-secondary)]">{countCell(command, "errors")}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
