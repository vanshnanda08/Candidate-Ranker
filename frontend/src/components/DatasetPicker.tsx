import { useEffect, useRef, useState } from "react";
import { fetchDemo, uploadDataset } from "../api";
import type { DatasetInfo } from "../types";

interface Props {
  selected: string | null | undefined;
  info: DatasetInfo | null;
  onSelect: (id: string | null, info: DatasetInfo | null) => void;
  loading: boolean;
}

export function DatasetPicker({ selected, info, onSelect, loading }: Props) {
  const [mode, setMode] = useState("demo");
  const [demo, setDemo] = useState<DatasetInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const onSelectRef = useRef(onSelect);
  const selectionRef = useRef(selected);
  selectionRef.current = selected;
  onSelectRef.current = onSelect;
  useEffect(() => {
    let active = true;
    fetchDemo().then((data) => { if (active) { setDemo(data); if (selectionRef.current === "demo") onSelectRef.current("demo", data); } })
      .catch(() => { if (active) setError("Could not load the demo. Start the local API, then reload this page."); });
    return () => { active = false; };
  }, []);

  async function upload(file: File) {
    const current = ++generation.current;
    setError(null); onSelect("", null);
    if (file.size > 10 * 1024 * 1024) { setError("Choose a JSON file no larger than 10 MiB."); return; }
    setBusy(true);
    try {
      const data = await uploadDataset(file);
      if (generation.current === current) onSelect(data.dataset_id, { ...data, label: file.name });
    } catch (e) { if (generation.current === current) setError(e instanceof Error ? e.message : "Upload failed"); }
    finally { if (generation.current === current) setBusy(false); }
  }
  return <section aria-label="Dataset selection" className="mb-4">
    <label htmlFor="dataset-mode" className="field-label">Candidate dataset</label>
    <select id="dataset-mode" value={selected == null && mode !== "upload" ? "legacy" : mode} disabled={loading || busy}
      className="ui-input"
      onChange={(e) => {
        generation.current++; setMode(e.target.value); setError(null);
        onSelect(e.target.value === "demo" ? "demo" : e.target.value === "upload" ? "" : null, e.target.value === "demo" ? demo : null);
      }}>
      <option value="demo">Fictional demo — 50 profiles</option>
      <option value="upload">Upload JSON</option>
      <option value="legacy">Advanced: existing local path</option>
    </select>
    {mode === "upload" && <label className="field-label upload-field">Upload candidate JSON (10 MiB maximum)
      <input type="file" accept=".json,application/json" disabled={loading || busy}
        className="upload-input" onChange={(e) => { const file = e.target.files?.[0]; if (file) void upload(file); }} />
    </label>}
    {busy && <p role="status" className="feedback">Validating JSON profiles…</p>}
    {error && <p role="alert" className="feedback feedback-error">{error}</p>}
    {info && selected && <p role="status" className="feedback feedback-success">Accepted {info.profile_count} profiles · {info.label}</p>}
    {mode === "upload" && <p className="helper mt-2">JSON array, 1–5,000 profiles. Validation completes before ranking; uploads stay on this local server.</p>}
  </section>;
}
