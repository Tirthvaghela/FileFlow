// A destination folder, styled as a manila tag. Wraps (never clips) and
// keeps its background on every wrapped line.
export default function FolderTag({ children, className = "", strong = false }) {
  return (
    <span
      className={`inline rounded-[2px] bg-[var(--manila)] px-[7px] py-[2px] font-mono-data text-[12px] text-[var(--manila-ink)] ${
        strong ? "font-semibold" : "font-medium"
      } ${className}`}
      style={{ overflowWrap: "anywhere", boxDecorationBreak: "clone", WebkitBoxDecorationBreak: "clone" }}
    >
      {children}
    </span>
  );
}
