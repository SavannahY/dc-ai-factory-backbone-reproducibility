from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

def test_efficiency_reference_case_ordering():
    df = pd.read_csv(ROOT / "data" / "efficiency_reference_case_v3.csv", index_col=0)
    assert df.loc["Subtransmission DC backbone", "eff"] > df.loc["Traditional AC", "eff"]
    assert df.loc["Local SST", "eff"] > df.loc["Traditional AC", "eff"]

def test_true_opendss_harmonic_ordering():
    df = pd.read_csv(ROOT / "data" / "true_opendss_harmonic_thdv_monte_carlo_v3.csv")
    p95 = df.groupby("architecture")["thdv_pct"].quantile(0.95)
    assert p95["traditional_ac"] > p95["local_sst"] > p95["dc_backbone"]
    assert p95["traditional_ac"] < 5.0

def test_dynamic_metrics_buffering():
    df = pd.read_csv(ROOT / "data" / "dynamic_metrics_v3.csv", index_col=0)
    assert df.loc["Subtransmission DC backbone", "relative_to_ac"] < df.loc["Local SST", "relative_to_ac"]
    assert df.loc["DC buffer", "energy_window_MWh"] > 0
