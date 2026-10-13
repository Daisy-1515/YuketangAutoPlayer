"""用本地媒体验证延迟加载、后台倍速与续播、自然结束和控制台渲染。"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from common import make_driver
from test_playback import player_functions
from selenium.webdriver.support.ui import WebDriverWait

for name in ('main.py', 'common.py', 'webui.py', 'tests/test_playback.py', 'tests/browser_check.py'):
    compile((ROOT / name).read_text(encoding='utf-8'), name, 'exec')
print('Python syntax: passed', flush=True)

sample = {'settings': {'host': 'www.yuketang.cn', 'course_url': '', 'headless': True,
                      'parallel': 5, 'has_cookie': False},
          'login': {'state': 'idle', 'message': '本地测试'},
          'courses': {'items': [], 'error': '', 'expired': False, 'loading': False},
          'player': {'running': True, 'exit_code': None, 'stopped': False},
          'status': {'videos': [dict(video=f'本地视频 {index}', duration=45,
                                    current_time=index * 5, rate=2, muted=True)
                                for index in (1, 2)]},
          'screenshot': 0, 'logs': []}


class FixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path.startswith('/api/state'):
            body = json.dumps(sample, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
        else:
            super().do_GET()


output = ROOT / 'output' / 'verification'
output.mkdir(parents=True, exist_ok=True)
with TemporaryDirectory(prefix='local-playback-', dir=output) as temporary:
    fixture = Path(temporary).resolve()
    assert fixture.parent == output.resolve()
    with wave.open(str(fixture / 'sound.wav'), 'wb') as media:
        media.setnchannels(1)
        media.setsampwidth(2)
        media.setframerate(8000)
        media.writeframes(b'\0\0' * 8000 * 45)
    with wave.open(str(fixture / 'short.wav'), 'wb') as media:
        media.setnchannels(1)
        media.setsampwidth(2)
        media.setframerate(8000)
        media.writeframes(b'\0\0' * 8000 * 2)
    fixture.joinpath('player.html').write_text('''<!doctype html>
        <meta charset="utf-8"><div class="xtplayer"></div>
        <script>setTimeout(() => {
            const video = document.createElement('video');
            video.src = 'sound.wav'; video.controls = true;
            window.mediaEvents = [];
            for (const name of ['pause', 'ended', 'play', 'seeking', 'seeked']) {
                video.addEventListener(name, () => window.mediaEvents.push({name,
                    time: video.currentTime, ended: video.ended, paused: video.paused}));
            }
            document.body.appendChild(video);
        }, 1200);</script>''', encoding='utf-8')
    fixture.joinpath('frame.html').write_text(
        '<!doctype html><iframe src="player.html" width="800" height="400"></iframe>',
        encoding='utf-8')
    fixture.joinpath('short.html').write_text(
        fixture.joinpath('player.html').read_text(encoding='utf-8').replace('sound.wav', 'short.wav'),
        encoding='utf-8')
    fixture.joinpath('ui.html').write_bytes((ROOT / 'webui.html').read_bytes())
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(FixtureHandler, directory=str(fixture)))
    Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    browser = None
    try:
        browser = make_driver(headless=True)
        browser.implicitly_wait(10)
        namespace = player_functions(browser)
        namespace.update(output_dir=lambda: str(fixture),
                         mute1video=lambda: browser.execute_script('video.muted = true;'),
                         change2speed2=lambda: False)
        wait = WebDriverWait(browser, 10)
        handles = []
        for page in ('player.html', 'frame.html'):
            if handles:
                browser.switch_to.new_window('tab')
            browser.get(f'{url}/{page}')
            started = time.monotonic()
            namespace['wait_video']()
            elapsed = time.monotonic() - started
            assert elapsed < 5, f'视频加载被隐式等待拖慢: {elapsed}'
            namespace['start_playback']()
            wait.until(lambda d: d.execute_script(
                'return !video.paused && video.playbackRate === 2 && video.muted;'))
            handles.append(browser.current_window_handle)
            print(f'Delayed {page}: located in {elapsed:.2f}s, playing at 2x', flush=True)

        for handle in handles:
            browser.switch_to.window(handle)
            namespace['wait_video']()
            browser.execute_script('video.playbackRate = 1; video.muted = false; video.pause();')
            wait.until(lambda d: d.execute_script('''return !video.paused && video.muted
                && video.playbackRate === 2 && video.defaultPlaybackRate === 2;'''))
            browser.execute_script('''const started = video.currentTime;
                setTimeout(() => { window.checked = {hidden: document.hidden,
                    paused: video.paused, rate: video.playbackRate,
                    advanced: video.currentTime - started}; }, 2000);''')
        browser.switch_to.new_window('tab')
        browser.get('about:blank')
        browser.execute_cdp_cmd('Page.bringToFront', {})
        time.sleep(2.4)
        for handle in handles:
            browser.switch_to.window(handle)
            namespace['wait_video']()
            observed = browser.execute_script('return window.checked;')
            assert observed and observed['hidden'] and not observed['paused'], observed
            assert observed['rate'] == 2 and observed['advanced'] > 2.5, observed
            print('Background playback:', json.dumps(observed), flush=True)
        # 本地文件服务器不支持媒体 Range seek；使用短视频真实播完验证结束事件。
        browser.switch_to.new_window('tab')
        browser.get(f'{url}/short.html')
        namespace['wait_video']()
        namespace['start_playback']()
        try:
            wait.until(lambda d: d.execute_script(
                'return video.ended && !!document.querySelector("#LetMeFly_Finished");'))
        except Exception:
            print('Completion diagnostic:', browser.execute_script('''return {
                ended: video.ended, time: video.currentTime, duration: video.duration,
                paused: video.paused, marker: !!document.querySelector('#LetMeFly_Finished'),
                events: window.mediaEvents.slice(-15)};'''), flush=True)
            raise
        time.sleep(0.5)
        assert browser.execute_script('return video.ended;'), '视频结束后被重新播放'
        print('Natural completion: finished marker present, no restart', flush=True)
        browser.get(f'{url}/ui.html')
        wait.until(lambda d: len(d.find_elements('css selector', '.now-item')) == 2)
        assert len(browser.find_elements('css selector', '.now-item .badge')) == 0
        assert all('2 倍速' in row.text for row in browser.find_elements('css selector', '.now-item'))
        browser.execute_script('document.getElementById("nowList").scrollIntoView({block: "center"});')
        browser.save_screenshot(str(output / 'playback-ui.png'))
        print('Console rendering: 2 rows at 2x, no exclusive-play badge', flush=True)
    finally:
        if browser is not None:
            browser.quit()
        server.shutdown()
        server.server_close()
