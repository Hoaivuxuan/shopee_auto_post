@echo off
REM Chay chuong trinh tu ma nguon (can cai Python 3.10 tro len, nho tick "Add python.exe to PATH").
REM Lan dau se tu cai thu vien can thiet. Neu dung ban .exe thi KHONG can file nay.
cd /d "%~dp0..\.."
py -c "import requests, playwright" 2>nul || (
    echo Dang cai thu vien lan dau, vui long cho...
    py -m pip install -r requirements.txt
)
start "" pyw app.py
