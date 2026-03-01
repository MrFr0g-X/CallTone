import { cn } from "@/lib/utils";
import { motion, HTMLMotionProps } from "framer-motion";
import { forwardRef, ReactNode } from "react";

interface GlassCardProps extends Omit<HTMLMotionProps<"div">, "children" | "className" | "onClick"> {
  children: ReactNode;
  className?: string;
  glow?: "primary" | "success" | "warning" | "destructive" | "accent" | "none";
  hover?: boolean;
  animate?: boolean;
  onClick?: () => void;
}

const GlassCard = forwardRef<HTMLDivElement, GlassCardProps>(
  ({ children, className, glow = "none", hover = false, animate = true, onClick, ...rest }, ref) => {
    const glowClasses = {
      primary: "glow-primary",
      success: "glow-success",
      warning: "glow-warning",
      destructive: "glow-destructive",
      accent: "glow-accent",
      none: "",
    };

    return (
      <motion.div
        ref={ref}
        initial={animate ? { opacity: 0, y: 16 } : undefined}
        animate={animate ? { opacity: 1, y: 0 } : undefined}
        transition={{ duration: 0.5, ease: [0.25, 0.46, 0.45, 0.94] }}
        whileHover={hover ? { y: -2, transition: { type: "spring", stiffness: 400, damping: 25 } } : undefined}
        whileTap={hover ? { scale: 0.98, transition: { type: "spring", stiffness: 400, damping: 25 } } : undefined}
        className={cn(
          "glass rounded-2xl",
          glowClasses[glow],
          hover && "cursor-pointer",
          className
        )}
        onClick={onClick}
        {...rest}
      >
        {children}
      </motion.div>
    );
  }
);

GlassCard.displayName = "GlassCard";

export default GlassCard;
