"""G0 (golden, caracterização): quais caracteres cada limpador de texto de terceiro tira, marca ou deixa passar.

Seis implementações do mesmo cuidado ("texto de fora não esconde instrução nem escape de terminal") com conjuntos diferentes.
A tabela caractere x módulo abaixo é o comportamento de HOJE; cada discordância é uma divergência herdada, marcada "U22 decide".
A correção U22a só pode mudar linhas desta tabela, e o diff dela é o que o dono aprova.

Colunas (nesta ordem; cada função recebe "a" + caractere + "b" e a saída é classificada):
  texto para o agente (tira):  matchcut._limpa_mcp, instagram._limpa_mcp, video_to_skill.limpa_mcp
  texto para o terminal (marca): matchcut.visivel, instagram.visivel, video_to_skill.visivel
  outros: busca._base, doctor_trilhas._limpa, openverse._s, openverse._clean_text
Classes: keep (passa igual), drop (some), space (vira espaço), nl (vira quebra de linha), mark (vira a marca do bloco U+2400, DEL = U+2421),
  hex (vira <U+XXXX>).

Privados exercitados por import direto (caracterização; sem API pública equivalente): todas as funções acima. `busca._base` também
mascara credenciais do ambiente: o teste zera `busca._valores_secretos`. `openverse._clean_text` é do texto digitado pelo usuário (não de
terceiro) e só entra porque o plano a lista entre as variantes: nele o ESC passa."""
from __future__ import annotations

import pytest

from simplicio_video import busca, doctor_trilhas, instagram, matchcut, openverse, video_to_skill

COLUNAS = ("matchcut._limpa_mcp", "instagram._limpa_mcp", "video_to_skill.limpa_mcp",
           "matchcut.visivel", "instagram.visivel", "video_to_skill.visivel",
           "busca._base", "doctor_trilhas._limpa", "openverse._s", "openverse._clean_text")
AGENTE, TERMINAL, OUTROS = slice(0, 3), slice(3, 6), slice(6, 10)


@pytest.fixture(autouse=True)
def _sem_segredo_do_ambiente(monkeypatch):
    monkeypatch.setattr(busca, "_valores_secretos", lambda: [])


def funcoes() -> tuple:
    return (matchcut._limpa_mcp, instagram._limpa_mcp, video_to_skill.limpa_mcp,
            matchcut.visivel, instagram.visivel, video_to_skill.visivel,
            busca._base, doctor_trilhas._limpa, openverse._s, lambda t: openverse._clean_text(t, "campo"))


def classe(c: str, saida: str) -> str:
    n = ord(c)
    assert saida.startswith("a") and saida.endswith("b") and len(saida) >= 2, repr(saida)
    meio = saida[1:-1]
    if meio == c:
        return "keep"
    if meio == "":
        return "drop"
    if meio == " ":
        return "space"
    if meio == "\n":
        return "nl"
    if meio == chr(0x2421 if n == 0x7F else 0x2400 + n):
        return "mark"
    assert meio == f"<U+{n:04X}>", repr(saida)
    return "hex"


