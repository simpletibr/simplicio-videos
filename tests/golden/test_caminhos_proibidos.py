"""G0 (golden, caracterização): onde cada trilha recusa gravar (as 5 versões de "lugar proibido").

As cinco regras fazem a mesma pergunta ("o MCP/terminal pode gravar em `real`?") com respostas diferentes. Este arquivo escreve a
tabela caminho x módulo COMO ELA É HOJE. Nada aqui é decisão de projeto: cada linha onde as colunas discordam é uma divergência
herdada, marcada "U22 decide". A correção U22a só pode mudar linhas desta tabela, e o diff dela é o que o dono aprova.

Privados exercitados por import direto (caracterização; não há API pública equivalente):
  matchcut._lugar_proibido, instagram._lugar_proibido, montage._lugar_proibido, video_to_skill._lugar_proibido,
  voicestudio._forbidden_place; constantes matchcut/instagram/video_to_skill._RAIZES_POSIX/_RAIZES_WINDOWS/_INICIO_AUTOMATICO,
  montage._SISTEMA_POSIX/_SISTEMA_WINDOWS/_INICIO_AUTOMATICO, voicestudio._ROOTS_POSIX/_ROOTS_WINDOWS, matchcut/instagram._STARTUP_DO_APPDATA.

Os chamadores passam o caminho real (links resolvidos); aqui `real()` faz o mesmo. Congelado no Linux: em macOS/Windows a regra de
maiúsculas (CASE_INSENSITIVE) e as raízes dos temporários mudam a tabela."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from simplicio_video import instagram, matchcut, montage, video_to_skill, voicestudio

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="tabela congelada no Linux (CASE_INSENSITIVE falso, /tmp fora de /var)")

MODULOS = ("matchcut", "instagram", "montage", "video_to_skill", "voicestudio")
L, S, O, I, G = "livre", "sistema", "oculta", "inicio", "git"  # noqa: E741

# A mensagem exata de cada módulo vira um rótulo curto. Uma mensagem fora desta tabela quebra o teste (KeyError): é o congelamento.
MENSAGEM = {
    "": L,
    "em pasta do sistema": S,
    "em pasta oculta do home (.ssh, .config, .claude...)": O,
    "em pasta de início automático (LaunchAgents, LaunchDaemons, Startup)": I,
    "dentro de uma pasta .git": G,
    "dentro do checkout do match-cut": "checkout",
    "dentro do checkout do instagram-agent-skill": "checkout",
    "dentro do checkout do video-to-skill": "checkout",
    "dentro do checkout do OpenMontage": "checkout",
    "dentro da pasta de ferramentas do motor": "ferramentas",
    "dentro da pasta de dados do match-cut (o venv)": "dados",
    "dentro da pasta de dados do motor (jobs, tools, openmontage-data)": "dados",
    "dentro do código do motor": "motor",
    "dentro de site-packages (pacotes de um venv)": "site-packages",
    "dentro de um venv (pyvenv.cfg)": "venv",
}


def real(p) -> Path:
    return Path(os.path.realpath(p))


def veredito(modulo: str, caminho: Path) -> str:
    if modulo == "voicestudio":
        r = voicestudio._forbidden_place(caminho)
        if r is None:
            return L
        return S if r.startswith("pasta do sistema (") else O if r.startswith("pasta oculta do home (") else r
    return MENSAGEM[getattr(sys.modules[f"simplicio_video.{modulo}"], "_lugar_proibido")(caminho)]


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    nomes = ("home", "work", "tools", "data", "programdata", "appdata")
    w = SimpleNamespace(**{n: real(tmp_path / n) for n in nomes})
    for n in nomes:
        getattr(w, n).mkdir()
    monkeypatch.setenv("HOME", str(w.home))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(w.tools))
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(w.data))
    monkeypatch.setenv("PROGRAMDATA", str(w.programdata))  # uma das 4 raízes do Windows, apontada para uma pasta daqui
    monkeypatch.setenv("APPDATA", str(w.appdata))
    for var in ("USERPROFILE", "SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "INSTAGRAM_DIR", "SIMPLICIO_INSTAGRAM_DIR", "MATCHCUT_DIR",
                "SIMPLICIO_MATCHCUT_DIR", "MATCHCUT_DATA_DIR", "VIDEO_TO_SKILL_DIR", "SIMPLICIO_VIDEO_TO_SKILL_DIR", "OPENMONTAGE_DIR",
                "SIMPLICIO_OPENMONTAGE_DIR", "OPENMONTAGE_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    return w


def sub(w, caminho: str) -> Path:
    return real(caminho.format(home=w.home, work=w.work, tools=w.tools, data=w.data, programdata=w.programdata, appdata=w.appdata))


# (caminho, veredito de matchcut, instagram, montage, video_to_skill, voicestudio)
UNANIMES = [
    ("/etc/passwd", *(S,) * 5), ("/usr/local/bin/x", *(S,) * 5), ("/dev/null", *(S,) * 5), ("/proc/1/x", *(S,) * 5),
    ("/sys/x", *(S,) * 5), ("/boot/x", *(S,) * 5), ("/run/x", *(S,) * 5), ("/System/x", *(S,) * 5), ("/Library/x", *(S,) * 5),
    ("/private/etc/x", *(S,) * 5), ("{programdata}/x", *(S,) * 5),
    ("{home}/.ssh/authorized_keys", *(O,) * 5), ("{home}/.config/x", *(O,) * 5), ("{home}/.git/x", *(O,) * 5),
    ("{home}", *(L,) * 5), ("{home}/docs/x.mp4", *(L,) * 5), ("{work}/clip.mp4", *(L,) * 5), ("/tmp/x", *(L,) * 5),
    ("/var/tmp/x", *(L,) * 5),
]

DIVERGENTES = [
    # U22 decide: voicestudio tem 15 raízes (sem /opt /srv /snap /Applications /var/lib /var/log /var/spool /var/run /var/db); as outras 4 têm 25.
    ("/opt/x", S, S, S, S, L), ("/srv/x", S, S, S, S, L), ("/snap/x", S, S, S, S, L), ("/Applications/x", S, S, S, S, L),
    ("/var/lib/x", S, S, S, S, L), ("/var/log/x", S, S, S, S, L), ("/var/spool/x", S, S, S, S, L), ("/var/db/x", S, S, S, S, L),
    # U22 decide: só o montage recusa /var inteiro (exceto /var/tmp, que as cinco deixam).
    ("/var/cache/x", L, L, S, L, L), ("/var/x", L, L, S, L, L),
    # U22 decide: voicestudio não conhece as pastas de início automático do home (LaunchAgents, LaunchDaemons, Startup do Windows).
    ("{home}/Library/LaunchAgents/x.plist", I, I, I, I, L), ("{home}/Library/LaunchDaemons/x.plist", I, I, I, I, L),
    ("{home}/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/x.bat", I, I, I, I, L),
    # U22 decide: o Startup achado por $APPDATA (fora do home) só existe em matchcut e instagram (_STARTUP_DO_APPDATA).
    ("{appdata}/Microsoft/Windows/Start Menu/Programs/Startup/x.bat", I, I, L, L, L),
    # U22 decide: .git fora de pasta oculta: voicestudio não olha.
    ("{work}/.git/hooks/pre-commit", G, G, G, G, L), ("{home}/proj/.git/config", G, G, G, G, L),
]


@pytest.mark.parametrize("linha", UNANIMES + DIVERGENTES, ids=lambda x: x[0])
def test_the_table_of_paths_by_module_is_the_one_of_today(mundo, linha):
    caminho, *esperado = linha
    p = sub(mundo, caminho)
    assert dict(zip(MODULOS, (veredito(m, p) for m in MODULOS))) == dict(zip(MODULOS, esperado)), caminho


def test_every_unanimous_row_agrees_and_every_divergent_row_does_not():
    """A trava da própria tabela: uma linha movida de grupo sem querer não passa."""
    assert all(len(set(r[1:])) == 1 for r in UNANIMES)
    assert all(len(set(r[1:])) > 1 for r in DIVERGENTES)


def test_voicestudio_messages_name_the_folder_that_matched(mundo):
    assert voicestudio._forbidden_place(sub(mundo, "/etc/passwd")) == "pasta do sistema (/etc)"
    assert voicestudio._forbidden_place(sub(mundo, "{home}/.ssh/authorized_keys")) == f"pasta oculta do home ({mundo.home}/.ssh)"
    assert voicestudio._forbidden_place(sub(mundo, "{home}/docs/x.mp4")) is None  # U22 decide: o contrato é str | None; os outros 4 devolvem "" ou o motivo


# ------------------------------------------------------------------------------------- o que cada módulo protege além do sistema

def test_matchcut_protects_its_checkout_the_tools_folder_and_its_venv_but_not_the_engine_data_root(mundo):
    v = lambda c: veredito("matchcut", sub(mundo, c))  # noqa: E731
    assert v("{tools}/matchcut/x") == "checkout"
    assert v("{tools}/instagram/x") == "ferramentas"
    assert v("{data}/matchcut-data/venv/bin/python") == "dados"
    assert v("{data}/x") == L  # U22 decide: o montage recusa a raiz de dados inteira; o matchcut só a própria subpasta


def test_instagram_and_video_to_skill_protect_only_their_checkout_and_the_tools_folder(mundo):
    for modulo in ("instagram", "video_to_skill"):  # o checkout de cada um é {tools}/<nome em tools.TOOLS>
        v = lambda c, m=modulo: veredito(m, sub(mundo, c))  # noqa: E731
        assert v("{tools}/" + modulo + "/x") == "checkout", modulo
        assert v("{tools}/matchcut/x") == "ferramentas", modulo
        assert v("{data}/x") == L, modulo  # U22 decide: nenhum dos dois protege a pasta de dados


def test_montage_adds_the_engine_own_places_that_the_others_do_not_check(mundo):
    v = lambda c: veredito("montage", sub(mundo, c))  # noqa: E731
    assert veredito("montage", real(Path(montage.__file__).parent / "x.py")) == "motor"
    assert v("{tools}/openmontage/x") == "checkout"
    assert v("{tools}/matchcut/x") == "dados"
    assert v("{data}/x") == "dados"
    assert v("{data}/openmontage-data/venv/x") == "dados"
    (mundo.work / "meuvenv").mkdir()
    (mundo.work / "meuvenv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    assert v("{work}/meuvenv/out.mp4") == "venv"
    assert v("{work}/lib/python3/site-packages/x.py") == "site-packages"
    # U22 decide: nenhum dos outros 4 olha site-packages, pyvenv.cfg nem o código do motor
    for modulo in ("matchcut", "instagram", "video_to_skill", "voicestudio"):
        assert veredito(modulo, sub(mundo, "{work}/meuvenv/out.mp4")) == L, modulo
        assert veredito(modulo, sub(mundo, "{work}/lib/python3/site-packages/x.py")) == L, modulo


# ------------------------------------------------------------------------------------------------ as constantes das cópias

def test_the_system_root_tables_of_the_copies():
    posix25 = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/proc", "/sys", "/run",
               "/opt", "/srv", "/snap", "/System", "/Library", "/Applications", "/private/etc", "/var/lib", "/var/log",
               "/var/spool", "/var/run", "/var/db")
    assert matchcut._RAIZES_POSIX == instagram._RAIZES_POSIX == video_to_skill._RAIZES_POSIX == montage._SISTEMA_POSIX == posix25
    assert len(posix25) == 25
    # U22 decide: a quinta cópia tem 15 (faltam /opt /srv /snap /Applications /var/lib /var/log /var/spool /var/run /var/db)
    assert voicestudio._ROOTS_POSIX == ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/proc", "/sys",
                                         "/run", "/System", "/Library", "/private/etc")
    assert set(posix25) - set(voicestudio._ROOTS_POSIX) == {"/opt", "/srv", "/snap", "/Applications", "/var/lib", "/var/log", "/var/spool",
                                                              "/var/run", "/var/db"}
    windows = ("SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA")
    assert matchcut._RAIZES_WINDOWS == instagram._RAIZES_WINDOWS == video_to_skill._RAIZES_WINDOWS == montage._SISTEMA_WINDOWS == windows
    assert voicestudio._ROOTS_WINDOWS == windows


def test_the_autostart_tables_and_the_appdata_startup_branch():
    inicio = (("Library", "LaunchAgents"), ("Library", "LaunchDaemons"),
              ("AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
    assert matchcut._INICIO_AUTOMATICO == instagram._INICIO_AUTOMATICO == video_to_skill._INICIO_AUTOMATICO == montage._INICIO_AUTOMATICO == inicio
    assert not hasattr(voicestudio, "_INICIO_AUTOMATICO")  # U22 decide
    startup = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    assert matchcut._STARTUP_DO_APPDATA == instagram._STARTUP_DO_APPDATA == startup
    assert not hasattr(video_to_skill, "_STARTUP_DO_APPDATA") and not hasattr(montage, "_STARTUP_DO_APPDATA")  # U22 decide
    assert not hasattr(voicestudio, "_STARTUP_DO_APPDATA")
