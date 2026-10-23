// Neutral paper file badge with a folded corner -- the extension is read
// straight off the real filename (never guessed), truncated to 4 chars.
// No per-type colours: every file is the same slip of paper.
export function extensionOf(filename = "") {
  const dot = filename.lastIndexOf(".");
  if (dot <= 0 || dot === filename.length - 1) return "—";
  return filename.slice(dot + 1, dot + 5).toUpperCase();
}

const SIZES = {
  md: { width: 34, height: 40, radius: "2px 9px 2px 2px", pad: 5 },
  sm: { width: 30, height: 36, radius: "2px 8px 2px 2px", pad: 4 },
  xs: { width: 26, height: 32, radius: "2px 7px 2px 2px", pad: 3 },
};

export default function FileBadge({ filename, size = "md", onSheet = false, className = "" }) {
  const s = SIZES[size] || SIZES.md;
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 font-mono-data text-[8.5px] font-semibold text-[var(--ink-2)] ${className}`}
      style={{
        width: s.width,
        height: s.height,
        borderRadius: s.radius,
        paddingBottom: s.pad,
        placeItems: "end center",
        background: onSheet ? "var(--sheet)" : "var(--sheet-2)",
        border: "1px solid var(--rule-2)",
      }}
    >
      {extensionOf(filename)}
    </span>
  );
}
