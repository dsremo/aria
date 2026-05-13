/* R32 LoginPanel — ship-wide authentication entry point.
 *
 * Two flows:
 *
 *  1. Hardware-key flow (production): the operator taps the bridge
 *     hardware token, the browser receives a signature via the
 *     WebAuthn-equivalent shim, the LoginPanel POSTs it. NOT
 *     implemented here — production builds replace the dev-seed input
 *     with a hardware-key prompt component.
 *
 *  2. Dev-seed flow (development / ground tests): the operator pastes
 *     the deterministic Ed25519 private-key seed from
 *     ``tests/fixtures/dev_keys.json`` and the browser uses the Web
 *     Crypto API to sign the server-issued challenge nonce.
 *
 * Both flows produce an opaque session Bearer token that subsequent
 * fetch() calls inject via the ``ariaApi.json`` wrapper.
 *
 * Wire contract: see /api/auth/{challenge,login,logout,me} in
 * src/aria/simulator/web_dashboard.py.
 */

import React, { useEffect, useState } from 'react';
import { ariaApi, ariaSession, type AuthSessionInfo } from '../api/aria';


// PKCS#8 envelope prefix for an Ed25519 raw 32-byte seed. Required by
// crypto.subtle.importKey(format='pkcs8') because raw-format Ed25519
// imports are public-key only in current browsers (Chrome 113+,
// Firefox 130+, Safari 17+).
const ED25519_PKCS8_PREFIX = new Uint8Array([
  0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06,
  0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20,
]);


function hexToBytes(hex: string): Uint8Array {
  const clean = hex.replace(/\s+/g, '').toLowerCase();
  if (clean.length % 2 !== 0) {
    throw new Error('hex string has odd length');
  }
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(clean.slice(2 * i, 2 * i + 2), 16);
  }
  return out;
}


function bytesToHex(buf: ArrayBuffer): string {
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}


async function signEd25519(seedHex: string, payload: string): Promise<string> {
  if (!('subtle' in crypto)) {
    throw new Error('Web Crypto unavailable in this context');
  }
  const seed = hexToBytes(seedHex);
  if (seed.length !== 32) {
    throw new Error(`expected 32-byte seed, got ${seed.length}`);
  }
  const pkcs8 = new Uint8Array(ED25519_PKCS8_PREFIX.length + seed.length);
  pkcs8.set(ED25519_PKCS8_PREFIX, 0);
  pkcs8.set(seed, ED25519_PKCS8_PREFIX.length);
  // Avoid the cryptographically-misleading "subtle" name in the type
  // system — { name: 'Ed25519' } is the published algorithm spec.
  const key = await crypto.subtle.importKey(
    'pkcs8', pkcs8, { name: 'Ed25519' } as unknown as AlgorithmIdentifier,
    false, ['sign'],
  );
  const sig = await crypto.subtle.sign(
    { name: 'Ed25519' } as unknown as AlgorithmIdentifier,
    key, new TextEncoder().encode(payload),
  );
  return bytesToHex(sig);
}


