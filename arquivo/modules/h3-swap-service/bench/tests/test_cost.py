"""Hand-computed checks for bench/cost.py. Pure math: no I/O, no worker/ import."""

from __future__ import annotations

import pytest

from bench import cost

USD_BRL = 5.07
VAST_USD_H = 0.767
SALAD_USD_H = 0.50
PRICE_BRL_PER_S = 0.16
RETRY = 2.0
PROVIDERS = {"vast": VAST_USD_H, "salad": SALAD_USD_H}
HEADER = "| Vídeo | Provedor | s GPU por s de vídeo | Custo por job | Cliente paga | Lucro R$ | Margem % |"


def _ok(duration: int, wall: float, out: float) -> dict:
    return {"duration_requested": duration, "wall_seconds": wall, "output_duration_s": out, "ok": True}


def _failed(duration: int) -> dict:
    return {
        "duration_requested": duration,
        "wall_seconds": None,
        "output_duration_s": None,
        "ok": False,
        "error": "timeout",
    }


RUNS = [
    _ok(10, 500.0, 10.0),  # 50 GPU-s per video-s
    _ok(10, 520.0, 10.0),  # 52
    _ok(10, 540.0, 10.0),  # 54
    _failed(10),  # excluded from averages, counted as failure
    _ok(30, 1500.0, 30.0),  # 50
    _ok(30, 1560.0, 30.0),  # 52
    _failed(30),
]


def _summarize(runs: list[dict] = RUNS) -> list[dict]:
    return cost.summarize(
        runs,
        usd_per_hour_by_provider=PROVIDERS,
        usd_brl=USD_BRL,
        price_brl_per_second=PRICE_BRL_PER_S,
        retry_factor=RETRY,
    )


def _row(rows: list[dict], duration: int, provider: str) -> dict:
    return next(r for r in rows if r["duration_s"] == duration and r["provider"] == provider)


# --- per-run math -----------------------------------------------------------


def test_gpu_seconds_per_video_second_is_wall_over_output():
    # 519 GPU-s for a 30 s clip: 519 / 30 = 17.3
    assert cost.gpu_seconds_per_video_second(519, 30) == pytest.approx(17.3)


def test_gpu_seconds_per_video_second_rejects_bad_input():
    with pytest.raises(ValueError):
        cost.gpu_seconds_per_video_second(100, 0)
    with pytest.raises(ValueError):
        cost.gpu_seconds_per_video_second(-1, 10)


def test_job_cost_brl_hand_computed():
    # 519 / 3600 h * 0.767 USD/h * 5.07 BRL/USD = 2018.23011 / 3600 = 0.560619475
    assert cost.job_cost_brl(519, VAST_USD_H, USD_BRL) == pytest.approx(0.560619475, abs=1e-9)


def test_job_cost_brl_retry_factor_doubles_cost():
    # 0.560619475 * 2 = 1.12123895
    got = cost.job_cost_brl(519, VAST_USD_H, USD_BRL, retry_factor=2.0)
    assert got == pytest.approx(1.12123895, abs=1e-8)


def test_job_cost_brl_zero_gpu_time_is_free():
    assert cost.job_cost_brl(0, VAST_USD_H, USD_BRL) == 0.0


def test_job_cost_brl_rejects_bad_input():
    with pytest.raises(ValueError):
        cost.job_cost_brl(-1, VAST_USD_H, USD_BRL)
    with pytest.raises(ValueError):
        cost.job_cost_brl(10, VAST_USD_H, 0.0)
    with pytest.raises(ValueError):
        cost.job_cost_brl(10, VAST_USD_H, USD_BRL, retry_factor=0.5)


def test_billed_seconds_rounds_up_and_never_exceeds_request():
    # CONTRACT section 5: charge ceil(output_duration_s), never more than reserved
    assert cost.billed_seconds(9.83, 10) == 10
    assert cost.billed_seconds(9.0, 10) == 9
    assert cost.billed_seconds(30.2, 30) == 30


def test_margin_hand_computed():
    # profit = 1.60 - 0.560619475 = 1.039380525 ; pct = profit / 1.60 * 100
    m = cost.margin(1.60, 0.560619475)
    assert m["profit_brl"] == pytest.approx(1.039380525, abs=1e-9)
    assert m["margin_pct"] == pytest.approx(64.9612828125, abs=1e-6)


def test_margin_negative_when_cost_exceeds_price():
    m = cost.margin(1.0, 1.5)
    assert m["profit_brl"] == pytest.approx(-0.5)
    assert m["margin_pct"] == pytest.approx(-50.0)


def test_margin_rejects_non_positive_price():
    with pytest.raises(ValueError):
        cost.margin(0.0, 1.0)


# --- summarize ----------------------------------------------------------------


def test_summarize_one_row_per_duration_and_provider_in_order():
    rows = _summarize()
    assert [(r["duration_s"], r["provider"]) for r in rows] == [
        (10, "vast"),
        (10, "salad"),
        (30, "vast"),
        (30, "salad"),
    ]


def test_summarize_10s_vast_hand_computed():
    row = _row(_summarize(), 10, "vast")
    assert row["runs_ok"] == 3
    assert row["runs_failed"] == 1
    # s GPU per video-s: 50, 52, 54 -> mean 52, min 50, max 54 (failed run ignored)
    assert row["s_gpu_per_video_s_mean"] == pytest.approx(52.0)
    assert row["s_gpu_per_video_s_min"] == pytest.approx(50.0)
    assert row["s_gpu_per_video_s_max"] == pytest.approx(54.0)
    # mean wall 520 s: 520 / 3600 * 0.767 * 5.07 * 2 = 1.1233993333
    assert row["cost_brl_per_job"] == pytest.approx(1.1233993333, abs=1e-9)
    # billed 10 s per job: 10 * 0.16 = 1.60
    assert row["price_brl_per_job"] == pytest.approx(1.60)
    # profit = 1.60 - 1.1233993333 = 0.4766006667 ; margin = 29.7875416667 %
    assert row["profit_brl"] == pytest.approx(0.4766006667, abs=1e-9)
    assert row["margin_pct"] == pytest.approx(29.7875416667, abs=1e-6)


