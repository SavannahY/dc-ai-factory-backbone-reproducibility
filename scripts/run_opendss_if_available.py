
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
