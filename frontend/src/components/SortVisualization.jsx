import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import { animate, createDrawable, createScope } from "animejs";
import { Archive as ArchiveIcon, FileText, Image as ImageIcon, Package } from "lucide-react";
import TiltCard from "./ui/TiltCard.jsx";
import { buildCategoryColorMap, categoryBadge } from "../utils/categoryMeta.js";

const FOLDER_NAMES = ["Archive", "Documents", "Finance Folder", "Images", "Large Files"];
const FOLDER_COLORS = buildCategoryColorMap(FOLDER_NAMES);

// Spacing (0.8s) deliberately shorter than TRAVEL (2s) so 2-3 files are
// always visibly mid-flight -- an idle/empty lane reads as broken, not calm.
const FLIGHTS = [
  { file: "invoice_2026.pdf", Icon: FileText, target: "Finance Folder", delay: 0 },
  { file: "photo_0421.jpg", Icon: ImageIcon, target: "Images", delay: 0.8 },
  { file: "report_v2.pdf", Icon: FileText, target: "Documents", delay: 1.6 },
  { file: "install_bundle.exe", Icon: Package, target: "Large Files", delay: 2.4 },
  { file: "old_project.zip", Icon: ArchiveIcon, target: "Archive", delay: 3.2 },
];

const TRAVEL = 2;
const CYCLE = 5.2;

function targetXPercent(name) {
  const i = FOLDER_NAMES.indexOf(name);
  return 10 + (i / (FOLDER_NAMES.length - 1)) * 80;
}

export default function SortVisualization({ className = "", height = 300 }) {
  const laneRef = useRef(null);
  const pathRefs = useRef([]);

  // The flying file chips (Framer Motion, below) already trace this exact
  // arc via left/top keyframes -- these anime.js-drawn curves give that
  // same path a real vector trail, drawn once per flight in lockstep with
  // it, rather than the chip appearing to move through empty space.
  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const paths = pathRefs.current.filter(Boolean);
    if (paths.length === 0) return;

    if (reduced) {
      paths.forEach((p) => p.setAttribute("stroke-opacity", "0.3"));
      return;
    }

    const scope = createScope({ root: laneRef }).add(() => {
      const drawables = createDrawable(paths);
      drawables.forEach((drawable, i) => {
        animate(drawable, {
          draw: ["0 0", "0 1"],
          duration: TRAVEL * 1000,
          delay: FLIGHTS[i].delay * 1000,
          loop: true,
          loopDelay: (CYCLE - TRAVEL) * 1000,
          ease: "inOutQuad",
        });
      });
    });

    return () => scope.revert();
  }, []);

  return (
    <TiltCard
      maxRotate={4}
      glareOpacityMax={0.05}
      className={`flex w-full max-w-md flex-col overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] shadow-[0_0_60px_-20px_var(--brand)] ${className}`}
      style={{ height }}
    >
      <div className="flex shrink-0 items-center gap-2 border-b border-[var(--border)] bg-[var(--page)]/60 px-4 py-3">
        <span className="relative flex h-2.5 w-2.5">
          <span
            className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-70"
            style={{ background: "var(--status-good)" }}
          />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full" style={{ background: "var(--status-good)" }} />
        </span>
        <span className="font-mono-data text-xs text-[var(--text-secondary)]">watching ~/Downloads</span>
        <span className="ml-auto flex gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--brand)]" />
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--gridline)]" />
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--gridline)]" />
        </span>
      </div>

      <div ref={laneRef} className="relative flex-1 overflow-hidden">
        <svg
          className="pointer-events-none absolute inset-0 h-full w-full"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {FLIGHTS.map((f, i) => {
            const endX = targetXPercent(f.target);
            const midX = (50 + endX) / 2;
            return (
              <path
                key={f.file}
                ref={(el) => (pathRefs.current[i] = el)}
                d={`M 50,0 Q ${midX},48 ${endX},96`}
                fill="none"
                stroke={FOLDER_COLORS[f.target]}
                strokeWidth="0.5"
                vectorEffect="non-scaling-stroke"
              />
            );
          })}
        </svg>
        {FLIGHTS.map((f) => {
          const endX = targetXPercent(f.target);
          const midX = (50 + endX) / 2;
          return (
            <motion.div
              key={f.file}
              className="absolute flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--page)] px-2.5 py-1 shadow-sm whitespace-nowrap"
              style={{ marginLeft: "-3.5rem" }}
              initial={{ left: "50%", top: "0%", opacity: 0, scale: 0.6 }}
              animate={{
                left: ["50%", `${midX}%`, `${endX}%`, `${endX}%`],
                top: ["0%", "48%", "96%", "96%"],
                opacity: [0, 1, 1, 0],
                scale: [0.6, 1, 1, 0.45],
              }}
              transition={{
                duration: TRAVEL,
                delay: f.delay,
                repeat: Infinity,
                repeatDelay: CYCLE - TRAVEL,
                times: [0, 0.4, 0.85, 1],
                ease: "easeInOut",
              }}
            >
              <f.Icon className="h-3 w-3 shrink-0" style={{ color: FOLDER_COLORS[f.target] }} />
              <span className="font-mono-data text-[10px] text-[var(--text-secondary)]">{f.file}</span>
            </motion.div>
          );
        })}
      </div>

      <div className="flex shrink-0 items-start justify-between border-t border-[var(--border)] px-3 py-3">
        {FOLDER_NAMES.map((name) => {
          const flight = FLIGHTS.find((f) => f.target === name);
          const arrival = flight.delay + TRAVEL * 0.8;
          return (
            <motion.div
              key={name}
              className="flex w-[18%] flex-col items-center gap-1"
              animate={{ scale: [1, 1, 1.18, 1] }}
              transition={{ duration: 0.55, delay: arrival, repeat: Infinity, repeatDelay: CYCLE - 0.55 }}
            >
              <span
                className="flex h-8 w-8 items-center justify-center rounded-lg text-[8px] font-bold"
                style={{
                  color: FOLDER_COLORS[name],
                  background: `color-mix(in srgb, ${FOLDER_COLORS[name]} 16%, transparent)`,
                }}
              >
                {categoryBadge(name)}
              </span>
              <span className="max-w-full truncate text-[9px] text-[var(--text-muted)]">{name}</span>
            </motion.div>
          );
        })}
      </div>
    </TiltCard>
  );
}
