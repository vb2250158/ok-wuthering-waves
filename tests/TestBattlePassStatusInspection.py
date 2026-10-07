"""Execute the read-only source branch with inert IO; no game is started."""
import ast
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

from tests.TestDailyProgressInspection import (
    DailyHarness, MultiAccountHarness, INSPECTION_ONLY, INSPECTION_ACCOUNT,
    REWARD_STATUS_ONLY, BATTLE_PASS_STATUS_ONLY,
)


def inspection_method(name='inspect_battle_pass_status'):
    path = Path(__file__).parents[1] / 'src/task/DailyTask.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DailyTask')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    scope = {'re': re}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    return scope[name]


class TestBattlePassStatusInspection(unittest.TestCase):
    def test_mode_enters_only_the_status_branch(self):
        task = DailyHarness(True)
        task.config = {BATTLE_PASS_STATUS_ONLY: True}
        task.inspect_battle_pass_status = lambda: task.calls.append('bp-status') or True
        self.assertTrue(task.run())
        self.assertEqual(task.calls, ['validate', 'base', 'main', 'bp-status', 'main'])

    def test_conflicting_modes_reject_before_any_input(self):
        for other in (INSPECTION_ONLY, REWARD_STATUS_ONLY):
            task = DailyHarness(True)
            task.config = {BATTLE_PASS_STATUS_ONLY: True, other: True}
            with self.assertRaisesRegex(ValueError, 'one daily inspection'):
                task.run()
            self.assertEqual(task.calls, [])

    def test_existing_saved_selector_precedes_observation(self):
        task = MultiAccountHarness()
        task.config = {BATTLE_PASS_STATUS_ONLY: True, INSPECTION_ACCOUNT: 'fixture-account'}
        task.run()
        self.assertLess(task.calls.index('select-account'), task.calls.index('inspect'))
        self.assertEqual(task.calls.count('inspect'), 1)

    def harness(self, *, opened=True, pages=None, click_error=False):
        calls = []
        pages = iter(pages if pages is not None else [
            [SimpleNamespace(name='电台任务')], *[[SimpleNamespace(name='先约电台')]] * 7,
        ])
        def click(x, y, **kw):
            calls.append(('click', x, y))
            if click_error:
                raise RuntimeError('inert input failure')
        def ocr(*args, **kwargs):
            calls.append(('ocr', *args))
            return next(pages)
        task = SimpleNamespace(
            send_key_down=lambda key: calls.append(('down', key)),
            send_key_up=lambda key: calls.append(('up', key)),
            sleep=lambda _seconds: None, click_relative=click,
            swipe_relative=lambda *args, **kwargs: calls.append(('swipe', args, kwargs)),
            wait_ocr=lambda *args, **kwargs: opened, ocr=ocr,
            info_set=lambda *args: None,
        )
        task.inspect_battle_pass_page = inspection_method('inspect_battle_pass_page').__get__(task)
        return task, calls

    def test_navigation_never_touches_claim_or_purchase_controls(self):
        task, calls = self.harness()
        self.assertTrue(inspection_method()(task))
        self.assertEqual([c for c in calls if c[0] == 'click'], [
            ('click', 0.86, 0.05), ('click', 0.04, 0.3), ('click', 0.04, 0.17),
        ])
        self.assertEqual([c for c in calls if c[0] == 'ocr'], [
            ('ocr', 0.02, 0.02, 0.98, 0.95),
        ] * 8)
        self.assertEqual([c for c in calls if c[0] == 'swipe'], [
            ('swipe', (0.28, 0.45, 0.63, 0.45), {'duration': 0.6, 'settle_time': 1}),
        ] * 6)

    def test_unreadable_reward_history_stops_the_bounded_sweep(self):
        task, calls = self.harness(pages=[
            [SimpleNamespace(name='电台任务')], [SimpleNamespace(name='先约电台')], [],
        ])
        self.assertFalse(inspection_method()(task))
        self.assertEqual(len([c for c in calls if c[0] == 'swipe']), 1)

    def test_invalid_history_request_rejects_before_input(self):
        for page, scroll_back in (('tasks', True), ('rewards', 'yes')):
            task, calls = self.harness()
            with self.assertRaisesRegex(ValueError, 'Only reward history'):
                task.inspect_battle_pass_page(page, scroll_back=scroll_back)
            self.assertEqual(calls, [])

    def test_unopened_page_stops_before_tasks_and_rewards(self):
        task, calls = self.harness(opened=False)
        self.assertFalse(inspection_method()(task))
        self.assertEqual([c for c in calls if c[0] == 'click'], [('click', 0.86, 0.05)])
        self.assertFalse(any(c[0] == 'ocr' for c in calls))

    def test_both_observed_pages_must_contain_the_page_anchor(self):
        for pages in ([[], [SimpleNamespace(name='先约电台')]],
                      [[SimpleNamespace(name='电台任务')], [SimpleNamespace(name='other page')]],
                      [[SimpleNamespace(name='先约电台')], [SimpleNamespace(name='先约电台')]],
                      [[SimpleNamespace(name='电台任务')], [SimpleNamespace(name='电台任务')]]):
            task, _calls = self.harness(pages=pages)
            self.assertFalse(inspection_method()(task))

    def test_alt_is_released_even_when_navigation_raises(self):
        task, calls = self.harness(click_error=True)
        with self.assertRaisesRegex(RuntimeError, 'inert input failure'):
            inspection_method()(task)
        self.assertEqual(calls[-1], ('up', 'alt'))

    def test_unknown_named_page_rejects_before_input(self):
        task, calls = self.harness()
        with self.assertRaisesRegex(ValueError, 'Unknown battle pass'):
            task.inspect_battle_pass_page('purchase')
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
