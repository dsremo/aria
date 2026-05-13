/* R33 AdminPanel — ship-wide identity + role administration.
 *
 * Sections appear conditionally based on the calling principal's
 * permissions (server-side authorize() runs again on every request,
 * so a hidden section is also a forbidden section). The custom-role
 * permission picker is filtered to the subset the actor holds —
 * matches the no-escalation guard enforced server-side.
 *
 * Every mutation submits a proposal to the ApprovalQueue; the actor
 * is implicitly the first signer via /api/safety/approve, but a
 * second-distinct signer must complete the two-person flow before
 * the executor fires.
 *
 * For the test/dev login flow + roster of pre-baked principals see
 * docs/DEV_CREDENTIALS.md.
 */

import React, { useEffect, useMemo, useState } from 'react';
import { ariaApi, ariaSession } from '../api/aria';

type RoleRow = {
  name: string;
  inherits: string[];
  trust_tier: string;
  authority_ceiling: string;
  description: string;
  is_sealed: boolean;
  permissions: string[];
};

type PrincipalRow = {
  principal_id: string;
  role: string;
  display_name: string;
  pubkey_hex: string;
  created_at: number;
  expires_at: number;
};

const PANEL_STYLE: React.CSSProperties = {
  background: 'rgb(var(--ui-bg-1))', color: 'rgb(var(--ui-text))',
  padding: 20, borderRadius: 8, marginBottom: 16,
  border: '1px solid rgb(var(--ui-border))',
};

const INPUT_STYLE: React.CSSProperties = {
  background: 'rgb(var(--ui-bg-2))', color: 'rgb(var(--ui-text))',
  border: '1px solid rgb(var(--ui-border))', borderRadius: 6,
  padding: 6, fontFamily: 'monospace', fontSize: 13,
};

const BUTTON_PRIMARY: React.CSSProperties = {
  background: 'rgb(var(--sev-ok))', color: 'white', padding: '6px 12px',
  borderRadius: 6, border: 'none', cursor: 'pointer',
};

const BUTTON_DANGER: React.CSSProperties = {
  background: 'rgb(var(--sev-crit))', color: 'white', padding: '6px 12px',
  borderRadius: 6, border: 'none', cursor: 'pointer',
};


