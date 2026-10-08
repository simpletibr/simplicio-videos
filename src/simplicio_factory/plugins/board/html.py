"""Dashboard HTML estático do quadro (#88, épico #81): `board build` grava um arquivo autocontido.

Só leitura: lê o JsonStore, os comentários (`comments.jsonl`), o Draft e o `studio.json` do estúdio, a prévia e o MP4
em `studio/`, e o recibo `media/<id>/media.json` quando existir. Não escreve nada e não faz rede. O arquivo traz CSS e
JS inline e nenhuma URL externa.

Determinístico: a mesma entrada gera os mesmos bytes. Não há horário de geração. A última atividade de um item é o
seu último evento (`seq`), e os cartões de cada coluna vão do evento mais recente para o mais antigo (desempate por id).
Todo texto que vem do estado passa por `html.escape`. Os links para prévia e MP4 são relativos à pasta do arquivo.
"""

from __future__ import annotations

import html as _html
import json
import os
from collections import defaultdict
from importlib import resources
from pathlib import Path

from simplicio_factory.contracts.json_store import JsonStore
from simplicio_factory.plugins.board import model, service

LIMITE_POR_COLUNA = 50
TEMPLATE = "templates/board.html.tpl"
EVENTO_ESTADO = "item.state_changed"
TIPO_PASSO_IA = "ai_media"

ROTULO_ESTADO = {
    "idea": "ideia",
    "drafted": "roteiro",
    "quoted": "orçamento",
    "approved": "aprovado",
    "generating": "gerando",
    "generated": "gerado",
    "rendering": "renderizando",
    "rendered": "renderizado",
    "failed": "falhou",
}
ROTULO_ROTA = {"deterministic": "determinística", "ai_assisted": "generativa"}
ROTULO_REVISAO = {"approved": "aprovada", "changes_requested": "alterações solicitadas", "pending": "pendente"}


def _e(texto) -> str:
    return _html.escape(str(texto), quote=True)


def _json_se_existir(caminho: Path):
    if not caminho.is_file():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except ValueError:
        return None


_SEGURO = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/")


def _percent(texto: str) -> str:
    """Percent-encoding de URL (RFC 3986) sem importar urllib, que o #86 proíbe no plugin."""
    return "".join(c if c in _SEGURO else "".join(f"%{b:02X}" for b in c.encode("utf-8")) for c in texto)


def _href(alvo: Path, pasta_saida: Path) -> str:
    """Caminho relativo à pasta do HTML (o HTML fica movível junto com o estúdio)."""
    alvo = alvo.resolve()
    try:
        relativo = os.path.relpath(alvo, pasta_saida)
    except ValueError:  # outro drive (Windows): cai no URI do arquivo
        return alvo.as_uri()
    return _percent(relativo.replace(os.sep, "/"))


def _passo_ia(item) -> dict | None:
    passos = [
        p for p in (item.production or {}).get("steps") or [] if isinstance(p, dict) and p.get("kind") == TIPO_PASSO_IA
    ]
    return passos[-1] if passos else None


def _cartao_de(home: Path, item, eventos: list) -> dict:
    """Dados de um item para o quadro e o detalhe. Só lê; nenhum campo sai do relógio."""
    draft = _json_se_existir(home / "studio" / item.id / "draft.json") or {}
    estudio = _json_se_existir(home / "studio" / item.id / "studio.json") or {}
    mp4 = (estudio.get("stages") or {}).get("studio", {}).get("mp4")
    previa = home / "studio" / "renders" / f"{item.id}-previa.mp4"
    recibo = _json_se_existir(home / "media" / item.id / "media.json")
    passo = _passo_ia(item)
    custo = None
    if passo is not None and isinstance(passo.get("credits"), int):
        custo = {"creditos": passo["credits"], "provedor": passo.get("provider", "")}
    return {
        "id": item.id,
        "marca": item.brand,
        "estado": item.state,
        "rota": (item.production or {}).get("route", "deterministic"),
        "revisao": item.review,
        "falhou_de": item.failed_from,
        "coluna": model.coluna_de(item.state, item.review),
        "titulo": draft.get("idea") or f"{item.brand} · {item.id}",
        "ultimo_seq": max((e.seq for e in eventos), default=0),
        "eventos": sorted(eventos, key=lambda e: e.seq),
        "comentarios": service.ler_comentarios(home, item.id),
        "custo": custo,
        "mp4": Path(mp4) if mp4 else None,
        "previa": previa if previa.is_file() else None,
        "recibo": json.dumps(recibo, ensure_ascii=False, indent=2, sort_keys=True) if recibo is not None else None,
    }


