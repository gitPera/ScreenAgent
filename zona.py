"""Scegli la zona dello schermo dentro cui cercare.

    python zona.py

Trascina il rettangolo e premi INVIO. Stampa una riga  "ZONA x y w h"  con le
coordinate assolute, che la GUI legge da sola.

Serve per escludere le barre dell'interfaccia: se cerchi per colore,
le icone colorate della barra somigliano a tutto.
"""
import sys
import time

import cv2

import screen as scr


def main():
    scr.enable_dpi_awareness()
    print("hai 2 secondi per portare in primo piano la finestra giusta...")
    time.sleep(2)
    shot, ox, oy = scr.grab()
    h, w = shot.shape[:2]
    k = min(1.0, 1850.0 / w, 950.0 / h)
    vista = cv2.resize(shot, None, fx=k, fy=k,
                       interpolation=cv2.INTER_AREA) if k < 1 else shot
    titolo = "Trascina la zona in cui cercare - INVIO conferma, C annulla"
    cv2.namedWindow(titolo, cv2.WINDOW_NORMAL)
    r = cv2.selectROI(titolo, vista, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()
    if r[2] == 0 or r[3] == 0:
        sys.exit("annullato")
    x, y, rw, rh = [int(v / k) for v in r]
    print("ZONA %d %d %d %d" % (x + ox, y + oy, rw, rh))


if __name__ == "__main__":
    main()
