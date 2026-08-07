import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { motion } from "motion/react";
import {
  Activity,
  BarChart3,
  FolderKanban,
  FolderOpen,
  History,
  LayoutGrid,
  Settings,
  SlidersHorizontal,
} from "lucide-react";
import { Switch } from "./ui/switch.jsx";
import { formatBytes } from "../utils/categoryMeta.js";
import { getStats } from "../services/api.js";
import { useRules } from "../context/RulesContext.jsx";
import { useAuth } from "../context/AuthContext.jsx";

const links = [
  { to: "/app", label: "Dashboard", end: true, Icon: LayoutGrid },
  { to: "/app/activity", label: "Activity", Icon: Activity },
  { to: "/app/rules", label: "Rules", Icon: SlidersHorizontal },
  { to: "/app/categories", label: "Categories", Icon: FolderOpen },
  { to: "/app/reports", label: "Reports", Icon: BarChart3 },
  { to: "/app/history", label: "History", Icon: History },
  { to: "/app/settings", label: "Settings", Icon: Settings },
];

export default function Sidebar() {
  const { rules, saveRules } = useRules();
  const { user, logout } = useAuth();
  const [storageSaved, setStorageSaved] = useState(0);
  const watchFolder = user?.watch_folder || "";

  useEffect(() => {
    getStats()
      .then((s) => setStorageSaved(s.storage_saved_bytes))
      .catch(() => {});
  }, []);

  async function toggleAutomation() {
    if (!rules) return;
    try {
      await saveRules((current) => ({
        ...current,
        realtime_monitoring_enabled: !current.realtime_monitoring_enabled,
      }));
    } catch {
      // saveRules already rolled the shared state back on failure
    }
  }

  const active = rules?.realtime_monitoring_enabled ?? true;
  const folderLabel = watchFolder ? watchFolder.split(/[\\/]/).slice(-2).join("/") : "…";

  return (
    <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col justify-between border-r border-[var(--border)] bg-[var(--surface-1)] z-10">
      <div>
        <div className="flex items-center gap-2.5 px-5 py-5">
          <motion.span
            whileHover={{ rotate: [0, -10, 10, -10, 0] }}
            transition={{ duration: 0.5 }}
            className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--brand)] text-[var(--brand-foreground)] shadow-sm shadow-[var(--brand)]/30 cursor-pointer"
          >
            <FolderKanban className="h-[18px] w-[18px]" />
          </motion.span>
          <div className="leading-tight">
            <div className="text-base font-semibold text-[var(--text-primary)]">
              FileFlow
            </div>
            <div className="text-xs text-[var(--text-muted)]">RPA Organizer</div>
          </div>
        </div>

        <nav className="flex flex-col gap-1 px-3">
          {links.map(({ to, label, end, Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className="relative z-0"
            >
              {({ isActive }) => (
                <div
                  className={`group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors relative cursor-pointer select-none ${
                    isActive
                      ? "font-medium text-[var(--brand)]"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {/* Sliding active pill indicator */}
                  {isActive && (
                    <motion.span
                      layoutId="activeNavIndicator"
                      className="absolute inset-0 -z-10 rounded-lg bg-[var(--brand)]/10 border border-[var(--brand)]/15 nav-pill-glow"
                      transition={{ type: "spring", stiffness: 380, damping: 30 }}
                    />
                  )}
                  {/* Dynamic background highlight on hover */}
                  <div
                    className="absolute inset-0 -z-20 rounded-lg bg-[var(--gridline)]/50 opacity-0 group-hover:opacity-100 transition-opacity duration-200"
                  />

                  {/* Icon hover micro-interactions */}
                  <motion.span
                    className="shrink-0"
                    variants={{
                      hover: {
                        scale: 1.15,
                        rotate: Icon === Settings ? 45 : Icon === History ? -25 : 0,
                        y: Icon === FolderOpen ? -2 : 0,
                      }
                    }}
                    whileHover="hover"
                  >
                    <Icon className="h-4 w-4" strokeWidth={2} />
                  </motion.span>
                  {label}
                </div>
              )}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="border-t border-[var(--border)] px-4 py-4">
        {/* Animated Automation switcher card */}
        <motion.div
          animate={{
            borderColor: active ? "rgba(12, 163, 12, 0.25)" : "var(--border)",
            backgroundColor: active ? "rgba(12, 163, 12, 0.04)" : "var(--page)",
            boxShadow: active ? "0 0 16px rgba(12, 163, 12, 0.05)" : "none",
          }}
          className="mb-3 flex items-center justify-between rounded-xl border px-3 py-2.5 transition-shadow"
        >
          <div>
            <div className="flex items-center gap-1.5 text-sm font-medium text-[var(--text-primary)]">
              <span className="relative flex h-2 w-2">
                {active && (
                  <span
                    className="absolute inline-flex h-full w-full animate-ping rounded-full opacity-65 bg-[var(--status-good)]"
                  />
                )}
                <span
                  className="relative h-2 w-2 rounded-full"
                  style={{ background: active ? "var(--status-good)" : "var(--text-muted)" }}
                />
              </span>
              Automation {active ? "active" : "paused"}
            </div>
            <div className="mt-0.5 text-xs text-[var(--text-muted)] truncate max-w-[130px]" title={watchFolder}>
              Watching {folderLabel}
            </div>
          </div>
          <Switch checked={active} onCheckedChange={toggleAutomation} />
        </motion.div>

        <div className="mb-3">
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-[var(--text-muted)]">Storage saved</span>
            <span className="font-medium text-[var(--brand)]">
              {formatBytes(storageSaved)}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-[var(--gridline)]">
            <motion.div
              className="h-full rounded-full bg-[var(--brand)]"
              initial={{ width: 0 }}
              animate={{ width: `${Math.min(100, (storageSaved / (500 * 1024 * 1024)) * 100)}%` }}
              transition={{ duration: 0.8, ease: "easeOut" }}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 border-t border-[var(--border)] pt-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--series-4)]/20 text-xs font-semibold text-[var(--series-4)]">
            {(user?.email?.[0] || "?").toUpperCase()}
          </span>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate text-sm font-medium text-[var(--text-primary)]" title={user?.email}>
              {user?.email || "…"}
            </div>
            <button
              type="button"
              onClick={logout}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:underline"
            >
              Sign out
            </button>
          </div>
        </div>
      </div>
    </aside>
  );
}
