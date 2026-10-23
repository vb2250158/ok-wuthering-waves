"""Real upstream method flow with synthetic UI/OS results; never starts an app."""
import ast
from copy import deepcopy
from functools import wraps
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'src/task/MultiAccountDailyTask.py'
A, B, OTHER = 'aa****@example.test', 'bb****@example.test', 'cc****@example.test'
MODES = ('Daily Progress Inspection Only', 'Daily Reward Status Inspection Only', 'Battle Pass Status Inspection Only')


class WaitFailedException(Exception): pass
class TaskDisabledException(Exception): pass
class DailyFailure(Exception): pass


def load_methods(source):
    class WWOneTimeTask:
        @staticmethod
        def run(task): task.trace.append(('setup',))
    class BaseCombatTask: pass
    class DailyTask: pass
    class MouseResetTask: pass
    namespace = dict(re=re, Box=object, WWOneTimeTask=WWOneTimeTask, BaseCombatTask=BaseCombatTask,
                     DailyTask=DailyTask, MouseResetTask=MouseResetTask, WaitFailedException=WaitFailedException,
                     TaskDisabledException=TaskDisabledException, LOGIN_TEXTS='login',
                     DAILY_PROGRESS_INSPECTION_ONLY=MODES[0], DAILY_REWARD_STATUS_INSPECTION_ONLY=MODES[1],
                     BATTLE_PASS_STATUS_INSPECTION_ONLY=MODES[2],
                     DAILY_PROGRESS_INSPECTION_ACCOUNT='Daily Progress Inspection Account')
    nodes = []
    for node in ast.parse(source.read_text(encoding='utf-8-sig')).body:
        if isinstance(node, ast.FunctionDef) and node.name in {'normalize_account_name', 'configured_accounts', 'next_requested_account'}:
            nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name == 'MultiAccountDailyTask': nodes.append(node)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'account_pattern', 'SAVED_ACCOUNTS'} for t in node.targets):
            nodes.append(node)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'), namespace)
    return namespace


