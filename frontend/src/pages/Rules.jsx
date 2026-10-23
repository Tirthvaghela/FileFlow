import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pencil, X } from "lucide-react";
import PageHeading from "../components/PageHeading.jsx";
import Kicker from "../components/Kicker.jsx";
import PrecedenceTester from "../components/PrecedenceTester.jsx";
import ConfirmDialog from "../components/ui/ConfirmDialog.jsx";
import Toggle from "../components/ui/Toggle.jsx";
import Stamp from "../components/ui/Stamp.jsx";
import FolderTag from "../components/ui/FolderTag.jsx";
import AIRuleGeneratorDialog from "../components/ui/AIRuleGeneratorDialog.jsx";
import RuleConflictCard from "../components/ui/RuleConflictCard.jsx";
import RuleConflictWarningDialog from "../components/ui/RuleConflictWarningDialog.jsx";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "../components/ui/dialog.jsx";
import { collectKnownFolders } from "../utils/categoryMeta.js";
import { applyRuleToDoc, FORM_TYPE_TO_RULE_TYPE, proposalFields } from "../utils/ruleForm.js";
import { groupLogsByTier, ORGANIZED_ACTIONS, pad2, RULE_TIERS } from "../utils/ruleTiers.js";
import { checkRuleConflicts, generateAIRule, getLogs, previewRule, simulateRules } from "../services/api.js";
import { useRules } from "../context/RulesContext.jsx";

const emptyForm = { type: "extension", match: "", folder: "" };

const FORM_TIER = { keyword: 1, regex: 2, content: 3, extension: 4, date: 6 };
const TIER_FORM = { 1: "keyword", 2: "regex", 3: "content", 4: "extension", 6: "date" };

const MATCH_LABEL = {
  extension: "Match",
  keyword: "Match",
  regex: "Regex pattern",
  content: "Keyword to find inside the file",
  date: "Older than (days)",
};
const MATCH_PLACEHOLDER = {
  extension: ".psd",
  keyword: "invoice",
  regex: "^IMG_\\d+",
  content: "confidential",
  date: "90",
};

// Mirrors services/rule_conflict_service.py _describe(), so a card can be
// matched against the rules a conflict check names.
function describe(type, value) {
  if (type === "keyword") return `Keyword "${value}"`;
  if (type === "content") return `File content contains "${value}"`;
  if (type === "regex") return `Regex pattern "${value}"`;
  if (type === "extension") return `Extension "${value}"`;
  if (type === "size") return `Large file (over ${value} MB)`;
  return `File age (over ${value} days old)`;
}

const SEVERITY_TONE = { high: "high", warning: "warn", info: "muted" };

function IndexCard({ card, conflict, onToggle, onEdit, onOpenConflict, maxWeek }) {
  return (
    <div
      className="ff-in flex flex-col gap-2.5 rounded-[4px] border border-[var(--rule-2)] px-3.5 py-3 transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[0_10px_18px_-12px_var(--shade)]"
      style={{
        backgroundColor: "var(--sheet)",
        backgroundImage: "linear-gradient(var(--stamp), var(--stamp))",
        backgroundSize: "100% 1px",
        backgroundPosition: "0 40px",
        backgroundRepeat: "no-repeat",
        boxShadow: "0 2px 0 var(--rule)",
        transitionDuration: "var(--d2)",
      }}
    >
      <div className="flex h-5 items-center gap-2">
        <span className="font-mono-data text-[10.5px] font-semibold text-[var(--ink-muted)]">T{pad2(card.tier)}</span>
        {conflict && (
          <Stamp as="button" type="button" tone={SEVERITY_TONE[conflict.severity] || "warn"} pop onClick={onOpenConflict} title="See conflict" className="cursor-pointer">
            {conflict.severity === "high" ? "Shadowed" : "Overlap"}
          </Stamp>
        )}
        {!card.enabled && <span className="ff-kicker text-[9.5px]">Off</span>}
        <span className="ml-auto flex items-center gap-1.5">
          {onEdit && (
            <button
              type="button"
              onClick={onEdit}
              aria-label={`Edit rule ${card.cond}`}
              className="grid h-6 w-6 cursor-pointer place-items-center rounded-[3px] border border-transparent bg-transparent text-[var(--ink-muted)] hover:border-[var(--rule-2)] hover:text-[var(--ink)]"
            >
              <Pencil width={12} height={12} />
            </button>
          )}
          <Toggle size="sm" checked={card.enabled} onChange={onToggle} label={`Enable rule ${card.cond}`} />
        </span>
      </div>
      <code className="mt-1 font-mono-data text-[15px] font-semibold" style={{ overflowWrap: "anywhere" }}>
        {card.cond}
      </code>
      <div className="min-w-0 leading-[1.7]">
        <span className="mr-1.5 text-[var(--stamp)]">→</span>
        <FolderTag>{card.folder}</FolderTag>
      </div>
      <div className="flex items-center gap-2">
        <span aria-hidden="true" className="h-1 flex-1 overflow-hidden rounded-[2px] bg-[var(--rule)]">
          <span className="block h-full bg-[var(--ink)]" style={{ width: `${maxWeek ? (card.week / maxWeek) * 100 : 0}%` }} />
        </span>
        <span className="whitespace-nowrap font-mono-data text-[11px] text-[var(--ink-muted)]">{card.week} this week</span>
      </div>
    </div>
  );
}

function AddCard({ label, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-h-[130px] cursor-pointer flex-col items-center justify-center gap-1.5 rounded-[4px] border-[1.5px] border-dashed border-[var(--rule-2)] bg-transparent text-[12.5px] font-semibold text-[var(--ink-muted)] transition-colors hover:border-[var(--ink)] hover:text-[var(--ink)]"
    >
      <span aria-hidden="true" className="text-[24px] leading-none">
        +
      </span>
      Add a {label} rule
    </button>
  );
}

