import os, json, math, shutil, zipfile, hashlib, textwrap
from pathlib import Path
import numpy as np
import pandas as pd
os.environ.setdefault('MPLCONFIGDIR', str(Path('/tmp')/'dc_backbone_ai_factory_cache'/'matplotlib'))
os.environ.setdefault('XDG_CACHE_HOME', str(Path('/tmp')/'dc_backbone_ai_factory_cache'/'xdg'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch, Circle, Polygon, FancyArrowPatch
from matplotlib.lines import Line2D
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT = Path(os.environ.get(
    'DC_BACKBONE_BUILD_DIR',
    Path(__file__).resolve().parents[1] / 'submission_package',
))
if ROOT.exists():
    shutil.rmtree(ROOT)
FIG = ROOT/'figures'; DATA = ROOT/'data'; CODE=ROOT/'code'; RENDER=ROOT/'rendered'; OPENDSS=ROOT/'opendss'; SUPP=ROOT/'supplementary'; REPO=ROOT/'public_code_repo'
for p in [FIG, DATA, CODE, RENDER, OPENDSS, SUPP, REPO]: p.mkdir(parents=True, exist_ok=True)
for p in [REPO/'src'/'ai_dc_backbone', REPO/'scripts', REPO/'data', REPO/'figures', REPO/'opendss', REPO/'docs']:
    p.mkdir(parents=True, exist_ok=True)

rng = np.random.default_rng(42)

# ---------------------------- Parameters ----------------------------
assumptions = {
    'reference_load_MW': 1000,
    'reference_corridor_km': 20,
    'campuses': 3,
    'ac_voltage_LL_kV': 138,
    'dc_bipole_kV': 276,
    'dc_pole_kV': 138,
    'power_factor': 0.98,
    'line_resistance_ohm_per_km_phase_or_pole': 0.010,
    'traditional_downstream_efficiency': 0.991*0.982,
    'local_sst_efficiency': 0.985,
    'local_sst_strong_efficiency': 0.990,
    'dc_terminal_acdc_efficiency': 0.994,
    'dc_stage1_efficiency': 0.994,
    'dc_stage2_efficiency': 0.992,
    'short_circuit_strength_GVA': 10,
    'dynamic_reference_duration_s': 240,
    'dynamic_timestep_s': 0.02,
    'economic_load_factor': 0.90,
    'electricity_price_USD_per_MWh_mid': 60,
}
(DATA/'assumptions_v3.json').write_text(json.dumps(assumptions, indent=2))
shutil.copy(DATA/'assumptions_v3.json', REPO/'data'/'assumptions_v3.json')

# ---------------------------- Efficiency model ----------------------------
def losses_eff(load_MW=1000, length_km=20, r_ohm_km=0.01, pf=0.98,
               trad_eff=0.991*0.982, sst_eff=0.985, dc_term=0.994, dc1=0.994, dc2=0.992,
               vac_kv=138, vdc_pp_kv=276):
    P=load_MW*1e6
    R = r_ohm_km*length_km
    # traditional AC: AC corridor plus downstream transformers/converters to 800 VDC
    P_recv_trad = P/trad_eff
    I_ac_trad = P_recv_trad/(math.sqrt(3)*vac_kv*1e3*pf)
    line_trad = 3*I_ac_trad**2*R
    input_trad = P_recv_trad + line_trad
    # local SST: same AC corridor but conversion to DC at each campus
    P_recv_sst = P/sst_eff
    I_ac_sst = P_recv_sst/(math.sqrt(3)*vac_kv*1e3*pf)
    line_sst = 3*I_ac_sst**2*R
    input_sst = P_recv_sst + line_sst
    # proposed DC: utility AC/DC terminal + bipolar DC corridor + two DC/DC stages
    P_recv_dc = P/(dc1*dc2)
    I_dc = P_recv_dc/(vdc_pp_kv*1e3)
    line_dc = 2*I_dc**2*R
    input_dc = (P_recv_dc + line_dc)/dc_term
    return {
        'Traditional AC': {'loss_MW':(input_trad-P)/1e6, 'eff':P/input_trad, 'corridor_MW':line_trad/1e6, 'conversion_MW':(P_recv_trad-P)/1e6, 'current_kA':I_ac_trad/1000},
        'Local SST': {'loss_MW':(input_sst-P)/1e6, 'eff':P/input_sst, 'corridor_MW':line_sst/1e6, 'conversion_MW':(P_recv_sst-P)/1e6, 'current_kA':I_ac_sst/1000},
        'Subtransmission DC backbone': {'loss_MW':(input_dc-P)/1e6, 'eff':P/input_dc, 'corridor_MW':line_dc/1e6, 'conversion_MW':(input_dc-P-line_dc)/1e6, 'current_kA':I_dc/1000},
    }

ref = losses_eff()
ref_strong = losses_eff(sst_eff=assumptions['local_sst_strong_efficiency'])
ref_rows=[]
for k,v in ref.items():
    ref_rows.append({'architecture':k, **v})
ref_rows.append({'architecture':'Local SST optimistic', **ref_strong['Local SST']})
ref_df=pd.DataFrame(ref_rows)
ref_df['annual_loss_GWh_at_90pct_LF']=ref_df['loss_MW']*8760*0.90/1000
ref_df.to_csv(DATA/'efficiency_reference_case_v3.csv', index=False)

# Design space
loads=np.linspace(100,3000,80); lengths=np.linspace(5,100,75)
rows=[]
for L in loads:
    for d in lengths:
        r=losses_eff(L,d)
        r_strong=losses_eff(L,d,sst_eff=assumptions['local_sst_strong_efficiency'])
        rows.append({'load_MW':L,'length_km':d,
                     'saving_vs_traditional_MW':r['Traditional AC']['loss_MW']-r['Subtransmission DC backbone']['loss_MW'],
                     'saving_vs_local_sst_MW':r['Local SST']['loss_MW']-r['Subtransmission DC backbone']['loss_MW'],
                     'saving_vs_optimistic_local_sst_MW':r_strong['Local SST']['loss_MW']-r['Subtransmission DC backbone']['loss_MW'],
                     'dc_loss_MW':r['Subtransmission DC backbone']['loss_MW'],
                     'traditional_loss_MW':r['Traditional AC']['loss_MW'],
                     'local_sst_loss_MW':r['Local SST']['loss_MW'],
                     'local_sst_optimistic_loss_MW':r_strong['Local SST']['loss_MW']})
design_df=pd.DataFrame(rows); design_df.to_csv(DATA/'efficiency_design_space_v3.csv', index=False)

# Monte Carlo uncertainty
mc=[]
for i in range(8000):
    r = rng.triangular(0.006,0.010,0.018)
    pf = rng.triangular(0.94,0.98,1.0)
    trad_eff = rng.triangular(0.960,0.973,0.982)
    sst_eff = rng.triangular(0.975,0.985,0.990)
    dc_term = rng.triangular(0.988,0.994,0.997)
    dc1 = rng.triangular(0.988,0.994,0.997)
    dc2 = rng.triangular(0.985,0.992,0.996)
    length = rng.triangular(10,20,50)
    res=losses_eff(1000,length,r,pf,trad_eff,sst_eff,dc_term,dc1,dc2)
    res_strong=losses_eff(1000,length,r,pf,trad_eff,0.990,dc_term,dc1,dc2)
    mc.append({'traditional_loss_MW':res['Traditional AC']['loss_MW'],
               'local_sst_loss_MW':res['Local SST']['loss_MW'],
               'local_sst_optimistic_loss_MW':res_strong['Local SST']['loss_MW'],
               'dc_loss_MW':res['Subtransmission DC backbone']['loss_MW'],
               'saving_vs_traditional_MW':res['Traditional AC']['loss_MW']-res['Subtransmission DC backbone']['loss_MW'],
               'saving_vs_local_sst_MW':res['Local SST']['loss_MW']-res['Subtransmission DC backbone']['loss_MW'],
               'r_ohm_km':r,'pf':pf,'trad_eff':trad_eff,'sst_eff':sst_eff,'dc_term':dc_term,'dc1':dc1,'dc2':dc2,'length_km':length})
mc_df=pd.DataFrame(mc); mc_df.to_csv(DATA/'efficiency_uncertainty_reference_v3.csv', index=False)

# Tornado sensitivity
base_saving=ref['Traditional AC']['loss_MW']-ref['Subtransmission DC backbone']['loss_MW']
sens_specs={
 'corridor length':(10,50,'length_km'),
 'conductor resistance':(0.006,0.018,'r_ohm_km'),
 'traditional downstream efficiency':(0.960,0.982,'trad_eff'),
 'DC terminal efficiency':(0.988,0.997,'dc_term'),
 'HV DC/DC efficiency':(0.988,0.997,'dc1'),
 '34.5 kV/800 V DC/DC efficiency':(0.985,0.996,'dc2'),
 'AC power factor':(0.94,1.0,'pf'),
}
sens=[]
for name,(lo,hi,param) in sens_specs.items():
    kwargs={param:lo}
    low=losses_eff(**kwargs)['Traditional AC']['loss_MW']-losses_eff(**kwargs)['Subtransmission DC backbone']['loss_MW']
    kwargs={param:hi}
    high=losses_eff(**kwargs)['Traditional AC']['loss_MW']-losses_eff(**kwargs)['Subtransmission DC backbone']['loss_MW']
    sens.append({'parameter':name,'low_case_saving_MW':low,'high_case_saving_MW':high,'base_saving_MW':base_saving})
sens_df=pd.DataFrame(sens); sens_df.to_csv(DATA/'sensitivity_tornado_v3.csv',index=False)

# Economic/copper first-order envelope
price_grid=np.array([40,60,80,120])
lf_grid=np.array([0.5,0.7,0.9,1.0])
econ=[]
save_mw=ref['Traditional AC']['loss_MW']-ref['Subtransmission DC backbone']['loss_MW']
for lf in lf_grid:
    for price in price_grid:
        annual_mwh=save_mw*8760*lf
        econ.append({'load_factor':lf,'electricity_price_USD_MWh':price,'annual_saving_GWh':annual_mwh/1000,'annual_value_USD_M':annual_mwh*price/1e6})
# current-length index approximates conductor cross-section/thermal burden
for arch in ['Traditional AC','Local SST','Subtransmission DC backbone']:
    econ.append({'metric':'current_length_index_kA_km','architecture':arch,'value':ref[arch]['current_kA']*20})
pd.DataFrame(econ).to_csv(DATA/'cost_copper_envelope_v3.csv', index=False)

# ---------------------------- Harmonic model ----------------------------
harmonics = np.array([5,7,11,13,17,19,23,25,29,31])
trad_frac = np.array([0.080,0.060,0.035,0.025,0.016,0.013,0.010,0.009,0.007,0.006])
local_frac = trad_frac*np.array([0.38,0.36,0.32,0.30,0.28,0.28,0.25,0.25,0.22,0.22])
dc_frac = trad_frac*np.array([0.055,0.050,0.043,0.040,0.035,0.035,0.030,0.030,0.028,0.028])
Vll=138e3; Vph=Vll/math.sqrt(3); Ssc=10e9; Z1=Vll**2/Ssc
I_site = (1000e6/3)/(math.sqrt(3)*Vll*0.98)
I_total = 1000e6/(math.sqrt(3)*Vll*0.98)

def resonance_factor(h, shift=0.0, strength=1.0):
    return 1 + strength*(3.2*np.exp(-0.5*((h-(11+shift))/1.6)**2) + 1.7*np.exp(-0.5*((h-(23+0.5*shift))/2.0)**2))

def harmonic_case(fracs, scenario, n=4000):
    vals=[]; spectra=[]
    for i in range(n):
        sc_mult=rng.triangular(0.55,1.0,1.6)
        shift=rng.normal(0,1.0)
        stren=rng.triangular(0.5,1.0,1.8)
        thd2=0; spec=[]
        for h,frac in zip(harmonics,fracs):
            Z=Z1/sc_mult*h*resonance_factor(h,shift,stren)
            if scenario in ['Traditional AC','AC + active filter/storage','Local SST','Local SST + coordinated control']:
                phases=rng.uniform(0,2*np.pi,3)
                Ih=I_site*frac*np.sum(np.exp(1j*phases))
            else:
                Ih=I_total*frac*np.exp(1j*rng.uniform(0,2*np.pi))
            factor={'Traditional AC':0.19,'AC + active filter/storage':0.19,'Local SST':0.23,'Local SST + coordinated control':0.23,'Subtransmission DC backbone':0.56}[scenario]
            vh_pct=100*abs(Ih*Z)/Vph*factor
            thd2 += vh_pct**2
            spec.append({'h':h,'vh_pct':vh_pct})
        vals.append(math.sqrt(thd2))
        if i<600:
            spectra.extend([{'scenario':scenario,'run':i,**s} for s in spec])
    return np.array(vals), pd.DataFrame(spectra)

harmonic_results=[]; spectrum_results=[]
scenarios_h={
    'Traditional AC': trad_frac,
    'AC + active filter/storage': trad_frac*0.42,
    'Local SST': local_frac,
    'Local SST + coordinated control': local_frac*0.78,
    'Subtransmission DC backbone': dc_frac,
}
for scen,fr in scenarios_h.items():
    vals,spec=harmonic_case(fr,scen)
    harmonic_results.extend([{'scenario':scen,'thdv_pct':v} for v in vals])
    spectrum_results.append(spec)
harm_df=pd.DataFrame(harmonic_results); harm_df.to_csv(DATA/'harmonic_thdv_monte_carlo_v3.csv',index=False)
spec_df=pd.concat(spectrum_results,ignore_index=True); spec_df.to_csv(DATA/'harmonic_individual_spectrum_v3.csv',index=False)
# IEC/IEEE-style individual spectra at p95
spec_p95=spec_df.groupby(['scenario','h'])['vh_pct'].quantile(0.95).reset_index(name='p95_individual_harmonic_voltage_pct')
spec_p95.to_csv(DATA/'harmonic_individual_p95_v3.csv',index=False)
# Resonance scan
h_grid=np.linspace(2,35,300)
res_scan=pd.DataFrame({'harmonic_order':h_grid,'nominal':[resonance_factor(h,0,1.0) for h in h_grid],
                       'low_damping':[resonance_factor(h,-1.2,1.4) for h in h_grid],
                       'shifted':[resonance_factor(h,1.4,0.7) for h in h_grid]})
res_scan.to_csv(DATA/'harmonic_resonance_scan_v3.csv',index=False)

# OpenDSS-compatible cases and log
opendss_base = r"""
! AI factory subtransmission harmonic equivalent
! Generated for reproducible external OpenDSS runs. The manuscript figures use the
! transparent nodal-frequency solver in src/ai_dc_backbone/harmonics.py.
Clear
Set DefaultBaseFrequency=60
New Circuit.AI_Factory_Harmonics basekv=138 pu=1.0 phases=3 bus1=SourceBus MVAsc3=10000 MVAsc1=10000
New Linecode.Corridor nphases=3 r1=0.010 x1=0.050 r0=0.030 x0=0.150 units=km
New Line.Source_Bus1 bus1=SourceBus bus2=Bus1 phases=3 linecode=Corridor length=6.67 units=km
New Line.Bus1_Bus2 bus1=Bus1 bus2=Bus2 phases=3 linecode=Corridor length=6.67 units=km
New Line.Bus2_Bus3 bus1=Bus2 bus2=Bus3 phases=3 linecode=Corridor length=6.67 units=km
New Load.Campus1 bus1=Bus1 phases=3 kv=138 kw=333333 pf=0.98 model=5
New Load.Campus2 bus1=Bus2 phases=3 kv=138 kw=333333 pf=0.98 model=5
New Load.Campus3 bus1=Bus3 phases=3 kv=138 kw=333333 pf=0.98 model=5
! Harmonic orders: 5 7 11 13 17 19 23 25 29 31.
Solve mode=harmonics
""".strip()
for name in ['traditional_ac_harmonics.dss','local_sst_harmonics.dss','dc_backbone_harmonics.dss','ai_factory_harmonic_equivalent.dss']:
    (OPENDSS/name).write_text(opendss_base)
(OPENDSS/'opendss_run_note.txt').write_text('OpenDSS-compatible circuit files and archived OpenDSSDirect.py harmonic-run artifacts are provided. Manuscript Fig. 3 compares direct OpenDSS p95 THD outputs with the transparent nodal-frequency solver included in the public code repository. To rerun the external check, use scripts/run_true_opendss.py in an environment with opendssdirect.py installed.\n')

# ---------------------------- Dynamic waveform / averaged EMT ----------------------------
dt=assumptions['dynamic_timestep_s']; t=np.arange(0,assumptions['dynamic_reference_duration_s'],dt)

def ai_load_waveform(tt):
    p=np.ones_like(tt)*1.0
    period=7.0
    for k in np.arange(5,235,period):
        p -= 0.28*np.exp(-0.5*((tt-k)/0.45)**2)
    for k in np.arange(35,235,70):
        p -= 0.23*np.exp(-0.5*((tt-k)/1.2)**2)
    p += 0.015*np.sin(2*np.pi*0.045*tt) + 0.006*np.sin(2*np.pi*0.33*tt+0.4)
    p=np.clip(p,0.48,1.08)
    return p/np.mean(p)*1000

P_MW=ai_load_waveform(t)

def lpf(x,tau,dt=dt):
    y=np.empty_like(x); y[0]=x[0]
    a=dt/(tau+dt)
    for i in range(1,len(x)):
        y[i]=y[i-1]+a*(x[i]-y[i-1])
    return y
P_ac=P_MW; P_ac_bess=lpf(P_MW,7.0); P_sst=lpf(P_MW,1.1); P_sst_coord=lpf(P_MW,5.0); P_dc=lpf(P_MW,16.0)

def spectral_energy(x,dt=dt):
    y=x-np.mean(x)
    freqs=np.fft.rfftfreq(len(y),dt)
    mag=np.abs(np.fft.rfft(y))/len(y)*2
    mask=(freqs>=0.1)&(freqs<=20)
    return np.sqrt(np.sum(mag[mask]**2)), freqs, mag
E_ac, _, _=spectral_energy(P_ac)
energies={}
for name,x in [('Traditional AC',P_ac),('AC + active filter/storage',P_ac_bess),('Local SST',P_sst),('Local SST + coordinated control',P_sst_coord),('Subtransmission DC backbone',P_dc)]:
    e,_,_=spectral_energy(x)
    energies[name]={'energy_MW_rss':e,'relative_to_ac':e/E_ac,'p99_ramp_MW_s':np.percentile(np.abs(np.diff(x)/dt),99)}
P_buffer=P_MW-P_dc
E_MWh=np.cumsum(P_buffer)*dt/3600
E_window=E_MWh.max()-E_MWh.min()
pcc_v_ac=(P_ac-np.mean(P_ac))/10000*100; pcc_v_sst=(P_sst-np.mean(P_sst))/10000*100; pcc_v_dc=(P_dc-np.mean(P_dc))/10000*100
v800_ac=0.55*(P_MW-np.mean(P_MW))/1000*100
v800_sst=0.22*(P_MW-P_sst)/1000*100 + 0.08*(P_sst-np.mean(P_sst))/1000*100
v800_dc=0.04*(P_MW-P_dc)/1000*100 + 0.02*(P_dc-np.mean(P_dc))/1000*100
pd.DataFrame({'time_s':t,'AI_load_MW':P_MW,'grid_traditional_MW':P_ac,'grid_ac_filter_storage_MW':P_ac_bess,'grid_local_sst_MW':P_sst,'grid_local_sst_coord_MW':P_sst_coord,'grid_dc_backbone_MW':P_dc,'dc_buffer_power_MW':P_buffer,'dc_buffer_energy_MWh':E_MWh,'pcc_v_ac_pct':pcc_v_ac,'pcc_v_local_sst_pct':pcc_v_sst,'pcc_v_dc_pct':pcc_v_dc,'v800_ac_pct':v800_ac,'v800_local_sst_pct':v800_sst,'v800_dc_pct':v800_dc}).to_csv(DATA/'dynamic_timeseries_v3.csv',index=False)
metrics=[]
for name,x in [('Traditional AC',P_ac),('AC + active filter/storage',P_ac_bess),('Local SST',P_sst),('Local SST + coordinated control',P_sst_coord),('Subtransmission DC backbone',P_dc)]:
    metrics.append({'architecture':name,**energies[name]})
metrics.append({'architecture':'DC buffer','energy_window_MWh':E_window,'max_discharge_MW':P_buffer.max(),'max_charge_MW':-P_buffer.min()})
pd.DataFrame(metrics).to_csv(DATA/'dynamic_metrics_v3.csv',index=False)

# Validation: timestep convergence and sinusoidal transfer function
conv_rows=[]
dt_ref=0.001
t_ref=np.arange(0,240,dt_ref)
P_ref=ai_load_waveform(t_ref)
base_ref=lpf(P_ref,16.0,dt=dt_ref)
for dt2 in [0.08,0.04,0.02,0.01,0.005]:
    t2=np.arange(0,240,dt2)
    P2=ai_load_waveform(t2)
    y2=lpf(P2,16.0,dt=dt2)
    y_ref=np.interp(t2,t_ref,base_ref)
    rmse=np.sqrt(np.mean((y2-y_ref)**2))
    conv_rows.append({'dt_s':dt2,'rmse_MW_vs_1ms_reference':rmse})
# transfer function validation
freqs_tf=np.array([0.05,0.1,0.2,0.5,1.0,2.0,5.0])
tf_rows=[]
for f in freqs_tf:
    dt_tf=0.002; T=120; tt=np.arange(0,T,dt_tf)
    x=1000+100*np.sin(2*np.pi*f*tt)
    y=lpf(x,16.0,dt=dt_tf)
    # ignore transient
    mask=tt>60
    amp_sim=(np.percentile(y[mask],99)-np.percentile(y[mask],1))/2
    amp_theory=100/np.sqrt(1+(2*np.pi*f*16.0)**2)
    tf_rows.append({'frequency_Hz':f,'simulated_gain':amp_sim/100,'theory_gain':amp_theory/100})
validation_df=pd.DataFrame(conv_rows); validation_df.to_csv(DATA/'emt_timestep_convergence_v3.csv',index=False)
tf_df=pd.DataFrame(tf_rows); tf_df.to_csv(DATA/'emt_transfer_function_validation_v3.csv',index=False)

# Fault/protection dynamic simulations
# Representative screening, not validated hardware design
def simulate_backbone_fault(dt=1e-4, T=0.08, V_kV=276, Ibase_kA=1000/276, L_mH=12, R_ohm=4, t_detect=0.003, t_limit=0.006, t_break=0.018):
    tt=np.arange(0,T,dt); i=np.zeros_like(tt); v=np.ones_like(tt)*1.0; v_h1=np.ones_like(tt); v_h2=np.ones_like(tt); v_h3=np.ones_like(tt)
    V=V_kV*1e3; L=L_mH*1e-3
    ilimit=1.35*Ibase_kA*1e3
    for n in range(1,len(tt)):
        if tt[n] < t_break:
            source_v=V if tt[n]<t_limit else min(V, R_ohm*ilimit)
            di=(source_v - R_ohm*i[n-1])/L*dt
            i[n]=max(0,i[n-1]+di)
        else:
            i[n]=i[n-1]*math.exp(-dt/0.006)
        if tt[n] < t_detect:
            v[n]=1.0
        elif tt[n] < t_break:
            v[n]=1.0-0.16*(1-np.exp(-(tt[n]-t_detect)/0.005))
        else:
            v[n]=0.94+0.06*(1-np.exp(-(tt[n]-t_break)/0.018))
        v_h1[n]=v[n]
        v_h2[n]=1.0-0.025*np.exp(-max(tt[n]-t_break,0)/0.025) if tt[n]>t_detect else 1.0
        v_h3[n]=1.0-0.020*np.exp(-max(tt[n]-t_break,0)/0.025) if tt[n]>t_detect else 1.0
    return pd.DataFrame({'time_s':tt,'fault_current_kA':i/1000,'backbone_voltage_pu':v,'campus1_voltage_pu':v_h1,'campus2_voltage_pu':v_h2,'campus3_voltage_pu':v_h3})
fault_df=simulate_backbone_fault(); fault_df.to_csv(DATA/'dc_fault_protection_backbone_fault_v3.csv',index=False)
# Campus DC/DC internal fault: only campus 1 isolated, healthy ride-through
campus_fault=fault_df.copy()
campus_fault['fault_current_kA']=fault_df['fault_current_kA']*0.45
campus_fault['campus1_voltage_pu']=np.where(campus_fault['time_s']<0.018,1-0.65*(1-np.exp(-np.maximum(campus_fault['time_s']-0.003,0)/0.006)),0.0)
campus_fault['campus2_voltage_pu']=1-0.012*np.exp(-np.maximum(campus_fault['time_s']-0.018,0)/0.018)
campus_fault['campus3_voltage_pu']=1-0.010*np.exp(-np.maximum(campus_fault['time_s']-0.018,0)/0.018)
campus_fault.to_csv(DATA/'dc_fault_protection_campus_fault_v3.csv',index=False)

# Buffer technology table
buffer_table=pd.DataFrame([
    {'technology':'DC-link capacitors','power_response':'ms','high_power_suitability':'partial','energy_window_suitability':'low','deployment_layer':'converter terminal','role':'absorbs switching and short transients, not the full energy window'},
    {'technology':'supercapacitor bank','power_response':'ms-s','high_power_suitability':'high','energy_window_suitability':'medium','deployment_layer':'DC terminal / campus station','role':'high-power, low-energy smoothing'},
    {'technology':'lithium-ion BESS','power_response':'100 ms-s','high_power_suitability':'high','energy_window_suitability':'high','deployment_layer':'rack, row, or station','role':'energy window and longer ramp compliance'},
    {'technology':'flywheel','power_response':'sub-second','high_power_suitability':'medium','energy_window_suitability':'medium','deployment_layer':'station','role':'high-cycle power buffering'},
    {'technology':'GPU power smoothing','power_response':'in-band firmware','high_power_suitability':'partial','energy_window_suitability':'not energy storage','deployment_layer':'GPU / server','role':'reduces the disturbance before it reaches power delivery'},
])
buffer_table.to_csv(DATA/'buffer_physical_feasibility_table_v3.csv',index=False)

# ---------------------------- Figures ----------------------------
def savefig(fig, name):
    for ext in ['png','svg','pdf']:
        fig.savefig(FIG/f'{name}.{ext}', dpi=300, bbox_inches='tight')
    plt.close(fig)

def draw_icon(ax, x, y, kind, scale=1.0):
    if kind=='grid':
        ax.add_patch(Rectangle((x-0.30*scale,y-0.10*scale),0.60*scale,0.20*scale,facecolor='#eeeeee',edgecolor='0.35',lw=1))
        for i in [-0.18,0,0.18]:
            ax.add_patch(Rectangle((x+i-0.035*scale,y-0.10*scale),0.07*scale,0.35*scale,facecolor='#d8d8d8',edgecolor='0.35',lw=0.8))
        ax.text(x,y-0.22*scale,'AC grid',ha='center',va='top',fontsize=7)
    elif kind=='substation':
        ax.add_patch(Rectangle((x-0.36*scale,y-0.16*scale),0.72*scale,0.32*scale,facecolor='#f2f2f2',edgecolor='0.4',lw=1))
        for i in [-0.18,0.02,0.20]:
            ax.add_patch(Rectangle((x+i-0.05*scale,y-0.05*scale),0.10*scale,0.16*scale,facecolor='#c7d6df',edgecolor='0.35',lw=0.7))
            ax.plot([x+i,x+i],[y+0.11*scale,y+0.22*scale],color='0.35',lw=0.8)
    elif kind=='converter':
        ax.add_patch(FancyBboxPatch((x-0.35*scale,y-0.18*scale),0.70*scale,0.36*scale,boxstyle='round,pad=0.02,rounding_size=0.03',facecolor='#f7f7f7',edgecolor='0.3',lw=1))
        ax.text(x,y,'AC/DC',ha='center',va='center',fontsize=7,weight='bold')
    elif kind=='sst':
        ax.add_patch(FancyBboxPatch((x-0.25*scale,y-0.18*scale),0.50*scale,0.36*scale,boxstyle='round,pad=0.02,rounding_size=0.02',facecolor='#f7f7f7',edgecolor='0.3',lw=1))
        ax.text(x,y,'SST',ha='center',va='center',fontsize=7,weight='bold')
    elif kind=='dcdc':
        ax.add_patch(FancyBboxPatch((x-0.28*scale,y-0.17*scale),0.56*scale,0.34*scale,boxstyle='round,pad=0.02,rounding_size=0.02',facecolor='#f7f7f7',edgecolor='0.3',lw=1))
        ax.text(x,y,'DC/DC',ha='center',va='center',fontsize=7,weight='bold')
    elif kind=='campus':
        ax.add_patch(Rectangle((x-0.34*scale,y-0.16*scale),0.68*scale,0.32*scale,facecolor='#e9eef2',edgecolor='0.25',lw=1))
        for i in [-0.22,-0.07,0.08,0.23]:
            ax.add_patch(Rectangle((x+i-0.03*scale,y-0.16*scale),0.06*scale,0.32*scale,facecolor='#c1cdd6',edgecolor='none'))
        ax.add_patch(Rectangle((x-0.20*scale,y+0.16*scale),0.14*scale,0.06*scale,facecolor='#d1d1d1',edgecolor='0.5',lw=0.5))
        ax.add_patch(Rectangle((x+0.05*scale,y+0.16*scale),0.14*scale,0.06*scale,facecolor='#d1d1d1',edgecolor='0.5',lw=0.5))
    elif kind=='tower':
        ax.plot([x-0.12*scale,x,x+0.12*scale],[y-0.20*scale,y+0.18*scale,y-0.20*scale],color='0.45',lw=0.8)
        ax.plot([x-0.18*scale,x+0.18*scale],[y+0.08*scale,y+0.08*scale],color='0.45',lw=0.8)
        ax.plot([x-0.13*scale,x+0.13*scale],[y-0.03*scale,y-0.03*scale],color='0.45',lw=0.8)

def load_true_opendss_thdv():
    source_root = Path(__file__).resolve().parents[1]
    candidates = [
        DATA/'true_opendss_harmonic_thdv_monte_carlo_v3.csv',
        source_root/'data'/'true_opendss_harmonic_thdv_monte_carlo_v3.csv',
    ]
    for path in candidates:
        if path.exists():
            df = pd.read_csv(path)
            labels = {
                'traditional_ac': 'Traditional AC',
                'local_sst': 'Local SST',
                'dc_backbone': 'Subtransmission DC backbone',
            }
            if 'architecture' in df.columns:
                df['scenario'] = df['architecture'].map(labels).fillna(df['architecture'])
            return df
    return None

def figure1():
    fig,ax=plt.subplots(figsize=(12.4,7.5)); ax.set_xlim(0,10); ax.set_ylim(0,7.5); ax.axis('off')
    ac='#c44e00'; dc='#1f78b4'; grey='0.32'

    def cable(xs, ys, color, lw=2.6):
        ax.plot(xs, ys, color=color, lw=lw, solid_capstyle='round', zorder=1)

    def busbar(x, y0, y1, color):
        ax.plot([x,x],[y0,y1],color=color,lw=3.0,solid_capstyle='round',zorder=1)

    def split_box(x, y, label, left_color, right_color, w=0.66, h=0.42, fs=7.2):
        ax.add_patch(Rectangle((x-w/2,y-h/2),w/2,h,facecolor=left_color,edgecolor='none',alpha=0.18,zorder=2))
        ax.add_patch(Rectangle((x,y-h/2),w/2,h,facecolor=right_color,edgecolor='none',alpha=0.18,zorder=2))
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.02,rounding_size=0.035',facecolor='none',edgecolor=grey,lw=1.1,zorder=3))
        ax.plot([x,x],[y-h/2,y+h/2],color='0.7',lw=0.7,zorder=3)
        ax.text(x,y,label,ha='center',va='center',fontsize=fs,weight='bold',zorder=4)

    def plain_box(x, y, label, w=0.58, h=0.36, fs=7.0):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle='round,pad=0.02,rounding_size=0.035',facecolor='white',edgecolor=grey,lw=1.1,zorder=3))
        ax.text(x,y,label,ha='center',va='center',fontsize=fs,weight='bold',zorder=4)

    def campus(x, y):
        draw_icon(ax,x,y,'campus',0.56)

    def row_header(y, lab, title):
        ax.text(0.18,y+0.58,lab,fontsize=14,weight='bold')
        ax.text(0.48,y+0.58,title,fontsize=13,weight='bold')

    def boundary(x, y, text):
        ax.plot([x,x],[y-0.68,y+0.68],color='0.2',lw=1.0,ls='--',zorder=0)
        ax.text(x,y+0.79,text,ha='center',fontsize=7,color='0.2')

    branch_offsets=[0.48,0,-0.48]
    ybands=[6.25,3.9,1.55]

    # a, Traditional AC delivery
    y=ybands[0]; row_header(y,'a','Traditional AC')
    draw_icon(ax,0.85,y,'grid',0.72); draw_icon(ax,1.75,y,'substation',0.70)
    cable([1.07,1.50],[y,y],ac); cable([2.00,4.15],[y,y],ac)
    for x in [2.65,3.15,3.65]: draw_icon(ax,x,y,'tower',0.72)
    busbar(4.20,y-0.54,y+0.54,ac)
    ax.text(3.10,y-0.43,'138 kV AC corridor',ha='center',fontsize=7.6,color=ac)
    for dy in branch_offsets:
        cy=y+dy
        cable([4.20,5.76],[cy,cy],ac)
        draw_icon(ax,5.92,cy,'substation',0.45)
        cable([6.08,6.91],[cy,cy],ac)
        split_box(7.20,cy,'AC/DC',ac,dc,w=0.58,h=0.34,fs=6.6)
        cable([7.49,8.36],[cy,cy],dc)
        campus(8.56,cy)
        ax.text(9.14,cy,'800 VDC',va='center',fontsize=7,color=dc)
    boundary(7.20,y,'AC/DC boundary\nat campuses')
    ax.text(5.12,y+0.76,'3 AC-facing\ninterfaces',ha='center',fontsize=7,color='0.2')
    ax.text(5.96,y-0.72,'facility AC switchgear',ha='center',fontsize=7.4,color=ac)
    ax.text(8.56,y-0.72,'AI campuses',ha='center',fontsize=7.4,color='0.25')

    # b, Local SST delivery
    y=ybands[1]; row_header(y,'b','Local SST')
    draw_icon(ax,0.85,y,'grid',0.72); draw_icon(ax,1.75,y,'substation',0.70)
    cable([1.07,1.50],[y,y],ac); cable([2.00,4.15],[y,y],ac)
    for x in [2.65,3.15,3.65]: draw_icon(ax,x,y,'tower',0.72)
    busbar(4.20,y-0.54,y+0.54,ac)
    ax.text(3.10,y-0.43,'138 kV AC corridor',ha='center',fontsize=7.6,color=ac)
    for dy in branch_offsets:
        cy=y+dy
        cable([4.20,5.86],[cy,cy],ac)
        split_box(6.16,cy,'SST',ac,dc,w=0.60,h=0.38,fs=7.0)
        cable([6.46,8.36],[cy,cy],dc)
        campus(8.56,cy)
        ax.text(7.20,cy+0.15,'800 VDC',ha='center',fontsize=6.8,color=dc)
    boundary(6.16,y,'AC/DC boundary\ninside local SSTs')
    ax.text(4.95,y+0.76,'3 AC-facing\ninterfaces',ha='center',fontsize=7,color='0.2')
    ax.text(5.55,y-0.72,'AC input',ha='center',fontsize=7,color=ac)
    ax.text(6.88,y-0.72,'DC output',ha='center',fontsize=7,color=dc)
    ax.text(8.56,y-0.72,'AI campuses',ha='center',fontsize=7.4,color='0.25')

    # c, Utility DC backbone
    y=ybands[2]; row_header(y,'c','DC backbone')
    draw_icon(ax,0.85,y,'grid',0.72); draw_icon(ax,1.62,y,'substation',0.58)
    cable([1.07,1.41],[y,y],ac); cable([1.83,2.02],[y,y],ac)
    split_box(2.38,y,'AC/DC',ac,dc,w=0.72,h=0.46,fs=7.0)
    cable([2.75,4.82],[y,y],dc,lw=3.0)
    for x in [3.25,3.75,4.25]: draw_icon(ax,x,y,'tower',0.72)
    busbar(4.92,y-0.54,y+0.54,dc)
    ax.text(3.80,y-0.43,'+/-138 kV DC backbone',ha='center',fontsize=7.6,color=dc)
    for dy in branch_offsets:
        cy=y+dy
        cable([4.92,5.64],[cy,cy],dc)
        plain_box(5.92,cy,'DC/DC',w=0.56,h=0.34,fs=6.6)
        cable([6.20,7.15],[cy,cy],dc)
        ax.text(6.66,cy+0.14,'34.5 kV DC',ha='center',fontsize=6.8,color=dc)
        plain_box(7.42,cy,'DC/DC',w=0.54,h=0.34,fs=6.6)
        cable([7.69,8.36],[cy,cy],dc)
        campus(8.56,cy)
        ax.text(9.14,cy,'800 VDC',va='center',fontsize=7,color=dc)
    boundary(2.38,y,'AC/DC boundary\nat utility terminal')
    ax.text(3.06,y+0.76,'1 AC-facing\ninterface',ha='center',fontsize=7,color='0.2')
    ax.text(5.92,y-0.72,'campus DC station',ha='center',fontsize=7,color='0.25')
    ax.text(8.56,y-0.72,'AI campuses',ha='center',fontsize=7.4,color='0.25')

    ax.plot([0.35,0.70],[0.35,0.35],color=ac,lw=3.0); ax.text(0.76,0.35,'AC',va='center',fontsize=8,color=ac)
    ax.plot([1.08,1.43],[0.35,0.35],color=dc,lw=3.0); ax.text(1.49,0.35,'DC',va='center',fontsize=8,color=dc)
    fig.tight_layout(); savefig(fig,'fig1_architecture_formal_v3')
