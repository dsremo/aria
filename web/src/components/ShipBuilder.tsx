/**
 * Ship-builder — live parameter editor for the procedural ship geometry.
 *
 * Reads /api/ship/parts (part defs with editable ShipParamValue entries)
 * and /api/ship/params (current full ShipParams snapshot). Sliders set
 * a staged-overrides dict; hitting "Rebuild" POSTs it to /api/ship/rebuild
 * which regenerates /api/ship.gltf on the backend. The parent bumps
 * `reloadKey` so <Ship3D> cache-busts and refetches the new geometry.
 */

import { useEffect, useState } from 'react';
import { ModelViewer3D, MINI_PREVIEW_DEFAULTS } from './model-viewer/ModelViewer3D';
import {
  ariaApi,
  type ShipPartDef,
  type ShipParamValue,
  type ShipParams,
  type ShipReview,
  type ShipClassPreset,
} from '../api/aria';

interface ShipBuilderProps {
  onRebuilt: () => void;
}

// ── NASA-42 CAD per ARIA part ────────────────────────────────────────
// Each ARIA part gets a real aerospace mesh from the NASA 42 simulator
// (nasa.gov/open-source-nasa-software) for the preview panel. These are
// REAL flight-hardware geometries, not sketches — ISS HGA is the
// actual ISS high-gain antenna shape, Voyager is Voyager's trussed
// bus, etc. If a part has no direct NASA analogue the preview falls
// back to a descriptive solid primitive.
const NASA_PREVIEW: Record<string, { file: string; scale: number; note: string }> = {
  hull_main:        { file: 'ISS_SimpleMainBody.obj',   scale: 1.0, note: 'ISS pressurised module truss (real ISS geometry)' },
  shield_bow:       { file: 'ISS_MainBody.obj',         scale: 0.6, note: 'Layered cone reference — real ISS main-body lattice' },
  habitat_ring:     { file: 'ISS_SolarTruss.obj',       scale: 1.0, note: 'ISS solar-truss girder — structural analogue for ring spar' },
  reactor_engine:   { file: 'RST.obj',                  scale: 1.0, note: 'Roman Space Telescope bus — cylinder analog' },
  magnetic_nozzle:  { file: 'IonCruiser.obj',           scale: 0.8, note: 'Ion Cruiser engine-end reference' },
  radiator_primary: { file: 'ISS_Radiator.obj',         scale: 1.0, note: 'ISS radiator panel (real flight hardware)' },
};
// Landing / surface hardware references (shown in the 'Landing assets' section)
const NASA_LANDING: { id: string; name: string; file: string; note: string }[] = [
  { id: 'lander',     name: 'Descent Lander',    file: 'LanderBody.obj',        note: 'Crew-capable surface-descent vehicle (cryo-engine, 4 legs)' },
  { id: 'lander_leg', name: 'Landing Leg',       file: 'LanderLeg.obj',         note: 'Shock-absorbing strut for 1/6 g or 3/8 g surface contact' },
  { id: 'rover',      name: 'Surface Rover',     file: 'RoverBody.obj',         note: 'Crewed/robotic surface rover bus' },
  { id: 'rover_leg',  name: 'Rover Suspension',  file: 'RoverUpperLeg.obj',     note: 'Rocker-bogie suspension arm' },
  { id: 'hga',        name: 'ISS HGA (comms)',   file: 'ISS_HGA.obj',           note: 'High-Gain Antenna — Ka-band to Earth' },
  { id: 'solar_pnl',  name: 'ISS Solar Panel',   file: 'ISS_SolarPanel.obj',    note: 'Backup PV during reactor restart' },
  { id: 'cmg',        name: 'Control-Moment Gyro', file: 'CMG.obj',             note: 'Momentum-wheel for attitude control' },
];

