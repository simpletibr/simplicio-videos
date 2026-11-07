# Benchmark: measured GPU cost per video second

**Read this first.** Every cost, margin or "seconds per video second" figure written
before this tool was an ESTIMATE. None of them is a measurement. Only `bench/benchmark.py`
produces measured numbers, and only when it runs against a real rented GPU. Do not quote
a cost, price or margin until a `summary.md` from a live run exists.

Status of this code: the cost math is unit-tested. The live path (queue, wait, download,
probe on a real ComfyUI) has **not** been run. See the VERIFY list at the end.

## What the benchmark measures

For each requested duration (default 10 s and 30 s) and each repeat (default 3):

1. Copies the source video and character images into ComfyUI's input folder under unique
   names (`<job_id>_source.mp4`, `<job_id>_char1.png`, ...) and removes the copies afterwards.
2. Builds the prompt with `worker.workflow.build_prompt`, applies the map with
   `apply_workflow`, and queues it with `ComfyClient.queue_prompt`.
3. Measures **wall_seconds** from `queue_prompt` until the outputs are ready. The download
   is not included. This wall time is treated as billed GPU time, because the rented box is
   billed for the whole run.
4. Downloads the first output and probes it with `worker.media.probe` (output duration, size,
   audio).

From those runs it computes, per (duration, provider):

- **s GPU por s de vídeo** = wall_seconds / output_duration_s (mean, min, max)
- **Custo por job** = wall_seconds / 3600 x USD/h x USD-to-BRL x retry-factor
- **Cliente paga** = billed seconds x R$/s, where billed seconds = ceil(output duration),
  never more than the requested duration (CONTRACT section 5)
- **Lucro R$** and **Margem %** = (price - cost) and (price - cost) / price

Failed runs are written to `results.csv` and counted in the failure rate. They are excluded
from the averages.

## Prerequisites

- A rented Vast.ai instance with one RTX 5090 (on-demand, verified). Record the instance's
  actual USD per hour (`dph_total` of the offer you rented).
- The worker code on the box: the live path imports `worker/` (CONTRACT section 1), so run from
  a checkout that contains `worker/`. Python 3.11. This benchmark uses only the standard
  library, but `worker/` may need its own packages (VERIFY).
- `ffprobe` on the box, needed by `worker.media.probe` (VERIFY).
- `nvidia-smi` on PATH (optional; only fills `gpu_name` and `gpu_memory`).
- A ComfyUI install with the H3 model and the Character-Swap LoRA present. Model file names
  are TODO_VERIFY: take them from your exported workflow, never from this document.

## Step by step

### 1. Rent the GPU

On Vast, rent one verified RTX 5090, on-demand. Note the offer's USD per hour. Use that
number in `--provider-prices`. The defaults in the script (`vast=0.767,salad=0.50`) are
planning placeholders, not measurements. Replace them with the real prices.

### 2. Start ComfyUI headless

On the box:

```bash
cd /opt/ComfyUI
python main.py --listen 127.0.0.1 --port 8188 --headless   # VERIFY flags for your ComfyUI version
```

To open the ComfyUI UI from your laptop, use an SSH tunnel with the host and port Vast shows
for the instance (VERIFY):

```bash
ssh -N -L 8188:127.0.0.1:8188 -p <ssh_port> root@<instance_host>
```

Then open `http://127.0.0.1:8188` on your laptop.

### 3. Load the workflow once in the UI

Load your swap workflow in the UI. Confirm that no node is red (every model and custom node
is found). Optional: run one short job by hand to warm up the models. Do not count it.
A cold first run includes model loading, which would inflate the first measurement.

### 4. Export it in API format

Enable the developer options in the ComfyUI settings (VERIFY the label for your version), then
choose **Save (API Format)** and save the file as `workflow_api.json`. Copy it to the box, for
example to `/root/bench/workflow_api.json`. The `.gitignore` already excludes it.

### 5. Write the workflow map

Copy `bench/workflow_map.example.json` to `/root/bench/workflow_map.json` and replace the node
ids and field keys with the ones in your exported `workflow_api.json`. The ids in the example
(`12`, `20`, `21`, `22`, `30`, `40`, `41`, `42`, `90`) are placeholders from CONTRACT section 7.
They are not your graph. Node ids change every time you re-export.

- `inputs.source_video`, `inputs.character_images` (one slot per character),
  `inputs.prompt` are required. `seed`, `length_frames`, `chunk_count` are optional.
- `output.node` must be the node that saves the video. `output.kind` is `videos`, `gifs` or
  `images`, matching the key the save node writes in ComfyUI's history.

The benchmark checks that every node in the map exists in the workflow before it runs.

### 6. Prepare the test inputs

- One source video. Use a real clip with audio, at least as long as the longest duration you
  will test (30 s). Whether the workflow needs the source to be that long is VERIFY.
