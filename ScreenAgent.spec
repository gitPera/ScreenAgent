# -*- mode: python ; coding: utf-8 -*-
# Ricetta PyInstaller: crea DUE programmi in un'unica cartella (dist/ScreenAgent):
#   ScreenAgent.exe     -> l'interfaccia grafica (senza finestra nera)
#   ScreenAgentRun.exe  -> l'esecutore delle sequenze da riga di comando (con log)
# Le librerie pesanti (OpenCV, numpy...) sono condivise fra i due grazie a MERGE.

block_cipher = None

# moduli importati "a mano" dentro il dispatcher --tool: li elenco perche'
# PyInstaller li includa di sicuro
nascosti = ["zona", "diagnosi", "agent", "incolla", "percorsi", "motore",
            "registratore", "clicker", "actions", "screen", "vision"]

a_gui = Analysis(["ScreenAgent.py"], pathex=[], binaries=[],
                 datas=[("icona.ico", ".")],     # serve alla finestra a runtime
                 hiddenimports=nascosti, hookspath=[], hooksconfig={},
                 runtime_hooks=[], excludes=[], noarchive=False,
                 cipher=block_cipher)
a_run = Analysis(["motore.py"], pathex=[], binaries=[], datas=[],
                 hiddenimports=nascosti, hookspath=[], hooksconfig={},
                 runtime_hooks=[], excludes=[], noarchive=False,
                 cipher=block_cipher)

MERGE((a_gui, "ScreenAgent", "ScreenAgent"),
      (a_run, "ScreenAgentRun", "ScreenAgentRun"))

pyz_gui = PYZ(a_gui.pure, a_gui.zipped_data, cipher=block_cipher)
pyz_run = PYZ(a_run.pure, a_run.zipped_data, cipher=block_cipher)

exe_gui = EXE(pyz_gui, a_gui.scripts, [], exclude_binaries=True,
              name="ScreenAgent", console=False, disable_windowed_traceback=False,
              icon="icona.ico")
exe_run = EXE(pyz_run, a_run.scripts, [], exclude_binaries=True,
              name="ScreenAgentRun", console=True, disable_windowed_traceback=False,
              icon="icona.ico")

coll = COLLECT(exe_gui, a_gui.binaries, a_gui.zipfiles, a_gui.datas,
               exe_run, a_run.binaries, a_run.zipfiles, a_run.datas,
               strip=False, upx=False, name="ScreenAgent")
