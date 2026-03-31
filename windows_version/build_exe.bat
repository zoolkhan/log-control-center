@echo off
echo --- LOG CONTROL CENTER EXE BUILDER ---
echo Installing PyInstaller...
call venv\Scripts\activate.bat
pip install pyinstaller

echo Building Standalone EXE...
pyinstaller --noconfirm --onefile --windowed ^
    --add-data "index.html;." ^
    --add-data "script.js;." ^
    --add-data "style.css;." ^
    --add-data "world.geojson;." ^
    --name "LogControlCenter" ^
    app.py

echo.
echo BUILD COMPLETE!
echo Your installer is located in: dist\LogControlCenter.exe
pause
