"""Interfaccia grafica di ScreenAgent.

    python ScreenAgent.py       (oppure doppio click su ScreenAgent.bat)

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
from tkinter import filedialog, messagebox, simpledialog, ttk

import cv2
from PIL import Image, ImageDraw, ImageTk

import actions
import agent
import clicker
import screen as scr
import motore
import registratore
import vision

import percorsi
QUI = percorsi.BASE
TPL_DIR = percorsi.TEMPLATES
SEQ_DIR = percorsi.SEQUENZE      # qui stanno tutte le sequenze (.json)

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


def abilita_trascinamento(albero, sposta, finito):
    """Riordino col mouse su una tabella i cui iid sono gli indici (0,1,2...).

    Mentre trascini la riga si sposta subito, cosi' vedi dove finisce; al
    rilascio scatta `finito` (che salva). Se non ti sei mosso non succede nulla,
    quindi il click semplice e il doppio click continuano a funzionare.
    """
    stato = {"da": None, "mosso": False}

    def premuto(evento):
        riga = albero.identify_row(evento.y)
        stato["da"] = int(riga) if riga else None
        stato["mosso"] = False

    def trascina(evento):
        if stato["da"] is None:
            return
        riga = albero.identify_row(evento.y)
        if not riga:
            return
        arrivo = int(riga)
        if arrivo != stato["da"]:
            sposta(stato["da"], arrivo)
            stato["da"] = arrivo
            stato["mosso"] = True

    def rilasciato(_evento):
        if stato["mosso"]:
            finito()
        stato["da"] = None
        stato["mosso"] = False

    albero.bind("<ButtonPress-1>", premuto, add="+")
    albero.bind("<B1-Motion>", trascina, add="+")
    albero.bind("<ButtonRelease-1>", rilasciato, add="+")


class App:
    def __init__(self, root):
        self.root = root
        root.title("ScreenAgent")
        root.geometry("1120x756")
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
        # cartelle dei dati (sequenze/, macro/, templates/): le crea e ci porta
        # dentro i file che le versioni precedenti lasciavano accanto al programma.
        # Va fatto PRIMA di leggere qualsiasi file di dati.
        self.file_spostati = motore.sistema_cartelle()

        # la registrazione "Record" dell'Autoclicker sta in macro/
        self.file_registrazione = percorsi.REGISTRAZIONE
        self.registrazione = clicker.carica(self.file_registrazione)

        # sequenza
        self.seq_stop = threading.Event()
        self.seq_worker = None
        self.file_sequenza = os.path.join(SEQ_DIR, "sequenza.json")
        # il motore vero sta in motore.py: lo usa anche il lanciatore autonomo
        self.passi, self.opzioni_iniziali = motore.leggi(self.file_sequenza)

        # catena di sequenze
        self.cat_stop = threading.Event()
        self.cat_worker = None
        self.file_catena = os.path.join(QUI, "catena.json")
        self.catena, self.opzioni_catena = motore.leggi_catena(self.file_catena)

        # macro (registra & riesegui)
        self.mac_stop = threading.Event()
        self.mac_worker = None
        self.mac_registrando = False
        self.mac_via_tasto = False          # la registrazione e' stata fermata con F7?
        self.vk_registra = 0x76             # F7
        self.nome_registra = "F7"
        self.dir_macro = percorsi.MACRO
        os.makedirs(self.dir_macro, exist_ok=True)
        self.macro_eventi = []              # ultima registrazione in memoria

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

        s.configure("Treeview", background=CARD_ALT, fieldbackground=CARD_ALT,
                    foreground=TESTO, borderwidth=0, rowheight=25, font=(F, 9))
        s.configure("Treeview.Heading", background=PULS, foreground=SPENTO,
                    borderwidth=0, relief="flat", font=(F, 8), padding=(6, 6))
        s.map("Treeview", background=[("selected", ACCENTO)],
              foreground=[("selected", "#08101f")])
        s.map("Treeview.Heading", background=[("active", PULS_HOVER)])

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
        etichetta = None
        if titolo:
            etichetta = ttk.Label(guscio, text=titolo.upper(),
                                  style="Intestazione.TLabel")
            etichetta.pack(anchor="w", padx=12, pady=(9, 0))
        dentro = ttk.Frame(guscio, style="Card.TFrame")
        dentro.pack(fill="both", expand=True, padx=12, pady=(6, 12))
        dentro.etichetta_titolo = etichetta   # per cambiare il titolo piu' avanti
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
        tab_seq = ttk.Frame(self.tabs, style="Sfondo.TFrame")
        self.tabs.add(tab_seq, text="Sequenza")
        tab_cat = ttk.Frame(self.tabs, style="Sfondo.TFrame")
        self.tabs.add(tab_cat, text="Catena")
        tab_mac = ttk.Frame(self.tabs, style="Sfondo.TFrame")
        self.tabs.add(tab_mac, text="Macro")
        self.idx_macro = 3
        tab_ac = ttk.Frame(self.tabs, style="Sfondo.TFrame")
        self.tabs.add(tab_ac, text="Autoclicker")
        self.idx_autoclicker = 4

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

        # gestione dell'immagine selezionata
        riga_g1 = ttk.Frame(lista_box, style="Card.TFrame")
        riga_g1.pack(fill="x", pady=(6, 0))
        ttk.Button(riga_g1, text="Rinomina", style="Piccolo.TButton",
                   command=self._img_rinomina).pack(side="left", expand=True, fill="x")
        ttk.Button(riga_g1, text="Duplica", style="Piccolo.TButton",
                   command=self._img_duplica).pack(side="left", expand=True,
                                                   fill="x", padx=(6, 0))
        riga_g2 = ttk.Frame(lista_box, style="Card.TFrame")
        riga_g2.pack(fill="x", pady=(6, 0))
        ttk.Button(riga_g2, text="Dove si usa?", style="Piccolo.TButton",
                   command=self._img_dove_usata).pack(side="left", expand=True,
                                                      fill="x")
        ttk.Button(riga_g2, text="Elimina", style="Piccolo.TButton",
                   command=self._img_elimina).pack(side="left", expand=True,
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

        # ---------------- altre schede
        self._tab_sequenza(tab_seq)
        self._tab_catena(tab_cat)
        self._tab_macro(tab_mac)
        self._tab_autoclicker(tab_ac)

        # ---------------- barra di stato
        piede = tk.Frame(self.root, bg=CARD, highlightthickness=1,
                         highlightbackground=BORDO)
        piede.pack(fill="x", side="bottom")
        self.spia = tk.Label(piede, text="●", bg=CARD, fg=SPENTO, font=(F, 11))
        self.spia.pack(side="left", padx=(14, 6), pady=5)
        self.stato = tk.Label(piede, text="pronto", bg=CARD, fg=SPENTO, font=(F, 9))
        self.stato.pack(side="left")
        tk.Label(piede, text="EMERGENZA: premi Esc (o porta il mouse nell'angolo in "
                             "alto a sinistra) per fermare tutto",
                 bg=CARD, fg=AVVISO, font=(F, 8)).pack(side="right", padx=14)

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
        if hasattr(self, "combo_seq_immagine"):
            self._seq_aggiorna_immagini(nomi)

    def _scacchiera(self, w, h, cella=9):
        img = Image.new("RGB", (w, h), (41, 46, 55))
        d = ImageDraw.Draw(img)
        for y in range(0, h, cella):
            for x in range(0, w, cella):
                if (x // cella + y // cella) % 2:
                    d.rectangle([x, y, x + cella - 1, y + cella - 1], fill=(34, 39, 47))
        return img

    def _carica_anteprima(self, nome, max_w, max_h):
        """Immagine Tk pronta per una Label (su scacchiera, per vedere la
        trasparenza), ridimensionata per stare in max_w x max_h. None se manca."""
        if not nome:
            return None
        p = os.path.join(TPL_DIR, nome + ".png")
        if not os.path.isfile(p):
            return None
        try:
            img = Image.open(p).convert("RGBA")
            w, h = img.size
            k = min(float(max_w) / w, float(max_h) / h)
            k = min(k, 4.0) if k > 1 else k
            if k != 1:
                filtro = Image.NEAREST if k > 1 else Image.LANCZOS
                img = img.resize((max(int(w * k), 1), max(int(h * k), 1)), filtro)
            fondo = self._scacchiera(img.width, img.height)
            fondo.paste(img, (0, 0), img)
            return ImageTk.PhotoImage(fondo)
        except Exception:
            return None

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
                elif tipo == "emergenza":
                    self._ferma_tutto(dato)
                elif tipo == "mirino":
                    self._mostra_mirino(*dato)
                elif tipo == "zona":
                    self.zona = dato
                    self.et_zona.configure(text="zona: %dx%d da (%d, %d)"
                                                % (dato[2], dato[3], dato[0], dato[1]))
                    self._inserisci_log(self.log, "[ok] zona impostata: %s" % (dato,))
                elif tipo == "seqlog":
                    self._inserisci_log(self.seq_log, dato)
                elif tipo == "seqfine":
                    self._seq_fine()
                elif tipo == "seqpasso":
                    self._seq_evidenzia(dato)
                elif tipo == "catlog":
                    self._inserisci_log(self.cat_log, dato)
                elif tipo == "catfine":
                    self._cat_fine()
                elif tipo == "catpasso":
                    self._cat_evidenzia(dato)
                elif tipo == "maclog":
                    self._inserisci_log(self.mac_log, dato)
                elif tipo == "macfine":
                    self._mac_fine()
                elif tipo == "macregistrata":
                    self._mac_registrata(dato)
                elif tipo == "registra_macro":
                    self._mac_toggle_registrazione()
                elif tipo == "aggiorna":
                    self._aggiorna_lista()
        except queue.Empty:
            pass
        self.root.after(100, self._svuota_coda)

    def chiedi_mirino(self, x, y, raggio=34, durata=800):
        """Da un thread qualsiasi: chiede di evidenziare il punto (x, y)."""
        self.coda.put(("mirino", (x, y, raggio, durata)))

    def _mostra_mirino(self, x, y, raggio=34, durata=800):
        """Disegna per un attimo un mirino rosso sul punto dove si cliccherebbe.
        Finestra senza bordo, trasparente e CLICK-THROUGH (il click la attraversa),
        posizionata anche su coordinate negative (monitor a sinistra)."""
        lato = raggio * 2 + 60
        try:
            ov = tk.Toplevel(self.root)
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            trasp = "#000001"
            ov.configure(bg=trasp)
            ov.attributes("-transparentcolor", trasp)
            ov.geometry("%dx%d+%d+%d" % (lato, lato, x - lato // 2, y - lato // 2))
            cv = tk.Canvas(ov, width=lato, height=lato, bg=trasp,
                           highlightthickness=0)
            cv.pack()
            c = lato // 2
            cv.create_oval(c - raggio, c - raggio, c + raggio, c + raggio,
                           outline="#ff2d2d", width=3)
            cv.create_line(c - raggio - 14, c, c + raggio + 14, c,
                           fill="#ff2d2d", width=2)
            cv.create_line(c, c - raggio - 14, c, c + raggio + 14,
                           fill="#ff2d2d", width=2)
            ov.update_idletasks()
            # rende la finestra click-through (il click la attraversa) senza
            # perdere la trasparenza: aggiungo lo stile e ri-applico il colore-chiave
            try:
                import ctypes
                u = ctypes.windll.user32
                hwnd = u.GetParent(ov.winfo_id()) or ov.winfo_id()
                GWL, LAYERED, TRANSP = -20, 0x80000, 0x20
                stile = u.GetWindowLongW(hwnd, GWL)
                u.SetWindowLongW(hwnd, GWL, stile | LAYERED | TRANSP)
                # #000001 come COLORREF (0x00BBGGRR) = 0x00010000
                u.SetLayeredWindowAttributes(hwnd, 0x00010000, 0, 0x1)  # LWA_COLORKEY
            except Exception:
                pass
            ov.after(int(durata), ov.destroy)
        except Exception:
            pass

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

    def _cmd_strumento(self, tool, *args):
        """Comando per lanciare un sotto-strumento con la sua finestra OpenCV.
        Da exe: rilancia questo exe con --tool. Da sorgente: lo script .py."""
        if percorsi.avvio_congelato():
            return [sys.executable, "--tool", tool] + list(args)
        script = {"zona": ["zona.py"], "diagnosi": ["diagnosi.py"],
                  "snip": ["agent.py", "snip"], "incolla": ["incolla.py"]}[tool]
        return [sys.executable] + [os.path.join(QUI, script[0])] + script[1:] \
            + list(args)

    def _scegli_zona(self):
        if self.worker and self.worker.is_alive():
            return

        def lavoro():
            self._scrivi("scegli la zona: trascina il rettangolo e premi INVIO")
            p = subprocess.Popen(self._cmd_strumento("zona"),
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
                cmd = self._cmd_strumento("diagnosi", nome,
                                          str(attesa if i == 0 else 0))
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

    def _esegui_script(self, tool, messaggio):
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
            cmd = self._cmd_strumento(tool, nome)
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
        self._esegui_script("incolla", "prendo l'immagine dagli appunti...")

    def _nuovo_da_schermo(self):
        self._esegui_script("snip",
                            "hai 3 secondi per mostrare la finestra, poi trascina "
                            "il rettangolo e premi INVIO")

    # ----------------------------------------------- gestione delle immagini
    def _img_selezionata(self):
        nomi = self._nomi()
        if not nomi:
            messagebox.showinfo("ScreenAgent",
                                "Scegli prima un'immagine dalla lista.")
            return None
        return nomi[0]

    def _img_file_sequenza(self):
        """I file .json della cartella sequenze/ che sono davvero sequenze
        (hanno dei passi)."""
        files = []
        for f in sorted(os.listdir(SEQ_DIR)):
            if f.lower().endswith(".json") and f not in motore.NON_SEQUENZE:
                passi, _ = motore.leggi(os.path.join(SEQ_DIR, f))
                if passi:
                    files.append(f)
        return files

    def _img_usi(self, nome):
        """Dove e' usata l'immagine: lista di (file, [numeri_passo]).
        Include la sequenza aperta nella scheda (anche se non salvata)."""
        usi = []
        aperti = [i + 1 for i, p in enumerate(self.passi)
                  if nome in (p.get("immagine"), p.get("immagine2"))]
        if aperti:
            usi.append(("(sequenza aperta, non salvata)", aperti))
        for f in self._img_file_sequenza():
            passi, _ = motore.leggi(os.path.join(SEQ_DIR, f))
            dentro = [i + 1 for i, p in enumerate(passi)
                      if nome in (p.get("immagine"), p.get("immagine2"))]
            if dentro:
                usi.append((f, dentro))
        return usi

    def _img_dove_usata(self):
        nome = self._img_selezionata()
        if not nome:
            return
        usi = self._img_usi(nome)
        if not usi:
            messagebox.showinfo("Dove si usa",
                                "'%s' non e' usata in nessuna sequenza." % nome)
            return
        righe = ["• %s: passo %s" % (f, ", ".join(map(str, n))) for f, n in usi]
        messagebox.showinfo("Dove si usa '%s'" % nome,
                            "Usata in:\n\n" + "\n".join(righe))

    def _img_duplica(self):
        nome = self._img_selezionata()
        if not nome:
            return
        nuovo = self._chiedi_nome()
        if not nuovo or nuovo == nome:
            return
        dest = os.path.join(TPL_DIR, nuovo + ".png")
        if os.path.exists(dest):
            messagebox.showwarning("ScreenAgent", "Esiste gia' un'immagine '%s'."
                                   % nuovo)
            return
        try:
            import shutil
            shutil.copyfile(os.path.join(TPL_DIR, nome + ".png"), dest)
        except OSError as e:
            messagebox.showerror("ScreenAgent", "Non riesco a duplicare: %s" % e)
            return
        self._aggiorna_lista()
        self._scrivi("[ok] '%s' duplicata in '%s'" % (nome, nuovo))

    def _img_rinomina(self):
        nome = self._img_selezionata()
        if not nome:
            return
        nuovo = self._chiedi_nome()
        if not nuovo or nuovo == nome:
            return
        dest = os.path.join(TPL_DIR, nuovo + ".png")
        if os.path.exists(dest):
            messagebox.showwarning("ScreenAgent", "Esiste gia' un'immagine '%s'."
                                   % nuovo)
            return
        usi = self._img_usi(nome)
        aggiorna = False
        if usi:
            righe = ["• %s: passo %s" % (f, ", ".join(map(str, n)))
                     for f, n in usi]
            aggiorna = messagebox.askyesno(
                "Rinomina '%s'" % nome,
                "Questa immagine e' usata in:\n\n" + "\n".join(righe) +
                "\n\nAggiorno anche questi riferimenti al nuovo nome '%s'?\n"
                "(Se scegli No, quelle sequenze cercheranno un'immagine che non "
                "esiste piu'.)" % nuovo)
        try:
            os.replace(os.path.join(TPL_DIR, nome + ".png"), dest)
        except OSError as e:
            messagebox.showerror("ScreenAgent", "Non riesco a rinominare: %s" % e)
            return
        if aggiorna:
            self._img_sostituisci_riferimenti(nome, nuovo)
        self._aggiorna_lista()
        self._scrivi("[ok] rinominata '%s' -> '%s'%s"
                     % (nome, nuovo, " (riferimenti aggiornati)" if aggiorna else ""))

    def _img_sostituisci_riferimenti(self, vecchio, nuovo):
        """Nei file di sequenza e nella sequenza aperta, cambia il nome immagine."""
        cambiato = False
        for p in self.passi:        # sequenza aperta in memoria
            for campo in ("immagine", "immagine2"):
                if p.get(campo) == vecchio:
                    p[campo] = nuovo
                    cambiato = True
        if cambiato:
            self._seq_ridisegna()
            self._seq_salva_auto()
        for f in self._img_file_sequenza():
            percorso = os.path.join(SEQ_DIR, f)
            passi, opz = motore.leggi(percorso)
            tocca = False
            for p in passi:
                for campo in ("immagine", "immagine2"):
                    if p.get(campo) == vecchio:
                        p[campo] = nuovo
                        tocca = True
            if tocca:
                motore.salva(percorso, passi, opz)

    def _img_elimina(self):
        nome = self._img_selezionata()
        if not nome:
            return
        usi = self._img_usi(nome)
        avviso = "Eliminare l'immagine '%s'?" % nome
        if usi:
            righe = ["• %s: passo %s" % (f, ", ".join(map(str, n)))
                     for f, n in usi]
            avviso = ("ATTENZIONE: '%s' e' usata in:\n\n%s\n\nQuelle sequenze "
                      "falliranno il passo. Eliminarla lo stesso?"
                      % (nome, "\n".join(righe)))
        if not messagebox.askyesno("Elimina immagine", avviso):
            return
        try:
            os.remove(os.path.join(TPL_DIR, nome + ".png"))
        except OSError as e:
            messagebox.showerror("ScreenAgent", "Non riesco a eliminare: %s" % e)
            return
        self._aggiorna_lista()
        self._scrivi("[ok] eliminata '%s'" % nome)

    # ====================================================== scheda SEQUENZA
    # etichetta mostrata <-> valore salvato
    AZIONI_SEQ = (("Click", "click"),
                  ("Doppio click", "doppio"),
                  ("Click destro", "destro"),
                  ("Solo aspetta che compaia", "aspetta"),
                  ("Premi un tasto", "tasto"),
                  ("Scrivi un testo", "scrivi"),
                  ("Scorri in giu'", "scroll_giu"),
                  ("Scorri in su'", "scroll_su"),
                  ("Pausa", "pausa"),
                  ("Spegni il PC", "spegni"),
                  ("Trascina su un'altra immagine", "trascina"),
                  ("Se c'e' l'immagine... (condizione)", "condizione"))

    def _tab_sequenza(self, parent):
        corpo = ttk.Frame(parent, style="Sfondo.TFrame")
        corpo.pack(fill="both", expand=True, pady=(10, 0))

        # ---- riga per comporre un passo nuovo (o correggerne uno esistente)
        c_new = self._card(corpo, "aggiungi un passo", fill="x")
        self.card_passo = c_new
        riga_form = ttk.Frame(c_new, style="Card.TFrame")
        riga_form.pack(fill="x")

        # anteprima dell'immagine scelta nella tendina, a destra del form
        box_prev = tk.Frame(riga_form, width=84, height=84, bg=CARD_ALT,
                            highlightthickness=1, highlightbackground=BORDO)
        box_prev.pack_propagate(False)
        box_prev.pack(side="right", padx=(12, 0))
        self.seq_prev_form = tk.Label(box_prev, bg=CARD_ALT, borderwidth=0)
        self.seq_prev_form.pack(expand=True)
        self.seq_prev_form_tk = None

        g = ttk.Frame(riga_form, style="Card.TFrame")
        g.pack(side="left", fill="x", expand=True)

        self.seq_azione = tk.StringVar(value="Click")
        self.seq_tasto = tk.StringVar(value="")
        self.seq_attesa = tk.StringVar(value="1.0")
        self.seq_timeout = tk.StringVar(value="10")
        self.seq_soglia = tk.StringVar(value="0.85")
        self.seq_dx = tk.StringVar(value="0")
        self.seq_dy = tk.StringVar(value="0")

        self.etichetta_immagine = ttk.Label(g, text="Immagine", style="Spento.TLabel")
        self.etichetta_immagine.grid(row=0, column=0, sticky="w")
        self.v_seq_immagine = tk.StringVar(value="")
        self.combo_seq_immagine = ttk.Combobox(g, state="readonly", font=(F, 9),
                                               width=20,
                                               textvariable=self.v_seq_immagine)
        self.combo_seq_immagine.grid(row=1, column=0, sticky="we", padx=(0, 12))
        self.combo_seq_immagine.bind("<<ComboboxSelected>>",
                                     lambda e: self._seq_prev_form_aggiorna())

        ttk.Label(g, text="Azione", style="Spento.TLabel").grid(row=0, column=1,
                                                                sticky="w")
        combo_az = ttk.Combobox(g, textvariable=self.seq_azione, state="readonly",
                                font=(F, 9), width=20,
                                values=[e for e, _ in self.AZIONI_SEQ])
        combo_az.grid(row=1, column=1, sticky="we", padx=(0, 12))
        combo_az.bind("<<ComboboxSelected>>", self._seq_cambia_azione)

        # tengo i riferimenti: a seconda dell'azione alcuni campi vanno spenti
        self.campi_seq = {}
        self.etichette_seq = {}
        for col, (chiave, et, var, largh) in enumerate(
                (("tasto", "Tasto o testo", self.seq_tasto, 10),
                 ("attesa", "Attesa dopo (s)", self.seq_attesa, 8),
                 ("timeout", "Timeout (s)", self.seq_timeout, 8),
                 ("soglia", "Soglia", self.seq_soglia, 8),
                 ("dx", "Scost. X", self.seq_dx, 6),
                 ("dy", "Scost. Y", self.seq_dy, 6)), start=2):
            etichetta = ttk.Label(g, text=et, style="Spento.TLabel")
            etichetta.grid(row=0, column=col, sticky="w")
            campo = ttk.Entry(g, textvariable=var, width=largh, font=(F_MONO, 9))
            campo.grid(row=1, column=col, sticky="we", padx=(0, 12))
            self.campi_seq[chiave] = campo
            self.etichette_seq[chiave] = etichetta

        # seconda tendina, per l'immagine di ARRIVO del trascinamento: sta nella
        # stessa cella del campo "Tasto o testo" e si mostra solo per "trascina"
        self.v_seq_arrivo = tk.StringVar(value="")
        self.combo_seq_arrivo = ttk.Combobox(g, textvariable=self.v_seq_arrivo,
                                             state="readonly", font=(F, 9), width=12)
        self.combo_seq_arrivo.grid(row=1, column=2, sticky="we", padx=(0, 12))
        self.combo_seq_arrivo.grid_remove()

        self.seq_ripeti_finche = tk.BooleanVar(value=False)
        self.etichette_seq["ripeti"] = ttk.Label(g, text="Ripeti",
                                                 style="Spento.TLabel")
        self.etichette_seq["ripeti"].grid(row=0, column=8, sticky="w")
        self.chk_seq_ripeti = ttk.Checkbutton(g, variable=self.seq_ripeti_finche,
                                              cursor="hand2", text="finche' c'e'")
        self.chk_seq_ripeti.grid(row=1, column=8, sticky="w", padx=(0, 12))

        self.seq_modifica = None      # indice del passo in modifica, o None
        self.b_seq_aggiungi = ttk.Button(g, text="+  Aggiungi",
                                         style="Accento.TButton", cursor="hand2",
                                         command=self._seq_aggiungi)
        self.b_seq_aggiungi.grid(row=1, column=9, sticky="e")
        self.b_seq_annulla = ttk.Button(g, text="Annulla", style="Piccolo.TButton",
                                        cursor="hand2",
                                        command=lambda: self._seq_modo_modifica(None))
        self.b_seq_annulla.grid(row=1, column=10, sticky="e", padx=(6, 0))
        self.b_seq_annulla.grid_remove()
        g.columnconfigure(0, weight=3)
        g.columnconfigure(1, weight=3)
        for c in range(2, 6):
            g.columnconfigure(c, weight=1)

        ttk.Label(c_new, style="Spento.TLabel", justify="left",
                  text="Le azioni Premi un tasto, Scrivi un testo, Scorri e Pausa non "
                       "usano nessuna immagine: quello che premono, scrivono o di "
                       "quante tacche scorrono si mette nel campo \"Tasto o testo\".\n"
                       "\"Attesa dopo\" e' la pausa prima del passo successivo; "
                       "\"Timeout\" e' quanto aspetta che l'immagine compaia prima di "
                       "considerare fallito il passo.\n\"Ripeti finche' c'e'\" rifa' "
                       "lo stesso passo sulla stessa immagine finche' non sparisce "
                       "dallo schermo, poi prosegue col passo dopo.\nPer correggere "
                       "un passo gia' inserito: doppio click sulla sua riga (o il "
                       "pulsante Modifica), lo ritrovi qui sopra. Doppio click sulla "
                       "colonna Ripeti per accendere o spegnere il ciclo."
                  ).pack(anchor="w", pady=(8, 0))

        # ---- la sequenza vera e propria
        centro = ttk.Frame(corpo, style="Sfondo.TFrame")
        centro.pack(fill="both", expand=True, pady=(12, 0))

        c_lista = self._card(centro, "sequenza", side="left", fill="both",
                             expand=True)
        cornice = tk.Frame(c_lista, bg=CARD_ALT, highlightthickness=1,
                           highlightbackground=BORDO)
        cornice.pack(fill="both", expand=True)
        colonne = ("n", "immagine", "azione", "ripeti", "tasto", "attesa", "timeout",
                   "soglia")
        self.albero = ttk.Treeview(cornice, columns=colonne, show="headings",
                                   height=6, selectmode="browse")
        self.albero.bind("<Double-1>", self._seq_doppio_click)
        for col, testo, largh, anc in (
                ("n", "#", 32, "center"), ("immagine", "Immagine", 150, "w"),
                ("azione", "Azione", 150, "w"), ("ripeti", "Ripeti", 80, "center"),
                ("tasto", "Tasto / testo", 135, "w"),
                ("attesa", "Attesa dopo", 85, "center"),
                ("timeout", "Timeout", 75, "center"),
                ("soglia", "Soglia", 60, "center")):
            self.albero.heading(col, text=testo, anchor=anc)
            self.albero.column(col, width=largh, anchor=anc,
                               stretch=(col == "immagine"))
        sb = ttk.Scrollbar(cornice, command=self.albero.yview)
        self.albero.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.albero.pack(fill="both", expand=True, padx=2, pady=2)
        abilita_trascinamento(self.albero, self._seq_trascina, self._seq_salva_auto)
        self.albero.bind("<<TreeviewSelect>>", self._seq_prev_passo_aggiorna)

        col_b = ttk.Frame(centro, style="Sfondo.TFrame")
        col_b.pack(side="left", fill="y", padx=(12, 0))

        # anteprima del passo selezionato nella tabella
        box_pp = tk.Frame(col_b, width=120, height=96, bg=CARD_ALT,
                         highlightthickness=1, highlightbackground=BORDO)
        box_pp.pack_propagate(False)
        box_pp.pack(fill="x", pady=(0, 4))
        self.seq_prev_passo = tk.Label(box_pp, bg=CARD_ALT, borderwidth=0,
                                      text="(seleziona\nun passo)", fg=SPENTO,
                                      font=(F, 8))
        self.seq_prev_passo.pack(expand=True)
        self.seq_prev_passo_tk = None
        self.seq_prev_passo_info = ttk.Label(col_b, text="", style="Spento.TLabel",
                                            font=(F, 8))
        self.seq_prev_passo_info.pack(fill="x", pady=(0, 6))

        ttk.Button(col_b, text="Prova passo", style="Accento.TButton",
                   cursor="hand2", width=12,
                   command=self._seq_prova_passo).pack(fill="x", pady=(0, 8))
        for testo, comando in (("▲  Su", self._seq_su),
                               ("▼  Giu'", self._seq_giu),
                               ("Modifica", self._seq_modifica_passo),
                               ("Rimuovi", self._seq_rimuovi),
                               ("Svuota", self._seq_svuota)):
            ttk.Button(col_b, text=testo, style="Piccolo.TButton", cursor="hand2",
                       width=12, command=comando).pack(fill="x", pady=(0, 6))
        ttk.Frame(col_b, style="Sep.TFrame", height=1).pack(fill="x", pady=6)
        ttk.Button(col_b, text="Salva...", style="Piccolo.TButton", cursor="hand2",
                   width=12, command=self._seq_salva_file).pack(fill="x", pady=(0, 6))
        ttk.Button(col_b, text="Apri...", style="Piccolo.TButton", cursor="hand2",
                   width=12, command=self._seq_apri_file).pack(fill="x", pady=(0, 6))
        ttk.Button(col_b, text="Unisci...", style="Piccolo.TButton", cursor="hand2",
                   width=12, command=self._seq_unisci).pack(fill="x")

        # ---- esecuzione
        c_run = self._card(corpo, "esecuzione", fill="x", pady=(12, 0))
        riga = ttk.Frame(c_run, style="Card.TFrame")
        riga.pack(fill="x")

        self.seq_ripeti = tk.StringVar(value="1")
        self.seq_attesa_iniziale = tk.StringVar(value="3")
        ttk.Label(riga, text="Ripeti (0 = all'infinito)",
                  style="Spento.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(riga, textvariable=self.seq_ripeti, width=6,
                  font=(F_MONO, 9)).pack(side="left", padx=(0, 18))
        ttk.Label(riga, text="Attesa prima di partire (s)",
                  style="Spento.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(riga, textvariable=self.seq_attesa_iniziale, width=6,
                  font=(F_MONO, 9)).pack(side="left", padx=(0, 18))
        ttk.Label(riga, text="Se un'immagine non compare",
                  style="Spento.TLabel").pack(side="left", padx=(0, 6))
        self.seq_se_manca = ttk.Combobox(riga, state="readonly", font=(F, 9), width=22,
                                         values=["ferma la sequenza",
                                                 "salta il passo",
                                                 "continua ad aspettare"])
        self.seq_se_manca.current(0)
        self.seq_se_manca.pack(side="left")

        self.v_seq_mirino = tk.BooleanVar(value=True)
        ttk.Checkbutton(c_run, variable=self.v_seq_mirino,
                        text="Mostra un mirino rosso dove sta per cliccare").pack(
            anchor="w", pady=(8, 0))

        barra = ttk.Frame(corpo, style="Sfondo.TFrame")
        barra.pack(fill="x", pady=12)
        self.seq_b_avvia = ttk.Button(barra, text="▶  Avvia sequenza",
                                      style="Accento.TButton", cursor="hand2",
                                      command=self._seq_avvia)
        self.seq_b_avvia.pack(side="left")
        self.seq_b_ferma = ttk.Button(barra, text="■  Ferma", style="Pericolo.TButton",
                                      cursor="hand2", state="disabled",
                                      command=self._seq_ferma)
        self.seq_b_ferma.pack(side="left", padx=8)
        ttk.Label(barra, style="Sottotitolo.TLabel",
                  text="   usa la zona e il modo colore impostati nella scheda "
                       "Riconoscimento").pack(side="left")

        # ---- registro: altezza fissa, cosi' lo spazio in piu' va alla tabella
        c_log = self._card(corpo, "registro", fill="x", pady=(0, 14))
        cornice_log = tk.Frame(c_log, bg=CARD_ALT, highlightthickness=1,
                               highlightbackground=BORDO)
        cornice_log.pack(fill="both", expand=True)
        self.seq_log = tk.Text(cornice_log, height=5, wrap="word", state="disabled",
                               bg=CARD_ALT, fg=TESTO, font=(F_MONO, 9), borderwidth=0,
                               highlightthickness=0, padx=10, pady=8, spacing3=2)
        sb2 = ttk.Scrollbar(cornice_log, command=self.seq_log.yview)
        self.seq_log.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self.seq_log.pack(fill="both", expand=True)
        for tag, colore in (("ora", "#5d6673"), ("ok", OK), ("err", ALLARME),
                            ("warn", AVVISO), ("titolo", ACCENTO),
                            ("normale", TESTO)):
            self.seq_log.tag_configure(tag, foreground=colore)

        self._seq_ridisegna()
        self._seq_cambia_azione()          # stato iniziale dei campi
        self._seq_applica_opzioni(self.opzioni_iniziali)
        if self.passi:
            self._seq_scrivi("[ok] sequenza precedente caricata: %d passi"
                             % len(self.passi))
        if self.file_spostati:
            self._seq_scrivi("[ok] file messi in ordine nelle cartelle: %s"
                             % ", ".join("%s -> %s" % coppia
                                         for coppia in self.file_spostati))

    # ------------------------------------------------------------- sequenza
    def _seq_scrivi(self, testo):
        self.coda.put(("seqlog", testo))

    def _seq_etichetta(self, valore):
        return dict((v, e) for e, v in self.AZIONI_SEQ).get(valore, valore)

    def _seq_valore(self, etichetta):
        return dict(self.AZIONI_SEQ).get(etichetta, "click")

    def _seq_cambia_azione(self, _evento=None):
        """Spegne i campi che non c'entrano con l'azione scelta: se un'azione non
        usa l'immagine, il menu delle immagini non deve nemmeno essere toccabile."""
        azione = self._seq_valore(self.seq_azione.get())
        senza_immagine = azione in motore.AZIONI_SENZA_IMMAGINE
        spento = "disabled"

        self.combo_seq_immagine.configure(state=spento if senza_immagine
                                          else "readonly")
        self.etichetta_immagine.configure(
            text="Immagine (non serve)" if senza_immagine else "Immagine")
        for chiave in ("timeout", "soglia"):
            self.campi_seq[chiave].configure(state=spento if senza_immagine
                                             else "normal")
        self.chk_seq_ripeti.configure(state=spento if senza_immagine else "normal")
        if senza_immagine:
            self.seq_ripeti_finche.set(False)

        # condizione e trascina usano immagine/timeout/soglia ma non il tasto ne'
        # "ripeti" (la 2a scelta si fa in una finestra a parte, con Aggiungi)
        if azione in ("condizione", "trascina"):
            self.chk_seq_ripeti.configure(state=spento)
            self.seq_ripeti_finche.set(False)
        if azione == "trascina":
            self.etichetta_immagine.configure(text="Immagine di partenza")

        # lo scostamento serve solo quando si clicca davvero su un'immagine
        clicca = azione in ("click", "doppio", "destro")
        for ch in ("dx", "dy"):
            self.campi_seq[ch].configure(state="normal" if clicca else spento)

        # per "trascina" al posto del campo testo mostro la tendina dell'arrivo
        if azione == "trascina":
            self.campi_seq["tasto"].grid_remove()
            self.combo_seq_arrivo["values"] = list(self.combo_seq_immagine["values"])
            self.combo_seq_arrivo.grid()
            self.etichette_seq["tasto"].configure(text="Immagine di arrivo")
        else:
            self.combo_seq_arrivo.grid_remove()
            self.campi_seq["tasto"].grid()
            self.campi_seq["tasto"].configure(
                state=spento if azione in ("pausa", "condizione") else "normal")
            etichette = {"tasto": "Tasto o testo", "scrivi": "Testo da scrivere",
                         "scroll_giu": "Quante tacche", "scroll_su": "Quante tacche",
                         "spegni": "Fra quanti secondi",
                         "condizione": "(rami: alla conferma)"}
            self.etichette_seq["tasto"].configure(
                text=etichette.get(azione, "Tasto o testo"))
        self._seq_prev_form_aggiorna()

    def _seq_prev_form_aggiorna(self):
        """Mostra nell'anteprima del form l'immagine scelta nella tendina."""
        azione = self._seq_valore(self.seq_azione.get())
        usa = azione not in motore.AZIONI_SENZA_IMMAGINE
        nome = self.v_seq_immagine.get().strip() if usa else ""
        tk_img = self._carica_anteprima(nome, 80, 80)
        self.seq_prev_form_tk = tk_img
        self.seq_prev_form.configure(image=tk_img if tk_img else "")

    def _seq_prev_passo_aggiorna(self, _evento=None):
        """Mostra l'anteprima dell'immagine del passo selezionato nella tabella."""
        i = self._seq_selezionato()
        nome = ""
        if i is not None and 0 <= i < len(self.passi):
            p = self.passi[i]
            if p["azione"] not in motore.AZIONI_SENZA_IMMAGINE:
                nome = p.get("immagine", "")
        tk_img = self._carica_anteprima(nome, 116, 80)
        self.seq_prev_passo_tk = tk_img
        if tk_img:
            self.seq_prev_passo.configure(image=tk_img, text="")
            self.seq_prev_passo_info.configure(text=nome)
        else:
            self.seq_prev_passo.configure(image="",
                                          text="(nessuna\nimmagine)", fg=SPENTO)
            self.seq_prev_passo_info.configure(text="")

    def _seq_sequenze_disponibili(self):
        """Le sequenze della cartella sequenze/, da offrire come rami di una
        condizione (solo il nome del file: il motore le cerca li' dentro)."""
        return self._img_file_sequenza()

    def _seq_dialogo_condizione(self, allora="", altrimenti=""):
        """Finestrella per scegliere le due sequenze-ramo. Ritorna
        (allora, altrimenti) coi nomi file, oppure None se si annulla."""
        disp = ["(niente)"] + self._seq_sequenze_disponibili()
        fin = tk.Toplevel(self.root)
        fin.title("Condizione: cosa fare nei due casi")
        fin.configure(bg=CARD)
        fin.resizable(False, False)
        fin.transient(self.root)
        tk.Label(fin, bg=CARD, fg=TESTO, font=(F, 10), justify="left",
                 padx=18, pady=(16, 6),
                 text="Se l'immagine C'E' a schermo eseguo una sequenza, se NON "
                      "c'e' un'altra.\nScegli quali (crea prima le sequenze-ramo "
                      "nella scheda e salvale).").pack(anchor="w")
        v_si = tk.StringVar(value=allora or "(niente)")
        v_no = tk.StringVar(value=altrimenti or "(niente)")
        for etichetta, var in (("Se C'E'  ->  esegui:", v_si),
                               ("Se NON c'e'  ->  esegui:", v_no)):
            riga = tk.Frame(fin, bg=CARD)
            riga.pack(fill="x", padx=18, pady=4)
            tk.Label(riga, text=etichetta, bg=CARD, fg=SPENTO, font=(F, 9),
                     width=20, anchor="w").pack(side="left")
            ttk.Combobox(riga, textvariable=var, state="readonly", font=(F, 9),
                         width=34, values=disp).pack(side="left")
        scelta = {}
        barra = tk.Frame(fin, bg=CARD)
        barra.pack(fill="x", padx=18, pady=(12, 16))

        def conferma():
            scelta["ok"] = True
            fin.destroy()

        ttk.Button(barra, text="OK", style="Accento.TButton", cursor="hand2",
                   command=conferma).pack(side="right")
        ttk.Button(barra, text="Annulla", cursor="hand2",
                   command=fin.destroy).pack(side="right", padx=(0, 8))
        fin.grab_set()
        fin.focus_force()
        self.root.wait_window(fin)
        if not scelta.get("ok"):
            return None
        pulisci = lambda v: "" if v == "(niente)" else v
        return pulisci(v_si.get()), pulisci(v_no.get())

    def _seq_aggiorna_immagini(self, nomi):
        if hasattr(self, "combo_seq_arrivo"):
            self.combo_seq_arrivo["values"] = nomi
        precedente = self.combo_seq_immagine.get()
        self.combo_seq_immagine["values"] = nomi
        if precedente in nomi:
            self.combo_seq_immagine.set(precedente)
        elif nomi:
            self.combo_seq_immagine.current(0)
        else:
            self.combo_seq_immagine.set("")
        if hasattr(self, "seq_prev_form"):
            self._seq_prev_form_aggiorna()

    def _opzioni_correnti(self):
        """Le impostazioni di esecuzione, salvate INSIEME ai passi: cosi' il
        lanciatore autonomo esegue la sequenza esattamente come la vedi qui."""
        return {
            "ripeti": self._numero(self.seq_ripeti, 1, intero=True),
            "prima": max(self._numero(self.seq_attesa_iniziale, 0), 0),
            "se_manca": self.seq_se_manca.get(),
            "zona": self.zona,
            "monitor": self._monitor(),
            "colore": bool(self.v_colore.get()),
        }

    def _seq_applica_opzioni(self, o):
        """Rimette nei campi le opzioni lette dal file."""
        self.seq_ripeti.set(str(int(o.get("ripeti", 1))))
        self.seq_attesa_iniziale.set("%g" % float(o.get("prima", 3)))
        if o.get("se_manca") in self.seq_se_manca["values"]:
            self.seq_se_manca.set(o["se_manca"])
        if o.get("zona"):
            self.coda.put(("zona", tuple(o["zona"])))
        if o.get("colore"):
            self.v_colore.set(True)
        for i, (indice, _) in enumerate(self.monitor_valori):
            if indice == int(o.get("monitor", 0)):
                self.combo_monitor.current(i)
                break

    def _seq_salva_auto(self, percorso=None):
        try:
            motore.salva(percorso or self.file_sequenza, self.passi,
                           self._opzioni_correnti())
        except OSError as e:
            self._seq_scrivi("[x] non riesco a salvare: %s" % e)

    def _seq_ridisegna(self):
        self.albero.delete(*self.albero.get_children())
        for i, p in enumerate(self.passi):
            pausa = p["azione"] in motore.AZIONI_SENZA_IMMAGINE
            cond = p["azione"] == "condizione"
            if cond:                     # mostro i due rami al posto di "tasto"
                col_tasto = "SI:%s | NO:%s" % (p.get("allora") or "-",
                                               p.get("altrimenti") or "-")
            elif p["azione"] == "trascina":
                col_tasto = "-> %s" % (p.get("immagine2") or "?")
            else:
                col_tasto = p["tasto"] or "—"
            dx, dy = int(p.get("dx", 0)), int(p.get("dy", 0))
            etichetta_img = "—" if pausa else p["immagine"]
            if (dx or dy) and p["azione"] in ("click", "doppio", "destro"):
                etichetta_img += "  (%+d,%+d)" % (dx, dy)
            self.albero.insert("", "end", iid=str(i), values=(
                i + 1,
                etichetta_img,
                self._seq_etichetta(p["azione"]),
                "finche' c'e'" if (p.get("ripeti_finche") and not pausa) else "—",
                col_tasto,
                "%g s" % p["attesa"],
                "—" if pausa else "%g s" % p["timeout"],
                "—" if pausa else "%.2f" % p["soglia"],
            ))

    def _seq_evidenzia(self, i):
        if 0 <= i < len(self.albero.get_children()):
            self.albero.selection_set(str(i))
            self.albero.see(str(i))

    def _seq_selezionato(self):
        sel = self.albero.selection()
        return int(sel[0]) if sel else None

    def _seq_doppio_click(self, evento):
        """Doppio click sulla colonna Ripeti: accende o spegne il ciclo del passo.
        Doppio click altrove: porta il passo su nel modulo per modificarlo."""
        riga = self.albero.identify_row(evento.y)
        if not riga:
            return
        i = int(riga)
        if self.albero.identify_column(evento.x) == "#4":
            if self.passi[i]["azione"] in motore.AZIONI_SENZA_IMMAGINE:
                return
            self.passi[i]["ripeti_finche"] = not self.passi[i].get("ripeti_finche")
            self._seq_ridisegna()
            self._seq_evidenzia(i)
            self._seq_salva_auto()
            return
        self._seq_modifica_passo(i)

    def _seq_modo_modifica(self, indice):
        """Passa fra 'sto aggiungendo un passo nuovo' e 'sto correggendo il n.X'."""
        self.seq_modifica = indice
        titolo = getattr(self.card_passo, "etichetta_titolo", None)
        if indice is None:
            self.b_seq_aggiungi.configure(text="+  Aggiungi")
            self.b_seq_annulla.grid_remove()
            if titolo:
                titolo.configure(text="AGGIUNGI UN PASSO", foreground=SPENTO)
        else:
            self.b_seq_aggiungi.configure(text="Salva il passo %d" % (indice + 1))
            self.b_seq_annulla.grid()
            if titolo:
                titolo.configure(text="STAI MODIFICANDO IL PASSO %d" % (indice + 1),
                                 foreground=ACCENTO)

    def _seq_modifica_passo(self, i=None):
        """Riporta un passo dell'elenco nei campi in alto, pronto da correggere."""
        if i is None:
            i = self._seq_selezionato()
        if i is None or not (0 <= i < len(self.passi)):
            messagebox.showinfo("ScreenAgent",
                                "Scegli prima un passo dall'elenco (o fai doppio "
                                "click sulla sua riga).")
            return
        p = self.passi[i]
        self.seq_azione.set(self._seq_etichetta(p["azione"]))
        self._seq_cambia_azione()          # sistema quali campi sono attivi
        self.v_seq_immagine.set(p["immagine"])
        self.seq_tasto.set(p["tasto"])
        self.v_seq_arrivo.set(p.get("immagine2", ""))   # arrivo del trascinamento
        self.seq_dx.set(str(int(p.get("dx", 0))))
        self.seq_dy.set(str(int(p.get("dy", 0))))
        self.seq_attesa.set("%g" % p["attesa"])
        self.seq_timeout.set("%g" % p["timeout"])
        self.seq_soglia.set("%g" % p["soglia"])
        self.seq_ripeti_finche.set(bool(p.get("ripeti_finche")))
        self._seq_prev_form_aggiorna()     # l'immagine e' cambiata dopo cambia_azione
        self._seq_evidenzia(i)
        self._seq_modo_modifica(i)

    def _seq_aggiungi(self):
        azione = self._seq_valore(self.seq_azione.get())
        immagine = self.combo_seq_immagine.get().strip()
        if azione not in motore.AZIONI_SENZA_IMMAGINE and not immagine:
            messagebox.showwarning("ScreenAgent",
                                   "Scegli prima un'immagine. Le azioni di tastiera, "
                                   "testo, scorrimento e pausa non ne hanno bisogno.")
            return
        if azione in ("tasto", "scrivi") and not self.seq_tasto.get().strip():
            messagebox.showwarning("ScreenAgent",
                                   "Scrivi nel campo \"Tasto o testo\" che cosa deve "
                                   "premere o scrivere.")
            return
        if azione == "spegni" and self.seq_modifica is None:
            secondi = self._numero(self.seq_tasto, motore.ATTESA_SPEGNIMENTO,
                                   intero=True)
            if not messagebox.askyesno(
                    "Spegnimento del PC",
                    "Questo passo SPEGNE davvero il computer, %d secondi dopo "
                    "essere stato eseguito.\n\nFinche' non si spegne puoi "
                    "annullare da un terminale con:\n    shutdown /a\n\n"
                    "Lo aggiungo alla sequenza?" % secondi):
                return
        attuale = (self.passi[self.seq_modifica]
                   if self.seq_modifica is not None else {})
        allora = altrimenti = immagine2 = ""
        if azione == "condizione":
            rami = self._seq_dialogo_condizione(attuale.get("allora", ""),
                                                attuale.get("altrimenti", ""))
            if rami is None:            # annullato
                return
            allora, altrimenti = rami
        if azione == "trascina":
            immagine2 = self.v_seq_arrivo.get().strip()
            if not immagine2:
                messagebox.showwarning("ScreenAgent",
                                       "Scegli l'immagine di arrivo del "
                                       "trascinamento dalla seconda tendina.")
                return
            if immagine2 == immagine:
                messagebox.showwarning("ScreenAgent",
                                       "Partenza e arrivo sono la stessa immagine: "
                                       "scegline una diversa per l'arrivo.")
                return
        passo = {
            # per le azioni che non guardano lo schermo l'immagine non va salvata:
            # nel file resterebbe un nome che non viene mai usato
            "immagine": "" if azione in motore.AZIONI_SENZA_IMMAGINE else immagine,
            "azione": azione,
            "tasto": "" if azione == "condizione" else self.seq_tasto.get().strip(),
            "attesa": max(self._numero(self.seq_attesa, 1.0), 0),
            "timeout": max(self._numero(self.seq_timeout, 10.0), 0),
            "soglia": self._numero(self.seq_soglia, 0.85),
            "ripeti_finche": bool(self.seq_ripeti_finche.get()),
            "allora": allora,
            "altrimenti": altrimenti,
            "immagine2": immagine2,
            "dx": self._numero(self.seq_dx, 0, intero=True),
            "dy": self._numero(self.seq_dy, 0, intero=True),
        }
        if self.seq_modifica is not None:          # sto correggendo un passo
            i = self.seq_modifica
            self.passi[i] = passo
            self._seq_modo_modifica(None)
            self._seq_scrivi("[ok] passo %d aggiornato" % (i + 1))
        else:
            self.passi.append(passo)
            i = len(self.passi) - 1
        self._seq_ridisegna()
        self._seq_evidenzia(i)
        self._seq_salva_auto()

    def _seq_rimuovi(self):
        i = self._seq_selezionato()
        if i is None:
            return
        self._seq_modo_modifica(None)   # gli indici cambiano: esco dalla modifica
        self.passi.pop(i)
        self._seq_ridisegna()
        self._seq_evidenzia(min(i, len(self.passi) - 1))
        self._seq_salva_auto()

    def _seq_sposta(self, delta):
        i = self._seq_selezionato()
        if i is None:
            return
        j = i + delta
        if not (0 <= j < len(self.passi)):
            return
        self._seq_modo_modifica(None)   # gli indici cambiano: esco dalla modifica
        self.passi[i], self.passi[j] = self.passi[j], self.passi[i]
        self._seq_ridisegna()
        self._seq_evidenzia(j)
        self._seq_salva_auto()

    def _seq_prova_passo(self):
        """Cerca l'immagine del passo selezionato e disegna il mirino dove
        cliccherebbe, SENZA cliccare: per verificare un passo mentre lo costruisci."""
        i = self._seq_selezionato()
        if i is None or not (0 <= i < len(self.passi)):
            messagebox.showinfo("ScreenAgent",
                                "Scegli prima un passo dall'elenco da provare.")
            return
        p = dict(self.passi[i])
        if p["azione"] in motore.AZIONI_SENZA_IMMAGINE:
            messagebox.showinfo("ScreenAgent",
                                "Questo passo non cerca nessuna immagine, "
                                "non c'e' niente da provare a schermo.")
            return
        cfg = {"zona": self.zona, "monitor": self._monitor(),
               "colore": bool(self.v_colore.get())}

        def una(nome, dx=0, dy=0, etichetta=""):
            ris = agent.locate_many([nome], p["soglia"], region=cfg["zona"],
                                    monitor=cfg["monitor"], colore=cfg["colore"])
            if not ris:
                self._seq_scrivi("[x] prova%s: '%s' NON trovata (soglia %.2f)"
                                 % (etichetta, nome, p["soglia"]))
                return
            _, (x, y), score = ris[0]
            x, y = x + dx, y + dy
            self.chiedi_mirino(x, y, durata=1200)
            self._seq_scrivi("[ok] prova%s: '%s' in (%d, %d)  match %.2f"
                             % (etichetta, nome, x, y, score))

        def lavoro():
            self._seq_scrivi("--- provo il passo %d (%s) ---"
                             % (i + 1, motore.descrivi(p)))
            try:
                if p["azione"] == "trascina":
                    una(p["immagine"], etichetta=" partenza")
                    if p.get("immagine2"):
                        una(p["immagine2"], etichetta=" arrivo")
                elif p["azione"] == "condizione":
                    una(p["immagine"], etichetta=" (condizione)")
                else:
                    una(p["immagine"], int(p.get("dx", 0)), int(p.get("dy", 0)))
            except SystemExit as e:
                self._seq_scrivi("[x] %s" % e)
            except Exception as e:
                self._seq_scrivi("[x] errore nella prova: %s" % e)
        self._seq_parti(lavoro, "provo il passo...")

    def _seq_trascina(self, da, a):
        """Un passo trascinato con il mouse da una posizione all'altra."""
        self._seq_modo_modifica(None)
        self.passi.insert(a, self.passi.pop(da))
        self._seq_ridisegna()
        self._seq_evidenzia(a)

    def _seq_unisci(self):
        """Attacca in fondo i passi di un'altra sequenza."""
        p = filedialog.askopenfilename(parent=self.root,
                                       initialdir=self._cartella_sequenze(),
                                       title="Unisci una sequenza a questa",
                                       filetypes=[("Sequenza", "*.json")])
        if not p:
            return
        passi, _ = motore.leggi(p)
        if not passi:
            messagebox.showwarning("ScreenAgent", "Quel file non contiene passi.")
            return
        self._seq_modo_modifica(None)
        self.passi.extend(passi)
        self._seq_ridisegna()
        self._seq_evidenzia(len(self.passi) - 1)
        self._seq_salva_auto()
        self._seq_scrivi("[ok] aggiunti %d passi da %s (ora sono %d in tutto)"
                         % (len(passi), os.path.basename(p), len(self.passi)))

    def _seq_su(self):
        self._seq_sposta(-1)

    def _seq_giu(self):
        self._seq_sposta(1)

    def _seq_svuota(self):
        if not self.passi:
            return
        if not messagebox.askyesno("ScreenAgent",
                                   "Cancellare tutti i %d passi?" % len(self.passi)):
            return
        self._seq_modo_modifica(None)
        self.passi = []
        self._seq_ridisegna()
        self._seq_salva_auto()

    def _cartella_sequenze(self):
        """La cartella sequenze/, creata se manca: le finestre Apri/Salva
        partono da qui, cosi' una sequenza nuova finisce nel posto giusto."""
        os.makedirs(SEQ_DIR, exist_ok=True)
        return SEQ_DIR

    def _seq_salva_file(self):
        p = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json",
                                         initialdir=self._cartella_sequenze(),
                                         title="Salva la sequenza",
                                         filetypes=[("Sequenza", "*.json")])
        if p:
            self._seq_salva_auto(p)
            dove = os.path.relpath(p, QUI) if os.path.normcase(
                os.path.abspath(p)).startswith(os.path.normcase(QUI)) else p
            self._seq_scrivi("[ok] salvata in %s" % dove)

    def _seq_apri_file(self):
        p = filedialog.askopenfilename(parent=self.root,
                                       initialdir=self._cartella_sequenze(),
                                       title="Apri una sequenza",
                                       filetypes=[("Sequenza", "*.json")])
        if not p:
            return
        passi, opzioni = motore.leggi(p)
        if not passi:
            messagebox.showwarning("ScreenAgent", "Quel file non contiene passi validi.")
            return
        self._seq_modo_modifica(None)
        self.passi = passi
        self._seq_ridisegna()
        self._seq_applica_opzioni(opzioni)
        self._seq_salva_auto()
        self._seq_scrivi("[ok] caricata %s: %d passi"
                         % (os.path.basename(p), len(passi)))

    # ------------------------------------------------- esecuzione sequenza
    def _seq_occupato(self):
        return self.seq_worker is not None and self.seq_worker.is_alive()

    def _seq_pulsanti(self, attivo):
        self.seq_b_avvia.configure(state="normal" if attivo else "disabled")
        self.seq_b_ferma.configure(state="disabled" if attivo else "normal")

    def _seq_parti(self, funzione, stato):
        if self._seq_occupato():
            messagebox.showinfo("ScreenAgent", "La sequenza e' gia' in esecuzione.")
            return
        self.seq_stop.clear()
        self._seq_pulsanti(attivo=False)
        self.stato.configure(text=stato, fg=TESTO)
        self.spia.configure(fg=ACCENTO)
        if self.v_riduci.get():
            self.root.iconify()

        def involucro():
            try:
                funzione()
            except SystemExit as e:
                self._seq_scrivi("[x] %s" % e)
            except actions.pyautogui.FailSafeException:
                self._seq_scrivi("[x] FAILSAFE: mouse nell'angolo, tutto fermato")
            except Exception as e:
                self._seq_scrivi("[x] errore: %s" % e)
            finally:
                self.coda.put(("seqfine", None))

        self.seq_worker = threading.Thread(target=involucro, daemon=True)
        self.seq_worker.start()

    def _seq_fine(self):
        self._seq_pulsanti(attivo=True)
        self.stato.configure(text="pronto", fg=SPENTO)
        self.spia.configure(fg=SPENTO)
        self.root.deiconify()
        self.root.lift()

    def _seq_ferma(self):
        self.seq_stop.set()
        self.stato.configure(text="mi fermo...", fg=AVVISO)
        self.spia.configure(fg=AVVISO)
        self._seq_scrivi("[i] richiesta di stop...")

    def _seq_avvia(self):
        """Esegue la sequenza con il motore condiviso di motore.py: lo stesso
        che usa il lanciatore autonomo, cosi' i due non possono divergere."""
        if not self.passi:
            messagebox.showwarning("ScreenAgent",
                                   "La sequenza e' vuota: aggiungi almeno un passo.")
            return
        # attenzione al nome: 'motore' e' il modulo, non usarlo come variabile
        su_click = self.chiedi_mirino if self.v_seq_mirino.get() else None
        esecutore = motore.Sequenza(
            self.passi, self._opzioni_correnti(),
            log=self._seq_scrivi, stop=self.seq_stop,
            su_passo=lambda i: self.coda.put(("seqpasso", i)),
            su_click=su_click)
        self._seq_parti(esecutore.esegui, "sequenza in corso...")

    # ======================================================== scheda CATENA
    def _tab_catena(self, parent):
        corpo = ttk.Frame(parent, style="Sfondo.TFrame")
        corpo.pack(fill="both", expand=True, pady=(10, 0))

        centro = ttk.Frame(corpo, style="Sfondo.TFrame")
        centro.pack(fill="both", expand=True)

        c_lista = self._card(centro, "sequenze da eseguire, in quest'ordine",
                             side="left", fill="both", expand=True)
        cornice = tk.Frame(c_lista, bg=CARD_ALT, highlightthickness=1,
                           highlightbackground=BORDO)
        cornice.pack(fill="both", expand=True)
        self.cat_albero = ttk.Treeview(cornice, columns=("n", "file", "passi", "note"),
                                       show="headings", height=7, selectmode="browse")
        for col, testo, largh, anc in (("n", "#", 32, "center"),
                                       ("file", "Sequenza", 300, "w"),
                                       ("passi", "Passi", 70, "center"),
                                       ("note", "Note", 220, "w")):
            self.cat_albero.heading(col, text=testo, anchor=anc)
            self.cat_albero.column(col, width=largh, anchor=anc,
                                   stretch=(col == "file"))
        sb = ttk.Scrollbar(cornice, command=self.cat_albero.yview)
        self.cat_albero.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cat_albero.pack(fill="both", expand=True, padx=2, pady=2)
        abilita_trascinamento(self.cat_albero, self._cat_trascina, self._cat_salva)

        ttk.Label(c_lista, style="Spento.TLabel",
                  text="Trascina le righe col mouse per cambiare l'ordine. Ogni "
                       "sequenza tiene le sue impostazioni (soglia, zona, "
                       "ripetizioni); l'attesa iniziale la decide la catena.").pack(
            anchor="w", pady=(6, 0))

        col_b = ttk.Frame(centro, style="Sfondo.TFrame")
        col_b.pack(side="left", fill="y", padx=(12, 0))
        for testo, comando in (("+ Aggiungi...", self._cat_aggiungi),
                               ("▲  Su", self._cat_su),
                               ("▼  Giu'", self._cat_giu),
                               ("Rimuovi", self._cat_rimuovi),
                               ("Svuota", self._cat_svuota)):
            ttk.Button(col_b, text=testo, style="Piccolo.TButton", cursor="hand2",
                       width=14, command=comando).pack(fill="x", pady=(0, 6))

        # ---- esecuzione
        c_run = self._card(corpo, "esecuzione", fill="x", pady=(12, 0))
        riga = ttk.Frame(c_run, style="Card.TFrame")
        riga.pack(fill="x")
        self.cat_ripeti = tk.StringVar(value="1")
        self.cat_prima = tk.StringVar(value="3")
        self.cat_continua = tk.BooleanVar(value=False)
        ttk.Label(riga, text="Ripeti tutta la catena (0 = all'infinito)",
                  style="Spento.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(riga, textvariable=self.cat_ripeti, width=6,
                  font=(F_MONO, 9)).pack(side="left", padx=(0, 18))
        ttk.Label(riga, text="Attesa prima di partire (s)",
                  style="Spento.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(riga, textvariable=self.cat_prima, width=6,
                  font=(F_MONO, 9)).pack(side="left")
        ttk.Checkbutton(c_run, variable=self.cat_continua,
                        text="Se una sequenza fallisce, passa comunque alla "
                             "successiva").pack(anchor="w", pady=(8, 0))

        barra = ttk.Frame(corpo, style="Sfondo.TFrame")
        barra.pack(fill="x", pady=12)
        self.cat_b_avvia = ttk.Button(barra, text="▶  Avvia catena",
                                      style="Accento.TButton", cursor="hand2",
                                      command=self._cat_avvia)
        self.cat_b_avvia.pack(side="left")
        self.cat_b_ferma = ttk.Button(barra, text="■  Ferma", style="Pericolo.TButton",
                                      cursor="hand2", state="disabled",
                                      command=self._cat_ferma)
        self.cat_b_ferma.pack(side="left", padx=8)
        ttk.Label(barra, style="Sottotitolo.TLabel",
                  text="   da riga di comando: python motore.py prima.json "
                       "seconda.json").pack(side="left")

        # ---- registro
        c_log = self._card(corpo, "registro", fill="x", pady=(0, 14))
        cornice_log = tk.Frame(c_log, bg=CARD_ALT, highlightthickness=1,
                               highlightbackground=BORDO)
        cornice_log.pack(fill="both", expand=True)
        self.cat_log = tk.Text(cornice_log, height=6, wrap="word", state="disabled",
                               bg=CARD_ALT, fg=TESTO, font=(F_MONO, 9), borderwidth=0,
                               highlightthickness=0, padx=10, pady=8, spacing3=2)
        sb2 = ttk.Scrollbar(cornice_log, command=self.cat_log.yview)
        self.cat_log.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self.cat_log.pack(fill="both", expand=True)
        for tag, colore in (("ora", "#5d6673"), ("ok", OK), ("err", ALLARME),
                            ("warn", AVVISO), ("titolo", ACCENTO),
                            ("normale", TESTO)):
            self.cat_log.tag_configure(tag, foreground=colore)

        self.cat_ripeti.set(str(int(self.opzioni_catena.get("ripeti", 1))))
        self.cat_prima.set("%g" % float(self.opzioni_catena.get("prima", 3)))
        self.cat_continua.set(bool(self.opzioni_catena.get("continua", False)))
        self._cat_ridisegna()
        if self.catena:
            self._cat_scrivi("[ok] catena precedente caricata: %d sequenze"
                             % len(self.catena))

    # --------------------------------------------------------------- catena
    def _cat_scrivi(self, testo):
        self.coda.put(("catlog", testo))

    def _cat_percorso(self, nome):
        return percorsi.sequenza(nome)      # nome semplice -> dentro sequenze/

    def _cat_nome_corto(self, percorso):
        """Le sequenze della cartella sequenze/ le tengo col nome semplice,
        cosi' la catena resta valida anche se sposti tutta la cartella."""
        dove = os.path.normcase(os.path.dirname(os.path.abspath(percorso)))
        if dove in (os.path.normcase(SEQ_DIR), os.path.normcase(QUI)):
            return os.path.basename(percorso)
        return percorso

    def _cat_opzioni(self):
        return {"ripeti": self._numero(self.cat_ripeti, 1, intero=True),
                "prima": max(self._numero(self.cat_prima, 0), 0),
                "continua": bool(self.cat_continua.get())}

    def _cat_salva(self):
        try:
            motore.salva_catena(self.file_catena, self.catena, self._cat_opzioni())
        except OSError as e:
            self._cat_scrivi("[x] non riesco a salvare la catena: %s" % e)

    def _cat_ridisegna(self):
        self.cat_albero.delete(*self.cat_albero.get_children())
        for i, nome in enumerate(self.catena):
            passi, _ = motore.leggi(self._cat_percorso(nome))
            self.cat_albero.insert("", "end", iid=str(i), values=(
                i + 1, nome, len(passi) if passi else "—",
                "" if passi else "file mancante o senza passi!"))

    def _cat_evidenzia(self, i):
        if 0 <= i < len(self.cat_albero.get_children()):
            self.cat_albero.selection_set(str(i))
            self.cat_albero.see(str(i))

    def _cat_selezionato(self):
        sel = self.cat_albero.selection()
        return int(sel[0]) if sel else None

    def _cat_aggiungi(self):
        scelti = filedialog.askopenfilenames(
            parent=self.root, initialdir=self._cartella_sequenze(),
            title="Scegli una o piu' sequenze (Ctrl per sceglierne piu' d'una)",
            filetypes=[("Sequenza", "*.json")])
        if not scelti:
            return
        for p in scelti:
            self.catena.append(self._cat_nome_corto(p))
        self._cat_ridisegna()
        self._cat_evidenzia(len(self.catena) - 1)
        self._cat_salva()
        self._cat_scrivi("[ok] aggiunte %d sequenze (ora sono %d)"
                         % (len(scelti), len(self.catena)))

    def _cat_rimuovi(self):
        i = self._cat_selezionato()
        if i is None:
            return
        self.catena.pop(i)
        self._cat_ridisegna()
        self._cat_evidenzia(min(i, len(self.catena) - 1))
        self._cat_salva()

    def _cat_svuota(self):
        if not self.catena:
            return
        if not messagebox.askyesno("ScreenAgent", "Svuotare la catena (%d sequenze)?"
                                   % len(self.catena)):
            return
        self.catena = []
        self._cat_ridisegna()
        self._cat_salva()

    def _cat_sposta(self, delta):
        i = self._cat_selezionato()
        if i is None:
            return
        j = i + delta
        if not (0 <= j < len(self.catena)):
            return
        self.catena[i], self.catena[j] = self.catena[j], self.catena[i]
        self._cat_ridisegna()
        self._cat_evidenzia(j)
        self._cat_salva()

    def _cat_su(self):
        self._cat_sposta(-1)

    def _cat_giu(self):
        self._cat_sposta(1)

    def _cat_trascina(self, da, a):
        self.catena.insert(a, self.catena.pop(da))
        self._cat_ridisegna()
        self._cat_evidenzia(a)

    # ------------------------------------------------- esecuzione catena
    def _cat_occupato(self):
        return self.cat_worker is not None and self.cat_worker.is_alive()

    def _cat_pulsanti(self, attivo):
        self.cat_b_avvia.configure(state="normal" if attivo else "disabled")
        self.cat_b_ferma.configure(state="disabled" if attivo else "normal")

    def _cat_fine(self):
        self._cat_pulsanti(attivo=True)
        self.stato.configure(text="pronto", fg=SPENTO)
        self.spia.configure(fg=SPENTO)
        self.root.deiconify()
        self.root.lift()

    def _cat_ferma(self):
        self.cat_stop.set()
        self.stato.configure(text="mi fermo...", fg=AVVISO)
        self.spia.configure(fg=AVVISO)
        self._cat_scrivi("[i] richiesta di stop...")

    def _cat_avvia(self):
        if not self.catena:
            messagebox.showwarning("ScreenAgent",
                                   "La catena e' vuota: aggiungi almeno una "
                                   "sequenza con + Aggiungi...")
            return
        if self._cat_occupato():
            messagebox.showinfo("ScreenAgent", "La catena e' gia' in esecuzione.")
            return
        opzioni = self._cat_opzioni()
        # (non chiamarla 'percorsi': coprirebbe il modulo omonimo)
        da_eseguire = [self._cat_percorso(n) for n in self.catena]
        self._cat_salva()

        def lavoro():
            motore.esegui_catena(
                da_eseguire, log=self._cat_scrivi, stop=self.cat_stop,
                ripeti=opzioni["ripeti"], prima=opzioni["prima"],
                continua_se_fallisce=opzioni["continua"],
                su_sequenza=lambda i: self.coda.put(("catpasso", i)))

        def involucro():
            try:
                lavoro()
            except SystemExit as e:
                self._cat_scrivi("[x] %s" % e)
            except actions.pyautogui.FailSafeException:
                self._cat_scrivi("[x] FAILSAFE: mouse nell'angolo, tutto fermato")
            except Exception as e:
                self._cat_scrivi("[x] errore: %s" % e)
            finally:
                self.coda.put(("catfine", None))

        self.cat_stop.clear()
        self._cat_pulsanti(attivo=False)
        self.stato.configure(text="catena in corso...", fg=TESTO)
        self.spia.configure(fg=ACCENTO)
        if self.v_riduci.get():
            self.root.iconify()
        self.cat_worker = threading.Thread(target=involucro, daemon=True)
        self.cat_worker.start()

    # ========================================================= scheda MACRO
    def _tab_macro(self, parent):
        corpo = ttk.Frame(parent, style="Sfondo.TFrame")
        corpo.pack(fill="both", expand=True, pady=(10, 0))

        intro = self._card(corpo, "registra e riesegui", fill="x")
        ttk.Label(intro, style="Spento.TLabel", justify="left", wraplength=1040,
                  text="Premi %s (o il pulsante Registra) e compi le azioni: ogni "
                       "click e ogni tasto viene salvato con i suoi tempi. Premi di "
                       "nuovo %s per fermare. La riproduzione rifa' tutto identico, "
                       "nello stesso ordine e alle stesse coordinate."
                       % (self.nome_registra, self.nome_registra)).pack(anchor="w")

        centro = ttk.Frame(corpo, style="Sfondo.TFrame")
        centro.pack(fill="both", expand=True, pady=(12, 0))

        c_lista = self._card(centro, "macro salvate", side="left", fill="both",
                             expand=True)
        cornice = tk.Frame(c_lista, bg=CARD_ALT, highlightthickness=1,
                           highlightbackground=BORDO)
        cornice.pack(fill="both", expand=True)
        self.mac_lista = tk.Listbox(cornice, height=10, exportselection=False,
                                    bg=CARD_ALT, fg=TESTO, font=(F, 10),
                                    selectbackground=ACCENTO,
                                    selectforeground="#08101f",
                                    highlightthickness=0, borderwidth=0,
                                    activestyle="none")
        sb = ttk.Scrollbar(cornice, command=self.mac_lista.yview)
        self.mac_lista.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.mac_lista.pack(fill="both", expand=True, padx=2, pady=2)
        self.mac_lista.bind("<<ListboxSelect>>", self._mac_seleziona)
        self.mac_info = ttk.Label(c_lista, text="nessuna macro selezionata",
                                  style="Dato.TLabel")
        self.mac_info.pack(anchor="w", pady=(8, 0))

        col_b = ttk.Frame(centro, style="Sfondo.TFrame")
        col_b.pack(side="left", fill="y", padx=(12, 0))
        self.mac_b_registra = ttk.Button(col_b, text="●  Registra (%s)"
                                         % self.nome_registra,
                                         style="Accento.TButton", cursor="hand2",
                                         width=16, command=self._mac_toggle_registrazione)
        self.mac_b_registra.pack(fill="x", pady=(0, 6))
        self.mac_b_riproduci = ttk.Button(col_b, text="▶  Riproduci", cursor="hand2",
                                          width=16, command=self._mac_riproduci)
        self.mac_b_riproduci.pack(fill="x", pady=(0, 6))
        self.mac_b_ferma = ttk.Button(col_b, text="■  Ferma", style="Pericolo.TButton",
                                      cursor="hand2", width=16, state="disabled",
                                      command=self._mac_ferma)
        self.mac_b_ferma.pack(fill="x", pady=(0, 6))
        ttk.Frame(col_b, style="Sep.TFrame", height=1).pack(fill="x", pady=6)
        ttk.Button(col_b, text="Rinomina", style="Piccolo.TButton", cursor="hand2",
                   width=16, command=self._mac_rinomina).pack(fill="x", pady=(0, 6))
        ttk.Button(col_b, text="Elimina", style="Piccolo.TButton", cursor="hand2",
                   width=16, command=self._mac_elimina).pack(fill="x")

        c_run = self._card(corpo, "riproduzione", fill="x", pady=(12, 0))
        riga = ttk.Frame(c_run, style="Card.TFrame")
        riga.pack(fill="x")
        self.mac_ripeti = tk.StringVar(value="1")
        self.mac_pausa = tk.StringVar(value="0")
        ttk.Label(riga, text="Ripeti (0 = all'infinito)",
                  style="Spento.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(riga, textvariable=self.mac_ripeti, width=6,
                  font=(F_MONO, 9)).pack(side="left", padx=(0, 18))
        ttk.Label(riga, text="Pausa tra un giro e l'altro (s)",
                  style="Spento.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(riga, textvariable=self.mac_pausa, width=6,
                  font=(F_MONO, 9)).pack(side="left")
        ttk.Checkbutton(c_run, variable=self.v_riduci,
                        text="Riduci a icona la finestra durante la riproduzione "
                             "(consigliato)").pack(anchor="w", pady=(8, 0))

        c_log = self._card(corpo, "registro", fill="both", expand=True, pady=(0, 14))
        cornice_log = tk.Frame(c_log, bg=CARD_ALT, highlightthickness=1,
                               highlightbackground=BORDO)
        cornice_log.pack(fill="both", expand=True)
        self.mac_log = tk.Text(cornice_log, height=6, wrap="word", state="disabled",
                               bg=CARD_ALT, fg=TESTO, font=(F_MONO, 9), borderwidth=0,
                               highlightthickness=0, padx=10, pady=8, spacing3=2)
        sb2 = ttk.Scrollbar(cornice_log, command=self.mac_log.yview)
        self.mac_log.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self.mac_log.pack(fill="both", expand=True)
        for tag, colore in (("ora", "#5d6673"), ("ok", OK), ("err", ALLARME),
                            ("warn", AVVISO), ("titolo", ACCENTO),
                            ("normale", TESTO)):
            self.mac_log.tag_configure(tag, foreground=colore)

        self._mac_aggiorna_lista()
        self._mac_scrivi("Il tasto %s registra anche con la finestra in secondo "
                         "piano." % self.nome_registra)

    # ---------------------------------------------------------------- macro
    def _mac_scrivi(self, testo):
        self.coda.put(("maclog", testo))

    def _mac_percorso(self, nome):
        if not nome.lower().endswith(".json"):
            nome += ".json"
        return os.path.join(self.dir_macro, nome)

    def _mac_occupato(self):
        return self.mac_worker is not None and self.mac_worker.is_alive()

    def _mac_aggiorna_lista(self):
        scelta = self._mac_nome()
        self.mac_lista.delete(0, tk.END)
        os.makedirs(self.dir_macro, exist_ok=True)     # se e' stata cancellata
        # i file che cominciano con "_" non sono macro (es. la registrazione
        # dell'Autoclicker, che ha un altro formato): non li elenco
        nomi = sorted(f[:-5] for f in os.listdir(self.dir_macro)
                      if f.lower().endswith(".json") and not f.startswith("_"))
        for n in nomi:
            self.mac_lista.insert(tk.END, "  " + n)
        if scelta in nomi:
            i = nomi.index(scelta)
            self.mac_lista.selection_set(i)
            self.mac_lista.see(i)
        elif nomi:
            self.mac_lista.selection_set(0)
        self._mac_seleziona()

    def _mac_nome(self):
        sel = self.mac_lista.curselection()
        return self.mac_lista.get(sel[0]).strip() if sel else None

    def _mac_seleziona(self, _evento=None):
        nome = self._mac_nome()
        if not nome:
            self.mac_info.configure(text="nessuna macro selezionata", foreground=SPENTO)
            return
        eventi = clicker.carica(self._mac_percorso(nome))
        if eventi:
            c, durata = registratore.riassunto(eventi)
            self.mac_info.configure(
                text="%s   %.1f s   %d movimenti, %d click, %d rotella, %d tasti"
                     % (nome, durata, c["m"], c["b"], c["w"], c["t"]),
                foreground=TESTO)
        else:
            self.mac_info.configure(text="%s   (vuota o illeggibile)" % nome,
                                    foreground=ALLARME)

    def _mac_pulsanti(self, attivo):
        stato = "normal" if attivo else "disabled"
        self.mac_b_riproduci.configure(state=stato)
        self.mac_b_ferma.configure(state="disabled" if attivo else "normal")
        # il pulsante Registra fa da interruttore: resta sempre premibile
        self.mac_b_registra.configure(
            text=("■  Ferma registrazione" if self.mac_registrando
                  else "●  Registra (%s)" % self.nome_registra))

    # -------------------------------------------------------- registrazione
    def _mac_toggle_registrazione(self):
        """Il cuore della funzione, chiamato da F7 e dal pulsante."""
        if self.mac_registrando:
            self.mac_via_tasto = True       # fermata pulita: niente da tagliare
            self.mac_stop.set()
            return
        if self._mac_occupato():
            return                          # sta gia' facendo altro (riproduzione)
        self.tabs.select(self.idx_macro)
        self.mac_registrando = True
        self.mac_via_tasto = False
        self.mac_stop.clear()
        self._mac_pulsanti(attivo=False)
        self.mac_b_ferma.configure(state="normal")
        self.stato.configure(text="registrazione macro...", fg=ALLARME)
        self.spia.configure(fg=ALLARME)

        def lavoro():
            self._mac_scrivi("--- registrazione avviata: fai le tue azioni, premi "
                             "%s per fermare ---" % self.nome_registra)
            eventi = registratore.registra(
                self.mac_stop, ignora_vk=(self.vk_registra, clicker.VK_ESC))
            self.coda.put(("macregistrata", eventi))

        def involucro():
            try:
                lavoro()
            except Exception as e:
                self._mac_scrivi("[x] errore nella registrazione: %s" % e)
                self.coda.put(("macregistrata", []))
            finally:
                self.coda.put(("macfine", None))

        self.mac_worker = threading.Thread(target=involucro, daemon=True)
        self.mac_worker.start()

    def _mac_registrata(self, eventi):
        """Fine registrazione (thread principale): rifinisce, chiede il nome, salva."""
        self.mac_registrando = False
        if not self.mac_via_tasto:
            # fermata col pulsante: il click d'avvio e quello di stop sono sul
            # pulsante stesso, non fanno parte della macro -> via testa e coda
            eventi = [e for e in eventi if e["t"] >= 0.4]
            eventi = clicker.taglia_coda(eventi)
        if not eventi:
            self._mac_scrivi("[!] non ho registrato nulla")
            return
        self.macro_eventi = eventi
        c, durata = registratore.riassunto(eventi)
        self._mac_scrivi("[ok] registrate %d azioni in %.1f s (%d mov, %d click, "
                         "%d rotella, %d tasti)"
                         % (len(eventi), durata, c["m"], c["b"], c["w"], c["t"]))
        nome = simpledialog.askstring(
            "Salva la macro",
            "Registrate %d azioni (%.1f s).\nNome con cui salvarla:"
            % (len(eventi), durata), parent=self.root)
        if not nome:
            self._mac_scrivi("[i] macro non salvata (registrazione persa)")
            return
        # niente "_" all'inizio: quei nomi sono riservati e non compaiono in elenco
        nome = "".join(c for c in nome.strip()
                       if c.isalnum() or c in " _-").strip().lstrip("_").strip()
        if not nome:
            return
        clicker.salva(eventi, self._mac_percorso(nome))
        self._mac_scrivi("[ok] salvata come '%s' nella cartella macro" % nome)
        self._mac_aggiorna_lista()
        nomi = [self.mac_lista.get(i).strip() for i in range(self.mac_lista.size())]
        if nome in nomi:
            self.mac_lista.selection_clear(0, tk.END)
            self.mac_lista.selection_set(nomi.index(nome))
            self._mac_seleziona()

    def _mac_fine(self):
        self._mac_pulsanti(attivo=True)
        self.stato.configure(text="pronto", fg=SPENTO)
        self.spia.configure(fg=SPENTO)
        self.root.deiconify()
        self.root.lift()

    def _mac_ferma(self):
        self.mac_stop.set()
        self.stato.configure(text="mi fermo...", fg=AVVISO)

    # ------------------------------------------------------- riproduzione
    def _mac_riproduci(self):
        if self._mac_occupato():
            return
        nome = self._mac_nome()
        if not nome:
            messagebox.showinfo("ScreenAgent", "Scegli prima una macro dall'elenco.")
            return
        eventi = clicker.carica(self._mac_percorso(nome))
        if not eventi:
            messagebox.showwarning("ScreenAgent", "Quella macro e' vuota o illeggibile.")
            return
        ripeti = self._numero(self.mac_ripeti, 1, intero=True)
        pausa = max(self._numero(self.mac_pausa, 0), 0)

        def lavoro():
            self._mac_scrivi("--- riproduco '%s' (%d azioni), %s ---"
                             % (nome, len(eventi),
                                "%d volte" % ripeti if ripeti > 0 else "all'infinito"))
            giri = registratore.riproduci(eventi, self.mac_stop, ripetizioni=ripeti,
                                          pausa_tra_giri=pausa)
            self._mac_scrivi("--- riproduzione finita: %d giri ---" % giri)

        def involucro():
            try:
                lavoro()
            except actions.pyautogui.FailSafeException:
                self._mac_scrivi("[x] FAILSAFE: mouse nell'angolo, fermato")
            except Exception as e:
                self._mac_scrivi("[x] errore: %s" % e)
            finally:
                self.coda.put(("macfine", None))

        self.mac_stop.clear()
        self._mac_pulsanti(attivo=False)
        self.stato.configure(text="riproduzione macro...", fg=TESTO)
        self.spia.configure(fg=ACCENTO)
        if self.v_riduci.get():
            self.root.iconify()
        self.mac_worker = threading.Thread(target=involucro, daemon=True)
        self.mac_worker.start()

    def _mac_rinomina(self):
        nome = self._mac_nome()
        if not nome:
            return
        nuovo = simpledialog.askstring("Rinomina", "Nuovo nome per '%s':" % nome,
                                       parent=self.root)
        if not nuovo:
            return
        nuovo = "".join(c for c in nuovo.strip() if c.isalnum() or c in " _-").strip()
        if not nuovo or nuovo == nome:
            return
        try:
            os.replace(self._mac_percorso(nome), self._mac_percorso(nuovo))
        except OSError as e:
            self._mac_scrivi("[x] non riesco a rinominare: %s" % e)
            return
        self._mac_aggiorna_lista()
        self._mac_scrivi("[ok] '%s' -> '%s'" % (nome, nuovo))

    def _mac_elimina(self):
        nome = self._mac_nome()
        if not nome:
            return
        if not messagebox.askyesno("ScreenAgent", "Eliminare la macro '%s'?" % nome):
            return
        try:
            os.remove(self._mac_percorso(nome))
        except OSError as e:
            self._mac_scrivi("[x] non riesco a eliminare: %s" % e)
            return
        self._mac_aggiorna_lista()
        self._mac_scrivi("[ok] eliminata '%s'" % nome)

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
                self._ac_scrivi("[ok] registrate %d azioni in %.1f s (salvate nella "
                                "cartella macro)" % (len(eventi), eventi[-1]["t"]))
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
        """Sorveglia i tasti anche quando la finestra non ha il fuoco: il tasto
        rapido (avvia/ferma) ed ESC, che ferma tutto e basta."""
        prima = False
        prima_esc = False
        prima_f7 = False
        while not self.chiuso.is_set():
            try:
                # "o scattato": cosi' non si perde una pressione breve
                ora = clicker.premuto_o_scattato(self.vk_hotkey)
                esc = clicker.premuto_o_scattato(clicker.VK_ESC)
                f7 = clicker.premuto_o_scattato(self.vk_registra)
            except Exception:
                ora = esc = f7 = False
            if ora and not prima:
                self.coda.put(("hotkey", None))
            if f7 and not prima_f7 and self.vk_registra not in (self.vk_hotkey,
                                                                clicker.VK_ESC):
                self.coda.put(("registra_macro", None))
            if esc and not prima_esc and self.vk_hotkey != clicker.VK_ESC:
                # Fermo SUBITO da qui: alzare gli eventi non tocca l'interfaccia
                # ed e' sicuro da un thread. Passare dalla coda costerebbe fino a
                # un decimo di secondo, che su un freno d'emergenza e' troppo.
                attivi = []
                if self._ac_occupato():
                    attivi.append("autoclicker")
                if self._seq_occupato():
                    attivi.append("sequenza")
                if self._cat_occupato():
                    attivi.append("catena")
                if self.worker is not None and self.worker.is_alive():
                    attivi.append("ricerca")
                if self._mac_occupato():
                    attivi.append("macro")
                for evento in (self.ac_stop, self.seq_stop, self.cat_stop,
                               self.mac_stop, self.stop_event):
                    evento.set()
                self.coda.put(("emergenza", attivi))   # il resto e' solo avviso
            prima, prima_esc, prima_f7 = ora, esc, f7
            time.sleep(0.03)

    def _ferma_tutto(self, attivi):
        """Avvisa che il freno d'emergenza e' scattato (gli stop sono gia' dati)."""
        if not attivi:
            return
        testo = "[x] EMERGENZA (Esc): fermo %s" % ", ".join(attivi)
        for registro in (self.log, self.seq_log, self.cat_log, self.ac_log,
                         self.mac_log):
            self._inserisci_log(registro, testo)
        self.stato.configure(text="fermato con Esc", fg=ALLARME)
        self.spia.configure(fg=ALLARME)

    def _tasto_rapido_premuto(self):
        """Il tasto rapido ferma qualunque cosa stia girando; se non gira niente
        avvia l'autoclicker (come OP Auto Clicker)."""
        if self._ac_occupato():
            self._ac_ferma()
        elif self._seq_occupato():
            self._seq_ferma()
        elif self._cat_occupato():
            self._cat_ferma()
        elif self.worker and self.worker.is_alive():
            self._ferma()
        else:
            self.tabs.select(self.idx_autoclicker)
            self._ac_avvia()

    def _chiudi(self):
        self.stop_event.set()
        self.ac_stop.set()
        self.seq_stop.set()
        self.cat_stop.set()
        self.mac_stop.set()
        self.chiuso.set()
        self.root.destroy()


def main():
    scr.enable_dpi_awareness()
    # dentro l'exe non ci sono i singoli .py: i sotto-strumenti (cattura, appunti,
    # diagnosi, scegli-zona) vengono richiamati rilanciando QUESTO exe con --tool
    if len(sys.argv) >= 3 and sys.argv[1] == "--tool":
        tool, rest = sys.argv[2], sys.argv[3:]
        if tool == "zona":
            import zona
            zona.main()
        elif tool == "diagnosi":
            import diagnosi
            sys.argv = ["diagnosi"] + rest
            diagnosi.main()
        elif tool == "snip":
            import agent
            sys.argv = ["agent", "snip"] + rest
            agent.main()
        elif tool == "incolla":
            import incolla
            sys.argv = ["incolla"] + rest
            incolla.main()
        return
    # identita' propria nella barra delle applicazioni (non quella di Python)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ScreenAgent")
    except Exception:
        pass
    root = tk.Tk()
    try:
        root.iconbitmap(default=percorsi.ICONA)   # icona di finestra e taskbar
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
