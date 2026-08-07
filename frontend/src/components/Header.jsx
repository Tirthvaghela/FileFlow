import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { Bell, ChevronDown, Download, FileText, Search, SlidersHorizontal } from "lucide-react";
import { agentInstallerUrl, getLogs, simulateDownloadUrl } from "../services/api.js";
import { useRules } from "../context/RulesContext.jsx";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
import { buildCategoryColorMap, categoryBadge } from "../utils/categoryMeta.js";
import { actionText, relativeTime } from "../utils/activity.js";

const MAX_RESULTS_PER_GROUP = 5;
const MAX_NOTIFICATIONS = 8;

function ruleResults(rules, query) {
  if (!rules) return [];
  const q = query.toLowerCase();
  const results = [];

  const extEntries = [
    ...Object.entries(rules.extension_rules || {}),
    ...Object.entries(rules.disabled_extension_rules || {}),
  ];
  for (const [ext, folder] of extEntries) {
    if (ext.toLowerCase().includes(q) || folder.toLowerCase().includes(q)) {
      results.push({ id: `ext-${ext}`, label: ext, sublabel: `→ ${folder}` });
    }
  }

  const keywordEntries = [
    ...(rules.keyword_rules || []),
    ...(rules.disabled_keyword_rules || []),
  ];
  for (const r of keywordEntries) {
    if (r.keyword.toLowerCase().includes(q) || r.folder.toLowerCase().includes(q)) {
      results.push({ id: `kw-${r.keyword}`, label: r.keyword, sublabel: `→ ${r.folder}` });
    }
  }

  if (rules.large_file_folder && rules.large_file_folder.toLowerCase().includes(q)) {
    results.push({
      id: "size-rule",
      label: `> ${rules.large_file_threshold_mb} MB`,
      sublabel: `→ ${rules.large_file_folder}`,
    });
  }

  return results.slice(0, MAX_RESULTS_PER_GROUP);
}

function fileResults(logs, query) {
  const q = query.toLowerCase();
  const seen = new Set();
  const results = [];
  for (const log of logs) {
    if (seen.has(log.final_filename)) continue;
    if (log.final_filename.toLowerCase().includes(q)) {
      seen.add(log.final_filename);
      results.push({ id: `log-${log.id}`, label: log.final_filename, sublabel: `→ ${log.category}` });
      if (results.length >= MAX_RESULTS_PER_GROUP) break;
    }
  }
  return results;
}

