"""Pure cost and margin math for the H3 swap benchmark. No I/O.

Units: GPU time in seconds, GPU rates in USD per hour, prices in BRL.
The measured wall time of a job is treated as billed GPU time, because the
rented box is billed for the whole run (see bench/README_bench.md).
Billing rule follows CONTRACT section 5: charge ceil(output_duration_s),
never more than the requested duration.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from statistics import fmean
from typing import Any

SECONDS_PER_HOUR = 3600.0
TABLE_HEADER = "| Vídeo | Provedor | s GPU por s de vídeo | Custo por job | Cliente paga | Lucro R$ | Margem % |"


def _require_non_negative(value: float, name: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")


def _require_positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {value!r}")


def gpu_seconds_per_video_second(wall_seconds: float, output_duration_s: float) -> float:
    """GPU seconds spent per second of generated video."""
    _require_non_negative(wall_seconds, "wall_seconds")
    _require_positive(output_duration_s, "output_duration_s")
    return wall_seconds / output_duration_s


def job_cost_brl(
    gpu_seconds: float,
    usd_per_hour: float,
    usd_brl: float,
    retry_factor: float = 1.0,
) -> float:
    """Cost in BRL of one job: GPU time x hourly rate x FX x retry multiplier."""
    _require_non_negative(gpu_seconds, "gpu_seconds")
    _require_non_negative(usd_per_hour, "usd_per_hour")
    _require_positive(usd_brl, "usd_brl")
    if not math.isfinite(retry_factor) or retry_factor < 1.0:
        raise ValueError(f"retry_factor must be >= 1.0, got {retry_factor!r}")
    return gpu_seconds / SECONDS_PER_HOUR * usd_per_hour * usd_brl * retry_factor


def billed_seconds(output_duration_s: float, requested_s: int) -> int:
    """Seconds the client pays for: ceil of the output duration, capped at the request."""
    return min(math.ceil(output_duration_s), requested_s)


def margin(price_brl: float, cost_brl: float) -> dict[str, float]:
    """Profit in BRL and margin as a percentage of the price."""
    _require_positive(price_brl, "price_brl")
    _require_non_negative(cost_brl, "cost_brl")
    profit = price_brl - cost_brl
    return {"profit_brl": profit, "margin_pct": profit / price_brl * 100.0}


def _empty_row(duration_s: int, provider: str, failed: int) -> dict[str, Any]:
    return {
        "duration_s": duration_s,
        "provider": provider,
        "runs_ok": 0,
        "runs_failed": failed,
        "s_gpu_per_video_s_mean": None,
        "s_gpu_per_video_s_min": None,
        "s_gpu_per_video_s_max": None,
        "cost_brl_per_job": None,
        "price_brl_per_job": None,
        "profit_brl": None,
        "margin_pct": None,
    }


def summarize(
    runs: Iterable[Mapping[str, Any]],
    *,
    usd_per_hour_by_provider: Mapping[str, float],
    usd_brl: float,
    price_brl_per_second: float,
    retry_factor: float,
) -> list[dict[str, Any]]:
    """One row per (requested duration, provider). Failed runs are counted, never averaged.

    Each run needs: duration_requested, ok, wall_seconds, output_duration_s.
    Rates come from usd_per_hour_by_provider; the same measured GPU time is
    costed under every provider.
    """
    _require_positive(price_brl_per_second, "price_brl_per_second")

    groups: dict[int, list[Mapping[str, Any]]] = {}
    for run in runs:
        groups.setdefault(int(run["duration_requested"]), []).append(run)

    rows: list[dict[str, Any]] = []
    for duration in sorted(groups):
        group = groups[duration]
        ok_runs = [r for r in group if r.get("ok") is True]
        failed = len(group) - len(ok_runs)
        for provider, usd_per_hour in usd_per_hour_by_provider.items():
            if not ok_runs:
                rows.append(_empty_row(duration, provider, failed))
                continue

            ratios = [
                gpu_seconds_per_video_second(float(r["wall_seconds"]), float(r["output_duration_s"]))
                for r in ok_runs
            ]
            costs = [
                job_cost_brl(float(r["wall_seconds"]), usd_per_hour, usd_brl, retry_factor)
                for r in ok_runs
            ]
            prices = [
                billed_seconds(float(r["output_duration_s"]), duration) * price_brl_per_second
                for r in ok_runs
            ]
            mean_cost = fmean(costs)
            mean_price = fmean(prices)
            result = margin(mean_price, mean_cost)
            rows.append(
                {
                    "duration_s": duration,
                    "provider": provider,
                    "runs_ok": len(ok_runs),
                    "runs_failed": failed,
                    "s_gpu_per_video_s_mean": fmean(ratios),
                    "s_gpu_per_video_s_min": min(ratios),
                    "s_gpu_per_video_s_max": max(ratios),
                    "cost_brl_per_job": mean_cost,
                    "price_brl_per_job": mean_price,
                    "profit_brl": result["profit_brl"],
                    "margin_pct": result["margin_pct"],
                }
            )
    return rows


def stress(summary: Iterable[Mapping[str, Any]], factor: float = 3.0) -> list[dict[str, Any]]:
    """Same rows as summarize(), with GPU time and cost multiplied by factor.

    Price is unchanged, so the margin shows what is left if the GPU is `factor`
    times slower (or more expensive per second) than measured.
    """
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError(f"factor must be > 0, got {factor!r}")

    stressed: list[dict[str, Any]] = []
    for row in summary:
        new = dict(row)
        if row["cost_brl_per_job"] is not None:
            new["s_gpu_per_video_s_mean"] = row["s_gpu_per_video_s_mean"] * factor
            new["s_gpu_per_video_s_min"] = row["s_gpu_per_video_s_min"] * factor
            new["s_gpu_per_video_s_max"] = row["s_gpu_per_video_s_max"] * factor
            new_cost = row["cost_brl_per_job"] * factor
            result = margin(row["price_brl_per_job"], new_cost)
            new["cost_brl_per_job"] = new_cost
            new["profit_brl"] = result["profit_brl"]
            new["margin_pct"] = result["margin_pct"]
        stressed.append(new)
    return stressed


def fmt_number(value: float, decimals: int) -> str:
    """Brazilian number format: 1.234,50."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _cell_money(value: float | None, prefix: bool = True) -> str:
    if value is None:
        return "—"
    text = fmt_number(value, 2)
    return f"R$ {text}" if prefix else text


def render_markdown(summary: Iterable[Mapping[str, Any]]) -> str:
    """Compact business table with Portuguese headers, one line per row."""
    lines = [TABLE_HEADER, "|---|---|---:|---:|---:|---:|---:|"]
    for row in summary:
        mean = row["s_gpu_per_video_s_mean"]
        if mean is None:
            gpu_cell = "—"
            margin_cell = "—"
        else:
            gpu_cell = (
                f"{fmt_number(mean, 2)} "
                f"({fmt_number(row['s_gpu_per_video_s_min'], 2)}–{fmt_number(row['s_gpu_per_video_s_max'], 2)})"
            )
            margin_cell = f"{fmt_number(row['margin_pct'], 1)}%"
        lines.append(
            "| {duration}s | {provider} | {gpu} | {cost} | {price} | {profit} | {margin} |".format(
                duration=row["duration_s"],
                provider=row["provider"],
                gpu=gpu_cell,
                cost=_cell_money(row["cost_brl_per_job"]),
                price=_cell_money(row["price_brl_per_job"]),
                profit=_cell_money(row["profit_brl"], prefix=False),
                margin=margin_cell,
            )
        )
    return "\n".join(lines) + "\n"
