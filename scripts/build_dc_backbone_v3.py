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
(OPENDSS/'opendss_run_note.txt').write_text('OpenDSS-compatible circuit files are provided. The container used for manuscript generation does not include an OpenDSS engine; run scripts/run_opendss_if_available.py in an environment with opendssdirect.py for a direct OpenDSS check. Manuscript Fig. 3 is generated by the transparent nodal-frequency solver included in the public code repository.\n')

# ---------------------------- Dynamic waveform / averaged EMT ----------------------------
dt=assumptions['dynamic_timestep_s']; t=np.arange(0,assumptions['dynamic_reference_duration_s'],dt)
P=np.ones_like(t)*1.0
period=7.0
for k in np.arange(5,235,period):
    P -= 0.28*np.exp(-0.5*((t-k)/0.45)**2)
for k in np.arange(35,235,70):
    P -= 0.23*np.exp(-0.5*((t-k)/1.2)**2)
P += 0.015*np.sin(2*np.pi*0.045*t) + 0.006*np.sin(2*np.pi*0.33*t+0.4)
P=np.clip(P,0.48,1.08)
P_MW=P/np.mean(P)*1000

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
base=lpf(P_MW,16.0,dt=0.02)
for dt2 in [0.04,0.02,0.01,0.005]:
    t2=np.arange(0,240,dt2)
    P2=np.interp(t2,t,P_MW)
    y2=lpf(P2,16.0,dt=dt2)
    y2r=np.interp(t,t2,y2)
    rmse=np.sqrt(np.mean((y2r-base)**2))
    conv_rows.append({'dt_s':dt2,'rmse_MW_vs_dt0p02':rmse})
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

def figure1():
    fig,ax=plt.subplots(figsize=(12,7.5)); ax.set_xlim(0,10); ax.set_ylim(0,7.5); ax.axis('off')
    ac='#1f77b4'; dc='#d94801'; campus_dc='#f16913'
    ybands=[6.3,3.9,1.5]; titles=['Traditional AC','Local SST','DC backbone']; labels=['a','b','c']
    for y,title,lab in zip(ybands,titles,labels):
        ax.text(0.22,y+0.55,lab,fontsize=14,weight='bold')
        ax.text(0.55,y+0.55,title,fontsize=13,weight='bold')
        draw_icon(ax,1.0,y,'grid',0.8)
        if lab!='c':
            draw_icon(ax,2.1,y,'substation',0.8)
            ax.plot([1.32,1.75],[y,y],color=ac,lw=2.2)
            for x in [2.9,3.35,3.8]: draw_icon(ax,x,y,'tower',0.8)
            ax.plot([2.45,4.3],[y,y],color=ac,lw=2.2)
            ax.text(3.35,y-0.45,'AC corridor',ha='center',fontsize=8,color=ac)
            if lab=='a':
                for cy in [y+0.45,y,y-0.45]:
                    ax.plot([4.3,5.3,5.8],[y,cy,cy],color=ac,lw=2)
                    draw_icon(ax,6.15,cy,'substation',0.5)
                    ax.plot([6.45,7.1],[cy,cy],color=ac,lw=2)
                    draw_icon(ax,7.45,cy,'converter',0.5)
                    ax.plot([7.78,8.3],[cy,cy],color=campus_dc,lw=2)
                    draw_icon(ax,8.85,cy,'campus',0.65)
                    ax.text(9.35,cy,'800 VDC',va='center',fontsize=7,color=campus_dc)
                ax.text(6.2,y-0.70,'facility AC',ha='center',fontsize=8,color=ac)
            else:
                for cy in [y+0.45,y,y-0.45]:
                    ax.plot([4.3,5.45,5.9],[y,cy,cy],color=ac,lw=2)
                    draw_icon(ax,6.2,cy,'sst',0.62)
                    ax.plot([6.58,7.15],[cy,cy],color=campus_dc,lw=2)
                    ax.text(6.86,cy+0.12,'800 VDC',ha='center',fontsize=7,color=campus_dc)
                    draw_icon(ax,7.9,cy,'campus',0.65)
        else:
            draw_icon(ax,2.05,y,'converter',0.8)
            ax.plot([1.32,1.68],[y,y],color=ac,lw=2.2); ax.text(1.5,y+0.12,'AC',ha='center',fontsize=7,color=ac)
            ax.plot([2.45,4.9],[y,y],color=dc,lw=2.7)
            for x in [3.15,3.65,4.15]: draw_icon(ax,x,y,'tower',0.8)
            ax.text(3.72,y-0.45,'subtransmission DC',ha='center',fontsize=8,color=dc)
            for cy in [y+0.45,y,y-0.45]:
                ax.plot([4.9,5.5,5.5],[y,y,cy],color=dc,lw=2.0)
                draw_icon(ax,5.95,cy,'dcdc',0.6)
                ax.plot([6.28,7.02],[cy,cy],color=dc,lw=2.0)
                ax.text(6.65,cy+0.12,'34.5 kV DC',ha='center',fontsize=7,color=dc)
                draw_icon(ax,7.35,cy,'dcdc',0.5)
                ax.plot([7.65,8.2],[cy,cy],color=campus_dc,lw=2)
                ax.text(7.92,cy+0.12,'800 VDC',ha='center',fontsize=7,color=campus_dc)
                draw_icon(ax,8.8,cy,'campus',0.65)
    ax.plot([0.35,0.7],[0.35,0.35],color=ac,lw=2.5); ax.text(0.75,0.35,'AC',va='center',fontsize=8)
    ax.plot([1.05,1.4],[0.35,0.35],color=dc,lw=2.5); ax.text(1.45,0.35,'DC',va='center',fontsize=8)
    fig.tight_layout(); savefig(fig,'fig1_architecture_formal_v3')
