import { useEffect, useState } from "react";
import Header from "../components/Header.jsx";
import StatCard from "../components/StatCard.jsx";
import { CalendarDays, Copy, Database, FileText } from "lucide-react";
import { csvReportUrl, excelReportUrl, getWeeklyReports, pdfReportUrl } from "../services/api.js";
import { formatBytes } from "../utils/categoryMeta.js";

function formatRange(start, end) {
  const s = new Date(`${start}T00:00:00`);
  const e = new Date(`${end}T00:00:00`);
  const opts = { month: "short", day: "numeric" };
  return `${s.toLocaleDateString(undefined, opts)} – ${e.toLocaleDateString(undefined, opts)}`;
}

export default function Reports() {
  const [weekly, setWeekly] = useState(null);

  useEffect(() => {
    getWeeklyReports(4)
      .then(setWeekly)
      .catch(() => setWeekly([]));
  }, []);

  const current = weekly?.[0];

  return (
    <>
      <Header title="Reports" subtitle="Weekly summaries and exports" />
      <div className="space-y-6 p-8">
        {current && (
          <div className="rounded-2xl bg-gradient-to-br from-[#1c3d7a] to-[var(--series-1)] p-6 shadow-lg shadow-[var(--series-1)]/20 text-white">
            <div className="mb-3 flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-white/70">
                  Weekly report · {formatRange(current.week_start, current.week_end)}
                </p>
                <h2 className="mt-1 text-2xl font-semibold">
                  {current.files_organized} files organized this week
                </h2>
                <p className="mt-1 text-sm text-white/80">
                  {current.duplicates_removed} duplicates removed ·{" "}
                  {formatBytes(current.storage_optimized_bytes)} storage optimized ·{" "}
                  {current.files_archived} archived
                </p>
              </div>
              <div className="flex gap-2">
                <a
                  href={csvReportUrl(current.week_start, current.week_end)}
                  className="rounded-lg bg-white/15 px-3 py-2 text-sm font-medium hover:bg-white/25"
                >
                  Export CSV
                </a>
                <a
                  href={pdfReportUrl()}
                  className="rounded-lg bg-white px-3 py-2 text-sm font-medium text-[var(--series-1)] hover:opacity-90"
                >
                  Export PDF
                </a>
              </div>
            </div>
          </div>
        )}

        {current && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Files organized"
              value={current.files_organized}
              icon={FileText}
              iconColor="var(--series-1)"
            />
            <StatCard
              label="Duplicates removed"
              value={current.duplicates_removed}
              icon={Copy}
              iconColor="var(--series-7)"
            />
            <StatCard
              label="Storage optimized"
              value={formatBytes(current.storage_optimized_bytes)}
              icon={Database}
              iconColor="var(--status-good)"
            />
            <StatCard
              label="Files archived"
              value={current.files_archived}
              icon={CalendarDays}
              iconColor="var(--series-2)"
            />
          </div>
        )}

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-medium text-[var(--text-secondary)]">
              Recent reports
            </h2>
            <a
              href={excelReportUrl()}
              className="text-xs font-medium text-[var(--series-1)] hover:underline"
            >
              Export full history (Excel)
            </a>
          </div>
          {!weekly || weekly.length === 0 ? (
            <p className="py-6 text-center text-sm text-[var(--text-muted)]">
              No activity yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                    <th className="py-2 pr-4 font-medium">Period</th>
                    <th className="py-2 pr-4 font-medium">Files</th>
                    <th className="py-2 pr-4 font-medium">Duplicates</th>
                    <th className="py-2 pr-4 font-medium">Storage</th>
                    <th className="py-2 pr-4 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {weekly.map((w) => (
                    <tr
                      key={w.week_start}
                      className="border-b border-[var(--border)] last:border-0"
                    >
                      <td className="py-2.5 pr-4 font-medium text-[var(--text-primary)]">
                        {formatRange(w.week_start, w.week_end)}
                      </td>
                      <td className="py-2.5 pr-4 text-[var(--text-secondary)]">
                        {w.files_organized} files
                      </td>
                      <td className="py-2.5 pr-4 text-[var(--text-secondary)]">
                        {w.duplicates_removed} dupes
                      </td>
                      <td className="py-2.5 pr-4 text-[var(--text-secondary)]">
                        {formatBytes(w.storage_optimized_bytes)}
                      </td>
                      <td className="py-2.5 pr-4 text-right">
                        <a
                          href={csvReportUrl(w.week_start, w.week_end)}
                          className="rounded-md border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text-primary)] hover:bg-[var(--gridline)]"
                        >
                          Download
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
