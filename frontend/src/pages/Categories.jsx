import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageHeading from "../components/PageHeading.jsx";
import { getCategories } from "../services/api.js";
import { formatBytes } from "../utils/categoryMeta.js";

// Each category is a cabinet drawer in a tray: manila label holder, a
// handle, the live file count from disk, and a single ink bar for its
// share of all files. /api/categories returns {category, count,
// size_bytes} only -- no per-extension split -- so no type strip is drawn
// rather than inventing one.
export default function Categories() {
  const [categories, setCategories] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    getCategories()
      .then(setCategories)
      .catch(() => {
        setError(true);
        setCategories([]);
      });
  }, []);

  const heading = (
    <PageHeading index={5} kicker="Cabinet" title="Categories" subtitle="The folders FileFlow files into, counted from disk." />
  );

  if (categories === null) {
    return (
      <>
        {heading}
        <div className="text-sm text-[var(--ink-muted)]">Loading…</div>
      </>
    );
  }

  const totalFiles = categories.reduce((sum, c) => sum + c.count, 0);

  return (
    <>
      {heading}
      <div className="ff-in flex flex-col gap-[18px]">
        {error ? (
          <div role="alert" className="py-6 text-[13px] text-[var(--stamp)]">
            Folder counts could not be read from disk. Try again once the server is reachable.
          </div>
        ) : categories.length === 0 ? (
          <div className="flex flex-col gap-1.5 py-8">
            <b className="ff-display text-[18px]">No folders yet.</b>
            <span className="text-[var(--ink-muted)]">Categories appear here once FileFlow moves something.</span>
          </div>
        ) : (
          <>
            <p className="m-0 text-[13px] text-[var(--ink-muted)]">
              <span className="font-mono-data text-[22px] font-semibold text-[var(--ink)]">{totalFiles}</span> files across{" "}
              {categories.length} folder{categories.length === 1 ? "" : "s"} · live count from disk
            </p>
            <div className="grid gap-2.5 rounded-[6px] bg-[var(--rule)] p-2.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
              {categories.map((cat, i) => {
                const share = totalFiles ? Math.round((cat.count / totalFiles) * 100) : 0;
                return (
                  <Link
                    key={cat.category}
                    to={`/app/categories/${encodeURIComponent(cat.category)}`}
                    aria-label={`Open ${cat.category}, ${cat.count} files`}
                    className="ff-in flex flex-col gap-3.5 rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet-2)] p-4 text-[var(--ink)] no-underline transition-[transform,box-shadow] hover:-translate-y-1 hover:shadow-[inset_0_-4px_0_var(--rule),0_12px_18px_-10px_var(--shade)]"
                    style={{
                      boxShadow: "inset 0 -4px 0 var(--rule), 0 2px 0 var(--rule-2)",
                      animationDelay: `${Math.min(i, 10) * 40}ms`,
                      transitionDuration: "var(--d2)",
                    }}
                  >
                    <span
                      className="w-max max-w-full self-center rounded-[2px] border-[1.5px] border-[var(--manila-2)] bg-[var(--manila)] px-3 py-1.5 text-center font-mono-data text-[12px] font-semibold text-[var(--manila-ink)]"
                      style={{ boxShadow: "inset 0 1px 2px var(--shade)", overflowWrap: "anywhere" }}
                    >
                      {cat.category}
                    </span>
                    <span
                      aria-hidden="true"
                      className="h-2 w-14 self-center rounded-full bg-[var(--rule-2)]"
                      style={{ boxShadow: "inset 0 2px 2px var(--shade)" }}
                    />
                    <span className="flex items-baseline gap-2">
                      <span className="font-mono-data text-[26px] font-semibold tracking-[-0.03em]">{cat.count}</span>
                      <span className="text-[12px] text-[var(--ink-muted)]">
                        file{cat.count === 1 ? "" : "s"} · {formatBytes(cat.size_bytes)}
                      </span>
                      <span className="ml-auto font-mono-data text-[11px] text-[var(--ink-muted)]">{share}%</span>
                    </span>
                    <span aria-hidden="true" className="h-2 overflow-hidden rounded-[2px] bg-[var(--rule)]">
                      <span className="block h-full bg-[var(--ink)]" style={{ width: `${Math.max(share, cat.count ? 2 : 0)}%` }} />
                    </span>
                  </Link>
                );
              })}
            </div>
          </>
        )}
      </div>
    </>
  );
}
