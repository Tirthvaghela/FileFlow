import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { Copy, FolderKanban, ShieldCheck, Sliders, Zap } from "lucide-react";
import GradientField from "../components/GradientField.jsx";
import SortVisualization from "../components/SortVisualization.jsx";

const PERKS = [
  { Icon: Zap, title: "Real-time", text: "Detected the instant a file lands" },
  { Icon: Sliders, title: "Rule-based", text: "Your extensions, keywords, sizes" },
  { Icon: Copy, title: "Deduped", text: "SHA-256 content hashing" },
  { Icon: ShieldCheck, title: "Reversible", text: "Undo any move, any time" },
];

export default function AuthLayout({ title, subtitle, children }) {
  return (
    <div className="relative flex min-h-dvh w-full overflow-hidden bg-[var(--page)]">
      <div className="relative hidden w-[55%] flex-col justify-center overflow-hidden border-r border-[var(--border)] px-12 py-16 xl:px-20 lg:flex">
        <div className="absolute inset-0 bg-grid-light" />
        <div className="absolute inset-0 bg-gradient-to-br from-[var(--brand)]/[0.06] via-transparent to-[var(--series-1)]/[0.06]" />
        <GradientField />

        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
          className="relative z-10 mx-auto w-full max-w-xl"
        >
          <Link to="/" className="mb-10 flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--brand)] text-[var(--brand-foreground)] shadow-sm shadow-[var(--brand)]/30">
              <FolderKanban className="h-[18px] w-[18px]" />
            </span>
            <span className="font-display text-base font-semibold text-[var(--text-primary)]">
              FileFlow
            </span>
          </Link>

          <h2 className="font-display text-4xl leading-[1.1] font-medium tracking-tight text-[var(--text-primary)] xl:text-5xl">
            Watch your files sort themselves.
          </h2>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-[var(--text-secondary)]">
            Every account gets its own watch folder, its own rules, and its own live pipeline —
            nothing shared, nothing to configure twice.
          </p>

          <div className="mt-8 grid grid-cols-2 gap-3">
            {PERKS.map(({ Icon, title, text }, i) => (
              <motion.div
                key={title}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.25 + i * 0.08, ease: "easeOut" }}
                className="rounded-xl border border-[var(--border)] bg-[var(--surface-1)]/80 p-3.5 shadow-sm backdrop-blur"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--brand)]/12 text-[var(--brand)]">
                  <Icon className="h-3.5 w-3.5" />
                </span>
                <div className="mt-2 text-xs font-semibold text-[var(--text-primary)]">{title}</div>
                <div className="mt-0.5 text-[11px] leading-snug text-[var(--text-muted)]">{text}</div>
              </motion.div>
            ))}
          </div>

          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.55, ease: "easeOut" }}
            className="mt-8"
          >
            <SortVisualization height={220} className="max-w-xl" />
          </motion.div>

          <p className="mt-8 font-mono-data text-[11px] text-[var(--text-muted)]">
            FileFlow · GLS University, IMScIT Sem. IX RPA project
          </p>
        </motion.div>
      </div>

      <div className="relative flex w-full flex-col items-center justify-center overflow-hidden px-6 py-12 lg:w-[45%]">
        <div className="absolute inset-0 bg-grid-light pointer-events-none lg:hidden" />
        <div className="pointer-events-none absolute inset-0 lg:hidden">
          <GradientField />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="relative z-10 w-full max-w-md"
        >
          <Link to="/" className="mb-8 flex items-center justify-center gap-2.5 lg:hidden">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--brand)] text-[var(--brand-foreground)] shadow-sm shadow-[var(--brand)]/30">
              <FolderKanban className="h-[18px] w-[18px]" />
            </span>
            <span className="font-display text-base font-semibold text-[var(--text-primary)]">
              FileFlow
            </span>
          </Link>

          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-10 shadow-xl shadow-black/[0.05]">
            <h1 className="font-display text-2xl font-medium text-[var(--text-primary)]">{title}</h1>
            {subtitle && <p className="mt-1.5 text-sm text-[var(--text-secondary)]">{subtitle}</p>}
            <div className="mt-7">{children}</div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
