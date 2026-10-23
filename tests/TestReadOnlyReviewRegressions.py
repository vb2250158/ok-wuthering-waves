"""Frozen upstream method replay. UI is inert; source files are never imported."""
import ast
import hashlib
import json
from pathlib import Path
import re
import types
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
TRACE = {}
FILES = ['BaseWWTask.py', 'DailyTask.py', 'DomainTask.py', 'ForgeryTask.py',
         'SimulationTask.py', 'TacetTask.py', 'StaminaBudget.py', 'MultiAccountDailyTask.py']


def method(file, owner, name, **env):
    path = SOURCE / 'src/task' / file
    cls = next(n for n in ast.parse(path.read_text(encoding='utf-8-sig')).body
               if isinstance(n, ast.ClassDef) and n.name == owner)
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), env)
    return env[name]


budget_env = {}
exec(compile((SOURCE/'src/task/StaminaBudget.py').read_text(), str(SOURCE/'src/task/StaminaBudget.py'), 'exec'), budget_env)
Budget = budget_env['StaminaBudget']


def bind(task, file, owner, name, **env):
    setattr(task, name, types.MethodType(method(file, owner, name, **env), task))


class Dead(Exception): pass


class Probe:
    def __init__(self):
        self.actions = []
        self.stamina_once = 40
        self.teleport_timeout = 100
        self.config = {'Which Forgery Challenge to Farm': 1, 'Material Selection': 'Shell Credit'}
        self.combats = 0
    def sleep(self, *a, **k): pass
    def info_set(self, *a, **k): pass
    def info_incr(self, *a, **k): pass
    def log_info(self, *a, **k): pass
    def log_debug(self, *a, **k): pass
    def back(self, *a, **k): pass
    def make_sure_in_world(self): self.actions.append('world')
    def open_F2_book_and_get_stamina(self): return 240, 999, 1239
    def get_current_stamina_strict(self): return 240
    def teleport_into_domain(self, *a): self.actions.append('teleport')
    def walk_until_f(self, *a, **k): pass
    def pick_f(self, *a, **k): pass
    def walk_to_treasure(self): pass
    def combat_once(self, *a, **k):
        self.combats += 1
        if self.combats == 2: raise Dead()
    def click_dialog_left_button(self): self.actions.append(('spend', self.stamina_once))
    def click_dialog_right_button(self): self.actions.append(('spend', 2*self.stamina_once))
    def wait_feature(self, *a, **k): return False
    def click(self, *a, **k): pass
    def wait_in_team_and_world(self, *a, **k): pass


