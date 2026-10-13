"""YuketangAutoPlayer 本地网页控制台：扫码登录、选择课程、启动/停止播放、查看进度。"""

import atexit
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import itertools
import json
import os
import subprocess
import sys
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser

from selenium.common.exceptions import WebDriverException

from common import (HOST_PATTERN, LoginExpired, app_dir, course_entry, fetch_courses,
                    is_logged_out, make_driver, output_dir, qr_login, read_settings,
                    update_settings)


DEFAULT_PORT = 8765
DEFAULT_HOST = 'www.yuketang.cn'
DEFAULT_PARALLEL = 3
MAX_PARALLEL = 5
PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'webui.html')


class Log:
    """界面日志：带递增序号，前端按序号增量拉取。"""

    def __init__(self):
        self.lines = deque(maxlen=1000)
        self.counter = itertools.count(1)
        self.lock = threading.Lock()

    def add(self, text):
        print(text, flush=True)
        with self.lock:
            self.lines.append((next(self.counter), text))

    def since(self, seq):
        with self.lock:
            return [line for line in self.lines if line[0] > seq]


log = Log()


class LoginSession:
    """一个只用于扫码登录的独立 Chrome，登录成功后自动关闭。"""

    def __init__(self):
        self.driver = None
        self.state = 'idle'  # idle / starting / waiting_qr
        self.message = ''

    @property
    def active(self):
        return self.state != 'idle'

    def start(self, host):
        if self.active:
            raise ValueError('登录浏览器已打开')
        if not HOST_PATTERN.match(host):
            raise ValueError('雨课堂域名格式不正确，例如 www.yuketang.cn')
        self.state, self.message = 'starting', '正在启动浏览器...'
        threading.Thread(target=self._run, args=(host,), daemon=True).start()

    def _run(self, host):
        try:
            self.driver = make_driver(False)
            self.driver.implicitly_wait(10)
            self.state, self.message = 'waiting_qr', '请用微信扫描弹出的浏览器中的二维码登录'
            log.add(f'[登录] {self.message}')
            sessionid = qr_login(self.driver, f'https://{host}/')
            if not sessionid:
                raise RuntimeError('登录成功但未找到 sessionid')
            # 部分学校登录后会跳到独立域名，登录态只在该域名下有效
            real_host = urlparse(self.driver.current_url).hostname or ''
            update_settings({'cookie': sessionid,
                             'host': real_host if HOST_PATTERN.match(real_host) else host})
            log.add('[登录] 扫码登录成功，登录态已保存，正在读取课程列表...')
            self._close()
            courses.load()
        except (WebDriverException, TimeoutError, RuntimeError, OSError) as error:
            if self.active:
                log.add(f'[登录] 失败: {getattr(error, "msg", None) or error}')
            self._close()

    def cancel(self):
        if self.state == 'starting':
            raise ValueError('浏览器正在启动，请稍候')
        if self.active:
            log.add('[登录] 已取消')
        self._close()

    def _close(self):
        driver, self.driver = self.driver, None
        self.state, self.message = 'idle', ''
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass


def saved_host(settings):
    """登录时保存的域名；旧配置没有 host 时从课程地址推断。"""
    host = settings.get('host', '').lower()
    if not HOST_PATTERN.match(host):
        host = (urlparse(settings.get('course_url', '')).hostname or '').lower()
    return host if HOST_PATTERN.match(host) else DEFAULT_HOST


