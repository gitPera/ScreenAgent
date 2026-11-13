"""Motore delle sequenze, piu' l'esecutore da riga di comando.

Questo file contiene la logica vera: la GUI (scheda Sequenza) e il lanciatore
autonomo usano LO STESSO codice, cosi' si comportano allo stesso modo.

    python motore.py                        esegue sequenze/sequenza.json
    python motore.py mia.json --ripeti 0    la ripete all'infinito
    python motore.py --lista                mostra i passi e basta

I file di sequenza stanno nella cartella sequenze/: basta il nome, senza percorso.

Durante l'esecuzione: F6 (o il tasto scelto con --tasto) ferma tutto, come pure
il mouse portato nell'angolo in alto a sinistra dello schermo.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

import actions
import agent
import clicker
import registratore

import percorsi as _perc
QUI = _perc.BASE

# file .json che NON sono sequenze (non vanno mai trattati come tali)
NON_SEQUENZE = ("catena.json", "registrazione.json")


def sistema_cartelle():
    """Crea le cartelle dei dati (sequenze, macro, templates) e ci porta dentro
    quello che le versioni precedenti lasciavano nella cartella principale:
    le sequenze in sequenze/, la registrazione dell'Autoclicker in macro/.
    Non sovrascrive mai: se la destinazione esiste gia', il file vecchio resta
    dov'e'. Ritorna l'elenco degli spostamenti come coppie (nome, cartella)."""
    for cartella in (_perc.SEQUENZE, _perc.MACRO, _perc.TEMPLATES):
        os.makedirs(cartella, exist_ok=True)
    spostati = []
    vecchia = os.path.join(QUI, "registrazione.json")
    if os.path.isfile(vecchia) and not os.path.exists(_perc.REGISTRAZIONE):
        try:
            os.replace(vecchia, _perc.REGISTRAZIONE)
            spostati.append(("registrazione.json", "macro"))
        except OSError:
            pass
    for f in sorted(os.listdir(QUI)):
        if not f.lower().endswith(".json") or f in NON_SEQUENZE:
            continue
        origine = os.path.join(QUI, f)
        destinazione = os.path.join(_perc.SEQUENZE, f)
        if not os.path.isfile(origine) or os.path.exists(destinazione):
            continue
        passi, _ = leggi(origine)
        if not passi and f != "sequenza.json":     # un .json qualsiasi: non e' mio
            continue
        try:
            os.replace(origine, destinazione)
            spostati.append((f, "sequenze"))
        except OSError:
            pass
    return spostati


def _crea_cartella_di(percorso):
    """Prima di scrivere un file: se la sua cartella non c'e' (cancellata,
    installazione nuova...) la crea, cosi' il salvataggio non fallisce mai."""
    cartella = os.path.dirname(os.path.abspath(percorso))
    os.makedirs(cartella, exist_ok=True)

OPZIONI_PREDEFINITE = {
    "ripeti": 1,                       # 0 = all'infinito
    "prima": 3.0,                      # secondi prima di partire
    "se_manca": "ferma la sequenza",   # oppure "salta il passo" / "continua ad aspettare"
    "zona": None,                      # (x, y, w, h) o None
    "monitor": 0,                      # 0 = tutti gli schermi
    "colore": False,                   # ricerca per colore invece che pixel
}

PASSO_PREDEFINITO = {
    "immagine": "", "azione": "click", "tasto": "",
    "attesa": 1.0, "timeout": 10.0, "soglia": 0.85, "ripeti_finche": False,
}

# Azioni che non cercano niente a schermo: agiscono e basta. Per tutte il campo
# "tasto" fa da valore: la combinazione, il testo da scrivere, le tacche.
AZIONI_SENZA_IMMAGINE = ("pausa", "tasto", "scrivi", "scroll_giu", "scroll_su",
                         "spegni")

# secondi di grazia predefiniti prima dello spegnimento: il tempo per accorgersi
# e annullare con "shutdown /a"
ATTESA_SPEGNIMENTO = 60


