import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
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
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deletingPath, setDeletingPath] = useState(null);
  const [error, setError] = useState("");

  function load() {
    getCategoryFiles(category)
      .then(setFiles)
      .catch(() => setFiles([]));
  }

  useEffect(() => {
    setFiles(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  async function confirmDelete() {
    const file = pendingDelete;
    setPendingDelete(null);
    setDeletingPath(file.path);
    setError("");
    try {
      const result = await deleteCategoryFile(category, file.path);
      if (result.success) {
        setFiles((current) => current.filter((f) => f.path !== file.path));
      } else {
        setError(result.message);
      }
    } catch {
      setError("Couldn't delete that file.");
    } finally {
      setDeletingPath(null);
    }
  }

  const color = buildCategoryColorMap([category])[category];
  const sorted = files ? [...files].sort(SORTS[sortKey].compare) : [];
  const totalSize = files ? files.reduce((sum, f) => sum + f.size_bytes, 0) : 0;

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
                      onClick={() => setPendingDelete(file)}
                      disabled={deletingPath === file.path}
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
        title={`Delete "${pendingDelete?.name}"?`}
        description="Moves this file to the Recycle Bin -- you can restore it from there if this was a mistake. It won't be tracked by FileFlow anymore."
        confirmLabel="Move to Recycle Bin"
        variant="destructive"
        onConfirm={confirmDelete}
      />
    </>
  );
}
