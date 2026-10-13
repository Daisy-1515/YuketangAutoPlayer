'''
Author: LetMeFly, Guo-Chenxu, Crsuh2er0, 420xincheng, tkzzzzzz6
Date: 2023-09-12 20:49:21
LastEditors: LetMeFly.xyz
LastEditTime: 2025-11-13 22:44:00
Description: 开源于https://github.com/LetMeFly666/YuketangAutoPlayer 欢迎issue、PR
'''
from selenium.common.exceptions import ElementNotInteractableException, WebDriverException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.remote.webelement import WebElement
from typing import List
from time import sleep
import random
import os
import sys
import configparser
import json

from common import (config_path, create_config_template, home_url_of, is_logged_out,
                    make_driver, output_dir, qr_login, update_settings)


def pause_exit(code):
    """命令行运行时等待回车再退出；被图形界面以子进程启动时直接退出。"""
    if sys.stdin is not None and sys.stdin.isatty():
        input('按回车键退出...')
    sys.exit(code)


def load_config():
    """从config.ini加载配置"""
    config = configparser.ConfigParser(interpolation=None)

    # 优先从可执行文件所在目录查找config.ini（支持打包后的exe）
    path = config_path()

    if not os.path.exists(path):
        # 如果exe目录没有，尝试从当前工作目录查找
        path = os.path.join(os.getcwd(), 'config.ini')

    if not os.path.exists(path):
        # 如果config.ini不存在，创建模板
        print(f'未找到配置文件，正在创建模板: {path}')
        create_config_template(path)
        print('\n请编辑 config.ini 文件填写你的配置信息后重新运行程序（或运行 webui.py 扫码登录）')
        pause_exit(0)

    try:
        config.read(path, encoding='utf-8')
        print(f'成功加载配置文件: {path}')
        return config
    except Exception as e:
        print(f'读取配置文件失败: {e}')
        pause_exit(1)


# 加载配置
print('='*50)
print('YuketangAutoPlayer - 雨课堂视频自动播放器')
print('='*50)

config = load_config()

# 读取配置项
try:
    IF_HEADLESS = config.getboolean('Settings', 'headless', fallback=False)
    COURSE_URL = config.get('Settings', 'course_url', fallback='')
    COOKIE = os.environ.get('YUKETANG_SESSIONID') or config.get('Settings', 'cookie', fallback='')
    IMPLICITLY_WAIT = config.getint('Settings', 'implicitly_wait', fallback=10)
    PARALLEL = min(5, max(1, config.getint('Settings', 'parallel', fallback=3)))
except Exception as e:
    print(f'\n配置文件格式错误: {e}')
    pause_exit(1)

# 验证配置
if not COURSE_URL or '在此填写' in COURSE_URL:
    print('\n错误: 检测到课程URL未正确填写!')
    print('请编辑 config.ini 文件填写 course_url，或在图形界面中选择课程')
    pause_exit(1)
if '在此填写' in COOKIE:
    COOKIE = ''
if not COOKIE and IF_HEADLESS:
    print('\n错误: 未配置登录态，无窗口模式下无法扫码登录')
    print('请在图形界面中扫码登录，或关闭无窗口模式')
    pause_exit(1)

print(f'\n配置信息:')
print(f'  无窗口模式: {IF_HEADLESS}')
print(f'  课程URL: {COURSE_URL[:50]}...' if len(COURSE_URL) > 50 else f'  课程URL: {COURSE_URL}')
print(f'  Cookie已配置: {"✓" if COOKIE else "✗（将扫码登录）"}')
print(f'  同时播放: {PARALLEL} 个视频（开启了防刷的视频单独播放）')
print('='*50 + '\n')


driver = make_driver(IF_HEADLESS)
if not IF_HEADLESS:  # 无窗口时 maximize 会把窗口缩回 800x600，窗口大小由 make_driver 设置
    driver.maximize_window()
driver.implicitly_wait(IMPLICITLY_WAIT)
IS_COMMONUI = False

def str2dic(s):
    d = dict()
    for i in s.split('; '):
        temp = i.split('=')
        d[temp[0]] = temp[1]
    return d


def setCookie(cookies):
    driver.delete_all_cookies()
    for name, value in cookies.items():
        driver.add_cookie({'name': name, 'value': value, 'path': '/'})


def text_of(element: WebElement):
    """元素文本；.text 只返回可见文本，未渲染完或折叠时为空，这里用 textContent。"""
    return (element.get_attribute('textContent') or '').strip()


