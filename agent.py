"""ScreenAgent - vede lo schermo e clicca quello che gli dici.

Uso rapido:
    python agent.py snip pulsante_salva            ritaglia un riferimento dallo schermo
    python agent.py find pulsante_salva            dove si trova? (non clicca)
    python agent.py click pulsante_salva           cliccalo
    python agent.py click pulsante_salva --wait 30 aspetta finche' compare, poi clicca
    python agent.py text "Salva"                   clicca la scritta "Salva" (OCR)
    python agent.py run script.esempio.json        esegue una sequenza di azioni
    python agent.py repl                           modalita' interattiva: comandi a mano
"""
import argparse
import json
import os
import sys
import time

import cv2

import actions
import screen as scr
import vision

TPL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
SCALES = (1.0,)


def tpl_path(name):
    if os.path.isfile(name):
        return name
    if not name.lower().endswith(".png"):
        name += ".png"
    return os.path.join(TPL_DIR, name)


_CACHE = {}


def load_template(name):
    p = tpl_path(name)
    chiave = (p, os.path.getmtime(p) if os.path.isfile(p) else 0)
    if chiave in _CACHE:          # nel ciclo non rileggiamo il file ogni volta
        return _CACHE[chiave]
    if not os.path.isfile(p):
        sys.exit("[x] template non trovato: %s\n    creane uno con:  python agent.py snip %s"
                 % (p, name))
    raw = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    if raw is None:
        sys.exit("[x] file illeggibile (non e' un'immagine valida): %s" % p)

    mask = None
    if raw.ndim == 2:
        img = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
    elif raw.shape[2] == 4:
        alpha = raw[:, :, 3]
        img = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        if (alpha < 255).any():   # sfondo cancellato: confronta solo i pixel opachi
            mask = alpha
    else:
        img = raw

    if mask is None and vision.contrast(img) < 6.0:
        print("[!] attenzione: '%s' e' quasi tutto di un colore, verra' 'riconosciuto'"
              " ovunque.\n    Ritaglialo di nuovo su una parte con piu' dettaglio." % name)
    _CACHE[chiave] = (img, mask)
    return img, mask


def locate(name, threshold=0.85, region=None, scales=SCALES, monitor=0):
    """Ritorna ((x, y) centro in coordinate schermo, punteggio) oppure (None, 0)."""
    shot, ox, oy = scr.grab(region, monitor)
    tpl, mask = load_template(name)
    matches = vision.find_template(shot, tpl, threshold, scales, mask=mask)
    if not matches:
        return None, 0.0
    cx, cy = vision.center(matches[0])
    return (cx + ox, cy + oy), matches[0][4]


def locate_many(names, threshold=0.85, region=None, scales=SCALES, monitor=0,
                best=False, colore=False):
    """Cerca PIU' template dentro UN SOLO screenshot (molto piu' veloce che
    chiamare locate() una volta per immagine).

    Ritorna [(nome, (x, y), punteggio), ...]: nell'ordine dei nomi (= priorita')
    oppure dal punteggio piu' alto se best=True. Lista vuota se non trova niente.

    colore=True cerca per COLORE invece che pixel per pixel: unico modo per
    prendere un oggetto che ruota o si anima (soglia consigliata 0.35).
    """
    shot, ox, oy = scr.grab(region, monitor)
    risultati = []
    for n in names:
        tpl, mask = load_template(n)
        if colore:
            trovati = vision.find_color(shot, tpl, threshold)
        else:
            trovati = vision.find_template(shot, tpl, threshold, scales, mask=mask)
        if trovati:
            cx, cy = vision.center(trovati[0])
            risultati.append((n, (cx + ox, cy + oy), trovati[0][4]))
    if best:
        risultati.sort(key=lambda r: -r[2])
    return risultati


def locate_many_wait(names, timeout=0.0, threshold=0.85, region=None, poll=0.4,
                     monitor=0, best=False, colore=False):
    deadline = time.time() + max(timeout, 0)
    while True:
        risultati = locate_many(names, threshold, region, SCALES, monitor, best,
                                colore)
        if risultati or time.time() >= deadline:
            return risultati
        time.sleep(poll)


def locate_wait(name, timeout=0.0, threshold=0.85, region=None, poll=0.4, monitor=0):
    deadline = time.time() + max(timeout, 0)
    while True:
        pos, score = locate(name, threshold, region, SCALES, monitor)
        if pos or time.time() >= deadline:
            return pos, score
        time.sleep(poll)


# ---------------------------------------------------------------- comandi

