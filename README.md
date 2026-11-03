<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/logo/kiri-horizontal-dark.svg">
    <img src="brand/logo/kiri-horizontal-light.svg" alt="Kiri" width="240">
  </picture>
</p>

# Kiri runtime test suite

A portable correctness and performance suite for Kiri and other Docker-compatible
runtimes. It measures lifecycle, direct API, storage, network, and container
density, and writes raw JSON plus a Markdown report for every run.

No Python packages, Kubernetes, root setup, or global cleanup are required.

## Clone and run

Requirements: Python 3.10+, a running Docker-compatible engine and its CLI.
For Kiri, run `kiri setup` once to create the `kiri` Docker context used by the
suite. `iperf3` is optional; install it for throughput tests. Kiri's build
measurement requires the `buildx` plugin and is skipped when it is unavailable.

```sh
git clone https://github.com/libracoder/kiri-bench.git
cd kiri-bench

./kiri-bench doctor --engine kiri
./kiri-bench run --engine kiri --quick
./kiri-bench run --engine kiri --label laptop-a
```

On Windows, use `kiri-bench.cmd` instead of `./kiri-bench`. Direct module
invocation also works: `python3 kiri_bench.py run --engine kiri --quick`.

The quick run caps each category at a few samples, 16 MiB transfers, 32 MiB
storage writes, two-second network streams, and three containers. A full run
uses three warmups per measurement, 30 latency samples, five I/O samples,
200 MiB transfers, 1 GiB storage writes, five-second streams, and 20
containers. Quick runs use one warmup.

## Other engines

```sh
./kiri-bench run --engine docker --quick
./kiri-bench run --engine docker-desktop --quick
./kiri-bench run --engine orbstack --quick
./kiri-bench run --engine podman --quick
./kiri-bench run --engine nerdctl --quick
./kiri-bench run --engine colima --quick
./kiri-bench run --engine docker --command "docker --context my-context" --quick
```

Run one engine at a time. Do not compare results from different machines or
from runs with different options without saying so in the report label.

To benchmark every available engine sequentially and produce a combined report:

```sh
./kiri-bench matrix --quick
./kiri-bench matrix --quick --engines docker-desktop,kiri
```

Matrix runs use identical options, skip missing or stopped engines, and write
per-engine raw results plus `summary.json` and `report.md` in a new matrix
results directory.

## Suites

| Suite | What it checks and measures |
|---|---|
| `lifecycle` | `run`, `exec`, stdin/stdout, uncached three-layer build, warm pull, and parallel starts |
| `api` | Direct create/start/wait/delete and exec over a Unix Docker API socket, without the CLI |
| `storage` | Bind-mount and named-volume writes with `fsync`, then reads |
| `network` | Published-port iperf3 throughput (single and parallel streams) and sequential new HTTP connections |
| `resources` | Container-density timing and a `docker stats` sample |

Use `--suite lifecycle,storage` to select categories. `--warmup`, `--runs`, `--io-runs`,
`--parallel`, `--transfer-mb`, `--storage-mb`, `--net-seconds`,
`--http-requests`, and `--density` change the workload. `--socket` selects the
API socket. The API suite currently supports Unix sockets, not Windows named
pipes.

Every run creates a new directory such as `results/20261031T120000Z-kiri/`:

- `summary.json`: options, normalized engine/host metadata, measurements, skips;
- `report.md`: the human-readable summary;
- `raw/*.json`: every sample, including failures and density stats;
- `manifest.json`: resources owned by the run, emptied after normal cleanup.

Failed tests are marked `fail` or `partial`; unavailable capabilities are
`skipped`. The command exits nonzero if any measurement fails. Warm-image
semantics are deliberate: the suite never removes an existing image to force a
cold pull. Do not treat a warm pull as registry download performance.

## Reports and comparison

```sh
./kiri-bench report results/20261031T120000Z-kiri
./kiri-bench compare results/run-a/summary.json results/run-b/summary.json
./kiri-bench compare results/run-a/summary.json results/run-b/summary.json --out comparison.md
```

The A/B column is the first engine's median time divided by the second's.
Above 1 means the first is slower; below 1 means it is faster. Compare medians
and p95s, not just means, and repeat runs when the machine is under similar
load.

## Safety and cleanup

The suite uses unique resource names and removes only resources in its own run
manifest. It never prunes, removes user images, kills daemon processes, or
changes host networking. A failed run still attempts cleanup.

```sh
./kiri-bench clean results/20261031T120000Z-kiri/manifest.json
```

`--keep` deliberately leaves test containers, volumes, networks, and the build
image for debugging; use the same manifest to remove them later. Host paths,
usernames, IP addresses, and environment variables are not collected in the
report metadata.

See [the framework and result schema](docs/RESULTS.md) and
[the research basis](docs/RESEARCH.md).

## Published results

### macOS — latest, 2026-11-03

Kiri, Docker Desktop, OrbStack and Colima on one Apple Silicon Mac, **every
engine limited to 2 CPUs and 8 GB**, full run. Medians; lower is better for
times, higher for rates. Kiri was measured on 3 November with the fix for the
bug that broke its build and iperf3 tests; the other engines are the
2 November run.

