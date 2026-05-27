
import numpy as np
def lpf(x, tau, dt):
    y=np.empty_like(x); y[0]=x[0]; a=dt/(tau+dt)
    for i in range(1,len(x)): y[i]=y[i-1]+a*(x[i]-y[i-1])
    return y
def spectral_energy(x, dt, fmin=0.1, fmax=20):
    y=x-np.mean(x); freqs=np.fft.rfftfreq(len(y),dt); mag=np.abs(np.fft.rfft(y))/len(y)*2
    mask=(freqs>=fmin)&(freqs<=fmax)
    return float(np.sqrt(np.sum(mag[mask]**2)))
