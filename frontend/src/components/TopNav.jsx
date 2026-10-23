import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { getOrganizationHealth } from "../services/api.js";

const tabs = [
  { to: "/app", label: "Dashboard", end: true },
  { to: "/app/activity", label: "Activity" },
  { to: "/app/history", label: "History" },
  { to: "/app/rules", label: "Rules" },
  { to: "/app/categories", label: "Categories" },
  { to: "/app/reports", label: "Reports" },
  { to: "/app/settings", label: "Settings" },
];

// Trapezoid folder tabs. The active tab is --sheet and sits flush on the
// page sheet below it (no gap, no border line), so the two read as one.
export default function TopNav() {
  const [conflicts, setConflicts] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getOrganizationHealth()
      .then((h) => {
        if (cancelled) return;
        setConflicts(h?.rules?.status === "available" ? h.rules.conflicts_total || 0 : 0);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <nav aria-label="Primary" className="ff-scroll-x ff-fade-edge mx-auto mt-4 flex max-w-[1360px] gap-[2px] px-4 sm:px-6">
      {tabs.map(({ to, label, end }, i) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            `flex h-[42px] flex-none items-center gap-2 px-6 text-[12px] uppercase tracking-[0.07em] no-underline transition-colors ${
              isActive
                ? "bg-[var(--sheet)] font-extrabold text-[var(--ink)]"
                : "bg-[var(--tab)] font-semibold text-[var(--ink-2)] hover:bg-[var(--tab-h)]"
            }`
          }
          style={{ clipPath: "polygon(10px 0, calc(100% - 10px) 0, 100% 100%, 0 100%)", fontStretch: "116%" }}
        >
          <span className="font-mono-data text-[10px] font-medium tracking-normal opacity-55">
            {String(i + 1).padStart(2, "0")}
          </span>
          {label}
          {label === "Rules" && conflicts > 0 && (
            <span
              title={`${conflicts} rule conflict${conflicts === 1 ? "" : "s"}`}
              className="grid h-[18px] min-w-[18px] place-items-center rounded-full bg-[var(--stamp)] px-[5px] text-[10px] font-bold tracking-normal text-white"
            >
              {conflicts}
            </span>
          )}
        </NavLink>
      ))}
    </nav>
  );
}
