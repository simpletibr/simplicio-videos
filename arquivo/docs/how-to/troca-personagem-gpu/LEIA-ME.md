---
title: Kit de medição da troca de personagem em GPU de 6 GB
summary: Passo a passo para medir, num notebook Windows com GPU NVIDIA de 6 GB, se a troca de personagem em vídeo (Wan2.2-Animate, VACE) cabe na máquina, com scripts de medida e de conferência testados só em CPU.
commands: python scripts/kit_gpu/checar_maquina.py, python scripts/kit_gpu/preparar_entradas.py, python scripts/kit_gpu/medir_gpu.py, python scripts/kit_gpu/compor_final.py, python scripts/kit_gpu/conferir_troca.py, python scripts/kit_gpu/receita_test_hash.py
last_verified: 2026-10-16
---

# Kit de teste: trocar um personagem em vídeo num notebook com GPU de 6 GB

Data: 2026-10-16. Escrito para quem não é programador. Comandos para copiar e colar no PowerShell do Windows 11.
Este kit só tem texto e scripts pequenos. Ele não traz pesos de modelo, nem o seu clipe, nem o seu avatar.

**Onde está o kit.** No repositório simplicio-videos, em duas pastas: [`scripts/kit_gpu/`](../../../scripts/kit_gpu) (os seis scripts Python) e `docs/how-to/troca-personagem-gpu/` (esta pasta: este texto, o [prompt para a sessão da GPU](PROMPT-sessao-gpu.md), os [resultados dos testes feitos em CPU](RESULTADOS.md) e a `planilha_medidas.csv`).
**O kit também pode ser usado fora do repositório:** copie as duas pastas, mantendo esses caminhos, para `C:\troca\kit-gpu` (ficam `C:\troca\kit-gpu\scripts\kit_gpu` e `C:\troca\kit-gpu\docs\how-to\troca-personagem-gpu`).
Neste repositório ele é só material de operação e de teste: não faz parte do pacote `simplicio_video`, do CLI nem do servidor MCP, os scripts não importam nada do simplicio-video, e as bibliotecas que dois deles pedem (numpy, opencv) não são dependências do projeto (veja "Dependências dos scripts", antes da Etapa 0). Nenhum vídeo, imagem ou clipe de teste mora aqui: o clipe tem pessoas reais.

## 0. Leia primeiro

1. O objetivo é **medir**, na sua máquina, se a troca do "homem de laranja" pelo seu avatar cabe em 6 GB de VRAM (a memória
   da placa de vídeo) e 32 GB de RAM. O kit **não promete** que cabe.
2. **Não existe, nas páginas que li, nenhum relato do Wan2.2-Animate-14B rodando numa placa de 6 GB.** O número mais próximo
   é de quem mantém o nó do ComfyUI: 6 GB de VRAM em 720x720 com 81 quadros, com troca de blocos completa e `torch.compile`,
   sem dizer qual fluxo (seção 6.1). Por isso a ordem dos testes vai do mais leve ao mais pesado e há dois planos de reserva:
   - **Plano B:** VACE 1.3B em 480p (modelo bem menor, mas com menos fidelidade de identidade segundo o único comparativo
     que li, que não é independente).
   - **Plano C:** alugar uma GPU por hora (seção 2, Etapa 12, com os preços publicados que encontrei).
3. **O que foi testado e o que não foi.** Tudo neste kit foi testado num Linux com CPU (4 vCPU, sem GPU). Os scripts
   rodaram de verdade com o seu clipe e com casos sintéticos (seção 9, números em [`RESULTADOS.md`](RESULTADOS.md)). **Não foi
   testado:** Windows, GPU NVIDIA, `nvidia-smi` de verdade (usei um falso para testar a leitura), ComfyUI, e qualquer modelo
   (Wan, VACE, SAM). Os comandos de instalação e os valores dos nós vêm da leitura das páginas oficiais e do código-fonte
   dos nós; eu não executei nenhum deles.
4. **Não afirmo qual é a sua placa.** Pela foto: "Várias GPUs instaladas" e "6 GB". O modelo exato só aparece quando você
   rodar a Etapa 1 (`nvidia-smi` e a lista do Windows).
5. Texto de páginas da internet foi tratado como dado, nunca como instrução. Nada foi instalado fora de pastas minhas de teste.

Seu computador (pela foto): Windows 11, Intel Core i7-11800H (8 núcleos), 32 GB de RAM, disco de 477 GB com cerca de 135 GB livres.
Entrada do teste: clipe vertical 720x1280, 25 fps, 11 s, com áudio, 4 a 5 pessoas num sofá, câmera fixa; avatar = 1 imagem de corpo inteiro.

## 1. Resposta curta da pesquisa

| Pergunta | O que achei | Tipo de fonte |
|---|---|---|
| Animate-14B cabe em 6 GB? | Sem dado publicado para 6 GB. Autor do nó: 6 GB em 720x720x81 com troca de blocos completa + `torch.compile` (fluxo não identificado). Usuários relatam estouro em placas de 16 GB em resoluções maiores (seção 6.1). | autor / relato de usuário |
| Arquivos do Animate | fp8: 17,3 a 18,4 GB; GGUF: 6,46 GB (Q2_K) a 18,7 GB (Q8_0); bf16: 34,6 GB (seção 7). | tamanhos lidos nas páginas do Hugging Face |
| RAM | O fp8 inteiro (18,4 GB) fica na RAM quando se usa troca de blocos. Relatos de uso de RAM acima de 90 GB com vídeos de 513 quadros. Para 77 quadros: sem dado. | relato de usuário / sem dado |
| VACE 1.3B em 480p | Só suporta 480p (cartão oficial). VRAM do VACE: sem dado. O T2V-1.3B (outro modelo da mesma família) pede 8,19 GB segundo o autor (com opções de descarregar). | autor / sem dado |
| Máscara do alvo | SAM 2.1 (Apache-2.0; tiny 0,16 GB, small 0,18 GB) é o que os exemplos do Kijai usam (base_plus). SAM 3.1 existe no ComfyUI (1,75 GB, licença SAM). VRAM de ambos: sem dado. | autor |
| Máscara automática do Wan | O guia oficial diz que ela é "só para vídeo de uma pessoa" e pode falhar em vídeo com várias. Seu clipe tem várias: use cliques seus no SAM. | autor (guia oficial) |
| Windows e NVIDIA | O ComfyUI portátil NVIDIA traz Python 3.13 e PyTorch com CUDA 13.0; só enxerga placas NVIDIA (CUDA), nunca a Intel integrada. | autor (README do ComfyUI e código) |
| Disco | Cerca de 55 GB de downloads se você fizer todas as etapas, mais reservas; cerca de 73 GB no total. Cabe nos 135 GB (seção 8). | soma dos tamanhos lidos |

## 2. Passo a passo (do mais leve ao mais pesado)

Pastas usadas (caminhos curtos e sem acento evitam erros no Windows):

```
mkdir C:\troca
mkdir C:\troca\saidas
```

Coloque seu clipe em `C:\troca\clipe.mp4` e a folha do avatar em `C:\troca\folha.webp`. Os scripts do kit estão na pasta `scripts\kit_gpu` (a do repositório, ou a da cópia em `C:\troca\kit-gpu`, veja a seção 0).
Abra o PowerShell (tecla Windows, digite "PowerShell"). Diga onde estão os scripts e vá para a pasta de trabalho:

```
$kit = "C:\troca\kit-gpu\scripts\kit_gpu"
cd C:\troca
```

(Se você baixou o repositório inteiro, ponha em `$kit` o caminho da pasta `scripts\kit_gpu` dele. **Rode os comandos a partir de `C:\troca`, não de dentro do repositório:** por padrão os scripts gravam o resultado na pasta atual (`medidas_gpu.csv`, `relatorio_conferencia.json`, as pastas `entradas` e `rodadas_hash`). Em cada janela nova do PowerShell, defina `$kit` de novo e, depois da Etapa 3, o `$py`.)

Depois do passo 3, quase tudo roda com o Python que vem dentro do ComfyUI:

```
$py = "C:\troca\ComfyUI_windows_portable\python_embeded\python.exe"
```

(Esse `$py` só existe depois da Etapa 3; antes dela use `python`.)

### Dependências dos scripts do kit (não são do projeto)

| Script | Precisa de | Observação |
|---|---|---|
| `checar_maquina.py` | só o Python | consulta o `nvidia-smi`, o ffmpeg, o Git e o `torch` se existirem; nenhum é obrigatório |
| `medir_gpu.py` | só o Python | sem `nvidia-smi` mede só tempo e RAM |
| `receita_test_hash.py` | só o Python | o ffmpeg, se existir, serve para comparar o conteúdo de vídeos |
| `preparar_entradas.py` | Python, ffmpeg e Pillow (`python -m pip install pillow`) | o Pillow só é usado para recortar o avatar (`--folha`) |
| `compor_final.py` | Python, ffmpeg, `numpy` e `opencv-python-headless` | |
| `conferir_troca.py` | Python, ffmpeg, `numpy` e `opencv-python-headless`; `torch` e `transformers` para a semelhança com o avatar (DINOv2, CLIP) | com `--modelo nenhum` não usa `torch` |