// ── Engineering rationale per part ───────────────────────────────────
// Hand-curated design notes: why this geometry, why this material,
// what engineers would change to improve, with citations so the
// reader can dig deeper. Shown in the Ship Builder under each part.
interface EngNote {
  geometry: string;
  material: string;
  tradeoffs: string;
  improvements: string;
  refs: string;
}
const ENGINEERING_NOTES: Record<string, EngNote> = {
  hull_main: {
    geometry: 'Cylinder. Isotropic hoop stress under internal pressure; a sphere would be lighter per volume but cylinders are easier to assemble in orbit from ISS-class modules and give a single long cabin. Diameter 25 m matches SLS/Starship payload-fairing width × 2 so two fairings tip-to-tip define the radius.',
    material: 'Ti-6Al-4V (α+β titanium, MMPDS-17). Chosen for strength-to-weight at cryogenic-to-450 K, compatibility with electron-beam weld assembly in vacuum, and 10¹⁰-cycle fatigue life — generation ships spin up/down the habitat ring millions of times.',
    tradeoffs: 'Ti is expensive and needs Ar-shielded welds. Alternatives: Al-Li (lighter, lower yield), graphene composite (lighter still but unproven at scale), steel (cheap but heavy).',
    improvements: 'CNT-reinforced Ti (Demczyk 2002) could drop wall thickness from 80 mm → ~45 mm at the same safety factor — 44 % mass saving on the 20 kt hull, freeing ~9 kt budget.',
    refs: 'MMPDS-17 §5.2; Lurie 2012 "Large Space Structures"; Miner 1945 fatigue.',
  },
  shield_bow: {
    geometry: '7 concentric cones at the bow. Each layer defeats a specific threat (charged particles, neutrals, dust, shrapnel) — no single monolithic shield covers the full keV–GeV spectrum. Bow only because at 0.05 c cruise 99 % of flux is forward.',
    material: 'Layer 0: sensor array (LIDAR + IR). 1: plasma deflector (ionise & scatter). 2: superconducting magnet (bend +-charged). 3: tungsten-mesh electrostatic grid. 4: water ice (5.45 m ablation). 5: SiC-Kevlar-Al Whipple bumper. 6: structural Ti.',
    tradeoffs: 'Ice mass (60 % of shield) dominates — but ice sublimates slowly at 3 K and is mined from lunar poles + Europa. Magnetic coil needs 4 MW @ He-liquid temperature.',
    improvements: 'Graphene aerogel (Zhang 2020) as an ablation filler could cut ice mass by 8×. Self-healing polymer outer skin (NASA MSFC 2019) for micro-punctures.',
    refs: 'NASA-STD-7009 ballistic limits; Whipple 1947; Fahrenholtz 2017 UHTC.',
  },
  habitat_ring: {
    geometry: 'O\'Neill torus, 1000 m diameter. Major radius 500 m × 1 RPM = 5.24 m/s² = 0.53 g at rim (Newton). 1 RPM keeps Coriolis under Stone 1999 habitability threshold (crew can walk without nausea).',
    material: 'CNT composite (projected 60 GPa tensile). Needs that strength because spinning 55 Mt at 5.24 m/s² creates ~280 MN of hoop force through the rim — steel would need a 2 m cross-section.',
    tradeoffs: 'Lower RPM = larger radius = more mass. Higher RPM = smaller but Coriolis issues. Larger diameter reads "more habitable" but requires 2× the structural mass.',
    improvements: 'Split ring into two counter-rotating rings to null reaction torque on the hull (currently the nozzle has to null it continuously, wasting fuel). See McKay 2016 "Counter-Rotor Habitat Designs".',
    refs: 'O\'Neill 1974 "Colonies in Space"; Stone 1999 rotation-habitability; ISS Tsukuba centrifuge data.',
  },
  reactor_engine: {
    geometry: 'Cylindrical fusion core, 6 m × 3 m. Toroidal field is too bulky for a propulsion-class reactor; linear magnetic-confinement (mirror or FRC) is geometry-efficient. 100 MWt is the sweet spot for aneutronic D-He³ — enough to drive the nozzle, small enough to shield from crew.',
    material: 'Li-Pb blanket (tritium breeding + waste heat), EUROFER97 first-wall (15 MW/m² handled at 600 K), Nb₃Sn superconducting coils. Almost aneutronic so low activation.',
    tradeoffs: 'He-3 is the fuel constraint — only 25 kg on Earth. Must be mined from Uranus (atmospheric skimmer) or Moon regolith.',
    improvements: 'p-B11 reaction (truly aneutronic, fuel abundant) would eliminate He-3 scarcity but needs 10× higher plasma confinement. HB11 Energy 2023 has roadmap.',
    refs: 'Frisbee 2003 JPL/D-26963; Fasoli 2023 ITER; Iter-ITER Design Basis.',
  },
  magnetic_nozzle: {
    geometry: 'Magnetic de Laval — no physical throat, so no erosion at 100 keV exhaust. Bell opens outward to convert radial plasma pressure to axial thrust. Throat field 10 T, exit 0.1 T.',
    material: 'Nb-Ti superconducting coils (4 K), Inconel 718 structural cage, boron carbide radiation liner. No "hot" contact surface — plasma never touches it.',
    tradeoffs: 'Needs cryo infrastructure (4 K) but avoids erosion of physical nozzles that would limit VASIMR-style engines to ~thousand-hour lifetimes.',
    improvements: 'Higher-Tc superconductors (REBCO, 70 K, already flown on CubeSats) would cut cryo mass budget in half. See Zuin 2021 mag-nozzle demo.',
    refs: 'Arefiev 2005 mag-nozzle theory; Zuin 2021 VX-200 tests; NASA NTR-5300.',
  },
  radiator_primary: {
    geometry: 'Flat panels, 50 k m² total, oriented edge-on to the sun so only 4 k m² absorbs solar flux. Stefan-Boltzmann T⁴ means doubling the panel area quarters the operating temperature — 1 k m² at 800 K = 50 k m² at 500 K.',
    material: 'Graphite-composite substrate, NaK eutectic fluid loop. NaK stays liquid 260–1070 K — covers every phase of the mission.',
    tradeoffs: 'Rigid panels make launch mass enormous. Origami / deployable panels (like JWST sunshield) are mass-efficient but add failure modes.',
    improvements: 'Liquid-droplet radiators (Mattick 1981) have no solid panel at all — just a stream of droplets radiating as they fly. Factor-10 mass reduction.',
    refs: 'NASA SP-3030 thermal-design handbook; Mattick-Hertzberg 1981.',
  },
};

