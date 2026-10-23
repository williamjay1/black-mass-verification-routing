"""Raw-workbook product-grade frontier, not a universal battery specification.

All masses are reconstructed from public deposited measured concentrations,
digested sample mass/volume, and collected precipitate mass. No product phase
is classified from its rounded figure label. Source NMC/LFP context is kept
separate from Allen's common-output cost case and national supply scenarios.
"""
from __future__ import annotations
import csv
import hashlib
import json
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path
import numpy as np
import pandas as pd
from extract_tudelft_public_ods import NS,cell_value

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'results/tudelft_58947_ods_extract_2026-09-30'
SOURCE=DATA/'electrochemical_and_precipitation_data_ph_4_table_3_and_fig_6__leaching_electro_precip_ph4.csv'
ODS=ROOT/'datasets/work_tudelft_58947_20260930/publication_files/Data for publication/Electrochemical and precipitation data pH 4 (Table 3 and Fig 6).ods'
OUT=ROOT/'results/qualified_product_mfa_20261001_v1'
ELEMENTS=('Li','Co','Ni','Mn','Al','Fe','Cu')
MOLAR={'Li':6.94,'Ni':58.6934,'Co':58.933194,'Mn':54.938044,'O':15.999}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def readrows():
    with SOURCE.open(encoding='utf-8-sig',newline='') as f:return list(csv.reader(f))
def find(rows,label,col=0):
    matches=[(i,row) for i,row in enumerate(rows) if len(row)>col and row[col]==label]
    if len(matches)!=1:raise ValueError((label,matches))
    return matches[0]

def original_cells():
    with zipfile.ZipFile(ODS) as f:root=ET.fromstring(f.read('content.xml'))
    sheet=[s for s in root.findall('.//table:table',NS) if s.get('{'+NS['table']+'}name','').lower().startswith('leaching')][0]
    result={};r=0
    for row in sheet.findall('table:table-row',NS):
        nrow=int(row.get('{'+NS['table']+'}number-rows-repeated','1'));c=0
        for cell in list(row):
            ncol=int(cell.get('{'+NS['table']+'}number-columns-repeated','1'));v=cell_value(cell)
            if v:result[(r+1,c+1)]=v
            c+=ncol
        r+=nrow
    return result

