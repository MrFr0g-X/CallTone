import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AnimatePresence } from "framer-motion";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import AgentDashboard from "./pages/AgentDashboard";
import QADashboard from "./pages/QADashboard";
import AdminLayout from "./components/AdminLayout";
import AdminDashboard from "./pages/AdminDashboard";
import AdminClients from "./pages/AdminClients";
import AdminTeam from "./pages/AdminTeam";
import AdminPermissions from "./pages/AdminPermissions";
import AdminActivity from "./pages/AdminActivity";
import AdminSettings from "./pages/AdminSettings";
import CallDetail from "./pages/CallDetail";
import NotFound from "./pages/NotFound";
import NotAuthorized from "./pages/NotAuthorized";
import AcceptInvite from "./pages/AcceptInvite";
import UploadCall from "./pages/UploadCall";
import CompanyContext from "./pages/CompanyContext";

const queryClient = new QueryClient();

const AnimatedRoutes = () => {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        {/* Public routes */}
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/not-authorized" element={<NotAuthorized />} />
        <Route path="/accept-invite" element={<AcceptInvite />} />

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
        <Route path="/qa/call/:callId" element={
          <ProtectedRoute allowedRoles={["qa"]}>
            <CallDetail />
          </ProtectedRoute>
        } />
        <Route path="/qa/upload" element={
          <ProtectedRoute allowedRoles={["qa", "admin", "super_admin"]}>
            <UploadCall />
          </ProtectedRoute>
        } />
        <Route path="/qa/context" element={
          <ProtectedRoute allowedRoles={["qa", "admin", "super_admin"]}>
            <CompanyContext />
          </ProtectedRoute>
        } />

        {/* Admin routes */}
        <Route path="/admin" element={
          <ProtectedRoute allowedRoles={["admin", "super_admin", "manager", "viewer"]}>
          <AdminLayout />
          </ProtectedRoute>
        }>
          <Route path="dashboard" element={<AdminDashboard />} />
          <Route path="clients" element={<AdminClients />} />
          <Route path="team" element={<AdminTeam />} />
          <Route path="permissions" element={<AdminPermissions />} />
          <Route path="activity" element={<AdminActivity />} />
          <Route path="settings" element={<AdminSettings />} />
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
