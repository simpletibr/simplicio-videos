# Licenças de áudio — video-01

| Elemento | Origem | Licença / uso comercial |
|---|---|---|
| **Trilha + efeitos sonoros** (`assets/audio/build/mix.wav`, gerado) | **Síntese procedural própria** em `scripts/build.mjs`: trilha original 120 BPM (kick, clap, hats, baixo, plucks, pad em Lá menor, Am–F–C–G) + efeitos (whoosh, impact, hit, click, blip, riser, glitch) gerados por osciladores, ruído com semente fixa e filtros biquad | Sem material de terceiros → nenhuma licença externa. Obra original deste repositório; uso comercial liberado. |
| **Narração** (`assets/audio/vo/vo1..vo6-*.wav`, versionados) | TTS local **Kokoro-82M v1.0** ([hexgrad/Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)), voz **`pm_alex`** (pt-BR masculina), `lang=pt-br`, `speed=1.15`, rodando em ONNX via [kokoro-onnx 0.6.1](https://github.com/thewh1teagle/kokoro-onnx) (arquivos `kokoro-v1.0.onnx` sha256 `7d5df8ec…` e `voices-v1.0.bin` sha256 `bca610b8…`, release `model-files-v1.0`) | Pesos do modelo: **Apache-2.0** — o model card diz *"Apache-licensed weights, Kokoro can be deployed anywhere from production environments to personal projects"* e que o treino usou áudio de domínio público/licenças permissivas + áudio sintético. kokoro-onnx: **MIT**. O fonetizador espeak-ng (via `espeakng-loader`) é GPL-3.0 como **ferramenta**; a GPL não se aplica ao áudio gerado. Uso comercial liberado, sem atribuição obrigatória (crédito opcional: "Voz: Kokoro-82M"). |

Pós-processamento da narração (ffmpeg): corte de silêncio, `atempo` ≤ 1,3× para caber no slot (valores reais em `assets/audio/vo/manifest.json`), 48 kHz mono. Na mixagem: passa-altas 110 Hz, nível igualado por frase, saturação leve, música abaixa 10 dB e efeitos 6 dB sob a voz. Master final: −14 LUFS / true peak ≤ −1,5 dBTP.

## Opções avaliadas e descartadas (30/09/2026)

| Opção | Por que não é a padrão |
|---|---|
| **Piper** vozes pt_BR `faber`, `cadu`, `jeff` (medium) | O repositório de vozes é MIT e os datasets pt-BR são CC0, **mas** os model cards dizem *"Finetuned from U.S. English lessac voice"*, e o dataset lessac (Blizzard 2013) é distribuído sob **"Research Licence Agreement"**. Cadeia de licença com dúvida para uso comercial → só usar com aceite consciente desse risco. O motor atual (`piper-tts` 1.8, OHF-Voice/piper1-gpl) é GPL-3.0 (não afeta o áudio). |
| **Piper** `pt_BR-edresson-low` | Dataset CC BY 4.0, mas fine-tune da voz `ryan` cujo dataset é **CC BY-NC-SA 4.0** (não comercial); qualidade "low" (16 kHz). |
| **Coqui XTTS-v2** | Coqui Public Model License: *"This license allows only non-commercial use of a machine learning model and its outputs."* → proibido para cliente. |
| **edge-tts** | Não é local: usa o serviço online "Read Aloud" do Microsoft Edge sem chave; o projeto não concede direitos sobre o áudio e não há termos da Microsoft autorizando esse uso fora do Edge → **só como nota**, não usar em entrega comercial. |
| **ElevenLabs** (opção paga, já suportada no script) | Qualidade superior em pt-BR. Plano gratuito **não** permite uso comercial (exige atribuição "elevenlabs.io"); planos pagos incluem licença comercial para o que for gerado durante a assinatura ([help center](https://help.elevenlabs.io/hc/en-us/articles/13313564601361-Can-I-publish-the-content-I-generate-on-the-platform)). Se usar, registrar aqui: plano, voice_id, data da geração. |

Se no futuro entrar trilha/efeito/voz de terceiros, registrar: arquivo · URL · autor · licença · data · crédito exigido.
