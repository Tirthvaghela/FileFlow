import { Link } from "react-router-dom";
import { motion } from "motion/react";
import {
  ArrowRight,
  Bot,
  Copy,
  FolderKanban,
  Mail,
  Radar,
  Sliders,
  Undo2,
} from "lucide-react";
import { Button } from "../components/ui/button.jsx";
import TiltCard from "../components/ui/TiltCard.jsx";

const TICKER = [
  { file: "invoice_march_2026.pdf", to: "Finance Folder", status: "good", label: "moved" },
  { file: "photo_0421.jpg", to: "Images", status: "good", label: "moved" },
  { file: "report_v2.pdf", to: null, status: "warning", label: "duplicate skipped" },
  { file: "college_notes.docx", to: "Semester 9", status: "good", label: "moved" },
  { file: "script_backup.py", to: "Python Projects", status: "good", label: "moved" },
  { file: "install_bundle.exe", to: "Large Files", status: "good", label: "moved" },
  { file: "receipt_scan (1).pdf", to: "Documents", status: "good", label: "renamed + moved" },
];

const STATUS_COLOR = {
  good: "var(--status-good)",
  warning: "var(--status-warning)",
  critical: "var(--status-critical)",
};

const PIPELINE = ["Detected", "Classified", "Duplicate check", "Moved", "Logged"];

const FEATURES = [
  {
    Icon: Radar,
    title: "Real-time monitoring",
    description: "Watchdog detects every new file the instant it lands — no manual sweep.",
  },
  {
    Icon: Sliders,
    title: "Rule-based classification",
    description: "Keyword, extension, and size rules decide where a file goes, in your order.",
  },
  {
    Icon: Copy,
    title: "Duplicate detection",
    description: "SHA-256 content hashing — rename, skip, or replace, your call.",
  },
  {
    Icon: Undo2,
    title: "Everything reversible",
    description: "Undo the last move, or manually reclassify anything that landed wrong.",
  },
  {
    Icon: Bot,
    title: "Real RPA execution",
    description: "Hand the physical move to a UiPath Robot — Python decides, UiPath executes.",
  },
  {
    Icon: Mail,
    title: "Weekly email digest",
    description: "A summary of what got organized, delivered on a schedule or on demand.",
  },
];

function ActivityTicker() {
  return (
    <TiltCard
      maxRotate={8}
      glareOpacityMax={0.12}
      className="w-full max-w-md border border-[var(--border)] bg-[var(--surface-1)]/70 backdrop-blur-xl shadow-2xl shadow-black/60 rounded-2xl"
    >
      <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
        <span className="relative flex h-2.5 w-2.5">
          <span
            className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-70"
            style={{ background: "var(--status-good)" }}
          />
          <span
            className="relative inline-flex h-2.5 w-2.5 rounded-full"
            style={{ background: "var(--status-good)" }}
          />
        </span>
        <span className="font-mono-data text-xs text-[var(--text-secondary)]">
          watching ~/Downloads
        </span>
      </div>
      <div className="divide-y divide-[var(--border)]">
        {TICKER.map((row, i) => (
          <motion.div
            key={row.file}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.4, delay: 0.4 + i * 0.08, ease: "easeOut" }}
            className="flex items-center gap-3 px-4 py-3 hover:bg-white/[0.02] transition-colors"
          >
            <span
              className="h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: STATUS_COLOR[row.status] }}
            />
            <span className="min-w-0 flex-1 truncate font-mono-data text-[13px] text-[var(--text-primary)]">
              {row.file}
            </span>
            <span className="shrink-0 font-mono-data text-[11px] text-[var(--text-muted)]">
              {row.to ? `→ ${row.to}` : row.label}
            </span>
          </motion.div>
        ))}
      </div>
    </TiltCard>
  );
}

