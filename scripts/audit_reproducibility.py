#!/usr/bin/env python
"""Submission-time reproducibility and scientific-claim audit.

This script is intentionally lightweight. It does not regenerate the expensive
scenario grids; instead, it checks that archived files have not drifted and that
key published tables still support the manuscript's bounded architecture-level
claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OPENDSS = ROOT / "opendss"
MANIFEST = ROOT / "MANIFEST_SHA256.csv"


class AuditFailure(RuntimeError):
    """Raised when a reproducibility audit check fails."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_manifest(strict: bool = False) -> list[str]:
    """Validate hashes for files already listed in MANIFEST_SHA256.csv.

    The default mode is intended for development branches and CI: it validates
    archived data, code, figures and OpenDSS files while allowing README and
    reproduction-note edits before the DOI manifest is regenerated. Use
    ``--strict`` for release-candidate archives; strict mode checks every listed
    file and fails if tracked release-like files are absent from the manifest.
    """

    if not MANIFEST.exists():
        raise AuditFailure("MANIFEST_SHA256.csv is missing")

    manifest = pd.read_csv(MANIFEST)
    required_columns = {"path", "sha256", "bytes"}
    if set(manifest.columns) != required_columns:
        raise AuditFailure(f"Manifest columns must be {sorted(required_columns)}")

    errors: list[str] = []
    manifest_paths = set(manifest["path"].astype(str))
    development_mutable_paths = {"README.md", "docs/reproduction.md"}
    for row in manifest.itertuples(index=False):
        rel = str(row.path)
        if not strict and rel in development_mutable_paths:
            continue
        path = ROOT / rel
        if not path.exists():
            errors.append(f"missing manifest file: {rel}")
            continue
        if path.stat().st_size != int(row.bytes):
            errors.append(f"byte-count mismatch: {rel}")
        actual = _sha256(path)
        if actual != row.sha256:
            errors.append(f"sha256 mismatch: {rel}")

    if strict:
        tracked_extensions = {".py", ".md", ".csv", ".json", ".yml", ".yaml", ".dss", ".cff", ".txt"}
        unmanifested = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(ROOT))
            if rel.startswith(".git/") or rel.startswith("reproduced/"):
                continue
            if path.suffix in tracked_extensions and rel not in manifest_paths:
                unmanifested.append(rel)
        if unmanifested:
            errors.append("unmanifested release files: " + ", ".join(sorted(unmanifested)))

    return errors


def check_reference_efficiency() -> None:
    df = pd.read_csv(DATA / "efficiency_reference_case_v3.csv").set_index("architecture")
    required = {
        "Traditional AC",
        "Local SST",
        "Subtransmission DC backbone",
        "Local SST 99pct sensitivity",
    }
    missing = required - set(df.index)
    if missing:
        raise AuditFailure(f"efficiency reference missing rows: {sorted(missing)}")

    if not df.loc["Subtransmission DC backbone", "loss_MW"] < df.loc["Traditional AC", "loss_MW"]:
        raise AuditFailure("DC backbone no longer improves on traditional AC reference losses")
    if not df.loc["Subtransmission DC backbone", "loss_MW"] < df.loc["Local SST", "loss_MW"]:
        raise AuditFailure("DC backbone no longer improves on central local-SST reference losses")
    if not df.loc["Local SST 99pct sensitivity", "loss_MW"] < df.loc[
        "Subtransmission DC backbone", "loss_MW"
    ]:
        raise AuditFailure("high-efficiency local-SST counter-case disappeared")


def check_dynamic_robustness() -> None:
    df = pd.read_csv(DATA / "dynamic_robustness_summary_v3.csv").set_index("level")
    expected = {"Traditional AC", "Local SST", "Subtransmission DC backbone"}
    if set(df.index) != expected:
        raise AuditFailure("dynamic robustness summary has unexpected architecture rows")
    if not (df["n_scenarios"] == 3072).all():
        raise AuditFailure("dynamic robustness summary must contain 3,072 cases per architecture")

    ramp = df["median_p99_ramp_pct_load_per_s"]
    voltage = df["median_p95_pcc_voltage_deviation_pct"]
    if not ramp["Subtransmission DC backbone"] < ramp["Local SST"] < ramp["Traditional AC"]:
        raise AuditFailure("dynamic ramp rank ordering changed")
    if not voltage["Subtransmission DC backbone"] < voltage["Local SST"] < voltage["Traditional AC"]:
        raise AuditFailure("dynamic voltage rank ordering changed")


def check_harmonic_robustness() -> None:
    df = pd.read_csv(DATA / "harmonic_robustness_summary_v3.csv")
    arch = df[df["group"] == "architecture"].set_index("level")
    expected = {"Traditional AC", "Local SST", "Subtransmission DC backbone"}
    if set(arch.index) != expected:
        raise AuditFailure("harmonic robustness summary has unexpected architecture rows")
    if not (arch["cases"] == 3072).all():
        raise AuditFailure("harmonic robustness summary must contain 3,072 cases per architecture")

    median = arch["median_p95_thdv_pct"]
    exceed = arch["fraction_exceeding_5pct_guide"]
    if not median["Subtransmission DC backbone"] < median["Local SST"] < median["Traditional AC"]:
        raise AuditFailure("harmonic median rank ordering changed")
    if exceed["Subtransmission DC backbone"] != 0:
        raise AuditFailure("DC backbone exceeds the 5% planning guide in robustness summary")


def check_opendss_log() -> None:
    log_path = OPENDSS / "true_opendss_run_log_v3.json"
    csv_path = DATA / "true_opendss_harmonic_thdv_monte_carlo_v3.csv"
    if not log_path.exists() or not csv_path.exists():
        raise AuditFailure("direct OpenDSS archived run log or CSV is missing")

    log = json.loads(log_path.read_text())
    df = pd.read_csv(csv_path)
    computed = df.groupby("architecture")["thdv_pct"].quantile(0.95).to_dict()
    for key, value in computed.items():
        logged = float(log["p95_thdv_pct"][key])
        if abs(logged - float(value)) > 1e-12:
            raise AuditFailure(f"OpenDSS p95 mismatch for {key}: log={logged}, csv={value}")
    if not computed["dc_backbone"] < computed["local_sst"] < computed["traditional_ac"]:
        raise AuditFailure("direct OpenDSS rank ordering changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail if release-like files are absent from the manifest")
    args = parser.parse_args()

    errors = check_manifest(strict=args.strict)
    checks = [
        check_reference_efficiency,
        check_dynamic_robustness,
        check_harmonic_robustness,
        check_opendss_log,
    ]
    for check in checks:
        try:
            check()
        except Exception as exc:  # pragma: no cover - explicit CLI failure path
            errors.append(f"{check.__name__}: {exc}")

    if errors:
        print("REPRODUCIBILITY AUDIT FAILED")
        for err in errors:
            print(f"- {err}")
        return 1

    print("REPRODUCIBILITY AUDIT PASSED")
    print("Checked manifest hashes, reference efficiency, dynamic robustness, harmonic robustness, and OpenDSS log consistency.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