def cmd_snip(args):
    """Screenshot -> selezioni col mouse il rettangolo -> salvato come template."""
    print("Hai 3 secondi per portare in primo piano la finestra da catturare...")
    time.sleep(3)
    shot, ox, oy = scr.grab(monitor=args.monitor)
    h, w = shot.shape[:2]
    view = shot.copy()
    k = min(1.0, 1850.0 / w, 950.0 / h)
    if k < 1.0:
        view = cv2.resize(view, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
    title = "Trascina sull'oggetto - INVIO per confermare, C per annullare"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    r = cv2.selectROI(title, view, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()
    if r[2] == 0 or r[3] == 0:
        sys.exit("annullato")
    x, y, rw, rh = [int(v / k) for v in r]
    crop = shot[y:y + rh, x:x + rw]
    os.makedirs(TPL_DIR, exist_ok=True)
    out = tpl_path(args.name)
    cv2.imwrite(out, crop)
    print("[ok] salvato %s  (%dx%d px)" % (out, rw, rh))


def cmd_monitors(args):
    for i, m in enumerate(scr.list_monitors()):
        etichetta = "TUTTI GLI SCHERMI" if i == 0 else (
            "primario" if m.get("is_primary") else "secondario")
        print("  --monitor %d  %s  %dx%d a partire da (%d, %d)  %s"
              % (i, etichetta.ljust(17), m["width"], m["height"],
                 m["left"], m["top"], m.get("name", "")))


def zona_di(args):
    return tuple(args.zona) if getattr(args, "zona", None) else None


def cmd_find(args):
    risultati = locate_many_wait(args.name, args.wait, args.threshold,
                                 region=zona_di(args), monitor=args.monitor,
                                 best=args.best, colore=args.colore)
    if not risultati:
        print("[x] non trovato (%d template cercati)" % len(args.name))
        sys.exit(1)
    for nome, pos, score in risultati:
        print("[ok] %-20s in (%d, %d)  match %.2f" % (nome, pos[0], pos[1], score))
    if len(args.name) > 1:
        print("-> con un click agirei su '%s'" % risultati[0][0])


def cmd_click(args):
    risultati = locate_many_wait(args.name, args.wait, args.threshold,
                                 region=zona_di(args), monitor=args.monitor,
                                 best=args.best, colore=args.colore)
    if not risultati:
        print("[x] non trovato, non clicco nulla")
        sys.exit(1)
    nome, pos, score = risultati[0]
    if args.offset != [0, 0]:
        pos = (pos[0] + args.offset[0], pos[1] + args.offset[1])
        print("[i] scostamento applicato: %+d, %+d" % tuple(args.offset))
    print("[ok] '%s' trovato in %s (match %.2f) -> click" % (nome, pos, score))
    if args.double:
        actions.double_click(*pos)
    elif args.right:
        actions.right_click(*pos)
    else:
        actions.click(*pos)

    if args.press:
        actions.wait(args.press_delay)
        actions.hotkey(*args.press.split("+"))
        print("[ok] premuto '%s' dopo %.2fs" % (args.press, args.press_delay))


def cmd_text(args):
    shot, ox, oy = scr.grab(monitor=args.monitor)
    matches = vision.find_text(shot, args.query)
    if not matches:
        print("[x] testo non trovato")
        sys.exit(1)
    cx, cy = vision.center(matches[0])
    print("[ok] '%s' in (%d, %d)" % (args.query, cx + ox, cy + oy))
    if not args.dry_run:
        actions.click(cx + ox, cy + oy)


def cmd_loop(args):
    """Cerca all'infinito e clicca ogni volta che compare. Ctrl+C per fermare."""
    for n in args.name:
        load_template(n)       # fallisce subito se un template non esiste
    print("Ciclo su %s: cerco e clicco finche' non lo fermi (Ctrl+C)."
          % ", ".join("'%s'" % n for n in args.name))
    if len(args.name) > 1:
        print("Criterio: %s." % ("punteggio piu' alto" if args.best
                                 else "ordine di priorita' come li hai scritti"))
    if args.durata:
        print("Mi fermo da solo dopo %g secondi." % args.durata)
    print("Failsafe: porta il mouse nell'angolo in alto a sinistra per abortire.\n")

    inizio = time.time()
    scadenza = inizio + args.durata if args.durata else None
    cicli = presi = errori = 0
    ultimo_stato = inizio

    try:
        while True:
            if scadenza and time.time() >= scadenza:
                print("[i] tempo scaduto")
                break
            cicli += 1
            try:
                risultati = locate_many(args.name, args.threshold,
                                        region=zona_di(args),
                                        monitor=args.monitor, best=args.best,
                                        colore=args.colore)
            except KeyboardInterrupt:
                raise
            except Exception as e:            # uno screenshot fallito non ferma il ciclo
                errori += 1
                print("[!] errore nella ricerca: %s" % e)
                risultati = []

            if risultati:
                nome, pos, score = risultati[0]
                pos = (pos[0] + args.offset[0], pos[1] + args.offset[1])
                actions.click(*pos, clicks=2 if args.double else 1)
                if args.press:
                    actions.wait(args.press_delay)
                    actions.hotkey(*args.press.split("+"))
                presi += 1
                altri = (" (+%d altri visibili)" % (len(risultati) - 1)
                         if len(risultati) > 1 else "")
                print("[%s] #%d '%s' cliccato in (%d, %d)  match %.2f%s"
                      % (time.strftime("%H:%M:%S"), presi, nome, pos[0], pos[1],
                         score, altri))
                if args.max and presi >= args.max:
                    print("[i] raggiunto il massimo di %d" % args.max)
                    break
                time.sleep(args.cooldown)
                ultimo_stato = time.time()
            else:
                if time.time() - ultimo_stato >= args.stato:
                    print("[%s] ...sto ancora cercando (%d controlli, %d presi)"
                          % (time.strftime("%H:%M:%S"), cicli, presi))
                    ultimo_stato = time.time()
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n[i] fermato da te")

    durata = time.time() - inizio
    print("\n--- RIEPILOGO ---")
    print("durata: %dm %ds | controlli: %d | cliccati: %d | errori: %d"
          % (durata // 60, durata % 60, cicli, presi, errori))
    if presi:
        print("media: uno ogni %.0f secondi" % (durata / presi))


def do_step(step):
    """Esegue un singolo passo di uno script."""
    op = step.get("do")
    if op == "click":
        nomi = step["target"] if isinstance(step["target"], list) else [step["target"]]
        risultati = locate_many_wait(nomi, step.get("timeout", 5),
                                     step.get("threshold", 0.85),
                                     monitor=step.get("monitor", 0),
                                     best=step.get("best", False))
        if not risultati:
            raise RuntimeError("non trovo %s" % step["target"])
        nome, pos, _ = risultati[0]
        dx, dy = step.get("offset", (0, 0))
        actions.click(pos[0] + dx, pos[1] + dy)
        print("    -> '%s'" % nome)
    elif op == "click_text":
        shot, ox, oy = scr.grab(monitor=step.get("monitor", 0))
        m = vision.find_text(shot, step["text"])
        if not m:
            raise RuntimeError("non trovo il testo '%s'" % step["text"])
        cx, cy = vision.center(m[0])
        actions.click(cx + ox, cy + oy)
    elif op == "type":
        actions.type_text(step["text"])
    elif op == "key":
        actions.hotkey(*step["keys"].split("+"))
    elif op == "scroll":
        actions.scroll(step.get("amount", -3))
    elif op == "wait":
        actions.wait(step.get("seconds", 1))
    elif op == "wait_for":
        nomi = step["target"] if isinstance(step["target"], list) else [step["target"]]
        if not locate_many_wait(nomi, step.get("timeout", 30),
                                monitor=step.get("monitor", 0)):
            raise RuntimeError("timeout aspettando %s" % step["target"])
    else:
        raise ValueError("passo sconosciuto: %s" % op)


def cmd_run(args):
    with open(args.script, encoding="utf-8") as f:
        script = json.load(f)
    steps = script["steps"] if isinstance(script, dict) else script
    for loop in range(args.repeat):
        for i, step in enumerate(steps, 1):
            print("[%d/%d] passo %d/%d: %s" % (loop + 1, args.repeat, i, len(steps), step))
            do_step(step)
    print("[ok] script completato")


def cmd_repl(args):
    print("Comandi disponibili:")
    print("  click <nome>   find <nome>   text <parola>")
    print("  type <testo>   key ctrl+s    wait 2        quit")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        verb, _, rest = line.partition(" ")
        try:
            if verb == "click":
                do_step({"do": "click", "target": rest, "timeout": 5})
            elif verb == "find":
                pos, score = locate(rest)
                print("  %s (match %.2f)" % (pos, score) if pos else "  non trovato")
            elif verb == "text":
                do_step({"do": "click_text", "text": rest})
            elif verb == "type":
                actions.type_text(rest)
            elif verb == "key":
                actions.hotkey(*rest.split("+"))
            elif verb == "wait":
                actions.wait(float(rest))
            else:
                print("  comando sconosciuto")
        except Exception as e:
            print("  [x] %s" % e)


def main():
    scr.enable_dpi_awareness()
    p = argparse.ArgumentParser(description="Agente che vede lo schermo e agisce")
    sub = p.add_subparsers(dest="cmd", required=True)

    mon_help = "0 = tutti gli schermi (default), 1..n = un solo schermo"

    s = sub.add_parser("monitors", help="elenca gli schermi rilevati")
    s.set_defaults(func=cmd_monitors)

    s = sub.add_parser("snip", help="ritaglia un oggetto dallo schermo e salvalo")
    s.add_argument("name")
    s.add_argument("--monitor", type=int, default=0, help=mon_help)
    s.set_defaults(func=cmd_snip)

    best_help = ("con piu' template: agisci su quello col punteggio piu' alto "
                 "invece che sul primo dell'elenco")
    colore_help = ("cerca per COLORE invece che pixel per pixel: unico modo per "
                   "prendere un oggetto che ruota o si anima (usa --threshold 0.35)")
    zona_help = "cerca solo dentro questo rettangolo dello schermo"

    def comuni(p):
        p.add_argument("--colore", action="store_true", help=colore_help)
        p.add_argument("--zona", type=int, nargs=4, metavar=("X", "Y", "W", "H"),
                       help=zona_help)
        return p

    s = sub.add_parser("find", help="cerca uno o piu' template a schermo")
    s.add_argument("name", nargs="+", metavar="NOME")
    s.add_argument("--threshold", type=float, default=0.85)
    s.add_argument("--wait", type=float, default=0.0)
    s.add_argument("--best", action="store_true", help=best_help)
    s.add_argument("--monitor", type=int, default=0, help=mon_help)
    comuni(s)
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("click", help="trova e clicca (accetta piu' template)")
    s.add_argument("name", nargs="+", metavar="NOME")
    s.add_argument("--best", action="store_true", help=best_help)
    s.add_argument("--threshold", type=float, default=0.85)
    s.add_argument("--wait", type=float, default=0.0, help="secondi da aspettare finche' compare")
    s.add_argument("--double", action="store_true")
    s.add_argument("--right", action="store_true")
    s.add_argument("--monitor", type=int, default=0, help=mon_help)
    s.add_argument("--offset", type=int, nargs=2, default=[0, 0], metavar=("DX", "DY"),
                   help="clicca a DX,DY pixel dal centro del match "
                        "(es. --offset 0 -69 per colpire cio' che sta sopra l'etichetta)")
    s.add_argument("--press", metavar="TASTO",
                   help="dopo il click premi questo tasto (es. 1, f5, invio, ctrl+s)")
    s.add_argument("--press-delay", type=float, default=0.3, metavar="SEC",
                   help="pausa tra il click e il tasto (default 0.3s)")
    comuni(s)
    s.set_defaults(func=cmd_click)

    s = sub.add_parser("loop", help="cerca e clicca all'infinito, finche' non lo fermi")
    s.add_argument("name", nargs="+", metavar="NOME")
    s.add_argument("--best", action="store_true", help=best_help)
    s.add_argument("--threshold", type=float, default=0.85)
    s.add_argument("--interval", type=float, default=0.5, metavar="SEC",
                   help="pausa tra un controllo e l'altro quando non trova nulla (0.5s)")
    s.add_argument("--cooldown", type=float, default=1.0, metavar="SEC",
                   help="pausa dopo ogni click riuscito (1s)")
    s.add_argument("--offset", type=int, nargs=2, default=[0, 0], metavar=("DX", "DY"))
    s.add_argument("--press", metavar="TASTO", help="tasto da premere dopo il click")
    s.add_argument("--press-delay", type=float, default=0.3, metavar="SEC")
    s.add_argument("--double", action="store_true")
    s.add_argument("--max", type=int, default=0, metavar="N",
                   help="fermati dopo N click (0 = mai)")
    s.add_argument("--durata", type=float, default=0, metavar="SEC",
                   help="fermati dopo SEC secondi (0 = mai)")
    s.add_argument("--stato", type=float, default=30, metavar="SEC",
                   help="ogni quanto stampare che e' vivo (30s)")
    s.add_argument("--monitor", type=int, default=0, help=mon_help)
    comuni(s)
    s.set_defaults(func=cmd_loop)

    s = sub.add_parser("text", help="trova e clicca una scritta (OCR)")
    s.add_argument("query")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--monitor", type=int, default=0, help=mon_help)
    s.set_defaults(func=cmd_text)

    s = sub.add_parser("run", help="esegue uno script JSON di azioni")
    s.add_argument("script")
    s.add_argument("--repeat", type=int, default=1)
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("repl", help="modalita' interattiva")
    s.set_defaults(func=cmd_repl)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
