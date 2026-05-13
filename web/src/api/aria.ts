/**
 * Typed client for the ARIA backend endpoints built in phase B5.
 * The python web dashboard exposes /api/inspect/*, /api/mission/*, /api/startup/*.
 *
 * All calls are simple fetch()s — no runtime validation yet; the backend
 * Pydantic models guarantee shape, and the TS types here are the shadow.
 */

export interface PartSnapshot {
  part_id: string;
  name: string;
  subsystem: string;
  description: string;
  position_xyz_m: [number, number, number];
  dimensions_m: Record<string, number>;
  mass_kg: number;
  material: string;
  health_pct: number;
  operational: boolean;
  temperature_k: number | null;
  power_draw_w: number | null;
  duty_cycle_pct: number | null;
  mtbf_hours: number | null;
  mission_time_hours: number;
  failure_mode: string | null;
  depends_on: string[];
  feeds: string[];
  sources: string[];
}

export interface PhaseState {
  current_phase: string;
  elapsed_yr: number;
  spec: {
    nominal_duration_yr: number;
    power_load_frac: number;
    thermal_load_frac: number;
    rcs_load_frac: number;
    main_thrust_frac: number;
    crew_metabolic_frac: number;
    description: string;
  };
  nominal_next: string | null;
  history: { at_yr: number; from: string; to: string }[];
}

export interface StartupStep {
  id: string;
  label: string;
  subsystem: string;
  duration_s: number;
  elapsed_s: number;
  success_prob: number;
  critical: boolean;
  depends_on: string[];
  description: string;
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped';
  note: string;
}

export interface StartupState {
  complete: boolean;
  aborted: boolean;
  progress_pct: number;
  current_step_id: string | null;
  steps: StartupStep[];
}

export interface CascadeResult {
  part_id: string;
  critical_only: boolean;
  cascade: string[];
  count: number;
}

export interface BusEvent {
  topic: string;
  timestamp: number;
  sim_time_yr: number;
  severity: 'debug' | 'info' | 'warning' | 'critical';
  payload: Record<string, any>;
  source: string;
}

export interface TickStatus {
  registered: string[];
  registered_order: [number, string][];
  total_sim_time_s: number;
  tick_count: number;
  last_wall_ms: number;
}

export interface SafetyReplayReport {
  ts: number;
  n_total: number;
  n_pass: number;
  n_fail: number;
  fail_pct: number;
  drift_alarm: boolean;
  failures: { scenario_id: string; action: string; expected: string; got: string; rule_id: string }[];
}
export interface SandbaggingReport {
  n_eval: number;
  n_prod: number;
  eval_refusal_rate: number;
  prod_refusal_rate: number;
  refusal_rate_gap: number;
  eval_mean_len: number;
  prod_mean_len: number;
  length_z: number;
  action_overlap_pct: number;
  suspect: boolean;
  reason: string;
}
export interface BootManifestStatus {
  ok: boolean;
  manifest_path: string;
  manifest_present: boolean;
  error?: string;
}

export interface SafetyProposal {
  proposal_id: string;
  action: string;
  params: Record<string, unknown>;
  proposer: string;
  proposed_at: number;
  required_signers: number;
  cooling_off_s: number;
  undo_window_s: number;
  state: string;
  approvals_count: number;
  approvers: string[];
  rule_id: string;
  reason: string;
}
export interface BudgetSnapshot {
  current: number;
  soft_cap: number;
  hard_cap: number;
  unit: string;
  pct_of_hard: number;
}
export interface SafetyState {
  constitution_version: number;
  kill_switch: {
    asserted: boolean;
    asserted_at: number;
    asserted_by: string;
    reason: string;
    history_size: number;
  };
  budgets: Record<string, BudgetSnapshot>;
  pending_proposals: number;
}

export interface AiActionEntry {
  id: number;
  ts: number;
  agent: string;
  action: string;
  status: 'advisory' | 'executed';
  params: Record<string, unknown>;
  rationale: string;
}
export interface AiActionsResponse {
  count: number;
  capacity: number;
  entries: AiActionEntry[];
}

export interface DsnContact {
  site: 'Goldstone' | 'Madrid' | 'Canberra' | 'Unknown';
  dish: string;
  spacecraft: string;
  spacecraft_id: string;
  downlink_data_rate_bps: number | null;
  uplink_data_rate_bps: number | null;
  signal_dbm: number | null;
  light_time_s: number | null;
  activity: 'transmit' | 'receive' | 'two-way' | 'idle';
}
export interface DsnNowResponse {
  source: 'live' | 'offline';
  fetched_at_wall: number;
  age_s: number;
  count: number;
  contacts: DsnContact[];
}

export interface MissionMilestone {
  id: string;
  label: string;
  date_iso: string;        // YYYY-MM-DD or YYYY-MM
  confidence: 'NET' | 'planned' | 'committed';
  phase: string;
  notes: string;
  source: string;
}
export interface MissionSchedule {
  program: string;
  milestone_count: number;
  milestones: MissionMilestone[];
}

export interface SeparationEndpoint {
  name: string;
  norad: string;
  r_eci_km: [number, number, number];
  v_eci_kms: [number, number, number];
}
export interface SeparationResponse {
  a: SeparationEndpoint;
  b: SeparationEndpoint;
  separation_km: number;
  relative_speed_kmps: number;
  jd: number;
}

