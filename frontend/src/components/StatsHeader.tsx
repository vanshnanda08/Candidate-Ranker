import type { RankResponse } from "../types";

interface StatsHeaderProps {
  data: RankResponse;
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn";
}) {
  return (
    <div className="stat-card">
      <div className="text-xs font-medium text-slate-500 mb-1">{label}</div>
      <div
        className={`text-2xl font-semibold ${
          tone === "warn"
            ? "text-red-600"
            : tone === "ok"
              ? "text-emerald-600"
              : "text-slate-900"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

export function StatsHeader({ data }: StatsHeaderProps) {
  const honeypotsOk = data.honeypots_in_top <= 10;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <StatCard label="Dataset profiles" value={data.total_candidates.toLocaleString()} />
      <StatCard label="Returned candidates" value={String(data.top_n)} />
      <StatCard
        label="Flagged in top results"
        value={String(data.honeypots_in_top)}
        tone={honeypotsOk ? "ok" : "warn"}
      />
      <StatCard label="Top displayed score" value={data.top_score.toFixed(4)} />
    </div>
  );
}
