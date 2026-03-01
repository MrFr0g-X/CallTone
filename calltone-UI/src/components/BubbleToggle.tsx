import { useId } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface BubbleToggleProps {
  options: string[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
  labels?: Record<string, string>;
}

const BubbleToggle = ({ options, value, onChange, className, labels }: BubbleToggleProps) => {
  const bubbleId = useId();
  const prefersReducedMotion = useReducedMotion();

  const bubbleTransition = prefersReducedMotion
    ? { duration: 0 }
    : { type: "spring" as const, stiffness: 400, damping: 30, mass: 0.8 };

  return (
    <div
      className={cn(
        "relative inline-flex w-fit max-w-full items-center gap-0.5 rounded-2xl border border-border/60 bg-muted/35 p-1 backdrop-blur-xl overflow-x-auto scrollbar-none",
        className
      )}
      role="tablist"
      aria-label="Selection"
    >
      {options.map((opt) => {
        const isActive = value === opt;

        return (
          <button
            key={opt}
            onClick={() => onChange(opt)}
            className="relative shrink-0 rounded-xl px-3 sm:px-4 py-2 text-xs sm:text-[13px] font-medium whitespace-nowrap"
            role="tab"
            aria-selected={isActive}
          >
            {isActive && (
              <>
                <motion.span
                  layoutId={`${bubbleId}-bubble`}
                  className="absolute inset-0 -z-10 rounded-xl bg-accent shadow-[0_0_0_1px_hsl(var(--accent)/0.5),0_8px_24px_hsl(var(--accent)/0.35)]"
                  transition={bubbleTransition}
                  style={{ originX: 0.5, originY: 0.5 }}
                />
                <motion.span
                  layoutId={`${bubbleId}-shine`}
                  className="pointer-events-none absolute inset-0 -z-10 rounded-xl bg-gradient-to-b from-white/30 via-white/10 to-transparent"
                  transition={bubbleTransition}
                />
              </>
            )}
            <motion.span
              animate={{
                color: isActive
                  ? "hsl(var(--accent-foreground))"
                  : "hsl(var(--muted-foreground))",
                scale: isActive ? 1.04 : 1,
              }}
              transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
              className="relative inline-block"
              whileHover={!isActive ? { color: "hsl(var(--foreground))", scale: 1.02 } : {}}
            >
              {labels?.[opt] ?? opt}
            </motion.span>
          </button>
        );
      })}
    </div>
  );
};

export default BubbleToggle;
