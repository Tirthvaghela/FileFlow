import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion, AnimatePresence } from "motion/react";
import { ArrowLeft, ArrowUpDown, FileX, Trash2 } from "lucide-react";
import Header from "../components/Header.jsx";
import EmptyState from "../components/EmptyState.jsx";
import ConfirmDialog from "../components/ui/ConfirmDialog.jsx";
import { deleteCategoryFile, getCategoryFiles } from "../services/api.js";
import { buildCategoryColorMap, categoryBadge, formatBytes } from "../utils/categoryMeta.js";

const SORTS = {
  largest: { label: "Largest first", compare: (a, b) => b.size_bytes - a.size_bytes },
  smallest: { label: "Smallest first", compare: (a, b) => a.size_bytes - b.size_bytes },
  newest: { label: "Newest first", compare: (a, b) => new Date(b.modified_at) - new Date(a.modified_at) },
  oldest: { label: "Oldest first", compare: (a, b) => new Date(a.modified_at) - new Date(b.modified_at) },
};

export default function CategoryDetail() {
  const { category } = useParams();
  const navigate = useNavigate();
  const [files, setFiles] = useState(null);
  const [sortKey, setSortKey] = useState("largest");
  const [pendingDelete, setPendingDelete] = useState(null); // array of file objects, or null
  const [deletingPaths, setDeletingPaths] = useState(() => new Set());
  const [selectedPaths, setSelectedPaths] = useState(() => new Set());
  const [error, setError] = useState("");

  function load() {
    getCategoryFiles(category)
      .then(setFiles)
      .catch(() => setFiles([]));
  }

  useEffect(() => {
    setFiles(null);
    setSelectedPaths(new Set());
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  async function confirmDelete() {
    const targets = pendingDelete;
    setPendingDelete(null);
    setDeletingPaths(new Set(targets.map((f) => f.path)));
    setError("");
    try {
      const results = await Promise.allSettled(
        targets.map((f) => deleteCategoryFile(category, f.path))
      );
      const deletedPaths = new Set();
      const failures = [];
      targets.forEach((f, i) => {
        const r = results[i];
        if (r.status === "fulfilled" && r.value.success) deletedPaths.add(f.path);
        else failures.push({ name: f.name, message: r.status === "fulfilled" ? r.value.message : null });
      });
      if (deletedPaths.size) {
        setFiles((current) => current.filter((f) => !deletedPaths.has(f.path)));
        setSelectedPaths((current) => {
          const next = new Set(current);
          deletedPaths.forEach((p) => next.delete(p));
          return next;
        });
      }
      if (failures.length === 1) {
        // The backend's own DeleteResult.message is specific and useful
        // ("That file no longer exists.", a path-containment refusal, an
        // agent-connected refusal, a real OS error) -- for the single-file
        // case (by far the most common: the per-row delete button), show
        // it directly instead of a generic string that discards it.
        setError(failures[0].message || `Couldn't delete ${failures[0].name}.`);
      } else if (failures.length === targets.length) {
        setError("Couldn't delete the selected file(s).");
      } else if (failures.length) {
        setError(`Couldn't delete: ${failures.map((f) => f.name).join(", ")}`);
      }
    } catch {
      setError("Couldn't delete the selected file(s).");
    } finally {
      setDeletingPaths(new Set());
    }
  }

  function toggleSelect(path) {
    setSelectedPaths((current) => {
      const next = new Set(current);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  const color = buildCategoryColorMap([category])[category];
  const sorted = files ? [...files].sort(SORTS[sortKey].compare) : [];
  const totalSize = files ? files.reduce((sum, f) => sum + f.size_bytes, 0) : 0;
  const allSelected = sorted.length > 0 && selectedPaths.size === sorted.length;

  return (
    <>
      <Header title={category} subtitle="Files in this category" />
      <div className="p-8">
        <button
          onClick={() => navigate("/app/categories")}
          className="mb-4 flex items-center gap-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Categories
        </button>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span
                className="flex h-9 w-9 items-center justify-center rounded-lg text-[10px] font-bold tracking-wide"
                style={{ color, background: `color-mix(in srgb, ${color} 16%, transparent)` }}
              >
                {categoryBadge(category)}
              </span>
              <div>
                <div className="text-sm font-medium text-[var(--text-primary)]">
                  {files ? `${files.length} file${files.length === 1 ? "" : "s"}` : "Loading…"}
                </div>
                {files && files.length > 0 && (
                  <div className="text-xs text-[var(--text-muted)]">{formatBytes(totalSize)} total</div>
                )}
              </div>
            </div>

            <label className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
              <ArrowUpDown className="h-3.5 w-3.5" />
              <select
                value={sortKey}
                onChange={(e) => setSortKey(e.target.value)}
                className="rounded-md border border-[var(--border)] bg-[var(--page)] px-2 py-1.5 text-xs text-[var(--text-primary)]"
              >
                {Object.entries(SORTS).map(([key, { label }]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {error && (
            <p className="mb-3 rounded-lg bg-[var(--status-critical)]/10 px-3 py-2 text-xs font-medium text-[var(--status-critical)]">
              {error}
            </p>
          )}

          {files && files.length > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--page)] px-3 py-2 text-xs">
              <label className="flex items-center gap-2 font-medium text-[var(--text-secondary)]">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={() =>
                    setSelectedPaths(allSelected ? new Set() : new Set(sorted.map((f) => f.path)))
                  }
                  className="h-4 w-4 rounded border-[var(--border)] accent-[var(--brand)]"
                />
                Select all
              </label>
              {selectedPaths.size > 0 && (
                <>
                  <span className="text-[var(--text-muted)]">{selectedPaths.size} selected</span>
                  <button
                    onClick={() =>
                      setPendingDelete(sorted.filter((f) => selectedPaths.has(f.path)))
                    }
                    className="flex items-center gap-1 rounded-md border border-[var(--status-critical)]/30 px-2.5 py-1 font-medium text-[var(--status-critical)] hover:bg-[var(--status-critical)]/10"
                  >
                    <Trash2 className="h-3 w-3" />
                    Delete selected ({selectedPaths.size})
                  </button>
                  <button
                    onClick={() => setSelectedPaths(new Set())}
                    className="ml-auto text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  >
                    Clear
                  </button>
                </>
              )}
            </div>
          )}

          {files === null ? (
            <p className="py-8 text-center text-sm text-[var(--text-muted)]">Loading…</p>
          ) : files.length === 0 ? (
            <EmptyState
              icon={FileX}
              message="Nothing in this category folder right now."
            />
          ) : (
            <div className="divide-y divide-[var(--border)]">
              <AnimatePresence initial={false}>
                {sorted.map((file) => (
                  <motion.div
                    key={file.path}
                    layout
                    initial={{ opacity: 1 }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.2 }}
                    className="flex items-center gap-3 py-3"
                  >
                    <input
                      type="checkbox"
                      checked={selectedPaths.has(file.path)}
                      onChange={() => toggleSelect(file.path)}
                      className="h-4 w-4 shrink-0 rounded border-[var(--border)] accent-[var(--brand)]"
                      aria-label={`Select ${file.name}`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-[var(--text-primary)]">
                        {file.name}
                      </div>
                      <div className="text-xs text-[var(--text-muted)]">
                        {new Date(file.modified_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}
                      </div>
                    </div>
                    <span
                      className="text-xs text-[var(--text-secondary)]"
                      style={{ fontVariantNumeric: "tabular-nums" }}
                    >
                      {formatBytes(file.size_bytes)}
                    </span>
                    <button
                      onClick={() => setPendingDelete([file])}
                      disabled={deletingPaths.has(file.path)}
                      title="Move to Recycle Bin"
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--text-muted)] hover:bg-[var(--status-critical)]/10 hover:text-[var(--status-critical)] disabled:opacity-50"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        title={
          pendingDelete?.length === 1
            ? `Delete "${pendingDelete[0].name}"?`
            : `Delete ${pendingDelete?.length ?? 0} files?`
        }
        description="Moves the file(s) to the Recycle Bin -- you can restore them from there if this was a mistake. They won't be tracked by FileFlow anymore."
        confirmLabel="Move to Recycle Bin"
        variant="destructive"
        onConfirm={confirmDelete}
      />
    </>
  );
}
