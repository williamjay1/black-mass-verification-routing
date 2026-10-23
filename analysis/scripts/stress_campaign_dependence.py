"""Fixed-policy campaign stress and analytic handling limits, not field evidence.

No optimizer import. Campaigns are independent; all material within a campaign
shares an outcome/dispatch channel. This conservative scenario changes both
quality and channel dependence, not the observed means or policy.
"""
from pathlib import Path
import hashlib, json, platform
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/inventions_campaign_stress_20261023_v2'
DATA = ROOT / 'datasets/futuram_network_inputs_20260930_v1'

def masses(p, c):
    if c['policy'] == 'confirmation':
        s, f = c['confirm_s'], c['confirm_f']
        return ['positive', 'negative'], np.array([p*s, p*(1-s)]), np.array([(1-p)*f, (1-p)*(1-f)])
    assert c['policy'] == 'cascade'
    ss, sc, fs, fc = c['screen_s'], c['confirm_s'], c['screen_f'], c['confirm_f']
    s = max(0., ss+sc-1) if c['conservative_joint_s'] else ss*sc
    f = fs*fc+c['bad_error_dependence']*(min(fs,fc)-fs*fc)
    return ['both_positive','screen_positive_confirm_negative','screen_negative'], p*np.array([s,ss-s,1-ss]), (1-p)*np.array([f,fs-f,1-fs])

