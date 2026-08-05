import { useEffect, useMemo, useState } from "react";
import Header from "../components/Header.jsx";
import { Folder, Pencil, Ruler, X } from "lucide-react";
import { buildCategoryColorMap, collectKnownFolders } from "../utils/categoryMeta.js";
import { previewRule } from "../services/api.js";
import { useRules } from "../context/RulesContext.jsx";

const inputClass =
  "rounded-md border border-[var(--border)] bg-[var(--page)] px-2.5 py-1.5 text-sm text-[var(--text-primary)]";

const TYPE_META = {
  extension: { label: "EXTENSION", Icon: Folder },
  keyword: { label: "KEYWORD", Icon: Pencil },
  size: { label: "SIZE", Icon: Ruler },
};

function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      onClick={onChange}
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

function RuleCard({ type, condition, folder, color, enabled, onToggle }) {
  const { label, Icon } = TYPE_META[type];
  return (
    <div
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

  // Debounced dry-run: shows which already-organized files this not-yet-
  // saved rule would have matched, so a typo (e.g. "invoic") is obvious
  // before it's saved rather than discovered days later.
  useEffect(() => {
    const match = form.match.trim();
    if (!match) {
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
      rules.large_file_folder,
      ...Object.keys(rules.categories || {}),
    ];
    return buildCategoryColorMap(folders);
  }, [rules]);

  const allFolders = useMemo(() => collectKnownFolders(rules), [rules]);

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
    } catch {
      setStatus("Failed to save");
    }
  }

  function toggleExtensionRule(ext, currentlyEnabled) {
    const next = { ...rules };
    const from = currentlyEnabled ? { ...rules.extension_rules } : { ...rules.disabled_extension_rules };
    const to = currentlyEnabled ? { ...rules.disabled_extension_rules } : { ...rules.extension_rules };
    to[ext] = from[ext];
    delete from[ext];
    if (currentlyEnabled) {
      next.extension_rules = from;
      next.disabled_extension_rules = to;
    } else {
      next.disabled_extension_rules = from;
      next.extension_rules = to;
    }
    persist(next);
  }

  function toggleKeywordRule(keyword, currentlyEnabled) {
    const fromList = currentlyEnabled ? rules.keyword_rules : rules.disabled_keyword_rules || [];
    const toList = currentlyEnabled ? rules.disabled_keyword_rules || [] : rules.keyword_rules;
    const moved = fromList.find((r) => r.keyword === keyword);
    const nextFrom = fromList.filter((r) => r.keyword !== keyword);
    const nextTo = [...toList, moved];
    persist({
      ...rules,
      keyword_rules: currentlyEnabled ? nextFrom : nextTo,
      disabled_keyword_rules: currentlyEnabled ? nextTo : nextFrom,
    });
  }

  function toggleLargeFileRule() {
    persist({ ...rules, large_file_enabled: !rules.large_file_enabled });
  }

  function addCategory() {
    const name = newCategoryName.trim();
    if (!name || rules.categories[name]) return;
    persist({ ...rules, categories: { ...rules.categories, [name]: [] } });
    setNewCategoryName("");
  }

  function removeCategory(name) {
    const extensions = rules.categories[name] || [];
    if (extensions.length > 0) {
      const confirmed = window.confirm(
        `"${name}" still maps ${extensions.length} extension(s) (${extensions.join(", ")}). Remove the category anyway?`,
      );
      if (!confirmed) return;
    }
    const next = { ...rules.categories };
    delete next[name];
    persist({ ...rules, categories: next });
  }

  function addExtensionToCategory(category) {
    const raw = (newExtByCategory[category] || "").trim();
    if (!raw) return;
    const ext = raw.startsWith(".") ? raw.toLowerCase() : `.${raw.toLowerCase()}`;
    const current = rules.categories[category] || [];
    if (current.includes(ext)) return;
    persist({
      ...rules,
      categories: { ...rules.categories, [category]: [...current, ext] },
    });
    setNewExtByCategory({ ...newExtByCategory, [category]: "" });
  }

  function removeExtensionFromCategory(category, ext) {
    persist({
      ...rules,
      categories: {
        ...rules.categories,
        [category]: (rules.categories[category] || []).filter((e) => e !== ext),
      },
    });
  }

  function toggleTimestampCategory(folder) {
    const current = rules.timestamp_rename_categories || [];
    const next = current.includes(folder)
      ? current.filter((c) => c !== folder)
      : [...current, folder];
    persist({ ...rules, timestamp_rename_categories: next });
  }

  async function handleAddRule() {
    if (!form.match.trim() || !form.folder.trim()) return;
    if (form.type === "extension") {
      const ext = form.match.trim().startsWith(".") ? form.match.trim() : `.${form.match.trim()}`;
      await persist({
        ...rules,
        extension_rules: { ...rules.extension_rules, [ext]: form.folder.trim() },
      });
    } else {
      await persist({
        ...rules,
        keyword_rules: [...rules.keyword_rules, { keyword: form.match.trim(), folder: form.folder.trim() }],
      });
    }
    setForm(emptyForm);
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

  return (
    <>
      <Header title="Automation rules" subtitle="Route files by extension, keyword or size" />
      <div className="grid grid-cols-1 gap-6 p-8 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          {extensionCards.map(({ ext, folder, enabled }) => (
            <RuleCard
              key={ext}
              type="extension"
              condition={ext}
              folder={folder}
              color={colorMap[folder]}
              enabled={enabled}
              onToggle={() => toggleExtensionRule(ext, enabled)}
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
              onToggle={() => toggleKeywordRule(keyword, enabled)}
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
                onChange={(e) =>
                  persist({ ...rules, auto_organize_unknown_extensions: e.target.checked })
                }
              />
              Auto-create a folder for unrecognized extensions
            </label>
            <label className="mt-2 flex items-center gap-2 text-sm text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={rules.enable_timestamp_rename}
                onChange={(e) =>
                  persist({ ...rules, enable_timestamp_rename: e.target.checked })
                }
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
                              background: "var(--series-1)",
                              color: "white",
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
            </select>
          </label>

          <label className="mb-3 block text-sm text-[var(--text-secondary)]">
            Match
            <input
              value={form.match}
              onChange={(e) => setForm({ ...form, match: e.target.value })}
              placeholder=".psd / Invoice / 500MB"
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
                    {preview.by_category.map((row) => (
                      <span
                        key={row.category}
                        className="rounded-full px-2 py-0.5 text-[var(--text-secondary)]"
                        style={{ background: "var(--gridline)" }}
                      >
                        currently in {row.category} ({row.count})
                      </span>
                    ))}
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
            className="w-full rounded-lg bg-[var(--series-1)] py-2.5 text-sm font-medium text-white hover:opacity-90"
          >
            Add rule
          </button>
          {status && (
            <p className="mt-3 text-center text-xs text-[var(--text-muted)]">{status}</p>
          )}
        </div>
      </div>
    </>
  );
}
