# How-to

Guias para uma tarefa específica. Cada página responde a uma pergunta do tipo "como faço X". Para aprender do zero, veja os [tutoriais](../tutorials/README.md). Para o que cada comando aceita, veja a [referência da CLI](../reference/cli.md).

| Guia | Para quê |
|---|---|
| [Instalar, atualizar e checar](install.md) | Instalar o simplicio-video no checkout, atualizar com `update` (checkout ou pip), conferir o ambiente com `doctor` e entrar com `login` |
| [Testar em Windows e macOS](testar-em-windows-e-macos.md) | Rodar `scripts/smoke_so.py` num Windows ou macOS de verdade, ler a tabela e registrar o resultado (esses sistemas são UNVERIFIED até lá) |
| [Receita de vídeo para cliente](../receita-video-cliente.md) | O passo a passo atual: o agente escreve o contrato e o CLI valida, gera a voz, renderiza e entrega |
| [Usar o LangFlow como cliente do motor](langflow.md) | Instalar o LangFlow à parte, apontar o executável do motor, importar o componente e o fluxo de exemplo, e rodar ponta a ponta |
| [Medir a troca de personagem numa GPU de 6 GB](troca-personagem-gpu/LEIA-ME.md) | Kit para medir, num notebook Windows com GPU NVIDIA de 6 GB, se a troca de personagem em vídeo cabe: passo a passo, [prompt para a sessão da GPU](troca-personagem-gpu/PROMPT-sessao-gpu.md), [resultados dos testes em CPU](troca-personagem-gpu/RESULTADOS.md) e seis scripts em [`scripts/kit_gpu/`](../../scripts/kit_gpu). Também funciona fora do repositório, copiando as duas pastas |
