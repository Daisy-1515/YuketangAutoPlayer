# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['webui.py'],
    pathex=[],
    binaries=[
        ('chromedriver.exe', '.'),  # 打包 chromedriver.exe 到根目录
    ],
    datas=[
        ('webui.html', '.'),  # 网页控制台页面
    ],
    hiddenimports=['main'],  # 播放子进程通过 --player 动态导入
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='YuketangAutoPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 保留控制台窗口，关闭即退出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 如果有图标可以在这里指定
)