export function LoginPanel(): React.ReactElement {
  const [session, setSession] = useState<AuthSessionInfo | null>(
    ariaSession.current(),
  );
  const [principalId, setPrincipalId] = useState<string>('captain.tau');
  const [seedHex, setSeedHex] = useState<string>('');
  const [duress, setDuress] = useState<boolean>(false);
  const [busy, setBusy] = useState<boolean>(false);
  const [error, setError] = useState<string>('');
  const [info, setInfo] = useState<string>('');

  useEffect(() => {
    const onChange = () => setSession(ariaSession.current());
    window.addEventListener('aria.session.changed', onChange);
    return () => window.removeEventListener('aria.session.changed', onChange);
  }, []);

  async function handleLogin(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError('');
    setInfo('');
    if (!principalId.trim() || !seedHex.trim()) {
      setError('principal_id and dev seed are both required');
      return;
    }
    setBusy(true);
    try {
      const ch = await ariaApi.authChallenge(principalId.trim());
      const payload = `${ch.nonce}|${ch.principal_id}|${ch.expires_at}`;
      const sig = await signEd25519(seedHex.trim(), payload);
      const out = await ariaApi.authLogin({
        principal_id: principalId.trim(),
        nonce: ch.nonce,
        signature_hex: sig,
        duress,
      });
      ariaSession.set({
        token: out.session_token,
        principalId: out.principal_id,
        role: out.role,
      });
      setSession(ariaSession.current());
      setInfo(`logged in as ${out.principal_id} (${out.role})`);
      setSeedHex('');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout(): Promise<void> {
    setError('');
    setInfo('');
    setBusy(true);
    try {
      await ariaApi.authLogout();
    } catch {
      // Even on a server error, clear local state — the user wants out.
    } finally {
      ariaSession.clear();
      setSession(null);
      setBusy(false);
      setInfo('logged out');
    }
  }

  if (session) {
    return (
      <div style={{
        background: 'rgb(var(--ui-bg-1))', color: 'rgb(var(--ui-text))',
        padding: 20, borderRadius: 8, maxWidth: 560,
        border: '1px solid rgb(var(--ui-border))',
      }}>
        <h2 style={{ marginTop: 0 }}>Session active</h2>
        <p>
          Signed in as <strong>{session.principalId}</strong>{' '}
          (role: <strong>{session.role}</strong>).
        </p>
        <button
          onClick={handleLogout}
          disabled={busy}
          style={{
            background: 'rgb(var(--ui-border-soft))', color: 'rgb(var(--ui-text))',
            padding: '6px 12px', borderRadius: 6,
            border: '1px solid rgb(var(--ui-border))', cursor: 'pointer',
          }}
        >
          {busy ? 'logging out…' : 'Log out'}
        </button>
        {info && <p style={{ color: 'rgb(var(--sev-ok))', marginTop: 12 }}>{info}</p>}
      </div>
    );
  }

  return (
    <div style={{
      background: 'rgb(var(--ui-bg-1))', color: 'rgb(var(--ui-text))',
      padding: 20, borderRadius: 8, maxWidth: 560,
      border: '1.5px solid rgb(var(--ui-border-strong))',
      boxShadow: '0 1px 2px rgb(0 0 0 / 0.04), 0 4px 12px rgb(0 0 0 / 0.06)',
    }}>
      <h2 style={{ marginTop: 0 }}>Sign in</h2>
      <p style={{ fontSize: 13, color: 'rgb(var(--ui-text-dim))' }}>
        DEV / ground-test flow: paste the Ed25519 seed for the principal
        from <code>tests/fixtures/dev_keys.json</code>. Production builds
        substitute a hardware-token prompt.
      </p>
      <form onSubmit={handleLogin} style={{ display: 'grid', gap: 12 }}>
        <label>
          <div style={{ marginBottom: 4 }}>principal_id</div>
          <input
            type="text"
            value={principalId}
            onChange={(e) => setPrincipalId(e.target.value)}
            placeholder="captain.tau"
            style={{
              width: '100%', background: 'rgb(var(--ui-bg-2))', color: 'rgb(var(--ui-text))',
              border: '1.5px solid rgb(var(--ui-border-strong))', borderRadius: 6, padding: 8,
              fontFamily: 'monospace',
            }}
          />
        </label>
        <label>
          <div style={{ marginBottom: 4 }}>priv_seed_hex (32 bytes / 64 hex)</div>
          <input
            type="password"
            value={seedHex}
            onChange={(e) => setSeedHex(e.target.value)}
            placeholder="…"
            style={{
              width: '100%', background: 'rgb(var(--ui-bg-2))', color: 'rgb(var(--ui-text))',
              border: '1.5px solid rgb(var(--ui-border-strong))', borderRadius: 6, padding: 8,
              fontFamily: 'monospace',
            }}
            autoComplete="off"
          />
        </label>
        <label style={{ fontSize: 13 }}>
          <input
            type="checkbox"
            checked={duress}
            onChange={(e) => setDuress(e.target.checked)}
          />{' '}
          this is a duress login (capped at SENSOR_ONLY for 30 s)
        </label>
        <button
          type="submit"
          disabled={busy}
          style={{
            background: 'rgb(var(--sev-ok))', color: 'white',
            padding: '8px 14px', borderRadius: 6,
            border: 'none', cursor: 'pointer',
          }}
        >
          {busy ? 'signing in…' : 'Sign in'}
        </button>
      </form>
      {error && <p style={{ color: 'rgb(var(--sev-crit))', marginTop: 12 }}>{error}</p>}
      {info && <p style={{ color: 'rgb(var(--sev-ok))', marginTop: 12 }}>{info}</p>}
    </div>
  );
}