def test_summarize_10s_salad_hand_computed():
    row = _row(_summarize(), 10, "salad")
    # 520 / 3600 * 0.50 * 5.07 * 2 = 2636.4 / 3600 = 0.7323333333
    assert row["cost_brl_per_job"] == pytest.approx(0.7323333333, abs=1e-9)
    assert row["profit_brl"] == pytest.approx(0.8676666667, abs=1e-9)
    assert row["margin_pct"] == pytest.approx(54.2291666667, abs=1e-6)


def test_summarize_30s_vast_hand_computed():
    row = _row(_summarize(), 30, "vast")
    assert row["runs_ok"] == 2
    # ratios 50 and 52 -> mean 51, min 50, max 52
    assert row["s_gpu_per_video_s_mean"] == pytest.approx(51.0)
    # mean wall 1530 s: 1530 / 3600 * 0.767 * 5.07 * 2 = 3.3053865
    assert row["cost_brl_per_job"] == pytest.approx(3.3053865, abs=1e-7)
    # billed 30 s: 30 * 0.16 = 4.80
    assert row["price_brl_per_job"] == pytest.approx(4.80)
    # profit = 4.80 - 3.3053865 = 1.4946135 ; margin = 1.4946135 / 4.80 * 100 = 31.1377812 %
    assert row["margin_pct"] == pytest.approx(31.1377812, abs=1e-6)


def test_failed_runs_do_not_move_the_average():
    failed_with_junk = {
        "duration_requested": 10,
        "wall_seconds": 99999.0,
        "output_duration_s": None,
        "ok": False,
    }
    row = _row(_summarize([_ok(10, 500.0, 10.0), failed_with_junk]), 10, "vast")
    assert row["s_gpu_per_video_s_mean"] == pytest.approx(50.0)
    assert row["runs_failed"] == 1


def test_group_with_only_failures_has_no_stats():
    rows = _summarize([_failed(20)])
    assert [(r["duration_s"], r["provider"], r["runs_ok"], r["runs_failed"]) for r in rows] == [
        (20, "vast", 0, 1),
        (20, "salad", 0, 1),
    ]
    assert all(r["cost_brl_per_job"] is None and r["margin_pct"] is None for r in rows)


def test_billing_uses_ceiling_of_output_capped_at_request():
    row = _row(_summarize([_ok(10, 500.0, 9.83)]), 10, "vast")
    assert row["price_brl_per_job"] == pytest.approx(1.60)  # ceil(9.83) = 10


def test_summarize_empty_runs_gives_no_rows():
    assert _summarize([]) == []


def test_summarize_rejects_non_positive_price_per_second():
    with pytest.raises(ValueError):
        cost.summarize(
            RUNS,
            usd_per_hour_by_provider=PROVIDERS,
            usd_brl=USD_BRL,
            price_brl_per_second=0.0,
            retry_factor=RETRY,
        )


# --- stress -------------------------------------------------------------------


def test_stress_triples_gpu_time_and_cost_and_recomputes_margin():
    summary = _summarize()
    base = _row(summary, 10, "vast")
    stressed = _row(cost.stress(summary, factor=3.0), 10, "vast")
    assert stressed["s_gpu_per_video_s_mean"] == pytest.approx(156.0)
    assert stressed["cost_brl_per_job"] == pytest.approx(3 * base["cost_brl_per_job"])
    assert stressed["price_brl_per_job"] == pytest.approx(1.60)
    # 1.60 - 3.370198 = -1.770198 ; margin = -1.770198 / 1.60 * 100 = -110.637375 %
    assert stressed["profit_brl"] == pytest.approx(-1.770198, abs=1e-6)
    assert stressed["margin_pct"] == pytest.approx(-110.637375, abs=1e-5)


def test_stress_defaults_to_factor_three():
    summary = _summarize()
    assert cost.stress(summary) == cost.stress(summary, factor=3.0)


def test_stress_keeps_empty_rows_empty():
    stressed = cost.stress(_summarize([_failed(20)]))
    assert all(r["cost_brl_per_job"] is None and r["margin_pct"] is None for r in stressed)


def test_stress_rejects_non_positive_factor():
    with pytest.raises(ValueError):
        cost.stress(_summarize(), factor=0)


# --- rendering ----------------------------------------------------------------


def test_render_markdown_portuguese_header_and_10s_vast_row():
    lines = cost.render_markdown(_summarize()).strip().splitlines()
    assert lines[0] == HEADER
    assert lines[1].startswith("|---")
    row = next(line for line in lines if line.startswith("| 10s | vast |"))
    assert "52,00 (50,00–54,00)" in row
    assert "R$ 1,12" in row  # cost 1.1234
    assert "R$ 1,60" in row  # price
    assert "0,48" in row  # profit 0.4766
    assert "29,8%" in row  # margin


def test_render_markdown_dashes_for_rows_without_successful_runs():
    lines = cost.render_markdown(_summarize([_failed(20)])).strip().splitlines()
    assert "| 20s | vast | — | — | — | — | — |" in lines


def test_fmt_number_uses_brazilian_separators():
    assert cost.fmt_number(1234.5, 2) == "1.234,50"
    assert cost.fmt_number(-0.08, 2) == "-0,08"
    assert cost.fmt_number(29.785, 1) == "29,8"
