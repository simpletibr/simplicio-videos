# simplicio-videos

> Un motore video deterministico guidato da agenti: in ingresso un contratto YAML, in uscita un MP4, e intorno una cassetta degli attrezzi per audio, video, voce, sostituzione del personaggio, pianificazione social, licenze degli asset e ricerca web.

[Inglese e tutte le lingue: README canonico](../README.md) · [Portoghese](../README.pt-BR.md)

## Cosa fa

- **Contratto in MP4:** valida un contratto YAML, genera la narrazione, esegue il render in modo deterministico con HyperFrames e il mix a -14 LUFS, e scrive un manifest. Nel percorso di render non gira nessun LLM.
- **Voce:** provider `file`, `local` (Kokoro-82M), `gemini`, `voxcpm`, `openvoice` e `voicestudio` (app locale). `elevenlabs` e `xai` sono stub (non implementati).
- **Audio e video (`media`):** probe, estrazione audio, fogli di fotogrammi, sottotitoli, maschere a riquadro, doppiaggio e download di un video pubblico con registro di provenienza.
- **Tagli verticali (`shorts`):** clip 9:16 da un video lungo, valutate con regole fisse su una trascrizione parola per parola.
- **Montaggio EDL (`edit`):** l'agente scrive l'EDL; gli helper di video-use (versione fissata) eseguono ffmpeg.
- **Template e cataloghi:** 14 template per settore (8 pronti al render), 55 voci di movimento, 50 formati pubblicitari e 50 angoli.
- **Sostituzione del personaggio e job (`swap`, `jobs`):** sostituzione a pagamento con sei adattatori, stima dei costi e tetto in US$, solo dal terminale; job in background per swap e voce locale.
- **Tracce esterne:** Hypit, OpenMontage, OpenCut, Toonflow e MoneyPrinterTurbo, ciascuna fissata ed eseguita come programma separato, mai importata.
- **Pianificazione social (`social`):** verifica un video rispetto ai limiti di ogni rete e scrive un piano. **Non pubblica mai.**
- **Libreria con licenza (`openverse`):** ricerca, download sicuro, revisione per ogni richiesta ed esportazione con crediti.
- **Ricerca web (`busca`):** query e letture di pagine tramite TinyFish, con fonte e data per ogni risultato e tetto giornaliero di chiamate.
- **Traccia UGC:** file di prompt per personaggi sintetici e una pipeline manuale, fuori dal render.
- **Integrazione con agenti:** server MCP con 19 strumenti `video.*`, sei skills e `install` per 11 host di agenti.
- **Operazioni:** stato, strumenti fissati, diagnostica, workspace, aggiornamenti e login Simplicio condiviso.

## Avvio rapido

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # `simplicio-video` command (Python >= 3.10); rendering needs Node >= 22 and ffmpeg
simplicio-video setup                 # first run
simplicio-video install               # copy the skills into your agent host (project; --global for the home folder)
simplicio-video doctor                # check what is missing

cd clients/<cliente>/<campanha>       # a client project with a contract.yaml
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # narration; local draft voice or --provider file|gemini|voxcpm|openvoice|voicestudio
simplicio-video render contract.yaml  # out/<cliente>-<campanha>.mp4 + render.manifest.json
```

## Limiti

- **Copertura MCP:** `media`, `shorts`, `tools`, `status`, `doctor` e `install` per ora sono solo CLI.
- **Adattatori di swap non verificati:** `fal`, `wavespeed`, `kie` e `alibaba` sono stati scritti dalla documentazione pubblica e non sono stati verificati sulle API reali.
- **Nessuna pubblicazione:** il motore non pubblica né carica mai nulla su un social network.
- **Piattaforme:** il pacchetto è classificato per Linux; macOS e Windows non sono confermati su macchine reali.

Questo riassunto è più breve del [README canonico](../README.md) e può essere meno aggiornato di esso.
