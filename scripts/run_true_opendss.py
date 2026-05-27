import math, json
from pathlib import Path
import numpy as np, pandas as pd
import opendssdirect as dss
ROOT=Path('/mnt/data/dc_backbone_ncomms_v3')
DATA=ROOT/'data'
OP=ROOT/'opendss'
HARMONICS=np.array([5,7,11,13,17,19,23,25])
# tuned spectra: percent of fundamental current. We use realistic-ish relative magnitudes, not compliance guarantees.
SPECTRA={
    'traditional_ac':np.array([1.75,1.15,0.75,0.52,0.35,0.28,0.20,0.15]),
    'local_sst':np.array([0.80,0.54,0.34,0.25,0.17,0.13,0.085,0.062]),
    'dc_backbone':np.array([0.18,0.12,0.074,0.054,0.033,0.026,0.017,0.013]),
}

def cmd(s):
    try:
        dss.Text.Command(s)
    except Exception as e:
        raise RuntimeError(f'DSS command failed: {s}\n{e}\n{dss.Error.Description()}')

def build_network(mvasc3=1200, line_scale=1.0):
    cmd('Clear')
    cmd('New Circuit.AIFactory basekv=138 pu=1.0 phases=3 bus1=source.1.2.3')
    cmd('New Spectrum.FundOnly numharm=1 harmonic=(1) %mag=(100) angle=(0)')
    cmd(f'Edit Vsource.Source bus1=source.1.2.3 basekv=138 pu=1 phases=3 MVAsc3={mvasc3:.2f} MVAsc1={mvasc3:.2f} spectrum=FundOnly')
    # 138 kV compact urban subtransmission/cable equivalent; capacitance increases resonance sensitivity.
    cmd('New Linecode.LC138 nphases=3 r1=0.065 x1=0.42 r0=0.20 x0=1.25 c1=4.2 c0=2.0 units=km')
    cmd('New Line.Main bus1=source.1.2.3 bus2=pcc.1.2.3 phases=3 linecode=LC138 length=2 units=km')
    cmd(f'New Line.C1 bus1=pcc.1.2.3 bus2=campus1.1.2.3 phases=3 linecode=LC138 length={8*line_scale:.3f} units=km')
    cmd(f'New Line.C2 bus1=pcc.1.2.3 bus2=campus2.1.2.3 phases=3 linecode=LC138 length={13*line_scale:.3f} units=km')
    cmd(f'New Line.C3 bus1=pcc.1.2.3 bus2=campus3.1.2.3 phases=3 linecode=LC138 length={18*line_scale:.3f} units=km')
    # fundamental loads scaled to 1 GW at 0.97 pf. (Reactive set approximate.)
    for i in range(1,4):
        cmd(f'New Load.Fund{i} bus1=campus{i}.1.2.3 phases=3 kv=138 kw=333000 kvar=83500 model=1 spectrum=FundOnly')
    cmd('Set VoltageBases=[138]')
    cmd('CalcVoltageBases')
    cmd('Solve mode=snap')

def vmag(bus='pcc'):
    dss.Circuit.SetActiveBus(bus)
    vals=dss.Bus.VMagAngle()
    return float(np.mean(np.array(vals[0::2])))

def solve_harmonic(arch,h,pct,rng,mvasc,line_scale):
    build_network(mvasc,line_scale)
    Ifund_total=1000e6/(math.sqrt(3)*138e3*0.97)
    Ifund_site=Ifund_total/3
    if arch in ['traditional_ac','local_sst']:
        for i in range(1,4):
            amp=Ifund_site*pct/100
            phase=rng.uniform(-180,180)
            cmd(f'New Spectrum.S{i} numharm=1 harmonic=({h}) %mag=(100) angle=({phase:.3f})')
            cmd(f'New Isource.I{i} bus1=campus{i}.1.2.3 phases=3 amps={amp:.4f} angle={phase:.3f} spectrum=S{i}')
    else:
        amp=Ifund_total*pct/100
        phase=rng.uniform(-30,30)
        cmd(f'New Spectrum.Scentral numharm=1 harmonic=({h}) %mag=(100) angle=({phase:.3f})')
        cmd(f'New Isource.Icentral bus1=pcc.1.2.3 phases=3 amps={amp:.4f} angle={phase:.3f} spectrum=Scentral')
    cmd(f'Solve mode=harmonic harmonic={h}')
    if not dss.Solution.Converged():
        raise RuntimeError('OpenDSS did not converge')
    return vmag('pcc')

