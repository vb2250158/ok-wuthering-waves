"""Actual native entry methods with inert UI: never claim to obtain a read."""
import re
import types
import unittest

from TestFirstAccountConfirmation import make_task, WaitFailedException, MODES
from TestReadOnlyReviewRegressions import Probe, bind, method, budget_env


def monthly_probe(present=True):
    task = Probe()
    task.logged_in = False
    task.debug = False
    task.monthly_present = present
    task.monthly_clicks = 0
    task.validate_additional_tasks = lambda: None
    task.in_team_and_world = lambda: not task.monthly_present
    task.in_realm = lambda: False
    task.find_monthly_card = lambda: object() if task.monthly_present else None
    task.find_one = lambda *a, **k: None
    task.ocr = lambda **k: []
    task.box_of_screen = lambda *a, **k: None
    task.find_boxes = lambda *a, **k: []
    task.set_check_monthly_card = lambda **k: None
    def click(*args, **kwargs):
        task.monthly_clicks += 1
        task.monthly_present = False
    task.click_relative = click
    task.wait_until = lambda condition, **kwargs: condition()
    for name in ('ensure_main', 'is_main', 'wait_login', 'handle_monthly_card'):
        bind(task, 'BaseWWTask.py', 'BaseWWTask', name, LOGIN_TEXTS='login', re=re,
             Labels=types.SimpleNamespace(switch_account='switch_account'))
    return task


class ReadOnlyEntryBoundaryTests(unittest.TestCase):
    def test_all_read_modes_block_monthly_on_entry_and_return(self):
        names = ('inspect_daily_progress', 'inspect_daily_reward_status',
                 'inspect_battle_pass_status', 'inspect_current_state')
        run = method('DailyTask.py', 'DailyTask', 'run', configured_budget=budget_env['configured_budget'],
                     DAILY_PROGRESS_INSPECTION_ONLY=MODES[0], DAILY_REWARD_STATUS_INSPECTION_ONLY=MODES[1],
                     BATTLE_PASS_STATUS_INSPECTION_ONLY=MODES[2], CURRENT_STATE_INSPECTION=MODES[3],
                     WWOneTimeTask=types.SimpleNamespace(run=lambda task: None))
        for mode, name in zip(MODES, names):
            for boundary in ('entry', 'return'):
                with self.subTest(mode=mode, boundary=boundary):
                    task = monthly_probe(present=boundary == 'entry')
                    task.config = {mode: True}
                    def inspect():
                        task.actions.append('inspection')
                        task.monthly_present = True
                        return True
                    setattr(task, name, inspect)
                    with self.assertRaisesRegex(RuntimeError, 'readonly_inspection_reward_page_blocked'):
                        run(task)
                    self.assertTrue(task.readonly_inspection)
                    self.assertEqual(task.monthly_clicks, 0)
                    self.assertEqual(task.actions, [] if boundary == 'entry' else ['inspection'])

    def test_multi_account_login_carries_policy_before_daily_task(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                label = 'exact0****@example.test'
                task, _ = make_task(selected=(), visible=(label,), current=label, location='login',
                                    inspection=mode, inspection_target=label)
                task.find_monthly_card = lambda: object()
                task.click_relative = lambda *a, **k: self.fail('monthly reward click')
                task.in_realm = lambda: False
                for name in ('ensure_main', 'is_main', 'wait_login', 'handle_monthly_card'):
                    bind(task, 'BaseWWTask.py', 'BaseWWTask', name)
                with self.assertRaisesRegex(WaitFailedException, 'account_login_unconfirmed') as raised:
                    task.run()
                self.assertIn('readonly_inspection_reward_page_blocked', str(raised.exception.__cause__))
                self.assertTrue(task.readonly_inspection)
                self.assertEqual(task.daily_calls, [])
                self.assertIsNone(task.observed_identity)
                self.assertTrue(task.mouse.enabled)

    def test_lookalike_accounts_never_reach_login_or_daily_for_any_read_mode(self):
        pairs = [('ab0****@example.test', 'abo****@example.test'),
                 ('ab****@example.con', 'ab****@example.com'),
                 ('AB****@example.test', 'ab****@example.test'),
                 ('ß****@example.test', 'ss****@example.test')]
        for mode in MODES:
            for mechanism in ('combo', 'ocr'):
                for wanted, actual in pairs:
                    with self.subTest(mode=mode, mechanism=mechanism, wanted=wanted):
                        task, _ = make_task(selected=(), visible=(actual,), current=actual, location='login',
                                            mode=mechanism, inspection=mode, inspection_target=wanted)
                        with self.assertRaises(WaitFailedException):
                            task.run()
                        self.assertEqual(task.daily_calls, [])
                        self.assertNotIn(('click', 'login'), task.trace)
                        self.assertIsNone(task.observed_identity)

    def test_ordinary_monthly_handler_remains_explicitly_outside_read_mode(self):
        task = monthly_probe()
        task.readonly_inspection = False
        self.assertTrue(task.handle_monthly_card())
        self.assertEqual(task.monthly_clicks, 2)

