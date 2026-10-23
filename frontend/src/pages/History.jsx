import { Fragment, useMemo, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import ExplanationPanel from "../components/ExplanationPanel.jsx";
import Stamp from "../components/ui/Stamp.jsx";
import FolderTag from "../components/ui/FolderTag.jsx";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import { useCommandStatusByLogId } from "../hooks/useCommandStatusByLogId.js";
import { reclassifyLog, undoLastOperation, undoLog } from "../services/api.js";
import { collectKnownFolders } from "../utils/categoryMeta.js";
import { dayHeading, folderName, operationTitle, stampFor, UNDOABLE_ACTIONS } from "../utils/activity.js";
import { useRules } from "../context/RulesContext.jsx";

const DOT = {
  filed: "var(--filed)",
  duplicate: "var(--warn)",
  archived: "var(--ink-2)",
  refiled: "var(--ink)",
  undone: "var(--rule-2)",
  error: "var(--stamp)",
};

function agentLabel(command) {
  if (!command) return null;
  if (command.status === "pending") return { label: "Waiting for agent…", tone: "warn" };
  if (command.success === false) return { label: "Failed", tone: "error" };
  return { label: "Completed", tone: "ok" };
}

export default function History() {
  const { logs, refresh } = useLiveLogs(100);
  const { commandStatusByLogId, refreshCommandStatus } = useCommandStatusByLogId();
  const { rules } = useRules();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [undoingId, setUndoingId] = useState(null);
  const [undoingLast, setUndoingLast] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [whyId, setWhyId] = useState(null);

  async function handleUndoLast() {
    // The backend only guards two calls racing on the *same* undo, so an
    // unguarded second click here would undo the next operation back too.
    if (undoingLast) return;
    setUndoingLast(true);
    setError("");
    try {
      const result = await undoLastOperation();
      setMessage(result.message);
      refresh();
      refreshCommandStatus();
    } catch {
      setMessage("");
      setError("Couldn't undo the last operation -- try again.");
    } finally {
      setUndoingLast(false);
    }
  }

  async function handleUndoRow(log) {
    if (undoingId) return;
    setUndoingId(log.id);
    setError("");
    try {
      const result = await undoLog(log.id);
      setMessage(result.message);
      refresh();
      refreshCommandStatus();
    } catch {
      setMessage("");
      setError("Couldn't undo that operation -- try again.");
    } finally {
      setUndoingId(null);
    }
  }

  async function handleReclassify(log, category) {
    setError("");
    try {
      const result = await reclassifyLog(log.id, category);
      setMessage(result.message);
      refresh();
      refreshCommandStatus();
    } catch {
      setMessage("");
      setError("Couldn't reclassify that file -- try again.");
    }
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
          : `Undid ${succeeded} of ${targets.length} selected (${targets.length - succeeded} failed).`,
      );
      clearSelection();
      refresh();
      refreshCommandStatus();
    } finally {
      setBulkBusy(false);
    }
  }

  async function handleBulkReclassify(category) {
    if (!category) return;
    const targets = logs.filter((l) => selectedIds.has(l.id) && l.destination_path && !l.undone && l.category !== category);
    if (!targets.length || bulkBusy) return;
    setBulkBusy(true);
    try {
      const results = await Promise.allSettled(targets.map((l) => reclassifyLog(l.id, category)));
      const succeeded = results.filter((r) => r.status === "fulfilled" && r.value.success).length;
      setMessage(
        succeeded === targets.length
          ? `Moved ${succeeded} file${succeeded === 1 ? "" : "s"} to ${category}.`
          : `Moved ${succeeded} of ${targets.length} selected (${targets.length - succeeded} failed).`,
      );
      clearSelection();
      refresh();
      refreshCommandStatus();
    } finally {
      setBulkBusy(false);
    }
  }

  const knownFolders = collectKnownFolders(rules);
  const undoneCount = logs.filter((l) => l.undone).length;
  const activeCount = logs.length - undoneCount;
  const selectedUndoableCount = logs.filter((l) => selectedIds.has(l.id) && UNDOABLE_ACTIONS.includes(l.action)).length;
  const hasSelection = selectedIds.size > 0;

  const groups = useMemo(() => {
    const out = [];
    for (const log of logs) {
      const key = new Date(log.timestamp).toDateString();
      const last = out[out.length - 1];
      if (last && last.key === key) last.items.push(log);
      else out.push({ key, heading: dayHeading(log.timestamp), items: [log] });
    }
    return out;
  }, [logs]);

  return (
    <>
      <PageHeading index={3} kicker="Timeline" title="History" subtitle="Reversible operations, newest first. Undo or refile anything." />
      <div className="ff-in flex flex-col gap-[18px]">
        <div
          className="sticky top-0 z-[5] flex flex-wrap items-center gap-2.5 rounded-[4px] px-3 py-2.5 transition-colors"
          style={{
            background: hasSelection ? "var(--ink)" : "var(--sheet-2)",
            color: hasSelection ? "var(--paper)" : "var(--ink)",
            transitionDuration: "var(--d2)",
          }}
        >
          {logs.length > 0 && (
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleSelectAll}
              disabled={selectableLogs.length === 0}
              aria-label="Select all"
              className="h-[18px] w-[18px]"
              style={{ accentColor: hasSelection ? "var(--paper)" : "var(--ink)" }}
            />
          )}
          {hasSelection ? (
            <>
              <span className="text-[13px] font-semibold">{selectedIds.size} selected</span>
              <select
                value=""
                onChange={(e) => handleBulkReclassify(e.target.value)}
                disabled={bulkBusy}
                aria-label="Move selected to"
                className="ff-input h-8 max-w-[170px] text-[12px]"
              >
                <option value="">Move selected to…</option>
                {knownFolders.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={handleBulkUndo}
                disabled={bulkBusy || selectedUndoableCount === 0}
                className="ff-btn ff-btn-sm border-none bg-[var(--paper)] font-bold text-[var(--ink)]"
              >
                Undo selected ({selectedUndoableCount})
              </button>
              <button type="button" onClick={clearSelection} className="ff-btn ff-btn-sm border border-[var(--ink-muted)] bg-transparent text-[var(--paper)]">
                Clear
              </button>
            </>
          ) : (
            <span className="text-[13px]">
              <b className="font-semibold">
                {activeCount} still in place · {undoneCount} undone
              </b>
              <span className="text-[var(--ink-muted)]"> · Select operations to undo several at once</span>
            </span>
          )}
          <button
            type="button"
            onClick={handleUndoLast}
            disabled={undoingLast}
            className={`ff-btn ff-btn-sm ml-auto ${hasSelection ? "border border-[var(--paper)] bg-transparent text-[var(--paper)]" : "ff-btn-outline"}`}
          >
            {undoingLast ? "Undoing…" : "Undo last operation"}
          </button>
        </div>

        {error && (
          <p role="alert" className="m-0 rounded-[4px] bg-[var(--stamp-bg)] px-3 py-2 text-[12.5px] font-medium text-[var(--stamp)]">
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="m-0 rounded-[4px] bg-[var(--filed-bg)] px-3 py-2 text-[12.5px] font-medium text-[var(--filed)]">
            {message}
          </p>
        )}

        {logs.length === 0 && (
          <div className="py-[30px] text-[13px] text-[var(--ink-muted)]">
            No operations yet. Moves, archives and refiles appear here and can be undone.
          </div>
        )}

        {groups.map((g) => (
          <section key={g.key} className="flex flex-col">
            <h2 className="ff-kicker m-0 mb-1.5 text-[11px] font-bold">{g.heading}</h2>
            <ol className="m-0 flex list-none flex-col border-l-2 border-[var(--ink)] p-0 pl-[18px]">
              {g.items.map((log) => {
                const stamp = stampFor(log);
                const undoable = !log.undone && UNDOABLE_ACTIONS.includes(log.action);
                const agent = agentLabel(commandStatusByLogId[log.id]);
                const renamed = log.original_filename && log.original_filename !== log.final_filename;
                const open = whyId === log.id;
                const sourceDir = log.source_path ? folderName(log.source_path.replace(/[\\/][^\\/]*$/, "")) : "";
                return (
                  <li key={log.id} className="relative border-b border-dashed border-[var(--rule-2)]">
                    <span
                      aria-hidden="true"
                      className="absolute left-[-25px] top-[18px] h-3 w-3 rounded-full border-2 border-[var(--sheet)]"
                      style={{ background: DOT[stamp.tone] || "var(--ink)" }}
                    />
                    <div
                      className="flex flex-wrap items-center gap-x-3.5 gap-y-2 py-3 transition-opacity"
                      style={{ opacity: log.undone ? 0.55 : 1 }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(log.id)}
                        onChange={() => toggleSelect(log.id)}
                        disabled={log.undone}
                        aria-label={`Select ${log.final_filename}`}
                        className="h-[18px] w-[18px]"
                        style={{ accentColor: "var(--ink)" }}
                      />
                      <span className="shrink-0 basis-[64px] font-mono-data text-[11.5px] font-medium text-[var(--ink-muted)]">
                        {new Date(log.timestamp).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false })}
                      </span>
                      <span className="flex min-w-0 flex-[1_1_320px] flex-col gap-[3px]">
                        <b className="text-[13px]">{operationTitle(log)}</b>
                        <span className="flex flex-wrap items-center gap-1.5 font-mono-data text-[12px] font-medium text-[var(--ink-2)]">
                          <span style={{ overflowWrap: "anywhere" }}>
                            {sourceDir && <span className="text-[var(--ink-muted)]">{sourceDir}/</span>}
                            <span>{renamed ? log.original_filename : log.final_filename}</span>
                          </span>
                          {renamed && (
                            <Fragment>
                              <span className="text-[var(--ink-muted)]">as</span>
                              <span style={{ overflowWrap: "anywhere" }}>{log.final_filename}</span>
                            </Fragment>
                          )}
                          <span className="text-[var(--stamp)]">→</span>
                          <FolderTag>{log.category}</FolderTag>
                        </span>
                      </span>
                      {log.undone ? (
                        <Stamp tone="undone" size="lg" pop style={{ transform: "rotate(-3deg)" }}>
                          Undone
                        </Stamp>
                      ) : (
                        <Stamp tone={stamp.tone}>{stamp.label}</Stamp>
                      )}
                      {agent && <Stamp tone={agent.tone}>{`agent · ${agent.label}`}</Stamp>}
                      <span className="ml-auto flex flex-wrap items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => setWhyId(open ? null : log.id)}
                          aria-expanded={open}
                          aria-label={`Why was ${log.final_filename} placed here?`}
                          className="ff-btn ff-btn-tertiary ff-btn-sm"
                        >
                          Why?
                        </button>
                        {log.destination_path && !log.undone && (
                          <select
                            value=""
                            onChange={(e) => {
                              if (e.target.value) handleReclassify(log, e.target.value);
                            }}
                            title="Move this file to a different category"
                            aria-label={`Refile ${log.final_filename}`}
                            className="ff-input h-[30px] max-w-[150px] text-[12px]"
                          >
                            <option value="">Refile to…</option>
                            {knownFolders
                              .filter((c) => c !== log.category)
                              .map((c) => (
                                <option key={c} value={c}>
                                  {c}
                                </option>
                              ))}
                          </select>
                        )}
                        {undoable && (
                          <button
                            type="button"
                            onClick={() => handleUndoRow(log)}
                            disabled={undoingId === log.id}
                            className="ff-btn ff-btn-outline ff-btn-sm"
                          >
                            {undoingId === log.id ? "Undoing…" : "Undo"}
                          </button>
                        )}
                      </span>
                    </div>
                    {open && (
                      <div className="mb-3">
                        <ExplanationPanel explanation={log.explanation} />
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
          </section>
        ))}
      </div>
    </>
  );
}
