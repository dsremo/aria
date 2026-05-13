"""IAS15 — 15th-order Gauss-Radau implicit integrator.

Adaptive-timestep integrator using 7 substeps at Gauss-Radau nodes.
Position accuracy is 15th order; energy conservation approaches machine
precision for moderate integration times.

The predictor uses Horner-nested polynomial evaluation matching the
exact formulation from Everhart (1985). The g→b coefficient update uses
the exact rr[], c[] constants for proper divided differences.

References:
    Rein, H. & Spiegel, D.S. (2015). MNRAS, 446(2), 1424-1437.
    Everhart, E. (1985). Dynamics of Comets, 115, 185-202.
"""

from __future__ import annotations

from typing import Callable, Tuple

import numpy as np

# ── Gauss-Radau nodes (Everhart 1985) ────────────────────────────
_H = np.array([
    0.0,
    0.0562625605369221464656522,
    0.1802406917368923649875799,
    0.3526247171131696373739078,
    0.5471536263305553830014486,
    0.7342101772154105315232106,
    0.8853209468390957680903598,
    0.9775206135612875018911745,
])

# ── Reciprocal differences rr[28] ───────────────────────────────
_RR = np.array([
    0.0562625605369221464656522, 0.1802406917368923649875799,
    0.1239781311999702185219278, 0.3526247171131696373739078,
    0.2963621565762474909082556, 0.1723840253762772723863278,
    0.5471536263305553830014486, 0.4908910657936332365357964,
    0.3669129345936630180138686, 0.1945289092173857456275408,
    0.7342101772154105315232106, 0.6779476166784883850575584,
    0.5539694854785181665356307, 0.3815854601022408941493028,
    0.1870565508848551485217621, 0.8853209468390957680903598,
    0.8290583863021736216247076, 0.7050802551022034031027798,
    0.5326962297259261307164520, 0.3381673205085403850889112,
    0.1511107696236852365671492, 0.9775206135612875018911745,
    0.9212580530243653554255223, 0.7972799218243951369035945,
    0.6248958964481178645172667, 0.4303669872307321188897259,
    0.2433104363458769703679639, 0.0921996667221917338008147,
])

# ── g→b transformation constants c[21] ──────────────────────────
_C = np.array([
    -0.0562625605369221464656522, 0.0101408028300636299864818,
    -0.2365032522738145114532321, -0.0035758977292516175949345,
    0.0935376952594620658957485, -0.5891279693869841488271399,
    0.0019565654099472210769006, -0.0547553868890686864408084,
    0.4158812000823068616886219, -1.1362815957175395318285885,
    -0.0014365302363708915424460, 0.0421585277212687077072973,
    -0.3600995965020568122897665, 1.2501507118406910258505441,
    -1.8704917729329500633517991, 0.0012717903090268677492943,
    -0.0387603579159067703699046, 0.3609622434528459832253398,
    -1.4668842084004269643701553, 2.9061362593084293014237913,
    -2.7558127197720458314421588,
])


def _sqrt7(a: float) -> float:
    """Machine-independent 7th root via Newton iteration."""
    if a <= 0:
        return 0.0
    scale = 1.0
    while a < 1e-7:
        scale *= 0.1
        a *= 1e7
    while a > 1e2:
        scale *= 10.0
        a *= 1e-7
    x = 1.0
    for _ in range(20):
        x6 = x * x * x * x * x * x
        x += (a / x6 - x) / 7.0
    return x * scale


