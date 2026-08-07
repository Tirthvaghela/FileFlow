import Header from "../components/Header.jsx";
import ActivityTable from "../components/ActivityTable.jsx";
import { CheckCircle2, RotateCcw, Undo2 } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
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
  const undoneCount = logs.filter((l) => l.undone).length;
  const activeCount = logs.length - undoneCount;

  return (
    <>
      <Header title="History" subtitle="Reversible operation timeline" />
      <div className="p-8">
        <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-2">
          {[
            { label: "Still in place", value: activeCount, icon: CheckCircle2, color: "var(--status-good)" },
            { label: "Undone", value: undoneCount, icon: RotateCcw, color: "var(--text-muted)" },
          ].map((stat, i) => (
            <motion.div
              key={stat.label}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: i * 0.06, ease: "easeOut" }}
              className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 shadow-sm"
            >
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                style={{ color: stat.color, background: `color-mix(in srgb, ${stat.color} 14%, transparent)` }}
              >
                <stat.icon className="h-[18px] w-[18px]" />
              </span>
              <div>
                <div className="text-lg font-semibold text-[var(--text-primary)]">{stat.value}</div>
                <div className="text-xs text-[var(--text-muted)]">{stat.label}</div>
              </div>
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.1, ease: "easeOut" }}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm"
        >
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
          <AnimatePresence>
            {message && (
              <motion.p
                key={message}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="mb-3 rounded-lg bg-[var(--brand)]/10 px-3 py-2 text-xs font-medium text-[var(--brand)]"
              >
                {message}
              </motion.p>
            )}
          </AnimatePresence>
          <ActivityTable
            logs={logs}
            showStatusBadge
            onReclassify={handleReclassify}
            categories={knownFolders}
          />
        </motion.div>
      </div>
    </>
  );
}
