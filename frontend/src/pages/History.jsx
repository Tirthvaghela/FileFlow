import Header from "../components/Header.jsx";
import ActivityTable from "../components/ActivityTable.jsx";
import { Undo2 } from "lucide-react";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import { reclassifyLog, undoLastOperation } from "../services/api.js";
import { collectKnownFolders } from "../utils/categoryMeta.js";
import { useRules } from "../context/RulesContext.jsx";
import { useState } from "react";

export default function History() {
  const { logs, refresh } = useLiveLogs(100);
  const { rules } = useRules();
  const [message, setMessage] = useState("");

  async function handleUndo() {
    const result = await undoLastOperation();
    setMessage(result.message);
    refresh();
  }

  async function handleReclassify(log, category) {
    const result = await reclassifyLog(log.id, category);
    setMessage(result.message);
    refresh();
  }

  const knownFolders = collectKnownFolders(rules);

  return (
    <>
      <Header title="History" subtitle="Reversible operation timeline" />
      <div className="p-8">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-medium text-[var(--text-primary)]">
                Operation history
              </h2>
              <p className="text-xs text-[var(--text-muted)]">
                Every automated action is reversible.
              </p>
            </div>
            <button
              onClick={handleUndo}
              className="flex items-center gap-1.5 rounded-md border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--gridline)]"
            >
              <Undo2 className="h-3.5 w-3.5" />
              Undo last operation
            </button>
          </div>
          {message && (
            <p className="mb-3 text-xs text-[var(--text-muted)]">{message}</p>
          )}
          <ActivityTable
            logs={logs}
            showStatusBadge
            onReclassify={handleReclassify}
            categories={knownFolders}
          />
        </div>
      </div>
    </>
  );
}