def _estado_texto(c: dict) -> str:
    texto = f"{ROTULO_ESTADO.get(c['estado'], c['estado'])} ({c['estado']})"
    if c["estado"] == "failed" and c["falhou_de"]:
        texto += f", em {c['falhou_de']}"
    return texto


def _cartao_html(c: dict) -> str:
    seq = c["ultimo_seq"]
    atividade = f"evento #{seq}" if seq else "sem eventos"
    linhas = [
        f'<article class="card" data-item="{_e(c["id"])}" data-ultimo-evento="{seq}" data-comentarios="{len(c["comentarios"])}">',
        f'<h3 class="titulo-cartao"><a class="card-link" href="#item-{_e(c["id"])}">{_e(c["titulo"])}</a></h3>',
        f'<p class="meta">{_e(c["marca"])} · rota {_e(ROTULO_ROTA.get(c["rota"], c["rota"]))}</p>',
        f'<p class="meta">Estado: {_e(_estado_texto(c))}</p>',
    ]
    if c["revisao"]:
        linhas.append(f'<p class="meta">Revisão: {_e(ROTULO_REVISAO.get(c["revisao"], c["revisao"]))}</p>')
    if c["custo"] is not None:
        linhas.append(f'<p class="meta">Custo: {c["custo"]["creditos"]} créditos ({_e(c["custo"]["provedor"])})</p>')
    linhas.append(f'<p class="meta">Última atividade: {atividade}</p>')
    linhas.append(f'<p class="meta">Comentários: {len(c["comentarios"])}</p>')
    linhas.append("</article>")
    return "".join(linhas)


def _descreve_evento(evento) -> str:
    dados = evento.data
    if evento.kind == EVENTO_ESTADO:
        de = ROTULO_ESTADO.get(dados.get("from"), dados.get("from"))
        para = ROTULO_ESTADO.get(dados.get("to"), dados.get("to"))
        return f"{de} → {para}"
    return "; ".join(f"{k}: {v}" for k, v in sorted(dados.items()))


