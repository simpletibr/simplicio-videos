"""G0 (golden, caracterização): o que cada `scrub` esconde, por formato de segredo e por variável de ambiente.

Cinco redatores do mesmo risco (chave vazando em log, erro, manifesto ou texto de terceiro), com listas de padrões e limiares diferentes.
As tabelas abaixo são o comportamento de HOJE; cada discordância é uma divergência herdada, marcada "U22 decide". A correção U22b só
pode mudar linhas destas tabelas (uma união dos padrões só ESCONDE mais: nenhuma linha "masked" pode virar "kept"), e o diff delas é o
que o dono aprova.

Privados exercitados por import direto (caracterização; não há API pública equivalente): busca.scrub, openverse.scrub, swap.scrub,
jobs._scrub (jobs.scrub é o swap.scrub importado), swap_providers.base.redact, social._SECRET_TEXT_RE (detecta e recusa; não esconde),
openverse._TOKEN (token OAuth em memória).

Nenhuma amostra é um segredo: cada uma é montada aqui (prefixo + enchimento de comprimento medido), nunca escrita por inteiro.

U22b (onda MUDA CONTRATO, aprovada pelo dono; o diff deste arquivo contra a main f4d8542 é o que ele vê antes do merge): as tabelas passam a
ser as da REGRA ÚNICA (`redact.py`), a união do que cada redator escondia. Cada comentário "U22 decide" virou "U22b decidiu", com o valor de
antes ao lado; os nomes dos testes e dos rótulos ficam como eram (o id de um teste não some: alguns nomes descrevem o G0, não o depois)."""
from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from simplicio_video import busca, jobs, openverse, social, swap
from simplicio_video.swap_providers import base

COLUNAS = ("busca.scrub", "openverse.scrub", "swap.scrub", "jobs._scrub", "base.redact", "social._SECRET_TEXT_RE")
COLUNAS_ENV = COLUNAS[:4]


def corpo(n: int, alfabeto: str = "Xy1Zq9") -> str:
    return (alfabeto * n)[:n]


def redatores() -> tuple:
    return busca.scrub, openverse.scrub, swap.scrub, jobs._scrub, base.redact


def classe(texto: str, saida: str) -> str:
    if saida == texto:
        return "kept"
    assert saida == "x *** y", repr(saida)
    return "masked"


