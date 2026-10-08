@echo off
REM Dong goi thanh thu muc chay duoc tren may Windows khac (khong can cai Python).
REM Chay file nay tren may da cai Python 3.10+ va co Internet.
REM Ket qua: dist\ShopeeFBTool\ShopeeFBTool.exe va dist\ShopeeFBTool-<phien ban>-windows.zip
REM Chep CA THU MUC dist\ShopeeFBTool (hoac file .zip) sang may khac va chay ShopeeFBTool.exe.
cd /d "%~dp0..\.."
echo === Cai thu vien ===
py -m pip install --upgrade pip
py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto loi
echo === Dong goi (mat vai phut) ===
py scripts\build.py
if errorlevel 1 goto loi
echo.
echo May dich can co Microsoft Edge hoac Google Chrome (Windows 10/11 da co san Edge).
pause
exit /b 0
:loi
echo.
echo Co loi khi dong goi. Hay chup man hinh gui lai de duoc ho tro.
pause
exit /b 1