def click(element: WebElement):
    try:
        element.click()
    except ElementNotInteractableException:  # 折叠章节中的条目不可见，改用 JS 点击
        driver.execute_script('arguments[0].click();', element)


def ifVideo(div: WebElement):
    for i in div.find_elements(By.TAG_NAME, 'i'):
        i_class = i.get_attribute('class')
        if 'icon--suo' in i_class:  # 锁的图标，表明视频未开放
            return False
    
    if IS_COMMONUI:  # www.yuketang.cn，非grsbupt.yuketang.cn，属新版ui
        try:
            span = div.find_element(By.CSS_SELECTOR, 'span.leaf-flag')
        except:
            return False
        return '视频' in text_of(span)
    
    try:
        i = div.find_element(By.TAG_NAME, 'i')
    except:
        return False  # 每个小结后面都存在空行<li>
    i_class = i.get_attribute('class')
    return 'icon--shipin' in i_class


def is_unfinished_video(div: WebElement):
    text = text_of(div)
    # 文本为空时无法判断是否已完成，跳过
    return bool(text) and '已完成' not in text and '截止' not in text and ifVideo(div)


def getAllvideos_notFinished(allClasses: List[WebElement]):
    driver.implicitly_wait(0.1)  # 找不到元素时会找满implicitly_wait秒
    allVideos = [thisClass for thisClass in allClasses if is_unfinished_video(thisClass)]
    driver.implicitly_wait(IMPLICITLY_WAIT)
    print(f'找到 {len(allVideos)} 个未完成的视频')
    return allVideos


def get1video_notFinished(allClasses: List[WebElement]):
    for thisClass in allClasses:
        if is_unfinished_video(thisClass):
            return thisClass
    return None


homePageURL = home_url_of(COURSE_URL)
if 'www.yuketang.cn' in homePageURL:
    IS_COMMONUI = True
# driver.get('https://grsbupt.yuketang.cn/')
driver.get(homePageURL)
if COOKIE:
    setCookie({'sessionid': COOKIE})
    driver.get(COURSE_URL)
    sleep(3)
if not COOKIE or is_logged_out(driver.current_url):
    if COOKIE:
        print('cookie失效或设置有误，需要重新扫码登录')
    if IF_HEADLESS:
        driver.quit()
        print('无窗口模式下无法扫码，请在图形界面中重新扫码登录')
        pause_exit(1)
    try:
        new_cookie = qr_login(driver, homePageURL, timeout=600)
    except TimeoutError as e:
        driver.quit()
        print(e)
        pause_exit(1)
    if new_cookie:
        update_settings({'cookie': new_cookie})
        print('新的登录态已保存到 config.ini')
    driver.get(COURSE_URL)


