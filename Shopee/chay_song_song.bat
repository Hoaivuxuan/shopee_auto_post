@echo off
REM Mo 2 cua so chay SONG SONG:
REM   Cua so 1: tai video moi (chay xong thi tu dung, cua so van mo de xem ket qua)
REM   Cua so 2: quet sheet moi 2 phut, video nao tai xong (cot B = "Thanh cong") thi dang len Facebook
REM Cua so 2 chay lien tuc: khi xong viec ban tu dong cua so (bam Ctrl+C hoac nut X).
REM Neu chua dung "setx SHEET_URL" va "setx SHEET_TOKEN" thi them --url va --token vao 2 lenh duoi day.

start "TAI VIDEO" cmd /k "cd /d D:\Shopee && py shopee_batch_appsscript.py --limit 10"
start "DANG FACEBOOK" cmd /k "cd /d D:\Shopee && py shopee_fb_post.py --watch 2 --schedule facebook --min-delay 0 --max-delay 0"
