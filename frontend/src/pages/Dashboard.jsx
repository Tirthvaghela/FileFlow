import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import PageHeading from "../components/PageHeading.jsx";
import Kicker from "../components/Kicker.jsx";
import FileBadge from "../components/FileBadge.jsx";
import HighlightName from "../components/HighlightName.jsx";
import Stamp from "../components/ui/Stamp.jsx";
import WeeklyChart from "../components/WeeklyChart.jsx";
import PipelineFlow from "../components/PipelineFlow.jsx";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import OrganizePreviewDialog from "../components/ui/OrganizePreviewDialog.jsx";
import UnclassifiedSuggestionsDialog from "../components/ui/UnclassifiedSuggestionsDialog.jsx";
import DuplicateGroupsDialog from "../components/ui/DuplicateGroupsDialog.jsx";
import DuplicateGroupDetailDialog from "../components/ui/DuplicateGroupDetailDialog.jsx";
import FileSearchDialog from "../components/ui/FileSearchDialog.jsx";
import HealthDashboard, { HealthHeaderControls } from "../components/ui/HealthDashboard.jsx";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../components/ui/dialog.jsx";
import {
  analyzeDuplicates,
  getAgentCommands,
  getCategories,
  getLogs,
  getOrganizationHealth,
  getStats,
  getUnclassifiedSuggestions,
  getWeeklyReports,
  organizeExistingFiles,
  previewOrganizeExisting,
  searchFiles,
} from "../services/api.js";
import { applyRuleToDoc, proposalFields } from "../utils/ruleForm.js";
import { groupLogsByTier, ORGANIZED_ACTIONS, pad2, tierFor } from "../utils/ruleTiers.js";
import { folderName, relativeTime, stampFor } from "../utils/activity.js";
import { useRules } from "../context/RulesContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";

// "FRI · 23 OCT 2026" -- the manila date chip in the machine room.
function dateChip(d = new Date()) {
  const wd = d.toLocaleDateString("en-GB", { weekday: "short" }).toUpperCase();
  const mon = d.toLocaleDateString("en-GB", { month: "short" }).toUpperCase();
  return `${wd} · ${pad2(d.getDate())} ${mon} ${d.getFullYear()}`;
}

// Split-flap counter: one 64x88 tile per digit of the real today count.
function FlapDigits({ value }) {
  const str = value == null ? "—" : String(value);
  return (
    <div role="img" aria-label={`${str} files filed today`} className="flex gap-[5px]">
      {str.split("").map((ch, i) => (
        <span
          key={i}
          className="ff-pop relative grid h-[88px] w-[64px] place-items-center rounded-[5px] border border-[var(--rule-2)] font-mono-data text-[64px] font-bold leading-none tracking-[-0.04em] text-[var(--ink)]"
          style={{
            background: "linear-gradient(var(--sheet-2) 0 50%, var(--rule) 50% 100%)",
            boxShadow: "0 8px 16px -10px rgba(0,0,0,.8)",
            animationDelay: `${i * 60}ms`,
          }}
        >
          {ch}
          <span aria-hidden="true" className="absolute inset-x-0 top-1/2 h-px bg-black/55" />
        </span>
      ))}
    </div>
  );
}

