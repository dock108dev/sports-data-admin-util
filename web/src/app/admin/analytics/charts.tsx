"use client";

import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";

/* ------------------------------------------------------------------ */
/* Score distribution bar chart (pregame simulator)                     */
/* ------------------------------------------------------------------ */

interface ScoreEntry {
  score: string;
  probability: number;
}

export function ScoreDistributionChart({ data }: { data: ScoreEntry[] }) {
  const chartData = data.map((d) => ({
    score: d.score,
    pct: +(d.probability * 100).toFixed(1),
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="score" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} unit="%" />
        <Tooltip formatter={(v) => `${v}%`} />
        <Bar dataKey="pct" name="Probability" radius={[4, 4, 0, 0]}>
          {chartData.map((_, i) => (
            <Cell key={i} fill={i === 0 ? "#3b82f6" : "#93c5fd"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* PA probabilities grouped bar chart                                  */
/* ------------------------------------------------------------------ */

export function PAProbabilitiesChart({
  homeProbs,
  awayProbs,
  homeLabel,
  awayLabel,
}: {
  homeProbs: Record<string, number>;
  awayProbs: Record<string, number>;
  homeLabel: string;
  awayLabel: string;
}) {
  const events = Object.keys(homeProbs);
  const chartData = events.map((key) => ({
    event: key.replace("_probability", ""),
    [homeLabel]: +((homeProbs[key] ?? 0) * 100).toFixed(1),
    [awayLabel]: +((awayProbs[key] ?? 0) * 100).toFixed(1),
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="event" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 12 }} unit="%" />
        <Tooltip formatter={(v) => `${v}%`} />
        <Legend />
        <Bar dataKey={homeLabel} fill="#3b82f6" radius={[3, 3, 0, 0]} />
        <Bar dataKey={awayLabel} fill="#f97316" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* Win probability timeline (live simulator)                           */
/* ------------------------------------------------------------------ */

interface WPTimelineEntry {
  label: string;
  home: number;
  away: number;
}

export function WinProbabilityTimeline({ data }: { data: WPTimelineEntry[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 12 }} unit="%" domain={[0, 100]} />
        <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} />
        <Legend />
        <Line type="monotone" dataKey="home" name="Home WP" stroke="#3b82f6" strokeWidth={2} dot={{ r: 4 }} />
        <Line type="monotone" dataKey="away" name="Away WP" stroke="#ef4444" strokeWidth={2} dot={{ r: 4 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/* ------------------------------------------------------------------ */
/* Calibration accuracy chart (model performance)                      */
/* ------------------------------------------------------------------ */

interface CalibrationEntry {
  label: string;
  predicted: number;
  actual: number;
}

export function CalibrationChart({ data }: { data: CalibrationEntry[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey="label" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 12 }} unit="%" domain={[0, 100]} />
        <Tooltip formatter={(v) => `${Number(v).toFixed(1)}%`} />
        <Legend />
        <Bar dataKey="predicted" name="Predicted WP" fill="#3b82f6" radius={[3, 3, 0, 0]} />
        <Bar dataKey="actual" name="Actual Win %" fill="#22c55e" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
