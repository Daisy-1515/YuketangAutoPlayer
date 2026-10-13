"""播放调度回归检查；只加载函数定义，避免 import main 时启动真实课程。"""

import ast
from pathlib import Path
import unittest
from unittest.mock import Mock, call


ROOT = Path(__file__).resolve().parents[1]


def player_functions(driver=None):
    source = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8'))
    source.body = [node for node in source.body
                   if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
    namespace = {'__name__': 'player_test'}
    exec(compile(source, str(ROOT / 'main.py'), 'exec'), namespace)
    namespace.update(driver=driver if driver is not None else Mock(),
                     COURSE_URL='https://www.yuketang.cn/example-course',
                     PARALLEL=3, IMPLICITLY_WAIT=10, sleep=Mock(), print=Mock())
    return namespace


class PlaybackSchedulingTests(unittest.TestCase):
    def test_player_wait_does_not_block_on_missing_iframes(self):
        namespace = player_functions()
        video = object()
        namespace['find_video'] = Mock(return_value=video)

        self.assertIs(namespace['wait_video'](), video)
        self.assertEqual(namespace['driver'].implicitly_wait.call_args_list,
                         [call(0), call(10)])

    def test_implicit_wait_is_restored_when_page_changes(self):
        namespace = player_functions()
        namespace['find_video'] = Mock(side_effect=RuntimeError('页面加载失败'))

        with self.assertRaisesRegex(RuntimeError, '页面加载失败'):
            namespace['wait_video']()
        self.assertEqual(namespace['driver'].implicitly_wait.call_args_list,
                         [call(0), call(10)])

    def slot_functions(self, driver=None):
        namespace = player_functions(driver)
        namespace.update(name_of=lambda video: video, wait_video=Mock(),
                         read_playback=Mock(return_value={'rate': 2, 'ended': False}),
                         start_playback=Mock(), write_status=Mock())
        return namespace

    def test_new_video_starts_while_another_is_playing(self):
        driver = Mock()
        driver.execute_script.side_effect = AssertionError('不应检测播放器内部设置')
        namespace = self.slot_functions(driver)
        namespace['open_video'] = Mock(return_value='second-video')
        slots = {'first-video': {'name': '第一段', 'playback': {'rate': 2}}}

        course_window = namespace['open_slot']('第二段', slots, 'course')

        self.assertEqual(course_window, 'course')
        self.assertEqual(set(slots), {'first-video', 'second-video'})
        namespace['start_playback'].assert_called_once_with()
        driver.close.assert_not_called()

    def test_inline_video_keeps_playing_in_its_own_tab(self):
        driver = Mock(current_window_handle='course')
        driver.switch_to.new_window.side_effect = (
            lambda kind: setattr(driver, 'current_window_handle', 'new-course'))
        namespace = self.slot_functions(driver)
        namespace['open_video'] = Mock(return_value=None)
        slots = {}

        course_window = namespace['open_slot']('页内视频', slots, 'course')

        self.assertEqual(course_window, 'new-course')
        self.assertEqual(slots['course']['name'], '页内视频')
        driver.switch_to.new_window.assert_called_once_with('tab')
        driver.get.assert_called_once_with(namespace['COURSE_URL'])
        driver.close.assert_not_called()

    def test_finished_inline_video_closes_without_navigating_other_tabs(self):
        namespace = self.slot_functions()
        namespace['read_playback'].return_value = {'ended': True}

        finished = namespace['poll_slot']('old-course', {'name': '页内视频'})

        self.assertTrue(finished)
        namespace['driver'].switch_to.window.assert_called_once_with('old-course')
        namespace['driver'].close.assert_called_once_with()
        namespace['driver'].get.assert_not_called()

    def test_scheduler_fills_and_reuses_all_parallel_slots(self):
        namespace = player_functions(Mock(current_window_handle='course'))
        videos = ['第一段', '第二段', '第三段', '第四段']
        opened, finished, counts = [], set(), []

        def open_slot(video, slots, course_window):
            opened.append(video)
            slots[video] = {'name': video}
            counts.append(len(slots))
            return course_window

        def poll_slot(handle, slot):
            if len(opened) < namespace['PARALLEL']:
                return False
            finished.add(slot['name'])
            return True

        namespace.update(
            activate=Mock(), name_of=lambda video: video,
            load_course_items=lambda: [video for video in videos if video not in finished],
            getAllvideos_notFinished=lambda items: items,
            open_slot=open_slot, poll_slot=poll_slot,
            write_status=lambda slots: counts.append(len(slots)),
        )

        namespace['play_all']()

        self.assertEqual(opened, videos)
        self.assertEqual(finished, set(videos))
        self.assertEqual(max(counts), 3)
        self.assertTrue(all(count <= 3 for count in counts))


if __name__ == '__main__':
    unittest.main()
