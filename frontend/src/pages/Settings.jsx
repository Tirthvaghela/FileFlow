import { useEffect, useState } from "react";
import Header from "../components/Header.jsx";
import { updateWatchFolder } from "../services/api.js";
import { useRules } from "../context/RulesContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";

const textInputClass =
  "mt-1 w-full rounded-md border border-[var(--border)] bg-[var(--page)] px-3 py-2 text-sm text-[var(--text-primary)]";

function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      role="switch"
      aria-checked={checked}
      className={`flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors ${
        checked ? "justify-end" : "justify-start"
      }`}
      style={{ background: checked ? "var(--series-1)" : "var(--gridline)" }}
    >
      <span className="h-4 w-4 rounded-full bg-white shadow-sm" />
    </button>
  );
}

export default function Settings() {
  const { rules, saveRules } = useRules();
  const { user, refresh: refreshUser } = useAuth();
  const savedWatchFolder = user?.watch_folder || "";
  const [watchFolder, setWatchFolder] = useState(savedWatchFolder);
  const [folderStatus, setFolderStatus] = useState("");
  const [folderError, setFolderError] = useState("");
  const [status, setStatus] = useState("");
  const [archiveFolder, setArchiveFolder] = useState("");
  const [defaultCategory, setDefaultCategory] = useState("");

  useEffect(() => {
    setWatchFolder(savedWatchFolder);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedWatchFolder]);

  async function commitWatchFolder() {
    const trimmed = watchFolder.trim();
    if (!trimmed || trimmed === savedWatchFolder) {
      setWatchFolder(savedWatchFolder);
      return;
    }
    const confirmed = window.confirm(
      `Change your watched folder to "${trimmed}"? FileFlow will start monitoring this folder instead of the current one. Files already sitting in the old folder are left alone unless you run "Organize existing files" there.`,
    );
    if (!confirmed) {
      setWatchFolder(savedWatchFolder);
      return;
    }
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
      await saveRules({ ...rules, ...patch });
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
            <input
              value={watchFolder}
              onChange={(e) => setWatchFolder(e.target.value)}
              onBlur={commitWatchFolder}
              spellCheck={false}
              className={textInputClass}
            />
            {folderStatus && (
              <span className="mt-1 block text-xs text-[var(--text-muted)]">{folderStatus}</span>
            )}
            {folderError && (
              <span className="mt-1 block text-xs" style={{ color: "var(--status-critical)" }}>
                {folderError}
              </span>
            )}
          </label>

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
                          borderColor: "var(--series-1)",
                          color: "var(--series-1)",
                          background: "color-mix(in srgb, var(--series-1) 10%, transparent)",
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
              <span className="font-medium text-[var(--series-1)]">
                {rules.archive_after_days} days
              </span>
            </div>
            <input
              type="range"
              min={1}
              max={90}
              value={rules.archive_after_days}
              onChange={(e) => save({ archive_after_days: Number(e.target.value) })}
              className="w-full accent-[var(--series-1)]"
            />
          </div>

          <div className="mb-5">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="text-[var(--text-secondary)]">Large file threshold</span>
              <span className="font-medium text-[var(--series-1)]">
                {rules.large_file_threshold_mb} MB
              </span>
            </div>
            <input
              type="range"
              min={10}
              max={2000}
              step={10}
              value={rules.large_file_threshold_mb}
              onChange={(e) => save({ large_file_threshold_mb: Number(e.target.value) })}
              className="w-full accent-[var(--series-1)]"
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

          {status && (
            <p className="mt-4 text-xs text-[var(--text-muted)]">{status}</p>
          )}
        </section>
      </div>
    </>
  );
}
