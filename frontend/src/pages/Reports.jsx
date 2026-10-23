import { useEffect, useMemo, useState } from "react";
import PageHeading from "../components/PageHeading.jsx";
import Kicker from "../components/Kicker.jsx";
import { csvReportUrl, excelReportUrl, getLogs, getWeeklyReports, pdfReportUrl } from "../services/api.js";
import { formatBytes } from "../utils/categoryMeta.js";
import { groupLogsByTier, ORGANIZED_ACTIONS, pad2 } from "../utils/ruleTiers.js";

function fmtDay(iso, opts = { month: "short", day: "numeric" }) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, opts);
}

function formatRange(start, end) {
  return `${fmtDay(start)} – ${fmtDay(end)}`;
}

// Local calendar date as YYYY-MM-DD (never via toISOString, which would
// shift the day for any timezone ahead of UTC).
function localDay(d) {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return localDay(d);
}

function logDay(log) {
  return log.timestamp ? localDay(new Date(log.timestamp)) : "";
}

const PERIODS = [
  { id: "this", label: "This week" },
  { id: "last", label: "Last week" },
  { id: "four", label: "4 weeks" },
];

export default function Reports() {
  const [weekly, setWeekly] = useState(null);
  const [logs, setLogs] = useState([]);
  const [period, setPeriod] = useState("this");

  useEffect(() => {
    getWeeklyReports(8)
      .then(setWeekly)
      .catch(() => setWeekly([]));
    getLogs(500)
      .then((l) => setLogs(Array.isArray(l) ? l : []))
      .catch(() => {});
  }, []);

  // The selected period, built only from the real weekly report rows.
  const view = useMemo(() => {
    if (!weekly || weekly.length === 0) return null;
    const weeks = period === "this" ? weekly.slice(0, 1) : period === "last" ? weekly.slice(1, 2) : weekly.slice(0, 4);
    if (weeks.length === 0) return { empty: true };
    const start = weeks[weeks.length - 1].week_start;
    const end = weeks[0].week_end;
    const sum = (k) => weeks.reduce((s, w) => s + (w[k] || 0), 0);
    return {
      weeks,
      start,
      end,
      kpis: [
        { label: "Files organized", value: sum("files_organized") },
        { label: "Duplicates removed", value: sum("duplicates_removed") },
        { label: "Storage optimized", value: formatBytes(sum("storage_optimized_bytes")) },
        { label: "Files archived", value: sum("files_archived") },
      ],
    };
  }, [weekly, period]);

  // Bars: per day for a single week (counted from the activity log), per
  // week for the 4-week view (straight from the weekly report rows).
  const bars = useMemo(() => {
    if (!view || view.empty) return [];
    if (period === "four") {
      return [...view.weeks].reverse().map((w) => ({ key: w.week_start, label: fmtDay(w.week_start), value: w.files_organized }));
    }
    const days = Array.from({ length: 7 }, (_, i) => addDays(view.start, i));
    return days.map((day) => ({
      key: day,
      label: fmtDay(day, { weekday: "short" }),
      value: logs.filter(
        (l) => !l.undone && ORGANIZED_ACTIONS.has(l.action) && logDay(l) === day,
      ).length,
    }));
  }, [view, period, logs]);

  const tiers = useMemo(() => {
    if (!view || view.empty) return [];
    const inRange = logs.filter((l) => {
      const d = logDay(l);
      return d >= view.start && d <= view.end;
    });
    return groupLogsByTier(inRange).filter((t) => t.count > 0);
  }, [view, logs]);

  const max = Math.max(1, ...bars.map((b) => b.value));
  const peak = bars.reduce((best, b, i) => (b.value > (bars[best]?.value ?? -1) ? i : best), 0);
  const tierMax = Math.max(1, ...tiers.map((t) => t.count));
  const unit = period === "four" ? "per week" : "per day";

  return (
    <>
      <PageHeading index={6} kicker="Reports" title="Reports" subtitle="What FileFlow did over a period, from your activity log." />
      <div className="ff-in flex flex-col gap-6">
        <div className="flex flex-wrap items-center gap-2.5">
          <div role="radiogroup" aria-label="Period" className="flex overflow-hidden rounded-[4px] border border-[var(--ink)]">
            {PERIODS.map((p) => {
              const on = period === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => setPeriod(p.id)}
                  className="h-[34px] cursor-pointer border-none px-3.5 text-[12.5px] font-semibold transition-colors"
                  style={{ background: on ? "var(--ink)" : "transparent", color: on ? "var(--paper)" : "var(--ink)" }}
                >
                  {p.label}
                </button>
              );
            })}
          </div>
          {view && !view.empty && (
            <span className="font-mono-data text-[12px] text-[var(--ink-muted)]">{formatRange(view.start, view.end)}</span>
          )}
          <span className="ml-auto flex flex-wrap gap-1.5">
            {view && !view.empty && (
              <a href={csvReportUrl(view.start, view.end)} className="ff-btn ff-btn-primary no-underline">
                Export CSV ({PERIODS.find((p) => p.id === period).label.toLowerCase()})
              </a>
            )}
            <a href={excelReportUrl()} className="ff-btn ff-btn-tertiary no-underline">
              Excel (full history)
            </a>
            <a href={pdfReportUrl()} className="ff-btn ff-btn-tertiary no-underline">
              Export PDF (full history)
            </a>
          </span>
        </div>

        {weekly === null ? (
          <p className="py-8 text-center text-[13px] text-[var(--ink-muted)]">Loading…</p>
        ) : weekly.length === 0 ? (
          <div className="flex flex-col gap-1.5 py-[30px]">
            <b className="ff-display text-[18px]">No activity yet.</b>
            <span className="text-[var(--ink-muted)]">Reports fill in once FileFlow has organized files.</span>
          </div>
        ) : view?.empty ? (
          <p className="m-0 py-6 text-[13px] text-[var(--ink-muted)]">No report rows for this period yet.</p>
        ) : (
          <>
            <div className="grid border-b border-t-2 border-[var(--rule)] border-t-[var(--ink)]" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
              {view.kpis.map((k) => (
                <div key={k.label} className="flex flex-col gap-[3px] border-r border-dashed border-[var(--rule-2)] py-3.5 pl-3.5 first:pl-0">
                  <span className="font-mono-data text-[28px] font-semibold tracking-[-0.03em]">{k.value}</span>
                  <span className="text-[12px] text-[var(--ink-2)]">{k.label}</span>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap gap-7">
              <section aria-label="Files organized over time" className="flex min-w-0 flex-[3_1_460px] flex-col gap-2.5">
                <h2 className="ff-kicker m-0 text-[11px] font-bold">Files organized · {unit}</h2>
                <div className="relative flex h-[220px] items-end gap-2 border-b-[1.5px] border-[var(--ink)] pl-[34px]">
                  <span aria-hidden="true" className="absolute left-0 top-[-6px] font-mono-data text-[10.5px] text-[var(--ink-muted)]">{max}</span>
                  <span aria-hidden="true" className="absolute left-[34px] right-0 top-0 border-t border-dashed border-[var(--rule-2)]" />
                  <span aria-hidden="true" className="absolute left-0 top-[calc(50%-6px)] font-mono-data text-[10.5px] text-[var(--ink-muted)]">
                    {Math.round(max / 2)}
                  </span>
                  <span aria-hidden="true" className="absolute left-[34px] right-0 top-1/2 border-t border-dashed border-[var(--rule-2)]" />
                  {bars.map((b, i) => (
                    <div key={b.key} title={`${b.label}: ${b.value} files`} className="relative flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1">
                      <span className="font-mono-data text-[11px] font-semibold">{b.value}</span>
                      <span
                        className="ff-in w-full max-w-[56px] rounded-[2px_2px_0_0]"
                        style={{
                          height: `${(b.value / max) * 190}px`,
                          background: i === peak && b.value > 0 ? "var(--stamp)" : "var(--ink)",
                          animationDelay: `${i * 40}ms`,
                        }}
                      />
                    </div>
                  ))}
                </div>
                <div className="flex gap-2 pl-[34px]">
                  {bars.map((b) => (
                    <span key={b.key} className="min-w-0 flex-1 truncate text-center font-mono-data text-[10.5px] text-[var(--ink-muted)]">
                      {b.label}
                    </span>
                  ))}
                </div>
                {period !== "four" && (
                  <p className="m-0 text-[12px] text-[var(--ink-muted)]">Daily bars count the most recent 500 activity-log entries.</p>
                )}
              </section>

              {tiers.length > 0 && (
                <section aria-label="Which tier decided" className="flex min-w-0 flex-[2_1_300px] flex-col gap-2.5">
                  <h2 className="ff-kicker m-0 text-[11px] font-bold">Which rule tier decided</h2>
                  {tiers.map((t) => (
                    <div key={t.matchType} className="grid items-center gap-2.5" style={{ gridTemplateColumns: "110px 1fr 40px" }}>
                      <span className="text-[12.5px] font-semibold">
                        <span className="mr-1.5 font-mono-data text-[10.5px] text-[var(--ink-muted)]">{pad2(t.n)}</span>
                        {t.label}
                      </span>
                      <span className="h-3.5 overflow-hidden rounded-[2px] bg-[var(--rule)]">
                        <span
                          className="block h-full"
                          style={{ width: `${(t.count / tierMax) * 100}%`, background: t.n === 1 ? "var(--stamp)" : "var(--ink-2)" }}
                        />
                      </span>
                      <span className="text-right font-mono-data text-[12px] font-semibold">{t.count}</span>
                    </div>
                  ))}
                  <p className="m-0 mt-1 text-[12px] text-[var(--ink-muted)]">From the match type stored with each file in the activity log.</p>
                </section>
              )}
            </div>
          </>
        )}

        {weekly && weekly.length > 0 && (
          <section aria-label="Recent weeks" className="flex flex-col gap-2">
            <Kicker>Recent weeks</Kicker>
            <div className="flex flex-col border-t border-[var(--ink)]">
              {weekly.map((w) => (
                <div key={w.week_start} className="flex flex-wrap items-center gap-x-5 gap-y-1.5 border-b border-[var(--rule)] px-1 py-2.5">
                  <span className="basis-[130px] font-mono-data text-[12.5px] font-semibold">{formatRange(w.week_start, w.week_end)}</span>
                  <span className="basis-[80px] font-mono-data text-[12px] text-[var(--ink-2)]">{w.files_organized} files</span>
                  <span className="basis-[80px] font-mono-data text-[12px] text-[var(--ink-2)]">{w.duplicates_removed} dupes</span>
                  <span className="basis-[80px] font-mono-data text-[12px] text-[var(--ink-2)]">{formatBytes(w.storage_optimized_bytes)}</span>
                  <a href={csvReportUrl(w.week_start, w.week_end)} className="ff-btn ff-btn-tertiary ff-btn-sm ml-auto no-underline">
                    Download
                  </a>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </>
  );
}
