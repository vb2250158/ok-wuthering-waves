import ast
from pathlib import Path
import re
from types import SimpleNamespace
import unittest


source = Path(__file__).parents[1] / 'src/task/DailyTask.py'
tree = ast.parse(source.read_text(encoding='utf-8'))
task_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'DailyTask')
method = next(node for node in task_class.body if isinstance(node, ast.FunctionDef) and node.name == 'get_total_daily_points')
scope = {'re': re}
exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), 'exec'), scope)


class ActivityReadTests(unittest.TestCase):
    def read(self, samples):
        task = SimpleNamespace(logs=[], waits=[], calls=0)

        def ocr(*args, **kwargs):
            sample = samples[min(task.calls, len(samples) - 1)]
            task.calls += 1
            return [SimpleNamespace(name=text) for text in sample]

        task.ocr = ocr
        task.sleep = task.waits.append
        task.info_set = lambda *entry: task.logs.append(entry)
        return task, lambda: scope['get_total_daily_points'](task)

    def test_zero_and_completed_values(self):
        for value in (0, 100, 110, 120, 240):
            task, read = self.read([[str(value)]])
            self.assertEqual(read(), value)
            self.assertTrue(task._daily_points_read_valid)
            self.assertEqual(task.calls, 1)

    def test_transient_failure_recovers(self):
        task, read = self.read([[], ['110']])
        self.assertEqual(read(), 110)
        self.assertEqual(task.waits, [0.3])

    def test_unreadable_invalid_and_conflicting_values_fail_closed(self):
        for sample in ([], ['unknown'], ['-1'], ['110', '20']):
            task, read = self.read([sample])
            with self.assertRaisesRegex(ValueError, 'refusing'):
                read()
            self.assertEqual(task.calls, 3)
            self.assertFalse(task._daily_points_read_valid)
            self.assertNotIn(('total daily points', 0), task.logs)


if __name__ == '__main__':
    unittest.main()
