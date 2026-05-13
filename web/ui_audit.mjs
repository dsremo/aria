// Playwright smoke test — open each UI tab, capture console errors +
// network errors + render crashes. No assertions; just reporting.
import { chromium } from 'playwright';

const TABS = [
  '3D Model', 'Ship Builder', 'Trajectory', 'Mission Planner',
  'Mission Control', "Captain's Log", 'Objectives', 'Hull Damage',
  'Subsystems', 'Operations', 'Dependency Map', 'Bill of Materials',
  'Mass Budget', 'Alarms', 'Event Log',
];

const HOST = process.env.ARIA_UI || 'http://127.0.0.1:5173';

const consoleErrs = [];
const pageErrs = [];
const netErrs = [];

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 960 } });
const page = await ctx.newPage();

page.on('console', (msg) => {
  if (msg.type() === 'error' || msg.type() === 'warning') {
    consoleErrs.push({ type: msg.type(), text: msg.text().slice(0, 240) });
  }
});
page.on('pageerror', (err) => {
  pageErrs.push({ name: err.name, msg: String(err.message).slice(0, 240) });
});
page.on('response', async (resp) => {
  if (resp.status() >= 400) {
    netErrs.push({ status: resp.status(), url: resp.url() });
  }
});

console.log(`[ui-audit] goto ${HOST}`);
await page.goto(HOST, { waitUntil: 'networkidle', timeout: 30_000 }).catch((e) => {
  console.log('goto err:', e.message);
});
await page.waitForTimeout(2000);

console.log('\n=== INITIAL LOAD ERRORS ===');
consoleErrs.forEach((c, i) => console.log(`  ${i+1}. [${c.type}] ${c.text}`));
pageErrs.forEach((e, i) => console.log(`  PE${i+1}: ${e.name}: ${e.msg}`));
netErrs.forEach((n, i) => console.log(`  N${i+1}: ${n.status} ${n.url}`));

const perTab = {};
for (const label of TABS) {
  const before = consoleErrs.length;
  const pbefore = pageErrs.length;
  const nbefore = netErrs.length;
  try {
    // Click the tab by text
    const tab = page.getByRole('button', { name: label, exact: true }).first();
    if (await tab.count() === 0) {
      // Fallback: any element with that text
      await page.getByText(label, { exact: true }).first().click({ timeout: 5000 });
    } else {
      await tab.click({ timeout: 5000 });
    }
    await page.waitForTimeout(1500);
  } catch (e) {
    perTab[label] = { click_error: e.message.slice(0, 120) };
    continue;
  }
  perTab[label] = {
    console: consoleErrs.slice(before),
    pageerror: pageErrs.slice(pbefore),
    net: netErrs.slice(nbefore),
  };
}

console.log('\n=== PER-TAB ERRORS ===');
for (const [tab, r] of Object.entries(perTab)) {
  const nC = (r.console || []).length;
  const nP = (r.pageerror || []).length;
  const nN = (r.net || []).length;
  if (r.click_error || nC + nP + nN > 0) {
    console.log(`\n[${tab}]  console=${nC}  pageerror=${nP}  net_4xx+5xx=${nN}`);
    if (r.click_error) console.log(`  click_error: ${r.click_error}`);
    (r.pageerror || []).forEach((e) => console.log(`  PE: ${e.name}: ${e.msg}`));
    (r.console || []).slice(0, 5).forEach((c) => console.log(`  [${c.type}] ${c.text}`));
    (r.net || []).slice(0, 5).forEach((n) => console.log(`  ${n.status} ${n.url}`));
  }
}

console.log(`\n=== TOTALS === console=${consoleErrs.length} pageerror=${pageErrs.length} net=${netErrs.length}`);
await browser.close();