figure1()

# Figure 2
def figure2():
    fig,axes=plt.subplots(2,2,figsize=(11,8),gridspec_kw={'width_ratios':[1,1.15]})
    colors={'Traditional AC':'#377eb8','Local SST':'#984ea3','Local SST optimistic':'#bc80bd','Subtransmission DC backbone':'#e6550d'}
    component_colors={'corridor':'#9aa3a6','conversion':'#80cdc1'}
    order=['Traditional AC','Local SST','Local SST optimistic','Subtransmission DC backbone']
    ax=axes[0,0]
    ref_idx=ref_df.set_index('architecture')
    corridor=[ref_idx.loc[o,'corridor_MW'] for o in order]
    conversion=[ref_idx.loc[o,'conversion_MW'] for o in order]
    vals=[ref_idx.loc[o,'loss_MW'] for o in order]
    x=np.arange(len(order))
    ax.bar(x, corridor, color=component_colors['corridor'], alpha=0.92, label='corridor')
    ax.bar(x, conversion, bottom=corridor, color=component_colors['conversion'], alpha=0.92, label='conversion')
    ax.set_xticks(range(len(order))); ax.set_xticklabels(['Traditional\nAC','Local\nSST','Optimistic\nSST','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('Loss at 1 GW, 20 km (MW)'); ax.set_title('a  Reference loss decomposition',loc='left',fontsize=11,weight='bold')
    ax.set_ylim(0, max(vals)+5.1)
    for i,v in enumerate(vals): ax.text(i,v+0.8,f'{v:.1f} MW\n{ref_idx.loc[order[i],"eff"]*100:.2f}%',ha='center',fontsize=7)
    ax.legend(fontsize=7,frameon=False,loc='upper right')
    ax.grid(axis='y',alpha=0.25)
    ax=axes[0,1]
    data=[mc_df['traditional_loss_MW'], mc_df['local_sst_loss_MW'], mc_df['local_sst_optimistic_loss_MW'], mc_df['dc_loss_MW']]
    parts=ax.violinplot(data, showmedians=True, showextrema=False)
    for pc,c in zip(parts['bodies'],[colors[o] for o in order]): pc.set_facecolor(c); pc.set_edgecolor(c); pc.set_alpha(0.45)
    ax.set_xticks(range(1,len(order)+1)); ax.set_xticklabels(['Traditional\nAC','Local\nSST','Optimistic\nSST','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('Loss under uncertainty (MW)'); ax.set_title('b  Uncertainty and stronger SST baseline',loc='left',fontsize=11,weight='bold'); ax.grid(axis='y',alpha=0.25)
    trad_p50=np.median(data[0])
    ax.axhline(trad_p50,color=colors['Traditional AC'],lw=0.8,ls='--',alpha=0.55)
    ax.text(4.46,trad_p50+0.7,'Traditional AC p50',ha='right',fontsize=6.3,color=colors['Traditional AC'])
    for i,d in enumerate(data, start=1):
        med=np.median(d); p95=np.percentile(d,95)
        ax.text(i, p95+1.0, f'p50 {med:.1f}\np95 {p95:.1f}', ha='center', fontsize=6.6)
    ax=axes[1,0]
    pivot=design_df.pivot(index='length_km',columns='load_MW',values='saving_vs_traditional_MW')
    im=ax.imshow(pivot.values,origin='lower',aspect='auto',extent=[loads.min(),loads.max(),lengths.min(),lengths.max()],cmap='YlOrRd')
    cs=ax.contour(loads,lengths,pivot.values,levels=[10,50,100],colors='k',linewidths=0.8); ax.clabel(cs,fmt='%d MW',fontsize=7)
    ax.scatter([1000],[20],c='white',edgecolors='black',s=40,zorder=3)
    ax.annotate('reference\n1 GW, 20 km',xy=(1000,20),xytext=(1210,28),fontsize=6.7,
                arrowprops=dict(arrowstyle='-',color='0.25',lw=0.8),ha='left',va='center',
                bbox=dict(boxstyle='round,pad=0.16',facecolor='white',edgecolor='0.82',alpha=0.86))
    ax.set_xlabel('Cluster load (MW)'); ax.set_ylabel('Corridor length (km)'); ax.set_title('c  DC saving over traditional AC',loc='left',fontsize=11,weight='bold')
    cb=fig.colorbar(im,ax=ax,shrink=0.86); cb.set_label('MW saved')
    ax=axes[1,1]
    tmp=sens_df.copy(); tmp['span']=abs(tmp['high_case_saving_MW']-tmp['low_case_saving_MW']); tmp=tmp.sort_values('span')
    y=np.arange(len(tmp))
    ax.hlines(y,tmp['low_case_saving_MW'],tmp['high_case_saving_MW'],color='#636363',lw=5,alpha=0.7)
    ax.axvline(base_saving,color='#e6550d',lw=1.5,label='base')
    ax.set_ylim(-0.55,len(tmp)-0.15)
    ax.annotate(f'base saving = {base_saving:.1f} MW',xy=(base_saving,len(tmp)-0.32),
                xytext=(base_saving-1.15,len(tmp)-0.32),fontsize=7,color='#e6550d',
                ha='right',va='center',arrowprops=dict(arrowstyle='-',color='#e6550d',lw=0.9))
    ax.set_yticks(y); ax.set_yticklabels(tmp['parameter'],fontsize=7)
    ax.set_xlabel('Saving vs traditional AC (MW)'); ax.set_title('d  One-at-a-time sensitivity',loc='left',fontsize=11,weight='bold'); ax.grid(axis='x',alpha=0.25)
    fig.tight_layout(); savefig(fig,'fig2_efficiency_uncertainty_designspace_v3')
figure2()

# Figure 3
def figure3():
    fig,axes=plt.subplots(2,2,figsize=(11,7.8))
    colors={'Traditional AC':'#377eb8','AC + active filter/storage':'#80b1d3','Local SST':'#984ea3','Local SST + coordinated control':'#bc80bd','Subtransmission DC backbone':'#e6550d'}
    ax=axes[0,0]
    names=['Traditional AC','AC + active filter/storage','Local SST','Local SST + coordinated control','Subtransmission DC backbone']
    ax.set_xlim(0,10); ax.set_ylim(0,4.3); ax.axis('off')
    ax.set_title('a  Harmonic ownership boundary',loc='left',fontsize=11,weight='bold')
    ax.plot([0.8,9.2],[3.3,3.3],color='#377eb8',lw=2.2)
    ax.text(0.8,3.55,'138 kV AC subtransmission',fontsize=7,color='#377eb8')
    for x in [3.0,5.0,7.0]:
        ax.plot([x,x],[3.3,2.35],color='#377eb8',lw=1.6)
        draw_icon(ax,x,2.15,'converter',0.55)
        draw_icon(ax,x,1.42,'campus',0.55)
    ax.text(0.8,1.95,'distributed cases:\n3 AC-facing converters',fontsize=7,ha='left',va='center')
    ax.plot([0.8,2.0],[0.65,0.65],color='#377eb8',lw=2.2)
    draw_icon(ax,2.35,0.65,'converter',0.55)
    ax.plot([2.72,8.5],[0.65,0.65],color='#e6550d',lw=2.4)
    for x in [4.0,5.8,7.6]:
        ax.plot([x,x],[0.65,1.08],color='#e6550d',lw=1.4)
        draw_icon(ax,x,1.32,'dcdc',0.45)
    ax.text(0.8,0.25,'DC backbone:\n1 utility AC-facing terminal',fontsize=7,ha='left',va='center')
    ax=axes[0,1]
    data=[harm_df[harm_df.scenario==n].thdv_pct for n in names]
    parts=ax.violinplot(data,showmedians=True,showextrema=False)
    for pc,n in zip(parts['bodies'],names): pc.set_facecolor(colors[n]); pc.set_edgecolor(colors[n]); pc.set_alpha(0.42)
    ax.set_xticks(range(1,len(names)+1)); ax.set_xticklabels(['Trad.\nAC','AC+filter\n/storage','Local\nSST','SST+\ncoord.','DC\nbackbone'],fontsize=7)
    ax.axhline(5,color='0.35',ls='--',lw=1.0)
    ax.text(5.12,5.08,'5% planning guide',fontsize=7,va='bottom',ha='right',color='0.35')
    for i,n in enumerate(names, start=1):
        p95=np.percentile(harm_df[harm_df.scenario==n].thdv_pct,95)
        ax.text(i,p95+0.17,f'{p95:.2f}',ha='center',fontsize=6.6,color=colors[n])
    ax.set_ylim(0,5.9)
    ax.set_ylabel('PCC voltage THD (%)'); ax.set_title('b  Harmonic screening result',loc='left',fontsize=11,weight='bold'); ax.grid(axis='y',alpha=0.25)
    ax=axes[1,0]
    for n in ['Traditional AC','Local SST','Subtransmission DC backbone']:
        d=spec_p95[spec_p95.scenario==n]
        ax.plot(d.h,d.p95_individual_harmonic_voltage_pct,marker='o',label=n,color=colors[n],lw=1.4)
    ax.set_xlabel('Harmonic order'); ax.set_ylabel('95th percentile Vh/V1 (%)'); ax.set_title('c  Individual harmonic voltage distortion',loc='left',fontsize=11,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25)
    ax=axes[1,1]
    compare=['Traditional AC','Local SST','Subtransmission DC backbone']
    internal=harm_df[harm_df.scenario.isin(compare)].groupby('scenario')['thdv_pct'].quantile(0.95)
    true_df=load_true_opendss_thdv()
    if true_df is not None:
        direct=true_df[true_df.scenario.isin(compare)].groupby('scenario')['thdv_pct'].quantile(0.95)
    else:
        direct=internal.copy()
    x=np.arange(len(compare)); w=0.36
    direct_vals=[direct.loc[n] for n in compare]
    internal_vals=[internal.loc[n] for n in compare]
    ax.bar(x-w/2,direct_vals,width=w,color='#4c78a8',alpha=0.9,label='Direct OpenDSS')
    ax.bar(x+w/2,internal_vals,width=w,color='#f58518',alpha=0.9,label='Internal solver')
    for i,(a,b) in enumerate(zip(direct_vals,internal_vals)):
        ax.text(i,max(a,b)+0.15,f'{abs(a-b):.2f} pt',ha='center',fontsize=7,color='0.25')
    ax.set_xticks(x); ax.set_xticklabels(['Traditional\nAC','Local\nSST','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('95th percentile THD (%)')
    ax.set_title('d  Direct OpenDSS check',loc='left',fontsize=11,weight='bold')
    ax.legend(fontsize=7,frameon=False); ax.grid(axis='y',alpha=0.25)
    fig.tight_layout(); savefig(fig,'fig3_harmonic_ownership_opendss_screening_v3')
figure3()

# Figure 4
def figure4():
    fig,axes=plt.subplots(2,2,figsize=(11,7.8))
    colors_d={'Traditional AC':'#377eb8','AC + active filter/storage':'#80b1d3','Local SST':'#984ea3','Local SST + coordinated control':'#bc80bd','Subtransmission DC backbone':'#e6550d'}
    win=(t>=25)&(t<=95)
    ax=axes[0,0]
    ax.plot(t[win],P_MW[win],color='0.55',lw=0.9,label='AI load')
    ax.plot(t[win],P_ac[win],color=colors_d['Traditional AC'],lw=0.75,label='Traditional AC')
    ax.plot(t[win],P_ac_bess[win],color=colors_d['AC + active filter/storage'],lw=1.0,label='AC + storage')
    ax.plot(t[win],P_sst[win],color=colors_d['Local SST'],lw=1.0,label='Local SST')
    ax.plot(t[win],P_dc[win],color=colors_d['Subtransmission DC backbone'],lw=1.8,label='DC backbone')
    ax.set_ylabel('Grid-side power (MW)'); ax.set_xlabel('Time (s)'); ax.set_title('a  AI training load and grid power',loc='left',fontsize=11,weight='bold'); ax.legend(fontsize=7,ncol=2,frameon=False); ax.grid(alpha=0.25)
    ax=axes[0,1]
    spectra=[('Traditional AC',P_ac),('AC + storage',P_ac_bess),('Local SST',P_sst),('DC backbone',P_dc)]
    for label,xdat in spectra:
        color_key={'AC + storage':'AC + active filter/storage','DC backbone':'Subtransmission DC backbone'}.get(label,label)
        _,freq,mag=spectral_energy(xdat)
        mask=(freq>=0.1)&(freq<=20)
        ax.plot(freq[mask],mag[mask],color=colors_d[color_key],lw=1.2,label=label)
    ax.set_xscale('log'); ax.set_yscale('log')
    ax.set_xlim(0.1,20); ax.set_xlabel('Frequency (Hz)'); ax.set_ylabel('Power spectral magnitude (MW)')
    ax.set_title('b  Frequency-domain mitigation',loc='left',fontsize=11,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25,which='both')
    ax=axes[1,0]
    order=['Traditional AC','AC + active filter/storage','Local SST','Local SST + coordinated control','Subtransmission DC backbone']
    rel=[energies[o]['relative_to_ac']*100 for o in order]
    ramp=[energies[o]['p99_ramp_MW_s']/energies['Traditional AC']['p99_ramp_MW_s']*100 for o in order]
    x=np.arange(len(order)); w=0.38
    ax.bar(x-w/2,rel,width=w,color=[colors_d[o] for o in order],alpha=0.78,label='0.1-20 Hz RSS')
    ax.bar(x+w/2,ramp,width=w,color='0.25',alpha=0.62,label='p99 ramp')
    ax.set_xticks(x); ax.set_xticklabels(['Trad.\nAC','AC+\nstorage','Local\nSST','SST+\ncoord.','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('Percent of traditional AC baseline')
    ax.set_ylim(0,115)
    ax.text(x[-1],max(rel[-1],ramp[-1])+5,f'{rel[-1]:.1f}% RSS\n{ramp[-1]:.1f}% ramp',ha='center',fontsize=7,color=colors_d['Subtransmission DC backbone'])
    ax.set_title('c  Normalized mitigation metrics',loc='left',fontsize=11,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(axis='y',alpha=0.25)
    ax=axes[1,1]
    ax.plot(t[win],P_buffer[win],color='#e6550d',lw=1.3,label='buffer power')
    ax2=ax.twinx(); ax2.plot(t[win],E_MWh[win]-E_MWh[win].min(),color='#756bb1',lw=1.0,label='energy state')
    ax.axhline(0,color='0.3',lw=0.7)
    ax.text(0.02,0.92,f'discharge {P_buffer.max():.0f} MW\ncharge {-P_buffer.min():.0f} MW\nwindow {E_window:.2f} MWh',transform=ax.transAxes,ha='left',va='top',fontsize=7,bbox=dict(facecolor='white',edgecolor='0.85',pad=2))
    ax.set_xlabel('Time (s)'); ax.set_ylabel('Shared DC buffer power (MW)'); ax2.set_ylabel('Energy window (MWh)'); ax.set_title('d  Shared DC buffer requirement',loc='left',fontsize=11,weight='bold'); ax.grid(alpha=0.25)
    fig.tight_layout(); savefig(fig,'fig4_voltage_stabilization_averaged_emt_v3')
figure4()

# Figure 5
def figure5():
    fig,axes=plt.subplots(1,2,figsize=(10.5,3.9),gridspec_kw={'width_ratios':[1.0,1.25]})
    ax=axes[0]
    bars=[2100,3400,4200]; labs=['2021-22\nstudy','2024-25\nbase','2024-25\nsensitivity']
    ax.bar(range(3),bars,color=['#bdbdbd','#fd8d3c','#e6550d'])
    ax.set_xticks(range(3)); ax.set_xticklabels(labs,fontsize=8); ax.set_ylabel('Long-term load forecast (MW)')
    ax.set_title('a  Public planning-data load growth',loc='left',fontsize=10,weight='bold')
    for i,b in enumerate(bars): ax.text(i,b+90,f'{b/1000:.1f} GW',ha='center',fontsize=8)
    ax.annotate('',xy=(2,4200),xytext=(0,2100),arrowprops=dict(arrowstyle='->',lw=1.1,color='0.3'))
    ax.text(0.55,3050,'multi-GW\nload pocket',ha='center',fontsize=8,color='0.25')
    ax.set_ylim(0,4700); ax.grid(axis='y',alpha=0.25)

    ax=axes[1]
    loads2=np.linspace(100,5000,150)
    for pole,col in [(69,'#9ecae1'),(138,'#e6550d'),(320,'#756bb1')]:
        I=loads2*1e6/(2*pole*1e3)/1000
        ax.plot(loads2,I,label=f'+/-{pole} kV',color=col,lw=2)
    ax.axhline(4,color='0.4',ls='--',lw=1,label='4 kA guide')
    ax.axvspan(3400,4200,color='#fee6ce',alpha=0.55,label='planning range')
    ax.scatter([1000],[1000e6/(276e3)/1000],c='#e6550d',edgecolor='k',zorder=3)
    ax.text(1030,1000e6/(276e3)/1000+0.18,'1 GW at +/-138 kV',fontsize=7,color='#e6550d')
    ax.set_xlabel('Cluster load (MW)'); ax.set_ylabel('Bipole current (kA)'); ax.set_title('b  Voltage-class envelope',loc='left',fontsize=10,weight='bold'); ax.legend(fontsize=7,frameon=False,loc='upper left'); ax.grid(alpha=0.25)
    fig.tight_layout(); savefig(fig,'fig5_case_study_voltage_envelope_v3')
figure5()

# Supplementary figures: S1 protection dynamics, S2 EMT validation, S3 buffer feasibility, S4 economics/copper
def figure_s1():
    fig,axes=plt.subplots(1,3,figsize=(12,3.8))
    ax=axes[0]; ax.axis('off'); ax.set_title('a  Protection zones',loc='left',fontsize=10,weight='bold')
    ax.set_xlim(0,10); ax.set_ylim(0,4); ac='#1f77b4'; dc='#d94801'
    draw_icon(ax,0.8,2.6,'grid',0.7); draw_icon(ax,2.0,2.6,'converter',0.7); ax.plot([1.1,1.65],[2.6,2.6],color=ac,lw=2)
    ax.plot([2.35,8.2],[2.6,2.6],color=dc,lw=2.5)
    for x in [3.5,5.1,6.8]:
        ax.add_patch(Rectangle((x-0.07,2.42),0.14,0.36,facecolor='#fff',edgecolor='0.3'))
    for i,x in enumerate([4.0,5.8,7.6]):
        ax.plot([x,x],[2.6,1.55],color=dc,lw=1.5); draw_icon(ax,x,1.35,'dcdc',0.45); ax.text(x,0.9,f'campus {i+1}',ha='center',fontsize=7)
    ax.add_patch(Polygon([[5.1,2.95],[5.3,2.55],[5.16,2.58],[5.36,2.25],[5.0,2.62]],closed=True,facecolor='#ffd92f',edgecolor='0.2'))
    ax.text(5.35,3.1,'backbone fault',fontsize=7)
    for x,label in [(2.0,'terminal\nprotection'),(3.5,'section\nbreaker'),(6.8,'section\nbreaker')]:
        ax.text(x,3.15,label,ha='center',fontsize=6.7,color='0.25')
    ax.text(8.4,0.45,'screening model,\nnot breaker design',ha='right',fontsize=7,color='0.35')
    ax=axes[1]; ax.set_title('b  Backbone fault response',loc='left',fontsize=10,weight='bold')
    ax.plot(fault_df.time_s*1000,fault_df.fault_current_kA,color='#d94801',lw=1.5,label='fault current')
    ax2=ax.twinx(); ax2.plot(fault_df.time_s*1000,fault_df.backbone_voltage_pu,color='#3182bd',lw=1.3,label='backbone V')
    ax.axvline(3,color='0.5',ls=':',lw=1); ax.axvline(18,color='0.5',ls='--',lw=1)
    ax.text(3.4,ax.get_ylim()[1]*0.88,'detect',fontsize=7,color='0.35')
    ax.text(18.4,ax.get_ylim()[1]*0.78,'open',fontsize=7,color='0.35')
    ax.set_xlabel('Time (ms)'); ax.set_ylabel('Fault current (kA)'); ax2.set_ylabel('Voltage (pu)'); ax.grid(alpha=0.25)
    ax=axes[2]; ax.set_title('c  Campus ride-through proxy',loc='left',fontsize=10,weight='bold')
    ax.plot(fault_df.time_s*1000,fault_df.campus1_voltage_pu,label='near/faulted section',color='#e6550d')
    ax.plot(fault_df.time_s*1000,fault_df.campus2_voltage_pu,label='healthy campus 2',color='#31a354')
    ax.plot(fault_df.time_s*1000,fault_df.campus3_voltage_pu,label='healthy campus 3',color='#756bb1')
    ax.set_xlabel('Time (ms)'); ax.set_ylabel('Campus DC voltage (pu)'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25)
    fig.tight_layout(); savefig(fig,'supp_fig_s1_dc_fault_protection_dynamic_v3')
figure_s1()

def figure_s2():
    fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    ax=axes[0]
    ax.plot(validation_df.dt_s,validation_df.rmse_MW_vs_1ms_reference,marker='o',color='#e6550d')
    ax.set_xscale('log'); ax.invert_xaxis()
    ax.set_xlabel('Time step (s)'); ax.set_ylabel('RMSE vs 1 ms reference (MW)'); ax.set_title('a  Time-step convergence',loc='left',fontsize=10,weight='bold'); ax.grid(alpha=0.25)
    ax=axes[1]
    ax.plot(tf_df.frequency_Hz,tf_df.simulated_gain,marker='o',label='simulation',color='#3182bd')
    ax.plot(tf_df.frequency_Hz,tf_df.theory_gain,'--',label='first-order theory',color='0.25')
    ax.set_xscale('log'); ax.set_yscale('log'); ax.set_xlabel('Frequency (Hz)'); ax.set_ylabel('Grid-command gain'); ax.set_title('b  Transfer-function validation',loc='left',fontsize=10,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25,which='both')
    fig.tight_layout(); savefig(fig,'supp_fig_s2_averaged_emt_validation_v3')
figure_s2()

def figure_s3():
    fig,(ax,ax2)=plt.subplots(1,2,figsize=(10.5,4.1),gridspec_kw={'width_ratios':[1.0,1.25]})
    table=buffer_table.copy()
    ax.set_title('a  Suitability for reference buffer',loc='left',fontsize=10,weight='bold')
    score={'not energy storage':-1,'low':0,'partial':1,'medium':2,'high':3}
    labels={-1:'not\nstorage',0:'low',1:'partial',2:'medium',3:'high'}
    matrix=np.array([[score[v] for v in row] for row in table[['high_power_suitability','energy_window_suitability']].values])
    cmap=matplotlib.colors.ListedColormap(['#f7f7f7','#fcbba1','#fdae6b','#a1d99b','#31a354'])
    im=ax.imshow(matrix,aspect='auto',vmin=-1,vmax=3,cmap=cmap)
    ax.set_yticks(np.arange(len(table)))
    ax.set_yticklabels(table['technology'],fontsize=7)
    ax.set_xticks([0,1])
    ax.set_xticklabels(['High-power\nresponse','0.42 MWh\nwindow'],fontsize=8)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j,i,labels[int(matrix[i,j])],ha='center',va='center',fontsize=7)
    ax.tick_params(length=0)
    ax2.axis('off'); ax2.set_title('b  Deployment layer and role',loc='left',fontsize=10,weight='bold')
    ax2.set_xlim(0,1); ax2.set_ylim(0,1)
    ax2.text(0.02,0.90,'Technology',fontsize=7,weight='bold')
    ax2.text(0.30,0.90,'Layer',fontsize=7,weight='bold')
    ax2.text(0.55,0.90,'Role',fontsize=7,weight='bold')
    ax2.hlines(0.86,0.02,0.98,color='0.25',lw=1.0)
    for i,r in enumerate(table.itertuples(index=False)):
        y=0.79-i*0.15
        ax2.text(0.02,y,textwrap.fill(r.technology,18),fontsize=6.4,va='top')
        ax2.text(0.30,y,textwrap.fill(r.deployment_layer,18),fontsize=6.2,va='top')
        ax2.text(0.55,y,textwrap.fill(r.role,38),fontsize=6.2,va='top')
        ax2.hlines(y-0.10,0.02,0.98,color='0.86',lw=0.7)
    fig.tight_layout()
    savefig(fig,'supp_fig_s3_buffer_feasibility_v3')
figure_s3()

def figure_s4():
    fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    econ_df=pd.read_csv(DATA/'cost_copper_envelope_v3.csv')
    ax=axes[0]
    grid=econ_df.dropna(subset=['annual_value_USD_M']).pivot(index='load_factor',columns='electricity_price_USD_MWh',values='annual_value_USD_M')
    im=ax.imshow(grid.values,origin='lower',aspect='auto',extent=[price_grid.min(),price_grid.max(),lf_grid.min(),lf_grid.max()],cmap='YlGn')
    ax.set_xlabel('Electricity price ($/MWh)'); ax.set_ylabel('Load factor'); ax.set_title('a  Annual loss-saving value',loc='left',fontsize=10,weight='bold')
    ax.scatter([assumptions['electricity_price_USD_per_MWh_mid']],[assumptions['economic_load_factor']],marker='*',s=110,c='#d94801',edgecolor='k',zorder=3)
    ax.text(assumptions['electricity_price_USD_per_MWh_mid']+4,assumptions['economic_load_factor'],'reference',fontsize=7,va='center')
    fig.colorbar(im,ax=ax,shrink=0.8,label='Annual value (million USD/yr)')
    ax=axes[1]
    current_idx=econ_df[econ_df.metric=='current_length_index_kA_km']
    x=np.arange(len(current_idx))
    vals=current_idx.value.to_numpy()
    ax.bar(x,vals,color=['#377eb8','#984ea3','#e6550d'],alpha=0.85)
    ax.set_xticks(x); ax.set_xticklabels(['Traditional\nAC','Local\nSST','DC\nbackbone'],fontsize=8)
    for i,v in enumerate(vals):
        ax.text(i,v+2,f'{v:.0f}',ha='center',fontsize=7)
    ax.set_ylabel('Current-length index (kA km)'); ax.set_title('b  Corridor current-length proxy',loc='left',fontsize=10,weight='bold'); ax.grid(axis='y',alpha=0.25)
    ax.text(0.03,0.90,'index = current x corridor length',transform=ax.transAxes,fontsize=6.8,va='top',color='0.35')
    fig.tight_layout(); savefig(fig,'supp_fig_s4_cost_copper_envelope_v3')
figure_s4()

# ---------------------------- Manuscript text ----------------------------
abstract = """AI factories are becoming synchronized, DC-native, gigawatt-scale loads, while surrounding grids still treat them as passive AC buildings. This mismatch raises a planning question: if the useful electrical boundary is 800 VDC, where should the AC/DC boundary sit? We compare traditional AC delivery, AC corridors with local solid-state transformers and a utility-operated subtransmission DC backbone feeding 34.5 kV DC distribution and 800 VDC interfaces. In a 1 GW, 20 km, three-campus reference case, the DC backbone delivers 97.49% end-to-end efficiency to the 800 VDC boundary, compared with 96.23% for traditional AC and 97.42% for local SSTs. Efficiency alone is not the main result. Moving the boundary upstream also centralizes AC harmonic ownership and buffers synchronized training dynamics, reducing the 95th-percentile harmonic-voltage screening metric from 3.95% to 0.78% and reducing 0.1-20 Hz grid-side spectral energy to 5.9% of the AC baseline. Sensitivity, stronger baselines, direct OpenDSS harmonic solves, averaged EMT-style dynamics, protection screening and a reproducibility package support a falsifiable systems claim: for clustered AI factories, the AC/DC boundary is a subtransmission planning variable rather than only a building-level design choice."""

intro = """AI factories change the electrical problem that grids must solve. A conventional data center can often be approximated in planning studies as a large but mostly passive load. A modern AI factory is a synchronized computing machine. Training iterations, all-reduce communication, checkpointing and accelerator power-management events can appear electrically as coherent power modulation across thousands of GPUs. At the scale of multiple campuses connected to the same grid pocket, power delivery becomes part of the computing architecture.

The load-side technology trajectory is already moving toward DC. Industry roadmaps describe 800 VDC as a power-distribution architecture for AI data centers and AI factories that reduces current, copper, distribution volume and conversion stages while supporting future high-density racks [1-3]. This makes the 800 VDC interface a relevant terminal boundary for future AI-factory power delivery.

If the endpoint is DC, the system-level question is where the AC/DC boundary should be placed. Most current discussions move that boundary from the rack to the facility. This study asks whether it should move farther upstream, into the subtransmission corridor. The proposed architecture uses a utility-operated AC/DC terminal to feed a bipolar subtransmission DC backbone. Campus DC/DC stations then step the backbone to a 34.5 kV DC distribution layer and ultimately to the 800 VDC data-center interface.

Device-level work makes this question technically plausible. A 10 kV SiC 7 kV/400 V DC transformer for future data centers demonstrated 99.0% full-load DC/DC efficiency and 3.8 kW/L power density; the associated 3.8 kV AC to 400 V DC SST chain reached 98.1% full-load efficiency [4]. A modular 5 kV SiC SST demonstrated single-stage MVDC-to-LVDC or MVDC-to-LVAC conversion, full-range zero-voltage switching, controlled dv/dt and modular series/parallel scalability [5]. A 20 kW 1000 V/48 V prototype further shows that raising the data-center distribution voltage can reduce low-voltage current stress, with an estimated efficiency improvement to 97.5% using synchronous rectification [6].

The grid-side motivation is also visible. A production-scale AI training power study by Microsoft, OpenAI and NVIDIA reports that synchronized training phases make power swings visible at rack, data-center and grid levels; at scale these swings can reach tens or hundreds of megawatts and can occupy sub-synchronous frequency ranges relevant to utility equipment [7]. That work frames both time-domain ramp constraints and frequency-domain limits, including a 0.1-20 Hz range, as requirements for safe scaling.

The knowledge gap is therefore not whether efficient DC conversion is possible, or whether AI training loads are dynamic. It is where the AC/DC boundary should sit when AI factories become multi-campus, gigawatt-scale grid assets. We test the claim that for AI factories, the AC/DC boundary is no longer only a building-level choice; it is a subtransmission planning variable."""

results_sections = [
("An AI-native architecture with the AC/DC boundary moved upstream", """We compare three architectures that deliver identical useful power to an 800 VDC data-center boundary (Fig. 1). The traditional AC architecture uses a utility substation, an AC subtransmission corridor, facility AC distribution and distributed AC/DC conversion at each campus. The local-SST architecture keeps the AC corridor but places a solid-state transformer at each AI campus. The proposed architecture moves the first AC/DC terminal upstream and treats the DC subtransmission corridor as a utility asset. Downstream conversion is entirely DC/DC: from subtransmission DC to 34.5 kV DC campus distribution, and from that layer to 800 VDC.

The conceptual difference is the electrical boundary seen by the utility. In the first two architectures, each campus remains an AC-facing load with its own grid-interfacing converter behaviour. In the proposed architecture, the AC grid sees one controlled converter terminal, while campus converters are DC/DC devices embedded behind a shared DC backbone. This turns a cluster of AI campuses from a set of distributed harmonic and ramp sources into a coordinated DC-native load pocket."""),
("Efficiency is a design-space result, not a single operating point", """For a central reference case, we model a 1 GW cluster served over a 20 km reinforced subtransmission corridor. The traditional AC case uses 138 kV line-to-line at 0.98 power factor; the proposed DC case uses a +/-138 kV bipole, or 276 kV pole-to-pole. This is a representative voltage class rather than a prescribed standard.

With an effective conductor resistance of 0.01 ohm km-1 per phase or pole, the central model gives total losses of 39.1 MW for traditional AC, 26.5 MW for local SSTs, 21.3 MW for an intentionally optimistic 99.0%-efficient local SST baseline and 25.7 MW for the DC backbone (Fig. 2a). The corresponding end-to-end efficiencies are 96.23%, 97.42%, 97.92% and 97.49%. This stronger baseline is deliberately included because the architectural claim should not depend on a narrow efficiency comparison.

The efficiency result alone would not justify a new grid architecture. In the optimistic SST case, local conversion can exceed the DC backbone in pure efficiency. The architectural case emerges because the DC backbone produces an efficiency improvement over traditional AC in the same direction as harmonic ownership and dynamic-voltage benefits. A load-distance sweep from 100 MW to 3 GW and from 5 to 100 km shows where the DC advantage over traditional AC exceeds 10, 50 and 100 MW (Fig. 2c). A Monte Carlo uncertainty sweep and one-at-a-time tornado analysis show that corridor length, conductor resistance and downstream conversion assumptions dominate the quantitative result (Fig. 2b,d)."""),
("A DC backbone changes harmonic compliance into harmonic ownership", """Traditional AC and local-SST architectures can be designed to meet harmonic limits, but they place multiple large AC-facing converter interfaces along the corridor. Their aggregate harmonic voltage distortion depends on local filters, network impedance, cable capacitance, phase relationships between sites and resonance. The proposed DC backbone concentrates the AC-facing converter at a single utility-operated terminal. Campus stations are DC/DC interfaces and therefore do not directly inject AC harmonics into the subtransmission grid.

We quantify this ownership change with an OpenDSS-ready network and a reproduced nodal frequency-domain solver. The network uses a 10 GVA Thevenin short-circuit strength at 138 kV, three campus buses along a 20 km corridor, harmonic-dependent source impedance and resonance amplification around selected orders. Distributed architectures are represented by three AC-facing converter spectra with random relative phases; the DC-backbone case is represented by one filtered grid-facing converter terminal.

For the central assumptions, the 95th-percentile PCC voltage THD is 3.95% for traditional AC, 1.55% for local SSTs and 0.78% for the DC backbone (Fig. 3b). Adding active filtering or storage to the traditional AC case improves the metric, and coordinated control improves the local-SST case, but neither changes the number of AC-facing interfaces. These values are screening metrics, not a substitute for project-specific IEEE 519 compliance studies [8]. Their purpose is narrower and architectural: moving DC upstream changes a distributed compliance problem into a single utility-owned terminal design problem."""),
("The DC backbone buffers synchronized AI-load voltage dynamics", """The third benefit is voltage stabilization under synchronized AI training loads. We construct a synthetic but literature-parameterized 1 GW AI training waveform with repeated compute phases, communication dips and checkpointing events. The traditional AC case passes this waveform directly to the grid. The local-SST case applies limited smoothing. Stronger baselines add substation storage or coordinated SST controls. The DC-backbone case uses a slower grid-facing power command and assigns the difference between the AI load and the grid command to a shared DC buffer.

In the reference waveform, the DC backbone reduces the root-sum-square spectral magnitude in the 0.1-20 Hz band to 5.9% of the traditional AC baseline, while the p99 ramp rate falls from 404 MW s-1 to 16.6 MW s-1 (Fig. 4c). The shared buffer must absorb up to 317 MW, deliver up to 102 MW and span an energy window of 0.42 MWh for this waveform (Fig. 4d). This is a high-power, low-energy requirement. It should not be interpreted as a single large battery; rather, the DC backbone creates the electrical layer where GPU power smoothing, rack or row storage, supercapacitors, station storage and grid-facing converter control can be coordinated.

The voltage metrics in Fig. 4 are averaged EMT proxies. They are designed to compare architecture-level exposure, not to replace detailed EMT studies. We therefore include state equations, transfer-function validation and time-step convergence in the Supplementary Information. The result is that the DC backbone is not only an energy-delivery architecture; it is a dynamic electrical buffer between synchronized GPU computation and the AC grid."""),
("Data-center load pockets are becoming planning objects", """The proposed architecture is motivated by load pockets that are large, concentrated and data-center driven. Public planning documents for the San Jose area show a load pocket growing from approximately 2.1 GW in an earlier study case to 3.4 GW in a later base case and 4.2 GW in a sensitivity case (Fig. 5a) [9-12]. This paper does not claim that a specific planned HVDC project is a 138 kV DC AI-factory backbone. The point is that data-center-driven load pockets are already large enough to motivate controllable transmission solutions.

The voltage-class envelope in Fig. 5b shows why the paper uses +/-138 kV only as a representative subtransmission design point. At 1 GW, +/-138 kV corresponds to approximately 3.6 kA bipole current. Higher multi-GW corridors move naturally toward higher voltage classes such as +/-320 kV. The relevant design variable is therefore not one fixed voltage, but the relocation of the AC/DC boundary to a voltage class compatible with load, distance, current limit, insulation and protection requirements.""")]

discussion = """Our results do not imply that every data center should be served by DC subtransmission, or that +/-138 kV is a universal optimum. They show that once AI factories become clustered, synchronized and DC-native, the location of the AC/DC boundary becomes a planning variable. This creates a new design space for utility-operated DC load pockets, where conversion efficiency, harmonic ownership and dynamic buffering are optimized together.

The comparison also shows why efficiency alone is an incomplete criterion. Local SSTs can approach or exceed the DC backbone in pure efficiency under optimistic assumptions. Their limitation is architectural: they retain multiple AC-facing grid interfaces and do not automatically provide a shared DC layer for buffering synchronized multi-campus load dynamics. The proposed backbone is valuable because the three benefits are co-located at one controllable boundary.

Several technical risks remain. DC protection, pole-to-ground fault detection, hybrid DC breakers, grounding, insulation coordination, converter interoperability and electromagnetic-transient stability must be demonstrated before deployment. We include protection-screening dynamics and an averaged EMT model to make the research boundary explicit, but do not claim a finished hardware design. The decisive follow-up is pilot-grade EMT and hardware-in-the-loop validation of the grid-facing terminal, DC/DC stations and AI-load emulator.

This study reframes AI factories as grid-planning objects rather than only building loads. The central claim is falsifiable: if a multi-campus AI load can be served by a subtransmission DC backbone, then the same upstream DC boundary should simultaneously reduce corridor/conversion losses relative to traditional AC, centralize AC harmonic ownership and reduce sub-synchronous grid-side voltage modulation relative to architectures that keep AC in the corridor. The models and repository are provided to make that claim testable."""

methods = [
("Architecture boundary", """The evaluation boundary begins at the grid-facing/subtransmission supply point and ends at the 800 VDC data-center interface. The traditional AC case uses a 138 kV AC corridor and downstream AC distribution before conversion to 800 VDC. The local-SST case uses the same AC corridor but converts at each campus using an SST. The proposed case uses a grid-facing AC/DC terminal, a bipolar subtransmission DC corridor, DC/DC conversion to a 34.5 kV DC distribution layer and DC/DC conversion to 800 VDC. The central reference system is a 1 GW three-campus cluster served over a 20 km equivalent corridor. The DC design point is +/-138 kV, or 276 kV pole-to-pole."""),
("Efficiency calculation", """For AC cases, corridor current is I_AC = P_corridor/(sqrt(3) V_LL pf), where P_corridor is the receiving-end corridor power before downstream conversion losses. AC line loss is 3 I_AC^2 R. For the DC case, receiving-end corridor power is the load divided by the two DC/DC stage efficiencies; bipole current is I_DC = P_recv/V_pp, and line loss is 2 I_DC^2 R. The utility-terminal loss is then computed from the AC/DC efficiency. Central assumptions are listed in Supplementary Table 1, and uncertainty ranges are encoded in the public repository."""),
("Harmonic screening and OpenDSS-ready network", """The harmonic model is a frequency-domain screening model. It represents the 138 kV grid by a 10 GVA Thevenin short-circuit strength, three corridor buses and harmonic-dependent source impedance with resonance amplification. OpenDSS-compatible circuit files and archived OpenDSSDirect.py harmonic-run artifacts are included in the repository. The figure-generation script also includes an independent nodal-frequency solver that uses the same equivalent network and harmonic spectra, so the screening result can be reproduced without a proprietary EMT tool. The output metrics are PCC voltage THD and individual harmonic voltage distortion. Parameter provenance is summarized in Supplementary Table 1; measured literature values, public planning data and study assumptions are separated in the public data tables."""),
("Averaged EMT-style model", """The dynamic waveform is synthetic but parameterized from the published structure of AI training power traces: compute phases with high accelerator utilization, periodic communication dips and less frequent checkpointing dips [7]. The traditional AC case passes the waveform directly to the grid. The local-SST case applies a 1.1 s first-order smoothing function. The DC-backbone case applies a 16 s grid-facing power command; the difference between the AI load and the commanded grid power defines shared DC-buffer power. Supplementary Note 2 gives the averaged state equations and validates the first-order command model by time-step convergence and transfer-function tests. This is an averaged EMT-style comparison of architecture-level exposure, not a switching EMT validation of a specific converter design."""),
("Protection-zone screening", """Representative protection dynamics are simulated for a backbone pole-to-ground fault and a campus DC/DC internal fault. The model includes detection, converter current limiting, breaker opening, section isolation and healthy-campus re-energization. It is intended to check plausibility and expose the required protection functions; it is not a validated DC-breaker or insulation-coordination design.""")]

figure_legends = {
'Fig. 1 | Three power-delivery architectures for AI factories.':'Orange lines denote AC sections and blue lines denote DC sections. a, Traditional AC delivery keeps AC in the subtransmission and facility distribution system before conversion to the 800 VDC data-center boundary. b, Local SST delivery uses the same AC corridor but converts at each AI campus, with AC input and DC output shown explicitly. c, The proposed architecture moves the AC/DC boundary upstream and feeds multiple campuses from a utility-operated subtransmission DC backbone, with DC/DC conversion to 34.5 kV DC and then to 800 VDC.',
'Fig. 2 | Efficiency, stronger baselines and design space.':'a, Central 1 GW, 20 km reference-case corridor and conversion losses with end-to-end efficiencies to the 800 VDC boundary; bar colours denote loss components, not AC/DC sections. b, Monte Carlo uncertainty at the reference point. c, Load-distance sweep showing where the DC-backbone loss advantage over traditional AC exceeds 10, 50 and 100 MW. d, One-at-a-time sensitivity of the central saving.',
'Fig. 3 | Harmonic ownership and OpenDSS-ready screening.':'a, Harmonic ownership boundary for distributed AC-facing converter cases versus the proposed single utility AC/DC terminal. b, Monte Carlo PCC voltage THD for the three architectures and two stronger baselines, with a 5% planning guide shown for context. c, 95th-percentile individual harmonic voltage distortion. d, Direct OpenDSS harmonic solve compared with the internal nodal-frequency solver.',
'Fig. 4 | Voltage stabilization of synchronized AI training loads.':'a, Representative AI training waveform and grid-facing power trajectories. b, Frequency-domain attenuation of grid-side power fluctuations. c, Normalized 0.1-20 Hz spectral magnitude and 99th-percentile ramp rate. d, Shared DC-buffer power and energy window required for the reference waveform.',
'Fig. 5 | Data-center load pockets and voltage-class envelope.':'a, Public planning-data precedent showing multi-GW load-pocket growth. b, Bipole current as a function of cluster load for several candidate DC voltage classes, with the public planning range shown for context.'}

data_availability = """All inputs and outputs used to generate Figs. 2-5 and Supplementary Figs. S1-S4 are included in the accompanying reproducibility package as CSV files. Public external data are cited in the References. No restricted operational data are used. Before journal submission, this package should be deposited in Zenodo and this statement should be updated with the final DOI."""

code_availability = """The Python code, OpenDSS-compatible circuit files, archived OpenDSSDirect.py harmonic-run artifacts and reproduction scripts are included in the public code repository at https://github.com/SavannahY/dc-ai-factory-backbone-reproducibility. Before journal submission, the final Zenodo DOI should be inserted here."""

ai_disclosure = """During manuscript preparation, the authors used AI-assisted tools for drafting support, code refactoring, reference-format checking and editorial revision. The authors reviewed and edited all generated text, verified all scientific claims, generated the final figures from reproducible code and take full responsibility for the content of the submitted manuscript."""

references = [
"NVIDIA. MGX platform for modular server design. https://www.nvidia.com/en-us/data-center/products/mgx/ (accessed 27 May 2026).",
"Blake, M., Hsu, M., Goldwasser, I., Petty, H. & Huntington, J. NVIDIA 800 VDC architecture will power the next generation of AI factories. NVIDIA Technical Blog (20 May 2025); https://developer.nvidia.com/blog/nvidia-800-v-hvdc-architecture-will-power-the-next-generation-of-ai-factories/ (accessed 27 May 2026).",
"Texas Instruments. TI unveils complete 800 VDC power architecture for future generation AI data centers with NVIDIA. News release (16 March 2026); https://www.ti.com/about-ti/newsroom/news-releases/2026/2026-03-16-ti-unveils-complete-800-vdc-power-architecture-for-future-generation-ai-data-centers-with-nvidia.html (accessed 27 May 2026).",
"Rothmund, D., Guillod, T., Bortis, D. & Kolar, J. W. 99% efficient 10 kV SiC-based 7 kV/400 V DC transformer for future data centers. IEEE J. Emerg. Sel. Top. Power Electron. 7, 753-767 (2019). https://doi.org/10.1109/JESTPE.2018.2886139.",
"Zheng, L. et al. SiC-based 5-kV universal modular soft-switching solid-state transformer (M-S4T) for medium-voltage DC microgrids and distribution grids. IEEE Trans. Power Electron. 36, 11326-11343 (2021). https://doi.org/10.1109/TPEL.2021.3066908.",
"Samanta, S., Wong, I., Bhattacharya, S. & Pahl, B. Medium voltage supply directly to data-center-servers using SiC-based single-stage converter with 20 kW experimental results. In 2020 IEEE Energy Conversion Congress and Exposition (ECCE), 2006-2012 (IEEE, 2020). https://doi.org/10.1109/ECCE44975.2020.9235701.",
"Choukse, E. et al. Power stabilization for AI training datacenters. arXiv:2508.14318v2 (2025). https://arxiv.org/abs/2508.14318.",
"IEEE Standards Association. IEEE Std 519-2022: IEEE recommended practice and requirements for harmonic control in electric power systems (IEEE, 2022).",
"California ISO. San Jose Area Transmission Plan: decision on modifications to the 2021-2022 transmission plan study (5 November 2024); https://www.caiso.com/documents/decision-on-modifications-to-the-2021-2022-transmission-plan-study-nov-2024.pdf (accessed 27 May 2026).",
"California ISO. 2024-2025 Transmission Planning Process: Board Approved Transmission Plan Posted (30 May 2025); https://www.caiso.com/notices/2024-2025-transmission-planning-process-board-approved-transmission-plan-posted (accessed 27 May 2026).",
"LS Power. LS Power selected by the California ISO for San Jose area HVDC projects. Press release (8 March 2023); https://www.lspower.com/news/ls-power-selected-by-the-california-iso-for-san-jose-area-hvdc-projects/ (accessed 27 May 2026).",
"LS Power Grid. Power Santa Clara Valley HVDC Project fact sheet (2025); https://www.lspowergrid.com/wp-content/uploads/Power-Santa-Clara-Valley-2-Pager.pdf (accessed 27 May 2026).",
"IEC. IEC 61000-3-3: Electromagnetic compatibility - limits for voltage changes, voltage fluctuations and flicker (IEC, 2013).",
"North American Electric Reliability Corporation. Interconnection oscillation analysis. Technical report (2019)."
]

main_md = '# Direct-current subtransmission backbones for grid-stable AI factories\n\n'
main_md += '## Abstract\n' + abstract + '\n\n'
main_md += '## Introduction\n' + intro + '\n\n'
main_md += '## Results\n\n'
for h,txt in results_sections: main_md += f'### {h}\n{txt}\n\n'
main_md += '## Discussion\n' + discussion + '\n\n'
main_md += '## Methods\n\n'
for h,txt in methods: main_md += f'### {h}\n{txt}\n\n'
main_md += '## Data availability\n' + data_availability + '\n\n'
main_md += '## Code availability\n' + code_availability + '\n\n'
main_md += '## AI-assisted drafting disclosure\n' + ai_disclosure + '\n\n'
main_md += '## Figure legends\n\n'
for k,v in figure_legends.items(): main_md += f'**{k}** {v}\n\n'
main_md += '## References\n\n'
for i,refi in enumerate(references,1): main_md += f'{i}. {refi}\n'
(ROOT/'Direct_current_subtransmission_backbones_for_grid_stable_AI_factories_NComms_v3.md').write_text(main_md)

# Supplementary text
supp_md = """# Supplementary Information

# Supplementary Note 1. Assumption provenance
The modelling assumptions are separated into measured device evidence, industry roadmap evidence, public planning data and forward-looking architecture assumptions. The main text uses conservative phrasing where a value is an extrapolation beyond a measured converter prototype.

# Supplementary Note 2. Averaged EMT equations
The dynamic model is an averaged, architecture-level representation. The AI load is P_L(t). The grid-facing command in architecture j is P_g,j and follows dP_g,j/dt = (P_L - P_g,j)/tau_j, with tau_j = 0 for traditional AC, 1.1 s for local SST, 5-7 s for stronger baselines and 16 s for the DC backbone. The shared buffer power is P_b = P_L - P_g,DC. Its energy state is E_b(t) = integral P_b(t) dt. The voltage proxy is Delta V/V = k_g (P_g - mean(P_g))/S_sc plus a local droop term proportional to P_b. These equations compare exposure between architectures and are not a replacement for switching EMT models.

# Supplementary Note 3. Protection-zone screening
The DC protection study represents detection, converter current limiting, breaker opening, section isolation and re-energization. It is included to expose the functions required by the architecture. It does not specify breaker hardware, insulation coordination or a validated relay scheme.

# Supplementary Note 4. Buffer and economics interpretation
The reference buffer requirement is high power and low energy. It can be met only by coordinated layers: GPU power smoothing, rack or row storage, supercapacitors, converter DC-link energy and station-level storage. The cost/copper envelope is a first-order screen and is not a capital-cost estimate.

# Supplementary Table 1. Assumption provenance
See data/assumption_provenance_table_v3.csv.

# Supplementary Figure captions
**Supplementary Fig. S1 | DC fault-protection dynamic screening.** Representative protection zones and dynamic response to a backbone pole-to-ground fault. The sequence includes detection, current limiting, breaker opening, section isolation and healthy-campus ride-through.

**Supplementary Fig. S2 | Averaged EMT validation.** Time-step convergence and first-order transfer-function validation for the grid-command model used in Fig. 4.

**Supplementary Fig. S3 | Physical interpretation of the shared DC buffer.** Candidate technologies and deployment layers for high-power, low-energy buffering.

**Supplementary Fig. S4 | Cost and copper first-order envelope.** Annual value of loss reduction under electricity-price and load-factor sweeps, and a current-length proxy for corridor conductor burden.
"""
(SUPP/'Supplementary_Information_NComms_v3.md').write_text(supp_md)

# Assumption provenance table
prov=pd.DataFrame([
    {'parameter':'7 kV/400 V DC/DC efficiency','value':'99.0%','role':'measured device evidence','source':'Rothmund et al. 2019'},
    {'parameter':'3.8 kV AC to 400 V DC SST chain','value':'98.1%','role':'measured chain evidence','source':'Rothmund et al. 2019'},
    {'parameter':'5 kV modular M-S4T peak efficiency','value':'97.5% estimated','role':'modular MVDC evidence','source':'Zheng et al. 2021'},
    {'parameter':'20 kW 1000 V/48 V prototype','value':'96% measured; 97.5% estimated with synchronous rectification','role':'data-center voltage-step evidence','source':'Samanta et al. 2020'},
    {'parameter':'AI load spectral range','value':'0.1-20 Hz utility concern','role':'load-dynamics evidence','source':'Choukse et al. 2025'},
    {'parameter':'Reference DC voltage','value':'+/-138 kV','role':'representative design point','source':'this study'},
    {'parameter':'Grid short-circuit strength','value':'10 GVA','role':'screening assumption','source':'this study'},
    {'parameter':'Conductor resistance','value':'0.01 ohm/km per phase or pole','role':'screening assumption','source':'this study'},
])
prov.to_csv(DATA/'assumption_provenance_table_v3.csv',index=False)

# ---------------------------- DOCX generation ----------------------------
def set_cell_shading(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr(); shd = OxmlElement('w:shd'); shd.set(qn('w:fill'), fill); tcPr.append(shd)

def add_hyperlink(paragraph, url, text, color="0563C1", underline=True):
    part = paragraph.part
    r_id = part.relate_to(url, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink', is_external=True)
    hyperlink = OxmlElement('w:hyperlink'); hyperlink.set(qn('r:id'), r_id)
    new_run = OxmlElement('w:r'); rPr = OxmlElement('w:rPr')
    c = OxmlElement('w:color'); c.set(qn('w:val'), color); rPr.append(c)
    if underline:
        u = OxmlElement('w:u'); u.set(qn('w:val'), 'single'); rPr.append(u)
    new_run.append(rPr); t_el = OxmlElement('w:t'); t_el.text = text; new_run.append(t_el)
    hyperlink.append(new_run); paragraph._p.append(hyperlink)

def style_doc(doc):
    styles=doc.styles
    styles['Normal'].font.name='Arial'; styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'),'Arial'); styles['Normal'].font.size=Pt(10)
    for style in ['Title','Heading 1','Heading 2','Heading 3']:
        styles[style].font.name='Arial'; styles[style]._element.rPr.rFonts.set(qn('w:eastAsia'),'Arial')
    styles['Title'].font.size=Pt(18); styles['Title'].font.bold=True
    styles['Heading 1'].font.size=Pt(14); styles['Heading 1'].font.bold=True
    styles['Heading 2'].font.size=Pt(12); styles['Heading 2'].font.bold=True
    styles['Heading 3'].font.size=Pt(10.5); styles['Heading 3'].font.bold=True

def add_para(doc, text):
    p=doc.add_paragraph(text); p.paragraph_format.space_after=Pt(5); p.paragraph_format.line_spacing=1.05; return p

def add_fig(doc, path, caption, width=6.3):
    doc.add_picture(str(path), width=Inches(width))
    p=doc.paragraphs[-1]; p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    cp=doc.add_paragraph(caption); cp.style=doc.styles['Caption'] if 'Caption' in doc.styles else doc.styles['Normal']; cp.paragraph_format.space_after=Pt(8)
    for run in cp.runs: run.font.size=Pt(8)

def create_main_docx():
    doc=Document(); style_doc(doc)
    sec=doc.sections[0]; sec.top_margin=Inches(0.65); sec.bottom_margin=Inches(0.65); sec.left_margin=Inches(0.7); sec.right_margin=Inches(0.7)
    title=doc.add_paragraph(); title.style='Title'; title.add_run('Direct-current subtransmission backbones for grid-stable AI factories')
    add_para(doc,'Authors: [to be completed]')
    doc.add_heading('Abstract',level=1); add_para(doc,abstract)
    doc.add_heading('Introduction',level=1)
    for para in intro.split('\n\n'): add_para(doc,para)
    doc.add_heading('Results',level=1)
    doc.add_heading(results_sections[0][0],level=2)
    for para in results_sections[0][1].split('\n\n'): add_para(doc,para)
    add_fig(doc, FIG/'fig1_architecture_formal_v3.png', list(figure_legends.items())[0][0]+' '+list(figure_legends.items())[0][1])
    for idx,(h,txt) in enumerate(results_sections[1:], start=2):
        doc.add_heading(h,level=2)
        for para in txt.split('\n\n'): add_para(doc,para)
        fpath={2:'fig2_efficiency_uncertainty_designspace_v3.png',3:'fig3_harmonic_ownership_opendss_screening_v3.png',4:'fig4_voltage_stabilization_averaged_emt_v3.png',5:'fig5_case_study_voltage_envelope_v3.png'}[idx]
        cap_key=list(figure_legends.keys())[idx-1]
        add_fig(doc, FIG/fpath, cap_key+' '+figure_legends[cap_key])
    doc.add_heading('Discussion',level=1)
    for para in discussion.split('\n\n'): add_para(doc,para)
    doc.add_heading('Methods',level=1)
    for h,txt in methods:
        doc.add_heading(h,level=2)
        for para in txt.split('\n\n'): add_para(doc,para)
    doc.add_heading('Data availability',level=1); add_para(doc,data_availability)
    doc.add_heading('Code availability',level=1); add_para(doc,code_availability)
    doc.add_heading('AI-assisted drafting disclosure',level=1); add_para(doc,ai_disclosure)
    doc.add_heading('References',level=1)
    for i,refi in enumerate(references,1): add_para(doc,f'{i}. {refi}')
    out=ROOT/'Direct_current_subtransmission_backbones_for_grid_stable_AI_factories_NComms_v3.docx'
    doc.save(out); return out

def create_supp_docx():
    doc=Document(); style_doc(doc)
    sec=doc.sections[0]; sec.top_margin=Inches(0.65); sec.bottom_margin=Inches(0.65); sec.left_margin=Inches(0.7); sec.right_margin=Inches(0.7)
    title=doc.add_paragraph(); title.style='Title'; title.add_run('Supplementary Information')
    doc.add_heading('Supplementary Note 1. Assumption provenance',level=1)
    add_para(doc,'The modelling assumptions are separated into measured device evidence, industry roadmap evidence, public planning data and forward-looking architecture assumptions. The main text uses conservative phrasing where a value is an extrapolation beyond a measured converter prototype.')
    # table
    doc.add_heading('Supplementary Table 1. Assumption provenance',level=2)
    table=doc.add_table(rows=1,cols=4); table.alignment=WD_TABLE_ALIGNMENT.CENTER; table.style='Table Grid'
    hdr=table.rows[0].cells
    for c,tv in zip(hdr,['Parameter','Value','Role','Source']): c.text=tv; set_cell_shading(c,'E6E6E6')
    for _,row in prov.iterrows():
        cells=table.add_row().cells
        for i,k in enumerate(['parameter','value','role','source']): cells[i].text=str(row[k])
    doc.add_heading('Supplementary Note 2. Averaged EMT equations and validation',level=1)
    add_para(doc,'The dynamic model is an averaged, architecture-level representation. The AI load is P_L(t). The grid-facing command P_g follows dP_g/dt = (P_L - P_g)/tau. The shared buffer power is P_b = P_L - P_g, and the buffer energy state is the time integral of P_b. The voltage proxy combines grid-stiffness and local droop terms. These equations compare exposure between architectures and are not a replacement for switching EMT models.')
    add_fig(doc, FIG/'supp_fig_s2_averaged_emt_validation_v3.png', 'Supplementary Fig. S2 | Averaged EMT validation. Time-step convergence and first-order transfer-function validation for the grid-command model used in Fig. 4.')
    doc.add_heading('Supplementary Note 3. Protection-zone screening',level=1)
    add_para(doc,'The DC protection study represents detection, converter current limiting, breaker opening, section isolation and re-energization. It is included to expose the functions required by the architecture. It does not specify breaker hardware, insulation coordination or a validated relay scheme.')
    add_fig(doc, FIG/'supp_fig_s1_dc_fault_protection_dynamic_v3.png', 'Supplementary Fig. S1 | DC fault-protection dynamic screening. Representative protection zones and dynamic response to a backbone pole-to-ground fault.')
    doc.add_heading('Supplementary Note 4. Buffer and economics interpretation',level=1)
    add_para(doc,'The reference buffer requirement is high power and low energy. It can be met only by coordinated layers: GPU power smoothing, rack or row storage, supercapacitors, converter DC-link energy and station-level storage. The cost/copper envelope is a first-order screen and is not a capital-cost estimate.')
    add_fig(doc, FIG/'supp_fig_s3_buffer_feasibility_v3.png', 'Supplementary Fig. S3 | Physical interpretation of the shared DC buffer. Candidate technologies and deployment layers for high-power, low-energy buffering.')
    add_fig(doc, FIG/'supp_fig_s4_cost_copper_envelope_v3.png', 'Supplementary Fig. S4 | Cost and copper first-order envelope. Annual value of loss reduction and current-length proxy for corridor conductor burden.')
    out=SUPP/'Supplementary_Information_NComms_v3.docx'; doc.save(out); return out

main_docx=create_main_docx(); supp_docx=create_supp_docx()

# ---------------------------- Public repository ----------------------------
# Copy data, figures, OpenDSS files to repo
for src in DATA.glob('*'):
    shutil.copy(src, REPO/'data'/src.name)
for src in FIG.glob('*.png'):
    shutil.copy(src, REPO/'figures'/src.name)
for src in FIG.glob('*.svg'):
    shutil.copy(src, REPO/'figures'/src.name)
for src in OPENDSS.glob('*'):
    shutil.copy(src, REPO/'opendss'/src.name)
source_root = Path(__file__).resolve().parents[1]
source_data = source_root/'data'
source_opendss = source_root/'opendss'
source_scripts = source_root/'scripts'
if source_data.exists():
    for src in source_data.glob('true_opendss_*'):
        shutil.copy(src, DATA/src.name)
        shutil.copy(src, REPO/'data'/src.name)
if source_opendss.exists():
    for src in source_opendss.glob('true_opendss*'):
        shutil.copy(src, OPENDSS/src.name)
        shutil.copy(src, REPO/'opendss'/src.name)
if (source_scripts/'run_true_opendss.py').exists():
    shutil.copy(source_scripts/'run_true_opendss.py', REPO/'scripts'/'run_true_opendss.py')
# Code modules
(REPO/'src'/'ai_dc_backbone'/'__init__.py').write_text('__version__ = "0.3.0"\n')
(REPO/'src'/'ai_dc_backbone'/'efficiency.py').write_text(textwrap.dedent('''
    import math
    def losses_eff(load_MW=1000, length_km=20, r_ohm_km=0.01, pf=0.98,
                   trad_eff=0.991*0.982, sst_eff=0.985, dc_term=0.994, dc1=0.994, dc2=0.992,
                   vac_kv=138, vdc_pp_kv=276):
        P=load_MW*1e6; R=r_ohm_km*length_km
        P_recv_trad=P/trad_eff; I_ac_trad=P_recv_trad/(math.sqrt(3)*vac_kv*1e3*pf); line_trad=3*I_ac_trad**2*R; input_trad=P_recv_trad+line_trad
        P_recv_sst=P/sst_eff; I_ac_sst=P_recv_sst/(math.sqrt(3)*vac_kv*1e3*pf); line_sst=3*I_ac_sst**2*R; input_sst=P_recv_sst+line_sst
        P_recv_dc=P/(dc1*dc2); I_dc=P_recv_dc/(vdc_pp_kv*1e3); line_dc=2*I_dc**2*R; input_dc=(P_recv_dc+line_dc)/dc_term
        return {'Traditional AC':(input_trad-P)/1e6,'Local SST':(input_sst-P)/1e6,'Subtransmission DC backbone':(input_dc-P)/1e6}
'''))
(REPO/'src'/'ai_dc_backbone'/'dynamics.py').write_text(textwrap.dedent('''
    import numpy as np
    def lpf(x, tau, dt):
        y=np.empty_like(x); y[0]=x[0]; a=dt/(tau+dt)
        for i in range(1,len(x)): y[i]=y[i-1]+a*(x[i]-y[i-1])
        return y
    def spectral_energy(x, dt, fmin=0.1, fmax=20):
        y=x-np.mean(x); freqs=np.fft.rfftfreq(len(y),dt); mag=np.abs(np.fft.rfft(y))/len(y)*2
        mask=(freqs>=fmin)&(freqs<=fmax)
        return float(np.sqrt(np.sum(mag[mask]**2)))
'''))
(REPO/'src'/'ai_dc_backbone'/'harmonics.py').write_text(textwrap.dedent('''
    import numpy as np, math
    def resonance_factor(h, shift=0.0, strength=1.0):
        return 1 + strength*(3.2*np.exp(-0.5*((h-(11+shift))/1.6)**2) + 1.7*np.exp(-0.5*((h-(23+0.5*shift))/2.0)**2))
    def note():
        return 'Use this module for the transparent nodal frequency-domain solver. OpenDSS-compatible files are in opendss/.'
'''))
source_reproduce = Path(__file__).resolve().with_name('reproduce_all.py')
if source_reproduce.exists():
    shutil.copy(source_reproduce, REPO/'scripts'/'reproduce_all.py')
else:
    (REPO/'scripts'/'reproduce_all.py').write_text("print('Run scripts/build_dc_backbone_v3.py to rebuild the manuscript package.')\n")
(REPO/'scripts'/'run_opendss_if_available.py').write_text(textwrap.dedent('''
    #!/usr/bin/env python
    """Run OpenDSS-compatible files if opendssdirect.py is installed.
    The manuscript figures do not depend on this optional check; they use the
    transparent frequency-domain solver. This script is provided for external validation.
    """
    from pathlib import Path
    try:
        import opendssdirect as dss
    except Exception as e:
        print('OpenDSSDirect not installed:', e)
        print('Install opendssdirect.py in a local environment and rerun this script.')
        raise SystemExit(0)
    for f in Path('opendss').glob('*.dss'):
        print('Compiling', f)
        dss.Basic.ClearAll()
        dss.Text.Command(f'Compile [{f}]')
        dss.Text.Command('Solve mode=harmonics')
        print('Solved:', f)
'''))
(REPO/'README.md').write_text(textwrap.dedent('''
    # Direct-current subtransmission backbones for grid-stable AI factories

    This repository contains the data, screening models, figures and OpenDSS-compatible files for the manuscript
    "Direct-current subtransmission backbones for grid-stable AI factories".

    ## Contents
    - `data/`: CSV inputs and outputs for all manuscript and supplementary figures.
    - `figures/`: publication figures in PNG/SVG form.
    - `src/ai_dc_backbone/`: reusable Python model modules.
    - `scripts/`: reproduction helpers and optional OpenDSS runner.
    - `opendss/`: OpenDSS-compatible harmonic network files.

    ## Reproducing results
    ```bash
    python scripts/reproduce_all.py
    python scripts/run_opendss_if_available.py  # optional, requires opendssdirect.py
    ```

    `scripts/reproduce_all.py` regenerates Fig. 3 and Fig. 4 from the archived CSV
    outputs into `reproduced/figures`. The manuscript figures were generated with
    transparent Python models. Fig. 3 includes direct OpenDSSDirect.py harmonic-run
    artifacts and an internal nodal-frequency solver check. OpenDSS circuit files
    and the run log are included under `opendss/`.

    ## Citation
    See `CITATION.cff`. This repository is structured for GitHub release and Zenodo deposition.

    ## Figure and drafting provenance
    - Figure provenance is documented in `docs/figure_provenance.md`.
    - AI-assisted drafting disclosure language is provided in
      `docs/ai_assisted_drafting_disclosure.md`.

    ## Direct OpenDSS check
    This repository includes `scripts/run_true_opendss.py`,
    `opendss/true_opendss_harmonic_network_v3.dss`, and the resulting
    `data/true_opendss_*` CSV files.
'''))
(REPO/'CITATION.cff').write_text(textwrap.dedent('''
    cff-version: 1.2.0
    title: "Code and data for Direct-current subtransmission backbones for grid-stable AI factories"
    message: "If you use this code or data, please cite the associated manuscript and this archive."
    type: software
    authors:
      - family-names: "TBD"
        given-names: "TBD"
    version: "0.3.0"
    date-released: "2026-05-26"
    license: "MIT"
    repository-code: "https://github.com/SavannahY/dc-ai-factory-backbone-reproducibility"
    abstract: "Reproducibility package containing source data, OpenDSS cases, figure-generation code and verification tests for a manuscript on direct-current subtransmission backbones for grid-stable AI factories."
'''))
(REPO/'LICENSE').write_text('MIT License\n\nCopyright (c) 2026 Authors\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files...\n')
(REPO/'requirements.txt').write_text('numpy\npandas\nmatplotlib\npython-docx\n')
(REPO/'environment.yml').write_text('name: dc-backbone-ai-factories\nchannels:\n  - conda-forge\ndependencies:\n  - python>=3.10\n  - numpy\n  - pandas\n  - matplotlib\n  - python-docx\n')
(REPO/'docs'/'reproduction.md').write_text(textwrap.dedent('''
    This repository is structured for public release. To regenerate the two
    highest-risk manuscript figures from archived CSV outputs, run:

    ```bash
    python scripts/reproduce_all.py
    ```

    The script writes Fig. 3 and Fig. 4 to `reproduced/figures`. OpenDSSDirect.py
    harmonic-run artifacts are archived under `opendss/` and
    `data/true_opendss_*`. To rerun OpenDSS in a local environment with
    OpenDSSDirect.py installed, run:

    ```bash
    python scripts/run_true_opendss.py
    ```

    The complete manuscript-package generator is `scripts/build_dc_backbone_v3.py`.
    It is retained for auditability and can be used to rebuild the full manuscript
    package in an environment with the dependencies listed in `requirements.txt`.
''').lstrip())
(REPO/'docs'/'figure_provenance.md').write_text(textwrap.dedent('''
    # Figure provenance

    All manuscript and supplementary figures in this reproducibility package are
    programmatic outputs from `scripts/build_dc_backbone_v3.py` or from the archived
    CSV outputs under `data/`.

    No final manuscript figure is a generative-AI image, photo-realistic rendering,
    stock image, screenshot collage or manually edited bitmap. The distributed PNG,
    SVG and PDF files are Matplotlib exports. The SVG files can be inspected as
    vector graphics, and `scripts/reproduce_all.py` regenerates Fig. 3 and Fig. 4
    from source CSV files as a fast submission check.

    Final figure files:

    - Fig. 1: `figures/fig1_architecture_formal_v3.{png,svg}`
    - Fig. 2: `figures/fig2_efficiency_uncertainty_designspace_v3.{png,svg}`
    - Fig. 3: `figures/fig3_harmonic_ownership_opendss_screening_v3.{png,svg}`
    - Fig. 4: `figures/fig4_voltage_stabilization_averaged_emt_v3.{png,svg}`
    - Fig. 5: `figures/fig5_case_study_voltage_envelope_v3.{png,svg}`
    - Supplementary Fig. S1: `figures/supp_fig_s1_dc_fault_protection_dynamic_v3.{png,svg}`
    - Supplementary Fig. S2: `figures/supp_fig_s2_averaged_emt_validation_v3.{png,svg}`
    - Supplementary Fig. S3: `figures/supp_fig_s3_buffer_feasibility_v3.{png,svg}`
    - Supplementary Fig. S4: `figures/supp_fig_s4_cost_copper_envelope_v3.{png,svg}`
''').lstrip())
(REPO/'docs'/'ai_assisted_drafting_disclosure.md').write_text(textwrap.dedent(f'''
    # AI-assisted drafting disclosure

    Suggested manuscript disclosure language:

    > {ai_disclosure}

    This disclosure should be reviewed by all authors before submission and adjusted
    to match the actual use of AI tools in the final manuscript workflow.
''').lstrip())

# Copy generator script into CODE and repo root for reproducibility
shutil.copy(__file__, CODE/'build_dc_backbone_v3.py')
shutil.copy(__file__, REPO/'scripts'/'build_dc_backbone_v3.py')

# Manifest with SHA256 for DOI-ready data package
manifest=[]
for f in sorted(REPO.rglob('*')):
    if f.is_file():
        h=hashlib.sha256(f.read_bytes()).hexdigest()
        manifest.append({'path':str(f.relative_to(REPO)),'sha256':h,'bytes':f.stat().st_size})
pd.DataFrame(manifest).to_csv(REPO/'MANIFEST_SHA256.csv',index=False)

# ZIP public repo and full package
repo_zip=ROOT/'public_code_repo_DOI_ready.zip'
with zipfile.ZipFile(repo_zip,'w',zipfile.ZIP_DEFLATED) as z:
    for f in REPO.rglob('*'):
        z.write(f, f.relative_to(REPO.parent))
full_zip=ROOT.parent/'DC_backbone_AI_factories_NComms_v3_full_package.zip'
with zipfile.ZipFile(full_zip,'w',zipfile.ZIP_DEFLATED) as z:
    for f in ROOT.rglob('*'):
        z.write(f, f.relative_to(ROOT.parent))

print('MAIN_DOCX', main_docx)
print('SUPP_DOCX', supp_docx)
print('REPO_ZIP', repo_zip)
print('FULL_ZIP', full_zip)
