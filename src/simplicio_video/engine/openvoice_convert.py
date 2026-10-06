"""Headless OpenVoice V2 tone-color conversion (runs in the OpenVoice Python env, not in simplicio-video's).

usage: openvoice_convert.py CHECKPOINTS_DIR BASE.wav REFERENCE.wav OUT.wav
BASE.wav is any TTS take (Kokoro, so pt-BR works); the converter swaps its timbre for the reference speaker's.
"""
import sys

import torch
from openvoice import se_extractor
from openvoice.api import ToneColorConverter

ckpt, base, ref, out = sys.argv[1:5]
device = "cuda:0" if torch.cuda.is_available() else "cpu"
conv = ToneColorConverter(f"{ckpt}/converter/config.json", device=device)
conv.load_ckpt(f"{ckpt}/converter/checkpoint.pth")
target_se, _ = se_extractor.get_se(ref, conv, vad=True)
source_se, _ = se_extractor.get_se(base, conv, vad=True)
conv.convert(audio_src_path=base, src_se=source_se, tgt_se=target_se, output_path=out, message="")
