import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { FolderOpen } from "lucide-react";
import Header from "../components/Header.jsx";
import EmptyState from "../components/EmptyState.jsx";
import { getCategories } from "../services/api.js";
import { buildCategoryColorMap, categoryBadge, formatBytes } from "../utils/categoryMeta.js";

export default function Categories() {
  const [categories, setCategories] = useState(null);

  useEffect(() => {
    getCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  if (categories === null) {
    return (
      <>
        <Header title="Categories" subtitle="Files sorted into smart folders" />
        <div className="p-8 text-sm text-[var(--text-muted)]">Loading…</div>
      </>
    );
  }

  const colorMap = buildCategoryColorMap(categories.map((c) => c.category));
  const maxSize = Math.max(1, ...categories.map((c) => c.size_bytes));

  return (
    <>
      <Header title="Categories" subtitle="Files sorted into smart folders" />
      <div className="p-8">
        {categories.length === 0 ? (
          <EmptyState
            icon={FolderOpen}
            message="No files organized yet — categories will appear here once FileFlow moves something."
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {categories.map((cat, i) => {
              const color = colorMap[cat.category];
              return (
                <motion.div
                  key={cat.category}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: Math.min(i, 8) * 0.04, ease: "easeOut" }}
                  className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm transition-shadow hover:shadow-md"
                >
                  <div className="mb-4 flex items-start justify-between">
                    <span
                      className="flex h-10 w-10 items-center justify-center rounded-lg text-[10px] font-bold tracking-wide"
                      style={{
                        color,
                        background: `color-mix(in srgb, ${color} 16%, transparent)`,
                      }}
                    >
                      {categoryBadge(cat.category)}
                    </span>
                    <span className="text-xs text-[var(--text-muted)]">
                      {formatBytes(cat.size_bytes)}
                    </span>
                  </div>
                  <div className="text-base font-semibold text-[var(--text-primary)]">
                    {cat.category}
                  </div>
                  <div className="mb-3 text-xs text-[var(--text-muted)]">
                    {cat.count} file{cat.count === 1 ? "" : "s"}
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-[var(--gridline)]">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${Math.max(4, (cat.size_bytes / maxSize) * 100)}%`,
                        background: color,
                      }}
                    />
                  </div>
                </motion.div>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
