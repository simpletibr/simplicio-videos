# Host

Documentos do host: como o repositório é checado, instalado e mantido na máquina de quem usa e de quem pousa mudanças. Cada página tem front matter com `title`, `summary`, `commands`, `issue` e `last_verified`.

| Página | Para quê |
|---|---|
| [Gate local, TDD e pouso de PRs](gate.md) | Como provar que a main está verde com um comando offline, a regra de testes primeiro, o ownership por issue e o pouso serializado sem CI |
| [Pacote de operação (install, update, doctor, setup)](packaging.md) | O que cada subcomando faz, o que o doctor checa, por que a falta de GEMINI_API_KEY é aviso e os limites até as #32 e #34 |
| [Licenças das dependências](licenses.md) | Como o gate confere licenças, como adicionar uma exceção justificada, como regerar `docs/licenses.md` e o que ainda falta (`web/`) |
| [Kernel da fábrica (simplicio_factory)](kernel.md) | Os contratos do kernel, `transition()` como única forma de mudar o estado, JsonStore e MemoryStore, o testkit e `make factory-schema` |
| [Host de plugins (manifesto, registro e despacho)](plugin-host.md) | Como cada plugin declara comandos no `plugin.json`, como o registro descobre os plugins, `plugin list` e por que o `plugin.json` da raiz é outro arquivo |
| [Duas rotas de produção (determinística e ai_assisted)](duas-rotas.md) | As duas rotas do item lado a lado, o que é reproduzível byte a byte, onde mora cada decisão e os comandos reais de cada etapa |
