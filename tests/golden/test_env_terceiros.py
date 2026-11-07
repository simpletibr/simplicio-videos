"""G0 (golden, caracterização): o conjunto EXATO de variáveis de ambiente que cada módulo repassa a um programa de terceiro.

Oito listas fechadas (allow-lists) escritas à mão, uma por módulo, e já divergentes (TMP/TEMP x TMPDIR, LC_CTYPE, proxy, certificados,
USERPROFILE...). O teste envenena `os.environ` com todos os nomes de todas as listas mais chaves de decoração (GEMINI_API_KEY,
GITHUB_TOKEN, PYTHONPATH, SSH_AUTH_SOCK...) e chama a função REAL de cada módulo que monta o ambiente do filho; o que sai é a lista efetiva,
não a constante. A correção U07 (`terceiros.env_para_terceiro`, que recebe de cada módulo o que ele tem a mais que o NUCLEO_ENV) tem de manter
cada conjunto IDÊNTICO: este arquivo é a prova, e qualquer linha que mude é decisão do dono ("U22 decide"), não de U07.

Privados exercitados por import direto (caracterização): download._ambiente, busca._ambiente_filho, matchcut._ambiente/_env_pip,
montage._child_env/_registry_keys/_ENV_KEEP, status._primeira_linha (o env passado a subprocess.run é capturado), video_to_skill._env,
instagram._ambiente, doctor_trilhas._ambiente; constantes download.ENV_REPASSADO, busca.ENV_REPASSADO/ENV_FORCADO, matchcut.ENV_NAMES/ENV_PIP,
status.ENV_FERRAMENTA, video_to_skill.ENV_NAMES/ENV_NET, instagram.ENV_NAMES."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from simplicio_video import busca, childio, doctor_trilhas, download, instagram, matchcut, montage, status, video_to_skill

PROXY = ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "no_proxy", "all_proxy")
DECORACAO = ("GEMINI_API_KEY", "GITHUB_TOKEN", "OPENAI_API_KEY", "SIMPLICIO_VIDEO_DATA", "PYTHONPATH", "SSH_AUTH_SOCK",
             "AWS_SECRET_ACCESS_KEY", "SIMPLICIO_OFFLINE", "FFREPORT")

# módulo -> nomes que chegam ao filho quando TODA variável conhecida está no ambiente do pai
ESPERADO = {
    "download._ambiente": {"ALL_PROXY", "HOME", "HTTPS_PROXY", "HTTP_PROXY", "LANG", "LC_ALL", "NO_PROXY", "PATH", "REQUESTS_CA_BUNDLE",
                           "SSL_CERT_DIR", "SSL_CERT_FILE", "TMPDIR", "all_proxy", "http_proxy", "https_proxy", "no_proxy"},
    "busca._ambiente_filho": {"ALL_PROXY", "HOME", "HTTPS_PROXY", "HTTP_PROXY", "LANG", "LC_ALL", "NODE_EXTRA_CA_CERTS", "NODE_USE_ENV_PROXY",
                              "NO_COLOR", "NO_PROXY", "PATH", "SSL_CERT_DIR", "SSL_CERT_FILE", "TINYFISH_API_KEY", "TINYFISH_NO_TELEMETRY",
                              "TMPDIR", "all_proxy", "http_proxy", "https_proxy", "no_proxy"},
    "matchcut._ambiente": {"HOME", "LANG", "LC_ALL", "NUMBA_CACHE_DIR", "PATH", "PYTHONIOENCODING", "SYSTEMROOT", "TEMP", "TMP"},
    "matchcut._env_pip": {"ALL_PROXY", "CURL_CA_BUNDLE", "HOME", "HTTPS_PROXY", "HTTP_PROXY", "LANG", "LC_ALL", "NO_PROXY", "PATH", "PIP_CERT",
                          "PIP_EXTRA_INDEX_URL", "PIP_INDEX_URL", "PIP_PROXY", "PIP_TRUSTED_HOST", "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR",
                          "SSL_CERT_FILE", "SYSTEMROOT", "TEMP", "TMP", "all_proxy", "http_proxy", "https_proxy", "no_proxy"},
    "montage._child_env": {"ALL_PROXY", "CURL_CA_BUNDLE", "HOME", "HTTPS_PROXY", "HTTP_PROXY", "LANG", "LC_ALL", "LC_CTYPE",
                           "NODE_EXTRA_CA_CERTS", "NO_PROXY", "PATH", "PATHEXT", "PIP_CERT", "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR",
                           "SSL_CERT_FILE", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "USER", "all_proxy", "http_proxy", "https_proxy", "no_proxy"},
    "status._primeira_linha": {"ALL_PROXY", "HOME", "HTTPS_PROXY", "HTTP_PROXY", "LANG", "LC_ALL", "LC_CTYPE", "NODE_EXTRA_CA_CERTS",
                               "NODE_USE_ENV_PROXY", "NO_PROXY", "PATH", "SSL_CERT_DIR", "SSL_CERT_FILE", "TMPDIR", "all_proxy",
                               "http_proxy", "https_proxy", "no_proxy"},
    "video_to_skill._env": {"APPDATA", "HOME", "LANG", "LC_ALL", "LOCALAPPDATA", "PATH", "SYSTEMROOT", "TEMP", "TMP", "TMPDIR", "USERPROFILE",
                            "VTS_DATA_DIR", "XDG_DATA_HOME"},
    "video_to_skill._env(net=True)": {"ALL_PROXY", "APPDATA", "CURL_CA_BUNDLE", "HOME", "HTTPS_PROXY", "HTTP_PROXY", "LANG", "LC_ALL",
                                      "LOCALAPPDATA", "NO_PROXY", "PATH", "REQUESTS_CA_BUNDLE", "SSL_CERT_DIR", "SSL_CERT_FILE", "SYSTEMROOT",
                                      "TEMP", "TMP", "TMPDIR", "USERPROFILE", "VTS_DATA_DIR", "XDG_DATA_HOME", "all_proxy", "http_proxy",
                                      "https_proxy", "no_proxy"},
    "instagram._ambiente": {"HOME", "LANG", "LC_ALL", "PATH", "PYTHONIOENCODING", "SYSTEMROOT", "TEMP", "TMP"},
    "doctor_trilhas._ambiente": {"ALL_PROXY", "HOME", "HTTPS_PROXY", "HTTP_PROXY", "LANG", "LC_ALL", "LC_CTYPE", "NODE_EXTRA_CA_CERTS",
                                 "NODE_USE_ENV_PROXY", "NO_PROXY", "PATH", "SSL_CERT_DIR", "SSL_CERT_FILE", "TMPDIR", "all_proxy",
                                 "http_proxy", "https_proxy", "no_proxy"},
}

# as 8 listas do plano (matchcut, instagram e video_to_skill entram com ENV_NAMES; o pip do matchcut e o `net` do video_to_skill são extras)
OITO = ("download._ambiente", "busca._ambiente_filho", "matchcut._ambiente", "montage._child_env", "status._primeira_linha",
        "video_to_skill._env", "instagram._ambiente", "doctor_trilhas._ambiente")
CONSTANTES = {
    "download.ENV_REPASSADO": download.ENV_REPASSADO, "busca.ENV_REPASSADO": busca.ENV_REPASSADO, "matchcut.ENV_NAMES": matchcut.ENV_NAMES,
    "matchcut.ENV_PIP": matchcut.ENV_PIP, "montage._ENV_KEEP": montage._ENV_KEEP, "status.ENV_FERRAMENTA": status.ENV_FERRAMENTA,
    "video_to_skill.ENV_NAMES": video_to_skill.ENV_NAMES, "video_to_skill.ENV_NET": video_to_skill.ENV_NET,
    "instagram.ENV_NAMES": instagram.ENV_NAMES,
}


def todos_os_nomes() -> set:
    nomes = {n for t in CONSTANTES.values() for n in t}
    return nomes | set(DECORACAO)


def efetivos(monkeypatch) -> dict:
    """O ambiente que cada módulo monta quando o pai tem todos os nomes conhecidos (cada valor é 'v:' + o nome)."""
    monkeypatch.setattr(os, "environ", {n: "v:" + n for n in sorted(todos_os_nomes())})
    visto = {}

    class Fim:
        returncode, stdout, stderr = 0, "x", ""

    def espia(cmd, **kw):
        visto["env"] = kw.get("env")
        return Fim()

    monkeypatch.setattr(status.subprocess, "run", espia)
    status._primeira_linha(["x"])
    return {
        "download._ambiente": download._ambiente(),
        "busca._ambiente_filho": busca._ambiente_filho(),
        "matchcut._ambiente": matchcut._ambiente(Path("/priv")),
        "matchcut._env_pip": matchcut._env_pip(),
        "montage._child_env": montage._child_env(),
        "status._primeira_linha": visto["env"],
        "video_to_skill._env": video_to_skill._env(),
        "video_to_skill._env(net=True)": video_to_skill._env(True),
        "instagram._ambiente": instagram._ambiente(),
        "doctor_trilhas._ambiente": doctor_trilhas._ambiente(),
    }


@pytest.mark.parametrize("modulo", list(ESPERADO))
def test_the_effective_environment_of_each_module_is_the_exact_set_of_today(monkeypatch, modulo):
    env = efetivos(monkeypatch)[modulo]
    assert set(env) == ESPERADO[modulo]


def test_the_values_are_forwarded_untouched_except_for_the_names_each_module_sets_itself(monkeypatch):
    env = efetivos(monkeypatch)
    assert env["busca._ambiente_filho"]["NO_COLOR"] == "1" and env["busca._ambiente_filho"]["TINYFISH_NO_TELEMETRY"] == "1"
    assert env["matchcut._ambiente"]["PYTHONIOENCODING"] == "utf-8" and env["instagram._ambiente"]["PYTHONIOENCODING"] == "utf-8"
    assert env["matchcut._ambiente"]["NUMBA_CACHE_DIR"] == str(Path("/priv") / "numba")
    for modulo, e in env.items():
        for nome, valor in e.items():
            if nome not in ("NO_COLOR", "TINYFISH_NO_TELEMETRY", "PYTHONIOENCODING", "NUMBA_CACHE_DIR"):
                assert valor == "v:" + nome, (modulo, nome)


def test_no_module_forwards_a_decoy_credential_or_a_python_or_engine_variable(monkeypatch):
    for modulo, e in efetivos(monkeypatch).items():
        assert not set(e) & set(DECORACAO), modulo  # nenhuma chave de provedor, token, PYTHONPATH, SIMPLICIO_*, nem FFREPORT
    # U22 decide (U07 mantém igual): a TINYFISH_API_KEY é a única chave que passa, e só no filho da busca
    assert [m for m, e in efetivos(monkeypatch).items() if "TINYFISH_API_KEY" in e] == ["busca._ambiente_filho"]


def test_the_constants_are_what_the_functions_forward():
    assert set(download.ENV_REPASSADO) == ESPERADO["download._ambiente"]
    assert set(busca.ENV_REPASSADO) | set(busca.ENV_FORCADO) == ESPERADO["busca._ambiente_filho"]
    assert set(matchcut.ENV_NAMES) | {"PYTHONIOENCODING", "NUMBA_CACHE_DIR"} == ESPERADO["matchcut._ambiente"]
    assert set(matchcut.ENV_PIP) == ESPERADO["matchcut._env_pip"]
    assert set(montage._ENV_KEEP) == ESPERADO["montage._child_env"]
    assert set(status.ENV_FERRAMENTA) == ESPERADO["status._primeira_linha"] == ESPERADO["doctor_trilhas._ambiente"]
    assert set(video_to_skill.ENV_NAMES) == ESPERADO["video_to_skill._env"]
    assert set(video_to_skill.ENV_NAMES) | set(video_to_skill.ENV_NET) == ESPERADO["video_to_skill._env(net=True)"]
    assert set(instagram.ENV_NAMES) | {"PYTHONIOENCODING"} == ESPERADO["instagram._ambiente"]
    assert doctor_trilhas.ENV_FERRAMENTA is status.ENV_FERRAMENTA  # a lista do doctor_trilhas É a do status (importada), não uma 9a cópia


def test_the_core_all_eight_lists_share_is_four_names():
    # U22 decide (U07 mantém igual): terceiros.NUCLEO_ENV = a interseção das 8 listas; hoje são só estes 4 (TMPDIR x TMP/TEMP e o resto divergem)
    nucleo = set.intersection(*(ESPERADO[m] for m in OITO))
    assert nucleo == {"HOME", "LANG", "LC_ALL", "PATH"}


def test_what_only_some_modules_forward():
    # U22 decide (U07 mantém igual): cada módulo passa o que tem a mais que o núcleo; estas são as diferenças de hoje
    e = ESPERADO
    assert {n for m in OITO for n in e[m]} - {"HOME", "LANG", "LC_ALL", "PATH"} >= {"TMP", "TEMP", "TMPDIR", "LC_CTYPE", "SYSTEMROOT"}
    assert set(e["instagram._ambiente"]) - {"PYTHONIOENCODING"} == {"HOME", "LANG", "LC_ALL", "PATH", "SYSTEMROOT", "TEMP", "TMP"}  # sem proxy, sem TMPDIR
    assert not any(n in e["instagram._ambiente"] or n in e["matchcut._ambiente"] for n in PROXY)  # instagram e matchcut: sem proxy (o pip do matchcut tem)
    assert all(n in e["download._ambiente"] for n in PROXY) and all(n in e["video_to_skill._env(net=True)"] for n in PROXY)
    assert not any(n in e["video_to_skill._env"] for n in PROXY)  # o video_to_skill só passa proxy quando há URL (net=True)
    assert {"USERPROFILE", "LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME", "VTS_DATA_DIR"} <= e["video_to_skill._env"]
    assert {"USERPROFILE", "LOCALAPPDATA", "APPDATA", "XDG_DATA_HOME", "VTS_DATA_DIR"}.isdisjoint(
        e["download._ambiente"] | e["busca._ambiente_filho"] | e["matchcut._ambiente"] | e["montage._child_env"] | e["instagram._ambiente"])
    assert {"USER", "PATHEXT"} <= e["montage._child_env"] and not {"USER", "PATHEXT"} & (e["download._ambiente"] | e["status._primeira_linha"])
    assert "LC_CTYPE" in e["montage._child_env"] and "LC_CTYPE" in e["status._primeira_linha"] and "LC_CTYPE" not in e["download._ambiente"]
    assert "NODE_EXTRA_CA_CERTS" in e["busca._ambiente_filho"] and "NODE_EXTRA_CA_CERTS" not in e["download._ambiente"]
    assert "CURL_CA_BUNDLE" in e["montage._child_env"] and "CURL_CA_BUNDLE" not in e["download._ambiente"]
    assert "REQUESTS_CA_BUNDLE" in e["download._ambiente"] and "REQUESTS_CA_BUNDLE" not in e["busca._ambiente_filho"]


# ------------------------------------------------------------------------------- a exceção do montage: as chaves do terminal

def test_montage_forwards_every_provider_key_of_the_terminal_to_the_registry_child_and_none_under_mcp(monkeypatch):
    # U22 decide (U07 mantém igual): fora do MCP, `_registry_keys` repassa TODA variável que termina em _API_KEY, _TOKEN ou _KEY (não é uma lista fechada)
    monkeypatch.setattr(os, "environ", {"PATH": "/bin", "GEMINI_API_KEY": "g", "GITHUB_TOKEN": "t", "FOO_KEY": "k", "KEYRING": "x",
                                         "SIMPLICIO_VIDEO_DATA": "/d", "MY_SECRET": "s", "FAL_KEY_FILE": "f"})
    assert sorted(montage._registry_keys()) == ["FOO_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN"]
    assert sorted(montage._child_env(montage._registry_keys())) == ["FOO_KEY", "GEMINI_API_KEY", "GITHUB_TOKEN", "PATH"]
    monkeypatch.setitem(os.environ, childio.ENV_FLAG, "1")
    assert montage._registry_keys() == []
    assert sorted(montage._child_env(montage._registry_keys())) == ["PATH"]