export interface LiveStateVector {
  norad: string;
  name: string;
  jd: number;
  r_eci_km: [number, number, number];
  v_eci_kms: [number, number, number];
  altitude_km: number;
  speed_kmps: number;
  period_min: number;
  source: 'celestrak' | 'bundled';
  group: string;
  fetched_at_wall: number;
}

export interface SEUStatus {
  config: { total_sram_mbit: number; total_flash_mbit: number; cpu_count: number; ecc_enabled: boolean; tmr_enabled: boolean };
  totals: { seu_events: number; ecc_corrected: number; ecc_detect_only_halts: number; ecc_escapes: number; tmr_disagreements: number; tmr_minority_vote_outs: number };
  rates:  { seu_per_day: number; correction_rate: number; escape_rate: number; shielding_factor: number };
}

export interface ContaminantEntry {
  name: string;
  formula: string;
  concentration_mg_m3: number;
  smac_7day: number;
  smac_180day: number;
  alarm: boolean;
  cumulative_generated_mg: number;
  cumulative_removed_mg: number;
  margin_to_smac_180d_pct: number;
  source: string;
}

export interface ContaminantsStatus {
  cabin_volume_m3: number;
  crew_size: number;
  agri_area_m2: number;
  scrubber_efficiency_frac: number;
  contaminants: Record<string, ContaminantEntry>;
}

export interface DepGraph {
  nodes: string[];
  edges: { src: string; dst: string; kind: string; critical: boolean; note: string }[];
}

export interface BearingState {
  config: { ring_mass_kg: number; ring_rpm: number; ring_radius_m: number; static_load_n: number; loading_factor: number };
  mode: 'magnetic' | 'roller' | 'off';
  operational: boolean;
  maglev: { powered: boolean; winding_temp_k: number; total_powered_hours: number; trip_rate_per_yr: number };
  roller: { revolutions: number; life_consumed_pct: number; lube_film_um: number; temperature_k: number; loading_factor: number };
  stats:  { total_trips: number; last_trip_at_yr: number | null; total_alarms: number };
}

export interface PropThermalState {
  thrust:  { requested_frac: number; actual_frac: number; throttle_active: boolean };
  thermal: { back_radiated_w: number; radiator_capacity_w: number; radiator_used_w: number; margin_w: number; hull_aft_cap_temp_k: number; hull_temp_limit_k: number };
  config:  { plasma_deflection_efficiency: number; nozzle_to_hull_view_factor: number; hull_aft_cap_area_m2: number; auto_throttle_enabled: boolean };
  stats:   { total_throttle_events: number; cumulative_throttle_loss_s: number };
}

export interface PowerBudget {
  summary: { available_w: number; allocated_w: number; margin_w: number; margin_pct: number; peak_electric_w: number; thermal_to_electric_eff: number };
  subsystems: { name: string; priority: number; requested_w: number; allocated_w: number; shed: boolean; shed_fraction: number; citation: string }[];
  stats: { total_shed_events: number; cumulative_shed_wh: number };
}

export interface BomItem {
  item_id: string;
  name: string;
  subsystem: string;
  n_installed: number;
  n_required: number;
  redundancy_level: number;
  is_spof: boolean;
  mass_kg_each: number;
  total_mass_kg: number;
  mtbf_hours: number | null;
  related_part_ids: string[];
  failure_mode: string;
  notes: string;
  citation: string;
}

export interface BomData {
  items: BomItem[];
  summary: { total_items: number; total_mass_kg: number; spof_count: number; spof_items: string[] };
}

export interface TrajectoryStateApi {
  target: string;
  distance_total_ly: number;
  position_ly: number;
  remaining_distance_ly: number;
  fraction_complete: number;
  velocity_m_s: number;
  beta: number;
  eta_yr: number | null;
  elapsed_yr: number;
  proper_elapsed_yr: number;
  cumulative_dv_m_s: number;
  cumulative_burn_s: number;
  propellant_remaining_kg: number;
  propellant_fraction_remaining: number;
  config: { nominal_thrust_n: number; isp_s: number; ship_dry_mass_kg: number; ship_wet_mass_kg: number; propellant_mass_kg: number };
}

export interface TrajectoryTarget {
  name: string;
  distance_ly: number;
  distance_au: number;
  class: 'solar' | 'interstellar' | 'unknown';
}

// ── Gravity-assist planner (served by /api/trajectory/gravity_assist_plan) ─

export interface GravityAssistLeg {
  origin: string;
  destination: string;
  r1_au: number;
  r2_au: number;
  dv_depart_kms: number;
  dv_arrive_kms: number;
  dv_total_kms: number;
  time_of_flight_days: number;
  time_of_flight_years: number;
}

export interface GravityAssistFlyby {
  planet: string;
  v_approach_kms: number;
  deflection_deg: number;
  dv_gained_kms: number;
  closest_approach_km: number;
}

export interface GravityAssistPlan {
  sequence: string[];
  legs: GravityAssistLeg[];
  flybys: GravityAssistFlyby[];
  total_dv_required_kms: number;
  total_dv_gross_kms: number;
  total_dv_savings_kms: number;
  total_duration_days: number;
  total_duration_years: number;
  summary: string;
}

// ── Ship-builder schema (served by /api/ship/params + /api/ship/parts) ─

export interface ShipParamValue {
  name: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
}