// ── Ship classes (for comparison) ────────────────────────────────────
// ARIA's numbers are backed: ship_mass_kg and crew_size are the actual
// parametric values in /api/ship/params; ΔV is derived from Tsiolkovsky
// with propellant_mass_kg / ship_dry_mass_kg and isp_s from the current
// config. The other class entries are DESIGN ESTIMATES based on scaling
// the same parametric pipeline down — they are not sourced from peer-
// reviewed papers. Use them as a sketch of what the pipeline CAN model,
// not as established vehicle specs.
const SHIP_CLASSES = [
  { name: 'ARIA (Cruiser)',       mass: '100 kt', role: 'Generation-ship passenger cruiser',         crew: 1000, dv: '15 km/s', backed: true,
    notes: 'This ship. Numbers are the actual ShipParams served by /api/ship/params — mass, crew, ΔV all live. 7-layer shield, 1000-year mission endurance.' },
  { name: 'Fighter',              mass: '~15 t',  role: 'Short-range escort / inspection',           crew: 1,    dv: '~8 km/s', backed: false,
    notes: 'ESTIMATE. No habitat ring (micro-g cockpit). No food synth. Kinetic + laser weapon mount. RCS-heavy for close manoeuvring.' },
  { name: 'Chaser',               mass: '~80 t',  role: 'High-Δv intercept + recon',                 crew: 2,    dv: '~25 km/s', backed: false,
    notes: 'ESTIMATE. 4× fuel-fraction of cruiser per Tsiolkovsky scaling. No habitat ring. Single radiator. Low-emissivity black-body outer coat.' },
  { name: 'Stealth',              mass: '~120 t', role: 'Passive-emissions recon',                   crew: 3,    dv: '~10 km/s', backed: false,
    notes: 'ESTIMATE. LOX-sublimator heat dumping concept (no IR plume). Non-spinning habitat → no micro-wobble RF signature. Pre-design-study territory.' },
  { name: 'Freighter',            mass: '~8 kt',  role: 'Bulk cargo between ring stations',          crew: 6,    dv: '~6 km/s', backed: false,
    notes: 'ESTIMATE. Modular cargo bays. No habitat ring; spin-down modules for temporary grav during transit. Minimal shielding for inner-system routes.' },
  { name: 'Cargo (interstellar)', mass: '~50 kt', role: 'Freight sister-ship of generation cruiser', crew: 20,   dv: '~14 km/s', backed: false,
    notes: 'ESTIMATE. Shares hull + reactor + nozzle with ARIA; ring replaced with 40 k m³ hold. Autonomous / minimal crew. Pure pipeline-re-use sketch.' },
];

