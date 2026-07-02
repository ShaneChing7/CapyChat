# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for CapyChat — minimal PySide6 Qt bundle.

Only QtWidgets / QtCore / QtGui / QtSvg are bundled.
WebEngine, Multimedia, Quick, QML, Charts, 3D, Network, etc. are excluded
to keep the .exe as small as possible.
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# ── project root (SPECPATH = directory containing this .spec file) ──────────
ROOT = Path(SPECPATH)

# ═════════════════════════════════════════════════════════════════════════════
# 1.  Qt modules the app *never* imports — strip them out
# ═════════════════════════════════════════════════════════════════════════════
UNUSED_QT_MODULES = [
    # ── Web (biggest single saving) ──
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebEngine',
    'PySide6.QtWebChannel',
    'PySide6.QtWebSockets',
    # ── Multimedia ──
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtMultimediaQuick',
    'PySide6.QtSpacialAudio',
    # ── QML / Quick ──
    'PySide6.QtQml',
    'PySide6.QtQmlModels',
    'PySide6.QtQuick',
    'PySide6.QtQuickWidgets',
    'PySide6.QtQuickControls2',
    'PySide6.QtQuickTemplates2',
    'PySide6.QtQuick3D',
    'PySide6.QtQuick3DRuntimeRender',
    'PySide6.QtQuick3DAssetImport',
    'PySide6.QtQuick3DUtils',
    'PySide6.QtQuick3DHelpers',
    'PySide6.QtQuick3DParticleEffects',
    'PySide6.QtQuick3DGlslParser',
    'PySide6.QtQuick3DIblBaker',
    'PySide6.QtShaderTools',
    # ── 3D ──
    'PySide6.Qt3DCore',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DRender',
    'PySide6.Qt3DAnimation',
    'PySide6.Qt3DExtras',
    # ── Charts / DataViz ──
    'PySide6.QtCharts',
    'PySide6.QtDataVisualization',
    'PySide6.QtGraphs',
    'PySide6.QtGraphsWidgets',
    # ── Network (app uses Python sockets, not QtNetwork) ──
    'PySide6.QtNetwork',
    'PySide6.QtNetworkAuth',
    # ── Hardware I/O ──
    'PySide6.QtBluetooth',
    'PySide6.QtNfc',
    'PySide6.QtSerialPort',
    'PySide6.QtSerialBus',
    'PySide6.QtSensors',
    'PySide6.QtSensorsQuick',
    'PySide6.QtPositioning',
    'PySide6.QtLocation',
    # ── PDF / Print ──
    'PySide6.QtPrintSupport',
    'PySide6.QtPdf',
    'PySide6.QtPdfWidgets',
    # ── Database ──
    'PySide6.QtSql',
    # ── Others ──
    'PySide6.QtTest',
    'PySide6.QtHelp',
    'PySide6.QtDesigner',
    'PySide6.QtUiTools',
    'PySide6.QtAxContainer',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    'PySide6.QtTextToSpeech',
    'PySide6.QtVirtualKeyboard',
    'PySide6.QtStateMachine',
    'PySide6.QtSvgWidgets',
    'PySide6.QtXml',
    'PySide6.QtConcurrent',
    'PySide6.QtDBus',
    'PySide6.QtLabsAnimation',
    'PySide6.QtLabsFolderListModel',
    'PySide6.QtLabsQmlApplicationEngine',
    'PySide6.QtLabsSettings',
    'PySide6.QtLabsSharedImage',
    'PySide6.QtLabsWavefrontMesh',
    'PySide6.QtRemoteObjects',
    'PySide6.QtScxml',
]

# ═════════════════════════════════════════════════════════════════════════════
# 2.  Collect asset files (avatars, icons, backgrounds, capybara, logo)
# ═════════════════════════════════════════════════════════════════════════════
datas = []
assets_dir = ROOT / 'capychat' / 'assets'

if assets_dir.is_dir():
    for f in assets_dir.rglob('*'):
        if f.is_file():
            rel = f.relative_to(ROOT)
            dest = str(rel.parent)  # e.g. capychat/assets/icons
            datas.append((str(f), dest))

# ═════════════════════════════════════════════════════════════════════════════
# 3.  Hidden imports (lazy / dynamic imports PyInstaller can't see)
# ═════════════════════════════════════════════════════════════════════════════
hiddenimports = [
    # project packages
    'capychat',
    'capychat._paths',
    'capychat.controller',
    'capychat.config_manager',
    'capychat.ai',
    'capychat.ai.capybara_agent',
    'capychat.network',
    'capychat.network.protocol',
    'capychat.network.crypto',
    'capychat.network.udp_broadcast',
    'capychat.network.tcp_p2p',
    'capychat.network.file_transfer',
    'capychat.ui',
    'capychat.ui.theme',
    'capychat.ui.avatar_cache',
    'capychat.ui.avatar_picker',
    'capychat.ui.capybara_widget',
    'capychat.ui.capybara_settings',
    'capychat.ui.chat_area',
    'capychat.ui.document_center',
    'capychat.ui.emoji_picker',
    'capychat.ui.message_bubble',
    'capychat.ui.message_list',
    'capychat.ui.sidebar',
    'capychat.views',
    'capychat.views.login_ui',
    'capychat.views.chat_ui',
    # third-party
    'cryptography',
    'requests',
]

# ═════════════════════════════════════════════════════════════════════════════
# 4.  Analysis
# ═════════════════════════════════════════════════════════════════════════════
a = Analysis(
    [str(ROOT / 'capychat' / 'main.py')],
    pathex=[str(ROOT), str(ROOT / 'capychat')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=UNUSED_QT_MODULES,
    noarchive=False,
    optimize=0,
)

# ── filter leftover Qt C++ DLLs for excluded modules ──
_UNUSED_DLL_PREFIXES = [
    'Qt6WebEngine', 'Qt6WebChannel', 'Qt6Multimedia', 'Qt6Qml',
    'Qt6Quick', 'Qt63D', 'Qt6Charts', 'Qt6DataVis', 'Qt6Graphs',
    'Qt6Bluetooth', 'Qt6Nfc', 'Qt6Serial', 'Qt6Sensors',
    'Qt6PrintSupport', 'Qt6Sql', 'Qt6Test', 'Qt6Help',
    'Qt6Designer', 'Qt6UiTools', 'Qt6Network', 'Qt6OpenGL',
    'Qt6Pdf', 'Qt6TextToSpeech', 'Qt6VirtualKeyboard',
    'Qt6StateMachine', 'Qt6Xml', 'Qt6Concurrent', 'Qt6DBus',
    'Qt6Positioning', 'Qt6Location', 'Qt6RemoteObjects', 'Qt6Scxml',
    'Qt6SpatialAudio', 'Qt6ShaderTools',
]


def _filter_dlls(toc):
    """Remove binaries for unused Qt modules from TOC."""
    result = []
    for src, dest, typecode in toc:
        name = Path(dest).name
        if any(name.startswith(p) for p in _UNUSED_DLL_PREFIXES):
            continue
        result.append((src, dest, typecode))
    return result


a.binaries = _filter_dlls(a.binaries)

# ═════════════════════════════════════════════════════════════════════════════
# 5.  PYZ + EXE
# ═════════════════════════════════════════════════════════════════════════════
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='CapyChat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'capychat' / 'assets' / 'icons' / 'logo.ico'),
)
