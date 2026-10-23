"""Execute real upstream methods with synthetic recognition results; no game APIs.

This proves control-flow behavior, not the cause of the live recognition failure.
Only selected AST methods are compiled: no upstream module/app initialization.
"""
from pathlib import Path
import ast
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / 'src/task/BaseCombatTask.py'

class CombatStillRunning(Exception):
    pass

class ReachedTreasure(Exception):
    pass

class ReenteredChallenge(Exception):
    pass

class FakeClock:
    now = 100.0
    def time(self):
        return self.now
    def advance(self, n):
        self.now += n
        if self.now > 120:
            raise AssertionError('offline execution exceeded its time budget')

class Log:
    def __getattr__(self, name):
        return lambda *a, **k: None

def methods(path, wanted):
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    return [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in wanted]

def make_task(path, scenario='transient', delay=0.3):
    clock = FakeClock()
    namespace = {'time': clock, 'logger': Log()}
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    exceptions = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in
                  {'NotInCombatException', 'CharDeadException', 'CharRevivedException'}]
    selected = methods(path, {'combat_once', 'switch_next_char', 'raise_not_in_combat'})
    selected += methods(ROOT / 'src/task/TacetTask.py', {'farm_tacet'})
    exec(compile(ast.Module(body=exceptions + selected, type_ignores=[]), str(path), 'exec'), namespace)
    # Function-local imports are replaced with inert class markers.
    for name, cls in [('src.char.ShoreKeeper', 'ShoreKeeper'), ('src.task.AutoCombatTask', 'AutoCombatTask')]:
        module = types.ModuleType(name)
        setattr(module, cls, type(cls, (), {}))
        sys.modules[name] = module

    class Char:
        char_type = 'MainDps'
        has_intro = False
        has_sub_dps_intro = False
        last_switch_time = 100.0
        def __init__(self, index):
            self.index = index
        def __str__(self):
            return f'char-{self.index}'
        def get_current_con(self):
            return 0
        def is_con_full(self):
            return False
        def wait_switch(self):
            return False
        def f_break(self, **kw):
            pass
        def switch_out(self, **kw):
            self.last_switch_time = clock.time()
        def perform(self):
            task.switch_next_char(self)
            task.switch_completed = True
            raise CombatStillRunning('combat remains active after switching')

    class Task:
        config = {'Which Tacet Suppression to Farm': 18}
        stamina_once = 60
        switch_char_time_out = 5
        debug = False
        def __init__(self):
            self.info = {}
            self.chars = [Char(0), Char(1)]
            self.switched_at = None
            self.switch_completed = False
            self.treasure_calls = 0
            self.input_calls = 0
            self.end_calls = 0
            self.entries = 0
        def update_lib_portrait_icon(self): pass
        def _choose_switch_target(self, *a, **kw): return self.chars[1]
        def _apply_intro_flags(self, *a, **kw): pass
        def check_combat(self): pass
        def log_debug(self, *a, **kw): pass
        def log_info(self, *a, **kw): pass
        def info_set(self, k, v): self.info[k] = v
        def info_incr(self, k, v): self.info[k] = self.info.get(k, 0) + v
        def sleep(self, n): clock.advance(n)
        def next_frame(self): clock.advance(0.1)
        def click(self): self.input_calls += 1
        def send_key(self, key):
            self.input_calls += 1
            if self.switched_at is None: self.switched_at = clock.time()
        def in_team(self):
            if self.switched_at is None: return True, 0, 2
            if scenario == 'normal_switch' or (scenario == 'transient' and clock.time()-self.switched_at >= delay):
                return True, 1, 2
            return False, -1, 1
        def wait_until(self, condition, time_out, raise_if_not_found):
            assert 0 < time_out <= self.switch_char_time_out
            assert raise_if_not_found is False
            start = clock.time()
            before_inputs = self.input_calls
            while clock.time() - start <= time_out:
                self.next_frame()
                if condition(): return True
            assert self.input_calls == before_inputs, 'waiting sent additional input'
            return None
        def wait_feature(self, *a, time_out, **kw):
            if scenario in {'dead', 'revived'}: return object()
            clock.advance(time_out)
            return None
        def reset_to_false(self, **kw): return False
        def revive_action(self): return scenario == 'revived'
        def wait_combat(self, **kw): return True
        def switch_healer_enabled(self): return False
        def in_combat(self): return scenario != 'normal_end'
        def get_current_char(self): return self.chars[0]
        def combat_end(self): self.end_calls += 1
        def wait_in_team_and_world(self, **kw): return True
        def openF2Book(self, *a):
            self.entries += 1
            if self.entries > 1: raise ReenteredChallenge()
        def get_stamina(self): return 120, 459, 579
        def open_boss_book(self, *a): pass
        def teleport_to_tacet(self, index): assert index == 17
        def click_team_challenge(self): pass
        def walk_to_treasure(self):
            self.treasure_calls += 1
            raise ReachedTreasure()
    for name in ['combat_once', 'switch_next_char', 'raise_not_in_combat', 'farm_tacet']:
        setattr(Task, name, namespace[name])
    task = Task()
    return task, namespace, clock

