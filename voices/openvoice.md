# OpenVoice V2 (provider `openvoice`)

[myshell-ai/OpenVoice](https://github.com/myshell-ai/OpenVoice) · MIT (commercial use ok). Tone-color cloning: a base take is converted to the reference speaker's timbre. The base is the local **Kokoro** voice (`voz.providers.local`), so pt-BR works even though OpenVoice's own base speakers do not cover it.

```bash
conda create -n openvoice python=3.9 && conda activate openvoice
git clone https://github.com/myshell-ai/OpenVoice && cd OpenVoice && pip install -e .
# download checkpoints_v2 (see docs/USAGE.md in the repo) and extract it
export OPENVOICE_PY=$(which python)
export OPENVOICE_CHECKPOINTS=/path/to/checkpoints_v2     # must contain converter/checkpoint.pth
```

Contract:

```yaml
voz:
  provider: openvoice
  providers:
    local: { voice: pf_dora, lang: pt-br }              # base voice
    openvoice:
      reference_audio: assets/audio/ref/speaker.wav       # authorized speaker, clean 10-30 s
```

```bash
simplicio-video voice contract.yaml --provider openvoice
```

The conversion runs in your OpenVoice env through `src/simplicio_video/engine/openvoice_convert.py`. It changes timbre, not prosody: the pacing comes from the Kokoro base.
