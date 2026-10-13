<!--
 * @Author: LetMeFly
 * @Date: 2023-09-22 18:26:15
 * @LastEditors: LetMeFly.xyz
 * @LastEditTime: 2025-11-13 23:45:53
-->
# YuketangAutoPlayer

雨课堂刷课脚本（雨课堂视频自动播放），基于 Selenium 模拟浏览器运行，无需虚拟机，也可以以无窗口模式运行。（MOOC）

视频演示地址：[Bilibili@BV15K4y1F7EN](https://www.bilibili.com/video/BV15K4y1F7EN/)

[![](img/video-cover.jpg)](https://www.bilibili.com/video/BV15K4y1F7EN/)

## 功能

- **本地网页控制台**：扫码登录、自动读取课程列表、点选课程、启动/停止播放，实时查看每个视频的进度、截图和运行日志
- **多视频同时播放**：同时播放 1~5 个视频（默认 3 个），播完一个自动补上下一个未完成的视频
- **固定 2 倍速、静音**：自动选择播放器最高的 2 倍速，播放器重置速度或暂停时自动恢复并续播，窗口在后台也不会停
- **自动跳过**：已完成、已锁定、已过截止时间的视频不会播放
- **支持多种雨课堂**：普通雨课堂（www.yuketang.cn）、荷塘、长江、黄河雨课堂及学校独立域名；兼容新旧两套课程页面

## 使用方法

### 一、准备环境

1. 安装 [Chrome 浏览器](https://www.google.cn/chrome/index.html)（注意别装成假的 Chrome）
2. 下载与 Chrome **版本对应的** `chromedriver.exe`：[Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/)、[旧版下载](https://chromedriver.chromium.org/downloads)。放到项目目录或加入环境变量 `PATH`（新版 Selenium 找不到时也会尝试自动下载）
3. 安装 Python 依赖（Python ≥ 3.8）：

```bash
uv pip install selenium      # 或 pip install selenium
```

Windows 下如果想直接双击 `start.cmd` 启动，需要先在项目目录创建虚拟环境：

```bash
uv venv
uv pip install selenium
```

### 二、网页控制台（推荐）

1. Windows 下双击 `start.cmd`，或运行：

   ```bash
   python webui.py              # 加 --no-browser 则不自动打开页面
   ```

2. 浏览器会自动打开本地控制台 `http://127.0.0.1:8765/`（端口被占用时换成随机端口，以命令行窗口里打印的地址为准）
3. **登录**：未登录或登录失效时会自动弹出扫码用的 Chrome，也可以手动点「扫码登录」。用微信扫码后浏览器自动关闭，登录态保存到 `config.ini`
4. **选择课程**：控制台列出你的所有课程，在要刷的课后面点「选这门课」。可在这里设置「无窗口模式」和「同时播放」的视频数
5. **播放**：点「开始播放」，控制台显示每个视频的进度、播放页面截图和运行日志；随时可以点「停止」

默认登录普通雨课堂（www.yuketang.cn）；荷塘、长江、黄河雨课堂或学校独立域名，在登录卡片里展开「不是普通雨课堂？」选择即可。列表里没有的课，可以展开「手动填写课程地址」，粘贴课程「学习内容」页的地址。

控制台只监听本机 `127.0.0.1`，页面和接口都不会返回你的 `sessionid`。退出时建议先点「停止」，再在命令行窗口按 `Ctrl+C` 或直接关闭窗口。

### 三、命令行运行（可选）

不需要网页控制台时，可以直接运行播放脚本：

```bash
python main.py
```

脚本读取 `config.ini`（先找程序所在目录，再找当前目录）。首次运行会自动生成模板并退出，也可以复制 `config.ini.example` 为 `config.ini`：

```ini
[Settings]
headless = false
course_url = 在此填写你的课程URL
cookie = 在此填写你的sessionid
implicitly_wait = 10
parallel = 3
```

| 配置项 | 说明 |
| --- | --- |
| `headless` | 是否无窗口运行。无窗口时不能扫码，必须先有有效的 `cookie` |
| `course_url` | 课程地址：进入课程，点「学习内容」，复制地址栏的 https 地址 |
| `cookie` | 登录态 `sessionid`，留空则运行时弹出浏览器扫码，扫码成功后自动写回配置 |
| `implicitly_wait` | 元素查找超时（秒），一般不用改 |
| `parallel` | 同时播放的视频数，1~5，默认 3；设为 1 即逐个播放 |

网页控制台会额外写入 `host`（登录所在的域名），命令行脚本不读取它。环境变量 `YUKETANG_SESSIONID` 优先于配置里的 `cookie`。

![how-to-get-url](img/how-to-get-url.jpg)

<details>
<summary>手动获取 cookie（推荐直接扫码，可跳过）</summary>

登录（你们学校的）雨课堂，打开开发者工具，依次点击「应用 → 存储 → Cookie → https&#58;&#47;&#47;xxx.yuketang...」，复制 **sessionid** 对应的值。

![how-to-get-cookie](img/how-to-get-cookie.jpg)

</details>

## 打包为 EXE（可选）

1. 确保 `chromedriver.exe` 在项目根目录
2. 安装 PyInstaller 并打包：

```bash
uv pip install pyinstaller
pyinstaller YuketangAutoPlayer.spec --clean
```

打包完成后 `dist` 目录下会生成 `YuketangAutoPlayer.exe`，已内置 chromedriver 和控制台页面。双击运行即打开网页控制台，`config.ini` 和运行输出保存在 exe 所在目录。

> 上游仓库 Release 中的 [v5.0 exe](https://github.com/LetMeFly666/YuketangAutoPlayer/releases/download/v5.0/YuketangAutoPlayer.exe) 是旧版命令行程序，不包含网页控制台和多开播放；需要新功能请按上面的步骤自行打包。

## 检查

```bash
uv run python -m unittest discover -s tests -v   # 调度与等待逻辑回归检查，不启动真实课程
uv run python tests/browser_check.py             # 本地 Chrome 媒体与界面检查，无需登录，预览写入 output/verification/
```

本地检查覆盖延迟加载、后台播放、倍速恢复、自动续播、自然结束及界面渲染；雨课堂实际课程与服务端进度仍需登录后实测。

## 使用提示

- 播放过程中可以把浏览器窗口最小化去做别的事，但尽量不要把鼠标移到程序打开的浏览器上：选择倍速是模拟鼠标操作完成的。
- 视频是否完成以雨课堂服务端记录为准，大约观看 90% 即算完成；程序会等视频自然播放结束再关闭。
- 运行状态和截图写在 `output/playwright/` 目录下，可以随时删除。
- 视频正常播完时浏览器缓存会自动清理；若中途强行结束程序，Windows 下 `%temp%` 中可能残留 Chrome 临时目录，可手动删除。

## 感谢列表

+ 感谢[Github@SwordLikeRain](https://github.com/SwordLikeRain)的[Cookie错误时提示不准确的issue](https://github.com/LetMeFly666/YuketangAutoPlayer/issues/1)（good first issue），使得程序修改后支持了每次扫码登录。
+ 感谢[BiliBili@Bacch](https://space.bilibili.com/21043185)的`AttributeError: 'WebDriver' object has no attribute 'find_elements_by_class_name'`的[报错提醒](https://www.bilibili.com/video/BV15K4y1F7EN/#reply187204230304)，使得程序修改后兼容了selenium≥4.0。
+ 感谢[BiliBili@青鹧不懂蓝桉情](https://space.bilibili.com/1208020409)提供的账号，使得程序修改后支持了`www.yuketang.cn`这种域名下的雨课堂界面。
+ 感谢[Github@420xincheng](https://github.com/420xincheng)的[没刷完视频，就自动退出的解决方法(#8)](https://github.com/LetMeFly666/YuketangAutoPlayer/issues/8)，播放完毕一个视频刷新后等待5秒防止页面暂未加载完成。
+ 感谢[Github@Guo-Chenxu](https://github.com/Guo-Chenxu)的[`ifVideo`函数修改(#13)](https://github.com/LetMeFly666/YuketangAutoPlayer/issues/13)，更新COMMONUI下未播放视频的判断逻辑。
+ 感谢[Github@泠辰](https://github.com/Crsuh2er0)的[已过期视频循环播放bugfix (#17)](https://github.com/LetMeFly666/YuketangAutoPlayer/pull/17)，修复了存在已过期视频时会重复播放已过期视频的问题。
+ 感谢[Github@ke tan](https://github.com/tkzzzzzz6)的[exe打包文件方式(#18)](https://github.com/LetMeFly666/YuketangAutoPlayer/issues/18)，Windows当前新版Chrome可一键运行免除环境配置及驱动下载困扰。

## TODO

- [ ] 抽象获取待播放视频的函数，见[建议](https://github.com/LetMeFly666/YuketangAutoPlayer/pull/17#discussion_r2450825512)。

## 免责声明

本项目的唯一目的是：selenium技术的学习与实践。

禁止用于其他用途，下载后请于24h内删除【Doge】。

<small>若导致账号封禁或其他因BUG造成的损失，与本项目无关。</small>
