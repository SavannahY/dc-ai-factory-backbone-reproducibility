
import numpy as np, math
def resonance_factor(h, shift=0.0, strength=1.0):
    return 1 + strength*(3.2*np.exp(-0.5*((h-(11+shift))/1.6)**2) + 1.7*np.exp(-0.5*((h-(23+0.5*shift))/2.0)**2))
def note():
    return 'Use this module for the transparent nodal frequency-domain solver. OpenDSS-compatible files are in opendss/.'
