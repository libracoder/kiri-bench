# How we tested — macOS, 2026-11-03

This is everything done to produce the [2026-11-03 macOS comparison](comparison.md),
in order, so anyone can repeat it or check it.

## 1. One machine, two sessions

- Apple M3 Max, 16 cores, 64 GB, macOS 27.0.1, on mains power.
- **Kiri** was measured on 3 November, 04:57–05:00 UTC, with the network
  suite run again at 05:01–05:03 UTC (see section 5). Host load average was
  about 4–5.
- **Docker Desktop, OrbStack and Colima** are the full `matrix` run of
  2 November, 18:20–18:34 UTC, host load about 7–9, with the same options
  and harness. Their method is in the
  [2026-11-02 How we tested](../2026-11-02/HOW-WE-TESTED.md).
- Other desktop apps stayed open in both sessions.

## 2. Same compute for every engine: 2 CPUs, 8 GB

Every engine's VM was set to **2 CPUs and 8 GB** and checked with
`docker --context <engine> info` before its run:

| Engine | How it was set | `docker info` before the run |
|---|---|---|
| Kiri | `vm.json`: `{"cpus": 2, "memory_mib": 8192}` | 2 CPUs, 7.8 GiB |
| Docker Desktop | Settings → Resources: CPU limit 2, Memory 8 GB, Apply & restart | 2 CPUs, 7.7 GiB |
| OrbStack | `orb config set cpu 2`, `orb config set memory_mib 8192`, `orb stop`, `orb start` | 2 CPUs, 7.8 GiB |
| Colima | `colima start --cpu 2 --memory 8 --vm-type vz --mount-type virtiofs --runtime docker` | 2 CPUs, 7.7 GiB |

## 3. The Kiri build

Kiri was a development build with the layer fix described in the
[comparison](comparison.md#what-changed-in-kiri); the fix ships in the next
release. It ran as a separate engine with its own Docker context, VM and
image store, starting empty, so nothing else was running in it and no layer
from before the fix was reused. Its Docker context is called `kiri-layers`
below; with a released Kiri use `kiri`.

## 4. The run

```sh
git clone https://github.com/libracoder/kiri-bench.git
cd kiri-bench
./kiri-bench doctor --engine kiri
./kiri-bench run --engine kiri --command "docker --context kiri-layers" \
  --label macos-2cpu-8gb-2026-11-03
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

The engine is reached only through its own Docker context. The direct API
tests use that context's Unix socket, and builds use the buildx builder named
after the context.

## 5. The second network run

In the full run, the 4-stream iperf3 test failed all five samples (see
[Known Kiri issue](comparison.md#known-kiri-issue)). The network suite was
run again on its own, with the same options:

```sh
./kiri-bench run --engine kiri --command "docker --context kiri-layers" \
  --suite network --io-runs 5 --parallel 4 --net-seconds 5 --http-requests 200
```

Every network test passed. The published iperf3 (single and 4 streams) and
new HTTP connection numbers for Kiri come from this run; everything else
comes from the full run.

## 6. Reading the results

- Times are medians of the samples; p95s are in the comparison. Rates
  (MB/s, containers/s, Gbit/s, req/s) are per-sample medians.
- Winner ratios compare the best engine with the runner-up.
- A failed test counts as a loss.
- Kiri's 23 GB/s volume read is a page-cache figure, not disk speed.

## 7. Check it yourself

The raw per-sample output is not published; run the suite above to produce
your own `summary.json`, `report.md` and `raw/` samples for every engine,
then compare runs with:

```sh
./kiri-bench compare results/run-a/summary.json results/run-b/summary.json
```

The general guide is [Reproduce the runtime comparison](../../REPRODUCE.md).
