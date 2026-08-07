const PALETTE = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
  "var(--series-7)",
  "var(--series-8)",
];

const BADGE_OVERRIDES = {
  Documents: "DOC",
  Images: "IMG",
  Videos: "VID",
  Audio: "AUD",
  Archives: "ZIP",
  "Source Code": "{ }",
  Software: "EXE",
  Others: "...",
};

// Categories are user-defined (rules can point anywhere), so colors are
// assigned deterministically by name rather than hardcoded -- same input
// set always produces the same mapping, never reassigned by rank/filter.
export function buildCategoryColorMap(categoryNames) {
  const sorted = [...new Set(categoryNames)].sort((a, b) => a.localeCompare(b));
  const map = {};
  sorted.forEach((name, i) => {
    map[name] = PALETTE[i % PALETTE.length];
  });
  return map;
}

export function categoryBadge(name) {
  if (BADGE_OVERRIDES[name]) return BADGE_OVERRIDES[name];
  const letters = (name || "?").replace(/[^A-Za-z]/g, "");
  return (letters.slice(0, 3) || "???").toUpperCase();
}

// Every folder name FileFlow can ever route a file to -- used both by the
// timestamp-rename picker and the reclassify action, so any known
// destination is offered, not just the formal rules.categories keys.
export function collectKnownFolders(rules) {
  if (!rules) return [];
  const names = new Set([
    ...Object.keys(rules.categories || {}),
    ...Object.values(rules.extension_rules || {}),
    ...(rules.keyword_rules || []).map((r) => r.folder),
    ...(rules.regex_rules || []).map((r) => r.folder),
    ...(rules.date_rules || []).map((r) => r.folder),
    ...(rules.content_keyword_rules || []).map((r) => r.folder),
    rules.large_file_folder,
    rules.archive_folder,
    rules.default_category,
  ]);
  names.delete(undefined);
  names.delete("");
  return [...names].sort((a, b) => a.localeCompare(b));
}

export function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}
