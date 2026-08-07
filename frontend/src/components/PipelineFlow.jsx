import { useRef, useState } from "react";
import { gsap, useGSAP } from "../lib/gsap.js";

const STEPS = ["Detected", "Classified", "Duplicate check", "Moved", "Logged"];

export default function PipelineFlow({ running }) {
  const containerRef = useRef(null);
  const pathRef = useRef(null);
  const dotRef = useRef(null);
  const chipRefs = useRef([]);
  const [svgSize, setSvgSize] = useState({ width: 0, height: 0 });
  const [pathD, setPathD] = useState("");

  useGSAP(
    () => {
      const chips = chipRefs.current.filter(Boolean);
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (chips.length === 0) return;

      const container = containerRef.current;
      const width = container.offsetWidth;
      const height = container.offsetHeight;
      setSvgSize({ width, height });

      // Real vector path (not just a dot moved between DOM offsets) --
      // straight segments between each chip's center, which also
      // naturally handles the row wrapping to a second line on narrow
      // screens since each segment only ever connects two real points.
      const points = chips.map((el) => ({
        x: el.offsetLeft + el.offsetWidth / 2,
        y: el.offsetTop + el.offsetHeight / 2,
      }));
      const d = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x},${p.y}`).join(" ");
      setPathD(d);

      if (!running || reduced) {
        gsap.set(dotRef.current, { opacity: 0 });
        gsap.set(pathRef.current, { drawSVG: "0%" });
        return;
      }

      // Wait a tick for the path's `d` to actually be in the DOM (state
      // update above triggers a re-render) before drawSVG/motionPath read
      // its geometry.
      requestAnimationFrame(() => {
        if (!pathRef.current) return;
        gsap.set(pathRef.current, { drawSVG: "0%" });
        gsap.set(dotRef.current, { opacity: 1 });

        const tl = gsap.timeline({ repeat: -1, repeatDelay: 0.6 });
        const segments = chips.length - 1;
        chips.forEach((chip, i) => {
          tl.addLabel(`step${i}`)
            .to(
              pathRef.current,
              { drawSVG: `0% ${(i / segments) * 100}%`, duration: 0.5, ease: "power1.inOut" },
              `step${i}`,
            )
            .to(chip, { scale: 1.06, borderColor: "var(--brand)", duration: 0.2, ease: "power1.out" }, `step${i}`)
            .to(chip, { scale: 1, borderColor: "var(--border)", duration: 0.3, ease: "power1.in" }, `step${i}+=0.3`);
          if (i < segments) {
            tl.to(
              dotRef.current,
              {
                motionPath: {
                  path: pathRef.current,
                  start: i / segments,
                  end: (i + 1) / segments,
                },
                duration: 0.5,
                ease: "power1.inOut",
              },
              `step${i}`,
            );
          }
        });

        return () => tl.kill();
      });
    },
    { dependencies: [running], scope: containerRef },
  );

  return (
    <div ref={containerRef} className="relative mt-4 flex flex-wrap items-center gap-2">
      <svg
        className="pointer-events-none absolute inset-0 overflow-visible"
        width={svgSize.width}
        height={svgSize.height}
      >
        <path
          ref={pathRef}
          d={pathD}
          fill="none"
          stroke="var(--brand)"
          strokeWidth="1.5"
          strokeLinecap="round"
          opacity="0.5"
        />
      </svg>
      <span
        ref={dotRef}
        className="pointer-events-none absolute h-2 w-2 rounded-full opacity-0"
        style={{ background: "var(--brand)", boxShadow: "0 0 8px var(--brand)" }}
      />
      {STEPS.map((step, i) => (
        <span key={step} className="flex items-center gap-2">
          <span
            ref={(el) => (chipRefs.current[i] = el)}
            className="relative flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--gridline)]/50 px-3 py-1 text-xs text-[var(--text-secondary)]"
          >
            <span
              className="h-1.5 w-1.5 rounded-full"
              style={{ background: running ? "var(--status-good)" : "var(--text-muted)" }}
            />
            {step}
          </span>
          {i < STEPS.length - 1 && <span className="text-[var(--text-muted)]">→</span>}
        </span>
      ))}
    </div>
  );
}
