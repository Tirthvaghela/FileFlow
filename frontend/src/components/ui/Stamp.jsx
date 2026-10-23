// The rubber-stamp status badge used for every operation result (Filed,
// Duplicate, Archived, Refiled, Undone, Error ...). Status is never
// colour-only: the stamp always carries a word.
const TONES = {
  filed: "var(--filed)",
  ok: "var(--filed)",
  duplicate: "var(--warn)",
  warn: "var(--warn)",
  archived: "var(--ink-2)",
  refiled: "var(--ink)",
  ink: "var(--ink)",
  undone: "var(--ink-muted)",
  muted: "var(--ink-muted)",
  error: "var(--stamp)",
  shadowed: "var(--stamp)",
  high: "var(--stamp)",
};

export default function Stamp({
  tone = "refiled",
  pop = false,
  size = "sm",
  as: Tag = "span",
  children,
  className = "",
  style,
  ...props
}) {
  const lg = size === "lg";
  return (
    <Tag
      className={`inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-[3px] border-[1.5px] bg-transparent font-bold uppercase ${
        lg ? "h-[22px] px-2 text-[10px]" : "h-5 px-[7px] text-[9.5px]"
      } ${pop ? "ff-stamp-pop" : ""} ${className}`}
      style={{
        color: TONES[tone] || TONES.refiled,
        borderColor: "currentColor",
        fontStretch: "120%",
        letterSpacing: "0.1em",
        transform: "rotate(-2deg)",
        ...style,
      }}
      {...props}
    >
      {children}
    </Tag>
  );
}
