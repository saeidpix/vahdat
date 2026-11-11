# ساخت فایل نصب روی ویندوز (در صورت نیاز به ساخت دستی)
1. Node.js 18 را نصب کنید. 2. پوشه پروژه را باز کنید و در CMD بزنید:
   npm install
   npx electron-builder --win nsis --x64 --publish never
3. فایل dist\Autobenz-Vahdat-Setup-1.0.0.exe ساخته می‌شود.
