import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import PageHeading from "../components/PageHeading.jsx";
import Kicker from "../components/Kicker.jsx";
import ActivityTable from "../components/ActivityTable.jsx";
import RecentAgentActivity from "../components/RecentAgentActivity.jsx";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import { useCommandStatusByLogId } from "../hooks/useCommandStatusByLogId.js";
import { reclassifyLog, undoLog } from "../services/api.js";
import { collectKnownFolders } from "../utils/categoryMeta.js";
import { useRules } from "../context/RulesContext.jsx";

// Action filters -- what actually happened to the file.
const FILTERS = {
  All: () => true,
  Filed: (l) => !l.undone && ["moved", "renamed_and_moved", "replaced"].includes(l.action),
  Duplicates: (l) => !l.undone && l.action === "duplicate_skipped",
  Archived: (l) => !l.undone && l.action === "archived",
  Undone: (l) => l.undone,
};

export default function ActivityLog() {
  const { logs, refresh } = useLiveLogs(200);
  const { commandStatusByLogId, refreshCommandStatus } = useCommandStatusByLogId();
  const { rules } = useRules();
  const location = useLocation();
  const [filter, setFilter] = useState("All");
  const [folder, setFolder] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const openParam = searchParams.get("open");
  const openId = openParam ? Number(openParam) : null;
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [undoingId, setUndoingId] = useState(null);

  // Keep the URL in sync so a search landed on via the header (or a
  // bookmark/back-button) reproduces the same filtered view.
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (search) next.set("q", search);
    else next.delete("q");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  useEffect(() => {
    if (location.hash === "#agent-commands") {
      document.getElementById("agent-commands")?.scrollIntoView?.({ behavior: "smooth" });
    }
  }, [location.hash]);

  const folders = useMemo(() => [...new Set(logs.map((l) => l.category))].sort((a, b) => a.localeCompare(b)), [logs]);

  const filtered = logs.filter((l) => {
    const q = search.trim().toLowerCase();
    const matchesSearch = !q || l.final_filename.toLowerCase().includes(q) || (l.category || "").toLowerCase().includes(q);
    return FILTERS[filter](l) && matchesSearch && (!folder || l.category === folder);
  });

  const knownFolders = collectKnownFolders(rules);

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

  return (
    <>
      <PageHeading index={2} kicker="Ledger" title="Activity" subtitle="Every action FileFlow has taken, with the reason it was taken." />
      <div className="ff-in flex flex-col gap-5">
        <div className="flex flex-wrap items-center gap-2.5">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by file name or folder"
            aria-label="Filter activity"
            className="ff-input flex-[1_1_260px]"
          />
          <div role="radiogroup" aria-label="Action" className="flex flex-wrap gap-1">
            {Object.keys(FILTERS).map((f) => {
              const active = filter === f;
              return (
                <button
                  key={f}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => setFilter(f)}
                  className="h-8 flex-none cursor-pointer whitespace-nowrap rounded-full border px-3 text-[12px] font-semibold transition-colors"
                  style={{
                    borderColor: active ? "var(--ink)" : "var(--rule-2)",
                    background: active ? "var(--ink)" : "var(--sheet)",
                    color: active ? "var(--paper)" : "var(--ink)",
                  }}
                >
                  {f}
                </button>
              );
            })}
          </div>
          {folders.length > 1 && (
            <select
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              aria-label="Filter by folder"
              className="ff-input h-8 max-w-[180px]"
            >
              <option value="">Folder: all</option>
              {folders.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          )}
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

        <ActivityTable
          logs={filtered}
          showStatusBadge
          commandStatusByLogId={commandStatusByLogId}
          onUndo={handleUndoRow}
          undoingId={undoingId}
          allowAnyRowUndo
          onReclassify={handleReclassify}
          categories={knownFolders}
          openId={openId}
          emptyMessage={
            logs.length === 0
              ? "No activity yet — drop a file into the watched folder to see it here."
              : "No entries match. Try another filter or clear the search."
          }
        />

        <section id="agent-commands" aria-label="Agent commands" className="mt-2 flex scroll-mt-4 flex-col gap-2.5">
          <Kicker>Agent commands</Kicker>
          <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">Undo and reclassify requests sent to the remote agent on your PC.</p>
          <RecentAgentActivity />
        </section>
      </div>
    </>
  );
}
