import type { ReactNode } from "react";

export interface PlotSeries {
  label: string;
  /** `null` marks a genuinely missing snapshot — never interpolate across one. */
  points: (number | null)[];
  color: string;
  weight?: number;
  dash?: string;
  opacity?: number;
  marker?: "dot" | "square";
  labelColor?: string;
}

/** Fraction of the data's own span left as breathing room above and below it. */
const AXIS_PADDING = 0.1;

/** How many gridlines the axis aims for. The nice-number step lands near this, not on it. */
const TARGET_TICKS = 5;

/** A series that never moves has no span to scale to, so the axis is given one: this
 *  fraction of the value itself, which puts a flat line through the middle of a
 *  plausible-looking axis instead of dividing by zero. */
const FLAT_SERIES_SPAN = 0.1;

/**
 * The next "round" number at or above `raw` -- 1, 2, 5 or 10 times a power of ten.
 *
 * Axis labels are read, not measured, so they have to be numbers a person would choose:
 * 0.5, 2, 25, 500. A step of 3.7 is arithmetically fine and unreadable.
 */
function niceStep(raw: number): number {
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalised = raw / magnitude;
  const rounded = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 5 ? 5 : 10;
  return rounded * magnitude;
}

/**
 * Axis bounds and gridlines for a range of values.
 *
 * This replaced a fixed one-unit step with bounds padded by a flat ±0.4, which was wrong
 * in both directions at once and produced the two chart complaints that led here:
 *
 *  - **It flattened real movement.** In ₹ lakh, a portfolio moving 6.65 -> 7.23 was
 *    scaled onto an axis of 6 to 8, so a 9% swing drew as a nearly horizontal line
 *    sitting on top of the invested-cost line. Padding proportional to the data's own
 *    span keeps the movement filling the plot whatever the portfolio is worth.
 *  - **It did not bound the gridlines.** One tick per lakh means a ₹1.5 crore portfolio
 *    draws 150 labelled gridlines. The step is chosen from the span now, so the count
 *    stays near TARGET_TICKS at every scale.
 *
 * `decimals` comes back with the bounds because it is a property of the step, not of the
 * caller: a step of 0.25 needs two decimals and a step of 50 needs none, and rounding to
 * it is also what keeps binary error (6.500000000000001) off the axis.
 */
function scaleFor(
  min: number,
  max: number,
  targetTicks: number = TARGET_TICKS
): { lo: number; hi: number; ticks: number[]; decimals: number } {
  const dataSpan = max - min;
  const padding =
    (dataSpan > 0 ? dataSpan : Math.max(Math.abs(max), 1) * FLAT_SERIES_SPAN) * AXIS_PADDING;
  const step = niceStep((max + padding - (min - padding)) / targetTicks);

  // Snap outward to whole multiples of the step, so every gridline is itself a round
  // number rather than an offset from an arbitrary minimum.
  //
  // The floor stops at zero for a series that never goes negative. Padding a portfolio
  // worth ₹0.29L down to -₹2L would spend a fifth of the plot on values that cannot
  // occur, and squash the part that can into what is left.
  const snapped = Math.floor((min - padding) / step) * step;
  const lo = min >= 0 && snapped < 0 ? 0 : snapped;
  const hi = Math.ceil((max + padding) / step) * step;

  const ticks: number[] = [];
  // Multiply out from the index instead of accumulating `t += step`: repeated addition
  // of a fractional step drifts, and the drift shows up as a duplicated axis label.
  for (let i = 0; lo + i * step <= hi + step / 1000; i += 1) ticks.push(lo + i * step);

  return { lo, hi, ticks, decimals: Math.max(0, -Math.floor(Math.log10(step))) };
}

/**
 * The engraved value plot — portfolio value against invested cost and a rebased
 * benchmark.
 *
 * Three deliberate choices, all of them about not lying with a line:
 *
 *  1. **Gaps stay gaps.** A `null` point breaks the path into separate runs rather
 *     than drawing straight through. A missing snapshot is missing data, and joining
 *     across it invents a value the ledger cannot reproduce.
 *  2. **The band is hatched, not filled.** The area between market value and invested
 *     cost is unrealised P&L — a diagonal hatch reads as an annotation over the plot
 *     rather than a fourth series competing with the three real ones.
 *  3. **Series are labelled in place** at their last known point, so the chart needs
 *     no legend and no hover to be read on paper or in a screenshot.
 */
