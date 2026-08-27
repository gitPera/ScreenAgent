# ScreenAgent

Un agente che **guarda lo schermo**, riconosce un oggetto e ci **clicca sopra**.
Differenza rispetto a MacroRecorder / AutoClicker: quelli cliccano a coordinate fisse,
questo trova l'oggetto ovunque si trovi (finestra spostata, lista che scorre, ecc.).

## Installazione

```
python -m pip install --user -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

(i `--trusted-host` servono perche' Avast intercetta l'SSL su questo PC)

OCR opzionale, serve solo per il comando `text`:
1. `python -m pip install --user pytesseract`
2. installa Tesseract-OCR per Windows (UB-Mannheim build) e aggiungilo al PATH,
   spuntando la lingua italiana durante l'installazione.

## Interfaccia grafica (il modo comodo)

Doppio click su **`ScreenAgent.bat`**, oppure:

```
python ScreenAgent.py
```

Tema scuro, tre riquadri: a sinistra la lista delle immagini, al centro l'**anteprima**
(su scacchiera, cosi' vedi subito se lo sfondo e' trasparente) con dimensioni e
contrasto del ritaglio, a destra l'azione. L'azione si sceglie da un selettore a
segmenti — *Solo cerca*, *Click singolo*, *Doppio click*, *Click destro* — e sotto ci
sono tasto da premere, scostamento, soglia, intervallo, cooldown, max click e schermo.
In fondo il registro colorato: verde le azioni riuscite, giallo gli avvisi, rosso gli
errori. Poi:

| Pulsante | Cosa fa |
|---|---|
| **Cerca** | dice solo se lo vede e dove, non tocca nulla |
| **Esegui una volta** | cerca e fa l'azione una volta sola |
| **Avvia ciclo** | continua finche' non premi FERMA (o il limite "Max click") |
| **Diagnosi** | prova tutte le dimensioni e ti dice perche' non lo trova |
| **Cattura** / **Nuovo dagli appunti** | crea un template nuovo e lo aggiunge alla lista |

"Attesa prima" ti da' i secondi per passare alla finestra giusta, e la spunta
*Riduci a icona* toglie di mezzo ScreenAgent durante l'azione (altrimenti rischi che
riconosca l'immagine dentro la sua stessa anteprima).

### Oggetti che ruotano: cerca per colore

Il confronto pixel per pixel fallisce con tutto cio' che **ruota o si anima**: il
modello e' un fotogramma solo, e l'oggetto girato di 40 gradi non gli somiglia piu'.
Misurato su un oggetto che gira su se' stesso, con 9 esemplari nella stessa
schermata e lo stesso ritaglio usato come modello:

| metodo | soglia | trovati su 9 |
|---|---|---|
| confronto pixel | 0.85 | 1 (solo quello da cui era ritagliato il modello) |
| confronto pixel | 0.70 | 2 |
| **ricerca per colore** | 0.35 | **9** |

Spunta **"Cerca per COLORE"**: dal tuo ritaglio ricava la fascia di colore
(tonalita', saturazione, luminosita') dei pixel luminosi e cerca le macchie di
quel colore, con dimensione simile al modello. La rotazione non conta piu'.

Attenzione a due cose:

1. la **soglia cambia significato**: non e' piu' somiglianza di forma ma di
   *dimensione* rispetto al modello. Usa 0.30-0.50, non 0.85 (la GUI te la
   cambia da sola quando spunti la casella);
2. le **barre degli strumenti** sono piene di icone colorate e verrebbero prese
   per bersagli: restringi con **Scegli zona** alla sola area che ti interessa.
   Da riga di comando: `python zona.py` ti da' le coordinate, poi passale con
   `--zona X Y W H`.

```
python agent.py loop oggetto_rotante --colore --threshold 0.35 --zona 200 190 1500 730
```

### Piu' immagini insieme

Nella lista tieni premuto **Ctrl** (o **Shift**) per selezionarne piu' di una, o usa
**Tutte**. Tutti i pulsanti lavorano sull'intera selezione:

- **Cerca** elenca tutte quelle che vede, con posizione e punteggio;
- **Esegui una volta** e **Avvia ciclo** agiscono su **una sola** per volta, e la
  spunta *"agisci su quella con il punteggio piu' alto"* decide quale:
  spuntata = vince il match migliore; non spuntata = vince **l'ordine della lista**
  dall'alto in basso (utile per dare una priorita': prima il pulsante di
  conferma, poi quello di ripiego);
- **Diagnosi** le esamina una dopo l'altra.

Ogni giro fa **un solo screenshot** e ci confronta tutte le immagini, quindi
aggiungerne una non raddoppia il tempo di scansione. Nel registro trovi sempre il
nome di quella su cui ha agito.

Il ciclo gira in un thread separato: la finestra resta viva e **FERMA** risponde subito.

## Scheda Autoclicker

Riproduce quello che fa OP Auto Clicker 3.0, nello stesso stile del resto.

| | |
|---|---|
| **Intervallo tra i click** | ore, minuti, secondi, millisecondi (si sommano) |
| **Opzioni del click** | pulsante sinistro / centrale / destro, click singolo o doppio |
| **Ripetizioni** | un numero preciso di click, oppure finche' non lo fermi |
| **Posizione** | dove si trova il mouse, oppure un punto fisso X/Y |
| **Scegli punto** | riduce la finestra, il tuo prossimo click definisce X/Y |
| **Tasto rapido** | F6 di default, avvia e ferma; premi il pulsante per cambiarlo |
| **Registra / Riproduci** | registra click e tasti con i loro tempi, poi li riesegue |

Il tasto rapido funziona **anche con la finestra in secondo piano** (legge lo stato
globale dei tasti), come l'originale. Per fermare hai tre strade: il tasto rapido,
il pulsante Ferma, o il mouse nell'angolo in alto a sinistra (failsafe).

I click passano dalle API di Windows invece che da pyautogui, che ha una pausa
interna di sicurezza: cosi' l'intervallo e' rispettato al millisecondo (misurato:
100 ms richiesti → 100.7 ms reali; 10 ms → 10.5 ms; 1 ms → 1.1 ms).

La registrazione salva in `registrazione.json` e viene ricaricata alla riapertura.
Registra premute e rilasci di mouse e tastiera con i tempi originali; la
riproduzione rispetta le pause e ripete quante volte dici nel riquadro Ripetizioni.
Ferma la registrazione **con il tasto rapido**: cosi' il click sul pulsante non
finisce dentro la registrazione (comunque gli ultimi 0.35 s vengono scartati).

## Riga di comando

**0) Guarda che schermi vede:**

```
python agent.py monitors
```

Su questo PC: `--monitor 1` e' l'ASUS a sinistra (coordinate **negative**, da -1920 a 0),
`--monitor 2` e' l'MSI primario (da 0 a 1920). Il default e' `--monitor 0` = tutti e due
insieme, quindi normalmente non devi specificare nulla. Restringere a un solo schermo
serve solo per andare piu' veloce o per evitare che trovi l'oggetto sbagliato sull'altro.

**1) Insegnagli cosa cercare** — ritagli l'oggetto dallo schermo:

```
python agent.py snip pulsante_salva
```

Hai 3 secondi per portare in primo piano la finestra giusta, poi trascini il
rettangolo sull'oggetto e premi INVIO. Finisce in `templates/pulsante_salva.png`.

Consiglio: ritaglia **stretto** sull'oggetto, senza sfondo che cambia
(niente bordi con dietro il desktop, niente parti animate).

**2) Verifica che lo veda** (non clicca, stampa solo le coordinate):

```
python agent.py find pulsante_salva
```

**3) Fallo cliccare:**

```
python agent.py click pulsante_salva
python agent.py click pulsante_salva --wait 30      # aspetta che compaia
python agent.py click pulsante_salva --double
python agent.py click pulsante_salva --threshold 0.8
python agent.py click pulsante_salva --press 1      # click, poi premi il tasto 1
python agent.py click etichetta --offset 0 -69      # clicca 69 px SOPRA il match
```

`--offset DX DY` serve quando la cosa che riconosci bene non e' la cosa che devi
cliccare (es. riconosci un'etichetta di testo stabile e devi colpire l'oggetto
sopra di essa). `--press TASTO` invia un tasto dopo il click (`--press-delay` per
la pausa, default 0.3s); i nomi italiani `invio`, `spazio`, `canc`, `maiusc`
funzionano, e un tasto inesistente da' errore invece di essere ignorato.

**3-bis) Piu' immagini contemporaneamente** — `find`, `click` e `loop` accettano piu'
nomi, cercati tutti nello stesso screenshot:

```
python agent.py find pulsante_ok pulsante_annulla icona_salva
python agent.py click pulsante_ok icona_salva --wait 20
python agent.py loop pulsante_ok pulsante_annulla --best --cooldown 2
```

Senza `--best` vince il **primo dell'elenco** che risulta visibile (= priorita');
con `--best` vince quello col punteggio piu' alto. `find` le elenca tutte.
Anche negli script JSON `"target"` accetta una lista:
`"target": ["pulsante_ok", "icona_salva"]`.

**4) Clicca una scritta invece di un'immagine** (richiede OCR):

```
python agent.py text "Salva"
```

**5) Sequenze di azioni** — scrivi un JSON e lo esegue:

```
python agent.py run script.esempio.json --repeat 5
```

Passi disponibili: `click`, `click_text`, `type`, `key`, `scroll`, `wait`, `wait_for`.

**6) Modalita' interattiva** — gli detti i comandi mentre gira:

```
python agent.py repl
> click pulsante_salva
> type ciao
> key ctrl+s
```

## Regolazioni utili

| Problema | Soluzione |
|---|---|
| Non trova mai l'oggetto | abbassa `--threshold` a 0.75-0.80 |
| Clicca la cosa sbagliata | alza `--threshold` a 0.9+, oppure ritaglia un template piu' distintivo |
| "attenzione: e' quasi tutto di un colore" | il ritaglio non ha dettaglio, verrebbe trovato ovunque: rifallo includendo un bordo, un'icona o del testo |
| L'oggetto cambia dimensione | in `agent.py` metti `SCALES = (0.8, 0.9, 1.0, 1.1, 1.2)` |
| Clicca spostato di qualche cm | e' lo scaling di Windows: `screen.enable_dpi_awareness()` deve girare per primo (gia' fatto in `main()`) |
| Lo schermo e' nero nello screenshot | app in DirectX/fullscreen esclusivo: mettila in modalita' finestra |
| Devi fermare tutto | sposta il mouse nell'angolo in alto a sinistra (failsafe di pyautogui) |

## File

- `screen.py` — cattura schermo (mss) + fix DPI
- `vision.py` — riconoscimento: template matching (OpenCV) e OCR
- `actions.py` — mouse e tastiera (pyautogui)
- `agent.py` — CLI e runner degli script
- `templates/` — le immagini di riferimento che crei con `snip`
