// The v5 logomark: a folder (tab + body) in ink with a red stamp dot.
// `light` renders it in manila for the dark auth panel.
export default function BrandMark({ light = false }) {
  const body = light ? "#E9D49E" : "var(--ink)";
  return (
    <span aria-hidden="true" className="relative inline-block shrink-0" style={{ width: 30, height: 24 }}>
      <span className="absolute left-0 top-0" style={{ width: 13, height: 6, borderRadius: "3px 3px 0 0", background: body }} />
      <span className="absolute left-0" style={{ top: 5, width: 30, height: 19, borderRadius: "0 4px 4px 4px", background: body }} />
      <span
        className="absolute"
        style={{ right: 4, bottom: 5, width: 7, height: 7, borderRadius: 4, background: light ? "#C23E26" : "var(--stamp)" }}
      />
    </span>
  );
}