@pytest.fixture(autouse=True)
def _ambiente_sem_credencial(monkeypatch):
    """Nenhuma credencial do ambiente de quem roda o teste entra na tabela: só a que a linha define."""
    import os
    for nome in list(os.environ):
        if any(p in nome for p in ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASSWD", "PROXY", "proxy", "OPENVERSE")):
            monkeypatch.delenv(nome)
    monkeypatch.setattr(openverse, "_TOKEN", {})


AMOSTRAS = [
 ("Google API key real: AIzaSy + 33", "AIzaSy" + corpo(33)),
 ("AIza + 16 (sem Sy)", "AIza" + corpo(16, "Qz7")),
 ("AIza + 12", "AIza" + corpo(12, "Qz7")),
 ("AIza + 8", "AIza" + corpo(8, "Qz7")),
 ("AIza + 7", "AIza" + corpo(7, "Qz7")),
 ("AIzaSy + 25", "AIzaSy" + corpo(25)),
 ("AIzaSy + 10", "AIzaSy" + corpo(10)),
 ("AQ. + 30", "AQ." + corpo(30)),
 ("AQ. + 10", "AQ." + corpo(10)),
 ("AQ. + 8", "AQ." + corpo(8)),
 ("AQ. + 7", "AQ." + corpo(7)),
 ("sk- + 20", "sk-" + corpo(20)),
 ("sk-proj- + 41 com - e _", "sk-proj-" + corpo(20) + "_" + corpo(10) + "-" + corpo(9)),
 ("sk- + 8", "sk-" + corpo(8)),
 ("sk- + 7", "sk-" + corpo(7)),
 ("ghp_ + 36", "ghp_" + corpo(36)),
 ("ghp_ + 16", "ghp_" + corpo(16)),
 ("ghp_ + 8", "ghp_" + corpo(8)),
 ("gho_ + 20", "gho_" + corpo(20)),
 ("ghu_ + 20", "ghu_" + corpo(20)),
 ("ghs_ + 20", "ghs_" + corpo(20)),
 ("ghr_ + 20", "ghr_" + corpo(20)),
 ("github_pat_ + 22", "github_pat_" + corpo(22)),
 ("github_pat_ + 19", "github_pat_" + corpo(19)),
 ("xoxb- + 12", "xoxb-" + corpo(12)),
 ("xoxp- + 8", "xoxp-" + corpo(8)),
 ("xoxb- + 7", "xoxb-" + corpo(7)),
 ("eyJ + 10 (JWT)", "eyJ" + corpo(10)),
 ("eyJ + 9", "eyJ" + corpo(9)),
 ("ya29. + 10", "ya29." + corpo(10)),
 ("ya29. + 9", "ya29." + corpo(9)),
 ("AKIA + 16 (AWS)", "AKIA" + corpo(16, "Q7Z")),
 ("AKIA + 15", "AKIA" + corpo(15, "Q7Z")),
 ("sk_live_ + 16 (Stripe)", "sk_live_" + corpo(16)),
 ("rk_test_ + 16 (Stripe)", "rk_test_" + corpo(16)),
 ("sk_live_ + 15", "sk_live_" + corpo(15)),
 ("hf_ + 30 (Hugging Face)", "hf_" + corpo(30)),
 ("hf_ + 29", "hf_" + corpo(29)),
 ("npm_ + 30", "npm_" + corpo(30)),
 ("glpat- + 20 (GitLab)", "glpat-" + corpo(20)),
 ("glpat- + 19", "glpat-" + corpo(19)),
 ("Bearer + 20 letras", "Bearer " + corpo(20, "Abc")),
 ("Bearer + 16 letras", "Bearer " + corpo(16, "Abc")),
 ("Bearer + 12 com digito", "Bearer " + "abc123def456"),
 ("bearer minusculo + 20 letras", "bearer " + corpo(20, "abc")),
 ("Bearer authentication (frase)", "Bearer authentication"),
 ("cabecalho de chave privada PEM", "-----BEGIN RSA PRIVATE KEY-----"),
 ("cabecalho PEM em minusculas", "-----begin private key-----"),
 ("sk- dentro de palavra: task-based-workflow-x", "task-based-workflow-x"),
]


# (rótulo, classe em cada coluna de COLUNAS)
# U22b decidiu (cada linha mudada está na tabela "antes -> depois" do PR): as 5 funções escondem a UNIÃO das de antes, então as 5 colunas de cada
# linha são iguais; o limiar de cada formato é o MENOR entre os redatores de antes; a coluna do social vira "hit" onde a união esconde (antes: o
# detector do social só recusava 8 formatos e recusava uma palavra comum). Os casos de decisão (formato colado a uma palavra, "Bearer" fora da
# classe do openverse...) têm tabela própria mais abaixo, TABELA_BORDAS, porque a saída deles não é "x *** y".
TABELA_FORMATOS = [
    ("Google API key real: AIzaSy + 33", "masked masked masked masked masked hit"),
    ("AIza + 16 (sem Sy)", "masked masked masked masked masked hit"),
    ("AIza + 12", "masked masked masked masked masked hit"),
    ("AIza + 8", "masked masked masked masked masked hit"),
    ("AIza + 7", "kept kept kept kept kept miss"),
    ("AIzaSy + 25", "masked masked masked masked masked hit"),
    ("AIzaSy + 10", "masked masked masked masked masked hit"),
    ("AQ. + 30", "masked masked masked masked masked hit"),
    ("AQ. + 10", "masked masked masked masked masked hit"),
    ("AQ. + 8", "masked masked masked masked masked hit"),
    ("AQ. + 7", "kept kept kept kept kept miss"),
    ("sk- + 20", "masked masked masked masked masked hit"),
    ("sk-proj- + 41 com - e _", "masked masked masked masked masked hit"),
    ("sk- + 8", "masked masked masked masked masked hit"),
    ("sk- + 7", "kept kept kept kept kept miss"),
    ("ghp_ + 36", "masked masked masked masked masked hit"),
    ("ghp_ + 16", "masked masked masked masked masked hit"),
    ("ghp_ + 8", "masked masked masked masked masked hit"),
    ("gho_ + 20", "masked masked masked masked masked hit"),
    ("ghu_ + 20", "masked masked masked masked masked hit"),
    ("ghs_ + 20", "masked masked masked masked masked hit"),
    ("ghr_ + 20", "masked masked masked masked masked hit"),
    ("github_pat_ + 22", "masked masked masked masked masked hit"),
    ("github_pat_ + 19", "kept kept kept kept kept miss"),
    ("xoxb- + 12", "masked masked masked masked masked hit"),
    ("xoxp- + 8", "masked masked masked masked masked hit"),
    ("xoxb- + 7", "kept kept kept kept kept miss"),
    ("eyJ + 10 (JWT)", "masked masked masked masked masked hit"),
    ("eyJ + 9", "kept kept kept kept kept miss"),
    ("ya29. + 10", "masked masked masked masked masked hit"),
    ("ya29. + 9", "kept kept kept kept kept miss"),
    ("AKIA + 16 (AWS)", "masked masked masked masked masked hit"),
    ("AKIA + 15", "kept kept kept kept kept miss"),
    ("sk_live_ + 16 (Stripe)", "masked masked masked masked masked hit"),
    ("rk_test_ + 16 (Stripe)", "masked masked masked masked masked hit"),
    ("sk_live_ + 15", "kept kept kept kept kept miss"),
    ("hf_ + 30 (Hugging Face)", "masked masked masked masked masked hit"),
    ("hf_ + 29", "kept kept kept kept kept miss"),
    ("npm_ + 30", "masked masked masked masked masked hit"),
    ("glpat- + 20 (GitLab)", "masked masked masked masked masked hit"),
    ("glpat- + 19", "kept kept kept kept kept miss"),
    ("Bearer + 20 letras", "masked masked masked masked masked hit"),
    ("Bearer + 16 letras", "masked masked masked masked masked hit"),
    ("Bearer + 12 com digito", "masked masked masked masked masked hit"),
    ("bearer minusculo + 20 letras", "masked masked masked masked masked hit"),
    ("Bearer authentication (frase)", "kept kept kept kept kept miss"),
    ("cabecalho de chave privada PEM", "masked masked masked masked masked hit"),
    ("cabecalho PEM em minusculas", "masked masked masked masked masked hit"),
    ("sk- dentro de palavra: task-based-workflow-x", "kept kept kept kept kept miss"),
]


@pytest.mark.parametrize("rotulo", [r[0] for r in TABELA_FORMATOS])
def test_the_table_of_secret_formats_by_module_is_the_one_of_today(rotulo):
    esperado = dict(TABELA_FORMATOS_POR_ROTULO[rotulo])
    texto = "x " + dict(AMOSTRAS)[rotulo] + " y"
    obtido = [classe(texto, f(texto)) for f in redatores()]
    obtido.append("hit" if social._SECRET_TEXT_RE.search(texto) else "miss")
    assert dict(zip(COLUNAS, obtido)) == esperado


TABELA_FORMATOS_POR_ROTULO = {r[0]: dict(zip(COLUNAS, r[1].split())) for r in TABELA_FORMATOS}


def test_every_sample_has_a_row_and_the_other_way_round():
    assert [r[0] for r in AMOSTRAS] == [r[0] for r in TABELA_FORMATOS]


def linhas() -> dict:
    return {r[0]: dict(zip(COLUNAS, r[1].split())) for r in TABELA_FORMATOS}


FICAM_A_VISTA = {"AIza + 7", "AQ. + 7", "sk- + 7", "github_pat_ + 19", "xoxb- + 7", "eyJ + 9", "ya29. + 9", "AKIA + 15", "sk_live_ + 15",
                    "hf_ + 29", "glpat- + 19", "Bearer authentication (frase)", "sk- dentro de palavra: task-based-workflow-x"}


def test_swap_jobs_and_base_redact_agree_on_every_shape():
    assert all(l["swap.scrub"] == l["jobs._scrub"] == l["base.redact"] for l in linhas().values())  # noqa: E741
    # U22b decidiu: as cinco funções são UMA, a de redact.py (antes: jobs.KEY_PATTERN is base.KEY_PATTERN, duas cópias do regex só do Google)
    from simplicio_video import redact
    assert busca.scrub is openverse.scrub is swap.scrub is jobs._scrub is base.redact is redact.scrub
    # U22b decidiu: esses três escondem a união dos formatos, de qualquer comprimento a partir do limiar (antes: só os 2 do Google, AIzaSy + 25 e AQ. + 30)
    assert {r for r, l in linhas().items() if l["swap.scrub"] == "masked"} == {r for r, _ in TABELA_FORMATOS} - FICAM_A_VISTA


def test_the_busca_hides_what_openverse_hides_except_a_bearer_of_16_letters():
    # U22b decidiu: a regra da busca passa a esconder também o "Bearer " + 16 letras (sem dígito) que o openverse escondia (antes: só o openverse)
    so_openverse = [r for r, l in linhas().items() if l["openverse.scrub"] == "masked" and l["busca.scrub"] == "kept"]
    assert so_openverse == []
    assert linhas()["Bearer + 16 letras"]["busca.scrub"] == "masked"


def test_the_busca_alone_knows_these_formats():
    # U22b decidiu: nenhum formato é só da busca: o openverse, o swap, o jobs e o detector do social passam a conhecer os mesmos
    # (antes: 16 formatos só da busca: AIza + 12, AIza + 8, AIzaSy + 10, AQ. + 8, ghp_ + 8, github_pat_ + 22, Bearer + 12 com dígito, AKIA, Stripe x2,
    # hf_, npm_, glpat-, bearer minúsculo + 20, os 2 cabeçalhos PEM)
    so_busca = [r for r, l in linhas().items() if l["busca.scrub"] == "masked" and l["openverse.scrub"] == "kept"]
    assert so_busca == []
    assert "sk- dentro de palavra: task-based-workflow-x" not in so_busca
    assert all(linhas()[r]["social._SECRET_TEXT_RE"] == "hit" for r in ("AKIA + 16 (AWS)", "hf_ + 30 (Hugging Face)", "cabecalho de chave privada PEM"))


def test_the_social_detector_has_no_lookbehind_and_fires_on_a_word():
    # U22b decidiu: o detector do social passa a ter o lookbehind da busca e do openverse e DEIXA PASSAR a palavra: `task-based-workflow-x` contém
    # "sk-based-workflow-x" mas não é uma chave (antes: o social recusava a legenda; busca e openverse já deixavam passar)
    l = linhas()["sk- dentro de palavra: task-based-workflow-x"]  # noqa: E741
    assert l == {"busca.scrub": "kept", "openverse.scrub": "kept", "swap.scrub": "kept", "jobs._scrub": "kept", "base.redact": "kept",
                 "social._SECRET_TEXT_RE": "miss"}


# (variável, valor, classe em cada coluna de COLUNAS_ENV): o valor exato da variável, sem formato de chave
# U22b decidiu: as 4 colunas de cada linha são iguais (antes: cada módulo escondia o seu subconjunto das variáveis); a união é: variável
# CONHECIDA a partir de 6 caracteres, variável de nome genérico (KEY, SECRET, TOKEN, PASSWORD, PASSWD como palavra inteira) e proxy com senha a partir de 8.
TABELA_ENV = [
    ("TINYFISH_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("TINYFISH_API_KEY", "abc123", "masked masked masked masked"),
    ("TINYFISH_API_KEY", "abc12", "kept kept kept kept"),
    ("GEMINI_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("GEMINI_API_KEY", "abc123", "masked masked masked masked"),
    ("GEMINI_API_KEY", "abc12", "kept kept kept kept"),
    ("FAL_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("WAVESPEED_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("KIE_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("DASHSCOPE_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("ELEVENLABS_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("XAI_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("OPENAI_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("VOICESTUDIO_API_KEY", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("GITHUB_TOKEN", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("GITHUB_TOKEN", "abc1234", "kept kept kept kept"),
    ("GITHUB_TOKEN", "abc12345", "masked masked masked masked"),
    ("FOO_PASSWORD", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("FOO_SECRET", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("FOO_PASSWD", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("MY_TOKEN_NAME", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("OPENVERSE_CLIENT_ID", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("OPENVERSE_CLIENT_SECRET", "valor-do-ambiente-1234", "masked masked masked masked"),
    ("HTTPS_PROXY", "http://user:pw1234@proxy.local:3128", "masked masked masked masked"),
    ("HTTPS_PROXY", "http://proxy.local:3128", "kept kept kept kept"),
    ("PIP_KEYRING_PROVIDER", "subprocess", "kept kept kept kept"),
    ("MONKEY_BUSINESS", "valor-do-ambiente-1234", "kept kept kept kept"),
]


@pytest.mark.parametrize("linha", TABELA_ENV, ids=lambda r: f"{r[0]}={len(r[1])}c")
def test_the_table_of_environment_values_by_module_is_the_one_of_today(monkeypatch, linha):
    nome, valor, esperado = linha
    monkeypatch.setenv(nome, valor)
    texto = "x " + valor + " y"
    obtido = [classe(texto, f(texto)) for f in redatores()[:4]]
    assert dict(zip(COLUNAS_ENV, obtido)) == dict(zip(COLUNAS_ENV, esperado.split()))


def test_the_openverse_oauth_token_in_memory_is_hidden_by_openverse_only(monkeypatch):
    # U22b decidiu: o token OAuth do Openverse vive em openverse._TOKEN e o openverse o registra em redact (`redact.register`): todos os redatores
    # o escondem (antes: nenhum outro redator o conhecia)
    monkeypatch.setitem(openverse._TOKEN, "valor", "valor-do-ambiente-1234")
    texto = "x valor-do-ambiente-1234 y"
    obtido = [classe(texto, f(texto)) for f in redatores()[:4]]
    assert dict(zip(COLUNAS_ENV, obtido)) == {"busca.scrub": "masked", "openverse.scrub": "masked", "swap.scrub": "masked", "jobs._scrub": "masked"}


def test_env_value_rules_in_numbers():
    """Os limiares de comprimento do valor do ambiente, como ficam (U22b decidiu: o menor limiar de cada variável entre os redatores de antes): a
    variável CONHECIDA (provedores do swap, TinyFish, ElevenLabs, xAI, Openverse) a partir de 6 caracteres, a de nome genérico (GITHUB_TOKEN) e o
    proxy com senha a partir de 8. Antes: a busca escondia a partir de 8 numa variável de nome genérico e de 6 na chave do TinyFish; swap e jobs, a
    partir de 6 (GEMINI_API_KEY); o openverse só as suas."""
    # derivado da tabela acima: valores curtos
    curtos = {(n, len(v)): c for n, v, c in TABELA_ENV if len(v) <= 7}
    assert curtos == {("TINYFISH_API_KEY", 6): "masked masked masked masked", ("TINYFISH_API_KEY", 5): "kept kept kept kept",
                      ("GEMINI_API_KEY", 6): "masked masked masked masked", ("GEMINI_API_KEY", 5): "kept kept kept kept",
                      ("GITHUB_TOKEN", 7): "kept kept kept kept"}


# ============================================================================================ U22b: a regra única (redact.py)
# Testes NOVOS da onda. O módulo `redact` não existe na main: tudo daqui o importa DENTRO do teste, para que a coleta do arquivo não quebre e
# os testes das tabelas acima fiquem vermelhos pelo VALOR (o que escondem), não por um import.

# As regras de hoje (main f4d8542), copiadas AQUI como referência (a busca, o openverse e o `KEY_PATTERN` do swap/jobs/base): tudo o que qualquer
# uma delas escondia, a regra única tem de esconder. O detector do social não entra: é o regex do openverse sem o lookbehind, e o que ele pegava
# a mais era palavra (`task-based-workflow-x`), a decisão da linha de baixo.
REFERENCIA_BUSCA = re.compile(r"(?<![A-Za-z0-9_])(?:AIza[0-9A-Za-z_-]{8,}|AQ\.[A-Za-z0-9_-]{8,}|sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|"
                              r"github_pat_[A-Za-z0-9_]{20,}|xox[a-z]-[A-Za-z0-9-]{8,}|eyJ[A-Za-z0-9_-]{10,}|ya29\.[A-Za-z0-9_-]{10,}|AKIA[0-9A-Z]{16}|"
                              r"[sr]k_(?:live|test)_[A-Za-z0-9]{16,}|hf_[A-Za-z0-9]{30,}|npm_[A-Za-z0-9]{30,}|glpat-[A-Za-z0-9_-]{20,}|"
                              r"(?i:bearer)\s+(?:(?=[A-Za-z0-9._~+/=-]{20})|(?=[A-Za-z._~+/=-]*[0-9]))[A-Za-z0-9._~+/=-]{8,})|"
                              r"(?i:-----BEGIN [A-Z ]*PRIVATE KEY-----)")
REFERENCIA_OPENVERSE = re.compile(r"(?<![A-Za-z0-9_])(sk-[A-Za-z0-9_-]{8,}|AIza[0-9A-Za-z_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|xox[a-z]-[A-Za-z0-9-]{8,}|"
                                  r"eyJ[A-Za-z0-9_-]{10,}|ya29\.[A-Za-z0-9_-]{10,}|AQ\.[A-Za-z0-9_-]{10,}|Bearer\s+[A-Za-z0-9._-]{16,})")
REFERENCIA_GOOGLE = re.compile(r"AIzaSy[A-Za-z0-9_-]{25,}|AQ\.[A-Za-z0-9_.-]{30,}")


def posicoes(regex, texto: str) -> set:
    return {i for m in regex.finditer(texto) for i in range(m.start(), m.end())}


def textos_de_borda() -> list:
    """Cada amostra da tabela, e mais algumas de cauda difícil, em contextos diferentes: depois de um não-palavra, colada a uma palavra, com cauda."""
    extras = ["AQ." + corpo(10) + "." + corpo(25),                   # ponto no meio: só a classe do Google (30+) cobre o que vem depois do ponto
              "AQ." + corpo(40) + "._-",                            # a chave do tests/test_swap.py: cauda com . _ -
              "AIzaSy" + corpo(40) + "-_",
              "Bearer " + corpo(10, "Abc") + "~" + corpo(10, "Abc"),  # o til só está na classe da busca
              "bearer " + corpo(22, "abc") + "/+=",
              "Bearer " + corpo(15, "Abc") + "7"]
    contextos = [("x ", " y"), ("=", ""), (":", ","), ('"', '"'), ("/", "/"), ("(", ")"), ("-", ""), (".", ""), ("key_", ""), ("a", ""), ("9", ""),
                 ("", "."), ("", "-x"), ("", "~")]
    return [antes + token + depois for token in [t for _, t in AMOSTRAS] + extras for antes, depois in contextos]


def test_the_one_rule_hides_every_character_any_rule_of_today_hid():
    from simplicio_video import redact
    falhas = []
    for texto in textos_de_borda():
        escondido = posicoes(redact.SECRET_RE, texto)
        for nome, ref in (("busca", REFERENCIA_BUSCA), ("openverse", REFERENCIA_OPENVERSE), ("swap/jobs/base", REFERENCIA_GOOGLE)):
            if not posicoes(ref, texto) <= escondido:
                falhas.append((nome, texto))
    assert falhas == []


def test_the_one_rule_is_idempotent_and_the_mask_is_not_a_secret():
    from simplicio_video import redact
    for texto in textos_de_borda():
        uma_vez = redact.scrub(texto)
        assert redact.scrub(uma_vez) == uma_vez
    assert not redact.SECRET_RE.search(redact.MASK) and redact.MASK == "***"


# Palavras e frases que só PARECEM chave. Nenhum redator de hoje as esconde (o detector do social recusava várias, sem lookbehind) e a
# regra única também não pode: esconder texto comum é o outro lado do vazamento (a busca recusaria a consulta; o log perderia a palavra).
INOCENTES = ["task-based-workflow-x", "risk-assessment-abcdefgh", "desk-organizer-set-2026", "disk-images-folder-final", "flask-sqlalchemy-tutorial-1",
             "tutorial sk-learn pipeline", "task-based planning", "o que e um Bearer token", "Bearer authentication", "bearer authentication",
             "AQ. estudo de caso", "FAQ.html", "FAQ.Short-title", "npm_lifecycle_event", "hf_model_name_long", "sk_learn_pipeline_x", "glpat explicado",
             "AIza", "ghp_", "sk-", "Bearer", "eyJ", "ya29.", "-----BEGIN-----", "xoxo", "AKIA", "high_resolution_preset", "https://example.com/risk-assessment-photo.jpg",
             "ya29x" + corpo(15), "AQx" + corpo(35), "AQx" + corpo(10)]  # o ponto de `ya29.` e de `AQ.` é um ponto


@pytest.mark.parametrize("texto", INOCENTES)
def test_text_that_only_looks_like_a_key_is_hidden_by_no_redactor_and_refused_by_none(texto):
    assert [f(texto) for f in redatores()] == [texto] * 5
    assert not social._SECRET_TEXT_RE.search(texto)


# (rótulo, texto, o que as 5 funções devolvem, o detector do social acha?). Os casos de DECISÃO da U22b, cuja saída não é "x *** y" (parte do texto
# fica à vista). Antes, uma chave do Google colada a uma palavra era escondida pelo swap/jobs/base e não pela busca/openverse (lookbehind), e o
# detector do social, sem lookbehind, recusava qualquer formato colado a uma palavra.
TABELA_BORDAS = [
    ("AIzaSy + 25 colado a um sublinhado: a chave do Google continua escondida", "x key_AIzaSy" + corpo(25) + " y", "x key_*** y", "hit"),
    ("AQ. + 30 colado a uma letra (FAQ.): escondida como no swap", "x FAQ." + corpo(30) + " y", "x F*** y", "hit"),
    ("AQ. com ponto no meio: o resto depois do ponto tambem", "x AQ." + corpo(10) + "." + corpo(25) + " y", "x *** y", "hit"),
    ("AQ. + 40 com cauda ._-", "x AQ." + corpo(40) + "._- y", "x *** y", "hit"),
    ("AIza + 16 colado a uma letra: sem lookbehind nao e chave", "x yAIza" + corpo(16, "Qz7") + " y", "x yAIza" + corpo(16, "Qz7") + " y", "miss"),
    ("sk- + 20 colado a uma letra (ask-): palavra", "x ask-" + corpo(20) + " y", "x ask-" + corpo(20) + " y", "miss"),
    ("ghp_ + 20 colado a um sublinhado: nao e chave", "x my_ghp_" + corpo(20) + " y", "x my_ghp_" + corpo(20) + " y", "miss"),
    ("eyJ + 20 colado a um digito: nao e chave", "x 9eyJ" + corpo(20) + " y", "x 9eyJ" + corpo(20) + " y", "miss"),
    ("bearer minusculo + 16 letras: nenhum redator de antes escondia", "x bearer " + corpo(16, "abc") + " y", "x bearer " + corpo(16, "abc") + " y", "miss"),
    ("Bearer + 15 letras: abaixo do limiar do openverse", "x Bearer " + corpo(15, "Abc") + " y", "x Bearer " + corpo(15, "Abc") + " y", "miss"),
    ("Bearer + 21 com til no meio: so a classe da busca cobre", "x Bearer " + corpo(10, "Abc") + "~" + corpo(10, "Abc") + " y", "x *** y", "hit"),
    ("cabecalho PEM colado a uma letra: sem lookbehind, como na busca", "x a-----BEGIN PRIVATE KEY----- y", "x a*** y", "hit"),
    ("duas chaves seguidas", "x AIzaSy" + corpo(33) + " sk-" + corpo(20) + " y", "x *** *** y", "hit"),
    ("chave dentro de um JSON", '{"k":"sk-' + corpo(20) + '"}', '{"k":"***"}', "hit"),
    ("chave na query de uma URL", "https://x/y?key=AIzaSy" + corpo(33) + "&a=1", "https://x/y?key=***&a=1", "hit"),
    # os limiares, um de cada lado (a tabela de cima só tem o lado de baixo de alguns): colados, para que valha o do Google sem lookbehind
    ("AIzaSy + 24 colado a um sublinhado: abaixo do limiar do Google", "x key_AIzaSy" + corpo(24) + " y", "x key_AIzaSy" + corpo(24) + " y", "miss"),
    ("AQ. + 29 colado a uma letra (FAQ.): abaixo do limiar do Google", "x FAQ." + corpo(29) + " y", "x FAQ." + corpo(29) + " y", "miss"),
    ("ghp_ + 7: abaixo do limiar", "x ghp_" + corpo(7) + " y", "x ghp_" + corpo(7) + " y", "miss"),
    ("github_pat_ + 20: o limiar", "x github_pat_" + corpo(20) + " y", "x *** y", "hit"),
    ("npm_ + 29: abaixo do limiar", "x npm_" + corpo(29) + " y", "x npm_" + corpo(29) + " y", "miss"),
    ("Bearer + 20 com til: o limiar da classe da busca", "x Bearer ~" + corpo(19, "Abc") + " y", "x *** y", "hit"),
    ("Bearer + 19 com til: abaixo do limiar", "x Bearer ~" + corpo(18, "Abc") + " y", "x Bearer ~" + corpo(18, "Abc") + " y", "miss"),
    ("Bearer + 8 com digito: o limiar", "x Bearer 1" + corpo(7, "abc") + " y", "x *** y", "hit"),
    ("Bearer + 7 com digito: abaixo do limiar", "x Bearer 1" + corpo(6, "abc") + " y", "x Bearer 1" + corpo(6, "abc") + " y", "miss"),
    ("bearer minusculo + tabulacao + 22 letras: o espaco em branco da busca", "x bearer\t" + corpo(22, "abc") + " y", "x *** y", "hit"),
    ("Bearer + tabulacao + 16 letras: o espaco em branco do openverse", "x Bearer\t" + corpo(16, "Abc") + " y", "x *** y", "hit"),
]


@pytest.mark.parametrize("linha", TABELA_BORDAS, ids=lambda r: r[0])
def test_the_border_cases_of_the_one_rule(linha):
    _, texto, esperado, social_acha = linha
    assert [f(texto) for f in redatores()] == [esperado] * 5
    assert ("hit" if social._SECRET_TEXT_RE.search(texto) else "miss") == social_acha


# ---------------------------------------------------------------------------------------------- a API do módulo novo

def test_redact_is_a_leaf_of_the_package_and_the_social_detector_is_its_regex():
    from simplicio_video import redact
    donos = set()
    for no in ast.walk(ast.parse(Path(redact.__file__).read_text(encoding="utf8"))):
        if isinstance(no, ast.ImportFrom):
            donos.add(("." * no.level) + (no.module or ""))
        elif isinstance(no, ast.Import):
            donos.update(a.name for a in no.names)
    assert {d for d in donos if d.startswith(".")} <= {".terceiros", "."}  # só o terceiros (ele mesmo uma folha) e `from . import terceiros`
    assert all(d.split(".")[0] in sys.stdlib_module_names for d in donos if not d.startswith("."))  # o resto é biblioteca padrão
    assert social._SECRET_TEXT_RE is redact.SECRET_RE  # `social.make_plan` recusa com a regra única


def test_a_registered_source_is_hidden_and_a_short_or_empty_value_is_not():
    from simplicio_video import redact
    redact.register("teste-u22b", lambda: ["valor-registrado-123", "curto", "", None, "  valor-com-espaco-1  "])
    try:
        assert redact.scrub("a valor-registrado-123 b curto c valor-com-espaco-1 d") == "a *** b curto c *** d"
        redact.register("teste-u22b", lambda: ["outro-valor-registrado"])  # o mesmo nome troca a fonte, não soma
        assert redact.scrub("a valor-registrado-123 b outro-valor-registrado") == "a valor-registrado-123 b ***"
    finally:
        redact.unregister("teste-u22b")
    assert redact.scrub("a outro-valor-registrado b") == "a outro-valor-registrado b"


def test_the_longest_value_is_hidden_first(monkeypatch):
    # dois valores, um prefixo do outro: o curto na frente deixaria a cauda do longo à vista ("***-segredo-longo")
    from simplicio_video import redact
    monkeypatch.setenv("GEMINI_API_KEY", "abcdef")
    monkeypatch.setenv("OPENAI_API_KEY", "abcdef-segredo-longo")
    assert redact.scrub("x abcdef-segredo-longo y abcdef z") == "x *** y *** z"
    assert redact.mask_values("x abcdef-segredo-longo y", ["abcdef", "abcdef-segredo-longo"]) == "x *** y"


def test_the_names_of_the_known_credentials_cover_every_owner_of_one():
    from simplicio_video import redact, swap_providers
    dos_provedores = {cls.env_var for cls in swap_providers.REGISTRY.values() if cls.env_var}
    assert dos_provedores == {"GEMINI_API_KEY", "FAL_KEY", "WAVESPEED_API_KEY", "KIE_API_KEY", "DASHSCOPE_API_KEY"}
    assert dos_provedores | {busca.ENV_CHAVE, openverse.ENV_ID, openverse.ENV_SECRET, "ELEVENLABS_API_KEY", "XAI_API_KEY"} == set(redact.KNOWN_ENV)
    assert set(busca.ENV_PROXY) == set(redact.PROXY_ENV)  # a lista de seis nomes (sem NO_PROXY) que o test_valores_v1 mantém na busca


def test_the_names_the_tests_patch_stay_in_their_module_and_are_still_called(monkeypatch, tmp_path):
    # os testes de hoje fazem monkeypatch destes nomes; a regra única mora em redact.py, mas o código de cada módulo segue chamando o nome local
    monkeypatch.setattr(busca, "_valores_secretos", lambda: ["abcdef-so-da-busca"])
    assert busca._oculta_env("x abcdef-so-da-busca y") == "x *** y"
    with pytest.raises(busca.BuscaError, match="segredo"):
        busca._guard("x abcdef-so-da-busca y")
    monkeypatch.setattr(openverse, "_secret_values", lambda: ["abcdef-so-do-openverse"])
    with pytest.raises(openverse.OpenverseError, match="segredo"):
        openverse._clean_text("x abcdef-so-do-openverse y", "campo")
    monkeypatch.setattr(swap, "_secrets", lambda: ["abcdef-so-do-swap"])
    with pytest.raises(swap.SwapError, match="segredo"):
        swap.write_manifest(tmp_path / "m.json", {"x": "abcdef-so-do-swap"})
    monkeypatch.setattr(openverse, "_TOKEN", {"valor": "token-em-memoria-123"})  # o dict inteiro trocado, como faz o tests/test_openverse.py
    assert swap.scrub("x token-em-memoria-123 y") == "x *** y"


def test_jobs_no_longer_reaches_into_the_private_secrets_of_swap():
    arvore = ast.parse(Path(jobs.__file__).read_text(encoding="utf8"))
    importados = [(n.module, a.name) for n in ast.walk(arvore) if isinstance(n, ast.ImportFrom) and n.level >= 1 for a in n.names if a.name.startswith("_")]
    assert importados == []  # antes: ("swap", "_secrets"), dentro de `jobs._secrets`
    acessos = [n.attr for n in ast.walk(arvore) if isinstance(n, ast.Attribute) and n.attr.startswith("_") and isinstance(n.value, ast.Name)
               and n.value.id in ("swap", "base", "busca", "openverse", "social")]
    assert acessos == []


# ---------------------------------------------------------------------------------------------- o que cada ponto de uso faz com a regra

@pytest.mark.parametrize("texto", ["quem usa Bearer " + corpo(16, "Abc"), "chave sk-" + corpo(20), "AKIA" + corpo(16, "Q7Z"), "hf_" + corpo(30)],
                         ids=["Bearer+16", "sk-", "AKIA", "hf_"])
def test_busca_refuses_a_query_with_any_shape_of_the_union(texto):
    # U22b decidiu: a busca recusa a consulta/URL com o "Bearer " + 16 letras que só o openverse escondia (antes: seguia para o TinyFish)
    with pytest.raises(busca.BuscaError, match=r"^segredo \(chave, token ou senha\) encontrado na consulta: nada foi enviado ao TinyFish nem gravado"):
        busca._confere_segredo(texto, "consulta")


@pytest.mark.parametrize("nome,valor", [("GEMINI_API_KEY", "abc123"), ("XAI_API_KEY", "abc123"), ("OPENVERSE_CLIENT_ID", "valor-id-1234"),
                                        ("ELEVENLABS_API_KEY", "abc123")])
def test_busca_refuses_and_hides_the_value_of_a_known_credential_of_any_module(monkeypatch, nome, valor):
    # U22b decidiu: a busca passa a conhecer as variáveis que só swap/jobs/openverse conheciam, com o limiar mais baixo (antes: GEMINI e as outras
    # só a partir de 8 caracteres e só pelo nome genérico; OPENVERSE_CLIENT_ID, ELEVENLABS e XAI sem nome genérico: nenhum limiar)
    monkeypatch.setenv(nome, valor)
    with pytest.raises(busca.BuscaError, match="segredo"):
        busca._confere_segredo(f"quem usa {valor}", "consulta")
    assert busca._base(f"x {valor} y") == "x *** y"


def test_busca_still_lets_the_ordinary_text_through():
    for texto in ("tutorial sk-learn pipeline", "task-based-workflow-x", "o que e um Bearer token", "AQ. estudo de caso"):
        busca._confere_segredo(texto, "consulta")


@pytest.mark.parametrize("params", [{"prompt": "use sk-" + corpo(20)}, {"prompt": "Bearer " + corpo(16, "Abc")}, {"refs": ["AKIA" + corpo(16, "Q7Z")]},
                                    {"prompt": "AIza" + corpo(12, "Qz7")}], ids=["sk-", "Bearer+16", "AKIA", "AIza+12"])
def test_jobs_refuses_arguments_with_any_shape_of_the_union(params):
    # U22b decidiu: o jobs recusa na submissão todo formato da união (antes: só os 2 do Google); a mensagem é a de sempre
    with pytest.raises(jobs.JobError, match=r"^recusado: os argumentos contêm uma chave de API\. A chave só entra pela variável de ambiente do provedor\.$"):
        jobs._no_secret(params)


@pytest.mark.parametrize("nome,valor", [("GITHUB_TOKEN", "valor-do-ambiente-1234"), ("TINYFISH_API_KEY", "abc123"), ("OPENVERSE_CLIENT_ID", "valor-id-1234"),
                                        ("GEMINI_API_KEY", "abc123"), ("ELEVENLABS_API_KEY", "abc123"), ("XAI_API_KEY", "abc123")])
def test_jobs_refuses_arguments_with_the_value_of_a_credential_of_any_module(monkeypatch, nome, valor):
    monkeypatch.setenv(nome, valor)
    with pytest.raises(jobs.JobError, match="^recusado: os argumentos contêm uma chave de API"):
        jobs._no_secret({"prompt": f"use {valor} aqui"})


def test_jobs_lets_a_path_that_only_looks_like_a_key_through():
    jobs._no_secret({"contrato": "/tmp/task-based-workflow-x/risk-assessment/c.yaml", "refs": ["/data/desk-organizer-set-2026.png"]})


def test_the_swap_manifest_hides_the_union_and_still_refuses_a_provider_key(monkeypatch, tmp_path):
    # U22b decidiu: o manifesto esconde a união (valores de qualquer módulo e formatos); a RECUSA de gravar continua só para a chave de provedor do swap,
    # com a mesma mensagem: um swap pago não perde o manifesto por causa de uma variável alheia (antes: o manifesto só escondia os 2 formatos do Google)
    monkeypatch.setenv("GITHUB_TOKEN", "valor-do-ambiente-1234")
    destino = tmp_path / "m.json"
    swap.write_manifest(destino, {"prompt": "use valor-do-ambiente-1234 e xoxb-" + corpo(12) + " e AIza" + corpo(12, "Qz7"), "ok": "task-based-workflow-x"})
    texto = destino.read_text(encoding="utf8")
    assert "valor-do-ambiente-1234" not in texto and "xoxb-" not in texto and "AIza" not in texto and "task-based-workflow-x" in texto and texto.count("***") == 3
    monkeypatch.setenv("GEMINI_API_KEY", "valor-gemini-1234")
    with pytest.raises(swap.SwapError, match=r"^segredo \(chave de API\) encontrado no manifesto: não gravado$"):
        swap.write_manifest(destino, {"prompt": "use valor-gemini-1234"})


def test_openverse_free_text_refuses_its_own_credential_and_hides_the_rest_of_the_union(monkeypatch):
    # U22b decidiu: o texto digitado recusa a credencial do Openverse como sempre (mesma mensagem) e ESCONDE (não recusa) o valor de outro módulo
    # e os formatos da união (antes: passava o valor de outro módulo e escondia só o regex do openverse)
    monkeypatch.setenv("OPENVERSE_CLIENT_SECRET", "valor-do-openverse-1234")
    monkeypatch.setenv("GEMINI_API_KEY", "valor-gemini-1234")
    with pytest.raises(openverse.OpenverseError, match=r"^segredo \(credencial do Openverse\) encontrado em motivo: nada foi gravado$"):
        openverse._clean_text("uso valor-do-openverse-1234", "motivo")
    assert openverse._clean_text("uso valor-gemini-1234 e AKIA" + corpo(16, "Q7Z") + " e task-based-workflow-x", "motivo") == "uso *** e *** e task-based-workflow-x"


def test_social_refuses_a_caption_or_a_title_with_any_shape_of_the_union_and_takes_a_word(monkeypatch, tmp_path):
    # U22b decidiu: o plano recusa os formatos da união (antes: 8) e aceita a palavra `task-based-workflow-x` (antes: recusava)
    video = tmp_path / "out" / "final.mp4"
    video.parent.mkdir()
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"conteudo-de-teste")
    sonda = {"duration_s": 20.0, "width": 1080, "height": 1920, "fps": 30.0, "video_codec": "h264", "audio_codec": "aac", "container": "mov,mp4,m4a,3gp,3g2,mj2"}
    monkeypatch.setattr(social, "_probe", lambda p: dict(sonda))
    monkeypatch.setattr(social, "_accept_key_path", lambda: tmp_path / "chave-de-aceite" / "social-accept.key")
    monkeypatch.setattr(social, "_now", lambda: datetime(2026, 10, 16, 12, tzinfo=timezone.utc))
    for ruim in ("AKIA" + corpo(16, "Q7Z"), "hf_" + corpo(30), "ghp_" + corpo(8), "AIza" + corpo(12, "Qz7"), "-----BEGIN PRIVATE KEY-----"):
        with pytest.raises(social.SocialError, match="chave|segredo"):
            social.make_plan(str(video), ["youtube", "tiktok"], caption=f"promo {ruim} #video")
        with pytest.raises(social.SocialError, match="chave|segredo"):
            social.make_plan(str(video), ["youtube", "tiktok"], caption="ok #video", title=f"t {ruim}")
    legenda = "o fluxo task-based-workflow-x e o desk-organizer-set #video"
    plano = social.make_plan(str(video), ["youtube", "tiktok"], caption=legenda)
    assert json.loads(Path(plano["path"]).read_text(encoding="utf8"))["caption"] == legenda


# ---------------------------------------------------------------------------------------------- o que a mutação própria deixou vivo

def test_a_registered_source_that_raises_does_not_break_the_redaction(monkeypatch):
    # a mensagem de um erro passa por aqui: uma fonte quebrada não pode virar um segundo erro, e o resto continua escondido
    from simplicio_video import redact
    redact.register("quebrada-u22b", lambda: 1 / 0)
    redact.register("nao-iteravel-u22b", lambda: 42)
    try:
        monkeypatch.setenv("GITHUB_TOKEN", "valor-do-ambiente-1234")
        assert redact.scrub("x valor-do-ambiente-1234 y") == "x *** y"
        assert redact.has_secret("x valor-do-ambiente-1234 y")
    finally:
        redact.unregister("quebrada-u22b")
        redact.unregister("nao-iteravel-u22b")


def test_the_empty_string_is_never_a_value_to_hide():
    from simplicio_video import redact
    assert redact.mask_values("abc", [""]) == "abc" and redact.mask_values("abc", []) == "abc" and redact.mask_values("", ["abcdef"]) == ""


def test_the_name_of_a_credential_variable_is_matched_in_any_case(monkeypatch):
    # antes: o `(?i)` da busca; é o que faz `npm_config_token` e `foo_secret` valerem
    from simplicio_video import redact
    monkeypatch.setenv("my_api_token", "valor-minusculo-1234")
    monkeypatch.setenv("Foo_Secret", "valor-misto-1234567")
    assert redact.scrub("x valor-minusculo-1234 valor-misto-1234567 y") == "x *** *** y"


def test_secret_values_come_longest_first_and_a_value_that_holds_a_key_shape_is_hidden_whole(monkeypatch):
    from simplicio_video import redact
    monkeypatch.setenv("GEMINI_API_KEY", "abcdef")
    monkeypatch.setenv("OPENAI_API_KEY", "abcdef-segredo-longo")
    assert redact.secret_values() == ["abcdef-segredo-longo", "abcdef"]
    # o valor primeiro, o formato depois: um valor que CONTÉM um formato (`sk-` + 8 depois de um hífen) sai inteiro, não "valor-***-fim"
    monkeypatch.setenv("GITHUB_TOKEN", "valor-sk-" + corpo(8) + "-fim")
    assert redact.scrub("x valor-sk-" + corpo(8) + "-fim y") == "x *** y"


def test_the_value_of_a_variable_is_hidden_without_the_blanks_at_its_ends(monkeypatch):
    # `export GITHUB_TOKEN="$(cat arquivo)"` traz o \n do fim: o valor que está no texto não o tem
    from simplicio_video import redact
    monkeypatch.setenv("GITHUB_TOKEN", "  valor-do-ambiente-1234\n")
    monkeypatch.setenv("GEMINI_API_KEY", "abc123\t")
    assert redact.scrub("x valor-do-ambiente-1234 abc123 y") == "x *** *** y"
    assert "valor-do-ambiente-1234" in redact.secret_values() and "abc123" in redact.secret_values()


def test_only_a_value_that_is_a_url_with_a_password_makes_a_proxy_a_credential(monkeypatch):
    from simplicio_video import redact
    monkeypatch.setenv("HTTPS_PROXY", "ver http://user:pw1234@proxy.local:3128 no manual")  # tem a URL, mas o valor não é uma URL de proxy
    monkeypatch.setenv("NO_PROXY", "http://user:pw5678@proxy.local")  # a lista de exceções nunca guarda senha
    assert redact.scrub("x ver http://user:pw1234@proxy.local:3128 no manual y") == "x ver http://user:pw1234@proxy.local:3128 no manual y"
    assert redact.scrub("x http://user:pw5678@proxy.local y") == "x http://user:pw5678@proxy.local y"


# ---------------------------------------------------------------------------------------------- o custo: a lista de valores pedida uma vez por tarefa

def test_scrub_hides_only_the_values_it_is_given_when_it_is_given_some(monkeypatch):
    # o laço que limpa linha a linha (o `_pump` do jobs) pede `secret_values()` uma vez e a passa: ler as ~175 variáveis a cada linha custa 20x o que custava
    from simplicio_video import redact
    monkeypatch.setenv("GITHUB_TOKEN", "valor-do-ambiente-1234")
    assert redact.scrub("x valor-do-ambiente-1234 y", values=[]) == "x valor-do-ambiente-1234 y"
    assert redact.scrub("x valor-do-ambiente-1234 y", values=["valor-do-ambiente-1234"]) == "x *** y"
    assert redact.scrub("x valor-do-ambiente-1234 y") == "x *** y"  # sem `values`, o ambiente de agora
    assert redact.scrub("x AKIA" + corpo(16, "Q7Z") + " y", values=[]) == "x *** y"  # o formato esconde com ou sem lista


def test_the_jobs_pump_reads_the_environment_once_and_still_hides_a_credential_in_every_line(monkeypatch, tmp_path):
    import asyncio
    from simplicio_video import redact

    class Fluxo:
        def __init__(self, *blocos):
            self.blocos = list(blocos)

        async def read(self, n):
            return self.blocos.pop(0) if self.blocos else b""

    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path))
    monkeypatch.setenv("GITHUB_TOKEN", "valor-do-ambiente-1234")
    chamadas = []
    original = redact.secret_values
    monkeypatch.setattr(redact, "secret_values", lambda: chamadas.append(1) or original())
    jid = "20261016-000000-0feedbee"
    jobs.job_dir(jid).mkdir(parents=True)
    saida = b"".join(b"linha %d com valor-do-ambiente-1234 e AKIA%s\n" % (i, corpo(16, "Q7Z").encode()) for i in range(300))
    asyncio.run(jobs._pump(Fluxo(saida), jid, {"tail": [], "json": None}))
    linhas = jobs.read_log(jid).splitlines()
    assert len(linhas) == 300 and linhas[0] == "linha 0 com *** e ***" and linhas[299] == "linha 299 com *** e ***"
    assert len(chamadas) == 1  # antes (e sem isto): uma por linha, 300
