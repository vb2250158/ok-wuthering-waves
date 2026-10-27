import ast
import os
from pathlib import Path
from types import MethodType, SimpleNamespace
import unittest

from TestFirstAccountConfirmation import make_task, MODES
from TestStaminaHardCap import method


class Cancelled(Exception):
    pass


class PartialFailureTests(unittest.TestCase):
    def daily(self, values=(120, 60, 80)):
        task = SimpleNamespace(config={MODES[3]: True}, actions=[], info={})
        task.validate_additional_tasks = lambda: None
        task.ensure_main = lambda **kwargs: task.actions.append('main')
        task.info_set = lambda key, value: task.info.__setitem__(key, value)

        def reader(name, value):
            def read():
                task.actions.append(name)
                if isinstance(value, Exception):
                    raise value
                return value
            return read

        for name, value in zip(('waveplates', 'consumption', 'activity'), values):
            setattr(task, 'read_current_state_' + name, reader(name, value))
        inspect = method('DailyTask.py', 'DailyTask', 'inspect_current_state')
        task.inspect_current_state = MethodType(inspect, task)
        run = method('DailyTask.py', 'DailyTask', 'run',
                     configured_budget=lambda config: None,
                     CURRENT_STATE_INSPECTION=MODES[3], DAILY_PROGRESS_INSPECTION_ONLY=MODES[0],
                     DAILY_REWARD_STATUS_INSPECTION_ONLY=MODES[1], BATTLE_PASS_STATUS_INSPECTION_ONLY=MODES[2],
                     WWOneTimeTask=SimpleNamespace(run=lambda task: None))
        task.run = MethodType(run, task)
        return task

    def test_partial_helper_keeps_valid_fields_and_reads_past_bad_middle(self):
        task = self.daily((120, ValueError('missing row'), 80))
        self.assertFalse(task.inspect_current_state())
        self.assertEqual(task.current_state_snapshot,
                         dict(currentWaveplates=120, dailyConsumed=None, dailyActivity=80))
        self.assertEqual(task.actions, ['waveplates', 'consumption', 'activity'])
        self.assertEqual(task.info['current state dailyConsumed'], 'unreadable')

    def test_each_missing_field_fails_after_return_without_business_actions(self):
        names = ('currentWaveplates', 'dailyConsumed', 'dailyActivity')
        for index, name in enumerate(names):
            with self.subTest(field=name):
                values = [120, 60, 80]
                values[index] = ValueError('unreadable')
                task = self.daily(values)
                with self.assertRaisesRegex(ValueError, 'incomplete: unreadable fields: ' + name):
                    task.run()
                self.assertEqual(task.actions, ['main', 'waveplates', 'consumption', 'activity', 'main'])
                self.assertTrue(task.readonly_inspection)
                self.assertIsNone(task.current_state_snapshot[name])

    def test_all_missing_fields_are_reported(self):
        task = self.daily([ValueError('unreadable')] * 3)
        with self.assertRaisesRegex(ValueError, 'currentWaveplates, dailyConsumed, dailyActivity'):
            task.run()
        self.assertEqual(list(task.current_state_snapshot.values()), [None, None, None])

    def test_zero_is_readable_not_missing(self):
        task = self.daily((0, 0, 0))
        self.assertTrue(task.run())
        self.assertEqual(list(task.current_state_snapshot.values()), [0, 0, 0])

    def test_rerun_replaces_old_snapshot(self):
        task = self.daily()
        self.assertTrue(task.run())
        task.read_current_state_consumption = lambda: None
        with self.assertRaisesRegex(ValueError, 'dailyConsumed'):
            task.run()
        self.assertIsNone(task.current_state_snapshot['dailyConsumed'])
        task.read_current_state_consumption = lambda: 0
        self.assertTrue(task.run())
        self.assertEqual(task.current_state_snapshot['dailyConsumed'], 0)

    def test_cancellation_and_unexpected_error_are_not_converted(self):
        for error in (Cancelled('stop'), RuntimeError('navigation failed')):
            with self.subTest(error=type(error).__name__):
                task = self.daily((120, error, 80))
                with self.assertRaises(type(error)) as raised:
                    task.run()
                self.assertIs(raised.exception, error)
                self.assertEqual(task.actions, ['main', 'waveplates', 'consumption'])

    def test_return_navigation_failure_is_not_success(self):
        task = self.daily((120, ValueError('missing row'), 80))
        def ensure_main(**kwargs):
            if not kwargs:
                raise RuntimeError('return blocked')
        task.ensure_main = ensure_main
        with self.assertRaisesRegex(RuntimeError, 'return blocked'):
            task.run()
        self.assertIsNone(task.current_state_snapshot['dailyConsumed'])

    def test_ordinary_daily_still_returns_none(self):
        task = self.daily()
        task.config = {}
        task.support_tasks = ['tacet']
        task.open_daily = lambda: (180, True)
        task.claim_daily = lambda: task.actions.append('daily')
        task.claim_mail = lambda: task.actions.append('mail')
        task.claim_battle_pass = lambda: task.actions.append('pass')
        task.run_additional_tasks = lambda: task.actions.append('additional')
        task.sleep = lambda seconds: None
        task.log_info = lambda *args, **kwargs: None
        task.run.__func__.__globals__.update(ADDITIONAL_TASKS='additional', AUTO_FARM_NIGHTMARE_NEST='nest')
        self.assertIsNone(task.run())
        self.assertEqual(task.actions, ['main', 'daily', 'mail', 'pass', 'additional'])

    def test_other_inspection_false_results_are_not_reinterpreted(self):
        for mode, name in zip(MODES[:3], ('inspect_daily_progress', 'inspect_daily_reward_status',
                                        'inspect_battle_pass_status')):
            with self.subTest(mode=mode):
                task = self.daily()
                task.config = {mode: True}
                setattr(task, name, lambda: False)
                self.assertFalse(task.run())
                self.assertEqual(task.actions, ['main', 'main'])

    @unittest.skipUnless(os.environ.get('OK_SCRIPT_TASK_SOURCE'), 'set OK_SCRIPT_TASK_SOURCE for SDK AST replay')
    def test_real_sdk_boundary_does_not_mark_incomplete_account_done(self):
        source = Path(os.environ['OK_SCRIPT_TASK_SOURCE'])
        tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        sdk_method = next(node for owner in tree.body if isinstance(owner, ast.ClassDef)
                          for node in owner.body if isinstance(node, ast.FunctionDef)
                          and node.name == 'run_task_by_class')
        scope = {}
        exec(compile(ast.Module(body=[sdk_method], type_ignores=[]), str(source), 'exec'), scope)
        for values, succeeds in (((120, ValueError('missing row'), 80), False), ((120, 0, 80), True)):
            with self.subTest(succeeds=succeeds):
                multi, _ = make_task(inspection=MODES[3], inspection_target='qa****@example.test')
                daily = self.daily(values)
                daily.config['Daily Progress Inspection Account'] = 'qa****@example.test'
                daily.info = {'original': True}
                multi.get_task_by_class = lambda cls: daily
                multi._prepare_first_account_login = lambda: None
                multi._select_and_login_account = lambda: 'qa****@example.test'
                multi.run_task_by_class = MethodType(scope['run_task_by_class'], multi)
                if succeeds:
                    self.assertIsNone(multi.run())
                    self.assertEqual(multi.done_set, {'qa****@example.test'})
                else:
                    with self.assertRaisesRegex(ValueError, 'current_state_inspection_incomplete'):
                        multi.run()
                    self.assertEqual(multi.done_set, set())
                self.assertEqual(daily.info, {'original': True})


if __name__ == '__main__':
    unittest.main()
