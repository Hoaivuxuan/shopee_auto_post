@echo off
REM Chay lan luot: (1) tai video moi, (2) dang video da tai len cac Page Facebook.
REM Dat file nay vao D:\Shopee. Co the dat lich bang Task Scheduler.

cd /d D:\Shopee

REM Neu ban da dung "setx SHEET_URL" va "setx SHEET_TOKEN" thi bo qua 2 dong set duoi day.
REM Neu chua, bo chu REM o dau dong va dien URL, TOKEN cua ban:
REM set SHEET_URL=DAN_WEB_APP_URL_VAO_DAY
REM set SHEET_TOKEN=DAN_TOKEN_VAO_DAY

echo ===== Buoc 1: tai video =====
py shopee_batch_appsscript.py --limit 10

echo ===== Buoc 2: dang len Facebook =====
py shopee_fb_post.py --limit 5

echo ===== Xong =====
