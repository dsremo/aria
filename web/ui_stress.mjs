// Stress the UI: rapid tab switching, button presses, mission tick
// advances — catch race conditions, stale-closure bugs, unmount races.
import { chromium } from 'playwright';

const HOST = process.env.ARIA_UI || 'http://127.0.0.1:5173';
const TABS = [
  '3D Model', 'Ship Builder', 'Trajectory', 'Mission Planner',
  'Mission Control', "Captain's Log", 'Objectives', 'Hull Damage',
  'Subsystems', 'Operations', 'Dependency Map', 'Bill of Materials',
  'Mass Budget', 'Alarms', 'Event Log',
];

const errs = { console: [], page: [], net: [] };

const browser = await chromium.launch({ headless: true });
const page = await (await browser.newContext({ viewport: { width: 1600, height: 960 } })).newPage();

page.on('console', (m) => {
  if (m.type() === 'error' || m.text().match(/warning|uncaught/i)) {
    const t = m.text();
    // Skip GL driver perf noise
    if (t.includes('WebGL') && t.includes('GPU stall')) return;
    errs.console.push({ type: m.type(), text: t.slice(0, 300) });
  }
});
page.on('pageerror', (e) => errs.page.push({ n: e.name, m: String(e.message).slice(0, 300) }));
page.on('response', (r) => {
  if (r.status() >= 400 && !r.url().includes('sourcemap')) {
    errs.net.push({ status: r.status(), url: r.url() });
  }
});

await page.goto(HOST, { waitUntil: 'networkidle', timeout: 30_000 });
await page.waitForTimeout(1500);

console.log('--- RAPID TAB CYCLE (3 passes) ---');
for (let pass = 0; pass < 3; pass++) {
  for (const label of TABS) {
    try {
      await page.getByRole('button', { name: label, exact: true }).first().click({ timeout: 2000 });
    } catch {
      try { await page.getByText(label, { exact: true }).first().click({ timeout: 2000 }); } catch {}
    }
    await page.waitForTimeout(80);
  }
}

console.log('--- TICK BUTTONS (Mission Control) ---');
try {
  await page.getByRole('button', { name: 'Mission Control', exact: true }).first().click();
  await page.waitForTimeout(500);
  for (const btn of ['+0.1 yr', '+1 yr', '+10 yr']) {
    for (let i = 0; i < 3; i++) {
      try { await page.getByRole('button', { name: btn, exact: true }).first().click({ timeout: 2000 }); } catch {}
      await page.waitForTimeout(150);
    }
  }
} catch (e) {
  console.log('tick-btn err:', e.message);
}

console.log('--- STARTUP TICK BUTTONS ---');
for (const btn of ['+30 s', '+5 min', '+1 hr', '+1 day']) {
  try { await page.getByRole('button', { name: btn, exact: true }).first().click({ timeout: 1500 }); } catch {}
  await page.waitForTimeout(100);
}

console.log('--- NAVIGATE TO FAILURE INJECTOR + TRIGGER DRILL ---');
try {
  await page.getByRole('button', { name: 'Subsystems', exact: true }).first().click();
  await page.waitForTimeout(500);
  await page.getByText('Maglev Controller Trip', { exact: false }).first().click({ timeout: 2000 }).catch(() => {});
  await page.waitForTimeout(1000);
} catch {}

console.log('--- TRAJECTORY + REFUEL ---');
try {
  await page.getByRole('button', { name: 'Trajectory', exact: true }).first().click();
  await page.waitForTimeout(500);
  await page.getByText('🛢', { exact: false }).first().click({ timeout: 1500 }).catch(() => {});
  await page.waitForTimeout(1000);
} catch {}

console.log('--- ADD EMPTY OPERATOR NOTE (should 400 now) ---');
try {
  await page.getByRole('button', { name: "Captain's Log", exact: true }).first().click();
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: '+ Note', exact: true }).first().click({ timeout: 1500 }).catch(() => {});
  await page.waitForTimeout(1000);
} catch {}

await page.waitForTimeout(1500);
await browser.close();

console.log(`\n=== RESULT ===`);
console.log(`console errors: ${errs.console.length}`);
console.log(`page errors:    ${errs.page.length}`);
console.log(`network 4xx+5xx:${errs.net.length}`);

console.log('\n--- console (first 10) ---');
errs.console.slice(0, 10).forEach((c) => console.log(`[${c.type}] ${c.text}`));
console.log('\n--- pageerror (all) ---');
errs.page.forEach((e) => console.log(`${e.n}: ${e.m}`));
console.log('\n--- network (first 10) ---');
errs.net.slice(0, 10).forEach((n) => console.log(`${n.status} ${n.url}`));
