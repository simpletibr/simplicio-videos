# Licenças de áudio — video-01

| Elemento | Origem | Licença / uso comercial |
|---|---|---|
| **Trilha + efeitos sonoros** (`assets/audio/build/mix.wav`, gerado) | **Síntese procedural própria** em `scripts/build.mjs`: trilha original 120 BPM (kick, clap, hats, baixo, plucks, pad em Lá menor, Am–F–C–G) + efeitos (whoosh, impact, hit, click, blip, riser, glitch, shimmer) gerados por osciladores, ruído com semente fixa e filtros biquad | Sem material de terceiros → nenhuma licença externa. Obra original deste repositório; uso comercial liberado. |
| **Narração (atual)** (`assets/audio/vo/external/line-01..09.wav` originais + `assets/audio/vo/vo1..vo9-*.wav` tratados, versionados) | **Gemini 3.8 Flash TTS**, voz **Puck**, single-speaker, gerada em **Google AI Studio** (Generate speech) pela conta do Wesley (Google AI Pro, wesleybob4@gmail.com) em 30/09/2026, uma frase por arquivo, com a instrução de estilo "Locutor brasileiro de propaganda de loja de games, tom animado, natural e próximo, português do Brasil, ritmo ágil sem correr." Entra no pipeline pelo provider `file` (`scripts/voice.py`): corte de silêncio + EQ/compressor/sala + 48 kHz mono, **sem aceleração**. Passo a passo: [`docs/tutorial-voz-gemini.md`](../../../../../docs/tutorial-voz-gemini.md). | [Gemini API Additional Terms of Service](https://ai.google.dev/gemini-api/terms) (vigentes desde 23/03/2026), que valem para Gemini API **e Google AI Studio**: *"Some of our Services allow you to generate original content. Google won't claim ownership over that content. You acknowledge that Google may generate the same or similar content for others"* → o Google não reivindica o áudio; uso comercial no anúncio do cliente é permitido, com a ressalva de que outra pessoa pode obter áudio parecido (sem exclusividade). Os termos dizem que AI Studio/Gemini API são para uso *"professional or business purposes"* (é o caso) e exigem seguir a [Prohibited Use Policy](https://policies.google.com/terms/generative-ai/use-policy). **Atenção:** o AI Studio sem projeto Cloud com faturamento ativo conta como *Unpaid Service* — o Google pode usar o texto enviado e o áudio gerado para melhorar produtos (a assinatura Google AI Pro não muda isso). Não enviar dados sensíveis/pessoais (o roteiro é texto público de anúncio). |
| Narração alternativa local (versão anterior deste vídeo) | Chatterbox Multilingual V3 (MIT) com referência sintética Kokoro `pm_alex` — continua no `voice.py` (`provider: "chatterbox"`); detalhes abaixo. | MIT; áudio com marca d'água Perth. |
| **Voz de referência** (`assets/audio/vo/ref/pm_alex.wav`, versionado) | Gerada pelo **Kokoro-82M v1.0**, voz `pm_alex` (pt-BR masculina), via kokoro-onnx 0.6.1 (`kokoro-v1.0.onnx` sha256 `7d5df8ec…`, `voices-v1.0.bin` sha256 `bca610b8…`). O Chatterbox usa esse clipe só como timbre de referência. | Kokoro: pesos **Apache-2.0** (treino em áudio de domínio público/licença permissiva + sintético); kokoro-onnx **MIT**; espeak-ng (fonetizador) GPL-3.0 **como ferramenta**, não se aplica ao áudio. **Nenhuma voz de pessoa real foi clonada**: a referência é 100% sintética. |
| **Seleção de takes** | faster-whisper `small` (MIT; pesos Whisper MIT) transcreve cada semente e fica a que tiver a transcrição mais fiel (desempate: take mais curto) | Ferramenta de análise; não entra no áudio. |

**Tratamento da voz** (`spec.json → voice.processing`, aplicado em `scripts/voice.py` com ffmpeg, depois do corte de silêncio): passa-altas 85 Hz · −2,5 dB em 320 Hz (tira o "embolado") · +2,5 dB em 3,4 kHz (presença) · +1,5 dB em 9 kHz (ar) · compressor 2,5:1 (limiar −20 dB, ataque 8 ms, release 140 ms) · sala curta sutil (`aecho` 19/31/47 ms, 9/6/4 %) · 48 kHz mono. Na mixagem (`build.mjs`): só nivelamento por frase (mesmo RMS), sem saturação; música abaixa 10 dB e efeitos 6 dB sob a voz. Master final: −14 LUFS / true peak ≤ −1,5 dBTP.

## Como a voz foi escolhida (30/09/2026)

Critério: **gratuito, local, licença que permite uso comercial do áudio**, e a fala pt-BR mais natural. Teste com as 9 frases do roteiro; nota de naturalidade = UTMOS22 "strong" (`tarepan/SpeechMOS` v1.2.0 — treinado em inglês, serve como indicador relativo, não absoluto); inteligibilidade = WER do faster-whisper `small` em pt (0 = perfeito).

| Candidato | UTMOS ↑ | WER ↓ | Observação |
|---|---|---|---|
| **Chatterbox V3 + referência Kokoro `pm_alex`** ✅ | **4,03** | 0,107 | Mais natural: entonação e ritmo de fala real. Erros só em marcas (WJR, Xbox, Hall Effect, PS5) → resolvidos com grafia fonética em `say` + melhor de 3 sementes por ASR. |
| Chatterbox V3 + referência Kokoro `pf_dora` | 3,96 | 0,079 | Feminina, quase empatada. |
| Kokoro `pf_dora` | 3,83 | 0,011 | Muito limpa, mas "leitura" mais robótica. |
| Chatterbox V3 + referência Kokoro `pm_santa` | 3,72 | 0,089 | |
| Kokoro `pm_alex` (versão anterior do vídeo) | 3,66 | 0,030 | Precisava de aceleração para caber em 15 s. |
| Kokoro `pm_santa` | 3,11 | 0,011 | |

### Descartados por licença (ou por não ter pt-BR)

| Opção | Motivo |
|---|---|
| **F5-TTS** e o fine-tune pt-BR `firstpixel/F5-TTS-pt-br` | Pesos **CC-BY-NC-4.0** (não comercial). |
| **Fish Speech / OpenAudio S1-mini** | Pesos **CC-BY-NC-SA-4.0** (não comercial). |
| **Orpheus multilingual** (research release) | Vozes Apache-2.0 só em espanhol/italiano — **sem português**. |
| **Kani-TTS** | Licença LFM Open e sem voz pt. |
| **Coqui XTTS-v2** | Coqui Public Model License: *"allows only non-commercial use of a machine learning model and its outputs"*. |
| **Piper** pt_BR `faber`, `cadu`, `jeff` | Vozes MIT e datasets CC0, **mas** são *"finetuned from U.S. English lessac voice"* e o dataset lessac tem **"Research Licence Agreement"** → cadeia de licença duvidosa. |
| **Piper** `pt_BR-edresson-low` | Fine-tune da voz `ryan` (dataset **CC BY-NC-SA 4.0**); 16 kHz. |
| **edge-tts** | Não é local: usa o serviço online do Microsoft Edge sem termos que autorizem esse uso → não usar em entrega comercial. |
| Clonar voz de dataset pt-BR CC0 (OHF-Voice) | Tecnicamente permitido, mas evitamos clonar a voz de uma pessoa real sem autorização direta dela. |

### Opções pagas (suportadas no `voice.py`, desligadas)

| Opção | Situação |
|---|---|
| **ElevenLabs** (`provider: "elevenlabs"`) | Qualidade alta em pt-BR. Plano gratuito **não** permite uso comercial; planos pagos incluem licença comercial ([help center](https://help.elevenlabs.io/hc/en-us/articles/13313564601361-Can-I-publish-the-content-I-generate-on-the-platform)). Precisa `ELEVENLABS_API_KEY`. |
| **xAI / Grok TTS** (`provider: "xai"`) | API `POST https://api.x.ai/v1/tts` ([docs](https://docs.x.ai/developers/model-capabilities/audio/text-to-speech)), vozes `eve`, `ara`, `rex`, `sal`, `leo` (+ catálogo em `GET /v1/tts/voices`, clonagem de voz disponível), `language: "pt-BR"`, saída MP3/WAV/PCM até 48 kHz. Preço em 30/09/2026: **US$ 15 por 1 milhão de caracteres** (o roteiro inteiro tem ~260 caracteres → centavos por render). Termos (Enterprise ToS, [x.ai/legal](https://x.ai/legal/terms-of-service-enterprise)): **o cliente é dono do output** e pode usá-lo comercialmente; proibido usar o output para treinar modelos e **proibido apresentar como gerado por humano**; vale a Acceptable Use Policy. Precisa `XAI_API_KEY` — **não configurada nesta máquina**, então não foi testada. Se usar, registrar aqui: voz, data, conta. |

Se no futuro entrar trilha/efeito/voz de terceiros, registrar: arquivo · URL · autor · licença · data · crédito exigido.
