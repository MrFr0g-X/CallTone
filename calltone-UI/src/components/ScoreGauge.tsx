import { useEffect, useState } from "react";

/**
 * Semicircular speedometer gauge for an overall QA score (0–100).
 * Color bands: <60 red, 60–79 amber, >=80 green. Pointer + value animate in.
 */
type ScoreGaugeProps = {
  score: number;
  grade?: string | null;
  size?: number;
};

const bandColor = (s: number) => {
  if (s >= 80) return "hsl(var(--success))";
  if (s >= 60) return "hsl(var(--warning))";
  return "hsl(var(--destructive))";
};

const ScoreGauge = ({ score, grade, size = 220 }: ScoreGaugeProps) => {
  const clamped = Math.max(0, Math.min(100, Math.round(score)));
  const [shown, setShown] = useState(0);

  useEffect(() => {
    // Animate the needle/value from 0 to the real score on mount/score change.
    const start = performance.now();
    const duration = 900;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(Math.round(eased * clamped));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [clamped]);

  // Geometry: 180° arc from 180° (left) to 0° (right).
  const stroke = Math.max(10, size * 0.07);
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = Math.PI * r; // half circle
  const dash = (shown / 100) * circumference;
  const color = bandColor(shown);

  // Needle angle: 0 score = 180° (pointing left), 100 = 0° (right).
  const angle = Math.PI - (shown / 100) * Math.PI;
  const needleLen = r - stroke * 0.4;
  const nx = cx + needleLen * Math.cos(angle);
  const ny = cy - needleLen * Math.sin(angle);

  return (
    <div className="flex flex-col items-center" style={{ width: size }}>
      <svg width={size} height={size / 2 + stroke} viewBox={`0 0 ${size} ${size / 2 + stroke}`}>
        {/* track */}
        <path
          d={`M ${stroke / 2} ${cy} A ${r} ${r} 0 0 1 ${size - stroke / 2} ${cy}`}
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth={stroke}
          strokeLinecap="round"
        />
        {/* value arc */}
        <path
          d={`M ${stroke / 2} ${cy} A ${r} ${r} 0 0 1 ${size - stroke / 2} ${cy}`}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference}`}
          style={{ transition: "stroke 200ms" }}
        />
        {/* needle */}
        <line x1={cx} y1={cy} x2={nx} y2={ny} stroke={color} strokeWidth={3} strokeLinecap="round" />
        <circle cx={cx} cy={cy} r={stroke * 0.45} fill={color} />
      </svg>
      <div className="-mt-6 text-center">
        <div className="text-4xl font-light tracking-tight" style={{ color }}>
          {shown}
          <span className="text-lg text-muted-foreground">/100</span>
        </div>
        {grade ? (
          <div className="text-xs uppercase tracking-wider text-muted-foreground mt-0.5">
            Grade {grade}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default ScoreGauge;
