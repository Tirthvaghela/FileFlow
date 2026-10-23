import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import PageHeading from "../components/PageHeading.jsx";
import RecentScheduledActivity from "../components/RecentScheduledActivity.jsx";
import ConfirmDialog from "../components/ui/ConfirmDialog.jsx";
import Toggle from "../components/ui/Toggle.jsx";
import FolderTag from "../components/ui/FolderTag.jsx";
import { Button } from "../components/ui/button.jsx";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "../components/ui/dialog.jsx";
import { PasswordInput } from "../components/ui/PasswordInput.jsx";
import {
  addWatchFolder,
  browseFolder,
  deleteAccount,
  disableTwoFactor,
  enableTwoFactor,
  generateAgentToken,
  getTwoFactorStatus,
  removeWatchFolder,
  setupTwoFactor,
  updateWatchFolder,
} from "../services/api.js";
import { folderName } from "../utils/activity.js";
import { useRules } from "../context/RulesContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";

const DUP_MODES = [
  { id: "rename", title: "Rename", desc: "Keep both. The new file gets a number.", example: "Documents/report (1).pdf" },
  { id: "skip", title: "Skip", desc: "Leave the new file where it landed.", example: "stays in Downloads" },
  { id: "replace", title: "Replace", desc: "Overwrite the existing file. Can't be undone.", example: "Documents/report.pdf (new)" },
];

// Settings save immediately (each control writes through saveRules), so
// a small toast confirms every change instead of a save bar.
function SaveToast({ status }) {
  if (!status) return null;
  const color = status === "Failed to save" ? "var(--stamp)" : status === "Saved" ? "var(--filed)" : "var(--ink-muted)";
  return (
    <div
      role="status"
      className="ff-pop fixed bottom-4 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet)] px-3.5 py-2 text-[12.5px] font-semibold shadow-[0_10px_24px_-14px_var(--shade)]"
      style={{ color }}
    >
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {status}
    </div>
  );
}