# (rótulo, caractere, classe em cada coluna de COLUNAS)
TABELA = [
    ("NUL", "\x00", "drop drop drop mark mark mark drop space drop keep"),
    ("BEL", "\x07", "drop drop drop mark mark mark drop space drop keep"),
    ("BS", "\x08", "drop drop drop mark mark mark drop space drop keep"),
    ("TAB", "\t", "keep keep keep keep keep keep keep space space space"),
    ("LF", "\n", "keep keep keep keep keep keep keep space space space"),
    ("VT", "\x0b", "drop drop drop mark mark mark drop space space space"),
    ("FF", "\x0c", "drop drop drop mark mark mark drop space space space"),
    ("CR", "\r", "drop drop drop mark mark mark nl space space space"),
    ("ESC", "\x1b", "drop drop drop mark mark mark drop space drop keep"),
    ("US", "\x1f", "drop drop drop mark mark mark drop space space space"),
    ("DEL", "\x7f", "drop drop drop mark mark mark drop space drop keep"),
    ("C1 NEL U+0085", "\x85", "drop drop drop hex hex hex drop space space space"),
    ("C1 CSI U+009B", "\x9b", "drop drop drop hex hex hex drop space drop keep"),
    ("NBSP U+00A0", "\xa0", "keep keep keep keep keep keep keep keep space space"),
    ("SHY U+00AD", "\xad", "drop drop drop hex hex hex drop space drop keep"),
    ("CGJ U+034F", "\u034f", "keep keep keep keep keep keep drop keep keep keep"),
    ("ARABIC NUMBER SIGN U+0600", "\u0600", "drop drop drop hex hex hex keep space drop keep"),
    ("ALM U+061C", "\u061c", "drop drop drop hex hex hex keep space drop keep"),
    ("SYRIAC U+070F", "\u070f", "drop drop drop hex hex hex keep space drop keep"),
    ("HANGUL CHOSEONG FILLER U+115F", "\u115f", "keep keep keep keep keep keep keep space keep keep"),
    ("MONGOLIAN VS U+180E", "\u180e", "drop drop drop hex hex hex drop space drop keep"),
    ("ZWSP U+200B", "\u200b", "drop drop drop hex hex hex drop space drop keep"),
    ("ZWNJ U+200C", "\u200c", "drop drop drop hex hex hex drop space drop keep"),
    ("ZWJ U+200D", "\u200d", "drop drop drop hex hex hex drop space drop keep"),
    ("LRM U+200E", "\u200e", "drop drop drop hex hex hex drop space drop keep"),
    ("RLM U+200F", "\u200f", "drop drop drop hex hex hex drop space drop keep"),
    ("LSEP U+2028", "\u2028", "drop drop drop hex hex hex nl space space space"),
    ("PSEP U+2029", "\u2029", "drop drop drop hex hex hex nl space space space"),
    ("LRE U+202A", "\u202a", "drop drop drop hex hex hex drop space drop keep"),
    ("RLO U+202E", "\u202e", "drop drop drop hex hex hex drop space drop keep"),
    ("NNBSP U+202F", "\u202f", "keep keep keep keep keep keep keep keep space space"),
    ("WJ U+2060", "\u2060", "drop drop drop hex hex hex drop space drop keep"),
    ("INVISIBLE PLUS U+2064", "\u2064", "drop drop drop hex hex hex drop space drop keep"),
    ("U+2065 (nao atribuido)", "\u2065", "drop drop drop hex hex hex keep keep drop keep"),
    ("LRI U+2066", "\u2066", "drop drop drop hex hex hex drop space drop keep"),
    ("PDI U+2069", "\u2069", "drop drop drop hex hex hex drop space drop keep"),
    ("U+206A", "\u206a", "drop drop drop hex hex hex keep space drop keep"),
    ("U+206F", "\u206f", "drop drop drop hex hex hex keep space drop keep"),
    ("BRAILLE BLANK U+2800", "\u2800", "keep keep keep keep keep keep drop keep keep keep"),
    ("IDEOGRAPHIC SPACE U+3000", "\u3000", "keep keep keep keep keep keep keep keep space space"),
    ("HANGUL FILLER U+3164", "\u3164", "keep keep keep keep keep keep drop space keep keep"),
    ("VS1 U+FE00", "\ufe00", "drop drop drop hex hex hex keep keep keep keep"),  # U22a: era "keep drop keep keep hex keep ..." (só o instagram)
    ("VS16 U+FE0F", "\ufe0f", "drop drop drop hex hex hex keep keep keep keep"),  # U22a: idem
    ("BOM U+FEFF", "\ufeff", "drop drop drop hex hex hex drop space drop keep"),
    ("ANNOTATION U+FFF9", "\ufff9", "drop drop drop hex hex hex keep space drop keep"),
    ("U+FFFB", "\ufffb", "drop drop drop hex hex hex keep space drop keep"),
    ("PRIVATE USE U+E000", "\ue000", "drop drop drop hex hex hex keep keep drop keep"),
    ("U+0378 (nao atribuido)", "\u0378", "drop drop drop hex hex hex keep keep drop keep"),
    ("TAG U+E0000", "\U000e0000", "drop drop drop hex hex hex drop space drop keep"),
    ("TAG U+E0001", "\U000e0001", "drop drop drop hex hex hex drop space drop keep"),
    ("TAG U+E0041", "\U000e0041", "drop drop drop hex hex hex drop space drop keep"),
    ("TAG U+E007F", "\U000e007f", "drop drop drop hex hex hex drop space drop keep"),
    ("VS17 U+E0100", "\U000e0100", "drop drop drop hex hex hex keep space keep keep"),  # U22a: era "keep drop keep keep hex keep ..." (só o instagram)
    ("VS256 U+E01EF", "\U000e01ef", "drop drop drop hex hex hex keep space keep keep"),  # U22a: idem
    ("combining acute U+0301", "\u0301", "keep keep keep keep keep keep keep keep keep keep"),
    ("a com til (precomposto) U+00E3", "\xe3", "keep keep keep keep keep keep keep keep keep keep"),
    ("kanji U+65E5", "\u65e5", "keep keep keep keep keep keep keep keep keep keep"),
    ("emoji U+1F600", "\U0001f600", "keep keep keep keep keep keep keep keep keep keep"),
]


