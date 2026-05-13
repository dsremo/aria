// Hit the backend with invalid inputs via the UI's apparent controls
// + direct curl-like fetches to exercise all handlers' validation paths.
import { chromium } from 'playwright';

const HOST = process.env.ARIA_UI || 'http://127.0.0.1:5173';
// Hit via Vite proxy → avoids CORS preflight the same way the real UI
// does (relative /api/* paths).
const BK = '';

const errs = { console: [], page: [], net: [] };

const browser = await chromium.launch({ headless: true });
const page = await (await browser.newContext({ viewport: { width: 1600, height: 960 } })).newPage();

page.on('console', (m) => {
  if (m.type() === 'error') {
    const t = m.text();
    if (t.includes('WebGL') && t.includes('GPU stall')) return;
    if (t.includes('400 (Bad Request)') || t.includes('404 (Not Found)')) return;
    errs.console.push({ type: m.type(), text: t.slice(0, 300) });
  }
});
page.on('pageerror', (e) => errs.page.push({ n: e.name, m: String(e.message).slice(0, 300) }));
page.on('response', (r) => {
  if (r.status() >= 500) errs.net.push({ status: r.status(), url: r.url() });
});

await page.goto(HOST, { waitUntil: 'domcontentloaded', timeout: 30_000 });
await page.waitForTimeout(2500);

// Run adversarial HTTP probes from within the browser page to see how
// both frontend + backend respond.
const results = await page.evaluate(async (BK) => {
  const probes = [
    { m: 'POST', u: '/api/hull/impact', body: { region_id: 'hull_zone_4', energy_j: -100 } },
    { m: 'POST', u: '/api/hull/impact', body: { region_id: 'hull_zone_4', energy_j: 'not-a-number' } },
    { m: 'POST', u: '/api/hull/impact', body: {} },
    { m: 'POST', u: '/api/trajectory/target', body: { target: 'Not-A-Star' } },
    { m: 'POST', u: '/api/trajectory/target', body: {} },
    { m: 'POST', u: '/api/mission/tick', body: { delta_yr: -5 } },
    { m: 'POST', u: '/api/mission/tick', body: { delta_yr: 'abc' } },
    { m: 'POST', u: '/api/mission/tick', body: { delta_yr: 1e12 } },
    { m: 'POST', u: '/api/startup/tick', body: { dt_s: -1 } },
    { m: 'POST', u: '/api/scheduler/add', body: { fire_at_yr: -5 } },
    { m: 'POST', u: '/api/comms/queue', body: { bytes_size: -1 } },
    { m: 'POST', u: '/api/comms/queue', body: { bytes_size: 1e20 } },
    { m: 'POST', u: '/api/repair/enqueue', body: { region_id: 'nonsense', priority: -1 } },
    { m: 'POST', u: '/api/ship/apply_class', body: { class: 'nonexistent' } },
    { m: 'POST', u: '/api/ship/apply_class', body: {} },
    { m: 'POST', u: '/api/narrative/note', body: { text: '', severity: 'info' } },
    { m: 'POST', u: '/api/narrative/note', body: { text: null, severity: 'info' } },
    { m: 'POST', u: '/api/hull/repair', body: {} },
    { m: 'POST', u: '/api/bearing/trip', body: {} },
    { m: 'POST', u: '/api/failures/trigger', body: { id: 'no_such_scenario' } },
    { m: 'POST', u: '/api/failures/trigger', body: {} },
  ];
  const out = [];
  for (const p of probes) {
    try {
      const r = await fetch(BK + p.u, {
        method: p.m,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(p.body),
      });
      let bodyText = '';
      try { bodyText = (await r.text()).slice(0, 120); } catch {}
      out.push({ u: p.u, body: p.body, status: r.status, resp: bodyText });
    } catch (e) {
      out.push({ u: p.u, body: p.body, status: -1, resp: String(e).slice(0, 120) });
    }
  }
  return out;
}, BK);

console.log('=== ADVERSARIAL PROBES ===');
for (const r of results) {
  const flag = (r.status >= 500 || r.status === -1) ? '🔴 CRASH' :
               r.status >= 400 ? '✅ 4xx valid' :
               r.status >= 200 ? '⚠  2xx accepted bad input?' : '';
  console.log(`  [${r.status}] ${flag}  ${r.u}  body=${JSON.stringify(r.body)}  →  ${r.resp}`);
}

console.log(`\n=== PAGE-LEVEL ===`);
console.log(`console: ${errs.console.length}, pageerror: ${errs.page.length}, 5xx: ${errs.net.length}`);
errs.console.forEach((c) => console.log(`  [${c.type}] ${c.text}`));
errs.page.forEach((e) => console.log(`  PE: ${e.n}: ${e.m}`));
errs.net.forEach((n) => console.log(`  ${n.status} ${n.url}`));

await browser.close();
