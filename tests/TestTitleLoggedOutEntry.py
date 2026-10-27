"""Actual upstream method AST with synthetic OCR/OS only; no SDK, models or app input."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from TestFirstAccountConfirmation import (A, B, OTHER, make_task,
    WaitFailedException, TaskDisabledException)


def box(name, x, y, confidence=0.99):
    return SimpleNamespace(name=name, x=x-.012, y=y-.009, width=.024,
                           height=.018, confidence=confidence)


def title_task(*, location='title', selected=(A, B), visible=(B, OTHER, A), failure=None):
    task, ns = make_task(location=location, selected=selected, visible=visible, failure=failure)
    task.clock = 0
    task.login_opens = True
    task.entry_error = None
    task.on_refresh = None
    task.extra = []
    task.title = [box('点击连接', .5, .95), box('账号', .95, .52)]
    task.modal = [box('提示', .27, .33), box('确认登出账号？', .50, .47),
                  box('取消', .35, .62), box('确认登出', .65, .62)]
    # Coordinates are manually transcribed from same-Attempt frame-03.jpg;
    # these are synthetic OCR boxes, never a claim of actual OCR success.
    task.logged_out = [box('退出', .947, .193), box('登入', .947, .313),
                       box('设置', .947, .432)]
    task.entry = box('switch_account', .95, .52)
    original_ocr, original_click, original_sleep = task.ocr, task.click, task.sleep
    task.box_of_screen = lambda *bounds: bounds
    task.find_one = lambda *a, **k: task.entry if task.location == 'title' else None
    def ocr(*args, **kwargs):
        if task.location == 'title': return task.title + task.extra
        if task.location == 'modal': return task.modal + task.extra
        if task.location == 'logged-out': return task.logged_out + task.extra
        hits = original_ocr(*args, **kwargs)
        for hit in hits:
            if not hasattr(hit, 'x'):
                hit.x, hit.y, hit.width, hit.height = .4, .5, .2, .03
        return hits
    task.ocr = ocr
    def find_boxes(texts, match=None, boundary=None, **kwargs):
        hits = texts
        if match is not None:
            hits = [b for b in hits if match.search(b.name)] if hasattr(match, 'search') else [b for b in hits if b.name == match]
        if boundary:
            left, top, right, bottom = boundary
            hits = [b for b in hits if left <= b.x and top <= b.y and
                    b.x+b.width <= right and b.y+b.height <= bottom]
        return hits
    task.find_boxes = find_boxes
    def sleep(seconds):
        task.clock += seconds
        original_sleep(seconds)
    task.sleep = sleep
    def next_frame():
        if task.on_refresh: task.on_refresh(task)
    task.next_frame = next_frame
    def wait_until(condition, time_out=100, **kwargs):
        deadline = task.clock + time_out
        while task.clock < deadline:
            result = condition()
            if result: return result
            task.clock += 1
        return None
    task.wait_until = wait_until
    def click(target, **kwargs):
        target = target[0] if isinstance(target, list) else target
        if target is task.entry:
            task.trace.append(('title-account',))
            task.location = 'modal'
        elif target.name == '确认登出':
            task.trace.append(('title-logout',))
            task.location = 'logged-out'
        elif target.name == '登入':
            task.trace.append(('title-login',))
            if task.entry_error: raise task.entry_error
            if task.login_opens: task.location = 'login'
        else:
            original_click(target, **kwargs)
    task.click = click
    return task, ns


class TitleLoggedOutEntryTests(unittest.TestCase):
    def test_observed_logout_sequence_reaches_only_requested_accounts(self):
        task, _ = title_task()
        task.run()
        self.assertEqual([x['actualDisplay'] for x in task.daily_calls], [A, B])
        self.assertEqual([x['observedIdentity'] for x in task.daily_calls], [A, B])
        self.assertTrue(all(x['inWorld'] for x in task.daily_calls))
        self.assertEqual(task.done_set, {A, B})
        self.assertEqual(task.config['Saved Accounts'], [A, B])
        for event in [('title-account',), ('title-logout',), ('title-login',)]:
            self.assertEqual(task.trace.count(event), 1)
        self.assertLess(task.trace.index(('title-logout',)), task.trace.index(('title-login',)))
        self.assertLess(task.trace.index(('title-login',)), task.trace.index(('select', A)))
        self.assertNotIn(('select', OTHER), task.trace)
        self.assertNotIn(('click', '点击连接'), task.trace)

    def test_preparation_opens_picker_without_selecting_or_running_daily(self):
        task, _ = title_task()
        task._prepare_first_account_login()
        self.assertEqual(task.location, 'login')
        self.assertEqual(task.trace, [('title-account',), ('title-logout',), ('title-login',)])
        self.assertEqual(task.daily_calls, [])

    def test_initial_logged_out_page_without_own_logout_is_preserved(self):
        task, _ = title_task(location='logged-out')
        with self.assertRaisesRegex(WaitFailedException, 'account_login_screen_unavailable'):
            task.run()
        self.assertEqual(task.trace, [('setup',)])
        self.assertEqual(task.daily_calls, [])

    def test_unknown_verification_page_fails_without_input(self):
        task, _ = title_task(location='verification')
        with self.assertRaisesRegex(WaitFailedException, 'account_login_screen_unavailable'):
            task.run()
        self.assertEqual(task.trace, [('setup',)])
        self.assertEqual(task.daily_calls, [])

    def test_initial_modal_without_own_title_click_is_preserved(self):
        task, _ = title_task(location='modal')
        with self.assertRaises(WaitFailedException): task.run()
        self.assertEqual(task.trace, [('setup',)])
        self.assertEqual(task.daily_calls, [])

    def test_ineffective_login_click_is_once_and_original_deadline_stays(self):
        task, _ = title_task()
        task.login_opens = False
        with self.assertRaisesRegex(WaitFailedException, 'within 100 seconds'):
            task.run()
        self.assertEqual(task.trace.count(('title-login',)), 1)
        self.assertGreaterEqual(task.clock, 100)
        self.assertLess(task.clock, 102)
        self.assertEqual(task.daily_calls, [])
        self.assertEqual(task.done_set, set())

    def test_click_exception_propagates_without_retry(self):
        task, _ = title_task()
        task.entry_error = RuntimeError('synthetic uncertain click')
        with self.assertRaisesRegex(RuntimeError, 'synthetic uncertain click'): task.run()
        self.assertEqual(task.trace.count(('title-login',)), 1)
        self.assertEqual(task.daily_calls, [])

    def test_cancellation_before_fresh_frame_propagates(self):
        task, _ = title_task()
        original = task.sleep
        def sleep(seconds):
            if task.location == 'logged-out': raise TaskDisabledException('synthetic stop')
            original(seconds)
        task.sleep = sleep
        with self.assertRaises(TaskDisabledException): task.run()
        self.assertNotIn(('title-login',), task.trace)
        self.assertEqual(task.daily_calls, [])

    def test_form_arriving_on_fresh_frame_blocks_click(self):
        task, _ = title_task()
        def refresh(t):
            if t.location == 'logged-out': t.extra = [box('验证码', .5, .5)]
        task.on_refresh = refresh
        with self.assertRaises(WaitFailedException): task.run()
        self.assertNotIn(('title-login',), task.trace)
        self.assertEqual(task.daily_calls, [])

    def test_missing_anchor_on_fresh_frame_blocks_click(self):
        task, _ = title_task()
        def refresh(t):
            if t.location == 'logged-out': t.logged_out = t.logged_out[:2]
        task.on_refresh = refresh
        with self.assertRaises(WaitFailedException): task.run()
        self.assertNotIn(('title-login',), task.trace)
        self.assertEqual(task.daily_calls, [])

    def test_picker_arriving_on_fresh_frame_needs_no_title_click(self):
        task, _ = title_task()
        def refresh(t):
            if t.location == 'logged-out': t.location = 'login'
        task.on_refresh = refresh
        task._prepare_first_account_login()
        self.assertEqual(task.trace, [('title-account',), ('title-logout',)])
        self.assertEqual(task.location, 'login')

    def test_world_arriving_on_fresh_frame_uses_existing_switch_flow(self):
        task, _ = title_task()
        def refresh(t):
            if t.location == 'logged-out': t.location = 'world'
        task.on_refresh = refresh
        task._prepare_first_account_login()
        self.assertNotIn(('title-login',), task.trace)
        self.assertIn(('switch-login',), task.trace)
        self.assertEqual(task.daily_calls, [])

    def test_precise_unique_anchors_are_required(self):
        for index in range(3):
            for defect in ['missing', 'duplicate', 'misplaced', 'wrong-text']:
                with self.subTest(index=index, defect=defect):
                    task, _ = title_task(location='logged-out')
                    anchor = task.logged_out[index]
                    if defect == 'missing': task.logged_out.pop(index)
                    elif defect == 'duplicate': task.extra = [box(anchor.name, .4, .5)]
                    elif defect == 'misplaced': anchor.y = .6
                    else: anchor.name += '测试'
                    self.assertIsNone(task._title_logged_out_login_entry())

    def test_low_missing_or_invalid_confidence_is_rejected(self):
        for index in range(3):
            for confidence in [.79, float('nan'), 1.1]:
                task, _ = title_task(location='logged-out')
                task.logged_out[index].confidence = confidence
                self.assertIsNone(task._title_logged_out_login_entry())
            task, _ = title_task(location='logged-out')
            del task.logged_out[index].confidence
            self.assertIsNone(task._title_logged_out_login_entry())

    def test_credentials_cost_permission_and_modal_overlays_block(self):
        for text in ['验证码', '密码', '短信验证', '手机号', '电子邮箱', 'Password',
                     'CAPTCHA', '授权', '支付', '购买', '充值', '确认登出账号？',
                     '提示', '取消', '账号', '点击连接']:
            with self.subTest(text=text):
                task, _ = title_task(location='logged-out')
                task.extra = [box(text, .5, .5)]
                self.assertIsNone(task._title_logged_out_login_entry())

    def test_observed_positions_qualify_exact_login_only(self):
        task, _ = title_task(location='logged-out')
        self.assertIs(task._title_logged_out_login_entry(), task.logged_out[1])

    def test_missing_requested_account_after_transition_stops_before_login(self):
        task, _ = title_task(visible=(B, OTHER))
        with self.assertRaisesRegex(WaitFailedException, 'account_not_available'): task.run()
        self.assertEqual(task.trace.count(('title-login',)), 1)
        self.assertNotIn(('click', 'login'), task.trace)
        self.assertEqual(task.daily_calls, [])
        self.assertEqual(task.done_set, set())

    def test_reverted_selected_identity_still_stops_before_saved_login(self):
        task, _ = title_task(failure='reverted')
        with self.assertRaisesRegex(WaitFailedException, 'account_selection_unconfirmed'): task.run()
        self.assertNotIn(('click', 'login'), task.trace)
        self.assertEqual(task.daily_calls, [])
        self.assertTrue(task.mouse.enabled)

    def test_known_static_title_labels_with_expected_positions_are_allowed(self):
        task, _ = title_task(location='logged-out')
        task.extra = [box('鸣潮', .06, .06), box('WUTHERING WAVES', .06, .10),
                      box('CN_Windows_Product_3.7.0_9052049_3.7.16_9131576 * HD', .70, .05),
                      box('16+', .95, .90), box('CADPA', .95, .93),
                      box('适龄提示', .95, .96), box('登录状态：0', .95, .985)]
        self.assertIs(task._title_logged_out_login_entry(), task.logged_out[1])

    def test_known_static_text_cannot_qualify_inside_modal_region(self):
        for text in ['鸣潮', 'WUTHERING WAVES', 'CN_Windows_Product_3.7.0_1 * HD',
                     '16+', 'CADPA', '适龄提示', '登录状态：0']:
            task, _ = title_task(location='logged-out')
            task.extra = [box(text, .5, .5)]
            self.assertIsNone(task._title_logged_out_login_entry())

    def test_unknown_text_anywhere_blocks_even_at_low_confidence(self):
        for x, y in [(.06, .06), (.5, .5), (.95, .94)]:
            task, _ = title_task(location='logged-out')
            task.extra = [box('unrecognized overlay', x, y, confidence=.1)]
            self.assertIsNone(task._title_logged_out_login_entry())

    def test_modal_confirmation_and_logged_in_title_keep_existing_guards(self):
        task, _ = title_task(location='modal')
        self.assertIs(task._title_logout_confirmation(), task.modal[-1])
        task.extra = [box('验证码', .5, .5)]
        self.assertIsNone(task._title_logout_confirmation())
        task.location = 'title'
        self.assertIsNone(task._title_account_entry())
        task.extra = []
        self.assertIs(task._title_account_entry(), task.entry)


if __name__ == '__main__':
    unittest.main(verbosity=2)
