import { Route, Routes } from "react-router-dom";
import "./lib/gsap.js";
import { AuthProvider } from "./context/AuthContext.jsx";
import ProtectedRoute from "./components/ProtectedRoute.jsx";
import DashboardLayout from "./layouts/DashboardLayout.jsx";
import Landing from "./pages/Landing.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import ForgotPassword from "./pages/ForgotPassword.jsx";
import ResetPassword from "./pages/ResetPassword.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import ActivityLog from "./pages/ActivityLog.jsx";
import Rules from "./pages/Rules.jsx";
import Categories from "./pages/Categories.jsx";
import Reports from "./pages/Reports.jsx";
import History from "./pages/History.jsx";
import Settings from "./pages/Settings.jsx";
import Welcome from "./pages/Welcome.jsx";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/app/welcome" element={<Welcome />} />
          <Route path="/app" element={<DashboardLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="activity" element={<ActivityLog />} />
            <Route path="rules" element={<Rules />} />
            <Route path="categories" element={<Categories />} />
            <Route path="reports" element={<Reports />} />
            <Route path="history" element={<History />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}
