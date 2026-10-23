// Page header exactly as v5: mono page number + kicker, big Archivo title,
// one-line subtitle, 2px ink rule underneath. `crumb` renders a link
// trail (e.g. "Categories /") before the kicker.
export default function PageHeading({ index, kicker, title, subtitle, crumb = null, children }) {
  return (
    <div className="mb-[22px] flex flex-wrap items-end gap-x-5 gap-y-3 border-b-2 border-[var(--ink)] pb-[18px]">
      <div className="flex min-w-0 flex-[1_1_320px] flex-col gap-1.5">
        <div className="ff-kicker flex items-center gap-2">
          <span className="font-mono-data tracking-normal">{String(index).padStart(2, "0")}</span>
          {crumb}
          <span>{kicker}</span>
        </div>
        <h1
          className="ff-display m-0 text-[var(--ink)]"
          style={{ fontSize: "clamp(28px, 3.4vw, 40px)", lineHeight: 1, letterSpacing: "-0.025em", overflowWrap: "anywhere" }}
        >
          {title}
        </h1>
        {subtitle && <p className="m-0 max-w-[70ch] text-[13.5px] text-[var(--ink-2)]">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}
