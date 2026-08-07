import { useRef } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { gsap, useGSAP } from "../lib/gsap.js";
import {
  ArrowRight,
  Bot,
  ClipboardCheck,
  Copy,
  Fingerprint,
  FolderInput,
  FolderKanban,
  Mail,
  Radar,
  Scan,
  Sliders,
  Tags,
  Undo2,
} from "lucide-react";
import { Button } from "../components/ui/button.jsx";
import TiltCard from "../components/ui/TiltCard.jsx";
import AnimatedNumber from "../components/ui/AnimatedNumber.jsx";
import GradientField from "../components/GradientField.jsx";
import SortVisualization from "../components/SortVisualization.jsx";

const FEATURES = [
  {
    Icon: Radar,
    color: "var(--series-1)",
    title: "Real-time monitoring",
    description: "Watchdog detects every new file the instant it lands — no manual sweep.",
  },
  {
    Icon: Sliders,
    color: "var(--series-7)",
    title: "Rule-based classification",
    description: "Keyword, extension, and size rules decide where a file goes, in your order.",
  },
  {
    Icon: Copy,
    color: "var(--series-4)",
    title: "Duplicate detection",
    description: "SHA-256 content hashing — rename, skip, or replace, your call.",
  },
  {
    Icon: Undo2,
    color: "var(--series-2)",
    title: "Everything reversible",
    description: "Undo the last move, or manually reclassify anything that landed wrong.",
  },
  {
    Icon: Bot,
    color: "var(--series-3)",
    title: "Real RPA execution",
    description: "Hand the physical move to a UiPath Robot — Python decides, UiPath executes.",
  },
  {
    Icon: Mail,
    color: "var(--series-5)",
    title: "Weekly email digest",
    description: "A summary of what got organized, delivered on a schedule or on demand.",
  },
];

const STAGES = [
  { n: "01", Icon: Scan, label: "Detected", desc: "Watchdog notices the file the instant it lands." },
  { n: "02", Icon: Tags, label: "Classified", desc: "Extension, keyword, and size rules pick a category." },
  { n: "03", Icon: Fingerprint, label: "Duplicate check", desc: "A SHA-256 content hash catches exact repeats." },
  { n: "04", Icon: FolderInput, label: "Moved", desc: "Python — or a real UiPath Robot — performs the move." },
  { n: "05", Icon: ClipboardCheck, label: "Logged", desc: "Every action recorded to your own activity log." },
];

const CAPABILITIES = [
  { value: 5, decimals: 0, prefix: "", suffix: "-stage", label: "detect → classify → move pipeline" },
  { value: 1, decimals: 0, prefix: "<", suffix: "s", label: "file-stability check interval" },
  { value: 256, decimals: 0, prefix: "", suffix: "-bit", label: "SHA hash for duplicate detection" },
  { value: 100, decimals: 0, prefix: "", suffix: "%", label: "reversible — undo, every time" },
];

