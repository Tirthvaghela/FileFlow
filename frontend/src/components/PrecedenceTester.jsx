import { useMemo, useState } from "react";
import { RULE_TIERS, pad2 } from "../utils/ruleTiers.js";

// Fixed dark panel in both themes (literal colours, not theme tokens).
const C = {
  bg: "#1C1B18",
  fg: "#EFE9DD",
  line: "#433D32",
  manila: "#E9D49E",
  manilaInk: "#3F310D",
  stamp: "#F07256",
};

// Name-only mirror of rules/classifier.py's tier order, for the "where
// would this file go?" preview. Content, size and age need the real file,
// so those tiers are reported as not checked instead of being guessed.
// The backend classifier stays authoritative; this only reads the rules.
function evaluate(rules, filename) {
  const name = filename.toLowerCase();
  const dot = filename.lastIndexOf(".");
  const ext = dot > 0 ? filename.slice(dot).toLowerCase() : "";
  const results = {};

  const kw = (rules.keyword_rules || []).find((r) => r.keyword && name.includes(r.keyword.toLowerCase()));
  if (kw) results[1] = { dest: kw.folder, value: `"${kw.keyword}"` };

  for (const r of rules.regex_rules || []) {
    try {
      if (new RegExp(r.pattern, "i").test(filename)) {
        results[2] = { dest: r.folder, value: r.pattern };
        break;
      }
    } catch {
      // invalid pattern -- the backend skips it too
    }
  }

  if ((rules.content_keyword_rules || []).length) results[3] = { unchecked: "needs the file's content" };
  if (ext && rules.extension_rules?.[ext]) results[4] = { dest: rules.extension_rules[ext], value: ext };
  if (rules.large_file_enabled) results[5] = { unchecked: "needs the file size" };
  if ((rules.date_rules || []).length) results[6] = { unchecked: "needs the file date" };

  if (ext) {
    const cat = Object.entries(rules.categories || {}).find(([, exts]) => exts.includes(ext));
    if (cat) results[7] = { dest: cat[0], value: ext };
    if (rules.auto_organize_unknown_extensions ?? true) results[8] = { dest: `${ext.slice(1).toUpperCase()} Files`, value: ext };
  }
  results[9] = { dest: rules.default_category || "Others" };

  const hit = RULE_TIERS.find((t) => results[t.n] && !results[t.n].unchecked)?.n ?? 9;
  return { results, hit };
}

function samplesFor(rules) {
  const out = [];
  const kw = (rules.keyword_rules || [])[0];
  if (kw) out.push(`${kw.keyword.replace(/\s+/g, "_")}_march.pdf`);
  const ext = Object.keys(rules.extension_rules || {})[0];
  if (ext) out.push(`notes_final${ext}`);
  const catExt = Object.values(rules.categories || {}).flat()[0];
  if (catExt && !out.some((s) => s.endsWith(catExt))) out.push(`holiday_photo${catExt}`);
  out.push("random_export.xyz");
  return [...new Set(out)].slice(0, 4);
}

export default function PrecedenceTester({ rules }) {
  const samples = useMemo(() => samplesFor(rules), [rules]);
  const [picked, setPicked] = useState(0);
  const [custom, setCustom] = useState("");
  const filename = custom.trim() || samples[picked] || "random_export.xyz";
  const { results, hit } = useMemo(() => evaluate(rules, filename), [rules, filename]);
  const hitTier = RULE_TIERS.find((t) => t.n === hit);
  const dest = results[hit]?.dest;

  return (
    <aside
      aria-label="Precedence tester"
      className="flex flex-col gap-3.5 rounded-[4px] p-[18px]"
      style={{ background: C.bg, color: C.fg, border: `1px solid ${C.line}` }}
    >
      <span className="ff-kicker" style={{ color: C.fg, opacity: 0.7 }}>
        Precedence tester · your current rules
      </span>
      <h2 className="ff-display m-0 text-[22px] leading-[1.1]">Where would this file go?</h2>
      <div role="radiogroup" aria-label="Sample file" className="flex flex-col gap-1">
        {samples.map((s, i) => {
          const on = !custom.trim() && picked === i;
          return (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => {
                setPicked(i);
                setCustom("");
              }}
              className="h-[34px] cursor-pointer rounded-[3px] border px-2.5 text-left font-mono-data text-[12px] font-medium transition-colors"
              style={{
                borderColor: on ? C.manila : C.line,
                background: on ? "rgba(233,212,158,.12)" : "transparent",
                color: C.fg,
              }}
            >
              {s}
            </button>
          );
        })}
        <input
          value={custom}
          onChange={(e) => setCustom(e.target.value)}
          placeholder="or type a filename…"
          aria-label="Try a filename"
          className="h-[34px] rounded-[3px] border px-2.5 font-mono-data text-[12px]"
          style={{ borderColor: C.line, background: "transparent", color: C.fg }}
        />
      </div>
      <ol className="m-0 flex list-none flex-col gap-0.5 p-0">
        {RULE_TIERS.map((t) => {
          const r = results[t.n];
          const isHit = t.n === hit;
          const before = t.n < hit;
          let verdict = "not reached";
          if (isHit) verdict = "✓ decides";
          else if (r?.unchecked) verdict = before ? `skipped · ${r.unchecked}` : "not reached";
          else if (before) verdict = "no match";
          else if (r?.dest) verdict = `would match ${r.dest}`;
          return (
            <li
              key={t.n}
              className="flex items-center gap-2.5 rounded-[3px] px-2.5 py-1.5 transition-all"
              style={{
                background: isHit ? C.manila : "transparent",
                color: isHit ? C.manilaInk : C.fg,
                opacity: isHit || before ? 1 : 0.55,
                transform: isHit ? "translateX(6px)" : "none",
                transitionDuration: "var(--d3)",
              }}
            >
              <span className="w-[18px] font-mono-data text-[10.5px] font-semibold">{pad2(t.n)}</span>
              <span className="flex-1 text-[12.5px] font-semibold">{t.label}</span>
              <span className="text-right text-[11.5px]">{verdict}</span>
            </li>
          );
        })}
      </ol>
      <div className="flex flex-col gap-1.5 border-t border-dashed pt-3" style={{ borderColor: "rgba(239,233,221,.3)" }}>
        <span className="flex flex-wrap items-center gap-1.5 font-mono-data text-[12.5px] font-medium">
          <span style={{ overflowWrap: "anywhere" }}>{filename}</span>
          <span style={{ color: C.stamp }}>→</span>
          <span className="rounded-[2px] px-[7px] py-px font-semibold" style={{ background: C.manila, color: C.manilaInk }}>
            {dest}
          </span>
        </span>
        <span className="text-[12.5px]" style={{ opacity: 0.82 }}>
          {hit === 9
            ? "Nothing above matched by name, so it falls through to the default folder."
            : `Tier ${pad2(hit)} ${hitTier.label}${results[hit].value ? ` (${results[hit].value})` : ""} is the first match, so lower tiers are never consulted.`}{" "}
          Content, size and age tiers need the real file and are checked when it lands.
        </span>
      </div>
    </aside>
  );
}
