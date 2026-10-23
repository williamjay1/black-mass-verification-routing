"""Independent engineering baselines; writes only its versioned result folder.

Run with ``python -B scripts/inventions_engineering_baselines.py``. No MILP or
new LP is solved. Exported routing is held fixed for capacity reblocking.
The centralized design is exhaustive only within a restricted nearest-H
heuristic family, never a globally optimized network. All currency is model
USD under the manuscript's source-cost conditions.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import platform
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
import numpy as np
import pandas as pd
from run_signal_contingent_network import Config


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/inventions_engineering_baselines_20261023_v1"
DATA = ROOT / "datasets/futuram_network_inputs_20260930_v1"
REGISTRY = ROOT.parent / "datasets/upgrade/route_parameter_registry_2026-09-26.csv"
ROUTES = ("D", "H", "P")
ELEMENTS = ("Li", "Co", "Ni", "Mn", "Al", "Fe", "Cu")
AW = {"Ni": 58.6934, "Co": 58.933194, "Mn": 54.938044}
RATIO = {"Ni": .6, "Co": .2, "Mn": .2}
MW = 6.94 + sum(AW[e] * RATIO[e] for e in AW) + 2 * 15.999
INPUTS: dict[str, str] = {}
CHECKS: list[dict] = []


def require(condition, description, **details):
    if not bool(condition):
        raise AssertionError((description, details))
    CHECKS.append({"check": description, "pass": True, **details})


def track(path):
    path = Path(path).resolve()
    INPUTS[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


def read_json(path):
    return json.loads(track(path).read_text(encoding="utf-8"))


def read_csv(path):
    return pd.read_csv(track(path))


def signal_masses(p, c):
    """Independent probability arithmetic; dispatch never uses these states."""
    if c.policy == "none":
        return ["untested"], np.array([p]), np.array([1-p]), 0.
    if c.policy in ("screen", "confirmation", "perfect"):
        s, f, fee = {"screen": (c.screen_s, c.screen_f, c.screen_fee),
                     "confirmation": (c.confirm_s, c.confirm_f, c.confirm_fee),
                     "perfect": (1., 0., c.confirm_fee)}[c.policy]
        return ["positive", "negative"], np.array([p*s, p*(1-s)]), np.array([(1-p)*f, (1-p)*(1-f)]), fee
    if c.policy == "cascade":
        sj = max(0., c.screen_s+c.confirm_s-1.) if c.conservative_joint_s else c.screen_s*c.confirm_s
        fj = c.screen_f*c.confirm_f + c.bad_error_dependence*(min(c.screen_f, c.confirm_f)-c.screen_f*c.confirm_f)
        return ["both_positive", "screen_positive_confirm_negative", "screen_negative"], p*np.array([sj, c.screen_s-sj, 1-c.screen_s]), (1-p)*np.array([fj, c.screen_f-fj, 1-c.screen_f]), c.screen_fee+c.confirm_fee*(p*c.screen_s+(1-p)*c.screen_f)
    raise ValueError(c.policy)


def capacity_required(mu, lot, epsilon, count, block, deterministic=False):
    """Smallest integer block count satisfying the total-capacity Bernstein bound.

    This is exact inversion of a conservative bound with Var<=lot*mu, not an
    exact overflow probability and not routing/capacity joint optimization.
    """
    if mu < -1e-7:
        raise ValueError("negative mean")
    if mu <= 1e-10:
        return 0, 0.
    ell = math.log(count/epsilon)
    margin = 0. if deterministic else ell*lot/3 + math.sqrt((ell*lot/3)**2+2*ell*lot*mu)
    n = int(math.ceil((mu+margin)/block-1e-11))
    return n, n*block


def bound_slack(mu, capacity, lot, epsilon, count):
    if mu <= 1e-10:
        return math.inf
    t = capacity-mu
    if t < -1e-8:
        return -math.inf
    return t*t-math.log(count/epsilon)*(2*lot*mu+2*lot*t/3)


def one_block_kappa(block, lot, epsilon, count):
    # Independent bisection rather than calling the optimizer's helper.
    lo, hi = 0., 1.
    for _ in range(90):
        mid = (lo+hi)/2
        if bound_slack(mid*block, block, lot, epsilon, count) >= 0:
            lo = mid
        else:
            hi = mid
    return lo


def geometry(year=2030):
    origins = read_csv(DATA / f"national_origins_{year}.csv").sort_values("origin_id").reset_index(drop=True)
    hubs = read_csv(DATA / "candidate_hubs.csv").sort_values("hub_id").reset_index(drop=True)
    distances = read_csv(DATA / "national_origin_hub_geodesic_matrix.csv")
    matrix = distances.pivot(index="origin_id", columns="hub_id", values="distance_km").loc[origins.origin_id, hubs.hub_id].to_numpy()
    require(np.isfinite(matrix).all() and (matrix >= 0).all(), "complete nonnegative distance matrix")
    return origins, hubs, matrix


def evaluate_policy(c, channels, origins, hubs, distance, costs):
    """Independently reconstruct all endpoint and midpoint expected accounts."""
    supply = dict(zip(origins.origin_id, origins.reference_black_mass_tpy))
    hi = {str(h): i for i, h in enumerate(hubs.hub_id)}
    oi = {str(o): i for i, o in enumerate(origins.origin_id)}
    totals = {}
    for row in channels:
        require(row.get("profile_index") is None, "non-anticipative channel", record_origin=str(row["origin_id"]))
        key = (str(row["origin_id"]), row["signal"])
        totals[key] = totals.get(key, 0.)+row["nominal_if_all_input_had_signal_t"]
    labels = signal_masses(c.p_low, c)[0]
    residual = max(abs(totals.get((str(o), s), 0.)-v) for o, v in supply.items() for s in labels)
    require(residual < 1e-4, "per-origin per-signal normalization", residual_t=residual)
    endpoints = sorted(set([c.p_low, c.p_high]))
    profiles = []
    for p in sorted(set(endpoints+[(c.p_low+c.p_high)/2])):
        labels, g, b, fee = signal_masses(p, c)
        require(abs(float((g+b).sum())-1) < 1e-12 and min(g.min(), b.min()) >= -1e-12, "probability mass conservation", p=p)
        si = dict(zip(labels, range(len(labels))))
        mu = np.zeros((len(hubs), 3))
        processing, tkm, gd, fd, hh, pp = 0., 0., 0., 0., 0., 0.
        for row in channels:
            a = si[row["signal"]]; j = hi[str(row["hub_id"])]; k = ROUTES.index(row["route"])
            v = float(row["nominal_if_all_input_had_signal_t"]); pi = g[a]+b[a]
            tkm += pi*v*distance[oi[str(row["origin_id"])], j]*c.distance_multiplier
            if k == 0:
                q = b[a]/pi if pi > 0 else 1.
                require(q <= c.risk_cap+1e-10, "D channel admission", p=p, signal=row["signal"])
                mu[j, 0] += (g[a]+c.failed_direct_capacity_fraction*b[a])*v
                mu[j, 2] += b[a]*v
                processing += v*(g[a]*costs[0]+b[a]*(c.sunk_cost_fraction*costs[0]+c.fallback_cost_multiplier*costs[2]))
                gd += g[a]*v; fd += b[a]*v
            else:
                mu[j, k] += pi*v
                processing += pi*v*costs[k]
                if k == 1: hh += pi*v
                else: pp += pi*v
        require(abs(gd+fd+hh+pp-sum(supply.values())) < 1e-4, "unique input balance", p=p)
        require(abs(mu.sum()-(sum(supply.values())+c.failed_direct_capacity_fraction*fd)) < 1e-4, "repeat process balance", p=p)
        assay = fee*sum(supply.values()); transport = tkm*c.transport_per_tkm
        profiles.append({"p": p, "is_endpoint": p in endpoints, "mu": mu,
                         "processing_cost_model_usd": processing, "assay_cost_model_usd": assay,
                         "transport_tkm": tkm, "transport_cost_model_usd": transport,
                         "operating_cost_model_usd": processing+assay+transport,
                         "direct_compatible_t": gd, "fallback_t": fd, "hydro_t": hh, "pyro_primary_t": pp})
    return profiles


def fixed_reblocking(runs, origins, hubs, distance, costs):
    summaries, capacity_rows, profiles_out = [], [], []
    for source_id, source_file, index, run in runs:
        c = Config(**run["config"])
        require(c.year == 2030 and not c.oracle_dispatch, "supported fixed-policy design", source_id=source_id)
        profiles = evaluate_policy(c, run["signal_contingent_nominal_policy_flows"], origins, hubs, distance, costs)
        original = np.zeros((len(hubs), 3)); hi = dict(zip(hubs.hub_id, range(len(hubs))))
        for row in run["capacity"]: original[hi[row["hub_id"]], ROUTES.index(row["route"])] = row["capacity_tpy"]
        source_reconstructed = max(x["operating_cost_model_usd"] for x in profiles)+original.sum()*c.incremental_reservation_premium_per_tpy
        require(abs(source_reconstructed-run["worst_cost_model_usd"]) < .05, "exported worst cost reconstruction", source_id=source_id, residual_model_usd=source_reconstructed-run["worst_cost_model_usd"])
        max_mu = np.max([p["mu"] for p in profiles if p["is_endpoint"]], axis=0)
        require((max_mu <= original+1e-5).all(), "source capacity covers expected endpoint loads", source_id=source_id)
        for block in (250., 500., 1000., 2000.):
            lot, premium, count = 10., 500., 3*len(hubs)
            revised = np.zeros_like(original); blocks = np.zeros_like(original, dtype=int)
            deterministic = c.policy == "none"
            for j in range(len(hubs)):
                for k, route in enumerate(ROUTES):
                    m = float(max_mu[j, k]); n, C = capacity_required(m, lot, c.network_overflow_budget, count, block, deterministic)
                    blocks[j, k] = n; revised[j, k] = C
                    if n and not deterministic:
                        require(bound_slack(m, C, lot, c.network_overflow_budget, count) >= -1e-5, "total-capacity Bernstein certificate", source_id=source_id, block_tpy=block)
                        require(n == 1 or bound_slack(m, C-block, lot, c.network_overflow_budget, count) < 0, "minimal fixed-route block count", source_id=source_id, block_tpy=block)
                    if m > 1e-10 or original[j, k] > 0:
                        capacity_rows.append({"source_id": source_id, "block_tpy": block, "evaluation_independent_lot_t": lot,
                            "hub_id": hubs.hub_id[j], "route": route, "maximum_endpoint_mean_tpy": m,
                            "original_capacity_tpy": original[j, k], "new_blocks": n, "new_capacity_tpy": C,
                            "within_original_blocks_per_route_site_limit": bool(n <= c.blocks_per_route_site),
                            "certificate": "deterministic conditional workload" if deterministic else "total-capacity Bernstein, Var<=b*mu"})
            feasible = bool((blocks <= c.blocks_per_route_site).all())
            worst = max(profiles, key=lambda x: x["operating_cost_model_usd"])
            total = float(revised.sum()); repriced = worst["operating_cost_model_usd"]+premium*total
            summaries.append({"source_id": source_id, "source_file": source_file, "source_run_index": index,
                "policy": c.policy, "source_design_lot_t": c.maximum_independent_lot_t,
                "source_premium_model_usd_per_tpy": c.incremental_reservation_premium_per_tpy,
                "new_block_tpy": block, "evaluation_independent_lot_t": lot, "repricing_premium_model_usd_per_tpy": premium,
                "original_total_capacity_tpy": float(original.sum()), "new_total_capacity_tpy": total,
                **{f"new_{k}_capacity_tpy": float(revised[:, i].sum()) for i, k in enumerate(ROUTES)},
                "original_capacity_repriced_worst_cost_h500_model_usd": worst["operating_cost_model_usd"]+premium*float(original.sum()),
                "new_worst_cost_h500_model_usd": repriced,
                "new_reservation_cost_model_usd": premium*total,
                "worst_cost_p": worst["p"], "worst_operating_cost_model_usd": worst["operating_cost_model_usd"],
                "capacity_reduction_tpy": float(original.sum())-total, "feasible_under_block_count_limit": feasible,
                "method_role": "fixed exported routing; new module scenario; minimum blocks under total-capacity Bernstein bound; no routing reoptimization"})
            for p in profiles:
                profiles_out.append({"source_id": source_id, "new_block_tpy": block,
                    **{k: v for k, v in p.items() if k != "mu"},
                    "new_total_capacity_tpy": total, "reservation_cost_h500_model_usd": total*premium,
                    "repriced_total_cost_h500_model_usd": p["operating_cost_model_usd"]+total*premium})
    return summaries, capacity_rows, profiles_out


def centralized_baseline(c, origins, hubs, distance, costs, reference):
    """Enumerate DP center, <=4 extra H sites, and nearest eligible H dispatch.

    The DP center may also host H without consuming a sixth physical hub.
    H subsets excluding/including that center are both tried. Whole lots from
    an origin with a given observed signal have one deterministic destination.
    """
    require(c.max_hubs == 5 and len(hubs) == 17, "centralized family dimensions")
    endpoints = sorted(set([c.p_low, c.p_high])); S = origins.reference_black_mass_tpy.to_numpy(); total = float(S.sum())
    packs = [signal_masses(p, c) for p in endpoints]
    pi = np.stack([x[1]+x[2] for x in packs]); g = np.stack([x[1] for x in packs]); bad = np.stack([x[2] for x in packs])
    risk = np.divide(bad, pi, out=np.ones_like(pi), where=pi > 0)
    safe = (risk.max(axis=0) <= c.risk_cap+1e-12) & (pi.min(axis=0) > 0)
    require(safe.any() and (~safe).any(), "nontrivial safe/unsafe observed signals", policy=c.policy)
    d_pi = pi[:, safe].sum(axis=1); h_pi = pi[:, ~safe].sum(axis=1)
    good_d = g[:, safe].sum(axis=1); bad_d = bad[:, safe].sum(axis=1)
    d_mu = total*(good_d+c.failed_direct_capacity_fraction*bad_d); p_mu = total*bad_d
    kappa = one_block_kappa(c.block_tpy, c.maximum_independent_lot_t, c.network_overflow_budget, 3*len(hubs))
    require(abs(kappa-reference["certified_mean_capacity_fraction"]) < 1e-10, "same one-block kappa as MILP", policy=c.policy, kappa=kappa)
    unit = kappa*c.block_tpy
    nd = int(math.ceil(float(d_mu.max())/unit-1e-11)); npy = int(math.ceil(float(p_mu.max())/unit-1e-11))
    basecost = total*(good_d*costs[0]+bad_d*(c.sunk_cost_fraction*costs[0]+c.fallback_cost_multiplier*costs[2])+h_pi*costs[1])+total*np.array([x[3] for x in packs])
    d = distance*c.distance_multiplier
    best, center_rows, search_count, feasible_count = None, [], 0, 0
    for center in range(len(hubs)):
        others = [j for j in range(len(hubs)) if j != center]
        center_best = None; center_count = 0; center_feasible = 0
        d_tkm = float(S @ d[:, center])
        for extra_count in range(c.max_hubs):
            for extra in itertools.combinations(others, extra_count):
                for include_center in (False, True):
                    hs = sorted(extra+((center,) if include_center else ()))
                    if not hs: continue
                    search_count += 1; center_count += 1
                    local = np.argmin(d[:, hs], axis=1); destinations = np.asarray(hs)[local]
                    assigned = np.bincount(destinations, weights=S, minlength=len(hubs))
                    nh = np.ceil(assigned*float(h_pi.max())/unit-1e-11).astype(int)
                    if max(nd, npy, int(nh.max())) > c.blocks_per_route_site: continue
                    feasible_count += 1; center_feasible += 1
                    C = c.block_tpy*(nd+npy+int(nh.sum()))
                    h_tkm = float(S @ d[np.arange(len(S)), destinations])
                    values = basecost+c.transport_per_tkm*(d_pi*d_tkm+h_pi*h_tkm)+C*c.incremental_reservation_premium_per_tpy
                    objective = float(values.max())
                    candidate = {"worst_cost_model_usd": objective, "center": center, "hs": hs,
                                 "destinations": destinations, "nh": nh, "nd": nd, "npy": npy,
                                 "capacity_tpy": C, "endpoint_costs": values,
                                 "tie_key": (objective, C, center, tuple(hs))}
                    if center_best is None or candidate["tie_key"] < center_best["tie_key"]: center_best = candidate
        require(center_best is not None, "feasible centralized center", policy=c.policy, center=str(hubs.hub_id[center]))
        center_rows.append({"policy": c.policy, "D_P_hub_id": hubs.hub_id[center], "D_P_city": hubs.city[center],
            "best_worst_endpoint_cost_model_usd": center_best["worst_cost_model_usd"],
            "total_capacity_tpy": center_best["capacity_tpy"], "H_candidate_hubs": json.dumps([str(hubs.hub_id[j]) for j in center_best["hs"]]),
            "families_evaluated": center_count, "feasible_families": center_feasible})
        if best is None or center_best["tie_key"] < best["tie_key"]: best = center_best
    channels = []
    for i, origin in enumerate(origins.origin_id):
        for a, label in enumerate(packs[0][0]):
            j = best["center"] if safe[a] else best["destinations"][i]
            channels.append({"profile_index": None, "signal": label, "origin_id": str(origin),
                             "hub_id": str(hubs.hub_id[j]), "route": "D" if safe[a] else "H",
                             "nominal_if_all_input_had_signal_t": float(S[i])})
    caps = np.zeros((len(hubs), 3)); caps[:, 1] = best["nh"]*c.block_tpy
    caps[best["center"], 0] = nd*c.block_tpy; caps[best["center"], 2] = npy*c.block_tpy
    profiles = evaluate_policy(c, channels, origins, hubs, distance, costs)
    violation = max(float(np.max(p["mu"]-kappa*caps)) for p in profiles)
    require(violation < 1e-6, "heuristic same one-block capacity constraints", policy=c.policy, max_violation_t=violation)
    reconstructed = max(p["operating_cost_model_usd"] for p in profiles)+caps.sum()*c.incremental_reservation_premium_per_tpy
    require(abs(reconstructed-best["worst_cost_model_usd"]) < .05, "heuristic independent cost reconstruction", policy=c.policy)
    require(best["worst_cost_model_usd"] >= reference["primary_lower_bound_model_usd"]-.05, "heuristic respects MILP lower bound", policy=c.policy)
    active = np.flatnonzero(caps.sum(axis=1) > 0)
    require(len(active) <= c.max_hubs, "heuristic physical hub limit", policy=c.policy)
    summary = {"policy": c.policy, "config": asdict(c), "method_role": "exhaustive enumeration within a restricted nearest-H centralized heuristic family; not globally optimal",
        "D_P_hub_id": str(hubs.hub_id[best["center"]]), "D_P_city": str(hubs.city[best["center"]]),
        "active_hubs": [str(hubs.hub_id[j]) for j in active], "families_evaluated": search_count,
        "feasible_families": feasible_count, "kappa": kappa,
        "worst_endpoint_cost_model_usd": best["worst_cost_model_usd"], "total_capacity_tpy": float(caps.sum()),
        **{f"{k}_capacity_tpy": float(caps[:, i].sum()) for i, k in enumerate(ROUTES)},
        "MILP_incumbent_model_usd": reference["worst_cost_model_usd"], "MILP_lower_bound_model_usd": reference["primary_lower_bound_model_usd"],
        "heuristic_minus_MILP_incumbent_model_usd": best["worst_cost_model_usd"]-reference["worst_cost_model_usd"],
        "heuristic_gap_to_MILP_incumbent_pct": 100*(best["worst_cost_model_usd"]/reference["worst_cost_model_usd"]-1),
        "heuristic_gap_to_MILP_lower_bound_pct": 100*(best["worst_cost_model_usd"]/reference["primary_lower_bound_model_usd"]-1),
        "D_eligible_signals": [label for label, yes in zip(packs[0][0], safe) if yes],
        "fallback_architecture": "incompatible D input visits P at the same selected D/P hub; no extra recovery credit",
        "max_one_block_constraint_violation_t": max(0., violation)}
    cap_rows = [{"policy": c.policy, "hub_id": str(hubs.hub_id[j]), "city": str(hubs.city[j]), "route": k,
                 "blocks": int(round(caps[j, i]/c.block_tpy)), "capacity_tpy": float(caps[j, i])}
                for j in range(len(hubs)) for i, k in enumerate(ROUTES) if caps[j, i] > 0]
    profile_rows = [{"policy": c.policy, **{k: v for k, v in p.items() if k != "mu"},
                     "reservation_cost_model_usd": float(caps.sum())*c.incremental_reservation_premium_per_tpy,
                     "total_cost_model_usd": p["operating_cost_model_usd"]+float(caps.sum())*c.incremental_reservation_premium_per_tpy}
                    for p in profiles]
    return summary, center_rows, [{"policy": c.policy, **x} for x in channels], cap_rows, profile_rows


def product_accounts(mass, fractions, delta, limit):
    selected = fractions @ mass
    impurity = float(selected[4:].sum()); clean = float(selected[:4].sum())
    high_i, low_c = (1+delta)*impurity, (1-delta)*clean
    worst_q = high_i/(high_i+low_c) if high_i+low_c else 0.
    nominal_n = min(selected[ELEMENTS.index(e)]/AW[e]/RATIO[e] for e in AW)
    n = (1-delta)*nominal_n
    required = {e: n*AW[e]*RATIO[e] for e in AW}
    # Explicit hypothetical closure: source Li retained; excess Ni/Co/Mn
    # removed, added Li/O excluded from this seven-source-metal grade basis.
    retained_clean = (1-delta)*float(selected[0])+sum(required.values())
    post_q = high_i/(high_i+retained_clean) if high_i+retained_clean else 0.
    u = limit/100
    removal = max(0., 1-u*retained_clean/((1-u)*high_i)) if high_i > 0 else 0.
    return {"nominal_potential_g": nominal_n*MW, "minimum_potential_g": n*MW,
            "worst_inventory_impurity_pct": 100*worst_q,
            "nominal_inventory_impurity_pct": 100*impurity/(impurity+clean) if impurity+clean else 0.,
            "grade_admissible": bool(worst_q <= u+1e-12),
            "post_surplus_removal_impurity_pct": 100*post_q,
            "minimum_impurity_removal_fraction": removal,
            "retained_source_Li_and_stoichiometric_TM_g": retained_clean,
            "worst_impurity_mass_before_removal_g": high_i}


def product_baselines():
    phase = read_csv(ROOT / "results/qualified_product_mfa_20261001_v1/measured_precipitate_phase_metal_masses.csv")
    frontier = read_csv(ROOT / "results/qualified_blending_20261001_v1/grade_blending_frontier.csv")
    mass = phase[[e+"_g" for e in ELEMENTS]].to_numpy(); I = mass[:, 4:].sum(axis=1); clean = mass[:, :4].sum(axis=1)
    source_z = (phase.precipitation_ph > 7.5).to_numpy(dtype=float)
    require(int(source_z.sum()) == 3, "three source high-pH products")
    source_q = float(source_z @ I / (source_z @ (I+clean)))
    greedy_rows, aggregate_rows, boundary_rows, removal_rows = [], [], [], []
    for t in sorted(frontier.quality_limit_pct.unique()):
        u = float(t)/100
        delta_max = (u-source_q)/(u+source_q-2*u*source_q) if u >= source_q else None
        boundary_rows.append({"quality_limit_pct": float(t), "nominal_source_aggregate_impurity_pct": source_q*100,
            "largest_admissible_relative_mass_interval": delta_max,
            "nominal_aggregate_admissible": u >= source_q,
            "method_role": "fixed measured three-high-pH aggregate; rectangular mass envelope; not measured analytical uncertainty"})
    for row in frontier[frontier.selection_rule == "pooled"].itertuples():
        t, delta = float(row.quality_limit_pct), float(row.relative_mass_interval); u = t/100
        ih = (1+delta)*I; cl = (1-delta)*clean
        grade = ih/(ih+cl); coeff = (1-u)*ih-u*cl
        z = np.zeros(len(phase)); budget = 0.
        for j in np.argsort(grade, kind="stable"):
            if coeff[j] <= 0:
                z[j] = 1.; budget += coeff[j]
            elif budget < 0:
                z[j] = min(1., -budget/coeff[j]); budget += z[j]*coeff[j]
        result = product_accounts(mass, z, delta, t)
        require(result["grade_admissible"] and (z >= 0).all() and (z <= 1).all(), "greedy recipe grade and source bounds", threshold_pct=t, delta=delta)
        lp_z_dict = json.loads(row.source_phase_fractions)
        lp_z = np.array([lp_z_dict[label] for label in phase.phase_label])
        lp = product_accounts(mass, lp_z, delta, t)
        require(abs(lp["minimum_potential_g"]-row.tm_stoichiometric_CAM_upper_bound_g) < 1e-7 and lp["grade_admissible"], "recorded LP independently reconstructed", threshold_pct=t, delta=delta)
        diff = row.tm_stoichiometric_CAM_upper_bound_g-result["minimum_potential_g"]
        require(diff >= -1e-7, "recorded LP not below feasible greedy", threshold_pct=t, delta=delta)
        greedy_rows.append({"quality_limit_pct": t, "relative_mass_interval": delta,
            "greedy_minimum_potential_g": result["minimum_potential_g"], "LP_minimum_potential_g": row.tm_stoichiometric_CAM_upper_bound_g,
            "LP_minus_greedy_g": diff, "match_within_1e_minus7_g": abs(diff) < 1e-7,
            "LP_improvement_over_greedy_pct": 100*diff/result["minimum_potential_g"] if result["minimum_potential_g"] > 0 else None,
            "greedy_worst_inventory_impurity_pct": result["worst_inventory_impurity_pct"],
            "source_phase_fractions": json.dumps(dict(zip(phase.phase_label, z.tolist()))),
            "method_role": "low-to-high impurity greedy baseline; stoichiometric inventory potential, not CAM output"})
        source = product_accounts(mass, source_z, delta, t)
        aggregate_rows.append({"quality_limit_pct": t, "relative_mass_interval": delta,
            **source, "admissible_inventory_potential_g": source["minimum_potential_g"] if source["grade_admissible"] else None,
            "method_role": "fixed source aggregate; infeasible inventory potential is not credited as qualified output"})
        for name, account in (("LP_selected_inventory", lp), ("fixed_source_high_pH_aggregate", source)):
            removal_rows.append({"recipe": name, "quality_limit_pct": t, "relative_mass_interval": delta,
                **account,
                "method_role": "hypothetical surplus-TM removal, source Li retained, added Li/O excluded; minimum impurity removal requirement only, not demonstrated separation yield"})
    require(len(greedy_rows) == 52, "52 matched product conditions")
    return greedy_rows, aggregate_rows, boundary_rows, removal_rows


def freeze_decomposition(premium_runs, profiles):
    def select(policy, h):
        return next((i, r) for i, r in enumerate(premium_runs) if r["config"]["policy"] == policy and r["config"]["maximum_independent_lot_t"] == 10 and r["config"]["incremental_reservation_premium_per_tpy"] == h)
    zi, zero = select("cascade", 0.); ji, joint = select("cascade", 500.)
    getp = lambda i: [p for p in profiles if p["source_id"] == f"premium:{i:02d}" and p["new_block_tpy"] == 1000.]
    zps, jps = getp(zi), getp(ji)
    zp = max(zps, key=lambda p: p["operating_cost_model_usd"])
    jp = max(jps, key=lambda p: p["operating_cost_model_usd"])
    Cz = sum(x["capacity_tpy"] for x in zero["capacity"]); Cj = sum(x["capacity_tpy"] for x in joint["capacity"])
    frozen = zp["operating_cost_model_usd"]+500*Cz; incumbent = jp["operating_cost_model_usd"]+500*Cj
    require(abs(incumbent-joint["worst_cost_model_usd"]) < .05, "main economic comparator source consistency")
    rows = []
    for z in zps:
        j = next(p for p in jps if p["p"] == z["p"])
        rows.append({"p": z["p"], "frozen_source_id": f"premium:{zi:02d}", "joint_source_id": f"premium:{ji:02d}",
            "frozen_original_capacity_tpy": Cz, "joint_original_capacity_tpy": Cj,
            "reservation_saving_model_usd": 500*(Cz-Cj),
            "additional_transport_tkm": j["transport_tkm"]-z["transport_tkm"],
            "additional_transport_cost_model_usd": j["transport_cost_model_usd"]-z["transport_cost_model_usd"],
            "additional_processing_cost_model_usd": j["processing_cost_model_usd"]-z["processing_cost_model_usd"],
            "additional_assay_cost_model_usd": j["assay_cost_model_usd"]-z["assay_cost_model_usd"],
            "profile_saving_model_usd": z["operating_cost_model_usd"]+500*Cz-j["operating_cost_model_usd"]-500*Cj,
            "is_frozen_worst_total_cost_profile": z["p"] == zp["p"], "is_joint_worst_total_cost_profile": j["p"] == jp["p"]})
    return {"frozen_source_id": f"premium:{zi:02d}", "joint_source_id": f"premium:{ji:02d}",
        "frozen_worst_cost_p": zp["p"], "joint_worst_cost_p": jp["p"],
        "original_frozen_worst_cost_h500_model_usd": frozen, "original_joint_incumbent_model_usd": incumbent,
        "original_saving_vs_frozen_model_usd": frozen-incumbent,
        "reservation_saving_model_usd": 500*(Cz-Cj),
        "additional_operating_cost_between_each_worst_profile_model_usd": jp["operating_cost_model_usd"]-zp["operating_cost_model_usd"],
        "method_role": "original exported capacities and premium-h0 frozen source exactly as audit_strong_comparators.py; each total-cost worst profile, never max transport"}, rows


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False,
                               default=lambda x: x.item() if isinstance(x, np.generic) else x.tolist())+"\n", encoding="utf-8")


def main():
    started = time.perf_counter(); track(__file__); track(ROOT / "scripts/run_signal_contingent_network.py")
    origins, hubs, distance = geometry()
    registry = read_csv(REGISTRY); values = dict(zip(registry.parameter_id, registry.value))
    costs = np.array([float(values[f"allen_{r}_total_cost"])*1000 for r in ("direct", "hydro", "pyro")])
    sources = [("mean_export", "signal_policy_export_20261001_v2/smoke_all_runs.json"),
               ("capacity_v4", "signal_capacity_20261001_v4/capacity_all_runs.json"),
               ("premium", "signal_reservation_premium_20261001_v1/premium_all_runs.json")]
    runs = []; premium_runs = None
    for name, rel in sources:
        entries = read_json(ROOT / "results" / rel)
        if name == "premium": premium_runs = entries
        for i, run in enumerate(entries):
            runs.append((f"{name}:{i:02d}", rel, i, run))
    fixed, fixed_caps, fixed_profiles = fixed_reblocking(runs, origins, hubs, distance, costs)
    frozen, frozen_profiles = freeze_decomposition(premium_runs, fixed_profiles)
    heuristic, centers, channels, caps, profiles = [], [], [], [], []
    for policy in ("confirmation", "cascade"):
        ref = next(r for r in premium_runs if r["config"]["policy"] == policy and r["config"]["maximum_independent_lot_t"] == 10 and r["config"]["incremental_reservation_premium_per_tpy"] == 500)
        result = centralized_baseline(Config(**ref["config"]), origins, hubs, distance, costs, ref)
        heuristic.append(result[0]); centers.extend(result[1]); channels.extend(result[2]); caps.extend(result[3]); profiles.extend(result[4])
    greedy, aggregate, boundary, removal = product_baselines()
    # Reject a run if inputs changed while being read (other agents may work
    # concurrently). No source or manuscript file is modified by this script.
    require(all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in INPUTS.items()), "all tracked inputs unchanged during calculation")
    tables = {"fixed_routing_capacity_reblocking.csv": fixed, "fixed_routing_capacity_by_site.csv": fixed_caps,
        "fixed_routing_profile_costs.csv": fixed_profiles, "frozen_comparator_profile_decomposition.csv": frozen_profiles,
        "centralized_heuristic_best_by_DP_center.csv": centers, "centralized_heuristic_policy_channels.csv": channels,
        "centralized_heuristic_capacity.csv": caps, "centralized_heuristic_profiles.csv": profiles,
        "product_greedy_52_conditions.csv": greedy, "source_aggregate_52_conditions.csv": aggregate,
        "source_aggregate_delta_boundaries.csv": boundary, "post_stoichiometry_impurity_removal_requirements.csv": removal}
    key_fixed = [x for x in fixed if x["source_id"] in (frozen["frozen_source_id"], frozen["joint_source_id"]) ]
    central_removal = next(x for x in removal if x["recipe"] == "LP_selected_inventory" and x["quality_limit_pct"] == .6 and x["relative_mass_interval"] == 0)
    summary = {"fixed_routing_source_designs": len(runs), "fixed_routing_module_scenarios": len(fixed),
        "fixed_routing_evaluation_independent_lot_t": 10., "fixed_routing_repricing_h": 500.,
        "fixed_routing_core_sources_module_comparison": key_fixed, "original_frozen_comparator": frozen,
        "centralized_heuristics": heuristic, "product_conditions": len(greedy),
        "greedy_matches_recorded_LP_within_1e_minus7_g": sum(bool(x["match_within_1e_minus7_g"]) for x in greedy),
        "greedy_nonmatches": [x for x in greedy if not x["match_within_1e_minus7_g"]],
        "source_aggregate_delta_boundary_at_0p6": next(x for x in boundary if x["quality_limit_pct"] == .6),
        "nominal_0p6_LP_post_stoichiometry_requirement": central_removal,
        "checks_passed": len(CHECKS), "runtime_seconds": time.perf_counter()-started,
        "interpretation": {"capacity": "fixed-routing minimum integer blocks under a total-capacity Bernstein sufficient bound, not routing reoptimization or exact chance constraints",
            "module_sensitivity": "new module scenarios at fixed routing, independent b=10 t and h=500; source design lot and premium preserved separately",
            "heuristic": "whole observed-signal lots sent to one selected DP hub or nearest selected H hub; same-hub P fallback; no latent-state/profile dispatch; no global optimality claim",
            "products": "matched measured inventories and uncertainty design conditions; stoichiometric potential and impurity removal requirement, not manufactured CAM or validated purification"}}
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items(): pd.DataFrame(rows).to_csv(OUT/name, index=False)
    pd.DataFrame([{k: v for k, v in x.items() if k != "config"} for x in heuristic]).to_csv(OUT/"centralized_heuristic_comparison.csv", index=False)
    write_json(OUT/"summary.json", summary); write_json(OUT/"self_checks.json", {"all_pass": True, "checks": CHECKS})
    manifest = {"generated_utc": datetime.now(timezone.utc).isoformat(), "script": str(Path(__file__).resolve()),
        "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
        "inputs": [{"path": p, "sha256": h} for p, h in sorted(INPUTS.items())],
        "outputs": [{"path": str(p.relative_to(OUT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "manifest.json"],
        "method_roles": summary["interpretation"], "runtime_seconds": time.perf_counter()-started,
        "write_scope": [str(Path(__file__).resolve()), str(OUT)], "optimization_calls": {"MILP": 0, "LP": 0},
        "candidate_location_role": "city options with unrestricted scenario D/H/P capability; no claim of verified plant capability",
        "certificate_assumptions": "fixed annual workload; independent bounded lot outcomes; K=51 union allocation and Var<=b*mu; no guarantee under cross-lot common-mode dependence"}
    write_json(OUT/"manifest.json", manifest)
    print(json.dumps({"output": str(OUT), "elapsed_seconds": time.perf_counter()-started,
        "fixed_source_designs": len(runs), "fixed_module_scenarios": len(fixed),
        "heuristics": [{k: v for k, v in x.items() if k in ("policy", "D_P_city", "total_capacity_tpy", "worst_endpoint_cost_model_usd", "heuristic_gap_to_MILP_incumbent_pct", "families_evaluated")} for x in heuristic],
        "greedy_matches": summary["greedy_matches_recorded_LP_within_1e_minus7_g"], "checks_passed": len(CHECKS)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