def _detalhe_html(c: dict, pasta_saida: Path) -> str:
    item = _e(c["id"])
    partes = [
        f'<article id="item-{item}" class="detalhe" aria-labelledby="titulo-{item}">',
        '<p class="topo-detalhe"><a class="fechar" href="#">Fechar</a></p>',
        f'<h2 id="titulo-{item}" tabindex="-1">{_e(c["titulo"])}</h2>',
        f'<p class="meta">{item} · marca {_e(c["marca"])} · rota {_e(ROTULO_ROTA.get(c["rota"], c["rota"]))} · '
        f"estado {_e(_estado_texto(c))}</p>",
        "<h3>Etapas</h3>",
    ]
    if c["eventos"]:
        partes.append('<ol class="linha-do-tempo">')
        for evento in c["eventos"]:
            partes.append(
                f'<li>#{evento.seq} {_e(_descreve_evento(evento))} <span class="meta">({_e(evento.kind)})</span></li>'
            )
        partes.append("</ol>")
    else:
        partes.append('<p class="meta">Sem eventos.</p>')

    partes.append("<h3>Arquivos</h3><ul>")
    if c["previa"] is not None:
        partes.append(f'<li>Prévia: <a href="{_e(_href(c["previa"], pasta_saida))}">prévia 540x960</a></li>')
    else:
        partes.append("<li>Prévia: não gerada</li>")
    if c["mp4"] is not None and c["mp4"].is_file():
        partes.append(f'<li>MP4 de entrega: <a href="{_e(_href(c["mp4"], pasta_saida))}">abrir o MP4</a></li>')
    else:
        partes.append("<li>MP4 de entrega: não gerado</li>")
    partes.append("</ul>")

    partes.append("<h3>Recibo da mídia</h3>")
    if c["recibo"] is not None:
        partes.append(f'<pre class="recibo">{_e(c["recibo"])}</pre>')
    else:
        partes.append('<p class="meta">Sem recibo de mídia gerada.</p>')

    partes.append("<h3>Comentários e revisão</h3>")
    if c["revisao"]:
        partes.append(f'<p class="meta">Revisão atual: {_e(ROTULO_REVISAO.get(c["revisao"], c["revisao"]))}</p>')
    if c["comentarios"]:
        partes.append('<ol class="comentarios">')
        for linha in c["comentarios"]:
            partes.append(
                f"<li><strong>{_e(linha.get('by', ''))}</strong> em {_e(linha.get('at', ''))} "
                f"({_e(linha.get('kind', ''))}): {_e(linha.get('text', ''))}</li>"
            )
        partes.append("</ol>")
    else:
        partes.append('<p class="meta">Sem comentários.</p>')
    partes.append(
        f'<p class="dica">Para comentar ou revisar, use no terminal: <code>simplicio-video board comment {item} '
        '"texto" --by NOME</code> ou <code>simplicio-video board review '
        f"{item} approve --by NOME</code>.</p>"
    )
    partes.append("</article>")
    return "".join(partes)


def _coluna_html(chave: str, titulo: str, total: int, mostrados: list[dict], restantes: int, pasta_saida: Path) -> str:
    corpo = "".join(_cartao_html(c) for c in mostrados) or '<p class="vazia">(vazia)</p>'
    fora = f'<p class="resto">+{restantes} mais antigos fora do quadro</p>' if restantes else ""
    return (
        f'<section data-coluna="{chave}" class="coluna" data-restantes="{restantes}" aria-labelledby="col-{chave}">'
        f'<h2 id="col-{chave}">{_e(titulo)} <span class="contagem">({total})</span></h2>'
        f"{corpo}{fora}</section>"
    )


def _template() -> str:
    return (resources.files("simplicio_factory.plugins.board") / TEMPLATE).read_text(encoding="utf-8")


def construir(home, pasta_saida: Path | str) -> str:
    """HTML do quadro do JsonStore em `home`. `pasta_saida` é a pasta onde o arquivo será gravado (base dos links)."""
    home = Path(home)
    pasta_saida = Path(pasta_saida).resolve()
    store = JsonStore(home)
    eventos_por_item: dict[str, list] = defaultdict(list)
    for evento in store.read():
        eventos_por_item[evento.item_id].append(evento)
    itens = [i for i in sorted(store.list_items(), key=lambda i: i.id) if i is not None]
    cartoes = [_cartao_de(home, item, eventos_por_item[item.id]) for item in itens]

    colunas: list[str] = []
    detalhes: list[str] = []
    for chave, titulo in model.COLUNAS:
        do_grupo = sorted((c for c in cartoes if c["coluna"] == chave), key=lambda c: (-c["ultimo_seq"], c["id"]))
        mostrados = do_grupo[:LIMITE_POR_COLUNA]
        restantes = len(do_grupo) - len(mostrados)
        colunas.append(_coluna_html(chave, titulo, len(do_grupo), mostrados, restantes, pasta_saida))
        detalhes.extend(_detalhe_html(c, pasta_saida) for c in mostrados)

    resumo = f"{len(itens)} {'item' if len(itens) == 1 else 'itens'} em {len(model.COLUNAS)} colunas"
    return (
        _template()
        .replace("@@RESUMO@@", _e(resumo))
        .replace("@@COLUNAS@@", "\n".join(colunas))
        .replace("@@DETALHES@@", "\n".join(detalhes))
    )
