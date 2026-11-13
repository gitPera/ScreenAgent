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
VK_ESC = 0x1B        # tasto di emergenza: ferma tutto, sempre e comunque
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x01000
TACCA = 120          # Windows conta 120 per ogni scatto di rotella

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


def premuto_o_scattato(vk):
    """True se il tasto e' giu' adesso (bit 0x8000) OPPURE se e' stato premuto
    da quando l'abbiamo chiesto l'ultima volta (bit 0x0001).

    Serve per i tasti di stop: controllando solo "e' giu' adesso" ogni 30 ms,
    una pressione piu' breve di un controllo passa inosservata, e un freno
    d'emergenza che ogni tanto non risponde non serve a niente.
    """
    return bool(user32.GetAsyncKeyState(vk) & 0x8001)


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


def muovi(x, y, durata=None):
    """Porta il cursore a destinazione scorrendo, non di scatto.

    Fa molti passetti con una curva che parte piano, accelera e frena in
    arrivo (ease-in-out): e' il profilo di un movimento a mano, e alcune
    applicazioni ignorano i puntatori che 'teletrasportano'.
    Se non dici quanto deve durare, lo decide la distanza.
    """
    x, y = int(x), int(y)
    x0, y0 = posizione()
    dx, dy = x - x0, y - y0
    distanza = (dx * dx + dy * dy) ** 0.5
    if distanza < 3:
        sposta(x, y)
        return
    if durata is None:
        durata = min(0.55, max(0.12, distanza / 2200.0))
    passi = int(max(12, min(distanza / 5.0, 140)))

    inizio = time.perf_counter()
    for i in range(1, passi + 1):
        t = float(i) / passi
        curva = t * t * (3 - 2 * t)          # ease-in-out
        sposta(int(round(x0 + dx * curva)), int(round(y0 + dy * curva)))
        prossimo = inizio + durata * t
        ritardo = prossimo - time.perf_counter()
        if ritardo > 0:
            time.sleep(ritardo)
    sposta(x, y)                              # l'arrivo dev'essere esatto


def scorri(tacche, orizzontale=False):
    """Rotella del mouse: numero positivo = in su', negativo = in giu'.

    Non si usa pyautogui.scroll perche' manda a Windows un delta pari al numero
    di scatti (3) invece dei 120 per scatto che Windows si aspetta: il sistema lo
    considera un movimento da nulla e non scorre niente.
    """
    tacche = int(tacche)
    if not tacche:
        return
    evento = MOUSEEVENTF_HWHEEL if orizzontale else MOUSEEVENTF_WHEEL
    delta = TACCA if tacche > 0 else -TACCA
    for _ in range(abs(tacche)):
        user32.mouse_event(evento, 0, 0, ctypes.c_int(delta), 0)
        time.sleep(0.02)


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
    # se la cartella (macro/) non c'e' la creo: il salvataggio non deve fallire
    os.makedirs(os.path.dirname(os.path.abspath(percorso)), exist_ok=True)
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
