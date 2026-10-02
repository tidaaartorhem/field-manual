import type { ChartSpec } from '../lib/charts';

// Editorial SVG charts: paper background, ink text, one accent.
// Sized for a 720px column; bars scale to the max value.

const INK = '#1d1a16';
const MUTED = '#6f675c';
const ACCENT = '#b0511f';
const ACCENT_SOFT = '#d99a6c';
const TIER3 = '#c9bfae';

const W = 672;
const ROW_H = 30;
const TOP_PAD = 8;
const BOTTOM_PAD = 26;

function barColor(tier: number | undefined): string {
  if (tier === 2) return ACCENT_SOFT;
  if (tier === 3) return TIER3;
  return ACCENT;
}

function HBar({ spec }: { spec: ChartSpec }) {
  const max = Math.max(...spec.data.map((d) => d.value), 1);
  const labelW = 150;
  const valueW = 430;
  const h = TOP_PAD + spec.data.length * ROW_H + BOTTOM_PAD;
  return (
    <svg
      viewBox={`0 0 ${W} ${h}`}
      width="100%"
      role="img"
      aria-label={`${spec.title}: ${spec.subtitle}`}
    >
      {spec.data.map((d, i) => {
        const y = TOP_PAD + i * ROW_H;
        const bw = Math.max(2, (d.value / max) * valueW);
        return (
          <g key={d.label}>
            <text
              x={labelW - 10}
              y={y + 15}
              textAnchor="end"
              fontSize="12.5"
              fill={INK}
              fontFamily="Georgia, serif"
            >
              {d.label}
            </text>
            <rect
              x={labelW}
              y={y + 4}
              width={bw}
              height={14}
              rx={3}
              fill={barColor(d.tier)}
            />
            <text x={labelW + bw + 8} y={y + 15} fontSize="11.5" fill={MUTED}>
              {d.detail ?? String(d.value)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Bar({ spec }: { spec: ChartSpec }) {
  const max = Math.max(...spec.data.map((d) => d.value), 1);
  const n = spec.data.length;
  const slot = W / n;
  const bw = Math.min(64, slot * 0.5);
  const plotH = 150;
  const h = TOP_PAD + plotH + 44;
  const base = TOP_PAD + plotH;
  return (
    <svg
      viewBox={`0 0 ${W} ${h}`}
      width="100%"
      role="img"
      aria-label={`${spec.title}: ${spec.subtitle}`}
    >
      {spec.data.map((d, i) => {
        const bh = Math.max(3, (d.value / max) * plotH);
        const x = slot * i + (slot - bw) / 2;
        return (
          <g key={d.label}>
            <rect
              x={x}
              y={base - bh}
              width={bw}
              height={bh}
              rx={3}
              fill={barColor(d.tier)}
            />
            <text
              x={x + bw / 2}
              y={base - bh - 6}
              textAnchor="middle"
              fontSize="11.5"
              fill={MUTED}
            >
              {d.detail ?? String(d.value)}
            </text>
            <text
              x={x + bw / 2}
              y={base + 18}
              textAnchor="middle"
              fontSize="12.5"
              fill={INK}
              fontFamily="Georgia, serif"
            >
              {d.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function ChartCard({ spec }: { spec: ChartSpec }) {
  return (
    <figure className="chart-card">
      <figcaption>
        <div className="chart-title">{spec.title}</div>
        <div className="chart-subtitle">{spec.subtitle}</div>
      </figcaption>
      {spec.kind === 'hbar' ? <HBar spec={spec} /> : <Bar spec={spec} />}
      <div className="chart-note">{spec.note}</div>
    </figure>
  );
}

export function ChartsStrip({ charts }: { charts: ChartSpec[] }) {
  if (charts.length === 0) return null;
  return (
    <section className="charts-strip" aria-label="By the numbers">
      <div className="charts-kicker">By the numbers</div>
      <div className="charts-grid">
        {charts.map((spec) => (
          <ChartCard key={spec.id} spec={spec} />
        ))}
      </div>
    </section>
  );
}
