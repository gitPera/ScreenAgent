"""Interfaccia grafica di ScreenAgent.

    python gui.py       (oppure doppio click su ScreenAgent.bat)

Scegli una o piu' immagini dalla lista (Ctrl/Shift per la selezione multipla),
imposta l'azione e premi un pulsante. Riusa gli stessi moduli della riga di
comando: agent, vision, actions, screen.
"""
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import cv2
from PIL import Image, ImageDraw, ImageTk

import actions
import agent
import clicker
import screen as scr
import vision

QUI = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(QUI, "templates")

# ---------------------------------------------------------------- palette
BG = "#0f1216"        # sfondo finestra
CARD = "#171b21"      # sfondo dei riquadri
CARD_ALT = "#1d222a"  # campi, lista
BORDO = "#272d37"
TESTO = "#e7eaef"
SPENTO = "#8b93a1"    # testo secondario
ACCENTO = "#4f8cff"
ACCENTO_HOVER = "#6a9cff"
OK = "#3ddc84"
ALLARME = "#ff5c5c"
AVVISO = "#ffc861"
PULS = "#242a34"
PULS_HOVER = "#2f3743"

F = "Segoe UI"
F_MONO = "Consolas"


class App:
    def __init__(self, root):
        self.root = root
        root.title("ScreenAgent")
        root.geometry("1120x730")
        root.minsize(1100, 660)
        root.configure(bg=BG)

        self.coda = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.anteprima_tk = None
        self.template_corrente = None

        # autoclicker
        self.chiuso = threading.Event()
        self.ac_stop = threading.Event()
        self.ac_worker = None
        self.ac_registrando = False
        self.vk_hotkey = 0x75                     # F6, come OP Auto Clicker
        self.nome_hotkey = "F6"
        self.file_registrazione = os.path.join(QUI, "registrazione.json")
        self.registrazione = clicker.carica(self.file_registrazione)

        self._stile()
        self._costruisci()
        self._aggiorna_lista()
        self.root.after(100, self._svuota_coda)
        self.root.protocol("WM_DELETE_WINDOW", self._chiudi)
        threading.Thread(target=self._ascolta_tasto_rapido, daemon=True).start()

    # ---------------------------------------------------------------- stile
    def _stile(self):
        s = ttk.Style()
        s.theme_use("clam")   # l'unico tema che si lascia ricolorare davvero

        s.configure(".", background=CARD, foreground=TESTO,
                    fieldbackground=CARD_ALT, font=(F, 9), borderwidth=0)
        s.configure("Sfondo.TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD)
        s.configure("TLabel", background=CARD, foreground=TESTO)
        s.configure("Sfondo.TLabel", background=BG, foreground=TESTO)
        s.configure("Titolo.TLabel", background=BG, foreground=TESTO,
                    font=(F + " Semibold", 17))
        s.configure("Sottotitolo.TLabel", background=BG, foreground=SPENTO, font=(F, 9))
        s.configure("Intestazione.TLabel", background=CARD, foreground=SPENTO,
                    font=(F + " Semibold", 8))
        s.configure("Spento.TLabel", background=CARD, foreground=SPENTO, font=(F, 8))
        s.configure("Dato.TLabel", background=CARD, foreground=TESTO, font=(F_MONO, 8))

        s.configure("TButton", background=PULS, foreground=TESTO, borderwidth=0,
                    focusthickness=0, padding=(14, 9), font=(F, 9), relief="flat",
                    anchor="center")
        s.map("TButton",
              background=[("disabled", "#1b2028"), ("active", PULS_HOVER)],
              foreground=[("disabled", "#555c68")])

        s.configure("Piccolo.TButton", padding=(8, 6), font=(F, 8))
        s.map("Piccolo.TButton",
              background=[("disabled", "#1b2028"), ("active", PULS_HOVER)],
              foreground=[("disabled", "#555c68")])

        s.configure("Accento.TButton", background=ACCENTO, foreground="#08101f",
                    font=(F + " Semibold", 9))
        s.map("Accento.TButton",
              background=[("disabled", "#22303f"), ("active", ACCENTO_HOVER)],
              foreground=[("disabled", "#5a6470")])

        s.configure("Pericolo.TButton", background="#3a1f24", foreground=ALLARME,
                    font=(F + " Semibold", 9))
        s.map("Pericolo.TButton",
              background=[("disabled", "#1b2028"), ("active", "#4d262c")],
              foreground=[("disabled", "#555c68")])

        # I radio in stile "segmento": pulsanti affiancati, uno solo acceso.
        # Molto piu' leggibili degli indicatori tondi, che clam disegna male.
        s.configure("Segmento.Toolbutton", background=CARD_ALT, foreground=SPENTO,
                    borderwidth=0, padding=(14, 8), font=(F, 9), relief="flat",
                    anchor="center")
        s.map("Segmento.Toolbutton",
              background=[("selected", ACCENTO), ("active", PULS_HOVER)],
              foreground=[("selected", "#08101f")])

        s.configure("TCheckbutton", background=CARD, foreground=SPENTO, font=(F, 8),
                    focuscolor=CARD, padding=(0, 3),
                    indicatorbackground=CARD_ALT, indicatorforeground=ACCENTO,
                    indicatorcolor=CARD_ALT, bordercolor=BORDO, indicatormargin=4)
        s.map("TCheckbutton",
              background=[("active", CARD)],
              foreground=[("selected", TESTO)],
              indicatorcolor=[("selected", ACCENTO), ("pressed", ACCENTO)],
              indicatorbackground=[("selected", ACCENTO), ("active", CARD_ALT)])

        s.configure("TEntry", fieldbackground=CARD_ALT, foreground=TESTO,
                    bordercolor=BORDO, lightcolor=BORDO, darkcolor=BORDO,
                    insertcolor=TESTO, padding=5)
        s.map("TEntry", bordercolor=[("focus", ACCENTO)])

        s.configure("TCombobox", fieldbackground=CARD_ALT, background=CARD_ALT,
                    foreground=TESTO, arrowcolor=SPENTO, bordercolor=BORDO,
                    lightcolor=BORDO, darkcolor=BORDO, padding=4)
        s.map("TCombobox", fieldbackground=[("readonly", CARD_ALT)],
              bordercolor=[("focus", ACCENTO)])
        self.root.option_add("*TCombobox*Listbox.background", CARD_ALT)
        self.root.option_add("*TCombobox*Listbox.foreground", TESTO)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENTO)
        self.root.option_add("*TCombobox*Listbox.font", (F, 9))

        for nome_sb in ("TScrollbar", "Vertical.TScrollbar"):
            s.configure(nome_sb, background=PULS, troughcolor=CARD_ALT,
                        bordercolor=CARD_ALT, darkcolor=PULS, lightcolor=PULS,
                        arrowcolor=SPENTO, arrowsize=11, gripcount=0, borderwidth=0)
            s.map(nome_sb, background=[("active", PULS_HOVER)],
                  arrowcolor=[("active", TESTO)])

        s.configure("Sep.TFrame", background=BORDO)

        # clam disegna cornici chiare: vanno spente una per una, altrimenti
        # attorno alle schede resta un contorno bianco
        s.configure("TNotebook", background=BG, borderwidth=0, bordercolor=BG,
                    lightcolor=BG, darkcolor=BG, tabmargins=(0, 4, 0, 0))
        s.configure("TNotebook.Tab", background=BG, foreground=SPENTO,
                    padding=(24, 10), borderwidth=0, bordercolor=BG, lightcolor=BG,
                    darkcolor=BG, focuscolor=BG, font=(F, 9))
        s.map("TNotebook.Tab",
              background=[("selected", CARD), ("active", CARD_ALT)],
              foreground=[("selected", ACCENTO), ("active", TESTO)],
              lightcolor=[("selected", CARD)], darkcolor=[("selected", CARD)],
              bordercolor=[("selected", CARD)],
              expand=[("selected", (0, 0, 0, 0))])

    def _segmenti(self, parent, var, opzioni, **pack):
        """Gruppo di scelte affiancate, stile interruttore a segmenti."""
        guscio = tk.Frame(parent, bg=CARD_ALT, highlightthickness=1,
                          highlightbackground=BORDO)
        guscio.pack(**pack)
        for testo, valore in opzioni:
            ttk.Radiobutton(guscio, text=testo, value=valore, variable=var,
                            style="Segmento.Toolbutton", cursor="hand2").pack(
                side="left", expand=True, fill="x", padx=1, pady=1)
        return guscio

    def _card(self, parent, titolo, **pack):
        """Riquadro con bordo sottile e titolino in alto: l'unita' visiva base."""
        guscio = tk.Frame(parent, bg=CARD, highlightthickness=1,
                          highlightbackground=BORDO, highlightcolor=BORDO)
        guscio.pack(**pack)
        if titolo:
            ttk.Label(guscio, text=titolo.upper(), style="Intestazione.TLabel").pack(
                anchor="w", padx=12, pady=(9, 0))
        dentro = ttk.Frame(guscio, style="Card.TFrame")
        dentro.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        return dentro

    # ---------------------------------------------------------- interfaccia
    def _costruisci(self):
        testata = ttk.Frame(self.root, style="Sfondo.TFrame")
        testata.pack(fill="x", padx=16, pady=(14, 10))
        ttk.Label(testata, text="ScreenAgent", style="Titolo.TLabel").pack(side="left")
        ttk.Label(testata, text="   guarda lo schermo, riconosce, clicca",
                  style="Sottotitolo.TLabel").pack(side="left", pady=(7, 0))

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=16)
        tab_ric = ttk.Frame(self.tabs, style="Sfondo.TFrame")
        self.tabs.add(tab_ric, text="Riconoscimento")
        tab_ac = ttk.Frame(self.tabs, style="Sfondo.TFrame")
        self.tabs.add(tab_ac, text="Autoclicker")

        corpo = ttk.Frame(tab_ric, style="Sfondo.TFrame")
        corpo.pack(fill="both", expand=True, pady=(10, 0))

        # ---------------- colonna sinistra: le immagini
        sx = ttk.Frame(corpo, style="Sfondo.TFrame")
        sx.pack(side="left", fill="y")
        lista_box = self._card(sx, "immagini", fill="both", expand=True)

        cornice_lista = tk.Frame(lista_box, bg=CARD_ALT, highlightthickness=1,
                                 highlightbackground=BORDO)
        cornice_lista.pack(fill="both", expand=True)
        self.lista = tk.Listbox(cornice_lista, width=22, height=15,
                                exportselection=False, selectmode="extended",
                                bg=CARD_ALT, fg=TESTO, font=(F, 10),
                                selectbackground=ACCENTO, selectforeground="#08101f",
                                highlightthickness=0, borderwidth=0, activestyle="none")
        self.lista.pack(fill="both", expand=True, padx=2, pady=2)
        self.lista.bind("<<ListboxSelect>>", self._seleziona)

        ttk.Label(lista_box, text="Ctrl o Shift per sceglierne piu' di una",
                  style="Spento.TLabel").pack(anchor="w", pady=(6, 6))

        riga_b = ttk.Frame(lista_box, style="Card.TFrame")
        riga_b.pack(fill="x")
        ttk.Button(riga_b, text="Tutte", style="Piccolo.TButton",
                   command=self._seleziona_tutti).pack(side="left", expand=True,
                                                       fill="x")
        ttk.Button(riga_b, text="Aggiorna", style="Piccolo.TButton",
                   command=self._aggiorna_lista).pack(side="left", expand=True,
                                                      fill="x", padx=(6, 0))
        riga_c = ttk.Frame(lista_box, style="Card.TFrame")
        riga_c.pack(fill="x", pady=(6, 0))
        ttk.Button(riga_c, text="+ Cattura", style="Piccolo.TButton",
                   command=self._nuovo_da_schermo).pack(side="left", expand=True,
                                                        fill="x")
        ttk.Button(riga_c, text="+ Appunti", style="Piccolo.TButton",
                   command=self._nuovo_da_appunti).pack(side="left", expand=True,
                                                        fill="x", padx=(6, 0))

        # ---------------- colonna destra
        dx = ttk.Frame(corpo, style="Sfondo.TFrame")
        dx.pack(side="left", fill="both", expand=True, padx=(14, 0))

        alto = ttk.Frame(dx, style="Sfondo.TFrame")
        alto.pack(fill="x")

        # anteprima
        ant = self._card(alto, "anteprima", side="left", fill="y")
        self.cornice_ant = tk.Frame(ant, width=252, height=176, bg=CARD_ALT,
                                    highlightthickness=1, highlightbackground=BORDO)
        self.cornice_ant.pack_propagate(False)
        self.cornice_ant.pack()
        self.anteprima = tk.Label(self.cornice_ant, bg=CARD_ALT, borderwidth=0)
        self.anteprima.pack(expand=True)
        self.info = ttk.Label(ant, text="nessuna immagine selezionata",
                              style="Dato.TLabel", justify="left", wraplength=250)
        self.info.pack(anchor="w", pady=(8, 0))

        # azione
        az = self._card(alto, "azione", side="left", fill="both", expand=True,
                        padx=(14, 0))

        # controllo a segmenti: le quattro azioni affiancate
        self.azione = tk.StringVar(value="click")
        self._segmenti(az, self.azione,
                       (("Solo cerca", "cerca"), ("Click singolo", "click"),
                        ("Doppio click", "doppio"), ("Click destro", "destro")),
                       fill="x", pady=(0, 14))

        col_campi = ttk.Frame(az, style="Card.TFrame")
        col_campi.pack(fill="x")

        self.v_press = tk.StringVar(value="")
        self.v_dx = tk.StringVar(value="0")
        self.v_dy = tk.StringVar(value="0")
        self.v_soglia = tk.StringVar(value="0.85")
        self.v_intervallo = tk.StringVar(value="0.3")
        self.v_cooldown = tk.StringVar(value="2.0")
        self.v_attesa = tk.StringVar(value="0")
        self.v_max = tk.StringVar(value="0")

        for c in range(4):
            col_campi.columnconfigure(c, weight=1, uniform="campi")

        def campo(r, c, etichetta, var, largh=7):
            ttk.Label(col_campi, text=etichetta, style="Spento.TLabel").grid(
                row=r * 2, column=c, sticky="w", padx=(0, 14))
            ttk.Entry(col_campi, textvariable=var, width=largh, font=(F_MONO, 9)).grid(
                row=r * 2 + 1, column=c, sticky="we", padx=(0, 14), pady=(0, 10))

        campo(0, 0, "Tasto dopo click", self.v_press)
        campo(0, 1, "Soglia", self.v_soglia)
        campo(0, 2, "Scostam. X", self.v_dx)
        campo(0, 3, "Scostam. Y", self.v_dy)
        campo(1, 0, "Intervallo (s)", self.v_intervallo)
        campo(1, 1, "Cooldown (s)", self.v_cooldown)
        campo(1, 2, "Attesa prima", self.v_attesa)
        campo(1, 3, "Max click", self.v_max)

        ttk.Label(col_campi, text="Schermo", style="Spento.TLabel").grid(
            row=4, column=0, sticky="w")
        self.v_monitor = tk.StringVar()
        self.combo_monitor = ttk.Combobox(col_campi, textvariable=self.v_monitor,
                                          state="readonly", font=(F, 9))
        self.combo_monitor.grid(row=5, column=0, columnspan=4, sticky="we",
                                padx=(0, 14))
        self._popola_monitor()

        self.v_best = tk.BooleanVar(value=False)
        ttk.Checkbutton(az, variable=self.v_best,
                        text="Con piu' immagini: agisci su quella col punteggio piu' "
                             "alto  (altrimenti conta l'ordine della lista)").pack(
            anchor="w", pady=(10, 0))
        self.v_riduci = tk.BooleanVar(value=True)
        ttk.Checkbutton(az, variable=self.v_riduci,
                        text="Riduci a icona questa finestra durante l'azione "
                             "(consigliato)").pack(anchor="w")
        self.v_colore = tk.BooleanVar(value=False)
        ttk.Checkbutton(az, variable=self.v_colore, command=self._cambia_modo,
                        text="Cerca per COLORE invece che pixel per pixel  (per "
                             "oggetti che ruotano o si animano)").pack(anchor="w")

        riga_z = ttk.Frame(az, style="Card.TFrame")
        riga_z.pack(fill="x", pady=(8, 0))
        ttk.Button(riga_z, text="Scegli zona", style="Piccolo.TButton",
                   cursor="hand2", command=self._scegli_zona).pack(side="left")
        ttk.Button(riga_z, text="Tutto lo schermo", style="Piccolo.TButton",
                   cursor="hand2", command=self._azzera_zona).pack(side="left",
                                                                   padx=(6, 10))
        self.zona = None
        self.et_zona = ttk.Label(riga_z, text="zona: tutto lo schermo",
                                 style="Spento.TLabel")
        self.et_zona.pack(side="left")

        # ---------------- barra dei pulsanti
        barra = ttk.Frame(dx, style="Sfondo.TFrame")
        barra.pack(fill="x", pady=12)
        self.b_cerca = ttk.Button(barra, text="Cerca", command=self._cerca)
        self.b_cerca.pack(side="left")
        self.b_una = ttk.Button(barra, text="Esegui una volta", command=self._una_volta)
        self.b_una.pack(side="left", padx=8)
        self.b_loop = ttk.Button(barra, text="▶  Avvia ciclo",
                                 style="Accento.TButton", command=self._loop)
        self.b_loop.pack(side="left")
        self.b_stop = ttk.Button(barra, text="■  Ferma", style="Pericolo.TButton",
                                 state="disabled", command=self._ferma)
        self.b_stop.pack(side="left", padx=8)
        self.b_diag = ttk.Button(barra, text="Diagnosi", command=self._diagnosi)
        self.b_diag.pack(side="right")
        for b in (self.b_cerca, self.b_una, self.b_loop, self.b_stop, self.b_diag):
            b.configure(cursor="hand2")

        # ---------------- registro
        reg = self._card(dx, "registro", fill="both", expand=True, pady=(0, 14))
        cornice_log = tk.Frame(reg, bg=CARD_ALT, highlightthickness=1,
                               highlightbackground=BORDO)
        cornice_log.pack(fill="both", expand=True)
        self.log = tk.Text(cornice_log, height=9, wrap="word", state="disabled",
                           bg=CARD_ALT, fg=TESTO, font=(F_MONO, 9), borderwidth=0,
                           highlightthickness=0, padx=10, pady=8,
                           insertbackground=TESTO, spacing1=1, spacing3=2)
        sb = ttk.Scrollbar(cornice_log, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("ora", foreground="#5d6673")
        self.log.tag_configure("ok", foreground=OK)
        self.log.tag_configure("err", foreground=ALLARME)
        self.log.tag_configure("warn", foreground=AVVISO)
        self.log.tag_configure("titolo", foreground=ACCENTO)
        self.log.tag_configure("normale", foreground=TESTO)

        # ---------------- seconda scheda
        self._tab_autoclicker(tab_ac)

        # ---------------- barra di stato
        piede = tk.Frame(self.root, bg=CARD, highlightthickness=1,
                         highlightbackground=BORDO)
        piede.pack(fill="x", side="bottom")
        self.spia = tk.Label(piede, text="●", bg=CARD, fg=SPENTO, font=(F, 11))
        self.spia.pack(side="left", padx=(14, 6), pady=5)
        self.stato = tk.Label(piede, text="pronto", bg=CARD, fg=SPENTO, font=(F, 9))
        self.stato.pack(side="left")
        tk.Label(piede, text="failsafe: mouse nell'angolo in alto a sinistra = stop",
                 bg=CARD, fg="#5d6673", font=(F, 8)).pack(side="right", padx=14)

    def _popola_monitor(self):
        self.monitor_valori = [(0, "Tutti gli schermi")]
        try:
            for i, m in enumerate(scr.list_monitors()):
                if i == 0:
                    continue
                etichetta = "primario" if m.get("is_primary") else "secondario"
                self.monitor_valori.append(
                    (i, "%d - %s - %dx%d" % (i, etichetta, m["width"], m["height"])))
        except Exception as e:
            self._scrivi("[!] non riesco a elencare gli schermi: %s" % e)
        self.combo_monitor["values"] = [t for _, t in self.monitor_valori]
        self.combo_monitor.current(0)

    # ------------------------------------------------------------ template
    def _seleziona_tutti(self):
        self.lista.selection_set(0, tk.END)
        self._seleziona()

    def _nomi(self):
        """I template selezionati, nell'ordine in cui compaiono nella lista.
        Nella lista i nomi sono indentati per respiro: qui vanno ripuliti."""
        return [self.lista.get(i).strip() for i in self.lista.curselection()]

    def _aggiorna_lista(self):
        selezionati = self._nomi() or ([self.template_corrente]
                                       if self.template_corrente else [])
        self.lista.delete(0, tk.END)
        if not os.path.isdir(TPL_DIR):
            os.makedirs(TPL_DIR, exist_ok=True)
        nomi = sorted(f[:-4] for f in os.listdir(TPL_DIR)
                      if f.lower().endswith(".png") and not f.startswith("_"))
        for n in nomi:
            self.lista.insert(tk.END, "  " + n)
        # la lista mostra i nomi indentati per respiro: li ripulisco in _nomi()
        ripristinati = [nomi.index(n) for n in selezionati if n in nomi]
        for i in ripristinati:
            self.lista.selection_set(i)
        if ripristinati:
            self.lista.see(ripristinati[0])
        elif nomi:
            self.lista.selection_set(0)
        self._seleziona()

    def _scacchiera(self, w, h, cella=9):
        img = Image.new("RGB", (w, h), (41, 46, 55))
        d = ImageDraw.Draw(img)
        for y in range(0, h, cella):
            for x in range(0, w, cella):
                if (x // cella + y // cella) % 2:
                    d.rectangle([x, y, x + cella - 1, y + cella - 1], fill=(34, 39, 47))
        return img

    def _seleziona(self, _evento=None):
        nomi = self._nomi()
        if not nomi:
            self.template_corrente = None
            self.anteprima.configure(image="")
            self.info.configure(text="nessuna immagine selezionata", foreground=SPENTO)
            return
        nome = nomi[0]          # l'anteprima mostra la prima dei selezionati
        self.template_corrente = nome
        p = os.path.join(TPL_DIR, nome + ".png")
        try:
            raw = cv2.imread(p, cv2.IMREAD_UNCHANGED)
            h, w = raw.shape[:2]
            canali = 1 if raw.ndim == 2 else raw.shape[2]
            trasparenti = int((raw[:, :, 3] < 255).sum()) if canali == 4 else 0
            contrasto = vision.contrast(raw)

            img = Image.open(p).convert("RGBA")
            k = min(240.0 / w, 164.0 / h)
            k = min(k, 4.0) if k > 1 else k
            if k != 1:
                filtro = Image.NEAREST if k > 1 else Image.LANCZOS
                img = img.resize((max(int(w * k), 1), max(int(h * k), 1)), filtro)
            fondo = self._scacchiera(img.width, img.height)  # trasparenza visibile
            fondo.paste(img, (0, 0), img)
            self.anteprima_tk = ImageTk.PhotoImage(fondo)
            self.anteprima.configure(image=self.anteprima_tk)

            righe = ["%s   %dx%d px   contrasto %.1f" % (nome, w, h, contrasto)]
            colore = SPENTO
            if len(nomi) > 1:
                righe.append("▸ %d selezionate: %s" % (len(nomi), ", ".join(nomi)))
                colore = ACCENTO
            if trasparenti:
                righe.append("maschera attiva, %d px ignorati" % trasparenti)
            if contrasto < 6:
                righe.append("! quasi tutta di un colore: la trovera' ovunque")
                colore = ALLARME
            if w > 400 or h > 400:
                righe.append("! grande: un ritaglio piu' stretto e' piu' affidabile")
            self.info.configure(text="\n".join(righe), foreground=colore)
        except Exception as e:
            self.info.configure(text="anteprima non disponibile: %s" % e,
                                foreground=ALLARME)

    # ------------------------------------------------------------ utilita'
    # Tkinter non e' thread-safe: il worker NON tocca widget ne' variabili Tk,
    # manda solo messaggi in coda che il thread principale consuma qui.
    def _scrivi(self, testo):
        self.coda.put(("log", testo))

    def _inserisci_log(self, widget, testo):
        if testo.startswith("---"):
            tag = "titolo"
        elif testo.startswith("[x]"):
            tag = "err"
        elif testo.startswith("[!]"):
            tag = "warn"
        elif testo.startswith("[ok]") or "cliccato" in testo or "trovato in" in testo:
            tag = "ok"
        else:
            tag = "normale"
        widget.configure(state="normal")
        widget.insert(tk.END, time.strftime("%H:%M:%S") + "  ", "ora")
        widget.insert(tk.END, testo + "\n", tag)
        widget.see(tk.END)
        widget.configure(state="disabled")

    def _svuota_coda(self):
        try:
            while True:
                tipo, dato = self.coda.get_nowait()
                if tipo == "log":
                    self._inserisci_log(self.log, dato)
                elif tipo == "aclog":
                    self._inserisci_log(self.ac_log, dato)
                elif tipo == "fine":
                    self._fine()
                elif tipo == "acfine":
                    self._ac_fine()
                elif tipo == "acstato":
                    self.stato.configure(text=dato, fg=TESTO)
                elif tipo == "acpunto":
                    self.ac_x.set(str(dato[0]))
                    self.ac_y.set(str(dato[1]))
                    self.ac_posizione.set("fisso")
                elif tipo == "hotkey":
                    self._tasto_rapido_premuto()
                elif tipo == "zona":
                    self.zona = dato
                    self.et_zona.configure(text="zona: %dx%d da (%d, %d)"
                                                % (dato[2], dato[3], dato[0], dato[1]))
                    self._inserisci_log(self.log, "[ok] zona impostata: %s" % (dato,))
                elif tipo == "aggiorna":
                    self._aggiorna_lista()
        except queue.Empty:
            pass
        self.root.after(100, self._svuota_coda)

    def _config(self):
        """Legge TUTTI i campi qui, nel thread principale, e li passa al worker."""
        return {
            "nomi": self._nomi(),
            "best": bool(self.v_best.get()),
            "colore": bool(self.v_colore.get()),
            "zona": self.zona,
            "soglia": self._numero(self.v_soglia, 0.85),
            "monitor": self._monitor(),
            "dx": self._numero(self.v_dx, 0, intero=True),
            "dy": self._numero(self.v_dy, 0, intero=True),
            "azione": self.azione.get(),
            "tasto": self.v_press.get().strip(),
            "intervallo": self._numero(self.v_intervallo, 0.3),
            "cooldown": self._numero(self.v_cooldown, 2.0),
            "massimo": self._numero(self.v_max, 0, intero=True),
            "attesa": max(self._numero(self.v_attesa, 0), 0),
        }

    def _cambia_modo(self):
        """La soglia ha significati diversi nei due modi: cambio il valore tipico
        se l'utente non l'ha personalizzato."""
        colore = self.v_colore.get()
        attuale = self.v_soglia.get().strip()
        if colore and attuale in ("0.85", "0,85"):
            self.v_soglia.set("0.35")
        elif not colore and attuale in ("0.35", "0,35"):
            self.v_soglia.set("0.85")
        self._scrivi("modo: %s" % ("ricerca per colore (la soglia e' somiglianza di "
                                   "dimensione)" if colore
                                   else "confronto pixel per pixel"))

    def _azzera_zona(self):
        self.zona = None
        self.et_zona.configure(text="zona: tutto lo schermo")

    def _scegli_zona(self):
        if self.worker and self.worker.is_alive():
            return

        def lavoro():
            self._scrivi("scegli la zona: trascina il rettangolo e premi INVIO")
            p = subprocess.Popen([sys.executable, os.path.join(QUI, "zona.py")],
                                 cwd=QUI, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, universal_newlines=True)
            for riga in p.stdout:
                riga = riga.strip()
                if riga.startswith("ZONA "):
                    self.coda.put(("zona", tuple(int(v) for v in riga.split()[1:])))
                elif riga:
                    self._scrivi("  " + riga)
            p.wait()
        self._avvia_senza_template(lavoro, "scelgo la zona...")

    def _numero(self, var, predefinito, intero=False):
        try:
            return int(float(var.get())) if intero else float(var.get())
        except (ValueError, AttributeError):
            return predefinito

    def _monitor(self):
        i = self.combo_monitor.current()
        return self.monitor_valori[max(i, 0)][0]

    def _avvia(self, funzione, nome_stato):
        if not self._nomi():
            messagebox.showwarning("ScreenAgent",
                                   "Seleziona prima almeno un'immagine.")
            return
        self._avvia_senza_template(funzione, nome_stato)

    def _avvia_senza_template(self, funzione, nome_stato):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("ScreenAgent", "C'e' gia' un'azione in corso.")
            return
        self.stop_event.clear()
        self._pulsanti(attivo=False)
        self.stato.configure(text=nome_stato, fg=TESTO)
        self.spia.configure(fg=ACCENTO)
        if self.v_riduci.get():
            self.root.iconify()
        self.worker = threading.Thread(target=self._esegui, args=(funzione,), daemon=True)
        self.worker.start()

    def _esegui(self, funzione):
        try:
            funzione()
        except SystemExit as e:            # load_template chiama sys.exit
            self._scrivi("[x] %s" % e)
        except actions.pyautogui.FailSafeException:
            self._scrivi("[x] FAILSAFE: mouse nell'angolo, tutto fermato")
        except Exception as e:
            self._scrivi("[x] errore: %s" % e)
        finally:
            self.coda.put(("fine", None))

    def _fine(self):
        self._pulsanti(attivo=True)
        self.stato.configure(text="pronto", fg=SPENTO)
        self.spia.configure(fg=SPENTO)
        self.root.deiconify()
        self.root.lift()

    def _pulsanti(self, attivo):
        stato = "normal" if attivo else "disabled"
        for b in (self.b_cerca, self.b_una, self.b_loop, self.b_diag):
            b.configure(state=stato)
        self.b_stop.configure(state="disabled" if attivo else "normal")

    def _ferma(self):
        self.stop_event.set()
        self.stato.configure(text="mi fermo...", fg=AVVISO)
        self.spia.configure(fg=AVVISO)
        self._scrivi("[i] richiesta di stop...")

    def _attendi_iniziale(self, attesa):
        if attesa > 0:
            self._scrivi("attendo %g s prima di iniziare..." % attesa)
            fine = time.time() + attesa
            while time.time() < fine and not self.stop_event.is_set():
                time.sleep(0.1)

    def _fai_azione(self, cfg, nome, pos, score, contatore=None):
        pos = (pos[0] + cfg["dx"], pos[1] + cfg["dy"])
        azione = cfg["azione"]
        etichetta = "#%d '%s' " % (contatore, nome) if contatore else "'%s' " % nome
        if azione == "cerca":
            self._scrivi("%strovato in (%d, %d) match %.2f (nessun click)"
                         % (etichetta, pos[0], pos[1], score))
            return
        if azione == "doppio":
            actions.double_click(*pos)
        elif azione == "destro":
            actions.right_click(*pos)
        else:
            actions.click(*pos)
        testo = "%scliccato in (%d, %d) match %.2f" % (etichetta, pos[0], pos[1], score)
        tasto = cfg["tasto"]
        if tasto:
            time.sleep(0.3)
            actions.hotkey(*tasto.split("+"))
            testo += " + tasto '%s'" % tasto
        self._scrivi(testo)

    # ------------------------------------------------------------ azioni
    def _cerca(self):
        cfg = self._config()
        nomi, soglia = cfg["nomi"], cfg["soglia"]

        def lavoro():
            self._attendi_iniziale(cfg["attesa"])
            risultati = agent.locate_many(nomi, soglia, region=cfg["zona"],
                                          monitor=cfg["monitor"], best=cfg["best"],
                                          colore=cfg["colore"])
            if not risultati:
                self._scrivi("[x] nessuna delle %d immagini e' a schermo (soglia %.2f). "
                             "Usa Diagnosi per capire perche'." % (len(nomi), soglia))
                return
            for nome, pos, score in risultati:
                self._scrivi("[ok] '%s' in (%d, %d)  match %.2f"
                             % (nome, pos[0], pos[1], score))
            if len(nomi) > 1:
                self._scrivi("     con un'azione agirei su '%s'" % risultati[0][0])
        self._avvia(lavoro, "cerco...")

    def _una_volta(self):
        cfg = self._config()
        nomi = cfg["nomi"]

        def lavoro():
            self._attendi_iniziale(cfg["attesa"])
            risultati = agent.locate_many(nomi, cfg["soglia"], region=cfg["zona"],
                                          monitor=cfg["monitor"], best=cfg["best"],
                                          colore=cfg["colore"])
            if not risultati:
                self._scrivi("[x] non trovato, non faccio nulla")
                return
            nome, pos, score = risultati[0]
            self._fai_azione(cfg, nome, pos, score)
        self._avvia(lavoro, "eseguo...")

    def _loop(self):
        cfg = self._config()
        nomi, soglia = cfg["nomi"], cfg["soglia"]
        intervallo, cooldown = cfg["intervallo"], cfg["cooldown"]
        massimo, monitor = cfg["massimo"], cfg["monitor"]

        def lavoro():
            self._attendi_iniziale(cfg["attesa"])
            self._scrivi("--- ciclo avviato su %s ---"
                         % ", ".join("'%s'" % n for n in nomi))
            if len(nomi) > 1:
                self._scrivi("    criterio: %s" % ("punteggio piu' alto" if cfg["best"]
                                                   else "ordine della lista"))
            inizio = time.time()
            cicli = presi = errori = 0
            ultimo_stato = time.time()
            while not self.stop_event.is_set():
                cicli += 1
                try:
                    risultati = agent.locate_many(nomi, soglia, region=cfg["zona"],
                                                  monitor=monitor, best=cfg["best"],
                                                  colore=cfg["colore"])
                except actions.pyautogui.FailSafeException:
                    raise
                except Exception as e:
                    errori += 1
                    self._scrivi("[!] errore nella ricerca: %s" % e)
                    risultati = []
                if risultati:
                    presi += 1
                    nome, pos, score = risultati[0]
                    self._fai_azione(cfg, nome, pos, score, presi)
                    if massimo and presi >= massimo:
                        self._scrivi("[i] raggiunto il massimo di %d" % massimo)
                        break
                    fine = time.time() + cooldown
                    while time.time() < fine and not self.stop_event.is_set():
                        time.sleep(0.05)
                    ultimo_stato = time.time()
                else:
                    if time.time() - ultimo_stato >= 30:
                        self._scrivi("...sto ancora cercando (%d controlli, %d presi)"
                                     % (cicli, presi))
                        ultimo_stato = time.time()
                    fine = time.time() + intervallo
                    while time.time() < fine and not self.stop_event.is_set():
                        time.sleep(0.05)
            durata = time.time() - inizio
            self._scrivi("--- ciclo finito: %dm %ds, %d controlli, %d azioni, %d errori ---"
                         % (durata // 60, durata % 60, cicli, presi, errori))
        self._avvia(lavoro, "ciclo in corso...")

    def _diagnosi(self):
        cfg = self._config()
        nomi, attesa = cfg["nomi"], cfg["attesa"]

        def lavoro():
            for i, nome in enumerate(nomi):
                self._scrivi("--- diagnosi di '%s' ---" % nome)
                # l'attesa serve solo la prima volta, per portare a schermo la finestra
                cmd = [sys.executable, os.path.join(QUI, "diagnosi.py"), nome,
                       str(attesa if i == 0 else 0)]
                p = subprocess.Popen(cmd, cwd=QUI, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, universal_newlines=True)
                for riga in p.stdout:
                    riga = riga.rstrip()
                    if riga:
                        self._scrivi("  " + riga)
                p.wait()
        self._avvia(lavoro, "diagnosi...")

    # ------------------------------------------------------ nuovi template
    def _chiedi_nome(self):
        nome = simpledialog.askstring("Nuova immagine",
                                      "Nome (senza .png):", parent=self.root)
        if not nome:
            return None
        return "".join(c for c in nome.strip() if c.isalnum() or c in "_-")

    def _esegui_script(self, script, pre_argomenti, messaggio):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("ScreenAgent", "C'e' gia' un'azione in corso.")
            return
        nome = self._chiedi_nome()
        if not nome:
            return
        if messaggio:
            self._scrivi(messaggio)
        self.root.update_idletasks()

        def lavoro():
            cmd = [sys.executable, os.path.join(QUI, script)] + pre_argomenti + [nome]
            p = subprocess.Popen(cmd, cwd=QUI, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, universal_newlines=True)
            for riga in p.stdout:
                riga = riga.rstrip()
                if riga:
                    self._scrivi("  " + riga)
            p.wait()
            self.coda.put(("aggiorna", None))

        self.root.iconify()
        self._pulsanti(attivo=False)
        self.stato.configure(text="creo l'immagine...", fg=TESTO)
        self.spia.configure(fg=ACCENTO)
        self.worker = threading.Thread(target=self._esegui, args=(lavoro,), daemon=True)
        self.worker.start()

    def _nuovo_da_appunti(self):
        self._esegui_script("incolla.py", [], "prendo l'immagine dagli appunti...")

    def _nuovo_da_schermo(self):
        self._esegui_script("agent.py", ["snip"],
                            "hai 3 secondi per mostrare la finestra, poi trascina "
                            "il rettangolo e premi INVIO")

    # ==================================================== scheda AUTOCLICKER
    def _tab_autoclicker(self, parent):
        corpo = ttk.Frame(parent, style="Sfondo.TFrame")
        corpo.pack(fill="both", expand=True, pady=(10, 0))

        # ---- intervallo fra i click
        c_int = self._card(corpo, "intervallo tra i click", fill="x")
        g = ttk.Frame(c_int, style="Card.TFrame")
        g.pack(fill="x")
        self.ac_ore = tk.StringVar(value="0")
        self.ac_min = tk.StringVar(value="0")
        self.ac_sec = tk.StringVar(value="0")
        self.ac_ms = tk.StringVar(value="100")
        for i, (et, var) in enumerate((("ore", self.ac_ore), ("minuti", self.ac_min),
                                       ("secondi", self.ac_sec),
                                       ("millisecondi", self.ac_ms))):
            ttk.Label(g, text=et, style="Spento.TLabel").grid(row=0, column=i,
                                                              sticky="w")
            ttk.Entry(g, textvariable=var, font=(F_MONO, 9), width=9).grid(
                row=1, column=i, sticky="w", padx=(0, 22))
        g.columnconfigure(4, weight=1)   # lo spazio in piu' finisce a destra

        # ---- opzioni + ripetizioni
        riga = ttk.Frame(corpo, style="Sfondo.TFrame")
        riga.pack(fill="x", pady=(12, 0))

        c_op = self._card(riga, "opzioni del click", side="left", fill="both",
                          expand=True)
        ttk.Label(c_op, text="Pulsante del mouse", style="Spento.TLabel").pack(
            anchor="w")
        self.ac_pulsante = ttk.Combobox(c_op, state="readonly", font=(F, 9),
                                        values=["sinistro", "centrale", "destro"])
        self.ac_pulsante.current(0)
        self.ac_pulsante.pack(fill="x", pady=(2, 10))
        ttk.Label(c_op, text="Tipo di click", style="Spento.TLabel").pack(anchor="w")
        self.ac_tipo = ttk.Combobox(c_op, state="readonly", font=(F, 9),
                                    values=["singolo", "doppio"])
        self.ac_tipo.current(0)
        self.ac_tipo.pack(fill="x", pady=(2, 0))

        c_rip = self._card(riga, "ripetizioni", side="left", fill="both", expand=True,
                           padx=(12, 0))
        self.ac_modo = tk.StringVar(value="infinito")
        self._segmenti(c_rip, self.ac_modo,
                       (("Un numero di volte", "n"),
                        ("Finche' non lo fermo", "infinito")), fill="x")
        riga_n = ttk.Frame(c_rip, style="Card.TFrame")
        riga_n.pack(fill="x", pady=(10, 0))
        ttk.Label(riga_n, text="numero di click", style="Spento.TLabel").pack(
            side="left", padx=(0, 8))
        self.ac_volte = tk.StringVar(value="10")
        ttk.Entry(riga_n, textvariable=self.ac_volte, width=8,
                  font=(F_MONO, 9)).pack(side="left")

        # ---- posizione del cursore
        c_pos = self._card(corpo, "posizione del cursore", fill="x", pady=(12, 0))
        self.ac_posizione = tk.StringVar(value="attuale")
        self._segmenti(c_pos, self.ac_posizione,
                       (("Dove si trova il mouse", "attuale"),
                        ("In un punto fisso", "fisso")), fill="x")
        riga_p = ttk.Frame(c_pos, style="Card.TFrame")
        riga_p.pack(fill="x", pady=(10, 0))
        ttk.Button(riga_p, text="Scegli punto", style="Piccolo.TButton",
                   cursor="hand2", command=self._ac_scegli_punto).pack(side="left")
        self.ac_x = tk.StringVar(value="0")
        self.ac_y = tk.StringVar(value="0")
        ttk.Label(riga_p, text="X", style="Spento.TLabel").pack(side="left",
                                                                padx=(16, 4))
        ttk.Entry(riga_p, textvariable=self.ac_x, width=8, font=(F_MONO, 9)).pack(
            side="left")
        ttk.Label(riga_p, text="Y", style="Spento.TLabel").pack(side="left",
                                                                padx=(12, 4))
        ttk.Entry(riga_p, textvariable=self.ac_y, width=8, font=(F_MONO, 9)).pack(
            side="left")

        # ---- pulsanti
        barra = ttk.Frame(corpo, style="Sfondo.TFrame")
        barra.pack(fill="x", pady=12)
        self.ac_b_avvia = ttk.Button(barra, text="▶  Avvia (F6)",
                                     style="Accento.TButton", cursor="hand2",
                                     command=self._ac_avvia)
        self.ac_b_avvia.pack(side="left")
        self.ac_b_ferma = ttk.Button(barra, text="■  Ferma (F6)",
                                     style="Pericolo.TButton", cursor="hand2",
                                     state="disabled", command=self._ac_ferma)
        self.ac_b_ferma.pack(side="left", padx=8)
        self.ac_b_tasto = ttk.Button(barra, text="Tasto rapido: F6", cursor="hand2",
                                     command=self._ac_scegli_tasto)
        self.ac_b_tasto.pack(side="left", padx=(16, 0))
        self.ac_b_riproduci = ttk.Button(barra, text="Riproduci", cursor="hand2",
                                         command=self._ac_riproduci)
        self.ac_b_riproduci.pack(side="right")
        self.ac_b_registra = ttk.Button(barra, text="Registra", cursor="hand2",
                                        command=self._ac_registra)
        self.ac_b_registra.pack(side="right", padx=8)

        # ---- registro
        c_log = self._card(corpo, "registro", fill="both", expand=True, pady=(0, 14))
        cornice = tk.Frame(c_log, bg=CARD_ALT, highlightthickness=1,
                           highlightbackground=BORDO)
        cornice.pack(fill="both", expand=True)
        self.ac_log = tk.Text(cornice, height=7, wrap="word", state="disabled",
                              bg=CARD_ALT, fg=TESTO, font=(F_MONO, 9), borderwidth=0,
                              highlightthickness=0, padx=10, pady=8, spacing3=2)
        sb = ttk.Scrollbar(cornice, command=self.ac_log.yview)
        self.ac_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.ac_log.pack(fill="both", expand=True)
        for tag, colore in (("ora", "#5d6673"), ("ok", OK), ("err", ALLARME),
                            ("warn", AVVISO), ("titolo", ACCENTO),
                            ("normale", TESTO)):
            self.ac_log.tag_configure(tag, foreground=colore)

        self._ac_scrivi("Il tasto rapido funziona anche con la finestra in secondo "
                        "piano. Failsafe: mouse nell'angolo in alto a sinistra.")
        if self.registrazione:
            self._ac_scrivi("[ok] registrazione precedente caricata: %d azioni"
                            % len(self.registrazione))

    # ---------------------------------------------------------- autoclicker
    def _ac_scrivi(self, testo):
        self.coda.put(("aclog", testo))

    def _ac_intervallo(self):
        return max(0.0,
                   self._numero(self.ac_ore, 0) * 3600
                   + self._numero(self.ac_min, 0) * 60
                   + self._numero(self.ac_sec, 0)
                   + self._numero(self.ac_ms, 0) / 1000.0)

    def _ac_config(self):
        return {
            "intervallo": self._ac_intervallo(),
            "pulsante": self.ac_pulsante.get(),
            "tipo": self.ac_tipo.get(),
            "doppio": self.ac_tipo.get() == "doppio",
            "posizione": self.ac_posizione.get(),
            "x": self._numero(self.ac_x, 0, intero=True),
            "y": self._numero(self.ac_y, 0, intero=True),
            "volte": (self._numero(self.ac_volte, 0, intero=True)
                      if self.ac_modo.get() == "n" else 0),
        }

    def _ac_occupato(self):
        return self.ac_worker is not None and self.ac_worker.is_alive()

    def _ac_pulsanti(self, attivo):
        stato = "normal" if attivo else "disabled"
        for b in (self.ac_b_avvia, self.ac_b_tasto, self.ac_b_riproduci):
            b.configure(state=stato)
        self.ac_b_ferma.configure(state="disabled" if attivo else "normal")
        self.ac_b_registra.configure(
            text="Ferma registrazione" if self.ac_registrando else "Registra",
            state="normal" if (attivo or self.ac_registrando) else "disabled")

    def _ac_parti(self, funzione, stato):
        if self._ac_occupato():
            messagebox.showinfo("ScreenAgent", "L'autoclicker sta gia' lavorando.")
            return
        self.ac_stop.clear()
        self._ac_pulsanti(attivo=False)
        self.stato.configure(text=stato, fg=TESTO)
        self.spia.configure(fg=ACCENTO)

        def involucro():
            try:
                funzione()
            except Exception as e:
                self._ac_scrivi("[x] errore: %s" % e)
            finally:
                self.coda.put(("acfine", None))

        self.ac_worker = threading.Thread(target=involucro, daemon=True)
        self.ac_worker.start()

    def _ac_fine(self):
        self.ac_registrando = False
        self._ac_pulsanti(attivo=True)
        self.stato.configure(text="pronto", fg=SPENTO)
        self.spia.configure(fg=SPENTO)

    def _ac_avvia(self):
        cfg = self._ac_config()

        def lavoro():
            self._ac_scrivi("--- avviato: click %s %s, ogni %s, %s ---"
                            % (cfg["tipo"], cfg["pulsante"],
                               self._ac_testo_intervallo(cfg["intervallo"]),
                               "%d volte" % cfg["volte"] if cfg["volte"]
                               else "finche' non lo fermo"))
            fatti = 0
            while not self.ac_stop.is_set():
                if clicker.nell_angolo():
                    self._ac_scrivi("[x] FAILSAFE: mouse nell'angolo, mi fermo")
                    break
                if cfg["posizione"] == "fisso":
                    clicker.click(cfg["pulsante"], cfg["doppio"], cfg["x"], cfg["y"])
                else:
                    clicker.click(cfg["pulsante"], cfg["doppio"])
                fatti += 1
                if fatti % 50 == 0:
                    self.coda.put(("acstato", "%d click" % fatti))
                if cfg["volte"] and fatti >= cfg["volte"]:
                    break
                if not clicker.attesa_interrompibile(cfg["intervallo"], self.ac_stop):
                    break
            self._ac_scrivi("--- fermato dopo %d click ---" % fatti)
        self._ac_parti(lavoro, "autoclicker in corso...")

    def _ac_testo_intervallo(self, s):
        return "%d ms" % round(s * 1000) if s < 1 else "%.2f s" % s

    def _ac_ferma(self):
        self.ac_stop.set()
        self.stato.configure(text="mi fermo...", fg=AVVISO)

    def _ac_registra(self):
        if self.ac_registrando:          # il pulsante fa da interruttore
            self.ac_stop.set()
            return
        self.ac_registrando = True

        def lavoro():
            self._ac_scrivi("--- registrazione: comincio fra 1 secondo, premi %s "
                            "(o il pulsante) per fermarla ---" % self.nome_hotkey)
            eventi = clicker.registra(self.ac_stop, ignora=(self.vk_hotkey,))
            eventi = clicker.taglia_coda(eventi)
            self.registrazione = eventi
            clicker.salva(eventi, self.file_registrazione)
            if eventi:
                self._ac_scrivi("[ok] registrate %d azioni in %.1f s (salvate in "
                                "registrazione.json)" % (len(eventi), eventi[-1]["t"]))
            else:
                self._ac_scrivi("[!] non ho registrato nulla")
        self._ac_parti(lavoro, "registrazione in corso...")

    def _ac_riproduci(self):
        if not self.registrazione:
            messagebox.showinfo("ScreenAgent",
                                "Non c'e' niente da riprodurre: registra prima.")
            return
        volte = (self._numero(self.ac_volte, 1, intero=True)
                 if self.ac_modo.get() == "n" else 0)
        eventi = list(self.registrazione)

        def lavoro():
            self._ac_scrivi("--- riproduco %d azioni, %s ---"
                            % (len(eventi), "%d volte" % volte if volte
                               else "finche' non lo fermo"))
            giri = clicker.riproduci(eventi, self.ac_stop, ripetizioni=volte)
            self._ac_scrivi("--- riproduzione finita: %d giri ---" % giri)
        self._ac_parti(lavoro, "riproduzione in corso...")

    def _ac_scegli_punto(self):
        if self._ac_occupato():
            return

        def lavoro():
            self._ac_scrivi("clicca dove vuoi: prendo quelle coordinate...")
            time.sleep(0.4)
            while not self.ac_stop.is_set():
                if clicker.premuto(0x01):        # pulsante sinistro
                    x, y = clicker.posizione()
                    self.coda.put(("acpunto", (x, y)))
                    self._ac_scrivi("[ok] punto scelto: (%d, %d)" % (x, y))
                    while clicker.premuto(0x01):
                        time.sleep(0.02)
                    return
                time.sleep(0.02)
        self._ac_parti(lavoro, "scegli il punto...")

    def _ac_scegli_tasto(self):
        fin = tk.Toplevel(self.root)
        fin.title("Tasto rapido")
        fin.configure(bg=CARD)
        fin.resizable(False, False)
        tk.Label(fin, text="Premi il tasto da usare\nper avviare e fermare",
                 bg=CARD, fg=TESTO, font=(F, 12), justify="center",
                 padx=40, pady=26).pack()
        tk.Label(fin, text="Esc annulla", bg=CARD, fg=SPENTO,
                 font=(F, 8)).pack(pady=(0, 18))
        fin.transient(self.root)
        fin.grab_set()
        fin.focus_force()

        def su_tasto(evento):
            if evento.keysym != "Escape":
                # su Windows keycode E' il codice del tasto virtuale
                self.vk_hotkey = evento.keycode
                self.nome_hotkey = clicker.nome_tasto(evento.keycode)
                self.ac_b_tasto.configure(text="Tasto rapido: %s" % self.nome_hotkey)
                self.ac_b_avvia.configure(text="▶  Avvia (%s)" % self.nome_hotkey)
                self.ac_b_ferma.configure(text="■  Ferma (%s)" % self.nome_hotkey)
                self._ac_scrivi("[ok] tasto rapido impostato su %s" % self.nome_hotkey)
            fin.destroy()

        fin.bind("<Key>", su_tasto)

    def _ascolta_tasto_rapido(self):
        """Sorveglia il tasto rapido anche quando la finestra non ha il fuoco."""
        prima = False
        while not self.chiuso.is_set():
            try:
                ora = clicker.premuto(self.vk_hotkey)
            except Exception:
                ora = False
            if ora and not prima:
                self.coda.put(("hotkey", None))
            prima = ora
            time.sleep(0.03)

    def _tasto_rapido_premuto(self):
        if self._ac_occupato():
            self._ac_ferma()
        elif self.worker and self.worker.is_alive():
            self._ferma()
        else:
            self.tabs.select(1)
            self._ac_avvia()

    def _chiudi(self):
        self.stop_event.set()
        self.ac_stop.set()
        self.chiuso.set()
        self.root.destroy()


def main():
    scr.enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
