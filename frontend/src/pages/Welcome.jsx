import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "motion/react";
import { FolderKanban, FolderOpen, LayoutTemplate, Zap, Loader2 } from "lucide-react";
import { Button } from "../components/ui/button.jsx";
import GradientField from "../components/GradientField.jsx";
import Toggle from "../components/ui/Toggle.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import {
  applyOnboardingTemplate,
  browseFolder,
  completeOnboarding,
  getOnboardingTemplates,
  getRules,
  updateRules,
  updateWatchFolder,
} from "../services/api.js";

const textInputClass =
  "mt-2 w-full rounded-md border border-[var(--border)] bg-[var(--page)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--brand)]/30";

const STEPS = [
  { label: "Watch folder", Icon: FolderOpen },
  { label: "Starter rules", Icon: LayoutTemplate },
  { label: "Automation", Icon: Zap },
];

export default function Welcome() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [finishing, setFinishing] = useState(false);
  const [finishError, setFinishError] = useState("");

  const [watchFolder, setWatchFolder] = useState(user?.watch_folder || "");
  const [folderError, setFolderError] = useState("");
  const [savingFolder, setSavingFolder] = useState(false);
  const [browsing, setBrowsing] = useState(false);

  const [templates, setTemplates] = useState(null);
  const [selectedTemplate, setSelectedTemplate] = useState(null); // null = start from scratch
  const [savingTemplate, setSavingTemplate] = useState(false);

  const [monitoringOn, setMonitoringOn] = useState(false);

  useEffect(() => {
    getOnboardingTemplates()
      .then(setTemplates)
      .catch(() => setTemplates([]));
  }, []);

  async function finish() {
    setFinishing(true);
    setFinishError("");
    try {
      if (monitoringOn) {
        const rules = await getRules();
        await updateRules({ ...rules, realtime_monitoring_enabled: true });
      }
      await completeOnboarding();
      await refresh();
      navigate("/app", { replace: true });
    } catch {
      setFinishError("Something went wrong finishing setup -- try again.");
      setFinishing(false);
    }
  }

  function skip() {
    setFinishing(true);
    setFinishError("");
    completeOnboarding()
      .then(refresh)
      .then(() => navigate("/app", { replace: true }))
      .catch(() => {
        setFinishError("Something went wrong skipping setup -- try again.");
        setFinishing(false);
      });
  }

  async function handleBrowseFolder() {
    setBrowsing(true);
    setFolderError("");
    try {
      const { path } = await browseFolder();
      if (path) setWatchFolder(path);
    } catch {
      setFolderError("Couldn't open the folder picker -- type the path instead.");
    } finally {
      setBrowsing(false);
    }
  }

  async function continueFromFolder() {
    const trimmed = watchFolder.trim();
    setFolderError("");
    if (!trimmed) {
      setFolderError("Pick a folder for FileFlow to watch.");
      return;
    }
    setSavingFolder(true);
    try {
      await updateWatchFolder(trimmed);
      setStep(1);
    } catch (err) {
      setFolderError(err?.response?.data?.detail || "Couldn't use that folder.");
    } finally {
      setSavingFolder(false);
    }
  }

  async function continueFromTemplate() {
    if (selectedTemplate) {
      setSavingTemplate(true);
      try {
        await applyOnboardingTemplate(selectedTemplate);
      } catch {
        // Best-effort -- the wizard shouldn't get stuck over a template
        // pick when everything else (folder, rules defaults) is fine.
      } finally {
        setSavingTemplate(false);
      }
    }
    setStep(2);
  }

  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-[var(--page)] px-6 py-12">
      <div className="absolute inset-0 bg-grid-light pointer-events-none" />
      <GradientField />

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="relative z-10 w-full max-w-lg"
      >
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--brand)] text-[var(--brand-foreground)] shadow-sm shadow-[var(--brand)]/30">
              <FolderKanban className="h-[18px] w-[18px]" />
            </span>
            <span className="font-display text-base font-semibold text-[var(--text-primary)]">
              FileFlow
            </span>
          </div>
          <button
            type="button"
            onClick={skip}
            disabled={finishing}
            className="text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:underline disabled:opacity-50"
          >
            Skip setup
          </button>
        </div>

        <div className="mb-6 flex items-center gap-2">
          {STEPS.map((s, i) => (
            <div key={s.label} className="flex flex-1 items-center gap-2">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-xs font-medium"
                style={{
                  borderColor: i <= step ? "var(--brand)" : "var(--border)",
                  color: i <= step ? "var(--brand)" : "var(--text-muted)",
                  background: i <= step ? "color-mix(in srgb, var(--brand) 12%, transparent)" : "transparent",
                }}
              >
                <s.Icon className="h-3.5 w-3.5" />
              </span>
              {i < STEPS.length - 1 && (
                <span
                  className="h-px flex-1"
                  style={{ background: i < step ? "var(--brand)" : "var(--border)" }}
                />
              )}
            </div>
          ))}
        </div>

        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-8 shadow-xl shadow-black/[0.15]">
          <AnimatePresence mode="wait">
            {step === 0 && (
              <motion.div
                key="folder"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
              >
                <h1 className="font-display text-xl font-medium text-[var(--text-primary)]">
                  Where should FileFlow watch?
                </h1>
                <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
                  We've already set up a folder for you -- change it now if you'd rather
                  point FileFlow somewhere else.
                </p>
                <label className="mt-5 block text-sm text-[var(--text-secondary)]">
                  Watched folder
                  <div className="mt-2 flex gap-2">
                    <input
                      value={watchFolder}
                      onChange={(e) => setWatchFolder(e.target.value)}
                      spellCheck={false}
                      className={`${textInputClass} mt-0`}
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="lg"
                      onClick={handleBrowseFolder}
                      disabled={browsing}
                      className="shrink-0"
                    >
                      {browsing ? <Loader2 className="h-4 w-4 animate-spin" /> : "Browse…"}
                    </Button>
                  </div>
                </label>
                {folderError && (
                  <p className="mt-2 text-xs" style={{ color: "var(--status-critical)" }}>
                    {folderError}
                  </p>
                )}
                <Button
                  size="lg"
                  className="mt-6 w-full"
                  onClick={continueFromFolder}
                  disabled={savingFolder}
                >
                  {savingFolder ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Continue
                </Button>
              </motion.div>
            )}

            {step === 1 && (
              <motion.div
                key="template"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
              >
                <h1 className="font-display text-xl font-medium text-[var(--text-primary)]">
                  Pick a starting point
                </h1>
                <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
                  A few extra rules on top of the basics -- you can change or remove any
                  of these later in Rules.
                </p>

                <div className="mt-5 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {(templates || []).map((t) => {
                    const active = selectedTemplate === t.id;
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setSelectedTemplate(t.id)}
                        className="rounded-xl border p-3.5 text-left transition-colors"
                        style={{
                          borderColor: active ? "var(--brand)" : "var(--border)",
                          background: active
                            ? "color-mix(in srgb, var(--brand) 8%, transparent)"
                            : "var(--page)",
                        }}
                      >
                        <div className="text-sm font-semibold text-[var(--text-primary)]">
                          {t.label}
                        </div>
                        <div className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">
                          {t.description}
                        </div>
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    onClick={() => setSelectedTemplate(null)}
                    className="rounded-xl border p-3.5 text-left transition-colors"
                    style={{
                      borderColor: selectedTemplate === null ? "var(--brand)" : "var(--border)",
                      background:
                        selectedTemplate === null
                          ? "color-mix(in srgb, var(--brand) 8%, transparent)"
                          : "var(--page)",
                    }}
                  >
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      Start from scratch
                    </div>
                    <div className="mt-0.5 text-xs leading-relaxed text-[var(--text-muted)]">
                      Just the basic file-type categories, nothing extra.
                    </div>
                  </button>
                </div>

                <Button
                  size="lg"
                  className="mt-6 w-full"
                  onClick={continueFromTemplate}
                  disabled={savingTemplate}
                >
                  {savingTemplate ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Continue
                </Button>
              </motion.div>
            )}

            {step === 2 && (
              <motion.div
                key="automation"
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -12 }}
                transition={{ duration: 0.2 }}
              >
                <h1 className="font-display text-xl font-medium text-[var(--text-primary)]">
                  Turn on automation now?
                </h1>
                <p className="mt-1.5 text-sm text-[var(--text-secondary)]">
                  With this on, FileFlow detects and organizes files the instant they land
                  in your watch folder. You can flip this any time from Settings.
                </p>

                <div className="mt-5 flex items-center justify-between rounded-xl border border-[var(--border)] bg-[var(--page)] px-4 py-3.5">
                  <div>
                    <div className="text-sm font-medium text-[var(--text-primary)]">
                      Real-time monitoring
                    </div>
                    <div className="text-xs text-[var(--text-muted)]">
                      Detect files the instant they land
                    </div>
                  </div>
                  <Toggle checked={monitoringOn} onChange={setMonitoringOn} />
                </div>

                {finishError && (
                  <p className="mt-3 text-xs" style={{ color: "var(--status-critical)" }}>
                    {finishError}
                  </p>
                )}

                <Button size="lg" className="mt-6 w-full" onClick={finish} disabled={finishing}>
                  {finishing ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Finish setup
                </Button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
