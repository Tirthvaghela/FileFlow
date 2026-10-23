import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTheme } from "next-themes";
import { Bell, ChevronDown, Download, Moon, Search, Sun } from "lucide-react";
import BrandMark from "./BrandMark.jsx";
import FileBadge from "./FileBadge.jsx";
import { agentInstallerUrl, getLogs, getOrganizationHealth, simulateDownloadUrl } from "../services/api.js";
import { useRules } from "../context/RulesContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useLiveLogs } from "../hooks/useLiveLogs.js";
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
      results.push({ id: `ext-${ext}`, label: ext, sublabel: folder });
    }
  }

  const keywordEntries = [...(rules.keyword_rules || []), ...(rules.disabled_keyword_rules || [])];
  for (const r of keywordEntries) {
    if (r.keyword.toLowerCase().includes(q) || r.folder.toLowerCase().includes(q)) {
      results.push({ id: `kw-${r.keyword}-${r.folder}`, label: r.keyword, sublabel: r.folder });
    }
  }

  if (rules.large_file_folder && rules.large_file_folder.toLowerCase().includes(q)) {
    results.push({ id: "size-rule", label: `> ${rules.large_file_threshold_mb} MB`, sublabel: rules.large_file_folder });
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
      results.push({ id: `log-${log.id}`, label: log.final_filename, sublabel: log.category });
      if (results.length >= MAX_RESULTS_PER_GROUP) break;
    }
  }
  return results;
}

// Header control: 34px tall, 1px --rule-2 border, --sheet bg, 12px semibold.
const CHIP =
  "flex h-[34px] shrink-0 items-center gap-2 whitespace-nowrap rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet)] px-3 text-[12px] font-semibold text-[var(--ink)] transition-colors hover:border-[var(--ink)]";

const MENU =
  "ff-pop absolute right-0 top-[40px] z-30 overflow-hidden rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet)] text-[var(--ink)] shadow-[0_18px_40px_-16px_var(--shade)]";

const MENU_ITEM =
  "flex w-full flex-col items-start gap-0.5 border-none bg-transparent px-3.5 py-3 text-left hover:bg-[var(--sheet-2)]";