def arrays(run, p):
    c = run['config']; org = pd.read_csv(DATA/f"national_origins_{c['year']}.csv")
    hubs = pd.read_csv(DATA/'candidate_hubs.csv').sort_values('hub_id').reset_index(drop=True)
    hi = {v:i for i,v in enumerate(hubs.hub_id)}; ki = {'D':0,'H':1,'P':2}
    caps = np.zeros((len(hubs),3))
    for x in run['capacity']: caps[hi[x['hub_id']],ki[x['route']]] = x['capacity_tpy']
    labels,g,b = masses(p,c); si = {v:i for i,v in enumerate(labels)}; origins=[]
    for o in org.itertuples():
        probs=[]; coeff=[]
        for row in run['signal_contingent_nominal_policy_flows']:
            if row['origin_id'] != o.origin_id: continue
            frac = row['nominal_if_all_input_had_signal_t']/o.reference_black_mass_tpy
            for bad, prob in ((False,g[si[row['signal']]]),(True,b[si[row['signal']]])):
                probs.append(frac*prob); load=np.zeros_like(caps)
                j,k = hi[row['hub_id']],ki[row['route']]
                if bad and k==0:
                    load[j,0]=c['failed_direct_capacity_fraction']; load[j,2]=1.
                else: load[j,k]=1.
                coeff.append(load.ravel())
        pr=np.array(probs); assert np.isclose(pr.sum(),1,atol=1e-8)
        origins.append((o.reference_black_mass_tpy,pr/pr.sum(),np.array(coeff)))
    return caps.ravel(),origins

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    base = ROOT/'results/signal_policy_export_20261001_v2/smoke_all_runs.json'
    cert = ROOT/'results/signal_capacity_20261001_v4/capacity_all_runs.json'
    premium = ROOT/'results/signal_reservation_premium_20261001_v1/premium_all_runs.json'
    designs = [r for r in json.loads(base.read_text()) if r['config']['policy'] in ('confirmation','cascade')]
    designs += [r for r in json.loads(cert.read_text()) if r['config']['policy'] in ('confirmation','cascade') and r['config']['maximum_independent_lot_t'] in (10,50)]
    designs += [r for r in json.loads(premium.read_text()) if r['config']['policy'] in ('confirmation','cascade') and r['config']['maximum_independent_lot_t']==10 and r['config']['incremental_reservation_premium_per_tpy']==500]
    for r in designs:
        r['config'].setdefault('maximum_independent_lot_t',0.)
        r['config'].setdefault('network_overflow_budget',.1)
        r['config'].setdefault('incremental_reservation_premium_per_tpy',0.)
    rows=[]; bounds=[]; diagnostic=[]; reps=4096
    for r in designs:
        c=r['config']; policy=c['policy']; design_b=c['maximum_independent_lot_t']; h=c['incremental_reservation_premium_per_tpy']
        bmax=[]
        for p in (.2,.35,.5,.65,.8):
            caps,origins=arrays(r,p)
            mu=sum(n*(pr@a) for n,pr,a in origins)
            # Affine means imply checking interval endpoints is sufficient.
            assert np.max(mu-caps)<1e-6, 'mean-infeasible policy cannot receive a certificate'
            headroom=np.maximum(0,caps-mu)
            ell=np.log(51/c['network_overflow_budget'])
            active=mu>1e-10
            safe=np.min(headroom[active]**2/(ell*(2*mu[active]+2*headroom[active]/3)))
            if safe < 1e-8: safe=0.
            bmax.append(safe)
            diagnostic.append({'policy':policy,'design_lot_t':design_b,'reservation_premium':h,'p':p,'certified_common_campaign_mass_t':safe,
                               'maximum_mean_capacity_excess_t':float(np.max(mu-caps))})
            for campaign in (10.,20.,50.,100.,250.,500.,1000.):
                rng=np.random.default_rng(34034); loads=np.zeros((reps,len(caps)))
                for n,pr,a in origins:
                    full=int(n//campaign);rem=n-full*campaign
                    counts=rng.multinomial(full,pr,size=reps)*campaign
                    if rem>1e-10: counts=counts+rng.multinomial(1,pr,size=reps)*rem
                    loads += counts@a
                fail=(loads>caps[None,:]+1e-7).any(axis=1)
                rows.append({'policy':policy,'design_lot_t':design_b,'reservation_premium':h,'p':p,'campaign_mass_t':campaign,
                             'repetitions':reps,'overflow_count':int(fail.sum()),'overflow_share':float(fail.mean()),
                             'total_reserved_tpy':float(caps.sum())})
        bounds.append({'policy':policy,'design_lot_t':design_b,'reservation_premium':h,'maximum_certified_campaign_mass_t':min(bmax),
                       'network_budget':c['network_overflow_budget'],'certificate_constraints':51})
        assert min(bmax) >= design_b-1e-6
        # Independently verify affine profile interpolation for exported policies.
        lo_caps, lo_org=arrays(r,.2); _,hi_org=arrays(r,.8)
        lo_mu=sum(n*(pr@a) for n,pr,a in lo_org)
        hi_mu=sum(n*(pr@a) for n,pr,a in hi_org)
        for p in np.linspace(.2,.8,41):
            _,mid_org=arrays(r,float(p)); mid_mu=sum(n*(pr@a) for n,pr,a in mid_org)
            assert np.allclose(mid_mu,lo_mu+(p-.2)/.6*(hi_mu-lo_mu),rtol=1e-10,atol=1e-8)
    pd.DataFrame(rows).to_csv(OUT/'fixed_policy_campaign_replay.csv',index=False)
    pd.DataFrame(bounds).to_csv(OUT/'certified_handling_limits.csv',index=False)
    pd.DataFrame(diagnostic).to_csv(OUT/'profile_handling_limits.csv',index=False)
    manifest={'role':'conditional computational stress test; no measured quality covariance or plant reliability',
              'dependence':'identical complete quality/outcome/dispatch channel within a campaign; independent campaigns',
              'seed':34034,'repetitions_per_cell':reps,'cells':len(rows),'python':platform.python_version(),
              'numpy':np.__version__,'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (base,cert,premium)},
              'formula':'b_max=min_(profile,occupied site route) (C-mu)^2/[log(51/eps)*(2mu+2(C-mu)/3)]',
              'limits':'Conservative sufficient bound; exceeding it is not proof of infeasibility. Zero simulated overflow is not zero risk.'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(pd.DataFrame(bounds).to_string(index=False))
    print(pd.DataFrame(rows).query('p == .8').to_string(index=False))

if __name__=='__main__': main()