// 24h strip of today's real organized-file timestamps: hour ticks along
// the bottom, one 8px manila square per file (latest red), red "now" line.
// Files filed within a few minutes of each other stack upward.
function DayTimeline({ logs }) {
  const now = new Date();
  const dayStart = new Date(now);
  dayStart.setHours(0, 0, 0, 0);
  const dayMs = 24 * 60 * 60 * 1000;
  const nowPct = ((now - dayStart) / dayMs) * 100;
  const points = logs
    .map((l) => ({ t: new Date(l.timestamp), x: Math.min(100, Math.max(0, ((new Date(l.timestamp) - dayStart) / dayMs) * 100)) }))
    .sort((a, b) => a.x - b.x);
  let prevX = -10;
  let level = 0;
  const placed = points.map((p) => {
    level = p.x - prevX < 1.2 ? (level + 1) % 2 : 0;
    prevX = p.x;
    return { ...p, y: level * 10 + 6 };
  });
  const nowLabel = now.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });

  return (
    <div aria-hidden="true" className="hidden flex-col gap-[5px] min-[420px]:flex">
      <div
        className="relative h-[26px] border-b border-[var(--rule-2)]"
        style={{
          backgroundImage: "linear-gradient(90deg, var(--rule-2) 1px, transparent 1px)",
          backgroundSize: "calc(100% / 24) 6px",
          backgroundRepeat: "repeat-x",
          backgroundPosition: "0 100%",
        }}
      >
        <span className="absolute bottom-[-1px] left-0 h-[2px] bg-[var(--ink-2)] opacity-50" style={{ width: `${nowPct}%` }} />
        {placed.map((p, i) => (
          <span
            key={i}
            title={p.t.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false })}
            className="ff-in absolute ml-[-4px] h-2 w-2 rounded-[2px]"
            style={{
              left: `${p.x}%`,
              bottom: p.y,
              background: i === placed.length - 1 ? "var(--stamp)" : "var(--manila)",
              animationDelay: `${200 + i * 35}ms`,
            }}
          />
        ))}
        <span className="absolute bottom-[-4px] top-[-2px] w-[1.5px] bg-[var(--stamp)]" style={{ left: `${nowPct}%` }} />
        <span className="absolute top-[-6px] ml-[-3px] h-[7px] w-[7px] rounded-full bg-[var(--stamp)]" style={{ left: `${nowPct}%` }} />
      </div>
      <div className="flex justify-between font-mono-data text-[10px] text-[var(--ink-muted)]">
        <span>00:00</span>
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
        <span className="text-[var(--stamp)]">now {nowLabel}</span>
      </div>
    </div>
  );
}

