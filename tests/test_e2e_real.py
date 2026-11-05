"""Testes offline do `scripts/e2e_real.py` (o roteiro de testes reais ponta a ponta).

Quase tudo aqui roda com fakes: sondas da máquina (chaves, apps, portas), um executor que grava os argumentos e devolve
respostas prontas, e relógio falso. O plano (sem --sim-gastar) é provado sem subprocesso e sem socket: um teste troca
`subprocess` e `socket` por funções que falham e roda o plano com as sondas reais. Nenhuma chave é usada, por isso o
arquivo entra no `make check`. O roteiro de verdade é `make e2e-real E2E_ARGS="--sim-gastar"`, fora do gate.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "e2e_real.py"
FIXTURE = ROOT / "tests" / "fixtures" / "mini" / "contract.yaml"
CHAVE_FALSA = "chave-falsa-do-teste-0123456789"


def _carrega():
    nome = "e2e_real_teste"
    if nome in sys.modules:
        return sys.modules[nome]
    spec = importlib.util.spec_from_file_location(nome, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nome] = mod
    spec.loader.exec_module(mod)
    return mod


e2e = _carrega()


class SondasFalsas:
    """A máquina de mentira: o que existe, quais portas abrem, quais chaves estão no ambiente."""

    def __init__(self, *, achados=("node", "npx", "ffmpeg", "docker", "tinyfish"), portas=(), chaves=(), node=(22, 23, 4),
                 mp=False, toonflow=False, config_tinyfish=False, pacote=True, config_mp=None):
        self.achados, self.portas, self.chaves = set(achados), set(portas), dict(chaves)
        self.node, self.mp, self.toonflow, self.config_tinyfish = node, mp, toonflow, config_tinyfish
        self._pacote, self._config_mp = pacote, config_mp

    def config_moneyprinter(self):
        return self._config_mp

    def achar(self, nome):
        return f"/bin/{nome}" if nome in self.achados else None

    def porta_aberta(self, host, porta):
        return porta in self.portas

    def versao(self, argv):
        if argv[0] == "node":
            return "v" + ".".join(map(str, self.node))
        return "fake 1.0"

    def env(self):
        return dict(self.chaves)

    def arquivo_existe(self, caminho):
        return self.config_tinyfish and str(caminho).endswith("config.json")

    def adaptadores(self):
        return {"gemini": ("GEMINI_API_KEY", True), "fal": ("FAL_KEY", False), "wavespeed": ("WAVESPEED_API_KEY", False),
                "kie": ("KIE_API_KEY", False), "alibaba": ("DASHSCOPE_API_KEY", False)}

    def fontes_pagas(self):
        return {"wavespeed": "--confirm-wavespeed-charge", "volcengine_seedance": "--confirm-seedance-charge",
                "openai_image": None}

    def moneyprinter_pronto(self):
        return self.mp

    def toonflow_dir(self):
        return Path("/x/toonflow") if self.toonflow else None

    def pacote(self):
        return self._pacote


class Gravador:
    """Executor falso: grava cada argv e responde pelo primeiro trecho do comando que bater (ou uma função que age)."""

    def __init__(self, respostas=None):
        self.chamadas = []
        self.respostas = respostas or {}

    def __call__(self, argv, *, env, cwd, timeout):
        self.chamadas.append(list(argv))
        texto = " ".join(map(str, argv))
        for trecho, resposta in self.respostas.items():
            if trecho in texto:
                return resposta(argv) if callable(resposta) else resposta
        return e2e.Saida(0, "", "")

    def comandos(self, trecho):
        return [c for c in self.chamadas if trecho in " ".join(map(str, c))]


def _estimativa(usd):
    return e2e.Saida(0, json.dumps({"estimate": {"usd": usd}, "chunks": 1, "duration_s": 4.0}), "")


def _saida_de(argv_):
    return argv_[argv_.index("--out") + 1]


def _run_swap(argv_):
    """Um swap run que cumpre o contrato: grava o MP4 de saída e responde state done."""
    out = Path(_saida_de(argv_))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"mp4")
    return e2e.Saida(0, json.dumps({"state": "done", "output": str(out)}), "")


def _roda(tmp_path, capsys, argv, sondas=None, gravador=None):
    gravador = gravador or Gravador()
    sondas = sondas or SondasFalsas()
    rc = e2e.main(["--pasta", str(tmp_path / "e2e"), *argv], sondas=sondas, runner=gravador)
    return rc, capsys.readouterr().out, gravador


def _item(saida_json, id_):
    return next(c for c in saida_json["checks"] if c["id"] == id_)


# ------------------------------------------------------------------------------------------------ consentimento

def test_plano_sem_sim_gastar_nao_roda_nada_nem_cria_pasta(tmp_path, capsys):
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA}, portas=(3900,))
    rc, out, grav = _roda(tmp_path, capsys, [], sondas=sondas)
    assert rc == 0
    assert grav.chamadas == [], "sem --sim-gastar nenhum comando pode rodar"
    assert not (tmp_path / "e2e").exists(), "o plano não cria a pasta temporária"
    assert "PLANO" in out and "--sim-gastar" in out


def test_yes_e_alias_de_sim_gastar(tmp_path, capsys):
    rc, out, grav = _roda(tmp_path, capsys, ["--yes", "--apenas", "smoke-so"])
    assert rc == 0
    assert any("smoke_so.py" in " ".join(c) for c in grav.chamadas)


def test_build_nunca_roda_sem_consentimento_mesmo_com_todas_as_flags(tmp_path, capsys):
    sondas = SondasFalsas(chaves={})
    argv = ["--incluir-build", "--max-usd", "2", "--build-args", "--spec x.json"]
    rc, out, grav = _roda(tmp_path, capsys, argv, sondas=sondas)
    assert rc == 0 and grav.chamadas == []


# -------------------------------------------------------------------------------------- chaves e apps (SKIP)

def test_sem_chaves_e_apps_os_checks_reais_viram_skip_com_motivo(tmp_path, capsys):
    sondas = SondasFalsas(achados=(), portas=(), chaves={})
    rc, out, grav = _roda(tmp_path, capsys, ["--json"], sondas=sondas)
    doc = json.loads(out)
    assert _item(doc, "voice-gemini")["estado"] == "SKIP"
    assert "GEMINI_API_KEY" in _item(doc, "voice-gemini")["motivo"]
    assert "TINYFISH_API_KEY" in _item(doc, "busca-consulta")["motivo"]
    assert "docker" in _item(doc, "toonflow")["motivo"]
    assert grav.chamadas == []


def test_porta_do_voicestudio_so_e_sondada_com_sim_gastar(tmp_path, capsys):
    # no plano a porta é só anotada como pendente (sem socket); na execução, sem app, vira SKIP com o motivo
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "voicestudio"], sondas=SondasFalsas(portas=(3900,)))
    assert _item(json.loads(out), "voicestudio")["estado"] == "PLANO"
    grav = Gravador()
    _, out, grav = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "voicestudio"], sondas=SondasFalsas(portas=()),
                         gravador=grav)
    item = _item(json.loads(out), "voicestudio")
    assert item["estado"] == "SKIP" and "3900" in item["motivo"]
    assert grav.chamadas == []


def test_a_chave_do_gemini_habilita_voz_e_swap_gemini_e_nada_mais(tmp_path, capsys):
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA}, portas=())
    rc, out, grav = _roda(tmp_path, capsys, ["--json"], sondas=sondas)
    doc = json.loads(out)
    assert _item(doc, "voice-gemini")["estado"] == "PLANO"
    assert _item(doc, "swap-estimate")["estado"] == "PLANO"
    assert _item(doc, "busca-consulta")["estado"] == "SKIP"
    assert _item(doc, "voicestudio")["estado"] == "PLANO"  # a porta só é sondada com --sim-gastar


def test_chave_do_fal_nao_habilita_o_swap_padrao_do_gemini(tmp_path, capsys):
    sondas = SondasFalsas(chaves={"FAL_KEY": CHAVE_FALSA})
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "swap-run"], sondas=sondas)
    motivo = _item(json.loads(out), "swap-run")["motivo"]
    assert "GEMINI_API_KEY" in motivo


def test_fal_so_vale_com_swap_provider_fal_e_aceito_unverified(tmp_path, capsys):
    base = ["--json", "--apenas", "swap-run", "--autorizo", "--swap-video", str(_arquivo(tmp_path)),
            "--swap-ref", str(_arquivo(tmp_path, "ref.png")), "--swap-provider", "fal"]
    sondas = SondasFalsas(chaves={"FAL_KEY": CHAVE_FALSA})
    _, out, _ = _roda(tmp_path, capsys, base, sondas=sondas)
    assert "aceito-unverified" in _item(json.loads(out), "swap-run")["motivo"]
    _, out, _ = _roda(tmp_path, capsys, base + ["--aceito-unverified"], sondas=sondas)
    assert _item(json.loads(out), "swap-run")["estado"] == "PLANO"


def _arquivo(tmp_path, nome="video.mp4"):
    p = tmp_path / nome
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


# ---------------------------------------------------------------------------------- swap: autorizo, teto, gasto

def test_swap_run_exige_autorizo(tmp_path, capsys):
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA})
    midias = ["--swap-video", str(_arquivo(tmp_path, "V.mp4")), "--swap-ref", str(_arquivo(tmp_path, "R.png"))]
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "swap-run", *midias], sondas=sondas)
    assert "--autorizo" in _item(json.loads(out), "swap-run")["motivo"]


def test_swap_run_exige_as_midias_do_usuario(tmp_path, capsys):
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA})
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "swap-run", "--autorizo"], sondas=sondas)
    assert "--swap-video" in _item(json.loads(out), "swap-run")["motivo"]


def test_teto_padrao_do_swap_e_um_dolar_e_max_usd_substitui(tmp_path, capsys):
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA})
    midias = ["--autorizo", "--swap-video", str(_arquivo(tmp_path, "V.mp4")), "--swap-ref", str(_arquivo(tmp_path, "R.png"))]
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "swap-run", *midias], sondas=sondas)
    assert _item(json.loads(out), "swap-run")["teto_usd"] == 1.0
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "swap-run", "--max-usd", "0.5", *midias], sondas=sondas)
    assert _item(json.loads(out), "swap-run")["teto_usd"] == 0.5


@pytest.mark.parametrize("valor", ["-1", "0", "nan", "inf"])
def test_teto_invalido_e_erro_de_uso(tmp_path, capsys, valor):
    with pytest.raises(SystemExit) as exc:
        e2e.main(["--pasta", str(tmp_path / "e2e"), "--max-usd", valor], sondas=SondasFalsas(), runner=Gravador())
    assert exc.value.code == 2


def test_swap_run_nao_gasta_quando_a_estimativa_passa_do_teto(tmp_path, capsys):
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA})
    grav = Gravador({"swap estimate": _estimativa(2.5), "swap run": _run_swap})
    argv = ["--sim-gastar", "--json", "--apenas", "swap-run", "--autorizo", "--max-usd", "1",
            "--swap-video", str(_arquivo(tmp_path, "V.mp4")), "--swap-ref", str(_arquivo(tmp_path, "R.png"))]
    rc, out, _ = _roda(tmp_path, capsys, argv, sondas=sondas, gravador=grav)
    assert rc == 0
    assert grav.comandos("swap run") == [], "estimativa acima do teto: nada pode ser enviado"
    item = _item(json.loads(out), "swap-run")
    assert item["estado"] == "SKIP" and "teto" in item["motivo"]


def test_swap_run_com_consentimento_passa_yes_teto_e_autorizo(tmp_path, capsys):
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA})
    grav = Gravador({"swap estimate": _estimativa(0.2), "swap run": _run_swap})
    argv = ["--sim-gastar", "--json", "--apenas", "swap-run", "--autorizo",
            "--swap-video", str(_arquivo(tmp_path, "V.mp4")), "--swap-ref", str(_arquivo(tmp_path, "R.png"))]
    rc, out, _ = _roda(tmp_path, capsys, argv, sondas=sondas, gravador=grav)
    assert rc == 0
    run = grav.comandos("swap run")
    assert len(run) == 1
    for trecho in ("--yes", "--autorizo", "--max-usd", "1.0"):
        assert trecho in run[0], trecho
    assert _item(json.loads(out), "swap-run")["estado"] == "PASS"


# --------------------------------------------------------------------------------- build e pago (opcionais)

@pytest.mark.parametrize("extra, motivo", [
    ([], "--incluir-build"),
    (["--incluir-build", "--build-args", "--spec x"], "--max-usd"),
    (["--incluir-build", "--max-usd", "2"], "--build-args"),
])
def test_build_so_roda_com_incluir_build_max_usd_e_args(tmp_path, capsys, extra, motivo):
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "hypit-build", *extra], sondas=SondasFalsas())
    item = _item(json.loads(out), "hypit-build")
    assert item["estado"] == "SKIP" and motivo in item["motivo"]


def test_build_com_as_tres_flags_e_consentimento_chama_clone_build(tmp_path, capsys):
    argv = ["--sim-gastar", "--apenas", "hypit-build", "--incluir-build", "--max-usd", "2", "--build-args", "--spec x.json"]
    _, out, grav = _roda(tmp_path, capsys, argv, sondas=SondasFalsas())
    assert grav.comandos("clone build") and "--spec" in grav.comandos("clone build")[0]


def test_pago_exige_incluir_pago_fonte_e_moneyprinter(tmp_path, capsys):
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "moneyprinter-pago"], sondas=SondasFalsas(mp=True))
    assert "--incluir-pago" in _item(json.loads(out), "moneyprinter-pago")["motivo"]


def test_fonte_paga_desconhecida_e_erro_de_uso(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        e2e.main(["--pasta", str(tmp_path / "e2e"), "--incluir-pago", "--moneyprinter-fonte", "pexels"],
                 sondas=SondasFalsas(mp=True), runner=Gravador())
    assert exc.value.code == 2


def test_media_fetch_exige_url_http_e_autorizo(tmp_path, capsys):
    _, out, _ = _roda(tmp_path, capsys, ["--json", "--apenas", "media-fetch"], sondas=SondasFalsas())
    assert "--url" in _item(json.loads(out), "media-fetch")["motivo"]
    with pytest.raises(SystemExit) as exc:
        e2e.main(["--pasta", str(tmp_path / "e2e"), "--url", "file:///etc/passwd"], sondas=SondasFalsas(), runner=Gravador())
    assert exc.value.code == 2


# ------------------------------------------------------------------------------------ resultado, JSON e segredos

def test_falha_de_check_da_exit_1_e_aparece_no_json(tmp_path, capsys):
    grav = Gravador({"smoke_so.py": e2e.Saida(1, "falhou: 2 de 10", "")})
    rc, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "smoke-so"], gravador=grav)
    doc = json.loads(out)
    assert rc == 1 and doc["resumo"]["FAIL"] == 1
    assert doc["schema"] == "simplicio.e2e-real/v1"
    assert _item(doc, "smoke-so")["estado"] == "FAIL"


def test_json_do_plano_tem_schema_checks_e_custo(tmp_path, capsys):
    rc, out, _ = _roda(tmp_path, capsys, ["--json"], sondas=SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA}))
    doc = json.loads(out)
    assert rc == 0 and doc["schema"] == "simplicio.e2e-real/v1" and doc["modo"] == "plano"
    ids = [c["id"] for c in doc["checks"]]
    assert ids[:2] == ["smoke-so", "smoke-trilhas"]
    assert {"voice-gemini", "swap-estimate", "swap-run", "busca-consulta", "voicestudio", "hypit", "hypit-build",
            "moneyprinter-livre", "moneyprinter-pago", "toonflow", "media-fetch"} <= set(ids)
    assert all("custo_previsto" in c and c["estado"] in {"PLANO", "SKIP"} for c in doc["checks"])


def test_segredo_nunca_sai_na_tela_nem_no_log(tmp_path, capsys):
    grav = Gravador({"smoke_so.py": e2e.Saida(0, f"ecoou {CHAVE_FALSA} aqui", "")})
    rc, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "smoke-so"],
                       sondas=SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA}), gravador=grav)
    assert CHAVE_FALSA not in out
    logs = list((tmp_path / "e2e").rglob("*.log"))
    assert logs and all(CHAVE_FALSA not in p.read_text(encoding="utf-8") for p in logs)


def test_apenas_roda_so_os_pedidos(tmp_path, capsys):
    grav = Gravador()
    rc, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--apenas", "smoke-trilhas"], gravador=grav)
    assert rc == 0
    assert len(grav.chamadas) == 1 and "smoke_trilhas.py" in " ".join(grav.chamadas[0])


def test_apenas_com_nome_desconhecido_e_erro_de_uso(tmp_path):
    with pytest.raises(SystemExit) as exc:
        e2e.main(["--pasta", str(tmp_path / "e2e"), "--apenas", "nao-existe"], sondas=SondasFalsas(), runner=Gravador())
    assert exc.value.code == 2


# ---------------------------------------------------------------------------------------- helpers puros

def test_preparar_contrato_alarga_so_a_copia_e_nao_mexe_no_fixture(tmp_path):
    antes = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    copia = e2e.preparar_contrato(FIXTURE.parent, tmp_path / "mini")
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == antes
    import yaml
    doc = yaml.safe_load(copia.read_text(encoding="utf-8"))
    fala = doc["cenas"][0]["fala"]
    assert fala["max_s"] == e2e.JANELA_FALA_S
    soma = sum(c["duracao_s"] for c in doc["cenas"])
    assert math.isclose(soma, doc["formato"]["duracao_s"])
    assert (copia.parent / "vo" / "line-01.wav").is_file()


def test_plano_nao_roda_subprocesso_nem_abre_socket(tmp_path, capsys, monkeypatch):
    """Prova do plano: com as sondas REAIS, nenhuma chamada a processo, shell ou socket pode acontecer."""
    proibidas = []

    def proibida(nome):
        def falha(*args, **kwargs):
            proibidas.append(nome)
            raise AssertionError(f"{nome} chamado no plano")
        return falha

    for nome in ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
        monkeypatch.setattr(subprocess, nome, proibida(f"subprocess.{nome}"))
    monkeypatch.setattr(os, "system", proibida("os.system"))
    monkeypatch.setattr(os, "popen", proibida("os.popen"))
    monkeypatch.setattr(socket, "socket", proibida("socket.socket"))
    monkeypatch.setattr(socket, "create_connection", proibida("socket.create_connection"))
    rc = e2e.main([], sondas=e2e.SondasReais(), runner=proibida("runner"))
    assert rc == 0
    assert proibidas == []
    out = capsys.readouterr().out
    assert "PLANO" in out and "--sim-gastar" in out


def test_versao_do_node_precisa_ser_22_15_ou_mais():
    assert e2e.node_ok((22, 15, 0)) and e2e.node_ok((23, 0, 0))
    assert not e2e.node_ok((22, 14, 9)) and not e2e.node_ok(None)


def test_sem_o_pacote_so_o_smoke_de_so_continua_planejado(tmp_path, capsys):
    sondas = SondasFalsas(pacote=False, chaves={"GEMINI_API_KEY": CHAVE_FALSA})
    rc, out, grav = _roda(tmp_path, capsys, ["--json"], sondas=sondas)
    doc = json.loads(out)
    assert rc == 0 and grav.chamadas == []
    assert _item(doc, "smoke-so")["estado"] == "PLANO"
    for id_ in ("smoke-trilhas", "voice-gemini", "swap-estimate"):
        assert _item(doc, id_)["estado"] == "SKIP" and "pacote" in _item(doc, id_)["motivo"], id_


def test_custo_do_swap_aparece_no_plano_com_os_segundos_do_sintetico(tmp_path, capsys):
    _, out, _ = _roda(tmp_path, capsys, ["--apenas", "swap-estimate"], sondas=SondasFalsas())
    assert "US$" in out and f"{e2e.DURACAO_SINTETICA_S:g} s" in out


def test_esperar_http_para_quando_responde_e_quando_o_processo_morre():
    respostas = iter([None, None, 200])

    def abrir(url):
        r = next(respostas)
        return r

    vivo = iter([True, True, True, True])
    relogio = iter([0, 1, 2, 3, 4, 5])
    assert e2e.esperar_http("http://127.0.0.1:3000", 60, abrir=abrir, dormir=lambda s: None,
                            agora=lambda: next(relogio), vivo=lambda: next(vivo))

    relogio2 = iter([0, 1, 2])
    assert not e2e.esperar_http("http://127.0.0.1:3000", 60, abrir=lambda u: None, dormir=lambda s: None,
                                agora=lambda: next(relogio2), vivo=lambda: False)


def test_log_do_servidor_passa_pela_redacao(tmp_path):
    """O stdout do `toonflow serve` pode ecoar uma chave: o serve.log só recebe o texto redigido."""
    log = tmp_path / "serve.log"
    filho = [sys.executable, "-c", f"print('erro com {CHAVE_FALSA}', flush=True); print('fim', flush=True)"]
    proc, leitor = e2e._iniciar_servidor(filho, env=dict(os.environ), log=log, segredos=[CHAVE_FALSA])
    assert proc.wait(timeout=60) == 0
    leitor.join(timeout=60)
    texto = log.read_text(encoding="utf-8")
    assert CHAVE_FALSA not in texto
    assert "erro com ***" in texto and "fim" in texto


@pytest.mark.parametrize("flags", [[], ["--sim-gastar"]], ids=["plano", "execucao"])
def test_pasta_nao_vazia_da_rc_2_no_plano_e_na_execucao_sem_tocar_nada(tmp_path, capsys, flags):
    pasta = tmp_path / "usado"
    pasta.mkdir()
    (pasta / "antigo.txt").write_text("não pode ser apagado", encoding="utf-8")
    grav = Gravador()
    with pytest.raises(SystemExit) as exc:
        e2e.main([*flags, "--pasta", str(pasta)], sondas=SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA}), runner=grav)
    assert exc.value.code == 2
    assert grav.chamadas == [], "nenhuma chamada: nem o plano roda processo, nem a execução começa"
    assert sorted(p.name for p in pasta.iterdir()) == ["antigo.txt"], "a pasta usada não ganha nada"


def test_pasta_que_e_arquivo_da_rc_2_sem_traceback(tmp_path, capsys):
    arquivo = tmp_path / "nao-e-pasta.txt"
    arquivo.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        e2e.main(["--sim-gastar", "--pasta", str(arquivo)], sondas=SondasFalsas(), runner=Gravador())
    assert exc.value.code == 2
    assert arquivo.read_text(encoding="utf-8") == "x"


def test_argumentos_puros_sao_validados_antes_de_detectar_a_maquina(tmp_path, monkeypatch):
    """--max-usd 0 e --pasta usada são recusados antes de qualquer leitura da máquina (sondas ou detectar)."""
    def detectar_proibido(*args, **kwargs):
        raise AssertionError("detectar chamado antes da validação dos argumentos puros")

    monkeypatch.setattr(e2e, "detectar", detectar_proibido)
    with pytest.raises(SystemExit) as exc:
        e2e.main(["--max-usd", "0"], sondas=SondasFalsas(), runner=Gravador())
    assert exc.value.code == 2
    pasta = tmp_path / "usado"
    pasta.mkdir()
    (pasta / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        e2e.main(["--pasta", str(pasta)], sondas=SondasFalsas(), runner=Gravador())
    assert exc.value.code == 2


def test_o_roteiro_nao_escreve_bytecode_no_repositorio():
    # o plano importa o pacote para o custo: sem isto ele criaria __pycache__ dentro do repo
    assert sys.dont_write_bytecode is True


def test_ambiente_filho_mantem_caches_e_bytecode_dentro_da_temporaria(tmp_path):
    env = e2e._ambiente_filho({"PATH": "/bin", "SIMPLICIO_OFFLINE": "1"}, tmp_path)
    assert env["npm_config_cache"] == str(tmp_path / "npm-cache")
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "SIMPLICIO_OFFLINE" not in env


def test_so_um_ffmpeg_gera_a_midia_sintetica_e_o_avatar_vem_do_repositorio(tmp_path, capsys):
    """A mídia sintética gasta uma chamada ao ffmpeg (o repo não tem vídeo de teste); a imagem é copiada do repo."""
    def ffmpeg_grava(argv):
        Path(argv[-1]).write_bytes(b"midia")  # como o ffmpeg de verdade: o arquivo de saída passa a existir
        return e2e.Saida(0, "", "")

    grav = Gravador({"/bin/ffmpeg": ffmpeg_grava})  # casa pelo binário, nunca por substring (o caminho tem o nome do teste)
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA}, mp=True)
    _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "swap-estimate,moneyprinter-livre"], sondas=sondas,
          gravador=grav)
    ffmpeg = [c for c in grav.chamadas if c[0] == "/bin/ffmpeg"]
    assert len(ffmpeg) == 1, ffmpeg
    estimativa = grav.comandos("swap estimate")[0]
    ref = estimativa[estimativa.index("--ref") + 1]
    assert Path(ref).name == "avatar.png" and Path(ref).is_file()


def test_falha_do_ffmpeg_e_memorizada_e_nao_roda_de_novo(tmp_path, capsys):
    grav = Gravador({"/bin/ffmpeg": e2e.Saida(1, "", "erro do ffmpeg")})
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA}, mp=True)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "swap-estimate,moneyprinter-livre"],
                      sondas=sondas, gravador=grav)
    assert len([c for c in grav.chamadas if c[0] == "/bin/ffmpeg"]) == 1, "uma falha não pode disparar nova tentativa"
    doc = json.loads(out)
    assert _item(doc, "swap-estimate")["estado"] == "FAIL"
    assert _item(doc, "moneyprinter-livre")["estado"] == "FAIL"


def test_toonflow_usa_o_serve_como_checagem_do_docker_e_nao_chama_docker_pelo_executor(tmp_path, capsys, monkeypatch):
    class Morto:
        def poll(self):
            return 1

        def wait(self, timeout=None):
            return 1

    class Leitor:
        def join(self, timeout=None):
            return None

    lancados = []

    def lancar(argv, **kwargs):
        lancados.append(list(argv))
        return Morto(), Leitor()

    def popen_proibido(*args, **kwargs):
        raise AssertionError("subprocess.Popen direto: o serve tem de sair por _iniciar_servidor (testável)")

    monkeypatch.setattr(e2e, "_iniciar_servidor", lancar)
    monkeypatch.setattr(e2e, "esperar_http", lambda *a, **k: None)
    monkeypatch.setattr(e2e, "_porta_ocupada", lambda porta: False)
    monkeypatch.setattr(subprocess, "Popen", popen_proibido)
    grav = Gravador()
    _, out, grav = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                         sondas=SondasFalsas(toonflow=True), gravador=grav)
    assert not any("docker" in " ".join(c) for c in grav.chamadas), grav.chamadas
    assert any("toonflow" in " ".join(c) and "serve" in " ".join(c) for c in lancados)
    assert _item(json.loads(out), "toonflow")["estado"] == "FAIL"


class _Morto:
    def poll(self):
        return 1

    def wait(self, timeout=None):
        return 1


class _Vivo:
    pid = os.getpid()  # processo de mentira com pid real: o dono da porta lê a árvore a partir dele

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


class _Leitor:
    def join(self, timeout=None):
        return None


def test_toonflow_pass_so_com_o_serve_vivo_quando_responde(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(e2e, "_diagnostico_dono", lambda proc, porta: (True, "mock"))  # o dono é testado à parte (B3)
    monkeypatch.setattr(e2e, "JANELA_VIVO_S", 0)
    monkeypatch.setattr(e2e, "_porta_ocupada", lambda porta: False)
    monkeypatch.setattr(e2e, "esperar_http", lambda *a, **k: 200)
    monkeypatch.setattr(e2e, "_iniciar_servidor", lambda argv, **kw: (_Vivo(), _Leitor()))
    monkeypatch.setattr(e2e, "_parar_processo", lambda proc, espera_s=120: None)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    item = _item(json.loads(out), "toonflow")
    assert item["estado"] == "PASS" and "200" in item["detalhe"]


def test_toonflow_serve_que_morreu_nao_da_pass_mesmo_com_http(tmp_path, capsys, monkeypatch):
    # outro processo pode ter respondido, ou o serve caiu logo depois: o PASS exige o processo lançado vivo
    monkeypatch.setattr(e2e, "_porta_ocupada", lambda porta: False)
    monkeypatch.setattr(e2e, "esperar_http", lambda *a, **k: 200)
    monkeypatch.setattr(e2e, "_iniciar_servidor", lambda argv, **kw: (_Morto(), _Leitor()))
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    assert _item(json.loads(out), "toonflow")["estado"] == "FAIL"


@pytest.mark.allow_hosts(["127.0.0.1", "localhost"])
def test_toonflow_com_outro_servidor_na_porta_da_falha_e_nao_sobe_o_serve(tmp_path, capsys, monkeypatch):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        monkeypatch.setattr(e2e, "PORTA_TOONFLOW", srv.getsockname()[1])
        lancados = []
        monkeypatch.setattr(e2e, "_iniciar_servidor", lambda argv, **kw: (lancados.append(argv), (_Morto(), _Leitor()))[1])
        _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                          sondas=SondasFalsas(toonflow=True), gravador=Gravador())
        item = _item(json.loads(out), "toonflow")
        assert item["estado"] == "FAIL" and "ocupad" in item["detalhe"]
        assert lancados == [], "com a porta ocupada o serve não pode ser lançado"
    finally:
        srv.close()


# ----------------------------------------------------------------------------- hypit: clone pricing

def test_hypit_pricing_recebe_a_fonte_pela_flag(tmp_path, capsys):
    grav = Gravador()
    _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "hypit", "--hypit-fonte", "minha-run"],
          sondas=SondasFalsas(), gravador=grav)
    assert grav.comandos("clone pricing")[0][-3:] == ["clone", "pricing", "minha-run"]
    assert grav.comandos("clone doctor"), "o doctor continua no check"


@pytest.mark.parametrize("flags", [[], ["--sim-gastar"]], ids=["plano", "execucao"])
def test_hypit_pricing_sem_fonte_nao_roda_e_diz_o_que_falta(tmp_path, capsys, flags):
    grav = Gravador()
    _, out, _ = _roda(tmp_path, capsys, [*flags, "--json", "--apenas", "hypit"], sondas=SondasFalsas(), gravador=grav)
    item = _item(json.loads(out), "hypit")
    assert item["estado"] == "SKIP" and "--hypit-fonte" in item["motivo"]
    assert grav.comandos("clone pricing") == [], "clone pricing sem fonte falha sempre: não pode rodar"


# ----------------------------------------------------------------------------- redação

def test_chave_curta_tambem_e_redigida():
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": "abc"})
    amb = e2e.detectar(sondas, sondar=False)
    assert "abc" in e2e._segredos(sondas, amb)


def test_segredo_partido_entre_pedacos_e_redigido():
    r = e2e.Redator(["chave-dividida-0123"])
    saida = r.alimentar("antes chave-divi") + r.alimentar("dida-0123 depois") + r.finalizar()
    assert "chave-divi" not in saida and "dida-0123" not in saida
    assert "antes" in saida and "depois" in saida and "***" in saida


def test_segredo_com_quebra_de_linha_e_redigido_no_fluxo():
    s = "linha-um\nlinha-dois-0123"
    r = e2e.Redator([s])
    saida = r.alimentar("inicio linha-um\n") + r.alimentar("linha-dois-0123 fim\n") + r.finalizar()
    assert "linha-um" not in saida and "linha-dois" not in saida
    assert "***" in saida and "inicio" in saida and "fim" in saida


def test_log_do_servidor_redige_segredo_com_quebra_de_linha(tmp_path):
    s = "linha-um\nlinha-dois-0123456"
    log = tmp_path / "serve.log"
    filho = [sys.executable, "-c", "import sys; sys.stdout.write(%r); sys.stdout.flush()" % ("pre " + s + " pos\n")]
    proc, leitor = e2e._iniciar_servidor(filho, env=dict(os.environ), log=log, segredos=[s])
    assert proc.wait(timeout=60) == 0
    leitor.join(timeout=60)
    texto = log.read_text(encoding="utf-8")
    assert "linha-dois-0123456" not in texto and "linha-um" not in texto
    assert "***" in texto and "pre" in texto and "pos" in texto


def test_chave_do_config_do_moneyprinter_entra_na_redacao(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[llm]\napi_key = "chave-config-mp-0123"\n\n[vazio]\napi_key = ""\n', encoding="utf-8")
    sondas = SondasFalsas(config_mp=cfg)
    amb = e2e.detectar(sondas, sondar=False)
    segredos = e2e._segredos(sondas, amb)
    assert "chave-config-mp-0123" in segredos
    assert "" not in segredos


# ----------------------------------------------------------------------- terceira revisão: vazamento, listas,
# redator, limites de saída, janela do Toonflow, --pasta em arquivo e validação antes da máquina

NOMES_SEGREDO_EXTRA = ["VOICESTUDIO_API_KEY", "XAI_API_KEY", "ELEVENLABS_API_KEY", "GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY",
                       "OMNIVOICE_API_KEY", "ACME_PASSWORD_X"]


def test_segredos_inclui_toda_variavel_com_key_token_secret_ou_password_e_so_essas():
    ambiente = {n: f"valor-{i}-{n.lower()}" for i, n in enumerate(NOMES_SEGREDO_EXTRA)}
    ambiente["ORDINARIA_SEM_SEGREDO"] = "nao-mexer-1234"
    sondas = SondasFalsas(chaves=ambiente)
    amb = e2e.detectar(sondas, sondar=False)
    segredos = e2e._segredos(sondas, amb)
    assert set(ambiente[n] for n in NOMES_SEGREDO_EXTRA) <= set(segredos)
    assert "nao-mexer-1234" not in segredos


@pytest.mark.parametrize("nome", NOMES_SEGREDO_EXTRA)
def test_filho_que_ecoa_cada_variavel_secreta_nao_vaza_no_log(tmp_path, nome):
    valor = f"valor-secreto-{nome.lower()}-0123"
    ambiente = dict(os.environ)
    ambiente[nome] = valor
    sondas = SondasFalsas(chaves={nome: valor})
    amb = e2e.detectar(sondas, sondar=False)
    segredos = e2e._segredos(sondas, amb)
    log = tmp_path / f"{nome}.log"
    filho = [sys.executable, "-c", f"import os; print('eco', os.environ[{nome!r}], 'fim', flush=True)"]
    proc, leitor = e2e._iniciar_servidor(filho, env=ambiente, log=log, segredos=segredos)
    assert proc.wait(timeout=60) == 0
    leitor.join(timeout=60)
    texto = log.read_text(encoding="utf-8")
    assert valor not in texto and "eco" in texto and "***" in texto


def test_listas_do_config_do_moneyprinter_entram_na_redacao(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[app]\npexels_api_keys = ["lista-um-0001", "lista-dois-0002"]\n', encoding="utf-8")
    sondas = SondasFalsas(config_mp=cfg)
    amb = e2e.detectar(sondas, sondar=False)
    assert {"lista-um-0001", "lista-dois-0002"} <= set(e2e._segredos(sondas, amb))


def test_listas_do_config_pelo_caminho_por_linha():
    texto = 'pexels_api_keys = ["lista-a-0001", "lista-b-0002"]\nname = "nao-secreto"\n'
    achados = e2e._valores_por_regex(texto)
    assert {"lista-a-0001", "lista-b-0002"} <= achados
    assert "nao-secreto" not in achados


def test_redator_nao_deixa_sair_um_segredo_que_cruza_o_corte():
    r = e2e.Redator(["ABCD", "CDX"])
    assert r.alimentar("ABCD") + r.finalizar() == "***"


def test_redator_3mb_de_abab_termina_rapido_e_retem_no_maximo_3_bytes():
    import time
    r = e2e.Redator(["abab"])
    texto = "ab" * (3 * 1024 * 1024 // 2) + "a"  # 3 MB, termina num começo de segredo
    inicio = time.perf_counter()
    saida = r.alimentar(texto)
    decorrido = time.perf_counter() - inicio
    assert decorrido < 2.0, f"{decorrido:.2f} s"
    assert len(r.resto) <= 3, len(r.resto)
    saida += r.finalizar()
    assert "abab" not in saida and saida.count("***") > 0


def test_redator_equivale_a_redigir_o_texto_inteiro_quando_nao_ha_sobreposicao():
    import random
    rnd = random.Random(20260505)
    segredos = ["chave-a-01", "zz9-segredo"]  # nenhum começa com pedaço do outro: não há sobreposição entre eles
    alfabeto = "chave-a-01zz9segredo xyz\n"
    for _ in range(300):
        texto = "".join(rnd.choice(alfabeto) for _ in range(rnd.randint(0, 200)))
        for _ in range(rnd.randint(0, 3)):
            pos = rnd.randint(0, len(texto))
            texto = texto[:pos] + rnd.choice(segredos) + texto[pos:]
        cortes = sorted(rnd.sample(range(len(texto) + 1), min(len(texto) + 1, rnd.randint(0, 10))))
        pedacos = [texto[a:b] for a, b in zip([0] + cortes, cortes + [len(texto)])]
        r = e2e.Redator(segredos)
        saida = "".join(r.alimentar(p) for p in pedacos) + r.finalizar()
        assert saida == e2e.redigir(texto, segredos)


def test_redator_nunca_deixa_um_segredo_inteiro_sair_mesmo_com_sobreposicao():
    import random
    rnd = random.Random(7)
    segredos = ["aba", "bab", "ab"]
    for _ in range(400):
        texto = "".join(rnd.choice("abx") for _ in range(rnd.randint(0, 120)))
        cortes = sorted(rnd.sample(range(len(texto) + 1), min(len(texto) + 1, rnd.randint(0, 8))))
        pedacos = [texto[a:b] for a, b in zip([0] + cortes, cortes + [len(texto)])]
        r = e2e.Redator(segredos)
        saida = "".join(r.alimentar(p) for p in pedacos) + r.finalizar()
        assert not any(s in saida for s in segredos), (texto, pedacos, saida)


def test_saida_de_processo_e_limitada_a_uma_cauda():
    argv = [sys.executable, "-c", "import sys; sys.stdout.write('x' * (3 * 1024 * 1024)); sys.stdout.write('FIM'); "
                                  "sys.stderr.write('e' * 10)"]
    saida = e2e._rodar(argv, env=dict(os.environ), cwd=Path(e2e.REPO), timeout=120)
    assert saida.rc == 0
    assert len(saida.out) <= e2e.TETO_CAUDA + 500
    assert saida.out.endswith("FIM")


def test_log_do_servidor_guarda_so_a_cauda_redigida(tmp_path):
    log = tmp_path / "serve.log"
    filho = [sys.executable, "-c", "import sys; sys.stdout.write('y' * (3 * 1024 * 1024) + '\\nfim\\n'); sys.stdout.flush()"]
    proc, leitor = e2e._iniciar_servidor(filho, env=dict(os.environ), log=log, segredos=[])
    proc.wait(timeout=120)
    leitor.join(timeout=120)
    texto = log.read_text(encoding="utf-8")
    assert len(texto) <= e2e.TETO_CAUDA + 500
    assert texto.rstrip().endswith("fim")


def _toonflow_com_processo_real(monkeypatch, codigo_filho, janela):
    real = e2e._iniciar_servidor
    monkeypatch.setattr(e2e, "_porta_ocupada", lambda porta: False)
    monkeypatch.setattr(e2e, "esperar_http", lambda *a, **k: 200)
    monkeypatch.setattr(e2e, "JANELA_VIVO_S", janela)
    monkeypatch.setattr(e2e, "_iniciar_servidor",
                        lambda argv, **kw: real([sys.executable, "-c", codigo_filho], **kw))


def test_toonflow_que_morre_dentro_da_janela_da_fail(tmp_path, capsys, monkeypatch):
    _toonflow_com_processo_real(monkeypatch, "import time; time.sleep(0.5)", janela=2.0)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    item = _item(json.loads(out), "toonflow")
    assert item["estado"] == "FAIL", item


def test_toonflow_que_sobrevive_a_janela_da_pass(tmp_path, capsys, monkeypatch):
    _toonflow_com_processo_real(monkeypatch, "import time; time.sleep(60)", janela=0.5)
    monkeypatch.setattr(e2e, "_diagnostico_dono", lambda proc, porta: (True, "mock"))  # o dono é testado à parte (B3)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    assert _item(json.loads(out), "toonflow")["estado"] == "PASS"


@pytest.mark.parametrize("flags", [[], ["--sim-gastar"]], ids=["plano", "execucao"])
def test_pasta_dentro_de_arquivo_da_rc_2_sem_traceback(tmp_path, flags):
    arquivo = tmp_path / "arquivo.txt"
    arquivo.write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        e2e.main([*flags, "--pasta", str(arquivo / "sub")], sondas=SondasFalsas(), runner=Gravador())
    assert exc.value.code == 2


def test_valor_curto_de_segredo_nao_quebra_o_json_do_swap_estimate(tmp_path, capsys):
    """Regressão: um segredo de um caractere (valor '1') trocava o dígito 1 do JSON antes da leitura e o check falhava.
    A leitura de números e de JSON usa a saída sem redação; o log e o relatório continuam redigidos."""
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": CHAVE_FALSA, "ALGUMA_TOKEN": "1"})
    grav = Gravador({"swap estimate": _estimativa(0.5)})  # o JSON traz "chunks": 1
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "swap-estimate"], sondas=sondas, gravador=grav)
    assert _item(json.loads(out), "swap-estimate")["estado"] == "PASS"


def test_swap_provider_e_fonte_paga_invalidos_da_rc_2_antes_de_detectar(monkeypatch):
    def detectar_proibido(*args, **kwargs):
        raise AssertionError("detectar chamado antes da validação dos argumentos")

    monkeypatch.setattr(e2e, "detectar", detectar_proibido)
    for argv in (["--swap-provider", "nao-existe"], ["--moneyprinter-fonte", "pexels"]):
        with pytest.raises(SystemExit) as exc:
            e2e.main(argv, sondas=SondasFalsas(), runner=Gravador())
        assert exc.value.code == 2, argv


# ------------------------------------------------------------------ quarta revisão (revisor 4): B1, B2, B3, N1 a N7
import http.server  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

SEG_CORTE = "SEGREDO-NA-FRONTEIRA-0123456789-ABC"  # 35 caracteres, sem "." nem "*" (o enchimento do teste é ".")
SEG_FORMAS = {
    "aspas": ('pw"SEGREDO-aspas', ["SEGREDO-aspas"]),
    "quebra": ("linha-um-SEG\nlinha-dois-SEG", ["linha-um-SEG", "linha-dois-SEG"]),
    "nao_ascii": ("senha-ção-123", ["senha-", "u00e7"]),
    "barra": ("caminho\\SEGREDO-barra", ["SEGREDO-barra"]),
}


def _formas_de(seg):
    return {seg, json.dumps(seg)[1:-1], json.dumps(seg, ensure_ascii=False)[1:-1], repr(seg)[1:-1],
            ascii(seg)[1:-1], json.dumps(json.dumps(seg))[1:-1]} - {""}


def _porta_livre():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


LINUX_SEM_PROC = pytest.mark.skipif(not Path("/proc/net/tcp").exists(), reason="dono da porta pelo /proc (Linux)")


# B1 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("k", [1, 10, 25, 34])
def test_b1_segredo_na_fronteira_do_corte_de_1mib_nao_deixa_sufixo_no_log_nem_no_passo(tmp_path, k):
    seg = SEG_CORTE
    assert len(seg) == 35
    # a saída bruta tem TETO+1000+k caracteres: o corte de 1 MiB cai k caracteres dentro do segredo
    # o nome da variável é minúsculo: o argv vai para o log e um "C" maiúsculo de "ECO" seria falso sufixo
    codigo = ("import os,sys; sys.stdout.write('.' * 1000 + os.environ['eco'] + '.' * (%d)); sys.stdout.flush()"
              % (e2e.TETO_CAUDA - len(seg) + k))
    env = dict(os.environ, eco=seg)
    (tmp_path / "run").mkdir()
    ctx = e2e.Ctx(tmp_path / "run", None, lambda argv, **kw: e2e._rodar(argv, segredos=[seg], **kw), env, None,
                  [seg], 1.0)
    p = ctx.passo("eco", [sys.executable, "-c", codigo], 120)
    log = Path(p.log).read_text(encoding="utf-8")
    assert p.rc == 0
    for j in range(1, len(seg)):
        assert seg[j:] not in log, (j, "log")
        assert seg[j:] not in p.saida, (j, "passo")
    assert seg not in p.saida and seg not in log


def test_b1_rodar_redige_a_cauda_antes_de_cortar(tmp_path):
    seg = SEG_CORTE
    codigo = ("import os,sys; sys.stdout.write('.' * 1000 + os.environ['eco'] + '.' * %d); sys.stdout.flush()"
              % (e2e.TETO_CAUDA - len(seg) + 10))
    saida = e2e._rodar([sys.executable, "-c", codigo], env=dict(os.environ, eco=seg), cwd=Path(e2e.REPO), timeout=120,
                       segredos=[seg])
    assert all(seg[j:] not in saida.out for j in range(1, len(seg)))


# B2 ------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("nome", list(SEG_FORMAS))
def test_b2_forma_escapada_do_json_e_redigida(nome):
    seg, _ = SEG_FORMAS[nome]
    textos = [json.dumps({"erro": seg}), json.dumps({"erro": seg}, ensure_ascii=False), "repr: " + repr(seg)]
    for texto in textos:
        redigido = e2e.redigir(texto, [seg])
        assert not any(f in redigido for f in _formas_de(seg)), (texto, redigido)


@pytest.mark.parametrize("nome", list(SEG_FORMAS))
def test_b2_forma_escapada_partida_em_qualquer_corte_do_redator(nome):
    seg, _ = SEG_FORMAS[nome]
    # termina em "." (não é começo de segredo): um "s" final seria redigido pela regra do fim do fluxo
    texto = "antes " + json.dumps({"erro": seg}) + " depois."
    for i in range(len(texto) + 1):
        r = e2e.Redator([seg])
        saida = r.alimentar(texto[:i]) + r.alimentar(texto[i:]) + r.finalizar()
        assert not any(f in saida for f in _formas_de(seg)), (i, saida)
        assert "antes" in saida and "depois." in saida


_IMPRIME_FORMAS = ("import os, json, sys; s = os.environ['ECO_SEG']; "
                   "print(json.dumps({'erro': s})); print(json.dumps({'erro': s}, ensure_ascii=False)); "
                   "print(repr(s)); sys.stderr.write(json.dumps(s) + chr(10))")


@pytest.mark.parametrize("nome", list(SEG_FORMAS))
def test_b2_log_do_passo_nao_tem_forma_escapada(tmp_path, nome):
    seg, pedacos = SEG_FORMAS[nome]
    (tmp_path / "run").mkdir()
    env = dict(os.environ, ECO_SEG=seg)
    ctx = e2e.Ctx(tmp_path / "run", None, lambda argv, **kw: e2e._rodar(argv, segredos=[seg], **kw), env, None,
                  [seg], 1.0)
    p = ctx.passo("imprime", [sys.executable, "-c", _IMPRIME_FORMAS], 120)
    log = Path(p.log).read_text(encoding="utf-8")
    for texto in (log, p.saida, p.erro):
        assert not any(f in texto for f in _formas_de(seg)), texto
        assert not any(t in texto for t in pedacos), texto


@pytest.mark.parametrize("nome", list(SEG_FORMAS))
def test_b2_serve_log_nao_tem_forma_escapada(tmp_path, nome):
    seg, pedacos = SEG_FORMAS[nome]
    log = tmp_path / "serve.log"
    proc, leitor = e2e._iniciar_servidor([sys.executable, "-c", _IMPRIME_FORMAS], env=dict(os.environ, ECO_SEG=seg),
                                         log=log, segredos=[seg])
    assert proc.wait(timeout=60) == 0
    leitor.join(timeout=60)
    texto = log.read_text(encoding="utf-8")
    assert not any(f in texto for f in _formas_de(seg)), texto
    assert not any(t in texto for t in pedacos), texto


@pytest.mark.parametrize("nome", list(SEG_FORMAS))
def test_b2_json_e_tabela_do_main_nao_tem_forma_escapada(tmp_path, capsys, nome):
    seg, pedacos = SEG_FORMAS[nome]
    # a última linha vira o detalhe da tabela e do JSON: é nela que a forma escapada do JSON precisa sair redigida
    corpo = repr(seg) + "\n" + json.dumps({"erro": seg}, ensure_ascii=False) + "\n" + json.dumps({"erro": seg})
    grav = Gravador({"smoke_so.py": e2e.Saida(0, corpo, json.dumps(seg))})
    rc = e2e.main(["--pasta", str(tmp_path / "e2e"), "--sim-gastar", "--json", "--apenas", "smoke-so"],
                  sondas=SondasFalsas(chaves={"GEMINI_API_KEY": seg}), runner=grav)
    captura = capsys.readouterr()
    assert rc == 0
    for texto in (captura.out, captura.err):
        assert not any(t in texto for t in pedacos), texto
        assert not any(f in texto for f in _formas_de(seg)), texto


# B3, N1, N3, N4 -------------------------------------------------------------------------------------------------
def _toonflow_mocks(monkeypatch, *, porta=None, esperar=200, dono=True, vivo=None, janela=0):
    monkeypatch.setattr(e2e, "_porta_ocupada", lambda p: False)
    monkeypatch.setattr(e2e, "esperar_http", lambda *a, **k: esperar)
    monkeypatch.setattr(e2e, "_iniciar_servidor", lambda argv, **kw: (vivo or _Vivo(), _Leitor()))
    monkeypatch.setattr(e2e, "_parar_processo", lambda proc, espera_s=120: None)
    monkeypatch.setattr(e2e, "JANELA_VIVO_S", janela)
    monkeypatch.setattr(e2e, "_diagnostico_dono", lambda proc, p: (dono, "mock"), raising=False)
    if porta is not None:
        monkeypatch.setattr(e2e, "PORTA_TOONFLOW", porta)


@pytest.mark.parametrize("codigo", [500, 404])
def test_n3_http_de_erro_do_serve_nao_da_pass(tmp_path, capsys, monkeypatch, codigo):
    _toonflow_mocks(monkeypatch, esperar=codigo, dono=True)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    item = _item(json.loads(out), "toonflow")
    assert item["estado"] == "FAIL" and str(codigo) in item["detalhe"], item


@pytest.mark.parametrize("codigo", [200, 302])
def test_n3_2xx_e_3xx_com_dono_confirmado_da_pass(tmp_path, capsys, monkeypatch, codigo):
    _toonflow_mocks(monkeypatch, esperar=codigo, dono=True)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    assert _item(json.loads(out), "toonflow")["estado"] == "PASS"


def test_b3_sem_como_confirmar_o_dono_da_porta_da_skip_e_nunca_pass(tmp_path, capsys, monkeypatch):
    _toonflow_mocks(monkeypatch, esperar=200, dono=None)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    item = _item(json.loads(out), "toonflow")
    assert item["estado"] == "SKIP" and "UNVERIFIED" in item["motivo"] + item["detalhe"], item


def test_b3_dono_recusado_da_fail_com_o_outro_processo(tmp_path, capsys, monkeypatch):
    _toonflow_mocks(monkeypatch, esperar=200, dono=False)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    assert _item(json.loads(out), "toonflow")["estado"] == "FAIL"


def test_n4_serve_que_morre_depois_do_200_diz_que_ele_morreu(tmp_path, capsys, monkeypatch):
    _toonflow_mocks(monkeypatch, esperar=200, dono=True, vivo=_Morto(), janela=3.0)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    item = _item(json.loads(out), "toonflow")
    assert item["estado"] == "FAIL"
    assert "outro processo" not in item["detalhe"] and ("saiu" in item["detalhe"] or "morr" in item["detalhe"]), item


CODIGO_SERVE_MORRE_1S = """
import http.server, os, threading
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header('Content-Length', '2'); self.end_headers(); self.wfile.write(b'ok')
        threading.Timer(1.0, lambda: os._exit(0)).start()
    def log_message(self, *a):
        pass
