import { useEffect, useMemo, useRef, useState } from "react";
import Header from "../components/Header.jsx";
import ConfirmDialog from "../components/ui/ConfirmDialog.jsx";
import Toggle from "../components/ui/Toggle.jsx";
import { Calendar, Download, FileSearch, FlaskConical, Folder, Pencil, Regex, Ruler, Upload, X } from "lucide-react";
import { buildCategoryColorMap, collectKnownFolders } from "../utils/categoryMeta.js";
import { previewRule, simulateRules } from "../services/api.js";
import { useRules } from "../context/RulesContext.jsx";
import { Flip, useGSAP } from "../lib/gsap.js";

const inputClass =
  "rounded-md border border-[var(--border)] bg-[var(--page)] px-2.5 py-1.5 text-sm text-[var(--text-primary)]";

const TYPE_META = {
  extension: { label: "EXTENSION", Icon: Folder },
  keyword: { label: "KEYWORD", Icon: Pencil },
  size: { label: "SIZE", Icon: Ruler },
  regex: { label: "REGEX", Icon: Regex },
  date: { label: "DATE", Icon: Calendar },
  content: { label: "CONTENT", Icon: FileSearch },
};

function RuleCard({ type, condition, folder, color, enabled, onToggle }) {
  const { label, Icon } = TYPE_META[type];
  return (
    <div
      data-flip-id={`${type}-${condition}`}
      className="flex items-center gap-3 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 transition-opacity"
      style={{ opacity: enabled ? 1 : 0.55 }}
    >
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
        style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}
      >
        <Icon width={16} height={16} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs">
          <span
            className="rounded px-1.5 py-0.5 font-semibold tracking-wide"
            style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}
          >
            {label}
          </span>
          <span className={`font-medium text-[var(--text-primary)] ${type === "keyword" ? "capitalize" : ""}`}>
            {condition}
          </span>
        </div>
        <div className="mt-0.5 text-xs text-[var(--text-muted)]">
          → moves to <span className="font-medium text-[var(--text-secondary)]">{folder}</span>
        </div>
      </div>
      <Toggle checked={enabled} onChange={onToggle} />
    </div>
  );
}

const emptyForm = { type: "extension", match: "", folder: "" };

