"""Real official AST, bounded synthetic UI; no SDK/application imports."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

from src.task.StaminaBudget import StaminaBudget, configured_budget, read_current_stamina, read_daily_consumption

ROOT = Path(__file__).resolve().parents[1]


def method(filename, owner, name, **env):
    path = ROOT/'src/task'/filename
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), env)
    return env[name]


def harness(current, *, recharge=False, click_error=False):
    actions = []
    def click(which):
        actions.append(which)
        if click_error:
            raise RuntimeError('unknown result after click')
    return NS(sleep=lambda _: None, get_current_stamina_strict=lambda: current,
        click_dialog_left_button=lambda: click('single'), click_dialog_right_button=lambda: click('double'),
        wait_feature=lambda *a, **k: recharge, info_set=lambda *a: None), actions


class TestStaminaHardCap(unittest.TestCase):
    def test_current_state_snapshot_keeps_unreadable_count_unknown(self):
        inspect = method('DailyTask.py', 'DailyTask', 'inspect_current_state')
        def unreadable(): raise ValueError('missing native row')
        task = NS(read_current_state_waveplates=lambda:120, read_current_state_consumption=unreadable,
                  read_current_state_activity=lambda:80, info_set=lambda *a:None)
        self.assertFalse(inspect(task))
        self.assertEqual(task.current_state_snapshot, dict(currentWaveplates=120, dailyConsumed=None, dailyActivity=80))

    def test_current_state_mode_never_reaches_daily_business(self):
        run = method('DailyTask.py', 'DailyTask', 'run', configured_budget=configured_budget,
            CURRENT_STATE_INSPECTION='Current State Inspection Only', DAILY_PROGRESS_INSPECTION_ONLY='progress',
            DAILY_REWARD_STATUS_INSPECTION_ONLY='reward', BATTLE_PASS_STATUS_INSPECTION_ONLY='pass',
            WWOneTimeTask=NS(run=lambda task:None))
        calls = []
        task = NS(config={'Current State Inspection Only':True}, validate_additional_tasks=lambda:None,
                  ensure_main=lambda **kw:calls.append('main'), inspect_current_state=lambda:calls.append('read') or True)
        self.assertTrue(run(task))
        self.assertEqual(calls, ['main', 'read', 'main'])

    def setUp(self):
        self.use = method('BaseWWTask.py', 'BaseWWTask', 'use_stamina')

    def test_reported_60_remaining_with120_current_uses_single60(self):
        task, actions = harness(120)
        budget = StaminaBudget(60)
        self.assertEqual(self.use(task, once=60, must_use=60, budget=budget), (False, 60))
        self.assertEqual(actions, ['single'])
        self.assertEqual(budget.remaining, 0)

    def test_all40_and60_boundaries_never_exceed_cap_or_current(self):
        for once in (40, 60):
            for cap in (0, 1, once-1, once, once+1, 2*once-1, 2*once, 180, 240):
                for current in (0, once-1, once, 2*once, 240):
                    with self.subTest(once=once, cap=cap, current=current):
                        budget = StaminaBudget(cap)
                        total = 0
                        for _ in range(8):
                            task, actions = harness(current-total)
                            more, used = self.use(task, once=once, must_use=999, budget=budget)
                            self.assertEqual(used, len(actions)*once*(2 if actions == ['double'] else 1))
                            total += used
                            self.assertLessEqual(total, cap)
                            self.assertLessEqual(total, current)
                            if not more:
                                break
                        else:
                            self.fail('bounded scenario did not terminate')

    def test_reservation_survives_unknown_click_effect(self):
        task, actions = harness(240, click_error=True)
        budget = StaminaBudget(60)
        with self.assertRaises(RuntimeError):
            self.use(task, once=60, budget=budget)
        self.assertEqual(budget.remaining, 0)
        task, second = harness(240)
        self.assertEqual(self.use(task, once=60, budget=budget), (False, 0))
        self.assertEqual(second, [])

    def test_recharge_dialog_never_gets_confirmation_or_extra_budget(self):
        task, actions = harness(120, recharge=True)
        budget = StaminaBudget(60)
        with self.assertRaisesRegex(RuntimeError, 'recharge_forbidden'):
            self.use(task, once=60, budget=budget)
        self.assertEqual(actions, ['single'])
        self.assertEqual(budget.remaining, 0)

    def test_missing_current_fails_before_any_reward_click(self):
        task, actions = harness(120)
        task.get_current_stamina_strict = lambda: read_current_stamina([NS(name='459')])
        budget = StaminaBudget(120)
        with self.assertRaises(ValueError):
            self.use(task, budget=budget)
        self.assertEqual(actions, [])
        self.assertEqual(budget.reserved, 0)

    def test_strict_current_rejects_missing_conflicting_and_malformed(self):
        for texts in ([], ['459'], ['120/240', '60/240'], ['241/240'], ['120/180'], ['x/240']):
            with self.subTest(texts=texts):
                with self.assertRaises(ValueError):
                    read_current_stamina([NS(name=t) for t in texts])
        self.assertEqual(read_current_stamina([NS(name='120/240'), NS(name='459')]), 120)

    def test_daily_counter_needs_unique_title_and_same_row(self):
        anchor = NS(name='累计消耗180点结晶波片', x=100, y=200, width=200, height=25)
        counter = NS(name='120/180', x=300, y=225, width=100, height=25)
        self.assertEqual(read_daily_consumption([anchor, counter], 900), 120)
        for boxes in ([counter], [anchor, counter, counter], [anchor, NS(**{**vars(counter), 'y': 700})]):
            with self.assertRaises(ValueError):
                read_daily_consumption(boxes, 900)

    def test_no_limit_is_legacy_and_invalid_limits_fail(self):
        self.assertIsNone(configured_budget({}))
        self.assertEqual(configured_budget({'Waveplate Spend Limit': 0}).remaining, 0)
        for value in (-1, True, '60', 10001):
            with self.assertRaises(ValueError):
                StaminaBudget(value)

    def test_domain_death_recovery_keeps_same_remaining_object(self):
        run = method('DomainTask.py', 'DomainTask', 'farm_domain_with_recovery_loop')
        budget = StaminaBudget(100)
        seen = []
        def farm(*, must_use, budget):
            seen.append((id(budget), budget.remaining))
            budget.reserve(40, 40)
            return len(seen) == 2, must_use-40
        task = NS(stamina_once=40, open_F2_book_and_get_stamina=lambda: (240, 999, 1239),
            get_current_stamina_strict=lambda: 240, farm_in_domain=farm, sleep=lambda _: None,
            log_info=lambda *a, **k: None, make_sure_in_world=lambda: None, back=lambda: None)
        run(task, 180, lambda: None, budget=budget)
        self.assertEqual(seen, [(id(budget), 100), (id(budget), 60)])
        self.assertEqual(budget.remaining, 20)

    def test_zero_budget_never_enters_domain(self):
        run = method('DomainTask.py', 'DomainTask', 'farm_domain_with_recovery_loop')
        task = NS(stamina_once=40)
        run(task, 180, lambda: self.fail('must not teleport'), budget=StaminaBudget(0))


if __name__ == '__main__':
    unittest.main()
