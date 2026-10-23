// The classifier's one real, fixed evaluation order (rules/classifier.py
// MATCH_TYPE_PRIORITY) -- not re-derived or guessed, just the same 9 tiers
// the backend already stamps onto every log's explanation.match_type.
export const RULE_TIERS = [
  { n: 1, matchType: "keyword", label: "Keyword", short: "Keyword", desc: "Filename contains" },
  { n: 2, matchType: "regex", label: "Regex", short: "Regex", desc: "Filename matches" },
  { n: 3, matchType: "content_keyword", label: "Content keyword", short: "Content", desc: "File content contains" },
  { n: 4, matchType: "extension", label: "Extension", short: "Ext.", desc: "File extension is" },
  { n: 5, matchType: "large_file", label: "Large file", short: "Size", desc: "Larger than" },
  { n: 6, matchType: "date", label: "File age", short: "Age", desc: "Older than" },
  { n: 7, matchType: "category", label: "Category", short: "Category", desc: "Extension listed in a category" },
  { n: 8, matchType: "auto_extension", label: "Automatic", short: "Auto", desc: "Folder named after extension" },
  { n: 9, matchType: "default", label: "Default", short: "Default", desc: "Nothing else matched" },
];

export const ORGANIZED_ACTIONS = new Set(["moved", "renamed_and_moved", "replaced"]);

// Groups real activity-log rows (each already carrying explanation.match_type
// from the classifier) into the 9 fixed tiers, for a given time window.
// Rows with no explanation (manual reclassify, archive sweep, undo) are
// left out, same as the backend's own organized-file counting.
export function groupLogsByTier(logs, { sinceMs } = {}) {
  const buckets = new Map(RULE_TIERS.map((t) => [t.matchType, { ...t, count: 0, categories: new Map() }]));
  for (const log of logs) {
    if (log.undone) continue;
    if (!ORGANIZED_ACTIONS.has(log.action)) continue;
    const matchType = log.explanation?.match_type;
    if (!matchType || !buckets.has(matchType)) continue;
    if (sinceMs && new Date(log.timestamp).getTime() < sinceMs) continue;
    const bucket = buckets.get(matchType);
    bucket.count += 1;
    bucket.categories.set(log.category, (bucket.categories.get(log.category) || 0) + 1);
  }
  return RULE_TIERS.map((t) => {
    const bucket = buckets.get(t.matchType);
    const categories = [...bucket.categories.entries()].sort((a, b) => b[1] - a[1]);
    return { ...t, count: bucket.count, categories };
  });
}

export function tierFor(matchType) {
  return RULE_TIERS.find((t) => t.matchType === matchType) || null;
}

export function pad2(n) {
  return String(n).padStart(2, "0");
}
