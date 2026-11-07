# simplicio-videos

> エージェントが駆動する決定論的な動画エンジンで、YAML契約を入力すると MP4 が出力されます。その周囲には、音声、動画、音声合成、キャラクター差し替え、ソーシャル計画、素材ライセンス、Web調査のためのツール群があります。

[英語および全言語：正規の README](../README.md) · [ポルトガル語](../README.pt-BR.md)

## 主な機能

- **契約から MP4 へ：** YAML契約を検証し、ナレーションを生成し、HyperFrames で決定論的にレンダリングして -14 LUFS でミックスし、マニフェストを書き出します。レンダリングの経路で LLM は動きません。
- **音声：** プロバイダ `file`、`local`（Kokoro-82M）、`gemini`、`voxcpm`、`openvoice`、`voicestudio`（ローカルアプリ）。`elevenlabs` と `xai` はスタブ（未実装）です。
- **音声と動画（`media`）：** プローブ、音声抽出、フレームシート、字幕、ボックス単位のマスク、吹き替え、公開動画1本のダウンロード（出所の記録付き）。
- **縦動画の切り抜き（`shorts`）：** 単語単位の文字起こしに基づく固定ルールで、長い動画から 9:16 のクリップを切り出します。
- **EDL 編集（`edit`）：** エージェントが EDL を書き、固定版の video-use のヘルパーが ffmpeg を実行します。
- **テンプレートとカタログ：** 業種テンプレート 14 種（うち 8 種はすぐにレンダリング可能）、モーションカタログ 55 件、広告フォーマット 50 種、アングル 50 種。
- **キャラクター差し替えとジョブ（`swap`、`jobs`）：** 6 つのアダプタによる有料の差し替え。コスト見積もりと US$ 上限があり、ターミナルからのみ実行できます。swap とローカル音声はバックグラウンドジョブとして実行できます。
- **外部制作トラック：** Hypit、OpenMontage、OpenCut、Toonflow、MoneyPrinterTurbo。いずれも固定されており、別のプログラムとして実行され、インポートはされません。
- **ソーシャル計画（`social`）：** 動画をネットワークごとの制限に照らして確認し、計画を書き出します。**投稿は一切しません。**
- **ライセンス済みライブラリ（`openverse`）：** 検索、安全なダウンロード、リクエストごとのレビュー、クレジット付きのエクスポート。
- **Web調査（`busca`）：** TinyFish 経由で検索とページ読み取りを行います。結果ごとに出典と日付が付き、1日の呼び出し上限があります。
- **UGC トラック：** 合成キャラクターのプロンプトファイルと手動のパイプライン。レンダリングの外にあります。
- **エージェント連携：** 28 個の `video.*` ツールを持つ MCP サーバー、6 つの skills、11 のエージェントホストへ `install` で導入。
- **運用：** ステータス、固定されたトラック、診断、ワークスペース、更新、共有の Simplicio ログイン。

## クイックスタート

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

## 制限事項

- **未検証の差し替えアダプタ：** `fal`、`wavespeed`、`kie`、`alibaba` は公開ドキュメントをもとに書かれており、実際の API での検証は済んでいません。
- **投稿機能なし：** エンジンはソーシャルネットワークへの投稿もアップロードも行いません。
- **プラットフォーム：** パッケージは Linux 向けに分類されています。macOS と Windows は実機で確認されていません。

この要約は[正規の README](../README.md) より短く、正規版より内容が遅れている場合があります。
