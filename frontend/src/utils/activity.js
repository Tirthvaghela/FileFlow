export function actionText(log) {
  if (log.action === "renamed_and_moved") return `Renamed duplicate → ${log.category}`;
  if (log.action === "replaced") return `Replaced existing file in ${log.category}`;
  if (log.action === "duplicate_skipped") return `Duplicate skipped`;
  if (log.action === "archived") return `Archived from ${log.category}`;
  return `Moved to ${log.category}`;
}

export function formatTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function relativeTime(iso) {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return formatTime(iso);
}

// One stamp tone+word per real action -- undone always wins regardless of
// what the original action was.
export const STAMP_META = {
  moved: { tone: "filed", label: "Filed" },
  renamed_and_moved: { tone: "filed", label: "Filed · renamed" },
  replaced: { tone: "filed", label: "Filed · replaced" },
  duplicate_skipped: { tone: "duplicate", label: "Duplicate" },
  archived: { tone: "archived", label: "Archived" },
  reclassified: { tone: "refiled", label: "Refiled" },
  deleted: { tone: "error", label: "Deleted" },
  error: { tone: "error", label: "Error" },
};

export function stampFor(log) {
  if (log.undone) return { tone: "undone", label: "Undone" };
  return STAMP_META[log.action] || { tone: "refiled", label: String(log.action || "").replace(/_/g, " ") };
}

// Mirrors the backend's UNDOABLE_ACTIONS (automation/organizer.py).
export const UNDOABLE_ACTIONS = ["moved", "renamed_and_moved", "replaced", "archived", "reclassified"];

// Past-tense operation title for History ("Moved", "Renamed and moved" ...).
export function operationTitle(log) {
  return (
    {
      moved: "Moved",
      renamed_and_moved: "Renamed and moved",
      replaced: "Replaced existing file",
      duplicate_skipped: "Skipped duplicate",
      archived: "Archived",
      reclassified: "Refiled",
      deleted: "Sent to Recycle Bin",
    }[log.action] || String(log.action || "").replace(/_/g, " ")
  );
}

// "14:05" for today, "21 Oct" otherwise.
export function clockTime(iso) {
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) {
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false });
  }
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

// "TODAY · FRI OCT 23" / "YESTERDAY · THU OCT 22" / "MON OCT 19".
export function dayHeading(iso) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const label = d
    .toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
    .replace(/,/g, "")
    .toUpperCase();
  if (d.toDateString() === today.toDateString()) return `Today · ${label}`;
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday · ${label}`;
  return label;
}

// Last path segment, for showing where a file came from ("Downloads").
export function folderName(path) {
  if (!path) return "";
  const parts = String(path).split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || "";
}
