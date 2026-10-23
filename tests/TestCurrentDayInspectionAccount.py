"""Exact official inspection entry with synthetic UI; no app import or input."""
from copy import deepcopy
import unittest

from TestFirstAccountConfirmation import A, B, OTHER, MODES, make_task


class TestCurrentDayInspectionAccount(unittest.TestCase):
    def test_every_inspection_selects_only_target_before_login_and_daily(self):
        for inspection in MODES:
            for mode in ('combo', 'ocr'):
                for location in ('world', 'login'):
                    with self.subTest(inspection=inspection, mode=mode, location=location):
                        task, _ = make_task(inspection=inspection, inspection_target=B,
                            current=OTHER, visible=(OTHER, A, B), mode=mode, location=location)
                        before = deepcopy(task.config)
                        task.run()
                        self.assertEqual(task._requested_accounts, (B,))
                        self.assertEqual(task.config, before)
                        self.assertEqual(len(task.daily_calls), 1)
                        self.assertEqual(task.daily_calls[0], dict(actualDisplay=B,
                            observedIdentity=B, inWorld=True, inspection=True))
                        self.assertNotIn(('select', OTHER), task.trace)
                        self.assertNotIn(('select', A), task.trace)
                        # OCR opens the dropdown by clicking its current text;
                        # that click is not a selection/login of the old account.
                        self.assertEqual(task.trace.count(('click', OTHER)), 1 if mode == 'ocr' else 0)
                        self.assertNotIn(('click', A), task.trace)
                        self.assertEqual([x for x in task.trace if x == ('click', 'login')], [('click', 'login')])

    def test_missing_or_invalid_target_fails_before_setup(self):
        for target in ('', None, 9, [], ' a**** ', 'bad\nlabel'):
            with self.subTest(target=target):
                task, _ = make_task(inspection=MODES[0], inspection_target=target)
                with self.assertRaises(ValueError):
                    task.run()
                self.assertEqual(task.trace, [])

    def test_multiple_or_non_boolean_modes_fail_before_setup(self):
        for value in (True, 'false', 1, None):
            with self.subTest(value=value):
                task, _ = make_task(inspection=MODES[0], inspection_target=B)
                task.daily_config[MODES[1]] = value
                with self.assertRaises(ValueError):
                    task.run()
                self.assertEqual(task.trace, [])

    def test_missing_or_ambiguous_target_never_inspects_other_accounts(self):
        for visible in ((OTHER, A), (B, B, OTHER)):
            for mode in ('combo', 'ocr'):
                task, _ = make_task(inspection=MODES[0], inspection_target=B,
                    current=OTHER, visible=visible, mode=mode, location='login')
                with self.assertRaises(Exception):
                    task.run()
                self.assertEqual(task.daily_calls, [])
                self.assertNotIn(('click', 'login'), task.trace)

    def test_failed_identity_world_entry_or_cancel_never_inspects(self):
        for failure in ('reverted', 'identity_missing', 'login_failed', 'login_button_missing', 'cancelled'):
            task, _ = make_task(inspection=MODES[0], inspection_target=B,
                current=OTHER, location='login', failure=failure)
            with self.assertRaises(Exception):
                task.run()
            self.assertEqual(task.daily_calls, [])
            self.assertEqual(task.done_set, set())


if __name__ == '__main__':
    unittest.main()
