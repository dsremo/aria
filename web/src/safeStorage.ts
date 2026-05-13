// safeStorage — REGRESSION-PREVENTION LINT WRAPPER around localStorage.
//
// IMPORTANT: this is NOT a security defence against XSS.  An attacker
// running script in this origin can call ``window.localStorage.getItem``
// directly and bypass every check below.  This wrapper exists to catch
// honest authoring mistakes ("I'll just save the token in localStorage
// for now") at runtime in dev and at code-review time via the ESLint
// rule that bans direct ``window.localStorage`` references.
//
// The actual control for tokens is:
//   * ``httpOnly`` + ``Secure`` + ``SameSite=Strict`` cookies, OR
//   * a memory-only access token refreshed via a same-origin cookie.
//
// The frontend persists only UI state (active tab, theme).  Audit
// HIGH-10 + round-2 audit NEW-HIGH-21 / NEW-MED-12 / NEW-MED-13 /
// NEW-MED-17 hardenings:
//   - regex extended to cover xsrf, csrf, bearer, oauth_state, pkce,
//     apikey, principal, otp.
//   - removeItem also gated.
//   - clear / length / key wrapped so accidental enumeration goes
//     through the same lint surface.

const SENSITIVE_KEY_RE = /(token|jwt|session|auth(?!or)|secret|key|cred|password|nonce|xsrf|csrf|bearer|oauth|pkce|apikey|principal|otp)/i;

function isProd(): boolean {
  return typeof window !== 'undefined' && !(window as any).__DEV__;
}

function reject(key: string, op: string): void {
  const msg = `safeStorage.${op}: refusing sensitive key '${key}' — use httpOnly cookie`;
  if (!isProd()) {
    // Hard-fail in dev so the regression is noticed at first run.
    throw new Error(msg);
  }
  // Production: log loudly so the bug is observable without crashing
  // the dashboard mid-emergency.
  // eslint-disable-next-line no-console
  console.error(msg);
}

export const safeStorage = {
  getItem(key: string): string | null {
    if (SENSITIVE_KEY_RE.test(key)) {
      reject(key, 'getItem');
      return null;
    }
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem(key: string, value: string): void {
    if (SENSITIVE_KEY_RE.test(key)) {
      reject(key, 'setItem');
      return;
    }
    try {
      window.localStorage.setItem(key, value);
    } catch {
      /* swallow QuotaExceeded etc. */
    }
  },
  removeItem(key: string): void {
    if (SENSITIVE_KEY_RE.test(key)) {
      reject(key, 'removeItem');
      return;
    }
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* noop */
    }
  },
  clear(): void {
    // Round-2 NEW-MED-17 — refuse blanket clear; force callers to
    // remove keys individually so a misbehaving widget cannot wipe
    // adjacent UI preferences.
    reject('<all>', 'clear');
  },
  length(): number {
    // Round-3 audit R3-HIGH-10 — count only non-sensitive keys.  An
    // accurate ``localStorage.length`` leaks the cardinality of any
    // mistakenly-stored token-like keys to a co-resident XSS payload
    // (the actual values are still readable via direct
    // ``window.localStorage`` — this is regression-prevention, not
    // an XSS defence).
    try {
      let n = 0;
      const raw = window.localStorage;
      for (let i = 0; i < raw.length; i += 1) {
        const k = raw.key(i);
        if (k && !SENSITIVE_KEY_RE.test(k)) n += 1;
      }
      return n;
    } catch {
      return 0;
    }
  },
  key(index: number): string | null {
    // Iterate non-sensitive keys only so callers can enumerate the
    // safe subset deterministically.
    try {
      const raw = window.localStorage;
      let visible = 0;
      for (let i = 0; i < raw.length; i += 1) {
        const k = raw.key(i);
        if (!k || SENSITIVE_KEY_RE.test(k)) continue;
        if (visible === index) return k;
        visible += 1;
      }
      return null;
    } catch {
      return null;
    }
  },
};
