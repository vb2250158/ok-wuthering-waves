"""Exercise the source inspection entry with inert IO and its shipped template."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

import cv2
import numpy as np

from tests.TestDailyProgressInspection import DailyHarness, MultiAccountHarness, INSPECTION_ONLY, INSPECTION_ACCOUNT, REWARD_STATUS_ONLY


def inspection_method():
    path = Path(__file__).parents[1] / 'src/task/DailyTask.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'DailyTask')
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'inspect_daily_reward_status')
    scope = {'Path': Path, 'cv2': cv2, '__file__': str(path),
             'DAILY_REWARD_CHECK_CENTERS': (0.392, 0.525, 0.659, 0.792, 0.925)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    return scope['inspect_daily_reward_status']


class TestDailyRewardStatusInspection(unittest.TestCase):
    def test_reward_mode_never_enters_claim_or_farming_path(self):
        task = DailyHarness(True)
        task.config = {REWARD_STATUS_ONLY: True}
        task.inspect_daily_reward_status = lambda: task.calls.append('reward-status') or True
        self.assertTrue(task.run())
        self.assertEqual(task.calls, ['validate', 'base', 'main', 'reward-status', 'main'])

    def test_conflicting_inspection_modes_fail_before_input(self):
        task = DailyHarness(True)
        task.config[REWARD_STATUS_ONLY] = True
        with self.assertRaisesRegex(ValueError, 'one daily inspection'):
            task.run()
        self.assertEqual(task.calls, [])

    def test_reward_status_uses_existing_saved_account_selection(self):
        task = MultiAccountHarness()
        task.config = {REWARD_STATUS_ONLY: True, INSPECTION_ACCOUNT: 'fixture-account'}
        task.run()
        self.assertLess(task.calls.index('select-account'), task.calls.index('inspect'))
        self.assertEqual(task.calls.count('inspect'), 1)

    def test_unreadable_or_insufficient_activity_does_not_probe_or_claim(self):
        method = inspection_method()
        for readable, ready in ((False, True), (True, False)):
            task = SimpleNamespace(open_daily=lambda: (0, ready), _daily_points_read_valid=readable)
            self.assertFalse(method(task))

    def test_every_reward_marker_is_required_on_one_recognition_frame(self):
        method = inspection_method()
        template = cv2.imread(str(Path(__file__).parents[1] / 'src/task/resources/daily_reward_claimed_check.png'))
        self.assertIsNotNone(template)
        for missing in (None, 0, 1, 2, 3, 4):
            with self.subTest(missing=missing):
                frame = np.zeros((2160, 3840, 3), dtype=np.uint8)
                for index, center in enumerate((0.392, 0.525, 0.659, 0.792, 0.925)):
                    if index != missing:
                        left, top = round(center * 3840) - 45, 1865
                        frame[top:top+80, left:left+90] = template
                seen = []
                expected_frame = frame
                def find_one(name, *, template, frame, threshold, box):
                    self.assertEqual(name, 'daily_reward_claimed_check')
                    self.assertIs(frame, expected_frame)
                    x1,y1,x2,y2 = box
                    result = cv2.matchTemplate(frame[y1:y2,x1:x2], template, cv2.TM_CCOEFF_NORMED)
                    _, score, _, _ = cv2.minMaxLoc(result)
                    seen.append(box)
                    return score >= threshold
                task = SimpleNamespace(open_daily=lambda: (180, True), _daily_points_read_valid=True,
                                       frame=frame, find_one=find_one,
                                       box_of_screen=lambda left,top,right,bottom: (round(left*3840),round(top*2160),round(right*3840),round(bottom*2160)),
                                       info_set=lambda *args: None)
                self.assertIs(method(task), missing is None)
                if missing is None:
                    self.assertEqual(len(seen), 5)
                    self.assertEqual(len(set(seen)), 5)


if __name__ == '__main__':
    unittest.main()
