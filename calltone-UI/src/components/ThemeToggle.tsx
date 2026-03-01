import { useId } from "react";
import { Sun, Moon, Monitor } from "lucide-react";
import { motion } from "framer-motion";
import { useTheme } from "@/components/ThemeProvider";
import { cn } from "@/lib/utils";

const ThemeToggle = () => {
  const { theme, setTheme } = useTheme();
  const toggleId = useId();

  const options = [
    { value: "light" as const, icon: Sun, label: "Light" },
    { value: "dark" as const, icon: Moon, label: "Dark" },
    { value: "system" as const, icon: Monitor, label: "System" },
  ];

  return (
    <div className="flex items-center gap-0.5 p-0.5 rounded-xl bg-black/[0.06] dark:bg-white/[0.06]">
      {options.map((opt) => {
        const isActive = theme === opt.value;
        return (
          <button
            key={opt.value}
            onClick={(e) => setTheme(opt.value, e)}
            className="relative p-1.5 rounded-lg"
            aria-label={`Switch to ${opt.label} mode`}
            title={opt.label}
          >
            {isActive && (
              <motion.span
                layoutId={`${toggleId}-theme-pill`}
                className="absolute inset-0 rounded-lg bg-white dark:bg-white/[0.12] shadow-sm"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <motion.span
              className="relative block"
              animate={{
                color: isActive ? "hsl(var(--foreground))" : "hsl(var(--muted-foreground))",
                scale: isActive ? 1.1 : 1,
                rotate: isActive ? (opt.value === "light" ? 15 : opt.value === "dark" ? -15 : 0) : 0,
              }}
              transition={{ duration: 0.3, ease: [0.25, 0.46, 0.45, 0.94] }}
            >
              <opt.icon className="w-3.5 h-3.5" />
            </motion.span>
          </button>
        );
      })}
    </div>
  );
};

export default ThemeToggle;