def make_task(*, selected=(A, B), visible=(B, OTHER, A), current=B, mode='combo', location='world',
              inspection=None, inspection_target='', failure=None, source=None):
    namespace = load_methods(source or SOURCE)
    task = object.__new__(namespace['MultiAccountDailyTask'])
    task.config = {'Saved Accounts': deepcopy(list(selected) if isinstance(selected,tuple) else selected)}
    task.daily_config = {key:key == inspection for key in MODES}
    task.daily_config['Daily Progress Inspection Account'] = inspection_target
    task.done_set, task.all_accounts = set(), set()
    task.trace, task.daily_calls = [], []
    task.visible, task.display = list(visible), current
    task.location, task.dropdown_open = location, False
    task.logged_in = location == 'world'
    task.observed_identity = None
    task.info = {}
    task.debug = False
    mouse = SimpleNamespace(enabled=True)
    def disable(): mouse.enabled=False; task.trace.append(('mouse-disable',))
    def enable(): mouse.enabled=True; task.trace.append(('mouse-enable',))
    mouse.disable, mouse.enable = disable, enable
    task.mouse = mouse
    task.executor = SimpleNamespace(get_task_by_class=lambda cls:mouse)
    task.get_task_by_class = lambda cls:SimpleNamespace(config=task.daily_config)
    task.tr = lambda message:message
    task.log_info = lambda *a,**k:None
    task.log_error = lambda *a,**k:None
    task.info_set = lambda key,value:task.info.__setitem__(key,deepcopy(value))
    task.box_of_screen = lambda *a,**k:None
    task.screenshot = lambda *a,**k:None
    def sleep(seconds):
        if seconds == 4 and failure == 'reverted': task.display=OTHER
        if seconds == 4 and failure == 'identity_missing': task.display=None
    task.sleep = sleep
    task.in_team_and_world = lambda:task.location == 'world'
    task._login_combo = lambda:1 if mode == 'combo' and task.location == 'login' else None
    def switch_login():
        task.trace.append(('switch-login',))
        task.location='login'
        task.dropdown_open=False
    task._switch_to_login = switch_login
    def ensure_main(**kwargs):
        task.trace.append(('ensure-main',task.location))
        if task.location == 'logging-in':
            if failure == 'login_failed': raise RuntimeError('synthetic verification still pending')
            if failure == 'cancelled': raise TaskDisabledException('synthetic cancellation')
            task.location='world'
        task.logged_in = task.location == 'world'
        if not task.logged_in: raise WaitFailedException('synthetic world unavailable')
    task.ensure_main = ensure_main
    def wait_until(condition, **kwargs): return condition()
    task.wait_until = wait_until
    def ocr(match=None, **kwargs):
        if task.location not in {'login','logging-in'}: return []
        if task.dropdown_open:
            names=task.visible
        else:
            names=[task.display] if task.display else []
            if failure != 'login_button_missing': names=names+['login']
        boxes=[SimpleNamespace(name=n) for n in names]
        return [b for b in boxes if match.search(b.name)] if match else boxes
    task.ocr=ocr
    def find_boxes(texts, match=None, **kwargs):
        if hasattr(match,'search'): return [b for b in texts if match.search(b.name)]
        return [b for b in texts if b.name == match]
    task.find_boxes=find_boxes
    def click(value, **kwargs):
        box=value[0] if isinstance(value,list) else value
        task.trace.append(('click',box.name))
        if box.name == 'login':
            task.location='logging-in'
        elif task.dropdown_open:
            task.display=OTHER if failure == 'ocr_mismatch' else box.name
            task.dropdown_open=False
        elif failure != 'dropdown_stuck': task.dropdown_open=True
    task.click=click
    def click_relative(*a, **kw): raise AssertionError('unrecognized-login coordinate fallback must not run')
    task.click_relative=click_relative
    namespace['combo_items']=lambda combo:list(task.visible)
    namespace['combo_selected_item']=lambda combo:task.display
    def select_combo(combo,index):
        task.trace.append(('select',task.visible[index]))
        if failure == 'selection_failed': return False
        task.display=task.visible[index]
        return True
    namespace['select_combo_item']=select_combo
    # Match the installed observer contract: only actual method return values
    # become observed identity, never the requested config value.
    for name in ['_detect_current_account_from_login','_select_and_login_account']:
        original=getattr(task,name)
        def observe(*args,_original=original,**kwargs):
            result=_original(*args,**kwargs)
            task.observed_identity=namespace['normalize_account_name'](result) or None
            task.trace.append(('identity',result))
            return result
        setattr(task,name,observe)
    def run_daily(cls):
        call={'actualDisplay':task.display,'observedIdentity':task.observed_identity,
              'inWorld':task.logged_in,'inspection':any(task.daily_config[m] for m in MODES)}
        task.daily_calls.append(call)
        task.trace.append(('daily',task.display))
        if failure == 'daily_failed': raise DailyFailure()
        if len(task.daily_calls)>10: raise AssertionError('bounded synthetic test exceeded account count')
    task.run_task_by_class=run_daily
    return task, namespace


