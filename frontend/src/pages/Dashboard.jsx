import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { CalendarDays, Copy, Database, FileText, Pause, Zap } from "lucide-react";
import Header from "../components/Header.jsx";
import StatCard from "../components/StatCard.jsx";
import CategoryDonut from "../components/CategoryDonut.jsx";
import WeeklyChart from "../components/WeeklyChart.jsx";
import ActivityTable from "../components/ActivityTable.jsx";
import PipelineFlow from "../components/PipelineFlow.jsx";
import RecentAgentActivity from "../components/RecentAgentActivity.jsx";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import TiltCard from "../components/ui/TiltCard.jsx";
import OrganizePreviewDialog from "../components/ui/OrganizePreviewDialog.jsx";
import UnclassifiedSuggestionsDialog from "../components/ui/UnclassifiedSuggestionsDialog.jsx";
import DuplicateGroupsDialog from "../components/ui/DuplicateGroupsDialog.jsx";
import DuplicateGroupDetailDialog from "../components/ui/DuplicateGroupDetailDialog.jsx";
import FileSearchDialog from "../components/ui/FileSearchDialog.jsx";
import HealthDashboard from "../components/ui/HealthDashboard.jsx";
import {
  analyzeDuplicates,
  getAgentCommands,
  getCategories,
  getOrganizationHealth,
  getStats,
  getUnclassifiedSuggestions,
  getWeeklyReports,
  organizeExistingFiles,
  previewOrganizeExisting,
  reclassifyLog,
  searchFiles,
  undoLastOperation,
} from "../services/api.js";
import { collectKnownFolders, formatBytes } from "../utils/categoryMeta.js";
import { applyRuleToDoc, proposalFields } from "../utils/ruleForm.js";
import { useRules } from "../context/RulesContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";

