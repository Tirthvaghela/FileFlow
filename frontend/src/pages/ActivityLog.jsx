import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "motion/react";
import Header from "../components/Header.jsx";
import EmptyState from "../components/EmptyState.jsx";
import { Activity, Search } from "lucide-react";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import { buildCategoryColorMap, categoryBadge } from "../utils/categoryMeta.js";
import { actionText, relativeTime } from "../utils/activity.js";
import { gsap, useGSAP } from "../lib/gsap.js";

export default function ActivityLog() {
  const { logs } = useLiveLogs(200);
  const [filter, setFilter] = useState("All");
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") || "");

  // Keep the URL in sync so a search landed on via the topbar (or a
  // bookmark/back-button) reproduces the same filtered view.
  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    if (search) next.set("q", search);
    else next.delete("q");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const categories = useMemo(() => {
    const seen = new Set(logs.map((l) => l.category));
    return ["All", ...[...seen].sort((a, b) => a.localeCompare(b))];
  }, [logs]);

  const colorMap = useMemo(
    () => buildCategoryColorMap(logs.map((l) => l.category)),
    [logs],
  );

  const filtered = logs.filter((l) => {
    const matchesCategory = filter === "All" || l.category === filter;
    const matchesSearch = !search.trim() || l.final_filename.toLowerCase().includes(search.trim().toLowerCase());
    return matchesCategory && matchesSearch;
  });

  const tbodyRef = useRef(null);

  // Re-run on every filter/search change so switching categories or typing
  // a search re-reveals the (new) row set -- a tame fade+lift, never
  // overshoot easing, which reads as sloppy on dense data rows.
  useGSAP(
    () => {
      if (!tbodyRef.current) return;
      gsap.from("tr", { opacity: 0, y: 6, stagger: 0.025, duration: 0.25, ease: "power1.out" });
    },
    { dependencies: [filtered.length, filter, search], scope: tbodyRef },
  );

  return (
    <>
      <Header title="Activity log" subtitle="Every action FileFlow has taken, live" />
      <div className="p-8">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {categories.map((cat) => {
              const active = filter === cat;
              return (
                <button
                  key={cat}
                  onClick={() => setFilter(cat)}
                  className={`isolate relative rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                    active ? "border-transparent text-[var(--brand-foreground)]" : "border-[var(--border)] text-[var(--text-secondary)] bg-[var(--surface-1)]"
                  }`}
                >
                  {active && (
                    <motion.span
                      layoutId="activityFilterPill"
                      className="absolute inset-0 -z-10 rounded-lg"
                      style={{ background: "var(--brand)" }}
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  {cat}
                </button>
              );
            })}
          </div>
          <label className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
              width={15}
              height={15}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by filename..."
              className="w-56 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]/30"
            />
          </label>
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] shadow-sm">
          {filtered.length === 0 ? (
            <EmptyState
              icon={Activity}
              message="No activity yet — drop a file into the watched folder to see it here."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-left text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
                    <th className="px-5 py-3 font-medium">File</th>
                    <th className="px-5 py-3 font-medium">Action</th>
                    <th className="px-5 py-3 text-right font-medium">Time</th>
                  </tr>
                </thead>
                <tbody ref={tbodyRef}>
                  {filtered.map((log) => {
                    const color = colorMap[log.category] || "var(--series-1)";
                    return (
                      <tr
                        key={log.id}
                        className="border-b border-[var(--border)] last:border-b-0 transition-colors hover:bg-[var(--gridline)]/40"
                      >
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-3">
                            <span
                              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[9px] font-bold tracking-wide"
                              style={{
                                color,
                                background: `color-mix(in srgb, ${color} 14%, transparent)`,
                              }}
                            >
                              {categoryBadge(log.category)}
                            </span>
                            <span
                              className={`truncate font-mono font-medium ${
                                log.undone
                                  ? "text-[var(--text-muted)] line-through"
                                  : "text-[var(--text-primary)]"
                              }`}
                            >
                              {log.final_filename}
                            </span>
                          </div>
                        </td>
                        <td className="px-5 py-3 text-[var(--text-secondary)]">
                          {log.undone ? "Undone" : actionText(log)}
                        </td>
                        <td
                          className="px-5 py-3 text-right text-[var(--text-muted)]"
                          style={{ fontVariantNumeric: "tabular-nums" }}
                        >
                          {relativeTime(log.timestamp)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