class TestFirstAccountConfirmation(unittest.TestCase):
    def test_first_daily_has_confirmed_account_and_configured_order(self):
        for mode in ['combo','ocr']:
            with self.subTest(mode=mode):
                task,ns=make_task(mode=mode)
                original=deepcopy(task.config)
                task.run()
                self.assertEqual([x['actualDisplay'] for x in task.daily_calls],[A,B])
                self.assertEqual([x['observedIdentity'] for x in task.daily_calls],[A,B])
                self.assertTrue(all(x['inWorld'] and not x['inspection'] for x in task.daily_calls))
                self.assertEqual(task.config,original)
                self.assertNotIn(('select',OTHER),task.trace)
                self.assertNotIn(('click',OTHER),task.trace)
                self.assertEqual(task.done_set,{A,B})
                self.assertTrue(task.mouse.enabled)

    def test_initial_login_page_does_not_auto_login_current_unselected_account(self):
        task,ns=make_task(location='login',current=OTHER)
        task.run()
        self.assertEqual(task.daily_calls[0]['observedIdentity'],A)
        self.assertEqual([x for x in task.trace if x[0]=='select'],[('select',A),('select',B)])

    def test_missing_scope_stops_before_any_input_or_daily(self):
        task,ns=make_task(selected=[])
        with self.assertRaisesRegex(ValueError,'account_selection_required'):task.run()
        self.assertEqual(task.trace,[])
        self.assertEqual(task.daily_calls,[])

    def test_invalid_and_colliding_scope_stops_before_input(self):
        for selected in [None,A,[''],[' '+A],[A,4],[A,A.upper()],['ab0****@example.test','abo****@example.test'],['x\n'],['ß****@example.test','ss****@example.test']]:
            with self.subTest(selected=selected):
                task,ns=make_task(selected=selected)
                with self.assertRaises(ValueError):task.run()
                self.assertEqual(task.trace,[])

    def test_unavailable_first_account_cannot_fall_back_to_another_account(self):
        for mode in ['combo','ocr']:
            task,ns=make_task(mode=mode,visible=(B,OTHER))
            with self.assertRaisesRegex(WaitFailedException,'account_not_available'):task.run()
            self.assertEqual(task.daily_calls,[])
            self.assertNotIn(('click','login'),task.trace)
            self.assertTrue(task.mouse.enabled)

    def test_missing_second_account_does_not_repeat_first(self):
        task,ns=make_task(visible=(A,OTHER))
        with self.assertRaisesRegex(WaitFailedException,'account_not_available'):task.run()
        self.assertEqual([x['actualDisplay'] for x in task.daily_calls],[A])
        self.assertEqual(task.done_set,{A})

    def test_combo_reverted_or_unknown_selection_stops_before_login(self):
        for failure in ['reverted','identity_missing','selection_failed']:
            task,ns=make_task(failure=failure)
            with self.assertRaisesRegex(WaitFailedException,'account_selection_unconfirmed'):task.run()
            self.assertEqual(task.daily_calls,[])
            self.assertNotIn(('click','login'),task.trace)
            self.assertTrue(task.mouse.enabled)

    def test_conflicting_saved_entries_stop_before_selection(self):
        for mode,visible in [('combo',(A,A,B)),('ocr',(A,A.upper(),B))]:
            task,ns=make_task(mode=mode,visible=visible)
            with self.assertRaisesRegex(WaitFailedException,'account_selection_ambiguous'):task.run()
            self.assertEqual(task.daily_calls,[])

    def test_identical_masked_ocr_rows_at_different_positions_are_ambiguous(self):
        task,ns=make_task(mode='ocr',visible=(A,A,B))
        original_ocr=task.ocr
        def spatial_ocr(*args,**kwargs):
            boxes=original_ocr(*args,**kwargs)
            for index,box in enumerate(boxes):
                box.x,box.y,box.width,box.height=200,100+80*index,220,24
            return boxes
        task.ocr=spatial_ocr
        with self.assertRaisesRegex(WaitFailedException,'account_selection_ambiguous'):task.run()
        self.assertEqual(task.daily_calls,[])
        self.assertFalse(any(item[0]=='click' and item[1] in {A,'login'} for item in task.trace))
        self.assertEqual(task.done_set,set())
        self.assertTrue(task.mouse.enabled)

    def test_exhausted_ocr_selection_never_attempts_login(self):
        for failure in ['dropdown_stuck','ocr_mismatch']:
            task,ns=make_task(mode='ocr',failure=failure)
            with self.assertRaises(Exception):task.run()
            self.assertEqual(task.daily_calls,[])
            self.assertNotIn(('click','login'),task.trace)
            self.assertTrue(task.mouse.enabled)

    def test_human_screen_before_selection_is_read_only_failure(self):
        task,ns=make_task(location='verification')
        with self.assertRaisesRegex(WaitFailedException,'manual login or verification required'):task.run()
        self.assertEqual(task.daily_calls,[])
        self.assertFalse(any(x[0] in {'click','select','switch-login'} for x in task.trace))

    def test_missing_login_confirmation_has_no_coordinate_fallback(self):
        task,ns=make_task(failure='login_button_missing')
        with self.assertRaisesRegex(WaitFailedException,'account_login_confirmation_unavailable'):task.run()
        self.assertEqual(task.daily_calls,[])
        self.assertTrue(task.mouse.enabled)

    def test_failed_login_has_clear_failure_before_daily(self):
        task,ns=make_task(failure='login_failed')
        with self.assertRaisesRegex(WaitFailedException,'account_login_unconfirmed'):task.run()
        self.assertEqual(task.daily_calls,[])
        self.assertEqual(task.done_set,set())
        self.assertTrue(task.mouse.enabled)

    def test_cancellation_propagates_and_restores_mouse_task(self):
        task,ns=make_task(failure='cancelled')
        with self.assertRaises(TaskDisabledException):task.run()
        self.assertEqual(task.daily_calls,[])
        self.assertEqual(task.done_set,set())
        self.assertTrue(task.mouse.enabled)

    def test_failed_daily_keeps_identity_and_does_not_start_second_account(self):
        task,ns=make_task(failure='daily_failed')
        with self.assertRaises(DailyFailure):task.run()
        self.assertEqual(len(task.daily_calls),1)
        self.assertEqual(task.daily_calls[0]['observedIdentity'],A)
        self.assertEqual(task.done_set,set())
        self.assertNotIn(('select',B),task.trace)

    def test_observed_identity_is_actual_returned_label_not_config_target(self):
        wanted='ab0****@example.test'
        actual='abo****@example.test'
        task,ns=make_task(selected=(wanted,),visible=(actual,OTHER))
        task.run()
        identities=[x[1] for x in task.trace if x[0]=='identity' and x[1]]
        self.assertTrue(identities)
        self.assertTrue(all(value==actual for value in identities))
        self.assertNotEqual(actual,wanted)

    def test_forged_selection_return_is_rejected_by_run_scope(self):
        task,ns=make_task()
        task._select_and_login_account=lambda:OTHER
        with self.assertRaisesRegex(WaitFailedException,'account_selection_unconfirmed'):task.run()
        self.assertEqual(task.daily_calls,[])

    def test_ocr_detection_requires_selected_login_field_not_open_list(self):
        task,ns=make_task(mode='ocr',location='login')
        task.dropdown_open=True
        self.assertIsNone(task._detect_current_account_from_login())
        self.assertIsNone(task.observed_identity)

    def test_each_inspection_mode_remains_inspection_only(self):
        for mode in MODES:
            task,ns=make_task(selected=[],inspection=mode,inspection_target=A)
            task.run()
            self.assertEqual([x['actualDisplay'] for x in task.daily_calls],[A])
            self.assertTrue(task.daily_calls[0]['inspection'])
            self.assertEqual(task._requested_accounts, (A,))

    def test_inspection_requires_exact_target_without_falling_back_to_all_accounts(self):
        task,ns=make_task(selected=[],inspection=MODES[0],visible=(A,B))
        with self.assertRaises(ValueError):task.run()
        self.assertEqual(task.daily_calls,[])
        self.assertEqual(task.trace,[])

    def test_reused_task_clears_completion_and_keeps_user_order(self):
        task,ns=make_task(selected=(B,A))
        task.done_set={A,B}
        task.run()
        self.assertEqual([x['actualDisplay'] for x in task.daily_calls],[B,A])
        self.assertEqual(task.config['Saved Accounts'],[B,A])


if __name__ == '__main__':
    unittest.main()
