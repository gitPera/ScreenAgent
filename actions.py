"""Azioni sul PC: mouse e tastiera."""
import time
import pyautogui

pyautogui.FAILSAFE = True   # sposta il mouse nell'angolo alto-sinistra per abortire tutto
pyautogui.PAUSE = 0.05


def move(x, y, duration=0.15):
    pyautogui.moveTo(x, y, duration=duration)


def click(x, y, button="left", clicks=1, duration=0.15):
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click(button=button, clicks=clicks, interval=0.08)


def double_click(x, y):
    click(x, y, clicks=2)


def right_click(x, y):
    click(x, y, button="right")


def drag(x1, y1, x2, y2, duration=0.4):
    pyautogui.moveTo(x1, y1, duration=0.15)
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
    if x is not None:
        pyautogui.moveTo(x, y)
    pyautogui.scroll(amount)


def wait(seconds):
    time.sleep(seconds)
