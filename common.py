"""main.py 与 webui.py 共用的配置读写、浏览器创建、扫码登录和课程列表逻辑。"""

import configparser
import json
import os
import re
import sys
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


PLACEHOLDER = '在此填写'
HOST_PATTERN = re.compile(r'^[a-z0-9-]+(\.[a-z0-9-]+)*\.yuketang\.cn$')
USER_AGENT = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')


def app_dir():
    """config.ini 与 output/ 所在目录；打包后为 exe 所在目录。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def config_path():
    return os.path.join(app_dir(), 'config.ini')


def output_dir():
    path = os.path.join(app_dir(), 'output', 'playwright')
    os.makedirs(path, exist_ok=True)
    return path


def create_config_template(path):
    """创建config.ini模板文件"""
    config = configparser.ConfigParser()
    config['Settings'] = {
        'headless': 'false',
        'course_url': 'https://在此填写你的课程URL',
        'cookie': '在此填写你的sessionid',
        'implicitly_wait': '10',
        'parallel': '3',
    }

    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('; YuketangAutoPlayer 配置文件\n')
            f.write('; headless: 是否无窗口运行 (true/false)，首次使用建议false\n')
            f.write('; course_url: 你的课程地址，必须包含 https:// 协议头\n')
            f.write(';             例如: https://www.yuketang.cn/v2/web/studentLog/12345678\n')
            f.write('; cookie: 你的sessionid值，可在图形界面中扫码登录自动获取\n')
            f.write('; implicitly_wait: 元素查找超时时间(秒)，一般不需要修改\n')
            f.write('; parallel: 同时播放的视频数(1-5)，1 为逐个播放；开启了防刷的视频总是单独播放\n\n')
            config.write(f)
    except Exception as e:
        print(f'创建配置文件失败: {e}')


def read_settings():
    """读取 [Settings]，占位符视为未填写。"""
    path = config_path()
    if not os.path.exists(path):
        create_config_template(path)
    config = configparser.ConfigParser(interpolation=None)
    config.read(path, encoding='utf-8')
    settings = dict(config['Settings']) if config.has_section('Settings') else {}
    return {key: '' if PLACEHOLDER in value else value.strip()
            for key, value in settings.items()}


def update_settings(values):
    """逐项替换 config.ini 中的配置，保留注释与其他内容，原子写入。"""
    path = config_path()
    if not os.path.exists(path):
        create_config_template(path)
    with open(path, 'rb') as f:
        content = f.read().decode('utf-8')
    newline = '\r\n' if '\r\n' in content else '\n'
    section = re.compile(r'(?m)^\[Settings\][ \t]*(?=\r?$)')
    for key, value in values.items():
        value = str(value)
        if '\n' in value or '\r' in value:
            raise ValueError(f'{key} 的值格式不正确')
        content, count = re.subn(rf'(?m)^{re.escape(key)}[ \t]*=[^\r\n]*',
                                 lambda _: f'{key} = {value}', content, count=1)
        if count:
            continue
        if not section.search(content):
            content = content.rstrip('\r\n') + f'{newline}{newline}[Settings]{newline}'
        content = section.sub(lambda m: f'{m.group(0)}{newline}{key} = {value}', content, count=1)
    temporary = path + '.tmp'
    try:
        with open(temporary, 'wb') as f:
            f.write(content.encode('utf-8'))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def make_driver(headless=False):
    option = webdriver.ChromeOptions()
    if headless:
        option.add_argument('--headless=new')
        # 无窗口时 maximize 只有约 800x600，播放器的倍速按钮会落在视口外点不到
        option.add_argument('--window-size=1440,900')
    # 打包后 chromedriver.exe 被解压到 _MEIPASS，与本文件同目录
    driver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chromedriver.exe')
    service = Service(driver_path) if os.path.exists(driver_path) else Service()
    return webdriver.Chrome(service=service, options=option)


def home_url_of(url):
    return 'https://' + url.split('://', 1)[-1].split('/')[0] + '/'


def is_login_page(url):
    """雨课堂网页版登录页 https://{host}/web，未登录访问课程也会被重定向到这里。"""
    return urlparse(url).path.rstrip('/') == '/web'


def is_logged_out(url):
    return 'pro/portal/home' in url or is_login_page(url)


def get_sessionid(driver):
    cookie = driver.get_cookie('sessionid')
    return cookie['value'] if cookie else ''


def qr_login(driver, home_url, timeout=300):
    """打开登录页等待扫码，成功后返回 sessionid。"""
    # 首页已改为宣传页，网页版登录页 /web 直接显示二维码
    driver.get(home_url.rstrip('/') + '/web')
    print('请扫码登录', flush=True)
    deadline = monotonic() + timeout
    while True:
        # 登录成功后页面会跳离 /web（通常到 /v2/web）
        url = driver.current_url
        if url.startswith('http') and not is_logged_out(url):
            sessionid = get_sessionid(driver)
            if sessionid:
                break
        if monotonic() > deadline:
            raise TimeoutError('扫码登录超时')
        sleep(0.5)
    print('登录成功', flush=True)
    return sessionid


class LoginExpired(Exception):
    pass


def fetch_courses(host, sessionid):
    """读取“我听的课”列表（与开源项目相同的 courses/list 接口）。"""
    if not HOST_PATTERN.match(host or ''):
        raise ValueError('雨课堂域名格式不正确')  # sessionid 只发往 *.yuketang.cn
    request = Request(f'https://{host}/v2/api/web/courses/list?identity=2', headers={
        'Cookie': f'sessionid={sessionid}',
        'User-Agent': USER_AGENT,
        'Referer': f'https://{host}/v2/web/index',
        'xtbz': 'ykt',
        'X-Client': 'web',
    })
    try:
        with urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        if error.code in (401, 403):
            raise LoginExpired() from None
        raise RuntimeError(f'无法连接雨课堂（HTTP {error.code}），请稍后重试') from None
    except (URLError, OSError, ValueError):
        raise RuntimeError('无法连接雨课堂，请检查网络') from None
    errcode = data.get('errcode') if isinstance(data, dict) else None
    if errcode in (401000, 401002):
        raise LoginExpired()
    if errcode != 0:
        raise RuntimeError(f'读取课程列表失败（错误码 {errcode}）')
    items = (data.get('data') or {}).get('list') or []
    return [item for item in items if isinstance(item, dict) and item.get('classroom_id')]


def course_entry(host, item):
    """整理一门课的显示信息，并拼出课程「学习内容」页地址。"""
    course = item.get('course') or {}
    teacher = item.get('teacher') or {}
    classroom_id = item['classroom_id']
    url = f'https://{host}/v2/web/studentLog/{classroom_id}'
    university_id = course.get('university_id')
    if university_id:
        url += (f'?university_id={university_id}&platform_id=3'
                f'&classroom_id={classroom_id}&content_url=')
    return {
        'classroom_id': str(classroom_id),
        'name': str(course.get('name') or item.get('name') or ''),
        'classroom': str(item.get('name') or ''),
        'teacher': str(teacher.get('name') or ''),
        'term': str(item.get('term') or ''),
        'url': url,
    }
