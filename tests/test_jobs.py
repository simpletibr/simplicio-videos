"""`simplicio-video jobs`: tarefas em segundo plano, num processo separado, com estado em JSON e sem porta de rede.

Hermético: o adaptador `fake` não fala com ninguém, a chave abaixo é falsa, nada escuta em porta. Os testes de ponta a
ponta sobem o runner de verdade (subprocesso), por isso rodam com ffmpeg e esperam por estado, nunca por tempo fixo.
"""
from __future__ import annotations

import inspect
import shutil
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_swap import make_png, make_video, needs_ffmpeg

from conftest import run_cli
from simplicio_video import cli, jobs, mcp_server

FAKE_KEY = "AIzaSyFAKE-KEY-for-tests-0000000000"
FINAL = ("done", "failed", "cancelled", "lost")


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("SIMPLICIO_VIDEO_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("SIMPLICIO_JOBS_GRACE_S", "5")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    for k in ("SIMPLICIO_FAKE_STUCK", "SIMPLICIO_FAKE_GENERATION_S", "SIMPLICIO_FAKE_SUBMIT_S"):
        monkeypatch.delenv(k, raising=False)


@pytest.fixture
def media(tmp_path):
    return {"video": make_video(tmp_path / "in.mp4", 6), "ref": make_png(tmp_path / "ref.png"), "dir": tmp_path}


def swap_params(m, **kw):
    p = {"provider": "fake", "video": str(m["video"]), "refs": [str(m["ref"])], "out": str(m["dir"] / "out" / "s.mp4"),
         "max_usd": 5.0, "autorizo": True}
    p.update(kw)
    return p


def wait_for(jid, states, timeout=40.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        st = jobs.status(jid)
        if st["state"] in states:
            return st
        time.sleep(0.05)
    raise AssertionError(f"job {jid} não chegou a {states}: {jobs.status(jid)}")


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture
def stub_spawn(monkeypatch):
    """Sem runner de verdade: registra o pedido e devolve um pid que não existe."""
    calls = []
    monkeypatch.setattr(jobs, "_spawn_runner", lambda jid: calls.append(jid) or os.getpid())
    return calls


# ---------------------------------------------------------------- lista fechada e quem pode gastar

def test_tipos_fechados():
    assert set(jobs.KINDS) == {"swap-run", "voice"}


def test_tipo_desconhecido_recusado(stub_spawn):
    with pytest.raises(jobs.JobError, match="desconhecid"):
        jobs.submit("render", {})
    assert stub_spawn == []


def test_swap_run_exige_yes_e_autorizo(media, stub_spawn):
    with pytest.raises(jobs.JobError, match="--yes"):
        jobs.submit("swap-run", swap_params(media))
    with pytest.raises(jobs.JobError, match="--autorizo"):
        jobs.submit("swap-run", swap_params(media, autorizo=False), confirm_yes=True)
    assert stub_spawn == [] and not (jobs.jobs_dir()).exists()


@needs_ffmpeg
def test_swap_run_confere_antes_de_criar_o_job(media, stub_spawn):
    with pytest.raises(jobs.JobError, match="não encontrado"):
        jobs.submit("swap-run", swap_params(media, video=str(media["dir"] / "nao.mp4")), confirm_yes=True)
    with pytest.raises(jobs.JobError, match="--max-usd"):
        jobs.submit("swap-run", swap_params(media, max_usd=0.001), confirm_yes=True)
    assert stub_spawn == []
    assert jobs.list_jobs() == []


@needs_ffmpeg
def test_swap_run_confirmado_na_submissao(media, stub_spawn):
    st = jobs.submit("swap-run", swap_params(media), confirm_yes=True)
    assert st["state"] == "queued" and stub_spawn == [st["id"]]
    assert st["confirmed"]["yes"] is True and st["confirmed"]["max_usd"] == 5.0 and st["confirmed"]["at"]
    assert st["estimate_usd"] > 0
    argv = jobs.build_argv(st["kind"], st["params"])
    assert argv[:3] == ["swap", "run", "--provider"] and {"--autorizo", "--yes", "--json"} <= set(argv)
    assert argv[argv.index("--max-usd") + 1] == "5.0"


def test_mcp_nao_submete_swap(media, stub_spawn):
    with pytest.raises(jobs.JobError, match="terminal"):
        jobs.submit("swap-run", swap_params(media), confirm_yes=True, origin="mcp")
    r = mcp_server.video_jobs("submit", kind="swap-run", params=swap_params(media))
    assert r["ok"] is False and "terminal" in r["error"]
    assert stub_spawn == []


@pytest.mark.parametrize("prov", ["gemini", "elevenlabs", "xai", "voicestudio", None])
def test_mcp_so_submete_voz_local(mini, stub_spawn, prov):
    r = mcp_server.video_jobs("submit", kind="voice", params={"contrato": str(mini), "provider": prov})
    assert r["ok"] is False and ("local" in r["error"] or "provider" in r["error"])
    assert stub_spawn == []


@pytest.mark.parametrize("prov", ["file", "local"])
def test_mcp_submete_voz_local(mini, stub_spawn, prov):
    r = mcp_server.video_jobs("submit", kind="voice", params={"contrato": str(mini), "provider": prov})
    assert r["ok"] is True and r["job"]["state"] == "queued" and r["job"]["kind"] == "voice"
    assert stub_spawn == [r["job"]["id"]]
    assert r["job"]["spends"] is False


def test_voz_de_rede_pelo_terminal_exige_yes(mini, stub_spawn):
    with pytest.raises(jobs.JobError, match="--yes"):
        jobs.submit("voice", {"contrato": str(mini), "provider": "gemini"})
    st = jobs.submit("voice", {"contrato": str(mini), "provider": "gemini"}, confirm_yes=True)
    assert st["spends"] is True and st["confirmed"]["yes"] is True


def test_voz_sem_provider_usa_o_do_contrato_para_decidir(mini, stub_spawn):
    # o contrato mini usa `file`: local, não gasta, não precisa de --yes
    st = jobs.submit("voice", {"contrato": str(mini)})
    assert st["spends"] is False and st["params"]["provider"] == "file"


def test_mcp_nao_tem_como_pedir_gasto():
    sig = inspect.signature(mcp_server.video_jobs)
    assert not {"yes", "autorizo", "confirm_yes", "origin"} & set(sig.parameters)


def test_mcp_expoe_so_o_que_nao_gasta():
    r = mcp_server.video_jobs("run")
    assert r["ok"] is False and "acao" in r["error"]
    assert mcp_server.video_jobs("list")["ok"] is True


def test_mcp_registrado():
    assert "video.jobs" in [t[0] for t in mcp_server.TOOLS]
    plugin = json.loads((Path(__file__).resolve().parents[1] / "plugin.json").read_text())
    verbos = {v["verb"] for v in plugin["commands"] if v["verb"].startswith("video.jobs")}
    assert verbos == {"video.jobs.list", "video.jobs.status", "video.jobs.result", "video.jobs.cancel", "video.jobs.submit-voice"}
    assert "video.jobs" in plugin["mcp"]["tools"]


def test_plugin_nao_expoe_swap_run_nem_yes_nem_args_livre():
    plugin = json.loads((Path(__file__).resolve().parents[1] / "plugin.json").read_text())
    for v in plugin["commands"]:
        if v.get("argv", [])[:2] == ["simplicio-video", "jobs"]:
            assert "swap-run" not in v["argv"] and "--yes" not in v["argv"] and "{args}" not in v["argv"], v["verb"]
            assert v["args_schema"]["additionalProperties"] is False
            if v["verb"].endswith("submit-voice"):
                assert set(v["args_schema"]["properties"]["provider"]["enum"]) == set(jobs.LOCAL_VOICE)


# ---------------------------------------------------------------- estado em arquivo, escrita atômica, sem segredo

def test_estado_e_json_atomico_e_sem_sobras(mini, stub_spawn):
    st = jobs.submit("voice", {"contrato": str(mini)})
    d = jobs.job_dir(st["id"])
    assert json.loads((d / "job.json").read_text())["id"] == st["id"]
    assert [p.name for p in d.iterdir() if p.name.endswith(".tmp")] == []
    for i in range(20):  # escritas repetidas nunca deixam um JSON pela metade
        jobs.update(st["id"], heartbeat_at=f"t{i}")
        json.loads((d / "job.json").read_text())
    assert [p.name for p in d.iterdir() if p.name.endswith(".tmp")] == []


def test_escrita_atomica_usa_replace(monkeypatch, tmp_path):
    seen = []
    real = os.replace
    monkeypatch.setattr(os, "replace", lambda a, b: (seen.append((Path(a).name, Path(b).name)), real(a, b)))
    jobs.write_json_atomic(tmp_path / "x.json", {"a": 1})
    assert seen and seen[0][1] == "x.json" and seen[0][0] != "x.json"


def test_argumento_com_chave_e_recusado_e_nada_e_gravado(monkeypatch, mini, stub_spawn):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    with pytest.raises(jobs.JobError, match="chave"):
        jobs.submit("voice", {"contrato": str(mini), "provider": "file", "only": [FAKE_KEY]})
    assert stub_spawn == [] and not jobs.jobs_dir().exists()


def test_escrita_do_estado_apaga_a_chave(monkeypatch, mini, stub_spawn):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    st = jobs.submit("voice", {"contrato": str(mini), "provider": "file"})
    jobs.update(st["id"], error=f"falhou com {FAKE_KEY}")
    text = (jobs.job_dir(st["id"]) / "job.json").read_text()
    assert FAKE_KEY not in text and "***" in text


def todos_os_arquivos(root: Path) -> str:
    return "\n".join(p.read_text(errors="replace") for p in root.rglob("*") if p.is_file())


# ---------------------------------------------------------------- ponta a ponta com o runner de verdade

@needs_ffmpeg
def test_swap_run_em_segundo_plano_termina_e_entrega_o_resultado(media, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    st = jobs.submit("swap-run", swap_params(media, concurrency=2), confirm_yes=True)
    fim = wait_for(st["id"], FINAL)
    assert fim["state"] == "done", fim
    assert fim["exit_code"] == 0 and fim["started_at"] and fim["finished_at"]
    res = jobs.result(st["id"])
    assert Path(res["result"]["output"]).is_file() and res["result"]["manifest"].endswith("swap.manifest.json")
    assert jobs.list_jobs()[0]["id"] == st["id"]
    assert "pedaço" in jobs.read_log(st["id"])
    assert FAKE_KEY not in todos_os_arquivos(jobs.jobs_dir())
    man = json.loads(Path(res["result"]["manifest"]).read_text())
    assert man["concurrency"]["requested"] == 2


@needs_ffmpeg
def test_runner_e_tarefa_ficam_em_grupos_proprios(media, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FAKE_STUCK", "1")
    st = jobs.submit("swap-run", swap_params(media, timeout=120, poll_interval=0.05), confirm_yes=True)
    try:
        run = wait_for(st["id"], ("running",))
        t0 = time.monotonic()
        while not run.get("task_pgid") and time.monotonic() - t0 < 20:
            time.sleep(0.05)
            run = jobs.status(st["id"])
        assert os.getpgid(run["runner_pid"]) == run["runner_pid"] != os.getpgid(os.getpid())
        assert run["task_pgid"] == run["task_pid"] != run["runner_pid"]
    finally:
        jobs.cancel(st["id"])


@needs_ffmpeg
def test_cancelar_para_o_grupo_e_deixa_o_manifesto_cancelado(media, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FAKE_STUCK", "1")
    st = jobs.submit("swap-run", swap_params(media, timeout=120, poll_interval=0.05), confirm_yes=True)
    run = wait_for(st["id"], ("running",))
    t0 = time.monotonic()
    while not run.get("task_pgid") and time.monotonic() - t0 < 20:
        time.sleep(0.05)
        run = jobs.status(st["id"])
    time.sleep(1.0)  # deixa o swap entrar no polling
    out = jobs.cancel(st["id"])
    assert out["state"] == "cancelled"
    fim = jobs.status(st["id"])
    assert fim["state"] == "cancelled" and fim["finished_at"]
    t0 = time.monotonic()
    while (alive(run["runner_pid"]) or alive(run["task_pid"])) and time.monotonic() - t0 < 10:
        time.sleep(0.05)
    assert not alive(run["runner_pid"]) and not alive(run["task_pid"])
    man = json.loads((media["dir"] / "out" / "swap.manifest.json").read_text())
    assert man["state"] == "interrupted"
    assert [p for p in (media["dir"] / "out").iterdir() if p.name.startswith(".swap-work")] == []
    assert not (media["dir"] / "out" / "s.mp4").exists()


@needs_ffmpeg
def test_falha_vira_estado_failed_com_o_erro(media, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FAKE_FAIL", "1")  # o fake recusa de vez no envio
    st = jobs.submit("swap-run", swap_params(media), confirm_yes=True)
    fim = wait_for(st["id"], FINAL)
    assert fim["state"] == "failed" and fim["exit_code"] == 1 and "falha simulada" in fim["error"]
    r = jobs.result(st["id"])
    assert r["state"] == "failed" and "falha simulada" in r["error"]


@needs_ffmpeg
def test_i5_segundo_swap_run_na_mesma_pasta_de_saida_e_recusado(media, stub_spawn):
    jobs.submit("swap-run", swap_params(media, out=str(media["dir"] / "out" / "a.mp4")), confirm_yes=True)
    with pytest.raises(jobs.JobError, match="mesma pasta"):
        jobs.submit("swap-run", swap_params(media, out=str(media["dir"] / "out" / "b.mp4")), confirm_yes=True)
    jobs.submit("swap-run", swap_params(media, out=str(media["dir"] / "outra" / "b.mp4")), confirm_yes=True)


@needs_ffmpeg
def test_swap_run_recusa_saida_existente_na_submissao(media, stub_spawn):
    (media["dir"] / "out").mkdir(parents=True)
    (media["dir"] / "out" / "s.mp4").write_bytes(b"ja existe")
    with pytest.raises(jobs.JobError, match="já existe"):
        jobs.submit("swap-run", swap_params(media), confirm_yes=True)
    jobs.submit("swap-run", swap_params(media, force=True), confirm_yes=True)


def test_chave_na_saida_da_tarefa_nao_vai_para_o_log(mini, monkeypatch):
    """A fala do contrato contém a chave (falsa): o `voice` a imprime no log; o runner a apaga antes de gravar."""
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    txt = mini.read_text().replace("tom de teste", f"tom {FAKE_KEY}")
    mini.write_text(txt)
    st = jobs.submit("voice", {"contrato": str(mini), "provider": "file", "force": True})
    fim = wait_for(st["id"], FINAL)
    assert fim["state"] in ("done", "failed")
    log = jobs.read_log(st["id"])
    assert "tom ***" in log and FAKE_KEY not in log
    assert FAKE_KEY not in todos_os_arquivos(jobs.jobs_dir())
    assert FAKE_KEY not in json.dumps(jobs.status(st["id"]))


def test_voz_local_em_segundo_plano(mini):
    r = mcp_server.video_jobs("submit", kind="voice", params={"contrato": str(mini), "provider": "file"})
    assert r["ok"], r
    fim = wait_for(r["job"]["id"], FINAL)
    assert fim["state"] == "done", fim
    res = mcp_server.video_jobs("result", id=r["job"]["id"])
    assert res["ok"] and res["result"]["lock"].endswith("timing.lock.json") and res["result"]["lines"] == 1
    assert (mini.parent / "timing.lock.json").is_file()
    assert mcp_server.video_jobs("status", id=r["job"]["id"])["job"]["state"] == "done"
    assert [j["id"] for j in mcp_server.video_jobs("list")["jobs"]] == [r["job"]["id"]]


def test_nada_escuta_em_porta():
    src = (Path(jobs.__file__)).read_text()
    for termo in ("socket", "bind(", "listen(", "http.server", "start_server", "serve_forever"):
        assert termo not in src, termo


# ---------------------------------------------------------------- órfãs (lost), cancelar sem runner, limpeza

def morto():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def fabrica(stub_spawn, mini, **campos):
    st = jobs.submit("voice", {"contrato": str(mini)})
    jobs.update(st["id"], **campos)
    return st["id"]


def test_runner_morto_vira_lost(stub_spawn, mini):
    jid = fabrica(stub_spawn, mini, state="running", runner_pid=morto(), started_at="2026-10-16T00:00:00+00:00")
    st = jobs.status(jid)
    assert st["state"] == "lost" and st["finished_at"] and "runner" in st["error"]
    assert jobs.list_jobs()[0]["state"] == "lost"
    assert jobs.result(jid)["state"] == "lost"


def test_lost_mata_a_tarefa_que_sobrou(stub_spawn, mini):
    sobra = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        jid = fabrica(stub_spawn, mini, state="running", runner_pid=morto(), task_pid=sobra.pid, task_pgid=sobra.pid,
                      task_start=jobs.proc_start(sobra.pid), task_boot=jobs.boot_id())
        assert jobs.status(jid)["state"] == "lost"
        sobra.wait(timeout=10)
        assert sobra.returncode is not None
    finally:
        if sobra.poll() is None:
            os.killpg(sobra.pid, signal.SIGKILL)


def test_b2_pgid_reciclado_nao_leva_sigkill(stub_spawn, mini):
    """O pgid gravado hoje pertence a um grupo alheio: o start time gravado não confere, então nada é sinalizado."""
    alheio = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        jid = fabrica(stub_spawn, mini, state="running", runner_pid=morto(), task_pid=alheio.pid, task_pgid=alheio.pid,
                      task_start="1", task_boot=jobs.boot_id())
        st = jobs.status(jid)
        assert st["state"] == "lost"
        time.sleep(0.3)
        assert alheio.poll() is None, "um status de leitura matou um grupo que não é o da tarefa"
    finally:
        if alheio.poll() is None:
            os.killpg(alheio.pid, signal.SIGKILL)


def test_b2_sem_identidade_gravada_nao_mata_e_marca_lost(stub_spawn, mini):
    alheio = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        jid = fabrica(stub_spawn, mini, state="running", runner_pid=morto(), task_pid=alheio.pid, task_pgid=alheio.pid)
        assert jobs.status(jid)["state"] == "lost"
        time.sleep(0.3)
        assert alheio.poll() is None
    finally:
        if alheio.poll() is None:
            os.killpg(alheio.pid, signal.SIGKILL)


def test_b2_boot_diferente_nao_mata(stub_spawn, mini):
    if jobs.boot_id() is None:
        pytest.skip("sem boot id neste sistema")
    alheio = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        jid = fabrica(stub_spawn, mini, state="running", runner_pid=morto(), task_pid=alheio.pid, task_pgid=alheio.pid,
                      task_start=jobs.proc_start(alheio.pid), task_boot="outro-boot")
        assert jobs.status(jid)["state"] == "lost"
        time.sleep(0.3)
        assert alheio.poll() is None
    finally:
        if alheio.poll() is None:
            os.killpg(alheio.pid, signal.SIGKILL)


def test_b2_cancelar_com_runner_morto_nao_mata_pgid_reciclado(stub_spawn, mini):
    alheio = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        jid = fabrica(stub_spawn, mini, state="running", runner_pid=morto(), task_pid=alheio.pid, task_pgid=alheio.pid,
                      task_start="1", task_boot=jobs.boot_id())
        assert jobs.cancel(jid)["state"] in ("cancelled", "lost")
        time.sleep(0.3)
        assert alheio.poll() is None
    finally:
        if alheio.poll() is None:
            os.killpg(alheio.pid, signal.SIGKILL)


def test_b2_runner_grava_a_identidade_da_tarefa(media, monkeypatch):
    monkeypatch.setenv("SIMPLICIO_FAKE_STUCK", "1")
    st = jobs.submit("swap-run", swap_params(media, timeout=120, poll_interval=0.05), confirm_yes=True)
    try:
        run = wait_for(st["id"], ("running",))
        t0 = time.monotonic()
        while not run.get("task_start") and time.monotonic() - t0 < 20:
            time.sleep(0.05)
            run = jobs.status(st["id"])
        assert run["task_start"] == jobs.proc_start(run["task_pid"])
        assert run["task_boot"] == jobs.boot_id()
    finally:
        jobs.cancel(st["id"])


def test_job_vivo_nao_vira_lost(stub_spawn, mini):
    jid = fabrica(stub_spawn, mini, state="running", runner_pid=os.getpid(), runner_start=jobs.proc_start(os.getpid()))
    assert jobs.status(jid)["state"] == "running"


def test_pid_reaproveitado_conta_como_morto(stub_spawn, mini):
    jid = fabrica(stub_spawn, mini, state="running", runner_pid=os.getpid(), runner_start="0")
    assert jobs.status(jid)["state"] == "lost"


def test_cancelar_sem_runner_marca_lost_ou_cancelled(stub_spawn, mini):
    jid = fabrica(stub_spawn, mini, state="running", runner_pid=morto())
    out = jobs.cancel(jid)
    assert out["state"] in ("cancelled", "lost")


def test_cancelar_job_terminado_nao_muda_nada(stub_spawn, mini):
    jid = fabrica(stub_spawn, mini, state="done", finished_at="2026-10-16T00:00:00+00:00")
    assert jobs.cancel(jid)["state"] == "done"


def test_limpeza_de_antigos(stub_spawn, mini):
    velho, recente, rodando = (fabrica(stub_spawn, mini) for _ in range(3))  # criados antes: submit também limpa
    jobs.update(velho, state="done", finished_at="2020-01-01T00:00:00+00:00")
    jobs.update(recente, state="done", finished_at=jobs.now_iso())
    jobs.update(rodando, state="running", runner_pid=os.getpid(), runner_start=jobs.proc_start(os.getpid()),
                created_at="2020-01-01T00:00:00+00:00")
    removidos = jobs.clean(older_than_days=7)
    assert removidos == [velho]
    ids = {j["id"] for j in jobs.list_jobs()}
    assert ids == {recente, rodando}


def test_submeter_limpa_os_antigos(stub_spawn, mini):
    velho = fabrica(stub_spawn, mini, state="failed", finished_at="2020-01-01T00:00:00+00:00")
    jobs.submit("voice", {"contrato": str(mini)})
    assert velho not in {j["id"] for j in jobs.list_jobs()}


def test_id_inexistente_ou_malicioso(stub_spawn):
    for jid in ("nao-existe", "../../etc", "a/b", ""):
        with pytest.raises(jobs.JobError):
            jobs.status(jid)


# ---------------------------------------------------------------- I1: saída longa sem quebra de linha

def _runner_com_script(monkeypatch, tmp_path, mini, corpo: str):
    """Roda o runner de verdade com um script no lugar do `python -m simplicio_video`: só a saída dele importa."""
    import asyncio

    script = tmp_path / "fakepy"
    script.write_text("#!/bin/sh\n" + corpo)
    script.chmod(0o755)

    class Shim:  # o runner executa [sys.executable, "-m", "simplicio_video", *argv]
        executable = str(script)

    monkeypatch.setattr(jobs, "sys", Shim)
    jid = "20261016-000000-0badc0de"
    jobs.write_json_atomic(jobs.job_dir(jid) / "job.json", {
        "schema": jobs.SCHEMA, "id": jid, "kind": "voice", "state": "queued", "created_at": jobs.now_iso(),
        "params": {"contrato": str(mini), "provider": "file"}, "cwd": str(tmp_path)})

    async def go():
        return await asyncio.wait_for(jobs._runner(jid), timeout=25)

    asyncio.run(go())
    return jid


def test_i1_saida_longa_sem_quebra_de_linha_nao_trava_o_runner(monkeypatch, tmp_path, mini):
    corpo = r"""i=0; while [ $i -lt 4000 ]; do printf '\r 45%%|#####     | 450/1000 [00:10<00:12]'; i=$((i+1)); done
echo
head -c 300000 /dev/zero | tr '\0' 'y'; echo
echo '{"ok": true}'
exit 0
"""
    jid = _runner_com_script(monkeypatch, tmp_path, mini, corpo)
    st = jobs.read_state(jid)
    assert st["state"] in ("done", "failed") and st["exit_code"] == 0
    log = jobs.read_log(jid)
    assert '{"ok": true}' in log, "a última linha (resultado) chegou ao log depois da saída longa"


def test_i1_chave_na_fronteira_de_um_bloco_continua_apagada(monkeypatch, tmp_path, mini):
    chave = "AIzaSy" + "Z" * 33
    corpo = (f"head -c 65500 /dev/zero | tr '\\0' 'y'; printf '{chave}'; head -c 70000 /dev/zero | tr '\\0' 'y'; echo\n"
             "exit 0\n")
    jid = _runner_com_script(monkeypatch, tmp_path, mini, corpo)
    assert chave not in jobs.read_log(jid) and chave not in json.dumps(jobs.read_state(jid))


# ---------------------------------------------------------------- I3: Windows (sem SIGKILL, sem fcntl, sem killpg)

def test_i3_cli_importa_sem_signal_sigkill_e_sem_fcntl():
    """Simula o Windows: `signal.SIGKILL` não existe e `fcntl` não importa. O CLI inteiro precisa montar o parser."""
    code = ("import signal, sys\nsys.modules['fcntl'] = None\ndel signal.SIGKILL\n"
            "from simplicio_video import cli\ncli.build_parser()\nfrom simplicio_video import jobs\n"
            "assert jobs._sigkill() == signal.SIGTERM\nprint('ok')\n")
    env = {**os.environ, "PYTHONPATH": str(Path(jobs.__file__).resolve().parent.parent)}
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "ok", r.stderr[-600:]


def test_i3_jobs_no_windows_recusa_com_mensagem_clara(monkeypatch, capsys):
    monkeypatch.setattr(sys, "platform", "win32")
    assert jobs.run_jobs(["list"]) == 1
    assert "Windows" in capsys.readouterr().err


def test_i3_fcntl_so_e_importado_onde_e_usado():
    assert not hasattr(jobs, "fcntl")


# ---------------------------------------------------------------- I4: sem /proc (macOS)

@pytest.fixture
def sem_proc(monkeypatch, tmp_path):
    if not shutil.which("ps"):
        pytest.skip("sem ps")
    monkeypatch.setattr(jobs, "PROC", tmp_path / "sem-proc")


def test_i4_start_time_sem_proc_vem_do_ps(sem_proc):
    a = subprocess.Popen(["sleep", "30"])
    try:
        s1 = jobs.proc_start(a.pid)
        assert s1 is not None, "sem /proc o start time precisa vir do ps"
        assert s1 == jobs.proc_start(a.pid)
    finally:
        a.kill()
        a.wait()


def test_i4_pid_reaproveitado_e_detectado_sem_proc(sem_proc, stub_spawn, mini):
    jid = fabrica(stub_spawn, mini, state="running", runner_pid=os.getpid(), runner_start="ps:Mon Jan  1 00:00:00 2001")
    assert jobs.status(jid)["state"] == "lost"


def test_i4_job_vivo_sem_proc_continua_running(sem_proc, stub_spawn, mini):
    jid = fabrica(stub_spawn, mini, state="running", runner_pid=os.getpid(), runner_start=jobs.proc_start(os.getpid()))
    assert jobs.status(jid)["state"] == "running"


def test_i4_cancel_sem_prova_de_identidade_nao_sinaliza(monkeypatch, stub_spawn, mini):
    alheio = subprocess.Popen(["sleep", "30"])
    try:
        monkeypatch.setattr(jobs, "proc_start", lambda pid: None)  # nem /proc nem ps: nenhuma prova
        jid = fabrica(stub_spawn, mini, state="running", runner_pid=alheio.pid, runner_start="x")
        with pytest.raises(jobs.JobError, match="provar"):
            jobs.cancel(jid, wait_s=0.2)
        time.sleep(0.2)
        assert alheio.poll() is None
    finally:
        alheio.kill()
        alheio.wait()


# ---------------------------------------------------------------- menores: M1 (chave no argumento) e M6 (cancel no MCP)

@pytest.mark.parametrize("chave", ["AIzaSy" + "F" * 33, "AQ.Ab8" + "x" * 40])
def test_m1_argumento_com_formato_de_chave_e_recusado_mesmo_fora_do_ambiente(stub_spawn, mini, chave):
    with pytest.raises(jobs.JobError, match="chave"):
        jobs.submit("voice", {"contrato": str(mini), "provider": "file", "only": [chave]}, origin="mcp")
    assert stub_spawn == [] and not jobs.jobs_dir().exists()


def test_m6_cancelar_sem_bloquear_devolve_na_hora(stub_spawn, mini):
    runner = subprocess.Popen(["sleep", "30"])
    try:
        jid = fabrica(stub_spawn, mini, state="running", runner_pid=runner.pid, runner_start=jobs.proc_start(runner.pid))
        t0 = time.monotonic()
        st = jobs.cancel(jid, block=False)
        assert time.monotonic() - t0 < 2.0
        assert st["cancel_requested_at"] and st["state"] in ("queued", "running", "cancelled", "lost")
        runner.wait(timeout=5)  # recebeu o SIGTERM
    finally:
        if runner.poll() is None:
            runner.kill()


def test_m6_mcp_cancel_nao_espera_o_runner(monkeypatch, stub_spawn, mini):
    chamadas = []
    monkeypatch.setattr(jobs, "cancel", lambda jid, **kw: chamadas.append(kw) or jobs.status(jid))
    jid = fabrica(stub_spawn, mini, state="running", runner_pid=os.getpid(), runner_start=jobs.proc_start(os.getpid()))
    assert mcp_server.video_jobs("cancel", id=jid)["ok"]
    assert chamadas == [{"block": False}]


# ---------------------------------------------------------------- CLI

def test_ajuda_do_jobs():
    r = run_cli("jobs", "--help")
    assert r.returncode == 0
    for termo in ("submit", "status", "list", "cancel", "result", "clean", "swap-run", "voice", "--yes", "exemplos:"):
        assert termo in r.stdout, termo


def test_cli_despacha_jobs(capsys, stub_spawn, mini):
    assert cli.main(["jobs", "submit", "voice", str(mini), "--provider", "file", "--json"]) == 0
    jid = json.loads(capsys.readouterr().out)["id"]
    assert cli.main(["jobs", "status", jid, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "queued"
    assert cli.main(["jobs", "list", "--json"]) == 0
    assert [j["id"] for j in json.loads(capsys.readouterr().out)["jobs"]] == [jid]
    assert cli.main(["jobs", "result", jid]) == 2  # ainda não terminou
    assert cli.main(["jobs", "status", "nao-existe"]) == 1


def test_cli_swap_run_sem_yes_recusa(capsys, media, stub_spawn):
    argv = ["jobs", "submit", "swap-run", "--provider", "fake", "--video", str(media["video"]), "--ref", str(media["ref"]),
            "--out", str(media["dir"] / "o.mp4"), "--autorizo"]
    assert cli.main(argv) == 1
    assert "--yes" in capsys.readouterr().err
    assert stub_spawn == []


# ---------------------------------------------------------------- ordem da saída: a linha de progresso não passa na frente nem fica para trás

class FluxoFalso:
    """Faz o papel do `proc.stdout`: cada `read()` devolve um dos blocos combinados e, no fim, vazio (EOF)."""

    def __init__(self, *blocos: bytes):
        self.blocos = list(blocos)

    async def read(self, n: int) -> bytes:
        return self.blocos.pop(0) if self.blocos else b""


def bombear(*blocos: bytes):
    """Passa a saída pelo `_pump` de verdade e devolve (linhas do log, box)."""
    import asyncio

    jid = "20261016-000000-0feedbee"
    jobs.job_dir(jid).mkdir(parents=True)
    box: dict = {"tail": [], "json": None}
    asyncio.run(jobs._pump(FluxoFalso(*blocos), jid, box))
    return jobs.read_log(jid).splitlines(), box


def test_progresso_com_cr_entra_no_log_antes_das_linhas_reais_que_vieram_depois():
    """`p1\\rp2\\rp3\\r` reescreve a mesma linha: fica só a última (p3), e na ordem em que a tarefa a escreveu, antes de real1 e real2.
    Antes ela ficava guardada até o fim e saía DEPOIS de tudo."""
    linhas, box = bombear(b"p1\rp2\rp3\rreal1\nreal2\n")
    assert linhas == ["p3", "real1", "real2"]
    assert box["tail"] == ["p3", "real1", "real2"]


def test_progresso_antes_de_uma_cauda_sem_quebra_de_linha_mantem_a_ordem():
    linhas, _ = bombear(b"p1\rp2\rcauda")
    assert linhas == ["p2", "cauda"]


def test_progresso_e_linha_real_em_blocos_diferentes_mantem_a_ordem():
    linhas, _ = bombear(b"p1\rp2\r", b"real1\nreal2", b"\n")
    assert linhas == ["p2", "real1", "real2"]


def test_o_erro_de_tarefa_que_falhou_mostra_a_ultima_linha_real_e_nao_um_progresso_velho():
    """O `error` do estado usa as últimas linhas do `tail`: um progresso velho no fim escondia a mensagem de erro."""
    _, box = bombear(b"baixando 10%\rbaixando 50%\rtraceback...\nErro: voz sem cota\n")
    assert [s for s in box["tail"] if s.strip()][-1] == "Erro: voz sem cota"


def test_linha_json_do_resultado_continua_sendo_lida_depois_de_um_progresso():
    _, box = bombear(b'p1\rp2\r{"ok": true}\n')
    assert box["json"] == {"ok": True}
    assert box["tail"][-1] == '{"ok": true}'


def test_progresso_repetido_deixa_no_log_so_a_ultima_atualizacao_e_nao_milhares():
    linhas, _ = bombear(b"".join(b"%d%%\r" % i for i in range(1, 500)) + b"fim\n")
    assert linhas == ["499%", "fim"]
