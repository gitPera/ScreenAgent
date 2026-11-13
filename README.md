# ScreenAgent

Un agente che **guarda lo schermo**, riconosce un oggetto e ci **clicca sopra**.
Differenza rispetto a MacroRecorder / AutoClicker: quelli cliccano a coordinate fisse,
questo trova l'oggetto ovunque si trovi (finestra spostata, lista che scorre, ecc.).

## Installazione su un altro PC (senza Python)

Per far girare ScreenAgent su un computer qualsiasi, dove Python non e' installato,
si crea un eseguibile e un installer. Serve una volta sola, sul PC di sviluppo:

1. doppio click su **`build.bat`**. Impacchetta tutto in `dist\ScreenAgent\`
   (`ScreenAgent.exe` + `ScreenAgentRun.exe` e le librerie). Se trovi anche
   **Inno Setup 6** installato, crea pure `Output\ScreenAgent-Setup.exe`.
2. porta sull'altro PC **`ScreenAgent-Setup.exe`** (oppure, senza Inno Setup, la
   cartella `dist\ScreenAgent` zippata) e lancialo.

L'installer e' **per utente**: non chiede l'amministratore e si installa in una
cartella scrivibile (`...\AppData\Local\Programs\ScreenAgent`), cosi' l'app puo'
salvare li' sequenze, macro e immagini. Crea i collegamenti nel menu Start e, se
spuntato, sul desktop.

Dopo l'installazione ScreenAgent e' una **normale applicazione Windows**: si avvia
dal menu Start o dall'icona sul desktop (niente `.bat`), ha la sua icona e compare
in *Impostazioni -> App installate*, da dove si disinstalla. Reinstallare una
versione nuova sopra la vecchia aggiorna il programma **senza toccare** le tue
immagini e sequenze.

**Portarsi dietro i propri dati**: l'app installata parte vuota. Per ritrovare
immagini e sequenze create altrove, copia nella cartella d'installazione la
cartella `templates` (immagini), la cartella `sequenze` (i `.json` delle sequenze),
la cartella `macro` e il file `catena.json`.

**Dove finiscono i dati**: accanto al programma ci sono tre cartelle, create da
sole se mancano (anche se le cancelli mentre l'app e' aperta):

| cartella | contenuto |
|---|---|
| `templates\` | le immagini da riconoscere |
| `sequenze\` | le sequenze: **Salva...** e **Apri...** partono da qui; c'e' anche `sequenza.json`, quella aperta nella scheda |
| `macro\` | le macro registrate con F7 e la registrazione "Record" dell'Autoclicker (`_autoclicker.json`) |

I file che una versione precedente lasciava accanto al programma (`sequenza.json`,
altre sequenze, `registrazione.json`) vengono spostati nella cartella giusta da
soli al primo avvio, senza sovrascrivere niente.

Nota: per trascinare le **icone del desktop** serve comunque avviare ScreenAgent
**come amministratore** (tasto destro -> Esegui come amministratore); e' un limite
di Windows, non dell'installazione.

## Dai sorgenti (sul PC di sviluppo)

Serve Python 3.10+. Installa le dipendenze:

```
python -m pip install --user -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
```

(i `--trusted-host` servono solo se un antivirus o un proxy intercetta le connessioni
SSL e pip da' errori di certificato; altrimenti puoi ometterli)

OCR opzionale, serve solo per il comando `text`:
1. `python -m pip install --user pytesseract`
2. installa Tesseract-OCR per Windows (UB-Mannheim build) e aggiungilo al PATH,
   spuntando la lingua italiana durante l'installazione.

## Interfaccia grafica (il modo comodo)

Se hai installato l'app con `ScreenAgent-Setup.exe`: menu Start -> **ScreenAgent**.
Dai sorgenti: doppio click su **`ScreenAgent.bat`**, oppure:

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

### Trascinamento da immagine a immagine

L'azione **"Trascina su un'altra immagine"** riconosce un'immagine di **partenza**,
ci preme sopra il tasto sinistro, trascina fino a una seconda immagine di
**arrivo** e rilascia. Scegliendo questa azione, al posto del campo "Tasto o testo"
compare una **seconda tendina** per l'immagine di arrivo: partenza e arrivo si
scelgono cosi' da due menu affiancati. Timeout e Soglia valgono per entrambe le
ricerche.

Usa lo stesso trascinamento affidabile delle macro (SendInput, con l'indugio dopo
la pressione che fa riconoscere il drag), quindi funziona anche per le icone del
desktop. Come per tutti i drag di sistema, se trascini icone del desktop puo'
servire avviare ScreenAgent **come amministratore**.

### Passo condizionale (se c'e' l'immagine...)

L'azione **"Se c'e' l'immagine..."** rende la sequenza capace di scegliere: cerca
un'immagine (entro il suo Timeout) e poi esegue **una sequenza salvata** se c'e',
**un'altra** se non c'e'.

Come si usa:
1. crea prima le due sequenze-ramo come sequenze normali e **salvale** (Salva...):
   una col cosa-fare-se-c'e', una col cosa-fare-altrimenti (un ramo puo' anche
   essere "(niente)", cioe' non fare nulla);
2. aggiungi il passo *Se c'e' l'immagine...*, scegli l'immagine, il Timeout (quanto
   cercarla) e la Soglia; alla conferma una finestrella ti fa scegliere le due
   sequenze-ramo.

I rami sono file di sequenza a tutti gli effetti: modificabili da soli e
riutilizzabili. Un ramo puo' contenere a sua volta un passo condizionale (fino a
5 livelli, poi si ferma per non rischiare cicli infiniti). Da riga di comando non
serve nulla di speciale: e' tutto dentro il file della sequenza.

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

## Scheda Sequenza

Per quando le immagini vanno cliccate **in un ordine preciso**: prima questa, poi
quella, con una pausa fra una e l'altra. Tipico caso: una procedura di accesso, o
una serie di finestre da attraversare.

Componi un passo in alto (immagine, azione, tasto da premere dopo, attesa, timeout,
soglia) e premi **+ Aggiungi**: finisce in fondo all'elenco. Con **▲ ▼** lo sposti,
con **Rimuovi** lo togli. L'ordine dell'elenco e' l'ordine di esecuzione.

Accanto al menu "aggiungi un passo" c'e' una piccola **anteprima** dell'immagine
scelta nella tendina; cliccando un passo della sequenza, un'altra anteprima (a
destra della tabella) mostra l'immagine di quel passo, col suo nome.

**Prova passo**: seleziona un passo e premi **Prova passo** per cercarne l'immagine
subito, **senza eseguire tutta la sequenza** e senza cliccare: se la trova disegna
un **mirino rosso** sul punto dove cliccherebbe (scostamento compreso) e scrive nel
registro la posizione e il punteggio. E' il modo veloce per mettere a punto un passo
mentre lo costruisci. Durante un'esecuzione vera, la spunta "Mostra un mirino rosso
dove sta per cliccare" (sotto, in *esecuzione*) fa lampeggiare lo stesso mirino a
ogni click.

**Per cambiare l'ordine** trascina le righe con il mouse (i pulsanti ▲ ▼ restano
per chi li preferisce). Un click secco non sposta niente, quindi selezione e
doppio click continuano a funzionare come prima.

**Per unire due sequenze** premi **Unisci...** e scegli un altro file: i suoi
passi vengono attaccati in fondo a quelli che hai gia'. Comodo per costruirne una
lunga da pezzi gia' collaudati.

**Per correggere un passo gia' inserito** fai doppio click sulla sua riga, oppure
selezionalo e premi **Modifica**: torna su nei campi in alto, il riquadro diventa
"STAI MODIFICANDO IL PASSO N" e il pulsante diventa **Salva il passo N**. Salvi e
torna al suo posto nell'elenco, senza aggiungerne uno nuovo; **Annulla** lascia
tutto com'era. (Doppio click sulla colonna *Ripeti* resta la scorciatoia per
accendere e spegnere il ciclo di quel passo.)

| Campo | Cosa fa |
|---|---|
| **Azione** | vedi la tabella qui sotto |
| **Tasto o testo** | dopo un click: il tasto da premere (es. `invio`, `ctrl+s`). Per le azioni di tastiera, testo e scorrimento e' il valore stesso dell'azione |
| **Attesa dopo** | **il timer**: quanti secondi passano prima del passo successivo |
| **Timeout** | quanto aspetta che l'immagine compaia prima di dichiarare fallito il passo |
| **Soglia** | soglia di riconoscimento solo per quel passo |
| **Ripeti finche' c'e'** | vedi sotto: il passo si rifa' finche' quell'immagine resta a schermo |
| **Scost. X / Scost. Y** | sposta il click rispetto al centro dell'immagine: X positivo = a destra, negativo = a sinistra; Y positivo = in basso, negativo = in alto (attivo solo per i click) |

### Ripeti finche' c'e' (ciclo su un singolo passo)

Spuntando **Ripeti finche' c'e'** quel passo, e solo quello, diventa un ciclo:
cerca l'immagine, agisce, riaspetta, ricerca, e va avanti cosi' **finche'
l'immagine non sparisce dallo schermo**; poi la sequenza prosegue dal passo
successivo. Serve quando non sai quante volte va fatta una cosa: raccogli tutti
gli oggetti presenti, chiudi tutti i popup aperti, svuota una lista.

Dettagli che contano:

- l'**Attesa dopo** diventa la pausa *tra una ripetizione e l'altra* (e non viene
  poi contata una seconda volta prima del passo seguente);
- per decidere che l'immagine e' sparita non usa il Timeout pieno ma un controllo
  breve (al massimo 2 secondi), cosi' non resta fermo a lungo alla fine del ciclo;
- se l'immagine **non sparisce mai** (per esempio i click non fanno effetto) si
  ferma dopo 500 ripetizioni e tira dritto, scrivendolo nel registro;
- funziona anche con l'azione *Solo aspetta*: in quel caso non clicca, aspetta
  soltanto che l'immagine sparisca (utile per le schermate di caricamento);
- la spunta si accende e si spegne anche con un **doppio click sulla colonna
  Ripeti** di una riga gia' inserita.

Le azioni disponibili:

| Azione | Cosa fa | Serve l'immagine? |
|---|---|---|
| **Click**, **Doppio click**, **Click destro** | trova l'immagine e ci clicca | si' |
| **Solo aspetta che compaia** | verifica che l'immagine ci sia, senza cliccare | si' |
| **Premi un tasto** | preme un tasto o una combinazione (`invio`, `ctrl+s`, `f5`, `1`) | no |
| **Scrivi un testo** | digita quello che scrivi nel campo, carattere per carattere | no |
| **Scorri in giu'** / **in su'** | rotella del mouse; nel campo metti quante tacche (default 3) | no |
| **Pausa** | aspetta e basta | no |
| **Spegni il PC** | programma lo spegnimento di Windows; nel campo metti fra quanti secondi (default 60) | no |
| **Trascina su un'altra immagine** | preme su un'immagine, trascina fino a una seconda immagine e rilascia | si' (due) |
| **Se c'e' l'immagine... (condizione)** | se l'immagine c'e' esegue una sequenza, se non c'e' un'altra (vedi sotto) | si' |

Lo spegnimento **non** si fa cliccando il menu di Windows: quel menu e' interfaccia
di sistema, si chiude appena perde il fuoco e Windows protegge parte della shell
dai click sintetici. Il passo usa il comando `shutdown /s /t <secondi>`, che e' il
modo giusto e funziona sempre. I secondi di grazia servono per ripensarci: finche'
il PC non si spegne puoi annullare da un terminale con `shutdown /a`.

Le ultime quattro agiscono **dove si trova il mouse in quel momento**: se devi
scrivere in una casella o scorrere dentro un riquadro preciso, mettici prima un
passo di click su quell'elemento.

Sotto: **Ripeti** (0 = all'infinito), **Attesa prima di partire** (i secondi per
portare davanti la finestra giusta) e il comportamento **se un'immagine non
compare**: fermare tutto, saltare il passo e tirare dritto, oppure continuare ad
aspettarla senza limite di tempo.

La sequenza usa la **zona** e la modalita' **colore** impostate nella scheda
Riconoscimento. Si ferma con **Ferma**, col tasto rapido (F6) o col failsafe.
Durante l'esecuzione la riga del passo in corso viene evidenziata.

L'elenco si salva da solo in `sequenze\sequenza.json` e torna al suo posto alla riapertura;
con **Salva...** e **Apri...** ne tieni piu' d'una.

### Avviare una sequenza senza aprire ScreenAgent

Doppio click su **`AvviaSequenza.bat`**: esegue `sequenze\sequenza.json` e basta,
senza interfaccia. Le sequenze si indicano col solo nome del file: il programma le
cerca nella cartella `sequenze`. Puoi anche **trascinare un file .json sopra il .bat** per eseguire
quella sequenza, o passarlo come argomento.

Da riga di comando:

```
python motore.py                        esegue sequenze\sequenza.json
python motore.py mia.json --ripeti 0    sequenze\mia.json, all'infinito
python motore.py --lista                stampa i passi e non esegue niente
```

Si ferma con **F6** (o `--tasto` per cambiarlo), col mouse nell'angolo in alto a
sinistra, o con Ctrl+C nella finestra.

Le impostazioni di esecuzione (ripetizioni, attesa iniziale, cosa fare se manca
un'immagine, zona, schermo, ricerca per colore) vengono **salvate dentro il file
della sequenza**: il lanciatore la esegue esattamente come l'avevi impostata nella
GUI. Da riga di comando puoi comunque scavalcarle con le opzioni
`--ripeti --prima --se-manca --zona --monitor --colore`.

**All'accensione del PC:** premi Windows+R, scrivi `shell:startup`, e metti in
quella cartella un **collegamento** al .bat (non una copia: il .bat deve restare
nella cartella di ScreenAgent, altrimenti non trova il programma).

**Un lanciatore per una sequenza precisa:** duplica `AvviaSequenza.bat`, dagli un
altro nome e sostituisci `sequenza.json` al suo interno con il nome della tua
sequenza. Cosi' hai un .bat per ogni automazione.

Il .bat parte **ridotto a icona**: resta solo nella barra delle
applicazioni e si chiude da solo a sequenza finita. Non e' un dettaglio
estetico — una finestra aperta sul desktop coprirebbe proprio le icone che la
sequenza deve riconoscere e cliccare. Se qualcosa va storto la finestra resta
aperta per farti leggere l'errore. Se non la vuoi proprio, sostituisci `python`
con `pythonw` dentro il .bat (ma perdi il registro; per fermarla resta F6).

Per l'avvio automatico **non serve un'attesa iniziale lunga**, anzi e' il modo
peggiore: se metti 5 minuti li aspetti tutti anche quando il PC e' gia' pronto,
e se il PC ci mette di piu' fallisci lo stesso. Meglio tenere l'attesa iniziale
a pochi secondi e alzare invece il **Timeout del primo passo** (per esempio
300 s): la sequenza controlla lo schermo di continuo e parte **nell'istante in
cui l'immagine compare**, qualunque sia la velocita' dell'avvio.

Il motore e' lo stesso della GUI (`motore.py`): non esistono due versioni che
si comportano diversamente.

## Scheda Catena

Serve a far girare **piu' sequenze una dopo l'altra**, tenendole pero' come file
separati: ognuna resta modificabile e riutilizzabile per conto suo, e la catena
decide solo l'ordine. E' l'alternativa a "Unisci...", che invece fonde tutto in
una sequenza sola.

Con **+ Aggiungi...** scegli uno o piu' file (Ctrl per selezionarne piu' d'uno),
li **trascini** per metterli in ordine, e premi **Avvia catena**. La tabella
mostra quanti passi ha ogni sequenza e segnala subito i file mancanti.

| Impostazione | Cosa fa |
|---|---|
| **Ripeti tutta la catena** | quante volte rifare il giro completo (0 = all'infinito) |
| **Attesa prima di partire** | vale per la catena; l'attesa iniziale salvata dentro le singole sequenze viene ignorata, altrimenti si sommerebbero |
| **Se una sequenza fallisce** | fermare tutto (default) o passare comunque alla successiva |

Tutto il resto (soglie, zona, ricerca per colore, ripetizioni interne) resta
quello salvato dentro ogni singola sequenza. La catena si salva da sola in
`catena.json` e si ritrova alla riapertura.

Anche da riga di comando: basta elencare piu' file e vengono eseguiti in ordine.

```
python motore.py prima.json seconda.json
python motore.py prima.json seconda.json --continua
```

`--continua` e' l'equivalente della spunta "passa comunque alla successiva".

## Scheda Macro

Registra **tutto** quello che fai — ogni movimento del mouse, ogni click, la
rotella, ogni tasto — con i tempi reali, e lo riesegue identico. Usa gli hook di
sistema di Windows, quindi cattura gli eventi nell'istante esatto in cui accadono,
non a intervalli. E' diverso dalla Sequenza: la sequenza cerca le immagini a
schermo e si adatta, la macro ripete gli stessi gesti alle **stesse coordinate**,
senza guardare nulla. Serve quando le posizioni sono sempre quelle e vuoi la
massima fedelta'.

- **Registra (F7)**: premi il tasto **F7** (funziona anche con la finestra in
  secondo piano) oppure il pulsante. Dopo 1 secondo comincia a registrare; fai le
  tue azioni; premi di nuovo **F7** per fermare. Ti chiede un nome e la salva.
- **Riproduci**: riesegue la macro selezionata, con **Ripeti** (0 = all'infinito)
  e un'eventuale **pausa tra un giro e l'altro**.
- **Rinomina / Elimina** gestiscono l'elenco.

Le macro sono file in `macro/`, una per file. Per fermare la riproduzione: **F6**,
**Esc** (emergenza), il pulsante Ferma o il mouse nell'angolo in alto a sinistra.

Un solo tasto non finisce nella macro: **Esc**, che resta riservato al freno
d'emergenza. Tutto il resto — movimenti, tutti i pulsanti del mouse (anche quelli
laterali), rotella verticale e orizzontale, e ogni tasto compresi quelli estesi
come le frecce — viene registrato e rieseguito fedelmente.

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

La registrazione si salva nella cartella `macro` (file `_autoclicker.json`) e viene
ricaricata alla riapertura.
Registra premute e rilasci di mouse e tastiera con i tempi originali; la
riproduzione rispetta le pause e ripete quante volte dici nel riquadro Ripetizioni.
Ferma la registrazione **con il tasto rapido**: cosi' il click sul pulsante non
finisce dentro la registrazione (comunque gli ultimi 0.35 s vengono scartati).

## Riga di comando

**0) Guarda che schermi vede:**

```
python agent.py monitors
```

Con piu' schermi, quello che sta a **sinistra del primario** ha coordinate
**negative** (per esempio da -1920 a 0): e' normale, e il programma le gestisce. Il
numero di ogni schermo te lo dice il comando qui sopra. Il default e' `--monitor 0` =
tutti gli schermi insieme, quindi normalmente non devi specificare nulla. Restringere
a un solo schermo serve solo per andare piu' veloce o per evitare che trovi l'oggetto
sbagliato sull'altro.

**1) Insegnagli cosa cercare** — ritagli l'oggetto dallo schermo:

```
python agent.py snip pulsante_salva
```

Hai 3 secondi per portare in primo piano la finestra giusta, poi trascini il
rettangolo sull'oggetto e premi INVIO. Finisce in `templates/pulsante_salva.png`.

Consiglio: ritaglia **stretto** sull'oggetto, senza sfondo che cambia
(niente bordi con dietro il desktop, niente parti animate).

**Gestire le immagini**: sotto la lista ci sono **Rinomina**, **Duplica**,
**Dove si usa?** ed **Elimina**. "Dove si usa?" elenca in quali sequenze (e a quali
passi) l'immagine e' usata. Rinominando un'immagine usata, il programma ti propone
di **aggiornare da solo i riferimenti** in tutte le sequenze, cosi' non si rompono.
Eliminando un'immagine usata, ti avvisa prima quali sequenze ne risentiranno.

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
python agent.py run mia_sequenza.json --repeat 5
```

