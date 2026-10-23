import { useEffect, useState } from "react";
import { getAgentCommands } from "../services/api.js";
import Stamp from "./ui/Stamp.jsx";

const ACTION_LABEL = { undo: "Undo", reclassify: "Reclassify" };

function statusLabel(command) {
  if (command.status === "pending") return "Waiting for agent…";
  if (command.success === false) return "Failed";
  return "Completed";
}

const STATUS_TONE = {
  "Waiting for agent…": "warn",
  Failed: "error",
  Completed: "ok",
};

// agent/commands.py's _do_undo() returns only (success, error) -- no result
// dict at all, so a completed undo command's result is always {}. _do_
// reclassify() returns {"destination_path": ...} on success, {} on
// failure. Neither operation is a batch -- each command moves exactly one
// file -- so there is no scanned/organized/error COUNT to show for either
// type, unlike organize_existing. Inventing one (e.g. "1 file") would be a
// fabricated number the backend never actually produced.
function resultText(command) {
  if (command.status !== "done") return "—";
  if (command.success === false) return "Failed";
  if (command.type === "reclassify") {
    const destinationPath = command.result?.destination_path;
    if (!destinationPath) return "—";
    const segments = destinationPath.split(/[\\/]/).filter(Boolean);
    const category = segments.length >= 2 ? segments[segments.length - 2] : null;
    return category ? `Moved to ${category}` : "—";
  }
  if (command.type === "undo") {
    // success=True here reliably means _do_undo's own rename() completed --
    // not a count, just the known, accurate outcome of a successful undo.
    return "Restored";
  }
  return "—";
}

export default function RecentAgentActivity() {
  const [commands, setCommands] = useState(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Two type-filtered requests, not one broad fetch -- an unfiltered,
    // limit-bounded request could easily have its most recent window
    // entirely filled with organize_existing rows on an account that runs
    // the scheduled sweep often, silently hiding real, more recent undo/
    // reclassify activity just outside that window.
    Promise.all([
      getAgentCommands({ type: "undo", limit: 10 }),
      getAgentCommands({ type: "reclassify", limit: 10 }),
    ])
      .then(([undoCommands, reclassifyCommands]) => {
        if (cancelled) return;
        const merged = [...undoCommands, ...reclassifyCommands].sort(
          (a, b) => new Date(b.created_at) - new Date(a.created_at),
        );
        setCommands(merged.slice(0, 10));
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) {
    return <p className="m-0 text-[13px] text-[var(--ink-muted)]">Couldn't load recent activity.</p>;
  }

  if (commands === null) {
    return <p className="m-0 text-[13px] text-[var(--ink-muted)]">Loading…</p>;
  }

  if (commands.length === 0) {
    return <p className="m-0 text-[13px] text-[var(--ink-muted)]">No recent undo/reclassify activity.</p>;
  }

  return (
    <table className="w-full border-collapse border-t border-[var(--ink)] text-[12.5px]" data-testid="recent-agent-activity">
      <thead>
        <tr className="text-left">
          <th className="ff-kicker py-2 pr-4 text-[9.5px] font-semibold">Time</th>
          <th className="ff-kicker py-2 pr-4 text-[9.5px] font-semibold">Action</th>
          <th className="ff-kicker py-2 pr-4 text-[9.5px] font-semibold">Status</th>
          <th className="ff-kicker py-2 text-[9.5px] font-semibold">Result</th>
        </tr>
      </thead>
      <tbody>
        {commands.map((command) => {
          const label = statusLabel(command);
          return (
            <tr key={command.id} className="border-t border-[var(--rule)]">
              <td className="py-2.5 pr-4 font-mono-data text-[11.5px] text-[var(--ink-muted)]">
                {new Date(command.created_at).toLocaleString()}
              </td>
              <td className="py-2.5 pr-4 font-semibold">{ACTION_LABEL[command.type] ?? command.type}</td>
              <td className="py-2.5 pr-4">
                <Stamp tone={STATUS_TONE[label]}>{label}</Stamp>
              </td>
              <td className="py-2.5 font-mono-data text-[12px] text-[var(--ink-2)]">{resultText(command)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
