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


def inspection_method():
    path = Path(__file__).parents[1] / 'src/task/DailyTask.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DailyTask')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'inspect_battle_pass_status')
    scope = {'re': re}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    return scope['inspect_battle_pass_status']


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
        pages = iter(pages or [[SimpleNamespace(name='先约电台')]] * 2)
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
            wait_ocr=lambda *args, **kwargs: opened, ocr=ocr,
            info_set=lambda *args: None,
        )
        return task, calls

    def test_navigation_never_touches_claim_or_purchase_controls(self):
        task, calls = self.harness()
        self.assertTrue(inspection_method()(task))
        self.assertEqual([c for c in calls if c[0] == 'click'], [
            ('click', 0.86, 0.05), ('click', 0.04, 0.3), ('click', 0.04, 0.17),
        ])
        self.assertEqual([c for c in calls if c[0] == 'ocr'], [
            ('ocr', 0.02, 0.02, 0.98, 0.95), ('ocr', 0.02, 0.02, 0.98, 0.95),
        ])

    def test_unopened_page_stops_before_tasks_and_rewards(self):
        task, calls = self.harness(opened=False)
        self.assertFalse(inspection_method()(task))
        self.assertEqual([c for c in calls if c[0] == 'click'], [('click', 0.86, 0.05)])
        self.assertFalse(any(c[0] == 'ocr' for c in calls))

    def test_both_observed_pages_must_contain_the_page_anchor(self):
        for pages in ([[], [SimpleNamespace(name='先约电台')]],
                      [[SimpleNamespace(name='先约电台')], [SimpleNamespace(name='other page')]]):
            task, _calls = self.harness(pages=pages)
            self.assertFalse(inspection_method()(task))

    def test_alt_is_released_even_when_navigation_raises(self):
        task, calls = self.harness(click_error=True)
        with self.assertRaisesRegex(RuntimeError, 'inert input failure'):
            inspection_method()(task)
        self.assertEqual(calls[-1], ('up', 'alt'))


if __name__ == '__main__':
    unittest.main()
