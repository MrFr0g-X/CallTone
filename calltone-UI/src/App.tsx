import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate, useLocation, useParams } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Home from "./pages/Home";
import Login from "./pages/Login";
import AgentDashboard from "./pages/AgentDashboard";
import QADashboard from "./pages/QADashboard";
import AdminLayout from "./components/AdminLayout";
import AdminClients from "./pages/AdminClients";
import AdminDashboard from "./pages/AdminDashboard";
import AdminTeam from "./pages/AdminTeam";
import AdminActivity from "./pages/AdminActivity";
import AdminSettings from "./pages/AdminSettings";
import CallDetail from "./pages/CallDetail";
import NotFound from "./pages/NotFound";
import NotAuthorized from "./pages/NotAuthorized";
import AcceptInvite from "./pages/AcceptInvite";
import UploadCall from "./pages/UploadCall";
import CompanyContext from "./pages/CompanyContext";
import SampleReport from "./pages/SampleReport";

const queryClient = new QueryClient();

// Backward-compat: the call-detail page used to live under /qa/call/:id, which wrongly
// implied a QA-only URL for agents/admins. Old links now redirect to the role-neutral
// /call/:id. Backend still authorizes each call per user.
const LegacyCallRedirect = () => {
  const { callId } = useParams();
  return <Navigate to={`/call/${callId}`} replace />;
};

const AnimatedRoutes = () => {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {/* Public routes */}
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/not-authorized" element={<NotAuthorized />} />
        <Route path="/accept-invite" element={<AcceptInvite />} />
        {/* Public, self-contained sample report — no auth, no API, no real data */}
        <Route path="/sample" element={<SampleReport />} />

        {/* Role-neutral call detail (any role that can view a call; backend authorizes per call) */}
        <Route path="/call/:callId" element={
          <ProtectedRoute allowedRoles={["qa", "agent", "owner", "admin", "super_admin", "manager", "viewer"]}>
            <CallDetail />
          </ProtectedRoute>
        } />

        {/* Agent routes */}
        <Route path="/agent/dashboard" element={
          <ProtectedRoute allowedRoles={["agent"]}>
            <AgentDashboard />
          </ProtectedRoute>
        } />

        {/* QA routes */}
        <Route path="/qa/dashboard" element={
          <ProtectedRoute allowedRoles={["qa"]}>
            <QADashboard />
          </ProtectedRoute>
        } />
        {/* Legacy QA-scoped path now redirects to the role-neutral /call/:callId */}
        <Route path="/qa/call/:callId" element={<LegacyCallRedirect />} />
        <Route path="/qa/upload" element={
          <ProtectedRoute allowedRoles={["qa", "owner", "admin", "super_admin"]}>
            <UploadCall />
          </ProtectedRoute>
        } />
        <Route path="/qa/context" element={
          <ProtectedRoute allowedRoles={["qa", "owner", "admin", "super_admin"]}>
            <CompanyContext />
          </ProtectedRoute>
        } />

        {/* Admin routes */}
        <Route path="/admin" element={
          <ProtectedRoute allowedRoles={["owner", "admin", "super_admin", "manager", "viewer"]}>
          <AdminLayout />
          </ProtectedRoute>
        }>
          <Route path="dashboard" element={<AdminDashboard />} />
          <Route path="context" element={
            <ProtectedRoute allowedRoles={["owner", "admin", "super_admin"]}>
              <CompanyContext chromeless />
            </ProtectedRoute>
          } />
          <Route path="clients" element={<AdminClients />} />
          <Route path="team" element={<AdminTeam />} />
          <Route path="activity" element={<AdminActivity />} />
          <Route path="settings" element={
            <ProtectedRoute allowedRoles={["owner", "admin", "super_admin"]}>
              <AdminSettings />
            </ProtectedRoute>
          } />
          <Route index element={<Navigate to="dashboard" replace />} />
        </Route>

        {/* Catch-all */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </AnimatePresence>
  );
};

const App = () => (
  <ThemeProvider>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <AuthProvider>
            <AnimatedRoutes />
          </AuthProvider>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  </ThemeProvider>
);

export default App;