def _passo_pulito(p):
    return {
        "immagine": str(p.get("immagine", "")),
        "azione": str(p.get("azione", "click")),
        "tasto": str(p.get("tasto", "")),
        "attesa": float(p.get("attesa", 1.0)),
        "timeout": float(p.get("timeout", 10.0)),
        "soglia": float(p.get("soglia", 0.85)),
        "ripeti_finche": bool(p.get("ripeti_finche", False)),
        # solo per l'azione "condizione": le due sequenze-ramo da eseguire
        "allora": str(p.get("allora", "")),
        "altrimenti": str(p.get("altrimenti", "")),
        # solo per l'azione "trascina": l'immagine di arrivo
        "immagine2": str(p.get("immagine2", "")),
        # scostamento del click rispetto al centro dell'immagine (pixel)
        "dx": int(p.get("dx", 0)),
        "dy": int(p.get("dy", 0)),
    }


def leggi(percorso):
    """Ritorna (passi, opzioni).

    Accetta due formati: il nuovo {"passi": [...], "opzioni": {...}} e il
    vecchio, che era la semplice lista dei passi.
    """
    opzioni = dict(OPZIONI_PREDEFINITE)
    if not os.path.isfile(percorso):
        return [], opzioni
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
    except (ValueError, OSError):
        return [], opzioni

    if isinstance(dati, dict):
        grezzi = dati.get("passi", [])
        for chiave, valore in (dati.get("opzioni") or {}).items():
            if chiave in opzioni:
                opzioni[chiave] = valore
    else:
        grezzi = dati
    if opzioni["zona"]:
        opzioni["zona"] = tuple(opzioni["zona"])

    passi = []
    for p in grezzi if isinstance(grezzi, list) else []:
        try:
            passi.append(_passo_pulito(p))
        except (TypeError, ValueError, AttributeError):
            continue
    return passi, opzioni


def salva(percorso, passi, opzioni=None):
    dati = {"passi": passi, "opzioni": dict(OPZIONI_PREDEFINITE)}
    dati["opzioni"].update(opzioni or {})
    if dati["opzioni"]["zona"]:
        dati["opzioni"]["zona"] = list(dati["opzioni"]["zona"])
    _crea_cartella_di(percorso)
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)


OPZIONI_CATENA = {"ripeti": 1, "prima": 3.0, "continua": False}


def leggi_catena(percorso):
    """Una catena e' un elenco di file di sequenza da eseguire in ordine."""
    opzioni = dict(OPZIONI_CATENA)
    if not os.path.isfile(percorso):
        return [], opzioni
    try:
        with open(percorso, encoding="utf-8") as f:
            dati = json.load(f)
    except (ValueError, OSError):
        return [], opzioni
    for chiave, valore in (dati.get("opzioni") or {}).items():
        if chiave in opzioni:
            opzioni[chiave] = valore
    sequenze = [str(s) for s in dati.get("sequenze", []) if str(s).strip()]
    return sequenze, opzioni


def salva_catena(percorso, sequenze, opzioni=None):
    dati = {"sequenze": list(sequenze), "opzioni": dict(OPZIONI_CATENA)}
    dati["opzioni"].update(opzioni or {})
    _crea_cartella_di(percorso)
    with open(percorso, "w", encoding="utf-8") as f:
        json.dump(dati, f, indent=2, ensure_ascii=False)


def durata_leggibile(secondi):
    secondi = int(round(secondi))
    if secondi < 60:
        return "%d second%s" % (secondi, "o" if secondi == 1 else "i")
    minuti, resto = divmod(secondi, 60)
    testo = "%d minut%s" % (minuti, "o" if minuti == 1 else "i")
    if resto:
        testo += " e %d second%s" % (resto, "o" if resto == 1 else "i")
    return testo


def descrivi(p, numero=None):
    """Riga leggibile che descrive un passo."""
    testa = "%d. " % numero if numero else ""
    valore = p["tasto"].strip()
    if p["azione"] == "pausa":
        return "%spausa di %g s" % (testa, p["attesa"])
    if p["azione"] == "tasto":
        return "%spremi '%s'" % (testa, valore)
    if p["azione"] == "scrivi":
        return "%sscrivi \"%s\"" % (testa, valore)
    if p["azione"] in ("scroll_giu", "scroll_su"):
        return "%sscorri %s di %s tacche" % (
            testa, "in giu'" if p["azione"] == "scroll_giu" else "in su'",
            valore or "3")
    if p["azione"] == "spegni":
        return "%sSPEGNI IL PC fra %s secondi" % (testa,
                                                  valore or ATTESA_SPEGNIMENTO)
    if p["azione"] == "condizione":
        a = p.get("allora") or "(niente)"
        b = p.get("altrimenti") or "(niente)"
        return "%sse c'e' '%s': %s | altrimenti: %s" % (testa, p["immagine"], a, b)
    if p["azione"] == "trascina":
        return "%strascina '%s' su '%s'" % (testa, p["immagine"],
                                            p.get("immagine2") or "?")
    pezzi = ["%s'%s'" % (testa, p["immagine"]), {"click": "click",
                                                 "doppio": "doppio click",
                                                 "destro": "click destro",
                                                 "aspetta": "solo aspetta"}.get(
        p["azione"], p["azione"])]
    if p["ripeti_finche"]:
        pezzi.append("finche' c'e'")
    if p["tasto"]:
        pezzi.append("poi tasto '%s'" % p["tasto"])
    pezzi.append("attesa %g s" % p["attesa"])
    return ", ".join(pezzi)