function TierHeader({ tier, meta }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b-[1.5px] border-[var(--ink)] pb-2">
      <span className="font-mono-data text-[28px] font-bold leading-none tracking-[-0.04em]">{pad2(tier.n)}</span>
      <b className="ff-caps text-[15px]">{tier.label}</b>
      <span className="text-[12.5px] text-[var(--ink-muted)]">{tier.desc}</span>
      <span className="ml-auto font-mono-data text-[11.5px] text-[var(--ink-muted)]">{meta}</span>
    </div>
  );
}

export default function Rules() {
  const { rules, saveRules } = useRules();
  const navigate = useNavigate();
  const [status, setStatus] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [formOpen, setFormOpen] = useState(false);
  const [formError, setFormError] = useState("");
  const [editing, setEditing] = useState(null);
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
  const [query, setQuery] = useState("");
  const [selTier, setSelTier] = useState(null);
  const [logs, setLogs] = useState([]);
  const [conflictDialog, setConflictDialog] = useState(false);
  const fileInputRef = useRef(null);
  const formRef = useRef(null);

  const [conflictCheck, setConflictCheck] = useState(null);
  const [checkingConflicts, setCheckingConflicts] = useState(false);
  // { conflicts, onSaveAnyway } while the pre-save warning dialog is open.
  // onSaveAnyway calls the exact same save path the gated action would
  // have used directly; there is no separate "save with conflict" path.
  const [pendingConflict, setPendingConflict] = useState(null);
  const [conflictSaving, setConflictSaving] = useState(false);

  const [aiOpen, setAiOpen] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiGenerating, setAiGenerating] = useState(false);
  const [aiResult, setAiResult] = useState(null);
  const [aiError, setAiError] = useState("");
  const [aiSaving, setAiSaving] = useState(false);
  const [aiImpact, setAiImpact] = useState(null);
  const [aiCheckingImpact, setAiCheckingImpact] = useState(false);

  // Files caught this week, per tier and per rule -- read from the match
  // type/value the classifier already stores with every activity-log row.
  useEffect(() => {
    getLogs(500)
      .then((l) => setLogs(Array.isArray(l) ? l : []))
      .catch(() => {});
  }, []);

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

  async function handleCheckConflicts() {
    setCheckingConflicts(true);
    try {
      const result = await checkRuleConflicts();
      setConflictCheck(result);
    } catch {
      setConflictCheck({ error: true });
    } finally {
      setCheckingConflicts(false);
    }
  }

  // Advisory only, and best-effort: a failed conflict check must never
  // block saving a rule (the deterministic RuleEngine remains authoritative).
  async function conflictsFor(baseRules, ruleType, fields) {
    try {
      const candidate = applyRuleToDoc(baseRules, ruleType, fields);
      const result = await checkRuleConflicts(candidate);
      return (result.conflicts || []).filter((c) => c.severity !== "info");
    } catch {
      return [];
    }
  }

  async function handleConflictSaveAnyway() {
    if (!pendingConflict || conflictSaving) return;
    setConflictSaving(true);
    try {
      await pendingConflict.onSaveAnyway();
    } finally {
      setConflictSaving(false);
      setPendingConflict(null);
    }
  }

  function handleConflictBack() {
    setPendingConflict(null);
  }

  // Debounced dry-run: shows which already-organized files this not-yet-
  // saved rule would have matched, so a typo is obvious before saving.
  // Content/date can't be previewed from recorded filenames, so they skip.
  useEffect(() => {
    const match = form.match.trim();
    if (!formOpen || !match || form.type === "date" || form.type === "content") {
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
  }, [form.type, form.match, formOpen]);

  const allFolders = useMemo(() => collectKnownFolders(rules), [rules]);

  const weekLogs = useMemo(() => {
    const since = Date.now() - 7 * 24 * 60 * 60 * 1000;
    return logs.filter(
      (l) => !l.undone && ORGANIZED_ACTIONS.has(l.action) && l.explanation && new Date(l.timestamp).getTime() >= since,
    );
  }, [logs]);
  const tierWeek = useMemo(() => groupLogsByTier(weekLogs), [weekLogs]);

  function weekFor(matchType, value) {
    return weekLogs.filter((l) => l.explanation.match_type === matchType && String(l.explanation.matched_value) === String(value))
      .length;
  }

  if (!rules) {
    return (
      <>
        <PageHeading index={4} kicker="Sorting rules" title="Rules" subtitle="Checked top to bottom. The first match decides the folder." />
        <div className="text-sm text-[var(--ink-muted)]">Loading…</div>
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
    // Entirely client-side -- `rules` is already the full document.
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
        setPendingImport(JSON.parse(reader.result));
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
      setStatus("Failed to save");
      setImportError(
        err?.response?.status === 422 ? "That file isn't a valid FileFlow rules export." : "Couldn't import that file.",
      );
    }
  }

  // Every mutation passes an updater -- `(current) => next` -- so queued
  // saves each apply on top of whatever the previous one landed as.

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

  function toggleListRule(enabledKey, disabledKey, field, value, currentlyEnabled) {
    persist((current) => {
      const fromList = currentlyEnabled ? current[enabledKey] || [] : current[disabledKey] || [];
      const toList = currentlyEnabled ? current[disabledKey] || [] : current[enabledKey] || [];
      const moved = fromList.find((r) => r[field] === value);
      const nextFrom = fromList.filter((r) => r[field] !== value);
      const nextTo = [...toList, moved];
      return {
        ...current,
        [enabledKey]: currentlyEnabled ? nextFrom : nextTo,
        [disabledKey]: currentlyEnabled ? nextTo : nextFrom,
      };
    });
  }

  function toggleLargeFileRule() {
    persist((current) => ({ ...current, large_file_enabled: !current.large_file_enabled }));
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

  // Removes the rule being edited (from whichever enabled/disabled list
  // holds it) before the edited version is applied in its place.
  function withoutEdited(current) {
    if (!editing) return current;
    const { type, value, enabled } = editing;
    if (type === "extension") {
      const key = enabled ? "extension_rules" : "disabled_extension_rules";
      const next = { ...(current[key] || {}) };
      delete next[value];
      return { ...current, [key]: next };
    }
    const lists = {
      keyword: ["keyword_rules", "disabled_keyword_rules", "keyword"],
      regex: ["regex_rules", "disabled_regex_rules", "pattern"],
      content: ["content_keyword_rules", "disabled_content_keyword_rules", "keyword"],
      date: ["date_rules", "disabled_date_rules", "older_than_days"],
    }[type];
    if (!lists) return current;
    const key = enabled ? lists[0] : lists[1];
    const list = current[key] || [];
    const idx = list.findIndex((r) => r[lists[2]] === value);
    if (idx < 0) return current;
    return { ...current, [key]: [...list.slice(0, idx), ...list.slice(idx + 1)] };
  }

  function openForm(type = form.type, preset = null) {
    setFormError("");
    setEditing(preset?.editing ?? null);
    setForm(preset?.form ?? { ...emptyForm, type });
    setFormOpen(true);
    setTimeout(() => formRef.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" }), 0);
  }

  function closeForm() {
    setFormOpen(false);
    setFormError("");
    setEditing(null);
    setForm(emptyForm);
  }

  async function commitManualRule(ruleType, fields) {
    const saved = await persist((current) => applyRuleToDoc(withoutEdited(current), ruleType, fields));
    // Only close/clear on a confirmed save -- a rejected rule must leave
    // what the user typed in place so they can see and fix it.
    if (saved) closeForm();
    return saved;
  }

  async function handleAddRule(e) {
    e?.preventDefault?.();
    if (!form.match.trim()) {
      setFormError(`Enter ${MATCH_LABEL[form.type].toLowerCase()}.`);
      return;
    }
    if (!form.folder.trim()) {
      setFormError("Enter a destination folder.");
      return;
    }
    if (form.type === "date" && (Number.isNaN(Number(form.match)) || Number(form.match) < 0)) {
      setFormError("Age must be a whole number of days.");
      return;
    }
    if (addingRule) return;
    setFormError("");
    setAddingRule(true);
    try {
      const ruleType = FORM_TYPE_TO_RULE_TYPE[form.type];
      const fields = {
        keyword: form.match.trim(),
        pattern: form.match.trim(),
        olderThanDays: Number(form.match),
        destination: form.folder.trim(),
      };
      const conflicts = await conflictsFor(withoutEdited(rules), ruleType, fields);
      if (conflicts.length > 0) {
        setPendingConflict({ conflicts, onSaveAnyway: () => commitManualRule(ruleType, fields) });
        return;
      }
      await commitManualRule(ruleType, fields);
    } finally {
      setAddingRule(false);
    }
  }

  function resetAIState() {
    setAiPrompt("");
    setAiResult(null);
    setAiError("");
    setAiImpact(null);
  }

  function handleOpenAIDialog() {
    resetAIState();
    setAiOpen(true);
  }

  async function handleGenerateRule() {
    if (aiGenerating || !aiPrompt.trim()) return;
    setAiGenerating(true);
    setAiError("");
    setAiResult(null);
    setAiImpact(null);
    try {
      setAiResult(await generateAIRule(aiPrompt.trim()));
    } catch {
      setAiError("Couldn't reach the AI service. Try again.");
    } finally {
      setAiGenerating(false);
    }
  }

  function handleEditRequest() {
    setAiResult(null);
    setAiError("");
    setAiImpact(null);
  }

  function handleRejectAI() {
    setAiOpen(false);
    resetAIState();
  }

  async function handleCheckAIImpact() {
    if (!aiResult?.proposal || aiCheckingImpact) return;
    setAiCheckingImpact(true);
    try {
      const candidate = applyRuleToDoc(rules, aiResult.proposal.rule_type, proposalFields(aiResult.proposal));
      setAiImpact(await simulateRules(candidate));
    } catch {
      setAiImpact({ error: true });
    } finally {
      setAiCheckingImpact(false);
    }
  }

  // Folds the proposal into the manual "New rule" form -- the user still
  // has to press Save rule. large_file has no form (singleton toggle), so
  // editing it is the same as applying it directly.
  function handleEditAIProposal(proposal) {
    if (proposal.rule_type === "large_file") {
      handleSaveAIProposal(proposal);
      return;
    }
    const formType = Object.entries(FORM_TYPE_TO_RULE_TYPE).find(([, rt]) => rt === proposal.rule_type)?.[0] || "keyword";
    openForm(formType, {
      form: {
        type: formType,
        match:
          proposal.rule_type === "regex"
            ? proposal.pattern || ""
            : proposal.rule_type === "date"
              ? String(proposal.older_than_days ?? "")
              : proposal.keyword || "",
        folder: proposal.destination || "",
      },
    });
    setAiOpen(false);
    resetAIState();
  }

  async function commitAIProposal(proposal) {
    const saved = await persist((current) => applyRuleToDoc(current, proposal.rule_type, proposalFields(proposal)));
    if (saved) {
      setAiOpen(false);
      resetAIState();
    }
    return saved;
  }

  async function handleSaveAIProposal(proposal) {
    if (aiSaving) return;
    setAiSaving(true);
    try {
      const conflicts = await conflictsFor(rules, proposal.rule_type, proposalFields(proposal));
      if (conflicts.length > 0) {
        setPendingConflict({ conflicts, onSaveAnyway: () => commitAIProposal(proposal) });
        return;
      }
      await commitAIProposal(proposal);
    } finally {
      setAiSaving(false);
    }
  }

  // ----- card data -----
  const listCards = (enabledKey, disabledKey, field, type, tier, matchType, label = (v) => v) => [
    ...(rules[enabledKey] || []).map((r) => ({ ...r, enabled: true })),
    ...(rules[disabledKey] || []).map((r) => ({ ...r, enabled: false })),
  ].map((r, i) => ({
    key: `${type}-${r[field]}-${i}`,
    type,
    tier,
    value: r[field],
    cond: label(r[field]),
    folder: r.folder,
    enabled: r.enabled,
    desc: describe(type, r[field]),
    week: weekFor(matchType, matchType === "date" ? `> ${r[field]} days old` : r[field]),
    onToggle: () => toggleListRule(enabledKey, disabledKey, field, r[field], r.enabled),
  }));

  const cardsByTier = {
    1: listCards("keyword_rules", "disabled_keyword_rules", "keyword", "keyword", 1, "keyword", (v) => `"${v}"`),
    2: listCards("regex_rules", "disabled_regex_rules", "pattern", "regex", 2, "regex"),
    3: listCards("content_keyword_rules", "disabled_content_keyword_rules", "keyword", "content", 3, "content_keyword", (v) => `"${v}"`),
    4: [
      ...Object.entries(rules.extension_rules || {}).map(([ext, folder]) => ({ ext, folder, enabled: true })),
      ...Object.entries(rules.disabled_extension_rules || {}).map(([ext, folder]) => ({ ext, folder, enabled: false })),
    ].map((r) => ({
      key: `ext-${r.ext}`,
      type: "extension",
      tier: 4,
      value: r.ext,
      cond: r.ext,
      folder: r.folder,
      enabled: r.enabled,
      desc: describe("extension", r.ext),
      week: weekFor("extension", r.ext),
      onToggle: () => toggleExtensionRule(r.ext, r.enabled),
    })),
    5: [
      {
        key: "size",
        type: "size",
        tier: 5,
        value: rules.large_file_threshold_mb || 500,
        cond: `> ${rules.large_file_threshold_mb || 500} MB`,
        folder: rules.large_file_folder,
        enabled: !!rules.large_file_enabled,
        desc: describe("size", rules.large_file_threshold_mb || 500),
        week: tierWeek.find((t) => t.n === 5)?.count ?? 0,
        onToggle: toggleLargeFileRule,
        noEdit: true,
      },
    ],
    6: listCards("date_rules", "disabled_date_rules", "older_than_days", "date", 6, "date", (v) => `> ${v} days old`),
  };

  const q = query.trim().toLowerCase();
  const matchesQuery = (c) => !q || String(c.value).toLowerCase().includes(q) || (c.folder || "").toLowerCase().includes(q);

  const conflicts = conflictCheck && !conflictCheck.error ? conflictCheck.conflicts || [] : [];
  function conflictFor(card) {
    return conflicts.find((c) => c.rules.some((r) => r.description === card.desc)) || null;
  }

  const categoryEntries = Object.entries(rules.categories || {}).filter(
    ([name, exts]) => !q || name.toLowerCase().includes(q) || exts.some((e) => e.toLowerCase().includes(q)),
  );
  const tierCount = (n) => {
    if (n <= 6) return String(cardsByTier[n].length);
    if (n === 7) return String(Object.keys(rules.categories || {}).length);
    return "auto";
  };
  const totalRules = [1, 2, 3, 4, 6].reduce((s, n) => s + cardsByTier[n].length, 0) + 1;
  const maxTierWeek = Math.max(1, ...tierWeek.map((t) => t.count));
  const visibleTiers = RULE_TIERS.filter((t) => selTier == null || selTier === t.n);
  const noHits =
    q &&
    [1, 2, 3, 4, 5, 6].every((n) => cardsByTier[n].filter(matchesQuery).length === 0) &&
    categoryEntries.length === 0;

  function tierMeta(n, cards) {
    const week = tierWeek.find((t) => t.n === n)?.count ?? 0;
    if (!cards) return `built in · ${week} this week`;
    return `${cards.filter((c) => c.enabled).length} of ${cards.length} enabled · ${week} this week`;
  }

  return (
    <>
      <PageHeading index={4} kicker="Sorting rules" title="Rules" subtitle="Checked top to bottom. The first match decides the folder." />
      <div className="ff-in flex flex-col gap-[18px]">
        <p className="m-0 -mt-2 text-[12.5px] text-[var(--ink-muted)]">
          Nine tiers, always in this order. A file stops at the first tier that matches; lower tiers are never consulted.
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a rule by match or folder"
            aria-label="Find a rule"
            className="ff-input flex-[1_1_240px]"
          />
          <button type="button" onClick={() => (formOpen ? closeForm() : openForm())} aria-expanded={formOpen} className="ff-btn ff-btn-primary ff-btn-lg">
            + New rule
          </button>
          <button type="button" onClick={handleOpenAIDialog} className="ff-btn ff-btn-outline ff-btn-lg">
            Generate with AI
          </button>
          <button
            type="button"
            onClick={handleSimulate}
            disabled={simulating}
            title="See what your current rules would classify differently than what's on record"
            className="ff-btn ff-btn-tertiary ff-btn-lg"
          >
            {simulating && <span aria-hidden="true" className="ff-spin h-3 w-3 rounded-full border-2 border-[var(--rule-2)] border-t-[var(--ink)]" />}
            {simulating ? "Checking…" : "Check impact"}
          </button>
          <button
            type="button"
            onClick={handleCheckConflicts}
            disabled={checkingConflicts}
            title="Check whether any of your rules can match the same file and disagree on where it goes"
            className="ff-btn ff-btn-tertiary ff-btn-lg"
          >
            {checkingConflicts && <span aria-hidden="true" className="ff-spin h-3 w-3 rounded-full border-2 border-[var(--rule-2)] border-t-[var(--ink)]" />}
            {checkingConflicts ? "Checking…" : "Check conflicts"}
          </button>
          <span className="flex flex-wrap items-center gap-2 lg:ml-auto">
            {status && (
              <span role="status" className="font-mono-data text-[11.5px]" style={{ color: status === "Failed to save" ? "var(--stamp)" : "var(--ink-muted)" }}>
                {status}
              </span>
            )}
            {importError && <span className="text-xs text-[var(--stamp)]">{importError}</span>}
            <input ref={fileInputRef} type="file" accept="application/json" className="hidden" onChange={handleImportFile} />
            <button type="button" onClick={handleImportClick} className="ff-btn ff-btn-tertiary ff-btn-lg">
              Import…
            </button>
            <button type="button" onClick={handleExportRules} className="ff-btn ff-btn-tertiary ff-btn-lg">
              Export JSON
            </button>
          </span>
        </div>

        {/* Tier index as a scrollable chip row on narrow screens */}
        <div role="group" aria-label="Rule tiers" className="ff-scroll-x ff-fade-edge -mx-1 flex gap-1.5 px-1 md:hidden">
          <button
            type="button"
            onClick={() => setSelTier(null)}
            aria-pressed={selTier == null}
            className="h-8 flex-none rounded-full border px-3 text-[12px] font-semibold"
            style={{ borderColor: selTier == null ? "var(--ink)" : "var(--rule-2)", background: selTier == null ? "var(--ink)" : "var(--sheet)", color: selTier == null ? "var(--paper)" : "var(--ink)" }}
          >
            All tiers
          </button>
          {RULE_TIERS.map((t) => {
            const on = selTier === t.n;
            return (
              <button
                key={t.n}
                type="button"
                onClick={() => setSelTier(on ? null : t.n)}
                aria-pressed={on}
                className="h-8 flex-none whitespace-nowrap rounded-full border px-3 text-[12px] font-semibold"
                style={{ borderColor: on ? "var(--ink)" : "var(--rule-2)", background: on ? "var(--ink)" : "var(--sheet)", color: on ? "var(--paper)" : "var(--ink)" }}
              >
                <span className="mr-1.5 font-mono-data text-[10.5px] opacity-70">{pad2(t.n)}</span>
                {t.label}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-start gap-6">
          <nav aria-label="Rule tiers" className="sticky top-4 hidden min-w-[200px] flex-[0_1_230px] flex-col gap-[3px] md:flex">
            <span className="ff-kicker pb-1.5">Priority order</span>
            <button
              type="button"
              onClick={() => setSelTier(null)}
              aria-pressed={selTier == null}
              className="cursor-pointer rounded-[0_4px_4px_0] border-0 px-2.5 py-2 text-left text-[12.5px] font-bold text-[var(--ink)]"
              style={{ borderLeft: `3px solid ${selTier == null ? "var(--stamp)" : "transparent"}`, background: selTier == null ? "var(--sheet-2)" : "transparent" }}
            >
              All tiers <span className="ml-1.5 font-mono-data text-[11px] font-medium text-[var(--ink-muted)]">{totalRules} rules</span>
            </button>
            {RULE_TIERS.map((t) => {
              const on = selTier === t.n;
              const week = tierWeek.find((x) => x.n === t.n)?.count ?? 0;
              return (
                <button
                  key={t.n}
                  type="button"
                  onClick={() => setSelTier(on ? null : t.n)}
                  aria-pressed={on}
                  className="grid cursor-pointer items-center gap-x-2 gap-y-1 rounded-[0_4px_4px_0] border-0 px-2.5 pb-2 pt-[7px] text-left text-[var(--ink)] transition-colors"
                  style={{
                    gridTemplateColumns: "22px minmax(0,1fr) auto",
                    borderLeft: `3px solid ${on ? "var(--stamp)" : "transparent"}`,
                    background: on ? "var(--sheet-2)" : "transparent",
                  }}
                >
                  <span className="font-mono-data text-[10.5px] font-semibold text-[var(--ink-muted)]">{pad2(t.n)}</span>
                  <span className="truncate text-[12.5px] font-semibold">{t.label}</span>
                  <span className="font-mono-data text-[11px] text-[var(--ink-muted)]">{tierCount(t.n)}</span>
                  <span aria-hidden="true" className="col-[2/4] h-[3px] overflow-hidden rounded-[2px] bg-[var(--rule)]">
                    <span
                      className="block h-full"
                      style={{ width: `${(week / maxTierWeek) * 100}%`, background: t.n === 1 || on ? "var(--stamp)" : "var(--ink-2)" }}
                    />
                  </span>
                </button>
              );
            })}
            <span className="px-0.5 pt-2 text-[11.5px] leading-[1.4] text-[var(--ink-muted)]">
              Bars show files each tier caught this week. A higher tier always wins.
            </span>
          </nav>

          <div className="flex min-w-0 flex-[1_1_440px] flex-col gap-[26px]">
            {formOpen && (
              <form
                ref={formRef}
                onSubmit={handleAddRule}
                aria-label={editing ? "Edit rule" : "New rule"}
                className="ff-in flex flex-col gap-3 rounded-[4px] border-[1.5px] border-[var(--ink)] bg-[var(--sheet-2)] p-4"
              >
                <div className="flex items-center gap-2">
                  <span className="ff-kicker">{editing ? "Edit rule" : "New rule"}</span>
                  <span className="flex-1 border-t border-dashed border-[var(--rule-2)]" />
                </div>
                <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
                  <label className="flex flex-col gap-[5px] text-[12px] font-semibold">
                    Rule type
                    <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="ff-input">
                      <option value="keyword">01 · Keyword</option>
                      <option value="regex">02 · Regex</option>
                      <option value="content">03 · Content keyword</option>
                      <option value="extension">04 · Extension</option>
                      <option value="date">06 · File age</option>
                    </select>
                  </label>
                  <label className="flex flex-col gap-[5px] text-[12px] font-semibold">
                    {MATCH_LABEL[form.type]}
                    <input
                      type={form.type === "date" ? "number" : "text"}
                      min={form.type === "date" ? 0 : undefined}
                      value={form.match}
                      onChange={(e) => setForm({ ...form, match: e.target.value })}
                      placeholder={MATCH_PLACEHOLDER[form.type]}
                      className="ff-input"
                      style={{ borderColor: formError && !form.match.trim() ? "var(--stamp)" : undefined }}
                    />
                  </label>
                  <label className="flex flex-col gap-[5px] text-[12px] font-semibold">
                    Destination folder
                    <input
                      list="ff-folders"
                      value={form.folder}
                      onChange={(e) => setForm({ ...form, folder: e.target.value })}
                      placeholder="Finance/Invoices"
                      className="ff-input"
                      style={{ borderColor: formError && form.match.trim() && !form.folder.trim() ? "var(--stamp)" : undefined }}
                    />
                  </label>
                </div>
                <datalist id="ff-folders">
                  {allFolders.map((f) => (
                    <option key={f} value={f} />
                  ))}
                </datalist>
                {formError && (
                  <span role="alert" className="text-[12.5px] text-[var(--stamp)]">
                    {formError}
                  </span>
                )}
                {form.match.trim() && form.type !== "date" && form.type !== "content" && (
                  <div className="rounded-[4px] border border-[var(--rule)] bg-[var(--sheet)] p-3 text-[12px]">
                    {previewLoading ? (
                      <span className="text-[var(--ink-muted)]">Checking existing files…</span>
                    ) : preview && preview.matched_count > 0 ? (
                      <>
                        <span className="font-semibold">
                          Would have matched {preview.matched_count} file{preview.matched_count === 1 ? "" : "s"} you've already organized
                        </span>
                        <span className="mt-1.5 flex flex-wrap gap-1.5">
                          {preview.by_category.map((row) => (
                            <span key={row.category} className="font-mono-data text-[11.5px] text-[var(--ink-2)]">
                              currently in <FolderTag>{row.category}</FolderTag> ({row.count})
                            </span>
                          ))}
                        </span>
                      </>
                    ) : (
                      <span className="text-[var(--ink-muted)]">No previously organized files match this yet.</span>
                    )}
                  </div>
                )}
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex-[1_1_220px] text-[12px] text-[var(--ink-muted)]">
                    Joins tier {FORM_TIER[form.type]}. Rules above it still win.
                  </span>
                  <button type="button" onClick={closeForm} className="ff-btn ff-btn-tertiary">
                    Cancel
                  </button>
                  <button type="submit" disabled={addingRule} className="ff-btn ff-btn-primary">
                    {addingRule ? "Saving…" : "Save rule"}
                  </button>
                </div>
              </form>
            )}

            {simulation && (
              <div className="ff-in flex flex-col gap-2 rounded-[4px] border border-[var(--rule-2)] p-3.5">
                {simulation.error ? (
                  <p className="m-0 text-[13px] text-[var(--stamp)]">Couldn't check rule impact. Try again.</p>
                ) : (
                  <>
                    <div className="flex items-start gap-2">
                      <span className="ff-kicker shrink-0">Impact</span>
                      <h3 className="m-0 flex-1 text-[13px] font-semibold">
                        {simulation.compared_count - simulation.unchanged_count === 0
                          ? `No changes — matches what's on record for the last ${simulation.compared_count} organized file${simulation.compared_count === 1 ? "" : "s"}.`
                          : `${simulation.compared_count - simulation.unchanged_count} of ${simulation.compared_count} recent files would be reclassified differently:`}
                      </h3>
                      <button type="button" onClick={() => setSimulation(null)} aria-label="Close impact" className="cursor-pointer border-none bg-transparent text-[var(--ink-muted)]">
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                    {simulation.changes.length > 0 && (
                      <div className="flex max-h-64 flex-col overflow-y-auto">
                        {simulation.changes.map((c, i) => (
                          <div key={`${c.filename}-${i}`} className="flex flex-wrap items-center gap-2 border-b border-dashed border-[var(--rule-2)] py-2 text-[12px]">
                            <span className="min-w-0 flex-1 truncate font-mono-data font-medium">{c.filename}</span>
                            <span className="font-mono-data text-[var(--ink-2)]">
                              {c.previous_category} <span className="text-[var(--stamp)]">→</span> <FolderTag>{c.new_category}</FolderTag>
                            </span>
                          </div>
                        ))}
                        {simulation.compared_count - simulation.unchanged_count > simulation.changes.length && (
                          <p className="m-0 pt-1 text-center text-xs text-[var(--ink-muted)]">Showing the first {simulation.changes.length} changes.</p>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {visibleTiers.map((tier) => {
              const n = tier.n;
              if (n <= 6) {
                const cards = cardsByTier[n];
                const shown = cards.filter(matchesQuery);
                if (q && shown.length === 0) return null;
                const editable = !!TIER_FORM[n];
                const maxWeek = Math.max(0, ...cards.map((c) => c.week));
                return (
                  <section key={n} aria-label={`Tier ${pad2(n)} ${tier.label}`} className="flex flex-col gap-3">
                    <TierHeader tier={tier} meta={tierMeta(n, cards)} />
                    <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))" }}>
                      {shown.map((card) => (
                        <IndexCard
                          key={card.key}
                          card={card}
                          maxWeek={maxWeek}
                          conflict={conflictFor(card)}
                          onOpenConflict={() => setConflictDialog(true)}
                          onToggle={card.onToggle}
                          onEdit={
                            card.noEdit
                              ? null
                              : () =>
                                  openForm(card.type, {
                                    form: { type: card.type, match: String(card.value), folder: card.folder },
                                    editing: { type: card.type, value: card.value, enabled: card.enabled },
                                  })
                          }
                        />
                      ))}
                      {editable && !q && <AddCard label={tier.label.toLowerCase()} onClick={() => openForm(TIER_FORM[n])} />}
                    </div>
                    {n === 5 && !q && (
                      <p className="m-0 text-[12px] text-[var(--ink-muted)]">The size threshold and folder are set in Settings → Automation policy.</p>
                    )}
                  </section>
                );
              }
              if (n === 7) {
                if (q && categoryEntries.length === 0) return null;
                return (
                  <section key={n} aria-label="Tier 07 Category" className="flex flex-col gap-3">
                    <TierHeader tier={tier} meta={`${Object.keys(rules.categories || {}).length} categories · ${tierWeek.find((t) => t.n === 7)?.count ?? 0} this week`} />
                    <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))" }}>
                      {categoryEntries.map(([category, extensions]) => (
                        <div key={category} className="ff-in flex flex-col gap-2.5 rounded-[4px] border border-[var(--rule-2)] bg-[var(--sheet)] px-3.5 py-3" style={{ boxShadow: "0 2px 0 var(--rule)" }}>
                          <div className="flex items-center gap-2">
                            <span className="font-mono-data text-[10.5px] font-semibold text-[var(--ink-muted)]">T07</span>
                            <b className="min-w-0 flex-1 truncate text-[13.5px]">{category}</b>
                            <button
                              type="button"
                              onClick={() => removeCategory(category)}
                              aria-label={`Remove ${category} category`}
                              className="grid h-6 w-6 cursor-pointer place-items-center rounded-[3px] border border-transparent bg-transparent text-[var(--ink-muted)] hover:border-[var(--rule-2)] hover:text-[var(--stamp)]"
                            >
                              <X width={13} height={13} />
                            </button>
                          </div>
                          <div className="flex flex-wrap items-center gap-1.5">
                            {extensions.map((ext) => (
                              <span key={ext} className="inline-flex items-center gap-1 rounded-[2px] bg-[var(--manila)] py-0.5 pl-1.5 pr-1 font-mono-data text-[11.5px] text-[var(--manila-ink)]">
                                {ext}
                                <button
                                  type="button"
                                  onClick={() => removeExtensionFromCategory(category, ext)}
                                  aria-label={`Remove ${ext} from ${category}`}
                                  className="cursor-pointer border-none bg-transparent p-0 leading-none text-[var(--manila-ink)] opacity-70 hover:opacity-100"
                                >
                                  ×
                                </button>
                              </span>
                            ))}
                            <input
                              value={newExtByCategory[category] || ""}
                              onChange={(e) => setNewExtByCategory({ ...newExtByCategory, [category]: e.target.value })}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") addExtensionToCategory(category);
                              }}
                              placeholder=".ext"
                              aria-label={`Add an extension to ${category}`}
                              className="ff-input h-6 w-16 px-1.5 text-[11.5px]"
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                    {!q && (
                      <div className="flex flex-wrap gap-2">
                        <input
                          value={newCategoryName}
                          onChange={(e) => setNewCategoryName(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") addCategory();
                          }}
                          placeholder="New category name"
                          aria-label="New category name"
                          className="ff-input h-[34px] flex-[1_1_200px]"
                        />
                        <button type="button" onClick={addCategory} className="ff-btn ff-btn-tertiary">
                          Add
                        </button>
                      </div>
                    )}
                  </section>
                );
              }
              if (q) return null;
              if (n === 8) {
                return (
                  <section key={n} aria-label="Tier 08 Automatic" className="flex flex-col gap-3">
                    <TierHeader tier={tier} meta={tierMeta(8)} />
                    <div className="flex flex-col rounded-[4px] border border-dashed border-[var(--rule-2)] px-3.5 py-1">
                      <div className="flex items-center gap-4 border-b border-dashed border-[var(--rule-2)] py-3">
                        <span className="flex min-w-0 flex-[1_1_0] flex-col gap-0.5">
                          <b className="text-[13.5px]">Auto-create a folder for unrecognized extensions</b>
                          <span className="text-[12px] text-[var(--ink-muted)]">
                            An unmatched .xyz file goes to “XYZ Files” instead of the default folder.
                          </span>
                        </span>
                        <Toggle
                          checked={!!rules.auto_organize_unknown_extensions}
                          onChange={(checked) => persist((current) => ({ ...current, auto_organize_unknown_extensions: checked }))}
                          label="Auto-create a folder for unrecognized extensions"
                        />
                      </div>
                      <div className="flex items-center gap-4 py-3">
                        <span className="flex min-w-0 flex-[1_1_0] flex-col gap-0.5">
                          <b className="text-[13.5px]">Rename with a timestamp prefix</b>
                          <span className="text-[12px] text-[var(--ink-muted)]">Prefix the file name with the date it was filed, in the folders you pick.</span>
                        </span>
                        <Toggle
                          checked={!!rules.enable_timestamp_rename}
                          onChange={(checked) => persist((current) => ({ ...current, enable_timestamp_rename: checked }))}
                          label="Rename with a timestamp prefix"
                        />
                      </div>
                      {rules.enable_timestamp_rename && (
                        <div className="flex flex-wrap gap-1.5 border-t border-dashed border-[var(--rule-2)] py-3">
                          {allFolders.length === 0 && <span className="text-xs text-[var(--ink-muted)]">No destination folders yet.</span>}
                          {allFolders.map((folder) => {
                            const active = (rules.timestamp_rename_categories || []).includes(folder);
                            return (
                              <button
                                key={folder}
                                type="button"
                                aria-pressed={active}
                                onClick={() => toggleTimestampCategory(folder)}
                                className="h-7 cursor-pointer rounded-[2px] border px-2 font-mono-data text-[11.5px]"
                                style={{
                                  borderColor: active ? "var(--ink)" : "var(--rule-2)",
                                  background: active ? "var(--ink)" : "transparent",
                                  color: active ? "var(--paper)" : "var(--ink-2)",
                                }}
                              >
                                {folder}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </section>
                );
              }
              return (
                <section key={n} aria-label="Tier 09 Default" className="flex flex-col gap-3">
                  <TierHeader tier={tier} meta={tierMeta(9)} />
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-[4px] border border-dashed border-[var(--rule-2)] p-3.5 text-[13px] text-[var(--ink-2)]">
                    <span className="flex-[1_1_240px]">
                      Everything that reaches this tier goes to <FolderTag>{rules.default_category || "Others"}</FolderTag>.
                    </span>
                    <button type="button" onClick={() => navigate("/app/settings#automation-policy")} className="ff-btn ff-btn-outline ff-btn-sm">
                      Open Settings
                    </button>
                  </div>
                </section>
              );
            })}
            {noHits && <div className="py-5 text-[var(--ink-muted)]">No rules match “{query}”.</div>}
          </div>

          <div className="sticky top-4 flex min-w-0 flex-[1_1_300px] flex-col gap-3.5">
            <PrecedenceTester rules={rules} />

            <div className="flex flex-col gap-1.5 rounded-[4px] border border-[var(--rule-2)] p-3.5">
              <Kicker
                right={
                  conflicts.length > 0 && <span className="font-mono-data text-[12px] font-semibold text-[var(--stamp)]">{conflicts.length}</span>
                }
              >
                Conflicts
              </Kicker>
              {!conflictCheck && (
                <p className="m-0 py-1 text-[12.5px] text-[var(--ink-muted)]">
                  Run “Check conflicts” to find rules that can match the same file and disagree on where it goes.
                </p>
              )}
              {conflictCheck?.error && <p className="m-0 text-[12.5px] text-[var(--stamp)]">Couldn't check rule conflicts. Try again.</p>}
              {conflictCheck && !conflictCheck.error && (
                <>
                  <p className="m-0 text-[12.5px] text-[var(--ink-2)]">
                    {conflictCheck.rules_checked} rule{conflictCheck.rules_checked === 1 ? "" : "s"} checked
                    {conflictCheck.total === 0
                      ? " — no potential conflicts found."
                      : ` — ${conflictCheck.warnings} potential overlap${conflictCheck.warnings === 1 ? "" : "s"}, ${conflictCheck.high} rule${conflictCheck.high === 1 ? "" : "s"} fully shadowed, ${conflictCheck.info} informational.`}
                  </p>
                  {conflicts.map((c, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => setConflictDialog(true)}
                      className="flex cursor-pointer flex-col gap-[5px] border-0 border-b border-dashed border-[var(--rule-2)] bg-transparent py-2 text-left hover:bg-[var(--sheet-2)]"
                    >
                      <Stamp tone={SEVERITY_TONE[c.severity] || "muted"} className="self-start">
                        {c.severity}
                      </Stamp>
                      <span className="font-mono-data text-[11.5px] text-[var(--ink-2)]" style={{ overflowWrap: "anywhere" }}>
                        {c.rules.map((r) => r.description).join("  vs.  ")}
                      </span>
                    </button>
                  ))}
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <Dialog open={conflictDialog} onOpenChange={setConflictDialog}>
        <DialogContent tab="Conflicts" className="max-h-[calc(100vh-60px)] overflow-y-auto p-[22px] sm:max-w-[680px]">
          <DialogHeader>
            <DialogTitle className="text-[24px]">Rule conflicts</DialogTitle>
            <DialogDescription className="text-[13px] text-[var(--ink-2)]">
              Rules that can match the same file. The higher tier wins; the other never sees that file.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-2.5">
            {conflicts.map((c, i) => (
              <RuleConflictCard key={i} conflict={c} />
            ))}
            {conflictCheck?.truncated && <p className="m-0 text-center text-xs text-[var(--ink-muted)]">Showing the first {conflicts.length} conflicts.</p>}
          </div>
        </DialogContent>
      </Dialog>

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

      <AIRuleGeneratorDialog
        open={aiOpen}
        onOpenChange={setAiOpen}
        prompt={aiPrompt}
        onPromptChange={setAiPrompt}
        generating={aiGenerating}
        result={aiResult}
        error={aiError}
        saving={aiSaving}
        impact={aiImpact}
        checkingImpact={aiCheckingImpact}
        onGenerate={handleGenerateRule}
        onCheckImpact={handleCheckAIImpact}
        onEditRequest={handleEditRequest}
        onEdit={handleEditAIProposal}
        onReject={handleRejectAI}
        onSaveRule={handleSaveAIProposal}
      />

      <RuleConflictWarningDialog
        open={pendingConflict !== null}
        onOpenChange={(open) => !open && setPendingConflict(null)}
        conflicts={pendingConflict?.conflicts || []}
        saving={conflictSaving}
        onBack={handleConflictBack}
        onSaveAnyway={handleConflictSaveAnyway}
      />
    </>
  );
}
