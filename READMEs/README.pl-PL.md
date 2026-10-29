# simplicio-videos

> Deterministyczny silnik wideo sterowany przez agentów: na wejściu kontrakt YAML, na wyjściu plik MP4, a wokół niego narzędzia do audio, wideo, głosu, podmiany postaci, planowania postów w mediach społecznościowych, licencjonowanych zasobów i researchu w sieci.

[Angielski i wszystkie języki: kanoniczny README](../README.md) · [Portugalski](../README.pt-BR.md)

## Co robi

- **Kontrakt do MP4:** sprawdza kontrakt YAML, generuje narrację, renderuje deterministycznie w HyperFrames z miksem na -14 LUFS i zapisuje manifest. W ścieżce renderowania nie działa żaden LLM.
- **Głos:** dostawcy `file`, `local` (Kokoro-82M), `gemini`, `voxcpm`, `openvoice` i `voicestudio` (lokalna aplikacja). `elevenlabs` i `xai` to stuby (niezaimplementowane).
- **Audio i wideo (`media`):** sonda, wyciąganie ścieżki audio, arkusze klatek, napisy, maski prostokątne, dubbing i pobieranie jednego publicznego wideo wraz z zapisem pochodzenia (provenance).
- **Cięcia pionowe (`shorts`):** klipy 9:16 z długiego wideo, oceniane stałymi regułami na podstawie transkrypcji słów.
- **Montaż EDL (`edit`):** agent pisze EDL, a pomocnicy video-use (przypięta wersja) uruchamiają ffmpeg.
- **Szablony i katalogi:** 14 szablonów branżowych (8 gotowych do renderowania), 55 pozycji ruchu, 50 formatów reklam i 50 kątów ujęcia.
- **Podmiana postaci i zadania (`swap`, `jobs`):** płatna podmiana przez sześć adapterów, z szacunkiem kosztów i limitem w USD, tylko z terminala; zadania w tle dla swap i lokalnego głosu.
- **Zewnętrzne ścieżki produkcyjne:** Hypit, OpenMontage, OpenCut, Toonflow i MoneyPrinterTurbo, każda przypięta i uruchamiana jako osobny program, nigdy importowana.
- **Planowanie publikacji (`social`):** sprawdza wideo pod kątem limitów każdej sieci i zapisuje plan. **Nigdy nie publikuje.**
- **Biblioteka licencjonowana (`openverse`):** wyszukiwanie, bezpieczne pobieranie, przegląd dla każdego żądania i eksport z oznaczeniem autorów (credits).
- **Research w sieci (`busca`):** zapytania i odczyty stron przez TinyFish, z podaniem źródła i daty przy każdym wyniku oraz dziennym limitem wywołań.
- **Ścieżka UGC:** pliki promptów dla syntetycznych postaci i ręczny pipeline, poza renderem.
- **Integracja z agentami:** serwer MCP z 19 narzędziami `video.*`, sześć skills i `install` dla 11 hostów agentów.
- **Operacje:** status, przypięte narzędzia, diagnostyka, przestrzeń robocza, aktualizacje i wspólne logowanie Simplicio.

## Szybki start

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

## Ograniczenia

- **Pokrycie MCP:** `media`, `shorts`, `tools`, `status`, `doctor` i `install` są na razie dostępne tylko w CLI.
- **Niezweryfikowane adaptery podmiany:** `fal`, `wavespeed`, `kie` i `alibaba` napisano na podstawie publicznej dokumentacji i nie sprawdzono ich na działających API.
- **Brak publikacji:** silnik nigdy nie publikuje ani nie wysyła plików do sieci społecznościowej.
- **Platformy:** pakiet jest sklasyfikowany dla Linuksa; macOS i Windows nie są potwierdzone na prawdziwych maszynach.

Ten skrót jest krótszy od [kanonicznego README](../README.md) i może być mniej aktualny.
