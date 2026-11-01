@echo off
rem Đóng gói thành dist\FireflyVideo\FireflyVideo.exe (cần Python 3.10+ trên máy build, máy chạy thì không cần)
cd /d "%~dp0"
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller firefly.spec --noconfirm --clean
echo.
echo Xong. Chay: dist\FireflyVideo\FireflyVideo.exe
pause
