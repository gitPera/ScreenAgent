"""Cattura schermo + consapevolezza DPI (fondamentale su Windows con scaling != 100%)."""
import ctypes
import mss
import numpy as np
import cv2


def enable_dpi_awareness():
    """Senza questo, screenshot e coordinate del mouse non coincidono se hai
    lo scaling di Windows a 125%/150%."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _sct():
    return (mss.MSS if hasattr(mss, "MSS") else mss.mss)()


def list_monitors():
    """monitors[0] = tutti gli schermi insieme, poi uno per schermo."""
    with _sct() as sct:
        return list(sct.monitors)


def primary_index():
    for i, m in enumerate(list_monitors()):
        if i and m.get("is_primary"):
            return i
    return 1


def grab(region=None, monitor=0):
    """Ritorna (immagine BGR, offset_x, offset_y).

    region  = (x, y, w, h) in coordinate schermo assolute, oppure None
    monitor = 0 -> tutti gli schermi (default), 1..n -> un singolo schermo.
              Le coordinate restituite sono sempre assolute: su uno schermo
              posto a sinistra del primario sono negative, e' normale e il
              mouse ci arriva lo stesso.
    """
    with _sct() as sct:
        if region is None:
            mon = sct.monitors[monitor]
        else:
            x, y, w, h = region
            mon = {"left": x, "top": y, "width": w, "height": h}
        raw = np.array(sct.grab(mon))
    img = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
    return img, mon["left"], mon["top"]