export default function Dashboard() {
  const { logs, refresh } = useLiveLogs(6);
  const { rules, saveRules } = useRules();
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [categoryStats, setCategoryStats] = useState(null);
  const watchFolder = user?.watch_folder || "";
  const [actionMessage, setActionMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [organizing, setOrganizing] = useState(false);
  const [organizeResult, setOrganizeResult] = useState(null);
  const [organizeError, setOrganizeError] = useState("");
  const [thisWeek, setThisWeek] = useState(null);
  const [undoing, setUndoing] = useState(false);

  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewWaitingForAgent, setPreviewWaitingForAgent] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const [preview, setPreview] = useState(null);
  const previewCancelledRef = useRef(false);

  const [unclassifiedOpen, setUnclassifiedOpen] = useState(false);
  const [unclassifiedLoading, setUnclassifiedLoading] = useState(false);
  const [unclassifiedWaitingForAgent, setUnclassifiedWaitingForAgent] = useState(false);
  const [unclassifiedError, setUnclassifiedError] = useState("");
  const [unclassifiedResult, setUnclassifiedResult] = useState(null);
  const [unclassifiedIgnored, setUnclassifiedIgnored] = useState(() => new Set());
  const [unclassifiedCreatingKey, setUnclassifiedCreatingKey] = useState(null);
  const unclassifiedCancelledRef = useRef(false);

  const [duplicatesOpen, setDuplicatesOpen] = useState(false);
  const [duplicatesLoading, setDuplicatesLoading] = useState(false);
  const [duplicatesWaitingForAgent, setDuplicatesWaitingForAgent] = useState(false);
  const [duplicatesError, setDuplicatesError] = useState("");
  const [duplicatesResult, setDuplicatesResult] = useState(null);
  const duplicatesCancelledRef = useRef(false);
  const [duplicateDetailGroup, setDuplicateDetailGroup] = useState(null);
  const [duplicateDetailIndex, setDuplicateDetailIndex] = useState(0);

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchPrompt, setSearchPrompt] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchWaitingForAgent, setSearchWaitingForAgent] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const searchCancelledRef = useRef(false);

  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthRefreshing, setHealthRefreshing] = useState(false);
  const [healthError, setHealthError] = useState("");

  function loadStats() {
    getStats()
      .then(setStats)
      .catch(() => {});
    // A live per-category count, not stats.by_category -- that's an
    // all-time historical aggregate (right for a Report, which should
    // never forget what happened), so it keeps a category like "Large
    // Files" showing up here forever after its one file gets deleted. This
    // chart is meant to show the current distribution, so it needs the
    // same live-disk source as the Categories page.
    getCategories()
      .then(setCategoryStats)
      .catch(() => {});
    getWeeklyReports(1)
      .then((weeks) => setThisWeek(weeks[0] ?? null))
      .catch(() => {});
  }

  function loadHealth({ refreshing = false } = {}) {
    if (refreshing) setHealthRefreshing(true);
    else setHealthLoading(true);
    setHealthError("");
    getOrganizationHealth()
      .then((result) => setHealth(result))
      .catch(() => setHealthError("Couldn't load workspace health -- try again."))
      .finally(() => {
        setHealthLoading(false);
        setHealthRefreshing(false);
      });
  }

  useEffect(() => {
    loadStats();
    loadHealth();
  }, []);

  useEffect(() => {
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logs[0]?.id]);

  function handleRefreshHealth() {
    if (healthLoading || healthRefreshing) return;
    loadHealth({ refreshing: true });
  }

  async function handleUndo() {
    // The backend only guards against two calls racing on the *same* undo
    // -- it doesn't know a fast double-click was meant as one undo, not
    // two, so an unguarded second call here would undo the next operation
    // back too. Ignore any click that lands while the first is in flight.
    if (undoing) return;
    setUndoing(true);
    setActionError("");
    try {
      const result = await undoLastOperation();
      setActionMessage(result.message);
      refresh();
      loadStats();
    } catch {
      setActionMessage("");
      setActionError("Couldn't undo the last operation -- try again.");
    } finally {
      setUndoing(false);
    }
  }

  async function handleReclassify(log, category) {
    setActionError("");
    try {
      const result = await reclassifyLog(log.id, category);
      setActionMessage(result.message);
      refresh();
      loadStats();
    } catch {
      setActionMessage("");
      setActionError("Couldn't reclassify that file -- try again.");
    }
  }

  async function runOrganizeExisting() {
    if (organizing) return;
    setOrganizing(true);
    setOrganizeResult(null);
    setOrganizeError("");
    try {
      const result = await organizeExistingFiles();
      setOrganizeResult(result);
      refresh();
      loadStats();
    } catch {
      setOrganizeError("Couldn't organize existing files -- try again.");
    } finally {
      setOrganizing(false);
    }
  }

  async function pollForAgentPreview() {
    // Same polling cadence/attempt budget as the existing agent-command
    // patterns elsewhere in the app (RecentScheduledActivity, useCommand
    // StatusByLogId) -- 2s apart, generous enough for a real agent's 5s
    // poll interval (agent/commands.py) without hammering the backend.
    for (let attempt = 0; attempt < 30; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      if (previewCancelledRef.current) return null;
      try {
        const commands = await getAgentCommands({ type: "preview_organize_existing", limit: 1 });
        if (commands[0]?.status === "done") return commands[0].result;
      } catch {
        return null;
      }
    }
    return null;
  }

  async function handleOpenPreview() {
    previewCancelledRef.current = false;
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewWaitingForAgent(false);
    setPreviewError("");
    setPreview(null);
    try {
      const result = await previewOrganizeExisting();
      if (previewCancelledRef.current) return;
      if (result.queued) {
        setPreviewLoading(false);
        setPreviewWaitingForAgent(true);
        const resolved = await pollForAgentPreview();
        if (previewCancelledRef.current) return;
        setPreviewWaitingForAgent(false);
        if (resolved) setPreview(resolved);
        else setPreviewError("Your agent didn't respond in time -- try again.");
        return;
      }
      setPreview(result);
    } catch {
      if (!previewCancelledRef.current) {
        setPreviewError("Couldn't preview existing files -- try again.");
      }
    } finally {
      if (!previewCancelledRef.current) setPreviewLoading(false);
    }
  }

  function handleCancelPreview() {
    previewCancelledRef.current = true;
    setPreviewOpen(false);
    setPreview(null);
    setPreviewError("");
    setPreviewLoading(false);
    setPreviewWaitingForAgent(false);
  }

  async function handleConfirmOrganize() {
    // Deliberately ignores the preview's own payload -- runOrganizeExisting
    // always re-scans and re-plans against the real, current filesystem
    // state, so a preview that's gone stale (a file changed since it was
    // shown) can never cause the wrong thing to be organized.
    await runOrganizeExisting();
    previewCancelledRef.current = true;
    setPreviewOpen(false);
  }

  async function pollForAgentUnclassifiedCommand(commandId) {
    // Same cadence/attempt budget as pollForAgentPreview above -- the agent
    // discovery step this reuses (preview_organize_existing) is identical,
    // just consumed by a different follow-up call once it completes.
    for (let attempt = 0; attempt < 30; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      if (unclassifiedCancelledRef.current) return null;
      try {
        const commands = await getAgentCommands({ type: "preview_organize_existing", limit: 1 });
        if (commands[0]?.status === "done") return commandId;
      } catch {
        return null;
      }
    }
    return null;
  }

  async function handleOpenUnclassified() {
    if (unclassifiedOpen) return;
    unclassifiedCancelledRef.current = false;
    setUnclassifiedOpen(true);
    setUnclassifiedLoading(true);
    setUnclassifiedWaitingForAgent(false);
    setUnclassifiedError("");
    setUnclassifiedResult(null);
    setUnclassifiedIgnored(new Set());
    try {
      const first = await getUnclassifiedSuggestions();
      if (unclassifiedCancelledRef.current) return;
      if (first.queued) {
        setUnclassifiedLoading(false);
        setUnclassifiedWaitingForAgent(true);
        const readyCommandId = await pollForAgentUnclassifiedCommand(first.command_id);
        if (unclassifiedCancelledRef.current) return;
        setUnclassifiedWaitingForAgent(false);
        if (!readyCommandId) {
          setUnclassifiedError("Your agent didn't respond in time -- try again.");
          return;
        }
        setUnclassifiedLoading(true);
        const final = await getUnclassifiedSuggestions(readyCommandId);
        if (unclassifiedCancelledRef.current) return;
        setUnclassifiedResult(final);
        return;
      }
      setUnclassifiedResult(first);
    } catch {
      if (!unclassifiedCancelledRef.current) {
        setUnclassifiedError("Couldn't get AI suggestions -- try again.");
      }
    } finally {
      if (!unclassifiedCancelledRef.current) setUnclassifiedLoading(false);
    }
  }

  function handleCloseUnclassified() {
    unclassifiedCancelledRef.current = true;
    setUnclassifiedOpen(false);
    setUnclassifiedResult(null);
    setUnclassifiedError("");
    setUnclassifiedLoading(false);
    setUnclassifiedWaitingForAgent(false);
  }

  function handleIgnoreSuggestion(suggestion) {
    setUnclassifiedIgnored((prev) => new Set(prev).add(suggestion.group_key));
  }

  async function handleCreateRuleFromSuggestion(suggestion) {
    if (unclassifiedCreatingKey || !suggestion.suggested_rule) return;
    setUnclassifiedCreatingKey(suggestion.group_key);
    try {
      await saveRules((current) =>
        applyRuleToDoc(current, suggestion.suggested_rule.rule_type, proposalFields(suggestion.suggested_rule)),
      );
      handleIgnoreSuggestion(suggestion); // saved -- drop it from the list, same as "Ignore"
    } catch {
      setUnclassifiedError("Couldn't save that rule -- try again.");
    } finally {
      setUnclassifiedCreatingKey(null);
    }
  }

  async function pollForAgentDuplicateCommand(commandId) {
    // Same polling cadence/attempt budget as pollForAgentPreview /
    // pollForAgentUnclassifiedCommand above.
    for (let attempt = 0; attempt < 30; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      if (duplicatesCancelledRef.current) return null;
      try {
        const commands = await getAgentCommands({ type: "duplicate_analysis", limit: 1 });
        if (commands[0]?.status === "done") return commandId;
      } catch {
        return null;
      }
    }
    return null;
  }

  async function runDuplicateAnalysis() {
    duplicatesCancelledRef.current = false;
    setDuplicatesLoading(true);
    setDuplicatesWaitingForAgent(false);
    setDuplicatesError("");
    setDuplicatesResult(null);
    try {
      const first = await analyzeDuplicates();
      if (duplicatesCancelledRef.current) return;
      if (first.queued) {
        setDuplicatesLoading(false);
        setDuplicatesWaitingForAgent(true);
        const readyCommandId = await pollForAgentDuplicateCommand(first.command_id);
        if (duplicatesCancelledRef.current) return;
        setDuplicatesWaitingForAgent(false);
        if (!readyCommandId) {
          setDuplicatesError("Your agent didn't respond in time -- try again.");
          return;
        }
        setDuplicatesLoading(true);
        const final = await analyzeDuplicates(readyCommandId);
        if (duplicatesCancelledRef.current) return;
        setDuplicatesResult(final);
        return;
      }
      setDuplicatesResult(first);
    } catch {
      if (!duplicatesCancelledRef.current) {
        setDuplicatesError("Couldn't check for duplicate files -- try again.");
      }
    } finally {
      if (!duplicatesCancelledRef.current) setDuplicatesLoading(false);
    }
  }

  function handleOpenDuplicates() {
    if (duplicatesOpen) return;
    setDuplicatesOpen(true);
    runDuplicateAnalysis();
  }

  function handleRefreshDuplicates() {
    if (duplicatesLoading || duplicatesWaitingForAgent) return;
    runDuplicateAnalysis();
  }

  function handleCloseDuplicates() {
    duplicatesCancelledRef.current = true;
    setDuplicatesOpen(false);
    setDuplicatesResult(null);
    setDuplicatesError("");
    setDuplicatesLoading(false);
    setDuplicatesWaitingForAgent(false);
  }

  function handleReviewDuplicateGroup(group, index) {
    setDuplicateDetailGroup(group);
    setDuplicateDetailIndex(index);
  }

  function handleCloseDuplicateDetail() {
    setDuplicateDetailGroup(null);
  }

  async function pollForAgentSearchCommand(commandId) {
    // Same polling cadence/attempt budget as every other agent-command
    // poll above.
    for (let attempt = 0; attempt < 30; attempt++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      if (searchCancelledRef.current) return null;
      try {
        const commands = await getAgentCommands({ type: "file_search", limit: 1 });
        if (commands[0]?.status === "done") return commandId;
      } catch {
        return null;
      }
    }
    return null;
  }

  function handleOpenSearch() {
    setSearchOpen(true);
  }

  async function handleRunSearch() {
    if (!searchPrompt.trim() || searching || searchWaitingForAgent) return;
    searchCancelledRef.current = false;
    setSearching(true);
    setSearchWaitingForAgent(false);
    setSearchError("");
    setSearchResult(null);
    try {
      const first = await searchFiles(searchPrompt.trim());
      if (searchCancelledRef.current) return;
      if (first.queued) {
        setSearching(false);
        setSearchWaitingForAgent(true);
        const readyCommandId = await pollForAgentSearchCommand(first.command_id);
        if (searchCancelledRef.current) return;
        setSearchWaitingForAgent(false);
        if (!readyCommandId) {
          setSearchError("Your agent didn't respond in time -- try again.");
          return;
        }
        setSearching(true);
        const final = await searchFiles(searchPrompt.trim(), readyCommandId);
        if (searchCancelledRef.current) return;
        setSearchResult(final);
        return;
      }
      setSearchResult(first);
    } catch {
      if (!searchCancelledRef.current) {
        setSearchError("Couldn't search your files -- try again.");
      }
    } finally {
      if (!searchCancelledRef.current) setSearching(false);
    }
  }

  function handleClearSearch() {
    setSearchPrompt("");
    setSearchResult(null);
    setSearchError("");
  }

  function handleCloseSearch() {
    searchCancelledRef.current = true;
    setSearchOpen(false);
    setSearchPrompt("");
    setSearchResult(null);
    setSearchError("");
    setSearching(false);
    setSearchWaitingForAgent(false);
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

        {/* FileFlow Health */}
        <motion.div variants={itemVariants}>
          <HealthDashboard
            data={health}
            loading={healthLoading}
            error={healthError}
            refreshing={healthRefreshing}
            onRefresh={handleRefreshHealth}
            onReviewUnclassified={handleOpenUnclassified}
            onReviewDuplicates={handleOpenDuplicates}
          />
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
          ].map((card) => (
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
              onClick={handleOpenPreview}
              disabled={organizing}
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-1)] hover:bg-[var(--gridline)]/50 hover:border-[var(--brand)]/30 px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-all cursor-pointer disabled:opacity-50"
            >
              {organizing ? "Organizing…" : "Organize existing files now"}
            </motion.button>
          </div>
          {organizeError && (
            <p className="mt-3 text-xs font-medium text-[var(--status-critical)]">
              {organizeError}
            </p>
          )}
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

        {/* Unclassified Files */}
        <motion.div
          variants={itemVariants}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium text-[var(--text-primary)]">Unclassified files</h2>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Ask AI what a file with no matching rule might be, and get a rule suggestion to
                review -- nothing is saved or moved automatically.
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleOpenUnclassified}
              disabled={unclassifiedOpen && (unclassifiedLoading || unclassifiedWaitingForAgent)}
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-1)] hover:bg-[var(--gridline)]/50 hover:border-[var(--brand)]/30 px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-all cursor-pointer disabled:opacity-50"
            >
              Get AI Suggestions
            </motion.button>
          </div>
        </motion.div>

        {/* Duplicate Files */}
        <motion.div
          variants={itemVariants}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium text-[var(--text-primary)]">Duplicate files</h2>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Find files with identical content across your watch folder -- nothing is deleted or
                changed automatically.
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleOpenDuplicates}
              disabled={duplicatesOpen && (duplicatesLoading || duplicatesWaitingForAgent)}
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-1)] hover:bg-[var(--gridline)]/50 hover:border-[var(--brand)]/30 px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-all cursor-pointer disabled:opacity-50"
            >
              Find Duplicates
            </motion.button>
          </div>
        </motion.div>

        {/* Search your files */}
        <motion.div
          variants={itemVariants}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-medium text-[var(--text-primary)]">Search your files</h2>
              <p className="mt-1 text-xs text-[var(--text-muted)]">
                Describe what you're looking for in plain language -- FileFlow searches file names,
                types, sizes, dates, and locations, never file contents.
              </p>
            </div>
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={handleOpenSearch}
              className="shrink-0 rounded-md border border-[var(--border)] bg-[var(--surface-1)] hover:bg-[var(--gridline)]/50 hover:border-[var(--brand)]/30 px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] transition-all cursor-pointer"
            >
              Search Files
            </motion.button>
          </div>
        </motion.div>

        {/* Recent undo/reclassify agent activity */}
        <motion.div
          variants={itemVariants}
          className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur p-5 shadow-sm"
        >
          <h2 className="mb-3 text-sm font-medium text-[var(--text-primary)]">Recent activity</h2>
          <RecentAgentActivity />
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
            {categoryStats && <CategoryDonut data={categoryStats} />}
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
            {actionError && (
              <p className="mb-2 text-xs font-medium text-[var(--status-critical)]">
                {actionError}
              </p>
            )}
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
              {rules?.keyword_rules.map((r, i) => (
                <span
                  // Keyword rules have no id and the same keyword may legitimately
                  // appear more than once (a redundant or shadowed rule -- the Rule
                  // Conflict Detector reports exactly that), so the position in the
                  // list is part of the key. The chips are stateless.
                  key={`${r.keyword}-${i}`}
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

      <OrganizePreviewDialog
        open={previewOpen}
        onOpenChange={(open) => {
          if (!open) handleCancelPreview();
        }}
        loading={previewLoading}
        waitingForAgent={previewWaitingForAgent}
        error={previewError}
        preview={preview}
        confirming={organizing}
        onCancel={handleCancelPreview}
        onConfirm={handleConfirmOrganize}
      />

      <UnclassifiedSuggestionsDialog
        open={unclassifiedOpen}
        onOpenChange={(open) => {
          if (!open) handleCloseUnclassified();
        }}
        loading={unclassifiedLoading}
        waitingForAgent={unclassifiedWaitingForAgent}
        error={unclassifiedError}
        result={unclassifiedResult}
        ignoredKeys={unclassifiedIgnored}
        creatingKey={unclassifiedCreatingKey}
        onCreateRule={handleCreateRuleFromSuggestion}
        onIgnore={handleIgnoreSuggestion}
        onClose={handleCloseUnclassified}
      />

      <DuplicateGroupsDialog
        open={duplicatesOpen}
        onOpenChange={(open) => {
          if (!open) handleCloseDuplicates();
        }}
        loading={duplicatesLoading}
        waitingForAgent={duplicatesWaitingForAgent}
        error={duplicatesError}
        result={duplicatesResult}
        onRefresh={handleRefreshDuplicates}
        onReviewGroup={handleReviewDuplicateGroup}
        onClose={handleCloseDuplicates}
      />

      <DuplicateGroupDetailDialog
        open={duplicateDetailGroup !== null}
        onOpenChange={(open) => {
          if (!open) handleCloseDuplicateDetail();
        }}
        group={duplicateDetailGroup}
        groupNumber={duplicateDetailIndex + 1}
        onClose={handleCloseDuplicateDetail}
      />

      <FileSearchDialog
        open={searchOpen}
        onOpenChange={(open) => {
          if (!open) handleCloseSearch();
        }}
        prompt={searchPrompt}
        onPromptChange={setSearchPrompt}
        searching={searching}
        waitingForAgent={searchWaitingForAgent}
        result={searchResult}
        error={searchError}
        onSearch={handleRunSearch}
        onClear={handleClearSearch}
        onClose={handleCloseSearch}
      />
    </>
  );
}
