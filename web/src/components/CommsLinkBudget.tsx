/**
 * Communications Link Budget — visual display of Earth link over distance.
 *
 * Polls /api/comms for current link parameters: distance, one-way delay,
 * SNR, modulation, bandwidth. Shows an SVG signal-strength gauge and
 * Friis-equation link budget breakdown.
 */

import { useEffect, useState } from 'react';
import { ariaApi, type CommsState } from '../api/aria';

const MOD_ORDER = ['BPSK', 'QPSK', '8-PSK', '16-QAM', '64-QAM'];

export function CommsLinkBudget() {
  const [comms, setComms] = useState<CommsState | null>(null);

  useEffect(() => {
    const refresh = () => ariaApi.comms().then(setComms).catch(() => {});
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  if (!comms) return <div className="p-4 text-sm text-ui-text-dim">Loading comms...</div>;

  const { link, config, queue, stats } = comms;

  // Signal quality gauge (SNR in dB, normalized to 0-100%)
  const snrPct = Math.max(0, Math.min(100, (link.snr_db + 10) * 2)); // -10 dB = 0%, 40 dB = 100%
  const snrColor = link.snr_db > 20 ? '#22c55e' : link.snr_db > 5 ? '#eab308' : '#ef4444';
  const snrLabel = link.snr_db > 20 ? 'STRONG' : link.snr_db > 5 ? 'MARGINAL' : 'WEAK';

  // Delay formatting
  const fmtDelay = (s: number) => {
    if (s < 60) return `${s.toFixed(1)} s`;
    if (s < 3600) return `${(s / 60).toFixed(1)} min`;
    if (s < 86400) return `${(s / 3600).toFixed(1)} hr`;
    return `${(s / 86400).toFixed(1)} d`;
  };

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Earth Communications Link Budget</h2>
        <p className="text-xs text-ui-text-dim">
          Ka-Band deep space link. Friis equation: P_rx = P_tx × G_tx × G_rx × (λ/4πd)².
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {/* Signal strength gauge */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4 flex flex-col items-center">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">Signal Strength</div>
          <svg viewBox="0 0 200 120" className="w-48">
            {/* Gauge arc */}
            <path
              d="M 20 100 A 80 80 0 0 1 180 100"
              fill="none" stroke="#1e293b" strokeWidth={12} strokeLinecap="round"
            />
            <path
              d="M 20 100 A 80 80 0 0 1 180 100"
              fill="none" stroke={snrColor} strokeWidth={12} strokeLinecap="round"
              strokeDasharray={`${snrPct * 2.5} 250`}
            />
            {/* Needle */}
            {(() => {
              const angle = Math.PI - (snrPct / 100) * Math.PI;
              const nx = 100 + 60 * Math.cos(angle);
              const ny = 100 - 60 * Math.sin(angle);
              return <line x1={100} y1={100} x2={nx} y2={ny} stroke="white" strokeWidth={2} />;
            })()}
            <circle cx={100} cy={100} r={4} fill="white" />
            <text x={100} y={80} textAnchor="middle" fontSize="20" fontWeight="700" fill={snrColor}>
              {link.snr_db.toFixed(1)}
            </text>
            <text x={100} y={93} textAnchor="middle" fontSize="10" fill="#94a3b8">dB SNR</text>
            <text x={100} y={115} textAnchor="middle" fontSize="11" fontWeight="600" fill={snrColor}>
              {snrLabel}
            </text>
          </svg>
        </div>

        {/* Link parameters */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">Link Parameters</div>
          <div className="space-y-2 text-xs">
            <Row label="Distance" value={link.distance_ly.toFixed(4)} unit="ly" />
            <Row label="One-way delay" value={fmtDelay(link.one_way_delay_s)} unit="" />
            <Row label="Round-trip" value={fmtDelay(link.one_way_delay_s * 2)} unit="" />
            <Row label="Modulation" value={link.modulation} unit="" />
            <Row label="Bandwidth" value={link.achievable_bps_human} unit="" />
            <Row label="Rx power" value={link.rx_power_w} unit="W" />
          </div>
        </div>

        {/* Modulation ladder */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">
            Modulation Step-Down Ladder
          </div>
          <div className="space-y-1">
            {MOD_ORDER.map(mod => {
              const active = mod === link.modulation;
              const passed = MOD_ORDER.indexOf(mod) <= MOD_ORDER.indexOf(link.modulation);
              return (
                <div key={mod} className={`flex items-center gap-2 px-2 py-1 rounded ${
                  active ? 'bg-ui-accent/50 border border-ui-accent' :
                  passed ? 'bg-ui-bg-2/50' : 'bg-ui-bg-1/30 opacity-40'
                }`}>
                  <div className={`w-3 h-3 rounded-full ${active ? 'bg-ui-accent' : passed ? 'bg-ui-bg-3' : 'bg-ui-bg-3'}`} />
                  <span className={`text-sm font-mono ${active ? 'text-ui-accent font-bold' : 'text-ui-text-dim'}`}>
                    {mod}
                  </span>
                  {active && <span className="text-[9px] text-ui-accent ml-auto">ACTIVE</span>}
                </div>
              );
            })}
          </div>
          <div className="text-[9px] text-ui-text-faint mt-2">
            Modulation downgrades as SNR decreases with distance.
          </div>
        </div>

        {/* Transmitter config */}
        <div className="bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold mb-2">
            Transmitter Configuration
          </div>
          <div className="space-y-2 text-xs">
            <Row label="TX power" value={(config.tx_power_w / 1000).toFixed(0)} unit="kW" />
            <Row label="TX antenna" value={config.tx_antenna_diam_m.toFixed(1)} unit="m" />
            <Row label="RX antenna" value={config.rx_antenna_diam_m.toFixed(0)} unit="m (DSN)" />
            <Row label="Frequency" value={(config.freq_hz / 1e9).toFixed(1)} unit="GHz" />
            <Row label="Shannon BW" value={(config.shannon_bw_hz / 1e6).toFixed(0)} unit="MHz" />
          </div>
          <div className="mt-3 text-[9px] text-ui-text-faint">
            Queue: {queue.length} messages · {(stats.cumulative_bytes_tx / 1024).toFixed(1)} KiB sent
          </div>
        </div>
      </div>

      {/* SNR vs distance — Friis projection.  Lets ops see how far the
          current link configuration can reach before SNR crosses the
          marginal / weak thresholds.  Current position marked by a
          cyan dot.  The three dashed horizontal bands are:
            · 20 dB  STRONG  (ceiling of green)
            ·  5 dB  MARGINAL (ceiling of yellow)
            ·  0 dB  LOST (noise floor). */}
      <div className="mt-3 bg-ui-bg-1/60 border border-ui-border rounded-lg p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-[10px] uppercase tracking-wider text-ui-text-faint font-bold">
            SNR vs Distance (Friis projection)
          </div>
          <div className="text-[9px] text-ui-text-faint">
            log₁₀ scale · current config
          </div>
        </div>
        <SnrVsDistanceChart
          txPowerW={config.tx_power_w}
          txAntennaM={config.tx_antenna_diam_m}
          rxAntennaM={config.rx_antenna_diam_m}
          freqHz={config.freq_hz}
          bandwidthHz={config.shannon_bw_hz}
          currentLy={link.distance_ly}
          currentSnr={link.snr_db}
        />
      </div>
    </div>
  );
}

/** Friis link-budget SNR(d) curve, rendered as an SVG line chart on a
 *  log-x axis.  Computed entirely client-side using the same config
 *  the backend uses, so the curve is consistent with the live gauge.
 *
 *  Pt_rx_dBm = Pt_tx_dBm + Gt + Gr + 20·log(λ/4πd)
 *  SNR_dB    = Pt_rx_dBm - 10·log(k·T·B) - 30  (Johnson noise, -174 dBm/Hz)
 *
 *  where Gt, Gr are parabolic-dish gains, d is distance in metres. */
function SnrVsDistanceChart({
  txPowerW, txAntennaM, rxAntennaM, freqHz, bandwidthHz,
  currentLy, currentSnr,
}: {
  txPowerW: number; txAntennaM: number; rxAntennaM: number;
  freqHz: number; bandwidthHz: number;
  currentLy: number; currentSnr: number;
}) {
  const c = 2.998e8;              // m/s
  const lambda = c / freqHz;
  // Parabolic-dish gain: G = (π d / λ)² · efficiency (≈ 0.55)
  const parabolicGain = (dm: number) =>
    Math.pow((Math.PI * dm) / lambda, 2) * 0.55;
  const gt = parabolicGain(txAntennaM);
  const gr = parabolicGain(rxAntennaM);
  const dBm = (w: number) => 10 * Math.log10(w) + 30;

  // Johnson-noise floor at 290 K (we're using the nominal ground-station
  // noise temperature as a single-figure approximation — the simulator's
  // real link budget uses a richer noise model, but this is close
  // enough for a planning curve).
  const kT = 1.381e-23 * 290;     // J
  const noiseDbm = 10 * Math.log10(kT * bandwidthHz * 1000);  // dBm

  const snrAt = (d_m: number) => {
    if (d_m <= 0) return 100;
    const fspl_dB = 20 * Math.log10(lambda / (4 * Math.PI * d_m));
    const rxDbm   = dBm(txPowerW) + 10 * Math.log10(gt) + 10 * Math.log10(gr) + fspl_dB;
    return rxDbm - noiseDbm;
  };

  // Sweep 0.1 AU → 1000 ly in log10 space.
  const AU = 1.496e11, LY = 9.461e15;
  const distances: { m: number; ly: number; snr: number }[] = [];
  for (let i = 0; i <= 50; i++) {
    const log10_m = Math.log10(0.1 * AU) + (i / 50) * (Math.log10(1000 * LY) - Math.log10(0.1 * AU));
    const d_m = Math.pow(10, log10_m);
    distances.push({ m: d_m, ly: d_m / LY, snr: snrAt(d_m) });
  }

  const W = 720, H = 160, padL = 40, padR = 14, padT = 10, padB = 22;
  const xMin = Math.log10(distances[0].ly || 1e-9);
  const xMax = Math.log10(distances[distances.length - 1].ly);
  const yMin = -30, yMax = 70;
  const xOf = (ly: number) => padL + ((Math.log10(Math.max(ly, 1e-12)) - xMin) / (xMax - xMin)) * (W - padL - padR);
  const yOf = (db: number) => H - padB - ((db - yMin) / (yMax - yMin)) * (H - padT - padB);

  let d = '';
  for (const p of distances) {
    const x = xOf(p.ly);
    const y = yOf(p.snr);
    d += `${d === '' ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)} `;
  }

  const bands = [
    { db: 20, label: '20 dB · strong',   color: '#22c55e' },
    { db:  5, label: ' 5 dB · marginal', color: '#eab308' },
    { db:  0, label: ' 0 dB · lost',     color: '#ef4444' },
  ];

  // log-axis grid for 1 AU, 1 lm, 1 ly, 10 ly, 100 ly, 1000 ly.
  const xTicks: { ly: number; label: string }[] = [
    { ly: AU / LY,          label: '1 AU' },
    { ly: 100 * AU / LY,    label: '100 AU' },
    { ly: 1,                label: '1 ly' },
    { ly: 10,               label: '10 ly' },
    { ly: 100,              label: '100 ly' },
    { ly: 1000,             label: '1000 ly' },
  ];

  return (
    <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} className="block">
      {/* Threshold bands */}
      {bands.map((b) => (
        <g key={b.db}>
          <line x1={padL} x2={W - padR} y1={yOf(b.db)} y2={yOf(b.db)}
                stroke={b.color} strokeWidth={0.7} strokeDasharray="3 3" opacity={0.6} />
          <text x={padL + 4} y={yOf(b.db) - 2} fontSize={8} fill={b.color} fontFamily="monospace">
            {b.label}
          </text>
        </g>
      ))}
      {/* y-axis gridlines */}
      {[-20, 0, 20, 40, 60].map((db) => (
        <text key={db} x={4} y={yOf(db) + 3} fontSize={8} fill="#64748b" fontFamily="monospace">
          {db}dB
        </text>
      ))}
      {/* x-axis ticks */}
      {xTicks.map((t) => (
        <g key={t.label}>
          <line x1={xOf(t.ly)} x2={xOf(t.ly)} y1={H - padB} y2={H - padB + 3}
                stroke="#334155" />
          <text x={xOf(t.ly)} y={H - padB + 12} fontSize={8} fill="#64748b"
                textAnchor="middle" fontFamily="monospace">
            {t.label}
          </text>
        </g>
      ))}
      {/* SNR curve */}
      <path d={d} stroke="#22d3ee" strokeWidth={1.8} fill="none" />
      {/* Current-position dot */}
      {currentLy > 0 && (
        <circle cx={xOf(currentLy)} cy={yOf(currentSnr)}
                r={4} fill="#22d3ee" stroke="#0f172a" strokeWidth={1.2} />
      )}
    </svg>
  );
}

function Row({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-ui-text-dim shrink-0">{label}</span>
      <span className="font-mono text-ui-text ml-auto truncate">
        {value}{unit && <span className="text-ui-text-faint ml-1">{unit}</span>}
      </span>
    </div>
  );
}