export default function Landing() {
  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.1, delayChildren: 0.1 } },
  };
  const itemVariants = {
    hidden: { opacity: 0, y: 16 },
    show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 100, damping: 15 } },
  };
  const revealVariants = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
  };

  const stagesSectionRef = useRef(null);
  const stageLineRef = useRef(null);
  const stageDotRef = useRef(null);
  const stageRefs = useRef([]);

  // Signature moment: on desktop, pin this section and scrub the
  // connecting-line draw + a traveling dot + each stage icon lighting up
  // in sync with scroll position -- the one place in the app where GSAP's
  // ScrollTrigger does something Framer Motion's whileInView genuinely
  // can't (continuous scroll-position sync, not just an enter/exit
  // trigger). Below the sm breakpoint the connecting line isn't even
  // rendered (grid-cols-1, no line), so mobile gets a plain tame
  // stagger-in instead -- no pinning a 5-column sequence into a 1-column
  // layout. prefers-reduced-motion skips straight to the settled state.
  useGSAP(
    () => {
      const stages = stageRefs.current.filter(Boolean);
      if (stages.length === 0) return;
      const icons = stages.map((el) => el.querySelector(".stage-icon"));
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      const mm = gsap.matchMedia();

      mm.add("(min-width: 640px)", () => {
        if (reduced) {
          gsap.set(stageLineRef.current, { scaleX: 1 });
          gsap.set(icons, { color: "#e8a33d" });
          return;
        }

        const trackWidth = stageLineRef.current.parentElement.getBoundingClientRect().width;
        gsap.set(stageDotRef.current, { opacity: 1, x: 0 });

        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: stagesSectionRef.current,
            start: "top top",
            end: "+=120%",
            scrub: 1,
            pin: true,
          },
        });

        tl.to(stageLineRef.current, { scaleX: 1, ease: "none" }, 0);
        tl.to(stageDotRef.current, { x: trackWidth, ease: "none" }, 0);
        icons.forEach((icon, i) => {
          tl.to(icon, { color: "#e8a33d", scale: 1.15, duration: 0.001 }, i / (icons.length - 1));
        });

        return () => {
          tl.scrollTrigger?.kill();
          tl.kill();
        };
      });

      mm.add("(max-width: 639px)", () => {
        if (reduced) {
          gsap.set(icons, { color: "#e8a33d" });
          return;
        }
        gsap.set(icons, { color: "#e8a33d" });
        gsap.from(stages, {
          opacity: 0,
          y: 16,
          stagger: 0.1,
          duration: 0.4,
          ease: "power1.out",
          scrollTrigger: { trigger: stagesSectionRef.current, start: "top 80%" },
        });
      });

      return () => mm.revert();
    },
    { scope: stagesSectionRef },
  );

  return (
    <div className="relative min-h-dvh overflow-hidden bg-[var(--page)]">
      <div className="absolute inset-0 bg-grid-light z-0 pointer-events-none" />

      <header className="relative z-10 mx-auto flex max-w-[1440px] items-center justify-between px-6 py-6 lg:px-10">
        <motion.div
          initial={{ opacity: 0, x: -15 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
          className="flex items-center gap-2.5"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--brand)] text-[var(--brand-foreground)] shadow-sm shadow-[var(--brand)]/30">
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
          <Button render={<Link to="/login" />} variant="ghost">
            Sign in
          </Button>
          <Button
            render={<Link to="/register" />}
            className="shadow-md shadow-[var(--brand)]/20 hover:shadow-lg hover:shadow-[var(--brand)]/30 transition-shadow"
          >
            Get started
          </Button>
        </motion.div>
      </header>

      <main className="relative z-10">
        <section className="relative">
          <GradientField className="z-0" />
          <div className="relative z-10 mx-auto grid max-w-[1440px] grid-cols-1 items-center gap-14 px-6 pt-16 pb-24 lg:px-10 lg:grid-cols-[1.1fr_1fr] lg:pt-20">
            <motion.div variants={containerVariants} initial="hidden" animate="show">
              <motion.div
                variants={itemVariants}
                className="mb-6 flex w-fit items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-1)] px-3.5 py-1.5 font-mono-data text-xs text-[var(--text-secondary)] shadow-sm"
              >
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--status-good)] opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--status-good)]" />
                </span>
                engine running
              </motion.div>

              <motion.h1
                variants={itemVariants}
                className="font-display text-5xl leading-[1.05] font-medium tracking-tight text-[var(--text-primary)] sm:text-6xl"
              >
                Your Downloads folder,
                <br />
                <span className="relative inline-block">
                  <span className="relative z-10 text-[var(--brand)]">organized</span>
                  <motion.span
                    initial={{ scaleX: 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: 0.6, delay: 1, ease: "easeOut" }}
                    style={{ transformOrigin: "left" }}
                    className="absolute -bottom-1 left-0 h-3 w-full origin-left rounded-full bg-[var(--brand)]/15"
                  />
                </span>{" "}
                while you sleep.
              </motion.h1>

              <motion.p
                variants={itemVariants}
                className="mt-6 max-w-md text-base leading-relaxed text-[var(--text-secondary)]"
              >
                FileFlow watches your Downloads folder, classifies every file by rules you write,
                catches duplicates by content hash, and moves things into place — with a UiPath
                Robot on standby to do the physical work.
              </motion.p>

              <motion.div variants={itemVariants} className="mt-8 flex items-center gap-4">
                <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                  <Button render={<Link to="/register" />} size="lg" className="shadow-lg shadow-[var(--brand)]/20">
                    Get started free
                    <ArrowRight className="h-4 w-4 group-hover/button:translate-x-1 transition-transform" />
                  </Button>
                </motion.div>
                <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                  <Button render={<Link to="/login" />} size="lg" variant="outline">
                    Sign in
                  </Button>
                </motion.div>
              </motion.div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.25, ease: "easeOut" }}
              className="flex justify-center lg:justify-end"
            >
              <SortVisualization className="max-w-xl" height={340} />
            </motion.div>
          </div>
        </section>

        <section className="border-y border-[var(--border)] bg-[var(--surface-1)]/60">
          <div className="mx-auto grid max-w-[1440px] grid-cols-2 gap-8 px-6 py-12 sm:grid-cols-4 lg:px-10">
            {CAPABILITIES.map((c, i) => (
              <motion.div
                key={c.label}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-40px" }}
                variants={revealVariants}
                transition={{ delay: i * 0.08 }}
                className="text-center sm:text-left"
              >
                <div className="font-display text-3xl font-medium tracking-tight text-[var(--text-primary)] sm:text-4xl">
                  <AnimatedNumber value={c.value} decimals={c.decimals} prefix={c.prefix} suffix={c.suffix} />
                </div>
                <div className="mt-1.5 text-xs leading-relaxed text-[var(--text-muted)]">{c.label}</div>
              </motion.div>
            ))}
          </div>
        </section>

        <section className="relative overflow-hidden">
          <div className="relative z-10 mx-auto max-w-[1440px] px-6 py-20 lg:px-10">
            <motion.div
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-60px" }}
              variants={revealVariants}
              className="mb-12 max-w-lg"
            >
              <h2 className="font-display text-2xl font-medium tracking-tight text-[var(--text-primary)] sm:text-3xl">
                Everything the pipeline needs
              </h2>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Built for the moment a rule gets it wrong, not just the moment it works.
              </p>
            </motion.div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map(({ Icon, color, title, description }, i) => (
                <motion.div
                  key={title}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true, margin: "-40px" }}
                  variants={revealVariants}
                  transition={{ delay: (i % 3) * 0.08 }}
                >
                  <TiltCard
                    maxRotate={6}
                    glareOpacityMax={0.06}
                    className="h-full rounded-2xl border border-[var(--border)] bg-[var(--surface-1)] p-6 shadow-sm transition-all hover:border-[var(--brand)]/30 hover:shadow-md"
                  >
                    <span
                      className="flex h-9 w-9 items-center justify-center rounded-lg"
                      style={{ color, background: `color-mix(in srgb, ${color} 14%, transparent)` }}
                    >
                      <Icon className="h-[18px] w-[18px]" />
                    </span>
                    <h3 className="mt-4 text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
                    <p className="mt-2 text-xs leading-relaxed text-[var(--text-muted)]">{description}</p>
                  </TiltCard>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        <section ref={stagesSectionRef} className="border-t border-[var(--border)] bg-[var(--surface-1)]/60">
          <div className="mx-auto max-w-[1440px] px-6 py-20 lg:px-10">
            <motion.div
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-60px" }}
              variants={revealVariants}
              className="mb-14 max-w-lg"
            >
              <h2 className="font-display text-2xl font-medium tracking-tight text-[var(--text-primary)] sm:text-3xl">
                How a file actually moves
              </h2>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Five stages, every time, logged and reversible.
              </p>
            </motion.div>

            <div className="relative grid grid-cols-1 gap-8 sm:grid-cols-5 sm:gap-4">
              <div className="absolute left-0 right-0 top-6 hidden h-px bg-[var(--border)] sm:block" />
              <div
                ref={stageLineRef}
                style={{ transformOrigin: "left", scaleX: 0 }}
                className="absolute left-0 right-0 top-6 hidden h-px bg-[var(--brand)] sm:block"
              />
              <span
                ref={stageDotRef}
                className="pointer-events-none absolute top-6 left-0 z-10 hidden h-2.5 w-2.5 -translate-y-1/2 rounded-full opacity-0 sm:block"
                style={{ background: "#e8a33d", boxShadow: "0 0 10px #e8a33d" }}
              />

              {STAGES.map((stage, i) => (
                <div
                  key={stage.label}
                  ref={(el) => (stageRefs.current[i] = el)}
                  className="relative flex flex-col items-start sm:items-center sm:text-center"
                >
                  <span className="stage-icon relative z-10 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-[var(--border)] bg-[var(--page)] text-[var(--text-muted)] shadow-sm">
                    <stage.Icon className="h-5 w-5" />
                  </span>
                  <span className="mt-3 font-mono-data text-[10px] text-[var(--text-muted)]">{stage.n}</span>
                  <h3 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{stage.label}</h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-[var(--text-muted)] sm:max-w-[140px]">
                    {stage.desc}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="relative mx-auto max-w-[1440px] overflow-hidden px-6 py-24 text-center lg:px-10">
          <GradientField />
          <motion.div
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, margin: "-60px" }}
            variants={revealVariants}
            className="relative z-10"
          >
            <h2 className="font-display text-2xl font-medium tracking-tight text-[var(--text-primary)] sm:text-4xl">
              Stop organizing files by hand
            </h2>
            <p className="mx-auto mt-3.5 max-w-md text-sm text-[var(--text-secondary)] leading-relaxed">
              Set your rules once. FileFlow takes it from there — with a full audit trail and undo,
              every time.
            </p>
            <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} className="inline-block mt-8">
              <Button render={<Link to="/register" />} size="lg" className="shadow-lg shadow-[var(--brand)]/20">
                Create your free account
                <ArrowRight className="h-4 w-4 group-hover/button:translate-x-1 transition-transform" />
              </Button>
            </motion.div>
          </motion.div>
        </section>
      </main>

      <footer className="relative z-10 border-t border-[var(--border)] py-8 text-center font-mono-data text-xs text-[var(--text-muted)]">
        FileFlow · GLS University, IMScIT Sem. IX RPA project
      </footer>
    </div>
  );
}
