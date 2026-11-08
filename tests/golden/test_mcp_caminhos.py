"""G0 (golden, U22h): onde o MCP deixa as tools `media`, `shorts`, `edit`, `clone` (o `get` e o `media` do Hypit) e `install` gravarem.

HOJE (main e U22a): cada uma só exige que o caminho de GRAVAÇÃO seja absoluto e sem `..` (`mcp_policy.caminho_seguro`; o `install --target`, só
absoluto) e o entrega ao CLI: `-o /etc/x`, `-o/etc/x` (colado), `-o` por um link simbólico para `.ssh`, `clone get ... --to /etc/x`,
`install --target {w}/../etc`. Só o voicestudio checava pasta de sistema, oculta e existente. Nada disso é decisão de projeto: é o que o revisor
da U11 mediu (main e antes da U11 iguais) e a onda MUDA CONTRATO (U22) corrige.

U22h: cada caminho que o CLI vai GRAVAR passa por UMA regra a mais, depois de toda recusa que a tool já tinha (essas ficam com as mesmas palavras):
(a) o lugar onde ele cai de verdade (links resolvidos, `//` e `.` tirados) não é um lugar que o motor recusa gravar (`terceiros.lugar_proibido`:
pasta do sistema, início automático, pasta oculta do home, `.git`, o código, as ferramentas e a pasta de dados do motor, site-packages, um venv);
(b) nenhum nome no caminho é link simbólico (a cadeia é andada como `rea_video._plain_path` anda). Os caminhos que o CLI só LÊ (a fonte, o EDL
de leitura, `--ranges`, `--transcript`, os posicionais do Hypit) e os modos que não gravam (`--help`, `--check`, `--dry-run`, `--verify`,
`grade --analyze`) seguem como estavam. Este arquivo escreve as chamadas MCP que passam a ser RECUSADAS e as que seguem ACEITAS; a tabela
de ~2600 chamadas de `tests/test_mcp_policy.py` guarda as recusas de sempre, palavra por palavra.

As tools rodam de verdade (a política é a real); só o CLI é trocado por um gravador. Congelado no Linux (links reais, `/dev/shm` e `/tmp` fora de
`/var`, caixa que conta)."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import simplicio_video
from simplicio_video import mcp_server, terceiros

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="congelado no Linux (links reais, /dev/shm, /tmp fora de /var, caixa que conta)")

DICA = "escolha uma pasta sua (a do projeto, /tmp ou o home fora das pastas ocultas)"
SEM_LINK = "o MCP só grava em caminho real, sem link em nenhuma pasta do caminho"


def real(p) -> Path:
    return Path(os.path.realpath(p))


@pytest.fixture(scope="module")
def ilha():
    """As pastas, os arquivos e os links de teste, criados uma vez num diretório CURTO de /tmp (a recusa corta o caminho em 120 caracteres)."""
    base = real(tempfile.mkdtemp(prefix="g0h-", dir="/tmp"))
    w = SimpleNamespace(base=base, home=base / "home", work=base / "work", data=base / "data", tools=base / "tools",
                        code=Path(simplicio_video.__file__).resolve().parent)
    for pasta in (w.home / ".ssh", w.home / ".config", w.home / "Library" / "LaunchAgents", w.home / "docs", w.data, w.tools, w.work / "out",
                  w.work / "data", w.work / "edit", w.work / ".git" / "hooks", w.work / "lib" / "python3" / "site-packages", w.work / "meuvenv"):
        pasta.mkdir(parents=True)
    (w.work / "meuvenv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    for nome in ("a.mp4", "plan.json", "edl.json", "words.json"):
        (w.work / nome).write_bytes(b"")
    links = {"lnk_ssh": w.home / ".ssh", "lnk_home": w.home, "lnk_etc": Path("/etc"), "lnk_ok": w.work / "out", "lnk_file.mp4": w.work / "a.mp4",
             "dangling": w.work / "nao-existe", "loop_a": w.work / "loop_b", "loop_b": w.work / "loop_a", "lnk_de_lnk": w.work / "lnk_ok",
             "out/lnk_in": w.work / "data"}
    for nome, alvo in links.items():
        (w.work / nome).symlink_to(alvo)
    yield w
    shutil.rmtree(base, ignore_errors=True)


def troca(texto: str, w) -> str:
    return (texto.replace("{work}", str(w.work)).replace("{home}", str(w.home)).replace("{data}", str(w.data)).replace("{tools}", str(w.tools))
            .replace("{code}", str(w.code)))


@pytest.fixture
def mundo(ilha, monkeypatch):
    """A ilha com o ambiente dela (depois do `_hermetic` do conftest, que troca a pasta de dados) e o CLI trocado por um gravador."""
    monkeypatch.setenv("HOME", str(ilha.home))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(ilha.tools))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(ilha.data))
    for var in ("USERPROFILE", "SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "APPDATA"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(mcp_server, "_cli", lambda argv, codigos_ok=(0,): {"ok": True, "cli": list(argv)})
    return ilha


FERRAMENTAS_MCP = {"media": mcp_server.video_media, "shorts": mcp_server.video_shorts, "edit": mcp_server.video_edit,
                   "clone": mcp_server.video_clone, "install": mcp_server.video_install}
ENTREGA = {"media": ["media"], "shorts": ["shorts"], "edit": ["edit"], "clone": ["clone"], "install": ["install", "--json"]}
ACEITA, RECUSA = "aceita", "recusa"


def chama(w, ferramenta: str, argv: list[str]):
    """("aceita", o argv que chegou ao CLI) ou ("recusa", o texto), com os `{work}`, `{home}`... das palavras trocados pelas pastas de teste."""
    r = FERRAMENTAS_MCP[ferramenta](argv=[troca(a, w) for a in argv])
    return (ACEITA, r["cli"]) if r["ok"] else (RECUSA, r["error"])


def aceita(w, ferramenta: str, argv: list[str]):
    return ACEITA, [*ENTREGA[ferramenta], *[troca(a, w) for a in argv]]


def lugar(quem: str, caminho: str, motivo: str, real_: str | None = None) -> str:
    """A recusa de um lugar da regra única: o motivo é o de `terceiros`, e o caminho real vem junto quando ele difere do pedido."""
    nota = f" (o caminho real é {real_!r})" if real_ is not None else ""
    return f"{quem} {caminho!r}: o MCP não grava {motivo}{nota}; {DICA}"


def elo(quem: str, caminho: str, link: str, real_: str | None) -> str:
    """A recusa de um link simbólico: o link é o próprio caminho, ou o primeiro nome do caminho que é link."""
    e_link = "é um link simbólico" if link == caminho else f"{link!r} é um link simbólico"
    seria = f" (o caminho real seria {real_!r})" if real_ is not None else ""
    return f"{quem} {caminho!r}: {e_link}; {SEM_LINK}{seria}"


# Cada tool que grava, com a chamada que leva o caminho `p` ao lugar onde o CLI grava e as palavras com que a recusa abre.
# A chamada traz tudo o que a tool já exigia (fonte, subcomando, `-o`): o que muda de uma linha para outra é só o caminho.
FONTE = "{work}/a.mp4"
CHAMADAS = {
    "media-probe": ("media", "media: saída", lambda p: ["probe", FONTE, "-o", p]),
    "media-audio": ("media", "media: saída", lambda p: ["audio", FONTE, "-o", p]),
    "media-fetch": ("media", "media: saída", lambda p: ["fetch", "https://exemplo.com/v", "--autorizo", "-o", p]),
    "shorts-cut": ("shorts", "shorts: saída", lambda p: ["cut", FONTE, "{work}/plan.json", "-o", p]),
    "shorts-plan": ("shorts", "shorts: saída", lambda p: ["plan", FONTE, "--transcript", "{work}/words.json", "-o", p]),
    "shorts-run": ("shorts", "shorts: saída", lambda p: ["run", FONTE, "--transcript", "{work}/words.json", "--out", p]),
    "shorts-inspect": ("shorts", "shorts: saída", lambda p: ["inspect", FONTE, "-o", p]),
    "edit-render": ("edit", "edit render: saída", lambda p: ["render", "{work}/edl.json", "-o", p]),
    "edit-transcribe": ("edit", "edit transcribe: saída", lambda p: ["transcribe", FONTE, "-o", p]),
    "edit-verify": ("edit", "edit verify: saída", lambda p: ["verify", FONTE, "1", "2", "-o", p]),
    "edit-grade": ("edit", "edit grade: saída", lambda p: ["grade", FONTE, "-o", p]),
    "clone-get": ("clone", "clone get: o destino --to", lambda p: ["get", "b1", "--output", "n", "--to", p]),
    "clone-cut": ("clone", "clone media cut: o destino --to", lambda p: ["media", "cut", FONTE, "--start", "0", "--end", "1", "--to", p]),
    "clone-frames": ("clone", "clone media frames: o destino --to", lambda p: ["media", "frames", FONTE, "--at", "2", "--to", p]),
    "clone-tile": ("clone", "clone media tile: o destino --to", lambda p: ["media", "tile", FONTE, "--to", p]),
    "clone-tiles": ("clone", "clone media tiles: o destino --to", lambda p: ["media", "tiles", FONTE, "--ranges", "{work}/words.json", "--to", p]),
    "clone-boundaries": ("clone", "clone media boundaries: o destino --to", lambda p: ["media", "boundaries", FONTE, "--to", p]),
    "install": ("install", "install: a pasta de --target", lambda p: ["--target", p]),
}
# A chamada de cada tool que o MCP trata de um jeito próprio, para os lugares que o CLI só grava POR CAUSA do caminho: o EDL de `edit render`
# (os intermediários vão ao lado dele) e a pasta EDIT_DIR de `edit pack` (o takes_packed.md vai nela).
CHAMADAS_DE_PASTA = {
    "edit-render-edl": ("edit", "edit render: a pasta do EDL", lambda p: ["render", p, "-o", "{work}/out/final.mp4"]),
    "edit-pack": ("edit", "edit pack: a pasta EDIT_DIR", lambda p: ["pack", p]),
}
TODAS = {**CHAMADAS, **CHAMADAS_DE_PASTA}
# Uma chamada por tool para os casos que não dependem do subcomando
UMA_POR_TOOL = ("media-probe", "shorts-cut", "edit-render", "clone-get", "install")

SISTEMA, INICIO, OCULTA, GIT = terceiros.SISTEMA, terceiros.INICIO, terceiros.OCULTA, terceiros.GIT
CODIGO, FERRAMENTAS, DADOS = terceiros.CODIGO, terceiros.FERRAMENTAS, terceiros.DADOS
SITE_PACKAGES, VENV = terceiros.SITE_PACKAGES, terceiros.VENV

# (id, o caminho pedido, o motivo da regra única, o caminho real quando difere do pedido)
PROIBIDOS = [
    ("sistema-etc", "/etc/novo.mp4", SISTEMA, None),
    ("sistema-usr", "/usr/lib/novo.mp4", SISTEMA, None),
    ("sistema-dev", "/dev/shm/novo.mp4", SISTEMA, None),
    ("sistema-var", "/var/lib/novo.mp4", SISTEMA, None),
    ("a-propria-pasta-do-sistema", "/etc", SISTEMA, None),
    ("barra-dupla", "//etc/novo.mp4", SISTEMA, "/etc/novo.mp4"),
    ("barras-no-meio", "/etc//novo.mp4", SISTEMA, "/etc/novo.mp4"),
    ("ponto-no-meio", "/etc/./novo.mp4", SISTEMA, "/etc/novo.mp4"),
    ("ponto-no-inicio", "/./etc/novo.mp4", SISTEMA, "/etc/novo.mp4"),
    ("home-oculta", "{home}/.ssh/novo.mp4", OCULTA, None),
    ("home-oculta-funda", "{home}/.config/a/b/novo.mp4", OCULTA, None),
    ("home-oculta-com-ponto", "{home}/./.ssh/novo.mp4", OCULTA, "{home}/.ssh/novo.mp4"),
    ("inicio-automatico", "{home}/Library/LaunchAgents/novo.plist", INICIO, None),
    ("git", "{work}/.git/hooks/novo.mp4", GIT, None),
    ("dados-do-motor", "{data}/novo.mp4", DADOS, None),
    ("ferramentas-do-motor", "{tools}/novo.mp4", FERRAMENTAS, None),
    ("codigo-do-motor", "{code}/novo.mp4", CODIGO, None),
    ("site-packages", "{work}/lib/python3/site-packages/novo.mp4", SITE_PACKAGES, None),
    ("venv", "{work}/meuvenv/novo.mp4", VENV, None),
    # por um link: o que vale é o lugar onde o caminho cai
    ("link-para-ssh", "{work}/lnk_ssh/novo.mp4", OCULTA, "{home}/.ssh/novo.mp4"),
    ("link-para-o-home-e-depois-ssh", "{work}/lnk_home/.ssh/novo.mp4", OCULTA, "{home}/.ssh/novo.mp4"),
    ("link-para-etc", "{work}/lnk_etc/novo.mp4", SISTEMA, "/etc/novo.mp4"),
]
# (id, o caminho pedido, o primeiro nome do caminho que é link, o caminho real) para os links que levam a um lugar que a regra deixa
LINKS = [
    ("link-no-fim", "{work}/lnk_file.mp4", "{work}/lnk_file.mp4", "{work}/a.mp4"),
    ("link-de-pasta", "{work}/lnk_ok/novo.mp4", "{work}/lnk_ok", "{work}/out/novo.mp4"),
    ("link-de-pasta-e-pastas-novas", "{work}/lnk_ok/a/b/novo.mp4", "{work}/lnk_ok", "{work}/out/a/b/novo.mp4"),
    ("link-no-meio-da-cadeia", "{work}/out/lnk_in/novo.mp4", "{work}/out/lnk_in", "{work}/data/novo.mp4"),
    ("link-de-link", "{work}/lnk_de_lnk/novo.mp4", "{work}/lnk_de_lnk", "{work}/out/novo.mp4"),
    ("link-pendurado", "{work}/dangling/novo.mp4", "{work}/dangling", "{work}/nao-existe/novo.mp4"),
]
CICLO = "{work}/loop_a/novo.mp4"  # o caminho real de um ciclo depende da versão do Python: só o link é conferido

# (id, o caminho pedido): onde grava continua aceito
ACEITOS = [
    ("pasta-de-trabalho", "{work}/out/novo.mp4"),
    ("raiz-do-projeto", "{work}/novo.mp4"),
    ("uma-pasta-chamada-data-do-projeto", "{work}/data/novo.mp4"),
    ("pastas-novas-fundo", "{work}/out/a/b/c/novo.mp4"),
    ("barra-no-fim", "{work}/out/"),
    ("barra-dupla-no-meio", "{work}//out/novo.mp4"),
    ("ponto-no-meio", "{work}/./out/novo.mp4"),
    ("tmp", "/tmp/u22h-nao-existe/novo.mp4"),
    ("var-tmp", "/var/tmp/u22h-nao-existe/novo.mp4"),
    ("home-fora-das-pastas-ocultas", "{home}/docs/novo.mp4"),
    ("o-proprio-home", "{home}/novo.mp4"),
    ("pasta-oculta-fora-do-home", "{work}/.cache/novo.mp4"),
    ("pasta-oculta-funda-no-home", "{home}/docs/.cache/novo.mp4"),
    ("nome-que-so-parece-git", "{work}/out/novo.gitignore"),
    ("nome-que-so-contem-git", "{work}/dados.git/novo.mp4"),
    ("nome-que-so-parece-venv", "{work}/venv/novo.mp4"),
    ("raiz-nova-que-nao-existe", "/abs/novo.mp4"),
    ("caixa-conta-no-linux", "/Etc/novo.mp4"),
    ("com-NUL", "{work}/out/a\x00b.mp4"),  # nenhum arquivo tem NUL no nome: o CLI falha sozinho, como sempre
]


def ids(tabela, indice=0):
    return [linha[indice] for linha in tabela]


# ============================================================================================ o que passa a ser RECUSADO

@pytest.mark.parametrize("chamada", list(TODAS))
@pytest.mark.parametrize("lugar_", PROIBIDOS, ids=ids(PROIBIDOS))
def test_every_tool_refuses_to_write_at_a_place_the_one_rule_refuses(mundo, chamada, lugar_):
    """HOJE todas essas chamadas passam ao CLI. Cada uma é recusada com o motivo da regra única, o caminho como veio e, se difere, o caminho real."""
    _, caminho, motivo, real_ = lugar_
    ferramenta, quem, monta = TODAS[chamada]
    p = troca(caminho, mundo)
    esperado = (RECUSA, lugar(quem, p, motivo, troca(real_, mundo) if real_ else None))
    assert chama(mundo, ferramenta, monta(caminho)) == esperado


@pytest.mark.parametrize("chamada", list(TODAS))
@pytest.mark.parametrize("link", LINKS, ids=ids(LINKS))
def test_every_tool_refuses_to_write_through_a_link_even_to_a_harmless_place(mundo, chamada, link):
    """O link pode estar no fim, numa pasta, no meio da cadeia, ser link de link ou estar pendurado; a recusa diz qual nome é o link."""
    _, caminho, primeiro_link, real_ = link
    ferramenta, quem, monta = TODAS[chamada]
    esperado = (RECUSA, elo(quem, troca(caminho, mundo), troca(primeiro_link, mundo), troca(real_, mundo)))
    assert chama(mundo, ferramenta, monta(caminho)) == esperado


@pytest.mark.parametrize("chamada", UMA_POR_TOOL)
def test_a_link_cycle_is_refused_as_a_link(mundo, chamada):
    ferramenta, quem, monta = CHAMADAS[chamada]
    status, texto = chama(mundo, ferramenta, monta(CICLO))
    p, link = troca(CICLO, mundo), troca("{work}/loop_a", mundo)
    assert status == RECUSA and texto.startswith(f"{quem} {p!r}: {link!r} é um link simbólico; {SEM_LINK}"), texto


@pytest.mark.parametrize("chamada", list(TODAS))
def test_a_link_to_a_place_the_rule_refuses_says_the_place_not_the_link(mundo, chamada):
    """Os dois valem para `{work}/lnk_ssh/novo.mp4`; a recusa diz o lugar (o mais grave e o que o agente precisa saber) e o caminho real."""
    ferramenta, quem, monta = TODAS[chamada]
    status, texto = chama(mundo, ferramenta, monta("{work}/lnk_ssh/novo.mp4"))
    assert status == RECUSA and "o MCP não grava em pasta oculta do home" in texto and "link simbólico" not in texto


# ============================================================================================ o que SEGUE aceito

@pytest.mark.parametrize("chamada", list(TODAS))
@pytest.mark.parametrize("aceito", ACEITOS, ids=ids(ACEITOS))
def test_every_tool_still_writes_at_the_places_of_the_user(mundo, chamada, aceito):
    """Pasta de trabalho do projeto, /tmp, /var/tmp, o home fora das pastas ocultas, uma pasta `data` do projeto: nada disso muda."""
    _, caminho = aceito
    ferramenta, _, monta = TODAS[chamada]
    assert chama(mundo, ferramenta, monta(caminho)) == aceita(mundo, ferramenta, monta(caminho))


# ============================================================================================ todas as grafias da saída

GRAFIAS_DO_EDIT = [("-o", "{p}"), ("-o{p}",), ("-o={p}",), ("--output", "{p}"), ("--output={p}",), ("--o", "{p}"), ("--o={p}",), ("--ou", "{p}"),
                   ("--out", "{p}"), ("--out={p}",), ("--outp", "{p}"), ("--outpu", "{p}"), ("--outpu={p}",)]
GRAFIAS_DO_MEDIA = [("-o", "{p}"), ("--o", "{p}"), ("--ou", "{p}"), ("--out", "{p}"), ("--outp", "{p}"), ("--output", "{p}"), ("-o{p}",), ("-o={p}",),
                    ("--out={p}",), ("--o={p}",), ("--output={p}",)]
GRAFIAS_DO_SHORTS = [("-o", "{p}"), ("--out", "{p}")]  # as outras grafias o shorts já recusava, com as palavras de sempre (a tabela de test_mcp_policy)
SAIDAS_PROIBIDAS = [("/etc/novo.mp4", SISTEMA, None), ("{work}/lnk_ssh/novo.mp4", OCULTA, "{home}/.ssh/novo.mp4"),
                    ("{work}/lnk_ok/novo.mp4", None, None)]


def grafia(modelo, p):
    return [t.replace("{p}", p) for t in modelo]


def esperado_da_saida(w, quem, caminho, motivo, real_):
    p = troca(caminho, w)
    if motivo is None:
        return elo(quem, p, troca("{work}/lnk_ok", w), troca("{work}/out/novo.mp4", w))
    return lugar(quem, p, motivo, troca(real_, w) if real_ else None)


@pytest.mark.parametrize("saida", SAIDAS_PROIBIDAS, ids=["etc", "link-para-ssh", "link-inofensivo"])
@pytest.mark.parametrize("modelo", GRAFIAS_DO_EDIT, ids=[" ".join(m) for m in GRAFIAS_DO_EDIT])
@pytest.mark.parametrize("sub", ["render", "transcribe", "verify", "grade"])
def test_edit_refuses_every_spelling_of_the_output_option(mundo, sub, modelo, saida):
    """`-o/etc/x` (colado), `-o=`, `--output=`, `--o`, `--ou`, `--out`, `--outp`... o upstream (argparse) lê todas; a recusa também."""
    caminho, motivo, real_ = saida
    entrada = {"render": ["render", "{work}/edl.json"], "transcribe": ["transcribe", FONTE], "verify": ["verify", FONTE, "1", "2"],
               "grade": ["grade", FONTE]}[sub]
    argv = [*entrada, *grafia(modelo, caminho)]
    assert chama(mundo, "edit", argv) == (RECUSA, esperado_da_saida(mundo, f"edit {sub}: saída", caminho, motivo, real_))


@pytest.mark.parametrize("saida", SAIDAS_PROIBIDAS, ids=["etc", "link-para-ssh", "link-inofensivo"])
@pytest.mark.parametrize("modelo", GRAFIAS_DO_MEDIA, ids=[" ".join(m) for m in GRAFIAS_DO_MEDIA])
def test_media_refuses_every_spelling_of_the_output_option(mundo, modelo, saida):
    """Só o `-o X` separado grava (o parse do `media` não lê as outras); a política confere todas as grafias, como sempre conferiu."""
    caminho, motivo, real_ = saida
    argv = ["probe", FONTE, *grafia(modelo, caminho)]
    assert chama(mundo, "media", argv) == (RECUSA, esperado_da_saida(mundo, "media: saída", caminho, motivo, real_))


@pytest.mark.parametrize("saida", SAIDAS_PROIBIDAS, ids=["etc", "link-para-ssh", "link-inofensivo"])
@pytest.mark.parametrize("modelo", GRAFIAS_DO_SHORTS, ids=[" ".join(m) for m in GRAFIAS_DO_SHORTS])
@pytest.mark.parametrize("sub", ["cut", "plan", "run", "inspect"])
def test_shorts_refuses_the_two_spellings_of_the_output_option_it_reads(mundo, sub, modelo, saida):
    caminho, motivo, real_ = saida
    entrada = {"cut": ["cut", FONTE, "{work}/plan.json"], "plan": ["plan", FONTE, "--transcript", "{work}/words.json"],
               "run": ["run", FONTE, "--transcript", "{work}/words.json"], "inspect": ["inspect", FONTE]}[sub]
    argv = [*entrada, *grafia(modelo, caminho)]
    assert chama(mundo, "shorts", argv) == (RECUSA, esperado_da_saida(mundo, "shorts: saída", caminho, motivo, real_))


@pytest.mark.parametrize("modelo", GRAFIAS_DO_EDIT, ids=[" ".join(m) for m in GRAFIAS_DO_EDIT])
@pytest.mark.parametrize("sub", ["render", "transcribe", "verify", "grade"])
def test_edit_still_runs_every_spelling_of_the_output_option_at_a_place_of_the_user(mundo, sub, modelo):
    entrada = {"render": ["render", "{work}/edl.json"], "transcribe": ["transcribe", FONTE], "verify": ["verify", FONTE, "1", "2"],
               "grade": ["grade", FONTE]}[sub]
    argv = [*entrada, *grafia(modelo, "{work}/out/novo.mp4")]
    assert chama(mundo, "edit", argv) == aceita(mundo, "edit", argv)


# ============================================================================================ mais de uma saída, e a ordem das recusas

def test_edit_refuses_when_any_of_several_outputs_is_a_refused_place(mundo):
    """O upstream fica com a última, quem confere confere todas: a que passa não salva a que não passa, em qualquer ordem."""
    bom, ruim = "{work}/out/a.mp4", "/etc/novo.mp4"
    quem = "edit render: saída"
    para_ruim = (RECUSA, lugar(quem, ruim, SISTEMA))
    assert chama(mundo, "edit", ["render", "{work}/edl.json", "-o", bom, "--output", ruim]) == para_ruim
    assert chama(mundo, "edit", ["render", "{work}/edl.json", "--output", ruim, "-o", bom]) == para_ruim
    assert chama(mundo, "edit", ["render", "{work}/edl.json", "-o", bom, "--output", bom]) == aceita(
        mundo, "edit", ["render", "{work}/edl.json", "-o", bom, "--output", bom])


# O texto de cada recusa que a tool já tinha, como era (a tabela de test_mcp_policy os guarda; aqui o que importa é a ORDEM: a regra nova vem depois)
T_GRADE = ("pelo MCP o --filter só aceita filtros de cor (eq, curves, colorbalance, hue, lut, lutrgb, lutyuv, colorchannelmixer, vibrance), sem opção "
           "que leia ou grave arquivo, sem barra invertida nem aspas; uma cadeia livre: rode `simplicio-video edit grade --filter` no terminal; o MCP não faz isso")
T_EDL = ("edit render: o EDL precisa ser um caminho absoluto, sem `..` (o render grava os intermediários na pasta dele, e o MCP não sabe de que "
         "pasta o servidor foi iniciado)")
T_PACK = "edit pack: a pasta EDIT_DIR precisa ser um caminho absoluto, sem `..` (o pack grava takes_packed.md nela)"
T_RELATIVO_MEDIA = ("media: -o/--out precisa ser um caminho absoluto, sem `..` (um relativo cairia na pasta onde o servidor MCP foi iniciado)")
T_ENGOLIDO = ("media: -o não é uma opção própria com um valor: foi engolido por outra opção, falta o valor, ou está repetido; ponha -o com um "
              "caminho absoluto")
T_SHORTS_SEM_SAIDA = ("shorts plan: informe -o/--out com caminho absoluto (sem padrão no MCP: o plano e os cortes iriam para shorts/, na pasta "
                      "onde o servidor foi iniciado)")
T_HYPIT_GET = ("`get` não está na lista do MCP (comando desconhecido ou não permitido, ou um caminho que não é absoluto): rode `simplicio-video "
               "clone get` no terminal; o MCP não faz isso")
T_INSTALL_REMOVER = "remover as skills dos hosts: rode `simplicio-video install --uninstall` no terminal; o MCP não faz isso"
T_INSTALL_RELATIVO = "install: --target precisa ser um caminho absoluto"
T_INSTALL_SEM_ALVO = ("install: informe --global (home) ou --target <caminho absoluto> do projeto; sem isso a pasta seria a de onde o servidor "
                      "MCP foi iniciado")


@pytest.mark.parametrize("ferramenta,argv,texto", [
    ("edit", ["grade", FONTE, "-o", "/etc/novo.mp4", "--filter", "movie=/etc/passwd"], T_GRADE),
    ("edit", ["render", "rel/edl.json", "-o", "/etc/novo.mp4"], T_EDL),
    ("edit", ["render", "/etc/edl.json", "-o", "rel/novo.mp4"], "edit render: -o/--out/--output precisa ser um caminho absoluto, sem `..` "
                                                                  "(um relativo cairia na pasta onde o servidor MCP foi iniciado)"),
    ("edit", ["pack", "rel/edit"], T_PACK),
    ("edit", ["transcribe", FONTE], "edit transcribe: -o <caminho absoluto> é obrigatório no MCP"),
    ("media", ["probe", FONTE, "-o", "/etc/novo.mp4", "-o", "rel.json"], T_RELATIVO_MEDIA),
    ("media", ["probe", FONTE, "-o", "/etc/novo.mp4", "-o", "{work}/out/b.json"], T_ENGOLIDO),
    ("media", ["probe", FONTE, "--fit", "-o", "/etc/novo.mp4"], T_ENGOLIDO),
    ("shorts", ["plan", FONTE, "--transcript", "{work}/words.json", "--o", "/etc/novo.mp4"], T_SHORTS_SEM_SAIDA),
    ("clone", ["get", "b1", "--output", "n", "--to", "/etc/novo.mp4", "--to=/etc/outro.mp4"], T_HYPIT_GET),
    ("clone", ["get", "b1", "--output", "n", "--to=/etc/novo.mp4"], T_HYPIT_GET),
    ("install", ["--target", "/etc/novo.mp4", "--uninstall"], T_INSTALL_REMOVER),
    ("install", ["--target", "rel/proj"], T_INSTALL_RELATIVO),
    ("install", ["--host", "claude"], T_INSTALL_SEM_ALVO),
], ids=["edit-filtro", "edit-edl-relativo", "edit-saida-relativa", "edit-pack-relativo", "edit-sem-saida", "media-relativa", "media-repetida",
        "media-engolida", "shorts-sem-saida", "clone-to-colado", "clone-to-colado-so", "install-remover", "install-relativo", "install-sem-alvo"])
def test_a_call_a_tool_already_refused_keeps_its_words_even_when_it_also_has_a_refused_place(mundo, ferramenta, argv, texto):
    """A regra nova vem DEPOIS de toda recusa de antes: quem já era recusado continua com o mesmo texto, byte a byte."""
    status, obtido = chama(mundo, ferramenta, argv)
    assert (status, obtido) == (RECUSA, texto)


# ============================================================================================ o que só LÊ, e os modos que não gravam, seguem como estavam

LEITURAS = [
    ("clone", ["media", "probe", "/etc/novo.mp4"]),  # a fonte (posicional) do Hypit é entrada
    ("clone", ["media", "cut", FONTE, "--ranges", "/etc/novo.mp4", "--to", "{work}/out/x.mp4"]),
    ("clone", ["media", "tile", FONTE, "--transcript", "{home}/.ssh/novo.json", "--to", "{work}/out/x.png"]),
    ("clone", ["media", "probe", "{work}/lnk_file.mp4"]),  # entrada por um link: lê o destino
    ("clone", ["media", "cut", "{work}/lnk_file.mp4", "--to", "{work}/out/x.mp4"]),
    ("clone", ["media", "cut", FONTE, "--start", "0", "--end", "1", "--to", "/etc/x.mp4", "--help"]),  # `--help` não grava
    ("media", ["probe", "{work}/lnk_file.mp4"]),
    ("media", ["probe", "/etc/novo.mp4"]),
    ("media", ["probe", FONTE, "-o", "/etc/novo.mp4", "--help"]),
    ("media", ["probe", FONTE, "-o", "{home}/.ssh/novo.json", "-h"]),
    ("shorts", ["plan", "{work}/lnk_file.mp4", "--transcript", "{work}/words.json", "-o", "{work}/out/p.json"]),
    ("shorts", ["plan", FONTE, "--transcript", "/etc/novo.json", "-o", "{work}/out/p.json"]),
    ("shorts", ["cut", FONTE, "/etc/plan.json", "-o", "{work}/out"]),
    ("shorts", ["--help", "-o", "/etc/novo"]),  # o primeiro é a ajuda: o `shorts` imprime e sai
    ("shorts", ["help"]),
    ("edit", ["render", "{work}/edl.json", "-o", "/etc/novo.mp4", "--help"]),
    ("edit", ["render", "--help"]),
    ("edit", ["grade", "--analyze", "/etc/novo.mp4", "-o", "{home}/.ssh/x.mp4"]),  # --analyze só lê
    ("edit", ["grade", "--list-presets", "-o", "/etc/novo.mp4"]),
    ("edit", ["grade", "--print-preset", "subtle", "-o", "/etc/novo.mp4"]),
    ("edit", ["transcribe", "{work}/lnk_file.mp4", "-o", "{work}/out/t.json"]),
    ("edit", ["verify", "/etc/novo.mp4", "1", "2", "-o", "{work}/out/v.png"]),
    ("edit", ["pack", "-h"]),
    ("edit", ["setup"]),
    ("install", ["--check", "--target", "/etc/novo"]),
    ("install", ["--dry-run", "--target", "{home}/.ssh"]),
    ("install", ["--verify", "--target", "{work}/lnk_ok"]),
    ("install", ["--check", "--target={work}/out/../data"]),
    ("install", ["--help"]),
    ("install", ["--global"]),
    ("install", ["--host", "claude", "--global", "--check"]),
]


@pytest.mark.parametrize("ferramenta,argv", LEITURAS, ids=[f"{f}-{i:02d}" for i, (f, _) in enumerate(LEITURAS)])
def test_what_the_cli_only_reads_and_the_modes_that_write_nothing_are_left_as_they_were(mundo, ferramenta, argv):
    resultado = chama(mundo, ferramenta, argv)
    assert resultado[0] == ACEITA, resultado


# ============================================================================================ o que o CLI lê e a política não via

def test_shorts_does_not_take_help_after_the_subcommand_as_a_reason_to_skip_the_output_rule(mundo):
    """Como sempre foi: `shorts cut ... -h` sem `-o` e com `-o` relativo já eram recusados; um `-o` em lugar recusado também é, com `--help`."""
    argv = ["cut", FONTE, "{work}/plan.json", "-o", "/etc/novo", "--help"]
    assert chama(mundo, "shorts", argv) == (RECUSA, lugar("shorts: saída", "/etc/novo", SISTEMA))


@pytest.mark.parametrize("ferramenta,argv_de", [
    ("media", lambda p: ["probe", FONTE, "--", "x", "-o", p]),
    ("media", lambda p: ["audio", FONTE, "--", "x", "-o", p]),
    ("shorts", lambda p: ["inspect", FONTE, "--", "x", "-o", p]),
    ("shorts", lambda p: ["cut", FONTE, "{work}/plan.json", "--", "x", "-o", p]),
    ("shorts", lambda p: ["plan", FONTE, "--transcript", "{work}/words.json", "--", "x", "--out", p]),
], ids=["media-probe", "media-audio", "shorts-inspect", "shorts-cut", "shorts-plan-out"])
@pytest.mark.parametrize("saida", [("/etc/novo.mp4", SISTEMA), ("{home}/.ssh/novo.mp4", OCULTA)], ids=["etc", "ssh"])
def test_an_output_after_a_dashdash_and_the_word_it_swallows_is_still_checked(mundo, ferramenta, argv_de, saida):
    """BYPASS achado na caça (main e U22a): `--` engole a palavra seguinte, e o `-o` depois dela é uma opção de verdade para o parse do CLI
    (media.parse_argv, shorts.parse_argv) mas não para `output_values`, que para no `--`. Ia ao CLI sem conferir nada, nem o caminho absoluto."""
    caminho, motivo = saida
    quem = "media: saída" if ferramenta == "media" else "shorts: saída"
    assert chama(mundo, ferramenta, argv_de(caminho)) == (RECUSA, lugar(quem, troca(caminho, mundo), motivo))


@pytest.mark.parametrize("ferramenta,argv_de", [
    ("media", lambda p: ["probe", FONTE, "--", "x", "-o", p]),
    ("shorts", lambda p: ["inspect", FONTE, "--", "x", "-o", p]),
], ids=["media", "shorts"])
def test_a_relative_output_after_a_dashdash_is_refused_as_any_relative_path_of_the_mcp(mundo, ferramenta, argv_de):
    """Era escrito na pasta onde o servidor foi iniciado: o relativo cai na regra nova (que repete o que a tool já exigia de todo caminho)."""
    quem = "media: saída" if ferramenta == "media" else "shorts: saída"
    texto = f"{quem} 'rel/novo.json': precisa ser um caminho absoluto, sem `..` (o MCP não grava em caminho relativo nem com `..`)"
    assert chama(mundo, ferramenta, argv_de("rel/novo.json")) == (RECUSA, texto)


@pytest.mark.parametrize("saida", [("/etc/novo.mp4", SISTEMA), ("{home}/.ssh/novo.mp4", OCULTA), ("rel/novo.json", None)], ids=["etc", "ssh", "relativo"])
def test_media_takes_help_only_before_the_first_dashdash_as_the_cli_does(mundo, saida):
    """BYPASS achado na caça: `-h` DEPOIS do `--` é palavra para o `media` (run_media só procura antes), e rodava; a política o tomava por ajuda
    e deixava passar qualquer `-o`, inclusive o relativo."""
    caminho, motivo = saida
    argv = ["probe", FONTE, "-o", caminho, "--", "-h"]
    status, texto = chama(mundo, "media", argv)
    assert status == RECUSA
    if motivo is None:
        assert texto == T_RELATIVO_MEDIA
    else:
        assert texto == lugar("media: saída", troca(caminho, mundo), motivo)
    # antes do `--` é ajuda de verdade (o CLI imprime e sai): segue como estava
    assert chama(mundo, "media", ["probe", FONTE, "-o", caminho, "-h", "--", "x"])[0] == ACEITA
    assert chama(mundo, "media", ["probe", FONTE, "--help", "-o", caminho])[0] == ACEITA


# ============================================================================================ install --target

def esperado_install(texto: str):
    return RECUSA, texto


@pytest.mark.parametrize("forma", [lambda p: ["--target", p], lambda p: [f"--target={p}"], lambda p: ["--host", "claude", "--target", p],
                                   lambda p: ["--global", "--target", p], lambda p: ["--dry-run=x", "--target", p]],
                         ids=["separado", "colado", "com-host", "com-global", "outra-opcao-antes"])
def test_install_refuses_the_target_in_both_forms_and_next_to_other_options(mundo, forma):
    """O `--target` do CLI (argparse, sem abreviação) vale nas duas formas; com `--global` ele nem é usado, mas o que a tool conferia segue conferindo."""
    argv = forma("/etc/novo")
    status, texto = chama(mundo, "install", argv)
    assert (status, texto) == (RECUSA, lugar("install: a pasta de --target", "/etc/novo", SISTEMA))


def test_install_takes_the_last_target_as_the_cli_does(mundo):
    ruim, bom = "/etc/novo", "{work}/out"
    assert chama(mundo, "install", ["--target", ruim, "--target", bom]) == aceita(mundo, "install", ["--target", ruim, "--target", bom])
    assert chama(mundo, "install", ["--target", bom, "--target", ruim]) == (RECUSA, lugar("install: a pasta de --target", ruim, SISTEMA))
    assert chama(mundo, "install", ["--target", bom, f"--target={ruim}"]) == (RECUSA, lugar("install: a pasta de --target", ruim, SISTEMA))


def test_install_refuses_dotdot_in_the_target_as_every_other_path_of_the_mcp(mundo):
    """Era o único caminho do MCP que só exigia ser absoluto: `{work}/../etc` e também `{work}/out/../data`, que cairia num lugar sem problema."""
    quem = "install: a pasta de --target"
    nota = "precisa ser um caminho absoluto, sem `..` (o MCP não grava em caminho relativo nem com `..`)"
    for caminho in ("{work}/../etc", "{work}/out/../data", "{work}/lnk_ok/../out", "/etc/../tmp/x"):
        p = troca(caminho, mundo)
        assert chama(mundo, "install", ["--target", caminho]) == (RECUSA, f"{quem} {p!r}: {nota}"), caminho


# ============================================================================================ Hypit

def test_hypit_get_and_media_refuse_only_the_place_it_writes_at_and_not_what_it_reads(mundo):
    ruim = "/etc/novo.mp4"
    saida = (RECUSA, lugar("clone media cut: o destino --to", ruim, SISTEMA))
    assert chama(mundo, "clone", ["media", "cut", ruim, "--to", ruim]) == saida  # a fonte lida em /etc passa; o destino não
    assert chama(mundo, "clone", ["media", "cut", ruim, "--to", "{work}/out/x.mp4"]) == aceita(mundo, "clone", ["media", "cut", ruim, "--to", "{work}/out/x.mp4"])
    for verbo in ("frames", "tile", "tiles", "boundaries"):
        quem = f"clone media {verbo}: o destino --to"
        assert chama(mundo, "clone", ["media", verbo, FONTE, "--to", ruim]) == (RECUSA, lugar(quem, ruim, SISTEMA)), verbo
    assert chama(mundo, "clone", ["media", "cut", FONTE, "--to", "{work}/out/x.mp4", "--json", "--no-color"])[0] == ACEITA


def test_hypit_other_commands_have_no_place_to_write_and_are_untouched(mundo):
    for argv in (["status", "b1", "--json"], ["inspect", "b1", "--output", "n"], ["logs", "b1", "--lines", "5"], ["paths"], ["plan", "/etc/x.md"],
                 ["check", "{home}/.ssh/x.md"], ["--help"]):
        assert chama(mundo, "clone", argv)[0] == ACEITA, argv


# ============================================================================================ NUL e o texto das recusas, palavra por palavra

def test_a_path_with_a_nul_is_left_to_the_cli_as_always(mundo):
    for chamada in UMA_POR_TOOL:
        ferramenta, _, monta = CHAMADAS[chamada]
        argv = monta("{work}/out/a\x00b.mp4")
        assert chama(mundo, ferramenta, argv) == aceita(mundo, ferramenta, argv), chamada


def test_the_words_of_each_new_refusal(mundo):
    """O texto exato (o que o agente lê): `lugar` e `elo` acima só montam estas frases, e este teste as escreve por extenso."""
    w = mundo
    p = lambda t: troca(t, w)  # noqa: E731
    assert chama(w, "media", ["probe", FONTE, "-o", "/etc/novo.mp4"]) == (
        RECUSA, "media: saída '/etc/novo.mp4': o MCP não grava em pasta do sistema; escolha uma pasta sua (a do projeto, /tmp ou o home fora das "
                "pastas ocultas)")
    assert chama(w, "edit", ["render", "{work}/edl.json", "-o//etc/novo.mp4"]) == (
        RECUSA, "edit render: saída '//etc/novo.mp4': o MCP não grava em pasta do sistema (o caminho real é '/etc/novo.mp4'); escolha uma pasta sua "
                "(a do projeto, /tmp ou o home fora das pastas ocultas)")
    assert chama(w, "shorts", ["cut", FONTE, "{work}/plan.json", "-o", "{home}/.ssh/x"]) == (
        RECUSA, p("shorts: saída '{home}/.ssh/x': o MCP não grava em pasta oculta do home (.ssh, .config, .claude...); escolha uma pasta sua (a do "
                  "projeto, /tmp ou o home fora das pastas ocultas)"))
    assert chama(w, "clone", ["get", "b1", "--output", "n", "--to", "{work}/.git/x"]) == (
        RECUSA, p("clone get: o destino --to '{work}/.git/x': o MCP não grava dentro de uma pasta .git; escolha uma pasta sua (a do projeto, /tmp "
                  "ou o home fora das pastas ocultas)"))
    assert chama(w, "install", ["--target", "{home}/Library/LaunchAgents"]) == (
        RECUSA, p("install: a pasta de --target '{home}/Library/LaunchAgents': o MCP não grava em pasta de início automático (LaunchAgents, "
                  "LaunchDaemons, Startup); escolha uma pasta sua (a do projeto, /tmp ou o home fora das pastas ocultas)"))
    assert chama(w, "edit", ["pack", "{data}"]) == (
        RECUSA, p("edit pack: a pasta EDIT_DIR '{data}': o MCP não grava dentro da pasta de dados do motor (jobs, tools, openmontage-data); escolha "
                  "uma pasta sua (a do projeto, /tmp ou o home fora das pastas ocultas)"))
    assert chama(w, "media", ["probe", FONTE, "-o", "{work}/lnk_file.mp4"]) == (
        RECUSA, p("media: saída '{work}/lnk_file.mp4': é um link simbólico; o MCP só grava em caminho real, sem link em nenhuma pasta do caminho "
                  "(o caminho real seria '{work}/a.mp4')"))
    assert chama(w, "media", ["probe", FONTE, "-o", "{work}/lnk_ok/x.json"]) == (
        RECUSA, p("media: saída '{work}/lnk_ok/x.json': '{work}/lnk_ok' é um link simbólico; o MCP só grava em caminho real, sem link em nenhuma "
                  "pasta do caminho (o caminho real seria '{work}/out/x.json')"))
    assert chama(w, "edit", ["render", "{work}/lnk_ssh/edl.json", "-o", "{work}/out/f.mp4"]) == (
        RECUSA, p("edit render: a pasta do EDL '{work}/lnk_ssh/edl.json': o MCP não grava em pasta oculta do home (.ssh, .config, .claude...) "
                  "(o caminho real é '{home}/.ssh/edl.json'); escolha uma pasta sua (a do projeto, /tmp ou o home fora das pastas ocultas)"))
    assert chama(w, "install", ["--target", "{work}/out/../data"]) == (
        RECUSA, p("install: a pasta de --target '{work}/out/../data': precisa ser um caminho absoluto, sem `..` (o MCP não grava em caminho "
                  "relativo nem com `..`)"))
