# qwen38-27b bench notes

Configs, scripts and results for benching the [syv-ai/qwen38-27b-rtx3090](https://github.com/syv-ai/qwen38-27b-rtx3090) stack
(+ vLLM OffloadingConnector KV eviction) on an RTX 3090 Ti in a Proxmox VM (GPU passthrough).

Related: [field report issue #33](https://github.com/syv-ai/qwen38-27b-rtx3090/issues/33).

- `configs/` — env snapshots per matrix config (API keys redacted; launcher = single-user/start_qwen.sh from the syv repo)
- `bench/` — the harness: `bench_matrix.py` (ladders + eviction pyramid), `ladder_replica.py` (micro-prompt decode ladder, stream + usage token counting), `bench_syv_offload.py` (eviction correctness canaries)
- `results/` — per-config outputs and the running summary table

Methodology notes that bit us (so you don't repeat them): count stream tokens via `usage` (MTP packs 3–4 tokens per SSE chunk);
cold-boot between configs and wipe `/dev/shm/vllm_offload_*.mmap` ghosts; micro-prompt ladders and full-wall ladders are
different genres — report both.
