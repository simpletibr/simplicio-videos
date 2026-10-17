"""Os templates que viajam no wheel compilam: o `{{padrao:<bloco>}}` e a composição de cada template `pronto`.

Os testes de venda saíram do motor junto com o `prospect` e levaram a única cobertura do `{{padrao:...}}` e da composição dos
quatro templates que nasceram dele (`institucional-*` e `sazonal-dia-das-criancas`): quebrar o placeholder deixava a suíte
inteira verde. Aqui cada template com composição é compilado com um contrato genérico (sem cliente, sem voz, sem rede),
montado do próprio template: as cenas e os blocos do `template.json` e o padrão de cada bloco da composição.
Hermético: só lê arquivos do repo e escreve em tmp_path.
"""
from __future__ import annotations

import json
import re

import pytest
import yaml

from conftest import ROOT
from simplicio_video import contract as ct
from simplicio_video.compiler import PH, compile_project, render_template

TEMPLATES = ROOT / "src" / "simplicio_video" / "data" / "templates"


def _templates_com_composicao() -> list[str]:
    return sorted(d.name for d in TEMPLATES.iterdir()
                  if (d / "template.json").is_file() and json.loads((d / "template.json").read_text(encoding="utf8")).get("composicao"))


# ------------------------------------------------------------------------------------------------ {{padrao:<bloco>}}
def _com_blocos(mini, **blocos):
    """O contrato mínimo com blocos de motion na cena `a` (bloco -> padrão)."""
    c = ct.load(mini)
    c.data["cenas"][0]["motion"] = [{"padrao": p, "bloco": b, "params": {}} for b, p in blocos.items()]
    return c


def test_padrao_expande_para_o_padrao_do_bloco(mini):
    c = _com_blocos(mini, **{"s2-main": "icon-mascot", "s3-main": "toothbrush-sparkle"})
    assert render_template("{{padrao:s2-main}}|{{padrao:s3-main}}", c, {}) == "icon-mascot|toothbrush-sparkle"
    html = '<div data-composition-id="{{padrao:s2-main}}" data-composition-src="compositions/{{padrao:s2-main}}.html"></div>'
    assert render_template(html, c, {}) == ('<div data-composition-id="icon-mascot" '
                                            'data-composition-src="compositions/icon-mascot.html"></div>')


def test_padrao_de_bloco_que_nao_existe_da_erro_claro(mini):
    c = _com_blocos(mini, **{"s2-main": "icon-mascot"})
    with pytest.raises(SystemExit) as e:
        render_template("compositions/{{padrao:s9-main}}.html", c, {})
    msg = str(e.value)
    assert "{{padrao:s9-main}}" in msg and "bloco: s9-main" in msg, msg


def test_padrao_vira_o_bloco_copiado_para_a_composicao(mini, tmp_path):
    """Com `{{padrao:}}` no template e o bloco no contrato, o compilado aponta para o padrão e copia o `block.html` dele."""
    c = ct.load(mini)
    c.data["cenas"][0]["motion"] = [{"padrao": "icon-mascot", "bloco": "s2-main", "params": {}}]
    comp = tmp_path / "composition"
    comp.mkdir()
    (comp / "index.template.html").write_text('<div data-composition-src="compositions/{{padrao:s2-main}}.html" '
                                              "data-variable-values='{{vars:s2-main}}'></div>", encoding="utf8")
    (tmp_path / "template.json").write_text(json.dumps({"composicao": {"dir": "composition"}}), encoding="utf8")
    c.data["template"] = str(tmp_path)
    c.data["voz"]["habilitada"] = False
    compile_project(c, tmp_path / "wd", None)
    html = (tmp_path / "wd" / "index.html").read_text(encoding="utf8")
    assert 'data-composition-src="compositions/icon-mascot.html"' in html and "{{" not in html
    assert (tmp_path / "wd" / "compositions" / "icon-mascot.html").is_file()


# ------------------------------------------------------------------------------------------------ cada template compila
def _padroes_do_bloco(html: str, bloco: str) -> str:
    m = re.search(rf'id="{re.escape(bloco)}"[^>]*data-composition-src="compositions/([^"]+)\.html"', html)
    assert m, f"a composição não tem o bloco {bloco!r}"
    return m.group(1)


