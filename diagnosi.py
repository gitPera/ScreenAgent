"""Perche' non lo trova? Questo script te lo dice.

    python diagnosi.py icona

Guarda il template, fa uno screenshot e prova TUTTE le scale, poi stampa il
punteggio migliore ottenuto e salva templates/_debug_<nome>.png con il rettangolo
disegnato dove ha trovato la somiglianza maggiore.
"""
import os
import sys
import time

import cv2
import numpy as np

import screen as scr
import vision

TPL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def main():
    if len(sys.argv) < 2:
        sys.exit("uso: python diagnosi.py <nome_template>")

    nome = sys.argv[1]
    attesa = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    base = nome if nome.lower().endswith(".png") else nome + ".png"
    p = base if os.path.isfile(base) else os.path.join(TPL_DIR, base)
    if not os.path.isfile(p):
        sys.exit("[x] non esiste: %s" % p)

    # 1) il template e' sano?
    raw = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    print("--- TEMPLATE ---")
    print("file: %s" % p)
    print("dimensioni: %dx%d, canali: %d" % (raw.shape[1], raw.shape[0],
                                             1 if raw.ndim == 2 else raw.shape[2]))
    mask = None
    if raw.ndim == 3 and raw.shape[2] == 4:
        alpha = raw[:, :, 3]
        trasparenti = int((alpha < 255).sum())
        if trasparenti:
            mask = alpha
            print("[i] %d pixel su %d sono trasparenti: uso la MASCHERA, contano solo "
                  "i pixel opachi\n    (con la maschera i punteggi non sono confrontabili"
                  " con quelli senza: ricalibra la soglia)" % (trasparenti, alpha.size))
        else:
            print("[i] ha il canale alfa ma e' tutto opaco: nessuna maschera."
                  "\n    Per uno sprite su sfondo variabile, cancella lo sfondo e "
                  "risalvalo in PNG.")
    tpl = cv2.imread(p, cv2.IMREAD_COLOR)
    print("contrasto: %.1f%s" % (vision.contrast(tpl),
                                 "  [!] troppo piatto" if vision.contrast(tpl) < 6 else ""))

    if attesa:
        print("\nhai %g secondi per mostrare a schermo l'oggetto..." % attesa)
        time.sleep(attesa)

    # 2) cosa c'e' a schermo adesso
    scr.enable_dpi_awareness()
    shot, ox, oy = scr.grab()
    print("\n--- SCHERMO ---")
    print("catturati %dx%d px a partire da (%d, %d)"
          % (shot.shape[1], shot.shape[0], ox, oy))

    # 3) prova tutte le scale
    print("\n--- RICERCA (provo diverse dimensioni) ---")
    img_g = cv2.cvtColor(shot, cv2.COLOR_BGR2GRAY)
    tpl_g = cv2.cvtColor(tpl, cv2.COLOR_BGR2GRAY)
    risultati = []
    for s in [0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0,
              1.05, 1.1, 1.15, 1.2, 1.25, 1.33, 1.5, 1.75, 2.0]:
        if s == 1.0:
            t, m = tpl_g, mask
        else:
            t = cv2.resize(tpl_g, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            m = None if mask is None else cv2.resize(
                mask, (t.shape[1], t.shape[0]), interpolation=cv2.INTER_NEAREST)
        if t.shape[0] > img_g.shape[0] or t.shape[1] > img_g.shape[1] or min(t.shape) < 4:
            continue
        res = vision.match_map(img_g, t, m)
        _, punteggio, _, loc = cv2.minMaxLoc(res)
        risultati.append((punteggio, s, loc, t.shape[1], t.shape[0]))

    risultati.sort(reverse=True)
    for punteggio, s, loc, tw, th in risultati[:5]:
        print("  scala %4.2f (%3dx%3d px) -> punteggio %.3f in (%d, %d)"
              % (s, tw, th, punteggio, loc[0] + ox, loc[1] + oy))

    best, s, loc, tw, th = risultati[0]

    # 4) verdetto
    print("\n--- VERDETTO ---")
    if best >= 0.85:
        print("[ok] TROVATO con punteggio %.3f alla scala %.2f" % (best, s))
        if abs(s - 1.0) > 0.01:
            print("     Nota: combacia a scala %.2f, non 1.00. Apri agent.py e metti:" % s)
            print("     SCALES = (0.8, 0.9, 1.0, 1.1, 1.2)")
        print("     Coordinate del centro: (%d, %d)"
              % (loc[0] + tw // 2 + ox, loc[1] + th // 2 + oy))
    elif best >= 0.6:
        print("[~] somiglianza parziale (%.3f): l'oggetto c'e' ma e' cambiato" % best)
        print("    (evidenziato/selezionato? tema diverso? sfondo diverso dietro?)")
        print("    Prova:  python agent.py click %s --threshold %.2f"
              % (os.path.splitext(base)[0], max(0.5, best - 0.05)))
    else:
        print("[x] punteggio massimo %.3f: l'oggetto NON e' visibile a schermo adesso."
              % best)
        print("    Se e' un'icona del desktop, il desktop e' coperto da questa finestra!")
        print("    Prova cosi', hai 5 secondi per minimizzare tutto (tasto Win+D):")
        print("      python diagnosi.py %s 5" % os.path.splitext(base)[0])

    # 5) e se cercassimo per colore? (per gli oggetti che ruotano e' l'unica via)
    prof = vision.profilo_colore(tpl)
    per_colore = vision.find_color(shot, tpl, threshold=0.3, profilo=prof)
    print("\n--- ALTERNATIVA: RICERCA PER COLORE ---")
    print("colore del modello: H %d-%d, S %d-%d, V %d+"
          % (prof["basso"][0], prof["alto"][0], prof["basso"][1], prof["alto"][1],
             prof["basso"][2]))
    if per_colore:
        print("cercando per colore troverei %d oggetti simili, il migliore in (%d, %d)"
              % (len(per_colore), per_colore[0][0] + per_colore[0][2] // 2 + ox,
                 per_colore[0][1] + per_colore[0][3] // 2 + oy))
        if best < 0.85:
            print("--> il confronto pixel non ce la fa ma il colore si': usa")
            print("    python agent.py click %s --colore --threshold 0.35"
                  % os.path.splitext(base)[0])
            print("    e restringi la zona con --zona (python zona.py) per non")
            print("    prendere le icone colorate dell'interfaccia.")
    else:
        print("nemmeno per colore trovo qualcosa: l'oggetto non e' proprio a schermo.")

    out = os.path.join(TPL_DIR, "_debug_%s" % base)
    dbg = shot.copy()
    cv2.rectangle(dbg, loc, (loc[0] + tw, loc[1] + th), (0, 0, 255), 3)
    cv2.imwrite(out, dbg)
    print("\nHo salvato %s: aprilo e guarda cosa ha cerchiato in rosso." % out)


if __name__ == "__main__":
    main()