http.server.ThreadingHTTPServer(('127.0.0.1', PORTA), H).serve_forever()
"""


@pytest.mark.allow_hosts(["127.0.0.1", "localhost"])
def test_n1_sem_janela_explicita_serve_que_morre_1s_apos_o_200_da_fail(tmp_path, capsys, monkeypatch):
    porta = _porta_livre()
    codigo = CODIGO_SERVE_MORRE_1S.replace("PORTA", str(porta))
    monkeypatch.setattr(e2e, "PORTA_TOONFLOW", porta)
    monkeypatch.setattr(e2e, "_py", lambda *a: [sys.executable, "-c", "print('{}')"] if a[:2] == ("toonflow", "status")
                        else [sys.executable, "-c", codigo])
    assert e2e.JANELA_VIVO_S == 3.0  # o teste não troca a janela: é a janela padrão que decide
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    assert _item(json.loads(out), "toonflow")["estado"] == "FAIL"


def _listener_em_outro_processo(porta):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", "5")
            self.end_headers()
            self.wfile.write(b"outro")

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", porta), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@LINUX_SEM_PROC
@pytest.mark.allow_hosts(["127.0.0.1", "localhost"])
def test_b3_outro_processo_que_ouve_a_porta_depois_do_precheck_nao_da_pass(tmp_path, capsys, monkeypatch):
    porta = _porta_livre()
    servidores = []

    def precheck(p):  # o outro processo começa a ouvir DEPOIS do pré-check
        if not servidores:
            servidores.append(_listener_em_outro_processo(porta))
        return False

    monkeypatch.setattr(e2e, "PORTA_TOONFLOW", porta)
    monkeypatch.setattr(e2e, "_porta_ocupada", precheck)
    monkeypatch.setattr(e2e, "_docker_publica", lambda p: False, raising=False)  # o docker não publica a porta para o serve lançado
    monkeypatch.setattr(e2e, "_py", lambda *a: [sys.executable, "-c", "print('{}')"] if a[:2] == ("toonflow", "status")
                        else [sys.executable, "-c", "import time; time.sleep(60)"])  # vivo, nunca escuta
    try:
        _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                          sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    finally:
        for srv in servidores:
            srv.shutdown()
            srv.server_close()
    item = _item(json.loads(out), "toonflow")
    assert item["estado"] == "FAIL", item


@LINUX_SEM_PROC
@pytest.mark.allow_hosts(["127.0.0.1", "localhost"])
def test_b3_dono_da_porta_confirma_o_filho_que_ouve(monkeypatch):
    porta = _porta_livre()
    codigo = (f"import socket,time; s=socket.socket(); s.bind(('127.0.0.1',{porta})); s.listen(1); "
              "print('ok', flush=True); time.sleep(60)")
    proc = subprocess.Popen([sys.executable, "-c", codigo], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ok"
        monkeypatch.setattr(e2e, "_docker_publica", lambda p: None, raising=False)  # a árvore basta: o docker não é consultado
        assert e2e._dono_da_porta(proc, porta) is True
    finally:
        proc.kill()
        proc.wait()


@LINUX_SEM_PROC
@pytest.mark.allow_hosts(["127.0.0.1", "localhost"])
def test_b3_dono_da_porta_recusa_quem_so_ouve_de_fora(monkeypatch):
    porta = _porta_livre()
    srv = _listener_em_outro_processo(porta)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        monkeypatch.setattr(e2e, "_docker_publica", lambda p: False, raising=False)
        assert e2e._dono_da_porta(proc, porta) is False
        monkeypatch.setattr(e2e, "_docker_publica", lambda p: None, raising=False)
        assert e2e._dono_da_porta(proc, porta) is None
    finally:
        proc.kill()
        proc.wait()
        srv.shutdown()
        srv.server_close()


# N2 -----------------------------------------------------------------------------------------------------------
def test_n2_serve_log_e_gravado_enquanto_o_filho_vive(tmp_path):
    log = tmp_path / "serve.log"
    filho = [sys.executable, "-c", "import time; print('linha-1-visivel', flush=True); time.sleep(4); "
                                   "print('linha-2', flush=True)"]
    proc, leitor = e2e._iniciar_servidor(filho, env=dict(os.environ), log=log, segredos=[])

    def conteudo():
        return log.read_text(encoding="utf-8") if log.exists() else ""

    try:
        limite = time.monotonic() + 3
        while time.monotonic() < limite and "linha-1-visivel" not in conteudo():
            time.sleep(0.1)
        assert proc.poll() is None, "o filho saiu antes da checagem: o teste não prova nada"
        assert "linha-1-visivel" in conteudo()
    finally:
        proc.wait(timeout=60)
        leitor.join(timeout=60)
    assert "linha-2" in conteudo()


# N5 -----------------------------------------------------------------------------------------------------------
CASOS_CONFIG = [
    ("C1 lista numa linha", 'pexels_api_keys = ["lista-a-1111", "lista-b-2222"]\n', "lista-b-2222"),
    ("C2 lista multilinha", 'pexels_api_keys = [\n    "multi-c-3333",\n    "multi-d-4444",\n]\n', "multi-d-4444"),
    ("C3 string em [app]", '[app]\nllm_api_key = "str-e-5555"\n', "str-e-5555"),
    ("C4 array de tabelas", '[[providers]]\napi_key = "aot-f-6666"\n', "aot-f-6666"),
    ("C5 aspas simples", "'literal_token' = 'lit-g-7777'\n", "lit-g-7777"),
    ("C6 tabela aninhada", '[tts.azure]\nspeech_key = "nest-h-8888"\n', "nest-h-8888"),
    ("C7 escape no valor", 'password = "pa\\"ss-i-9999"\n', 'pa"ss-i-9999'),
    ("C8 tabela inline", 'tts = { api_key = "inline-j-1010" }\n', "inline-j-1010"),
    ("C9 lista aspas simples", "wavespeed_keys = ['sq-k-1212']\n", "sq-k-1212"),
    ("C10 nome nao secreto", 'name = "nao-secreto-zz"\n', None),
]


@pytest.mark.parametrize("nome,texto,esperado", CASOS_CONFIG, ids=[c[0] for c in CASOS_CONFIG])
def test_n5_config_do_moneyprinter_com_tomllib(tmp_path, nome, texto, esperado):
    cfg = tmp_path / "config.toml"
    cfg.write_text(texto, encoding="utf-8")
    achados = e2e._valores_do_config(cfg)
    assert (esperado in achados) if esperado else not achados, achados


@pytest.mark.parametrize("nome,texto,esperado", CASOS_CONFIG, ids=[c[0] for c in CASOS_CONFIG])
def test_n5_config_do_moneyprinter_sem_tomllib(tmp_path, monkeypatch, nome, texto, esperado):
    monkeypatch.setitem(sys.modules, "tomllib", None)  # Python 3.10: o caminho por leitura
    cfg = tmp_path / "config.toml"
    cfg.write_text(texto, encoding="utf-8")
    achados = e2e._valores_do_config(cfg)
    assert (esperado in achados) if esperado else not achados, achados


# N7 -----------------------------------------------------------------------------------------------------------
def test_n7_pasta_que_nao_pode_ser_criada_da_rc_2_antes_de_qualquer_sonda(capsys):
    chamadas = []

    class Sondas(SondasFalsas):
        def versao(self, argv):
            chamadas.append(("versao", argv))
            return super().versao(argv)

        def porta_aberta(self, host, porta):
            chamadas.append(("porta", porta))
            return False

    with pytest.raises(SystemExit) as exc:
        e2e.main(["--sim-gastar", "--pasta", "/proc/nao-cria-aqui/sub"], sondas=Sondas(), runner=Gravador())
    assert exc.value.code == 2
    assert chamadas == [], chamadas


import io  # noqa: E402

# ------------------------------------------------------- quinta revisão (revisor 5): itens 1 a 7
# 1. prefixo do segredo no fim do fluxo
@pytest.mark.parametrize("k", range(1, len(SEG_CORTE)))
def test_r5_prefixo_do_segredo_no_fim_do_fluxo_nao_sai_cru(k):
    seg = SEG_CORTE
    r = e2e.Redator([seg])
    saida = r.alimentar("fim " + seg[:k]) + r.finalizar()
    assert not saida.endswith(seg[:k]) and seg[:k] not in saida, saida


@pytest.mark.parametrize("k", [1, 5, 20, 34])
def test_r5_prefixo_do_segredo_no_fim_do_fluxo_pelo_cauda_e_pelo_drenar(tmp_path, k):
    seg = SEG_CORTE
    cauda = e2e._Cauda(io.BytesIO(("linha " + seg[:k]).encode("utf-8")), [seg]).texto()
    assert seg[:k] not in cauda, cauda
    log = tmp_path / "serve.log"
    e2e._drenar(io.StringIO("linha " + seg[:k]), log, [seg])
    assert seg[:k] not in log.read_text(encoding="utf-8")


def test_r5_prefixo_no_fim_com_pedacos_de_qualquer_tamanho():
    seg = SEG_CORTE
    for tam in (1, 2, 7):
        for k in range(1, len(seg)):
            texto = "xy " + seg[:k]
            r = e2e.Redator([seg])
            saida = "".join(r.alimentar(texto[i:i + tam]) for i in range(0, len(texto), tam)) + r.finalizar()
            assert seg[:k] not in saida, (tam, k, saida)


# 2. valor numérico num campo de segredo do config.toml (tomllib e regex)
CASOS_NUMERICOS = [
    ("numero", "llm_api_key = 1234567890\n", "1234567890"),
    ("decimal", "[app]\ntoken = 3.14159\n", "3.14159"),
    ("lista_de_numeros", "[app]\ntokens = [1111, 2222]\n", "2222"),
]


@pytest.mark.parametrize("nome,texto,esperado", CASOS_NUMERICOS, ids=[c[0] for c in CASOS_NUMERICOS])
def test_r5_numero_em_campo_de_segredo_do_config_com_tomllib(tmp_path, nome, texto, esperado):
    cfg = tmp_path / "config.toml"
    cfg.write_text(texto, encoding="utf-8")
    assert esperado in e2e._valores_do_config(cfg)


@pytest.mark.parametrize("nome,texto,esperado", CASOS_NUMERICOS, ids=[c[0] for c in CASOS_NUMERICOS])
def test_r5_numero_em_campo_de_segredo_do_config_sem_tomllib(tmp_path, monkeypatch, nome, texto, esperado):
    monkeypatch.setitem(sys.modules, "tomllib", None)
    cfg = tmp_path / "config.toml"
    cfg.write_text(texto, encoding="utf-8")
    assert esperado in e2e._valores_do_config(cfg)


# 3. formas ascii() e JSON dentro de JSON
@pytest.mark.parametrize("nome", list(SEG_FORMAS))
def test_r5_formas_ascii_e_json_em_json_redigidas(nome):
    seg, _ = SEG_FORMAS[nome]
    for forma in (ascii(seg)[1:-1], json.dumps(json.dumps(seg))[1:-1]):
        texto = "pre " + forma + " pos"
        assert forma not in e2e.redigir(texto, [seg]), forma
        r = e2e.Redator([seg])
        saida = "".join(r.alimentar(texto[i:i + 5]) for i in range(0, len(texto), 5)) + r.finalizar()
        assert forma not in saida, forma


# 4. nomes com KEY no meio de outra palavra; valores de 1 ou 2 caracteres
def test_r5_variavel_com_key_em_outra_palavra_nao_redige_o_valor():
    env = {"KEYBOARD_LAYOUT": "layout-br", "MONKEY_MODE": "modo-banana", "DEBUG_TOKEN": "tok-0123456"}
    sondas = SondasFalsas(chaves=env)
    amb = e2e.detectar(sondas, sondar=False)
    segredos = e2e._segredos(sondas, amb)
    assert "tok-0123456" in segredos
    assert "layout-br" not in segredos and "modo-banana" not in segredos
    assert e2e.redigir("layout-br e modo-banana", segredos) == "layout-br e modo-banana"


def test_r5_valor_de_segredo_com_dois_caracteres_nao_e_redigido_e_o_de_tres_e():
    sondas = SondasFalsas(chaves={"GEMINI_API_KEY": "ab", "FAL_KEY": "abc"})
    amb = e2e.detectar(sondas, sondar=False)
    segredos = e2e._segredos(sondas, amb)
    assert "ab" not in segredos and "abc" in segredos


def test_r5_chave_do_config_com_keyboard_nao_e_campo_de_segredo():
    assert e2e._valores_por_regex('keyboard = "layout-br"\n') == set()
    assert e2e._valores_por_regex('monkey_mode = "modo-banana"\n') == set()


# 5. mensagem do dono da porta diz o que aconteceu
def test_r5_dono_fora_da_arvore_com_docker_indisponivel_nao_diz_sem_proc(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(e2e, "_porta_ocupada", lambda p: False)
    monkeypatch.setattr(e2e, "esperar_http", lambda *a, **k: 200)
    monkeypatch.setattr(e2e, "_iniciar_servidor", lambda argv, **kw: (_Vivo(), _Leitor()))
    monkeypatch.setattr(e2e, "_parar_processo", lambda proc, espera_s=120: None)
    monkeypatch.setattr(e2e, "JANELA_VIVO_S", 0)
    monkeypatch.setattr(e2e, "_inodes_escutando", lambda p: {"555"})
    monkeypatch.setattr(e2e, "_inodes_dos_processos", lambda pids: set())
    monkeypatch.setattr(e2e, "_docker_publica", lambda p: None)
    _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                      sondas=SondasFalsas(toonflow=True), gravador=Gravador())
    item = _item(json.loads(out), "toonflow")
    texto = item["motivo"] + item["detalhe"]
    assert item["estado"] == "SKIP" and "UNVERIFIED" in texto, item
    assert "sem /proc" not in texto and "árvore" in texto, texto


# 6. nenhuma exceção escapa da checagem do dono
@LINUX_SEM_PROC
def test_r5_linha_malformada_do_proc_net_tcp_nao_derruba_a_leitura(monkeypatch):
    hdr = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    ruim = "   0: 0100007F:ZZZZ 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000  0 4242 1 0000000000000000\n"
    boa = "   1: 0100007F:0BB8 00000000:0000 0A 00000000:00000000 00:00000000 00000000  1000  0 4343 1 0000000000000000\n"
    monkeypatch.setattr(e2e.Path, "read_text", lambda self, *a, **k: hdr + ruim + boa if str(self) == "/proc/net/tcp" else "")
    assert e2e._inodes_escutando(3000) == {"4343"}


@pytest.mark.parametrize("saida", ['[{"State":"running","Publishers":5}]', '[{"State":"running","Publishers":true}]'])
def test_r5_compose_com_publishers_fora_do_formato_da_false_sem_excecao(tmp_path, monkeypatch, saida):
    from simplicio_video import toonflow as tf
    monkeypatch.setattr(tf, "find_toonflow_dir", lambda: tmp_path)
    monkeypatch.setattr(tf, "_compose_cmd", lambda: ["docker", "compose"])
    monkeypatch.setattr(e2e.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, saida, ""))
    assert e2e._docker_publica(3000) is False


def test_r5_dono_da_porta_nunca_levanta_excecao(monkeypatch):
    monkeypatch.setattr(e2e, "_inodes_escutando", lambda p: {"1"})

    def falha(pid):
        raise PermissionError("/proc")

    monkeypatch.setattr(e2e, "_pids_da_arvore", falha)
    monkeypatch.setattr(e2e, "_docker_publica", lambda p: None)
    assert e2e._dono_da_porta(_Vivo(), 3000) is None


# 7. a porta é verificada de novo logo antes de subir o serve
@pytest.mark.allow_hosts(["127.0.0.1", "localhost"])
def test_r5_porta_ocupada_durante_o_toonflow_status_nao_sobe_o_serve(tmp_path, capsys, monkeypatch):
    porta = _porta_livre()
    ocupantes = []

    def status(argv_):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", porta))
        srv.listen(1)
        ocupantes.append(srv)
        return e2e.Saida(0, "{}", "")

    lancados = []
    monkeypatch.setattr(e2e, "PORTA_TOONFLOW", porta)
    monkeypatch.setattr(e2e, "_iniciar_servidor", lambda argv, **kw: (lancados.append(argv), (_Morto(), _Leitor()))[1])
    try:
        _, out, _ = _roda(tmp_path, capsys, ["--sim-gastar", "--json", "--apenas", "toonflow"],
                          sondas=SondasFalsas(toonflow=True), gravador=Gravador({"toonflow status": status}))
    finally:
        for srv in ocupantes:
            srv.close()
    item = _item(json.loads(out), "toonflow")
    assert item["estado"] == "FAIL" and "ocupad" in item["detalhe"], item
    assert lancados == [], "com a porta ocupada depois do status o serve não pode subir"
