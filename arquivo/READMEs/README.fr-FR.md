# simplicio-videos

> Un moteur vidéo déterministe piloté par des agents : un contrat YAML en entrée, un MP4 en sortie, et autour, une boîte à outils pour l'audio, la vidéo, la voix, le remplacement de personnage, la planification sociale, les licences d'actifs et la recherche web.

[Anglais et toutes les langues : README canonique](../README.md) · [Portugais](../README.pt-BR.md)

## Ce qu'il fait

- **Contrat vers MP4 :** valide un contrat YAML, génère la narration, effectue un rendu déterministe avec HyperFrames et le mixage à -14 LUFS, puis écrit un manifeste. Aucun LLM n'intervient dans le rendu.
- **Voix :** fournisseurs `file`, `local` (Kokoro-82M), `gemini`, `voxcpm`, `openvoice` et `voicestudio` (application locale). `elevenlabs` et `xai` sont des stubs (non implémentés).
- **Audio et vidéo (`media`) :** sonde, extraction audio, planches d'images, sous-titres, masques de zone, doublage et téléchargement d'une vidéo publique avec un enregistrement de provenance.
- **Coupes verticales (`shorts`) :** clips 9:16 extraits d'une vidéo longue, notés par des règles fixes à partir d'une transcription mot à mot.
- **Montage EDL (`edit`) :** l'agent écrit l'EDL ; les aides de video-use (version figée) lancent ffmpeg.
- **Modèles et catalogues :** 14 modèles par secteur (8 prêts au rendu), 55 entrées de mouvement, 50 formats publicitaires et 50 angles.
- **Remplacement de personnage et tâches (`swap`, `jobs`) :** remplacement payant via six adaptateurs, avec estimation du coût et plafond en US$, uniquement depuis le terminal ; tâches en arrière-plan pour swap et voix locale.
- **Pistes externes :** Hypit, OpenMontage, OpenCut, Toonflow et MoneyPrinterTurbo, chacune épinglée et lancée comme programme séparé, jamais importée.
- **Planification sociale (`social`) :** vérifie une vidéo selon les limites de chaque réseau et écrit un plan. **Ne publie jamais.**
- **Bibliothèque sous licence (`openverse`) :** recherche, téléchargement sûr, revue par demande et export avec crédits.
- **Recherche web (`busca`) :** requêtes et lectures de pages via TinyFish, avec source et date pour chaque résultat, et plafond quotidien d'appels.
- **Piste UGC :** fichiers de prompts pour personnages synthétiques et pipeline manuel, hors rendu.
- **Intégration aux agents :** serveur MCP avec 28 outils `video.*`, six skills, et `install` pour 11 hôtes d'agents.
- **Opérations :** statut, outils épinglés, diagnostic, espace de travail, mises à jour et connexion Simplicio partagée.

## Démarrage rapide

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

## Limites

- **Adaptateurs de remplacement non vérifiés :** `fal`, `wavespeed`, `kie` et `alibaba` ont été écrits à partir de la documentation publique et n'ont pas été vérifiés sur les API en service.
- **Pas de publication :** le moteur ne publie ni n'envoie jamais rien sur un réseau social.
- **Plateformes :** le paquet est classé pour Linux ; macOS et Windows ne sont pas confirmés sur de vraies machines.

Ce résumé est plus court que le [README canonique](../README.md) et peut être moins à jour que lui.
