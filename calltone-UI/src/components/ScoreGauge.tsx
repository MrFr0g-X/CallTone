import { useEffect, useState } from "react";

/**
 * Semicircular score gauge (0–100). Clean, needle-less design: a muted track arc
 * with a colored value arc on top, and the score + grade centered in the bowl.
 * Color bands: <60 red, 60–79 amber, >=80 green.
 */
type ScoreGaugeProps = {
  score: number;
  grade?: string | null;
  size?: number;
};

const band = (s: number) => {
  if (s >= 80) return { stroke: "hsl(var(--success))", label: "text-success" };
  if (s >= 60) return { stroke: "hsl(var(--warning))", label: "text-warning" };
  return { stroke: "hsl(var(--destructive))", label: "text-destructive" };
};

const ScoreGauge = ({ score, grade, size = 200 }: ScoreGaugeProps) => {
  const target = Math.max(0, Math.min(100, Math.round(score)));
  const [shown, setShown] = useState(0);

  useEffect(() => {
    const start = performance.now();
    const dur = 850;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(Math.round(eased * target));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);

  const stroke = Math.round(size * 0.085);
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = r + stroke / 2;          // baseline (flat edge) of the semicircle
  const height = cy + Math.round(size * 0.20); // room for the grade under the baseline
  // Semicircle that bulges upward, left baseline -> right baseline.
  const arc = `M ${stroke / 2} ${cy} A ${r} ${r} 0 0 1 ${size - stroke / 2} ${cy}`;
  const { stroke: color, label } = band(shown);

  return (
    <svg
      width={size}
      height={height}
      viewBox={`0 0 ${size} ${height}`}
      role="img"
      aria-label={`Overall score ${target} out of 100${grade ? `, grade ${grade}` : ""}`}
    >
      {/* track */}
      <path d={arc} fill="none" stroke="hsl(var(--muted))" strokeWidth={stroke} strokeLinecap="round" />
      {/* value arc — pathLength=100 lets dasharray map 1:1 to the score */}
      <path
        d={arc}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        pathLength={100}
        strokeDasharray={`${shown} 100`}
        style={{ transition: "stroke 250ms ease" }}
      />
      {/* end labels */}
      <text x={stroke / 2} y={cy + 16} textAnchor="middle"
            className="fill-muted-foreground" style={{ fontSize: size * 0.06 }}>0</text>
      <text x={size - stroke / 2} y={cy + 16} textAnchor="middle"
            className="fill-muted-foreground" style={{ fontSize: size * 0.06 }}>100</text>
      {/* score + grade, centered in the bowl, clear of the arc */}
      <text x={cx} y={cy - size * 0.06} textAnchor="middle" className={label}
            style={{ fontSize: size * 0.26, fontWeight: 300, fill: color }}>
        {shown}
        <tspan className="fill-muted-foreground" style={{ fontSize: size * 0.085 }}>/100</tspan>
      </text>
      {grade ? (
        <text x={cx} y={cy + height * 0.13} textAnchor="middle"
              className="fill-muted-foreground"
              style={{ fontSize: size * 0.07, letterSpacing: "0.08em" }}>
          GRADE {String(grade).toUpperCase()}
        </text>
      ) : null}
    </svg>
  );
};

export default ScoreGauge;
