# simplicio-videos

> 에이전트가 구동하는 결정론적 영상 엔진입니다. YAML 계약을 입력하면 MP4가 출력되며, 그 주변에 오디오, 영상, 음성, 캐릭터 교체, 소셜 게시 계획, 에셋 라이선스, 웹 조사를 위한 도구 모음이 있습니다.

[영어 및 모든 언어: 기준 README](../README.md) · [포르투갈어](../README.pt-BR.md)

## 주요 기능

- **계약에서 MP4로:** YAML 계약을 검증하고, 내레이션을 생성하고, HyperFrames로 결정론적으로 렌더링하며 -14 LUFS로 믹싱한 뒤 매니페스트를 씁니다. 렌더링 경로에서는 LLM이 실행되지 않습니다.
- **음성:** 제공자 `file`, `local`(Kokoro-82M), `gemini`, `voxcpm`, `openvoice`, `voicestudio`(로컬 앱)를 지원합니다. `elevenlabs`와 `xai`는 스텁(stub, 미구현)입니다.
- **오디오와 영상(`media`):** 프로브, 오디오 추출, 프레임 시트, 자막, 영역 마스크, 더빙, 출처 기록과 함께 공개 영상 1개 다운로드.
- **세로 클립 추출(`shorts`):** 단어 단위 전사에 고정 규칙을 적용해 긴 영상에서 9:16 클립을 만듭니다.
- **EDL 편집(`edit`):** 에이전트가 EDL을 작성하고, 고정 버전 video-use 도우미가 ffmpeg를 실행합니다.
- **템플릿과 카탈로그:** 업종별 템플릿 14개(8개는 바로 렌더링 가능), 모션 카탈로그 55개 항목, 광고 형식 50개, 앵글 50개.
- **캐릭터 교체와 작업(`swap`, `jobs`):** 여섯 개 어댑터를 통한 유료 교체로, 비용 추정과 US$ 상한이 있으며 터미널에서만 실행합니다. swap과 로컬 음성은 백그라운드 작업으로 실행할 수 있습니다.
- **외부 제작 트랙:** Hypit, OpenMontage, OpenCut, Toonflow, MoneyPrinterTurbo. 각각 고정 버전으로 별도 프로그램으로 실행되며, 가져와서 쓰지 않습니다.
- **소셜 계획(`social`):** 영상이 네트워크별 제한을 만족하는지 확인하고 계획을 씁니다. **게시하지 않습니다.**
- **라이선스 라이브러리(`openverse`):** 검색, 안전한 다운로드, 요청별 검토, 크레딧을 포함한 내보내기.
- **웹 조사(`busca`):** TinyFish를 통한 검색과 페이지 읽기. 결과마다 출처와 날짜를 붙이며, 하루 호출 한도가 있습니다.
- **UGC 트랙:** 가상 캐릭터용 프롬프트 파일과 수동 파이프라인. 렌더링 밖에서 동작합니다.
- **에이전트 연동:** 28개의 `video.*` 도구를 가진 MCP 서버, 6개의 skills, 11개 에이전트 호스트에 설치하는 `install`.
- **운영:** 상태, 고정된 트랙, 진단, 작업 공간, 업데이트, 공용 Simplicio 로그인.

## 빠른 시작

```bash
gh repo clone simpletibr/simplicio-videos && cd simplicio-videos
pip install -e .                      # `simplicio-video` command (Python >= 3.10); rendering needs Node >= 22 and ffmpeg
simplicio-video setup                 # first run
simplicio-video install               # copy the skills into your agent host (project; --global for the home folder)
simplicio-video doctor                # check what is missing

cd clients/<cliente>/<campanha>       # a client project with a contract.yaml
simplicio-video validate contract.yaml
simplicio-video voice contract.yaml   # narration; local draft voice or --provider file|gemini|voxcpm|openvoice|voicestudio
simplicio-video render contract.yaml  # out/<cliente>-<campanha>.mp4 + render.manifest.json
```

## 한계

- **검증되지 않은 교체 어댑터:** `fal`, `wavespeed`, `kie`, `alibaba`는 공개 문서를 바탕으로 작성되었으며, 실제 API에 대해 검증되지 않았습니다.
- **게시 기능 없음:** 엔진은 소셜 네트워크에 게시하거나 업로드하지 않습니다.
- **플랫폼:** 패키지는 Linux용으로 분류되어 있으며, macOS와 Windows는 실제 기기에서 확인되지 않았습니다.

이 요약은 [기준 README](../README.md)보다 짧으며, 기준 문서보다 최신이 아닐 수 있습니다.
