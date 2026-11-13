"""Dove vivono i dati dell'applicazione (template, sequenze, macro).

Un solo posto che decide la cartella base, cosi' funziona sia lanciando i .py
sia dentro l'exe creato con PyInstaller:
  - da sorgente: la cartella dei file .py
  - da exe "congelato": la cartella dell'exe (scelta scrivibile dall'installer)

Dentro la cartella base i dati sono divisi per tipo:
  templates/   le immagini
  sequenze/    le sequenze (.json), compresa quella aperta nella GUI (sequenza.json)
  macro/       le macro registrate con F7
"""
import os
import sys

if getattr(sys, "frozen", False):          # dentro un exe PyInstaller
    BASE = os.path.dirname(sys.executable)
else:                                       # dai sorgenti .py
    BASE = os.path.dirname(os.path.abspath(__file__))

TEMPLATES = os.path.join(BASE, "templates")   # le immagini da riconoscere
SEQUENZE = os.path.join(BASE, "sequenze")     # i file .json delle sequenze
MACRO = os.path.join(BASE, "macro")           # le registrazioni della scheda Macro

# la registrazione "Record" della scheda Autoclicker: sta anche lei in macro/, ma
# ha un formato diverso dalle macro, quindi il nome comincia con "_" e l'elenco
# della scheda Macro salta i file che cominciano cosi'
REGISTRAZIONE = os.path.join(MACRO, "_autoclicker.json")


def sequenza(nome):
    """Percorso completo di un file di sequenza a partire dal nome.

    Un percorso assoluto resta com'e'. Un nome semplice ("mia.json") si
    cerca in sequenze/; se li' non c'e' ma esiste nella cartella principale
    (com'era nelle versioni precedenti) vale quello. Un file che non esiste
    ancora nasce in sequenze/."""
    if os.path.isabs(nome):
        return nome
    in_cartella = os.path.join(SEQUENZE, nome)
    if os.path.exists(in_cartella):
        return in_cartella
    vecchio = os.path.join(BASE, nome)
    if os.path.exists(vecchio):
        return vecchio
    return in_cartella


# file "di sola lettura" impacchettati con il programma (l'icona): nell'exe
# PyInstaller li mette in una cartella a parte (_internal), non accanto all'exe
RISORSE = getattr(sys, "_MEIPASS", BASE)
ICONA = os.path.join(RISORSE, "icona.ico")


def avvio_congelato():
    return bool(getattr(sys, "frozen", False))
