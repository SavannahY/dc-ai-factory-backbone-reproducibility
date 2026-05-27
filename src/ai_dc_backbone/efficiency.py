
import math
def losses_eff(load_MW=1000, length_km=20, r_ohm_km=0.01, pf=0.98,
               trad_eff=0.991*0.982, sst_eff=0.985, dc_term=0.994, dc1=0.994, dc2=0.992,
               vac_kv=138, vdc_pp_kv=276):
    P=load_MW*1e6; R=r_ohm_km*length_km
    P_recv_trad=P/trad_eff; I_ac_trad=P_recv_trad/(math.sqrt(3)*vac_kv*1e3*pf); line_trad=3*I_ac_trad**2*R; input_trad=P_recv_trad+line_trad
    P_recv_sst=P/sst_eff; I_ac_sst=P_recv_sst/(math.sqrt(3)*vac_kv*1e3*pf); line_sst=3*I_ac_sst**2*R; input_sst=P_recv_sst+line_sst
    P_recv_dc=P/(dc1*dc2); I_dc=P_recv_dc/(vdc_pp_kv*1e3); line_dc=2*I_dc**2*R; input_dc=(P_recv_dc+line_dc)/dc_term
    return {'Traditional AC':(input_trad-P)/1e6,'Local SST':(input_sst-P)/1e6,'Subtransmission DC backbone':(input_dc-P)/1e6}