def change2speed2():
    """通过播放器的倍速菜单切到 2 倍速（菜单最高 2 倍，直接改 playbackRate 会被播放器每秒改回）。"""
    for attempt in range(3):
        try:
            speedbutton = driver.find_element(By.TAG_NAME, 'xt-speedbutton')
            ActionChains(driver).move_to_element(speedbutton).perform()
            ul = speedbutton.find_element(By.TAG_NAME, 'ul')
            lis = ul.find_elements(By.TAG_NAME, 'li')
            li_speed2 = lis[0]
            diffY = speedbutton.location['y'] - li_speed2.location['y']
            # ActionChains(driver).move_to_element_with_offset(speedbutton, 3, 5).perform()
            # ActionChains(driver).click().perform()
            # 我也不知道为啥要一点一点移动上去，反正直接移动上去的话，点击是无效的
            for i in range(diffY // 10):  # 可能不是一个好算法
                ActionChains(driver).move_by_offset(0, -10).perform()
                sleep(0.5)
            sleep(0.8)
            ActionChains(driver).click().perform()
        except WebDriverException as e:
            print(f'切换倍速失败（第 {attempt + 1} 次）: {e.msg or e}')
        sleep(1)
        if driver.execute_script('return video.playbackRate;') == 2:
            return True
    print('未能切换到 2 倍速，将以当前倍速播放')
    return False


def mute1video():
    if driver.execute_script('return video.muted;'):
        return
    voice = driver.find_element(By.TAG_NAME, 'xt-volumebutton')
    ActionChains(driver).move_to_element(voice).perform()
    ActionChains(driver).click().perform()


def open_study_content_tab():
    """课程页默认停在「学习日志」，学习内容 iframe 被隐藏，条目不可见也点不了，先切到「学习内容」。"""
    for tab in driver.find_elements(By.XPATH, '//*[contains(@class, "rain-tabs__nav-item")]'
                                              '[normalize-space()="学习内容"]'):
        if tab.is_displayed():
            tab.click()
            sleep(2)
            return


def rendered_leaves(d):
    """leaf-detail 列表内容渲染出来后才返回，否则条目文本为空无法判断是否已完成。"""
    leaves = d.find_elements(By.CLASS_NAME, 'leaf-detail')
    return leaves if any(text_of(leaf) for leaf in leaves) else []


def load_course_items():
    """回到课程列表并返回所有学习单元；新版学习内容页的列表在 iframe 中，返回时 driver 停在该 iframe 内。"""
    global IS_COMMONUI
    driver.switch_to.default_content()
    driver.implicitly_wait(0.1)
    # 新版学习内容页使用旧版 leaf-detail 列表，并可能嵌在 iframe 中。
    allClasses = driver.find_elements(By.CLASS_NAME, 'leaf-detail')
    if not allClasses:
        for frame in driver.find_elements(By.TAG_NAME, 'iframe'):
            if '/studycontent' in (frame.get_attribute('src') or ''):
                if not frame.is_displayed():
                    open_study_content_tab()
                driver.switch_to.frame(frame)
                allClasses = WebDriverWait(driver, 30).until(rendered_leaves)
                break
    IS_COMMONUI = not bool(allClasses)
    driver.implicitly_wait(IMPLICITLY_WAIT)
    if IS_COMMONUI:
        # TODO: WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "xxx")))
        # then remove the sleep before calling function load_course_items
        # todo中改动较大需测试面较广，先用sleep代替
        scoreList = driver.find_element(By.ID, 'tab-student_school_report')
        scoreList.click()
        allClasses = driver.find_elements(By.CLASS_NAME, 'study-unit')
    if not allClasses:
        raise RuntimeError('未找到课程学习单元；请检查登录状态和学习内容地址')
    return allClasses


def name_of(video: WebElement):
    return next((line.strip() for line in text_of(video).splitlines() if line.strip()), '未命名视频')


def open_video(video: WebElement):
    """点击视频条目并切到播放页，返回新标签页句柄；视频在课程页内直接播放时返回 None。"""
    previous_windows = set(driver.window_handles)
    driver.execute_script('arguments[0].scrollIntoView(false);', video)
    if IS_COMMONUI:
        click(video.find_element(By.TAG_NAME, 'span'))
    else:
        click(video)
    WebDriverWait(driver, 30).until(
        lambda d: set(d.window_handles) - previous_windows
        or d.find_elements(By.TAG_NAME, 'video')
    )
    new_windows = set(driver.window_handles) - previous_windows
    if not new_windows:
        driver.switch_to.default_content()
        return None
    handle = next(iter(new_windows))
    activate(handle)
    return handle


def activate(handle):
    """切到该标签页并放到前台（模拟鼠标操作和防刷检查都要求页面在前台）。"""
    driver.switch_to.window(handle)
    driver.execute_cdp_cmd('Page.bringToFront', {})


def wait_video():
    WebDriverWait(driver, 10).until(lambda x: driver.execute_script('video = document.querySelector("video"); console.log(video); return video;'))  # 这里即使2次sleep3s选中的video还是null


def is_anti_brushing():
    """老师是否给该视频开启了防刷（页面隐藏或失焦即暂停）；读不到时按开启处理，只单独播放。"""
    return driver.execute_script('const p = document.querySelector(".xtplayer");'
                                 'return !(p && p.__vue__ && p.__vue__.isAntiBrushing === false);')


def start_playback():
    """在当前页开始播放：注入完成标记与自动续播，静音并切到 2 倍速。"""
    driver.execute_script('videoPlay = setInterval(function() {if (video.paused) {video.play();}}, 200);')
    driver.execute_script('setTimeout(() => clearInterval(videoPlay), 5000)')
    driver.execute_script('addFinishMark = function() {finished = document.createElement("span"); finished.setAttribute("id", "LetMeFly_Finished"); document.body.appendChild(finished); console.log("Finished");}')
    driver.execute_script('video.addEventListener("ended", addFinishMark, {once: true});')
    # 暂停后自动续播；开启了防刷的视频在页面隐藏或失焦时不续播，回到前台后再继续
    driver.execute_script('''
        antiBrushing = () => { const p = document.querySelector(".xtplayer"); return !!(p && p.__vue__ && p.__vue__.isAntiBrushing); };
        resumeVideo = () => { if (video.paused && !video.ended && !(antiBrushing() && (document.hidden || !document.hasFocus()))) { video.play(); } };
        video.addEventListener("pause", resumeVideo);
        document.addEventListener("visibilitychange", resumeVideo);
        window.addEventListener("focus", resumeVideo);
    ''')
    mute1video()
    change2speed2()
    driver.save_screenshot(os.path.join(output_dir(), 'playback.png'))


def open_slot(video: WebElement, slots, deferred, course_window):
    """打开一个视频开始播放并登记到 slots；开启了防刷且还有其他视频在播时关掉，留到之后单独播放。"""
    name = name_of(video)
    handle = open_video(video)
    wait_video()
    if handle is None:  # 在课程页内播放，播完才能回到列表，只能单独播放
        anti, exclusive, handle = is_anti_brushing(), True, course_window
    else:
        anti = is_anti_brushing()
        exclusive = anti
        if anti and slots:
            print(f'「{name}」开启了防刷，需单独播放，等其他视频播完后再播')
            deferred.add(name)
            driver.close()
            return
    if anti:
        print(f'「{name}」开启了防刷，单独播放，播放页需保持在前台')
    print(f'开始播放: {name}')
    start_playback()
    slots[handle] = {'name': name, 'anti': anti, 'exclusive': exclusive,
                     'in_page': handle == course_window, 'playback': {}}


def poll_slot(handle, slot):
    """刷新一个视频的播放状态，播完时关闭它并返回 True。"""
    driver.switch_to.window(handle)
    playback = driver.execute_script('return {current_time: video.currentTime, duration: video.duration, paused: video.paused, ended: video.ended, rate: video.playbackRate, muted: video.muted};')
    slot['playback'] = playback
    if not driver.execute_script('return document.querySelector("#LetMeFly_Finished");'):
        print(f'正在播放: {slot["name"]} | {playback["current_time"] or 0:.0f}/{playback["duration"] or 0:.0f}秒 | {playback["rate"]}倍速')
        return False
    print(f'播放完毕: {slot["name"]}，再等 5 秒')
    sleep(5)  # 再让它播5秒
    if slot['in_page']:
        driver.get(COURSE_URL)
    else:
        driver.close()
    return True


def write_status(slots):
    status = {
        'videos': [dict(slot['playback'], video=slot['name'], anti_brushing=slot['anti'])
                   for slot in slots.values()],
        'parallel': PARALLEL,
        'debugger_address': driver.capabilities['goog:chromeOptions']['debuggerAddress'],
    }
    with open(os.path.join(output_dir(), 'playback-status.json'), 'w', encoding='utf-8') as status_file:
        json.dump(status, status_file, ensure_ascii=False, indent=2)


def play_all():
    """在课程页依次打开未完成的视频，最多同时播放 PARALLEL 个；开启了防刷的视频单独播放。"""
    course_window = driver.current_window_handle
    slots = {}  # 窗口句柄 -> 正在播放的视频
    deferred = set()  # 开启了防刷、等其他视频播完再单独播放的视频名
    need_refresh = False  # 有视频播完后要刷新课程页，列表里的完成状态才会更新
    exhausted = False  # 暂时没有可以新开的视频，等有视频播完再找
    while True:
        for handle, slot in list(slots.items()):
            if poll_slot(handle, slot):
                del slots[handle]
                need_refresh, exhausted = True, False
        write_status(slots)
        if (len(slots) < PARALLEL and not exhausted
                and not any(slot['exclusive'] for slot in slots.values())):
            activate(course_window)
            if need_refresh:
                driver.refresh()
                sleep(5)  # thanks for @420xincheng's #8
                need_refresh = False
            print('正在寻找未完成的视频，请耐心等待')
            playing = {slot['name'] for slot in slots.values()}
            candidates = [video for video in getAllvideos_notFinished(load_course_items())
                          if name_of(video) not in playing and not (slots and name_of(video) in deferred)]
            if candidates:
                open_slot(candidates[0], slots, deferred, course_window)
                continue  # 马上看还能不能再开一个
            if not slots:
                return
            exhausted = True
        if len(slots) > 1:
            print(f'同时播放 {len(slots)}/{PARALLEL} 个视频')
        sleep(3)


try:
    play_all()
finally:
    driver.quit()
print('恭喜你！全部播放完毕')
sleep(5)
