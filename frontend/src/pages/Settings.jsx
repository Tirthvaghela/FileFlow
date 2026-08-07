import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, CheckCircle2, Copy, Loader2, Plus, X, XCircle } from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import Header from "../components/Header.jsx";
import ConfirmDialog from "../components/ui/ConfirmDialog.jsx";
import Toggle from "../components/ui/Toggle.jsx";
import { Button } from "../components/ui/button.jsx";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "../components/ui/dialog.jsx";
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
import { useRules } from "../context/RulesContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { gsap, useGSAP } from "../lib/gsap.js";

const textInputClass =
  "mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--page)] px-3 py-2 text-sm text-[var(--text-primary)]";

const STATUS_META = {
  "Saving…": { color: "var(--text-muted)", Icon: Loader2, spin: true },
  Saved: { color: "var(--status-good)", Icon: CheckCircle2 },
  "Failed to save": { color: "var(--status-critical)", Icon: XCircle },
};

function StatusMessage({ status }) {
  const meta = status ? STATUS_META[status] : null;
  return (
    <AnimatePresence mode="wait">
      {status && meta && (
        <motion.p
          key={status}
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="mt-4 flex items-center gap-1.5 text-xs font-medium"
          style={{ color: meta.color }}
        >
          <meta.Icon className={`h-3.5 w-3.5 ${meta.spin ? "animate-spin" : ""}`} />
          {status}
        </motion.p>
      )}
    </AnimatePresence>
  );
}

function Slider({ value, onChange, min, max, step = 1 }) {
  const trackRef = useRef(null);
  const pct = gsap.utils.clamp(0, 100, gsap.utils.mapRange(min, max, 0, 100, value));

  useGSAP(
    () => {
      gsap.to(trackRef.current, { width: `${pct}%`, duration: 0.2, ease: "power1.out" });
    },
    { dependencies: [pct], scope: trackRef },
  );

  return (
    <div className="relative flex h-5 w-full items-center">
      <div className="absolute inset-y-0 my-auto h-1.5 w-full rounded-full" style={{ background: "var(--gridline)" }} />
      <div
        ref={trackRef}
        className="absolute inset-y-0 my-auto h-1.5 rounded-full"
        style={{ background: "var(--brand)", width: 0 }}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="relative z-10 w-full cursor-pointer appearance-none bg-transparent [&::-webkit-slider-runnable-track]:bg-transparent [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-[var(--brand-foreground)] [&::-webkit-slider-thumb]:bg-[var(--brand)] [&::-webkit-slider-thumb]:shadow-sm [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-[var(--brand-foreground)] [&::-moz-range-thumb]:bg-[var(--brand)]"
      />
    </div>
  );
}