@pytest.mark.parametrize("linha", TABELA, ids=lambda x: x[0])
def test_the_table_of_characters_by_module_is_the_one_of_today(linha):
    _, c, esperado = linha
    obtido = [classe(c, f("a" + c + "b")) for f in funcoes()]
    assert dict(zip(COLUNAS, obtido)) == dict(zip(COLUNAS, esperado.split()))


def discordam(grupo: slice) -> set:
    return {r[0] for r in TABELA if len(set(r[2].split()[grupo])) > 1}


def test_the_three_agent_text_versions_disagree_only_on_variation_selectors():
    # U22 decide: instagram tira os seletores de variação (U+FE00-FE0F, U+E0100-E01EF); matchcut e video_to_skill deixam passar
    # U22a decidiu: os três tiram (é a mesma função, `terceiros.limpa_mcp`): já não discordam em nada (o nome deste teste é histórico: o id não muda)
    assert discordam(AGENTE) == set()


def test_the_three_terminal_versions_disagree_only_on_variation_selectors():
    # U22 decide: instagram.visivel mostra <U+FE0F> etc.; as outras duas deixam o seletor invisível passar para o terminal
    # U22a decidiu: os três mostram (é a mesma função, `terceiros.visivel`): já não discordam em nada (o nome deste teste é histórico: o id não muda)
    assert discordam(TERMINAL) == set()


def test_the_other_cleaners_agree_only_on_ordinary_text_and_the_emoji_selectors():
    # U22 decide: busca, doctor_trilhas e openverse têm cada um o seu conjunto; só concordam (todos deixam passar) nestes 6 caracteres
    concordam = {r[0] for r in TABELA if len(set(r[2].split()[OUTROS])) == 1}
    assert concordam == {"VS1 U+FE00", "VS16 U+FE0F", "combining acute U+0301", "a com til (precomposto) U+00E3", "kanji U+65E5",
                         "emoji U+1F600"}
    busca_difere = {r[0] for r in TABELA if r[2].split()[0] != r[2].split()[6]}
    assert {"ARABIC NUMBER SIGN U+0600", "ALM U+061C", "SYRIAC U+070F", "U+206A", "U+206F", "ANNOTATION U+FFF9", "U+FFFB",
            "PRIVATE USE U+E000", "U+2065 (nao atribuido)", "U+0378 (nao atribuido)"} <= busca_difere  # a regra por categoria tira, a da busca deixa
    assert {"CGJ U+034F", "BRAILLE BLANK U+2800", "HANGUL FILLER U+3164", "CR", "LSEP U+2028", "PSEP U+2029"} <= busca_difere  # a da busca tira ou quebra, a por categoria deixa