Cada script avisa e mostra o comando do `pip` quando falta uma biblioteca. Nada disto entra no `pyproject.toml` do simplicio-video. Quem mantém o repositório e só quer conferir que os scripts abrem usa um ambiente virtual descartável (seção 12).

### Etapa 0. Programas básicos
- **Disco:** cerca de 0,3 GB. **Tempo:** meça e anote.
- Python 3.13 (64 bits) pelo site python.org, marcando "Add python.exe to PATH". Teste: `python --version`.
- ffmpeg: `winget install Gyan.FFmpeg` (não verifiquei esse nome de pacote; se falhar, baixe uma versão para Windows em ffmpeg.org e coloque a pasta `bin` no PATH). Teste, em uma janela nova do PowerShell: `ffmpeg -version`.
- Git: `winget install Git.Git` (também não verificado). Sem Git, use "Download ZIP" de cada repositório na Etapa 4.
- Driver NVIDIA atualizado (site da NVIDIA ou aplicativo da NVIDIA). O README do ComfyUI só diz "atualize os drivers da Nvidia se não iniciar", sem número. Fontes da comunidade citam driver 580 ou mais novo para o CUDA 13 (não é número oficial do ComfyUI).
- Para extrair o `.7z` do ComfyUI basta o Explorador de Arquivos do Windows 11 (diz o README); se não conseguir, instale o 7-Zip.

### Etapa 1. Conferir a máquina
- **Disco:** 0. **Tempo:** segundos (meça).
```
cd C:\troca
python "$kit\checar_maquina.py"
```
Cole a saída inteira no chat. Ela lista as placas de vídeo que o Windows vê (a Intel e a NVIDIA), o nome e a VRAM da NVIDIA
(`nvidia-smi`), RAM, disco livre, ffmpeg e Git. (Nesta versão corrigi a leitura de RAM no Windows novo, onde o `wmic` não existe mais; não testei no Windows.)

### Etapa 2. Preparar as entradas (corte de 3 s, versão reduzida e avatar)
- **Disco:** cerca de 6 MB. **Tempo:** 16 s no Linux de 4 vCPU onde testei; no seu PC: meça e anote.
```
cd C:\troca
python "$kit\preparar_entradas.py" --clipe "C:\troca\clipe.mp4" --folha "C:\troca\folha.webp" --saida C:\troca\entradas --quadros 77
```
Gera em `C:\troca\entradas`: `clipe_corte_77q_720x1280.mp4`, `clipe_corte_77q_480x848.mp4` (mesmo áudio), `avatar_corpo_inteiro.png` e `manifesto_entradas.json`.
- **Por que 77 e não 75 quadros:** os modelos Wan trabalham com 4n+1 quadros (73, 77, 81); o nó do Animate anda de 4 em 4 e a janela dele é de 77 (README do Cordux: "o +1 é exigido pelo Wan"; código do nó). Sem `--quadros 77` o script usa 75 quadros (3,00 s exatos), mas o nó provavelmente ajustaria para 73 ou 77 e o número de quadros deixaria de bater com o original (não consegui confirmar o comportamento do nó). 77 quadros = 3,08 s.
- **Por que começa em 3,0 s:** no seu clipe o homem de laranja só aparece inteiro a partir do quadro 75; nos 3 s iniciais ele está ausente ou quase todo fora do quadro (medido no protótipo anterior). Para começar do zero use `--inicio 0`.
- **Por que 848 e não 854:** o ComfyUI pede largura e altura múltiplas de 16 (página do template Animate); 854 não é. Para 480x854 use `--altura 854`.
- **O avatar:** o recorte do painel inferior direito sai com 215x502 px (o rosto fica com poucos pixels). Isso limita a fidelidade do rosto em qualquer modelo; o script avisa.
- Se o resultado do script disser `FALHOU`, pare e mande a mensagem.