export function VintageLinePlot({
  labels,
  series,
  height = 300,
  formatTick = (v: string) => v,
  gapNote,
}: {
  labels: string[];
  series: PlotSeries[];
  height?: number;
  /** Receives the tick already rounded and rendered to the axis's own precision, so a
   *  caller only ever appends a unit -- it never has to guess how many decimals a step
   *  of 0.25 needs, nor defend against 6.500000000000001. */
  formatTick?: (v: string) => ReactNode;
  gapNote?: string;
}) {
  const W = 860;
  const PL = 46;
  const PR = 108;
  const PT = 18;
  const PB = 34;

  const flat = series.flatMap((s) => s.points).filter((v): v is number => v != null);
  if (flat.length === 0 || labels.length < 2) return null;

  const { lo, hi, ticks, decimals } = scaleFor(Math.min(...flat), Math.max(...flat));
  const span = hi - lo;

  const x = (i: number) => PL + (i * (W - PL - PR)) / (labels.length - 1);
  const y = (v: number) => PT + ((hi - v) / span) * (height - PT - PB);

  /** Contiguous runs of non-null indices — one path segment each. */
  const runs = (pts: (number | null)[]): number[][] => {
    const out: number[][] = [];
    let cur: number[] = [];
    pts.forEach((v, i) => {
      if (v == null) {
        if (cur.length) out.push(cur);
        cur = [];
      } else cur.push(i);
    });
    if (cur.length) out.push(cur);
    return out;
  };

  const path = (pts: (number | null)[]) =>
    runs(pts)
      .map((r) => "M" + r.map((i) => `${x(i).toFixed(1)} ${y(pts[i] as number).toFixed(1)}`).join("L"))
      .join(" ");

  // The band closes the primary series (market value) against the reference series
  // (invested cost), but only over spans where BOTH have data — otherwise it would
  // fill straight across a snapshot gap and invent the very area it is measuring.
  const primary = series[0];
  const reference = series[1];
  const band =
    primary && reference
      ? runs(primary.points)
          .filter((r) => r.every((i) => reference.points[i] != null))
          .map(
            (r) =>
              "M" +
              r.map((i) => `${x(i).toFixed(1)} ${y(primary.points[i] as number).toFixed(1)}`).join("L") +
              "L" +
              r
                .slice()
                .reverse()
                .map((i) => `${x(i).toFixed(1)} ${y(reference.points[i] as number).toFixed(1)}`)
                .join("L") +
              "Z"
          )
      : [];

  const gapIndex = primary ? primary.points.findIndex((v) => v == null) : -1;

  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      width="100%"
      style={{ display: "block", overflow: "visible" }}
      role="img"
      aria-label={series.map((s) => s.label).join(", ")}
    >
      <defs>
        <pattern id="ledger-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="6" stroke="var(--ledger-ink)" strokeWidth="0.6" opacity="0.15" />
        </pattern>
      </defs>

      {ticks.map((t) => (
        <g key={t}>
          <line
            x1={PL}
            y1={y(t)}
            x2={W - PR}
            y2={y(t)}
            stroke="var(--ledger-ink)"
            strokeWidth="0.4"
            opacity={0.11}
            strokeDasharray="1 3"
          />
          <text
            x={PL - 9}
            y={y(t) + 3.5}
            textAnchor="end"
            style={{ fontFamily: "var(--font-slip)", fontSize: 13, fill: "var(--ledger-ink)", opacity: 0.6 }}
          >
            {formatTick(t.toFixed(decimals))}
          </text>
        </g>
      ))}

      {band.map((dPath, i) => (
        <path key={i} d={dPath} fill="url(#ledger-hatch)" />
      ))}

      <line x1={PL} y1={height - PB} x2={W - PR} y2={height - PB} stroke="var(--ledger-ink)" strokeWidth="1" />
      {labels.map((l, i) => (
        <g key={l + i}>
          <line
            x1={x(i)}
            y1={height - PB}
            x2={x(i)}
            y2={height - PB + 5}
            stroke="var(--ledger-ink)"
            strokeWidth="0.7"
            opacity=".55"
          />
          <text
            x={x(i)}
            y={height - PB + 18}
            textAnchor="middle"
            style={{
              fontFamily: "var(--font-label)",
              fontSize: 9.5,
              letterSpacing: ".08em",
              textTransform: "uppercase",
              fill: "var(--ledger-ink-faint)",
            }}
          >
            {l}
          </text>
        </g>
      ))}

      {/* Drawn back-to-front so the primary series sits on top of the reference lines. */}
      {series
        .slice()
        .reverse()
        .map((s) => (
          <path
            key={s.label}
            d={path(s.points)}
            fill="none"
            stroke={s.color}
            strokeWidth={s.weight ?? 1.2}
            strokeDasharray={s.dash}
            strokeLinejoin="round"
            strokeLinecap={s.dash ? "round" : "butt"}
            opacity={s.opacity ?? 1}
          />
        ))}

      {series.map((s) =>
        s.points.map((v, i) =>
          v == null ? null : s.marker === "square" ? (
            <rect
              key={s.label + i}
              x={x(i) - 2.6}
              y={y(v) - 2.6}
              width="5.2"
              height="5.2"
              fill="var(--surface)"
              stroke={s.color}
              strokeWidth="1.1"
            />
          ) : s.marker === "dot" ? (
            <circle key={s.label + i} cx={x(i)} cy={y(v)} r="3.1" fill={s.color} />
          ) : null
        )
      )}

      {series.map((s) => {
        const i = s.points.reduce((acc: number, v, idx) => (v == null ? acc : idx), -1);
        if (i < 0) return null;
        return (
          <text
            key={s.label}
            x={x(i) + 10}
            y={y(s.points[i] as number) + 4}
            style={{
              fontFamily: "var(--font-label)",
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: ".04em",
              fill: s.labelColor ?? s.color,
            }}
          >
            {s.label}
          </text>
        );
      })}

      {gapIndex > -1 && gapNote && (
        <g>
          <line
            x1={x(gapIndex)}
            y1={PT + 16}
            x2={x(gapIndex)}
            y2={height - PB - 4}
            stroke="var(--ledger-ink)"
            strokeWidth="0.5"
            strokeDasharray="2 3"
            opacity=".32"
          />
          <text
            x={x(gapIndex)}
            y={PT + 8}
            textAnchor="middle"
            style={{
              fontFamily: "var(--font-label)",
              fontSize: 9.5,
              letterSpacing: ".14em",
              textTransform: "uppercase",
              fill: "var(--ledger-ink-faint)",
            }}
          >
            {gapNote}
          </text>
        </g>
      )}
    </svg>
  );
}
