@echo off
rem Apre l'interfaccia grafica. Usa l'exe se c'e' (installazione), altrimenti i
rem sorgenti Python.
cd /d "%~dp0"
if exist "ScreenAgent.exe" (
    start "" "ScreenAgent.exe"
) else (
    start "" pythonw ScreenAgent.py
)
