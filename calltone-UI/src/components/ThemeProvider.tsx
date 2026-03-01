import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";

type Theme = "light" | "dark" | "system";

interface ThemeContextType {
  theme: Theme;
  resolved: "light" | "dark";
  setTheme: (theme: Theme, event?: React.MouseEvent) => void;
}

const ThemeContext = createContext<ThemeContextType>({
  theme: "system",
  resolved: "dark",
  setTheme: () => {},
});

export const useTheme = () => useContext(ThemeContext);

const STORAGE_KEY = "calltone-theme";

const getEffective = (theme: Theme): "light" | "dark" => {
  if (theme === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return theme;
};

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
  const [theme, setThemeState] = useState<Theme>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return (stored as Theme) || "system";
  });

  const [resolved, setResolved] = useState<"light" | "dark">(() => getEffective(
    (localStorage.getItem(STORAGE_KEY) as Theme) || "system"
  ));

  const applyTheme = useCallback((t: Theme) => {
    const effective = getEffective(t);
    setResolved(effective);
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(effective);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme(theme);
    applyTheme(theme);
    mediaQuery.addEventListener("change", handler);
    return () => mediaQuery.removeEventListener("change", handler);
  }, [theme, applyTheme]);

  const setTheme = useCallback((t: Theme, event?: React.MouseEvent) => {
    const newEffective = getEffective(t);
    const oldEffective = getEffective(theme);

    // If no actual change, just update
    if (newEffective === oldEffective) {
      setThemeState(t);
      localStorage.setItem(STORAGE_KEY, t);
      return;
    }

    // Try View Transition API for smooth animation
    if (document.startViewTransition && event) {
      const x = event.clientX;
      const y = event.clientY;
      const endRadius = Math.hypot(
        Math.max(x, window.innerWidth - x),
        Math.max(y, window.innerHeight - y)
      );

      const transition = document.startViewTransition(() => {
        setThemeState(t);
        localStorage.setItem(STORAGE_KEY, t);
        applyTheme(t);
      });

      transition.ready.then(() => {
        document.documentElement.animate(
          {
            clipPath: [
              `circle(0px at ${x}px ${y}px)`,
              `circle(${endRadius}px at ${x}px ${y}px)`,
            ],
          },
          {
            duration: 500,
            easing: "cubic-bezier(0.25, 0.46, 0.45, 0.94)",
            pseudoElement: "::view-transition-new(root)",
          }
        );
      });
    } else {
      // Fallback: fade via opacity
      document.documentElement.style.transition = "opacity 0.3s ease";
      document.documentElement.style.opacity = "0.6";
      setTimeout(() => {
        setThemeState(t);
        localStorage.setItem(STORAGE_KEY, t);
        applyTheme(t);
        document.documentElement.style.opacity = "1";
        setTimeout(() => {
          document.documentElement.style.transition = "";
        }, 300);
      }, 150);
    }
  }, [theme, applyTheme]);

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};
