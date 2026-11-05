"""Offline regressions for final tactical levels and municipal payload paging."""
import copy
import csv
import random
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from notification_state import NotificationState
from operational_notices import civil_defense_notice
from test_notification_state import forecast
from test_operational_notices import alert, municipal, regions
from test_rain_alert import NOW, payload


def general_notice(level, rain_only=False):
    return dict(title='Radar POA - ' + level.upper(), body='Resumo de teste',
                level=level, rain_only=rain_only)


def long_municipal(grouped=False):
    rows = regions()
    for index, row in enumerate(rows):
        row['name'] = f'(R{index + 1:02}) ' + 'á' * 90
        row['alert'] = alert(
            id=1 if grouped else index,
            criticality='extreme_risk' if index == 16 and not grouped else 'attention_notice',
            alert_description='Descrição longa ' * 400,
            alert_types=[dict(name=f'Tipo {i}: ' + 'ç' * 100) for i in range(30)] if grouped else [dict(name='Chuva intensa')],
        )
    return municipal(rows)


class GeneralLevelRegressions(unittest.TestCase):
    def test_final_tactical_levels_and_downgrades_notify_once(self):
        state = NotificationState()
        notify = Mock(return_value=True)
        f = forecast(0)
        state.general(f, general_notice('verde'), NOW, notify)
        notify.assert_not_called()
        for index, level in enumerate(['amarelo', 'laranja', 'vermelho', 'amarelo', 'verde'], 1):
            with self.subTest(level=level, transition=index):
                state.general(f, general_notice(level), NOW, notify)
                state.general(f, general_notice(level), NOW, notify)
                self.assertEqual(notify.call_count, index)
                self.assertEqual(state.data['events']['general']['signature']['level'], level)

    def test_failed_tactical_update_preserves_baseline_and_retries(self):
        state = NotificationState()
        f = forecast(0)
        state.general(f, general_notice('verde'), NOW, Mock(return_value=True))
        baseline = copy.deepcopy(state.data)
        for failure in [False, RuntimeError('private transport detail')]:
            notify = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
            result = state.general(f, general_notice('vermelho'), NOW, notify)
            self.assertEqual(result[0]['status'], 'failed')
            self.assertEqual(state.data, baseline)
        notify = Mock(return_value=True)
        self.assertEqual(state.general(f, general_notice('vermelho'), NOW, notify)[0]['status'], 'sent')
        self.assertEqual(state.general(f, general_notice('vermelho'), NOW, notify)[0]['status'], 'suppressed')

    def test_history_uses_same_final_tactical_level_as_notice(self):
        f = forecast(0)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.csv'
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.DictWriter(stream, fieldnames=['timestamp', 'tactical_level', 'p24_max_mm', 'p72_max_mm', 'gust_max_kmh'])
                writer.writeheader()
                writer.writerow(dict(timestamp=NOW.isoformat(), tactical_level='vermelho',
                                     **{key: f[key] for key in ['p24_max_mm', 'p72_max_mm', 'gust_max_kmh']}))
            state = NotificationState(history_path=path)
            notify = Mock(return_value=True)
            state.general(f, general_notice('vermelho'), NOW, notify)
            notify.assert_not_called()

    def test_rain_only_coverage_requires_accepted_primary_alert(self):
        f = forecast(20)
        for accepted in [False, True]:
            with self.subTest(accepted=accepted):
                state = NotificationState()
                state.rain(f, {}, {}, general_notice('laranja'), NOW, Mock(return_value=accepted))
                notify = Mock(return_value=True)
                state.general(f, general_notice('amarelo', rain_only=True), NOW, notify)
                self.assertEqual(notify.call_count, 0 if accepted else 1)
                self.assertEqual(state.data['events']['general'].get('covered_by_rain', False), accepted)

    def test_unrelated_yellow_and_red_tactical_levels_are_not_covered_by_rain(self):
        for level in ['amarelo', 'vermelho']:
            with self.subTest(level=level):
                state = NotificationState()
                f = forecast(20)
                state.rain(f, {}, {}, general_notice('laranja'), NOW, Mock(return_value=True))
                notify = Mock(return_value=True)
                state.general(f, general_notice(level), NOW, notify)
                notify.assert_called_once()

    def test_independent_yellow_after_rain_coverage_retries_and_notifies_once(self):
        state = NotificationState()
        f = forecast(20)
        state.rain(f, {}, {}, general_notice('laranja'), NOW, Mock(return_value=True))
        state.general(f, general_notice('amarelo', rain_only=True), NOW, Mock(return_value=True))
        covered = copy.deepcopy(state.data)
        self.assertEqual(state.general(f, general_notice('amarelo'), NOW, Mock(return_value=False))[0]['status'], 'failed')
        self.assertEqual(state.data, covered)
        notify = Mock(return_value=True)
        self.assertEqual(state.general(f, general_notice('amarelo'), NOW, notify)[0]['status'], 'sent')
        self.assertEqual(state.general(f, general_notice('amarelo'), NOW, notify)[0]['status'], 'suppressed')
        notify.assert_called_once()

    def test_high_tactical_downgrade_not_hidden_by_rain_coverage(self):
        state = NotificationState()
        f = forecast(20)
        notify = Mock(return_value=True)
        state.general(f, general_notice('vermelho'), NOW, notify)
        state.rain(f, {}, {}, general_notice('laranja'), NOW, Mock(return_value=True))
        self.assertEqual(state.general(f, general_notice('amarelo', rain_only=True), NOW, notify)[0]['status'], 'sent')
        self.assertEqual(notify.call_count, 2)

    def test_rain_only_poll_preserves_independently_accepted_baseline(self):
        state = NotificationState()
        f = forecast(20)
        notify = Mock(return_value=True)
        state.general(f, general_notice('amarelo'), NOW, notify)
        state.rain(f, {}, {}, general_notice('laranja'), NOW, Mock(return_value=True))
        accepted_general = copy.deepcopy(state.data['events']['general'])
        changed = copy.deepcopy(f)
        changed['p24_max_mm'] += 4
        state.general(changed, general_notice('amarelo', rain_only=True), NOW, notify)
        self.assertEqual(state.data['events']['general'], accepted_general)
        self.assertEqual(state.general(f, general_notice('amarelo'), NOW, notify)[0]['status'], 'suppressed')
        changed['p24_max_mm'] = f['p24_max_mm'] + max(5, f['p24_max_mm'] * .25)
        self.assertEqual(state.general(changed, general_notice('amarelo'), NOW, notify)[0]['status'], 'sent')
        self.assertEqual(notify.call_count, 2)

    def test_accepted_rain_only_fallback_does_not_hide_later_independent_yellow(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            state = NotificationState(path)
            f = forecast(20)
            state.rain(f, {}, {}, general_notice('laranja'), NOW, Mock(return_value=False))
            self.assertEqual(state.general(f, general_notice('amarelo', rain_only=True), NOW, Mock(return_value=True))[0]['status'], 'sent')
            state = NotificationState(path)
            state.rain(f, {}, {}, general_notice('laranja'), NOW, Mock(return_value=True))
            state.general(f, general_notice('amarelo', rain_only=True), NOW, Mock(return_value=True))
            before = copy.deepcopy(state.data)
            result = state.general(f, general_notice('amarelo'), NOW, Mock(return_value=False))
            self.assertEqual(result[0]['status'], 'failed')
            self.assertEqual(state.data, before)
            state = NotificationState(path)
            notify = Mock(return_value=True)
            self.assertEqual(state.general(f, general_notice('amarelo'), NOW, notify)[0]['status'], 'sent')
            self.assertEqual(state.general(f, general_notice('amarelo'), NOW, notify)[0]['status'], 'suppressed')
            notify.assert_called_once()

    def test_main_tracks_external_tactical_changes_with_unchanged_forecast(self):
        import robot
        state = NotificationState()
        with ExitStack() as stack:
            for name in ['ensure_dirs', 'Path', 'save_report', 'save_history', 'create_forecast_chart']:
                stack.enter_context(patch.object(robot, name))
            stack.enter_context(patch('builtins.print'))
            stack.enter_context(patch.object(robot, 'now_brt', return_value=NOW))
            stack.enter_context(patch.object(robot, 'collect_official_data', return_value={}))
            stack.enter_context(patch.object(robot, 'collect_open_meteo', return_value={'status': 'ok', 'json': payload(0)}))
            stack.enter_context(patch.object(robot, 'collect_aviation_weather', return_value={'status': 'ok', 'metar': [{}], 'taf': [{}]}))
            stack.enter_context(patch.object(robot, 'SOURCES', [{}]))
            stack.enter_context(patch.object(robot, 'collect_html_source', return_value={'layer': 'tactical', 'status': 'ok', 'source': 'Fonte simulada'}))
            classify = stack.enter_context(patch.object(robot, 'classify_keywords'))
            notify = stack.enter_context(patch.object(robot, 'notify_ntfy', return_value=True))
            stack.enter_context(patch.dict('os.environ', {'RUN_MODE': 'daily'}))
            for level in ['verde', 'vermelho', 'vermelho', 'amarelo', 'verde']:
                classify.return_value = {'level': level, 'hits': {}}
                robot.main(notification_state=state)
            self.assertEqual([call.args[2] for call in notify.call_args_list], ['vermelho', 'amarelo', 'verde'])


class MunicipalPagingRegressions(unittest.TestCase):
    def test_all_seventeen_groups_are_sent_and_payloads_fit(self):
        product = long_municipal()
        state = NotificationState()
        notify = Mock(return_value=True)
        outcomes = state.municipal(product, NOW, notify)
        self.assertGreater(len(outcomes), 1)
        bodies = [call.args[1] for call in notify.call_args_list]
        self.assertTrue(all(len(body.encode('utf-8')) <= 4096 for body in bodies))
        for group in product['alerts']:
            for region in group['regions']:
                self.assertTrue(any(region['name'] in body for body in bodies), region['order'])
                self.assertIn('municipal:' + str(region['order']), state.data['events'])
        self.assertEqual(state.municipal(product, NOW, notify), [])
        self.assertEqual(notify.call_count, len(outcomes))
        self.assertEqual(notify.call_args_list[0].args[2], 'vermelho')
        self.assertTrue(all(call.args[2] == 'amarelo' for call in notify.call_args_list[1:]))

    def test_failed_page_only_is_retried_after_restart(self):
        product = long_municipal()
        for failure in [False, RuntimeError('private transport detail')]:
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'state.json'
                state = NotificationState(path)
                failed_body, accepted_bodies = [], []
                def first_send(title, body, level):
                    if not failed_body:
                        failed_body.append(body)
                        if isinstance(failure, Exception):
                            raise failure
                        return failure
                    accepted_bodies.append(body)
                    return True
                outcomes = state.municipal(product, NOW, first_send)
                self.assertEqual(outcomes[0]['status'], 'failed')
                self.assertTrue(accepted_bodies)
                for group in product['alerts']:
                    for region in group['regions']:
                        self.assertEqual('municipal:' + str(region['order']) in state.data['events'],
                                         any(region['name'] in body for body in accepted_bodies))
                state = NotificationState(path)
                notify = Mock(return_value=True)
                state.municipal(product, NOW, notify)
                retried = '\n'.join(call.args[1] for call in notify.call_args_list)
                for group in product['alerts']:
                    for region in group['regions']:
                        self.assertEqual(region['name'] in retried, region['name'] in failed_body[0])
                self.assertEqual(len(state.data['events']), 17)

    def test_oversized_group_splits_regions_and_truncates_types_safely(self):
        product = long_municipal(grouped=True)
        self.assertEqual(len(product['alerts']), 1)
        notify = Mock(return_value=True)
        state = NotificationState()
        state.municipal(product, NOW, notify)
        bodies = [call.args[1] for call in notify.call_args_list]
        self.assertTrue(all(len(body.encode('utf-8')) <= 4096 for body in bodies))
        for region in product['alerts'][0]['regions']:
            self.assertTrue(any(region['name'] in body for body in bodies), region['order'])
        self.assertEqual(len(state.data['events']), 17)

    def test_renderer_reports_only_regions_actually_included(self):
        product = long_municipal()
        notice = civil_defense_notice(product, NOW)
        self.assertTrue(notice['region_orders'])
        for group in product['alerts']:
            for region in group['regions']:
                self.assertEqual(region['order'] in notice['region_orders'], region['name'] in notice['body'])

    def test_deterministic_payload_stress_keeps_exact_acceptance_boundaries(self):
        rng = random.Random(20261105)
        for case in range(40):
            with self.subTest(case=case):
                rows = regions()
                for index, row in enumerate(rows):
                    row['name'] = f'(R{index + 1:02}) ' + rng.choice(['á', '🌧', '區']) * rng.randint(1, 94)
                    row['alert'] = alert(
                        id=rng.randrange(4),
                        criticality=rng.choice(['attention_notice', 'high_risk', 'very_high_risk', 'extreme_risk']),
                        alert_description=rng.choice(['a', 'á', '🌧']) * rng.randint(1, 9000),
                        alert_types=[dict(name='Tipo ' + '🌧' * 100) for _ in range(rng.randrange(30))],
                    )
                product = municipal(rows)
                product['status'] = rng.choice(['ok', 'partial'])
                state = NotificationState()
                sent_bodies = []
                def send(title, body, level):
                    sent_bodies.append(body)
                    return len(sent_bodies) % 3 != 2
                outcomes = state.municipal(product, NOW, send)
                included = [order for result in outcomes for order in result['region_orders']]
                self.assertEqual(sorted(included), list(range(1, 18)))
                accepted = {order for result in outcomes if result['accepted'] for order in result['region_orders']}
                self.assertEqual(set(state.data['events']), {'municipal:' + str(order) for order in accepted})
                for body, result in zip(sent_bodies, outcomes):
                    self.assertLessEqual(len(body.encode('utf-8')), 3900)
                    for row in rows:
                        self.assertEqual(row['name'] in body, row['order'] in result['region_orders'])
                retry = state.municipal(product, NOW, Mock(return_value=True))
                self.assertEqual({order for result in retry for order in result['region_orders']}, set(range(1, 18)) - accepted)
                self.assertEqual(state.municipal(product, NOW, Mock(return_value=True)), [])


if __name__ == '__main__':
    unittest.main()