def contrato_generico(tid: str, alternativa: int = 0) -> dict:
    """Contrato sem cliente montado do template: cenas e durações, e um bloco por entrada de `composicao.blocos`.

    O padrão de cada bloco vem do `data-composition-src` da composição; onde ele é `{{padrao:<bloco>}}` o contrato escolhe,
    entre os padrões da cena (`a|b` são as alternativas), o que nenhum outro bloco da cena já usa."""
    d = TEMPLATES / tid
    t = json.loads((d / "template.json").read_text(encoding="utf8"))
    comp = t["composicao"]
    html = (d / comp.get("dir", "composition") / comp.get("entrada", "index.template.html")).read_text(encoding="utf8")
    ids = comp["cenas"]
    if comp.get("blocos"):
        duracoes = [c["dur_s"] for c in t["cenas"]]
    else:  # composição monolítica: as durações saem da grade BASE da própria composição
        base = [float(x) for x in re.search(r"BASE = \[([^\]]+)\]", html).group(1).split(",")]
        duracoes = [round(b - a, 4) for a, b in zip(base, base[1:])]
    assert len(duracoes) == len(ids), (tid, duracoes, ids)
    fonte = {b: _padroes_do_bloco(html, b) for b in comp.get("blocos", [])}
    cenas = [{"id": i, "duracao_s": dur, "motion": []} for i, dur in zip(ids, duracoes)]
    for bloco, padrao in fonte.items():
        m = re.match(r"s(\d+)-", bloco)
        idx = int(m.group(1)) - 1 if m else 0  # bg e x0..xN: na primeira cena
        if padrao.startswith("{{padrao:"):
            usados = {p for b, p in fonte.items() if b.startswith(f"s{idx + 1}-") and not p.startswith("{{")}
            livre = next(p for p in t["cenas"][idx]["padroes"] if p not in usados)
            opcoes = livre.split("|")
            padrao = opcoes[alternativa % len(opcoes)]
        cenas[idx]["motion"].append({"padrao": padrao, "bloco": bloco, "params": {}})
    return {"schema": "simplicio.video-contract/v1",
            "cliente": {"slug": "exemplo", "nome": "Exemplo", "drive_nome": "Exemplo"},
            "campanha": {"id": "Teste", "ano": 2026},
            "formato": {**t["formato"], "duracao_s": round(sum(duracoes), 4)}, "template": tid, "cenas": cenas,
            "voz": {"provider": "file", "habilitada": False},
            "trilha": {"bpm": t["musica"].get("bpm", 120), "seed": 1,
                       "music": {"gain_db": -5, "fade_in_s": 0.05, "fade_out_s": 1, "progression": [[48, [60, 64, 67]]]},
                       "master": {"target_lufs": -14, "true_peak_db": -1.5}},
            "saida": {"arquivo": "out/exemplo.mp4"}}


def _alternativas(tid: str) -> int:
    """Quantas alternativas `a|b` os padrões das cenas oferecem (cada uma vira um contrato)."""
    t = json.loads((TEMPLATES / tid / "template.json").read_text(encoding="utf8"))
    return max([len(p.split("|")) for c in t["cenas"] for p in c["padroes"]] or [1])


CASOS = [(tid, alt) for tid in _templates_com_composicao() for alt in range(_alternativas(tid))]


def test_ha_templates_com_composicao_e_os_quatro_que_nasceram_do_prospect():
    assert {"institucional-odontologia", "institucional-estetica", "institucional-advocacia",
            "sazonal-dia-das-criancas"} <= set(_templates_com_composicao())
    assert any(alt for _, alt in CASOS), "nenhum template tem alternativa a|b: o caso do {{padrao:}} com opção ficou sem cobertura"


@pytest.mark.parametrize("tid,alternativa", CASOS, ids=[f"{t}-alt{a}" for t, a in CASOS])
def test_template_empacotado_valida_e_compila_sem_placeholder_solto(tid, alternativa, tmp_path):
    t = json.loads((TEMPLATES / tid / "template.json").read_text(encoding="utf8"))
    (tmp_path / "contract.yaml").write_text(yaml.safe_dump(contrato_generico(tid, alternativa), allow_unicode=True, sort_keys=False),
                                            encoding="utf8")
    c = ct.load(tmp_path / "contract.yaml")
    rep = ct.validate(c)
    assert rep.ok, rep.errors
    spec = compile_project(c, tmp_path / "wd", None)  # SystemExit com placeholder sem bloco, bloco sem padrão, etc.
    html = (tmp_path / "wd" / "index.html").read_text(encoding="utf8")
    assert not PH.search(html), f"placeholder de template sem resolver: {PH.search(html).group(0)}"
    assert "{{" not in html.split("-->", 1)[-1], "'{{' solto fora do comentário de abertura"
    blocos = t["composicao"].get("blocos", [])
    assert sorted(spec["blocks"]) == sorted(blocos)
    usados = {m["padrao"] for s in c.data["cenas"] for m in s["motion"]}
    for padrao in usados:
        assert (tmp_path / "wd" / "compositions" / f"{padrao}.html").is_file(), f"block.html de {padrao} não foi copiado"
    for bloco in blocos:  # cada bloco aparece na composição com o padrão que o contrato declarou
        padrao = next(m["padrao"] for s in c.data["cenas"] for m in s["motion"] if m["bloco"] == bloco)
        assert re.search(rf'id="{re.escape(bloco)}"[^>]*data-composition-src="compositions/{re.escape(padrao)}\.html"', html), (bloco, padrao)
