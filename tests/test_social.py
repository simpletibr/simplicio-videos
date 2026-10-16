"""Módulo `social` (`simplicio-video social providers|plan|check|recipe`): hermético e sem rede.

O motor só planeja e documenta: nenhum teste chama o Real Oficial nem o Zernio, usa chave ou posta algo. O vídeo dos
testes é um arquivo com cabeçalho `ftyp` e o `ffprobe` é trocado por uma função fixa (um teste com ffmpeg real fica
pulado quando o ffmpeg falta). Provas centrais: o plano é determinístico e nunca grava segredo; os limites por rede
carregam fonte, data e confiança; e nenhuma saída do motor chama "confirmar" sem a etapa de consentimento antes.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT, run_cli
from simplicio_video import mcp_server, paths, social

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg ausente")

CAPTION = "Aprenda a montar o seu primeiro anúncio em vídeo. #marketing #video #reels"
PROBE_OK = {"duration_s": 20.0, "width": 1080, "height": 1920, "fps": 30.0, "video_codec": "h264",
            "audio_codec": "aac", "container": "mov,mp4,m4a,3gp,3g2,mj2"}
REDES = ["youtube", "tiktok", "instagram", "facebook", "twitter", "linkedin", "threads", "pinterest", "bluesky"]
PROVEDORES = ["realoficial", "zernio"]
ID_RO = "01HZX3K9Q2M4N5P6R7S8T9V0WA"  # 26 caracteres, no formato dos ids do Real Oficial (valor inventado)
CLIP_RO = "01HZX3K9Q2M4N5P6R7S8T9V0WB"


def fazer_mp4(path: Path, extra: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"conteudo-de-teste" + extra)
    return path


@pytest.fixture(autouse=True)
def sonda(monkeypatch, tmp_path):
    from datetime import datetime, timezone
    monkeypatch.setattr(social, "_probe", lambda p: dict(PROBE_OK))
    monkeypatch.setattr(social, "_accept_key_path", lambda: tmp_path / "chave-de-aceite" / "social-accept.key", raising=False)
    monkeypatch.setattr(social, "_now", lambda: datetime(2026, 10, 16, 12, tzinfo=timezone.utc))  # relógio fixo: agendas dos testes


@pytest.fixture
def video(tmp_path):
    return fazer_mp4(tmp_path / "out" / "final.mp4")


def plano(video, targets=("youtube", "tiktok"), **kw):
    kw.setdefault("caption", CAPTION)
    return social.make_plan(str(video), list(targets), **kw)


def ler(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


# ------------------------------------------------------------------------------------------------ provedores

def test_providers_padrao_e_realoficial_e_lista_os_dois():
    rep = social.providers_report()
    assert rep["default"] == "realoficial"
    assert [p["id"] for p in rep["providers"]] == PROVEDORES
    ro = rep["providers"][0]
    assert ro["default"] is True and rep["providers"][1]["default"] is False
    nomes = {t["name"] for t in ro["tools"]}
    assert {"ro_list_social_accounts", "ro_preview_publication", "ro_confirm_publishing", "ro_list_publications",
            "ro_suggest_caption", "ro_get_social_analytics", "ro_share", "ro_import_video", "ro_whoami"} <= nomes
    z = rep["providers"][1]
    assert {"posts_create", "accounts_list", "media_generate_upload_link", "search_tools", "call_tool"} <= {t["name"] for t in z["tools"]}


def test_providers_cada_ferramenta_declara_efeito_e_as_de_publicar_estao_marcadas():
    for p in social.providers_report()["providers"]:
        assert p["publish_tools"], p["id"]
        por_nome = {t["name"]: t for t in p["tools"]}
        for t in p["tools"]:
            assert t["effect"] in {"read", "quote", "publish", "other"}, t["name"]
            assert t["confidence"] in {"official", "UNVERIFIED"}, t["name"]
        for nome in p["publish_tools"]:
            assert por_nome[nome]["effect"] == "publish", nome
    ro = social.providers_report()["providers"][0]
    assert ro["publish_tools"] == ["ro_confirm_publishing"]


def test_providers_traz_fonte_data_confianca_e_pendencias():
    for p in social.providers_report()["providers"]:
        assert p["source_url"].startswith("https://"), p["id"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", p["read_on"]), p["id"]
        assert p["confidence"] in {"official", "UNVERIFIED"}
        assert p["auth"] and p["networks"] and p["pricing"]
    z = social.providers_report()["providers"][1]
    assert "UNVERIFIED" in json.dumps(z, ensure_ascii=False)
    ro = social.providers_report()["providers"][0]
    assert any("clip_id" in g or "upload" in g.lower() for g in ro["gaps"])  # RO não recebe MP4 local


def test_providers_nao_guarda_chave_nem_token():
    texto = json.dumps(social.providers_report())
    assert not re.search(r"(sk-[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_-]{20,}|Bearer [A-Za-z0-9._-]{20,})", texto)


# ------------------------------------------------------------------------------------------------ limites

def test_tabela_de_limites_tem_fonte_data_e_confianca_por_linha():
    tab = social.limits_table()
    assert tab["schema"] == "simplicio.social-limits/v1"
    assert {r["network"] for r in tab["rows"]} == set(REDES)
    for r in tab["rows"]:
        assert {"network", "field", "value", "source_url", "read_on", "confidence", "note"} <= set(r), r
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["read_on"]), r
        assert r["confidence"] in {"official", "UNVERIFIED"}, r
        assert r["source_url"].startswith("https://"), r
        assert r["field"] in social.FIELDS, r
        if r["confidence"] == "official":
            assert r["value"] is not None, r
    assert any(r["confidence"] == "official" for r in tab["rows"])
    assert any(r["confidence"] == "UNVERIFIED" for r in tab["rows"])


def test_limite_lido_so_em_documentacao_de_terceiro_fica_unverified():
    for r in social.limits_table()["rows"]:
        if "docs.zernio.com" in r["source_url"]:
            assert r["confidence"] == "UNVERIFIED", r


def test_cada_rede_tem_duracao_maxima_ou_pendencia_explicita():
    tab = social.limits_table()
    for rede in REDES:
        campos = {r["field"] for r in tab["rows"] if r["network"] == rede}
        assert "caption_max_chars" in campos, rede


# ------------------------------------------------------------------------------------------------ plano

def test_plano_gera_arquivo_ao_lado_do_video_com_o_conteudo_esperado(video):
    r = plano(video)
    path = Path(r["path"])
    assert path == video.parent / "social.plan.json" and path.is_file()
    p = ler(path)
    assert p["schema"] == "simplicio.social-plan/v1" and p["ok"] is True
    v = p["video"]
    assert v["sha256"] == social.sha256_file(video) and v["size_bytes"] == video.stat().st_size
    assert (v["duration_s"], v["width"], v["height"], v["aspect_ratio"]) == (20.0, 1080, 1920, "9:16")
    assert v["video_codec"] == "h264" and v["audio_codec"] == "aac" and v["container"] == "mp4"
    assert p["caption"] == CAPTION and p["hashtags"] == ["#marketing", "#video", "#reels"]
    assert p["targets"] == [{"network": "youtube", "account": None}, {"network": "tiktok", "account": None}]
    assert p["schedule"] is None and re.fullmatch(r"[0-9a-f]{64}", p["plan_id"])
    assert p["checks"] and all({"network", "field", "limit", "actual", "status", "confidence", "source_url", "read_on"} <= set(c) for c in p["checks"])


def test_plano_e_deterministico_e_sem_horario_de_geracao(video, tmp_path):
    a = plano(video, out=str(tmp_path / "a.json"))
    b = plano(video, out=str(tmp_path / "b.json"))
    assert Path(a["path"]).read_bytes() == Path(b["path"]).read_bytes()
    texto = Path(a["path"]).read_text(encoding="utf8")
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", texto)
    p = ler(a["path"])
    corpo = {k: v for k, v in p.items() if k != "plan_id"}
    assert p["plan_id"] == social.plan_id(corpo)


def test_plano_muda_de_id_quando_a_legenda_muda(video, tmp_path):
    a = ler(plano(video, out=str(tmp_path / "a.json"))["path"])
    b = ler(plano(video, caption=CAPTION + " mais", out=str(tmp_path / "b.json"))["path"])
    assert a["plan_id"] != b["plan_id"]


def test_plano_recusa_video_inexistente_diretorio_e_nao_mp4(tmp_path):
    with pytest.raises(social.SocialError, match="não existe"):
        social.make_plan(str(tmp_path / "nada.mp4"), ["youtube"], caption="x")
    with pytest.raises(social.SocialError, match="arquivo"):
        social.make_plan(str(tmp_path), ["youtube"], caption="x")
    mov = fazer_mp4(tmp_path / "v.mov")
    with pytest.raises(social.SocialError, match="MP4"):
        social.make_plan(str(mov), ["youtube"], caption="x")
    falso = tmp_path / "falso.mp4"
    falso.write_bytes(b"isto nao e um mp4 de verdade, so tem a extensao")
    with pytest.raises(social.SocialError, match="MP4"):
        social.make_plan(str(falso), ["youtube"], caption="x")
    assert not list(tmp_path.glob("social.plan.json"))


def test_plano_nao_sobrescreve_sem_force(video):
    plano(video)
    with pytest.raises(social.SocialError, match="--force"):
        plano(video)
    assert plano(video, force=True)["ok"] is True


def test_plano_exige_legenda_e_rede_conhecida(video):
    with pytest.raises(social.SocialError, match="legenda"):
        plano(video, caption="   ")
    with pytest.raises(social.SocialError, match="rede"):
        plano(video, targets=["orkut"])
    with pytest.raises(social.SocialError, match="rede"):
        plano(video, targets=[])


def test_alvos_com_conta_e_deduplicados(video):
    p = ler(plano(video, targets=["tiktok=@minha.conta", "tiktok=@minha.conta", f"youtube={ID_RO}", "instagram"])["path"])
    assert p["targets"] == [{"network": "tiktok", "account": "@minha.conta"}, {"network": "youtube", "account": ID_RO},
                            {"network": "instagram", "account": None}]


def test_plano_recusa_conta_que_parece_segredo(video):
    for ruim in ("sk-abcdefghijklmnopqrstuvwxyz0123456789", "Bearer abc.def.ghi", "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6", "a b", "x" * 70):
        with pytest.raises(social.SocialError, match="conta"):
            plano(video, targets=[f"tiktok={ruim}"], force=True)


def test_plano_nunca_grava_chaves_nem_valor_de_ambiente(video, monkeypatch):
    monkeypatch.setenv("ZERNIO_API_KEY", "zernio-chave-falsa-0123456789")
    monkeypatch.setenv("REALOFICIAL_TOKEN", "ro-token-falso-0123456789")
    r = plano(video, targets=[f"tiktok={ID_RO}"])
    texto = Path(r["path"]).read_text(encoding="utf8")
    assert "chave-falsa" not in texto and "token-falso" not in texto

    def chaves(n):
        if isinstance(n, dict):
            for k, v in n.items():
                yield k
                yield from chaves(v)
        elif isinstance(n, list):
            for v in n:
                yield from chaves(v)
    assert not [k for k in chaves(ler(r["path"])) if re.search(r"key|token|secret|password|senha|authorization", k, re.I)]


def test_plano_com_agendamento_valido(video):
    p = ler(plano(video, at="2026-10-20T09:30", timezone="America/Sao_Paulo")["path"])
    assert p["schedule"] == {"at": "2026-10-20T09:30", "timezone": "America/Sao_Paulo"}


@pytest.mark.parametrize("kw,msg", [
    ({"at": "2026-10-20T09:30"}, "timezone"),
    ({"timezone": "America/Sao_Paulo"}, "--at"),
    ({"at": "20/10/2026 09:30", "timezone": "America/Sao_Paulo"}, "AAAA-MM-DDTHH:MM"),
    ({"at": "2026-10-20T09:30", "timezone": "Marte/Olimpo"}, "timezone"),
    ({"at": "2026-02-31T09:30", "timezone": "America/Sao_Paulo"}, "AAAA-MM-DDTHH:MM"),
])
def test_agendamento_invalido_e_recusado(video, kw, msg):
    with pytest.raises(social.SocialError, match=re.escape(msg)):
        plano(video, **kw)


# ------------------------------------------------------------------------------------------------ limites no plano

def test_duracao_acima_do_limite_oficial_recusa_e_nao_aceita_bypass(video, monkeypatch):
    monkeypatch.setattr(social, "_probe", lambda p: {**PROBE_OK, "duration_s": 200.0})
    for kw in ({}, {"accept_unverified": True}):
        with pytest.raises(social.SocialError, match="youtube.*duration_max_s"):
            plano(video, targets=["youtube"], **kw)


def test_limite_unverified_recusa_e_so_passa_com_aceite_explicito(video, monkeypatch):
    monkeypatch.setattr(social, "_probe", lambda p: {**PROBE_OK, "duration_s": 700.0})
    with pytest.raises(social.SocialError, match="UNVERIFIED.*--aceito-unverified"):
        plano(video, targets=["tiktok"])
    p = ler(plano(video, targets=["tiktok"], accept_unverified=True)["path"])
    ruim = [c for c in p["checks"] if c["status"] == "violation"]
    assert ruim and ruim[0]["confidence"] == "UNVERIFIED" and p["accepted_unverified"] == ["tiktok:duration_max_s"]


def test_proporcao_horizontal_nao_serve_para_rede_vertical(video, monkeypatch):
    monkeypatch.setattr(social, "_probe", lambda p: {**PROBE_OK, "width": 1920, "height": 1080})
    with pytest.raises(social.SocialError, match="tiktok.*aspect_ratios"):
        plano(video, targets=["tiktok"])
    assert plano(video, targets=["linkedin", "threads"], force=True)["ok"] is True  # 16:9 cabe nas duas


def test_legenda_e_hashtags_acima_do_limite_recusam(video):
    tab = {"schema": "simplicio.social-limits/v1", "rows": [
        {"network": "tiktok", "field": "caption_max_chars", "value": 30, "source_url": "https://exemplo.test/x", "read_on": "2026-10-16",
         "confidence": "official", "note": ""},
        {"network": "tiktok", "field": "hashtags_max", "value": 2, "source_url": "https://exemplo.test/x", "read_on": "2026-10-16",
         "confidence": "official", "note": ""},
        {"network": "tiktok", "field": "size_max_mb", "value": 0.00001, "source_url": "https://exemplo.test/x", "read_on": "2026-10-16",
         "confidence": "official", "note": ""}]}
    with pytest.raises(social.SocialError) as e:
        plano(video, targets=["tiktok"], limits=tab)
    msg = str(e.value)
    assert "caption_max_chars" in msg and "hashtags_max" in msg and "size_max_mb" in msg


def test_campo_sem_valor_na_tabela_fica_unchecked_e_aparece_no_plano(video):
    p = ler(plano(video, targets=["tiktok", "twitter"])["path"])
    sem = [c for c in p["checks"] if c["status"] == "unchecked"]
    assert sem and all(c["limit"] is None and c["confidence"] == "UNVERIFIED" for c in sem)


def test_limites_oficiais_e_titulo(video):
    p = ler(plano(video, targets=["youtube"], title="Meu título")["path"])
    assert p["title"] == "Meu título"
    with pytest.raises(social.SocialError, match="title_max_chars"):
        plano(video, targets=["youtube"], title="t" * 101, force=True)


# ------------------------------------------------------------------------------------------------ check

def test_check_ok_e_detecta_arquivo_alterado_removido_e_plano_adulterado(video):
    path = plano(video)["path"]
    assert social.check_plan(path) == {"ok": True, "plan_id": ler(path)["plan_id"], "problems": []}
    video.write_bytes(video.read_bytes() + b"x")
    rep = social.check_plan(path)
    assert rep["ok"] is False and any("sha256" in p for p in rep["problems"])
    video.unlink()
    assert any("não existe" in p for p in social.check_plan(path)["problems"])


def test_check_detecta_plano_editado_a_mao(video):
    path = plano(video)["path"]
    p = ler(path)
    p["caption"] = "outra legenda"
    Path(path).write_text(json.dumps(p), encoding="utf8")
    assert any("plan_id" in x for x in social.check_plan(path)["problems"])


def test_check_funciona_depois_de_mover_a_pasta(video, tmp_path):
    plano(video)
    novo = tmp_path / "movido"
    shutil.copytree(video.parent, novo)
    assert social.check_plan(str(novo / "social.plan.json"))["ok"] is True


def test_check_recusa_arquivo_que_nao_e_plano(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{}", encoding="utf8")
    with pytest.raises(social.SocialError, match="plano"):
        social.check_plan(str(p))
    with pytest.raises(social.SocialError, match="não existe"):
        social.check_plan(str(tmp_path / "nada.json"))


def test_check_avisa_agendamento_no_passado(video, monkeypatch):
    path = plano(video, at="2026-10-20T09:30", timezone="America/Sao_Paulo")["path"]
    from datetime import datetime, timezone
    monkeypatch.setattr(social, "_now", lambda: datetime(2026, 10, 25, tzinfo=timezone.utc))
    rep = social.check_plan(path)
    assert rep["ok"] is False and any("passado" in p for p in rep["problems"])


# ------------------------------------------------------------------------------------------------ receita

def passos(rec):
    return rec["steps"]


def conferir_consentimento(steps, publish_tools, preview_tools=()):
    """Regra de ouro: toda chamada de publicar vem DEPOIS de um 'mostrar' e de um 'consentimento', nessa ordem
    (e, quando o provedor cota, depois da chamada de cotação)."""
    consent_idx = [i for i, s in enumerate(steps) if s["kind"] == "consent"]
    show_idx = [i for i, s in enumerate(steps) if s["kind"] == "show"]
    for i, s in enumerate(steps):
        if s["kind"] == "call" and s["tool"] in publish_tools:
            assert s["effect"] == "publish"
            assert consent_idx and max(c for c in consent_idx if c < i) is not None, f"publicar sem consentimento: {s}"
            c = max(c for c in consent_idx if c < i)
            assert any(sh < c for sh in show_idx), "consentimento sem mostrar antes"
            assert s["requires_step"] == steps[c]["n"]
            for pv in preview_tools:
                assert any(x["kind"] == "call" and x["tool"] == pv and j < c for j, x in enumerate(steps)), f"falta {pv} antes do consentimento"
    publicar = [s for s in steps if s["kind"] == "call" and s["tool"] in publish_tools]
    assert publicar, "a receita precisa terminar numa chamada de publicar (depois do consentimento)"


@pytest.mark.parametrize("provedor", PROVEDORES)
def test_receita_so_publica_depois_de_mostrar_e_do_consentimento(video, provedor):
    path = plano(video, targets=[f"tiktok={ID_RO}", "instagram", "youtube"], at="2026-10-20T09:30", timezone="America/Sao_Paulo")["path"]
    rec = social.recipe(path, provider=provedor, clip_id=CLIP_RO)
    pub = {p["id"]: p for p in social.providers_report()["providers"]}[provedor]
    conferir_consentimento(passos(rec), set(pub["publish_tools"]), preview_tools=("ro_preview_publication",) if provedor == "realoficial" else ())
    assert [s["n"] for s in rec["steps"]] == list(range(1, len(rec["steps"]) + 1))


def sequencia_do_texto(texto):
    """Lê a saída em texto: devolve [(tipo, ferramenta|None)] na ordem em que aparece."""
    out = []
    for linha in texto.splitlines():
        m = re.match(r"^\s*(\d+)\. \[([a-z]+)\](?: (\S+))?", linha)
        if m:
            out.append((m.group(2), m.group(3)))
    return out


@pytest.mark.parametrize("provedor", PROVEDORES)
@pytest.mark.parametrize("alvos,agenda", [(["youtube"], None), (["tiktok", "instagram", "youtube"], ("2026-10-21T18:00", "America/Sao_Paulo")),
                                          (REDES, None)])
def test_nenhuma_saida_do_motor_confirma_sem_consentimento_antes(video, provedor, alvos, agenda, capsys):
    kw = {"at": agenda[0], "timezone": agenda[1]} if agenda else {}
    path = plano(video, targets=alvos, accept_unverified=True, **kw)["path"]
    pub = set({p["id"]: p for p in social.providers_report()["providers"]}[provedor]["publish_tools"])
    rec = social.recipe(path, provider=provedor, clip_id=CLIP_RO)
    saidas = [social.recipe_text(rec)]
    assert social.run_social(["recipe", path, "--provider", provedor, "--clip-id", CLIP_RO]) == 0
    saidas.append(capsys.readouterr().out)
    assert social.run_social(["recipe", path, "--provider", provedor, "--clip-id", CLIP_RO, "--json"]) == 0
    js = json.loads(capsys.readouterr().out)
    conferir_consentimento(js["steps"], pub)
    for texto in saidas:
        seq = sequencia_do_texto(texto)
        assert seq, texto
        vistos = set()
        for tipo, ferr in seq:
            if tipo == "chamada" and ferr in pub:
                assert {"mostrar", "consentimento"} <= vistos, f"{ferr} antes do consentimento:\n{texto}"
            vistos.add(tipo)
        assert [t for t, _ in seq].index("consentimento") < [i for i, (t, f) in enumerate(seq) if f in pub][0]


def test_receita_preenche_os_argumentos_do_plano_no_realoficial(video):
    path = plano(video, targets=[f"youtube={ID_RO}"], title="Título curto", at="2026-10-20T09:30", timezone="America/Sao_Paulo")["path"]
    rec = social.recipe(path, clip_id=CLIP_RO)
    assert rec["provider"] == "realoficial"  # padrão
    prev = next(s for s in rec["steps"] if s.get("tool") == "ro_preview_publication")
    a = prev["args"]
    assert a["action"] == "create" and a["mode"] == "at"
    assert a["scheduled_at"] == "2026-10-20T09:30" and a["timezone"] == "America/Sao_Paulo"
    assert a["items"] == [{"clip_id": CLIP_RO, "title": "Título curto", "description": CAPTION}]
    assert a["account_ids"] == [ID_RO]
    conf = next(s for s in rec["steps"] if s.get("tool") == "ro_confirm_publishing")
    assert conf["args"]["confirm"] is True and conf["args"]["quote_id"].startswith("<")
    assert conf["args"]["accept_terms"].startswith("<")  # nunca preenchido pelo motor
    assert set(conf["args"]) == {"quote_id", "confirm", "accept_terms"}


def test_receita_agora_usa_mode_now_e_marca_ai_generated(video):
    path = plano(video, targets=["youtube"], ai_generated=True)["path"]
    prev = next(s for s in social.recipe(path, clip_id=CLIP_RO)["steps"] if s.get("tool") == "ro_preview_publication")
    assert prev["args"]["mode"] == "now" and "scheduled_at" not in prev["args"] and prev["args"]["ai_generated"] is True


def test_receita_tiktok_pede_privacidade_ao_usuario_e_nunca_escolhe(video):
    path = plano(video, targets=["tiktok"])["path"]
    rec = social.recipe(path, clip_id=CLIP_RO)
    prev = next(s for s in rec["steps"] if s.get("tool") == "ro_preview_publication")
    assert prev["args"]["tiktok_privacy"].startswith("<") and "usuário" in prev["args"]["tiktok_privacy"]
    assert not re.search(r"PUBLIC_TO_EVERYONE|SELF_ONLY", json.dumps(prev["args"]))
    assert any(s.get("tool") == "ro_list_social_accounts" for s in rec["steps"])


def test_receita_realoficial_sem_clip_id_bloqueia_com_passo_manual(video):
    path = plano(video, targets=["youtube"])["path"]
    rec = social.recipe(path)
    assert rec["steps"][0]["kind"] == "manual" and "clip_id" in rec["steps"][0]["text"]
    assert rec["blocked_until"] and "clip_id" in rec["blocked_until"][0]
    prev = next(s for s in rec["steps"] if s.get("tool") == "ro_preview_publication")
    assert prev["args"]["items"][0]["clip_id"].startswith("<")


def test_receita_zernio_marca_o_que_nao_foi_conferido(video):
    path = plano(video, targets=["instagram", "tiktok"], at="2026-10-20T09:30", timezone="America/Sao_Paulo")["path"]
    rec = social.recipe(path, provider="zernio")
    tools = [s["tool"] for s in rec["steps"] if s["kind"] == "call"]
    assert tools.index("accounts_list") < tools.index("media_generate_upload_link") < tools.index("posts_create")
    post = next(s for s in rec["steps"] if s.get("tool") == "posts_create")
    assert post["args"]["platforms"] == ["instagram", "tiktok"] and post["args"]["content"] == CAPTION
    assert post["args"]["publish_at"].startswith("2026-10-20T09:30")
    assert rec["unverified"] and any("search_tools" in u for u in rec["unverified"])
    assert any("UNVERIFIED" in json.dumps(s, ensure_ascii=False) for s in rec["steps"])


def test_receita_zernio_sem_agenda_usa_now_so_depois_do_consentimento(video):
    path = plano(video, targets=["bluesky"])["path"]
    rec = social.recipe(path, provider="zernio")
    post = next(s for s in rec["steps"] if s.get("tool") == "posts_create")
    assert post["args"]["publish_at"] == "now" and post["requires_step"]


def test_receita_recusa_plano_que_nao_confere_e_provedor_desconhecido(video):
    path = plano(video)["path"]
    with pytest.raises(social.SocialError, match="provedor"):
        social.recipe(path, provider="buffer")
    video.write_bytes(video.read_bytes() + b"x")
    with pytest.raises(social.SocialError, match="check"):
        social.recipe(path)


def test_receita_manda_reconferir_o_plano_e_lembra_a_regra_do_consentimento(video):
    rec = social.recipe(plano(video)["path"], clip_id=CLIP_RO)
    assert rec["steps"][0]["kind"] in {"local", "manual"}
    assert any(s["kind"] == "local" and "social check" in s["text"] for s in rec["steps"])
    c = next(s for s in rec["steps"] if s["kind"] == "consent")
    assert "sim" in c["text"].lower() and c["not_consent"]
    assert any("card" in n or "resultado de ferramenta" in n for n in c["not_consent"])
    assert rec["rules"]


# ------------------------------------------------------------------------------------------------ CLI

def test_cli_providers_json_e_texto():
    r = run_cli("social", "providers", "--json")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["default"] == "realoficial"
    t = run_cli("social", "providers")
    assert t.returncode == 0 and "realoficial" in t.stdout and "padrão" in t.stdout and "zernio" in t.stdout


def test_cli_subprocesso_recusa_arquivo_sem_trilha_de_video(video, tmp_path):
    out = tmp_path / "social.plan.json"
    r = run_cli("social", "plan", "--video", video, "--caption", CAPTION, "--target", "youtube", "--target", "tiktok=@conta",
                "--out", out, "--aceito-unverified", "--json")
    # a sonda real não está trocada no subprocesso: o arquivo falso não tem trilha, então o plano é recusado
    assert r.returncode == 1 and "social:" in r.stderr and "Traceback" not in r.stderr


def test_cli_in_process_fluxo_completo(video, capsys):
    assert social.run_social(["plan", "--video", str(video), "--caption", CAPTION, "--target", "youtube", "--target", "tiktok=@conta", "--json"]) == 0
    saida = json.loads(capsys.readouterr().out)
    path = saida["path"]
    assert social.run_social(["check", path, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert social.run_social(["recipe", path]) == 0
    texto = capsys.readouterr().out
    assert "ro_preview_publication" in texto and "consentimento" in texto
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"mudou")
    assert social.run_social(["check", path]) == 1


def test_cli_plan_aceita_legenda_de_arquivo_e_recusa_as_duas_formas(video, tmp_path, capsys):
    leg = tmp_path / "legenda.txt"
    leg.write_text(CAPTION + "\n", encoding="utf8")
    assert social.run_social(["plan", "--video", str(video), "--caption-file", str(leg), "--target", "youtube", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["plan"]["caption"] == CAPTION
    assert social.run_social(["plan", "--video", str(video), "--caption", "a", "--caption-file", str(leg), "--target", "youtube", "--force"]) == 1
    assert "social:" in capsys.readouterr().err


def test_cli_erros_saem_com_codigo_1_sem_traceback(tmp_path, capsys):
    assert social.run_social(["plan", "--video", str(tmp_path / "x.mp4"), "--caption", "a", "--target", "youtube"]) == 1
    assert "não existe" in capsys.readouterr().err
    assert social.run_social(["recipe", str(tmp_path / "nada.json")]) == 1


def test_cli_registra_social_no_help_principal_e_no_proprio():
    r = run_cli("--help")
    assert r.returncode == 0 and re.search(r"^  social\s", r.stdout, re.M)
    h = run_cli("social", "--help")
    assert h.returncode == 0 and "exemplos:" in h.stdout and "simplicio-video social" in h.stdout
    for palavra in ("providers", "plan", "check", "recipe", "realoficial", "zernio", "não posta", "consentimento", "UNVERIFIED"):
        assert palavra in h.stdout, palavra


@needs_ffmpeg
def test_com_ffmpeg_real_o_plano_le_codec_resolucao_e_duracao(tmp_path, monkeypatch):
    monkeypatch.setattr(social, "_probe", social._real_probe)  # sonda real
    mp4 = tmp_path / "real.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=270x480:rate=30:duration=4", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(mp4)], check=True)
    p = ler(social.make_plan(str(mp4), ["tiktok", "instagram"], caption="legenda #teste")["path"])
    v = p["video"]
    assert (v["width"], v["height"], v["aspect_ratio"], v["video_codec"], v["audio_codec"]) == (270, 480, "9:16", "h264", "aac")
    assert 3.9 < v["duration_s"] < 4.3 and v["container"] == "mp4"


# ------------------------------------------------------------------------------------------------ MCP

def test_mcp_social_providers_plan_check_recipe(video):
    assert mcp_server.video_social("providers")["default"] == "realoficial"
    r = mcp_server.video_social("plan", video=str(video), caption=CAPTION, targets=["youtube", "tiktok"])
    assert r["ok"] is True and r["path"].endswith("social.plan.json")
    assert mcp_server.video_social("check", plano=r["path"])["ok"] is True
    rec = mcp_server.video_social("recipe", plano=r["path"], clip_id=CLIP_RO)
    assert rec["ok"] is True and rec["provider"] == "realoficial"
    conferir_consentimento(rec["steps"], {"ro_confirm_publishing"}, ("ro_preview_publication",))
    z = mcp_server.video_social("recipe", plano=r["path"], provider="zernio")
    conferir_consentimento(z["steps"], {"posts_create", "posts_cross_post", "posts_publish_now"})


def test_mcp_social_nunca_publica_e_nao_escolhe_onde_gravar(video):
    for acao in ("publish", "post", "confirm", "run", "send"):
        r = mcp_server.video_social(acao)
        assert r["ok"] is False and "publicar" in r["error"]
    import inspect
    params = set(inspect.signature(mcp_server.video_social).parameters)
    assert "out" not in params and "force" not in params and "accept_unverified" not in params
    assert not [n for n, _, _ in mcp_server.TOOLS if re.search(r"publish|post\b|confirm", n.split(".", 1)[1])]
    assert [n for n, _, _ in mcp_server.TOOLS].count("video.social") == 1


def test_mcp_social_erros_voltam_como_json(tmp_path):
    r = mcp_server.video_social("plan", video=str(tmp_path / "x.mp4"), caption="a", targets=["youtube"])
    assert r["ok"] is False and "não existe" in r["error"]
    assert mcp_server.video_social("check")["ok"] is False
    assert mcp_server.video_social("recipe", plano="x.json", provider="buffer")["ok"] is False
    assert mcp_server.video_social("nada")["ok"] is False


# ------------------------------------------------------------------------------------------------ fronteira do motor

def test_motor_nao_importa_rede_nem_http_nem_cliente_mcp():
    arvore = ast.parse(Path(social.__file__).read_text(encoding="utf8"))
    mods = set()
    for n in ast.walk(arvore):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            mods.add(n.module.split(".")[0])
    proibidos = {"socket", "ssl", "urllib", "http", "requests", "httpx", "aiohttp", "websockets", "ftplib", "smtplib", "mcp",
                 "playwright", "selenium"}
    assert not mods & proibidos, mods & proibidos
    fonte = Path(social.__file__).read_text(encoding="utf8")
    assert not re.search(r"os\.environ|getenv", fonte), "o módulo social não lê variável de ambiente (nenhuma credencial)"


def test_plugin_json_tem_verbos_fechados_do_social_e_nenhum_de_publicar():
    data = json.loads((ROOT / "plugin.json").read_text(encoding="utf8"))
    verbos = {c["verb"]: c for c in data["commands"]}
    sociais = {v for v in verbos if v.startswith("video.social")}
    assert sociais == {"video.social.providers", "video.social.plan", "video.social.check", "video.social.recipe"}
    for v in sociais:
        c = verbos[v]
        assert c["argv"][:2] == ["simplicio-video", "social"] and c["args_schema"]["additionalProperties"] is False
        assert "{args}" not in c["argv"] and "publish" not in " ".join(c["argv"])
    assert not [v for v in verbos if re.search(r"social\.(publish|post|confirm|run)", v)]
    assert "video.social" in data["mcp"]["tools"]


def test_agents_md_aponta_a_excecao_sem_ampliar_a_regra_3():
    ag = (ROOT / "AGENTS.md").read_text(encoding="utf8")
    assert "social" in ag and "docs/decisoes/ADR-0018" in ag
    regra3 = next(l for l in ag.splitlines() if l.startswith("3. The engine must keep working standalone"))
    assert "publishing/posting" in regra3  # a regra continua como estava
    assert "O motor não posta" in ag


def test_adr_explica_por_que_o_social_respeita_a_regra_3():
    adr = ROOT / "docs" / "decisoes" / "ADR-0018-social-planejar-sem-postar.md"
    t = adr.read_text(encoding="utf8")
    for trecho in ("regra 3", "não posta", "Real Oficial", "Zernio", "consentimento", "social.plan.json", "UNVERIFIED"):
        assert trecho in t, trecho
    assert "ADR-0018" in (ROOT / "docs" / "decisoes" / "README.md").read_text(encoding="utf8")


def test_skill_social_ensina_o_fluxo_e_o_consentimento():
    sk = ROOT / "skills" / "simplicio-video-social" / "SKILL.md"
    t = sk.read_text(encoding="utf8")
    assert t.startswith("---\nname: simplicio-video-social\n") and "description:" in t.split("---")[1]
    for trecho in ("social plan", "social recipe", "social check", "ro_preview_publication", "ro_confirm_publishing", "quote_id",
                   "confirm", "sim explícito", "uma postagem", "accept_terms", "tiktok_privacy", "posts_create", "UNVERIFIED",
                   "nunca", "card"):
        assert trecho in t, trecho


def test_dados_social_existem_no_pacote():
    for nome in ("limits.json", "providers.json", "limits.schema.json", "providers.schema.json"):
        assert (paths.data_dir() / "social" / nome).is_file(), nome


# ------------------------------------------------------------------------------------------------ dados e trava da receita

def test_dados_batem_com_os_schemas():
    jsonschema = pytest.importorskip("jsonschema")
    base = paths.data_dir() / "social"
    for dado, esquema in (("limits.json", "limits.schema.json"), ("providers.json", "providers.schema.json")):
        jsonschema.validate(json.loads((base / dado).read_text(encoding="utf8")), json.loads((base / esquema).read_text(encoding="utf8")))


def test_motor_recusa_gerar_receita_que_publica_antes_do_consentimento(video, monkeypatch):
    path = plano(video)["path"]
    doc = social._providers_doc()
    ro = doc["providers"][0]["recipe"]
    ids = [s["id"] for s in ro]
    ro.insert(ids.index("consent"), ro.pop(ids.index("confirm")))  # confirmar antes de pedir o sim
    monkeypatch.setattr(social, "_providers_doc", lambda: doc)
    with pytest.raises(social.SocialError, match="receita insegura"):
        social.recipe(path, clip_id=CLIP_RO)


def test_motor_recusa_receita_sem_cotar_antes_do_consentimento(video, monkeypatch):
    path = plano(video)["path"]
    doc = social._providers_doc()
    ro = doc["providers"][0]["recipe"]
    ro.insert(len(ro) - 1, ro.pop([s["id"] for s in ro].index("preview")))  # cotar só depois de confirmar
    monkeypatch.setattr(social, "_providers_doc", lambda: doc)
    with pytest.raises(social.SocialError, match="receita insegura"):
        social.recipe(path, clip_id=CLIP_RO)


def test_publicar_so_aparece_como_chamada_com_requires_nas_duas_receitas():
    for p in social._providers_doc()["providers"]:
        for s in p["recipe"]:
            if s["kind"] == "call" and s["tool"] in p["publish_tools"]:
                assert s["requires"] == "consent", s["id"]


# ------------------------------------------------------------------------------------------------ achado 1: o plano é revalidado, nunca confiado

def reforjar(path, mutar):
    """Edita o plano e RECALCULA o plan_id, como faria quem sabe como o id é calculado (o id não é autenticação)."""
    pl = ler(path)
    mutar(pl)
    corpo = {k: v for k, v in pl.items() if k not in ("plan_id", "accept_proof")}
    pl["plan_id"] = social.plan_id(corpo)
    Path(path).write_text(json.dumps(pl), encoding="utf8")


def test_plano_forjado_com_id_recalculado_nao_fura_o_limite_oficial(video, monkeypatch):
    path = plano(video, targets=["youtube"])["path"]
    monkeypatch.setattr(social, "_probe", lambda p: {**PROBE_OK, "duration_s": 200.0})  # o arquivo de verdade tem 200 s
    reforjar(path, lambda pl: None)  # só recalcula o id: o plano continua dizendo 20 s
    rep = social.check_plan(path)
    assert rep["ok"] is False and any("duration_max_s" in p for p in rep["problems"]), rep
    with pytest.raises(social.SocialError, match="duration_max_s|não confere"):
        social.recipe(path, clip_id=CLIP_RO)
    forjar_duracao = lambda pl: pl["video"].update(duration_s=200.0)  # noqa: E731
    reforjar(path, forjar_duracao)
    assert social.check_plan(path)["ok"] is False  # 200 s com o limite oficial de 180 s: nem com o plano coerente passa


def test_plano_forjado_nao_ganha_o_aceite_unverified(video, monkeypatch):
    path = plano(video, targets=["tiktok"])["path"]
    monkeypatch.setattr(social, "_probe", lambda p: {**PROBE_OK, "duration_s": 700.0})
    def forjar(pl):
        pl["video"]["duration_s"] = 700.0
        pl["accepted_unverified"] = ["tiktok:duration_max_s"]
    reforjar(path, forjar)
    rep = social.check_plan(path)
    assert rep["ok"] is False and any("aceite" in p or "UNVERIFIED" in p for p in rep["problems"]), rep
    with pytest.raises(social.SocialError):
        social.recipe(path, clip_id=CLIP_RO)


def test_aceite_unverified_legitimo_passa_no_check_e_na_receita(video, monkeypatch):
    monkeypatch.setattr(social, "_probe", lambda p: {**PROBE_OK, "duration_s": 700.0})
    path = plano(video, targets=["tiktok"], accept_unverified=True)["path"]
    assert ler(path)["accepted_unverified"] == ["tiktok:duration_max_s"]
    assert social.check_plan(path)["ok"] is True
    assert social.recipe(path, clip_id=CLIP_RO)["steps"]


def test_aceite_unverified_nao_vale_sem_a_chave_local_de_quem_aceitou(video, monkeypatch, tmp_path):
    monkeypatch.setattr(social, "_probe", lambda p: {**PROBE_OK, "duration_s": 700.0})
    path = plano(video, targets=["tiktok"], accept_unverified=True)["path"]
    monkeypatch.setattr(social, "_accept_key_path", lambda: tmp_path / "outra-maquina" / "social-accept.key", raising=False)
    rep = social.check_plan(path)
    assert rep["ok"] is False and any("aceite" in p for p in rep["problems"])


def test_plano_forjado_com_conta_que_parece_segredo_e_recusado(video):
    path = plano(video, targets=["tiktok"])["path"]
    reforjar(path, lambda pl: pl["targets"].__setitem__(0, {"network": "tiktok", "account": "AIzaSyTESTE_nao_real_000000000000000"}))
    assert social.check_plan(path)["ok"] is False
    with pytest.raises(social.SocialError):
        social.recipe(path, provider="zernio")


def test_plano_forjado_com_conteudo_diferente_do_que_o_plan_geraria_e_recusado(video):
    path = plano(video)["path"]
    reforjar(path, lambda pl: pl["checks"].clear())
    assert social.check_plan(path)["ok"] is False
    path2 = plano(video, force=True)["path"]
    reforjar(path2, lambda pl: pl.update(hashtags=["#inventada"]))
    assert social.check_plan(path2)["ok"] is False
    reforjar(path2, lambda pl: pl.update(extra="campo que o plan nunca gera"))
    assert social.check_plan(path2)["ok"] is False


def test_plano_malformado_vira_erro_do_social_e_nao_traceback(video):
    path = plano(video)["path"]
    for chave in ("caption", "targets", "checks"):
        reforjar(path, lambda pl, chave=chave: pl.pop(chave))
        for chamada in (lambda: social.check_plan(path), lambda: social.recipe(path)):
            try:
                rep = chamada()
            except social.SocialError:
                continue
            assert rep["ok"] is False
        r = mcp_server.video_social("recipe", plano=path)
        assert r["ok"] is False and "error" in r
        r = mcp_server.video_social("check", plano=path)
        assert r["ok"] is False
        plano(video, force=True)
