// v5 switch: square-ish track (radius 3) and knob (radius 2).
// sm 32x18 (rule cards), md 40x22 (settings rows), lg 64x34 (monitoring hero).
// On = --filed, off = --rule-2. A disabled rule still renders at full
// contrast; the caller shows an "Off" label next to it.
const SIZES = {
  sm: { w: 32, h: 18, k: 14 },
  md: { w: 40, h: 22, k: 18 },
  lg: { w: 64, h: 34, k: 30 },
};

export default function Toggle({ checked, onChange, size = "md", label, disabled = false, className = "" }) {
  const s = SIZES[size] || SIZES.md;
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!!checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={`flex shrink-0 cursor-pointer border-none bg-transparent p-0 disabled:cursor-not-allowed ${className}`}
    >
      <span
        className="flex p-[2px] transition-colors"
        style={{
          width: s.w,
          height: s.h,
          borderRadius: 3,
          justifyContent: checked ? "flex-end" : "flex-start",
          background: checked ? "var(--filed)" : "var(--rule-2)",
          transitionDuration: "var(--d2)",
        }}
      >
        <span style={{ width: s.k, height: s.k, borderRadius: 2, background: "var(--sheet)", boxShadow: "0 1px 2px var(--shade)" }} />
      </span>
    </button>
  );
}