- 1 to 3 character images, each with a `--replace-description`: a short phrase that describes
  the person, never a name (3 to 200 characters). Example: `o homem de boné, à esquerda`.

Keep these files outside the repo, for example in `/root/bench/`.

### 7. Dry run

From the repo root. This only validates arguments and files. It copies, queues and writes
nothing, and prints no numbers:

```bash
python -m bench.benchmark --dry-run \
  --workflow /root/bench/workflow_api.json \
  --map /root/bench/workflow_map.json \
  --source-video /root/bench/source_30s.mp4 \
  --character-image /root/bench/char1.png \
  --replace-description "o homem de boné, à esquerda" \
  --input-dir /opt/ComfyUI/input
```

Fix anything it reports before the live run.

### 8. Live run

```bash
python -m bench.benchmark \
  --comfy-url http://127.0.0.1:8188 \
  --workflow /root/bench/workflow_api.json \
  --map /root/bench/workflow_map.json \
  --source-video /root/bench/source_30s.mp4 \
  --character-image /root/bench/char1.png \
  --replace-description "o homem de boné, à esquerda" \
  --durations 10 30 --repeats 3 \
  --provider-prices "vast=<your_offer_usd_per_hour>,salad=<salad_usd_per_hour>" \
  --usd-brl <today_usd_brl_rate> \
  --price-brl-per-second 0.16 \
  --retry-factor 2.0 \
  --input-dir /opt/ComfyUI/input \
  --out-dir bench/results
```

With two characters, pass `--character-image` and `--replace-description` twice each, in the
same order. The progress lines go to stderr. The table prints at the end.

Outputs in `bench/results/` (git-ignored):

- `summary.md`: the Portuguese business table, the failure rate and the stress table.
- `results.json`: run records, summary rows, stress rows and metadata (GPU, workflow hash,
  prices, FX).
- `results.csv`: one row per run, including failures and their error text.
- `videos/`: the downloaded output of each successful run.

### 9. Destroy the instance

Destroy the Vast instance when you are done. Do not just stop it: CONTRACT section 9 says
stopped instances can lose their GPU. Use the console or `DELETE /instances/{id}/`.

## Reading the table

| Column | Meaning |
|---|---|
| Vídeo | Requested duration |
| Provedor | Provider whose USD/h is applied to the same measured GPU time |
| s GPU por s de vídeo | Mean (min to max) GPU seconds per second of output |
| Custo por job | Mean BRL cost of the GPU time, with the retry factor |
| Cliente paga | Mean BRL the client pays at the given R$/s |
| Lucro R$ | Client price minus cost |
| Margem % | Profit as a share of the client price |

## Reading the stress table (GPU 3x worse)

The stress table multiplies GPU seconds and cost by 3 and keeps the client price. It answers:
"If the GPU is three times slower than measured, or costs three times as much per second, what
margin is left?"

- Positive margin in every row: the price survives a 3x worse GPU.
- Negative margin in any row: at 3x cost that duration or provider loses money. Raise the price
  per second, use a cheaper provider, or cut retries and wall time, then measure again.

The factor is `STRESS_FACTOR = 3.0` in `bench/benchmark.py`. The function `bench.cost.stress`
takes any factor.

## Limits of this measurement

- **One GPU type, one box.** Salad prices are the same measured time costed at Salad's USD/h.
  That assumes Salad's GPU runs the job as fast. That is not measured (VERIFY).
- **retry-factor is an assumption** (default 2.0). The failure rate is measured and printed.
  Use it to decide whether the assumption holds.
- **Only queue to outputs-ready is billed here.** Instance boot, model download and idle time
  are not in `wall_seconds`. The real cost per paid second is higher. Measure it from the
  provider's billing when you have it.
- **Cold starts.** The first job after ComfyUI starts may load models. Warm up first (step 3).

## VERIFY list

- [ ] ComfyUI launch flags (`--listen`, `--port`, `--headless`) for the installed version.
- [ ] "Enable developer options" and "Save (API Format)" exist in this ComfyUI version.
- [ ] Node ids and field keys in `workflow_map.json` match the export.
- [ ] The workflow sets output length from the mapped frames and chunks, or from the source
      video. Check which, and whether a 30 s source is required.
- [ ] `worker/` imports on the box (`python -c "import worker.comfy_client, worker.media"`)
      with the dependencies it needs.
- [ ] `ffprobe` is installed for `worker.media.probe`.
- [ ] `--provider-prices` matches the USD/h of the rented offer.
- [ ] `gpu_name` in `results.csv` / `summary.md` says RTX 5090.
- [ ] The output kind (`videos`, `gifs`, `images`) matches the save node.
- [ ] Model file names: TODO_VERIFY. Taken from the exported workflow only.
- [ ] `--usd-brl` is the rate on the day of the run.
- [ ] The live loop (queue, wait, download, probe) has not run against ComfyUI. Only the
      loop logic is tested, with a fake backend.
