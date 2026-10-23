import { RULE_TIERS, pad2, tierFor } from "../utils/ruleTiers.js";

const MATCH_TYPE_LABEL = {
  keyword: "Keyword",
  regex: "Regex",
  content_keyword: "File content",
  extension: "Extension",
  large_file: "Large file",
  date: "File age",
  category: "Category",
  auto_extension: "Automatic grouping",
  default: "Default category",
};

function sentence(explanation, tier) {
  const dest = explanation.destination;
  if (explanation.match_type === "default") {
    return `No rule matched, so it went to the default folder ${dest}. Add a rule if files like this belong somewhere specific.`;
  }
  const higher = tier && tier.n > 1 ? ` Tiers 01–${pad2(tier.n - 1)} were checked first and none of them matched.` : "";
  return `${explanation.rule_name || MATCH_TYPE_LABEL[explanation.match_type] || "A rule"} matched, so it was filed in ${dest}.${higher}`;
}

// The inline "Why here?" panel: a 9-cell tier ladder (the deciding tier in
// ink, tiers checked before it shaded, later tiers never reached), the
// stored facts, and one plain sentence. Only the explanation the backend
// recorded is shown -- nothing is inferred for rows without one.
export default function ExplanationPanel({ explanation }) {
  if (!explanation) {
    return (
      <div className="ff-in flex flex-col gap-3 rounded-[4px] border border-dashed border-[var(--rule-2)] bg-[var(--sheet-2)] p-3.5">
        <p className="m-0 text-[13px] text-[var(--ink-2)]">
          No explanation was recorded for this entry. Manual refiles, archive sweeps and undos don't go through the rule tiers.
        </p>
      </div>
    );
  }

  const tier = tierFor(explanation.match_type);
  const hit = tier?.n ?? 9;
  const facts = [
    { k: "Match type", v: MATCH_TYPE_LABEL[explanation.match_type] || explanation.match_type },
    explanation.matched_value ? { k: "Matched value", v: `"${explanation.matched_value}"` } : null,
    explanation.rule_name ? { k: "Rule", v: explanation.rule_name } : null,
    { k: "Destination", v: explanation.destination },
    { k: "Priority", v: `${explanation.priority ?? hit} of 9` },
  ].filter(Boolean);

  return (
    <div className="ff-in flex flex-col gap-3 rounded-[4px] border border-dashed border-[var(--rule-2)] bg-[var(--sheet-2)] p-3.5">
      {explanation.match_type === "default" && (
        <p className="m-0 text-[13px] font-semibold">No matching rule — this file was placed in the account's default category.</p>
      )}
      <div className="flex gap-[3px] overflow-x-auto" aria-label={`Matched tier ${hit} of 9`}>
        {RULE_TIERS.map((t) => {
          const isHit = t.n === hit;
          const before = t.n < hit;
          return (
            <span
              key={t.n}
              aria-hidden="true"
              title={t.label}
              className="flex min-w-[44px] flex-1 flex-col gap-0.5 rounded-[3px] border px-1.5 py-1.5"
              style={{
                background: isHit ? "var(--ink)" : before ? "var(--rule)" : "transparent",
                color: isHit ? "var(--paper)" : before ? "var(--ink-2)" : "var(--ink-muted)",
                borderColor: isHit ? "var(--ink)" : "var(--rule-2)",
              }}
            >
              <span className="font-mono-data text-[10px] font-semibold">{pad2(t.n)}</span>
              <span className="truncate text-[10.5px]">{t.short}</span>
            </span>
          );
        })}
      </div>
      <dl className="m-0 grid gap-x-[18px] gap-y-2.5" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))" }}>
        {facts.map((f) => (
          <div key={f.k} className="flex flex-col gap-0.5">
            <dt className="ff-kicker text-[9.5px]">{f.k}</dt>
            <dd className="m-0 font-mono-data text-[12.5px] font-medium" style={{ overflowWrap: "anywhere" }}>
              {f.v}
            </dd>
          </div>
        ))}
      </dl>
      <p className="m-0 text-[13px] text-[var(--ink-2)]">{sentence(explanation, tier)}</p>
    </div>
  );
}
