import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CandidateResult } from "../types";

interface ScoreChartProps {
  results: CandidateResult[];
}

export function ScoreChart({ results }: ScoreChartProps) {
  const data = results.map((r) => ({
    rank: r.rank,
    score: r.display_score,
    isHoneypot: r.honeypot_penalty < 0.2,
    name: r.name,
  }));

  return (
    <div className="score-chart">
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#deded4" />
          <XAxis
            dataKey="rank"
            tick={{ fontSize: 11, fill: "#686b60" }}
            label={{ value: "Rank", position: "insideBottom", offset: -2, fontSize: 11, fill: "#686b60" }}
          />
          <YAxis tick={{ fontSize: 11, fill: "#686b60" }} domain={[0, 1]} />
          <Tooltip
            formatter={(value) => Number(value).toFixed(4)}
            labelFormatter={(label, payload) =>
              payload?.[0]
                ? `Rank ${label} — ${(payload[0].payload as { name: string }).name}`
                : `Rank ${label}`
            }
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Bar isAnimationActive={false} dataKey="score" radius={[3, 3, 0, 0]}>
            {data.map((d) => (
              <Cell key={d.rank} fill={d.isHoneypot ? "#986722" : "#214f3e"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-emerald-800 inline-block" /> Normal
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm bg-amber-700 inline-block" /> Honeypot flagged
        </span>
      </div>
    </div>
  );
}
