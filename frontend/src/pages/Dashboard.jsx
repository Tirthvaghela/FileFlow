import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { CalendarDays, Copy, Database, FileText, Pause, Zap } from "lucide-react";
import Header from "../components/Header.jsx";
import StatCard from "../components/StatCard.jsx";
import CategoryDonut from "../components/CategoryDonut.jsx";
import WeeklyChart from "../components/WeeklyChart.jsx";
import ActivityTable from "../components/ActivityTable.jsx";
import PipelineFlow from "../components/PipelineFlow.jsx";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import TiltCard from "../components/ui/TiltCard.jsx";
import ConfirmDialog from "../components/ui/ConfirmDialog.jsx";
import {
  getStats,
  getWeeklyReports,
  organizeExistingFiles,
  reclassifyLog,
  undoLastOperation,
} from "../services/api.js";
import { collectKnownFolders, formatBytes } from "../utils/categoryMeta.js";
import { useRules } from "../context/RulesContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";

export default function Dashboard() {
  const { logs, refresh } = useLiveLogs(6);
  const { rules } = useRules();
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const watchFolder = user?.watch_folder || "";
  const [actionMessage, setActionMessage] = useState("");
  const [organizing, setOrganizing] = useState(false);
  const [organizeResult, setOrganizeResult] = useState(null);
  const [thisWeek, setThisWeek] = useState(null);
  const [confirmOrganize, setConfirmOrganize] = useState(false);
  const [undoing, setUndoing] = useState(false);

  function loadStats() {
    getStats()
      .then(setStats)
      .catch(() => {});
    getWeeklyReports(1)
      .then((weeks) => setThisWeek(weeks[0] ?? null))
      .catch(() => {});
  }

  useEffect(() => {
    loadStats();
  }, []);

  useEffect(() => {
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logs[0]?.id]);

  async function handleUndo() {
    // The backend only guards against two calls racing on the *same* undo
    // -- it doesn't know a fast double-click was meant as one undo, not
    // two, so an unguarded second call here would undo the next operation
    // back too. Ignore any click that lands while the first is in flight.
    if (undoing) return;
    setUndoing(true);
    try {
      const result = await undoLastOperation();
      setActionMessage(result.message);
      refresh();
      loadStats();
    } finally {
      setUndoing(false);
    }
  }

  async function handleReclassify(log, category) {
    const result = await reclassifyLog(log.id, category);
    setActionMessage(result.message);
    refresh();
    loadStats();
  }

  async function runOrganizeExisting() {
    setOrganizing(true);
    setOrganizeResult(null);
    try {
      const result = await organizeExistingFiles();
      setOrganizeResult(result);
      refresh();
      loadStats();
    } finally {
      setOrganizing(false);
    }
  }

  const running = rules?.realtime_monitoring_enabled ?? true;
  const knownFolders = collectKnownFolders(rules);

  // Animation variants
  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.08,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 12 },
    show: {
      opacity: 1,
      y: 0,
      transition: { type: "spring", stiffness: 120, damping: 18 },
    },
  };

  return (
    <>
      <Header
        title="Dashboard"
        subtitle="Real-time overview of your automated file organization"
      />
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="show"
        className="space-y-6 p-8 relative z-0 min-h-[calc(100vh-80px)] overflow-hidden"
      >
        {/* Subtle grid background */}
        <div className="absolute inset-0 bg-grid-light z-[-1] pointer-events-none" />

        {/* Automation Status Panel */}
        <motion.div
          variants={itemVariants}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur px-5 py-5 shadow-sm"
        >
          <div className="flex flex-wrap items-center gap-3">
            <motion.span
              animate={{
                scale: running ? [1, 1.05, 1] : 1,
                boxShadow: running ? "0 0 12px rgba(42, 120, 214, 0.25)" : "none",
              }}
              transition={{ repeat: Infinity, duration: 2.5 }}
              className="flex h-9 w-9 items-center justify-center rounded-lg"
              style={{
                color: "var(--series-1)",
                background: "color-mix(in srgb, var(--series-1) 14%, transparent)",
              }}
            >
              {running ? <Zap className="h-[18px] w-[18px]" /> : <Pause className="h-[18px] w-[18px]" />}
            </motion.span>
            <div>
              <div className="text-sm font-semibold text-[var(--text-primary)]">
                Automation engine {running ? "running" : "paused"}
              </div>
              <div className="text-xs text-[var(--text-muted)]">
                Watching {watchFolder || "…"} for new files
              </div>
            </div>
          </div>
          <PipelineFlow running={running} />
        </motion.div>

        {/* Stats Grid */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            {
              label: "Files organized",
              value: stats?.total_files_organized ?? "—",
              icon: FileText,
              iconColor: "var(--series-1)",
              badge: thisWeek?.files_organized ? `+${thisWeek.files_organized}` : null,
            },
            {
              label: "Duplicates removed",
              value: stats?.duplicates_detected ?? "—",
              icon: Copy,
              iconColor: "var(--series-7)",
              badge: thisWeek?.duplicates_removed ? `+${thisWeek.duplicates_removed}` : null,
            },
            {
              label: "Storage saved",
              value: stats ? `${(stats.storage_saved_bytes / (1024 * 1024)).toFixed(1)} MB` : "—",
              icon: Database,
              iconColor: "var(--status-good)",
              badge: thisWeek?.storage_optimized_bytes
                ? `+${formatBytes(thisWeek.storage_optimized_bytes)}`
                : null,
            },
            {
              label: "Organized today",
              value: stats?.today_count ?? "—",
              icon: CalendarDays,
              iconColor: "var(--series-2)",
              badge: running ? "live" : "paused",
              badgeColor: running ? "var(--status-good)" : "var(--text-muted)",
            },
          ].map((card, i) => (
            <motion.div
              key={card.label}
              variants={itemVariants}
            >
              <TiltCard
                maxRotate={8}
                glareOpacityMax={0.12}
                className="h-full rounded-2xl"
              >
                <StatCard {...card} />
              </TiltCard>
            </motion.div>
          ))}
        </div>

        {/* Sweep Section */}
        <motion.div
          variants={itemVariants}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium text-[var(--text-primary)]">
                Organize existing downloads
              </h2>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                One-time sweep of files already sitting loose in the watch
                folder. Already-organized subfolders are left alone.
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => setConfirmOrganize(true)}
              disabled={organizing}
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-1)] hover:bg-[var(--gridline)]/50 hover:border-[var(--brand)]/30 px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-all cursor-pointer disabled:opacity-50"
            >
              {organizing ? "Organizing…" : "Organize existing files now"}
            </motion.button>
          </div>
          {organizeResult && organizeResult.queued && (
            <p className="mt-3 text-xs text-[var(--text-secondary)]">
              Queued — your agent will pick this up shortly.
            </p>
          )}
          {organizeResult && !organizeResult.queued && (
            <p className="mt-3 text-xs text-[var(--text-secondary)]">
              Scanned {organizeResult.scanned} file(s) — {organizeResult.organized}{" "}
              organized, {organizeResult.duplicates} duplicate(s) skipped
              {organizeResult.errors > 0 && `, ${organizeResult.errors} error(s)`}.
            </p>
          )}
        </motion.div>

        {/* Weekly Activity & Categories charts */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <motion.div
            variants={itemVariants}
            className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
          >
            <h2 className="mb-1 text-sm font-medium text-[var(--text-primary)]">
              Weekly activity
            </h2>
            <p className="mb-3 text-xs text-[var(--text-muted)]">Files organized per day</p>
            {stats && <WeeklyChart data={stats.last_7_days} />}
          </motion.div>
          <motion.div
            variants={itemVariants}
            className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
          >
            <h2 className="mb-1 text-sm font-medium text-[var(--text-primary)]">
              By category
            </h2>
            <p className="mb-3 text-xs text-[var(--text-muted)]">Distribution</p>
            {stats && <CategoryDonut data={stats.by_category} />}
          </motion.div>
        </div>

        {/* Live Logs & Active Rules */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <motion.div
            variants={itemVariants}
            className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
          >
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-sm font-medium text-[var(--text-primary)]">
                Live activity
              </h2>
              <Link
                to="/app/activity"
                className="text-xs font-medium text-[var(--brand)] hover:underline"
              >
                View all
              </Link>
            </div>
            {actionMessage && (
              <p className="mb-2 text-xs text-[var(--text-muted)]">{actionMessage}</p>
            )}
            <ActivityTable
              logs={logs}
              onUndo={handleUndo}
              undoing={undoing}
              onReclassify={handleReclassify}
              categories={knownFolders}
            />
          </motion.div>

          <motion.div
            variants={itemVariants}
            className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
          >
            <h2 className="mb-3 text-sm font-medium text-[var(--text-primary)]">
              Active rules
            </h2>
            <div className="mb-4 flex flex-wrap gap-2">
              {rules?.keyword_rules.map((r) => (
                <span
                  key={r.keyword}
                  className="flex items-center gap-1.5 rounded-full border border-[var(--border)] hover:border-[var(--brand)]/40 px-3 py-1 text-xs text-[var(--text-secondary)] transition-colors cursor-default"
                >
                  <span className="font-semibold text-[var(--brand)]">{r.keyword}</span>
                  <span className="text-[var(--text-muted)]">→</span>
                  {r.folder}
                </span>
              ))}
              {rules &&
                Object.entries(rules.extension_rules).map(([ext, folder]) => (
                  <span
                    key={ext}
                    className="flex items-center gap-1.5 rounded-full border border-[var(--border)] hover:border-[var(--brand)]/40 px-3 py-1 text-xs text-[var(--text-secondary)] transition-colors cursor-default"
                  >
                    <span className="font-semibold text-[var(--brand)]">{ext}</span>
                    <span className="text-[var(--text-muted)]">→</span>
                    {folder}
                  </span>
                ))}
              {rules && rules.large_file_enabled && (
                <span className="flex items-center gap-1.5 rounded-full border border-[var(--border)] hover:border-[var(--status-warning)]/40 px-3 py-1 text-xs text-[var(--text-secondary)] transition-colors cursor-default">
                  <span className="font-semibold text-[var(--status-warning)]">
                    &gt; {rules.large_file_threshold_mb} MB
                  </span>
                  <span className="text-[var(--text-muted)]">→</span>
                  {rules.large_file_folder}
                </span>
              )}
            </div>
            <Link
              to="/app/rules"
              className="block rounded-lg border border-[var(--border)] py-2 text-center text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--gridline)] transition-colors"
            >
              Manage rules
            </Link>
          </motion.div>
        </div>
      </motion.div>

      <ConfirmDialog
        open={confirmOrganize}
        onOpenChange={setConfirmOrganize}
        title="Organize existing files now?"
        description="This scans every file currently sitting loose in the watch folder root and organizes them right now, using your current rules. It affects real files immediately."
        confirmLabel="Organize now"
        onConfirm={runOrganizeExisting}
      />
    </>
  );
}