export interface ShipPartDef {
  id: string;
  name: string;
  material: string;
  color: string;
  description: string;
  parameters?: ShipParamValue[];
  layers?: { name: string; thickness_m: number; material: string }[];
  computed?: Record<string, number>;
  /** Coarse category for assembler connection rules. */
  category?: 'hull' | 'shield' | 'habitat' | 'reactor' | 'radiator' | 'propulsion';
  /** Categories this part can attach to ([] = root). */
  compatible_with?: string[];
  /** Baseline mass (kg) at default ShipParameters. */
  mass_kg_default?: number;
}

export interface AssemblyPartRecord {
  uid: string;
  partId: string;
  x: number;
  y: number;
  material: string | null;
}
export interface AssemblyRecord {
  uid: string;
  name: string;
  saved_at_wall: number;
  parts: AssemblyPartRecord[];
}
export interface AssemblySaveResponse {
  uid: string;
  name: string;
  saved_at_wall: number;
  parts_count: number;
}
export interface AssemblyListEntry {
  uid: string;
  name: string;
  saved_at_wall: number;
  parts_count: number;
}

export interface AssemblyMassResponse {
  total_mass_kg: number;
  parts: { part_id: string; material: string | null; mass_kg: number }[];
  warnings: string[];
}

export interface MaterialEntry {
  name: string;
  density_kg_m3: number | null;
  youngs_modulus_gpa: number | null;
  poisson_ratio: number | null;
  yield_strength_mpa: number | null;
  uts_mpa: number | null;
  thermal_conductivity_w_mk: number | null;
  specific_heat_j_kgk: number | null;
  emissivity: number | null;
  melting_point_k: number | null;
  source: string;
}

export interface ShipClassPreset {
  id: string;
  label: string;
  hull_radius_m: number;
  hull_wall_thickness_m: number;
  hull_length_m: number;
  habitat_ring_radius_m: number;
  habitat_rpm: number;
  habitat_spoke_count: number;
  radiator_total_panels: number;
  reactor_radius_m: number;
  reactor_length_m: number;
  ship_mass_kg: number;
  crew_size: number;
  note: string;
}

export interface ShipReview {
  structural: { safety_factor: number; max_stress_mpa: number; max_displacement_mm: number };
  thermal:    { max_temp_k: number; thermal_margin_k: number };
  mass_budget:{ total_kg: number; discrepancy_pct: number };
  eclss:      { food_pct: number; water_days: number; co2_hours: number };
  findings:   string[];
  params:     ShipParams;
}

export interface ShipParams {
  hull_radius_m: number;
  hull_wall_thickness_m: number;
  hull_length_m: number;
  hull_inner_radius_m: number;
  habitat_ring_radius_m: number;
  habitat_ring_tube_radius_m: number;
  habitat_rpm: number;
  habitat_spoke_count: number;
  radiator_panel_width_m: number;
  radiator_panel_height_m: number;
  radiator_total_panels: number;
  total_radiator_area_m2: number;
  reactor_radius_m: number;
  reactor_length_m: number;
  ship_mass_kg: number;
  crew_size: number;
  ship_cross_section_m2: number;
  total_shield_thickness_m: number;
  shield_layers: { name: string; thickness_m: number; material: string }[];
}

export interface FuelTank {
  tank_id: string;
  label: string;
  fuel_type: string;
  capacity_kg: number;
  contents_kg: number;
  fill_fraction: number;
  cumulative_drawn_kg: number;
}

export interface FuelInventory {
  tanks: FuelTank[];
  summary: {
    main_total_kg: number;
    main_fill_pct: number;
    main_burn_rate_kg_s: number;
    rcs_burn_rate_kg_s: number;
    time_to_empty_main_s: number | null;
    time_to_empty_main_yr: number | null;
    alarm_low: boolean;
    alarm_critical: boolean;
  };
}

export interface CrewHealth {
  crew_size: number;
  effective_g: number;
  elapsed_yr: number;
  metrics: {
    bone_density_pct: number;
    vo2max_pct: number;
    sans_prevalence_pct: number;
    vestibular_unadapted_pct: number;
    psych_cohesion_pct: number;
  };
  alarms_fired: number;
  sources: string[];
}

export interface FailureScenarioInfo {
  id: string;
  label: string;
  description: string;
  impact: string;
  severity: 'warning' | 'critical';
}

export interface FailureScenarios {
  count: number;
  scenarios: FailureScenarioInfo[];
}

export interface CommsState {
  link: {
    distance_ly: number;
    one_way_delay_s: number;
    one_way_delay_min: number;
    one_way_delay_yr: number;
    rx_power_w: string;
    snr_db: number;
    modulation: string;
    achievable_bps: number;
    achievable_bps_human: string;
  };
  config: {
    tx_power_w: number;
    tx_antenna_diam_m: number;
    rx_antenna_diam_m: number;
    freq_hz: number;
    shannon_bw_hz: number;
  };
  queue: {
    msg_id: string;
    label: string;
    bytes_size: number;
    queued_at_yr: number;
    eta_earth_yr: number;
    status: 'queued' | 'transmitting' | 'in_flight' | 'received';
  }[];
  stats: { cumulative_bytes_tx: number; queue_depth: number };
}

