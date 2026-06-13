import { useState, useId } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { LogOut, BarChart3, Users, Menu, X, Upload, Building2 } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";
import ThemeToggle from "@/components/ThemeToggle";
import calltoneIcon from "@/assets/calltone-icon.png";
import calltoneLogo from "@/assets/calltone-logo.png";
import { useAuth } from "@/contexts/AuthContext";
interface NavbarProps {
  userName: string;
  userRole: "agent" | "qa" | "admin";
}

const Navbar = ({ userName, userRole }: NavbarProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const navId = useId();
  const { logout, user } = useAuth();

  const handleSignOut = async () => {
    await logout();
    navigate("/login", { replace: true });
  };

  const agentLinks = [
    { to: "/agent/dashboard", label: "Dashboard", icon: BarChart3 },
  ];

  const canUploadCalls = Boolean(user?.capabilities?.canUploadCalls);
  const canManageContext = Boolean(user?.capabilities?.canManageContext);

  // Company Context is a core QA surface (view the policy the AI scores against +
  // submit change tickets), so QA always sees it regardless of edit rights. The page
  // itself gates the "Replace Context" tab on canManageContext.
  const qaLinks = [
    { to: "/qa/dashboard", label: "Dashboard", icon: Users },
    ...(canUploadCalls ? [{ to: "/qa/upload", label: "Upload", icon: Upload }] : []),
    { to: "/qa/context", label: "Context", icon: Building2 },
  ];

  const adminLinks = [
    { to: "/admin/dashboard", label: "Admin", icon: BarChart3 },
    ...(canUploadCalls ? [{ to: "/qa/upload", label: "Upload", icon: Upload }] : []),
    ...(canManageContext ? [{ to: "/qa/context", label: "Context", icon: Building2 }] : []),
  ];

  const links = userRole === "agent" ? agentLinks : userRole === "admin" ? adminLinks : qaLinks;
  const homePath = userRole === "agent" ? "/agent/dashboard" : userRole === "admin" ? "/admin/dashboard" : "/qa/dashboard";
  const roleLabel = userRole === "agent" ? "Agent" : userRole === "admin" ? "Admin" : "QA Analyst";

  return (
    <nav className="sticky top-0 z-50 bg-background/60 backdrop-blur-2xl border-b border-border/50">
      <div className="max-w-7xl mx-auto px-5 sm:px-8 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link to={homePath} className="flex items-center gap-2">
          <img src={calltoneIcon} alt="CallTone" className="w-28 h-28 -my-8 md:hidden" />
          <img src={calltoneLogo} alt="CallTone" className="hidden md:block h-36 -my-12" />
        </Link>

        {/* Desktop Nav Links */}
        <div className="hidden md:flex items-center gap-1">
          {links.map((link) => {
            const isActive = location.pathname === link.to;
            return (
              <Link
                key={link.to}
                to={link.to}
                className="relative flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] font-medium"
              >
                {isActive && (
                  <motion.span
                    layoutId={`${navId}-nav-pill`}
                    className="absolute inset-0 rounded-xl bg-foreground/[0.08]"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <motion.span
                  className="relative flex items-center gap-2"
                  animate={{ color: isActive ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))" }}
                  transition={{ duration: 0.25 }}
                  whileHover={{ color: "hsl(var(--foreground))" }}
                >
                  <link.icon className="w-4 h-4" />
                  {link.label}
                </motion.span>
              </Link>
            );
          })}
        </div>

        {/* Desktop Right */}
        <div className="hidden md:flex items-center gap-3">
          <ThemeToggle />
          <div className="w-px h-6 bg-border/50" />
          <div className="text-right">
            <p className="text-[13px] font-medium text-foreground">{userName}</p>
            <p className="text-[11px] text-muted-foreground capitalize">{roleLabel}</p>
          </div>
          <motion.button
            onClick={handleSignOut}
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04] transition-colors duration-300"
            title="Sign out"
            aria-label="Sign out"
            whileHover={{ scale: 1.08 }}
            whileTap={{ scale: 0.92 }}
            transition={{ type: "spring", stiffness: 400, damping: 20 }}
          >
            <LogOut className="w-4 h-4" />
          </motion.button>
        </div>

        {/* Mobile Hamburger */}
        <div className="md:hidden flex items-center gap-2">
          <ThemeToggle />
          <motion.button
            className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04] transition-colors"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label={mobileOpen ? "Close menu" : "Open menu"}
            whileTap={{ scale: 0.9 }}
          >
            <AnimatePresence mode="wait" initial={false}>
              {mobileOpen ? (
                <motion.div key="close" initial={{ rotate: -90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: 90, opacity: 0 }} transition={{ duration: 0.2 }}>
                  <X className="w-5 h-5" />
                </motion.div>
              ) : (
                <motion.div key="menu" initial={{ rotate: 90, opacity: 0 }} animate={{ rotate: 0, opacity: 1 }} exit={{ rotate: -90, opacity: 0 }} transition={{ duration: 0.2 }}>
                  <Menu className="w-5 h-5" />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.button>
        </div>
      </div>

      {/* Mobile Drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
            className="md:hidden overflow-hidden border-t border-border/50 bg-background/80 backdrop-blur-2xl"
          >
            <div className="px-5 py-5 space-y-1.5">
              {links.map((link, i) => (
                <motion.div
                  key={link.to}
                  initial={{ opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.06, duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
                >
                  <Link
                    to={link.to}
                    onClick={() => setMobileOpen(false)}
                    className={cn(
                      "flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all",
                      location.pathname === link.to
                        ? "bg-foreground/[0.08] text-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04]"
                    )}
                  >
                    <link.icon className="w-4 h-4" />
                    {link.label}
                  </Link>
                </motion.div>
              ))}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.15, duration: 0.3 }}
                className="border-t border-border/50 pt-4 mt-3 flex items-center justify-between"
              >
                <div>
                  <p className="text-sm font-medium text-foreground">{userName}</p>
                  <p className="text-xs text-muted-foreground capitalize">{roleLabel}</p>
                </div>
                <motion.button
                  onClick={() => { setMobileOpen(false); handleSignOut(); }}
                  className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-foreground/[0.04] transition-all"
                  aria-label="Sign out"
                  whileTap={{ scale: 0.9 }}
                >
                  <LogOut className="w-4 h-4" />
                </motion.button>
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
};

export default Navbar;