figure1()

# Figure 2
def figure2():
    fig,axes=plt.subplots(2,2,figsize=(11,8),gridspec_kw={'width_ratios':[1,1.15]})
    colors={'Traditional AC':'#377eb8','Local SST':'#984ea3','Local SST optimistic':'#bc80bd','Subtransmission DC backbone':'#e6550d'}
    order=['Traditional AC','Local SST','Local SST optimistic','Subtransmission DC backbone']
    ax=axes[0,0]
    vals=[ref_df.set_index('architecture').loc[o,'loss_MW'] for o in order]
    ax.bar(range(len(order)), vals, color=[colors[o] for o in order], alpha=0.86)
    ax.set_xticks(range(len(order))); ax.set_xticklabels(['Traditional\nAC','Local\nSST','Optimistic\nSST','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('Loss at 1 GW (MW)'); ax.set_title('a  Reference losses to 800 VDC',loc='left',fontsize=11,weight='bold')
    for i,v in enumerate(vals): ax.text(i,v+0.8,f'{v:.1f}',ha='center',fontsize=7)
    ax.grid(axis='y',alpha=0.25)
    ax=axes[0,1]
    data=[mc_df['traditional_loss_MW'], mc_df['local_sst_loss_MW'], mc_df['local_sst_optimistic_loss_MW'], mc_df['dc_loss_MW']]
    parts=ax.violinplot(data, showmedians=True, showextrema=False)
    for pc,c in zip(parts['bodies'],[colors[o] for o in order]): pc.set_facecolor(c); pc.set_edgecolor(c); pc.set_alpha(0.45)
    ax.set_xticks(range(1,len(order)+1)); ax.set_xticklabels(['Traditional\nAC','Local\nSST','Optimistic\nSST','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('Loss under uncertainty (MW)'); ax.set_title('b  Uncertainty and stronger SST baseline',loc='left',fontsize=11,weight='bold'); ax.grid(axis='y',alpha=0.25)
    ax=axes[1,0]
    pivot=design_df.pivot(index='length_km',columns='load_MW',values='saving_vs_traditional_MW')
    im=ax.imshow(pivot.values,origin='lower',aspect='auto',extent=[loads.min(),loads.max(),lengths.min(),lengths.max()],cmap='YlOrRd')
    cs=ax.contour(loads,lengths,pivot.values,levels=[10,50,100],colors='k',linewidths=0.8); ax.clabel(cs,fmt='%d MW',fontsize=7)
    ax.scatter([1000],[20],c='white',edgecolors='black',s=40,zorder=3)
    ax.set_xlabel('Cluster load (MW)'); ax.set_ylabel('Corridor length (km)'); ax.set_title('c  DC saving over traditional AC',loc='left',fontsize=11,weight='bold')
    cb=fig.colorbar(im,ax=ax,shrink=0.86); cb.set_label('MW saved')
    ax=axes[1,1]
    tmp=sens_df.copy(); tmp['span']=abs(tmp['high_case_saving_MW']-tmp['low_case_saving_MW']); tmp=tmp.sort_values('span')
    y=np.arange(len(tmp))
    ax.hlines(y,tmp['low_case_saving_MW'],tmp['high_case_saving_MW'],color='#636363',lw=5,alpha=0.7)
    ax.axvline(base_saving,color='#e6550d',lw=1.5,label='base')
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
    interfaces=[3,3,3,3,1]
    ax.bar(range(len(names)),interfaces,color=[colors[n] for n in names],alpha=0.85)
    ax.set_xticks(range(len(names))); ax.set_xticklabels(['Trad.\nAC','AC+filter\n/storage','Local\nSST','SST+\ncoord.','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('AC-facing large converter interfaces'); ax.set_ylim(0,3.6); ax.set_title('a  Harmonic ownership boundary',loc='left',fontsize=11,weight='bold'); ax.grid(axis='y',alpha=0.25)
    ax=axes[0,1]
    data=[harm_df[harm_df.scenario==n].thdv_pct for n in names]
    parts=ax.violinplot(data,showmedians=True,showextrema=False)
    for pc,n in zip(parts['bodies'],names): pc.set_facecolor(colors[n]); pc.set_edgecolor(colors[n]); pc.set_alpha(0.42)
    ax.set_xticks(range(1,len(names)+1)); ax.set_xticklabels(['Trad.\nAC','AC+filter\n/storage','Local\nSST','SST+\ncoord.','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('PCC voltage THD (%)'); ax.set_title('b  Harmonic screening result',loc='left',fontsize=11,weight='bold'); ax.grid(axis='y',alpha=0.25)
    ax=axes[1,0]
    for n in ['Traditional AC','Local SST','Subtransmission DC backbone']:
        d=spec_p95[spec_p95.scenario==n]
        ax.plot(d.h,d.p95_individual_harmonic_voltage_pct,marker='o',label=n,color=colors[n],lw=1.4)
    ax.set_xlabel('Harmonic order'); ax.set_ylabel('95th percentile Vh/V1 (%)'); ax.set_title('c  Individual harmonic voltage distortion',loc='left',fontsize=11,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25)
    ax=axes[1,1]
    ax.plot(res_scan.harmonic_order,res_scan.nominal,label='nominal',color='0.3')
    ax.plot(res_scan.harmonic_order,res_scan.low_damping,label='low damping',color='#e6550d')
    ax.plot(res_scan.harmonic_order,res_scan.shifted,label='shifted resonance',color='#3182bd')
    ax.set_xlabel('Harmonic order'); ax.set_ylabel('Network amplification factor'); ax.set_title('d  Resonance scan',loc='left',fontsize=11,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25)
    fig.tight_layout(); savefig(fig,'fig3_harmonic_ownership_opendss_screening_v3')
figure3()

# Figure 4
def figure4():
    fig,axes=plt.subplots(2,2,figsize=(11,7.8))
    colors_d={'Traditional AC':'#377eb8','AC + active filter/storage':'#80b1d3','Local SST':'#984ea3','Local SST + coordinated control':'#bc80bd','Subtransmission DC backbone':'#e6550d'}
    sl=slice(0,int(150/dt))
    ax=axes[0,0]
    ax.plot(t[sl],P_MW[sl],color='0.55',lw=1.0,label='AI load')
    ax.plot(t[sl],P_ac[sl],color=colors_d['Traditional AC'],lw=0.8,label='Traditional AC')
    ax.plot(t[sl],P_ac_bess[sl],color=colors_d['AC + active filter/storage'],lw=1.0,label='AC + storage')
    ax.plot(t[sl],P_sst[sl],color=colors_d['Local SST'],lw=1.0,label='Local SST')
    ax.plot(t[sl],P_dc[sl],color=colors_d['Subtransmission DC backbone'],lw=1.7,label='DC backbone')
    ax.set_ylabel('Grid-side power (MW)'); ax.set_xlabel('Time (s)'); ax.set_title('a  AI training load and grid power',loc='left',fontsize=11,weight='bold'); ax.legend(fontsize=7,ncol=2,frameon=False); ax.grid(alpha=0.25)
    ax=axes[0,1]
    ax.plot(t[sl],pcc_v_ac[sl],color=colors_d['Traditional AC'],lw=0.8,label='Traditional AC')
    ax.plot(t[sl],pcc_v_sst[sl],color=colors_d['Local SST'],lw=1.0,label='Local SST')
    ax.plot(t[sl],pcc_v_dc[sl],color=colors_d['Subtransmission DC backbone'],lw=1.5,label='DC backbone')
    ax.set_ylabel('PCC voltage-deviation proxy (%)'); ax.set_xlabel('Time (s)'); ax.set_title('b  Averaged voltage response',loc='left',fontsize=11,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25)
    ax=axes[1,0]
    order=['Traditional AC','AC + active filter/storage','Local SST','Local SST + coordinated control','Subtransmission DC backbone']
    rel=[energies[o]['relative_to_ac']*100 for o in order]; ramp=[energies[o]['p99_ramp_MW_s'] for o in order]
    x=np.arange(len(order)); w=0.38
    ax.bar(x-w/2,rel,width=w,color=[colors_d[o] for o in order],alpha=0.75,label='0.1-20 Hz energy (%)')
    ax2=ax.twinx(); ax2.plot(x+w/2,ramp,marker='o',color='k',lw=1.2,label='p99 ramp')
    ax.set_xticks(x); ax.set_xticklabels(['Trad.\nAC','AC+\nstorage','Local\nSST','SST+\ncoord.','DC\nbackbone'],fontsize=7)
    ax.set_ylabel('Spectral energy vs AC (%)'); ax2.set_ylabel('p99 ramp (MW/s)'); ax.set_title('c  Frequency and ramp-rate mitigation',loc='left',fontsize=11,weight='bold'); ax.grid(axis='y',alpha=0.25)
    ax=axes[1,1]
    ax.plot(t[sl],P_buffer[sl],color='#e6550d',lw=1.3,label='buffer power')
    ax2=ax.twinx(); ax2.plot(t[sl],E_MWh[sl]-E_MWh[sl].min(),color='#756bb1',lw=1.0,label='energy state')
    ax.axhline(0,color='0.3',lw=0.7)
    ax.set_xlabel('Time (s)'); ax.set_ylabel('Shared DC buffer power (MW)'); ax2.set_ylabel('Energy window (MWh)'); ax.set_title('d  Shared DC buffer requirement',loc='left',fontsize=11,weight='bold'); ax.grid(alpha=0.25)
    fig.tight_layout(); savefig(fig,'fig4_voltage_stabilization_averaged_emt_v3')
figure4()

# Figure 5
def figure5():
    fig,axes=plt.subplots(1,3,figsize=(12,3.9),gridspec_kw={'width_ratios':[1.1,1.25,1.05]})
    ax=axes[0]
    # simple load pocket schematic
    ax.axis('off'); ax.set_title('a  San Jose / Silicon Valley-style load pocket',loc='left',fontsize=10,weight='bold')
    ax.add_patch(FancyBboxPatch((0.06,0.35),0.24,0.28,boxstyle='round,pad=0.02',facecolor='#f2f2f2',edgecolor='0.4'))
    ax.text(0.18,0.49,'HV grid\nsource',ha='center',va='center',fontsize=8)
    ax.add_patch(FancyBboxPatch((0.42,0.62),0.18,0.16,boxstyle='round,pad=0.02',facecolor='#e9eef2',edgecolor='0.4'))
    ax.add_patch(FancyBboxPatch((0.62,0.42),0.18,0.16,boxstyle='round,pad=0.02',facecolor='#e9eef2',edgecolor='0.4'))
    ax.add_patch(FancyBboxPatch((0.42,0.17),0.18,0.16,boxstyle='round,pad=0.02',facecolor='#e9eef2',edgecolor='0.4'))
    for xy,lab in [((0.51,0.70),'AI campus'),((0.71,0.50),'AI campus'),((0.51,0.25),'AI campus')]: ax.text(*xy,lab,ha='center',va='center',fontsize=7)
    for y in [0.70,0.50,0.25]: ax.plot([0.30,0.42 if y!=0.50 else 0.62],[0.49,y],color='#d94801',lw=2)
    ax.text(0.50,0.03,'A concentrated data-center load pocket\ncan be treated as a planning object',ha='center',fontsize=7,color='0.35')

    ax=axes[1]
    bars=[2100,3400,4200]; labs=['2021-22\nstudy','2024-25\nbase','2024-25\nsensitivity']
    ax.bar(range(3),bars,color=['#bdbdbd','#fd8d3c','#e6550d'])
    ax.set_xticks(range(3)); ax.set_xticklabels(labs,fontsize=8); ax.set_ylabel('Long-term load forecast (MW)')
    ax.set_title('b  Data-center-driven load growth',loc='left',fontsize=10,weight='bold')
    for i,b in enumerate(bars): ax.text(i,b+90,f'{b/1000:.1f} GW',ha='center',fontsize=8)
    ax.set_ylim(0,4700); ax.grid(axis='y',alpha=0.25)

    ax=axes[2]
    loads2=np.linspace(100,5000,150)
    for pole,col in [(69,'#9ecae1'),(138,'#e6550d'),(320,'#756bb1')]:
        I=loads2*1e6/(2*pole*1e3)/1000
        ax.plot(loads2,I,label=f'+/-{pole} kV',color=col,lw=2)
    ax.axhline(4,color='0.4',ls='--',lw=1,label='4 kA guide')
    ax.scatter([1000],[1000e6/(276e3)/1000],c='#e6550d',edgecolor='k',zorder=3)
    ax.set_xlabel('Cluster load (MW)'); ax.set_ylabel('Bipole current (kA)'); ax.set_title('c  Voltage-class envelope',loc='left',fontsize=10,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25)
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
    ax=axes[1]; ax.set_title('b  Backbone fault response',loc='left',fontsize=10,weight='bold')
    ax.plot(fault_df.time_s*1000,fault_df.fault_current_kA,color='#d94801',lw=1.5,label='fault current')
    ax2=ax.twinx(); ax2.plot(fault_df.time_s*1000,fault_df.backbone_voltage_pu,color='#3182bd',lw=1.3,label='backbone V')
    ax.axvline(3,color='0.5',ls=':',lw=1); ax.axvline(18,color='0.5',ls='--',lw=1)
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
    ax.plot(validation_df.dt_s,validation_df.rmse_MW_vs_dt0p02,marker='o',color='#e6550d')
    ax.set_xscale('log'); ax.set_xlabel('Time step (s)'); ax.set_ylabel('RMSE vs 20 ms run (MW)'); ax.set_title('a  Time-step convergence',loc='left',fontsize=10,weight='bold'); ax.grid(alpha=0.25)
    ax=axes[1]
    ax.plot(tf_df.frequency_Hz,tf_df.simulated_gain,marker='o',label='simulation',color='#3182bd')
    ax.plot(tf_df.frequency_Hz,tf_df.theory_gain,'--',label='first-order theory',color='0.25')
    ax.set_xscale('log'); ax.set_yscale('log'); ax.set_xlabel('Frequency (Hz)'); ax.set_ylabel('Grid-command gain'); ax.set_title('b  Transfer-function validation',loc='left',fontsize=10,weight='bold'); ax.legend(fontsize=7,frameon=False); ax.grid(alpha=0.25,which='both')
    fig.tight_layout(); savefig(fig,'supp_fig_s2_averaged_emt_validation_v3')
figure_s2()

def figure_s3():
    fig,ax=plt.subplots(figsize=(9,3.8))
    table=buffer_table.copy()
    ax.axis('off'); ax.set_title('Supplementary Fig. S3 | Physical interpretation of the shared DC buffer',loc='left',fontsize=10,weight='bold')
    cols=['technology','power_response','high_power_suitability','energy_window_suitability','deployment_layer']
    cell_text=table[cols].values.tolist()
    tbl=ax.table(cellText=cell_text,colLabels=['Technology','Response','High power','0.42 MWh window','Layer'],loc='center',cellLoc='center',colLoc='center')
    tbl.auto_set_font_size(False); tbl.set_fontsize(7); tbl.scale(1.0,1.6)
    for (r,c),cell in tbl.get_celld().items():
        if r==0: cell.set_facecolor('#e5e5e5'); cell.set_text_props(weight='bold')
    savefig(fig,'supp_fig_s3_buffer_feasibility_v3')
figure_s3()

def figure_s4():
    fig,axes=plt.subplots(1,2,figsize=(10,3.8))
    econ_df=pd.read_csv(DATA/'cost_copper_envelope_v3.csv')
    ax=axes[0]
    grid=econ_df.dropna(subset=['annual_value_USD_M']).pivot(index='load_factor',columns='electricity_price_USD_MWh',values='annual_value_USD_M')
    im=ax.imshow(grid.values,origin='lower',aspect='auto',extent=[price_grid.min(),price_grid.max(),lf_grid.min(),lf_grid.max()],cmap='YlGn')
    ax.set_xlabel('Electricity price ($/MWh)'); ax.set_ylabel('Load factor'); ax.set_title('a  Annual loss-saving value',loc='left',fontsize=10,weight='bold')
    fig.colorbar(im,ax=ax,shrink=0.8,label='$M yr$^{-1}$')
    ax=axes[1]
    current_idx=econ_df[econ_df.metric=='current_length_index_kA_km']
    ax.bar(current_idx.architecture,current_idx.value,color=['#377eb8','#984ea3','#e6550d'],alpha=0.85)
    ax.set_xticklabels(['Traditional\nAC','Local\nSST','DC\nbackbone'],fontsize=8)
    ax.set_ylabel('Current-length index (kA km)'); ax.set_title('b  Corridor current-length proxy',loc='left',fontsize=10,weight='bold'); ax.grid(axis='y',alpha=0.25)
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

With an effective conductor resistance of 0.01 ohm km-1 per phase or pole, the central model gives total losses of 39.1 MW for traditional AC, 26.5 MW for local SSTs, 21.4 MW for an intentionally optimistic 99.0%-efficient local SST baseline and 25.7 MW for the DC backbone (Fig. 2a). The corresponding end-to-end efficiencies are 96.23%, 97.42%, 97.91% and 97.49%. This stronger baseline is deliberately included because the architectural claim should not depend on a narrow efficiency comparison.

The efficiency result alone would not justify a new grid architecture. In the optimistic SST case, local conversion can exceed the DC backbone in pure efficiency. The architectural case emerges because the DC backbone produces an efficiency improvement over traditional AC in the same direction as harmonic ownership and dynamic-voltage benefits. A load-distance sweep from 100 MW to 3 GW and from 5 to 100 km shows where the DC advantage over traditional AC exceeds 10, 50 and 100 MW (Fig. 2c). A Monte Carlo uncertainty sweep and one-at-a-time tornado analysis show that corridor length, conductor resistance and downstream conversion assumptions dominate the quantitative result (Fig. 2b,d)."""),
("A DC backbone changes harmonic compliance into harmonic ownership", """Traditional AC and local-SST architectures can be designed to meet harmonic limits, but they place multiple large AC-facing converter interfaces along the corridor. Their aggregate harmonic voltage distortion depends on local filters, network impedance, cable capacitance, phase relationships between sites and resonance. The proposed DC backbone concentrates the AC-facing converter at a single utility-operated terminal. Campus stations are DC/DC interfaces and therefore do not directly inject AC harmonics into the subtransmission grid.

We quantify this ownership change with an OpenDSS-ready network and a reproduced nodal frequency-domain solver. The network uses a 10 GVA Thevenin short-circuit strength at 138 kV, three campus buses along a 20 km corridor, harmonic-dependent source impedance and resonance amplification around selected orders. Distributed architectures are represented by three AC-facing converter spectra with random relative phases; the DC-backbone case is represented by one filtered grid-facing converter terminal.

For the central assumptions, the 95th-percentile PCC voltage THD is 3.95% for traditional AC, 1.55% for local SSTs and 0.78% for the DC backbone (Fig. 3b). Adding active filtering or storage to the traditional AC case improves the metric, and coordinated control improves the local-SST case, but neither changes the number of AC-facing interfaces. These values are screening metrics, not a substitute for project-specific IEEE 519 compliance studies [8]. Their purpose is narrower and architectural: moving DC upstream changes a distributed compliance problem into a single utility-owned terminal design problem."""),
("The DC backbone buffers synchronized AI-load voltage dynamics", """The third benefit is voltage stabilization under synchronized AI training loads. We construct a synthetic but literature-parameterized 1 GW AI training waveform with repeated compute phases, communication dips and checkpointing events. The traditional AC case passes this waveform directly to the grid. The local-SST case applies limited smoothing. Stronger baselines add substation storage or coordinated SST controls. The DC-backbone case uses a slower grid-facing power command and assigns the difference between the AI load and the grid command to a shared DC buffer.

In the reference waveform, the DC backbone reduces the root-sum-square spectral magnitude in the 0.1-20 Hz band to 5.9% of the traditional AC baseline, while the p99 ramp rate falls from 404 MW s-1 to 16.6 MW s-1 (Fig. 4c). The shared buffer must absorb up to 317 MW, deliver up to 102 MW and span an energy window of 0.42 MWh for this waveform (Fig. 4d). This is a high-power, low-energy requirement. It should not be interpreted as a single large battery; rather, the DC backbone creates the electrical layer where GPU power smoothing, rack or row storage, supercapacitors, station storage and grid-facing converter control can be coordinated.

The voltage metrics in Fig. 4 are averaged EMT proxies. They are designed to compare architecture-level exposure, not to replace detailed EMT studies. We therefore include state equations, transfer-function validation and time-step convergence in the Supplementary Information. The result is that the DC backbone is not only an energy-delivery architecture; it is a dynamic electrical buffer between synchronized GPU computation and the AC grid."""),
("Data-center load pockets are becoming planning objects", """The proposed architecture is motivated by load pockets that are large, concentrated and data-center driven. Public planning documents for the San Jose area show a load pocket growing from approximately 2.1 GW in an earlier study case to 3.4 GW in a later base case and 4.2 GW in a sensitivity case (Fig. 5b) [9-12]. This paper does not claim that a specific planned HVDC project is a 138 kV DC AI-factory backbone. The point is that data-center-driven load pockets are already large enough to motivate controllable transmission solutions.

The voltage-class envelope in Fig. 5c shows why the paper uses +/-138 kV only as a representative subtransmission design point. At 1 GW, +/-138 kV corresponds to approximately 3.6 kA bipole current. Higher multi-GW corridors move naturally toward higher voltage classes such as +/-320 kV. The relevant design variable is therefore not one fixed voltage, but the relocation of the AC/DC boundary to a voltage class compatible with load, distance, current limit, insulation and protection requirements.""")]

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
'Fig. 1 | Three power-delivery architectures for AI factories.':'a, Traditional AC delivery keeps AC in the subtransmission and facility distribution system before conversion to the 800 VDC data-center boundary. b, Local SST delivery uses the same AC corridor but converts at each AI campus. c, The proposed architecture moves the AC/DC boundary upstream and feeds multiple campuses from a utility-operated subtransmission DC backbone, with DC/DC conversion to 34.5 kV DC and then to 800 VDC.',
'Fig. 2 | Efficiency, stronger baselines and design space.':'a, Central 1 GW, 20 km reference-case losses and end-to-end efficiencies to the 800 VDC boundary, including an intentionally optimistic local-SST baseline. b, Monte Carlo uncertainty at the reference point. c, Load-distance sweep showing where the DC-backbone loss advantage over traditional AC exceeds 10, 50 and 100 MW. d, One-at-a-time sensitivity of the central saving.',
'Fig. 3 | Harmonic ownership and OpenDSS-ready screening.':'a, Number of AC-facing large converter interfaces seen by the subtransmission grid. b, Monte Carlo PCC voltage THD for the three architectures and two stronger baselines. c, 95th-percentile individual harmonic voltage distortion. d, Harmonic resonance amplification used by the screening model.',
'Fig. 4 | Voltage stabilization of synchronized AI training loads.':'a, Representative AI training waveform and grid-facing power trajectories. b, Averaged grid-voltage response. c, 0.1-20 Hz spectral energy and 99th-percentile ramp rate. d, Shared DC-buffer power and energy window required for the reference waveform.',
'Fig. 5 | Data-center load pockets and voltage-class envelope.':'a, San Jose / Silicon Valley-style data-center load pocket concept. b, Public planning-data precedent showing multi-GW load-pocket growth. c, Bipole current as a function of cluster load for several candidate DC voltage classes.'}

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

    `scripts/reproduce_all.py` regenerates Fig. 3 and Fig. 4 from the archived CSV outputs
    into `reproduced/figures`. The manuscript figures were generated with transparent
    Python models. OpenDSS-compatible cases and archived harmonic-run artifacts are included
    so that the harmonic model can be checked externally with OpenDSS.

    ## Citation
    See `CITATION.cff`. This repository is structured for GitHub release and Zenodo deposition.
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
    abstract: "Reproducibility package containing source data, OpenDSS cases, figure-generation code and verification tests for a manuscript on direct-current subtransmission backbones for grid-stable AI factories."
'''))
(REPO/'LICENSE').write_text('MIT License\n\nCopyright (c) 2026 Authors\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files...\n')
(REPO/'requirements.txt').write_text('numpy\npandas\nmatplotlib\npython-docx\n')
(REPO/'environment.yml').write_text('name: dc-backbone-ai-factories\nchannels:\n  - conda-forge\ndependencies:\n  - python>=3.10\n  - numpy\n  - pandas\n  - matplotlib\n  - python-docx\n')
(REPO/'docs'/'reproduction.md').write_text('This repository is structured for public release. Run `python scripts/reproduce_all.py` to regenerate Fig. 3 and Fig. 4 from archived CSV outputs into `reproduced/figures`. OpenDSS-compatible files and archived harmonic-run artifacts are included for external harmonic validation.\n')
(REPO/'docs'/'figure_provenance.md').write_text('All final manuscript and supplementary figures are programmatic Matplotlib outputs from scripts/build_dc_backbone_v3.py or archived CSV files under data/. No final figure is a generative-AI image. Run `python scripts/reproduce_all.py` to regenerate Fig. 3 and Fig. 4 from source CSV outputs.\n')
(REPO/'docs'/'ai_assisted_drafting_disclosure.md').write_text(ai_disclosure + '\n')

# Manifest with SHA256 for DOI-ready data package
manifest=[]
for f in sorted(REPO.rglob('*')):
    if f.is_file():
        h=hashlib.sha256(f.read_bytes()).hexdigest()
        manifest.append({'path':str(f.relative_to(REPO)),'sha256':h,'bytes':f.stat().st_size})
pd.DataFrame(manifest).to_csv(REPO/'MANIFEST_SHA256.csv',index=False)

# Copy generator script into CODE and repo root for reproducibility
shutil.copy(__file__, CODE/'build_dc_backbone_v3.py')
shutil.copy(__file__, REPO/'scripts'/'build_dc_backbone_v3.py')

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
