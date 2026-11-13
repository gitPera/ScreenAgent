"""Salva l'immagine che hai negli appunti (Win+Shift+S) come template.

    python incolla.py                 dimmi solo cosa c'e' negli appunti
    python incolla.py icona_chrome    salvala in templates/icona_chrome.png
"""
import os
import sys

import cv2
import numpy as np
from PIL import ImageGrab

import vision

import percorsi
TPL_DIR = percorsi.TEMPLATES


def main():
    dati = ImageGrab.grabclipboard()

    if dati is None:
        sys.exit("[x] negli appunti non c'e' nessuna immagine.\n"
                 "    Rifai la cattura con Win+Shift+S (resta negli appunti) e riprova,\n"
                 "    oppure usa direttamente:  python agent.py snip <nome>")

    if isinstance(dati, list):   # hai copiato dei FILE, non un'immagine
        percorsi = [p for p in dati if str(p).lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))]
        if not percorsi:
            sys.exit("[x] negli appunti ci sono file, ma nessuna immagine: %s" % dati)
        img = cv2.imread(percorsi[0], cv2.IMREAD_UNCHANGED)
        print("[i] preso dal file copiato: %s" % percorsi[0])
    elif dati.mode in ("RGBA", "LA", "P"):
        rgba = np.array(dati.convert("RGBA"))
        if (rgba[:, :, 3] < 255).any():   # trasparenza vera: la conserviamo come maschera
            img = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGRA)
        else:
            img = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    else:
        img = cv2.cvtColor(np.array(dati.convert("RGB")), cv2.COLOR_RGB2BGR)

    if img is None:
        sys.exit("[x] immagine illeggibile")

    h, w = img.shape[:2]
    c = vision.contrast(img)
    alfa = img.ndim == 3 and img.shape[2] == 4
    print("[i] immagine negli appunti: %dx%d px, contrasto %.1f%s"
          % (w, h, c, ", con sfondo trasparente (maschera)" if alfa else ""))
    if not alfa and dati is not None and getattr(dati, "mode", "") == "RGBA":
        print("[i] ha il canale alfa ma e' tutto opaco: lo sfondo NON e' stato tolto.")

    if w > 400 or h > 400:
        print("[!] e' grossa: hai catturato piu' del singolo oggetto? Un'icona sta "
              "in ~40-120 px.\n    Piu' e' stretto il ritaglio, piu' e' affidabile.")
    if c < 6.0:
        print("[!] quasi tutta di un colore: verrebbe 'riconosciuta' ovunque, rifai il "
              "ritaglio\n    includendo un bordo o un dettaglio.")

    if len(sys.argv) < 2:
        print("\nPer salvarla:  python incolla.py <nome_che_vuoi>")
        return

    nome = sys.argv[1]
    if not nome.lower().endswith(".png"):
        nome += ".png"
    os.makedirs(TPL_DIR, exist_ok=True)
    out = os.path.join(TPL_DIR, nome)
    cv2.imwrite(out, img)
    print("\n[ok] salvato in %s" % out)
    print("Ora provala:   python agent.py find %s" % os.path.splitext(nome)[0])


if __name__ == "__main__":
    main()
