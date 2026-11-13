"""Registrazione e riproduzione FEDELE di tutto quello che fa l'utente.

A differenza del registratore dell'autoclicker (che a intervalli guarda quali
tasti sono premuti), qui si usano gli hook di sistema di Windows: WH_MOUSE_LL e
WH_KEYBOARD_LL intercettano OGNI evento nell'istante esatto in cui accade -
movimenti del mouse compresi, rotella compresa, ogni tasto. Cosi' la riproduzione
ripete il gesto identico, non solo i click.

Formato di un evento (chiavi corte per non gonfiare i file):
    {"t": secondi, "k": "m"}                       movimento -> + x, y
    {"t": secondi, "k": "b", "btn": "l/r/m/x1/x2", "giu": bool, "x":, "y":}  pulsante
    {"t": secondi, "k": "w", "d": delta, "orizz": bool, "x":, "y":}          rotella
    {"t": secondi, "k": "t", "vk":, "sc":, "ext": bool, "giu": bool}         tastiera
"""
import ctypes
import threading
import time
from ctypes import wintypes

import clicker

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_XBUTTONDOWN, WM_XBUTTONUP = 0x020B, 0x020C
WM_MOUSEWHEEL, WM_MOUSEHWHEEL = 0x020A, 0x020E

WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105

LLKHF_EXTENDED = 0x01

# flag per SendInput (mouse)
ME_MOVE = 0x0001
ME_ABSOLUTE = 0x8000
ME_VIRTUALDESK = 0x4000
ME_WHEEL, ME_HWHEEL = 0x0800, 0x01000
ME_LEFTDOWN, ME_LEFTUP = 0x0002, 0x0004
ME_RIGHTDOWN, ME_RIGHTUP = 0x0008, 0x0010
ME_MIDDLEDOWN, ME_MIDDLEUP = 0x0020, 0x0040
ME_XDOWN, ME_XUP = 0x0080, 0x0100
BTN_FLAG = {"l": (ME_LEFTDOWN, ME_LEFTUP), "r": (ME_RIGHTDOWN, ME_RIGHTUP),
            "m": (ME_MIDDLEDOWN, ME_MIDDLEUP)}

SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT


def _normalizza(x, y):
    """Coordinate schermo -> coordinate assolute 0..65535 su tutto il desktop
    virtuale (cosi' vale anche per il monitor a sinistra, con x negative)."""
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    if vw <= 1 or vh <= 1:
        return None
    nx = int(round((x - vx) * 65535.0 / (vw - 1)))
    ny = int(round((y - vy) * 65535.0 / (vh - 1)))
    return nx, ny


def _mouse(flags, x=None, y=None, data=0):
    """Un singolo evento mouse via SendInput. Se x,y sono dati, il movimento
    assoluto e' incluso NELLO STESSO evento del pulsante: e' cosi' che Windows
    riconosce un vero drag (spostamento e pressione arrivano insieme)."""
    mi = MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0)
    if x is not None:
        n = _normalizza(x, y)
        if n is None:
            clicker.sposta(x, y)
        else:
            mi.dx, mi.dy = n
            mi.dwFlags = flags | ME_MOVE | ME_ABSOLUTE | ME_VIRTUALDESK
    inp = INPUT(INPUT_MOUSE, _INPUTUNION(mi=mi))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _key(vk, scan, giu, ext):
    flags = 0
    if ext:
        flags |= KEYEVENTF_EXTENDEDKEY
    if not giu:
        flags |= KEYEVENTF_KEYUP
    ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    inp = INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=ki))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def muovi_assoluto(x, y):
    """Sposta il cursore iniettando un movimento nel pipeline di input (non con
    SetCursorPos, che non genera un vero WM_MOUSEMOVE e che le app non vedono)."""
    _mouse(0, x, y)

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.CFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p,
                                     wintypes.DWORD]
user32.CallNextHookEx.restype = LRESULT
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM,
                                  wintypes.LPARAM]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                               ctypes.c_uint]
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, ctypes.c_uint,
                                      wintypes.WPARAM, wintypes.LPARAM]

# di default Windows manda un WM_MOUSEMOVE ogni pochi millisecondi: registrarne
# uno ogni ~8 ms (125 al secondo) e' piu' fluido dell'occhio e tiene i file snelli
INTERVALLO_MOVIMENTO = 0.008


