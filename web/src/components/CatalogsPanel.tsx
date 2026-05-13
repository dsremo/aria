/**
 * Catalogs Browser — searchable list of everything in the ARIA sky database.
 *
 * Aggregates: exoplanet hosts, variable stars, double stars, NGC highlights,
 * meteor showers, bright asteroids, comets, major moons, 110 Messier objects.
 * Each row links its RA/Dec so the user can correlate against the
 * planetarium / sky-tonight views.
 */

import { useEffect, useMemo, useState } from 'react';

interface CatalogItem {
  source: string;             // which catalog it came from
  name: string;
  subtitle?: string;
  ra?: number;
  dec?: number;
  mag?: number;
  extra?: string;
}

type Source =
  | 'exoplanets' | 'variable_stars' | 'double_stars'
  | 'ngc_highlights' | 'messier' | 'satellites' | 'pulsars' | 'nearby_stars';

export function CatalogsPanel() {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [sources, setSources] = useState<Set<Source>>(new Set([
    'exoplanets', 'variable_stars', 'double_stars', 'ngc_highlights',
  ]));
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setErr(null);
      const out: CatalogItem[] = [];
      try {
        if (sources.has('exoplanets')) {
          const r = await fetch('/api/exoplanets?mag_limit=20');
          const j = await r.json();
          for (const h of j.hosts || []) {
            out.push({
              source: 'Exoplanet host',
              name: h.name,
              subtitle: `${h.n_planets} planet${h.n_planets > 1 ? 's' : ''} · ${h.discoverer}`,
              ra: h.ra, dec: h.dec, mag: h.host_mag,
              extra: `${h.distance_ly.toFixed(1)} ly · ${h.description}`,
            });
          }
        }
        if (sources.has('variable_stars')) {
          const r = await fetch('/api/variable_stars?mag_limit=14');
          const j = await r.json();
          for (const v of j.stars || []) {
            out.push({
              source: 'Variable',
              name: v.name,
              subtitle: `${v.var_type} · period ${v.period_d.toFixed(2)}d`,
              ra: v.ra, dec: v.dec, mag: v.current_mag,
              extra: `range [${v.mag_max.toFixed(1)}, ${v.mag_min.toFixed(1)}] · ${v.description}`,
            });
          }
        }
        if (sources.has('double_stars')) {
          const r = await fetch('/api/double_stars');
          const j = await r.json();
          for (const d of j.doubles || []) {
            out.push({
              source: 'Double',
              name: d.name,
              subtitle: `${d.spec_a} + ${d.spec_b} · sep ${d.sep_arcsec.toFixed(1)}″`,
              ra: d.ra, dec: d.dec, mag: d.mag_a,
              extra: `PA ${d.pa_deg}° · ${d.notes}`,
            });
          }
        }
        if (sources.has('ngc_highlights')) {
          const r = await fetch('/api/ngc_highlights?mag_limit=12');
          const j = await r.json();
          for (const o of j.objects || []) {
            out.push({
              source: 'NGC/IC',
              name: `${o.catalog_id}${o.common_name ? ' — ' + o.common_name : ''}`,
              subtitle: `${o.obj_class} · ${o.size_amin.toFixed(1)}′`,
              ra: o.ra, dec: o.dec, mag: o.mag,
              extra: o.description,
            });
          }
        }
        if (sources.has('messier')) {
          const r = await fetch('/api/star_field?messier_mag=11');
          const j = await r.json();
          for (const m of j.messier || []) {
            out.push({
              source: 'Messier',
              name: `M${m.m}${m.name ? ' — ' + m.name : ''}`,
              subtitle: `${m.obj_class} · ${m.size_amaj.toFixed(1)}′`,
              ra: m.ra, dec: m.dec, mag: m.mag,
              extra: m.ngc,
            });
          }
        }
        if (sources.has('nearby_stars')) {
          const r = await fetch('/api/nearby_stars');
          const j = await r.json();
          for (const s of j.stars || []) {
            out.push({
              source: 'Nearby star',
              name: s.name,
              subtitle: `${s.spectral_type} · ${s.distance_ly.toFixed(2)} ly · ${s.category}`,
              ra: s.ra, dec: s.dec, mag: s.app_mag,
              extra: `${s.known_planets} known planet${s.known_planets !== 1 ? 's' : ''} · ${s.notes}`,
            });
          }
        }
        if (sources.has('pulsars')) {
          const r = await fetch('/api/pulsars');
          const j = await r.json();
          for (const p of j.pulsars || []) {
            out.push({
              source: 'Pulsar',
              name: p.common_name || p.jname,
              subtitle: `${p.jname}  period ${p.period_ms.toFixed(2)} ms`,
              ra: p.ra, dec: p.dec,
              extra: `${p.distance_kpc.toFixed(2)} kpc · ${p.description}`,
            });
          }
        }
        if (sources.has('satellites')) {
          const r = await fetch('/api/satellites?min_alt=-90');
          const j = await r.json();
          for (const s of j.satellites || []) {
            out.push({
              source: 'Satellite',
              name: s.name,
              subtitle: `${s.category} · NORAD ${s.norad}`,
              extra: `h=${s.altitude_km}km, v=${s.speed_kmps} km/s, period ${s.period_min} min`,
            });
          }
        }
        setItems(out);
      } catch (e: any) {
        setErr(e.message ?? String(e));
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [sources]);

  const filtered = useMemo(() => {
    if (!query) return items;
    const q = query.toLowerCase();
    return items.filter((i) =>
      i.name.toLowerCase().includes(q) ||
      (i.subtitle ?? '').toLowerCase().includes(q) ||
      (i.extra ?? '').toLowerCase().includes(q)
    );
  }, [items, query]);

  const toggleSource = (s: Source) => {
    const next = new Set(sources);
    if (next.has(s)) next.delete(s); else next.add(s);
    setSources(next);
  };

  const sourceCount: Record<string, number> = {};
  for (const i of items) sourceCount[i.source] = (sourceCount[i.source] || 0) + 1;

  return (
    <div className="h-full overflow-y-auto p-3">
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-ui-accent">Catalogs Browser</h2>
        <p className="text-xs text-ui-text-dim">
          {loading ? 'Loading…' : `${filtered.length} / ${items.length} entries across ${Object.keys(sourceCount).length} catalogs`}
        </p>
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        {(['exoplanets', 'variable_stars', 'double_stars', 'ngc_highlights', 'messier', 'satellites', 'pulsars', 'nearby_stars'] as Source[]).map((s) => (
          <button
            key={s}
            onClick={() => toggleSource(s)}
            className={`px-2 py-0.5 text-xs rounded border ${
              sources.has(s)
                ? 'bg-ui-accent/40 border-ui-accent text-white'
                : 'bg-ui-bg-2 border-ui-border text-ui-text-dim hover:border-ui-border-strong'
            }`}
          >
            {s.replace('_', ' ')}
          </button>
        ))}
      </div>

      <input
        type="text"
        placeholder="Search name / type / notes…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full bg-ui-bg-2 border border-ui-border-strong rounded px-3 py-1.5 text-ui-text mb-3 text-sm"
      />

      {err && (
        <div className="bg-sev-crit/40 border border-sev-crit rounded p-2 text-sev-crit text-xs mb-2">Error: {err}</div>
      )}

      <div className="bg-ui-bg-1/60 border border-ui-border rounded overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-ui-bg-2 text-ui-text-dim sticky top-0">
            <tr>
              <th className="text-left p-2 w-24">Source</th>
              <th className="text-left p-2 w-56">Name</th>
              <th className="text-left p-2 w-48">Type / info</th>
              <th className="text-right p-2 w-16">V mag</th>
              <th className="text-right p-2 w-20">RA (°)</th>
              <th className="text-right p-2 w-20">Dec (°)</th>
              <th className="text-left p-2">Notes</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 300).map((i, idx) => (
              <tr key={idx} className="border-t border-ui-border">
                <td className="p-2 text-ui-text-faint">{i.source}</td>
                <td className="p-2 text-ui-text truncate max-w-[220px]">{i.name}</td>
                <td className="p-2 text-ui-text-dim truncate max-w-[200px]">{i.subtitle}</td>
                <td className="p-2 text-right font-mono text-ui-text">{i.mag !== undefined ? i.mag.toFixed(2) : '—'}</td>
                <td className="p-2 text-right font-mono text-ui-text-dim">{i.ra !== undefined ? i.ra.toFixed(2) : '—'}</td>
                <td className="p-2 text-right font-mono text-ui-text-dim">{i.dec !== undefined ? i.dec.toFixed(2) : '—'}</td>
                <td className="p-2 text-ui-text-faint truncate max-w-[360px]">{i.extra}</td>
              </tr>
            ))}
            {filtered.length > 300 && (
              <tr><td colSpan={7} className="p-3 text-center text-ui-text-faint italic">
                showing first 300 of {filtered.length} — refine your search
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-ui-text-dim">
        {Object.entries(sourceCount).map(([s, n]) => (
          <span key={s}>{s}: <span className="text-ui-text font-mono">{n}</span></span>
        ))}
      </div>
    </div>
  );
}
