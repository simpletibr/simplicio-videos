"""G0 (golden, caracterização): o que cada `scrub` esconde, por formato de segredo e por variável de ambiente.

Cinco redatores do mesmo risco (chave vazando em log, erro, manifesto ou texto de terceiro), com listas de padrões e limiares diferentes.
As tabelas abaixo são o comportamento de HOJE; cada discordância é uma divergência herdada, marcada "U22 decide". A correção U22b só
pode mudar linhas destas tabelas (uma união dos padrões só ESCONDE mais: nenhuma linha "masked" pode virar "kept"), e o diff delas é o
que o dono aprova.

Privados exercitados por import direto (caracterização; não há API pública equivalente): busca.scrub, openverse.scrub, swap.scrub,
jobs._scrub (jobs.scrub é o swap.scrub importado), swap_providers.base.redact, social._SECRET_TEXT_RE (detecta e recusa; não esconde),
openverse._TOKEN (token OAuth em memória).

Nenhuma amostra é um segredo: cada uma é montada aqui (prefixo + enchimento de comprimento medido), nunca escrita por inteiro."""
from __future__ import annotations

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
TABELA_FORMATOS = [
    ("Google API key real: AIzaSy + 33", "masked masked masked masked masked hit"),
    ("AIza + 16 (sem Sy)", "masked masked kept kept kept hit"),
    ("AIza + 12", "masked kept kept kept kept miss"),
    ("AIza + 8", "masked kept kept kept kept miss"),
    ("AIza + 7", "kept kept kept kept kept miss"),
    ("AIzaSy + 25", "masked masked masked masked masked hit"),
    ("AIzaSy + 10", "masked kept kept kept kept miss"),
    ("AQ. + 30", "masked masked masked masked masked hit"),
    ("AQ. + 10", "masked masked kept kept kept hit"),
    ("AQ. + 8", "masked kept kept kept kept miss"),
    ("AQ. + 7", "kept kept kept kept kept miss"),
    ("sk- + 20", "masked masked kept kept kept hit"),
    ("sk-proj- + 41 com - e _", "masked masked kept kept kept hit"),
    ("sk- + 8", "masked masked kept kept kept hit"),
    ("sk- + 7", "kept kept kept kept kept miss"),
    ("ghp_ + 36", "masked masked kept kept kept hit"),
    ("ghp_ + 16", "masked masked kept kept kept hit"),
    ("ghp_ + 8", "masked kept kept kept kept miss"),
    ("gho_ + 20", "masked masked kept kept kept hit"),
    ("ghu_ + 20", "masked masked kept kept kept hit"),
    ("ghs_ + 20", "masked masked kept kept kept hit"),
    ("ghr_ + 20", "masked masked kept kept kept hit"),
    ("github_pat_ + 22", "masked kept kept kept kept miss"),
    ("github_pat_ + 19", "kept kept kept kept kept miss"),
    ("xoxb- + 12", "masked masked kept kept kept hit"),
    ("xoxp- + 8", "masked masked kept kept kept hit"),
    ("xoxb- + 7", "kept kept kept kept kept miss"),
    ("eyJ + 10 (JWT)", "masked masked kept kept kept hit"),
    ("eyJ + 9", "kept kept kept kept kept miss"),
    ("ya29. + 10", "masked masked kept kept kept hit"),
    ("ya29. + 9", "kept kept kept kept kept miss"),
    ("AKIA + 16 (AWS)", "masked kept kept kept kept miss"),
    ("AKIA + 15", "kept kept kept kept kept miss"),
    ("sk_live_ + 16 (Stripe)", "masked kept kept kept kept miss"),
    ("rk_test_ + 16 (Stripe)", "masked kept kept kept kept miss"),
    ("sk_live_ + 15", "kept kept kept kept kept miss"),
    ("hf_ + 30 (Hugging Face)", "masked kept kept kept kept miss"),
    ("hf_ + 29", "kept kept kept kept kept miss"),
    ("npm_ + 30", "masked kept kept kept kept miss"),
    ("glpat- + 20 (GitLab)", "masked kept kept kept kept miss"),
    ("glpat- + 19", "kept kept kept kept kept miss"),
    ("Bearer + 20 letras", "masked masked kept kept kept hit"),
    ("Bearer + 16 letras", "kept masked kept kept kept hit"),
    ("Bearer + 12 com digito", "masked kept kept kept kept miss"),
    ("bearer minusculo + 20 letras", "masked kept kept kept kept miss"),
    ("Bearer authentication (frase)", "kept kept kept kept kept miss"),
    ("cabecalho de chave privada PEM", "masked kept kept kept kept miss"),
    ("cabecalho PEM em minusculas", "masked kept kept kept kept miss"),
    ("sk- dentro de palavra: task-based-workflow-x", "kept kept kept kept kept hit"),
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


def test_swap_jobs_and_base_redact_agree_on_every_shape():
    assert all(l["swap.scrub"] == l["jobs._scrub"] == l["base.redact"] for l in linhas().values())  # noqa: E741
    assert jobs.KEY_PATTERN is base.KEY_PATTERN
    # U22 decide: esses três só escondem os 2 formatos do Google (AIzaSy + 25, AQ. + 30)
    assert {r for r, l in linhas().items() if l["swap.scrub"] == "masked"} == {"AQ. + 30", "AIzaSy + 25", "Google API key real: AIzaSy + 33"}


def test_the_busca_hides_what_openverse_hides_except_a_bearer_of_16_letters():
    # U22 decide: a regra da busca NÃO é superconjunto estrito do openverse: "Bearer " + 16 letras (sem dígito) o openverse esconde e a busca deixa
    so_openverse = [r for r, l in linhas().items() if l["openverse.scrub"] == "masked" and l["busca.scrub"] == "kept"]
    assert so_openverse == ["Bearer + 16 letras"]


def test_the_busca_alone_knows_these_formats():
    # U22 decide: formatos que só a busca esconde (nem openverse, nem swap, nem jobs, nem o detector do social)
    so_busca = [r for r, l in linhas().items() if l["busca.scrub"] == "masked" and l["openverse.scrub"] == "kept"]
    assert set(so_busca) == {"AIza + 12", "AIza + 8", "AIzaSy + 10", "AQ. + 8", "ghp_ + 8", "github_pat_ + 22", "Bearer + 12 com digito",
                             "AKIA + 16 (AWS)", "sk_live_ + 16 (Stripe)", "rk_test_ + 16 (Stripe)", "hf_ + 30 (Hugging Face)", "npm_ + 30",
                             "glpat- + 20 (GitLab)", "bearer minusculo + 20 letras", "cabecalho de chave privada PEM",
                             "cabecalho PEM em minusculas"}
    assert "sk- dentro de palavra: task-based-workflow-x" not in so_busca


def test_the_social_detector_has_no_lookbehind_and_fires_on_a_word():
    # U22 decide: `task-based-workflow-x` contém "sk-based-workflow-x"; busca e openverse têm lookbehind e deixam passar, o detector do social recusa
    l = linhas()["sk- dentro de palavra: task-based-workflow-x"]  # noqa: E741
    assert l == {"busca.scrub": "kept", "openverse.scrub": "kept", "swap.scrub": "kept", "jobs._scrub": "kept", "base.redact": "kept",
                 "social._SECRET_TEXT_RE": "hit"}


# (variável, valor, classe em cada coluna de COLUNAS_ENV): o valor exato da variável, sem formato de chave
TABELA_ENV = [
    ("TINYFISH_API_KEY", "valor-do-ambiente-1234", "masked kept kept kept"),
    ("TINYFISH_API_KEY", "abc123", "masked kept kept kept"),
    ("TINYFISH_API_KEY", "abc12", "kept kept kept kept"),
    ("GEMINI_API_KEY", "valor-do-ambiente-1234", "masked kept masked masked"),
    ("GEMINI_API_KEY", "abc123", "kept kept masked masked"),
    ("GEMINI_API_KEY", "abc12", "kept kept kept kept"),
    ("FAL_KEY", "valor-do-ambiente-1234", "masked kept masked masked"),
    ("WAVESPEED_API_KEY", "valor-do-ambiente-1234", "masked kept masked masked"),
    ("KIE_API_KEY", "valor-do-ambiente-1234", "masked kept masked masked"),
    ("DASHSCOPE_API_KEY", "valor-do-ambiente-1234", "masked kept masked masked"),
    ("ELEVENLABS_API_KEY", "valor-do-ambiente-1234", "masked kept kept masked"),
    ("XAI_API_KEY", "valor-do-ambiente-1234", "masked kept kept masked"),
    ("OPENAI_API_KEY", "valor-do-ambiente-1234", "masked kept kept kept"),
    ("VOICESTUDIO_API_KEY", "valor-do-ambiente-1234", "masked kept kept kept"),
    ("GITHUB_TOKEN", "valor-do-ambiente-1234", "masked kept kept kept"),
    ("GITHUB_TOKEN", "abc1234", "kept kept kept kept"),
    ("GITHUB_TOKEN", "abc12345", "masked kept kept kept"),
    ("FOO_PASSWORD", "valor-do-ambiente-1234", "masked kept kept kept"),
    ("FOO_SECRET", "valor-do-ambiente-1234", "masked kept kept kept"),
    ("FOO_PASSWD", "valor-do-ambiente-1234", "masked kept kept kept"),
    ("MY_TOKEN_NAME", "valor-do-ambiente-1234", "masked kept kept kept"),
    ("OPENVERSE_CLIENT_ID", "valor-do-ambiente-1234", "kept masked kept kept"),
    ("OPENVERSE_CLIENT_SECRET", "valor-do-ambiente-1234", "masked masked kept kept"),
    ("HTTPS_PROXY", "http://user:pw1234@proxy.local:3128", "masked kept kept kept"),
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
    # U22 decide: o token OAuth do Openverse vive em openverse._TOKEN; nenhum outro redator o conhece
    monkeypatch.setitem(openverse._TOKEN, "valor", "valor-do-ambiente-1234")
    texto = "x valor-do-ambiente-1234 y"
    obtido = [classe(texto, f(texto)) for f in redatores()[:4]]
    assert dict(zip(COLUNAS_ENV, obtido)) == {"busca.scrub": "kept", "openverse.scrub": "masked", "swap.scrub": "kept", "jobs._scrub": "kept"}


def test_env_value_rules_in_numbers():
    """Os limiares de comprimento do valor do ambiente, como estão hoje (U22 decide): a busca esconde a partir de 8 caracteres numa variável
    de nome genérico (GITHUB_TOKEN) e de 6 na chave do TinyFish; swap e jobs, a partir de 6 (GEMINI_API_KEY)."""
    # derivado da tabela acima: valores curtos
    curtos = {(n, len(v)): c for n, v, c in TABELA_ENV if len(v) <= 7}
    assert curtos == {("TINYFISH_API_KEY", 6): "masked kept kept kept", ("TINYFISH_API_KEY", 5): "kept kept kept kept",
                      ("GEMINI_API_KEY", 6): "kept kept masked masked", ("GEMINI_API_KEY", 5): "kept kept kept kept",
                      ("GITHUB_TOKEN", 7): "kept kept kept kept"}
