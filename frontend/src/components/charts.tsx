/**
 * Graphiques en SVG natif.
 *
 * Écrits à la main plutôt qu'avec une bibliothèque : Recharts pesait 114 Ko
 * compressés pour deux formes élémentaires, sur un produit destiné à des réseaux
 * mobiles sénégalais. Le coût n'était pas proportionné au besoin.
 *
 * Les spécifications suivies sont fixes, pas affaire de goût :
 *
 * - lignes de 2 px, jointures arrondies ; marqueurs de rayon ≥ 4 px cerclés de 2 px
 *   de la couleur de surface, pour rester lisibles quand ils se croisent ;
 * - barres de 24 px au plus, extrémité arrondie de 4 px côté donnée, carrée sur la
 *   ligne de base ; 2 px de surface entre deux barres voisines ;
 * - grille en filet de 1 px continu, jamais en tirets ;
 * - légende dès deux séries, plus un libellé direct en bout de série — la couleur
 *   seule ne doit jamais porter l'identité ;
 * - le texte porte les jetons de texte, jamais la couleur de série ;
 * - une vue tableau est toujours accessible, ce qui lève aussi la réserve de
 *   contraste sur l'aqua en mode clair.
 */

import { useId, useMemo, useState } from "react";

import { money } from "../api";

const SERIES_VARS = ["--series-1", "--series-2", "--series-3"];

/** Graduations arrondies : 0 / 1 000 / 2 000, jamais 0 / 1 337 / 2 674. */
function niceTicks(min: number, max: number, count = 4) {
  if (min === max) return [min];
  const span = max - min;
  const rawStep = span / count;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const step = [1, 2, 2.5, 5, 10]
    .map((multiple) => multiple * magnitude)
    .find((candidate) => candidate >= rawStep) ?? 10 * magnitude;

  const start = Math.floor(min / step) * step;
  const ticks: number[] = [];
  for (let value = start; value <= max + step / 2; value += step) ticks.push(value);
  return ticks;
}

/** Abréviation de mois lisible : « oct. », « déc. » — jamais un `slice` brutal. */
const MONTH_ABBR: Record<string, string> = {
  janvier: "janv.", février: "févr.", mars: "mars", avril: "avr.",
  mai: "mai", juin: "juin", juillet: "juil.", août: "août",
  septembre: "sept.", octobre: "oct.", novembre: "nov.", décembre: "déc.",
};

export function abbreviateMonth(label: string): string {
  const month = label.split(" ")[0].toLowerCase();
  return MONTH_ABBR[month] ?? label.slice(0, 4);
}

function compact(value: number) {
  const sign = value < 0 ? "-" : "";
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) return `${sign}${(absolute / 1_000_000).toFixed(1)} M`;
  if (absolute >= 1_000) return `${sign}${Math.round(absolute / 1_000)} k`;
  return String(value);
}

/**
 * Écarte verticalement des étiquettes trop proches.
 *
 * Deux séries qui convergent placeraient leurs libellés au même endroit. On les
 * repousse d'un pas minimal, en restant dans le cadre — un libellé qui sort du
 * graphique ou qui se superpose ne remplit pas son office.
 */
function spreadLabels(
  labels: { name: string; y: number }[],
  top: number,
  bottom: number,
  minGap = 13,
) {
  const sorted = [...labels].sort((a, b) => a.y - b.y);
  for (let i = 1; i < sorted.length; i += 1) {
    const gap = sorted[i].y - sorted[i - 1].y;
    if (gap < minGap) sorted[i].y = sorted[i - 1].y + minGap;
  }
  // Recale si le décalage a poussé la dernière étiquette hors du cadre.
  const overflow = sorted[sorted.length - 1].y - bottom;
  if (overflow > 0) {
    const shift = Math.min(overflow, sorted[0].y - top);
    sorted.forEach((label) => {
      label.y -= shift;
    });
  }
  return sorted;
}

// --------------------------------------------------------------------------- //
// Graphique en lignes                                                          //
// --------------------------------------------------------------------------- //

type LineChartProps = {
  title: string;
  series: { name: string; values: number[] }[];
  labels: string[];
  unit?: string;
  height?: number;
  /** Trace le remplissage sous une série unique. */
  area?: boolean;
};

