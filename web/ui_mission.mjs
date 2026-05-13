// Run a full Proxima mission via the Mission Planner UI then abort
// mid-run, then restart, then switch tabs rapidly. This is the class
// of user flow the prior agent audit said could leak or stale-closure.
import { chromium } from 'playwright';

const HOST = process.env.ARIA_UI || 'http://127.0.0.1:5173';
const errs = { console: [], page: [], net: [] };

const browser = await chromium.launch({ headless: true });
const page = await (await browser.newContext({ viewport: { width: 1600, height: 960 } })).newPage();

page.on('console', (m) => {
  if (m.type() === 'error' || m.text().match(/warning|uncaught/i)) {
    const t = m.text();
    if (t.includes('WebGL') && t.includes('GPU stall')) return;
    if (t.includes('400 (Bad Request)')) return; // legitimate validation
    errs.console.push({ type: m.type(), text: t.slice(0, 300) });
  }
});
page.on('pageerror', (e) => errs.page.push({ n: e.name, m: String(e.message).slice(0, 300) }));
page.on('response', (r) => {
  if (r.status() >= 500) errs.net.push({ status: r.status(), url: r.url() });
});

await page.goto(HOST, { waitUntil: 'networkidle', timeout: 30_000 });
await page.waitForTimeout(1500);

// Go to Mission Planner
await page.getByRole('button', { name: 'Mission Planner', exact: true }).first().click();
await page.waitForTimeout(500);

// Pick "Shakedown: Earth → Moon" preset (short, completes)
try {
  await page.getByRole('button', { name: 'Shakedown: Earth → Moon', exact: true }).first().click({ timeout: 2000 });
  await page.waitForTimeout(500);
} catch (e) { console.log('preset click err', e.message); }

// Click Run (▶)
try {
  await page.getByRole('button', { name: '▶ Run plan', exact: true }).first().click({ timeout: 2000 });
  console.log('started run');
} catch (e) { console.log('run click err', e.message); }

// Wait 5 s then abort
await page.waitForTimeout(5000);
try {
  await page.getByRole('button', { name: 'Abort', exact: true }).first().click({ timeout: 2000 });
  console.log('clicked abort');
} catch (e) { console.log('abort click err', e.message); }

await page.waitForTimeout(3000);

// Tab switch race: rapidly cycle a few tabs while mission planner state settles
for (const t of ['3D Model', 'Trajectory', 'Event Log', 'Subsystems', 'Captain\'s Log', 'Mission Planner']) {
  try { await page.getByRole('button', { name: t, exact: true }).first().click({ timeout: 1500 }); } catch {}
  await page.waitForTimeout(200);
}

await page.waitForTimeout(2000);
await browser.close();

console.log(`\n=== RESULT ===`);
console.log(`console errors: ${errs.console.length}`);
console.log(`page errors:    ${errs.page.length}`);
console.log(`network 5xx:    ${errs.net.length}`);
errs.console.slice(0, 10).forEach((c) => console.log(`[${c.type}] ${c.text}`));
errs.page.forEach((e) => console.log(`PE: ${e.n}: ${e.m}`));
errs.net.forEach((n) => console.log(`${n.status} ${n.url}`));
