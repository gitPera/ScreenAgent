"""Riconoscimento di un oggetto a schermo.

Due strategie:
  1. find_template  -> confronto pixel (veloce, preciso, richiede un ritaglio di riferimento)
  2. find_text      -> OCR, trova una scritta (richiede pytesseract + Tesseract installato)
"""
import cv2
import numpy as np

Match = tuple  # (x, y, w, h, score) in coordinate immagine

# Un template che combacia con mezzo schermo (es. un'area di colore piatto) genera
# decine di migliaia di candidati: li limitiamo ai migliori, altrimenti la
# deduplica impiega minuti.
MAX_CANDIDATES = 400


def _nms(boxes, iou_thr=0.4):
    """Toglie i doppioni sovrapposti, tiene il punteggio piu' alto."""
    boxes = sorted(boxes, key=lambda b: -b[4])
    kept = []
    for b in boxes:
        x1, y1, w1, h1, _ = b
        dup = False
        for k in kept:
            x2, y2, w2, h2, _ = k
            ix = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
            iy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
            inter = ix * iy
            union = w1 * h1 + w2 * h2 - inter
            if union and inter / union > iou_thr:
                dup = True
                break
        if not dup:
            kept.append(b)
    return kept


def contrast(template):
    """Deviazione standard dei pixel: sotto ~6 il template e' quasi uniforme
    e verra' 'trovato' ovunque. Serve per avvisare l'utente."""
    if template.ndim == 2:
        g = template
    elif template.shape[2] == 4:
        g = cv2.cvtColor(template, cv2.COLOR_BGRA2GRAY)
    else:
        g = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    return float(g.std())


def match_map(img, tpl, mask=None):
    """Mappa dei punteggi (0..1) di tpl dentro img.

    Con `mask` (canale alfa del PNG) contano SOLO i pixel opachi: e' il modo
    giusto di cercare uno sprite ritagliato male, con sfondo variabile intorno.
    OpenCV accetta la maschera solo con TM_SQDIFF, quindi normalizziamo a mano.
    """
    if mask is None:
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    else:
        sq = cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF, mask=mask)
        pixel_utili = float((mask.astype(np.float64) / 255.0).sum())
        canali = 1 if tpl.ndim == 2 else tpl.shape[2]
        denom = max(pixel_utili * canali * (255.0 ** 2), 1.0)
        # scarto quadratico medio -> punteggio: senza la radice i punteggi
        # starebbero tutti schiacciati sopra 0.94 e la soglia non discriminerebbe
        res = 1.0 - np.sqrt(np.clip(sq / denom, 0.0, 1.0))
    return np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)