export default function Settings() {
  const { rules, saveRules } = useRules();
  const { user, refresh: refreshUser, logout } = useAuth();
  const navigate = useNavigate();
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedWatchFolder]);

  useEffect(() => {
    getTwoFactorStatus()
      .then((s) => setTwoFactorEnabled(s.enabled))
      .catch(() => {});
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

  // Local input state so a PUT only fires once the field loses focus, not
  // on every keystroke (unlike the sliders/toggles below, which are cheap
  // to save immediately).
  useEffect(() => {
    if (rules) {
      setArchiveFolder(rules.archive_folder);
      setDefaultCategory(rules.default_category);
    }
  }, [rules]);

  async function save(patch) {
    setStatus("Saving…");
    try {
      // Updater form, not a `{ ...rules, ...patch }` snapshot -- the
      // archive-days/threshold sliders fire one save per pointer-move
      // while dragging, so several of these can be queued at once, each
      // needing to apply its own patch on top of whichever save ahead of
      // it in the queue lands, not the `rules` this component rendered
      // with before the drag started.
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

  async function handleGenerateAgentToken() {
    setGeneratingToken(true);
    setTokenCopied(false);
    try {
      const { token, scope } = await generateAgentToken(selectedTokenScope);
      setAgentToken(token);
      setAgentTokenScope(scope);
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
      const data = await setupTwoFactor();
      setTwoFactorSetup(data);
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

  function commitDefaultCategory() {
    const trimmed = defaultCategory.trim() || "Others";
    setDefaultCategory(trimmed);
    if (trimmed !== rules.default_category) save({ default_category: trimmed });
  }

  if (!rules) {
    return (
      <>
        <Header title="Settings" subtitle="Configure monitoring and automation policy" />
        <div className="p-8 text-sm text-[var(--text-muted)]">Loading…</div>
      </>
    );
  }

  return (
    <>
      <Header title="Settings" subtitle="Configure monitoring and automation policy" />
      <div className="grid grid-cols-1 gap-6 p-8 lg:grid-cols-2">
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm">
          <h2 className="mb-4 text-sm font-medium text-[var(--text-primary)]">
            Folder monitoring
          </h2>

          <label className="mb-4 block text-sm text-[var(--text-secondary)]">
            Watched folder
            <div className="flex gap-2">
              <input
                value={watchFolder}
                onChange={(e) => setWatchFolder(e.target.value)}
                onBlur={commitWatchFolder}
                spellCheck={false}
                className={`${textInputClass} flex-1`}
              />
              <button
                type="button"
                onClick={handleBrowseFolder}
                disabled={browsingFolder}
                className="mt-1 shrink-0 rounded-md border border-[var(--border)] bg-[var(--page)] px-3 py-2 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--gridline)] disabled:opacity-50"
              >
                {browsingFolder ? "Opening…" : "Browse…"}
              </button>
            </div>
            {folderStatus && (
              <span className="mt-1 block text-xs text-[var(--text-muted)]">{folderStatus}</span>
            )}
            {folderError && (
              <span className="mt-1 block text-xs" style={{ color: "var(--status-critical)" }}>
                {folderError}
              </span>
            )}
          </label>

          <div className="mb-4">
            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-sm text-[var(--text-secondary)]">
                Additional watch folders
              </span>
              <button
                type="button"
                onClick={handleAddAdditionalFolder}
                disabled={addingFolder}
                className="flex items-center gap-1 text-xs font-medium text-[var(--brand)] hover:underline disabled:opacity-50"
              >
                <Plus className="h-3 w-3" />
                {addingFolder ? "Opening…" : "Add folder"}
              </button>
            </div>
            {(user?.additional_watch_folders || []).length === 0 ? (
              <p className="text-xs text-[var(--text-muted)]">
                Watch more than one folder with the same rules -- add one here.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {user.additional_watch_folders.map((path) => (
                  <li
                    key={path}
                    className="flex items-center justify-between gap-2 rounded-md border border-[var(--border)] bg-[var(--page)] px-3 py-2"
                  >
                    <span className="min-w-0 flex-1 truncate text-xs text-[var(--text-primary)]">
                      {path}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleRemoveAdditionalFolder(path)}
                      disabled={removingFolder === path}
                      className="shrink-0 text-[var(--text-muted)] hover:text-[var(--status-critical)] disabled:opacity-50"
                      aria-label={`Stop watching ${path}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {additionalFolderError && (
              <span className="mt-1.5 block text-xs" style={{ color: "var(--status-critical)" }}>
                {additionalFolderError}
              </span>
            )}
          </div>

          <div className="flex items-center justify-between border-t border-[var(--border)] py-3">
            <div>
              <div className="text-sm text-[var(--text-primary)]">Real-time monitoring</div>
              <div className="text-xs text-[var(--text-muted)]">
                Detect files the instant they land
              </div>
            </div>
            <Toggle
              checked={rules.realtime_monitoring_enabled}
              onChange={(v) => save({ realtime_monitoring_enabled: v })}
            />
          </div>

          <div className="flex items-center justify-between border-t border-[var(--border)] py-3">
            <div>
              <div className="text-sm text-[var(--text-primary)]">Desktop notifications</div>
              <div className="text-xs text-[var(--text-muted)]">Toast on every action</div>
            </div>
            <Toggle
              checked={rules.desktop_notifications_enabled}
              onChange={(v) => save({ desktop_notifications_enabled: v })}
            />
          </div>

          <div className="flex items-center justify-between border-t border-[var(--border)] py-3">
            <div>
              <div className="text-sm text-[var(--text-primary)]">Scheduled nightly sweep</div>
              <div className="text-xs text-[var(--text-muted)]">
                Run "Organize existing files" automatically every day
              </div>
            </div>
            <Toggle
              checked={rules.scheduled_organize_enabled}
              onChange={(v) => save({ scheduled_organize_enabled: v })}
            />
          </div>
          {rules.scheduled_organize_enabled && (
            <div className="flex items-center justify-between border-t border-[var(--border)] py-3">
              <div className="text-sm text-[var(--text-secondary)]">Run at</div>
              <input
                type="time"
                value={rules.scheduled_organize_time}
                onChange={(e) => save({ scheduled_organize_time: e.target.value })}
                className="rounded-md border border-[var(--border)] bg-[var(--page)] px-3 py-1.5 text-sm text-[var(--text-primary)]"
              />
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm">
          <h2 className="mb-4 text-sm font-medium text-[var(--text-primary)]">
            Automation policy
          </h2>

          <div className="mb-5">
            <div className="mb-2 text-sm text-[var(--text-secondary)]">Duplicate handling</div>
            <div className="grid grid-cols-3 gap-2">
              {["rename", "skip", "replace"].map((mode) => (
                <button
                  key={mode}
                  onClick={() => save({ duplicate_handling: mode })}
                  className="rounded-lg border px-3 py-2 text-sm font-medium capitalize"
                  style={
                    rules.duplicate_handling === mode
                      ? {
                          borderColor: "var(--brand)",
                          color: "var(--brand)",
                          background: "color-mix(in srgb, var(--brand) 10%, transparent)",
                        }
                      : { borderColor: "var(--border)", color: "var(--text-secondary)" }
                  }
                >
                  {mode}
                </button>
              ))}
            </div>
            {rules.duplicate_handling === "replace" && (
              <p className="mt-2 text-xs" style={{ color: "var(--status-critical)" }}>
                Replace permanently deletes the existing file at the destination before moving the new one in. This can't be undone.
              </p>
            )}
          </div>

          <div className="mb-5">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="text-[var(--text-secondary)]">Archive files older than</span>
              <span className="font-medium text-[var(--brand)]">
                {rules.archive_after_days} days
              </span>
            </div>
            <Slider
              min={1}
              max={90}
              value={rules.archive_after_days}
              onChange={(v) => save({ archive_after_days: v })}
            />
          </div>

          <div className="mb-5">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="text-[var(--text-secondary)]">Large file threshold</span>
              <span className="font-medium text-[var(--brand)]">
                {rules.large_file_threshold_mb} MB
              </span>
            </div>
            <Slider
              min={10}
              max={2000}
              step={10}
              value={rules.large_file_threshold_mb}
              onChange={(v) => save({ large_file_threshold_mb: v })}
            />
          </div>

          <label className="mb-4 block text-sm text-[var(--text-secondary)]">
            Archive folder name
            <input
              value={archiveFolder}
              onChange={(e) => setArchiveFolder(e.target.value)}
              onBlur={commitArchiveFolder}
              className={textInputClass}
            />
          </label>

          <label className="block text-sm text-[var(--text-secondary)]">
            Fallback folder name
            <input
              value={defaultCategory}
              onChange={(e) => setDefaultCategory(e.target.value)}
              onBlur={commitDefaultCategory}
              className={textInputClass}
            />
            <span className="mt-1 block text-xs text-[var(--text-muted)]">
              Used for files that don't match any rule or category.
            </span>
          </label>

          <StatusMessage status={status} />
        </section>
      </div>

      <div className="px-8 pb-8">
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm">
          <h2 className="mb-1 text-sm font-medium text-[var(--text-primary)]">Remote agent</h2>
          <p className="mb-4 text-xs text-[var(--text-muted)]">
            Run FileFlow's agent on your own machine so it watches your real local folder
            directly, instead of a folder on whatever machine runs this dashboard. Install it
            from the <strong>Downloads</strong> menu in the top bar — the first time it runs,
            it'll ask for this dashboard's address and a token. Generate one below and paste it
            in.
          </p>

          <div className="mb-3 flex gap-2">
            <button
              type="button"
              onClick={() => setSelectedTokenScope("full")}
              className="rounded-lg border px-3 py-1.5 text-xs font-medium"
              style={
                selectedTokenScope === "full"
                  ? { borderColor: "var(--brand)", color: "var(--brand)", background: "color-mix(in srgb, var(--brand) 10%, transparent)" }
                  : { borderColor: "var(--border)", color: "var(--text-secondary)" }
              }
            >
              Full control
            </button>
            <button
              type="button"
              onClick={() => setSelectedTokenScope("read_only")}
              className="rounded-lg border px-3 py-1.5 text-xs font-medium"
              style={
                selectedTokenScope === "read_only"
                  ? { borderColor: "var(--brand)", color: "var(--brand)", background: "color-mix(in srgb, var(--brand) 10%, transparent)" }
                  : { borderColor: "var(--border)", color: "var(--text-secondary)" }
              }
            >
              Read-only
            </button>
          </div>
          <p className="mb-3 text-xs text-[var(--text-muted)]">
            {selectedTokenScope === "full"
              ? "Can watch, organize, and report activity -- what a real agent installation needs."
              : "Can only fetch rules -- can't move files, report activity, or run commands. Useful for a monitoring/preview integration that shouldn't be able to touch anything."}
          </p>

          <button
            type="button"
            onClick={handleGenerateAgentToken}
            disabled={generatingToken}
            className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-medium text-[var(--brand-foreground)] hover:opacity-90 disabled:opacity-50"
          >
            {generatingToken ? "Generating…" : "Generate agent token"}
          </button>

          {agentToken && (
            <div className="mt-4 rounded-lg border border-[var(--border)] bg-[var(--page)] p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="text-xs font-medium text-[var(--text-secondary)]">
                  Shown once — copy it now
                  {agentTokenScope === "read_only" && (
                    <span
                      className="ml-1.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
                      style={{ color: "var(--status-warning)", background: "color-mix(in srgb, var(--status-warning) 14%, transparent)" }}
                    >
                      Read-only
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  onClick={copyAgentToken}
                  className="flex items-center gap-1 text-xs text-[var(--brand)] hover:underline"
                >
                  <Copy className="h-3 w-3" />
                  {tokenCopied ? "Copied" : "Copy"}
                </button>
              </div>
              <code className="block break-all font-mono-data text-[11px] text-[var(--text-primary)]">
                {agentToken}
              </code>
              <p className="mt-2 text-xs" style={{ color: "var(--status-warning)" }}>
                Generating a new token immediately invalidates this one and any others issued
                before it.
              </p>
            </div>
          )}
        </section>
      </div>

      <div className="px-8 pb-8">
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm">
          <h2 className="mb-1 text-sm font-medium text-[var(--text-primary)]">
            Two-factor authentication
          </h2>
          <p className="mb-4 text-xs text-[var(--text-muted)]">
            Require a code from an authenticator app in addition to your password when signing
            in.
          </p>

          {twoFactorEnabled === null ? (
            <p className="text-xs text-[var(--text-muted)]">Loading…</p>
          ) : backupCodes ? (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--page)] p-3">
              <p className="mb-2 text-xs font-medium text-[var(--text-secondary)]">
                Save these backup codes — shown once. Each works one time if you lose access to
                your authenticator app.
              </p>
              <div className="grid grid-cols-2 gap-1.5 font-mono-data text-xs text-[var(--text-primary)]">
                {backupCodes.map((c) => (
                  <code key={c} className="rounded bg-[var(--surface-1)] px-2 py-1">
                    {c}
                  </code>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setBackupCodes(null)}
                className="mt-3 rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-medium text-[var(--brand-foreground)] hover:opacity-90"
              >
                I've saved these
              </button>
            </div>
          ) : twoFactorSetup ? (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--page)] p-3">
              <p className="mb-3 text-xs text-[var(--text-secondary)]">
                Scan this with your authenticator app (Google Authenticator, Authy, etc.), then
                enter the 6-digit code it shows.
              </p>
              <img
                src={twoFactorSetup.qr_code_data_uri}
                alt="2FA setup QR code"
                className="mb-3 h-40 w-40 rounded-lg border border-[var(--border)] bg-white p-2"
              />
              <p className="mb-3 text-xs text-[var(--text-muted)]">
                Can't scan it? Enter this key manually:{" "}
                <code className="font-mono-data text-[var(--text-primary)]">
                  {twoFactorSetup.secret}
                </code>
              </p>
              <label className="mb-3 block text-sm text-[var(--text-secondary)]">
                6-digit code
                <input
                  value={enableCode}
                  onChange={(e) => setEnableCode(e.target.value)}
                  placeholder="123456"
                  className={textInputClass}
                />
              </label>
              {twoFactorError && (
                <p className="mb-3 text-xs" style={{ color: "var(--status-critical)" }}>
                  {twoFactorError}
                </p>
              )}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleEnableTwoFactor}
                  disabled={enablingTwoFactor || !enableCode.trim()}
                  className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-medium text-[var(--brand-foreground)] hover:opacity-90 disabled:opacity-50"
                >
                  {enablingTwoFactor ? "Verifying…" : "Enable"}
                </button>
                <button
                  type="button"
                  onClick={cancelTwoFactorSetup}
                  className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--gridline)]"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : twoFactorEnabled ? (
            <div className="flex items-center justify-between">
              <span
                className="rounded-lg px-3 py-1.5 text-xs font-medium"
                style={{ color: "var(--status-good)", background: "color-mix(in srgb, var(--status-good) 14%, transparent)" }}
              >
                Enabled
              </span>
              <button
                type="button"
                onClick={() => setDisable2FADialogOpen(true)}
                className="rounded-lg border border-[var(--border)] px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--gridline)]"
              >
                Disable
              </button>
            </div>
          ) : (
            <>
              {twoFactorError && (
                <p className="mb-3 text-xs" style={{ color: "var(--status-critical)" }}>
                  {twoFactorError}
                </p>
              )}
              <button
                type="button"
                onClick={handleStartTwoFactorSetup}
                disabled={startingSetup}
                className="rounded-lg bg-[var(--brand)] px-4 py-2 text-sm font-medium text-[var(--brand-foreground)] hover:opacity-90 disabled:opacity-50"
              >
                {startingSetup ? "Starting…" : "Set up 2FA"}
              </button>
            </>
          )}
        </section>
      </div>

      <Dialog open={disable2FADialogOpen} onOpenChange={handleDisable2FADialogChange}>
        <DialogContent className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[420px]">
          <DialogTitle className="font-display text-base font-semibold text-[var(--text-primary)]">
            Disable two-factor authentication?
          </DialogTitle>
          <DialogDescription className="text-sm leading-relaxed text-[var(--text-secondary)]">
            Your account will only need a password to sign in. Enter your password to confirm.
          </DialogDescription>
          <PasswordInput
            autoFocus
            placeholder="Password"
            value={disable2FAPassword}
            onChange={(e) => setDisable2FAPassword(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && disable2FAPassword && !disablingTwoFactor) {
                handleDisableTwoFactor();
              }
            }}
          />
          {disable2FAError && (
            <p className="text-xs" style={{ color: "var(--status-critical)" }}>
              {disable2FAError}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => handleDisable2FADialogChange(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={!disable2FAPassword || disablingTwoFactor}
              onClick={handleDisableTwoFactor}
            >
              {disablingTwoFactor ? "Disabling…" : "Disable"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="px-8 pb-8">
        <section
          className="rounded-2xl border p-5 shadow-sm"
          style={{ borderColor: "var(--status-critical)", background: "var(--surface-1)" }}
        >
          <h2 className="mb-1 text-sm font-medium text-[var(--text-primary)]">Danger zone</h2>
          <p className="mb-4 text-xs text-[var(--text-muted)]">
            Permanently deletes your account, watched-folder history, and rules. This can't be
            undone.
          </p>
          <button
            type="button"
            onClick={() => setDeleteDialogOpen(true)}
            className="rounded-lg border px-4 py-2 text-sm font-medium hover:opacity-90"
            style={{ borderColor: "var(--status-critical)", color: "var(--status-critical)" }}
          >
            Delete account
          </button>
        </section>
      </div>

      <Dialog open={deleteDialogOpen} onOpenChange={handleDeleteDialogChange}>
        <DialogContent className="rounded-2xl bg-[var(--surface-1)] p-6 sm:max-w-[420px]">
          <span
            className="flex h-11 w-11 items-center justify-center rounded-full"
            style={{
              color: "var(--status-critical)",
              background: "color-mix(in srgb, var(--status-critical) 14%, transparent)",
            }}
          >
            <AlertTriangle className="h-5 w-5" />
          </span>
          <DialogTitle className="mt-3 font-display text-base font-semibold text-[var(--text-primary)]">
            Delete your account?
          </DialogTitle>
          <DialogDescription className="text-sm leading-relaxed text-[var(--text-secondary)]">
            This permanently deletes your account, activity history, and rules. Files already
            organized on disk are left alone. Enter your password to confirm.
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
          {deleteError && (
            <p className="text-xs" style={{ color: "var(--status-critical)" }}>
              {deleteError}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => handleDeleteDialogChange(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={!deletePassword || deletingAccount}
              onClick={handleDeleteAccount}
            >
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
