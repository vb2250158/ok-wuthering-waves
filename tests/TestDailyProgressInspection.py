"""Execute the official methods with inert harnesses; never initialize a game."""
import ast
import re
from pathlib import Path
from types import SimpleNamespace
import unittest

from src.task.StaminaBudget import CURRENT_STATE_INSPECTION, configured_budget
from TestFirstAccountConfirmation import make_task, WaitFailedException


INSPECTION_ONLY = 'Daily Progress Inspection Only'
INSPECTION_ACCOUNT = 'Daily Progress Inspection Account'
REWARD_STATUS_ONLY = 'Daily Reward Status Inspection Only'
BATTLE_PASS_STATUS_ONLY = 'Battle Pass Status Inspection Only'


def run_method(filename, classname):
    path = Path(__file__).parents[1] / 'src/task' / filename
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == classname)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
    class Base:
        @staticmethod
        def run(task):
            task.calls.append('base')
    scope = {'WWOneTimeTask': Base, 'DailyTask': object(),
             'DAILY_PROGRESS_INSPECTION_ONLY': INSPECTION_ONLY,
             'DAILY_PROGRESS_INSPECTION_ACCOUNT': INSPECTION_ACCOUNT,
             'DAILY_REWARD_STATUS_INSPECTION_ONLY': REWARD_STATUS_ONLY,
             'BATTLE_PASS_STATUS_INSPECTION_ONLY': BATTLE_PASS_STATUS_ONLY,
             'CURRENT_STATE_INSPECTION': CURRENT_STATE_INSPECTION,
             'configured_budget': configured_budget,
             'ADDITIONAL_TASKS': 'Additional Tasks to Run After Daily Task',
             'AUTO_FARM_NIGHTMARE_NEST': 'Auto Farm all Nightmare Nest'}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    return scope['run']


class DailyHarness:
    def __init__(self, ready):
        self.config = {INSPECTION_ONLY: True}
        self.calls = []
        self.ready = ready
        self.run = run_method('DailyTask.py', 'DailyTask').__get__(self)

    def validate_additional_tasks(self):
        self.calls.append('validate')

    def ensure_main(self, **kwargs):
        self.calls.append('main')

    def open_daily(self):
        self.calls.append('inspect')
        self._daily_points_read_valid = self.ready
        if not self.ready:
            raise ValueError('Daily activity OCR unreadable; refusing to treat it as zero')
        return 180, self.ready

    def inspect_daily_progress(self):
        self.open_daily()
        return self._daily_points_read_valid

    def claim_daily(self):
        raise AssertionError('Inspection must not claim daily rewards')

    def claim_mail(self):
        raise AssertionError('Inspection must not claim mail')

    def claim_battle_pass(self):
        raise AssertionError('Inspection must not claim battle pass rewards')


class MultiAccountHarness:
    def __new__(cls, target='fixture-account', visible=None):
        task, _ = make_task(selected=(), visible=(target,) if visible is None else visible,
                            current=target, location='login', inspection=INSPECTION_ONLY,
                            inspection_target=target)
        task.calls = []
        task.config = task.daily_config
        task.get_task_by_class = lambda _cls: SimpleNamespace(config=task.config)
        select_account = task._select_and_login_account
        run_daily = task.run_task_by_class

        def select():
            task.calls.append('select-account')
            return select_account()

        def inspect(task_class):
            run_daily(task_class)
            task.calls.append('inspect')

        task._select_and_login_account = select
        task.run_task_by_class = inspect
        return task