def find_template(screen, template, threshold=0.85, scales=(1.0,), grayscale=True,
                  max_candidates=MAX_CANDIDATES, mask=None):
    """Cerca `template` dentro `screen`. Ritorna lista di match ordinati per punteggio.

    scales: prova piu' dimensioni, utile se la finestra e' ridimensionabile.
            es. (0.8, 0.9, 1.0, 1.1, 1.2)
    mask:   canale alfa (uint8) delle stesse dimensioni del template; i pixel a 0
            vengono ignorati nel confronto.
    """
    img = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY) if grayscale else screen
    tpl0 = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) if grayscale else template

    found = []
    for s in scales:
        if s == 1.0:
            tpl, msk = tpl0, mask
        else:
            tpl = cv2.resize(tpl0, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
            msk = None if mask is None else cv2.resize(
                mask, (tpl.shape[1], tpl.shape[0]), interpolation=cv2.INTER_NEAREST)
        th, tw = tpl.shape[:2]
        if th > img.shape[0] or tw > img.shape[1]:
            continue
        res = match_map(img, tpl, msk)
        ys, xs = np.where(res >= threshold)
        if xs.size == 0:
            continue
        scores = res[ys, xs]
        if xs.size > max_candidates:   # tieni solo i migliori
            idx = np.argpartition(-scores, max_candidates - 1)[:max_candidates]
            xs, ys, scores = xs[idx], ys[idx], scores[idx]
        found.extend((int(x), int(y), tw, th, float(sc))
                     for x, y, sc in zip(xs, ys, scores))
    return _nms(found)


def profilo_colore(template, soglia_luce=70):
    """Ricava dalla figura la fascia di colore (HSV) dei suoi pixel luminosi.

    Serve per cercare un oggetto che RUOTA o si anima: i pixel cambiano posto,
    ma il colore resta quello.
    """
    if template.ndim == 3 and template.shape[2] == 4:
        bgr = cv2.cvtColor(template, cv2.COLOR_BGRA2BGR)
        alfa = template[:, :, 3]
    else:
        bgr = template if template.ndim == 3 else cv2.cvtColor(template,
                                                               cv2.COLOR_GRAY2BGR)
        alfa = None

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    utili = hsv[:, :, 2] > soglia_luce
    if alfa is not None:
        utili &= alfa > 128
    if utili.sum() < 15:      # figura scura: prendi il 30% piu' chiaro
        utili = hsv[:, :, 2] >= np.percentile(hsv[:, :, 2], 70)

    H, S, V = hsv[:, :, 0][utili], hsv[:, :, 1][utili], hsv[:, :, 2][utili]
    basso = np.array([max(0, np.percentile(H, 5) - 6),
                      max(0, np.percentile(S, 5) - 40),
                      max(30, np.percentile(V, 5) - 40)], dtype=np.uint8)
    alto = np.array([min(179, np.percentile(H, 95) + 6),
                     min(255, np.percentile(S, 95) + 60), 255], dtype=np.uint8)
    return {"basso": basso, "alto": alto, "area": int(utili.sum()),
            "w": template.shape[1], "h": template.shape[0]}


def find_color(screen, template, threshold=0.35, profilo=None, area_minima=30):
    """Cerca le macchie dello stesso colore del template.

    Il punteggio qui NON e' una somiglianza di forma ma di DIMENSIONE: 1.00 vuol
    dire "grande esattamente come il modello". Percio' la soglia va molto piu'
    bassa che nel confronto pixel (0.30-0.50 invece di 0.85).
    """
    p = profilo or profilo_colore(template)
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    maschera = cv2.inRange(hsv, p["basso"], p["alto"])
    maschera = cv2.morphologyEx(maschera, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    quante, _, stat, _ = cv2.connectedComponentsWithStats(maschera, 8)
    trovati = []
    for i in range(1, quante):
        x, y, w, h, area = stat[i]
        if area < area_minima:
            continue
        if not (p["w"] * 0.3 <= w <= p["w"] * 2.5):
            continue
        if not (p["h"] * 0.3 <= h <= p["h"] * 2.5):
            continue
        punteggio = min(area, p["area"]) / float(max(area, p["area"]))
        if punteggio >= threshold:
            trovati.append((int(x), int(y), int(w), int(h), float(punteggio)))
    return _nms(trovati)


def center(match):
    x, y, w, h, _ = match
    return x + w // 2, y + h // 2


def find_text(screen, query, min_conf=60):
    """Trova una scritta a schermo via OCR. Ritorna lista di match come find_template."""
    try:
        import pytesseract
    except ImportError:
        raise RuntimeError("Serve pytesseract + Tesseract-OCR. Vedi README.")

    data = pytesseract.image_to_data(screen, output_type=pytesseract.Output.DICT,
                                     lang="ita+eng")
    q = query.lower().strip()
    out = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        try:
            conf = float(data["conf"][i])
        except ValueError:
            continue
        if conf < min_conf:
            continue
        if q in word.lower():
            out.append((data["left"][i], data["top"][i],
                        data["width"][i], data["height"][i], conf / 100.0))
    return sorted(out, key=lambda b: -b[4])