export default function Header({ title, subtitle }) {
  const navigate = useNavigate();
  const { rules } = useRules();
  // Header owns its own live connection so the bell/status dot is accurate
  // on every page, not just the ones that happen to render an activity feed.
  const { logs: notifLogs, connected } = useLiveLogs(20);
  const [toast, setToast] = useState("");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [logs, setLogs] = useState([]);
  const [logsLoaded, setLogsLoaded] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [downloadOpen, setDownloadOpen] = useState(false);
  const [lastSeenId, setLastSeenId] = useState(null);
  const wrapRef = useRef(null);
  const notifRef = useRef(null);
  const downloadRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) {
        setOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(e.target)) {
        setNotifOpen(false);
      }
      if (downloadRef.current && !downloadRef.current.contains(e.target)) {
        setDownloadOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Baseline "seen" marker so pre-existing history isn't counted as unread
  // the moment the page loads -- only entries that arrive after that count.
  useEffect(() => {
    if (lastSeenId === null && notifLogs.length > 0) {
      setLastSeenId(notifLogs[0].id);
    }
  }, [notifLogs, lastSeenId]);

  const unreadCount = lastSeenId === null ? 0 : notifLogs.filter((l) => l.id > lastSeenId).length;
  // "Live" must mean automation is actually watching for new files, not
  // just that the browser has a socket open -- the socket stays connected
  // even while the user has paused monitoring from the sidebar toggle.
  const monitoring = rules?.realtime_monitoring_enabled ?? true;
  const isLive = connected && monitoring;
  const statusLabel = !connected ? "Disconnected" : monitoring ? "Live" : "Paused";
  const notifColorMap = useMemo(
    () => buildCategoryColorMap(notifLogs.map((l) => l.category)),
    [notifLogs],
  );

  function toggleNotifications() {
    setNotifOpen((v) => {
      const next = !v;
      if (next && notifLogs.length > 0) setLastSeenId(notifLogs[0].id);
      return next;
    });
  }

  function ensureLogsLoaded() {
    if (logsLoaded) return;
    setLogsLoaded(true);
    getLogs(200)
      .then(setLogs)
      .catch(() => {});
  }

  const files = useMemo(() => (query.trim() ? fileResults(logs, query.trim()) : []), [logs, query]);
  const ruleMatches = useMemo(
    () => (query.trim() ? ruleResults(rules, query.trim()) : []),
    [rules, query],
  );
  const hasResults = files.length > 0 || ruleMatches.length > 0;

  function goTo(path) {
    setOpen(false);
    setQuery("");
    navigate(path);
  }

  function handleSimulate() {
    // A genuine browser download (not a JSON call) -- it lands wherever
    // the browser saves downloads, typically the same folder FileFlow is
    // already watching, so the real pipeline picks it up naturally.
    const link = document.createElement("a");
    link.href = simulateDownloadUrl();
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setToast("Demo file downloading — FileFlow will pick it up once it lands.");
    setTimeout(() => setToast(""), 4000);
  }

  function handleAgentDownload() {
    // Same genuine-browser-download pattern as handleSimulate, just
    // pointed at the real installer instead of a demo file.
    const link = document.createElement("a");
    link.href = agentInstallerUrl();
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setToast("Downloading FileFlow Agent — run the installer once it lands.");
    setTimeout(() => setToast(""), 4000);
  }

  return (
    <header className="sticky top-0 z-10 flex items-center justify-between gap-6 border-b border-[var(--border)] bg-[var(--page)] px-8 py-5">
      <div>
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">{title}</h1>
        {subtitle && (
          <p className="mt-0.5 text-sm text-[var(--text-muted)]">{subtitle}</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        {toast && (
          <span className="hidden text-xs text-[var(--text-secondary)] lg:inline">
            {toast}
          </span>
        )}

        <div ref={wrapRef} className="relative hidden md:block">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            width={16}
            height={16}
          />
          <input
            type="text"
            value={query}
            onFocus={() => {
              ensureLogsLoaded();
              setOpen(true);
            }}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setOpen(false);
                e.currentTarget.blur();
              }
              if (e.key === "Enter" && query.trim()) {
                goTo(`/app/activity?q=${encodeURIComponent(query.trim())}`);
              }
            }}
            placeholder="Search files, rules..."
            className="w-56 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]/30"
          />

          <AnimatePresence>
          {open && query.trim() && (
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: -4 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              style={{ transformOrigin: "top right" }}
              className="absolute right-0 top-[calc(100%+6px)] z-20 w-80 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-1)] shadow-lg"
            >
              {!hasResults ? (
                <p className="px-4 py-6 text-center text-xs text-[var(--text-muted)]">
                  No matches for "{query.trim()}"
                </p>
              ) : (
                <>
                  {files.length > 0 && (
                    <div className="border-b border-[var(--border)] py-1.5">
                      <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                        Files
                      </p>
                      {files.map((r) => (
                        <button
                          key={r.id}
                          onClick={() => goTo(`/app/activity?q=${encodeURIComponent(r.label)}`)}
                          className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-[var(--gridline)]"
                        >
                          <FileText width={14} height={14} className="shrink-0 text-[var(--text-muted)]" />
                          <span className="min-w-0 flex-1 truncate text-[var(--text-primary)]">{r.label}</span>
                          <span className="shrink-0 text-xs text-[var(--text-muted)]">{r.sublabel}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {ruleMatches.length > 0 && (
                    <div className="py-1.5">
                      <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                        Rules
                      </p>
                      {ruleMatches.map((r) => (
                        <button
                          key={r.id}
                          onClick={() => goTo("/app/rules")}
                          className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm hover:bg-[var(--gridline)]"
                        >
                          <SlidersHorizontal width={14} height={14} className="shrink-0 text-[var(--text-muted)]" />
                          <span className="min-w-0 flex-1 truncate text-[var(--text-primary)]">{r.label}</span>
                          <span className="shrink-0 text-xs text-[var(--text-muted)]">{r.sublabel}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </motion.div>
          )}
          </AnimatePresence>
        </div>

        <div ref={downloadRef} className="relative">
          <button
            onClick={() => setDownloadOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-medium text-[var(--brand-foreground)] hover:opacity-90"
          >
            <Download width={16} height={16} />
            Downloads
            <ChevronDown width={14} height={14} />
          </button>

          <AnimatePresence>
          {downloadOpen && (
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: -4 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              style={{ transformOrigin: "top right" }}
              className="absolute right-0 top-[calc(100%+6px)] z-20 w-72 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-1)] shadow-lg"
            >
              <button
                onClick={() => {
                  setDownloadOpen(false);
                  handleSimulate();
                }}
                className="flex w-full flex-col items-start gap-0.5 px-4 py-2.5 text-left hover:bg-[var(--gridline)]"
              >
                <span className="text-sm font-medium text-[var(--text-primary)]">
                  Simulate a download
                </span>
                <span className="text-xs text-[var(--text-muted)]">
                  Drop a demo file to test the pipeline
                </span>
              </button>
              <button
                onClick={() => {
                  setDownloadOpen(false);
                  handleAgentDownload();
                }}
                className="flex w-full flex-col items-start gap-0.5 border-t border-[var(--border)] px-4 py-2.5 text-left hover:bg-[var(--gridline)]"
              >
                <span className="text-sm font-medium text-[var(--text-primary)]">
                  FileFlow Agent (.exe)
                </span>
                <span className="text-xs text-[var(--text-muted)]">
                  Windows installer — watches your own machine's folder
                </span>
              </button>
            </motion.div>
          )}
          </AnimatePresence>
        </div>

        <div ref={notifRef} className="relative">
          <button
            onClick={toggleNotifications}
            className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--gridline)]"
            aria-label="Notifications"
          >
            <Bell width={17} height={17} />
            {unreadCount > 0 ? (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--status-critical)] px-1 text-[10px] font-semibold text-white">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            ) : (
              <span
                className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full"
                style={{ background: isLive ? "var(--status-good)" : "var(--text-muted)" }}
              />
            )}
          </button>

          <AnimatePresence>
          {notifOpen && (
            <motion.div
              initial={{ opacity: 0, scale: 0.96, y: -4 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.96, y: -4 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              style={{ transformOrigin: "top right" }}
              className="absolute right-0 top-[calc(100%+6px)] z-20 w-80 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-1)] shadow-lg"
            >
              <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-2.5">
                <span className="text-sm font-semibold text-[var(--text-primary)]">
                  Notifications
                </span>
                <span
                  className="text-xs"
                  style={{ color: isLive ? "var(--status-good)" : "var(--text-muted)" }}
                >
                  {statusLabel}
                </span>
              </div>
              {notifLogs.length === 0 ? (
                <p className="px-4 py-6 text-center text-xs text-[var(--text-muted)]">
                  No activity yet — drop a file into the watched folder to see it here.
                </p>
              ) : (
                <div className="max-h-80 overflow-y-auto py-1.5">
                  {notifLogs.slice(0, MAX_NOTIFICATIONS).map((log) => {
                    const color = notifColorMap[log.category] || "var(--series-1)";
                    return (
                      <button
                        key={log.id}
                        onClick={() => {
                          setNotifOpen(false);
                          navigate(`/app/activity?q=${encodeURIComponent(log.final_filename)}`);
                        }}
                        className="flex w-full items-start gap-2.5 px-4 py-2.5 text-left hover:bg-[var(--gridline)]"
                      >
                        <span
                          className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[8px] font-bold tracking-wide"
                          style={{
                            color,
                            background: `color-mix(in srgb, ${color} 14%, transparent)`,
                          }}
                        >
                          {categoryBadge(log.category)}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium text-[var(--text-primary)]">
                            {log.final_filename}
                          </span>
                          <span className="block text-xs text-[var(--text-muted)]">
                            {actionText(log)} · {relativeTime(log.timestamp)}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
              <button
                onClick={() => {
                  setNotifOpen(false);
                  navigate("/app/activity");
                }}
                className="block w-full border-t border-[var(--border)] py-2 text-center text-xs font-medium text-[var(--brand)] hover:bg-[var(--gridline)]"
              >
                View all activity
              </button>
            </motion.div>
          )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  );
}