function plural(n, noun) {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

function listJoin(items) {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

export default function Dashboard() {
  const { logs, refresh } = useLiveLogs(6);
  const { rules, saveRules } = useRules();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [statsError, setStatsError] = useState(false);
  const [healthOpen, setHealthOpen] = useState(false);
  const [agentCommands, setAgentCommands] = useState([]);
  const [stats, setStats] = useState(null);
  const [categoryStats, setCategoryStats] = useState(null);
  const [weekLogs, setWeekLogs] = useState([]);
  const [organizing, setOrganizing] = useState(false);
  const [organizeResult, setOrganizeResult] = useState(null);
  const [organizeError, setOrganizeError] = useState("");
  const [thisWeek, setThisWeek] = useState(null);

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
      .then((s) => {
        setStats(s);
        setStatsError(false);
      })
      .catch(() => setStatsError(true));
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
    // Enough rows to cover a busy week for the "by rule tier" breakdown
    // below -- grouped client-side from explanation.match_type, the same
    // field the classifier already stamps onto every log (no new backend
    // aggregation endpoint needed).
    getLogs(500)
      .then(setWeekLogs)
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
    // Recent undo/reclassify commands sent to the remote agent -- any still
    // waiting, or failed in the last day, surface as a "Needs you" item.
    const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
    Promise.all([getAgentCommands({ type: "undo", limit: 10 }), getAgentCommands({ type: "reclassify", limit: 10 })])
      .then(([u, r]) => {
        const recent = [...(u || []), ...(r || [])].filter(
          (c) => c.status === "pending" || new Date(c.completed_at || c.created_at).getTime() >= dayAgo,
        );
        setAgentCommands(recent);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [logs[0]?.id]);

  function handleRefreshHealth() {
    if (healthLoading || healthRefreshing) return;
    loadHealth({ refreshing: true });
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

  const unclassifiedCount =
    health?.files?.status === "available" && health.files.unclassified > 0 ? health.files.unclassified : 0;
  const conflictsCount =
    health?.rules?.status === "available" && health.rules.conflicts_total > 0 ? health.rules.conflicts_total : 0;
  const waitingCount = health?.files?.status === "available" ? health.files.scanned : null;

  const weekAgoMs = Date.now() - 7 * 24 * 60 * 60 * 1000;
  const tiers = groupLogsByTier(weekLogs, { sinceMs: weekAgoMs });
  const tiersWithActivity = tiers.filter((t) => t.count > 0);
  const idleTiers = tiers.filter((t) => t.count === 0).map((t) => t.label);
  const maxTierCount = Math.max(1, ...tiers.map((t) => t.count));
  const weekTierTotal = tiers.reduce((sum, t) => sum + t.count, 0);

  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayLogs = weekLogs.filter(
    (l) => !l.undone && ORGANIZED_ACTIONS.has(l.action) && new Date(l.timestamp) >= todayStart,
  );

  const categoryFilesTotal = categoryStats ? categoryStats.reduce((sum, c) => sum + c.count, 0) : null;
  const last7 = stats?.last_7_days ? [...stats.last_7_days].sort((a, b) => a.date.localeCompare(b.date)).slice(-7) : [];
  const sparkMax = Math.max(1, ...last7.map((d) => d.count));

  // The same four machine-room metrics at every breakpoint.
  const ledger = [
    {
      label: "filed this week",
      value: thisWeek?.files_organized ?? "—",
      onClick: () => navigate("/app/reports"),
      spark: last7.length > 0,
    },
    { label: "in category folders", value: categoryFilesTotal ?? "—", onClick: () => navigate("/app/categories") },
    {
      label: "unclassified",
      value: health?.files?.status === "available" ? health.files.unclassified : "—",
      color: unclassifiedCount > 0 ? "var(--warn)" : undefined,
      onClick: handleOpenUnclassified,
    },
    {
      label: "rule conflicts",
      value: health?.rules?.status === "available" ? health.rules.conflicts_total : "—",
      color: conflictsCount > 0 ? "var(--stamp)" : undefined,
      onClick: () => navigate("/app/rules"),
    },
  ];

  const pendingAgent = agentCommands.filter((c) => c.status === "pending").length;
  const failedAgent = agentCommands.filter((c) => c.status === "done" && c.success === false).length;

  const attention = [];
  if (conflictsCount > 0) {
    attention.push({
      key: "conflicts",
      value: conflictsCount,
      title: "Rule conflicts",
      sub:
        health.rules.conflicts_high > 0
          ? `${plural(health.rules.conflicts_high, "rule")} can never match`
          : "Review on the Rules page",
      color: "var(--stamp)",
      onClick: () => navigate("/app/rules"),
    });
  }
  if (unclassifiedCount > 0) {
    attention.push({
      key: "unclassified",
      value: unclassifiedCount,
      title: "Unclassified files",
      sub: "No rule matched · get AI suggestions",
      color: "var(--warn)",
      onClick: handleOpenUnclassified,
    });
  }
  if (pendingAgent + failedAgent > 0) {
    attention.push({
      key: "agent",
      value: pendingAgent + failedAgent,
      title: "Agent commands",
      sub: [failedAgent && `${failedAgent} failed`, pendingAgent && `${pendingAgent} waiting`].filter(Boolean).join(" · "),
      color: failedAgent ? "var(--stamp)" : "var(--warn)",
      onClick: () => navigate("/app/activity#agent-commands"),
    });
  }

  const tools = [
    { key: "01 / search", title: "Search your files", hint: "Describe a file in plain words.", onClick: handleOpenSearch },
    {
      key: "02 / dupes",
      title: "Find duplicate files",
      hint: "Identical content, grouped.",
      onClick: handleOpenDuplicates,
      disabled: duplicatesOpen && (duplicatesLoading || duplicatesWaitingForAgent),
    },
    { key: "03 / health", title: "Organization health", hint: "Monitoring, agent, conflicts, backlog.", onClick: () => setHealthOpen(true) },
  ];

  const slips = logs.slice(0, 5);
  const weekRange =
    last7.length > 0
      ? `${new Date(`${last7[0].date}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" })} – ${new Date(
          `${last7[last7.length - 1].date}T00:00:00`,
        ).toLocaleDateString(undefined, { day: "numeric", month: "short" })}`
      : null;

  return (
    <>
      <PageHeading index={1} kicker="Intake desk" title="Dashboard" subtitle="What came in, where it went, and what needs you." />

      <div className="ff-in flex flex-col gap-[22px]">
        {organizeResult && (
          <div role="status" className="flex flex-wrap items-center gap-2.5 rounded-[4px] bg-[var(--filed-bg)] px-3.5 py-2.5 text-[var(--filed)]">
            <Stamp tone="filed" pop>
              {organizeResult.queued ? "Queued" : "Filed"}
            </Stamp>
            <span className="text-[13px]">
              {organizeResult.queued
                ? "Queued — your agent will pick this up shortly."
                : `Organize existing files scanned ${organizeResult.scanned}, moved ${organizeResult.organized}, skipped ${plural(
                    organizeResult.duplicates,
                    "duplicate",
                  )}${organizeResult.errors > 0 ? `, ${plural(organizeResult.errors, "error")}` : ""}.`}
            </span>
            <Link to="/app/activity" className="ml-auto text-[13px] text-[var(--filed)]">
              See Activity
            </Link>
          </div>
        )}
        {organizeError && (
          <div role="alert" className="rounded-[4px] bg-[var(--stamp-bg)] px-3.5 py-2.5 text-[13px] text-[var(--stamp)]">
            {organizeError}
          </div>
        )}

        {/* Row 1: machine room + your desk */}
        <div className="flex flex-wrap items-stretch gap-[22px]">
          <section
            data-ink=""
            aria-label="Machine room"
            className="flex min-w-0 flex-[1_1_640px] flex-col gap-[18px] rounded-[6px] border border-[var(--rule-2)] bg-[var(--sheet)] p-4 sm:p-[22px]"
            style={{ boxShadow: "0 30px 60px -36px rgba(0,0,0,.7)" }}
          >
            <div className="flex flex-wrap items-end gap-x-7 gap-y-4">
              <div className="flex min-w-0 flex-[1_1_360px] flex-col gap-3.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex h-6 items-center gap-[7px] whitespace-nowrap rounded-full border border-[var(--rule-2)] pl-2 pr-2.5 text-[11.5px] font-semibold">
                    <span
                      className="h-[7px] w-[7px] rounded-full"
                      style={{
                        background: running ? "var(--filed)" : "var(--rule-2)",
                        boxShadow: `0 0 0 3px ${running ? "rgba(108,199,155,.18)" : "rgba(255,255,255,.06)"}`,
                      }}
                    />
                    Auto-sort {running ? "on" : "off"}
                  </span>
                  <span className="inline-flex h-6 items-center whitespace-nowrap rounded-[2px] bg-[var(--manila)] px-[9px] font-mono-data text-[11px] font-semibold tracking-[0.04em] text-[var(--manila-ink)]">
                    {dateChip()}
                  </span>
                </div>

                {statsError ? (
                  <span className="ff-kicker">Today's count unavailable</span>
                ) : (
                  <>
                    <div className="flex flex-wrap items-center gap-[18px]">
                      <FlapDigits value={stats?.today_count} />
                      <div className="flex min-w-0 flex-col gap-1.5">
                        <b className="ff-display text-[22px] leading-none">files filed today</b>
                        <span className="flex flex-wrap gap-x-2.5 gap-y-1 text-[12.5px] text-[var(--ink-2)]">
                          {waitingCount != null && (
                            <span className="whitespace-nowrap">
                              {waitingCount} waiting in {folderName(user?.watch_folder) || "the watched folder"}
                            </span>
                          )}
                          <span className="whitespace-nowrap text-[var(--ink-muted)]">
                            {logs[0] ? `last one ${relativeTime(logs[0].timestamp)}` : "no activity yet"}
                          </span>
                        </span>
                      </div>
                    </div>
                    <DayTimeline logs={todayLogs} />
                  </>
                )}
              </div>

              <div className="grid w-full grid-cols-2 overflow-hidden rounded-[4px] border border-[var(--rule-2)] sm:ml-auto sm:w-auto sm:grid-cols-[repeat(2,minmax(120px,1fr))]">
                {ledger.map((k, i) => (
                  <button
                    key={k.label}
                    type="button"
                    onClick={k.onClick}
                    className={`flex flex-col gap-0.5 border-0 border-[var(--rule)] bg-transparent px-3 py-2.5 text-left text-[var(--ink)] transition-colors hover:bg-[var(--sheet-2)] ${
                      i % 2 === 0 ? "border-r" : ""
                    } ${i < 2 ? "border-b" : ""}`}
                  >
                    <span className="flex items-end gap-2">
                      <span className="font-mono-data text-[20px] font-semibold tracking-[-0.02em]" style={{ color: k.color }}>
                        {k.value}
                      </span>
                      {k.spark && (
                        <span aria-hidden="true" className="flex h-[18px] items-end gap-[2px] pb-1">
                          {last7.map((d, j) => (
                            <span
                              key={d.date}
                              className="w-1 rounded-[1px]"
                              style={{
                                height: `${Math.max(1, Math.round((d.count / sparkMax) * 14))}px`,
                                background: j === last7.length - 1 ? "var(--stamp)" : "var(--ink-2)",
                              }}
                            />
                          ))}
                        </span>
                      )}
                    </span>
                    <span className="text-[11.5px] text-[var(--ink-muted)]">{k.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col border-t border-[var(--rule-2)]">
              <div className="flex items-center gap-2.5 pb-1.5 pt-2.5">
                <span className="ff-kicker">This week by rule tier</span>
                <span className="flex-1" />
                <span className="font-mono-data text-[11px] text-[var(--ink-muted)]">{plural(weekTierTotal, "file")}</span>
              </div>
              {tiersWithActivity.length === 0 ? (
                <p className="m-0 py-3 text-[12.5px] text-[var(--ink-muted)]">
                  Nothing has gone through the sorter this week. Download a file, or use Downloads → Simulate a download.
                </p>
              ) : (
                tiersWithActivity.map((t) => (
                  <div
                    key={t.matchType}
                    className="grid items-center gap-x-3.5 gap-y-1.5 border-b border-[var(--rule)] py-[9px]"
                    style={{ gridTemplateColumns: "minmax(84px,130px) minmax(0,1fr) 28px" }}
                  >
                    <span className="flex min-w-0 items-baseline gap-2">
                      <span className="font-mono-data text-[10.5px] text-[var(--ink-muted)]">{pad2(t.n)}</span>
                      <span className="truncate text-[13px] font-semibold">{t.label}</span>
                    </span>
                    <span className="flex min-w-0 flex-col gap-1.5">
                      <span aria-hidden="true" className="h-1.5 overflow-hidden rounded-[3px] bg-[var(--rule)]">
                        <span
                          className="block h-full rounded-[3px]"
                          style={{ width: `${(t.count / maxTierCount) * 100}%`, background: t.n === 1 ? "var(--stamp)" : "var(--ink-2)" }}
                        />
                      </span>
                      {t.categories.length > 0 && (
                        <span className="font-mono-data text-[11.5px] text-[var(--ink-muted)]" style={{ overflowWrap: "anywhere" }}>
                          {t.categories.map(([name, n]) => `${name} ${n}`).join(" · ")}
                        </span>
                      )}
                    </span>
                    <span className="text-right font-mono-data text-[13px] font-semibold">{t.count}</span>
                  </div>
                ))
              )}
              {idleTiers.length > 0 && tiersWithActivity.length > 0 && (
                <span className="pt-2 text-[12px] text-[var(--ink-muted)]">{listJoin(idleTiers)} caught nothing this week.</span>
              )}
            </div>
          </section>

          <aside aria-label="Your desk" className="flex min-w-0 flex-[1_1_300px] flex-col gap-[18px]">
            <button
              type="button"
              onClick={handleOpenPreview}
              disabled={organizing}
              className="relative cursor-pointer border-none bg-transparent p-0 pt-3.5 text-left transition-transform hover:-translate-y-[3px] active:-translate-y-px disabled:opacity-60"
              style={{ transitionDuration: "var(--d2)" }}
            >
              <span aria-hidden="true" className="absolute left-0 top-0 h-[18px] w-[46%] rounded-[6px_6px_0_0] bg-[var(--manila-2)]" />
              <span
                className="relative flex flex-col gap-2.5 rounded-[0_6px_6px_6px] bg-[var(--manila)] p-[18px] text-[var(--manila-ink)]"
                style={{ boxShadow: "0 16px 26px -18px var(--shade)" }}
              >
                <span className="text-[10.5px] font-bold uppercase tracking-[0.14em] opacity-75" style={{ fontStretch: "125%" }}>
                  Manual sweep
                </span>
                <b className="ff-display text-[24px] leading-[1.05]">Organize existing files</b>
                <span className="text-[13px] leading-[1.4]">
                  See where every file already in {folderName(user?.watch_folder) || "the watched folder"} would go. Nothing moves until you
                  confirm.
                </span>
                <span className="mt-1 flex items-center justify-between border-t border-dashed border-[rgba(63,49,13,.35)] pt-2.5 text-[13px] font-bold">
                  Preview the plan
                  <span aria-hidden="true" className="text-[18px]">
                    →
                  </span>
                </span>
              </span>
            </button>

            <div className="flex flex-col gap-1.5">
              <Kicker>Needs you</Kicker>
              {attention.map((n) => (
                <button
                  key={n.key}
                  type="button"
                  onClick={n.onClick}
                  className="flex cursor-pointer items-center gap-2.5 rounded-[0_4px_4px_0] border-0 bg-[var(--sheet-2)] px-3 py-2.5 text-left transition-transform hover:translate-x-[3px]"
                  style={{ borderLeft: `3px solid ${n.color}` }}
                >
                  <span className="min-w-[28px] font-mono-data text-[20px] font-semibold" style={{ color: n.color }}>
                    {n.value}
                  </span>
                  <span className="flex flex-1 flex-col gap-px">
                    <b className="text-[13px]">{n.title}</b>
                    <span className="text-[12px] text-[var(--ink-muted)]">{n.sub}</span>
                  </span>
                  <span aria-hidden="true">→</span>
                </button>
              ))}
              {attention.length === 0 && health && !healthError && (
                <p className="m-0 text-[13px] text-[var(--ink-muted)]">Nothing is waiting on you.</p>
              )}
              {healthError && <p className="m-0 text-[13px] text-[var(--stamp)]">Unknown until health loads.</p>}
            </div>

            <div className="grid grid-cols-3 gap-2">
              {tools.map((a) => (
                <button
                  key={a.key}
                  type="button"
                  onClick={a.onClick}
                  disabled={a.disabled}
                  title={a.hint}
                  className="flex min-h-[84px] cursor-pointer flex-col justify-between gap-2 rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet)] p-3 text-left transition-[border-color,transform] hover:-translate-y-0.5 hover:border-[var(--ink)] disabled:opacity-60 sm:min-h-[100px]"
                  style={{ transitionDuration: "var(--d2)" }}
                >
                  <span className="font-mono-data text-[10.5px] font-semibold text-[var(--stamp)]">{a.key}</span>
                  <b className="text-[13px] leading-[1.2]">{a.title}</b>
                </button>
              ))}
            </div>
          </aside>
        </div>

        {/* Row 2: latest slips (receipt) + this week / pigeonholes */}
        <div className="flex flex-wrap items-start gap-[22px]">
          <section
            aria-label="Latest activity"
            className="relative min-w-0 flex-[3_1_520px] rounded-[0_0_4px_4px] bg-[var(--sheet-2)] px-[18px] pb-2 pt-3.5"
            style={{ boxShadow: "0 1px 0 var(--rule-2)" }}
          >
            <span
              aria-hidden="true"
              className="absolute inset-x-0 top-[-6px] h-3"
              style={{
                backgroundImage: "radial-gradient(circle at 6px 6px, var(--sheet) 4px, transparent 4.5px)",
                backgroundSize: "14px 12px",
              }}
            />
            <Kicker
              className="mb-0.5 mt-1"
              right={
                <Link to="/app/activity" className="text-[12px] text-[var(--ink)] underline decoration-[var(--manila-2)] underline-offset-[3px] hover:text-[var(--stamp)]">
                  All activity
                </Link>
              }
            >
              Latest slips
            </Kicker>
            {slips.length === 0 ? (
              <div className="py-[22px] text-[13px] text-[var(--ink-muted)]">
                No slips yet — drop a file into the watched folder to see it here.
              </div>
            ) : (
              slips.map((log, i) => {
                const stamp = stampFor(log);
                const tier = tierFor(log.explanation?.match_type);
                const why = tier
                  ? `Tier ${tier.n} · ${tier.label}${log.explanation?.matched_value ? ` ${log.explanation.matched_value}` : ""}`
                  : null;
                return (
                  <button
                    key={log.id}
                    type="button"
                    onClick={() => navigate(`/app/activity?open=${log.id}`)}
                    title="Open in Activity"
                    className="ff-in flex w-full cursor-pointer items-center gap-3 border-0 border-b border-dashed border-[var(--rule-2)] bg-transparent py-[11px] text-left last:border-b-0"
                    style={{ animationDelay: `${120 + i * 50}ms` }}
                  >
                    <FileBadge filename={log.final_filename} onSheet />
                    <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                      <HighlightName
                        name={log.final_filename}
                        term={log.explanation?.matched_value}
                        className="truncate font-mono-data text-[12.5px] font-medium"
                      />
                      <span className="flex flex-wrap gap-x-2 gap-y-1 text-[12px] text-[var(--ink-muted)]">
                        <span className="whitespace-nowrap text-[var(--ink-2)]">
                          → <b className="font-semibold">{log.category}</b>
                        </span>
                        {why && <span>{why}</span>}
                      </span>
                    </span>
                    <span className="flex shrink-0 flex-col items-end gap-1">
                      <Stamp tone={stamp.tone}>{stamp.label}</Stamp>
                      <span className="font-mono-data text-[11px] text-[var(--ink-muted)]">{relativeTime(log.timestamp)}</span>
                    </span>
                  </button>
                );
              })
            )}
          </section>

          <section aria-label="This week" className="flex min-w-0 flex-[2_1_320px] flex-col gap-4">
            <div className="flex flex-col gap-2.5">
              <Kicker right={weekRange && <span className="font-mono-data text-[11px] text-[var(--ink-muted)]">{weekRange}</span>}>
                This week
              </Kicker>
              {stats ? (
                <WeeklyChart data={stats.last_7_days} />
              ) : (
                <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">{statsError ? "Weekly counts unavailable." : "Loading…"}</p>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Kicker
                right={
                  <Link to="/app/categories" className="text-[12px] text-[var(--ink)] underline decoration-[var(--manila-2)] underline-offset-[3px] hover:text-[var(--stamp)]">
                    All folders
                  </Link>
                }
              >
                Pigeonholes
              </Kicker>
              {categoryStats && categoryStats.length > 0 ? (
                <div className="grid grid-cols-3 gap-1 rounded-[4px] bg-[var(--rule)] p-1">
                  {[...categoryStats].sort((a, b) => b.count - a.count).slice(0, 6).map((c) => (
                    <Link
                      key={c.category}
                      to={`/app/categories/${encodeURIComponent(c.category)}`}
                      className="flex min-h-[70px] min-w-0 flex-col justify-between gap-1.5 rounded-[2px] bg-[var(--sheet)] p-2.5 text-[var(--ink)] no-underline transition-colors hover:bg-[var(--sheet-2)]"
                      style={{ boxShadow: "inset 0 6px 8px -6px var(--shade)" }}
                    >
                      <span className="truncate font-mono-data text-[10.5px] font-medium text-[var(--ink-muted)]">{c.category}</span>
                      <span className="font-mono-data text-[18px] font-semibold tracking-[-0.02em]">{c.count}</span>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">No files organized yet.</p>
              )}
            </div>
          </section>
        </div>

        <PipelineFlow
          running={running}
          activeRules={health?.rules?.active}
          duplicateHandling={rules?.duplicate_handling}
          totalLogged={stats?.total_files_organized}
        />
      </div>

      <Dialog open={healthOpen} onOpenChange={setHealthOpen}>
        <DialogContent tab="Health" className="max-h-[calc(100vh-60px)] overflow-y-auto p-[22px] sm:max-w-[780px]">
          <DialogHeader className="flex-row flex-wrap items-start gap-3 pr-8">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <DialogTitle className="text-[24px]">Organization health</DialogTitle>
              <DialogDescription className="text-[13px] text-[var(--ink-2)]">
                FileFlow Health — monitoring, agent, conflicts and backlog, from the latest server check.
              </DialogDescription>
            </div>
            <HealthHeaderControls data={health} loading={healthLoading} refreshing={healthRefreshing} onRefresh={handleRefreshHealth} />
          </DialogHeader>
          <HealthDashboard
            headerless
            data={health}
            loading={healthLoading}
            error={healthError}
            refreshing={healthRefreshing}
            onRefresh={handleRefreshHealth}
            onReviewUnclassified={() => {
              setHealthOpen(false);
              handleOpenUnclassified();
            }}
            onReviewDuplicates={() => {
              setHealthOpen(false);
              handleOpenDuplicates();
            }}
          />
        </DialogContent>
      </Dialog>

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