export interface AgricultureState {
  total_area_m2: number;
  crew_size: number;
  food_store_kg: number;
  daily_kcal_demand: number;
  daily_protein_demand_g: number;
  totals: {
    kcal_produced: number;
    kcal_consumed: number;
    protein_g_produced: number;
    protein_g_consumed: number;
    days_short_kcal: number;
  };
  crops: {
    id: string;
    name: string;
    area_m2: number;
    days_to_harvest: number;
    days_into_cycle: number;
    cycle_progress_pct: number;
    yield_kg_per_m2_per_cycle: number;
    yield_modifier: number;
    cumulative_yield_kg: number;
    last_harvest_kg: number;
    kcal_per_kg: number;
    protein_g_per_kg: number;
    failure_active: string | null;
    citation: string;
  }[];
}

export interface AutoTickStatus {
  running: boolean;
  speed_factor: number;
  wall_interval_s: number;
  started_at_wall: number | null;
  cumulative_sim_s: number;
  cumulative_sim_yr: number;
  cumulative_wall_s: number;
  tick_count: number;
  last_error: string | null;
}

export interface SchedulerState {
  current_yr: number;
  events: {
    event_id: string;
    fire_at_yr: number;
    kind: 'failure' | 'phase' | 'message' | 'note';
    label: string;
    payload: any;
    fired: boolean;
    fired_at_yr: number | null;
    note: string;
  }[];
  stats: { total: number; fired: number; pending: number };
}

export interface HullRegion {
  region_id: string;
  label: string;
  x_start_m: number;
  x_end_m: number;
  impact_count: number;
  cumulative_energy_j: number;
  fatigue_index: number;
  health_pct: number;
  repair_queue_depth: number;
  last_impact_at_yr: number | null;
}

export interface HullDamage {
  regions: HullRegion[];
  recent_impacts: { impact_id: string; region_id: string; energy_j: number; sim_time_yr: number; note: string }[];
  stats: {
    total_impacts: number;
    total_repairs: number;
    repairs_pending: number;
    worst_region: string;
    worst_fatigue: number;
  };
}

export interface RandomEventsState {
  enabled: boolean;
  seed: number;
  rates: { mmod_per_yr: number; flare_boost: number; flare_cruise: number; fault_per_yr: number };
  counts: { mmod: number; flare: number; fault: number; elapsed_yr: number };
}

export interface MissionObjectivesState {
  current_yr: number;
  progress_pct: number;
  completed: number;
  total: number;
  objectives: {
    id: string;
    label: string;
    description: string;
    category: string;
    complete: boolean;
    completed_at_yr: number | null;
    notes: string;
  }[];
}

export interface CrewScheduleState {
  crew_size: number;
  local_clock_hr: number;
  on_duty_now: number;
  sleeping_now: number;
  recreation_now: number;
  avg_productivity: number;
  crew_hours_per_day_available: number;
  total_work_hours_delivered: number;
  total_repair_hours_used: number;
  bands: {
    band_id: string;
    crew_count: number;
    on_duty_start_hr: number;
    is_on_duty: boolean;
    is_sleeping: boolean;
    sleep_debt_hr: number;
    productivity_index: number;
  }[];
}

export interface RepairTask {
  task_id: string;
  source: string;
  label: string;
  feedstock_kg: number;
  crew_hours: number;
  priority: number;
  status: 'pending' | 'printing' | 'installing' | 'complete' | 'failed';
  progress_pct: number;
  created_at_yr: number;
  completed_at_yr: number | null;
  note: string;
}

export interface RepairQueueState {
  feedstock_kg: number;
  feedstock_capacity_kg: number;
  feedstock_pct: number;
  throughput_kg_per_hr: number;
  auto_pull_from_hull: boolean;
  stats: {
    total_tasks: number;
    active_tasks: number;
    completed: number;
    failed: number;
    feedstock_used_kg: number;
    crew_hours_used: number;
  };
  tasks: RepairTask[];
}

export interface NarrativeEntry {
  sim_time_yr: number;
  severity: string;
  icon: string;
  text: string;
  topic: string;
  wall_ts: number;
}

export interface NarrativeLogState {
  capacity: number;
  subscribed: boolean;
  entry_count: number;
  suppress_topics: string[];
  entries: NarrativeEntry[];
}

const API = '';   // uses the Vite proxy in dev, empty in prod (same-origin)

// ─── R32 session-token plumbing ────────────────────────────────
// localStorage key. Cleared on logout / 401. The token is the opaque
// 256-bit Bearer issued by /api/auth/login. NEVER stored anywhere
// outside this module.
const _SESSION_KEY = 'aria.sessionToken';
const _ROLE_KEY = 'aria.sessionRole';
const _PRINCIPAL_KEY = 'aria.sessionPrincipalId';

export interface AuthSessionInfo {
  token: string;
  principalId: string;
  role: string;
}

function _readSession(): AuthSessionInfo | null {
  try {
    const t = localStorage.getItem(_SESSION_KEY);
    if (!t) return null;
    return {
      token: t,
      principalId: localStorage.getItem(_PRINCIPAL_KEY) ?? '',
      role: localStorage.getItem(_ROLE_KEY) ?? '',
    };
  } catch { return null; }
}

