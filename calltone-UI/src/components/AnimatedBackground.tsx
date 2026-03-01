import { useTheme } from "@/components/ThemeProvider";

const AnimatedBackground = () => {
  const { resolved } = useTheme();
  const isDark = resolved === "dark";

  return (
    <div className="fixed inset-0 -z-10 overflow-hidden transition-colors duration-500">
      {/* Base gradient */}
      <div
        className="absolute inset-0 transition-all duration-500"
        style={{
          background: isDark
            ? "linear-gradient(135deg, hsl(225,80%,5%) 0%, hsl(222,60%,8%) 50%, hsl(218,70%,10%) 100%)"
            : "linear-gradient(135deg, hsl(220,20%,97%) 0%, hsl(220,25%,94%) 50%, hsl(224,30%,92%) 100%)",
        }}
      />

      {/* Subtle grain texture overlay */}
      <div
        className="absolute inset-0 transition-opacity duration-500"
        style={{
          opacity: isDark ? 0.015 : 0.03,
          backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E\")",
        }}
      />

      {/* Floating orbs */}
      <div
        className="absolute w-[600px] h-[600px] rounded-full blur-[120px] transition-opacity duration-500"
        style={{
          background: `radial-gradient(circle, hsl(224 76% ${isDark ? "48%" : "65%"}) 0%, transparent 70%)`,
          opacity: isDark ? 0.12 : 0.08,
          top: "5%",
          left: "10%",
          animation: "float 30s ease-in-out infinite",
        }}
      />
      <div
        className="absolute w-[500px] h-[500px] rounded-full blur-[120px] transition-opacity duration-500"
        style={{
          background: `radial-gradient(circle, hsl(192 91% ${isDark ? "36%" : "55%"}) 0%, transparent 70%)`,
          opacity: isDark ? 0.08 : 0.06,
          top: "45%",
          right: "5%",
          animation: "float 35s ease-in-out infinite reverse",
        }}
      />
      <div
        className="absolute w-[450px] h-[450px] rounded-full blur-[100px] transition-opacity duration-500"
        style={{
          background: `radial-gradient(circle, hsl(187 92% ${isDark ? "43%" : "60%"}) 0%, transparent 70%)`,
          opacity: isDark ? 0.06 : 0.05,
          bottom: "5%",
          left: "35%",
          animation: "float 28s ease-in-out infinite",
          animationDelay: "-5s",
        }}
      />
    </div>
  );
};

export default AnimatedBackground;