class CourseList:
    """用保存的登录态读取课程列表，供网页点选。"""

    def __init__(self):
        self.items = []
        self.error = ''
        self.expired = False
        self.loading = False
        self.lock = threading.Lock()
        self.load_lock = threading.Lock()  # 串行读取，保证最后一次读取用的是最新登录态

    def load(self, auto_login=False):
        with self.load_lock:
            with self.lock:
                self.loading = True
            self._load(auto_login)

    def _load(self, auto_login):
        items, error, expired, need_login = [], '', False, False
        try:
            settings = read_settings()
            if not settings.get('cookie'):
                error, need_login = '请先扫码登录', True
            else:
                host = saved_host(settings)
                items = [course_entry(host, item) for item in fetch_courses(host, settings['cookie'])]
                items.sort(key=lambda item: item['term'], reverse=True)  # 最新学期在前
                if not items:
                    error = '这个账号下没有找到课程'
                log.add(f'[课程] 已读取 {len(items)} 门课程')
        except LoginExpired:
            error, expired, need_login = '登录已失效，请重新扫码登录', True, True
        except (RuntimeError, ValueError, OSError) as e:
            error = str(e)
        if error and error != '请先扫码登录':
            log.add(f'[课程] {error}')
        with self.lock:
            self.items, self.error, self.expired, self.loading = items, error, expired, False
        if auto_login and need_login:
            self._auto_login(settings)

    @staticmethod
    def _auto_login(settings):
        """未登录或登录失效时直接弹出扫码窗口；登录后的读取不走这里，避免反复弹窗。"""
        if login.active or player.running:
            return
        try:
            login.start(saved_host(settings))
        except ValueError as error:
            log.add(f'[登录] 无法自动打开扫码窗口: {error}')
            return
        log.add('[登录] 已自动打开扫码窗口')

    def load_in_background(self, auto_login=False):
        threading.Thread(target=self.load, args=(auto_login,), daemon=True).start()

    def snapshot(self):
        with self.lock:
            return {'items': self.items, 'error': self.error,
                    'expired': self.expired, 'loading': self.loading}


def is_true(value):
    return (value or '').lower() in ('1', 'true', 'yes', 'on')


def parallel_of(settings):
    try:
        return min(MAX_PARALLEL, max(1, int(settings.get('parallel', ''))))
    except ValueError:
        return DEFAULT_PARALLEL


def is_course_url(url):
    parsed = urlparse(url)
    return (parsed.scheme == 'https' and bool(HOST_PATTERN.match(parsed.hostname or ''))
            and parsed.path.strip('/') not in ('', 'v2/web/index')
            and 'courselist' not in url and not is_logged_out(url))


class PlayerProcess:
    """以子进程运行 main.py，采集输出。"""

    def __init__(self):
        self.process = None
        self.exit_code = None
        self.stopped = False

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None

    def start(self):
        if self.running:
            raise ValueError('已经在播放中')
        if login.active:
            raise ValueError('请先完成或取消登录浏览器中的操作')
        settings = read_settings()
        if not settings.get('course_url'):
            raise ValueError('请先选择课程')
        if not settings.get('cookie') and is_true(settings.get('headless')):
            raise ValueError('无窗口模式需要先扫码登录')
        for name in ('playback-status.json', 'playback.png'):
            path = os.path.join(output_dir(), name)
            if os.path.exists(path):
                os.remove(path)
        if getattr(sys, 'frozen', False):
            command = [sys.executable, '--player']
        else:
            command = [sys.executable, '-u', os.path.join(app_dir(), 'main.py')]
        env = os.environ.copy()
        env.pop('YUKETANG_SESSIONID', None)  # 以 config.ini 中刚保存的登录态为准
        env.update(PYTHONUTF8='1', PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
        self.exit_code = None
        self.stopped = False
        self.process = subprocess.Popen(
            command, cwd=app_dir(), env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1,
        )
        log.add('[播放] 播放进程已启动')
        threading.Thread(target=self._read, args=(self.process,), daemon=True).start()

    def _read(self, process):
        for line in process.stdout:
            line = line.rstrip()
            if line:
                log.add(line)
        self.exit_code = process.wait()
        log.add(f'[播放] 播放进程已退出（代码 {self.exit_code}）')

    def stop(self):
        if not self.running:
            return
        log.add('[播放] 正在停止...')
        self.stopped = True
        if os.name == 'nt':
            # /T 连带结束 chromedriver 与 Chrome
            subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                           capture_output=True)
        else:
            self.process.terminate()


login = LoginSession()
courses = CourseList()
player = PlayerProcess()


def read_status():
    try:
        with open(os.path.join(output_dir(), 'playback-status.json'), encoding='utf-8') as f:
            status = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(status, dict):
        return None
    status.pop('debugger_address', None)
    if 'videos' not in status:  # 旧版播放进程只写单个视频
        status = {'videos': [status]}
    if not isinstance(status['videos'], list):
        return None
    for video in status['videos']:
        if isinstance(video, dict):
            video.pop('page_url', None)
    return status


def screenshot_mtime():
    try:
        return os.path.getmtime(os.path.join(output_dir(), 'playback.png'))
    except OSError:
        return 0


