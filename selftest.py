"""Verifica che la pipeline funzioni, senza toccare mouse o tastiera.

Prende uno screenshot, ne ritaglia un pezzo a caso, e controlla che il
riconoscimento ritrovi quel pezzo esattamente dove si trovava.
"""
import screen as scr
import vision

scr.enable_dpi_awareness()

shot, ox, oy = scr.grab()
h, w = shot.shape[:2]
print("screenshot: %dx%d (offset %d,%d)" % (w, h, ox, oy))

# ritaglio di riferimento preso dallo schermo stesso: scegliamo la zona con piu'
# dettaglio, un ritaglio di colore piatto sarebbe ambiguo per definizione
cw, ch = 180, 90
candidati = [(x, y) for y in range(0, h - ch, max(1, (h - ch) // 6))
             for x in range(0, w - cw, max(1, (w - cw) // 8))]
x0, y0 = max(candidati, key=lambda p: vision.contrast(shot[p[1]:p[1] + ch, p[0]:p[0] + cw]))
crop = shot[y0:y0 + ch, x0:x0 + cw]
print("ritaglio di prova in (%d, %d), contrasto %.1f" % (x0, y0, vision.contrast(crop)))

matches = vision.find_template(shot, crop, threshold=0.9)
print("match trovati: %d" % len(matches))
if not matches:
    raise SystemExit("[x] FALLITO: non ha ritrovato il ritaglio")

cx, cy = vision.center(matches[0])
atteso = (x0 + cw // 2, y0 + ch // 2)
errore = abs(cx - atteso[0]) + abs(cy - atteso[1])
print("centro trovato %s, atteso %s, errore %d px, score %.3f"
      % ((cx, cy), atteso, errore, matches[0][4]))
if errore > 2:
    raise SystemExit("[x] FALLITO: posizione sbagliata")

import actions  # verifica solo che pyautogui si carichi
print("posizione mouse attuale:", actions.pyautogui.position())
print("[ok] tutto funziona")