export default function Landing() {
  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
        delayChildren: 0.1,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 16 },
    show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 100, damping: 15 } },
  };

  return (
    <div className="marketing relative min-h-dvh overflow-hidden bg-[var(--page)]">
      {/* Background Grids & Ambient Lights */}
      <div className="absolute inset-0 bg-grid-overlay z-0 pointer-events-none" />
      <div className="absolute top-[-10%] left-[5%] h-[40%] w-[40%] rounded-full bg-[var(--series-1)]/10 blur-[130px] pointer-events-none animate-ambient-1" />
      <div className="absolute bottom-[20%] right-[-5%] h-[50%] w-[45%] rounded-full bg-[var(--series-7)]/10 blur-[140px] pointer-events-none animate-ambient-2" />

      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <motion.div
          initial={{ opacity: 0, x: -15 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="flex items-center gap-2.5"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--series-1)] text-white shadow-lg shadow-[var(--series-1)]/20">
            <FolderKanban className="h-[18px] w-[18px]" />
          </span>
          <span className="font-display text-base font-semibold tracking-tight text-[var(--text-primary)]">
            FileFlow
          </span>
        </motion.div>
        <motion.div
          initial={{ opacity: 0, x: 15 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="flex items-center gap-2"
        >
          <Button
            render={<Link to="/login" />}
            variant="ghost"
            className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-white/[0.04]"
          >
            Sign in
          </Button>
          <Button
            render={<Link to="/register" />}
            className="shadow-md shadow-[var(--series-1)]/20 hover:shadow-lg hover:shadow-[var(--series-1)]/30 transition-shadow"
          >
            Get started
          </Button>
        </motion.div>
      </header>

      <main className="relative z-10">
        <section className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-14 px-6 pt-16 pb-24 lg:grid-cols-[1.1fr_1fr] lg:pt-24">
          <motion.div
            variants={containerVariants}
            initial="hidden"
            animate="show"
          >
            <motion.div
              variants={itemVariants}
              className="mb-5 flex w-fit items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-1)]/80 backdrop-blur-md px-3.5 py-1.5 font-mono-data text-xs text-[var(--text-secondary)]"
            >
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--status-good)] opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--status-good)]" />
              </span>
              engine running
            </motion.div>

            <motion.h1
              variants={itemVariants}
              className="font-display text-4xl leading-[1.05] font-medium tracking-tight text-gradient-hero sm:text-5.5xl"
            >
              Your Downloads folder,
              <br />
              organized while you sleep.
            </motion.h1>

            <motion.p
              variants={itemVariants}
              className="mt-6 max-w-md text-base leading-relaxed text-[var(--text-secondary)]"
            >
              FileFlow watches your Downloads folder, classifies every file by rules you write,
              catches duplicates by content hash, and moves things into place — with a UiPath
              Robot on standby to do the physical work.
            </motion.p>

            <motion.div
              variants={itemVariants}
              className="mt-8 flex items-center gap-4"
            >
              <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                <Button render={<Link to="/register" />} size="lg" className="shadow-lg shadow-[var(--series-1)]/20">
                  Get started free
                  <ArrowRight className="h-4 w-4 group-hover/button:translate-x-1 transition-transform" />
                </Button>
              </motion.div>
              <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                <Button render={<Link to="/login" />} size="lg" variant="outline" className="hover:bg-white/[0.04]">
                  Sign in
                </Button>
              </motion.div>
            </motion.div>

            <motion.div
              variants={itemVariants}
              className="mt-12 flex flex-wrap items-center gap-x-2.5 gap-y-2 font-mono-data text-xs text-[var(--text-muted)]"
            >
              {PIPELINE.map((step, i) => (
                <span key={step} className="flex items-center gap-2">
                  <span className="hover:text-[var(--text-secondary)] transition-colors cursor-default">
                    {step}
                  </span>
                  {i < PIPELINE.length - 1 && <span className="text-[var(--text-muted)] opacity-60">→</span>}
                </span>
              ))}
            </motion.div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 15 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.25, ease: "easeOut" }}
            className="flex justify-center lg:justify-end"
          >
            <ActivityTicker />
          </motion.div>
        </section>

        <section className="border-t border-[var(--border)] bg-[var(--surface-2)]/20 backdrop-blur-sm relative overflow-hidden">
          <div className="absolute inset-0 bg-grid-overlay z-0 opacity-40 pointer-events-none" />
          <div className="relative z-10 mx-auto max-w-6xl px-6 py-20">
            <div className="mb-12 max-w-lg">
              <h2 className="font-display text-2xl font-medium tracking-tight text-[var(--text-primary)] sm:text-3xl">
                Everything the pipeline needs
              </h2>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Built for the moment a rule gets it wrong, not just the moment it works.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map(({ Icon, title, description }, i) => (
                <TiltCard
                  key={title}
                  maxRotate={5}
                  glareOpacityMax={0.08}
                  className="bg-[var(--page)]/60 border border-[var(--border)] hover:border-[var(--series-1)]/30 p-6 rounded-2xl shadow-sm transition-all"
                >
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-40px" }}
                    transition={{ duration: 0.4, delay: i * 0.08 }}
                  >
                    <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--surface-1)] text-[var(--series-1)] border border-[var(--border)] shadow-sm">
                      <Icon className="h-4.5 w-4.5" />
                    </span>
                    <h3 className="mt-4 text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
                    <p className="mt-2 text-xs leading-relaxed text-[var(--text-muted)]">{description}</p>
                  </motion.div>
                </TiltCard>
              ))}
            </div>
          </div>
        </section>

        <section className="relative mx-auto max-w-6xl px-6 py-24 text-center overflow-hidden">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[300px] w-[300px] rounded-full bg-[var(--series-1)]/5 blur-[90px] pointer-events-none" />
          <h2 className="font-display text-2xl font-medium tracking-tight text-[var(--text-primary)] sm:text-3.5xl">
            Stop organizing files by hand
          </h2>
          <p className="mx-auto mt-3.5 max-w-md text-sm text-[var(--text-secondary)] leading-relaxed">
            Set your rules once. FileFlow takes it from there — with a full audit trail and undo,
            every time.
          </p>
          <motion.div
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            className="inline-block mt-8"
          >
            <Button render={<Link to="/register" />} size="lg" className="shadow-lg shadow-[var(--series-1)]/20">
              Create your free account
              <ArrowRight className="h-4 w-4 group-hover/button:translate-x-1 transition-transform" />
            </Button>
          </motion.div>
        </section>
      </main>

      <footer className="relative z-10 border-t border-[var(--border)] py-8 text-center font-mono-data text-xs text-[var(--text-muted)]">
        FileFlow — IMScIT Semester IX RPA project, GLS University.
      </footer>
    </div>
  );
}
