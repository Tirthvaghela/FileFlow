const DUPLICATE_LABELS = { rename: "rename", skip: "skip", replace: "replace" };

// The real, fixed FileFlow architecture -- five stages every file passes
// through, Classify filled in ink as the step that does the work. Every
// sub-stat is read from real state the caller already has.
function steps({ running, activeRules, duplicateHandling, totalLogged }) {
  return [
    { n: 1, title: "Detect", body: "Watchdog or your PC agent sees a file once it stops changing.", sub: running ? "monitoring on" : "monitoring paused" },
    { n: 2, title: "Classify", body: "Rules are checked in a fixed order of 9 tiers.", sub: `${activeRules ?? "—"} rule${activeRules === 1 ? "" : "s"}`, emphasis: true },
    { n: 3, title: "Explain", body: "Match type, value and rule are stored with the file.", sub: "kept per file" },
    { n: 4, title: "Move", body: "Python or a UiPath robot moves it into the folder.", sub: `duplicates: ${DUPLICATE_LABELS[duplicateHandling] || "rename"}` },
    { n: 5, title: "Log", body: "Every action is written to Activity and can be undone.", sub: `${totalLogged ?? "—"} entries` },
  ];
}

export default function PipelineFlow({ running, activeRules, duplicateHandling, totalLogged }) {
  const stages = steps({ running, activeRules, duplicateHandling, totalLogged });

  return (
    <section aria-label="How FileFlow sorts" className="flex flex-col gap-2.5 border-t-[1.5px] border-[var(--ink)] pt-1.5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5">
        <span className="ff-kicker">How a file moves</span>
        <span className="text-[12px] text-[var(--ink-muted)]">
          New downloads go straight down the line. Only “Organize existing files” stops at a preview, then re-scans and
          re-plans when you confirm.
        </span>
      </div>
      <ol className="m-0 grid list-none grid-cols-2 gap-2 p-0 sm:grid-cols-[repeat(auto-fit,minmax(170px,1fr))]">
        {stages.map((s, i) => (
          <li key={s.n} className="ff-in flex items-start gap-2.5 py-2.5" style={{ animationDelay: `${i * 50}ms` }}>
            <span
              className="grid h-[26px] w-[26px] shrink-0 place-items-center rounded-full border-[1.5px] border-[var(--ink)] font-mono-data text-[11px] font-semibold"
              style={{ background: s.emphasis ? "var(--ink)" : "transparent", color: s.emphasis ? "var(--paper)" : "var(--ink)" }}
            >
              {s.n}
            </span>
            <span className="flex min-w-0 flex-col gap-[3px]">
              <b className="text-[13px] font-extrabold uppercase tracking-[0.05em]" style={{ fontStretch: "116%" }}>
                {s.title}
              </b>
              <span className="text-[12px] leading-[1.35] text-[var(--ink-2)]">{s.body}</span>
              <span className="font-mono-data text-[11px] text-[var(--ink-muted)]">{s.sub}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