export function LineChart({
  title,
  series,
  labels,
  unit = "",
  height = 240,
  area = false,
}: LineChartProps) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const clipId = useId();

  const width = 720;

  // Marge droite calculée d'après le libellé de série le plus long : à 10,5 px de
  // fonte, un caractère occupe environ 5,9 px. Une marge fixe rognerait
  // « Ressources » — et un libellé tronqué ne remplit pas son office.
  const labelWidth =
    series.length > 1
      ? Math.max(...series.map((s) => s.name.length)) * 5.9 + 12
      : 14;
  const pad = { top: 16, right: Math.max(24, labelWidth), bottom: 26, left: 52 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;

  const { ticks, scaleY, scaleX } = useMemo(() => {
    const all = series.flatMap((s) => s.values);
    const rawMin = Math.min(0, ...all);
    const rawMax = Math.max(0, ...all);
    const marks = niceTicks(rawMin, rawMax);
    const low = Math.min(...marks, rawMin);
    const high = Math.max(...marks, rawMax);
    const range = high - low || 1;

    return {
      ticks: marks,
      scaleY: (value: number) => pad.top + plotHeight - ((value - low) / range) * plotHeight,
      scaleX: (index: number) =>
        pad.left + (labels.length === 1 ? plotWidth / 2 : (index / (labels.length - 1)) * plotWidth),
    };
  }, [series, labels.length, plotHeight, plotWidth, pad.left, pad.top]);


  const zeroY = scaleY(0);
  const showZero = ticks.some((t) => t < 0);

  if (asTable) {
    return (
      <figure className="chart" style={{ margin: 0 }}>
        <ChartHead title={title} asTable onToggle={() => setAsTable(false)} />
        <DataTable labels={labels} series={series} unit={unit} />
      </figure>
    );
  }

  return (
    <figure className="chart" style={{ margin: 0 }}>
      <ChartHead
        title={title}
        series={series.length > 1 ? series : undefined}
        onToggle={() => setAsTable(true)}
      />

      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title}. ${series.map((s) => s.name).join(", ")}.`}
        onMouseLeave={() => setHover(null)}
      >
        <defs>
          <clipPath id={clipId}>
            <rect x={pad.left} y={pad.top - 4} width={plotWidth} height={plotHeight + 8} />
          </clipPath>
        </defs>

        {/* Grille et graduations */}
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              className="grid-line"
              x1={pad.left}
              x2={pad.left + plotWidth}
              y1={scaleY(tick)}
              y2={scaleY(tick)}
            />
            <text className="tick" x={pad.left - 8} y={scaleY(tick) + 3.5} textAnchor="end">
              {compact(tick)}
            </text>
          </g>
        ))}
        {showZero && (
          <line
            className="axis-line"
            x1={pad.left}
            x2={pad.left + plotWidth}
            y1={zeroY}
            y2={zeroY}
            strokeWidth={1.5}
          />
        )}

        {/* Libellés de l'axe des mois — un sur deux si l'espace manque */}
        {labels.map((label, index) =>
          // Un mois sur deux quand l'espace manque, mais le dernier toujours :
          // c'est le point de lecture le plus utile de la série.
          labels.length > 8 && index % 2 !== 0 && index !== labels.length - 1 ? null : (
            <text
              key={label + index}
              className="tick"
              x={scaleX(index)}
              y={height - 8}
              textAnchor="middle"
            >
              {label}
            </text>
          ),
        )}

        {/* Repère de survol, sous les marques pour ne pas les masquer */}
        {hover !== null && (
          <line
            className="crosshair"
            x1={scaleX(hover)}
            x2={scaleX(hover)}
            y1={pad.top}
            y2={pad.top + plotHeight}
          />
        )}

        <g clipPath={`url(#${clipId})`}>
          {series.map((entry, seriesIndex) => {
            const color = `var(${SERIES_VARS[seriesIndex % SERIES_VARS.length]})`;
            const path = entry.values
              .map((value, index) => `${index ? "L" : "M"}${scaleX(index)},${scaleY(value)}`)
              .join(" ");

            return (
              <g key={entry.name}>
                {area && series.length === 1 && (
                  <path
                    d={`${path} L${scaleX(entry.values.length - 1)},${zeroY} L${scaleX(0)},${zeroY} Z`}
                    fill={color}
                    opacity={0.1}
                  />
                )}
                <path
                  d={path}
                  fill="none"
                  stroke={color}
                  strokeWidth={2}
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
                {/* Marqueur en bout de série : cerclé de la surface pour rester
                    lisible quand deux séries se croisent. */}
                <circle
                  cx={scaleX(entry.values.length - 1)}
                  cy={scaleY(entry.values[entry.values.length - 1])}
                  r={4}
                  fill={color}
                  stroke="var(--chart-surface)"
                  strokeWidth={2}
                />
                {hover !== null && (
                  <circle
                    cx={scaleX(hover)}
                    cy={scaleY(entry.values[hover])}
                    r={4.5}
                    fill={color}
                    stroke="var(--chart-surface)"
                    strokeWidth={2}
                  />
                )}
              </g>
            );
          })}
        </g>

        {/* Libellé direct en bout de série : l'identité ne repose jamais sur la
            seule couleur, et cela lève la réserve de contraste sur l'aqua.

            Les positions sont écartées quand deux séries se rejoignent — sans
            cela, deux courbes convergeant vers zéro superposent leurs étiquettes
            en un amas illisible. */
        }
        {series.length > 1 &&
          spreadLabels(
            series.map((entry) => ({
              name: entry.name,
              y: scaleY(entry.values[entry.values.length - 1]),
            })),
            pad.top,
            pad.top + plotHeight,
          ).map((label) => (
            <text
              key={`label-${label.name}`}
              className="series-label"
              x={pad.left + plotWidth + 7}
              y={label.y + 3.5}
            >
              {label.name}
            </text>
          ))}

        {/* Zones de capture : plus larges que les marques, pour un survol confortable */}
        {labels.map((_, index) => (
          <rect
            key={`hit-${index}`}
            x={scaleX(index) - plotWidth / (labels.length * 2)}
            y={pad.top}
            width={plotWidth / labels.length}
            height={plotHeight}
            fill="transparent"
            onMouseEnter={() => setHover(index)}
          />
        ))}
      </svg>

      {hover !== null && (
        <Tooltip
          x={(scaleX(hover) / width) * 100}
          title={labels[hover]}
          rows={series.map((entry, index) => ({
            name: entry.name,
            value: entry.values[hover],
            color: `var(${SERIES_VARS[index % SERIES_VARS.length]})`,
          }))}
          unit={unit}
        />
      )}
    </figure>
  );
}

