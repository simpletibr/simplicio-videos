# Resultados dos testes feitos aqui (Linux, CPU, sem GPU)

Registro dos testes do kit ([LEIA-ME.md](LEIA-ME.md)). Os logs brutos (`logs\`), os relatórios JSON (`relatorios\`) e os scripts que fabricaram os casos sintéticos (`scripts_de_teste\`) citados abaixo não foram incluídos no repositório (o clipe usado tem pessoas reais e nenhuma mídia entra aqui): as tabelas desta página são o registro que ficou.

Gerado em 2026-10-16. Tudo abaixo rodou **sem GPU, sem Windows e sem nenhum modelo de IA de troca de personagem**. Os scripts foram executados com `python -I`
(modo isolado) a partir de uma pasta separada da dos dados.

## Ambiente
- Linux 6.18.44, Intel Xeon 2,1 GHz com 4 vCPU, 15,7 GB de RAM, sem GPU.
- Python 3.13.16 (ambiente virtual novo só para este teste): torch 2.14.1+cpu, transformers 5.20.1, numpy 2.5.4, opencv-python-headless 5.0.0.93, Pillow 12.3.0.
- ffmpeg 6.1.1 (Ubuntu). Pesos baixados do Hugging Face para o teste: facebook/dinov2-small (88 MB, Apache-2.0) e laion/CLIP-ViT-B-32-laion2B-s34B-b79K (605 MB, MIT).

## Entradas do teste
- Clipe: `clipe_original.mp4` (nome de origem omitido; sha256 `0c4a67cd0808315e47312f68f7e32f5ee046fabbf1a4e9d976ffc38cc710204e`, 274 quadros, 720x1280, 25 fps, áudio HE-AAC 44,1 kHz).
- Corte de 75 quadros (3,00 s) a partir de 3,0 s: sha256 `86a9e922208c44f3...`; versão 480x848: `c699b6a81603dcfe...`. Corte de 77 quadros: `70051628ce7a4e33...`, reduzido `a4490975b8de955b...`.
- Máscara do alvo **gerada só para o teste** (YOLOv8n-seg + cor laranja, igual ao método do protótipo anterior): 75 PNGs, área mediana 110.003 px. É imperfeita: vaza um pouco para o joelho do vizinho.
- Avatar: recorte do painel inferior direito da folha, 215x502 px, sha256 `060a6db1c3b891f1...` (idêntico nas duas execuções).

## Como os casos foram fabricados (`scripts_de_teste\gerar_casos.py`, só para teste)
"Troca falsa" = o avatar colado dentro da máscara sobre um buraco preenchido por inpaint em baixa resolução, com os pixels originais fora da máscara. "Saída crua de modelo" =
a troca falsa com borrão gaussiano de 0,7 px, ganho de 1% e ruído (desvio 2,5) no quadro inteiro, imitando um modelo que redesenha tudo. São imitações, **não saídas reais do Wan**.

## preparar_entradas.py
- 75 quadros e 77 quadros: contagem decodificada conferida (75/75 e 77/77), 720x1280 e 480x848, 25 fps, duração 3,00 s e 3,08 s.
- Duas execuções seguidas dão os mesmos sha256 (corte, reduzida e avatar) com `-threads 1` e `bitexact`.
- Áudio do corte e da versão reduzida com o mesmo hash do PCM (`8ae44234de5f3298...`).
- Fidelidade do corte contra os quadros 75 a 149 do original: PSNR médio 50,9 dB (recodificação x264 crf 12).
- Tempo no Linux de 4 vCPU: 16 s.

## medir_gpu.py (logs em `logs\medir_gpu_*.txt`)
| Teste | Resultado |
|---|---|
| Comando falso (3,2 s) sem GPU | termina sem erro; mede tempo 3,2 s e RAM; VRAM "não medida"; linha no CSV com `nvidia_smi = nao` |
| Comando que sai com código 3 | código 3 registrado, sem erro do medidor |
| Programa inexistente | mensagem clara, `erro_ao_iniciar` no CSV |
| Modo manual (ENTER via pipe depois de 2,2 s) | mede 2,2 s |
| `--tempo-max 2` | mata o comando em 2,0 s, `tempo_max` no CSV |
| `nvidia-smi` FALSO no PATH (VRAM sobe até 5.700 MB em 600 MB por chamada; duas GPUs; nome com vírgula; um `[N/A]`) | pico 5.700 MB de 6.144 MB (93%), base 1.500 MB, delta 4.200 MB, uso médio 52% e pico 99%, GPU 0 escolhida pela maior VRAM, GPU 1 listada à parte; série de 1 em 1 s gravada |
| `--formato-en` | vírgula e ponto decimal |
Não testado: `nvidia-smi` real, Windows (`GlobalMemoryStatusEx`, `CREATE_NO_WINDOW`, `cmd /c` para `.bat`).

## conferir_troca.py (relatórios em `relatorios\`, logs em `logs\conferir_*.txt`)
Esta tabela foi regerada com a versão final dos scripts (`scripts_de_teste\rodar_matriz_conferir.sh`; 5 min 29 s no total). Original = corte de 75 quadros 720x1280, máscara = pasta de 75 PNGs, avatar = PNG de 215x502. Limiares padrão: PSNR mínimo 40 dB, SSIM médio 0,98, alvo mudou em 30% ou mais, DINOv2 cosseno 0,50 e melhora de 0,05, CLIP 0,70 e melhora de 0,05, áudio com correlação de 0,999 ou mais.

| Caso | O que é | Quadros orig/troc | PSNR fora mín / média (dB) | SSIM fora | % do alvo que mudou | DINOv2 trocado (ator orig.) | CLIP trocado (ator orig.) | Áudio | Veredito | Itens que não passaram |
|---|---|---|---|---|---|---|---|---|---|---|
| T1_original_x_original | original contra ele mesmo (3 s, 75 quadros, 720x1280) | 75/75 | 100.0 / 100.0 | 1.0000 | 0.0 | 0.482 (0.482) | 0.674 (0.674) | IGUAL | HÁ FALHAS | alvo_mudou=FALHOU parece_com_o_avatar=FALHOU |
| C8_original_regravado | original regravado em x264 crf 14 (controle de codec) | 75/75 | 41.9 / 42.7 | 0.9906 | 0.0 | - | - | IGUAL | HÁ FALHAS | alvo_mudou=FALHOU |
| C1_troca_falsa_so_colada | avatar colado só dentro da máscara (troca falsa), original fora | 75/75 | 41.7 / 42.4 | 0.9900 | 93.4 | 0.744 (0.482) | 0.821 (0.674) | IGUAL | TUDO OK | - |
| C9_cru_composto | saída 'crua de modelo' (borrão+ruído no quadro todo) passada por compor_final.py | 75/75 | 41.8 / 42.5 | 0.9902 | 93.3 | 0.738 (0.482) | 0.817 (0.674) | IGUAL | TUDO OK | - |
| C10_composto_de_480p_16fps | gerado em 480x848 a 16 fps, composto com --reamostrar sobre o original 720x1280 | 75/75 | 41.7 / 42.7 | 0.9906 | 92.8 | 0.738 (0.482) | - | IGUAL | TUDO OK | - |
| R2_fluxo_1a_rodada_480p | fluxo da 1ª rodada: original reduzido 480x848, gerado 480x848 a 16 fps, máscara 720x1280 | 75/75 | 40.5 / 41.7 | 0.9896 | 92.8 | 0.738 (0.484) | - | IGUAL | TUDO OK | - |
| C2_recolorido | alvo recolorido (matiz +60), sem avatar | 75/75 | 41.2 / 41.6 | 0.9891 | 96.1 | 0.450 (0.482) | 0.565 (0.674) | IGUAL | HÁ FALHAS | parece_com_o_avatar=FALHOU |
| C3_violacao_fundo | troca falsa + retângulo +35 níveis fora da máscara | 75/75 | 30.0 / 30.5 | 0.9808 | 93.9 | 0.750 (0.482) | - | IGUAL | HÁ FALHAS | fora_da_mascara_nao_mudou=FALHOU |
| C6_modelo_cru | saída crua de modelo (sem compor_final): borrão 0,7 + ruído no quadro todo | 75/75 | 38.5 / 38.9 | 0.9616 | 93.4 | - | - | DIFERENTE (corr 0.99457) | HÁ FALHAS | fora_da_mascara_nao_mudou=FALHOU audio=FALHOU |
| R1_480x848_vs_original_720 | troca falsa reduzida a 480x848 contra o original 720x1280 | 75/75 | 37.9 / 38.6 | 0.9802 | 93.4 | - | - | IGUAL | HÁ FALHAS | fora_da_mascara_nao_mudou=FALHOU |
| C4a_audio_silencio | troca falsa com áudio de silêncio | 75/75 | 41.7 / 42.4 | 0.9900 | 93.4 | - | - | DIFERENTE (corr 0.00000) | HÁ FALHAS | audio=FALHOU |
| C4b_audio_seno | troca falsa com áudio de seno 440 Hz | 75/75 | 41.7 / 42.4 | 0.9900 | 93.4 | - | - | DIFERENTE (corr 0.00619) | HÁ FALHAS | audio=FALHOU |
| C4c_audio_aac96 | troca falsa com o áudio original recodificado em AAC 96 kb/s | 75/75 | 41.7 / 42.4 | 0.9900 | 93.4 | - | - | DIFERENTE (corr 0.99457) | HÁ FALHAS | audio=FALHOU |
| C4d_audio_aac320_equivalente | original com o áudio recodificado em AAC 320 kb/s | 75/75 | 100.0 / 100.0 | 1.0000 | 0.0 | - | - | EQUIVALENTE (corr 0.99998) | HÁ FALHAS | alvo_mudou=FALHOU |
| C5_falta_um_quadro | troca falsa sem o último quadro (74 de 75) | 75/74 | 41.7 / 42.4 | 0.9900 | 93.4 | - | - | IGUAL | HÁ FALHAS | quadros_fps_duracao=FALHOU |
| C7_sem_audio | troca falsa sem trilha de áudio | 75/75 | 41.7 / 42.4 | 0.9900 | 93.4 | - | - | o trocado nao tem audio | HÁ FALHAS | audio=FALHOU |
| M1_mascara_video_ffv1 | máscara como VÍDEO sem perda (ffv1), saída composta C9 | 75/75 | 41.8 / 42.5 | 0.9902 | 93.3 | - | - | IGUAL | OK com itens pulados | - |
| M2_mascara_video_x264 | máscara como VÍDEO x264 crf 20, saída composta C9 | 75/75 | 41.8 / 42.5 | 0.9902 | 93.3 | - | - | IGUAL | OK com itens pulados | - |
| M3_mascara_imagem_unica | UMA máscara estática para um alvo que se move | 75/75 | 22.7 / 31.3 | 0.9797 | 81.0 | - | - | IGUAL | HÁ FALHAS | fora_da_mascara_nao_mudou=FALHOU |
| N1_dinov2_offline_sem_cache | troca falsa, DINOv2 com --offline e sem pesos em cache | 20/20 | 41.7 / 42.2 | 0.9889 | 94.9 | pulado | - | IGUAL | OK com itens pulados | - |

Leitura dos resultados:
- **Original contra ele mesmo:** diferença zero fora da máscara (PSNR 100 dB, SSIM 1,0000, 0 pixels alterados), áudio com o mesmo hash. Ele também aponta, corretamente, que o alvo **não mudou** e que não ficou mais parecido com o avatar.
- **Piso do codec:** recodificar o próprio original em x264 crf 14 deixa 41,9 a 42,7 dB fora da máscara (nada mudou de verdade). O limiar de 40 dB foi escolhido entre esse piso e a "saída crua de modelo" (38,5 dB).
- **Detecta:** fundo alterado (30,0 dB), saída crua de modelo (38,5 dB e SSIM 0,962), áudio de silêncio ou seno (correlação 0,000 e 0,006), áudio recodificado em AAC 96 kb/s (0,99457, abaixo de 0,999), falta de 1 quadro, vídeo sem áudio, máscara estática errada (22,7 dB no pior quadro), alvo só recolorido (não parece com o avatar), e comparação com resolução diferente sem usar o original reduzido (37,9 dB).
- **Aceita:** troca falsa, saída crua depois do `compor_final.py` (41,8 dB), gerada em 480x848 a 16 fps depois de `compor_final.py --reamostrar`, fluxo da 1ª rodada com original reduzido e máscara de 720x1280, áudio AAC 320 kb/s como "equivalente" (correlação 0,99998).
- **Semelhança com o avatar (calibração):** o ator original já tem cosseno 0,482 (DINOv2-small) e 0,674 (CLIP) com o avatar; o avatar colado chegou a 0,744 e 0,821; o alvo recolorido ficou em 0,450 e 0,565. Por isso o critério que vale é a **melhora sobre o ator original**. Com saídas reais do Wan os valores serão outros: estes limiares são ponto de partida.
- **Máscara como vídeo:** com vídeo sem perda (ffv1) e com vídeo x264 crf 20 os números saíram idênticos aos da pasta de PNGs (PSNR 41,8 dB mínimo, 42,5 dB médio, 93,3% do alvo mudado). Com imagem única, o conferidor acusou o problema (22,7 dB).
- **Tempo (CPU de 4 vCPU):** 10 a 11 s para 75 quadros 720x1280 sem modelo; 17 a 21 s com DINOv2; 21 a 25 s com DINOv2 e CLIP; 37,7 s para os 274 quadros do clipe inteiro (original contra ele mesmo).

## compor_final.py
- Saída crua sintética (720x1280, 25 fps) recomposta sobre o original: fora da máscara 41,8 dB (mín.) e 42,5 dB (média), áudio com o mesmo hash do original (cópia sem recodificar). Tempo: 12 s para 75 quadros.
- Saída em 480x848 e 16 fps (48 quadros) com `--reamostrar` sobre o original de 75 quadros: 75 quadros, 41,7 dB mínimo. Sem `--reamostrar` dá erro claro ("números de quadros diferentes") e **não deixa arquivo pela metade**.
- Fluxo da 1ª rodada (original reduzido 480x848, gerado 480x848 a 16 fps, máscara de 720x1280 redimensionada por vizinho mais próximo): 40,5 dB mínimo, 41,7 dB médio.

## receita_test_hash.py (logs em `logs\receita_hash_*.txt`)
| Cenário | Resultado |
|---|---|
| Texto determinístico, 2 rodadas | IDENTICA (bytes) |
| Saída aleatória | DIFERENTE |
| Vídeo x264 com `-threads 1` e `bitexact` | IDENTICA (bytes) |
| Vídeo só com um metadado diferente | bytes diferentes, **IDENTICA NO CONTEUDO** (hash dos quadros e do PCM iguais) |
| Vídeo com ruído diferente | DIFERENTE, PSNR de cerca de 42 dB entre as rodadas (42,05 a 42,13 em duas execuções; a semente do ruído é aleatória) |
| Saída não criada | erro claro, código 2 |
| Comando que falha (código 5) | erro claro, código 2, teste interrompido |
| Modo `--comparar` com dois arquivos | funciona sem rodar nada |
| Saída que é uma pasta | hash da lista de arquivos, IDENTICA |
| 3 rodadas, saída aleatória | 3 hashes diferentes |

## Problemas que os testes revelaram (já corrigidos no kit)
1. **Conversão de cor do ffmpeg:** ao gravar um vídeo a partir de quadros RGB, o ffmpeg com as opções padrão deixa um erro de até 5 níveis por canal (medido em cinzas puros). Isso aparecia como "o fundo mudou" (PSNR de 39 dB sem nada ter mudado). `compor_final.py` agora usa `accurate_rnd+full_chroma_int` e copia a etiqueta e a matriz de cor do original: o piso passou para 42 a 43 dB.
2. **Etiqueta de cor:** o original do clipe é `bt709` (faixa `tv`); um vídeo regravado sem etiqueta sai com as cores levemente deslocadas. `conferir_troca.py` agora avisa quando as etiquetas diferem.
3. **`compor_final.py`** deixava um arquivo pela metade quando dava erro; agora apaga.
4. **`checar_maquina.py`** dependia do `wmic`, que não existe mais em versões novas do Windows 11; agora usa `GlobalMemoryStatusEx` (não testado no Windows) e lista as placas de vídeo pelo PowerShell.
5. **Recorte do avatar:** com o limiar de fundo em 30, partes brancas das mangas eram tratadas como fundo no conferidor; baixei para 16.
6. **Limiares:** os padrões iniciais (38 dB, 0,97, 0,30) foram refeitos depois de medir o piso do codec e as semelhanças de controle.
7. **`conferir_troca.py --help` quebrava** por um sinal de porcentagem no texto de ajuda (o `argparse` trata `%` como formato). Corrigido e conferido com `--help` nos cinco scripts.
8. **Veredito honesto:** quando a semelhança com o avatar não é verificada (sem pesos em cache com `--offline`, sem `torch` ou com `--modelo nenhum`), o resumo agora diz "TUDO OK, MAS COM ITENS PULADOS" e o JSON lista os `pulados`, em vez de só "TUDO OK". Caso `N1` na tabela: DINOv2 com `--offline` e sem cache vira item pulado com o motivo, sem erro nem traceback.

## Limites
- Nada disto prova que o kit funciona no Windows ou com GPU.
- Os casos de troca são sintéticos. A semelhança com o avatar (DINOv2/CLIP) mede aparência global, não identidade de rosto.
- A máscara de teste é imperfeita; com a sua máscara dos cliques do SAM os números mudarão.
- Os `nvidia-smi` e a série de VRAM são simulados; só o formato de leitura foi validado.
