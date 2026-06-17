from pathlib import Path
import unittest

from aiwf.doctor import run_doctor


class DoctorTests(unittest.TestCase):
    def test_doctor_acceptance_checks_pass(self) -> None:
        project = Path(__file__).resolve().parents[1]
        report = run_doctor(project)

        self.assertTrue(report.ok, report.to_dict())
        self.assertGreaterEqual(len(report.checks), 6)


if __name__ == "__main__":
    unittest.main()

