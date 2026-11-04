import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from rain_alert import rain_alert, alert_text, TZ

NOW = datetime(2026, 11, 4, 18, 17, tzinfo=TZ)


def payload(total=21):
    start = NOW.replace(minute=0)
    return dict(timezone="America/Sao_Paulo", latitude=-30, longitude=-51.125,
                hourly_units={"precipitation": "mm"},
                hourly={"time": [(start + timedelta(hours=i)).isoformat() for i in range(0, 25)],
                        "precipitation": [999] + [total] + [0] * 23},
                daily_units={"precipitation_sum": "mm", "wind_gusts_10m_max": "km/h"},
                daily={"time": ["2026-11-04", "2026-11-05", "2026-11-06"],
                       "precipitation_sum": [0, 0, 0], "wind_gusts_10m_max": [0, 0, 0]})


class RainTests(unittest.TestCase):
    def test_inclusive_threshold(self):
        for value, expected in [(0, False), (19.99, False), (20, True), (20.01, True), (21, True)]:
            with self.subTest(value=value):
                self.assertEqual(rain_alert(payload(value), NOW)["triggered"], expected)

    def test_decimal_boundary(self):
        p = payload(0)
        p["hourly"]["precipitation"][1:13] = [1.7] * 10 + [1.5] * 2
        self.assertTrue(rain_alert(p, NOW)["triggered"])

    def test_midnight_and_end_timestamp(self):
        a = rain_alert(payload(), NOW)
        self.assertEqual(a["total_mm"], 21)  # 999 at 18:00 belongs to the PAST hour
        self.assertEqual(a["end"], "2026-11-05T06:00:00-03:00")
        self.assertIn("hora em curso", alert_text(a))

    def test_outside_window(self):
        p = payload(0)
        p["hourly"]["precipitation"][13] = 100
        self.assertFalse(rain_alert(p, NOW)["triggered"])

    def test_invalid_data(self):
        for value in [None, -1, float("nan"), float("inf"), True, "21"]:
            p = payload()
            p["hourly"]["precipitation"][4] = value
            with self.subTest(value=value):
                a = rain_alert(p, NOW)
                self.assertEqual(a["status"], "unavailable")
                self.assertIsNone(a["triggered"])

    def test_schema_and_coverage(self):
        variants = []
        p = payload(); p["timezone"] = "GMT"; variants.append(p)
        p = payload(); p["longitude"] = 0; variants.append(p)
        p = payload(); p["hourly_units"]["precipitation"] = "inch"; variants.append(p)
        p = payload(); p["hourly"]["time"][3] = p["hourly"]["time"][2]; variants.append(p)
        p = payload(); del p["hourly"]["time"][4]; del p["hourly"]["precipitation"][4]; variants.append(p)
        variants.append({})
        for p in variants:
            self.assertEqual(rain_alert(p, NOW)["status"], "unavailable")
        self.assertEqual(rain_alert(payload(), NOW + timedelta(days=3))["status"], "unavailable")

    def test_local_and_utc(self):
        p = payload()
        p["hourly"]["time"] = [s[:19] for s in p["hourly"]["time"]]
        self.assertEqual(rain_alert(p, NOW)["total_mm"], 21)
        self.assertEqual(rain_alert(p, NOW.astimezone(__import__('datetime').timezone.utc))["total_mm"], 21)

    def test_robot_integration(self):
        import robot
        f = robot.classify_forecast(payload(), NOW)
        self.assertEqual(f["level"], "amarelo")
        self.assertIn("ALERTA", f["reasons"][0])
        aviation = dict(status="ok", metar=[{}], taf=[{}])
        self.assertEqual(robot.determine_collection_reliability([], {"status": "ok"}, aviation, f)["reliability"], "confiavel")
        aviation["taf"] = []
        self.assertEqual(robot.determine_collection_reliability([], {"status": "ok"}, aviation, f)["reliability"], "insuficiente")
        self.assertEqual(robot.classify_keywords("alerta vermelho evacuação El Niño", {"layer": "tactical", "regional_scope": True})["level"], "não classificado")

    def test_daily_null_does_not_crash_or_pass(self):
        import robot
        p = payload(); p["daily"]["precipitation_sum"][0] = None
        self.assertEqual(robot.classify_forecast(p, NOW)["data_status"], "unavailable")

    def test_rain_mode_notifications_mocked(self):
        import robot
        for total, sends in [(19.99, 0), (20, 1), (21, 1)]:
            with patch.object(robot, "collect_official_data", return_value={}), patch.object(robot, "Path"), patch.dict("os.environ", {"RUN_MODE": "rain_alert"}), patch.object(robot, "ensure_dirs"), patch.object(robot, "save_report"), patch.object(robot, "collect_open_meteo", return_value={"status": "ok", "json": payload(total)}), patch.object(robot, "classify_forecast", return_value=robot.classify_forecast(payload(total), NOW)), patch.object(robot, "notify_ntfy") as notify:
                robot.main()
                self.assertEqual(notify.call_count, sends)

    def test_missing_notification_configuration(self):
        import robot
        with patch.object(robot, "collect_official_data", return_value={}), patch.object(robot, "Path"), patch.dict("os.environ", {"RUN_MODE": "rain_alert"}), patch.object(robot, "ensure_dirs"), patch.object(robot, "save_report"), patch.object(robot, "collect_open_meteo", return_value={"status": "ok", "json": payload()}), patch.object(robot, "classify_forecast", return_value=robot.classify_forecast(payload(), NOW)), patch.object(robot, "notify_ntfy", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "NTFY_TOPIC"):
                robot.main()

    def test_unavailable_sends_failure_notice_not_rain_alert(self):
        import robot
        f = robot.classify_forecast({}, NOW)
        with patch.object(robot, "collect_official_data", return_value={}), patch.object(robot, "Path"), patch.dict("os.environ", {"RUN_MODE": "rain_alert"}), patch.object(robot, "ensure_dirs"), patch.object(robot, "save_report"), patch.object(robot, "collect_open_meteo", return_value={"status": "error", "json": {}}), patch.object(robot, "classify_forecast", return_value=f), patch.object(robot, "notify_ntfy") as notify:
            with self.assertRaisesRegex(RuntimeError, "indisponível"):
                robot.main()
            self.assertEqual(notify.call_count,1)
            self.assertIn("FALHA",notify.call_args.args[0])
            self.assertIn("NÃO SIGNIFICAM AUSÊNCIA DE RISCO",notify.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