class Regression(unittest.TestCase):
    def setUp(self):
        self.original_modules = {name: sys.modules.get(name) for name in
                                 ['src.char.ShoreKeeper', 'src.task.AutoCombatTask']}

    def tearDown(self):
        for name, original in self.original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original

    def test_transient_loss_recovers_without_exiting_combat_or_seeking_reward(self):
        for delay in [0.1, 0.3, 1.5, 4.5]:
            with self.subTest(delay=delay):
                task, ns, clock = make_task(CANDIDATE, delay=delay)
                with self.assertRaises(CombatStillRunning): task.farm_tacet(daily=True)
                self.assertTrue(task.switch_completed)
                self.assertEqual(task.treasure_calls, 0)
                self.assertEqual(task.end_calls, 0)

    def test_persistent_loss_fails_closed_before_reward(self):
        task, ns, clock = make_task(CANDIDATE, 'persistent')
        with self.assertRaisesRegex(RuntimeError, 'combat completion unconfirmed') as result:
            task.farm_tacet(daily=True)
        self.assertIsInstance(result.exception.__cause__, ns['NotInCombatException'])
        self.assertEqual(task.treasure_calls, 0)
        self.assertEqual(task.end_calls, 0)
        self.assertLess(clock.time() - task.switched_at, 7.3)

    def test_normal_switch_still_continues_combat(self):
        task, ns, clock = make_task(CANDIDATE, 'normal_switch')
        with self.assertRaises(CombatStillRunning): task.farm_tacet(daily=True)
        self.assertTrue(task.switch_completed)
        self.assertEqual(task.treasure_calls, 0)

    def test_actual_combat_end_can_still_reach_reward(self):
        task, ns, clock = make_task(CANDIDATE, 'normal_end')
        with self.assertRaises(ReachedTreasure): task.farm_tacet(daily=True)
        self.assertEqual(task.end_calls, 1)

    def test_death_remains_official_death_exception(self):
        task, ns, clock = make_task(CANDIDATE, 'dead')
        with self.assertRaises(ns['CharDeadException']): task.farm_tacet(daily=True)
        self.assertEqual(task.treasure_calls, 0)

    def test_revival_reenters_through_official_tacet_branch(self):
        task, ns, clock = make_task(CANDIDATE, 'revived')
        with self.assertRaises(ReenteredChallenge): task.farm_tacet(daily=True)
        self.assertTrue(task.realm_entry_at_heal_point)
        self.assertEqual(task.treasure_calls, 0)

    def test_revival_retry_limit_is_preserved(self):
        task, ns, clock = make_task(CANDIDATE, 'revived')
        self.assertIsNone(task.farm_tacet(daily=True, max_recovery_retries=1))
        self.assertEqual(task.entries, 1)
        self.assertEqual(task.treasure_calls, 0)

if __name__ == '__main__':
    unittest.main()
