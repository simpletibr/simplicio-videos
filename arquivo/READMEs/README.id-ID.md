# simplicio-videos

> Mesin video deterministik yang digerakkan agen: kontrak YAML masuk, MP4 keluar, dan di sekitarnya ada perangkat untuk audio, video, suara, penggantian karakter, perencanaan media sosial, lisensi aset, dan riset web.

[Inggris dan semua bahasa: README kanonik](../README.md) · [Portugis](../README.pt-BR.md)

## Fungsinya

- **Kontrak ke MP4:** memvalidasi kontrak YAML, membuat narasi, merender secara deterministik dengan HyperFrames dan mix di -14 LUFS, lalu menulis manifest. Tidak ada LLM yang berjalan di jalur render.
- **Suara:** penyedia `file`, `local` (Kokoro-82M), `gemini`, `voxcpm`, `openvoice`, dan `voicestudio` (aplikasi lokal). `elevenlabs` dan `xai` masih berupa stub (belum diimplementasikan).
- **Audio dan video (`media`):** probe, ekstraksi audio, lembar frame, subtitle, masker kotak, dubbing, dan pengunduhan satu video publik beserta catatan asal (provenance).
- **Potongan vertikal (`shorts`):** klip 9:16 dari video panjang, dinilai dengan aturan tetap dari transkrip per kata.
- **Penyuntingan EDL (`edit`):** agen menulis EDL; helper video-use (versi dipatok) menjalankan ffmpeg.
- **Template dan katalog:** 14 template sektor (8 siap dirender), 55 entri katalog gerak, 50 format iklan, dan 50 sudut pandang.
- **Penggantian karakter dan job (`swap`, `jobs`):** penggantian berbayar lewat enam adapter, dengan estimasi biaya dan batas US$, hanya dari terminal; job latar belakang untuk swap dan suara lokal.
- **Jalur produksi eksternal:** Hypit, OpenMontage, OpenCut, Toonflow, dan MoneyPrinterTurbo, masing-masing dipatok versinya dan dijalankan sebagai program terpisah, tidak pernah diimpor.
- **Perencanaan media sosial (`social`):** memeriksa video terhadap batas tiap jaringan dan menulis rencana. **Tidak pernah memposting.**
- **Pustaka berlisensi (`openverse`):** pencarian, unduhan aman, tinjauan per permintaan, dan ekspor dengan kredit.
- **Riset web (`busca`):** kueri dan pembacaan halaman lewat TinyFish, dengan sumber dan tanggal pada setiap hasil serta batas panggilan harian.
- **Jalur UGC:** file prompt untuk karakter sintetis dan pipeline manual, di luar render.
- **Integrasi agen:** server MCP dengan 28 alat `video.*`, enam skills, dan `install` untuk 11 host agen.
- **Operasi:** status, alat yang dipatok, diagnostik, workspace, pembaruan, dan login Simplicio bersama.

## Mulai cepat

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

## Batasan

- **Adapter swap yang belum diverifikasi:** `fal`, `wavespeed`, `kie`, dan `alibaba` ditulis dari dokumentasi publik dan belum diperiksa terhadap API langsung.
- **Tidak ada publikasi:** mesin tidak pernah memposting atau mengunggah apa pun ke jaringan sosial.
- **Platform:** paket diklasifikasikan untuk Linux; macOS dan Windows belum dikonfirmasi pada mesin sungguhan.

Ringkasan ini lebih pendek dari [README kanonik](../README.md) dan mungkin tertinggal darinya.
