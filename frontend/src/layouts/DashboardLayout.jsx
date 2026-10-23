import { Outlet, useLocation } from "react-router-dom";
import Header from "../components/Header.jsx";
import TopNav from "../components/TopNav.jsx";
import { RulesProvider } from "../context/RulesContext.jsx";

// v5 shell: brand bar, trapezoid tab strip, then one big page sheet. No
// background on the wrapper, so the body's dotted paper texture shows
// around the sheet. When the first tab is active the sheet's top-left
// corner is square, so the tab and sheet read as one piece.
export default function DashboardLayout() {
  const { pathname } = useLocation();
  const firstTab = pathname === "/app" || pathname === "/app/";
  return (
    <RulesProvider>
      <div className="min-h-screen">
        <Header />
        <TopNav />
        <main className="mx-auto max-w-[1360px] px-4 pb-12 sm:px-6">
          <div
            className="min-h-[72vh] min-w-0 bg-[var(--sheet)] text-[var(--ink)]"
            style={{
              borderRadius: firstTab ? "0 6px 6px 6px" : "6px",
              boxShadow: "0 1px 0 var(--rule-2), 0 24px 48px -32px var(--shade)",
              padding: "clamp(16px, 3vw, 30px)",
            }}
          >
            <Outlet />
          </div>
        </main>
      </div>
    </RulesProvider>
  );
}