export default function Header() {
  const navigate = useNavigate();
  const { rules, saveRules } = useRules();
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const { logs: notifLogs, connected } = useLiveLogs(20);
  const [toast, setToast] = useState("");
  const [query, setQuery] = useState("");
  // Which popover is open: "search" | "notif" | "download" | "account" | null
  const [menu, setMenu] = useState(null);
  const [logs, setLogs] = useState([]);
  const [logsLoaded, setLogsLoaded] = useState(false);
  const [lastSeenId, setLastSeenId] = useState(null);
  const [agentConnected, setAgentConnected] = useState(null);
  const controlsRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    getOrganizationHealth()
      .then((h) => {
        if (!cancelled) setAgentConnected(h.agent_connected);
      })
      .catch(() => {
        if (!cancelled) setAgentConnected(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function handleClickOutside(e) {
      if (controlsRef.current && !controlsRef.current.contains(e.target)) setMenu(null);
    }
    function handleKey(e) {
      if (e.key === "Escape") setMenu(null);
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKey);
    };
  }, []);

  useEffect(() => {
    if (lastSeenId === null && notifLogs.length > 0) setLastSeenId(notifLogs[0].id);
  }, [notifLogs, lastSeenId]);

  const unreadCount = lastSeenId === null ? 0 : notifLogs.filter((l) => l.id > lastSeenId).length;
  const monitoring = rules?.realtime_monitoring_enabled ?? true;
  const isLive = connected && monitoring;
  const dark = theme === "dark";
  const initials = (user?.email?.[0] || "?").toUpperCase();

  async function toggleAutomation() {
    if (!rules) return;
    try {
      await saveRules((current) => ({
        ...current,
        realtime_monitoring_enabled: !current.realtime_monitoring_enabled,
      }));
    } catch {
      // saveRules already rolled the shared state back on failure
    }
  }

  function openMenu(name) {
    setMenu((current) => {
      const next = current === name ? null : name;
      if (next === "notif" && notifLogs.length > 0) setLastSeenId(notifLogs[0].id);
      if (next === "search" && !logsLoaded) {
        setLogsLoaded(true);
        getLogs(200).then(setLogs).catch(() => {});
      }
      return next;
    });
  }

  const files = useMemo(() => (query.trim() ? fileResults(logs, query.trim()) : []), [logs, query]);
  const ruleMatches = useMemo(() => (query.trim() ? ruleResults(rules, query.trim()) : []), [rules, query]);
  const hasResults = files.length > 0 || ruleMatches.length > 0;

  function goTo(path) {
    setMenu(null);
    setQuery("");
    navigate(path);
  }

  function triggerDownload(url, message) {
    const link = document.createElement("a");
    link.href = url;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
    setToast(message);
    setTimeout(() => setToast(""), 4000);
  }

  return (
    <header className="mx-auto flex max-w-[1360px] flex-nowrap items-center gap-3 px-4 pt-[18px] sm:gap-4 sm:px-6">
      <div className="flex shrink-0 items-center gap-2.5">
        <BrandMark />
        <span className="hidden text-[16px] font-extrabold tracking-[0.06em] sm:inline" style={{ fontStretch: "125%" }}>
          FILEFLOW
        </span>
      </div>

      <div title="Watched folder" className="hidden min-w-0 flex-[1_1_260px] items-center gap-2 sm:flex">
        <span className="ff-kicker hidden text-[10px] md:inline">Watching</span>
        <code className="min-w-0 truncate rounded-[3px] border border-[var(--rule-2)] bg-[var(--sheet)] px-2 py-1 font-mono-data text-[12px] font-medium shadow-[inset_0_1px_2px_var(--shade)]">
          {user?.watch_folder || "Not configured"}
        </code>
      </div>

      <div ref={controlsRef} className="relative ml-auto flex flex-none items-center gap-2 whitespace-nowrap">
        <button
          type="button"
          role="switch"
          aria-checked={monitoring}
          aria-label={`Real-time monitoring: ${monitoring ? "active" : "paused"}`}
          title="Real-time monitoring"
          onClick={toggleAutomation}
          className={`${CHIP} pl-1.5 pr-1.5 sm:pr-2.5`}
        >
          <span
            className="flex h-5 w-[34px] p-[2px] transition-colors"
            style={{ borderRadius: 3, background: monitoring ? "var(--filed)" : "var(--rule-2)", justifyContent: monitoring ? "flex-end" : "flex-start" }}
          >
            <span className="h-4 w-4 bg-[var(--sheet)] shadow-[0_1px_2px_var(--shade)]" style={{ borderRadius: 2 }} />
          </span>
          <span className="hidden sm:inline">Auto-sort {monitoring ? "on" : "off"}</span>
        </button>

        <span
          title={agentConnected === true ? "Agent connected" : agentConnected === false ? "Agent not connected" : "Agent status unknown"}
          className={`${CHIP} hidden cursor-default hover:border-[var(--rule-2)] md:flex`}
          style={{ color: agentConnected === true ? "var(--filed)" : "var(--ink-muted)" }}
        >
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: agentConnected === true ? "var(--filed)" : "var(--ink-muted)" }}
          />
          <span className="hidden xl:inline">
            {agentConnected === true ? "Agent connected" : agentConnected === false ? "Agent offline" : "Agent unknown"}
          </span>
        </span>

        <button
          type="button"
          onClick={() => setTheme(dark ? "light" : "dark")}
          aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
          className={`${CHIP} px-2.5 xl:px-3`}
        >
          {dark ? <Sun width={14} height={14} /> : <Moon width={14} height={14} fill="currentColor" />}
          <span className="hidden xl:inline">{dark ? "Day" : "Night"}</span>
        </button>

        {toast && (
          <span role="status" className="hidden max-w-[200px] truncate text-xs text-[var(--ink-2)] xl:inline">
            {toast}
          </span>
        )}

        <button
          type="button"
          aria-label="Search files and rules"
          aria-expanded={menu === "search"}
          onClick={() => openMenu("search")}
          className={`${CHIP} hidden px-2.5 sm:flex`}
        >
          <Search width={14} height={14} />
        </button>

        <button
          type="button"
          aria-label="Notifications"
          aria-expanded={menu === "notif"}
          onClick={() => openMenu("notif")}
          className={`${CHIP} hidden px-2.5 sm:flex`}
        >
          <Bell width={14} height={14} />
          {unreadCount > 0 && (
            <span className="grid h-4 min-w-4 place-items-center rounded-full bg-[var(--stamp)] px-1 text-[9px] font-bold text-white">
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </button>

        <button
          type="button"
          aria-expanded={menu === "download"}
          aria-label="Downloads"
          onClick={() => openMenu("download")}
          className="flex h-[34px] shrink-0 items-center gap-1.5 rounded-[4px] border-none bg-[var(--ink)] px-3 text-[12px] font-semibold text-[var(--paper)]"
        >
          <Download width={13} height={13} className="sm:hidden" />
          <span className="hidden sm:inline">Downloads</span>
          <ChevronDown width={12} height={12} />
        </button>

        <button
          type="button"
          onClick={logout}
          title={`${user?.email || ""} · Sign out`}
          className={`${CHIP} hidden bg-transparent px-2.5 lg:flex`}
        >
          <span className="grid h-[22px] w-[22px] place-items-center rounded-full bg-[var(--manila)] text-[11px] font-bold text-[var(--manila-ink)]">
            {initials}
          </span>
          Sign out
        </button>

        <button
          type="button"
          aria-label="Account menu"
          aria-expanded={menu === "account"}
          onClick={() => openMenu("account")}
          className="grid h-[34px] w-[34px] shrink-0 place-items-center rounded-[4px] border border-[var(--rule-2)] bg-transparent lg:hidden"
        >
          <span className="grid h-[22px] w-[22px] place-items-center rounded-full bg-[var(--manila)] text-[11px] font-bold text-[var(--manila-ink)]">
            {initials}
          </span>
        </button>

        {menu === "account" && (
          <div role="menu" className={`${MENU} w-[250px]`}>
            {user?.email && (
              <div className="border-b border-dashed border-[var(--rule-2)] px-3.5 py-2.5 font-mono-data text-[11.5px] text-[var(--ink-muted)]">
                {user.email}
              </div>
            )}
            <button type="button" role="menuitem" className={`${MENU_ITEM} sm:hidden`} onClick={() => openMenu("search")}>
              <b className="text-[13px]">Search files and rules</b>
            </button>
            <button type="button" role="menuitem" className={`${MENU_ITEM} sm:hidden`} onClick={() => openMenu("notif")}>
              <b className="text-[13px]">Notifications{unreadCount > 0 ? ` (${unreadCount})` : ""}</b>
            </button>
            <button type="button" role="menuitem" className={MENU_ITEM} onClick={logout}>
              <b className="text-[13px] text-[var(--stamp)]">Sign out</b>
            </button>
          </div>
        )}

        {menu === "download" && (
          <div role="menu" className={`${MENU} w-[290px] max-w-[calc(100vw-32px)]`}>
            <button
              type="button"
              role="menuitem"
              className={MENU_ITEM}
              onClick={() => {
                setMenu(null);
                triggerDownload(simulateDownloadUrl(), "Demo file downloading — FileFlow will pick it up once it lands.");
              }}
            >
              <b className="text-[13px]">Simulate a download</b>
              <span className="text-[12px] text-[var(--ink-muted)]">Drops a demo file into the watched folder</span>
            </button>
            <button
              type="button"
              role="menuitem"
              className={`${MENU_ITEM} border-t border-dashed border-[var(--rule-2)]`}
              onClick={() => {
                setMenu(null);
                triggerDownload(agentInstallerUrl(), "Downloading FileFlow Agent — run the installer once it lands.");
              }}
            >
              <b className="text-[13px]">FileFlow Agent for Windows</b>
              <span className="text-[12px] text-[var(--ink-muted)]">Sorts a folder on your own PC</span>
            </button>
          </div>
        )}

        {menu === "search" && (
          <div className={`${MENU} w-[320px] max-w-[calc(100vw-32px)]`}>
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && query.trim()) goTo(`/app/activity?q=${encodeURIComponent(query.trim())}`);
              }}
              placeholder="Search files, rules…"
              aria-label="Search files and rules"
              className="w-full border-0 border-b border-[var(--rule)] bg-transparent px-3.5 py-3 font-mono-data text-[12.5px] focus:outline-none"
            />
            {query.trim() &&
              (!hasResults ? (
                <p className="px-4 py-6 text-center text-xs text-[var(--ink-muted)]">No matches for “{query.trim()}”</p>
              ) : (
                <>
                  {files.length > 0 && (
                    <div className="border-b border-[var(--rule)] py-1.5">
                      <p className="ff-kicker px-3.5 pb-1">Files</p>
                      {files.map((r) => (
                        <button
                          key={r.id}
                          type="button"
                          onClick={() => goTo(`/app/activity?q=${encodeURIComponent(r.label)}`)}
                          className="flex w-full items-center gap-2.5 border-none bg-transparent px-3.5 py-2 text-left hover:bg-[var(--sheet-2)]"
                        >
                          <span className="min-w-0 flex-1 truncate font-mono-data text-[12px]">{r.label}</span>
                          <span className="shrink-0 font-mono-data text-[11px] text-[var(--ink-muted)]">→ {r.sublabel}</span>
                        </button>
                      ))}
                    </div>
                  )}
                  {ruleMatches.length > 0 && (
                    <div className="py-1.5">
                      <p className="ff-kicker px-3.5 pb-1">Rules</p>
                      {ruleMatches.map((r) => (
                        <button
                          key={r.id}
                          type="button"
                          onClick={() => goTo("/app/rules")}
                          className="flex w-full items-center gap-2.5 border-none bg-transparent px-3.5 py-2 text-left hover:bg-[var(--sheet-2)]"
                        >
                          <span className="min-w-0 flex-1 truncate font-mono-data text-[12px] font-semibold">{r.label}</span>
                          <span className="shrink-0 font-mono-data text-[11px] text-[var(--ink-muted)]">→ {r.sublabel}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </>
              ))}
          </div>
        )}

        {menu === "notif" && (
          <div className={`${MENU} w-[320px] max-w-[calc(100vw-32px)]`}>
            <div className="flex items-center justify-between border-b border-[var(--rule)] px-3.5 py-2.5">
              <span className="ff-kicker">Notifications</span>
              <span className="font-mono-data text-[11px]" style={{ color: isLive ? "var(--filed)" : "var(--ink-muted)" }}>
                {!connected ? "disconnected" : monitoring ? "live" : "paused"}
              </span>
            </div>
            {notifLogs.length === 0 ? (
              <p className="px-4 py-6 text-center text-xs text-[var(--ink-muted)]">
                No activity yet — drop a file into the watched folder to see it here.
              </p>
            ) : (
              <div className="max-h-80 overflow-y-auto py-1">
                {notifLogs.slice(0, MAX_NOTIFICATIONS).map((log) => (
                  <button
                    key={log.id}
                    type="button"
                    onClick={() => goTo(`/app/activity?q=${encodeURIComponent(log.final_filename)}`)}
                    className="flex w-full items-center gap-2.5 border-none bg-transparent px-3.5 py-2 text-left hover:bg-[var(--sheet-2)]"
                  >
                    <FileBadge filename={log.final_filename} size="xs" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono-data text-[12px]">{log.final_filename}</span>
                      <span className="block text-[11.5px] text-[var(--ink-muted)]">
                        {actionText(log)} · {relativeTime(log.timestamp)}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
            <button
              type="button"
              onClick={() => goTo("/app/activity")}
              className="block w-full border-0 border-t border-[var(--rule)] bg-transparent py-2 text-center text-xs font-semibold hover:bg-[var(--sheet-2)]"
            >
              View all activity
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