export function AdminPanel(): React.ReactElement {
  const session = ariaSession.current();
  const [perms, setPerms] = useState<string[] | null>(null);
  const [actorRole, setActorRole] = useState<string>('anonymous');
  const [allPerms, setAllPerms] = useState<string[]>([]);
  const [principals, setPrincipals] = useState<PrincipalRow[]>([]);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [error, setError] = useState<string>('');
  const [info, setInfo] = useState<string>('');

  async function refresh(): Promise<void> {
    setError('');
    try {
      const me = await ariaApi.authMe();
      setPerms(me.permissions);
      setActorRole(me.role);
      const [pl, rl, pp] = await Promise.all([
        ariaApi.adminPrincipals().catch(() => ({ principals: [] as PrincipalRow[], count: 0 })),
        ariaApi.adminRoles().catch(() => ({ roles: [] as RoleRow[], count: 0 })),
        ariaApi.adminPermissions().catch(() => ({ all_permissions: [] as string[], actor_holds: [] as string[], actor_role: '' })),
      ]);
      setPrincipals(pl.principals || []);
      setRoles(rl.roles || []);
      setAllPerms(pp.all_permissions || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => { refresh(); }, []);

  const has = useMemo(() => (p: string) =>
    perms !== null && perms.indexOf(p) >= 0, [perms]);

  if (!session) {
    return (
      <div style={PANEL_STYLE}>
        <h2 style={{ marginTop: 0 }}>Admin</h2>
        <p>Sign in via the <strong>Login</strong> tab to see admin
          controls.</p>
      </div>
    );
  }

  return (
    <div>
      <div style={PANEL_STYLE}>
        <h2 style={{ marginTop: 0 }}>Admin — {session.principalId}
          <span style={{ marginLeft: 8, fontSize: 13, color: 'rgb(var(--ui-text-dim))' }}>
            ({actorRole})
          </span>
        </h2>
        <p style={{ fontSize: 13, color: 'rgb(var(--ui-text-dim))', marginBottom: 0 }}>
          Sections appear based on the permissions your role holds.
          Every action below submits a proposal to the
          ApprovalQueue — a second-distinct principal must sign via
          the <strong>Safety Console</strong> tab before it executes
          (cooling-off applies, default 30 s).
        </p>
        {error && <p style={{ color: 'rgb(var(--sev-crit))' }}>{error}</p>}
        {info && <p style={{ color: 'rgb(var(--sev-ok))' }}>{info}</p>}
        <button onClick={refresh} style={{ ...BUTTON_PRIMARY, background: 'rgb(var(--ui-border-soft))' }}>
          Refresh
        </button>
      </div>

      <PrincipalsSection
        principals={principals}
        roles={roles}
        canCreate={has('principal.create')}
        canRevoke={has('principal.revoke')}
        canAssign={has('role.assign')}
        onAction={(msg) => { setInfo(msg); refresh(); }}
        onError={(msg) => setError(msg)}
      />

      <RolesSection
        roles={roles}
        actorPermissions={perms || []}
        allPermissions={allPerms}
        canCreate={has('role.create_custom')}
        canRevoke={has('role.revoke_custom')}
        onAction={(msg) => { setInfo(msg); refresh(); }}
        onError={(msg) => setError(msg)}
      />
    </div>
  );
}


// ── Principals section ──────────────────────────────────────────


function PrincipalsSection(props: {
  principals: PrincipalRow[];
  roles: RoleRow[];
  canCreate: boolean;
  canRevoke: boolean;
  canAssign: boolean;
  onAction: (msg: string) => void;
  onError: (msg: string) => void;
}): React.ReactElement {
  const { principals, roles, canCreate, canRevoke, canAssign,
    onAction, onError } = props;

  return (
    <div style={PANEL_STYLE}>
      <h3 style={{ marginTop: 0 }}>Principals ({principals.length})</h3>
      <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid rgb(var(--ui-border))', textAlign: 'left' }}>
            <th>id</th>
            <th>role</th>
            <th>display</th>
            <th style={{ textAlign: 'right' }}>actions</th>
          </tr>
        </thead>
        <tbody>
          {principals.map((p) => (
            <PrincipalRow
              key={p.principal_id}
              principal={p}
              roles={roles}
              canRevoke={canRevoke}
              canAssign={canAssign}
              onAction={onAction}
              onError={onError}
            />
          ))}
        </tbody>
      </table>
      {canCreate && (
        <CreatePrincipalForm
          roles={roles}
          onAction={onAction}
          onError={onError}
        />
      )}
    </div>
  );
}


function PrincipalRow(props: {
  principal: PrincipalRow;
  roles: RoleRow[];
  canRevoke: boolean;
  canAssign: boolean;
  onAction: (msg: string) => void;
  onError: (msg: string) => void;
}): React.ReactElement {
  const { principal, roles, canRevoke, canAssign, onAction, onError } = props;
  const [newRole, setNewRole] = useState<string>('');

  async function revoke(): Promise<void> {
    try {
      const r = await ariaApi.adminRevokePrincipal(principal.principal_id);
      onAction(`revoke proposed (proposal_id=${r.proposal_id})`);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  async function assign(): Promise<void> {
    if (!newRole) return;
    try {
      const r = await ariaApi.adminAssignRole(principal.principal_id, newRole);
      onAction(`role-assign proposed (proposal_id=${r.proposal_id})`);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <tr style={{ borderBottom: '1px solid rgb(var(--ui-border-soft))' }}>
      <td style={{ fontFamily: 'monospace' }}>{principal.principal_id}</td>
      <td>{principal.role}</td>
      <td style={{ color: 'rgb(var(--ui-text-dim))' }}>{principal.display_name}</td>
      <td style={{ textAlign: 'right' }}>
        {canAssign && (
          <>
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              style={{ ...INPUT_STYLE, marginRight: 4 }}
            >
              <option value="">— role —</option>
              {roles.filter((r) => r.name !== principal.role)
                .map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.name}{r.is_sealed ? '' : ' (custom)'}
                  </option>
                ))}
            </select>
            <button
              onClick={assign}
              disabled={!newRole}
              style={{ ...BUTTON_PRIMARY, background: 'rgb(var(--sev-info))', marginRight: 4 }}
            >
              reassign
            </button>
          </>
        )}
        {canRevoke && (
          <button onClick={revoke} style={BUTTON_DANGER}>
            revoke
          </button>
        )}
      </td>
    </tr>
  );
}


function CreatePrincipalForm(props: {
  roles: RoleRow[];
  onAction: (msg: string) => void;
  onError: (msg: string) => void;
}): React.ReactElement {
  const [pid, setPid] = useState<string>('');
  const [role, setRole] = useState<string>('crew');
  const [pubkey, setPubkey] = useState<string>('');
  const [displayName, setDisplayName] = useState<string>('');

  async function submit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    try {
      const r = await ariaApi.adminCreatePrincipal({
        principal_id: pid.trim(),
        role: role.trim(),
        pubkey_hex: pubkey.trim(),
        display_name: displayName.trim(),
      });
      props.onAction(`create proposed (proposal_id=${r.proposal_id})`);
      setPid('');
      setPubkey('');
      setDisplayName('');
    } catch (err) {
      props.onError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <form onSubmit={submit} style={{ marginTop: 16, display: 'grid', gap: 8,
      gridTemplateColumns: '1fr 1fr 2fr 1fr auto' }}>
      <input style={INPUT_STYLE} value={pid}
        onChange={(e) => setPid(e.target.value)}
        placeholder="principal_id" />
      <select style={INPUT_STYLE} value={role}
        onChange={(e) => setRole(e.target.value)}>
        {props.roles.map((r) => (
          <option key={r.name} value={r.name}>
            {r.name}{r.is_sealed ? '' : ' (custom)'}
          </option>
        ))}
      </select>
      <input style={INPUT_STYLE} value={pubkey}
        onChange={(e) => setPubkey(e.target.value)}
        placeholder="pubkey_hex (64 chars)" />
      <input style={INPUT_STYLE} value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
        placeholder="display name" />
      <button type="submit" style={BUTTON_PRIMARY}>create</button>
    </form>
  );
}


// ── Roles section ───────────────────────────────────────────────


function RolesSection(props: {
  roles: RoleRow[];
  actorPermissions: string[];
  allPermissions: string[];
  canCreate: boolean;
  canRevoke: boolean;
  onAction: (msg: string) => void;
  onError: (msg: string) => void;
}): React.ReactElement {
  const { roles, actorPermissions, allPermissions, canCreate, canRevoke,
    onAction, onError } = props;

  return (
    <div style={PANEL_STYLE}>
      <h3 style={{ marginTop: 0 }}>Roles ({roles.length})</h3>
      <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid rgb(var(--ui-border))', textAlign: 'left' }}>
            <th>name</th>
            <th>kind</th>
            <th>inherits</th>
            <th>permissions</th>
            <th style={{ textAlign: 'right' }}>actions</th>
          </tr>
        </thead>
        <tbody>
          {roles.map((r) => (
            <tr key={r.name} style={{ borderBottom: '1px solid rgb(var(--ui-border-soft))' }}>
              <td style={{ fontFamily: 'monospace' }}>{r.name}</td>
              <td>
                <span style={{ color: r.is_sealed ? 'rgb(var(--ui-text-faint))' : 'rgb(var(--sev-ok))' }}>
                  {r.is_sealed ? 'sealed' : 'custom'}
                </span>
              </td>
              <td style={{ color: 'rgb(var(--ui-text-dim))' }}>{r.inherits.join(', ') || '—'}</td>
              <td>{r.permissions.length}</td>
              <td style={{ textAlign: 'right' }}>
                {canRevoke && !r.is_sealed && (
                  <button
                    onClick={async () => {
                      try {
                        const x = await ariaApi.adminRevokeCustomRole(r.name);
                        onAction(`revoke proposed (proposal_id=${x.proposal_id})`);
                      } catch (err) {
                        onError(err instanceof Error ? err.message : String(err));
                      }
                    }}
                    style={BUTTON_DANGER}
                  >
                    revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {canCreate && (
        <CreateCustomRoleForm
          sealedRoles={roles.filter((r) => r.is_sealed)}
          actorPermissions={actorPermissions}
          allPermissions={allPermissions}
          onAction={onAction}
          onError={onError}
        />
      )}
    </div>
  );
}


function CreateCustomRoleForm(props: {
  sealedRoles: RoleRow[];
  actorPermissions: string[];
  allPermissions: string[];
  onAction: (msg: string) => void;
  onError: (msg: string) => void;
}): React.ReactElement {
  const [name, setName] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [inherits, setInherits] = useState<string[]>(['operator']);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  function toggle(perm: string): void {
    setPicked((cur) => {
      const next = new Set(cur);
      if (next.has(perm)) next.delete(perm);
      else next.add(perm);
      return next;
    });
  }

  async function submit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    try {
      const r = await ariaApi.adminCreateCustomRole({
        name: name.trim(),
        inherits,
        permissions: Array.from(picked),
        description: description.trim(),
      });
      props.onAction(`custom role proposed (proposal_id=${r.proposal_id})`);
      setName('');
      setDescription('');
      setPicked(new Set());
    } catch (err) {
      props.onError(err instanceof Error ? err.message : String(err));
    }
  }

  // No-escalation: actor can only grant permissions they themselves
  // hold. We render the FULL catalogue but disable + grey out perms
  // outside the actor's set so the operator can see what's missing.
  const actorSet = useMemo(() => new Set(props.actorPermissions),
    [props.actorPermissions]);

  return (
    <form onSubmit={submit} style={{ marginTop: 16 }}>
      <h4 style={{ marginBottom: 8 }}>Create custom role</h4>
      <div style={{ display: 'grid', gap: 8,
        gridTemplateColumns: '1fr 1fr 2fr', marginBottom: 8 }}>
        <input style={INPUT_STYLE} value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="role name (alphanumeric)" />
        <select
          multiple
          style={{ ...INPUT_STYLE, height: 80 }}
          value={inherits}
          onChange={(e) => setInherits(
            Array.from(e.target.selectedOptions).map((o) => o.value),
          )}
        >
          {props.sealedRoles.map((r) => (
            <option key={r.name} value={r.name}>{r.name}</option>
          ))}
        </select>
        <input style={INPUT_STYLE} value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="description" />
      </div>
      <div style={{ marginBottom: 8, fontSize: 12, color: 'rgb(var(--ui-text-dim))' }}>
        Pick permissions to grant directly (in addition to those inherited
        from the parent roles). <strong>You can only grant permissions
        you yourself hold.</strong> Other permissions are shown but
        disabled.
      </div>
      <div style={{
        maxHeight: 220, overflowY: 'auto',
        background: 'rgb(var(--ui-bg-2))', border: '1px solid rgb(var(--ui-border))',
        padding: 8, borderRadius: 6, marginBottom: 8,
      }}>
        {props.allPermissions.map((perm) => {
          const allowed = actorSet.has(perm);
          return (
            <label key={perm} style={{
              display: 'block', fontSize: 12,
              fontFamily: 'monospace',
              opacity: allowed ? 1 : 0.4, padding: 2,
            }}>
              <input
                type="checkbox"
                disabled={!allowed}
                checked={picked.has(perm)}
                onChange={() => toggle(perm)}
              />{' '}
              {perm}
            </label>
          );
        })}
      </div>
      <button type="submit" style={BUTTON_PRIMARY}>
        propose custom role
      </button>
    </form>
  );
}
