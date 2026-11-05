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
    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


class _Leitor:
    def join(self, timeout=None):
        return None


def test_toonflow_pass_so_com_o_serve_vivo_quando_responde(tmp_path, capsys, monkeypatch):
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
