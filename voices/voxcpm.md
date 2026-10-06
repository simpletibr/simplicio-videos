# VoxCPM2 (provider `voxcpm`)

[OpenBMB/VoxCPM](https://github.com/OpenBMB/VoxCPM) · Apache-2.0 · 2B model, 30 languages (pt included), 48 kHz output, voice design and cloning.

```bash
pip install voxcpm            # Python 3.10-3.12, PyTorch >= 2.5; GPU recommended (CPU is slow)
# or point to an existing binary: export VOXCPM_BIN=/path/to/voxcpm
```

Contract:

```yaml
voz:
  provider: voxcpm
  providers:
    voxcpm:
      control: "Young female voice, warm and gentle"   # voice design (no reference) or style on top of a clone
      reference_audio: assets/audio/ref/speaker.wav     # optional: enables cloning (authorized speaker only)
      reference_text: "Exact transcript of the clip."   # optional: ultimate cloning
      seed: 42                                          # fixed seed, part of the cache key
```

```bash
simplicio-video voice contract.yaml --provider voxcpm
```

Maps to `voxcpm design` (no reference) or `voxcpm clone` (reference). Takes are kept in `<file.dir>/voxcpm/line-NN.wav`; the cache key includes the settings and the reference file hash. Output is not bit-reproducible across hardware, so the processed take (versioned) is what makes the render deterministic.
