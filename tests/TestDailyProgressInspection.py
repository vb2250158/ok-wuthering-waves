"""Execute the official methods with inert harnesses; never initialize a game."""
import ast
import re
from pathlib import Path
from types import SimpleNamespace
import unittest


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
             'normalize_account_name': lambda name: name.lower().replace('0', 'o').replace('.con', '.com') if name else name,
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
    def __init__(self):
        self.calls = []
        self.config = {INSPECTION_ONLY: True}
        self.done_set = set()
        self.all_accounts = set()
        self.identity_selected = False
        self.run = run_method('MultiAccountDailyTask.py', 'MultiAccountDailyTask').__get__(self)

    def get_task_by_class(self, _cls):
        return SimpleNamespace(config=self.config)

    def run_task_by_class(self, _cls):
        if not self.identity_selected:
            raise AssertionError('First inspection needs the official selected account identity')
        self.calls.append('inspect')

    def ensure_main(self, **kwargs):
        self.calls.append('main')

    def _switch_to_login(self):
        self.calls.append('login-page')

    def _select_and_login_account(self):
        self.calls.append('select-account')
        if self.identity_selected:
            return None
        self.identity_selected = True
        return 'fixture-account'

    def _mark_done(self, account):
        self.done_set.add(account)

    def info_set(self, *args):
        pass


class TestDailyProgressInspection(unittest.TestCase):
    def test_requested_account_is_inspected_once_without_foreign_business(self):
        task = MultiAccountHarness()
        task.config[INSPECTION_ACCOUNT] = 'target-fixture'
        accounts = iter(['foreign-fixture', 'target-fixture', None])
        task._select_and_login_account = lambda: next(accounts)
        task.identity_selected = True
        task.run()
        self.assertEqual(task.calls.count('inspect'), 1)
        self.assertEqual(task.done_set, {'foreign-fixture', 'target-fixture'})

    def test_missing_requested_account_fails_without_inspection(self):
        task = MultiAccountHarness()
        task.config[INSPECTION_ACCOUNT] = 'missing-fixture'
        with self.assertRaisesRegex(Exception, 'not found'):
            task.run()
        self.assertEqual(task.calls.count('inspect'), 0)

    def test_inspection_does_not_claim_or_farm(self):
        task = DailyHarness(True)
        self.assertTrue(task.run())
        self.assertEqual(task.calls, ['validate', 'base', 'main', 'inspect', 'main'])

    def test_unreadable_progress_returns_false_without_claiming(self):
        task = DailyHarness(False)
        self.assertFalse(task.run())
        self.assertEqual(task.calls, ['validate', 'base', 'main', 'inspect', 'main'])

    def test_first_account_is_selected_before_inspection(self):
        task = MultiAccountHarness()
        task.run()
        self.assertLess(task.calls.index('select-account'), task.calls.index('inspect'))
        self.assertEqual(task.calls.count('inspect'), 1)
        self.assertEqual(task.done_set, {'fixture-account'})

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

    def test_points_read_distinguishes_zero_and_unreadable_without_changing_integer_results(self):
        path = Path(__file__).parents[1] / 'src/task/DailyTask.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DailyTask')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'get_total_daily_points')
        scope = {'re': re, 'number_re': re.compile(r'\d+')}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
        for text, expected, valid in [('0', 0, True), ('100', 100, True), ('101', 101, True), ('120', 120, True), ('-1', 1, False), ('unreadable', 0, False), (None, 0, False)]:
            with self.subTest(text=text):
                task = SimpleNamespace(ocr=lambda *args, **kwargs: [] if text is None else [SimpleNamespace(name=text)],
                                       info_set=lambda *args: None, _daily_points_read_valid=True)
                self.assertEqual(scope['get_total_daily_points'](task), expected)
                self.assertIs(task._daily_points_read_valid, valid)