class TestDailyProgressInspection(unittest.TestCase):
    def test_requested_account_is_inspected_once_without_foreign_business(self):
        task = MultiAccountHarness(target='target-fixture', visible=('foreign-fixture', 'target-fixture'))
        task.run()
        self.assertEqual(task.calls.count('inspect'), 1)
        self.assertEqual(task.done_set, {'target-fixture'})
        self.assertEqual([call['observedIdentity'] for call in task.daily_calls], ['target-fixture'])
        self.assertNotIn(('select', 'foreign-fixture'), task.trace)
        self.assertNotIn(('click', 'foreign-fixture'), task.trace)

    def test_missing_requested_account_fails_without_inspection(self):
        task = MultiAccountHarness(target='missing-fixture', visible=('foreign-fixture',))
        with self.assertRaisesRegex(WaitFailedException, 'account_not_available'):
            task.run()
        self.assertEqual(task.calls.count('inspect'), 0)
        self.assertEqual(task.done_set, set())
        self.assertNotIn(('click', 'login'), task.trace)
        self.assertNotIn(('select', 'foreign-fixture'), task.trace)

    def test_inspection_does_not_claim_or_farm(self):
        task = DailyHarness(True)
        self.assertTrue(task.run())
        self.assertEqual(task.calls, ['validate', 'base', 'main', 'inspect', 'main'])

    def test_unreadable_progress_raises_without_claiming(self):
        task = DailyHarness(False)
        with self.assertRaisesRegex(ValueError, 'Daily activity OCR unreadable'):
            task.run()
        self.assertEqual(task.calls, ['validate', 'base', 'main', 'inspect'])

    def test_first_account_is_selected_before_inspection(self):
        task = MultiAccountHarness()
        task.run()
        self.assertLess(task.calls.index('select-account'), task.calls.index('inspect'))
        self.assertEqual(task.calls.count('inspect'), 1)
        self.assertEqual(task.done_set, {'fixture-account'})
        self.assertEqual(task.daily_calls, [{'actualDisplay': 'fixture-account',
            'observedIdentity': 'fixture-account', 'inWorld': True, 'inspection': True}])

    def test_disabled_mode_keeps_the_original_claim_path(self):
        task = DailyHarness(True)
        task.config[INSPECTION_ONLY] = False
        with self.assertRaisesRegex(AssertionError, 'claim daily rewards'):
            task.run()

    def test_missing_mode_keeps_the_original_claim_path(self):
        task = DailyHarness(True)
        task.config.pop(INSPECTION_ONLY)
        with self.assertRaisesRegex(AssertionError, 'claim daily rewards'):
            task.run()

    def test_points_read_distinguishes_zero_from_unreadable_exception(self):
        path = Path(__file__).parents[1] / 'src/task/DailyTask.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DailyTask')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'get_total_daily_points')
        scope = {'re': re, 'number_re': re.compile(r'\d+')}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
        for texts, expected in [(['0'], 0), (['100'], 100), (['101'], 101), (['120'], 120),
                                ([' 120 '], 120), (['120', '120'], 120),
                                (['-1'], None), (['unreadable'], None), ([], None),
                                (['100', '120'], None)]:
            with self.subTest(texts=texts):
                reads, sleeps, info = [], [], {}

                def ocr(*args, **kwargs):
                    reads.append(kwargs)
                    return [SimpleNamespace(name=text) for text in texts]

                task = SimpleNamespace(ocr=ocr, sleep=sleeps.append,
                                       info_set=lambda key, value: info.__setitem__(key, value),
                                       _daily_points_read_valid=True)
                if expected is None:
                    with self.assertRaisesRegex(ValueError, 'Daily activity OCR unreadable'):
                        scope['get_total_daily_points'](task)
                    self.assertFalse(task._daily_points_read_valid)
                    self.assertEqual(len(reads), 3)
                    self.assertEqual(sleeps, [0.3, 0.3])
                    self.assertEqual(info['total daily points'], 'unreadable')
                else:
                    self.assertEqual(scope['get_total_daily_points'](task), expected)
                    self.assertTrue(task._daily_points_read_valid)
                    self.assertEqual(len(reads), 1)
                    self.assertEqual(sleeps, [])
                    self.assertEqual(info['total daily points'], expected)