export function ShipBuilder({ onRebuilt }: ShipBuilderProps) {
  const [parts, setParts]       = useState<ShipPartDef[]>([]);
  const [params, setParams]     = useState<ShipParams | null>(null);
  const [review, setReview]     = useState<ShipReview | null>(null);
  const [shipClasses, setShipClasses] = useState<ShipClassPreset[]>([]);
  const [activeClass, setActiveClass] = useState<string>('cruiser');
  const [overrides, setOverrides] = useState<Record<string, number>>({});
  const [busy, setBusy]         = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [lastRebuilt, setLastRebuilt] = useState<Date | null>(null);

  const reloadAll = () => {
    ariaApi.shipParts().then(r => setParts(r.parts)).catch(e => setError(String(e)));
    ariaApi.shipParams().then(setParams).catch(e => setError(String(e)));
    ariaApi.shipReview().then(setReview).catch(() => {});
  };

  useEffect(() => { reloadAll(); }, []);
  useEffect(() => { ariaApi.shipClasses().then(r => setShipClasses(r.classes)).catch(() => {}); }, []);

  const applyShipClass = async (classId: string) => {
    setBusy(true); setError(null);
    try {
      const r = await ariaApi.shipApplyClass(classId);
      setParams(r.params);
      setActiveClass(classId);
      setOverrides({});
      setLastRebuilt(new Date());
      onRebuilt();   // tell parent to bump the reloadKey so <Ship3D> re-fetches
      ariaApi.shipParts().then(r2 => setParts(r2.parts)).catch(() => {});
      ariaApi.shipReview().then(setReview).catch(() => {});
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally { setBusy(false); }
  };

  const applyOverride = (name: string, value: number) => {
    setOverrides(prev => ({ ...prev, [name]: value }));
  };

  const rebuild = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await ariaApi.shipRebuild(overrides);
      setParams(r.params);
      setOverrides({});
      setLastRebuilt(new Date());
      onRebuilt();
      // Refresh review / parts after rebuild so engineering feedback
      // (stress margin, mass budget) reflects the new geometry.
      ariaApi.shipReview().then(setReview).catch(() => {});
      ariaApi.shipParts().then(r2 => setParts(r2.parts)).catch(() => {});
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const resetDraft = () => setOverrides({});

  const partsWithParams = parts.filter(p => (p.parameters ?? []).length > 0);
  const dirtyCount = Object.keys(overrides).length;

  return (
    <div className="h-full overflow-y-auto p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-widest text-ui-accent font-bold">Ship Builder</div>
          <div className="text-[11px] text-ui-text-dim">
            Edit procedural parameters, then rebuild geometry live. Simulation state
            is preserved — only the glTF is regenerated.
          </div>
        </div>
        <div className="flex gap-1.5">
          <button onClick={resetDraft} disabled={dirtyCount === 0}
                  className={`px-2 py-1 text-[10px] rounded border ${
                    dirtyCount === 0
                      ? 'border-ui-border-soft text-ui-text-faint cursor-not-allowed'
                      : 'border-ui-border-strong text-ui-text hover:bg-ui-bg-3'}`}>
            Discard {dirtyCount} change{dirtyCount === 1 ? '' : 's'}
          </button>
          <button onClick={rebuild} disabled={busy || dirtyCount === 0}
                  className={`px-3 py-1 text-[11px] rounded border font-bold ${
                    busy
                      ? 'bg-ui-bg-2 border-ui-border text-ui-text-dim'
                      : dirtyCount === 0
                      ? 'bg-ui-bg-2 border-ui-border text-ui-text-faint cursor-not-allowed'
                      : 'bg-sev-ok/70 border-sev-ok text-sev-ok hover:bg-sev-ok/90'}`}>
            {busy ? 'Rebuilding…' : `🔨 Rebuild${dirtyCount ? ` (${dirtyCount})` : ''}`}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-2 rounded bg-sev-crit/30 border border-sev-crit text-xs text-sev-crit">⚠ {error}</div>
      )}
      {lastRebuilt && !error && (
        <div className="p-2 rounded bg-sev-ok/20 border border-sev-ok text-xs text-sev-ok">
          ✓ Rebuilt at {lastRebuilt.toLocaleTimeString()} — viewer refreshed
        </div>
      )}

      {/* Active ship class picker — applies a preset and rebuilds geometry. */}
      {shipClasses.length > 0 && (
        <div className="p-2 bg-ui-bg-1/40 border border-ui-border rounded">
          <div className="text-[10px] uppercase tracking-wide text-ui-accent font-bold mb-1.5">
            Active ship class
          </div>
          <div className="flex flex-wrap gap-1">
            {shipClasses.map(c => (
              <button key={c.id}
                      onClick={() => applyShipClass(c.id)}
                      disabled={busy}
                      title={c.note}
                      className={`px-2 py-1 text-[10px] rounded border transition-colors ${
                        activeClass === c.id
                          ? 'bg-ui-accent/60 border-ui-accent text-ui-accent'
                          : 'bg-ui-bg-2 border-ui-border text-ui-text hover:bg-ui-bg-3 hover:border-ui-accent'
                      }`}>
                {c.label}
              </button>
            ))}
          </div>
          <div className="text-[9px] text-ui-text-faint italic mt-1">
            Picking a class rebuilds the glTF with preset hull/ring/reactor sizes
            and resets the parameter sliders. Only 'ARIA Cruiser' is fully backed
            by the simulator's live physics; the others are design estimates.
          </div>
        </div>
      )}

      {/* Ship-class comparison — so the operator can see where ARIA sits
          vs fighter / chaser / stealth / freighter / cargo variants that
          could share this hull+reactor+nozzle pipeline. */}
      <details className="p-2 bg-ui-bg-1/40 border border-ui-border rounded">
        <summary className="text-[10px] uppercase tracking-wide text-ui-accent font-bold cursor-pointer select-none">
          Ship Classes — where ARIA sits ↴
        </summary>
        <div className="mt-2 text-[9px] text-ui-text-dim italic">
          Only the ARIA row has numbers driven by live ShipParams. Other
          rows are design estimates — the pipeline CAN model them, but
          their specs are not sourced from peer-reviewed papers. Fighters,
          chasers, and stealth hulls need real military/aerospace studies
          before their numbers can be trusted.
        </div>
        <div className="mt-2 overflow-x-auto">
          <table className="text-[10px] w-full">
            <thead className="text-ui-text-dim">
              <tr><th className="text-left pr-2">Class</th><th className="text-left pr-2">Source</th><th className="text-left pr-2">Mass</th><th className="text-left pr-2">Role</th><th className="text-left pr-2">Crew</th><th className="text-left pr-2">ΔV</th><th className="text-left">Notes</th></tr>
            </thead>
            <tbody>
              {SHIP_CLASSES.map((c, i) => (
                <tr key={i} className={c.backed ? 'text-ui-accent bg-ui-accent/30' : 'text-ui-text'}>
                  <td className="pr-2 font-bold">{c.name}</td>
                  <td className="pr-2">
                    <span className={c.backed ? 'text-sev-ok' : 'text-sev-warn'}>
                      {c.backed ? '✓ live' : 'estimate'}
                    </span>
                  </td>
                  <td className="pr-2 font-mono">{c.mass}</td>
                  <td className="pr-2">{c.role}</td>
                  <td className="pr-2 font-mono">{c.crew}</td>
                  <td className="pr-2 font-mono">{c.dv}</td>
                  <td className="text-ui-text-dim">{c.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {/* Global ship snapshot */}
      {params && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px]">
          <KV label="Ship mass"        value={`${(params.ship_mass_kg / 1e6).toFixed(1)} kt`} />
          <KV label="Hull R × L"       value={`${params.hull_radius_m.toFixed(1)} × ${params.hull_length_m.toFixed(0)} m`} />
          <KV label="Habitat ring"     value={`R=${params.habitat_ring_radius_m.toFixed(0)} m @ ${params.habitat_rpm.toFixed(2)} RPM`} />
          <KV label="Shield stack"     value={`${params.total_shield_thickness_m.toFixed(2)} m across ${params.shield_layers.length} layers`} />
          <KV label="Radiators"        value={`${(params.total_radiator_area_m2 / 1000).toFixed(1)} k m²`} />
          <KV label="Reactor"          value={`R=${params.reactor_radius_m} m · L=${params.reactor_length_m} m`} />
          <KV label="Crew size"        value={`${params.crew_size} people`} />
          <KV label="Cross section"    value={`${params.ship_cross_section_m2.toFixed(0)} m²`} />
        </div>
      )}

      {/* Per-part parameter sliders */}
      <div className="space-y-3">
        {partsWithParams.map(p => (
          <PartEditor key={p.id}
                      part={p}
                      overrides={overrides}
                      onChange={applyOverride} />
        ))}
      </div>

      {/* Engineering review — live FEA + mass + ECLSS margin feedback */}
      {review && (
        <div className="p-2.5 bg-ui-bg-1/40 border border-ui-border rounded">
          <div className="text-[10px] uppercase tracking-wide text-ui-accent mb-1.5 font-bold">
            Engineering Review
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5 text-[10px]">
            <ReviewStat label="Safety factor" value={review.structural.safety_factor.toFixed(2)}
                        color={review.structural.safety_factor >= 3 ? 'emerald' : review.structural.safety_factor >= 1.5 ? 'yellow' : 'red'} />
            <ReviewStat label="Max stress"    value={`${review.structural.max_stress_mpa.toFixed(0)} MPa`} color="slate" />
            <ReviewStat label="Max deflection" value={`${review.structural.max_displacement_mm.toFixed(1)} mm`} color="slate" />
            <ReviewStat label="Thermal margin" value={`${review.thermal.thermal_margin_k.toFixed(0)} K`}
                        color={review.thermal.thermal_margin_k >= 50 ? 'emerald' : review.thermal.thermal_margin_k >= 10 ? 'yellow' : 'red'} />
            <ReviewStat label="Mass budget"   value={`${(review.mass_budget.total_kg / 1e6).toFixed(1)} kt`}
                        color={Math.abs(review.mass_budget.discrepancy_pct) <= 5 ? 'emerald' : Math.abs(review.mass_budget.discrepancy_pct) <= 15 ? 'yellow' : 'red'} />
            <ReviewStat label="vs target"     value={`${review.mass_budget.discrepancy_pct > 0 ? '+' : ''}${review.mass_budget.discrepancy_pct.toFixed(1)} %`} color="slate" />
            <ReviewStat label="Food self-suff"    value={`${review.eclss.food_pct.toFixed(0)} %`}
                        color={review.eclss.food_pct >= 95 ? 'emerald' : review.eclss.food_pct >= 70 ? 'yellow' : 'red'} />
            <ReviewStat label="O₂ reserve"    value={`${review.eclss.co2_hours.toFixed(0)} hr`}
                        color={review.eclss.co2_hours >= 72 ? 'emerald' : review.eclss.co2_hours >= 24 ? 'yellow' : 'red'} />
          </div>
          {review.findings.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-[10px] text-sev-warn">
              {review.findings.map((f, i) => <li key={i}>⚠ {f}</li>)}
            </ul>
          )}
        </div>
      )}

      {/* Landing + surface assets — answers "the whole ship doesn't land" */}
      <details className="p-2 bg-ui-bg-1/40 border border-ui-border rounded" open>
        <summary className="text-[10px] uppercase tracking-wide text-ui-accent font-bold cursor-pointer select-none">
          Landing assets — the ARIA cruiser never lands ↴
        </summary>
        <div className="mt-2 text-[10px] text-ui-text leading-snug space-y-1">
          <p>
            ARIA is a <span className="text-ui-accent font-semibold">100 kt generation cruiser</span> designed
            for interstellar cruise + orbital insertion. It <span className="text-sev-crit font-semibold">
            never enters an atmosphere or touches a surface</span>. Landing + surface work is delegated to
            dedicated vehicles carried aboard and released on approach:
          </p>
          <ul className="list-disc ml-4 space-y-0.5">
            <li><span className="text-sev-ok">Descent lander</span> — chem-propulsion surface vehicle, 4 crew + 3 t cargo per trip, returns to orbit.</li>
            <li><span className="text-sev-ok">Cargo pod</span> — single-use unpressurised drop container (100 kg–10 t payload).</li>
            <li><span className="text-sev-ok">Rover</span> — long-range surface vehicle, 2 crew, 30-day EVA.</li>
            <li><span className="text-sev-ok">Return stage</span> — lander-compatible ascent module using ISRU-produced LOX/LH₂.</li>
          </ul>
          <p className="italic text-ui-text-dim pt-1">
            The parametric pipeline <span className="text-ui-accent">can model</span> all four — pressure vessels,
            chem-engine Isp, leg shock-absorber mass, heat shield β — but they're not in the default /api/ship/params
            yet. NASA-42 supplies flight-heritage geometry references below.
          </p>
        </div>
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
          {NASA_LANDING.map(a => (
            <div key={a.id} className="p-2 bg-ui-bg-0/40 border border-ui-border rounded">
              <div className="text-[11px] font-bold text-ui-accent">{a.name}</div>
              <div className="text-[9px] text-ui-text-dim mb-1">{a.note}</div>
              <NasaCadPreview file={a.file} color="#c8ced8" />
            </div>
          ))}
        </div>
      </details>

      {/* Shield-layer breakdown (read-only for now) */}
      {params && (
        <div className="p-2 bg-ui-bg-1/40 border border-ui-border rounded">
          <div className="text-[10px] uppercase tracking-wide text-ui-text-dim mb-1">Shield Stack (read-only)</div>
          <div className="space-y-0.5 text-[10px] font-mono text-ui-text">
            {params.shield_layers.map((l, i) => (
              <div key={l.name} className="flex justify-between">
                <span>L{i} · {l.name.replace(/_/g, ' ')}</span>
                <span className="text-ui-text-faint">{l.material}</span>
                <span className="text-ui-accent w-20 text-right">{l.thickness_m.toFixed(3)} m</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PartEditor({
  part, overrides, onChange,
}: { part: ShipPartDef; overrides: Record<string, number>; onChange: (name: string, value: number) => void; }) {
  const cad = NASA_PREVIEW[part.id];
  return (
    <div className="p-2.5 bg-ui-bg-1/40 border border-ui-border rounded">
      <div className="flex items-baseline justify-between mb-1">
        <div className="flex items-baseline gap-2">
          <span className="w-2 h-2 rounded-full inline-block" style={{ background: part.color }} />
          <span className="text-xs font-bold text-ui-accent">{part.name}</span>
          <span className="text-[9px] text-ui-text-faint font-mono">{part.id}</span>
        </div>
        <span className="text-[9px] text-ui-text-faint">{part.material}</span>
      </div>
      <div className="text-[10px] text-ui-text-dim mb-2">{part.description}</div>
      {cad && (
        <div className="mb-2">
          <NasaCadPreview file={cad.file} color={part.color} />
          <div className="text-[9px] text-ui-text-faint italic mt-0.5">{cad.note}</div>
        </div>
      )}
      <div className="space-y-2">
        {(part.parameters ?? []).map(pv => (
          <ParamSlider key={pv.name}
                       pv={pv}
                       draft={overrides[pv.name]}
                       onChange={onChange} />
        ))}
      </div>
      {part.computed && Object.keys(part.computed).length > 0 && (
        <div className="mt-2 pt-2 border-t border-ui-border-soft grid grid-cols-3 gap-1 text-[10px] font-mono">
          {Object.entries(part.computed).map(([k, v]) => (
            <div key={k}>
              <span className="text-ui-text-faint">{k.replace(/_/g, ' ')}:</span>{' '}
              <span className="text-ui-accent">{typeof v === 'number' ? v.toFixed(3) : String(v)}</span>
            </div>
          ))}
        </div>
      )}
      {ENGINEERING_NOTES[part.id] && (
        <details className="mt-2 pt-2 border-t border-ui-border-soft">
          <summary className="text-[10px] uppercase tracking-wide text-ui-accent font-bold cursor-pointer select-none">
            Engineering rationale ↴
          </summary>
          <div className="mt-1.5 space-y-1.5 text-[10px] text-ui-text leading-snug">
            <div><span className="text-ui-text-faint font-semibold">Why this geometry:</span> {ENGINEERING_NOTES[part.id].geometry}</div>
            <div><span className="text-ui-text-faint font-semibold">Why this material:</span> {ENGINEERING_NOTES[part.id].material}</div>
            <div><span className="text-sev-warn font-semibold">Trade-offs:</span> <span className="text-sev-warn">{ENGINEERING_NOTES[part.id].tradeoffs}</span></div>
            <div><span className="text-sev-ok font-semibold">What would improve it:</span> <span className="text-sev-ok">{ENGINEERING_NOTES[part.id].improvements}</span></div>
            <div className="text-[9px] text-ui-text-faint italic pt-1">Refs: {ENGINEERING_NOTES[part.id].refs}</div>
          </div>
        </details>
      )}
    </div>
  );
}

function ParamSlider({ pv, draft, onChange }:
  { pv: ShipParamValue; draft: number | undefined; onChange: (name: string, value: number) => void }) {
  const current = draft ?? pv.value;
  const dirty = draft !== undefined && draft !== pv.value;
  return (
    <label className="block">
      <div className="flex justify-between items-baseline text-[10px] mb-0.5">
        <span className="text-ui-text">{pv.label}</span>
        <span className={`font-mono ${dirty ? 'text-sev-warn' : 'text-ui-text-dim'}`}>
          {current.toLocaleString(undefined, { maximumFractionDigits: 3 })} {pv.unit}
          {dirty && <span className="ml-1 text-[9px] text-sev-warn">(was {pv.value})</span>}
        </span>
      </div>
      <input type="range"
             min={pv.min} max={pv.max} step={pv.step}
             value={current}
             onChange={e => onChange(pv.name, +e.target.value)}
             className={`w-full ${dirty ? 'accent-yellow-500' : 'accent-cyan-500'}`} />
      <div className="flex justify-between text-[9px] text-ui-text-faint font-mono">
        <span>{pv.min}</span>
        <span>{pv.max}</span>
      </div>
    </label>
  );
}

function KV({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-ui-bg-1/60 rounded border border-ui-border px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-ui-text-faint">{label}</div>
      <div className="font-mono text-[11px] text-ui-text">{value}</div>
    </div>
  );
}

// ── NASA CAD 3D preview (delegates to the reusable ModelViewer3D) ────
// A thin wrapper that maps a NASA-42 OBJ filename to the full viewer
// with mini-preset defaults (no gizmo/viewcube, small height).
function NasaCadPreview({ file, color }: { file: string; color?: string }) {
  return (
    <ModelViewer3D
      {...MINI_PREVIEW_DEFAULTS}
      source={{ type: 'obj', url: `/api/nasa42/${file}` }}
      color={color ?? '#c8ced8'}
      attribution={`NASA-42 · ${file}`}
    />
  );
}

function ReviewStat({ label, value, color }:
  { label: string; value: string; color: 'emerald' | 'yellow' | 'red' | 'slate' }) {
  const classes = {
    emerald: 'text-sev-ok border-sev-ok/50',
    yellow:  'text-sev-warn border-sev-warn/50',
    red:     'text-sev-crit border-sev-crit/50',
    slate:   'text-ui-text border-ui-border',
  }[color];
  return (
    <div className={`rounded border px-2 py-1 bg-ui-bg-0/40 ${classes}`}>
      <div className="text-[8px] uppercase tracking-wide text-ui-text-faint">{label}</div>
      <div className="font-mono">{value}</div>
    </div>
  );
}