export default function Rules() {
  const { rules, saveRules } = useRules();
  const [status, setStatus] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [newCategoryName, setNewCategoryName] = useState("");
  const [newExtByCategory, setNewExtByCategory] = useState({});
  const [preview, setPreview] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [pendingRemoveCategory, setPendingRemoveCategory] = useState(null);
  const [addingRule, setAddingRule] = useState(false);
  const [pendingImport, setPendingImport] = useState(null);
  const [importError, setImportError] = useState("");
  const [simulation, setSimulation] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const fileInputRef = useRef(null);

  async function handleSimulate() {
    setSimulating(true);
    try {
      const result = await simulateRules(rules);
      setSimulation(result);
    } catch {
      setSimulation({ error: true });
    } finally {
      setSimulating(false);
    }
  }

  // Debounced dry-run: shows which already-organized files this not-yet-
  // saved rule would have matched, so a typo (e.g. "invoic") is obvious
  // before it's saved rather than discovered days later.
  useEffect(() => {
    const match = form.match.trim();
    // "Already organized" history only ever recorded a filename, never a
    // file's content or modification date -- a content/date preview here
    // would have to fake the match against the filename instead, which is
    // actively misleading rather than merely absent. Regex still previews
    // (against the same recorded filenames); extension/keyword unchanged.
    if (!match || form.type === "date" || form.type === "content") {
      setPreview(null);
      setPreviewLoading(false);
      return;
    }
    setPreviewLoading(true);
    const timer = setTimeout(() => {
      previewRule(form.type, match)
        .then(setPreview)
        .catch(() => setPreview(null))
        .finally(() => setPreviewLoading(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [form.type, form.match]);

  const colorMap = useMemo(() => {
    if (!rules) return {};
    const folders = [
      ...Object.values(rules.extension_rules),
      ...Object.values(rules.disabled_extension_rules || {}),
      ...rules.keyword_rules.map((r) => r.folder),
      ...(rules.disabled_keyword_rules || []).map((r) => r.folder),
      ...(rules.regex_rules || []).map((r) => r.folder),
      ...(rules.disabled_regex_rules || []).map((r) => r.folder),
      ...(rules.date_rules || []).map((r) => r.folder),
      ...(rules.disabled_date_rules || []).map((r) => r.folder),
      ...(rules.content_keyword_rules || []).map((r) => r.folder),
      ...(rules.disabled_content_keyword_rules || []).map((r) => r.folder),
      rules.large_file_folder,
      ...Object.keys(rules.categories || {}),
    ];
    return buildCategoryColorMap(folders);
  }, [rules]);

  const allFolders = useMemo(() => collectKnownFolders(rules), [rules]);

  // A rule card's position in the list changes when it's toggled (enabled
  // cards render before disabled ones) or when one is added -- Flip
  // animates that reflow instead of letting cards snap to their new spot.
  // captureFlip() must run synchronously in the same click handler that
  // triggers the reorder (before React commits the new order); the
  // useGSAP below then plays from that captured state once the reorder
  // has actually rendered, keyed on a string that changes exactly when
  // the rendered card set/order does.
  const flipKey = useMemo(() => {
    if (!rules) return "";
    const ext = [
      ...Object.keys(rules.extension_rules).map((e) => `e:${e}:1`),
      ...Object.keys(rules.disabled_extension_rules || {}).map((e) => `e:${e}:0`),
    ];
    const kw = [
      ...rules.keyword_rules.map((r) => `k:${r.keyword}:1`),
      ...(rules.disabled_keyword_rules || []).map((r) => `k:${r.keyword}:0`),
    ];
    return [...ext, ...kw].join("|");
  }, [rules]);
  const cardsRef = useRef(null);
  const flipStateRef = useRef(null);

  function captureFlip() {
    if (cardsRef.current) {
      flipStateRef.current = Flip.getState(cardsRef.current.querySelectorAll("[data-flip-id]"));
    }
  }

  useGSAP(
    () => {
      if (flipStateRef.current) {
        Flip.from(flipStateRef.current, { duration: 0.4, ease: "power2.inOut", absolute: true });
        flipStateRef.current = null;
      }
    },
    { dependencies: [flipKey], scope: cardsRef },
  );

  if (!rules) {
    return (
      <>
        <Header title="Automation rules" subtitle="Route files by extension, keyword or size" />
        <div className="p-8 text-sm text-[var(--text-muted)]">Loading…</div>
      </>
    );
  }

  async function persist(next) {
    setStatus("Saving…");
    try {
      await saveRules(next);
      setStatus("Saved");
      setTimeout(() => setStatus(""), 1500);
      return true;
    } catch {
      setStatus("Failed to save");
      return false;
    }
  }

  function handleExportRules() {
    // Entirely client-side -- `rules` is already the full document in
    // memory, so there's nothing a round trip to the server would add.
    const blob = new Blob([JSON.stringify(rules, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `fileflow-rules-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function handleImportClick() {
    setImportError("");
    fileInputRef.current?.click();
  }

  function handleImportFile(e) {
    const file = e.target.files?.[0];
    e.target.value = ""; // reset so picking the same file again still fires onChange
    if (!file) return;
    setImportError("");

    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result);
        setPendingImport(parsed);
      } catch {
        setImportError("That file isn't valid JSON.");
      }
    };
    reader.onerror = () => setImportError("Couldn't read that file.");
    reader.readAsText(file);
  }

  async function confirmImport() {
    const imported = pendingImport;
    setPendingImport(null);
    setStatus("Saving…");
    try {
      await saveRules(imported);
      setStatus("Saved");
      setTimeout(() => setStatus(""), 1500);
    } catch (err) {
      // persist() (used everywhere else) swallows its error after setting
      // "Failed to save" -- this bypasses it and calls saveRules directly
      // so the catch below can show *why* an import specifically failed.
      // The server's field-level validation errors aren't meant for
      // display (a list of Pydantic error objects, not prose); a flat
      // "this wasn't a real export" covers every way an arbitrary JSON
      // file can fail to be one, without trying to translate that shape.
      setStatus("Failed to save");
      setImportError(
        err?.response?.status === 422
          ? "That file isn't a valid FileFlow rules export."
          : "Couldn't import that file.",
      );
    }
  }

  // Every mutation below passes an *updater* -- `(current) => next`, same
  // shape as React's functional setState -- rather than a `{ ...rules,
  // ... }` object built from this render's `rules`. RulesContext queues
  // saves and resolves each updater against whatever the previous queued
  // save actually landed as, so two rapid, independent edits (e.g. two
  // different extension toggles clicked back to back) each apply cleanly
  // on top of the other instead of one silently overwriting the other's
  // change when built from the same stale snapshot.

  function toggleExtensionRule(ext, currentlyEnabled) {
    persist((current) => {
      const from = currentlyEnabled ? { ...current.extension_rules } : { ...current.disabled_extension_rules };
      const to = currentlyEnabled ? { ...current.disabled_extension_rules } : { ...current.extension_rules };
      to[ext] = from[ext];
      delete from[ext];
      return currentlyEnabled
        ? { ...current, extension_rules: from, disabled_extension_rules: to }
        : { ...current, disabled_extension_rules: from, extension_rules: to };
    });
  }

  function toggleKeywordRule(keyword, currentlyEnabled) {
    persist((current) => {
      const fromList = currentlyEnabled ? current.keyword_rules : current.disabled_keyword_rules || [];
      const toList = currentlyEnabled ? current.disabled_keyword_rules || [] : current.keyword_rules;
      const moved = fromList.find((r) => r.keyword === keyword);
      const nextFrom = fromList.filter((r) => r.keyword !== keyword);
      const nextTo = [...toList, moved];
      return {
        ...current,
        keyword_rules: currentlyEnabled ? nextFrom : nextTo,
        disabled_keyword_rules: currentlyEnabled ? nextTo : nextFrom,
      };
    });
  }

  function toggleLargeFileRule() {
    persist((current) => ({ ...current, large_file_enabled: !current.large_file_enabled }));
  }

  function toggleRegexRule(pattern, currentlyEnabled) {
    persist((current) => {
      const fromList = currentlyEnabled ? current.regex_rules || [] : current.disabled_regex_rules || [];
      const toList = currentlyEnabled ? current.disabled_regex_rules || [] : current.regex_rules || [];
      const moved = fromList.find((r) => r.pattern === pattern);
      const nextFrom = fromList.filter((r) => r.pattern !== pattern);
      const nextTo = [...toList, moved];
      return {
        ...current,
        regex_rules: currentlyEnabled ? nextFrom : nextTo,
        disabled_regex_rules: currentlyEnabled ? nextTo : nextFrom,
      };
    });
  }

  function toggleContentRule(keyword, currentlyEnabled) {
    persist((current) => {
      const fromList = currentlyEnabled
        ? current.content_keyword_rules || []
        : current.disabled_content_keyword_rules || [];
      const toList = currentlyEnabled
        ? current.disabled_content_keyword_rules || []
        : current.content_keyword_rules || [];
      const moved = fromList.find((r) => r.keyword === keyword);
      const nextFrom = fromList.filter((r) => r.keyword !== keyword);
      const nextTo = [...toList, moved];
      return {
        ...current,
        content_keyword_rules: currentlyEnabled ? nextFrom : nextTo,
        disabled_content_keyword_rules: currentlyEnabled ? nextTo : nextFrom,
      };
    });
  }

  function toggleDateRule(olderThanDays, currentlyEnabled) {
    // Keyed by the threshold value itself -- two date rules with the same
    // threshold would behave identically anyway, so there's nothing more
    // meaningful to key on than the value the card actually displays.
    persist((current) => {
      const fromList = currentlyEnabled ? current.date_rules || [] : current.disabled_date_rules || [];
      const toList = currentlyEnabled ? current.disabled_date_rules || [] : current.date_rules || [];
      const moved = fromList.find((r) => r.older_than_days === olderThanDays);
      const nextFrom = fromList.filter((r) => r.older_than_days !== olderThanDays);
      const nextTo = [...toList, moved];
      return {
        ...current,
        date_rules: currentlyEnabled ? nextFrom : nextTo,
        disabled_date_rules: currentlyEnabled ? nextTo : nextFrom,
      };
    });
  }

  function addCategory() {
    const name = newCategoryName.trim();
    if (!name || rules.categories[name]) return;
    persist((current) => ({ ...current, categories: { ...current.categories, [name]: [] } }));
    setNewCategoryName("");
  }

  function removeCategory(name) {
    const extensions = rules.categories[name] || [];
    if (extensions.length > 0) {
      setPendingRemoveCategory(name);
      return;
    }
    deleteCategory(name);
  }

  function deleteCategory(name) {
    persist((current) => {
      const next = { ...current.categories };
      delete next[name];
      return { ...current, categories: next };
    });
  }

  function addExtensionToCategory(category) {
    const raw = (newExtByCategory[category] || "").trim();
    if (!raw) return;
    const ext = raw.startsWith(".") ? raw.toLowerCase() : `.${raw.toLowerCase()}`;
    persist((current) => {
      const list = current.categories[category] || [];
      if (list.includes(ext)) return current;
      return { ...current, categories: { ...current.categories, [category]: [...list, ext] } };
    });
    setNewExtByCategory({ ...newExtByCategory, [category]: "" });
  }

  function removeExtensionFromCategory(category, ext) {
    persist((current) => ({
      ...current,
      categories: {
        ...current.categories,
        [category]: (current.categories[category] || []).filter((e) => e !== ext),
      },
    }));
  }

  function toggleTimestampCategory(folder) {
    persist((current) => {
      const list = current.timestamp_rename_categories || [];
      const next = list.includes(folder) ? list.filter((c) => c !== folder) : [...list, folder];
      return { ...current, timestamp_rename_categories: next };
    });
  }

  async function handleAddRule() {
    if (!form.match.trim() || !form.folder.trim()) return;
    if (form.type === "date" && (Number.isNaN(Number(form.match)) || Number(form.match) < 0)) return;
    if (addingRule) return;
    setAddingRule(true);
    captureFlip();
    try {
      let saved = false;
      if (form.type === "extension") {
        const ext = form.match.trim().startsWith(".") ? form.match.trim() : `.${form.match.trim()}`;
        saved = await persist((current) => ({
          ...current,
          extension_rules: { ...current.extension_rules, [ext]: form.folder.trim() },
        }));
      } else if (form.type === "keyword") {
        saved = await persist((current) => ({
          ...current,
          keyword_rules: [...current.keyword_rules, { keyword: form.match.trim(), folder: form.folder.trim() }],
        }));
      } else if (form.type === "regex") {
        saved = await persist((current) => ({
          ...current,
          regex_rules: [...(current.regex_rules || []), { pattern: form.match.trim(), folder: form.folder.trim() }],
        }));
      } else if (form.type === "content") {
        saved = await persist((current) => ({
          ...current,
          content_keyword_rules: [
            ...(current.content_keyword_rules || []),
            { keyword: form.match.trim(), folder: form.folder.trim() },
          ],
        }));
      } else if (form.type === "date") {
        saved = await persist((current) => ({
          ...current,
          date_rules: [
            ...(current.date_rules || []),
            { older_than_days: Number(form.match), folder: form.folder.trim() },
          ],
        }));
      }
      // Only clear the form on a confirmed save -- a rejected rule (e.g. an
      // invalid or ReDoS-shaped regex pattern the backend rejects) must
      // leave what the user typed in place so they can see and fix it,
      // not silently discard it alongside the generic "Failed to save".
      if (saved) setForm(emptyForm);
    } finally {
      setAddingRule(false);
    }
  }

  const extensionCards = [
    ...Object.entries(rules.extension_rules).map(([ext, folder]) => ({ ext, folder, enabled: true })),
    ...Object.entries(rules.disabled_extension_rules || {}).map(([ext, folder]) => ({
      ext,
      folder,
      enabled: false,
    })),
  ];
  const keywordCards = [
    ...rules.keyword_rules.map((r) => ({ ...r, enabled: true })),
    ...(rules.disabled_keyword_rules || []).map((r) => ({ ...r, enabled: false })),
  ];
  const regexCards = [
    ...(rules.regex_rules || []).map((r) => ({ ...r, enabled: true })),
    ...(rules.disabled_regex_rules || []).map((r) => ({ ...r, enabled: false })),
  ];
  const contentCards = [
    ...(rules.content_keyword_rules || []).map((r) => ({ ...r, enabled: true })),
    ...(rules.disabled_content_keyword_rules || []).map((r) => ({ ...r, enabled: false })),
  ];
  const dateCards = [
    ...(rules.date_rules || []).map((r) => ({ ...r, enabled: true })),
    ...(rules.disabled_date_rules || []).map((r) => ({ ...r, enabled: false })),
  ];

  return (
    <>
      <Header title="Automation rules" subtitle="Route files by extension, keyword or size" />
      <div className="flex items-center justify-end gap-2 px-8 pt-6">
        {importError && (
          <span className="text-xs" style={{ color: "var(--status-critical)" }}>
            {importError}
          </span>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="application/json"
          className="hidden"
          onChange={handleImportFile}
        />
        <button
          type="button"
          onClick={handleImportClick}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--gridline)]"
        >
          <Upload className="h-3.5 w-3.5" />
          Import
        </button>
        <button
          type="button"
          onClick={handleExportRules}
          className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--gridline)]"
        >
          <Download className="h-3.5 w-3.5" />
          Export
        </button>
        <button
          type="button"
          onClick={handleSimulate}
          disabled={simulating}
          title="See what your current rules would classify differently than what's on record"
          className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--gridline)] disabled:opacity-50"
        >
          <FlaskConical className="h-3.5 w-3.5" />
          {simulating ? "Checking…" : "Check impact"}
        </button>
      </div>

      {simulation && (
        <div className="mx-8 mt-4 rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 shadow-sm">
          {simulation.error ? (
            <p className="text-sm text-[var(--status-critical)]">Couldn't check rule impact. Try again.</p>
          ) : (
            <>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-medium text-[var(--text-primary)]">
                  {simulation.compared_count - simulation.unchanged_count === 0
                    ? `No changes — matches what's on record for the last ${simulation.compared_count} organized file${simulation.compared_count === 1 ? "" : "s"}.`
                    : `${simulation.compared_count - simulation.unchanged_count} of ${simulation.compared_count} recent files would be reclassified differently:`}
                </h3>
                <button
                  onClick={() => setSimulation(null)}
                  className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              {simulation.changes.length > 0 && (
                <div className="max-h-64 space-y-1.5 overflow-y-auto">
                  {simulation.changes.map((c, i) => (
                    <div
                      key={`${c.filename}-${i}`}
                      className="flex items-center justify-between rounded-lg bg-[var(--page)] px-3 py-2 text-xs"
                    >
                      <span className="truncate font-medium text-[var(--text-primary)]">{c.filename}</span>
                      <span className="shrink-0 text-[var(--text-secondary)]">
                        {c.previous_category} → <span className="font-medium">{c.new_category}</span>
                      </span>
                    </div>
                  ))}
                  {simulation.compared_count - simulation.unchanged_count > simulation.changes.length && (
                    <p className="pt-1 text-center text-xs text-[var(--text-muted)]">
                      Showing the first {simulation.changes.length} changes.
                    </p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 p-8 lg:grid-cols-[1fr_320px]">
        <div ref={cardsRef} className="space-y-3">
          {extensionCards.map(({ ext, folder, enabled }) => (
            <RuleCard
              key={ext}
              type="extension"
              condition={ext}
              folder={folder}
              color={colorMap[folder]}
              enabled={enabled}
              onToggle={() => {
                captureFlip();
                toggleExtensionRule(ext, enabled);
              }}
            />
          ))}
          {keywordCards.map(({ keyword, folder, enabled }) => (
            <RuleCard
              key={keyword}
              type="keyword"
              condition={keyword}
              folder={folder}
              color={colorMap[folder]}
              enabled={enabled}
              onToggle={() => {
                captureFlip();
                toggleKeywordRule(keyword, enabled);
              }}
            />
          ))}
          {regexCards.map(({ pattern, folder, enabled }) => (
            <RuleCard
              key={pattern}
              type="regex"
              condition={pattern}
              folder={folder}
              color={colorMap[folder]}
              enabled={enabled}
              onToggle={() => {
                captureFlip();
                toggleRegexRule(pattern, enabled);
              }}
            />
          ))}
          {contentCards.map(({ keyword, folder, enabled }) => (
            <RuleCard
              key={`content-${keyword}`}
              type="content"
              condition={keyword}
              folder={folder}
              color={colorMap[folder]}
              enabled={enabled}
              onToggle={() => {
                captureFlip();
                toggleContentRule(keyword, enabled);
              }}
            />
          ))}
          {dateCards.map(({ older_than_days, folder, enabled }) => (
            <RuleCard
              key={`date-${older_than_days}`}
              type="date"
              condition={`> ${older_than_days} days old`}
              folder={folder}
              color={colorMap[folder]}
              enabled={enabled}
              onToggle={() => {
                captureFlip();
                toggleDateRule(older_than_days, enabled);
              }}
            />
          ))}
          <RuleCard
            type="size"
            condition={`> ${rules.large_file_threshold_mb || 500} MB`}
            folder={rules.large_file_folder}
            color={colorMap[rules.large_file_folder]}
            enabled={rules.large_file_enabled}
            onToggle={toggleLargeFileRule}
          />

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 shadow-sm">
            <h2 className="mb-1 text-sm font-medium text-[var(--text-primary)]">
              Unrecognized file types
            </h2>
            <p className="mb-3 text-xs text-[var(--text-muted)]">
              When a file's extension doesn't match any rule above, put it in
              its own folder named after the extension instead of a generic
              "Others" bucket.
            </p>
            <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={rules.auto_organize_unknown_extensions}
                onChange={(e) => {
                  const checked = e.target.checked;
                  persist((current) => ({ ...current, auto_organize_unknown_extensions: checked }));
                }}
              />
              Auto-create a folder for unrecognized extensions
            </label>
            <label className="mt-2 flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={rules.enable_timestamp_rename}
                onChange={(e) => {
                  const checked = e.target.checked;
                  persist((current) => ({ ...current, enable_timestamp_rename: checked }));
                }}
              />
              Rename with a timestamp prefix
            </label>
            {rules.enable_timestamp_rename && (
              <div className="mt-2 flex flex-wrap gap-1.5 border-t border-[var(--border)] pt-2">
                {allFolders.length === 0 && (
                  <span className="text-xs text-[var(--text-muted)]">
                    No destination folders yet.
                  </span>
                )}
                {allFolders.map((folder) => {
                  const active = (rules.timestamp_rename_categories || []).includes(folder);
                  return (
                    <button
                      key={folder}
                      type="button"
                      onClick={() => toggleTimestampCategory(folder)}
                      className="rounded-full px-2.5 py-1 text-xs font-medium"
                      style={
                        active
                          ? {
                              background: "var(--brand)",
                              color: "var(--brand-foreground)",
                            }
                          : {
                              border: "1px solid var(--border)",
                              color: "var(--text-secondary)",
                            }
                      }
                    >
                      {folder}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-4 shadow-sm">
            <h2 className="mb-1 text-sm font-medium text-[var(--text-primary)]">
              Category mapping
            </h2>
            <p className="mb-3 text-xs text-[var(--text-muted)]">
              Fallback used when a file's extension doesn't match any rule
              above — maps extensions to a category folder.
            </p>
            <div className="space-y-3">
              {Object.entries(rules.categories || {}).map(([category, extensions]) => (
                <div
                  key={category}
                  className="rounded-lg border border-[var(--border)] p-3"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <span
                      className="text-sm font-medium"
                      style={{ color: colorMap[category] }}
                    >
                      {category}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeCategory(category)}
                      aria-label={`Remove ${category} category`}
                      className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                    >
                      <X width={14} height={14} />
                    </button>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    {extensions.map((ext) => (
                      <span
                        key={ext}
                        className="flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
                        style={{
                          color: colorMap[category],
                          background: `color-mix(in srgb, ${colorMap[category]} 14%, transparent)`,
                        }}
                      >
                        {ext}
                        <button
                          type="button"
                          onClick={() => removeExtensionFromCategory(category, ext)}
                          aria-label={`Remove ${ext} from ${category}`}
                        >
                          <X width={10} height={10} />
                        </button>
                      </span>
                    ))}
                    <input
                      value={newExtByCategory[category] || ""}
                      onChange={(e) =>
                        setNewExtByCategory({ ...newExtByCategory, [category]: e.target.value })
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") addExtensionToCategory(category);
                      }}
                      placeholder=".ext"
                      className="w-16 rounded-md border border-[var(--border)] bg-[var(--page)] px-2 py-1 text-xs text-[var(--text-primary)]"
                    />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex gap-2">
              <input
                value={newCategoryName}
                onChange={(e) => setNewCategoryName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") addCategory();
                }}
                placeholder="New category name"
                className={`${inputClass} flex-1`}
              />
              <button
                type="button"
                onClick={addCategory}
                className="rounded-md border border-[var(--border)] px-3 py-1.5 text-sm font-medium text-[var(--text-primary)] hover:bg-[var(--gridline)]"
              >
                Add
              </button>
            </div>
          </div>
        </div>

        <div className="h-fit rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">New rule</h2>
          <p className="mb-4 text-xs text-[var(--text-muted)]">
            Route files automatically by type or keyword.
          </p>

          <label className="mb-3 block text-sm text-[var(--text-secondary)]">
            Condition type
            <select
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
              className={`${inputClass} mt-1 w-full`}
            >
              <option value="extension">Extension</option>
              <option value="keyword">Keyword</option>
              <option value="regex">Regex</option>
              <option value="content">Content keyword</option>
              <option value="date">Age</option>
            </select>
          </label>

          <label className="mb-3 block text-sm text-[var(--text-secondary)]">
            {
              {
                extension: "Match",
                keyword: "Match",
                regex: "Regex pattern",
                content: "Keyword to find inside the file",
                date: "Older than (days)",
              }[form.type]
            }
            <input
              type={form.type === "date" ? "number" : "text"}
              min={form.type === "date" ? 0 : undefined}
              value={form.match}
              onChange={(e) => setForm({ ...form, match: e.target.value })}
              placeholder={
                {
                  extension: ".psd / Invoice / 500MB",
                  keyword: ".psd / Invoice / 500MB",
                  regex: "^IMG_\\d+",
                  content: "confidential",
                  date: "90",
                }[form.type]
              }
              className={`${inputClass} mt-1 w-full`}
            />
          </label>

          <label className="mb-4 block text-sm text-[var(--text-secondary)]">
            Destination folder
            <input
              value={form.folder}
              onChange={(e) => setForm({ ...form, folder: e.target.value })}
              placeholder="Design Assets"
              className={`${inputClass} mt-1 w-full`}
            />
          </label>

          {form.match.trim() && (
            <div className="mb-4 rounded-lg border border-[var(--border)] bg-[var(--page)] p-3 text-xs">
              {previewLoading ? (
                <span className="text-[var(--text-muted)]">Checking existing files…</span>
              ) : preview && preview.matched_count > 0 ? (
                <>
                  <span className="font-medium text-[var(--text-primary)]">
                    Would have matched {preview.matched_count} file
                    {preview.matched_count === 1 ? "" : "s"} you've already organized
                  </span>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {preview.by_category.map((row) => {
                      const color = colorMap[row.category] || "var(--series-1)";
                      return (
                        <span
                          key={row.category}
                          className="rounded-full px-2 py-0.5 font-medium"
                          style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}
                        >
                          currently in {row.category} ({row.count})
                        </span>
                      );
                    })}
                  </div>
                </>
              ) : (
                <span className="text-[var(--text-muted)]">
                  No previously organized files match this yet.
                </span>
              )}
            </div>
          )}

          <button
            onClick={handleAddRule}
            disabled={addingRule}
            className="w-full rounded-lg bg-[var(--brand)] py-2.5 text-sm font-medium text-[var(--brand-foreground)] hover:opacity-90 disabled:opacity-50"
          >
            {addingRule ? "Adding…" : "Add rule"}
          </button>
          {status && (
            <p className="mt-3 text-center text-xs text-[var(--text-muted)]">{status}</p>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={pendingRemoveCategory !== null}
        onOpenChange={(open) => !open && setPendingRemoveCategory(null)}
        title={`Remove "${pendingRemoveCategory}"?`}
        description={
          pendingRemoveCategory
            ? `"${pendingRemoveCategory}" still maps ${(rules.categories[pendingRemoveCategory] || []).length} extension(s) (${(rules.categories[pendingRemoveCategory] || []).join(", ")}). Remove the category anyway?`
            : ""
        }
        confirmLabel="Remove category"
        variant="destructive"
        onConfirm={() => {
          deleteCategory(pendingRemoveCategory);
          setPendingRemoveCategory(null);
        }}
      />

      <ConfirmDialog
        open={pendingImport !== null}
        onOpenChange={(open) => !open && setPendingImport(null)}
        title="Replace all rules?"
        description="Importing this file replaces every category, extension, keyword, and automation setting with what's in it. This can't be undone -- export your current rules first if you want to keep them."
        confirmLabel="Replace rules"
        variant="destructive"
        onConfirm={confirmImport}
      />
    </>
  );
}
