import { useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";

interface SplitTextProps {
  text: string;
  className?: string;
  delay?: number;
  duration?: number;
  ease?: string;
  splitType?: "chars" | "words";
  from?: { opacity?: number; y?: number; x?: number };
  to?: { opacity?: number; y?: number; x?: number };
  tag?: keyof JSX.IntrinsicElements;
  onAnimationComplete?: () => void;
  children?: React.ReactNode;
}

const easingMap: Record<string, number[]> = {
  "power3.out": [0.22, 1, 0.36, 1],
  "power2.out": [0.33, 1, 0.68, 1],
};

const SplitText = ({
  text,
  className = "",
  delay = 50,
  duration = 1.25,
  ease = "power3.out",
  splitType = "chars",
  from = { opacity: 0, y: 40 },
  to = { opacity: 1, y: 0 },
  tag: Tag = "span",
  onAnimationComplete,
  children,
}: SplitTextProps) => {
  const prefersReducedMotion = useReducedMotion();
  const easing = easingMap[ease] ?? [0.22, 1, 0.36, 1];

  const units = useMemo(() => {
    if (splitType === "words") {
      return text.split(/(\s+)/).map((word, i) => ({ key: `${word}-${i}`, char: word }));
    }
    return text.split("").map((char, i) => ({ key: `${char}-${i}`, char }));
  }, [text, splitType]);

  if (prefersReducedMotion) {
    return (
      <Tag className={className}>
        {text}
        {children}
      </Tag>
    );
  }

  return (
    <Tag className={`inline-block ${className}`}>
      {units.map((unit, i) => (
        <motion.span
          key={unit.key}
          className="inline-block"
          style={{ whiteSpace: unit.char.trim() === "" ? "pre" : undefined }}
          initial={from}
          animate={to}
          transition={{
            duration,
            ease: easing as [number, number, number, number],
            delay: (i * delay) / 1000,
          }}
          onAnimationComplete={i === units.length - 1 ? onAnimationComplete : undefined}
        >
          {unit.char}
        </motion.span>
      ))}
      {children}
    </Tag>
  );
};

export default SplitText;
