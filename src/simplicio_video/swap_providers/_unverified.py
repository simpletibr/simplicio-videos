"""Shared base of the adapters written from public documentation that could not be checked against the real API
(UNVERIFIED): fal, wavespeed, kie and alibaba.

They are minimal on purpose. Each sends the clip and the reference image as data URIs in the URL fields, which none of
the four documents as accepted (UNVERIFIED), and `swap run` refuses to spend on them without `--aceito-unverified`.
`estimate`, `providers` and the dry run work without that flag, because they never call the network.
"""
from __future__ import annotations

from .base import Adapter, ProviderError, data_uri


class UnverifiedAdapter(Adapter):
    verified = False
    # provider state name -> orchestration state
    states: dict = {}

    def _json(self, res) -> dict:
        if res.status >= 400:
            raise self._error(res)
        data = res.json()
        if not isinstance(data, dict):
            raise ProviderError(f"{self.name}: resposta que não é JSON", retryable=True, network=True)
        return data

    def _state(self, raw: str | None) -> str:
        return self.states.get(str(raw or "").upper(), "running")

    def _download(self, url: str) -> bytes:
        res = self._call("GET", url)  # result URLs are signed: no key header goes to a third-party host
        if res.status >= 400:
            raise self._error(res)
        return res.body

    def _inputs(self, job) -> tuple[str, str]:
        if not job.refs:
            raise ProviderError(f"{self.name}: falta a imagem de referência", retryable=False)
        return data_uri(job.video), data_uri(job.refs[0])
