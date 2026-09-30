# ADR-0001 — simplicio-videos é um plugin do Simplicio Runtime (esteira determinística por setor)

- **Status:** aceita
- **Data:** 2026-09-30
- **Decisor:** Wesley Simplicio (visão de produto passada em 30/09/2026)
- **Registrado por:** agente (Grok) na reestruturação do repositório

## Contexto

O repositório nasceu como kit para um vídeo de cliente (WJR, `clients/wjr-informatica-games/video-01`): composição HyperFrames escrita por IA, render determinístico a partir de `spec.json`, narração com cache. Para atender qualquer usuário do Simplicio, esse fluxo manual precisa virar produto: perguntas padronizadas, templates por setor, peças de animação reutilizáveis e um render que não depende de LLM.

## Decisão

**simplicio-videos é um plugin do Simplicio Runtime (Simplicio MCP).** Quando um usuário do Simplicio pede um vídeo, o plugin executa a esteira:

1. **Intake** — questionário. Se o usuário der site e/ou Instagram, extrai sozinho nicho, empresa, serviços, logo, cores e tom e pergunta **só o que falta** (objetivo, formato/aspecto, duração, voz sim/não + provider Gemini/ElevenLabs/outro + tipo de voz, referências, CTA). Sem site/Instagram, faz o questionário completo (logo, nicho, do que se trata, ofertas, contatos, referências). → `intake/`
2. **Brief/spec** — o intake aprovado vira brief e spec (fonte única da verdade). → `schemas/`, `clients/<c>/coleta/`
3. **Template do setor** — escolhido pelo nicho. → `templates/`
4. **Composição** com a biblioteca de padrões de motion (HyperFrames). → `motion/`
5. **Voz TTS** com escolha de provider e cache. → `voices/`
6. **video-use** para edição/montagem agêntica de footage (quando houver material filmado). → `docs/video-use-integracao.md`
7. **Render determinístico** (mesmo spec + mesmos assets = mesmo vídeo).

**LLM (Opus 5.5) só cria templates e padrões novos.** O caminho intake → spec → render roda sem LLM. Objetivo: uma esteira determinística com templates para todos os setores.

## Consequências

- Estrutura do repo organizada por etapa da esteira: `intake/`, `templates/`, `motion/`, `voices/`, `schemas/`, `docs/`, `clients/` (só trabalho de cliente).
- Todo padrão de motion vira bloco parametrizado com preview e fonte; todo template declara cenas, padrões, voz, música e cuidados do setor.
- Fatos do cliente continuam com proveniência (fonte + data); nada inventado entra no spec.
- A voz é passo de geração com cache (TTS não é bit a bit reprodutível; o WAV versionado é a entrada fixa do render).
- O plugin (`plugin.json`) passa a expor as operações da esteira (`intake`, `brief`, `template`, `compose`, `voice`, `edit`, `render`); o binário ainda não existe — até lá os passos rodam pelos scripts do repo e pelo agente anfitrião.
- Pendências conhecidas: gerador automático intake → spec (hoje o spec é escrito seguindo o template), templates `skeleton` sem vídeo de referência, padrões `proposto` sem bloco.

## Alternativas consideradas

- **LLM gerando cada vídeo do zero** (estilo "one-shot" do Opus 5.5): ótima qualidade pontual, mas custo e resultado variáveis por vídeo e sem garantia de fatos — rejeitado para o caminho padrão; fica restrito à autoria de padrões/templates.
- **Editor de vídeo tradicional/template fechado** (CapCut-like): determinístico, mas sem a expressividade de código (GSAP/HyperFrames) e sem integração agêntica.
