@echo off
REM ytgen Studio - Windows 앱 만들기 (Python 3.10 이상 필요: https://www.python.org/downloads/)
REM 이 파일을 더블클릭하면 dist\ytgen-studio\ytgen-studio.exe 가 만들어집니다.
cd /d "%~dp0\.."
if not exist .venv ( py -3 -m venv .venv || python -m venv .venv )
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt -r requirements-desktop.txt
if not exist packaging\ffmpeg\bin\ffmpeg.exe (
  echo ffmpeg 내려받는 중...
  powershell -NoProfile -Command "Invoke-WebRequest https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip -OutFile ffmpeg.zip; Expand-Archive ffmpeg.zip -DestinationPath ffmpeg_tmp -Force; New-Item -ItemType Directory -Force packaging\ffmpeg\bin | Out-Null; Copy-Item ffmpeg_tmp\*\bin\ffmpeg.exe,ffmpeg_tmp\*\bin\ffprobe.exe packaging\ffmpeg\bin\; Remove-Item ffmpeg.zip; Remove-Item ffmpeg_tmp -Recurse"
)
pyinstaller packaging\ytgen.spec --noconfirm
echo.
echo 완료: dist\ytgen-studio\ytgen-studio.exe  (폴더째 원하는 곳에 옮겨 사용하세요)
pause
