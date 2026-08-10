import { lazy, Suspense } from "react";
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

const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
const ActivityLog = lazy(() => import("./pages/ActivityLog.jsx"));
const Rules = lazy(() => import("./pages/Rules.jsx"));
const Categories = lazy(() => import("./pages/Categories.jsx"));
const CategoryDetail = lazy(() => import("./pages/CategoryDetail.jsx"));
const Reports = lazy(() => import("./pages/Reports.jsx"));
const History = lazy(() => import("./pages/History.jsx"));
const Settings = lazy(() => import("./pages/Settings.jsx"));
const Welcome = lazy(() => import("./pages/Welcome.jsx"));

function RouteFallback() {
  return <div className="p-8 text-sm text-[var(--text-muted)]">Loading…</div>;
}

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
          <Route
            path="/app/welcome"
            element={
              <Suspense fallback={<RouteFallback />}>
                <Welcome />
              </Suspense>
            }
          />
          <Route path="/app" element={<DashboardLayout />}>
            <Route
              index
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Dashboard />
                </Suspense>
              }
            />
            <Route
              path="activity"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <ActivityLog />
                </Suspense>
              }
            />
            <Route
              path="rules"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Rules />
                </Suspense>
              }
            />
            <Route
              path="categories"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Categories />
                </Suspense>
              }
            />
            <Route
              path="categories/:category"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <CategoryDetail />
                </Suspense>
              }
            />
            <Route
              path="reports"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Reports />
                </Suspense>
              }
            />
            <Route
              path="history"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <History />
                </Suspense>
              }
            />
            <Route
              path="settings"
              element={
                <Suspense fallback={<RouteFallback />}>
                  <Settings />
                </Suspense>
              }
            />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}