function Card({ id, n, title, desc, danger = false, children, bodyClass = "p-[18px]" }) {
  return (
    <section
      id={id}
      className="scroll-mt-4 overflow-hidden rounded-[4px] border bg-[var(--sheet)]"
      style={{ borderColor: danger ? "var(--stamp)" : "var(--rule-2)" }}
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-[var(--rule)] bg-[var(--sheet-2)] px-[18px] py-3.5">
        <span className="font-mono-data text-[11px] font-semibold text-[var(--ink-muted)]">{n}</span>
        <h2 className="ff-caps m-0 text-[15px]" style={{ color: danger ? "var(--stamp)" : "var(--ink)" }}>
          {title}
        </h2>
        <span className="text-[12.5px] text-[var(--ink-muted)]">{desc}</span>
      </div>
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

// One setting: text block grows, the control never wraps under it.
function Row({ title, desc, children, last = false }) {
  return (
    <div className={`flex items-center gap-4 py-3.5 ${last ? "" : "border-b border-dashed border-[var(--rule-2)]"}`}>
      <div className="flex min-w-0 flex-[1_1_0] flex-col gap-0.5">
        <b className="text-[13.5px]">{title}</b>
        {desc && <span className="text-[12px] text-[var(--ink-muted)]">{desc}</span>}
      </div>
      <div className="flex-none">{children}</div>
    </div>
  );
}

function Slider({ label, value, display, onChange, min, max, step = 1, help, muted = false }) {
  const pct = Math.min(100, Math.max(0, ((value - min) / (max - min)) * 100));
  return (
    <div className="flex flex-col gap-1.5 border-b border-dashed border-[var(--rule-2)] py-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <label className="text-[13.5px] font-bold">{label}</label>
        <span className="font-mono-data text-[13px] font-semibold" style={{ color: muted ? "var(--ink-muted)" : "var(--ink)" }}>
          {display}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-label={label}
        onChange={(e) => onChange(Number(e.target.value))}
        className="ff-range"
        style={{ "--ff-pct": `${pct}%` }}
      />
      {help && <span className="text-[12px] text-[var(--ink-muted)]">{help}</span>}
    </div>
  );
}

export default function Settings() {
  const { rules, saveRules } = useRules();
  const { user, refresh: refreshUser, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const savedWatchFolder = user?.watch_folder || "";
  const [watchFolder, setWatchFolder] = useState(savedWatchFolder);
  const [folderStatus, setFolderStatus] = useState("");
  const [folderError, setFolderError] = useState("");
  const [status, setStatus] = useState("");
  const [archiveFolder, setArchiveFolder] = useState("");
  const [defaultCategory, setDefaultCategory] = useState("");
  const [pendingFolder, setPendingFolder] = useState(null);
  const [agentToken, setAgentToken] = useState(null);
  const [agentTokenScope, setAgentTokenScope] = useState(null);
  const [generatingToken, setGeneratingToken] = useState(false);
  const [tokenError, setTokenError] = useState("");
  const [tokenCopied, setTokenCopied] = useState(false);
  const [selectedTokenScope, setSelectedTokenScope] = useState("full");
  const [browsingFolder, setBrowsingFolder] = useState(false);
  const [addingFolder, setAddingFolder] = useState(false);
  const [additionalFolderError, setAdditionalFolderError] = useState("");
  const [removingFolder, setRemovingFolder] = useState(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [activeSection, setActiveSection] = useState("watch-folders");

  const [twoFactorEnabled, setTwoFactorEnabled] = useState(null);
  const [twoFactorSetup, setTwoFactorSetup] = useState(null);
  const [startingSetup, setStartingSetup] = useState(false);
  const [enableCode, setEnableCode] = useState("");
  const [enablingTwoFactor, setEnablingTwoFactor] = useState(false);
  const [backupCodes, setBackupCodes] = useState(null);
  const [twoFactorError, setTwoFactorError] = useState("");
  const [disable2FADialogOpen, setDisable2FADialogOpen] = useState(false);
  const [disable2FAPassword, setDisable2FAPassword] = useState("");
  const [disable2FAError, setDisable2FAError] = useState("");
  const [disablingTwoFactor, setDisablingTwoFactor] = useState(false);

  useEffect(() => {
    setWatchFolder(savedWatchFolder);
  }, [savedWatchFolder]);

  useEffect(() => {
    getTwoFactorStatus()
      .then((s) => setTwoFactorEnabled(s.enabled))
      .catch(() => {});
  }, []);

  // Local input state so a PUT only fires once the field loses focus.
  useEffect(() => {
    if (rules) {
      setArchiveFolder(rules.archive_folder);
      setDefaultCategory(rules.default_category);
    }
  }, [rules]);

  // Deep links (e.g. Rules → "Open Settings") land on their section.
  const hasRules = !!rules;
  useEffect(() => {
    const id = location.hash.replace("#", "");
    if (id && hasRules) document.getElementById(id)?.scrollIntoView?.({ behavior: "smooth" });
  }, [location.hash, hasRules]);

  // Highlights the section currently in view in the numbered nav.
  useEffect(() => {
    function onScroll() {
      const ids = ["watch-folders", "monitoring-schedule", "automation-policy", "remote-agent", "two-factor", "danger-zone"];
      let current = ids[0];
      for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top < 140) current = id;
      }
      setActiveSection(current);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function commitWatchFolder() {
    const trimmed = watchFolder.trim();
    if (!trimmed || trimmed === savedWatchFolder) {
      setWatchFolder(savedWatchFolder);
      return;
    }
    setPendingFolder(trimmed);
  }

  async function handleBrowseFolder() {
    setBrowsingFolder(true);
    setFolderError("");
    try {
      const { path } = await browseFolder();
      if (path && path !== savedWatchFolder) {
        setWatchFolder(path);
        setPendingFolder(path);
      }
    } catch {
      setFolderError("Couldn't open the folder picker -- type the path instead.");
    } finally {
      setBrowsingFolder(false);
    }
  }

  async function handleAddAdditionalFolder() {
    setAddingFolder(true);
    setAdditionalFolderError("");
    try {
      const { path } = await browseFolder();
      if (!path) return; // user canceled the picker
      await addWatchFolder(path);
      await refreshUser();
    } catch (err) {
      setAdditionalFolderError(err?.response?.data?.detail || "Couldn't add that folder.");
    } finally {
      setAddingFolder(false);
    }
  }

  async function handleRemoveAdditionalFolder(path) {
    setRemovingFolder(path);
    setAdditionalFolderError("");
    try {
      await removeWatchFolder(path);
      await refreshUser();
    } catch {
      setAdditionalFolderError("Couldn't remove that folder.");
    } finally {
      setRemovingFolder(null);
    }
  }

  function handleFolderDialogChange(open) {
    if (!open) {
      setPendingFolder(null);
      setWatchFolder(savedWatchFolder);
    }
  }

  async function applyWatchFolderChange() {
    const trimmed = pendingFolder;
    setPendingFolder(null);
    setFolderStatus("Saving…");
    setFolderError("");
    try {
      const result = await updateWatchFolder(trimmed);
      setWatchFolder(result.watch_folder);
      await refreshUser();
      setFolderStatus("Saved");
      setTimeout(() => setFolderStatus(""), 1500);
    } catch (err) {
      setFolderError(err?.response?.data?.detail || "Couldn't use that folder.");
      setWatchFolder(savedWatchFolder);
      setFolderStatus("");
    }
  }

  async function save(patch) {
    setStatus("Saving…");
    try {
      // Updater form: slider drags queue several saves, each applying its
      // own patch on top of whichever save ahead of it lands.
      await saveRules((current) => ({ ...current, ...patch }));
      setStatus("Saved");
      setTimeout(() => setStatus(""), 1500);
    } catch {
      setStatus("Failed to save");
    }
  }

  function commitArchiveFolder() {
    const trimmed = archiveFolder.trim() || "Archive";
    setArchiveFolder(trimmed);
    if (trimmed !== rules.archive_folder) save({ archive_folder: trimmed });
  }

  function commitDefaultCategory() {
    const trimmed = defaultCategory.trim() || "Others";
    setDefaultCategory(trimmed);
    if (trimmed !== rules.default_category) save({ default_category: trimmed });
  }

  async function handleGenerateAgentToken() {
    setGeneratingToken(true);
    setTokenCopied(false);
    setTokenError("");
    try {
      const { token, scope } = await generateAgentToken(selectedTokenScope);
      setAgentToken(token);
      setAgentTokenScope(scope);
    } catch (err) {
      setTokenError(err?.response?.data?.detail || "Couldn't generate a token -- try again.");
    } finally {
      setGeneratingToken(false);
    }
  }

  function copyAgentToken() {
    navigator.clipboard.writeText(agentToken);
    setTokenCopied(true);
    setTimeout(() => setTokenCopied(false), 1500);
  }

  function handleDeleteDialogChange(open) {
    setDeleteDialogOpen(open);
    if (!open) {
      setDeletePassword("");
      setDeleteError("");
    }
  }

  async function handleDeleteAccount() {
    setDeletingAccount(true);
    setDeleteError("");
    try {
      await deleteAccount(deletePassword);
      await logout();
      navigate("/", { replace: true });
    } catch (err) {
      setDeleteError(err?.response?.data?.detail || "Couldn't delete your account.");
      setDeletingAccount(false);
    }
  }

  async function handleStartTwoFactorSetup() {
    setStartingSetup(true);
    setTwoFactorError("");
    try {
      setTwoFactorSetup(await setupTwoFactor());
    } catch {
      setTwoFactorError("Couldn't start 2FA setup -- try again.");
    } finally {
      setStartingSetup(false);
    }
  }

  function cancelTwoFactorSetup() {
    setTwoFactorSetup(null);
    setEnableCode("");
    setTwoFactorError("");
  }

  async function handleEnableTwoFactor() {
    setEnablingTwoFactor(true);
    setTwoFactorError("");
    try {
      const { backup_codes } = await enableTwoFactor(enableCode.trim());
      setBackupCodes(backup_codes);
      setTwoFactorSetup(null);
      setEnableCode("");
      setTwoFactorEnabled(true);
    } catch (err) {
      setTwoFactorError(err?.response?.data?.detail || "That code is incorrect or expired.");
    } finally {
      setEnablingTwoFactor(false);
    }
  }

  function handleDisable2FADialogChange(open) {
    setDisable2FADialogOpen(open);
    if (!open) {
      setDisable2FAPassword("");
      setDisable2FAError("");
    }
  }

  async function handleDisableTwoFactor() {
    setDisablingTwoFactor(true);
    setDisable2FAError("");
    try {
      await disableTwoFactor(disable2FAPassword);
      setTwoFactorEnabled(false);
      setBackupCodes(null);
      setDisable2FADialogOpen(false);
      setDisable2FAPassword("");
    } catch (err) {
      setDisable2FAError(err?.response?.data?.detail || "Couldn't disable 2FA.");
    } finally {
      setDisablingTwoFactor(false);
    }
  }

  const heading = (
    <PageHeading index={7} kicker="Configuration" title="Settings" subtitle="How FileFlow watches, sorts and handles duplicates." />
  );

  if (!rules) {
    return (
      <>
        {heading}
        <div className="text-sm text-[var(--ink-muted)]">Loading…</div>
      </>
    );
  }

  const folderCount = 1 + (user?.additional_watch_folders || []).length;
  const watchBase = folderName(savedWatchFolder) || "Downloads";
  const nav = [
    { id: "watch-folders", n: "01", label: "Watch folders", state: `${folderCount} folder${folderCount === 1 ? "" : "s"}` },
    {
      id: "monitoring-schedule",
      n: "02",
      label: "Monitoring & schedule",
      state: `Auto-sort ${rules.realtime_monitoring_enabled ? "on" : "off"}${rules.scheduled_organize_enabled ? ` · nightly ${rules.scheduled_organize_time}` : ""}`,
      color: rules.realtime_monitoring_enabled ? "var(--filed)" : "var(--warn)",
    },
    {
      id: "automation-policy",
      n: "03",
      label: "Automation policy",
      state: `${DUP_MODES.find((m) => m.id === rules.duplicate_handling)?.title || "Rename"} · ${rules.archive_after_days} days`,
    },
    {
      id: "remote-agent",
      n: "04",
      label: "Remote agent",
      state: user?.agent_connected ? "Connected" : "Not connected",
      color: user?.agent_connected ? "var(--filed)" : undefined,
    },
    {
      id: "two-factor",
      n: "05",
      label: "Two-factor",
      state: twoFactorEnabled == null ? "…" : twoFactorEnabled ? "2FA on" : "2FA off",
      color: twoFactorEnabled ? "var(--filed)" : twoFactorEnabled === false ? "var(--warn)" : undefined,
    },
    { id: "danger-zone", n: "06", label: "Danger zone", state: "Permanent", danger: true },
  ];

  function goTo(id) {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  return (
    <>
      {heading}
      <div className="ff-in flex flex-col gap-7 lg:flex-row lg:items-start">
        <nav
          aria-label="Settings sections"
          className="ff-scroll-x ff-fade-edge -mx-1 flex gap-1 px-1 lg:sticky lg:top-4 lg:mx-0 lg:w-[220px] lg:min-w-[190px] lg:flex-none lg:flex-col lg:gap-0.5 lg:overflow-visible lg:px-0 lg:[mask-image:none]"
        >
          <span className="ff-kicker hidden pb-1.5 lg:block">Sections</span>
          {nav.map((item) => {
            const on = activeSection === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => goTo(item.id)}
                aria-current={on ? "true" : undefined}
                className="grid flex-none cursor-pointer gap-x-2 gap-y-px rounded-[0_4px_4px_0] border-0 px-2.5 py-[9px] text-left transition-colors hover:bg-[var(--sheet-2)]"
                style={{
                  gridTemplateColumns: "22px minmax(0,1fr)",
                  borderLeft: `3px solid ${on ? "var(--stamp)" : "transparent"}`,
                  background: on ? "var(--sheet-2)" : "transparent",
                }}
              >
                <span className="row-span-2 pt-0.5 font-mono-data text-[10.5px] font-semibold text-[var(--ink-muted)]">{item.n}</span>
                <b className="whitespace-nowrap text-[13px]" style={{ color: item.danger ? "var(--stamp)" : "var(--ink)" }}>
                  {item.label}
                </b>
                <span className="whitespace-nowrap text-[11.5px]" style={{ color: item.color || "var(--ink-muted)" }}>
                  {item.state}
                </span>
              </button>
            );
          })}
        </nav>

        <div className="flex min-w-0 flex-1 flex-col gap-[18px]">
          <Card id="watch-folders" n="01" title="Watch folders" desc="Where FileFlow looks for new files.">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="ff-watch" className="ff-kicker">
                Watched folder
              </label>
              <div className="flex gap-2">
                <input
                  id="ff-watch"
                  value={watchFolder}
                  onChange={(e) => setWatchFolder(e.target.value)}
                  onBlur={commitWatchFolder}
                  spellCheck={false}
                  className="ff-input flex-1"
                />
                <button type="button" onClick={handleBrowseFolder} disabled={browsingFolder} className="ff-btn ff-btn-tertiary ff-btn-lg">
                  {browsingFolder ? "Opening…" : "Browse…"}
                </button>
              </div>
              {folderStatus && <span className="font-mono-data text-[11.5px] text-[var(--ink-muted)]">{folderStatus}</span>}
              {folderError && <span className="text-xs text-[var(--stamp)]">{folderError}</span>}
            </div>

            <div className="mt-5 flex flex-col gap-2">
              <div className="flex items-center gap-2.5">
                <span className="ff-kicker">Additional folders</span>
                <span className="flex-1 border-t border-dashed border-[var(--rule-2)]" />
              </div>
              {(user?.additional_watch_folders || []).length === 0 ? (
                <p className="m-0 text-[12.5px] text-[var(--ink-muted)]">Watch more than one folder with the same rules — add one here.</p>
              ) : (
                <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
                  {user.additional_watch_folders.map((path) => (
                    <li key={path} className="flex items-center gap-2 rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet)] px-3 py-2">
                      <span className="min-w-0 flex-1 truncate font-mono-data text-[12.5px]">{path}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveAdditionalFolder(path)}
                        disabled={removingFolder === path}
                        className="shrink-0 cursor-pointer border-none bg-transparent text-[var(--ink-muted)] hover:text-[var(--stamp)] disabled:opacity-60"
                        aria-label={`Stop watching ${path}`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div>
                <button type="button" onClick={handleAddAdditionalFolder} disabled={addingFolder} className="ff-btn ff-btn-tertiary">
                  {addingFolder ? "Opening…" : "+ Add folder"}
                </button>
              </div>
              {additionalFolderError && <span className="text-xs text-[var(--stamp)]">{additionalFolderError}</span>}
              {user?.agent_connected && (user?.additional_watch_folders || []).length > 0 && (
                <div className="rounded-[4px] border-l-[3px] border-[var(--warn)] bg-[var(--warn-bg)] px-3 py-2">
                  <p className="m-0 text-[12.5px] font-semibold text-[var(--warn)]">Remote agent watches only one folder</p>
                  <p className="m-0 mt-0.5 text-[12px] text-[var(--ink-2)]">
                    Your connected agent monitors and organizes only the one folder it's set up with. Real-time monitoring and
                    "Organize existing files" don't reach your other watch folders while the agent stays connected.
                  </p>
                </div>
              )}
            </div>
          </Card>

          <Card id="monitoring-schedule" n="02" title="Monitoring & schedule" desc="What FileFlow watches and when it acts." bodyClass="px-[18px] pb-2 pt-[18px]">
            <div className="flex items-center gap-5 border-b border-dashed border-[var(--rule-2)] pb-4">
              <div className="flex min-w-0 flex-[1_1_0] flex-col gap-1">
                <b className="ff-display text-[22px]">Auto-sort is {rules.realtime_monitoring_enabled ? "on" : "off"}</b>
                <span className="text-[13px] text-[var(--ink-2)]">
                  {rules.realtime_monitoring_enabled
                    ? "New files are sorted as soon as they finish downloading."
                    : "New downloads stay where they land until you turn this back on."}
                </span>
              </div>
              <Toggle
                size="lg"
                checked={rules.realtime_monitoring_enabled}
                onChange={(v) => save({ realtime_monitoring_enabled: v })}
                label="Real-time monitoring"
              />
            </div>
            <Row title="Desktop notifications" desc="A toast on every action FileFlow takes.">
              <Toggle checked={rules.desktop_notifications_enabled} onChange={(v) => save({ desktop_notifications_enabled: v })} label="Desktop notifications" />
            </Row>
            <Row
              title="Scheduled nightly sweep"
              desc={'Run "Organize existing files" automatically every day.'}
              last={!rules.scheduled_organize_enabled}
            >
              <Toggle checked={rules.scheduled_organize_enabled} onChange={(v) => save({ scheduled_organize_enabled: v })} label="Scheduled nightly sweep" />
            </Row>
            {rules.scheduled_organize_enabled && (
              <>
                <Row title="Run at" desc="Local time on the machine running FileFlow.">
                  <input
                    type="time"
                    value={rules.scheduled_organize_time}
                    onChange={(e) => save({ scheduled_organize_time: e.target.value })}
                    aria-label="Run at"
                    className="ff-input h-[34px]"
                  />
                </Row>
                <div className="flex flex-col gap-2 py-3.5">
                  <span className="ff-kicker">Recent scheduled activity</span>
                  <RecentScheduledActivity />
                </div>
              </>
            )}
          </Card>

          <Card id="automation-policy" n="03" title="Automation policy" desc="Duplicates, archiving, size and storage limits.">
            <div className="flex flex-col gap-2.5">
              <span className="ff-kicker">Duplicate handling</span>
              <div role="radiogroup" aria-label="Duplicate handling" className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 170px), 1fr))" }}>
                {DUP_MODES.map((m) => {
                  const on = rules.duplicate_handling === m.id;
                  return (
                    <button
                      key={m.id}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      onClick={() => save({ duplicate_handling: m.id })}
                      className="flex cursor-pointer flex-col gap-2 rounded-[4px] border-[1.5px] p-3.5 text-left transition-[border-color,background,transform] hover:-translate-y-0.5"
                      style={{ borderColor: on ? "var(--ink)" : "var(--rule-2)", background: on ? "var(--sheet-2)" : "var(--sheet)", transitionDuration: "var(--d2)" }}
                    >
                      <span className="flex items-center gap-2">
                        <span className="grid h-4 w-4 place-items-center rounded-full border-[1.5px] border-[var(--ink)]">
                          <span className="h-2 w-2 rounded-full" style={{ background: on ? "var(--stamp)" : "transparent" }} />
                        </span>
                        <b className="text-[14px]">{m.title}</b>
                      </span>
                      <span className="text-[12.5px] text-[var(--ink-2)]">{m.desc}</span>
                      <span className="mt-auto flex flex-col gap-[3px] rounded-[3px] border border-[var(--rule)] bg-[var(--sheet)] p-2 font-mono-data text-[11.5px]" style={{ overflowWrap: "anywhere" }}>
                        <span className="text-[var(--ink-muted)]">Documents/report.pdf exists</span>
                        <span>
                          <span className="text-[var(--stamp)]">→ </span>
                          {m.example}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
              {rules.duplicate_handling === "replace" ? (
                <p className="m-0 text-[12px] text-[var(--stamp)]">
                  Replace permanently deletes the existing file at the destination before moving the new one in. This can't be undone.
                </p>
              ) : (
                <p className="m-0 text-[12px] text-[var(--ink-muted)]">Applies when the destination already has a file with that name.</p>
              )}
            </div>

            <div className="mt-3 flex flex-col">
              <Slider
                label="Archive files older than"
                value={rules.archive_after_days}
                display={`${rules.archive_after_days} days`}
                min={1}
                max={90}
                onChange={(v) => save({ archive_after_days: v })}
                help="Files left untouched this long are moved to the archive folder."
              />
              <Slider
                label="Large file threshold"
                value={rules.large_file_threshold_mb}
                display={`${rules.large_file_threshold_mb} MB`}
                min={10}
                max={2000}
                step={10}
                onChange={(v) => save({ large_file_threshold_mb: v })}
                help="Tier 05: anything bigger goes to the large-files folder."
              />
              <Slider
                label="Empty Recycle Bin entries after"
                value={rules.recycle_bin_retention_days}
                display={`${rules.recycle_bin_retention_days} days`}
                min={1}
                max={90}
                onChange={(v) => save({ recycle_bin_retention_days: v })}
                help="Only files FileFlow itself sent to the Recycle Bin (via Categories → Delete) are ever permanently purged, and only after sitting this long."
              />
              <Slider
                label="Alert when a category exceeds"
                value={rules.storage_alert_threshold_gb}
                display={rules.storage_alert_threshold_gb > 0 ? `${rules.storage_alert_threshold_gb} GB` : "Disabled"}
                muted={!(rules.storage_alert_threshold_gb > 0)}
                min={0}
                max={50}
                step={0.5}
                onChange={(v) => save({ storage_alert_threshold_gb: v })}
                help="When a category folder crosses this size, FileFlow notifies you and archives its oldest files to bring it back down. 0 disables this."
              />
            </div>

            <div className="mt-4 flex flex-col gap-3">
              <div className="flex items-center gap-2.5">
                <span className="ff-kicker">Folders</span>
                <span className="flex-1 border-t border-dashed border-[var(--rule-2)]" />
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex min-w-0 flex-[1_1_220px] flex-col gap-1.5 text-[12.5px] font-semibold">
                  Archive folder name
                  <input value={archiveFolder} onChange={(e) => setArchiveFolder(e.target.value)} onBlur={commitArchiveFolder} className="ff-input" />
                </label>
                <span className="pb-2.5">
                  <FolderTag>{`${watchBase}/${archiveFolder || "Archive"}`}</FolderTag>
                </span>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex min-w-0 flex-[1_1_220px] flex-col gap-1.5 text-[12.5px] font-semibold">
                  Fallback folder name
                  <input value={defaultCategory} onChange={(e) => setDefaultCategory(e.target.value)} onBlur={commitDefaultCategory} className="ff-input" />
                </label>
                <span className="pb-2.5">
                  <FolderTag>{`${watchBase}/${defaultCategory || "Others"}`}</FolderTag>
                </span>
              </div>
              <span className="text-[12px] text-[var(--ink-muted)]">The fallback folder is tier 09: files that don't match any rule or category.</span>
            </div>
          </Card>

          <Card id="remote-agent" n="04" title="Remote agent" desc="Sort a folder on your own Windows PC.">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3.5">
              <span aria-hidden="true" className="grid h-11 w-11 flex-none place-items-center rounded-full border-[1.5px] border-[var(--rule-2)]">
                <span
                  className="h-3.5 w-3.5 rounded-full"
                  style={{
                    background: user?.agent_connected ? "var(--filed)" : "var(--ink-muted)",
                    boxShadow: `0 0 0 5px ${user?.agent_connected ? "var(--filed-bg)" : "var(--sheet-2)"}`,
                  }}
                />
              </span>
              <div className="flex min-w-0 flex-[1_1_260px] flex-col gap-[3px]">
                <b className="text-[15px]">{user?.agent_connected ? "Agent connected" : "Agent not connected"}</b>
                <span className="text-[12.5px] text-[var(--ink-2)]">
                  Install the agent from the Downloads menu. The first time it runs it asks for this dashboard's address and a token —
                  generate one here and paste it in.
                </span>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2.5">
              <div role="radiogroup" aria-label="Token permissions" className="flex overflow-hidden rounded-[4px] border border-[var(--ink)]">
                {[
                  ["full", "Full control"],
                  ["read_only", "Read-only"],
                ].map(([id, label]) => {
                  const on = selectedTokenScope === id;
                  return (
                    <button
                      key={id}
                      type="button"
                      role="radio"
                      aria-checked={on}
                      onClick={() => setSelectedTokenScope(id)}
                      className="h-[34px] cursor-pointer border-none px-3.5 text-[12.5px] font-semibold"
                      style={{ background: on ? "var(--ink)" : "transparent", color: on ? "var(--paper)" : "var(--ink)" }}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              <button type="button" onClick={handleGenerateAgentToken} disabled={generatingToken} className="ff-btn ff-btn-primary">
                {generatingToken ? "Generating…" : "Generate agent token"}
              </button>
            </div>
            <p className="m-0 mt-2 text-[12px] text-[var(--ink-muted)]">
              {selectedTokenScope === "full"
                ? "Can watch, organize, and report activity — what a real agent installation needs."
                : "Can only fetch rules — can't move files, report activity, or run commands. Useful for a monitoring or preview integration."}
            </p>
            {tokenError && <span className="mt-2 block text-xs text-[var(--stamp)]">{tokenError}</span>}
            {agentToken && (
              <div className="mt-4 rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet-2)] p-3">
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-[var(--ink-2)]">
                    Shown once — copy it now
                    {agentTokenScope === "read_only" && <span className="ml-1.5 font-mono-data text-[10.5px] text-[var(--warn)]">READ-ONLY</span>}
                  </span>
                  <button type="button" onClick={copyAgentToken} className="ff-btn ff-btn-tertiary ff-btn-sm">
                    {tokenCopied ? "Copied" : "Copy"}
                  </button>
                </div>
                <code className="block break-all font-mono-data text-[11px]">{agentToken}</code>
                <p className="m-0 mt-2 text-xs text-[var(--warn)]">
                  Generating a new token immediately invalidates this one and any others issued before it.
                </p>
              </div>
            )}
          </Card>

          <Card id="two-factor" n="05" title="Two-factor" desc="Ask for a 6-digit code at sign in.">
            {twoFactorEnabled === null ? (
              <p className="m-0 text-xs text-[var(--ink-muted)]">Loading…</p>
            ) : backupCodes ? (
              <div className="rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet-2)] p-3">
                <p className="m-0 mb-2 text-xs font-semibold text-[var(--ink-2)]">
                  Save these backup codes — shown once. Each works one time if you lose access to your authenticator app.
                </p>
                <div className="grid grid-cols-2 gap-1.5 font-mono-data text-xs">
                  {backupCodes.map((c) => (
                    <code key={c} className="rounded-[2px] bg-[var(--sheet)] px-2 py-1">
                      {c}
                    </code>
                  ))}
                </div>
                <button type="button" onClick={() => setBackupCodes(null)} className="ff-btn ff-btn-primary mt-3">
                  I've saved these
                </button>
              </div>
            ) : twoFactorSetup ? (
              <div className="rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet-2)] p-3">
                <p className="m-0 mb-3 text-xs text-[var(--ink-2)]">
                  Scan this with your authenticator app (Google Authenticator, Authy, etc.), then enter the 6-digit code it shows.
                </p>
                <img src={twoFactorSetup.qr_code_data_uri} alt="2FA setup QR code" className="mb-3 h-40 w-40 rounded-[4px] border border-[var(--rule-2)] bg-white p-2" />
                <p className="m-0 mb-3 text-xs text-[var(--ink-muted)]">
                  Can't scan it? Enter this key manually: <code className="font-mono-data text-[var(--ink)]">{twoFactorSetup.secret}</code>
                </p>
                <label className="mb-3 flex flex-col gap-1.5 text-[12.5px] font-semibold">
                  6-digit code
                  <input value={enableCode} onChange={(e) => setEnableCode(e.target.value)} placeholder="123456" className="ff-input" />
                </label>
                {twoFactorError && <p className="m-0 mb-3 text-xs text-[var(--stamp)]">{twoFactorError}</p>}
                <div className="flex gap-2">
                  <button type="button" onClick={handleEnableTwoFactor} disabled={enablingTwoFactor || !enableCode.trim()} className="ff-btn ff-btn-primary">
                    {enablingTwoFactor ? "Verifying…" : "Enable"}
                  </button>
                  <button type="button" onClick={cancelTwoFactorSetup} className="ff-btn ff-btn-tertiary">
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex items-center gap-4">
                  <div className="flex min-w-0 flex-[1_1_0] flex-col gap-0.5">
                    <b className="text-[13.5px]">Two-factor authentication</b>
                    <span className="text-[12px]" style={{ color: twoFactorEnabled ? "var(--filed)" : "var(--ink-muted)" }}>
                      {twoFactorEnabled ? "Enabled" : "Off"}
                    </span>
                  </div>
                  {twoFactorEnabled ? (
                    <button type="button" onClick={() => setDisable2FADialogOpen(true)} className="ff-btn ff-btn-tertiary">
                      Disable
                    </button>
                  ) : (
                    <button type="button" onClick={handleStartTwoFactorSetup} disabled={startingSetup} className="ff-btn ff-btn-primary">
                      {startingSetup ? "Starting…" : "Set up 2FA"}
                    </button>
                  )}
                </div>
                {twoFactorError && <p className="m-0 mt-3 text-xs text-[var(--stamp)]">{twoFactorError}</p>}
              </>
            )}
          </Card>

          <Card id="danger-zone" n="06" title="Danger zone" desc="Permanent and can't be undone." danger>
            <div className="flex items-center gap-4">
              <p className="m-0 min-w-0 flex-[1_1_0] text-[12.5px] text-[var(--ink-2)]">
                Permanently deletes your account, watched-folder history, and rules. Files already organized on disk are left alone.
              </p>
              <button type="button" onClick={() => setDeleteDialogOpen(true)} className="ff-btn ff-btn-danger">
                Delete account
              </button>
            </div>
          </Card>
        </div>
      </div>

      <SaveToast status={status} />

      <Dialog open={disable2FADialogOpen} onOpenChange={handleDisable2FADialogChange}>
        <DialogContent className="p-6 sm:max-w-[420px]">
          <DialogTitle>Disable two-factor authentication?</DialogTitle>
          <DialogDescription className="text-sm leading-relaxed text-[var(--ink-2)]">
            Your account will only need a password to sign in. Enter your password to confirm.
          </DialogDescription>
          <PasswordInput
            autoFocus
            placeholder="Password"
            value={disable2FAPassword}
            onChange={(e) => setDisable2FAPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && disable2FAPassword && !disablingTwoFactor) handleDisableTwoFactor();
            }}
          />
          {disable2FAError && <p className="m-0 text-xs text-[var(--stamp)]">{disable2FAError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => handleDisable2FADialogChange(false)}>
              Cancel
            </Button>
            <Button variant="destructive" disabled={!disable2FAPassword || disablingTwoFactor} onClick={handleDisableTwoFactor}>
              {disablingTwoFactor ? "Disabling…" : "Disable"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteDialogOpen} onOpenChange={handleDeleteDialogChange}>
        <DialogContent tab="Danger zone" className="p-6 sm:max-w-[420px]">
          <DialogTitle>Delete your account?</DialogTitle>
          <DialogDescription className="text-sm leading-relaxed text-[var(--ink-2)]">
            This permanently deletes your account, activity history, and rules. Files already organized on disk are left alone. Enter your
            password to confirm.
          </DialogDescription>
          <PasswordInput
            autoFocus
            placeholder="Password"
            value={deletePassword}
            onChange={(e) => setDeletePassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && deletePassword && !deletingAccount) handleDeleteAccount();
            }}
          />
          {deleteError && <p className="m-0 text-xs text-[var(--stamp)]">{deleteError}</p>}
          <DialogFooter>
            <Button variant="outline" onClick={() => handleDeleteDialogChange(false)}>
              Cancel
            </Button>
            <Button variant="destructive" disabled={!deletePassword || deletingAccount} onClick={handleDeleteAccount}>
              {deletingAccount ? "Deleting…" : "Delete account"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={pendingFolder !== null}
        onOpenChange={handleFolderDialogChange}
        title="Change watched folder?"
        description={`FileFlow will start monitoring "${pendingFolder}" instead of the current folder. Files already sitting in the old folder are left alone unless you run "Organize existing files" there.`}
        confirmLabel="Change folder"
        onConfirm={applyWatchFolderChange}
      />
    </>
  );
}