def current_state(since):
    settings = read_settings()
    return {
        'settings': {
            'host': saved_host(settings),
            'course_url': settings.get('course_url', ''),
            'headless': is_true(settings.get('headless')),
            'parallel': parallel_of(settings),
            'has_cookie': bool(settings.get('cookie')),  # 不回显 sessionid
        },
        'login': {'state': login.state, 'message': login.message},
        'courses': courses.snapshot(),
        'player': {'running': player.running, 'exit_code': player.exit_code, 'stopped': player.stopped},
        'status': read_status(),
        'screenshot': screenshot_mtime(),
        'logs': log.since(since),
    }


class Handler(BaseHTTPRequestHandler):
    allowed_hosts = set()

    def log_message(self, format, *args):
        pass

    def _send(self, code, body, content_type='application/json; charset=utf-8'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self):
        # 防止 DNS rebinding：只接受本机地址访问
        if self.headers.get('Host', '') in self.allowed_hosts:
            return True
        self._send(403, {'error': '禁止访问'})
        return False

    def do_GET(self):
        if not self._host_ok():
            return
        parsed = urlparse(self.path)
        if parsed.path == '/':
            with open(PAGE_PATH, 'rb') as f:
                self._send(200, f.read(), 'text/html; charset=utf-8')
        elif parsed.path == '/api/state':
            try:
                since = int(parse_qs(parsed.query).get('since', ['0'])[0])
            except ValueError:
                since = 0
            self._send(200, current_state(since))
        elif parsed.path == '/api/screenshot':
            try:
                with open(os.path.join(output_dir(), 'playback.png'), 'rb') as f:
                    self._send(200, f.read(), 'image/png')
            except OSError:
                self._send(404, {'error': '暂无截图'})
        else:
            self._send(404, {'error': '未找到'})

    def do_POST(self):
        if not self._host_ok():
            return
        # 只接受 JSON，跨源页面无法在不经预检的情况下发送
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            self._send(415, {'error': '仅接受 JSON 请求'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if length > 65536:
                raise ValueError('请求过大')
            data = json.loads(self.rfile.read(length) or b'{}')
            if not isinstance(data, dict):
                raise ValueError('请求格式不正确')
            result = self._route(urlparse(self.path).path, data)
        except (ValueError, OSError) as error:
            self._send(400, {'error': str(error)})
        except WebDriverException as error:
            self._send(500, {'error': f'浏览器操作失败: {error.msg}'})
        else:
            if result is None:
                self._send(404, {'error': '未找到'})
            else:
                self._send(200, result)

    def _route(self, path, data):
        if path == '/api/login':
            login.start(str(data.get('host', '')).strip().lower())
        elif path == '/api/login/cancel':
            login.cancel()
        elif path == '/api/courses/refresh':
            courses.load_in_background(auto_login=True)
        elif path == '/api/settings':
            values = {}
            if 'course_url' in data:
                url = str(data['course_url']).strip()
                if not is_course_url(url):
                    raise ValueError('课程地址格式不正确，应为 https://xxx.yuketang.cn/... 的课程页面')
                values['course_url'] = url
            if 'headless' in data:
                values['headless'] = 'true' if data['headless'] else 'false'
            if 'parallel' in data:
                parallel = data['parallel']
                if type(parallel) is not int or not 1 <= parallel <= MAX_PARALLEL:
                    raise ValueError(f'同时播放数应为 1 到 {MAX_PARALLEL} 之间的整数')
                values['parallel'] = parallel
            if values:
                update_settings(values)
        elif path == '/api/player/start':
            player.start()
        elif path == '/api/player/stop':
            player.stop()
        else:
            return None
        return {'ok': True}


def cleanup():
    player.stop()
    login._close()


def serve(open_browser=True):
    try:
        server = ThreadingHTTPServer(('127.0.0.1', DEFAULT_PORT), Handler)
    except OSError:
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    port = server.server_address[1]
    Handler.allowed_hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
    url = f'http://127.0.0.1:{port}/'
    atexit.register(cleanup)
    print('=' * 50)
    print('YuketangAutoPlayer - 雨课堂视频自动播放器')
    print(f'控制台地址: {url}')
    print('关闭此窗口即可退出')
    print('=' * 50, flush=True)
    courses.load_in_background(auto_login=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    if '--player' in sys.argv:
        import main  # noqa: F401  模块级脚本，import 即开始播放（打包后的子进程入口）
    else:
        serve(open_browser='--no-browser' not in sys.argv)