class ExtraReplay(unittest.TestCase):
    def test_domain_routes_real_methods_preserve_budget_after_death(self):
        for route in ('ForgeryTask', 'SimulationTask'):
            with self.subTest(route=route):
                task = Probe()
                for file, owner, name in [('BaseWWTask.py','BaseWWTask','use_stamina'),
                    ('DomainTask.py','DomainTask','farm_in_domain'),
                    ('DomainTask.py','DomainTask','farm_domain_with_recovery_loop')]:
                    bind(task,file,owner,name,NotInCombatException=Dead,CharDeadException=Dead)
                name = 'farm_forgery' if route == 'ForgeryTask' else 'farm_simulation'
                bind(task,route+'.py',route,name)
                budget = Budget(120)
                getattr(task,name)(daily=True,used_stamina=0,config=task.config,budget=budget)
                self.assertEqual([a[1] for a in task.actions if isinstance(a,tuple)],[80,40])
                self.assertEqual(budget.reserved,120)
                self.assertEqual(task.combats,3)
                self.assertEqual(task.actions.count('teleport'),2)
                TRACE[route] = dict(actions=task.actions,reserved=budget.reserved,combats=task.combats)

    def test_tacet_real_methods_preserve_budget_after_death(self):
        task = Probe()
        task.stamina_once = 60
        task.openF2Book = lambda *a: None
        task.get_stamina = lambda: (240,999,1239)
        task.open_boss_book = lambda *a: None
        task.teleport_to_tacet = lambda *a: task.actions.append('teleport')
        task.click_team_challenge = lambda: None
        task.has_claim_stamina = lambda: True
        task.click_relative = lambda *a,**k: None
        task.wait_click_skip_dialog_confirm = lambda: None
        bind(task,'BaseWWTask.py','BaseWWTask','use_stamina')
        bind(task,'TacetTask.py','TacetTask','farm_tacet',CharRevivedException=Dead)
        budget = Budget(180)
        task.farm_tacet(daily=True,used_stamina=0,config=task.config,budget=budget)
        self.assertEqual([a[1] for a in task.actions if isinstance(a,tuple)],[120,60])
        self.assertEqual(budget.reserved,180)
        self.assertEqual(task.combats,3)
        TRACE['TacetTask'] = dict(actions=task.actions,reserved=budget.reserved,combats=task.combats)

    def test_exception_after_click_retains_reservation_with_partial_budget(self):
        task = Probe()
        budget = Budget(140)
        def unknown():
            task.actions.append(('unknown',80))
            raise RuntimeError('unknown after attempted click')
        task.click_dialog_right_button = unknown
        bind(task,'BaseWWTask.py','BaseWWTask','use_stamina')
        with self.assertRaises(RuntimeError): task.use_stamina(once=40,must_use=-999,budget=budget)
        self.assertEqual((budget.reserved,budget.remaining),(80,60))
        self.assertEqual(task.use_stamina(once=40,must_use=999,budget=budget),(False,40))
        self.assertEqual((budget.reserved,budget.remaining),(120,20))
        TRACE['partialUnknown'] = dict(actions=task.actions,reserved=budget.reserved)

    def test_daily_entry_passes_one_configured_budget_without_deriving_must_use(self):
        modes = dict(CURRENT_STATE_INSPECTION='current',DAILY_PROGRESS_INSPECTION_ONLY='progress',
                     DAILY_REWARD_STATUS_INSPECTION_ONLY='reward',BATTLE_PASS_STATUS_INSPECTION_ONLY='pass',
                     ADDITIONAL_TASKS='extra',AUTO_FARM_NIGHTMARE_NEST='nightmare')
        for route,name in [('tacet','farm_tacet'),('forgery','farm_forgery'),('simulation','farm_simulation')]:
            seen=[]
            task = Probe()
            task.config.update({'Waveplate Spend Limit':60,'Which to Farm':route})
            task.support_tasks=['tacet','forgery','simulation']
            task.validate_additional_tasks=lambda:None
            task.ensure_main=lambda **k:None
            task.open_daily=lambda:(120,False)
            task.claim_daily=task.claim_mail=task.claim_battle_pass=task.run_additional_tasks=lambda:None
            def farm(**kwargs): seen.append(kwargs)
            task.get_task_by_class=lambda cls:types.SimpleNamespace(**{name:farm})
            run=method('DailyTask.py','DailyTask','run',configured_budget=budget_env['configured_budget'],
                       WWOneTimeTask=types.SimpleNamespace(run=lambda t:None),TacetTask=object,
                       ForgeryTask=object,SimulationTask=object,**modes)
            run(task)
            self.assertEqual(len(seen),1)
            self.assertEqual(seen[0]['budget'].maximum,60)
            self.assertEqual(seen[0]['used_stamina'],120)

    def test_counterexample_exact_saved_account_mismatch_must_not_start(self):
        path=SOURCE/'tests/TestFirstAccountConfirmation.py'
        namespace={'__file__':str(path),'__name__':'frozen_identity_fixture'}
        exec(compile(path.read_text(encoding='utf-8-sig'),str(path),'exec'),namespace)
        wanted,actual='ab0****@example.test','abo****@example.test'
        task,env=namespace['make_task'](selected=(),visible=(actual,),current=actual,
            inspection='Current State Inspection Only',inspection_target=wanted)
        with self.assertRaisesRegex(namespace['WaitFailedException'], 'account_not_available'):
            task.run()
        self.assertNotIn(('click', 'login'), task.trace)
        TRACE['exactIdentityMismatch']=dict(requested=wanted,actual=actual,dailyCalls=task.daily_calls,trace=task.trace)
        self.assertEqual(task.daily_calls,[], 'Exact-scope inspection accepted a different raw saved-account label')

    def test_counterexample_current_state_mode_must_not_execute_monthly_claim(self):
        task = Probe()
        task.config={'Current State Inspection Only':True}
        task.logged_in=False
        task.debug=False
        task.monthly_present=True
        task.monthly_clicks=0
        task.validate_additional_tasks=lambda:None
        task.in_team_and_world=lambda: not task.monthly_present
        task.in_realm=lambda:False
        task.find_monthly_card=lambda:object() if task.monthly_present else None
        task.set_check_monthly_card=lambda **k:None
        task.find_one=lambda *a,**k:None
        task.ocr=lambda **k:[]
        task.box_of_screen=lambda *a,**k:None
        task.find_boxes=lambda *a,**k:[]
        def click_monthly(*a,**k):
            task.monthly_clicks+=1
            task.actions.append(('monthly-click',list(a)))
            if task.monthly_clicks==2: task.monthly_present=False
        task.click_relative=click_monthly
        def wait_until(fn,**kwargs):
            for _ in range(4):
                value=fn()
                if value:return value
            return False
        task.wait_until=wait_until
        task.inspect_current_state=lambda:task.actions.append('inspection') or True
        for name in ('ensure_main','is_main','wait_login','handle_monthly_card'):
            bind(task,'BaseWWTask.py','BaseWWTask',name,LOGIN_TEXTS='login',re=re,
                 Labels=types.SimpleNamespace(switch_account='switch_account'))
        run=method('DailyTask.py','DailyTask','run',configured_budget=budget_env['configured_budget'],
             CURRENT_STATE_INSPECTION='Current State Inspection Only',DAILY_PROGRESS_INSPECTION_ONLY='progress',
             DAILY_REWARD_STATUS_INSPECTION_ONLY='reward',BATTLE_PASS_STATUS_INSPECTION_ONLY='pass',
             WWOneTimeTask=types.SimpleNamespace(run=lambda t:None))
        with self.assertRaisesRegex(RuntimeError, 'readonly_inspection_reward_page_blocked'):
            run(task)
        self.assertNotIn('inspection', task.actions)
        TRACE['readonlyMonthlyClaim']=dict(actions=task.actions,monthlyClicks=task.monthly_clicks)
        self.assertEqual(task.monthly_clicks,0,'Read-only inspection reached original monthly-card claim clicks')


