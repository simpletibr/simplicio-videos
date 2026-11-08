"""G0 (golden, caracterização): onde cada trilha recusa gravar (as 5 versões de "lugar proibido").

As cinco regras fazem a mesma pergunta ("o MCP/terminal pode gravar em `real`?") com respostas diferentes. Este arquivo escreve a
tabela caminho x módulo COMO ELA É HOJE. Nada aqui é decisão de projeto: cada linha onde as colunas discordam é uma divergência
herdada, marcada "U22 decide". A correção U22a só pode mudar linhas desta tabela, e o diff dela é o que o dono aprova.

Privados exercitados por import direto (caracterização; não há API pública equivalente):
  matchcut._lugar_proibido, instagram._lugar_proibido, montage._lugar_proibido, video_to_skill._lugar_proibido,
  voicestudio._forbidden_place; as constantes das cópias (matchcut/instagram/video_to_skill._RAIZES_POSIX/_RAIZES_WINDOWS/_INICIO_AUTOMATICO,
  montage._SISTEMA_POSIX/_SISTEMA_WINDOWS/_INICIO_AUTOMATICO, matchcut/instagram._STARTUP_DO_APPDATA) agora são UMA tabela em
  terceiros.RAIZES_POSIX/RAIZES_WINDOWS/INICIO_AUTOMATICO/STARTUP_DO_APPDATA; voicestudio._ROOTS_POSIX/_ROOTS_WINDOWS ficam, só para a LEITURA.

U22a (a UNIÃO): as cinco regras viraram `terceiros.lugar_proibido`. Cada trilha ainda pergunta primeiro os lugares que são só dela, com as
palavras dela; o resto é a regra única, que recusa a união do que as cinco recusavam. Onde duas razões valem para o mesmo caminho, cada
trilha continua dizendo a razão que sempre disse (teste `test_where_two_reasons_apply...`).

Os chamadores passam o caminho real (links resolvidos); aqui `real()` faz o mesmo. Congelado no Linux: em macOS/Windows a regra de
maiúsculas (CASE_INSENSITIVE) e as raízes dos temporários mudam a tabela."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from simplicio_video import instagram, matchcut, montage, terceiros, video_to_skill, voicestudio

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
        return S if r.startswith("pasta do sistema (") else O if r.startswith("pasta oculta do home (") else MENSAGEM[r]  # U22a: o resto são as palavras da regra única
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
    # --- as linhas que eram DIVERGENTES e U22a unificou: agora as cinco dizem a mesma coisa (cada comentário "U22 decide" fica, com a decisão embaixo)
    # U22 decide: voicestudio tem 16 raízes (sem /opt /srv /snap /Applications /var/lib /var/log /var/spool /var/run /var/db); as outras 4 têm 25.
    #   U22a decidiu: a regra única tem as 25; o voicestudio passa a recusar as que não conhecia (era L, passa a S).
    ("/opt/x", *(S,) * 5), ("/srv/x", *(S,) * 5), ("/snap/x", *(S,) * 5), ("/Applications/x", *(S,) * 5),
    ("/var/lib/x", *(S,) * 5), ("/var/log/x", *(S,) * 5), ("/var/spool/x", *(S,) * 5), ("/var/db/x", *(S,) * 5),
    # U22 decide: só o montage recusa /var inteiro (exceto /var/tmp, que as cinco deixam).
    #   U22a decidiu: os cinco recusam /var inteiro, menos /var/tmp (matchcut, instagram, video_to_skill e voicestudio: era L, passa a S).
    ("/var/cache/x", *(S,) * 5), ("/var/x", *(S,) * 5),
    # U22 decide: voicestudio não conhece as pastas de início automático do home (LaunchAgents, LaunchDaemons, Startup do Windows).
    #   U22a decidiu: o voicestudio passa a recusá-las (era L, passa a I).
    ("{home}/Library/LaunchAgents/x.plist", *(I,) * 5), ("{home}/Library/LaunchDaemons/x.plist", *(I,) * 5),
    ("{home}/AppData/Roaming/Microsoft/Windows/Start Menu/Programs/Startup/x.bat", *(I,) * 5),
    # U22 decide: o Startup achado por $APPDATA (fora do home) só existe em matchcut e instagram (_STARTUP_DO_APPDATA).
    #   U22a decidiu: os cinco o recusam (montage, video_to_skill e voicestudio: era L, passa a I).
    ("{appdata}/Microsoft/Windows/Start Menu/Programs/Startup/x.bat", *(I,) * 5),
    # U22 decide: .git fora de pasta oculta: voicestudio não olha.
    #   U22a decidiu: o voicestudio passa a recusar (era L, passa a G).
    ("{work}/.git/hooks/pre-commit", *(G,) * 5), ("{home}/proj/.git/config", *(G,) * 5),
    # U22a, linhas novas: o que o resto do arquivo só dizia por módulo (a raiz de dados, site-packages) entra na tabela, nos cinco.
    ("{data}/x", *("dados",) * 5), ("{work}/lib/python3/site-packages/x.py", *("site-packages",) * 5),
    # U22a, revisão independente: a exceção de /var/tmp vale só com a caixa exata onde o disco distingue caixa (Linux): /var/Tmp e /var/TMP são
    # outras pastas e seguem recusadas como o resto de /var (o montage já as recusava no main).
    ("/var/Tmp/x", *(S,) * 5), ("/var/TMP/x", *(S,) * 5),
]

DIVERGENTES = [
    # U22a: nenhuma das linhas antigas sobrou (as cinco concordam). Ficam duas em que todos recusam mas a razão dita difere,
    # de propósito: cada trilha segue dizendo a razão que sempre disse (a mensagem de uma recusa que já existe não muda).
    # A pasta de ferramentas: o montage a conta como "dados do motor (jobs, tools, openmontage-data)"; as outras três a chamam de "ferramentas".
    # A do voicestudio é nova (era L).
    ("{tools}/x", "ferramentas", "ferramentas", "dados", "ferramentas", "ferramentas"),
    # /var inteiro é "pasta do sistema" para o montage antes de olhar .git; as outras trilhas olham .git primeiro (e o voicestudio, que não olhava, agora também).
    ("/var/www/site/.git/x", G, G, S, G, G),
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
    # U22a decidiu: o contrato único é o da regra (`terceiros.lugar_proibido`: str | None, teste abaixo); os quatro nomes locais seguem
    # devolvendo "" ou o motivo porque tests/test_jobspec.py:600 (fora da posse da U22a) afirma `montage._lugar_proibido(...) == ""`.


def test_the_one_rule_answers_str_or_none_and_the_four_local_names_keep_answering_the_empty_text(mundo):
    livre, proibido = sub(mundo, "{work}/ok.txt"), sub(mundo, "/etc/x")
    assert terceiros.lugar_proibido(livre) is None
    assert terceiros.lugar_proibido(proibido) == "em pasta do sistema"
    for modulo in ("matchcut", "instagram", "montage", "video_to_skill"):
        assert getattr(sys.modules[f"simplicio_video.{modulo}"], "_lugar_proibido")(livre) == "", modulo
        assert getattr(sys.modules[f"simplicio_video.{modulo}"], "_lugar_proibido")(proibido) == "em pasta do sistema", modulo
    assert voicestudio._forbidden_place(livre) is None


# ------------------------------------------------------------------------------------- o que cada módulo protege além do sistema

def test_matchcut_protects_its_checkout_the_tools_folder_and_its_venv_but_not_the_engine_data_root(mundo):
    v = lambda c: veredito("matchcut", sub(mundo, c))  # noqa: E731
    assert v("{tools}/matchcut/x") == "checkout"
    assert v("{tools}/instagram/x") == "ferramentas"
    assert v("{data}/matchcut-data/venv/bin/python") == "dados"
    assert v("{data}/x") == "dados"  # U22 decide: o montage recusa a raiz de dados inteira; o matchcut só a própria subpasta
    # U22a decidiu: a raiz de dados inteira é recusada por todos (matchcut: era L, passa a "dados"; o nome deste teste é histórico: o id não muda)


def test_instagram_and_video_to_skill_protect_only_their_checkout_and_the_tools_folder(mundo):
    for modulo in ("instagram", "video_to_skill"):  # o checkout de cada um é {tools}/<nome em tools.TOOLS>
        v = lambda c, m=modulo: veredito(m, sub(mundo, c))  # noqa: E731
        assert v("{tools}/" + modulo + "/x") == "checkout", modulo
        assert v("{tools}/matchcut/x") == "ferramentas", modulo
        assert v("{data}/x") == "dados", modulo  # U22 decide: nenhum dos dois protege a pasta de dados
        # U22a decidiu: protegem (era L, passa a "dados"; o nome deste teste é histórico: o id não muda)


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
    # U22a decidiu: os outros 4 passam a recusar os três (era L; o nome deste teste é histórico: o id não muda)
    for modulo in ("matchcut", "instagram", "video_to_skill", "voicestudio"):
        assert veredito(modulo, sub(mundo, "{work}/meuvenv/out.mp4")) == "venv", modulo
        assert veredito(modulo, sub(mundo, "{work}/lib/python3/site-packages/x.py")) == "site-packages", modulo
        assert veredito(modulo, real(Path(montage.__file__).parent / "x.py")) == "motor", modulo


# ------------------------------------------------------------------------------------------------ as constantes das cópias

def test_the_system_root_tables_of_the_copies():
    posix25 = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/proc", "/sys", "/run",
               "/opt", "/srv", "/snap", "/System", "/Library", "/Applications", "/private/etc", "/var/lib", "/var/log",
               "/var/spool", "/var/run", "/var/db")
    assert terceiros.RAIZES_POSIX == posix25  # U22a: era `matchcut._RAIZES_POSIX == instagram._RAIZES_POSIX == video_to_skill._RAIZES_POSIX == montage._SISTEMA_POSIX == posix25`
    assert not any(hasattr(m, n) for m, n in ((matchcut, "_RAIZES_POSIX"), (instagram, "_RAIZES_POSIX"), (video_to_skill, "_RAIZES_POSIX"),
                                              (montage, "_SISTEMA_POSIX")))  # U22a: as quatro cópias de 25 saíram dos módulos
    assert len(posix25) == 25
    # U22 decide: a quinta cópia tem 16 (faltam /opt /srv /snap /Applications /var/lib /var/log /var/spool /var/run /var/db)
    # U22a decidiu: para GRAVAR vale a tabela única (as 25); as 16 do voicestudio ficam só para LER (`_guard_input`), que a ficha não muda.
    assert voicestudio._ROOTS_POSIX == ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/proc", "/sys",
                                         "/run", "/System", "/Library", "/private/etc")
    assert set(posix25) - set(voicestudio._ROOTS_POSIX) == {"/opt", "/srv", "/snap", "/Applications", "/var/lib", "/var/log", "/var/spool",
                                                              "/var/run", "/var/db"}
    windows = ("SYSTEMROOT", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA")
    assert terceiros.RAIZES_WINDOWS == windows  # U22a: era `matchcut._RAIZES_WINDOWS == instagram._... == video_to_skill._... == montage._SISTEMA_WINDOWS == windows`
    assert not any(hasattr(m, n) for m, n in ((matchcut, "_RAIZES_WINDOWS"), (instagram, "_RAIZES_WINDOWS"), (video_to_skill, "_RAIZES_WINDOWS"),
                                              (montage, "_SISTEMA_WINDOWS")))
    assert voicestudio._ROOTS_WINDOWS == windows


def test_the_autostart_tables_and_the_appdata_startup_branch():
    inicio = (("Library", "LaunchAgents"), ("Library", "LaunchDaemons"),
              ("AppData", "Roaming", "Microsoft", "Windows", "Start Menu", "Programs", "Startup"))
    assert terceiros.INICIO_AUTOMATICO == inicio  # U22a: era `matchcut._INICIO_AUTOMATICO == instagram._... == video_to_skill._... == montage._INICIO_AUTOMATICO == inicio`
    assert not any(hasattr(m, "_INICIO_AUTOMATICO") for m in (matchcut, instagram, video_to_skill, montage))
    assert not hasattr(voicestudio, "_INICIO_AUTOMATICO")  # U22 decide
    startup = ("Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    assert terceiros.STARTUP_DO_APPDATA == startup  # U22a: era `matchcut._STARTUP_DO_APPDATA == instagram._STARTUP_DO_APPDATA == startup`; agora é de todos
    assert not hasattr(matchcut, "_STARTUP_DO_APPDATA") and not hasattr(instagram, "_STARTUP_DO_APPDATA")
    assert not hasattr(video_to_skill, "_STARTUP_DO_APPDATA") and not hasattr(montage, "_STARTUP_DO_APPDATA")  # U22 decide
    assert not hasattr(voicestudio, "_STARTUP_DO_APPDATA")


# ------------------------------------------------------------------------- a razão dita quando duas valem (U22a: verde antes e depois)

def test_where_two_reasons_apply_each_module_tells_the_one_it_always_told(mundo, monkeypatch):
    """Unificar a regra não troca a razão dita num caminho que já era recusado. O padrão do motor guarda os dados em ~/.simplicio-video,
    que também é uma pasta oculta do home; site-packages e um venv podem estar numa pasta do sistema ou do home. Nesses caminhos o montage
    diz "dados", "site-packages" ou "venv" (olha esses lugares antes do sistema e do home) e as outras trilhas dizem a pasta oculta ou do sistema."""
    dados = mundo.home / ".simplicio-video"
    (dados / "tools").mkdir(parents=True)
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(dados))
    monkeypatch.setenv("SIMPLICIO_TOOLS_DIR", str(dados / "tools"))
    (mundo.home / ".venv").mkdir()
    (mundo.home / ".venv" / "pyvenv.cfg").write_text("home = /usr/bin\n")
    # (caminho, matchcut, instagram, montage, video_to_skill, voicestudio)
    linhas = [
        ("{home}/.simplicio-video/jobs/x.json", O, O, "dados", O, O),
        ("{home}/.simplicio-video/tools/x", "ferramentas", "ferramentas", "dados", "ferramentas", O),
        ("/usr/lib/python3/site-packages/x.py", S, S, "site-packages", S, S),
        ("{home}/.local/lib/python3/site-packages/x.py", O, O, "site-packages", O, O),
        ("{home}/.venv/bin/x", O, O, "venv", O, O),
    ]
    for caminho, *esperado in linhas:
        p = sub(mundo, caminho)
        assert dict(zip(MODULOS, (veredito(m, p) for m in MODULOS))) == dict(zip(MODULOS, esperado)), caminho


# ------------------------------------------------------------------------ U22a, revisão independente: nome longo demais para o disco

def test_a_name_too_long_for_the_disk_is_no_reason_and_never_a_traceback(mundo):
    """A sonda de `pyvenv.cfg` da regra única levantava OSError (ENAMETOOLONG) para um componente de mais de 255 bytes, em quatro módulos que no
    main devolviam '' (o montage já levantava). O nome não existe: não é razão para recusar, e o `--out` do video-to-skill dá a mensagem limpa
    de sempre (`video-to-skill extract ... --out <300 letras>/x`: rc 1 com a mensagem, não um traceback)."""
    longo = sub(mundo, "{work}") / ("a" * 300) / "x.txt"
    assert {m: veredito(m, longo) for m in MODULOS} == {m: L for m in MODULOS}
    with pytest.raises(video_to_skill.VideoToSkillError, match="não existe"):
        video_to_skill._new_dir(str(longo), "terminal", "--out")
