import { useLocation, Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { useAuth } from "@/contexts/AuthContext";
import {
  LayoutDashboard, Users, Settings, LogOut,
  ChevronLeft, ChevronRight, Activity
} from "lucide-react";
import { cn } from "@/lib/utils";
import { roleConfig } from "@/data/adminMockData";
import ThemeToggle from "@/components/ThemeToggle";
import calltoneIcon from "@/assets/calltone-icon.png";
import calltoneLogo from "@/assets/calltone-logo.png";
import { useState } from "react";

const navItems = [
  { to: "/admin/dashboard", label: "Overview", icon: LayoutDashboard },
  { to: "/admin/team", label: "Team", icon: Users },
  { to: "/admin/activity", label: "Activity Log", icon: Activity },
  { to: "/admin/settings", label: "Settings", icon: Settings },
];

const AdminSidebar = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const [collapsed, setCollapsed] = useState(false);
  const adminRole = (user?.role ?? "viewer") as keyof typeof roleConfig;
  const role = roleConfig[adminRole] ?? roleConfig.viewer;
  const userName = user?.name ?? "Admin";

  return (
    <aside
      className={cn(
        "sticky top-0 h-screen flex flex-col border-r border-border/50 bg-sidebar-background/80 backdrop-blur-2xl transition-all duration-300 z-40 shrink-0",
        collapsed ? "w-[68px]" : "w-[240px]"
      )}
    >
      {/* Logo */}
      <div className="h-14 flex items-center justify-between px-4 border-b border-border/50">
        <Link to="/admin/dashboard" className="flex items-center gap-2 overflow-hidden">
          {collapsed ? (
            <img src={calltoneIcon} alt="CallTone" className="w-8 h-8" />
          ) : (
            <img src={calltoneLogo} alt="CallTone" className="h-28 -my-8" />
          )}
        </Link>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-sidebar-accent transition-colors hidden lg:flex"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = location.pathname === item.to;
          return (
            <Link
              key={item.to}
              to={item.to}
              className={cn(
                "relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 group",
                isActive
                  ? "text-sidebar-primary-foreground"
                  : "text-muted-foreground hover:text-foreground hover:bg-sidebar-accent"
              )}
            >
              {isActive && (
                <motion.span
                  layoutId="admin-nav-active"
                  className="absolute inset-0 rounded-xl bg-sidebar-primary"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <item.icon className={cn("w-4 h-4 relative z-10 shrink-0", isActive && "text-sidebar-primary-foreground")} />
              <AnimatePresence>
                {!collapsed && (
                  <motion.span
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: "auto" }}
                    exit={{ opacity: 0, width: 0 }}
                    className="relative z-10 whitespace-nowrap overflow-hidden"
                  >
                    {item.label}
                  </motion.span>
                )}
              </AnimatePresence>
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="border-t border-border/50 p-3 space-y-3">
        <div className="flex items-center justify-center">
          <ThemeToggle />
        </div>
        <div className={cn("flex items-center gap-3 px-2", collapsed && "justify-center")}>
          <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center shrink-0">
            <span className="text-xs font-bold text-accent">
              {userName.split(" ").map(n => n[0]).join("")}
            </span>
          </div>
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold truncate">{userName}</p>
              <p className={cn("text-[10px] font-medium", role.color)}>{role.label}</p>
            </div>
          )}
          {!collapsed && (
            <button
              onClick={() => { logout(); navigate("/login"); }}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-sidebar-accent transition-colors"
              aria-label="Sign out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
};

export default AdminSidebar;