@pytest.mark.parametrize("texto", ["a\r\nb", "a\rb"], ids=["CRLF", "CR"])
def test_a_carriage_return_is_normalised_differently(texto):
    obtido = dict(zip(COLUNAS, (f(texto) for f in funcoes())))
    if texto == "a\r\nb":
        assert obtido == {"matchcut._limpa_mcp": "a\nb", "instagram._limpa_mcp": "a\nb", "video_to_skill.limpa_mcp": "a\nb",
                          "matchcut.visivel": "a\nb", "instagram.visivel": "a\nb", "video_to_skill.visivel": "a\nb",
                          "busca._base": "a\nb", "doctor_trilhas._limpa": "a  b", "openverse._s": "a b", "openverse._clean_text": "a b"}
    else:  # U22 decide: o CR sozinho some no texto para o agente, vira a marca no terminal, quebra linha na busca
        assert obtido == {"matchcut._limpa_mcp": "ab", "instagram._limpa_mcp": "ab", "video_to_skill.limpa_mcp": "ab",
                          "matchcut.visivel": "a\u240db", "instagram.visivel": "a\u240db", "video_to_skill.visivel": "a\u240db",
                          "busca._base": "a\nb", "doctor_trilhas._limpa": "a b", "openverse._s": "a b", "openverse._clean_text": "a b"}


def test_a_lone_surrogate_is_dropped_marked_or_kept_depending_on_the_module():
    obtido = dict(zip(COLUNAS, (f("a\ud800b") for f in funcoes())))
    assert obtido == {"matchcut._limpa_mcp": "ab", "instagram._limpa_mcp": "ab", "video_to_skill.limpa_mcp": "ab",
                      "matchcut.visivel": "a<U+D800>b", "instagram.visivel": "a<U+D800>b", "video_to_skill.visivel": "a<U+D800>b",
                      "busca._base": "ab", "doctor_trilhas._limpa": "a\ud800b",  # U22 decide: o doctor e o openverse._clean_text deixam passar
                      "openverse._s": "ab", "openverse._clean_text": "a\ud800b"}


def test_a_zero_width_joiner_sequence_loses_its_joiner_in_every_cleaner_but_two():
    familia = "\U0001f468\u200d\U0001f469"
    obtido = dict(zip(COLUNAS, (f(familia) for f in funcoes())))
    assert obtido == {"matchcut._limpa_mcp": "\U0001f468\U0001f469", "instagram._limpa_mcp": "\U0001f468\U0001f469",
                      "video_to_skill.limpa_mcp": "\U0001f468\U0001f469",
                      "matchcut.visivel": "\U0001f468<U+200D>\U0001f469", "instagram.visivel": "\U0001f468<U+200D>\U0001f469",
                      "video_to_skill.visivel": "\U0001f468<U+200D>\U0001f469",
                      "busca._base": "\U0001f468\U0001f469", "doctor_trilhas._limpa": "\U0001f468 \U0001f469",
                      "openverse._s": "\U0001f468\U0001f469", "openverse._clean_text": "\U0001f468\u200d\U0001f469"}


def test_plain_text_in_portuguese_and_japanese_is_untouched_by_every_cleaner():
    for texto in ("ação, coração e não", "日本語のテキスト", "e\u0301 (acento combinante)"):
        assert [f(texto) for f in funcoes()[:6]] == [texto] * 6
        assert busca._base(texto) == doctor_trilhas._limpa(texto) == openverse._s(texto) == texto
