# PyInstaller spec — ytgen Studio PC 앱
#   pyinstaller packaging/ytgen.spec --noconfirm
# packaging/ffmpeg/bin/ 에 ffmpeg·ffprobe 를 넣어 두면 앱에 같이 포함됩니다 (없으면 앱의 설정 화면에서 자동 설치).
import os, sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(ROOT, "config.yaml"), "."), (os.path.join(ROOT, "examples"), "examples")]
datas += [d for d in collect_data_files("googleapiclient") if os.path.basename(d[0]).startswith("youtube.v3")]  # YouTube API 정의만
datas += collect_data_files("edge_tts")
ff = os.path.join(SPECPATH, "ffmpeg", "bin")
if os.path.isdir(ff):
    datas.append((ff, os.path.join("ffmpeg", "bin")))

hidden = collect_submodules("ytgen") + ["googleapiclient.discovery", "google_auth_oauthlib.flow"]

a = Analysis([os.path.join(ROOT, "app.py")], pathex=[ROOT], datas=datas, hiddenimports=hidden,
             excludes=["tkinter", "matplotlib", "numpy", "pandas"], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ytgen-studio",
          console=False, icon=None, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="ytgen-studio", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="ytgen Studio.app", bundle_identifier="com.ytgen.studio",
                 info_plist={"NSHighResolutionCapable": True})