def main():
    OUT.mkdir(parents=True,exist_ok=True);rows=readrows()
    # Public workflow uses concentration ppm in a 100 mL digestion of a
    # weighed sample, followed by a collected dry precipitate mass.
    first=next(i for i,r in enumerate(rows) if len(r)>1 and r[1]=='ICP results precipitate characterization')
    end=next(i for i,r in enumerate(rows[first+1:],first+1) if r and r[0]=='Concentration of elements in precipitates') if any(r and r[0]=='Concentration of elements in precipitates' for r in rows[first+1:]) else 202
    precip=[]
    for i,row in enumerate(rows[first+2:first+8],first+2):
        label=row[0]; assert label.endswith(' Pr') and len(row)>17
        ph=float(row[15]);digested_g=float(row[16]);volume_ml=float(row[17])
        # Collected mass is recorded in precipitation-stripping experiment.
        matches=[r for r in rows if len(r)>17 and r[10]==label.removesuffix(' Pr') and r[16] and r[17]]
        assert len(matches)==1,(label,len(matches))
        collected_g=float(matches[0][17])-float(matches[0][16])
        concentration=np.array([float(row[j]) for j in range(1,8)])
        mass_fraction=concentration*volume_ml/1e6/digested_g
        metal_g=mass_fraction*collected_g
        impurity_pct=100*sum(metal_g[4:])/metal_g.sum()
        record={'phase_label':label,'precipitation_ph':ph,'source_csv_row_1based':i+1,
                'collected_precipitate_g':collected_g,'digested_sample_g':digested_g,'digestion_volume_ml':volume_ml,
                'impurity_on_all_metal_basis_pct':impurity_pct,'target_metals_g':float(sum(metal_g[1:4])),
                **{f'{e}_g':float(metal_g[j]) for j,e in enumerate(ELEMENTS)}}
        precip.append(record)
    a=pd.DataFrame(precip)
    assert len(a)==6
    # Independent check against deposited calculation block, not the article
    # caption. This check would fail on ppm/kg/g or basis errors.
    block=next(i for i,r in enumerate(rows) if len(r)>1 and r[1]=='Amount of metal per precipitate')
    for record in precip:
        entries=[r for r in rows[block+2:block+8] if r[0]==record['phase_label']]
        assert len(entries)==1
        for j,e in enumerate(ELEMENTS): assert abs(record[f'{e}_g']-float(entries[0][j+1]))<1e-10
    a.to_csv(OUT/'measured_precipitate_phase_metal_masses.csv',index=False)
    # Inspect the ACTUAL original formula: A294=C257:C259/C97*500/L160.
    # C97 is original metal in solids, NOT concentration in initial PLS.
    # Thus the source reports original-feed recovery with a 220/500mL aliquot
    # factor. No second leaching factor should be applied to that recovery.
    cells=original_cells()
    aliquot_fraction=float(cells[(160,12)])/500.
    assert abs(aliquot_fraction-.44)<1e-12
    source_yields={'Co':48.294755876082029/100,'Ni':47.924995806673159/100,'Mn':53.978388594552825/100}
    high=a[a.precipitation_ph>=7.98]
    original_feed_metals={e:float(cells[(97,j)]) for e,j in (('Co',3),('Ni',4),('Mn',5))}
    entering={e:original_feed_metals[e]*aliquot_fraction for e in source_yields}
    for e in source_yields:assert abs(float(high[f'{e}_g'].sum()/entering[e])-source_yields[e])<1e-12
    frontier=[]
    thresholds=(.1,.2,.3,.5,.6,.64,.65,1.,5.,12.,46.,80.)
    nmc622_molar_mass=MOLAR['Li']+.6*MOLAR['Ni']+.2*MOLAR['Co']+.2*MOLAR['Mn']+2*MOLAR['O']
    for limit in thresholds:
        selected=a[a.impurity_on_all_metal_basis_pct<=limit+1e-12]
        outputs={e:float(selected[f'{e}_g'].sum()) for e in source_yields}
        n_cam=min(outputs['Ni']/MOLAR['Ni']/.6,outputs['Co']/MOLAR['Co']/.2,outputs['Mn']/MOLAR['Mn']/.2)
        frontier.append({'quality_limit_metal_impurity_pct':limit,'selected_phase_count':len(selected),
                         'qualified_precipitate_g':float(selected.collected_precipitate_g.sum()),
                         'qualified_target_metal_g':sum(outputs.values()),
                         **{f'{e}_qualified_g':outputs[e] for e in source_yields},
                         **{f'{e}_source_denominator_recovery_pct':100*outputs[e]/entering[e] for e in source_yields},
                         'nmc622_tm_stoichiometric_upper_bound_g':n_cam*nmc622_molar_mass,
                         'definition':'quality limit is analyst-requested; TM-based CAM upper bound ignores added Li, synthesis loss and electrochemical qualification'})
    f=pd.DataFrame(frontier);f.to_csv(OUT/'product_grade_recovery_frontier.csv',index=False)
    # Scale sensitivity: reserve needed per same qualified-product requirement,
    # relative to the 0.65% illustration; not industrial capacity forecasting.
    ref=float(f.loc[f.quality_limit_metal_impurity_pct.eq(.65),'nmc622_tm_stoichiometric_upper_bound_g'].iloc[0])
    f['throughput_multiplier_for_same_tm_CAM_upper_bound_vs_0p65']=np.where(f.nmc622_tm_stoichiometric_upper_bound_g>0,ref/f.nmc622_tm_stoichiometric_upper_bound_g,np.inf)
    f.to_csv(OUT/'product_grade_recovery_frontier.csv',index=False)
    summary={'article_doi':'10.1039/d6ra04652e','dataset_doi':'10.4121/58947ce2-c651-43cc-8e4d-760b2e60adfb',
             'source_file_sha256':sha(SOURCE),'original_ods_sha256':sha(ODS),'script_sha256':sha(Path(__file__)),
             'article_online_date':'2026-08-18','raw_deposited_phase_count':len(a),
             'source_yield_denominator':'original metal in solids, corrected by220/500mL aliquot; original ODS A294:C294 formulas verified againstC97:E97andL160',
             'original_feed_metals_g':original_feed_metals,'aliquot_fraction':aliquot_fraction,
             'aliquot_equivalent_original_feed_metals_g':entering,
             'phase_7p98_impurity_pct':float(a.loc[a.precipitation_ph.eq(7.98),'impurity_on_all_metal_basis_pct'].iloc[0]),
             'source_reported_weighted_impurity_pct':.49968927282418879,
             'computed_high_phase_weighted_metal_impurity_pct':float(100*high[['Al_g','Fe_g','Cu_g']].to_numpy().sum()/high[[f'{e}_g' for e in ELEMENTS]].to_numpy().sum()),
             'rounding_warning':'Article rounds 0.641336% to0.6%; strict0.6% and rounded-label admission are different design rules. Neither is a universal battery-grade specification.',
             'scope':'measured source purification products; no industrial scale-up, validated assay, EU prevalence, battery CAM qualification, or LCA credit inferred'}
    (OUT/'audit_manifest.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2));print(f.to_string(index=False))

if __name__=='__main__':main()
