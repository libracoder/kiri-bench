# How we tested — macOS, 2026-11-02

This is everything done to produce the [2026-11-02 macOS comparison](comparison.md),
in order, so anyone can repeat it or check it.

## 1. One machine, one session

- Apple M3 Max, 16 cores, 64 GB, macOS 27.0.1, on mains power.
- All four engines installed side by side and measured back to back in one
  `matrix` run (18:20–18:34 UTC), so they saw the same machine state.
- Other desktop apps stayed open. Host load average was about 9 at the start
  and 7 at the end of the run.

## 2. Same compute for every engine: 2 CPUs, 8 GB

Defaults differ a lot (OrbStack and Docker Desktop take all 16 cores), so
every engine's VM was set to **2 CPUs and 8 GB** and checked with
`docker --context <engine> info` before the run:

| Engine | How it was set | `docker info` before the run |
|---|---|---|
| Kiri | Default (2 CPUs, memory ceiling 8 GB) | 2 CPUs, 7.8 GiB |
| Docker Desktop | Settings → Resources: CPU limit 2, Memory 8 GB, Apply & restart | 2 CPUs, 7.7 GiB |
| OrbStack | `orb config set cpu 2`, `orb config set memory_mib 8192`, `orb stop`, `orb start` | 2 CPUs, 7.8 GiB |
| Colima | `colima start --cpu 2 --memory 8 --vm-type vz --mount-type virtiofs --runtime docker` | 2 CPUs, 7.7 GiB |

## 3. Nothing else running inside the engines

- OrbStack had a Kubernetes cluster and seven kind/other containers running
  (about 340% CPU). Kubernetes was turned off (`orb config set k8s.enable
  false`) and the containers stopped for the run, then restored afterwards.
- Docker Desktop and Colima had no containers. Kiri had two idle containers
  (nginx and Postgres) that were left running.

## 4. The run

```sh
git clone https://github.com/libracoder/kiri-bench.git
cd kiri-bench
./kiri-bench doctor --engine kiri        # and each other engine
./kiri-bench matrix --engines kiri,docker-desktop,orbstack,colima \
  --label macos-2cpu-8gb-2026-11-02
```

This is a **full run**, the suite defaults with no `--quick`:

| Option | Value |
|---|---|
| Latency samples (`--runs`) | 30, after 3 warmups |
| I/O samples (`--io-runs`) | 5 |
| stdout/stdin transfer (`--transfer-mb`) | 200 MiB |
| Storage write (`--storage-mb`) | 1 GiB with `fsync` |
| Network streams (`--net-seconds`) | 5 s, parallel = 4 |
| HTTP requests (`--http-requests`) | 200 new connections |
| Density (`--density`) | 20 containers |

Images are warm: the suite never removes an image, so "warm pull" measures
the pull path with the image present, not registry download speed.

Each engine is reached only through its own Docker context:
`docker --context kiri | desktop-linux | orbstack | colima`. The direct API
tests use that context's Unix socket, and builds use the buildx builder named
after the context.

## 5. Harness fixes made before this run

Earlier runs that day exposed three kiri-bench bugs. They were fixed in
commit `76713f3`, before the published run:

1. **API socket.** The API suite fell back to `/var/run/docker.sock` for
   every engine except Kiri. On this Mac that is a symlink to OrbStack, so
   "Colima" API numbers were really OrbStack's. It now reads the socket from
   the engine's Docker context.
2. **Build builder.** `buildx` builds on the globally selected builder unless
   told otherwise, so every engine built on the same (Kiri's) builder. Builds
   now pass `--builder <context>`.
3. **Warmup failures.** A failing warmup aborted the whole matrix. It is now
   recorded as a failed test and the run continues.

Results from before these fixes are not published.

## 6. Reading the results

- Times are medians of the samples; p95s are in the comparison. Rates
  (MB/s, containers/s, Gbit/s, req/s) are per-sample medians.
- Winner ratios compare the best engine with the runner-up.
- A failed test counts as a loss. Kiri's build and iperf3 failures come from
  a Kiri image-unpacking bug, described in the comparison.
- Kiri's 21 GB/s volume read is a page-cache figure, not disk speed.

## 7. Check it yourself

The raw per-sample output is not published; run the suite above to produce
your own `summary.json`, `report.md` and `raw/` samples for every engine,
then compare runs with:

```sh
./kiri-bench compare results/run-a/summary.json results/run-b/summary.json
```

The general guide is [Reproduce the runtime comparison](../../REPRODUCE.md).