| Test | Kiri | Docker Desktop | OrbStack | Colima | Winner |
|---|---:|---:|---:|---:|---|
| `docker run --rm` | **18.3 ms** | 178 ms | 279 ms | 152 ms | **Kiri**, 8.3x |
| `docker exec` | **13.1 ms** | 47.7 ms | 32.5 ms | 36.8 ms | **Kiri**, 2.5x |
| API container lifecycle | **2.5 ms** | 163 ms | 238 ms | 88 ms | **Kiri**, ~35x |
| API exec | **0.4 ms** | 17.1 ms | 18.3 ms | 20.8 ms | **Kiri**, ~43x |
| Build (3 layers, no cache) | **242 ms** | 527 ms | 1048 ms | 505 ms | **Kiri**, 2.1x |
| Warm pull | **350 ms** | 2798 ms | 1569 ms | 2893 ms | **Kiri**, 4.5x |
| Parallel starts | **176 /s** | 11.4 /s | 8.2 /s | 12.9 /s | **Kiri**, 13.7x |
| Density | **20.7 /s** | 3.2 /s | 2.9 /s | 4.1 /s | **Kiri**, 5.0x |
| stdout / stdin | **297 / 189** MB/s | 45 / 90 | 87 / 158 | 63 / 123 | **Kiri** |
| Bind mount write / read | **2042** / 2497 MB/s | 1425 / 1354 | 1596 / 3240 | 1272 / **5235** | Kiri / Colima |
| Volume write / read | **1974 / 23225**¹ MB/s | 1920 / 4097 | 1216 / 2692 | 1779 / 5391 | **Kiri** |
| iperf3 single / 4 streams | **26.2** / 13.7 Gbit/s² | 1.1 / 1.6 | 24.0 / **17.7** | 2.4 / 2.5 | Kiri / OrbStack |
| New HTTP connections | **2741 req/s**² | 865 | 2389 | 1484 | **Kiri**, 1.15x |

**Verdict:** at equal compute Kiri wins 15 of 17 tests, including every
container-lifecycle test by 2x to 43x. OrbStack leads 4-stream published-port
throughput, Colima leads bind-mount reads, Docker Desktop wins none.
¹ Page-cache figure, not disk speed. ² From a second network-suite run; the
4-stream test failed in the full run (see the comparison).

- [Full comparison with p95s](docs/benchmarks/2026-11-03/comparison.md)
- [**How we tested**](docs/benchmarks/2026-11-03/HOW-WE-TESTED.md): machine, the 2 CPU / 8 GB settings for each engine, commands
- [PDF report](docs/benchmarks/2026-11-03/kiri-bench-macos-2026-11-03.pdf)

### macOS — 2026-11-02

The first equal-compute run, where Kiri won 11 of 16 tests and failed build
and iperf3 because of the bug fixed above:
[comparison](docs/benchmarks/2026-11-02/comparison.md),
[how we tested](docs/benchmarks/2026-11-02/HOW-WE-TESTED.md),
[PDF](docs/benchmarks/2026-11-02/kiri-bench-macos-2026-11-02.pdf).

### Windows — 2026-11-01

Times are median seconds; rates are per-sample medians.

| Test | Docker Desktop | Kiri | Leader |
|---|---:|---:|---|
| `run` | 0.575s | **0.105s** | **Kiri** |
| `exec` | 0.108s | **0.089s** | **Kiri** |
| Build | 1.675s | 31.592s | Docker Desktop |
| Warm pull | 1.651s | **0.396s** | **Kiri** |
| Volume read | 46.34 MB/s | **290.35 MB/s** | **Kiri** |
| HTTP connections | **201.3 req/s** | 146.3 req/s | Docker Desktop |
| Density | 0.80 containers/s | **3.01 containers/s** | **Kiri** |

### WSL — 2026-11-01

| Test | Docker Engine | Kiri | Leader |
|---|---:|---:|---|
| `run` | 0.845s | **0.176s** | **Kiri** |
| `exec` | 0.181s | **0.158s** | **Kiri** |
| Build | 1.914s | **1.373s** | **Kiri** |
| Warm pull | 2.007s | 2.543s | Docker Engine |
| Volume read | 49.62 MB/s | **188.59 MB/s** | **Kiri** |
| HTTP connections | 2523.3 req/s | **2733.4 req/s** | **Kiri** |
| Parallel iperf3 | 180.14 Gbit/s | **193.81 Gbit/s** | **Kiri** |
| Density | 0.71 containers/s | **2.03 containers/s** | **Kiri** |

**Verdict:** native Windows Kiri is the fastest overall on this machine,
winning most lifecycle, storage, pull, and parallel-start tests. Docker
Desktop leads build and new HTTP connections; WSL Kiri leads direct API and
network measurements. The pause/resume work reduced Kiri's build from 31.59s
to 1.37s, so the original 30-second mirror delay is no longer the bottleneck.
These are local measurements, not universal claims; rerun the suite on your
own hardware before making a decision.

See the [Windows and WSL comparison](docs/benchmarks/2026-11-01/comparison.md) for p95s and skipped capabilities, plus the [build-delay investigation](docs/benchmarks/2026-11-01/build-rerun.md). Follow the [reproduction guide](docs/REPRODUCE.md) to rerun the suite and compare your own results.

## License

Apache License 2.0. See [LICENSE](LICENSE).