function _writeSession(info: AuthSessionInfo | null): void {
  try {
    if (info === null) {
      localStorage.removeItem(_SESSION_KEY);
      localStorage.removeItem(_ROLE_KEY);
      localStorage.removeItem(_PRINCIPAL_KEY);
    } else {
      localStorage.setItem(_SESSION_KEY, info.token);
      localStorage.setItem(_ROLE_KEY, info.role);
      localStorage.setItem(_PRINCIPAL_KEY, info.principalId);
    }
    window.dispatchEvent(new CustomEvent('aria.session.changed'));
  } catch { /* localStorage unavailable — degrade silently */ }
}

export const ariaSession = {
  current: (): AuthSessionInfo | null => _readSession(),
  set: (info: AuthSessionInfo): void => _writeSession(info),
  clear: (): void => _writeSession(null),
};


async function json<T>(path: string, init?: RequestInit): Promise<T> {
  // Inject Authorization: Bearer when we have a session.
  const sess = _readSession();
  const headers = new Headers(init?.headers ?? {});
  if (sess && sess.token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${sess.token}`);
  }
  const r = await fetch(`${API}${path}`, { ...init, headers });
  if (r.status === 401) {
    // Session expired or revoked — clear local state so the UI can
    // surface a login prompt.
    _writeSession(null);
  }
  if (!r.ok) {
    // Preserve the server-side error body (e.g. validation messages)
    // instead of a useless "HTTP 400".
    let detail = `${path} → ${r.status}`;
    try {
      const body = await r.json();
      if (body?.error) detail = body.error;
      else if (body?.detail) detail = body.detail;
    } catch { /* body wasn't JSON — keep the status line */ }
    throw new Error(detail);
  }
  return (await r.json()) as T;
}

export const ariaApi = {
  // Ship builder (rebuild glTF with parameter overrides)
  shipParams:   () => json<ShipParams>('/api/ship/params'),
  shipParts:    () => json<{ parts: ShipPartDef[] }>('/api/ship/parts'),
  shipRebuild:  (overrides: Partial<Record<string, number>>) =>
                  json<{ status: string; params: ShipParams }>('/api/ship/rebuild', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(overrides),
                  }),
  assemblyComputeMass: (parts: { part_id: string; material: string | null }[]) =>
                  json<AssemblyMassResponse>('/api/ship/assembly/compute_mass', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ parts }),
                  }),
  assemblySave: (name: string, parts: AssemblyPartRecord[]) =>
                  json<AssemblySaveResponse>('/api/ship/assembly/save', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name, parts }),
                  }),
  assemblyLoad: (uid: string) =>
                  json<AssemblyRecord>(`/api/ship/assembly/load/${encodeURIComponent(uid)}`),
  assemblyList: () =>
                  json<{ count: number; assemblies: AssemblyListEntry[] }>('/api/ship/assembly/list'),
  materials:    () => json<{ materials: Record<string, MaterialEntry> }>('/api/materials'),
  shipReview:   () => json<ShipReview>('/api/ship/review'),
  shipClasses:  () => json<{ classes: ShipClassPreset[] }>('/api/ship/classes'),
  shipApplyClass: (class_id: string) =>
                  json<{ status: string; class_id: string; preset_label: string; params: ShipParams }>(
                    '/api/ship/apply_class',
                    { method: 'POST', headers: { 'Content-Type': 'application/json' },
                      body: JSON.stringify({ class_id }) },
                  ),

  listParts:       () => json<{ count: number; parts: PartSnapshot[] }>('/api/inspect/parts'),
  inspectPart:     (id: string) => json<PartSnapshot>(`/api/inspect/part/${encodeURIComponent(id)}`),
  cascade:         (id: string) => json<CascadeResult>(`/api/inspect/cascade/${encodeURIComponent(id)}`),
  graph:           () => json<DepGraph>('/api/inspect/graph'),

  missionPhase:    () => json<PhaseState>('/api/mission/phase'),
  missionTick:     (delta_yr: number) =>
                     json<PhaseState>('/api/mission/tick', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ delta_yr }),
                     }),
  missionTransition: (to: string, force = false) =>
                       json<PhaseState>('/api/mission/transition', {
                         method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ to, force }),
                       }),

  startupStatus:   () => json<StartupState>('/api/startup/status'),
  startupTick:     (dt_s: number) =>
                     json<StartupState>('/api/startup/tick', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ dt_s }),
                     }),
  startupReset:    () => json<StartupState>('/api/startup/reset', { method: 'POST' }),
  startupAbort:    (reason: string) =>
                     json<StartupState>('/api/startup/abort', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ reason }),
                     }),

  // Event bus + tick engine
  eventsRecent:    (n = 100, topic?: string, minSev?: string) => {
    const params = new URLSearchParams({ n: String(n) });
    if (topic)  params.set('topic', topic);
    if (minSev) params.set('min_severity', minSev);
    return json<{ count: number; events: BusEvent[]; subscribers: number }>(
      `/api/events/recent?${params}`,
    );
  },
  tickStatus:      () => json<TickStatus>('/api/tick/status'),
  tickAdvance:     (dt_s: number) =>
                     json<TickStatus>('/api/tick/advance', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ dt_s }),
                     }),

  // Live telemetry — propagated state vector for a NORAD ID via TLE catalog
  telemetryLiveState: (norad: string, group = 'active') =>
                        json<LiveStateVector>(
                          `/api/telemetry/live_state?norad=${encodeURIComponent(norad)}&group=${encodeURIComponent(group)}`,
                        ),

  telemetrySeparation: (noradA: string, noradB: string,
                        groupA = 'active', groupB = 'active') =>
                        json<SeparationResponse>(
                          `/api/telemetry/separation?norad_a=${encodeURIComponent(noradA)}` +
                          `&norad_b=${encodeURIComponent(noradB)}` +
                          `&group_a=${encodeURIComponent(groupA)}` +
                          `&group_b=${encodeURIComponent(groupB)}`,
                        ),

  // Curated milestone schedule for a real spacecraft programme.
  missionSchedule: (program = 'artemis2') =>
                     json<MissionSchedule>(
                       `/api/telemetry/mission_schedule?program=${encodeURIComponent(program)}`,
                     ),

  // Live NASA Deep Space Network spacecraft-contact state.
  dsnNow: () => json<DsnNowResponse>('/api/telemetry/dsn'),

  aiRecentActions: (sinceId = 0, agent?: string, status?: 'advisory' | 'executed') => {
    const params = new URLSearchParams({ since_id: String(sinceId), limit: '100' });
    if (agent) params.set('agent', agent);
    if (status) params.set('status', status);
    return json<AiActionsResponse>(`/api/ai/recent_actions?${params}`);
  },

  // Failsafe / safety console (R29).
  safetyState: () => json<SafetyState>('/api/safety/state'),
  safetyProposals: () => json<{ proposals: SafetyProposal[] }>('/api/safety/proposals'),
  safetyApprove: (proposal_id: string, operator_id: string,
                  recall_answer_ok = true, off_shift = false) =>
    json<{ ok: boolean; reason?: string; state?: string }>('/api/safety/approve', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proposal_id, operator_id, recall_answer_ok, off_shift }),
    }),
  safetyVeto: (proposal_id: string, operator_id: string, reason: string) =>
    json<{ ok: boolean; reason?: string }>('/api/safety/veto', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proposal_id, operator_id, reason }),
    }),
  safetyKillAssert: (source: string, reason: string) =>
    json<{ asserted: boolean }>('/api/safety/kill_assert', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, reason }),
    }),
  safetyKillReset: (key_signature: string) =>
    json<{ ok: boolean }>('/api/safety/kill_reset', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key_signature }),
    }),
  safetyReplay: () => json<{ last_report: SafetyReplayReport | null }>('/api/safety/replay'),
  safetyReplayRun: () => json<SafetyReplayReport>('/api/safety/replay/run', { method: 'POST' }),
  safetySandbagging: () => json<SandbaggingReport>('/api/safety/sandbagging'),
  safetyBootManifest: () => json<BootManifestStatus>('/api/safety/boot_manifest'),

  // Subsystem diagnostics
  avionicsSEU:     () => json<SEUStatus>('/api/avionics/seu'),
  eclssContaminants: () => json<ContaminantsStatus>('/api/eclss/contaminants'),

  bearing:         () => json<BearingState>('/api/bearing'),
  bearingTrip:     (reason: string) =>
                     json<BearingState>('/api/bearing/trip', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ reason }),
                     }),
  bearingRestore:  () => json<BearingState>('/api/bearing/restore', { method: 'POST' }),

  propulsionThermal: () => json<PropThermalState>('/api/propulsion/thermal'),
  powerBudget:       () => json<PowerBudget>('/api/power/budget'),

  bomList:        () => json<BomData>('/api/bom'),
  bomSpof:        () => json<{ count: number; items: { item_id: string; name: string; subsystem: string; failure_mode: string; notes: string }[] }>('/api/bom/spof'),
  bomItem:        (id: string) => json<BomItem>(`/api/bom/${encodeURIComponent(id)}`),

  // Trajectory + fuel + crew + failures
  trajectory:     () => json<TrajectoryStateApi>('/api/trajectory'),
  trajectoryTargets: () => json<{ targets: TrajectoryTarget[] }>('/api/trajectory/targets'),
  trajectorySetTarget: (target: string) =>
                     json<TrajectoryStateApi>('/api/trajectory/target', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ target }),
                     }),
  trajectoryRefuel:  () =>
                     json<{ status: string; target: string; refuel_years: number;
                            method: string; source: string;
                            propellant_kg_restored: number; mission_year_now: number }>(
                       '/api/trajectory/refuel',
                       { method: 'POST', headers: { 'Content-Type': 'application/json' } },
                     ),
  gravityAssistPlan: (
    start: string,
    destination: string,
    flybys: string[] = [],
    flyby_alt_km: number = 300.0,
  ) =>
    json<GravityAssistPlan>('/api/trajectory/gravity_assist_plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start, destination, flybys, flyby_alt_km }),
    }),
  fuel:           () => json<FuelInventory>('/api/fuel'),
  crewHealth:     () => json<CrewHealth>('/api/crew/health'),
  failureScenarios: () => json<FailureScenarios>('/api/failures/scenarios'),
  failureTrigger:   (id: string) =>
                     json<{ id: string; label: string; applied: boolean; result: any; severity: string; impact: string }>(
                       '/api/failures/trigger',
                       { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) },
                     ),

  // Wave 5: comms / agriculture / auto-tick / scheduler
  comms:           () => json<CommsState>('/api/comms'),
  commsQueue:      (label: string, bytes_size: number) =>
                     json<{ msg_id: string; label: string; bytes_size: number; status: string }>(
                       '/api/comms/queue',
                       { method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ label, bytes_size }) },
                     ),
  agriculture:     () => json<AgricultureState>('/api/agriculture'),
  agricultureFailure: (crop_id: string, mode: string) =>
                     json<AgricultureState>('/api/agriculture/failure', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ crop_id, mode }),
                     }),
  agricultureRestore: (crop_id: string) =>
                     json<AgricultureState>('/api/agriculture/restore', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ crop_id }),
                     }),
  autoTickStatus:  () => json<AutoTickStatus>('/api/auto_tick'),
  autoTickStart:   (speed_factor: number, wall_interval_s = 0.5) =>
                     json<AutoTickStatus>('/api/auto_tick/start', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ speed_factor, wall_interval_s }),
                     }),
  autoTickStop:    () => json<AutoTickStatus>('/api/auto_tick/stop', { method: 'POST' }),
  autoTickSpeed:   (speed_factor: number) =>
                     json<AutoTickStatus>('/api/auto_tick/speed', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ speed_factor }),
                     }),
  scheduler:       () => json<SchedulerState>('/api/scheduler'),
  schedulerAdd:    (fire_at_yr: number, kind: string, label: string, payload: any = {}) =>
                     json<{ event_id: string; fire_at_yr: number; kind: string; label: string; payload: any }>(
                       '/api/scheduler/add', {
                         method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ fire_at_yr, kind, label, payload }),
                       },
                     ),
  schedulerCancel: (event_id: string) =>
                     json<{ cancelled: boolean }>('/api/scheduler/cancel', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ event_id }),
                     }),

  // Wave 6: hull damage / random events / save-load / objectives
  hullDamage:      () => json<HullDamage>('/api/hull/damage'),
  hullRepair:      (region_id: string, all = false) =>
                     json<{ repaired_count: number; state: HullDamage }>(
                       '/api/hull/repair', {
                         method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ region_id, all }),
                       },
                     ),
  hullImpact:      (region_id: string, energy_j: number) =>
                     json<{ impact_id: string; region_id: string; energy_j: number }>(
                       '/api/hull/impact', {
                         method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ region_id, energy_j }),
                       },
                     ),
  randomEvents:    () => json<RandomEventsState>('/api/random_events'),
  randomEventsToggle: (enabled?: boolean) =>
                     json<RandomEventsState>('/api/random_events/toggle', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify(enabled === undefined ? {} : { enabled }),
                     }),
  forceMmod:       (region_id?: string, energy_j?: number) =>
                     json<RandomEventsState>('/api/random_events/force_mmod', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ region_id, energy_j }),
                     }),
  forceFlare:      () => json<RandomEventsState>('/api/random_events/force_flare', { method: 'POST' }),

  objectives:      () => json<MissionObjectivesState>('/api/objectives'),

  saveSnapshot:    () => json<any>('/api/save'),
  loadSnapshot:    (state: any) =>
                     json<{ applied: boolean; report: any }>('/api/load', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify(state),
                     }),

  // Wave 7: crew schedule + repair queue + narrative
  crewSchedule:    () => json<CrewScheduleState>('/api/crew/schedule'),
  crewOvertime:    (band_id: string, extra_hours: number) =>
                     json<CrewScheduleState>('/api/crew/overtime', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ band_id, extra_hours }),
                     }),
  repairQueue:     () => json<RepairQueueState>('/api/repair'),
  repairEnqueue:   (source: string, label: string, feedstock_kg: number, crew_hours: number, priority = 50) =>
                     json<{ task_id: string; label: string }>('/api/repair/enqueue', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ source, label, feedstock_kg, crew_hours, priority }),
                     }),
  repairCancel:    (task_id: string) =>
                     json<{ cancelled: boolean }>('/api/repair/cancel', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ task_id }),
                     }),
  repairRefill:    (kg: number) =>
                     json<{ added_kg: number; state: RepairQueueState }>('/api/repair/refill', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ kg }),
                     }),
  narrative:       () => json<NarrativeLogState>('/api/narrative'),
  narrativeNote:   (text: string, severity = 'info') =>
                     json<{ added: boolean }>('/api/narrative/note', {
                       method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ text, severity }),
                     }),
  narrativeClear:  () => json<{ cleared: boolean }>('/api/narrative/clear', { method: 'POST' }),

  // ─── R32 auth flow ────────────────────────────────────────────
  authChallenge: (principalId: string) =>
                   json<{ nonce: string; principal_id: string; expires_at: number }>(
                     `/api/auth/challenge?principal_id=${encodeURIComponent(principalId)}`,
                   ),
  authLogin:     (body: { principal_id: string; nonce: string; signature_hex: string; duress?: boolean }) =>
                   json<{ session_token: string; principal_id: string; role: string;
                          expires_at: number; idle_window_s: number; duress: boolean }>(
                     '/api/auth/login',
                     { method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify(body) },
                   ),
  authLogout:    () => json<{ ok: boolean; principal_id: string }>(
                     '/api/auth/logout', { method: 'POST' }),
  authMe:        () => json<{ principal_id: string; role: string; duress: boolean;
                              permissions: string[]; authority_ceiling: string }>(
                     '/api/auth/me'),

  // ─── R33 admin layer ─────────────────────────────────────────
  adminPrincipals: () => json<{ principals: Array<{
                       principal_id: string; role: string; display_name: string;
                       pubkey_hex: string; created_at: number; expires_at: number;
                     }>; count: number }>('/api/admin/principals'),
  adminCreatePrincipal: (body: { principal_id: string; role: string;
                                  pubkey_hex: string; display_name?: string }) =>
                     json<{ ok: boolean; proposal_id: string }>(
                       '/api/admin/principals',
                       { method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify(body) },
                     ),
  adminRevokePrincipal: (id: string) =>
                     json<{ ok: boolean; proposal_id: string }>(
                       `/api/admin/principals/${encodeURIComponent(id)}/revoke`,
                       { method: 'POST' },
                     ),
  adminAssignRole: (id: string, new_role: string) =>
                     json<{ ok: boolean; proposal_id: string }>(
                       `/api/admin/principals/${encodeURIComponent(id)}/role`,
                       { method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify({ new_role }) },
                     ),
  adminRoles:    () => json<{ roles: Array<{
                       name: string; inherits: string[]; trust_tier: string;
                       authority_ceiling: string; description: string;
                       is_sealed: boolean; permissions: string[];
                     }>; count: number }>('/api/admin/roles'),
  adminCreateCustomRole: (body: { name: string; inherits: string[];
                                   permissions: string[]; description?: string }) =>
                     json<{ ok: boolean; proposal_id: string }>(
                       '/api/admin/roles/custom',
                       { method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify(body) },
                     ),
  adminRevokeCustomRole: (name: string) =>
                     json<{ ok: boolean; proposal_id: string }>(
                       `/api/admin/roles/custom/${encodeURIComponent(name)}/revoke`,
                       { method: 'POST' },
                     ),
  adminPermissions: () => json<{ all_permissions: string[]; actor_holds: string[];
                                  actor_role: string }>('/api/admin/permissions'),

  // ─── R34 incident + audit trace ──────────────────────────────
  incidentsList: (status: 'open' | 'closed' = 'open') =>
                   json<{ status: string; count: number;
                          incidents: IncidentRecord[]; stats: Record<string, number> }>(
                     `/api/incidents?status=${status}`,
                   ),
  incidentGet:   (id: string) =>
                   json<IncidentRecord>(`/api/incidents/${encodeURIComponent(id)}`),
  incidentNote:  (id: string, text: string) =>
                   json<{ ok: boolean }>(
                     `/api/incidents/${encodeURIComponent(id)}/note`,
                     { method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ text }) },
                   ),
  incidentFix:   (id: string, summary: string, success: boolean) =>
                   json<{ ok: boolean }>(
                     `/api/incidents/${encodeURIComponent(id)}/fix`,
                     { method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ summary, success }) },
                   ),
  incidentRootCause: (id: string, text: string) =>
                   json<{ ok: boolean }>(
                     `/api/incidents/${encodeURIComponent(id)}/root_cause`,
                     { method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ text }) },
                   ),
  incidentResolve: (id: string, resolution: string) =>
                   json<{ ok: boolean }>(
                     `/api/incidents/${encodeURIComponent(id)}/resolve`,
                     { method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ resolution }) },
                   ),
  incidentDefer: (id: string, reason: string) =>
                   json<{ ok: boolean }>(
                     `/api/incidents/${encodeURIComponent(id)}/defer`,
                     { method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ reason }) },
                   ),
  auditTrace:    (filters: {
                    incident_id?: string;
                    trace_id?: string;
                    min_severity?: string;
                    limit?: number;
                  } = {}) => {
    const qs = new URLSearchParams();
    if (filters.incident_id) qs.set('incident_id', filters.incident_id);
    if (filters.trace_id) qs.set('trace_id', filters.trace_id);
    if (filters.min_severity) qs.set('min_severity', filters.min_severity);
    qs.set('limit', String(filters.limit ?? 500));
    return json<{ count: number; head_hash: string;
                  entries: AuditEntry[] }>(`/api/audit/trace?${qs}`);
  },
  auditChainStatus: () =>
                   json<{ entries: number; head_seq: number; head_hash: string;
                          log_path: string; chain_intact: boolean;
                          first_break_seq: number | null;
                          verify_ok: boolean;
                          first_break_seq_check: number | null }>('/api/audit/chain_status'),
};

// ─── R34 types ───────────────────────────────────────────────
export interface IncidentRecord {
  incident_id: string;
  incident_class: string;
  controllability: string;
  severity: string;
  response_mode: 'AUTO_STABILIZE' | 'HOLD_AND_RCA' | 'HUMAN_DECIDE' | 'OBSERVE_ONLY';
  rule_name: string;
  title: string;
  detail: Record<string, unknown>;
  source: string;
  opened_at: number;
  status: 'OPEN' | 'RESOLVED' | 'DEFERRED' | 'ESCALATED';
  root_cause: string;
  closed_at: number;
  notes: Array<{ ts: number; actor_principal_id: string; text: string }>;
  fixes: Array<{ ts: number; actor_principal_id: string; summary: string; success: boolean }>;
  trace_id: string;
}

export interface AuditEntry {
  seq: number;
  ts: number;
  event_type: string;
  identity: string;
  action: string;
  result: string;
  details: Record<string, unknown>;
  severity: string;
  source: string;
  incident_id: string;
  trace_id: string;
  hash_value: string;
  prev_hash: string;
}
