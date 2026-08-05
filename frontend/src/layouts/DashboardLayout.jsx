import { Outlet } from "react-router-dom";
import Sidebar from "../components/Sidebar.jsx";
import { RulesProvider } from "../context/RulesContext.jsx";

export default function DashboardLayout() {
  return (
    <RulesProvider>
      <div className="flex min-h-screen bg-[var(--page)]">
        <Sidebar />
        <div className="flex-1">
          <Outlet />
        </div>
      </div>
    </RulesProvider>
  );
}
