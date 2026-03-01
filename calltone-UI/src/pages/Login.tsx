import { useState } from "react";
import { useNavigate, Navigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Eye, EyeOff } from "lucide-react";
import calltoneLogo from "@/assets/calltone-logo.png";
import { useToast } from "@/hooks/use-toast";
import AnimatedBackground from "@/components/AnimatedBackground";
import PageTransition from "@/components/PageTransition";
import { useAuth } from "@/contexts/AuthContext";

const Login = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { login, isAuthenticated, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  // Redirect if already logged in
  if (isAuthenticated && user) {
    const dest = user.role === "admin" ? "/admin/dashboard" : user.role === "qa" ? "/qa/dashboard" : "/agent/dashboard";
    return <Navigate to={dest} replace />;
  }

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast({ title: "Missing credentials", description: "Please enter both email and password.", variant: "destructive" });
      return;
    }
    setIsLoading(true);
    setTimeout(() => {
      login(email);
      toast({ title: "Welcome back", description: "You've been signed in successfully." });
      if (email.includes("admin")) {
        navigate("/admin/dashboard");
      } else if (email.includes("qa")) {
        navigate("/qa/dashboard");
      } else {
        navigate("/agent/dashboard");
      }
      setIsLoading(false);
    }, 800);
  };

  return (
    <PageTransition>
      <div className="min-h-screen flex items-center justify-center relative px-4">
        <AnimatedBackground />

        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.7, ease: [0.25, 0.46, 0.45, 0.94] }}
          className="glass-strong rounded-3xl p-8 sm:p-10 w-full max-w-[420px] glow-primary"
        >
          {/* Logo */}
          <div className="text-center mb-10">
            <div className="flex items-center justify-center mb-3">
              <img src={calltoneLogo} alt="CallTone" className="h-56 -my-16" />
            </div>
            <p className="text-muted-foreground text-sm font-light">AI-Powered Call Quality Assurance</p>
          </div>

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@calltone.tech"
                className="w-full h-12 px-4 rounded-xl glass-input text-sm"
                required
              />
            </div>

            <div>
              <label className="text-xs font-medium text-muted-foreground mb-2 block uppercase tracking-wider">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full h-12 px-4 pr-11 rounded-xl glass-input text-sm"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <motion.button
              type="submit"
              disabled={isLoading}
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.98 }}
              transition={{ type: "spring", stiffness: 400, damping: 25 }}
              className="relative w-full h-12 rounded-xl bg-gradient-to-r from-primary to-accent text-primary-foreground font-semibold text-sm transition-all duration-300 hover:brightness-110 disabled:opacity-50 shadow-lg shadow-primary/30 overflow-hidden"
              onClick={(e) => {
                const btn = e.currentTarget;
                const rect = btn.getBoundingClientRect();
                const ripple = document.createElement("span");
                const size = Math.max(rect.width, rect.height);
                ripple.style.width = ripple.style.height = `${size}px`;
                ripple.style.left = `${e.clientX - rect.left - size / 2}px`;
                ripple.style.top = `${e.clientY - rect.top - size / 2}px`;
                ripple.className = "absolute rounded-full bg-white/30 animate-[ripple_0.6s_ease-out] pointer-events-none";
                btn.appendChild(ripple);
                setTimeout(() => ripple.remove(), 600);
              }}
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                  Signing in...
                </span>
              ) : (
                "Sign In"
              )}
            </motion.button>
          </form>

          <p className="text-center text-[11px] text-muted-foreground mt-8 font-light">
            Demo: use "admin" for Admin, "qa" for QA, otherwise Agent view
          </p>
        </motion.div>
      </div>
    </PageTransition>
  );
};

export default Login;