def integrate_ias15(
    accel_fn: Callable[[float, np.ndarray], np.ndarray],
    r0: np.ndarray,
    v0: np.ndarray,
    t0: float,
    t_end: float,
    dt_initial: float = 0.0,
    epsilon: float = 1e-9,
    max_steps: int = 1_000_000,
    min_dt: float = 1e-20,
) -> Tuple[np.ndarray, np.ndarray, float, int, float]:
    """Integrate using IAS15 with exact Everhart predictor.

    Returns (r, v, t, n_steps, rel_energy_error).
    """
    r = np.asarray(r0, dtype=np.float64).copy()
    v = np.asarray(v0, dtype=np.float64).copy()
    t = float(t0)

    # Compensated summation
    csr = np.zeros(3)
    csv = np.zeros(3)

    a0 = accel_fn(t, r)

    # Initial timestep
    if dt_initial <= 0:
        a_norm = np.linalg.norm(a0)
        r_norm = np.linalg.norm(r)
        if a_norm > 0 and r_norm > 0:
            dt = 0.01 * 2 * np.pi * np.sqrt(r_norm / a_norm)
        else:
            dt = (t_end - t0) * 0.01
        dt = min(dt, (t_end - t0) * 0.5)
    else:
        dt = dt_initial

    # b and g coefficients (7 stages × 3 components)
    b = [np.zeros(3) for _ in range(7)]
    g = [np.zeros(3) for _ in range(7)]

    E0 = 0.5 * np.dot(v, v) - np.linalg.norm(a0) * np.linalg.norm(r)
    n_steps = 0
    safety = 0.9

    while t < t_end - 1e-15 * abs(dt) and n_steps < max_steps:
        dt = min(dt, t_end - t)
        if abs(dt) < min_dt:
            break

        # Predictor-corrector loop
        pc_error = 1e300
        pc_error_last = 2.0
        for iteration in range(12):
            if pc_error < 1e-16:
                break
            if iteration > 2 and pc_error_last <= pc_error:
                break
            pc_error_last = pc_error
            pc_error = 0.0

            for n in range(1, 8):
                h = _H[n]

                # Horner-nested position predictor (exact Everhart form):
                # x = ((((((b6*7h/9+b5)*3h/4+b4)*5h/7+b3)*2h/3+b2)*3h/5+b1)*h/2+b0)*h/3+a0)*dt*h/2+v0)*dt*h
                s = (((((((b[6] * 7 * h / 9 + b[5]) * 3 * h / 4 + b[4]) * 5 * h / 7
                         + b[3]) * 2 * h / 3 + b[2]) * 3 * h / 5 + b[1]) * h / 2
                       + b[0]) * h / 3 + a0) * dt * h / 2 + v
                r_pred = s * dt * h + r

                at = accel_fn(t + dt * h, r_pred)

                # Update g and b using divided differences with exact rr[], c[]
                tmp = at - a0
                if n == 1:
                    gk_old = g[0].copy()
                    g[0] = tmp / _RR[0]
                    delta = g[0] - gk_old
                    b[0] = b[0] + delta
                elif n == 2:
                    gk_old = g[1].copy()
                    g[1] = (tmp / _RR[1] - g[0]) / _RR[2]
                    delta = g[1] - gk_old
                    b[0] = b[0] + delta * _C[0]
                    b[1] = b[1] + delta
                elif n == 3:
                    gk_old = g[2].copy()
                    g[2] = ((tmp / _RR[3] - g[0]) / _RR[4] - g[1]) / _RR[5]
                    delta = g[2] - gk_old
                    b[0] = b[0] + delta * _C[1]
                    b[1] = b[1] + delta * _C[2]
                    b[2] = b[2] + delta
                elif n == 4:
                    gk_old = g[3].copy()
                    g[3] = (((tmp / _RR[6] - g[0]) / _RR[7] - g[1]) / _RR[8] - g[2]) / _RR[9]
                    delta = g[3] - gk_old
                    b[0] = b[0] + delta * _C[3]
                    b[1] = b[1] + delta * _C[4]
                    b[2] = b[2] + delta * _C[5]
                    b[3] = b[3] + delta
                elif n == 5:
                    gk_old = g[4].copy()
                    g[4] = ((((tmp / _RR[10] - g[0]) / _RR[11] - g[1]) / _RR[12] - g[2]) / _RR[13] - g[3]) / _RR[14]
                    delta = g[4] - gk_old
                    b[0] = b[0] + delta * _C[6]
                    b[1] = b[1] + delta * _C[7]
                    b[2] = b[2] + delta * _C[8]
                    b[3] = b[3] + delta * _C[9]
                    b[4] = b[4] + delta
                elif n == 6:
                    gk_old = g[5].copy()
                    g[5] = (((((tmp / _RR[15] - g[0]) / _RR[16] - g[1]) / _RR[17] - g[2]) / _RR[18] - g[3]) / _RR[19] - g[4]) / _RR[20]
                    delta = g[5] - gk_old
                    b[0] = b[0] + delta * _C[10]
                    b[1] = b[1] + delta * _C[11]
                    b[2] = b[2] + delta * _C[12]
                    b[3] = b[3] + delta * _C[13]
                    b[4] = b[4] + delta * _C[14]
                    b[5] = b[5] + delta
                elif n == 7:
                    gk_old = g[6].copy()
                    g[6] = ((((((tmp / _RR[21] - g[0]) / _RR[22] - g[1]) / _RR[23] - g[2]) / _RR[24] - g[3]) / _RR[25] - g[4]) / _RR[26] - g[5]) / _RR[27]
                    delta = g[6] - gk_old
                    b[0] = b[0] + delta * _C[15]
                    b[1] = b[1] + delta * _C[16]
                    b[2] = b[2] + delta * _C[17]
                    b[3] = b[3] + delta * _C[18]
                    b[4] = b[4] + delta * _C[19]
                    b[5] = b[5] + delta * _C[20]
                    b[6] = b[6] + delta

                    # Error estimate from b6
                    for c in range(3):
                        errk = abs(b[6][c] / max(abs(at[c]), 1e-30))
                        if np.isfinite(errk) and errk > pc_error:
                            pc_error = errk

        # Timestep control
        if epsilon > 0:
            maxa = max(np.max(np.abs(a0)), 1e-30)
            maxb6 = np.max(np.abs(b[6]))
            integrator_error = maxb6 / maxa

            if np.isfinite(integrator_error) and integrator_error > 0:
                dt_new = _sqrt7(epsilon / integrator_error) * dt
            else:
                dt_new = dt / safety

            if abs(dt_new) < min_dt:
                dt_new = np.copysign(min_dt, dt_new)

            if abs(dt_new / dt) < safety:
                # Reject step — reduce dt and retry
                dt = dt_new
                continue

        # Accept step — advance using the polynomial
        # Position: same Horner form evaluated at h=1
        dr = (((((((b[6] / 9 + b[5]) * 3 / 4 + b[4]) * 5 / 7
                   + b[3]) * 2 / 3 + b[2]) * 3 / 5 + b[1]) / 2
                 + b[0]) / 3 + a0) * dt / 2 + v
        dr = dr * dt

        # Velocity
        dv = ((((((b[6] * 7 / 8 + b[5]) * 6 / 7 + b[4]) * 5 / 6
                  + b[3]) * 4 / 5 + b[2]) * 3 / 4 + b[1]) * 2 / 3
               + b[0]) / 2 + a0
        dv = dv * dt

        # Kahan compensated summation
        yr = dr - csr
        tr = r + yr
        csr = (tr - r) - yr
        r = tr

        yv = dv - csv
        tv = v + yv
        csv = (tv - v) - yv
        v = tv

        t += dt
        n_steps += 1

        a0 = accel_fn(t, r)

        # New timestep
        if epsilon > 0 and np.isfinite(integrator_error) and integrator_error > 0:
            dt = _sqrt7(epsilon / integrator_error) * dt

        # Predict b values for next step (extrapolation)
        ratio = dt / max(abs(dt), 1e-30)  # simplified; full prediction would use dt_new/dt_old
        # Reset for next step (simpler but slightly less efficient)
        for k in range(7):
            b[k] *= 0
            g[k] *= 0

    # Energy error
    a_final = accel_fn(t, r)
    E1 = 0.5 * np.dot(v, v) + np.dot(a_final, r)
    E0_final = 0.5 * np.dot(v0, v0) + np.dot(accel_fn(t0, r0), r0)
    e_err = abs((E1 - E0_final) / E0_final) if abs(E0_final) > 1e-30 else 0.0

    return r, v, t, n_steps, e_err
