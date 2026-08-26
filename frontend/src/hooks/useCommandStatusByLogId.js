import { useCallback, useEffect, useState } from "react";
import { getAgentCommands } from "../services/api.js";

// Builds a { [log_id]: command } lookup from the most recent undo/
// reclassify agent commands, so a History row can show its own real
// agent-command status (pending/completed/failed) instead of nothing.
// log_id is the correlation key: routes.py's undo/reclassify dispatch
// routes always pass payload.log_id = the exact activity_log row id the
// action targets, and GET /api/agent-commands surfaces it as a top-level
// field for exactly this purpose (see its own docstring).
//
// The same log_id can have more than one command over time (a file
// reclassified twice, or reclassified then undone) -- both fetches come
// back newest-first from the backend, and this merge keeps the first
// (i.e. newest) command seen per log_id, so the row always reflects
// "what did I most recently do to this file, and is it done yet."
//
// No polling: refetch happens on mount and whenever the caller invokes
// `refresh` (History.jsx calls it right after dispatching an undo/
// reclassify, alongside its own existing logs refresh). There is no
// websocket broadcast or periodic refresh for agent_commands to piggyback
// on today, and "click, then later return to this row" -- the task's own
// framing -- is already satisfied by refetch-on-mount without needing a
// continuous poll while the page stays open.
export function useCommandStatusByLogId(limit = 100) {
  const [commandStatusByLogId, setCommandStatusByLogId] = useState({});
  const [commandStatusLoadError, setCommandStatusLoadError] = useState(false);

  const refresh = useCallback(() => {
    Promise.all([
      getAgentCommands({ type: "undo", limit }),
      getAgentCommands({ type: "reclassify", limit }),
    ])
      .then(([undoCommands, reclassifyCommands]) => {
        const merged = [...undoCommands, ...reclassifyCommands].sort((a, b) => b.id - a.id);
        const next = {};
        for (const command of merged) {
          if (command.log_id == null) continue;
          if (!(command.log_id in next)) next[command.log_id] = command;
        }
        setCommandStatusByLogId(next);
        setCommandStatusLoadError(false);
      })
      .catch(() => setCommandStatusLoadError(true));
  }, [limit]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { commandStatusByLogId, commandStatusLoadError, refreshCommandStatus: refresh };
}
