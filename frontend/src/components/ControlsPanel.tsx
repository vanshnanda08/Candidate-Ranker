import type { DatasetInfo, RankRequest } from "../types";
import { DatasetPicker } from "./DatasetPicker";

interface ControlsPanelProps {
  form: RankRequest;
  onChange: (patch: Partial<RankRequest>) => void;
  loading: boolean;
  dataset: DatasetInfo | null;
  onDataset: (id: string | null, info: DatasetInfo | null) => void;
}

export function ControlsPanel({ form, onChange, loading, dataset, onDataset }: ControlsPanelProps) {
  return <section className="setup-step" aria-label="Choose candidates">
    <div className="step-heading"><div><h3>Candidates</h3></div></div>
    <DatasetPicker selected={form.dataset_id} info={dataset} onSelect={onDataset} loading={loading} />
    <details className="advanced-options"><summary>Legacy local path settings</summary>
      <label htmlFor="candidate-path" className="field-label">Candidates file path</label>
      <input id="candidate-path" type="text" value={form.data_path} disabled={loading} className="ui-input"
        onChange={(e) => { onDataset(null, null); onChange({ data_path: e.target.value }); }} />
      <label className="checkbox-label"><input type="checkbox" checked={form.is_sample} disabled={loading}
        onChange={(e) => { onDataset(null, null); onChange({ is_sample: e.target.checked }); }} />Sample JSON file (not .jsonl.gz)</label>
    </details>
  </section>;
}
