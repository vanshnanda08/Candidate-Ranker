interface ScoreBarProps { label: string; value: number }

export function ScoreBar({ label, value }: ScoreBarProps) {
  return <div className="score-bar">
    <div><span>{label}</span><span>{value.toFixed(2)}</span></div>
    <div className="score-track"><div style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} /></div>
  </div>;
}
