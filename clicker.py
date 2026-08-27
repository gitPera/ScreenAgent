"""Motore dell'autoclicker.

Usa direttamente le API di Windows invece di pyautogui: pyautogui ha una pausa
interna di sicurezza fra un'azione e l'altra che impedisce i click rapidi.

Contiene: click veloci, lettura dei tasti globali (funzionano anche con la
finestra in secondo piano), registrazione e riproduzione di azioni.
"""
import ctypes
import json
import os
import time
from ctypes import wintypes

user32 = ctypes.windll.user32

# Di base Windows sveglia i timer ogni ~15.6 ms: con un intervallo di 20 ms
# otterresti 31 ms reali. Cosi' si scende a 1 ms di risoluzione.
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
except Exception:
    pass

# codici degli eventi mouse: (premi, rilascia)
GIU_SU = {
    "sinistro": (0x0002, 0x0004),
    "destro": (0x0008, 0x0010),
    "centrale": (0x0020, 0x0040),
}
VK_MOUSE = {0x01: "sinistro", 0x02: "destro", 0x04: "centrale"}
KEYEVENTF_KEYUP = 0x0002

NOMI_TASTI = {0x01: "click sinistro", 0x02: "click destro", 0x04: "click centrale",
              0x08: "backspace", 0x09: "tab", 0x0D: "invio", 0x10: "shift",
              0x11: "ctrl", 0x12: "alt", 0x14: "bloc maiusc", 0x1B: "esc",
              0x20: "spazio", 0x25: "sinistra", 0x26: "su", 0x27: "destra",
              0x28: "giu", 0x2D: "ins", 0x2E: "canc"}
for _i in range(1, 25):
    NOMI_TASTI[0x6F + _i] = "F%d" % _i


def nome_tasto(vk):
    if vk in NOMI_TASTI:
        return NOMI_TASTI[vk]
    if 0x30 <= vk <= 0x5A:
        return chr(vk)
    return "tasto %d" % vk


def posizione():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def sposta(x, y):
    user32.SetCursorPos(int(x), int(y))


def premuto(vk):
    """True se il tasto e' premuto ORA, anche se la nostra finestra non ha il
    fuoco: e' cosi' che funziona un tasto rapido globale."""
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def click(pulsante="sinistro", doppio=False, x=None, y=None):
    if x is not None and y is not None:
        sposta(x, y)
    giu, su = GIU_SU[pulsante]
    user32.mouse_event(giu, 0, 0, 0, 0)
    user32.mouse_event(su, 0, 0, 0, 0)
    if doppio:
        time.sleep(0.04)          # dentro il tempo di doppio click di Windows
        user32.mouse_event(giu, 0, 0, 0, 0)
        user32.mouse_event(su, 0, 0, 0, 0)


def tasto(vk, giu=True):
    user32.keybd_event(vk, 0, 0 if giu else KEYEVENTF_KEYUP, 0)


def nell_angolo(margine=3):
    """Failsafe: mouse nell'angolo in alto a sinistra dello schermo primario."""
    x, y = posizione()
    return x <= margine and y <= margine


def attesa_interrompibile(secondi, stop, passo=0.02):
    """Aspetta, ma controlla spesso se e' stato chiesto di fermarsi."""
    fine = time.time() + secondi
    while time.time() < fine:
        if stop.is_set():
            return False
        rimasto = fine - time.time()
        time.sleep(min(passo, rimasto) if rimasto > 0 else 0)
    return not stop.is_set()


# ------------------------------------------------------------------ registrazione
# Tasti da sorvegliare: i tre pulsanti del mouse e tutta la tastiera utile.
VK_SORVEGLIATI = [0x01, 0x02, 0x04] + list(range(0x08, 0xB8))


def registra(stop, ignora=(), su_evento=None, ritardo_iniziale=1.0):
    """Registra premute e rilasci (mouse + tastiera) finche' `stop` non scatta.

    Ritorna [{"t": secondi_dall_inizio, "vk": codice, "giu": bool, "x":, "y":}, ...]
    `ignora`: codici da non registrare (tipicamente il tasto rapido di stop).
    """
    time.sleep(ritardo_iniziale)      # non registrare il click sul pulsante Registra
    stato = {vk: premuto(vk) for vk in VK_SORVEGLIATI}
    eventi = []
    t0 = time.time()
    while not stop.is_set():
        for vk in VK_SORVEGLIATI:
            if vk in ignora:
                continue
            giu = premuto(vk)
            if giu != stato[vk]:
                stato[vk] = giu
                x, y = posizione()
                ev = {"t": round(time.time() - t0, 3), "vk": vk, "giu": giu,
                      "x": x, "y": y}
                eventi.append(ev)
                if su_evento:
                    su_evento(ev)
        time.sleep(0.004)
    return eventi


def taglia_coda(eventi, secondi=0.35):
    """Toglie gli ultimi eventi: se hai fermato la registrazione col mouse,
    quel click e' finito dentro."""
    if not eventi:
        return eventi
    limite = eventi[-1]["t"] - secondi
    tenuti = [e for e in eventi if e["t"] <= limite]
    return tenuti if tenuti else []


def riproduci(eventi, stop, ripetizioni=1, pausa_tra_giri=0.0, su_giro=None):
    """Riesegue gli eventi rispettando i tempi originali."""
    giro = 0
    while not stop.is_set() and (ripetizioni <= 0 or giro < ripetizioni):
        giro += 1
        t0 = time.time()
        for ev in eventi:
            if stop.is_set() or nell_angolo():
                return giro - 1
            ritardo = ev["t"] - (time.time() - t0)
            if ritardo > 0 and not attesa_interrompibile(ritardo, stop):
                return giro - 1
            if ev["vk"] in VK_MOUSE:
                sposta(ev["x"], ev["y"])
                giu, su = GIU_SU[VK_MOUSE[ev["vk"]]]
                user32.mouse_event(giu if ev["giu"] else su, 0, 0, 0, 0)
            else:
                tasto(ev["vk"], ev["giu"])
        if su_giro:
            su_giro(giro)
        if pausa_tra_giri and not attesa_interrompibile(pausa_tra_giri, stop):
            break
    return giro


def salva(eventi, percorso):
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(eventi, f)


def carica(percorso):
    if not os.path.isfile(percorso):
        return []
    try:
        with open(percorso, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return []