Passi disponibili: `click`, `click_text`, `type`, `key`, `scroll`, `wait`, `wait_for`.

**6) Modalita' interattiva** — gli detti i comandi mentre gira:

```
python agent.py repl
> click pulsante_salva
> type ciao
> key ctrl+s
```

## Come si muove il puntatore

Prima di ogni click il cursore **scorre** fino al bersaglio invece di comparirci
sopra di colpo: parte piano, accelera, frena in arrivo. La durata dipende dalla
distanza (circa 0.12 s per uno spostamento corto, al massimo 0.55 s attraversando
tutto lo schermo). Misurato: da 3 posizioni intermedie con salti da 650 px si e'
passati a **122 posizioni con salti da 28 px**, e l'arrivo resta esatto al pixel.

Fa eccezione l'**autoclicker su punto fisso**, che continua a posizionarsi
istantaneamente: li' il senso e' la frequenza, e un'animazione ad ogni click
falserebbe l'intervallo.

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

- `ScreenAgent.py` — l'interfaccia grafica (cinque schede)
- `screen.py` — cattura schermo (mss) + fix DPI
- `vision.py` — riconoscimento: confronto pixel, ricerca per colore, OCR
- `actions.py` — mouse e tastiera (pyautogui)
- `clicker.py` — motore dell'autoclicker: click veloci, tasti globali, registrazione
- `motore.py` — motore delle sequenze + lanciatore autonomo
- `registratore.py` — registrazione fedele (hook di sistema) e riproduzione delle macro
- `percorsi.py` — decide dove stanno i dati (funziona sia da sorgente sia da exe)
- `build.bat` + `ScreenAgent.spec` — creano l'eseguibile con PyInstaller
- `installer.iss` — ricetta dell'installer (Inno Setup)
- `agent.py` — CLI del riconoscimento e runner degli script JSON
- `diagnosi.py` — perche' non trova un'immagine
- `zona.py` — sceglie la zona dello schermo in cui cercare
- `incolla.py` — crea un template da quello che hai negli appunti
- `AvviaSequenza.bat` — lancia una sequenza senza aprire l'interfaccia
- `templates/`, `sequenze/`, `macro/` — i tuoi dati (immagini, sequenze, macro):
  il programma crea le cartelle da solo e non fanno parte del repository

## Licenza

MIT — vedi il file `LICENSE`.