def registra(stop, ignora_vk=()):
    """Registra TUTTO finche' `stop` non scatta. Da chiamare in un thread suo:
    installa gli hook e fa girare il ciclo dei messaggi di Windows.
    """
    eventi = []
    t0 = time.perf_counter()
    ultimo_movimento = [0.0]

    def ora():
        return round(time.perf_counter() - t0, 3)

    def su_mouse(nCode, wParam, lParam):
        if nCode == 0:
            ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y = ms.pt.x, ms.pt.y
            w = wParam
            if w == WM_MOUSEMOVE:
                t = time.perf_counter() - t0
                if t - ultimo_movimento[0] >= INTERVALLO_MOVIMENTO:
                    ultimo_movimento[0] = t
                    eventi.append({"t": round(t, 3), "k": "m", "x": x, "y": y})
            elif w in (WM_LBUTTONDOWN, WM_LBUTTONUP):
                eventi.append({"t": ora(), "k": "b", "btn": "l",
                               "giu": w == WM_LBUTTONDOWN, "x": x, "y": y})
            elif w in (WM_RBUTTONDOWN, WM_RBUTTONUP):
                eventi.append({"t": ora(), "k": "b", "btn": "r",
                               "giu": w == WM_RBUTTONDOWN, "x": x, "y": y})
            elif w in (WM_MBUTTONDOWN, WM_MBUTTONUP):
                eventi.append({"t": ora(), "k": "b", "btn": "m",
                               "giu": w == WM_MBUTTONDOWN, "x": x, "y": y})
            elif w in (WM_XBUTTONDOWN, WM_XBUTTONUP):
                quale = "x2" if (ms.mouseData >> 16) & 0xFFFF == 2 else "x1"
                eventi.append({"t": ora(), "k": "b", "btn": quale,
                               "giu": w == WM_XBUTTONDOWN, "x": x, "y": y})
            elif w in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
                delta = ctypes.c_short((ms.mouseData >> 16) & 0xFFFF).value
                eventi.append({"t": ora(), "k": "w", "d": delta,
                               "orizz": w == WM_MOUSEHWHEEL, "x": x, "y": y})
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def su_tasto(nCode, wParam, lParam):
        if nCode == 0:
            kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if kb.vkCode not in ignora_vk:
                giu = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                eventi.append({"t": ora(), "k": "t", "vk": kb.vkCode,
                               "sc": kb.scanCode,
                               "ext": bool(kb.flags & LLKHF_EXTENDED), "giu": giu})
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    cb_mouse = HOOKPROC(su_mouse)     # riferimenti da tenere vivi: senza, crash
    cb_tasto = HOOKPROC(su_tasto)
    h_mouse = user32.SetWindowsHookExW(WH_MOUSE_LL, cb_mouse, None, 0)
    h_tasto = user32.SetWindowsHookExW(WH_KEYBOARD_LL, cb_tasto, None, 0)
    tid = kernel32.GetCurrentThreadId()

    def sveglia_per_uscire():
        stop.wait()
        user32.PostThreadMessageW(tid, WM_QUIT, 0, 0)

    threading.Thread(target=sveglia_per_uscire, daemon=True).start()

    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    if h_mouse:
        user32.UnhookWindowsHookEx(h_mouse)
    if h_tasto:
        user32.UnhookWindowsHookEx(h_tasto)
    return eventi


def _esegui(ev):
    k = ev.get("k")
    if k == "m":
        _mouse(0, ev["x"], ev["y"])
    elif k == "b":
        btn = ev["btn"]
        if btn in BTN_FLAG:
            giu, su = BTN_FLAG[btn]
            # movimento + pulsante nello STESSO evento: cosi' il drag e' credibile
            _mouse(giu if ev["giu"] else su, ev["x"], ev["y"])
        else:                                   # x1 / x2 (pulsanti laterali)
            dato = 1 if btn == "x1" else 2
            _mouse(ME_XDOWN if ev["giu"] else ME_XUP, ev["x"], ev["y"], dato)
    elif k == "w":
        evento = ME_HWHEEL if ev.get("orizz") else ME_WHEEL
        _mouse(evento, ev["x"], ev["y"], ev["d"])
    elif k == "t":
        _key(ev["vk"], ev.get("sc", 0), ev["giu"], ev.get("ext", False))
    else:
        # formato vecchio (registratore dell'autoclicker): vk + x,y
        vk = ev.get("vk")
        if vk in clicker.VK_MOUSE:
            btn = {0x01: "l", 0x02: "r", 0x04: "m"}[vk]
            giu, su = BTN_FLAG[btn]
            _mouse(giu if ev.get("giu") else su, ev.get("x", 0), ev.get("y", 0))
        elif vk is not None:
            _key(vk, 0, ev.get("giu", True), False)


