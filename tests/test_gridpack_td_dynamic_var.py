import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_gridpack_td_dynamic_var as gridpack_td  # noqa: E402


class GridpackTdDynamicVarTest(unittest.TestCase):
    def test_travis150_raw_summary_uses_real_transmission_case(self):
        raw = gridpack_td.DEFAULT_RAW
        if not raw.exists():
            self.skipTest(f"Travis 150 RAW case is not available: {raw}")

        summary = gridpack_td.summarize_raw(raw)

        self.assertEqual(summary["bus_count"], 168)
        self.assertEqual(summary["generator_count"], 39)
        self.assertEqual(summary["online_generator_count"], 30)
        self.assertEqual(summary["branch_count"], 263)
        self.assertEqual(summary["online_branch_count"], 263)
        self.assertLessEqual({branch["from_kv"] for branch in summary["online_branches"]}, {69.0, 230.0})
        self.assertLessEqual({branch["to_kv"] for branch in summary["online_branches"]}, {69.0, 230.0})

    def test_gridpack_input_references_real_raw_dyr_and_fault_branch(self):
        raw = gridpack_td.DEFAULT_RAW
        dyr = gridpack_td.DEFAULT_DYR
        if not raw.exists() or not dyr.exists():
            self.skipTest("Travis 150 RAW/DYR files are not available")

        args = argparse.Namespace(
            fault_branch="137 150",
            poi_bus=150,
            max_watch_generators=4,
            simulation_time_s=2.0,
            gridpack_timestep_s=0.005,
            watch_frequency=1,
        )

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            raw_case, dyr_case = gridpack_td.prepare_gridpack_case_files(raw, dyr, tmp_path)
            input_xml = tmp_path / "gridpack_travis150_dynamic_input.xml"
            watch_csv = tmp_path / "gridpack_travis150_generator_watch.csv"
            watch_generators = gridpack_td.write_gridpack_input(input_xml, raw_case, dyr_case, watch_csv, args)

            xml = input_xml.read_text()
            self.assertIn("<networkConfiguration> 150.RAW </networkConfiguration>", xml)
            self.assertIn("<generatorParameters> 150_gridpack_REECA1_candidate.dyr </generatorParameters>", xml)
            self.assertIn("<faultBranch> 137 150 </faultBranch>", xml)
            self.assertIn("<busID> 150 </busID>", xml)
            self.assertIn("<generatorWatchFileName>gridpack_travis150_generator_watch.csv</generatorWatchFileName>", xml)
            self.assertEqual(len(watch_generators), 4)


if __name__ == "__main__":
    unittest.main()