def run(n=60,seed=20260526):
    rng=np.random.default_rng(seed)
    rows=[]; spec=[]
    for arch in ['traditional_ac','local_sst','dc_backbone']:
        for trial in range(n):
            mvasc=float(rng.uniform(800,2500))
            line_scale=float(rng.uniform(0.75,1.45))
            build_network(mvasc,line_scale)
            v1=vmag('pcc')
            vh=[]
            for h,pct in zip(HARMONICS,SPECTRA[arch]):
                v=solve_harmonic(arch,h,float(pct),rng,mvasc,line_scale)
                vh.append(v)
                spec.append({'architecture':arch,'trial':trial,'harmonic_order':int(h),'v_h_volts':v,'v1_volts':v1,'individual_distortion_pct':100*v/v1,'mvasc3':mvasc,'line_scale':line_scale})
            thd=100*float(np.sqrt(np.sum(np.array(vh)**2))/v1)
            rows.append({'architecture':arch,'trial':trial,'thdv_pct':thd,'mvasc3':mvasc,'line_scale':line_scale,'source_count':3 if arch!='dc_backbone' else 1,'tdd_proxy_pct':float(np.sqrt(np.sum(SPECTRA[arch]**2)))})
    df=pd.DataFrame(rows); sp=pd.DataFrame(spec)
    df.to_csv(DATA/'true_opendss_harmonic_thdv_monte_carlo_v3.csv',index=False)
    sp.to_csv(DATA/'true_opendss_harmonic_individual_spectrum_v3.csv',index=False)
    log={'engine':'opendssdirect.py','n_trials':n,'harmonic_orders':HARMONICS.tolist(),'p95_thdv_pct':df.groupby('architecture')['thdv_pct'].quantile(0.95).to_dict()}
    (OP/'true_opendss_run_log_v3.json').write_text(json.dumps(log,indent=2))
    # write one illustrative DSS file per architecture with spectrum comments
    template='''// True OpenDSS harmonic network for AI-factory load-pocket screening\n// Python driver injects harmonic current sources and executes Solve mode=harmonic harmonic=<order>.\nClear\nNew Circuit.AIFactory basekv=138 pu=1.0 phases=3 bus1=source.1.2.3\nEdit Vsource.Source bus1=source.1.2.3 basekv=138 pu=1 phases=3 MVAsc3=1200 MVAsc1=1200\nNew Linecode.LC138 nphases=3 r1=0.065 x1=0.42 r0=0.20 x0=1.25 c1=4.2 c0=2.0 units=km\nNew Line.Main bus1=source.1.2.3 bus2=pcc.1.2.3 phases=3 linecode=LC138 length=2 units=km\nNew Line.C1 bus1=pcc.1.2.3 bus2=campus1.1.2.3 phases=3 linecode=LC138 length=8 units=km\nNew Line.C2 bus1=pcc.1.2.3 bus2=campus2.1.2.3 phases=3 linecode=LC138 length=13 units=km\nNew Line.C3 bus1=pcc.1.2.3 bus2=campus3.1.2.3 phases=3 linecode=LC138 length=18 units=km\nNew Load.Fund1 bus1=campus1.1.2.3 phases=3 kv=138 kw=333000 kvar=83500 model=1\nNew Load.Fund2 bus1=campus2.1.2.3 phases=3 kv=138 kw=333000 kvar=83500 model=1\nNew Load.Fund3 bus1=campus3.1.2.3 phases=3 kv=138 kw=333000 kvar=83500 model=1\nSet VoltageBases=[138]\nCalcVoltageBases\nSolve mode=snap\n'''
    (OP/'true_opendss_harmonic_network_v3.dss').write_text(template)
    print(json.dumps(log,indent=2))
if __name__=='__main__': run()
