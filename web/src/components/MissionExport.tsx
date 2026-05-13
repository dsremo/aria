/**
 * Mission Export — generate and download a mission summary report.
 *
 * Aggregates data from multiple endpoints into a single comprehensive
 * JSON report with: trajectory state, crew health, fuel status,
 * hull damage, objectives progress, mass budget, and engineering review.
 * Downloads as a timestamped JSON file.
 */

import { useState } from 'react';
import { ariaApi } from '../api/aria';

interface ReportSection {
  label: string;
  status: 'pending' | 'loading' | 'done' | 'error';
  data?: any;
}

export function MissionExport() {
  const [sections, setSections] = useState<ReportSection[]>([]);
  const [generating, setGenerating] = useState(false);

  const generateReport = async () => {
    setGenerating(true);

    const sectionDefs: { label: string; fetch: () => Promise<any> }[] = [
      { label: 'Mission Phase', fetch: () => ariaApi.missionPhase() },
      { label: 'Trajectory State', fetch: () => ariaApi.trajectory() },
      { label: 'Fuel Inventory', fetch: () => ariaApi.fuel() },
      { label: 'Crew Health', fetch: () => ariaApi.crewHealth() },
      { label: 'Hull Damage', fetch: () => ariaApi.hullDamage() },
      { label: 'Mission Objectives', fetch: () => ariaApi.objectives() },
      { label: 'Power Budget', fetch: () => ariaApi.powerBudget() },
      { label: 'Bearing Status', fetch: () => ariaApi.bearing() },
      { label: 'Agriculture', fetch: () => ariaApi.agriculture() },
      { label: 'Bill of Materials', fetch: () => ariaApi.bomList() },
      { label: 'Ship Parameters', fetch: () => ariaApi.shipParams() },
      { label: 'Communications', fetch: () => ariaApi.comms() },
    ];

    const results: ReportSection[] = sectionDefs.map(s => ({
      label: s.label, status: 'pending',
    }));
    setSections([...results]);

    for (let i = 0; i < sectionDefs.length; i++) {
      results[i].status = 'loading';
      setSections([...results]);
      try {
        results[i].data = await sectionDefs[i].fetch();
        results[i].status = 'done';
      } catch (e: any) {
        results[i].status = 'error';
        results[i].data = { error: String(e?.message ?? e) };
      }
      setSections([...results]);
    }

    // Build the final report
    const report: Record<string, any> = {
      _meta: {
        generated_at: new Date().toISOString(),
        generator: 'ARIA Engineering Lab v0.4.0',
        sections: results.length,
        successful: results.filter(r => r.status === 'done').length,
      },
    };
    for (const r of results) {
      const key = r.label.toLowerCase().replace(/\s+/g, '_');
      report[key] = r.data;
    }

    // Download
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `aria-mission-report-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    a.click();
    URL.revokeObjectURL(url);

    setGenerating(false);
  };

  const doneCount = sections.filter(s => s.status === 'done').length;
  const errorCount = sections.filter(s => s.status === 'error').length;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Mission Report Export</h2>
        <p className="text-xs text-ui-text-dim">
          Generate a comprehensive JSON report aggregating data from 12 subsystems.
          Includes trajectory, crew, fuel, hull, objectives, power, BOM, and more.
        </p>
      </div>

      <button
        onClick={generateReport}
        disabled={generating}
        className={`px-6 py-3 rounded-xl border font-bold text-sm mb-4 ${
          generating
            ? 'bg-ui-bg-2 border-ui-border text-ui-text-dim cursor-not-allowed'
            : 'bg-ui-accent/60 border-ui-accent text-ui-accent hover:bg-cyan-800/80'
        }`}
      >
        {generating ? `Generating... (${doneCount}/${sections.length})` : 'Generate & Download Report'}
      </button>

      {/* Progress */}
      {sections.length > 0 && (
        <div className="space-y-1 mb-4">
          {sections.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <div className={`w-4 h-4 flex items-center justify-center rounded text-[10px] ${
                s.status === 'done' ? 'bg-sev-ok/50 text-sev-ok' :
                s.status === 'error' ? 'bg-sev-crit/50 text-sev-crit' :
                s.status === 'loading' ? 'bg-ui-accent/50 text-ui-accent animate-pulse' :
                'bg-ui-bg-2 text-ui-text-faint'
              }`}>
                {s.status === 'done' ? '✓' : s.status === 'error' ? '✗' : s.status === 'loading' ? '…' : '○'}
              </div>
              <span className={s.status === 'done' ? 'text-ui-text' : s.status === 'error' ? 'text-sev-crit' : 'text-ui-text-dim'}>
                {s.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {sections.length > 0 && !generating && (
        <div className={`p-3 rounded-lg border ${errorCount > 0 ? 'bg-sev-warn/20 border-sev-warn/50' : 'bg-sev-ok/20 border-sev-ok/50'}`}>
          <div className={`text-sm font-bold ${errorCount > 0 ? 'text-sev-warn' : 'text-sev-ok'}`}>
            Report downloaded — {doneCount}/{sections.length} sections collected
            {errorCount > 0 && ` (${errorCount} errors)`}
          </div>
        </div>
      )}

      {/* Report contents preview */}
      <div className="mt-4 bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
        <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">
          Report Contents
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-[10px]">
          {[
            'Mission phase + history', 'Trajectory (pos, vel, Δv)',
            'Fuel tanks + burn rate', 'Crew health (5 metrics)',
            'Hull damage (10 regions)', 'Objectives (14 items)',
            'Power budget (20 subsystems)', 'Bearing status',
            'Agriculture (5 crops)', 'BOM (28 items)',
            'Ship parameters', 'Communications link',
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-1">
              <div className="w-1.5 h-1.5 rounded-full bg-ui-accent" />
              <span className="text-ui-text">{item}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