# Dopo aver premuto un tasto del mouse, il sistema (e in particolare il drag di
# Explorer con DoDragDrop) ha bisogno di un attimo prima del movimento successivo
# per capire che e' un trascinamento e non un click. Questo indugio minimo lo
# garantisce, senza rovinare la fedelta' dei tempi (e' quanto ci mette una mano).
MIN_DOPO_PRESSIONE = 0.09


def trascina(ax, ay, bx, by, stop=None, durata=0.5, passi=24):
    """Trascina da (ax,ay) a (bx,by): preme il tasto sinistro alla partenza,
    aspetta un attimo (perche' il drag venga rilevato), si muove fino all'arrivo
    passando per punti intermedi, poi rilascia. Tutto via SendInput."""
    if stop is None:
        stop = threading.Event()
    # pressione (movimento + tasto giu' nello stesso evento) alla partenza
    _mouse(ME_LEFTDOWN, ax, ay)
    if not clicker.attesa_interrompibile(MIN_DOPO_PRESSIONE, stop):
        _mouse(ME_LEFTUP, ax, ay)
        return
    dx, dy = bx - ax, by - ay
    t0 = time.perf_counter()
    for i in range(1, passi + 1):
        if stop.is_set():
            break
        f = i / float(passi)
        curva = f * f * (3 - 2 * f)          # ease-in-out: parte piano, frena
        _mouse(0, int(round(ax + dx * curva)), int(round(ay + dy * curva)))
        ritardo = t0 + durata * f - time.perf_counter()
        if ritardo > 0 and not clicker.attesa_interrompibile(ritardo, stop):
            break
    _mouse(0, bx, by)                        # arrivo esatto
    clicker.attesa_interrompibile(0.05, stop)
    _mouse(ME_LEFTUP, bx, by)                # rilascio


def _e_pressione_mouse(ev):
    return (ev.get("k") == "b" and ev.get("giu")) or \
           (ev.get("k") is None and ev.get("vk") in clicker.VK_MOUSE and ev.get("giu"))


def riproduci(eventi, stop, ripetizioni=1, pausa_tra_giri=0.0, su_giro=None):
    """Riesegue gli eventi rispettando i tempi originali."""
    giro = 0
    while not stop.is_set() and (ripetizioni <= 0 or giro < ripetizioni):
        giro += 1
        t0 = time.perf_counter()
        dwell_fino_a = 0.0
        for ev in eventi:
            if stop.is_set() or clicker.nell_angolo():
                return giro - 1
            ritardo = ev["t"] - (time.perf_counter() - t0)
            if ritardo > 0 and not clicker.attesa_interrompibile(ritardo, stop):
                return giro - 1
            # rispetta l'indugio minimo dopo una pressione del mouse
            extra = dwell_fino_a - time.perf_counter()
            if extra > 0 and not clicker.attesa_interrompibile(extra, stop):
                return giro - 1
            _esegui(ev)
            if _e_pressione_mouse(ev):
                dwell_fino_a = time.perf_counter() + MIN_DOPO_PRESSIONE
        if su_giro:
            su_giro(giro)
        if pausa_tra_giri and not clicker.attesa_interrompibile(pausa_tra_giri, stop):
            break
    return giro


def riassunto(eventi):
    """Conta le azioni per tipo, per mostrarle nell'interfaccia."""
    c = {"m": 0, "b": 0, "w": 0, "t": 0}
    for e in eventi:
        k = e.get("k")
        if k in c:
            c[k] += 1
        elif e.get("vk") in clicker.VK_MOUSE:
            c["b"] += 1
        elif "vk" in e:
            c["t"] += 1
    durata = eventi[-1]["t"] if eventi else 0.0
    return c, durata
