import type { ReviewRecord } from "../api/types";
import { tokens } from "../theme";

/** Last-attempt overall score per chapter, ascending chapter order. */
export function trendPoints(records: ReviewRecord[]): { x: number; y: number }[] {
  const last = new Map<number, { attempt: number; overall: number }>();
  for (const r of records) {
    const cur = last.get(r.chapter);
    if (!cur || r.attempt > cur.attempt)
      last.set(r.chapter, { attempt: r.attempt, overall: r.overall });
  }
  return [...last.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([chapter, v]) => ({ x: chapter, y: v.overall }));
}

/** R5: inline-SVG score trend — no chart dependency. */
export function Trend({ points }: { points: { x: number; y: number }[] }) {
  if (points.length < 2) return null;
  const w = 320;
  const h = 80;
  const pad = 8;
  const maxY = 100;
  const minY = 0;
  const xs = (i: number) => pad + (i * (w - 2 * pad)) / (points.length - 1);
  const ys = (y: number) => pad + (1 - (y - minY) / (maxY - minY)) * (h - 2 * pad);
  return (
    <svg data-testid="score-trend" width={w} height={h} role="img" aria-label="各章总分趋势">
      <polyline
        fill="none"
        stroke={tokens.brand}
        strokeWidth="2"
        points={points.map((p, i) => `${xs(i)},${ys(p.y)}`).join(" ")}
      />
      {points.map((p, i) => (
        <circle key={p.x} cx={xs(i)} cy={ys(p.y)} r="3" fill={tokens.brand} />
      ))}
    </svg>
  );
}
