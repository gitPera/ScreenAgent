@echo off
rem ===========================================================================
rem Crea l'eseguibile di ScreenAgent (cartella dist\ScreenAgent) e, se trovi
rem Inno Setup, anche l'installer (cartella Output\ScreenAgent-Setup.exe).
rem
rem Serve una volta sola, sul PC di sviluppo con Python installato.
rem Doppio click su questo file.
rem ===========================================================================
cd /d "%~dp0"
echo.
echo === 1) Installo gli strumenti di build (se mancano) ===
python -m pip install --upgrade pyinstaller ^
    --trusted-host pypi.org --trusted-host files.pythonhosted.org
if errorlevel 1 (
    echo.
    echo [x] Non sono riuscito a installare PyInstaller. Controlla Python/pip.
    pause
    exit /b 1
)

echo.
echo === 2) Impacchetto l'applicazione in un .exe ===
python -m PyInstaller --clean --noconfirm ScreenAgent.spec
if errorlevel 1 (
    echo.
    echo [x] La creazione dell'exe e' fallita. Leggi gli errori qui sopra.
    pause
    exit /b 1
)
echo.
echo [ok] Eseguibile pronto in:  dist\ScreenAgent\ScreenAgent.exe

echo.
echo === 3) Creo l'installer (se Inno Setup e' installato) ===
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
rem installato "solo per me" (es. con winget) finisce nella cartella utente
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" (
    echo [i] Inno Setup non trovato: salto la creazione dell'installer.
    echo     Per averlo: installa Inno Setup 6 ^(https://jrsoftware.org/isdl.php^)
    echo     e rilancia questo build.bat. In alternativa distribuisci la cartella
    echo     dist\ScreenAgent zippata: funziona gia' cosi' su qualsiasi PC.
) else (
    "%ISCC%" installer.iss
    if errorlevel 1 (
        echo [x] La creazione dell'installer e' fallita.
    ) else (
        echo [ok] Installer pronto in:  Output\ScreenAgent-Setup.exe
    )
)

echo.
pause
