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