class StopCatena(threading.Event):
    """Segnale di stop di UNA sequenza dentro una catena.

    Serve perche' una sequenza che si ferma da sola (un passo fallito) non deve
    fermare anche tutte le altre: alza la propria bandierina, mentre quella della
    catena resta abbassata. Chi esegue puo' distinguere i due casi.
    """

    def __init__(self, padre):
        threading.Event.__init__(self)
        self.padre = padre

    def is_set(self):
        return threading.Event.is_set(self) or self.padre.is_set()

    def fermata_da_sola(self):
        return threading.Event.is_set(self) and not self.padre.is_set()


def aspetta_con_conto(secondi, stop, log):
    """Attesa con conto alla rovescia: con attese lunghe devi poter vedere che
    il programma e' vivo e quanto manca."""
    fine = time.time() + secondi
    log("attendo %s prima di cominciare" % durata_leggibile(secondi))
    for tappa in (900, 600, 300, 240, 180, 120, 60, 30, 10):
        if tappa >= secondi:
            continue
        if not clicker.attesa_interrompibile(max(0.0, fine - tappa - time.time()),
                                             stop):
            return False
        log("... mancano %s" % durata_leggibile(tappa))
    return clicker.attesa_interrompibile(max(0.0, fine - time.time()), stop)


class Sequenza:
    """Esegue una lista di passi. Non sa nulla dell'interfaccia grafica."""

    LIMITE_RIPETIZIONI = 500     # se l'immagine non sparisce mai, non restare appeso

    def __init__(self, passi, opzioni=None, log=None, stop=None, su_passo=None,
                 su_click=None):
        self.passi = [dict(p) for p in passi]
        self.opzioni = dict(OPZIONI_PREDEFINITE)
        self.opzioni.update(opzioni or {})
        self.log = log or (lambda t: None)
        self.stop = stop or threading.Event()
        self.su_passo = su_passo or (lambda i: None)
        # chiamato con (x, y) subito prima di un click: la GUI ci disegna il mirino
        self.su_click = su_click or (lambda x, y: None)

    # ------------------------------------------------------------ ricerca
    def _cerca(self, p, timeout, per_sempre=False):
        """Ritorna (esito, risultato), esito in trovato / assente / errore."""
        scadenza = time.time() + timeout
        while not self.stop.is_set():
            try:
                risultati = agent.locate_many([p["immagine"]], p["soglia"],
                                              region=self.opzioni["zona"],
                                              monitor=self.opzioni["monitor"],
                                              colore=self.opzioni["colore"])
            except SystemExit as e:      # immagine cancellata nel frattempo
                self.log("[x] %s" % e)
                return "errore", None
            except Exception as e:
                self.log("[!] errore nella ricerca: %s" % e)
                return "errore", None
            if risultati:
                return "trovato", risultati[0]
            if not per_sempre and time.time() >= scadenza:
                return "assente", None
            clicker.attesa_interrompibile(0.3, self.stop)
        return "assente", None

    def _azione_semplice(self, n, p):
        """Tastiera, testo, rotella: niente da cercare a schermo."""
        azione = p["azione"]
        valore = p["tasto"].strip()
        if azione == "pausa":
            self.log("%d. pausa di %g s" % (n, p["attesa"]))
        elif azione == "tasto":
            if not valore:
                raise ValueError("nessun tasto indicato nel campo 'Tasto o testo'")
            actions.hotkey(*valore.split("+"))
            self.log("[ok] %d. premuto '%s'" % (n, valore))
        elif azione == "scrivi":
            if not valore:
                raise ValueError("niente da scrivere nel campo 'Tasto o testo'")
            actions.type_text(valore)
            self.log("[ok] %d. scritto \"%s\"" % (n, valore))
        elif azione == "spegni":
            try:
                secondi = max(0, int(float(valore))) if valore else ATTESA_SPEGNIMENTO
            except ValueError:
                secondi = ATTESA_SPEGNIMENTO
            # non si clicca il menu di Windows: si usa il comando di sistema
            subprocess.Popen(["shutdown", "/s", "/t", str(secondi)],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.log("[!] %d. SPEGNIMENTO programmato fra %s. Per annullare, "
                     "da un terminale:  shutdown /a"
                     % (n, durata_leggibile(secondi)))
        elif azione in ("scroll_giu", "scroll_su"):
            try:
                tacche = abs(int(float(valore))) if valore else 3
            except ValueError:
                tacche = 3
            actions.scroll(-tacche if azione == "scroll_giu" else tacche)
            self.log("[ok] %d. scorso %d tacche %s"
                     % (n, tacche,
                        "in giu'" if azione == "scroll_giu" else "in su'"))

    def _agisci(self, n, p, trovato, volta=None):
        nome, pos, punteggio = trovato
        conta = " (%d)" % volta if volta else ""
        if p["azione"] == "aspetta":
            self.log("[ok] %d. '%s' comparsa in (%d, %d)  match %.2f%s"
                     % (n, nome, pos[0], pos[1], punteggio, conta))
            return
        # scostamento rispetto al centro: +dx a destra, +dy in basso
        dx, dy = int(p.get("dx", 0)), int(p.get("dy", 0))
        pos = (pos[0] + dx, pos[1] + dy)
        self.su_click(pos[0], pos[1])         # la GUI evidenzia il punto
        if p["azione"] == "doppio":
            actions.double_click(*pos)
        elif p["azione"] == "destro":
            actions.right_click(*pos)
        else:
            actions.click(*pos)
        scost = " [scost. %+d,%+d]" % (dx, dy) if (dx or dy) else ""
        testo = "[ok] %d. '%s' cliccata in (%d, %d)%s  match %.2f%s" % (
            n, nome, pos[0], pos[1], scost, punteggio, conta)
        if p["tasto"]:
            time.sleep(0.3)
            actions.hotkey(*p["tasto"].split("+"))
            testo += " + tasto '%s'" % p["tasto"]
        self.log(testo)

    # ------------------------------------------------------------ condizione
    PROFONDITA_MASSIMA = 5     # limite ai rami dentro rami, contro i cicli infiniti

    def _ramo(self, nome_file, profondita):
        """Esegue una sequenza-ramo (un altro file .json) come sotto-routine."""
        if not nome_file:
            return
        if profondita >= self.PROFONDITA_MASSIMA:
            self.log("[!] troppi rami annidati (%d): mi fermo qui per sicurezza"
                     % profondita)
            return
        percorso = _perc.sequenza(nome_file)       # di norma dentro sequenze/
        passi, _ = leggi(percorso)
        if not passi:
            self.log("[x] ramo '%s': nessun passo (file mancante o vuoto)"
                     % os.path.basename(nome_file))
            return
        self.log("   -> eseguo '%s' (%d passi)"
                 % (os.path.basename(nome_file), len(passi)))
        self._esegui_passi(passi, profondita + 1, evidenzia=False)

    def _trascina(self, n, p):
        """Trova l'immagine di partenza e quella di arrivo e trascina dall'una
        all'altra (click tenuto premuto, movimento, rilascio)."""
        esito, sorgente = self._cerca(p, p["timeout"], per_sempre=False)
        if esito != "trovato":
            if not self.stop.is_set():
                self.log("[x] %d. '%s' (partenza) non trovata entro %g s"
                         % (n, p["immagine"], p["timeout"]))
            return False
        dest_nome = p.get("immagine2", "")
        if not dest_nome:
            self.log("[x] %d. manca l'immagine di arrivo" % n)
            return False
        p_dest = dict(p, immagine=dest_nome)
        esito2, arrivo = self._cerca(p_dest, p["timeout"], per_sempre=False)
        if esito2 != "trovato":
            if not self.stop.is_set():
                self.log("[x] %d. '%s' (arrivo) non trovata entro %g s"
                         % (n, dest_nome, p["timeout"]))
            return False
        na, (ax, ay), _ = sorgente
        nb, (bx, by), _ = arrivo
        self.log("[ok] %d. trascino '%s' (%d,%d) -> '%s' (%d,%d)"
                 % (n, na, ax, ay, nb, bx, by))
        registratore.trascina(ax, ay, bx, by, stop=self.stop)
        return True

    def _condizione(self, n, p, profondita):
        # cerca l'immagine entro il suo timeout, poi prende un ramo o l'altro
        esito, _ = self._cerca(p, p["timeout"], per_sempre=False)
        c_e = esito == "trovato"
        ramo = p.get("allora") if c_e else p.get("altrimenti")
        self.log("[i] %d. '%s' %s -> %s"
                 % (n, p["immagine"], "c'e'" if c_e else "non c'e'",
                    os.path.basename(ramo) if ramo else "(niente)"))
        self._ramo(ramo, profondita)

    # -------------------------------------------------------------- passo
    def passo(self, i, p, profondita=0):
        """Esegue un passo. Ritorna (riuscito, ho_gia_aspettato).

        Con "ripeti finche' c'e'" il passo si rifa' sulla stessa immagine finche'
        questa resta a schermo: e' il ciclo locale su quel punto della sequenza.
        """
        n = i + 1
        if p["azione"] == "condizione":
            self._condizione(n, p, profondita)
            return True, False
        if p["azione"] == "trascina":
            return self._trascina(n, p), False
        if p["azione"] in AZIONI_SENZA_IMMAGINE:
            try:
                self._azione_semplice(n, p)
            except Exception as e:
                self.log("[x] %d. %s" % (n, e))
                return False, False
            return True, False

        per_sempre = str(self.opzioni["se_manca"]).startswith("continua")
        esito, trovato = self._cerca(p, p["timeout"], per_sempre)
        if esito != "trovato":
            if self.stop.is_set():
                return False, False
            if esito == "assente":
                self.log("[x] %d. '%s' non e' comparsa entro %g s"
                         % (n, p["immagine"], p["timeout"]))
            return False, False

        if not p.get("ripeti_finche"):
            self._agisci(n, p, trovato)
            return True, False

        # per capire se e' sparita basta una ricerca breve, non il timeout pieno
        riaggancio = min(p["timeout"], 2.0)
        volte = 0
        while not self.stop.is_set():
            volte += 1
            self._agisci(n, p, trovato, volte)
            if volte >= self.LIMITE_RIPETIZIONI:
                self.log("[!] %d. '%s' e' ancora li' dopo %d ripetizioni: vado "
                         "avanti lo stesso" % (n, p["immagine"], volte))
                break
            if p["attesa"] > 0 and not clicker.attesa_interrompibile(p["attesa"],
                                                                     self.stop):
                break
            esito, trovato = self._cerca(p, riaggancio)
            if esito != "trovato":
                if esito == "assente":
                    self.log("%d. '%s' non c'e' piu' dopo %d volte: passo al "
                             "successivo" % (n, p["immagine"], volte))
                break
        return True, True       # l'attesa l'ho gia' fatta dentro il ciclo

    # ----------------------------------------------------------- esecuzione
    def _esegui_passi(self, passi, profondita=0, evidenzia=False):
        """Un passaggio su una lista di passi. Riusato sia per la sequenza vera
        sia per i rami di una condizione. Ritorna quanti passi sono riusciti."""
        ferma_se_manca = str(self.opzioni["se_manca"]).startswith("ferma")
        fatti = 0
        for i, p in enumerate(passi):
            if self.stop.is_set():
                break
            if evidenzia:
                self.su_passo(i)
            riuscito, gia_atteso = self.passo(i, p, profondita)
            if riuscito:
                fatti += 1
            elif self.stop.is_set():
                break                   # fermato a mano: non e' un passo fallito
            elif ferma_se_manca:
                self.log("[x] passo %d fallito: fermo la sequenza" % (i + 1))
                self.stop.set()
                break
            else:
                self.log("[!] passo %d saltato, tiro dritto" % (i + 1))
            if p["attesa"] > 0 and not gia_atteso and not self.stop.is_set():
                clicker.attesa_interrompibile(p["attesa"], self.stop)
        return fatti

    def _aspetta_inizio(self, secondi):
        return aspetta_con_conto(secondi, self.stop, self.log)

    def esegui(self):
        """Esegue tutta la sequenza. Ritorna (giri, passi_riusciti, durata)."""
        prima = max(float(self.opzioni["prima"]), 0)
        if prima > 0:
            if not self._aspetta_inizio(prima):
                self.log("--- fermata prima di iniziare ---")
                return 0, 0, 0.0

        ripeti = int(self.opzioni["ripeti"])
        self.log("--- sequenza avviata: %d passi, %s ---"
                 % (len(self.passi),
                    "%d giri" % ripeti if ripeti > 0 else "all'infinito"))

        giro = fatti = 0
        inizio = time.time()
        while not self.stop.is_set() and (ripeti <= 0 or giro < ripeti):
            giro += 1
            if ripeti != 1:
                self.log("--- giro %d ---" % giro)
            fatti += self._esegui_passi(self.passi, profondita=0, evidenzia=True)

        durata = time.time() - inizio
        self.log("--- finita: %d giri, %d passi riusciti, %dm %ds ---"
                 % (giro, fatti, durata // 60, durata % 60))
        return giro, fatti, durata


# ================================================================== catena
def esegui_catena(percorsi, log=None, stop=None, ripeti=1, prima=0.0,
                  continua_se_fallisce=False, su_sequenza=None, override=None):
    """Esegue piu' file di sequenza uno dopo l'altro.

    L'attesa iniziale la decide la catena: quella salvata dentro i singoli file
    viene ignorata, altrimenti si sommerebbero (una sequenza puo' averne da sola
    diversi minuti). Se una sequenza si ferma per un passo fallito, la catena prosegue o
    si interrompe a seconda di `continua_se_fallisce`.
    """
    log = log or (lambda t: None)
    stop = stop or threading.Event()
    su_sequenza = su_sequenza or (lambda i: None)

    if prima > 0 and not aspetta_con_conto(prima, stop, log):
        log("--- catena fermata prima di iniziare ---")
        return 0, 0

    log("--- catena avviata: %d sequenze, %s ---"
        % (len(percorsi), "%d giri" % ripeti if ripeti > 0 else "all'infinito"))
    inizio = time.time()
    giro = fatte = 0
    while not stop.is_set() and (ripeti <= 0 or giro < ripeti):
        giro += 1
        if ripeti != 1:
            log("--- giro %d della catena ---" % giro)
        for i, percorso in enumerate(percorsi):
            if stop.is_set():
                break
            su_sequenza(i)
            nome = os.path.basename(percorso)
            passi, opzioni = leggi(percorso)
            if not passi:
                log("[x] %s: nessun passo (file mancante o vuoto)" % nome)
                if not continua_se_fallisce:
                    stop.set()
                continue
            opzioni.update(override or {})
            opzioni["prima"] = 0          # l'attesa iniziale la fa la catena
            log("=== %d/%d  %s  (%d passi) ==="
                % (i + 1, len(percorsi), nome, len(passi)))
            locale = StopCatena(stop)
            Sequenza(passi, opzioni, log=log, stop=locale).esegui()
            if locale.fermata_da_sola():
                if continua_se_fallisce:
                    log("[!] %s si e' fermata, passo alla prossima" % nome)
                else:
                    log("[x] %s si e' fermata: fermo la catena" % nome)
                    stop.set()
            else:
                fatte += 1

    durata = time.time() - inizio
    log("--- catena finita: %d giri, %d sequenze completate, %dm %ds ---"
        % (giro, fatte, durata // 60, durata % 60))
    return giro, fatte


# ============================================================ riga di comando
def _sorveglia_tasto(vk, stop, chiuso, log):
    """Ferma tutto quando premi il tasto rapido o ESC, anche se la finestra
    attiva e' un'altra: ESC e' il freno d'emergenza e vale sempre."""
    tasti = [vk] if vk == clicker.VK_ESC else [vk, clicker.VK_ESC]
    prima = dict((t, False) for t in tasti)
    while not chiuso.is_set():
        for t in tasti:
            try:
                ora = clicker.premuto_o_scattato(t)
            except Exception:
                ora = False
            if ora and not prima[t] and not stop.is_set():
                log("[i] %s premuto: fermo tutto" % clicker.nome_tasto(t))
                stop.set()
            prima[t] = ora
        time.sleep(0.03)


def main():
    p = argparse.ArgumentParser(
        description="Esegue una sequenza salvata, senza aprire ScreenAgent.")
    p.add_argument("file", nargs="*",
                   help="uno o piu' file di sequenza: se ne indichi piu' d'uno "
                        "vengono eseguiti in ordine (default: sequenza.json)")
    p.add_argument("--continua", action="store_true",
                   help="in una catena: se una sequenza fallisce passa comunque "
                        "alla successiva invece di fermare tutto")
    p.add_argument("--lista", action="store_true",
                   help="mostra i passi e non esegue niente")
    p.add_argument("--ripeti", type=int, metavar="N",
                   help="quante volte ripeterla (0 = all'infinito)")
    p.add_argument("--prima", type=float, metavar="SEC",
                   help="secondi di attesa prima di partire")
    p.add_argument("--se-manca", dest="se_manca",
                   choices=["ferma", "salta", "aspetta"],
                   help="cosa fare se un'immagine non compare")
    p.add_argument("--zona", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    p.add_argument("--monitor", type=int, metavar="N")
    p.add_argument("--colore", action="store_true",
                   help="cerca per colore invece che pixel per pixel")
    p.add_argument("--tasto", type=lambda v: int(v, 0), default=0x75, metavar="VK",
                   help="codice del tasto che ferma tutto (default 0x75 = F6)")
    args = p.parse_args()

    import screen as scr
    scr.enable_dpi_awareness()

    for nome, cartella in sistema_cartelle():
        print("[i] %s spostato nella cartella %s" % (nome, cartella))
    # un nome semplice si cerca in sequenze/ (poi, per le installazioni
    # vecchie, nella cartella principale): cosi' i .bat non cambiano
    percorsi = [_perc.sequenza(f) for f in (args.file or ["sequenza.json"])]

    # quello che passi da riga di comando vince su quello salvato nei file
    override = {}
    if args.ripeti is not None and len(percorsi) == 1:
        override["ripeti"] = args.ripeti
    if args.prima is not None and len(percorsi) == 1:
        override["prima"] = args.prima
    if args.se_manca:
        override["se_manca"] = {"ferma": "ferma la sequenza",
                                "salta": "salta il passo",
                                "aspetta": "continua ad aspettare"}[args.se_manca]
    if args.zona:
        override["zona"] = tuple(args.zona)
    if args.monitor is not None:
        override["monitor"] = args.monitor
    if args.colore:
        override["colore"] = True

    tutte = []
    for percorso in percorsi:
        passi, opzioni = leggi(percorso)
        if not passi:
            sys.exit("[x] nessun passo da eseguire in %s\n"
                     "    Componi la sequenza in ScreenAgent e salvala." % percorso)
        opzioni.update(override)
        tutte.append((percorso, passi, opzioni))
        print("Sequenza: %s  (%d passi)"
              % (os.path.basename(percorso), len(passi)))
        for i, passo in enumerate(passi, 1):
            print("   %s" % descrivi(passo, i))
        print("Opzioni: %s giri, attesa iniziale %g s, se manca -> %s, zona %s, "
              "schermo %s, colore %s"
              % (opzioni["ripeti"] or "infiniti", opzioni["prima"],
                 opzioni["se_manca"], opzioni["zona"] or "tutta",
                 opzioni["monitor"] or "tutti", "si" if opzioni["colore"] else "no"))
    if args.lista:
        return

    print("\nPer fermare: %s, oppure ESC (freno d'emergenza), oppure il mouse "
          "nell'angolo in alto a sinistra.\n" % clicker.nome_tasto(args.tasto))

    stop = threading.Event()
    chiuso = threading.Event()
    threading.Thread(target=_sorveglia_tasto,
                     args=(args.tasto, stop, chiuso, print), daemon=True).start()

    def scrivi(testo):
        print("%s  %s" % (time.strftime("%H:%M:%S"), testo))

    try:
        if len(tutte) == 1:
            percorso, passi, opzioni = tutte[0]
            Sequenza(passi, opzioni, log=scrivi, stop=stop).esegui()
        else:
            prima = (args.prima if args.prima is not None
                     else float(tutte[0][2]["prima"]))
            esegui_catena([p for p, _, _ in tutte], log=scrivi, stop=stop,
                          ripeti=args.ripeti if args.ripeti is not None else 1,
                          prima=prima, continua_se_fallisce=args.continua,
                          override=override)
    except KeyboardInterrupt:
        stop.set()
        scrivi("[i] interrotto da tastiera")
    except actions.pyautogui.FailSafeException:
        stop.set()
        scrivi("[x] FAILSAFE: mouse nell'angolo, tutto fermato")
    finally:
        chiuso.set()


if __name__ == "__main__":
    main()