### Etapa 3. ComfyUI portátil NVIDIA e a prova de que ele usa a NVIDIA
- **Disco:** download de 2,01 GB (lido no cabeçalho do arquivo); descompactado: **não medi**, reserve 10 GB. **Tempo:** depende da internet.
- Baixe: https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z (hoje esse link apontava para a versão v0.41.0). Extraia em `C:\troca` para ficar `C:\troca\ComfyUI_windows_portable`.
- Se a sua NVIDIA for da série GTX 10 ou mais antiga, use o `..._nvidia_cu126.7z` (o README manda NÃO usar esse em placas da série 20 para cima). O `nvidia-smi` da Etapa 1 diz o modelo.
- Abra `C:\troca\ComfyUI_windows_portable\run_nvidia_gpu.bat`. Nas primeiras linhas do console procure (formato tirado do código-fonte):
  - `Total VRAM 6144 MB, total RAM ... MB`  (deve ser cerca de 6 GB e cerca de 32 GB)
  - `pytorch version: ...+cu130`
  - `Device: cuda:0 NVIDIA ...`  (o nome da placa NVIDIA)
  Se aparecer `Device: cpu`, ou "Torch not compiled with CUDA enabled", ou a janela fechar sozinha: atualize o driver (o próprio `.bat` diz isso) e, se aparecer erro de `c10.dll`, instale o "vc redist" (https://aka.ms/vc14/vc_redist.x64.exe, endereço que o `.bat` imprime).
- **Como garantir NVIDIA e não a Intel integrada ("Várias GPUs"):**
  1. A versão portátil NVIDIA usa PyTorch com CUDA, e o CUDA só enxerga placas NVIDIA. A Intel integrada só seria usada pela versão "intel" do ComfyUI, que não vamos instalar.
  2. No Windows, o ComfyUI já fixa `CUDA_VISIBLE_DEVICES=0` (uma GPU só) se você não escolher outra (código `main.py`); só mexa nisso, com `--cuda-device N`, se `nvidia-smi` listar duas NVIDIA.
  3. Prova com número: durante qualquer geração, `medir_gpu.py` (seção 3) grava a VRAM da NVIDIA; se a VRAM sobe, é ela que está trabalhando.
  4. Opcional, **não verificado por mim**: Configurações > Sistema > Tela > Elementos gráficos > adicionar `python_embeded\python.exe` > Alto desempenho. Para cálculo em CUDA não deve ser necessário.
  5. Para ganhar VRAM: feche navegadores e programas. O README do Wan2GP diz que desligar a aceleração de GPU do navegador libera de 1 GB a 5 GB de VRAM.
- Teste do PyTorch (opcional): `cd C:\troca\ComfyUI_windows_portable` e depois `.\python_embeded\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"`. Esperado: `True` e o nome da NVIDIA.
- Feche o ComfyUI (Ctrl+C na janela do console).

### Etapa 4. Instalar os nós do ComfyUI
- **Disco:** os repositórios são pequenos; as bibliotecas (`pip`) somam um valor que **não medi** (reserve 3 GB). **Tempo:** meça e anote.
```
cd C:\troca\ComfyUI_windows_portable\ComfyUI\custom_nodes
git clone https://github.com/kijai/ComfyUI-WanVideoWrapper
git clone https://github.com/kijai/ComfyUI-WanAnimatePreprocess
git clone https://github.com/kijai/ComfyUI-KJNodes
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite
git clone https://github.com/kijai/ComfyUI-segment-anything-2
cd C:\troca\ComfyUI_windows_portable
.\python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-WanVideoWrapper\requirements.txt
.\python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-WanAnimatePreprocess\requirements.txt
.\python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-KJNodes\requirements.txt
.\python_embeded\python.exe -m pip install -r ComfyUI\custom_nodes\ComfyUI-VideoHelperSuite\requirements.txt
```
(O `ComfyUI-segment-anything-2` não tem `requirements.txt`; o arquivo de pesos dele baixa sozinho na Etapa 5.)
- Sem Git: em cada página do GitHub use Code > Download ZIP e extraia dentro de `custom_nodes`. (O endereço padrão `https://github.com/DONO/REPO/archive/refs/heads/main.zip` não pude testar daqui.)
- **Anote a versão exata de cada nó** (o repositório do Kijai não publica versões, só commits):
```
cd C:\troca\ComfyUI_windows_portable\ComfyUI\custom_nodes
Get-ChildItem -Directory | ForEach-Object { "$($_.Name) $(git -C $_.FullName rev-parse HEAD)" }
```
- Se o `pip` reclamar do `onnxruntime-gpu` ou de CUDA: é o nó de pose (`WanAnimatePreprocess`). Saída de emergência, **minha sugestão, não testada**: `.\python_embeded\python.exe -m pip uninstall -y onnxruntime-gpu` e depois `.\python_embeded\python.exe -m pip install onnxruntime`, e no nó `OnnxDetectionModelLoader` escolha `CPUExecutionProvider` (esse nó oferece `CUDAExecutionProvider` e `CPUExecutionProvider`).
- Abra o ComfyUI de novo. No console, a lista "Import times for custom nodes" mostra os que falharam com "IMPORT FAILED". Mande o texto do erro se houver.
- **SageAttention e Triton são opcionais.** Os fluxos de exemplo do Kijai pedem `sageattn` e um nó `WanVideoTorchCompileSettings`; na primeira rodada, no `WanVideoModelLoader` troque `attention_mode` para `sdpa` (é o padrão do nó) e **desconecte** o nó de compile.
- Os fluxos de exemplo ficam em `ComfyUI\custom_nodes\ComfyUI-WanVideoWrapper\example_workflows\`. Arraste o `.json` para a janela do ComfyUI:
  - `wanvideo_WanAnimate_preprocess_example_02.json` (Animate com troca, pose e rosto pelos nós ViTPose e SAM 2; é o que usamos nas Etapas 5, 6, 8, 9 e 10);
  - `wanvideo_1_3B_VACE_examples_03.json` (VACE 1.3B, Etapa 7).
  (Existe também o `wanvideo_WanAnimate_example_01.json`, mas ele usa o nó `DWPreprocessor` de outro pacote, o `comfyui_controlnet_aux`, que não instalamos.)

### Etapa 5. Máscara do alvo com SAM 2.1 (a etapa mais leve de IA)
- **Disco:** 0,18 GB (small). **Tempo:** sem dado para a sua placa; meça e anote. (Dado do autor, numa A100: 84,8 quadros por segundo para o small, que não vale para 6 GB.)
- Os pesos baixam sozinhos (`DownloadAndLoadSAM2Model` grava em `ComfyUI\models\sam2`). Modelos: `sam2.1_hiera_tiny` (0,156 GB), `small` (0,184 GB), `base_plus` (0,323 GB, o dos exemplos), `large` (0,898 GB). Em `segmentor` escolha **video**; em `device`, `cuda` (ou `cpu` com `precision` fp32, se quiser poupar a VRAM nesta etapa).
- No fluxo `wanvideo_WanAnimate_preprocess_example_02.json`, o `Sam2Segmentation` recebe a **caixa** que o nó `PoseAndFaceDetection` acha. O código desse nó pega a **primeira detecção por quadro** (`detector(...)[0][0]`): num grupo de pessoas ela pode pular de uma pessoa para outra. Por isso, para o seu clipe, troque a caixa por **cliques seus**: adicione um nó `PointsEditor` (vem no ComfyUI-KJNodes; duplo clique no fundo da tela e digite "PointsEditor"), ligue a entrada `bg_image` dele ao vídeo carregado, e ligue `positive_coords` ao `coordinates_positive` do `Sam2Segmentation` (e `negative_coords` ao `coordinates_negative`); **desconecte o `bboxes`**. É a mesma ligação que o `wanvideo_WanAnimate_example_01.json` do Kijai faz (lida no arquivo), mas não testei no ComfyUI.
- **Clique no homem de laranja no primeiro quadro** (cliques positivos) e, se a máscara vazar para um vizinho, ponha cliques negativos nele. Segundo o nó, o editor pega o primeiro quadro do vídeo quando você manda executar: rode uma vez para o quadro aparecer e então clique. O `Sam2Segmentation` (modo `video`) propaga a máscara para todos os quadros.
- Para a pose, uma ideia **minha, não testada**: pintar de cinza tudo fora da máscara antes de mandar o vídeo para o detector de pose, para ele só ver o alvo (o detector de pose também pega uma pessoa por quadro).
- Confira a máscara com `MaskPreview` nos quadros 0, 38 e 76. Para guardar: ligue a máscara a `MaskToImage` e depois a `SaveImage` (prefixo `mascara`). Copie os PNGs de `ComfyUI\output` para `C:\troca\mascaras` (devem ser tantos quantos os quadros do clipe: 77).
- Opcional, mais pesado: **SAM 3.1** nativo do ComfyUI (modelo de 1,75 GB, `ComfyUI\models\checkpoints\sam3.1_multiplex_fp16.safetensors`; no menu Workflow > Browse Templates > Utility: "SAM3: Video Segmentation"). Funciona por texto (até 32 tokens) e o nó `SAM3_VideoTrack` aceita uma máscara inicial; a página não diz como mandar clique ou caixa nem como exportar um vídeo de máscara. Licença SAM (seção 7). VRAM: sem dado. Fica como segunda opção.
- Anote: tempo, pico de VRAM (com `medir_gpu.py`, seção 3), e se a máscara ficou boa.

### Etapa 6. Pose e rosto (pré-processamento do Animate)
- **Disco:** 1,30 GB. **Tempo:** sem dado; meça e anote.
- Baixe para `C:\troca\ComfyUI_windows_portable\ComfyUI\models\detection` (crie a pasta se não existir):
```
cd C:\troca\ComfyUI_windows_portable\ComfyUI\models
mkdir detection
curl.exe -L -C - -o detection\yolov10m.onnx https://huggingface.co/Wan-AI/Wan2.2-Animate-14B/resolve/main/process_checkpoint/det/yolov10m.onnx
curl.exe -L -C - -o detection\vitpose-l-wholebody.onnx https://huggingface.co/JunkyByte/easy_ViTPose/resolve/main/onnx/wholebody/vitpose-l-wholebody.onnx
```
  (`-C -` retoma o download se cair.) Há também o ViTPose-H, mais pesado (2,55 GB mais um arquivo `.onnx` pequeno, em `Kijai/vitpose_comfy`); não é necessário para o primeiro teste.
- No fluxo, o nó `OnnxDetectionModelLoader` carrega os dois; `onnx_device` = `CUDAExecutionProvider` (padrão) ou `CPUExecutionProvider`. O nó `PoseAndFaceDetection` produz a pose e os recortes de rosto (512 px) para o Animate; `DrawViTPose` desenha o vídeo de pose.
- Anote: tempo, pico de VRAM e qual provedor (CUDA ou CPU) funcionou.

### Etapa 7. Plano B: VACE 1.3B em 480p
- **Disco:** 11,3 GB (modelo de vídeo 2,84 GB, módulo VACE 1,47 GB, texto UMT5 fp8 6,73 GB, VAE 0,25 GB). **Tempo:** sem dado para 6 GB; meça e anote.
```
cd C:\troca\ComfyUI_windows_portable\ComfyUI\models
mkdir diffusion_models, text_encoders, vae
curl.exe -L -C - -o diffusion_models\wan2.1_t2v_1.3B_fp16.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_t2v_1.3B_fp16.safetensors
curl.exe -L -C - -o diffusion_models\Wan2_1-VACE_module_1_3B_bf16.safetensors https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1-VACE_module_1_3B_bf16.safetensors
curl.exe -L -C - -o text_encoders\umt5-xxl-enc-fp8_e4m3fn.safetensors https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/umt5-xxl-enc-fp8_e4m3fn.safetensors
curl.exe -L -C - -o vae\Wan2_1_VAE_bf16.safetensors https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors
```
  (Se `mkdir` disser que a pasta já existe, tudo bem.)
- Abra `wanvideo_1_3B_VACE_examples_03.json`. Valores do exemplo do Kijai: 480x832, 20 passos, cfg 4, shift 8, `unipc`, troca de blocos do VACE (`vace_blocks_to_swap`) = 15 (o VACE tem 15 blocos; o nó diz que com pelo menos 1 bloco trocado as saídas intermediárias também vão para a RAM e a VRAM cai bastante), `attention_mode` = `sdpa`.
- Para trocar o personagem: o nó `WanVideoVACEEncode` recebe os quadros de entrada, a **máscara** (branco = região a gerar) e a **imagem de referência** (o avatar). Os quadros de entrada devem ter a região do alvo pintada de cinza. **Não consegui verificar essa ligação no exemplo** (o exemplo mostra pintura externa, quadro inicial/final e profundidade, não a troca com máscara); se não conseguir ligar, mande uma captura de tela.
- Limite do modelo: só 480p (o cartão do Wan2.1-VACE-1.3B diz 480P, cerca de 81x480x832, e 720P sem suporte).
- Dados publicados: T2V-1.3B pede 8,19 GB (autor do Wan2.1, com opções de descarregar); um teste do autor do nó com janela de contexto no T2V-1.3B usou menos de 5 GB e levou 10 minutos numa 5090 (não é VACE e não é 6 GB). Para o VACE em 6 GB: sem dado.

### Etapa 8. Animate 14B quantizado GGUF Q3_K_S (o 14B mais leve)
- **Disco:** 11,4 GB (modelo 7,97 GB, CLIP-vision 1,26 GB, LoRA de 4 passos 0,74 GB, LoRA de iluminação 1,44 GB; o texto e o VAE já vieram na Etapa 7).
```
cd C:\troca\ComfyUI_windows_portable\ComfyUI\models
mkdir clip_vision, loras
curl.exe -L -C - -o diffusion_models\Wan2.2-Animate-14B-Q3_K_S.gguf https://huggingface.co/QuantStack/Wan2.2-Animate-14B-GGUF/resolve/main/Wan2.2-Animate-14B-Q3_K_S.gguf
curl.exe -L -C - -o clip_vision\clip_vision_h.safetensors https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors
curl.exe -L -C - -o loras\lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors
curl.exe -L -C - -o loras\WanAnimate_relight_lora_fp16.safetensors https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/LoRAs/Wan22_relight/WanAnimate_relight_lora_fp16.safetensors
```
  O README do nó diz que o carregador principal também abre GGUF. **Não consegui confirmar** que ele lista arquivos `.gguf` da pasta `diffusion_models`; se não aparecer, copie o arquivo também para `ComfyUI\models\unet` (pasta que o cartão da QuantStack e o nó ComfyUI-GGUF usam). Relatos de usuários mostram o GGUF Q4_K_M rodando com os nós do Kijai (seção 6.1).
- Abra `wanvideo_WanAnimate_preprocess_example_02.json` (com a troca do SAM por cliques, Etapa 5) e ajuste (valores de partida para 6 GB, tirados de comentários do autor, de relatos e do código dos nós; **nenhum foi testado por mim**):

| Nó | Campo | Exemplo do Kijai | Ponha para 6 GB |
|---|---|---|---|
| `WanVideoModelLoader` | modelo | `...fp8_e4m3fn_scaled_KJ` | o `.gguf` Q3_K_S |
| `WanVideoModelLoader` | `attention_mode` | `sageattn` | `sdpa` |
| `WanVideoModelLoader` | `base_precision` | `fp16_fast` | `fp16` (o `fp16_fast` pede PyTorch muito novo, diz o autor) |
| `WanVideoModelLoader` | `compile_args` | ligado | desconectar |
| `WanVideoBlockSwap` | `blocks_to_swap` | 25 | **40** (o 14B tem 40 blocos; mais que isso não ajuda) |
| `WanVideoBlockSwap` | `offload_img_emb`, `offload_txt_emb` | falso | verdadeiro |
| `WanVideoBlockSwap` | `use_non_blocking` | verdadeiro | **falso** (usa mais RAM; usuários precisaram desligar acima de 30 blocos) |
| `WanVideoBlockSwap` | `prefetch_blocks` | 1 | 0 (o nó diz que prefetch aumenta o uso de memória) |
| `INTConstant` chamados "Width" e "Height" | valor | 832, 480 | **480, 848** (o exemplo é horizontal; o seu vídeo é vertical. Esses dois nós alimentam o carregamento do vídeo, o redimensionamento do avatar e o `WanVideoAnimateEmbeds`) |
| `WanVideoAnimateEmbeds` | `num_frames` | 501 | **77**: o valor vem ligado do `VHS_LoadVideo` (que conta os quadros do arquivo); confira que ele mostra 77 (o nó anda de 4 em 4: 73, 77, 81) |
| `WanVideoAnimateEmbeds` | `frame_window_size` | 77 | 77 |
| `WanVideoAnimateEmbeds` | `tiled_vae` | falso | verdadeiro |
| `WanVideoDecode` | `enable_vae_tiling` | falso | verdadeiro |
| `WanVideoTextEncodeCached` | `device` (último campo) | `gpu` | **`cpu`** (o texto fp8 tem 6,7 GB e não cabe em 6 GB junto do resto; o nó descarrega o T5 depois de usar) |
| `WanVideoVAELoader` | arquivo | `Wan2_1_VAE_bf16` | manter bf16 (o autor diz que o VAE fp32 quase dobra a VRAM do VAE) |
| `WanVideoSampler` | passos / semente | 6 / 42 fixa | 4 a 6 / 42 fixa (a LoRA de 4 passos está no exemplo com força 1,2) |
| `VHS_LoadVideo` | `force_rate` | 16 | 0 (não mudar o fps: ficam os 25 do clipe) |
| `VHS_LoadVideo` | arquivo | `raw.mp4` | `clipe_corte_77q_480x848.mp4` (copie para `ComfyUI\input`) |
| `LoadImage` (referência) | arquivo | `refer.jpeg` | `avatar_corpo_inteiro.png` (copie para `ComfyUI\input`) |
| `WanVideoLoraSelectMulti` | LoRAs | relight 1,0 e lightx2v 1,2 | manter (arquivos baixados na Etapa 8) |
| `VHS_VideoCombine` (o último, "Wanimate") | `frame_rate` | 16 | **25** |

- **Sobre o fps:** o exemplo do Kijai carrega o vídeo a 16 fps. Tente primeiro com os 25 fps do clipe (assim a saída tem o mesmo número de quadros e o áudio bate). Se o movimento ficar estranho, carregue com `force_rate` 16 e use `compor_final.py --reamostrar` (seção 3). Efeito de 25 fps na qualidade do Animate: sem dado.
- **Tempo:** sem dado do autor para o Animate. Única referência publicada é de um concorrente (Viggle): 160 s para 124 quadros 480x832 numa B200, que não serve de estimativa para 6 GB. Meça e anote.
- Anote: tempo, pico de VRAM, pico de RAM, se deu `out of memory`, e o número de quadros que saiu.

### Etapa 9. Animate 14B GGUF Q4_K_S (mais qualidade, mais peso)
- **Disco:** +10,6 GB (troque o arquivo do modelo; o resto é o mesmo da Etapa 8).
```
cd C:\troca\ComfyUI_windows_portable\ComfyUI\models
curl.exe -L -C - -o diffusion_models\Wan2.2-Animate-14B-Q4_K_S.gguf https://huggingface.co/QuantStack/Wan2.2-Animate-14B-GGUF/resolve/main/Wan2.2-Animate-14B-Q4_K_S.gguf
```
- Mesmo fluxo da Etapa 8, só trocando o modelo. Só vale tentar se a Etapa 8 terminou sem estourar memória.

### Etapa 10. Animate 14B fp8 com troca de blocos (o caminho que o autor do nó recomenda)
- **Disco:** 18,4 GB (o arquivo `..._scaled_KJ`, o que está no exemplo; para o ComfyUI nativo o autor fez um `v2` de 17,3 GB, que não é o que o nó do Kijai usa).
```
cd C:\troca\ComfyUI_windows_portable\ComfyUI\models
curl.exe -L -C - -o diffusion_models\Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled/resolve/main/Wan22Animate/Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors
```
- Mesmo fluxo da Etapa 8. O arquivo inteiro (18,4 GB) vai para a RAM: junto com o Windows e o resto, **32 GB ficam justos**. Se a RAM encher (o `medir_gpu.py` avisa), o Windows começa a usar o disco e tudo fica muito lento; veja "Se faltar RAM" na seção 4.
- O autor do nó diz que o fp8 "escalado" é a recomendação pessoal dele. Placas anteriores à série 40 não fazem a conta em fp8 de forma nativa (os modos `_fast` pedem capacidade de computação 8.9 ou mais, diz o nó); o modo normal carrega em fp8 e calcula em 16 bits (entendimento meu do código; não testado).

### Etapa 11. Tamanho original 720x1280 (opcional)
- Só se a Etapa 8, 9 ou 10 deu certo em 480x848 com folga de VRAM. Use `clipe_corte_77q_720x1280.mp4`, largura 720 e altura 1280. Relato de usuário: numa RTX 4090 (24 GB), 1280x720 falhou com fp8 e com GGUF Q4, enquanto 832x480 com 81 quadros funcionou. Não espere isto em 6 GB; é só para ter o número.

### Etapa 12. Plano C: alugar GPU por hora (se nada acima coube)
- Preços publicados pela RunPod, por hora, sob demanda (página "Updated October 8, 2026", lida em 2026-10-16 no relatório anterior; **não revi nesta sessão**): RTX 4090 US$ 0,34 (comunidade) ou US$ 0,89 (seguro); RTX 5090 US$ 0,69 ou US$ 1,19; L40S US$ 0,79 ou US$ 1,09; A100 80 GB PCIe US$ 1,19 ou US$ 1,79.
- Tempo por vídeo no Animate: sem dado do autor. Ordem de grandeza só com o número do concorrente: dezenas de minutos de uma B200 para 11 a 30 s (relatório anterior); para as outras GPUs: sem dado. Cada rodada de teste soma ao custo.

## 3. Como medir, compor e conferir cada geração (use nas Etapas 5 a 11)

**Janela 1 (medidor).** Deixe rodando enquanto o ComfyUI trabalha. Troque o nome da etapa a cada vez:
```
cd C:\troca
& $py "$kit\medir_gpu.py" --manual --etapa E8_animate_gguf_q3ks_480p --modelo "Animate 14B GGUF Q3_K_S" --resolucao 480x848 --quadros 77
```
**Janela 2 (ComfyUI).** Rode o fluxo (Queue). Quando o vídeo aparecer, volte à Janela 1 e **aperte ENTER**. O tempo "oficial" é a linha
`Prompt executed in X seconds` do console do ComfyUI; use o medidor principalmente para os **picos de VRAM e de RAM**. Ele grava uma linha
em `medidas_gpu.csv` (separador `;` e vírgula decimal, abre direto no Excel em português) e imprime uma linha pronta para a tabela da seção 5.
Se der erro de memória, **anote assim mesmo**: o pico até o erro é informação valiosa.

**Depois da geração.** Copie o vídeo que o ComfyUI salvou (`ComfyUI\output`) para `C:\troca\saidas\NOME.mp4`.

1. **Compor** (cola o gerado só dentro da máscara, mantém o resto e o áudio ORIGINAL sem recodificar; o modelo redesenha o quadro inteiro, então sem isto a conferência de "fora da máscara" não faz sentido):
```
& $py "$kit\compor_final.py" --original C:\troca\entradas\clipe_corte_77q_480x848.mp4 --gerado C:\troca\saidas\NOME.mp4 --mascara C:\troca\mascaras --saida C:\troca\saidas\final_NOME.mp4
```
   Se o número de quadros do gerado for diferente do original (por exemplo 16 fps), acrescente `--reamostrar`.
2. **Conferir:**
```
& $py "$kit\conferir_troca.py" --original C:\troca\entradas\clipe_corte_77q_480x848.mp4 --trocado C:\troca\saidas\final_NOME.mp4 --mascara C:\troca\mascaras --avatar C:\troca\entradas\avatar_corpo_inteiro.png --saida C:\troca\saidas\relatorio_NOME.json
```
   Use sempre o **original na mesma resolução** do gerado (por isso a versão reduzida da Etapa 2): comparar um vídeo reduzido com o original 720x1280 derruba o PSNR só por causa da reamostragem (testei: 37,9 dB, "FALHOU", sem nada ter mudado).
   Na primeira vez ele baixa os pesos do DINOv2-small (88 MB) do Hugging Face. Para CLIP também, acrescente `--modelo ambos` (mais 605 MB).
3. **Reprodutibilidade (2ª rodada).** Rode **o mesmo fluxo de novo**, com a mesma semente e as mesmas configurações, copie a saída para `NOME_rodada2.mp4` e compare as duas saídas **cruas** (antes do `compor_final`):
```
& $py "$kit\receita_test_hash.py" --comparar C:\troca\saidas\NOME.mp4 C:\troca\saidas\NOME_rodada2.mp4
```
   Respostas possíveis: `IDENTICA (bytes)`, `IDENTICA NO CONTEUDO` (quadros iguais, só o arquivo difere) ou `DIFERENTE` (com o PSNR entre as duas). Ele imprime o "sim/não" da última coluna da tabela. Ninguém garante saída idêntica entre execuções de modelos de difusão; isto mede só o que acontece na sua máquina.

**Como ler o resultado do `conferir_troca.py`** (limiares calibrados só com casos sintéticos daqui; ajuste depois da sua primeira saída real, com `--min-psnr`, `--min-ssim`, `--limiar-dino`, `--margem-melhora`):

| Linha | Quer dizer | Esperado numa troca boa |
|---|---|---|
| Quadros, fps, duração | o número de quadros bate com o original | iguais |
| FORA da máscara | as outras pessoas e o fundo não mudaram (PSNR por quadro, SSIM, diferença média) | PSNR mínimo de 40 dB ou mais; 100 dB = idêntico. Depois do `compor_final.py`, o ruído do x264 deixa cerca de 41 a 43 dB, não zero. |
| DENTRO da máscara | o alvo mudou de verdade | 30% ou mais dos pixels mudaram |
| Avatar | semelhança visual (DINOv2, e CLIP se pedir) do recorte do alvo com a imagem do avatar, e a **melhora sobre o ator original** | melhora de 0,05 ou mais; é semelhança global (roupa, cores, silhueta), **não identidade de rosto** |
| Áudio | o PCM do resultado é igual ao do original (hash); se foi recodificado, correlação de 0,999 ou mais | `IGUAL` quando você usa o `compor_final.py` |

## 4. Se faltar memória

**Se faltar VRAM** (erro `out of memory` ou `CUDA out of memory`), desça um degrau de cada vez e anote o que funcionou:
1. Feche navegadores e programas (ganha de 1 a 5 GB de VRAM se o navegador usar GPU).
2. `blocks_to_swap` = 40, `offload_img_emb` e `offload_txt_emb` ligados, `use_non_blocking` falso, `prefetch_blocks` = 0.
3. Ligue o tiling do VAE (`tiled_vae` no `WanVideoAnimateEmbeds` e `enable_vae_tiling` no `WanVideoDecode`). Um relato mostra o pico de VRAM subindo de 11 a 12 GB na amostragem para mais de 15 GB na passagem entre janelas de quadros (placa de 16 GB): o VAE entre janelas é um pico à parte.
4. Texto no `cpu` (`WanVideoTextEncodeCached`, campo `device`).
5. Menos quadros (77, depois 49, depois 33: sempre 4n+1): `python "$kit\preparar_entradas.py" ... --quadros 49 --saida C:\troca\entradas49`.
6. Menos pixels: `--largura 384 --altura 672` (múltiplos de 16) no `preparar_entradas.py`.
7. Quantização menor: Q4_K_S, Q3_K_S, e por fim Q2_K (6,46 GB; baixa bastante a qualidade).
8. No `run_nvidia_gpu.bat`, acrescente depois de `--windows-standalone-build` uma destas opções do ComfyUI (existem no código dele): `--disable-smart-memory` (descarrega os modelos para a RAM com mais agressividade) ou `--cache-none` (menos RAM e VRAM, mas refaz tudo a cada rodada). O ComfyUI tem um modo "DynamicVRAM" ligado por padrão no código; se ele está ativo na sua máquina, não sei (UNVERIFIED).
9. Plano B (VACE 1.3B, Etapa 7) e, por fim, Plano C (Etapa 12).

**Se faltar RAM** (o `medir_gpu.py` avisa quando passa de 92% de uso; o computador fica lento e o disco trabalha o tempo todo):
1. Use o texto UMT5 em fp8 (6,7 GB) e não o bf16 (11,4 GB); mantenha o texto no `cpu` e `use_non_blocking` falso.
2. Feche tudo que não precisa. Reinicie o ComfyUI entre rodadas: relatos mostram os modelos ficando na RAM até fechar o programa.
3. Deixe o Windows gerenciar o arquivo de paginação (memória virtual) e tenha pelo menos 40 GB livres em `C:` (a ajuda do Cordux, que roda numa placa de 6 GB, recomenda ativar a paginação). Isso evita travar, mas deixa mais lento.
4. Use o GGUF (Etapa 8 ou 9) em vez do fp8 (Etapa 10): 8 a 10,6 GB na RAM contra 18,4 GB.

## 5. Tabela para colar de volta no chat

Preencha com os números do `medir_gpu.py` (ele imprime a linha pronta). A mesma tabela está em `planilha_medidas.csv`, nesta pasta (abre no Excel).
Cole também o conteúdo de `medidas_gpu.csv` e os `relatorio_*.json`, e um texto com os erros, se houve.

| etapa | modelo | resolução | quadros | tempo | pico de VRAM | pico de RAM | deu certo (sim/não) | saída idêntica na 2ª rodada (sim/não) |
|---|---|---|---|---|---|---|---|---|
| E3 ComfyUI usa a NVIDIA | (sem modelo) | | | | | | | |
| E5 máscara SAM 2.1 small | SAM 2.1 small | 480x848 | 77 | | | | | |
| E6 pose e rosto | ViTPose-L + YOLOv10m | 480x848 | 77 | | | | | |
| E7 VACE 1.3B (plano B) | Wan2.1 VACE 1.3B | 480x848 | 77 | | | | | |
| E8 Animate GGUF Q3_K_S | Wan2.2-Animate-14B Q3_K_S | 480x848 | 77 | | | | | |
| E9 Animate GGUF Q4_K_S | Wan2.2-Animate-14B Q4_K_S | 480x848 | 77 | | | | | |
| E10 Animate fp8 + troca de blocos | Wan2.2-Animate-14B fp8 KJ | 480x848 | 77 | | | | | |
| E11 melhor modelo em 720p (opcional) | (o melhor) | 720x1280 | 77 | | | | | |

Mande também, da Etapa 3, as linhas `Total VRAM`, `pytorch version` e `Device:` do console do ComfyUI.

## 6. O que a pesquisa achou, em detalhe

Separei três tipos de informação: **autor** (o que o próprio projeto publica), **relato de usuário** (comentários em issues e fóruns; sem verificação independente) e **sem dado** (não achei). Li páginas de github.com, huggingface.co e docs.comfy.org em 2026-10-16.

### 6.1 Wan2.2-Animate-14B em placa pequena
**Autor**
- Repositório Wan2.2: os comandos do Animate não citam `--offload_model`, `--convert_model_dtype` nem `--t5_cpu` (essas opções só aparecem na seção de texto-para-vídeo); a tabela de eficiência é uma imagem sem texto. VRAM mínima do Animate: sem dado.
- Cartão da QuantStack (GGUF): sem requisito de VRAM ou RAM; diz que "todos os termos de licença originais continuam valendo".
- Autor do nó (Kijai), issue #1272, 22/09/2025: "no máximo consegui rodar 720x720x81 com 6 GB de VRAM usados, com troca de blocos completa e usando torch.compile" (citação livre minha do inglês). O comentário não diz qual fluxo era; no mesmo issue, em 24/09/2025, o fluxo I2V 2.2 de exemplo com troca de blocos completa deu `max_reserved` de 7,594 GB (a resolução 720x720, os 81 quadros e os 3 passos vêm do resumo que li da página; não consegui citar o trecho literal). Ele explica: só um bloco do modelo fica na VRAM por vez e "o resto, cerca de 6 GB, é o que a própria amostragem precisa". Minha conta, **sem medição**: em 480x848 com 77 quadros há cerca de 0,73 do volume de 720x720x81, o que daria na casa de 4,4 GB só de amostragem se a relação fosse linear (não é: a atenção cresce mais que isso); soma-se o que o Windows e o driver reservam.
- README do nó: 512x512x81 usa cerca de 16 GB com 20 de 40 blocos trocados (medida antiga, não é do Animate); a janela de contexto no T2V-1.3B usou menos de 5 GB.
- README do ComfyUI: "modelos enormes com 4 GB de VRAM + 8 GB de RAM" por transmissão assíncrona de pesos. É afirmação, sem número de teste.
- Template Animate do ComfyUI: sem VRAM; "use um tamanho pequeno se a VRAM for limitada"; largura e altura múltiplas de 16; cada bloco de extensão acrescenta 77 quadros (cerca de 4,8 s).

**Relato de usuário (nenhum é em placa de 6 GB)**
- RTX 4090: 832x480 com 81 quadros funciona; 1280x720 falhou com fp8 e com GGUF Q4 (issue #1272).
- RTX 4080 SUPER 16 GB: amostragem de uma janela usa 11 a 12 GB, mas na passagem para a janela seguinte o pico passa de 15 GB e às vezes dá erro; só chega a 720x1120 (issue #1722, aberto).
- 16 GB de VRAM e 32 GB de RAM: erro de memória com 45 quadros e 30 blocos trocados; com os nós nativos, sem troca de blocos, o mesmo usuário relata 9,9 GB para 77 quadros; em outro teste o arquivo `v2` usou 15,5 GB (30 blocos, 77 quadros, 480p) e o GGUF Q4_K_M 17,8 GB (issue #1272; o relato não diz se é VRAM ou RAM).
- 16 GB de VRAM, 40 blocos trocados, vídeo de 513 quadros: RAM chegou a 92 GB depois dos embeddings do Animate e encheu 128 GB na amostragem (issue #1272).
- RTX 3090 (24 GB): erro de memória nos passos de SAM 2, pose e máscara de rosto em vídeos de 2 a 3 minutos (issue #1272).
- RTX 5060 Ti 16 GB, 64 GB de RAM: Q8 GGUF funciona; vídeos de 5 s a 1024x574 levam cerca de 7 minutos com SageAttention (discussão no Hugging Face; não confirma que era o Animate).
- Única experiência numa placa de 6 GB que achei: o fluxo "Cordux" para RTX 3050 6 GB, que **não é o Animate** (é um modelo 14B "rapid all-in-one" de texto-para-vídeo em GGUF Q4_K): 512x512, 16 quadros, cerca de 4,6 minutos e cerca de 9 GB descarregados para a RAM, segundo o autor do fluxo.

**Sem dado:** Animate-14B em 6 GB (nenhum relato encontrado); tempo por vídeo em 6 GB; RAM mínima; qualidade do Q3_K_S no Animate; efeito de rodar a 25 fps em vez de 16.

### 6.2 VACE 1.3B (Wan2.1-VACE-1.3B) em 480p
- **Autor:** cartão do Hugging Face: 480P, cerca de 81x480x832; 720P não suportado; licença Apache-2.0. O único número de VRAM é do T2V-1.3B: 8,19 GB. O README do Wan2.1 (relatório anterior) fala de cerca de 4 minutos para 5 s em 480p numa RTX 4090 sem otimização (também T2V).
- **Documentação do ComfyUI:** a página chama o 1.3B de "lighter, ~7GB" sem dizer se é arquivo ou VRAM (o arquivo fp16 que ela cita tem 4,31 GB); para a primeira rodada, 640x640; texto em fp8 usa menos VRAM. Os tempos que a página dá (4090: 640x640 com 49 quadros em cerca de 7 min; 720x1280 com 81 quadros em cerca de 40 min) são do 14B.
- **Usuário em 6 GB:** nenhum relato do VACE. O Wan2GP diz rodar "modelos selecionados com apenas 6 GB" e lista o VACE entre os recursos, mas não cita o 1.3B.
- **Qualidade:** o único comparativo que li (tabela do artigo do MoCha, feito por um concorrente, não independente) dá ao VACE a pior consistência de sujeito do grupo.

### 6.3 SAM 2.1 e SAM 3 para a máscara
- **SAM 2.1** (Apache-2.0): tiny 38,9 milhões de parâmetros a large 224,4 milhões. Autor, numa A100: tiny 91,2 quadros por segundo, small 84,8, base_plus 64,1, large 39,5. Em 6 GB: sem dado. O nó do Kijai (`DownloadAndLoadSAM2Model`) oferece os modelos `sam2.1_hiera_tiny/small/base_plus/large`, modos `single_image`, `video` e `automaskgenerator`, e dispositivos `cuda`, `cpu` (só fp32) e `mps`. O `Sam2Segmentation` aceita `coordinates_positive`, `coordinates_negative`, `bboxes` e `mask`. O README do nó diz "apenas para teste".
- **SAM 3 / 3.1:** 848 milhões de parâmetros; pede Python 3.12 ou mais, PyTorch 2.7 ou mais e CUDA 12.6 ou mais; pesos originais com acesso restrito (aceite de termos) no Hugging Face (`facebook/sam3`, 3,44 GB); o ComfyUI tem suporte nativo ao 3.1 (arquivo `sam3.1_multiplex_fp16.safetensors`, 1,75 GB, no repositório `Comfy-Org/sam3.1`, licença SAM). VRAM e velocidade: sem dado.
- **Como a máscara entra no replace do Animate** (lido nos fluxos de exemplo do Kijai): `Sam2Segmentation` (cliques ou caixa) → `GrowMask`/`GrowMaskWithBlur` (10 px) → `BlockifyMask` (blocos de 32) = entrada `mask` do `WanVideoAnimateEmbeds`. Já `bg_images` = os quadros do vídeo com a máscara pintada de preto (`DrawMaskOnImage`).

### 6.4 O fluxo de replace (src_pose, src_face, src_bg, src_mask)
| Arquivo do pré-processamento oficial (Wan2.2) | Nó equivalente no ComfyUI (Kijai) |
|---|---|
| `src_pose.mp4` (pose do ator) | `DrawViTPose` sobre os dados do `PoseAndFaceDetection` (ViTPose-H ou L + YOLOv10m) |
| `src_face.mp4` (rosto do ator) | `face_images` do `PoseAndFaceDetection` |
| `src_bg.mp4` (fundo) | `bg_images` = quadros com o alvo pintado (`DrawMaskOnImage`) |
| `src_mask.mp4` (máscara do alvo) | `mask` = `BlockifyMask(GrowMask(Sam2Segmentation))` |
| `src_ref.png` (avatar) | `ref_images` + `clip_embeds` (CLIP-vision do avatar) |

- O pré-processamento oficial (`preprocess_data.py`) no modo troca usa `--replace_flag --iterations 3 --k 7 --w_len 1 --h_len 1` e a geração usa `--replace_flag --use_relighting_lora`. O guia oficial diz que a máscara dele é "para vídeos de **uma pessoa apenas**" e que, com várias, é preciso uma solução própria. O seu clipe tem várias pessoas, por isso a máscara tem de vir de cliques no SAM.
- Desconectar `bg_images` e `mask` desliga a troca e deixa só o modo "animar a imagem" (resposta do autor no issue #1262).
- Dois pontos do Animate que o relatório anterior já listava: a janela de 77 quadros (clipes longos viram vários blocos) e o aviso do guia oficial de que proporções muito diferentes entre avatar e ator geram artefatos.

### 6.5 Instalação no Windows
- ComfyUI portátil NVIDIA: Python 3.13 e PyTorch com CUDA 13.0 (README de hoje); PyTorch 2.7 é o mínimo aceito e o README diz que CUDA 13 ou mais novo é **obrigatório em placas NVIDIA da série 20 para cima**; para série 10 ou mais antiga existe a versão `cu126` (Python 3.12). Python 3.12 é a alternativa se algum nó der problema no 3.13. Driver: o README só diz para atualizar; a comunidade cita 580 ou mais novo para o CUDA 13 (não oficial). Windows 10 ou mais novo (página de requisitos, para o aplicativo desktop).
- Python e PyTorch exigidos pelo `ComfyUI-WanVideoWrapper`: não estão no README dele. Se o `pip` quebrar no Python 3.13 por falta de pacote pronto para alguma biblioteca, a alternativa é uma instalação manual do ComfyUI com Python 3.12 (README do ComfyUI, "Manual Install"); não testei.
- Espaço: ver seção 8.

## 7. Arquivos, tamanhos e licenças

Tamanhos lidos na API pública do Hugging Face em 2026-10-16 (GB decimais; o Windows mostra um número ligeiramente menor, porque usa 1 GB = 1,07 GB decimais). "Etiqueta" = o que o cartão do repositório declara; "sem etiqueta" = o repositório não declara licença (não significa que não exista).

| Arquivo | Tamanho | Pasta em `ComfyUI\models` | Licença | Etapa |
|---|---|---|---|---|
| `Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors` (Kijai/WanVideo_comfy_fp8_scaled, pasta Wan22Animate) | 18,4 GB | diffusion_models | Apache-2.0 (etiqueta do repositório; pesos derivados do Wan2.2-Animate-14B, Apache-2.0, com cláusula de uso aceitável no cartão) | 10 |
| `Wan2_2-Animate-14B_fp8_scaled_e4m3fn_KJ_v2.safetensors` (mesmo repositório; para ComfyUI nativo) | 17,3 GB | diffusion_models | Apache-2.0 (etiqueta) | opcional |
| `Wan2_2-Animate-14B_fp8_e5m2_scaled_KJ.safetensors` (mesmo repositório) | 18,4 GB | diffusion_models | Apache-2.0 (etiqueta) | opcional: o nó diz que o e4m3fn não compila com `torch.compile` em placas anteriores à série 40; este é o e5m2 |
| `Wan2.2-Animate-14B-Q2_K.gguf` (QuantStack) | 6,46 GB | diffusion_models (ou unet) | Apache-2.0 (etiqueta) | 8 (se faltar memória) |
| `Wan2.2-Animate-14B-Q3_K_S.gguf` | 7,97 GB | idem | Apache-2.0 (etiqueta) | 8 |
| `Wan2.2-Animate-14B-Q4_K_S.gguf` | 10,6 GB | idem | Apache-2.0 (etiqueta) | 9 |
| outros GGUF do mesmo repositório | Q3_K_M 8,63; Q4_0 10,4; Q4_K_M 11,5; Q5_K_S 12,3; Q5_0 12,5; Q5_K_M 13,0; Q6_K 14,6; Q8_0 18,7 GB | idem | Apache-2.0 (etiqueta) | opcional |
| `wan2.2_animate_14B_bf16.safetensors` (Comfy-Org, nativo) | 34,6 GB | diffusion_models | Apache-2.0 (etiqueta) | **não use**, não cabe |
| `umt5-xxl-enc-fp8_e4m3fn.safetensors` (Kijai/WanVideo_comfy) | 6,73 GB | text_encoders | sem etiqueta no repositório (UNVERIFIED para o arquivo); origem google/umt5-xxl, Apache-2.0 (etiqueta) | 7 |
| `umt5-xxl-enc-bf16.safetensors` (idem) | 11,36 GB | text_encoders | idem | opcional, mais RAM |
| `Wan2_1_VAE_bf16.safetensors` | 0,254 GB | vae | sem etiqueta no repositório; origem Wan-AI, Apache-2.0 (cartão do VACE-1.3B) | 7 |
| `clip_vision_h.safetensors` (Comfy-Org) | 1,264 GB | clip_vision | Apache-2.0 (etiqueta do repositório; origem OpenCLIP: não verifiquei) | 8 |
| `lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors` (Kijai) | 0,738 GB | loras | sem etiqueta na cópia; origem lightx2v, Apache-2.0 (etiqueta do projeto de origem) | 8 |
| `WanAnimate_relight_lora_fp16.safetensors` (Kijai) | 1,437 GB (há uma versão reduzida de 0,273 GB) | loras | sem etiqueta na cópia; origem `relighting_lora.ckpt` do repositório Wan-AI/Wan2.2-Animate-14B, Apache-2.0 | 8 |
| `wan2.1_t2v_1.3B_fp16.safetensors` (Comfy-Org) | 2,838 GB | diffusion_models | Apache-2.0 (etiqueta) | 7 |
| `Wan2_1-VACE_module_1_3B_bf16.safetensors` (Kijai) | 1,470 GB | diffusion_models (UNVERIFIED a pasta) | sem etiqueta; base Wan2.1-VACE-1.3B, Apache-2.0 | 7 |
| `yolov10m.onnx` (dentro do repositório Wan-AI/Wan2.2-Animate-14B) | 0,062 GB | detection | repositório marcado Apache-2.0, **mas o YOLOv10 original (THU-MIG/yolov10) é AGPL-3.0** (LICENSE lido hoje). Qual licença vale para este `.onnx`: UNVERIFIED; para uso comercial, consulte um jurista | 6 |
| `vitpose-l-wholebody.onnx` (JunkyByte/easy_ViTPose) | 1,235 GB | detection | sem etiqueta no Hugging Face; o ViTPose original é Apache-2.0 (relatório anterior); UNVERIFIED para este arquivo | 6 |
| `vitpose_h_wholebody_model.onnx` + `..._data.bin` (Kijai/vitpose_comfy; opcional) | 2,549 GB (o `.bin`) mais o `.onnx` pequeno | detection | Apache-2.0 (etiqueta) | opcional |
| `sam2.1_hiera_small.safetensors` (Kijai/sam2-safetensors) | 0,184 GB (tiny 0,156; base_plus 0,323; large 0,898) | sam2 | Apache-2.0 (etiqueta) | 5 |
| `sam3.1_multiplex_fp16.safetensors` (Comfy-Org/sam3.1; opcional) | 1,746 GB | checkpoints | licença SAM da Meta (etiqueta `sam-license`); veda uso militar e controles de exportação e tem cláusula de rescisão por processo (texto lido no relatório anterior) | 5 (opcional) |
| `facebook/dinov2-small` (usado só pelo `conferir_troca.py`) | 0,088 GB | cache do Hugging Face | Apache-2.0 (etiqueta) | conferência |
| `laion/CLIP-ViT-B-32-laion2B-s34B-b79K` (só com `--modelo clip` ou `ambos`) | 0,605 GB | cache do Hugging Face | MIT (etiqueta) | conferência |
| ComfyUI portátil NVIDIA | 2,01 GB (compactado) | | ComfyUI: GPL-3.0 | 3 |

Os nós: `ComfyUI-WanVideoWrapper` e `ComfyUI-WanAnimatePreprocess` (Apache-2.0), `ComfyUI-segment-anything-2` (Apache-2.0), `ComfyUI-KJNodes` e `ComfyUI-VideoHelperSuite` (GPL-3.0), segundo o relatório anterior. A GPL e a AGPL pesam sobre quem distribui; quem só roda não é afetado. A licença dos pesos vale para o uso comercial dos resultados: se for publicar, leia os cartões. O cartão do Wan2.2 tem cláusula de uso aceitável.

## 8. Espaço em disco

Você tem cerca de 135 GB livres. Valores em GB decimais, somando só os arquivos das etapas (ver a tabela da seção 7):

| Etapa | Baixa | Observação |
|---|---|---|
| 0, 1, 2 | cerca de 0,3 | Python, ffmpeg, Git; cortes de vídeo de poucos MB |
| 3 ComfyUI portátil | 2,01 | descompactado: **não medi**; reservei 10 |
| 4 nós e bibliotecas | pequeno + pip | **não medi** o pip; reservei 3 |
| 5 SAM 2.1 small | 0,18 | |
| 6 pose e rosto | 1,30 | |
| 7 VACE 1.3B | 11,29 | inclui o texto fp8 e o VAE (usados também nas etapas seguintes) |
| 8 Animate GGUF Q3_K_S | 11,41 | inclui CLIP-vision e as duas LoRAs |
| 9 Animate GGUF Q4_K_S | 10,60 | |
| 10 Animate fp8 | 18,40 | |
| **Soma dos downloads** | **55,2** | |
| Reservas (ComfyUI descompactado, pip, saídas e quadros) | 18 | estimativa minha, não medida |
| **Total** | **cerca de 73** | cerca de 68 "GB do Windows" |

Cabe nos 135 GB com folga de cerca de 60 GB. Além disso o Windows pode ocupar espaço com o arquivo de paginação (por isso a recomendação de manter 40 GB livres em `C:`). Se faltar espaço, apague os arquivos de uma etapa depois de anotar os números dela. Se usar o texto bf16 (11,4 GB) no lugar do fp8, some 4,6 GB; o SAM 3.1 opcional soma 1,75 GB.

## 9. O que foi testado aqui e o que não foi

**Testado** (Linux, 4 vCPU Intel Xeon 2,1 GHz, 15,7 GB de RAM, sem GPU; Python 3.13.16 num ambiente virtual novo; PyTorch 2.14.1 para CPU, transformers 5.20.1, OpenCV 5.0.0.93, NumPy 2.5.4, ffmpeg 6.1.1). Detalhes e números em [`RESULTADOS.md`](RESULTADOS.md) (os logs brutos e os relatórios JSON desses testes não foram incluídos no repositório):
- `preparar_entradas.py`: no seu clipe real; 75 e 77 quadros conferidos, hashes iguais em duas execuções, áudio do corte e da versão reduzida com o mesmo PCM, avatar recortado (215x502 px).
- `medir_gpu.py`: comando falso sem GPU, comando que falha, programa inexistente, modo manual, tempo máximo; leitura do `nvidia-smi` testada com um `nvidia-smi` falso (inclusive nome de placa com vírgula e valor `[N/A]`).
- `conferir_troca.py`: o clipe contra ele mesmo (diferença zero, PSNR 100 dB, SSIM 1,0000, áudio igual) e 19 casos sintéticos, todos com o resultado esperado (recolorido, fundo alterado, áudio trocado, falta de um quadro, resolução diferente, máscara errada etc.). Máscara aceita como pasta de PNGs, vídeo e imagem única.
- `compor_final.py`: saída "crua" sintética recomposta sobre o original (fora da máscara voltou a ficar com 41,8 a 42,5 dB), saída a 480x848 e 16 fps reamostrada.
- `receita_test_hash.py`: 9 cenários (saída igual, aleatória, vídeo igual só no conteúdo, ruído, saída não criada, comando que falha, modo comparar, pasta).
- Tempo medido aqui, só para referência: conferir 75 quadros 720x1280 em cerca de 11 s (cerca de 20 s com DINOv2), os 274 quadros em cerca de 38 s; compor 75 quadros em cerca de 12 s.

**Não testado:** Windows (nem `ctypes` da RAM, nem o PowerShell); GPU NVIDIA de verdade; ComfyUI e todos os nós; qualquer modelo de IA de troca de personagem (Wan, VACE, SAM); saídas reais de modelo (os casos sintéticos são imitações: um avatar colado, borrão e ruído); os limiares de identidade e de PSNR com saídas reais.
**Cuidados que o teste revelou** (já corrigidos no kit, mas vale saber): a conversão RGB para YUV do ffmpeg, sem `accurate_rnd`, deixa um erro de até 5 níveis que apareceria como "o fundo mudou"; sem etiqueta de cor o vídeo regravado sai com as cores levemente deslocadas; por isso o `compor_final.py` copia a etiqueta e a matriz de cor do original.
**Limites do avatar:** o painel de corpo inteiro da sua folha é pequeno (215x502 px, rosto de poucos pixels). Em todas as comparações de identidade o DINOv2/CLIP mede semelhança global, não rosto.

## 10. UNVERIFIED (não consegui ler ou confirmar)

- Nomes de pacote do `winget` (Gyan.FFmpeg, Git.Git) e o endereço `.../archive/refs/heads/main.zip` do GitHub (o proxy da minha sessão bloqueou).
- Tamanho do ComfyUI portátil descompactado e das bibliotecas do `pip`.
- Número mínimo oficial do driver NVIDIA para o CUDA 13.0 (só achei o número 580 em fontes da comunidade).
- Se o `WanVideoModelLoader` lista `.gguf` da pasta `diffusion_models`; em qual pasta o seletor do módulo VACE procura; como ligar a troca com máscara no exemplo do VACE 1.3B.
- Se o nó do Animate aceita 75 quadros (o nó anda de 4 em 4; por isso o kit usa 77).
- Compatibilidade do `onnxruntime-gpu` com o PyTorch CUDA 13 do portátil; Python e PyTorch exigidos pelo `ComfyUI-WanVideoWrapper`.
- Qual licença vale para `yolov10m.onnx` e `vitpose-l-wholebody.onnx`; licença dos arquivos copiados pelo Kijai (sem etiqueta); origem do `clip_vision_h` (OpenCLIP).
- Se o modo DynamicVRAM do ComfyUI está ativo na sua máquina; ajuste "Alto desempenho" do Windows para o `python.exe`.
- Os preços da RunPod (lidos no relatório anterior, não revistos hoje).
- A parte da pesquisa do relatório anterior que eu só reaproveitei: licença SAM 3, MoCha, Viggle, HunyuanCustom.

## 11. Fontes lidas (2026-10-16)

- ComfyUI: README e `main.py`, `comfy/cli_args.py`, `comfy/model_management.py`, `.ci/windows_nvidia_base_files/run_nvidia_gpu.bat` (github.com/Comfy-Org/ComfyUI); docs.comfy.org: requisitos do sistema, template Wan2.2 Animate, VACE, SAM 3.1 e nó SAM3_VideoTrack.
- Kijai: ComfyUI-WanVideoWrapper (README, pasta `example_workflows`, `nodes.py`, `nodes_model_loading.py`, issues #898, #1262, #1267, #1272, #1722); ComfyUI-WanAnimatePreprocess (README, `nodes.py`, `requirements.txt`); ComfyUI-segment-anything-2 (README, `nodes.py`); Hugging Face Kijai/WanVideo_comfy, WanVideo_comfy_fp8_scaled (README da pasta Wan22Animate), vitpose_comfy, sam2-safetensors.
- Wan-Video/Wan2.2 (README, `UserGuider.md`, issue #283); Hugging Face Wan-AI/Wan2.2-Animate-14B (e a discussão nº 4), Wan-AI/Wan2.1-VACE-1.3B, QuantStack/Wan2.2-Animate-14B-GGUF, Comfy-Org/Wan_2.1_ComfyUI_repackaged, Comfy-Org/Wan_2.2_ComfyUI_Repackaged, Comfy-Org/sam3.1, facebook/sam2.1-hiera-tiny e small, facebook/sam3, JunkyByte/easy_ViTPose, facebook/dinov2-small, laion/CLIP-ViT-B-32-laion2B-s34B-b79K.
- github.com/Cordux/ComfyUI-Wan2.2-workflow, github.com/facebookresearch/sam3, github.com/deepbeepmeep/Wan2GP, github.com/city96/ComfyUI-GGUF, github.com/THU-MIG/yolov10 (LICENSE), github.com/openai/CLIP (LICENSE).
- Relatórios anteriores do mesmo trabalho (`github-troca\RELATORIO.md` e `posetest\RELATORIO.md`; foram feitos fora do repositório e não estão nele), de onde reaproveitei os preços da RunPod, licenças e os dados do clipe.

## 12. Para quem mantém o kit no repositório

Esta seção é para quem edita os scripts, não para quem roda o teste na máquina com GPU.

- **Lugar e escopo.** Scripts em `scripts/kit_gpu/` (o `ruff check .` do gate cobre a pasta, junto com o resto de `scripts/`), texto em `docs/how-to/troca-personagem-gpu/`. Nenhum script entra no pacote `simplicio_video`, e `numpy`, `opencv`, `torch`, `transformers` e Pillow **não** vão para o `pyproject.toml`.
- **Provar que os scripts abrem (`--help`).** `medir_gpu.py`, `preparar_entradas.py` e `receita_test_hash.py` abrem com o Python do projeto. `compor_final.py` e `conferir_troca.py` importam `numpy` e `opencv` logo no começo e, sem eles, saem com "ERRO: falta cv2" (código 2), até no `--help`. Para conferir esses dois, use um ambiente virtual descartável fora do checkout:

```
python3 -m venv /tmp/venv-kit
/tmp/venv-kit/bin/python -m pip install numpy opencv-python-headless
/tmp/venv-kit/bin/python -I scripts/kit_gpu/compor_final.py --help
/tmp/venv-kit/bin/python -I scripts/kit_gpu/conferir_troca.py --help
```

- **`checar_maquina.py` não tem opções.** Qualquer argumento, inclusive `--help`, é ignorado e a checagem roda (só leitura: imprime sistema, GPU, RAM, disco e ferramentas).
- **Idioma.** Os textos de ajuda, mensagens e comentários dos scripts estão em português sem acento (o texto é para quem não é programador e é lido no terminal do Windows; o `--help` é a documentação do script). Isto foge da regra de comentários em inglês do `AGENTS.md`; não foi traduzido para não mudar o comportamento de arquivos que só foram testados em CPU.
- **Testes.** Os scripts não têm testes automatizados no `pytest` do projeto: foram exercitados fora do `pytest`, com casos sintéticos, como descrito em [`RESULTADOS.md`](RESULTADOS.md) (os logs, os relatórios JSON e os scripts que fabricaram os casos sintéticos ficaram de fora).
