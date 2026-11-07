import runpy
import unittest
from pathlib import Path
from unittest.mock import Mock


covering_run = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / ".github/scripts/rain_alert_coverage.py")
)["covering_run"]
RUNS_PATH = "workflows/rain-alert.yml/runs?branch=main&status=success&per_page=20"
HOUR = "2026-11-07T22:"


class RainAlertCoverageTests(unittest.TestCase):
    def test_only_a_successful_real_consultation_in_the_hour_counts(self):
        runs = [{"id": run_id, "updated_at": HOUR + "58:00Z"} for run_id in (4, 3, 2, 1)]
        responses = {RUNS_PATH: {"workflow_runs": runs}}
        for run_id, conclusion, start in (
            (4, "skipped", None),
            (3, "failure", HOUR + "27:00Z"),
            (2, "success", "2026-11-07T21:59:55Z"),
            (1, "success", HOUR + "07:00Z"),
        ):
            step = dict(name="Consultar previsao e avaliar alertas", conclusion=conclusion, started_at=start)
            responses[f"runs/{run_id}/jobs"] = {"jobs": [{"steps": [step]}]}

        self.assertEqual(covering_run(responses.__getitem__, HOUR), 1)

    def test_old_runs_do_not_prevent_a_new_consultation(self):
        get = Mock(return_value={"workflow_runs": [{"id": 1, "updated_at": "2026-11-07T21:59:59Z"}]})

        self.assertIsNone(covering_run(get, HOUR))
        get.assert_called_once_with(RUNS_PATH)


if __name__ == "__main__":
    unittest.main()
