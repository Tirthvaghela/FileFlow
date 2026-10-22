import { Outlet } from "react-router-dom";
import Sidebar from "../components/Sidebar.jsx";
import { RulesProvider } from "../context/RulesContext.jsx";
import { SidebarProvider } from "../context/SidebarContext.jsx";

export default function DashboardLayout() {
  return (
    <RulesProvider>
      <SidebarProvider>
        <div className="flex min-h-screen bg-[var(--page)]">
          <Sidebar />
          {/* min-w-0: without it, a flex child that would rather not shrink
              (a wide table, a long watch-folder path) forces the whole row
              wider than the viewport instead of scrolling internally --
              the actual cause of the mobile horizontal-overflow bug. */}
          <div className="min-w-0 flex-1">
            <Outlet />
          </div>
        </div>
      </SidebarProvider>
    </RulesProvider>
  );
}
