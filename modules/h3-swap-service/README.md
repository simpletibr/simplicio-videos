# h3-swap-service

Serviço de **troca de personagem em vídeo** sobre o MiniMax H3 + akatz-ai Character-Swap LoRA,
rodando em GPUs alugadas (Vast.ai primeiro, Salad depois) com o plano de controle na Cloudflare.
Preço-alvo ao cliente: **R$ 0,16 por segundo**, vídeos de 1 a 30 s, saída 768p-class.

> Status: **código gerado, NADA foi executado contra GPU, Vast, Cloudflare ou Docker.**
> Todo número de custo antes do benchmark é **estimativa**. Só `bench/` produz número medido.

## Dentro do simplicio-videos

Este repo vive como módulo em `modules/h3-swap-service/` do simplicio-videos. Regras do encaixe:

- **Não é importado pelo motor.** Nada em `src/simplicio_video/` importa daqui, e `modules/` fica fora do wheel e do sdist.
- **`api/` é um serviço à parte** (contas, créditos e cobrança por segundo, na Cloudflare). O AGENTS.md do simplicio-videos
  proíbe billing dentro do motor; por isso `api/` só roda como deploy próprio e nunca entra no pacote `simplicio_video`.
  Se o dono preferir manter o motor 100% sem billing, mova `api/` para o repositório de operação e deixe aqui só
  `docker/`, `worker/` e `bench/` (o contrato entre eles está em `CONTRACT.md`).
- **Ponte com o motor:** `docker/` + `worker/` executam o swap numa GPU alugada; o adaptador `swap_providers/` do motor
  pode chamar a API deste módulo como mais um fornecedor. Esse adaptador **não existe ainda** (UNVERIFIED).
- **Testes** (não entram no `make check` da raiz, que só roda `tests/`):
  `cd modules/h3-swap-service && python -m pytest docker/tests worker/tests bench/tests -q` e
  `cd api && npm install && npx tsc --noEmit && npx vitest run`.

## Arquitetura

```
cliente -> API Worker (CF) -> R2 (uploads) + Queue (h3-jobs) + D1
                                   ^ cron 1 min = autoscaler -> Vast REST (cria/destrói)
caixa GPU (Docker): worker -- puxa a Queue por HTTP --> ComfyUI :8188 -> R2 (outputs)
                          \-- status + heartbeat --> API Worker
```

| Pasta | O que é | Dono |
|---|---|---|
| `CONTRACT.md` | contrato único (chaves R2, mensagem da fila, callbacks, env) | lead |
| `docker/` | imagem (alvos `runtime` e `baked`), entrypoint, baixa modelos do R2 | squad A |
| `worker/` | worker Python da GPU: fila -> ComfyUI -> R2 -> callback | squad B |
| `api/` | Worker TypeScript: API, créditos, D1, autoscaler Vast | squad C |
| `bench/` | benchmark que mede GPU-s por segundo de vídeo e calcula margem em R$ | squad D |

## Ordem de execução (runbook)

1. **Licença primeiro.** Confirme que a licença do MiniMax H3 e do LoRA permite vender o serviço.
   Não verifiquei. Se não permitir, nada abaixo vale.
2. **Cloudflare** (`api/README_api.md`): criar D1, bucket R2, fila `h3-jobs` com
   *HTTP pull consumer*, aplicar `api/schema.sql`, `wrangler secret put ...`, `wrangler deploy`.
3. **Modelos no R2**: subir os ~36 GB para `models/...` (lista em `docker/models.manifest.json`;
   itens `TODO_VERIFY_*` precisam do nome real no HF `Comfy-Org/MiniMax-H3`).
4. **Imagem** (`docker/build.sh`): `runtime` (baixa do R2 no boot) ou `baked` (modelos na imagem;
   na Vast a fase *loading* não é cobrada). Salad: limite de 35 GB comprimido, use `runtime`.
5. **Workflow**: numa caixa Vast 5090 com a imagem, abra o ComfyUI, monte o fluxo de swap com o
   `comfyui-h3-continuum`, **Save (API Format)** -> `workflow_api.json` e escreva `workflow_map.json`
   (exemplo em `bench/workflow_map.example.json`).
6. **Benchmark** (`bench/README_bench.md`): rode 10 s e 30 s, 3 repetições. Isso troca a estimativa
   por número medido e imprime custo, lucro e margem em R$ (inclusive o cenário com GPU 3x pior).
7. **Só então** ligue o autoscaler com `MAX_WORKERS` pequeno (1 ou 2) e faça um job de ponta a ponta.

## Riscos abertos (nada disso foi provado)

| Risco | Efeito | Como fechar |
|---|---|---|
| Licença comercial MiniMax H3 / LoRA | pode inviabilizar a venda | ler a licença no HF |
| Tempo de GPU por segundo de vídeo | margem sai de ~54-77% (estimado) para prejuízo se for 3x pior | `bench/` numa 5090 real |
| LoRA de swap (Ref2VA) x Continuum (FL2VA) | fluxo pode não encadear chunks > 15 s | testar 30 s no benchmark |
| Encoder NVFP4 exige Blackwell | placa não-50xx não roda | o entrypoint avisa; filtrar ofertas |
| `workflow_api.json` não existe ainda | worker não roda sem ele | passo 5 acima |
| Vast: parar/religar pode perder a GPU | job preso | nunca stop/start, só destruir e recriar |
| Vast: `CONTAINER_ID`/`CONTAINER_API_KEY` não documentados | caixa não se autodestrói | o autoscaler destrói; a caixa só manda heartbeat |
| Nomes de campos extras do filtro de ofertas da Vast | filtro pode falhar | ficam em `VAST_OFFER_FILTER_JSON`, marcados VERIFY |
| Salad interrompe sem aviso, disco apagado | job perdido | fila com retry; v1 não tem checkpoint no meio do job |

## Preço e margem (ESTIMADO, ainda não medido)

Premissas: US$ 1 = R$ 5,07, 15% de impostos/taxas (chute), custo realista = 2x (retries + overhead).

| Job | Cliente paga | Custo Vast (est.) | Custo Salad (est.) |
|---|---|---|---|
| 10 s | R$ 1,60 | ~R$ 0,74 | ~R$ 0,48 |
| 30 s | R$ 4,80 | ~R$ 2,21 | ~R$ 1,44 |

Máquina 24 h ligada: Vast ~R$ 93/dia, Salad ~R$ 61/dia. Só compensa acima de ~42-83 jobs de 30 s por dia
por GPU; abaixo disso, por job (liga e destrói) sai mais barato.
Infra Cloudflare fixa: ~R$ 30-60/mês (o valor do plano pago vem de memória, não verifiquei).

## Testes

```bash
python -m pytest docker/tests worker/tests bench/tests -q
cd api && npm install && npx tsc --noEmit && npx vitest run
```

Integração real (ComfyUI, Cloudflare, Vast, Docker build) = **UNVERIFIED** até alguém rodar.
