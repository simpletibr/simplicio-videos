# simplicio-videos

> Enjin video deterministik yang dipacu ejen: kontrak YAML masuk, MP4 keluar, dan di sekelilingnya tersedia kit alat untuk audio, video, suara, penggantian watak, perancangan media sosial, pelesenan aset dan penyelidikan web.

[Inggeris dan semua bahasa: README kanonikal](../README.md) · [Portugis](../README.pt-BR.md)

## Apa yang dilakukannya

- **Kontrak kepada MP4:** mengesahkan kontrak YAML, menjana narasi, merender secara deterministik dengan HyperFrames dan campuran pada -14 LUFS, dan menulis manifest. Tiada LLM berjalan dalam laluan render.
- **Suara:** penyedia `file`, `local` (Kokoro-82M), `gemini`, `voxcpm`, `openvoice` dan `voicestudio` (aplikasi tempatan). `elevenlabs` dan `xai` ialah stub (belum dilaksanakan).
- **Audio dan video (`media`):** probe, pengekstrakan audio, lembaran bingkai, sari kata, topeng kotak, dabbing dan muat turun satu video awam dengan rekod asal usul (provenance).
- **Potongan menegak (`shorts`):** klip 9:16 daripada video panjang, dinilai dengan peraturan tetap daripada transkrip mengikut perkataan.
- **Penyuntingan EDL (`edit`):** ejen menulis EDL; pembantu video-use (versi dikunci) menjalankan ffmpeg.
- **Templat dan katalog:** 14 templat sektor (8 sedia untuk render), 55 entri katalog gerakan, 50 format iklan dan 50 sudut.
- **Penggantian watak dan kerja (`swap`, `jobs`):** penggantian berbayar melalui enam penyesuai, dengan anggaran kos dan had US$, hanya dari terminal; kerja latar belakang untuk swap dan suara tempatan.
- **Trek pengeluaran luaran:** Hypit, OpenMontage, OpenCut, Toonflow dan MoneyPrinterTurbo, setiap satunya dikunci versinya dan dijalankan sebagai program berasingan, tidak pernah diimport.
- **Perancangan media sosial (`social`):** menyemak video mengikut had setiap rangkaian dan menulis pelan. **Tidak pernah menyiarkan.**
- **Perpustakaan berlesen (`openverse`):** carian, muat turun selamat, semakan bagi setiap permintaan dan eksport dengan kredit.
- **Penyelidikan web (`busca`):** pertanyaan dan bacaan halaman melalui TinyFish, dengan sumber dan tarikh bagi setiap hasil serta had panggilan harian.
- **Trek UGC:** fail prompt untuk watak sintetik dan saluran manual, di luar render.
- **Integrasi ejen:** pelayan MCP dengan 28 alat `video.*`, enam skills dan `install` untuk 11 hos ejen.
- **Operasi:** status, alat yang dikunci versinya, diagnostik, ruang kerja, kemas kini dan log masuk Simplicio yang dikongsi.

## Permulaan pantas

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

## Had

- **Penyesuai swap yang tidak disahkan:** `fal`, `wavespeed`, `kie` dan `alibaba` ditulis berdasarkan dokumentasi awam dan belum diperiksa terhadap API langsung.
- **Tiada penerbitan:** enjin tidak pernah menyiarkan atau memuat naik apa-apa ke rangkaian sosial.
- **Platform:** pakej dikelaskan untuk Linux; macOS dan Windows belum disahkan pada mesin sebenar.

Ringkasan ini lebih pendek daripada [README kanonikal](../README.md) dan mungkin ketinggalan daripadanya.