// --------------------------------------------------------------------------- //
// Barres horizontales                                                          //
// --------------------------------------------------------------------------- //

type BarChartProps = {
  title: string;
  data: { label: string; value: number }[];
  unit?: string;
};

export function BarChart({ title, data, unit = "" }: BarChartProps) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  const width = 720;
  const rowHeight = 28;
  const barThickness = 18; // sous le plafond de 24 px ; le reste de la bande est de l'air
  const pad = { top: 8, right: 96, bottom: 8, left: 220 };
  const height = pad.top + data.length * rowHeight + pad.bottom;
  const plotWidth = width - pad.left - pad.right;

  const max = Math.max(1, ...data.map((row) => row.value));
  const scale = (value: number) => (value / max) * plotWidth;

  if (asTable) {
    return (
      <figure className="chart" style={{ margin: 0 }}>
        <ChartHead title={title} asTable onToggle={() => setAsTable(false)} />
        <DataTable
          labels={data.map((row) => row.label)}
          series={[{ name: "Montant", values: data.map((row) => row.value) }]}
          unit={unit}
          transposed
        />
      </figure>
    );
  }

  return (
    <figure className="chart" style={{ margin: 0 }}>
      {/* Une seule série : pas de légende, le titre dit déjà ce qui est mesuré. */}
      <ChartHead title={title} onToggle={() => setAsTable(true)} />

      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${title}, ${data.length} rubriques.`}
        onMouseLeave={() => setHover(null)}
      >
        {data.map((row, index) => {
          // 2 px de surface entre deux barres voisines : c'est le blanc qui sépare,
          // jamais un contour ajouté autour de la marque.
          const y = pad.top + index * rowHeight + (rowHeight - barThickness) / 2 + 1;
          const barWidth = Math.max(2, scale(row.value));
          const radius = 4;

          return (
            <g
              key={row.label}
              onMouseEnter={() => setHover(index)}
              opacity={hover === null || hover === index ? 1 : 0.55}
            >
              <text
                className="tick"
                x={pad.left - 10}
                y={y + barThickness / 2 + 3.5}
                textAnchor="end"
              >
                {row.label.length > 32 ? `${row.label.slice(0, 31)}…` : row.label}
              </text>

              {/* Extrémité arrondie côté donnée, carrée sur la ligne de base. */}
              <path
                d={`M${pad.left},${y}
                    H${pad.left + barWidth - radius}
                    a${radius},${radius} 0 0 1 ${radius},${radius}
                    V${y + barThickness - radius}
                    a${radius},${radius} 0 0 1 -${radius},${radius}
                    H${pad.left} Z`}
                fill="var(--series-1)"
              />

              <text
                className="tick"
                x={pad.left + barWidth + 8}
                y={y + barThickness / 2 + 3.5}
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {money(row.value)}
              </text>

              <rect
                x={0}
                y={pad.top + index * rowHeight}
                width={width}
                height={rowHeight}
                fill="transparent"
              />
            </g>
          );
        })}
      </svg>

      {hover !== null && (
        <Tooltip
          x={30}
          y={pad.top + hover * rowHeight + rowHeight + 4}
          title={data[hover].label}
          rows={[{ name: "Montant", value: data[hover].value, color: "var(--series-1)" }]}
          unit={unit}
        />
      )}
    </figure>
  );
}

// --------------------------------------------------------------------------- //
// Pièces communes                                                              //
// --------------------------------------------------------------------------- //

function ChartHead({
  title,
  series,
  asTable,
  onToggle,
}: {
  title: string;
  series?: { name: string }[];
  asTable?: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="chart-head">
      <figcaption className="card-title" style={{ marginBottom: 0 }}>
        {title}
      </figcaption>

      <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap" }}>
        {series && (
          <div className="chart-legend">
            {series.map((entry, index) => (
              <span key={entry.name}>
                <i
                  className="legend-key"
                  style={{ background: `var(${SERIES_VARS[index % SERIES_VARS.length]})` }}
                />
                {entry.name}
              </span>
            ))}
          </div>
        )}
        <button type="button" className="chart-toggle" onClick={onToggle}>
          {asTable ? "Voir le graphique" : "Voir les données"}
        </button>
      </div>
    </div>
  );
}

function Tooltip({
  x,
  y = 34,
  title,
  rows,
  unit,
}: {
  x: number;
  y?: number;
  title: string;
  rows: { name: string; value: number; color: string }[];
  unit: string;
}) {
  // Bascule le côté au-delà du milieu, pour ne pas sortir du cadre.
  const flip = x > 60;
  return (
    <div
      className="chart-tooltip"
      style={{
        left: `${Math.min(Math.max(x, 4), 96)}%`,
        top: y,
        transform: flip ? "translateX(-100%)" : "none",
        marginLeft: flip ? -10 : 10,
      }}
    >
      <div className="tip-title">{title}</div>
      {rows.map((row) => (
        <div className="tip-row" key={row.name}>
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <i className="legend-key dot" style={{ background: row.color }} />
            {row.name}
          </span>
          <b>
            {money(row.value)} {unit}
          </b>
        </div>
      ))}
    </div>
  );
}

/** Vue tableau — garantit qu'aucune valeur n'est accessible par la couleur seule. */
function DataTable({
  labels,
  series,
  unit,
  transposed = false,
}: {
  labels: string[];
  series: { name: string; values: number[] }[];
  unit: string;
  transposed?: boolean;
}) {
  if (transposed) {
    return (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rubrique</th>
              <th className="num">Montant ({unit})</th>
            </tr>
          </thead>
          <tbody>
            {labels.map((label, index) => (
              <tr key={label}>
                <td style={{ whiteSpace: "normal" }}>{label}</td>
                <td className="num">{money(series[0].values[index])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Période</th>
            {series.map((entry) => (
              <th key={entry.name} className="num">
                {entry.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {labels.map((label, index) => (
            <tr key={label + index}>
              <td>{label}</td>
              {series.map((entry) => (
                <td key={entry.name} className="num">
                  {money(entry.values[index])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
