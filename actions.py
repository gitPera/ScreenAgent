"""Azioni sul PC: mouse e tastiera.

Il puntatore viene spostato da clicker.muovi, che scorre fino al bersaglio
invece di saltarci sopra di colpo.
"""
import time

import pyautogui

import clicker

pyautogui.FAILSAFE = True   # sposta il mouse nell'angolo alto-sinistra per abortire tutto
pyautogui.PAUSE = 0.05


def move(x, y, duration=None):
    clicker.muovi(x, y, duration)


def click(x, y, button="left", clicks=1, duration=None):
    clicker.muovi(x, y, duration)
    time.sleep(0.05)          # un attimo fermo prima di premere, come faresti tu
    pyautogui.click(button=button, clicks=clicks, interval=0.08)


def double_click(x, y):
    click(x, y, clicks=2)


def right_click(x, y):
    click(x, y, button="right")


def drag(x1, y1, x2, y2, duration=0.4):
    clicker.muovi(x1, y1)
    time.sleep(0.05)
    pyautogui.dragTo(x2, y2, duration=duration, button="left")


def type_text(text, interval=0.02):
    pyautogui.typewrite(text, interval=interval)


# pyautogui conosce solo i nomi inglesi, e i tasti che non riconosce li ignora
# in silenzio: qui traduciamo e segnaliamo l'errore.
ALIAS = {
    "invio": "enter", "spazio": "space", "canc": "delete", "maiusc": "shift",
    "esci": "esc", "tab": "tab", "backspace": "backspace", "indietro": "backspace",
    "su": "up", "giu": "down", "sinistra": "left", "destra": "right",
    "win": "win", "capslock": "capslock", "stamp": "printscreen",
}


def hotkey(*keys):
    tasti = [ALIAS.get(k.strip().lower(), k.strip().lower()) for k in keys if k.strip()]
    sconosciuti = [k for k in tasti if k not in pyautogui.KEYBOARD_KEYS]
    if sconosciuti:
        raise ValueError("tasto sconosciuto: %s (usa i nomi tipo 1, a, f5, enter, "
                         "space, ctrl, alt, shift)" % ", ".join(sconosciuti))
    pyautogui.hotkey(*tasti)


def scroll(amount, x=None, y=None):
    # la rotella passa da clicker: pyautogui.scroll su Windows manda un delta
    # sbagliato e non scorre niente (vedi clicker.scorri)
    if x is not None:
        clicker.muovi(x, y)
    clicker.scorri(amount)


def wait(seconds):
    time.sleep(seconds)
