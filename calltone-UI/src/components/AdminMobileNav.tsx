import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { AnimatePresence, motion } from "framer-motion";
import {
  Building2, LayoutDashboard, Users, Settings, LogOut,
  Menu, X, Activity
} from "lucide-react";
import { cn } from "@/lib/utils";
import { roleConfig } from "@/data/adminMockData";
import ThemeToggle from "@/components/ThemeToggle";
import calltoneIcon from "@/assets/calltone-icon.png";
import { canManageAdminUsers } from "@/lib/roles";

const navItems = [
  { to: "/admin/dashboard", label: "Overview", icon: LayoutDashboard },
  { to: "/admin/clients", label: "Clients", icon: Building2 },
  { to: "/admin/team", label: "Team", icon: Users },
  { to: "/admin/activity", label: "Activity Log", icon: Activity },
  { to: "/admin/settings", label: "Settings", icon: Settings },
];

const AdminMobileNav = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout, user } = useAuth();
  const [open, setOpen] = useState(false);
  const adminRole = (user?.role ?? "viewer") as keyof typeof roleConfig;
  const role = roleConfig[adminRole] ?? roleConfig.viewer;
  const userName = user?.name ?? "Admin";
  const visibleNavItems = navItems.filter((item) => item.to !== "/admin/settings" || canManageAdminUsers(user?.role));

  const handleLogout = async () => {
    setOpen(false);
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <nav className="bg-background/60 backdrop-blur-2xl border-b border-border/50">
      <div className="px-5 h-14 flex items-center justify-between">
        <Link to="/admin/dashboard" className="flex items-center gap-2">
          <img src={calltoneIcon} alt="CallTone" className="w-8 h-8" />
        </Link>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <button
            onClick={() => setOpen(!open)}
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground transition-colors"
            aria-label={open ? "Close menu" : "Open menu"}
          >
            <AnimatePresence mode="wait" initial={false}>
              {open ? (
                <motion.div key="close" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.2 }}>
                  <X className="w-5 h-5" />
                </motion.div>
              ) : (
                <motion.div key="menu" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }} transition={{ duration: 0.2 }}>
                  <Menu className="w-5 h-5" />
                </motion.div>
              )}
            </AnimatePresence>
          </button>
        </div>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="overflow-hidden border-t border-border/50 bg-background/80 backdrop-blur-2xl"
          >
            <div className="px-5 py-5 space-y-1.5">
              {visibleNavItems.map((item, i) => (
                <motion.div
                  key={item.to}
                  initial={{ opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.3 }}
                >
                  <Link
                    to={item.to}
                    onClick={() => setOpen(false)}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all",
                      location.pathname === item.to
                        ? "bg-foreground/[0.08] text-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04]"
                    )}
                  >
                    <item.icon className="w-4 h-4" />
                    {item.label}
                  </Link>
                </motion.div>
              ))}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2, duration: 0.3 }}
                className="border-t border-border/50 pt-4 mt-3 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
                    <span className="text-xs font-bold text-accent">
                      {userName.split(" ").map(n => n[0]).join("")}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-medium">{userName}</p>
                    <p className={cn("text-xs font-medium", role.color)}>{role.label}</p>
                  </div>
                </div>
                <button
                  onClick={handleLogout}
                  className="p-2 rounded-xl text-muted-foreground hover:text-foreground transition-all"
                  aria-label="Sign out"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
};

export default AdminMobileNav;
