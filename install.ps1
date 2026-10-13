# 安装运行环境：uv、Python（电脑上没有时由 uv 自动下载）、.venv 虚拟环境和 selenium。
# 可以重复运行，已装好的部分会跳过。由 install.cmd 调用；start.cmd 发现环境缺失时会带 -FromStart 调用。
param([switch]$FromStart)

Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONUTF8 = '1'
$VenvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
# 国内网络访问 GitHub、PyPI 较慢时使用的镜像
$PipMirror = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$PythonMirror = 'https://registry.npmmirror.com/-/binary/python-build-standalone'
# uv 官方安装脚本的默认安装位置，装完后当前窗口的 PATH 不会自动刷新
$env:Path = (Join-Path $env:USERPROFILE '.local\bin') + ';' + $env:Path
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Step($text) { Write-Host ''; Write-Host $text -ForegroundColor Cyan }
function Info($text) { Write-Host "      $text" }
function Fail($text) {
    Write-Host ''
    Write-Host $text -ForegroundColor Red
    Read-Host '按回车键退出' | Out-Null
    exit 1
}
function Test-Command($name) { [bool](Get-Command $name -ErrorAction SilentlyContinue) }
function Test-Python {
    # Windows 自带的 python.exe 可能只是应用商店的占位程序，要实际运行一次才知道能不能用
    if (-not (Test-Command 'python')) { return $false }
    & python -m pip --version *> $null
    return $LASTEXITCODE -eq 0
}

$UvCommand = 'uv'
$UvPrefix = @()  # 退回 pip 安装时改为 python -m uv

Write-Host '=================================================='
Write-Host 'YuketangAutoPlayer 环境安装'
Write-Host '=================================================='

# ---------- 1. uv ----------
if (-not (Test-Command 'uv')) {
    Step '[1/4] 未找到 uv，正在通过官方脚本安装...'
    & powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
    if (-not (Test-Command 'uv')) {
        Info '官方脚本安装失败，尝试用电脑上已有的 Python 从镜像安装 uv...'
        if (-not (Test-Python)) {
            Fail 'uv 安装失败。请检查网络后重试，或参考 https://docs.astral.sh/uv/getting-started/installation/ 手动安装。'
        }
        & python -m pip install --user --upgrade uv -i $PipMirror
        if ($LASTEXITCODE -ne 0) { Fail 'uv 安装失败，请检查网络后重试。' }
        $UvCommand = 'python'
        $UvPrefix = @('-m', 'uv')
    }
}
Step '[1/4] uv 已就绪'
& $UvCommand @UvPrefix --version

# ---------- 2. Python 虚拟环境 ----------
if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.venv')) {
        Fail ("[2/4] 已有的 .venv 不是 Windows 虚拟环境（可能是在 WSL 或其他系统中创建的）。`n" +
              '      请删除项目目录下的 .venv 文件夹后重新运行本脚本。')
    }
    Step '[2/4] 正在创建虚拟环境 .venv，电脑上没有合适的 Python 时会自动下载...'
    & $UvCommand @UvPrefix venv .venv --python '>=3.9'
    if ($LASTEXITCODE -ne 0) {
        Info '下载 Python 失败，改用国内镜像重试...'
        $env:UV_PYTHON_INSTALL_MIRROR = $PythonMirror
        & $UvCommand @UvPrefix venv .venv --python '>=3.9'
        if ($LASTEXITCODE -ne 0) {
            Fail '创建虚拟环境失败。请检查网络后重试，也可以先自行安装 Python 3.9 或更高版本：https://www.python.org/downloads/'
        }
    }
}
Step '[2/4] 虚拟环境已就绪'
& $VenvPython --version

# ---------- 3. 依赖 ----------
Step '[3/4] 正在安装依赖 selenium...'
& $UvCommand @UvPrefix pip install --python $VenvPython 'selenium>=4.6'
if ($LASTEXITCODE -ne 0) {
    Info '安装失败，改用国内镜像重试...'
    & $UvCommand @UvPrefix pip install --python $VenvPython 'selenium>=4.6' --index-url $PipMirror
}
& $VenvPython -c "import selenium; print('selenium', selenium.__version__)"
if ($LASTEXITCODE -ne 0) { Fail '依赖安装失败，请检查网络后重新运行本脚本。' }

# ---------- 4. Chrome ----------
$chromePaths = @(
    (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
)
$chromeFound = [bool]($chromePaths | Where-Object { $_ -and (Test-Path -LiteralPath $_) }) -or
    (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') -or
    (Test-Path 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe')
if ($chromeFound) {
    Step '[4/4] 已检测到 Chrome 浏览器'
} else {
    Step '[4/4] 未检测到 Chrome 浏览器，请先安装：https://www.google.cn/chrome/'
}
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'chromedriver.exe'))) {
    Info '项目目录没有 chromedriver.exe，首次运行时 selenium 会自动下载匹配的版本；'
    Info '如果下载失败，请手动下载与 Chrome 版本一致的 chromedriver.exe 放到本目录。'
}

Write-Host ''
Write-Host '=================================================='
Write-Host '环境安装完成' -ForegroundColor Green
Write-Host '=================================================='
if ($FromStart) { exit 0 }

$answer = Read-Host '现在启动网页控制台吗？[Y/n]'
if ($answer -notmatch '^[nN]') {
    & (Join-Path $PSScriptRoot 'start.cmd')
}
exit 0
