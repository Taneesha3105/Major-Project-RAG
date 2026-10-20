import { Compass } from "lucide-react";
import { Suspense, lazy } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { EmptyState, PageLoader } from "./components/ui/primitives";
import { useAuth } from "./context/AuthContext";
import AppLayout from "./layouts/AppLayout";
import { P } from "./lib/constants";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";

// Route-level code splitting keeps the initial bundle small (charts/markdown load on demand).
const AdminUsersPage = lazy(() => import("./pages/AdminUsersPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));
const DealsPage = lazy(() => import("./pages/DealsPage"));
const SettingsPage = lazy(() => import("./pages/SettingsPage"));
const DealWorkspacePage = lazy(() => import("./pages/deal/DealWorkspacePage"));
const OverviewTab = lazy(() => import("./pages/deal/OverviewTab"));
const DataRoomTab = lazy(() => import("./pages/deal/DataRoomTab"));
const AssistantTab = lazy(() => import("./pages/deal/AssistantTab"));
const RisksTab = lazy(() => import("./pages/deal/RisksTab"));
const ChecklistTab = lazy(() => import("./pages/deal/ChecklistTab"));
const TeamTab = lazy(() => import("./pages/deal/TeamTab"));
const ActivityTab = lazy(() => import("./pages/deal/ActivityTab"));

function RequireAuth({ children, permission }) {
  const { user, loading, can } = useAuth();
  const location = useLocation();
  if (loading) return <PageLoader label="Loading your workspace…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (permission && !can(permission)) return <Navigate to="/" replace />;
  return children;
}

function GuestOnly({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <PageLoader />;
  return user ? <Navigate to="/" replace /> : children;
}

function NotFound() {
  return (
    <div className="page">
      <EmptyState icon={Compass} title="Page not found" description="The page you are looking for does not exist." action={<Link to="/" className="btn btn-primary">Back to dashboard</Link>} />
    </div>
  );
}

export default function App() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
      <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
      <Route path="/register" element={<GuestOnly><RegisterPage /></GuestOnly>} />
      <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
        <Route index element={<DashboardPage />} />
        <Route path="deals" element={<DealsPage />} />
        <Route path="deals/:dealId" element={<DealWorkspacePage />}>
          <Route index element={<OverviewTab />} />
          <Route path="data-room" element={<DataRoomTab />} />
          <Route path="assistant" element={<AssistantTab />} />
          <Route path="risks" element={<RisksTab />} />
          <Route path="checklist" element={<ChecklistTab />} />
          <Route path="team" element={<TeamTab />} />
          <Route path="activity" element={<ActivityTab />} />
        </Route>
        <Route path="admin/users" element={<RequireAuth permission={P.USER_MANAGE}><AdminUsersPage /></RequireAuth>} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
      </Routes>
    </Suspense>
  );
}
