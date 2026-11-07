# simplicio-videos

> Un motor de vídeo determinista guiado por agentes: entra un contrato YAML, sale un MP4, y alrededor hay herramientas para audio, vídeo, voz, cambio de personaje, planificación social, licencias de recursos e investigación web.

[Inglés y todos los idiomas: README canónico](../README.md) · [Portugués](../README.pt-BR.md)

## Qué hace

- **Contrato a MP4:** valida un contrato YAML, genera la narración, renderiza de forma determinista con HyperFrames y la mezcla a -14 LUFS, y escribe un manifiesto. Ningún LLM interviene en el render.
- **Voz:** proveedores `file`, `local` (Kokoro-82M), `gemini`, `voxcpm`, `openvoice` y `voicestudio` (app local). `elevenlabs` y `xai` son stubs (sin implementar).
- **Audio y vídeo (`media`):** sonda, extracción de audio, hojas de fotogramas, subtítulos, máscaras de caja, doblaje y descarga de un vídeo público con registro de procedencia.
- **Cortes verticales (`shorts`):** clips 9:16 a partir de un vídeo largo, puntuados con reglas fijas sobre una transcripción por palabras.
- **Edición EDL (`edit`):** el agente escribe la EDL; los ayudantes de video-use (versión fijada) ejecutan ffmpeg.
- **Plantillas y catálogos:** 14 plantillas por sector (8 listas para renderizar), 55 entradas de movimiento, 50 formatos de anuncio y 50 ángulos.
- **Cambio de personaje y trabajos (`swap`, `jobs`):** cambio de pago con seis adaptadores, estimación de coste y tope en US$, solo desde la terminal; trabajos en segundo plano para swap y voz local.
- **Pistas externas:** Hypit, OpenMontage, OpenCut, Toonflow y MoneyPrinterTurbo, cada una fijada y ejecutada como programa separado, nunca importada.
- **Planificación social (`social`):** comprueba un vídeo frente a los límites de cada red y escribe un plan. **Nunca publica.**
- **Biblioteca con licencia (`openverse`):** búsqueda, descarga segura, revisión por solicitud y exportación con créditos.
- **Investigación web (`busca`):** consultas y lecturas de páginas a través de TinyFish, con fuente y fecha por resultado y un límite diario de llamadas.
- **Pista UGC:** archivos de prompts para personajes sintéticos y un flujo manual, fuera del render.
- **Integración con agentes:** servidor MCP con 28 herramientas `video.*`, seis skills, e `install` para 11 hosts de agentes.
- **Operaciones:** estado, herramientas fijadas, diagnóstico, espacio de trabajo, actualizaciones e inicio de sesión Simplicio compartido.

## Inicio rápido

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

## Límites

- **Adaptadores de cambio sin verificar:** `fal`, `wavespeed`, `kie` y `alibaba` se escribieron a partir de documentación pública y no se han comprobado contra las APIs reales.
- **Sin publicación:** el motor nunca publica ni sube nada a una red social.
- **Plataformas:** el paquete está clasificado para Linux; macOS y Windows no están confirmados en equipos reales.

Este resumen es más corto que el [README canónico](../README.md) y puede quedar desfasado respecto a él.
