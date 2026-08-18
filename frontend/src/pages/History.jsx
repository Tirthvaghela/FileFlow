import Header from "../components/Header.jsx";
import ActivityTable from "../components/ActivityTable.jsx";
import { CheckCircle2, RotateCcw, Undo2, X } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import { reclassifyLog, undoLastOperation, undoLog } from "../services/api.js";
import { collectKnownFolders } from "../utils/categoryMeta.js";
import { useRules } from "../context/RulesContext.jsx";
import { useMemo, useState } from "react";

// Mirrors the backend's UNDOABLE_ACTIONS -- only these rows can actually be
// undone, so "select all" and bulk-undo both skip anything else silently
// rather than firing a request that can only ever fail.
const UNDOABLE_ACTIONS = ["moved", "renamed_and_moved", "replaced", "archived", "reclassified"];

export default function History() {
  const { logs, refresh } = useLiveLogs(100);
  const { rules } = useRules();
  const [message, setMessage] = useState("");
  const [undoingId, setUndoingId] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  async function handleUndoLast() {
    const result = await undoLastOperation();
    setMessage(result.message);
    refresh();
  }

  async function handleUndoRow(log) {
    if (undoingId) return;
    setUndoingId(log.id);
    try {
      const result = await undoLog(log.id);
      setMessage(result.message);
      refresh();
    } finally {
      setUndoingId(null);
    }
  }

  async function handleReclassify(log, category) {
    const result = await reclassifyLog(log.id, category);
    setMessage(result.message);
    refresh();
  }

  function toggleSelect(logId) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(logId)) next.delete(logId);
      else next.add(logId);
      return next;
    });
  }

  function clearSelection() {
    setSelectedIds(new Set());
  }

  const selectableLogs = useMemo(() => logs.filter((l) => !l.undone), [logs]);
  const allSelected = selectableLogs.length > 0 && selectedIds.size === selectableLogs.length;

  function toggleSelectAll() {
    setSelectedIds(allSelected ? new Set() : new Set(selectableLogs.map((l) => l.id)));
  }

  async function handleBulkUndo() {
    const targets = logs.filter((l) => selectedIds.has(l.id) && UNDOABLE_ACTIONS.includes(l.action));
    if (!targets.length || bulkBusy) return;
    setBulkBusy(true);
    try {
      const results = await Promise.allSettled(targets.map((l) => undoLog(l.id)));
      const succeeded = results.filter((r) => r.status === "fulfilled" && r.value.success).length;
      setMessage(
        succeeded === targets.length
          ? `Undid ${succeeded} operation${succeeded === 1 ? "" : "s"}.`
          : `Undid ${succeeded} of ${targets.length} selected (${targets.length - succeeded} failed).`
      );
      clearSelection();
      refresh();
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleBulkReclassify(category) {
    if (!category) return;
    const targets = logs.filter(
      (l) => selectedIds.has(l.id) && l.destination_path && !l.undone && l.category !== category
    );
    if (!targets.length || bulkBusy) return;
    setBulkBusy(true);
    try {
      const results = await Promise.allSettled(targets.map((l) => reclassifyLog(l.id, category)));
      const succeeded = results.filter((r) => r.status === "fulfilled" && r.value.success).length;
      setMessage(
        succeeded === targets.length
          ? `Moved ${succeeded} file${succeeded === 1 ? "" : "s"} to ${category}.`
          : `Moved ${succeeded} of ${targets.length} selected (${targets.length - succeeded} failed).`
      );
      clearSelection();
      refresh();
    } finally {
      setBulkBusy(false);
    }
  }

  const knownFolders = collectKnownFolders(rules);
  const undoneCount = logs.filter((l) => l.undone).length;
  const activeCount = logs.length - undoneCount;
  const selectedUndoableCount = logs.filter(
    (l) => selectedIds.has(l.id) && UNDOABLE_ACTIONS.includes(l.action)
  ).length;

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
              onClick={handleUndoLast}
              className="flex items-center gap-1.5 rounded-md border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--gridline)]"
            >
              <Undo2 className="h-3.5 w-3.5" />
              Undo last operation
            </button>
          </div>

          {logs.length > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--page)] px-3 py-2 text-xs">
              <label className="flex items-center gap-2 font-medium text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleSelectAll}
                  className="h-4 w-4 rounded border-[var(--border)] accent-[var(--brand)]"
                  disabled={selectableLogs.length === 0}
                />
                Select all
              </label>
              {selectedIds.size > 0 && (
                <>
                  <span className="text-[var(--text-muted)]">{selectedIds.size} selected</span>
                  <button
                    onClick={handleBulkUndo}
                    disabled={bulkBusy || selectedUndoableCount === 0}
                    className="flex items-center gap-1 rounded-md border border-[var(--border)] px-2.5 py-1 font-medium text-[var(--text-primary)] hover:bg-[var(--gridline)] disabled:opacity-50"
                  >
                    <Undo2 className="h-3 w-3" />
                    Undo selected ({selectedUndoableCount})
                  </button>
                  <select
                    value=""
                    onChange={(e) => handleBulkReclassify(e.target.value)}
                    disabled={bulkBusy}
                    className="rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2 py-1 text-[var(--text-secondary)] disabled:opacity-50"
                  >
                    <option value="">Move selected to…</option>
                    {knownFolders.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={clearSelection}
                    className="ml-auto flex items-center gap-1 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  >
                    <X className="h-3 w-3" />
                    Clear
                  </button>
                </>
              )}
            </div>
          )}

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
            onUndo={handleUndoRow}
            undoingId={undoingId}
            allowAnyRowUndo
            onReclassify={handleReclassify}
            categories={knownFolders}
            selectable
            selectedIds={selectedIds}
            onToggleSelect={toggleSelect}
          />
        </motion.div>
      </div>
    </>
  );
}
