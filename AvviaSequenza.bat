@echo off
rem ---------------------------------------------------------------------------
rem Avvia una sequenza salvata, senza aprire ScreenAgent.
rem   - doppio click                -> esegue sequenze\sequenza.json
rem   - trascina un .json qui sopra -> esegue quel file
rem   - da riga di comando          -> AvviaSequenza.bat mia.json --ripeti 0
rem Le sequenze stanno nella cartella "sequenze": basta il nome del file.
rem Per fermarla: F6, Esc, o il mouse nell'angolo in alto a sinistra.
rem
rem Questo file deve stare nella cartella di ScreenAgent (accanto a motore.py o
rem a ScreenAgentRun.exe). Per lanciarlo da un altro posto -- per esempio dalla
rem cartella Esecuzione automatica -- crea un COLLEGAMENTO, non una copia.
rem
rem Per un lanciatore dedicato a una sola sequenza: duplica questo file e
rem sostituisci sequenza.json qui sotto con il nome della tua.
rem ---------------------------------------------------------------------------
set "CARTELLA=%~dp0"
if not exist "%CARTELLA%ScreenAgentRun.exe" if not exist "%CARTELLA%motore.py" goto manca
cd /d "%CARTELLA%"

set "ARGOMENTI=%*"
if "%~1"=="" set "ARGOMENTI=sequenza.json"

rem usa l'exe se c'e' (installazione), altrimenti i sorgenti Python
set "PROGRAMMA=python motore.py"
if exist "ScreenAgentRun.exe" set "PROGRAMMA=ScreenAgentRun.exe"

rem (riga volutamente fuori da blocchi fra parentesi: un percorso che contiene
rem parentesi, come "Cartella (copia)", li' dentro darebbe errore)
start "ScreenAgent - sequenza" /min cmd /c "%PROGRAMMA% %ARGOMENTI% || pause"
goto :eof

:manca
echo.
echo Non trovo ScreenAgent accanto a questo file.
echo Tieni il .bat nella cartella di ScreenAgent; se ti serve altrove, crea un
echo collegamento invece di copiarlo.
echo.
pause
exit /b 1
