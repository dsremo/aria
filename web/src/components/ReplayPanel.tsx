import { useState } from 'react'

const SCENARIOS = [
  'apollo_13_cryo_stir','apollo_12_lightning','sts_114_gap_filler',
  'soho_1998_attitude_loss','mir_spektr_collision','salyut7_blackout',
  'maven_safe_mode','galileo_hga_failure','jwst_micrometeorite',
  'voyager2_plasma_anomaly','apollo_1_fire','iss_quest_leak',
  'dragon_dock_abort','hayabusa_wheel_failures','hubble_sm4_stuck_bolt'
]

export default function ReplayPanel() {
  const [scenario, setScenario] = useState(SCENARIOS[0])
  const [withDoctrine, setWithDoctrine] = useState(true)
  const [withLessons, setWithLessons] = useState(true)
  const [noise, setNoise] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [report, setReport] = useState<string>('')
  const [error, setError] = useState<string>('')

  async function runReplay() {
    setRunning(true); setError(''); setResult(null); setReport('')
    try {
      const r = await fetch('/api/replay/run', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({scenario_id: scenario, with_doctrine: withDoctrine,
                              with_lessons: withLessons, noise})
      })
      const d = await r.json()
      if (!d.ok) { setError(d.error || 'Run failed'); }
      else { setResult(d.result) }
    } catch(e: any) { setError(e.message) }
    finally { setRunning(false) }
  }

  async function genReport() {
    setRunning(true); setError(''); setReport('')
    try {
      const r = await fetch('/api/replay/report', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({scenario_id: scenario})
      })
      const d = await r.json()
      if (!d.ok) { setError(d.error || 'Report failed') }
      else { setReport(d.report || '') }
    } catch(e: any) { setError(e.message) }
    finally { setRunning(false) }
  }

  return (
    <div className="p-4 font-mono max-w-[900px]">
      <h2 className="mb-2 text-ui-text font-bold">Historical Replay Engine</h2>
      <p className="text-ui-text-faint text-[0.85rem] mb-4">
        {SCENARIOS.length} scenarios · ARIA doctrine + lessons applied
      </p>

      <div className="flex gap-4 flex-wrap items-end mb-4">
        <div>
          <label className="block text-[0.8rem] text-ui-text-faint mb-1">Scenario</label>
          <select value={scenario} onChange={e=>setScenario(e.target.value)}
            className="bg-ui-bg-2 text-ui-text border border-ui-border rounded px-2 py-1 min-w-[260px] focus:outline-none focus:border-ui-accent">
            {SCENARIOS.map(s=><option key={s} value={s}>{s.replace(/_/g,' ')}</option>)}
          </select>
        </div>
        <label className="flex gap-1.5 items-center text-[0.85rem] cursor-pointer text-ui-text">
          <input type="checkbox" checked={withDoctrine} onChange={e=>setWithDoctrine(e.target.checked)}/> with_doctrine
        </label>
        <label className="flex gap-1.5 items-center text-[0.85rem] cursor-pointer text-ui-text">
          <input type="checkbox" checked={withLessons} onChange={e=>setWithLessons(e.target.checked)}/> with_lessons
        </label>
        <label className="flex gap-1.5 items-center text-[0.85rem] cursor-pointer text-ui-text">
          <input type="checkbox" checked={noise} onChange={e=>setNoise(e.target.checked)}/> noise
        </label>
        <button onClick={runReplay} disabled={running}
          className="px-4 py-1.5 rounded border border-ui-accent bg-ui-accent/15 text-ui-text hover:bg-ui-accent/25 font-bold disabled:opacity-50 transition-colors">
          {running ? 'Running…' : 'Run'}
        </button>
        <button onClick={genReport} disabled={running}
          className="px-4 py-1.5 rounded border border-sev-ok bg-sev-ok/15 text-ui-text hover:bg-sev-ok/25 font-bold disabled:opacity-50 transition-colors">
          {running ? '…' : 'Generate report'}
        </button>
      </div>

      {error && <div className="text-sev-crit mb-2">⚠ {error}</div>}

      {result && (
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-md p-4 mb-4 text-ui-text">
          <h3 className="mt-0 text-ui-accent font-semibold">Run Results — {scenario}</h3>
          {result.outcome && <div><b>Outcome:</b> {result.outcome}</div>}
          {result.lead_time_s != null && (
            <div><b>Lead time vs historical:</b> {result.lead_time_s}s
              {result.lead_time_s > 30
                ? <span className="text-sev-ok"> ✓ &gt;30 s early</span>
                : <span className="text-sev-crit"> ✗ &lt;30 s</span>}
            </div>
          )}
          {result.hal_applies != null && <div><b>HAL applies:</b> {String(result.hal_applies)}</div>}
          {result.audit?.length > 0 && (
            <div className="mt-2">
              <b>Audit (first 5):</b>
              <ol className="my-1 pl-5">
                {result.audit.slice(0,5).map((a:string,i:number)=><li key={i} className="text-[0.8rem]">{a}</li>)}
              </ol>
            </div>
          )}
          <details className="mt-2">
            <summary className="cursor-pointer text-ui-text-faint text-[0.8rem]">Raw JSON</summary>
            <pre className="text-[0.75rem] overflow-auto max-h-[200px] text-ui-text">{JSON.stringify(result,null,2)}</pre>
          </details>
        </div>
      )}

      {report && (
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-md p-4">
          <h3 className="mt-0 text-ui-accent font-semibold">Markdown Report</h3>
          <pre className="whitespace-pre-wrap text-[0.78rem] overflow-auto max-h-[400px] text-ui-text">{report}</pre>
        </div>
      )}

      {!result && !report && !error && !running && (
        <div className="text-ui-text-faint text-center py-12">
          Select a scenario and click <b>Run</b> to replay with ARIA doctrine applied.
        </div>
      )}
    </div>
  )
}
