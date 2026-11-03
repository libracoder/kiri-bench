# Reproduce the runtime comparison

This repository is self-contained. No custom test scripts, private services,
Kubernetes installation, or Python packages are needed.

## Requirements

- Python 3.10 or later.
- A running Docker-compatible engine and its CLI.
- For Kiri, run `kiri setup` once to create its Docker context.
- Optional: `iperf3` for throughput measurements and `buildx` for build tests.
  Missing capabilities are reported as skipped, not silently treated as passes.

## Run

```sh
git clone https://github.com/libracoder/kiri-bench.git
cd kiri-bench
./kiri-bench doctor --engine kiri
./kiri-bench matrix --quick
```

On Windows, use `kiri-bench.cmd`. To test only Kiri:

```sh
./kiri-bench run --engine kiri --quick --label laptop-a
```

To select engines:

```sh
./kiri-bench matrix --quick --engines docker-desktop,kiri
```

Engines run sequentially with identical options. Missing or stopped engines are
skipped with a reason. The suite removes only resources in its own manifest; it
does not prune, remove user images, kill daemon processes, or change host
networking.

## Results

Each run creates a new directory containing:

- `summary.json`: machine-readable options, versions, environment, and results;
- `report.md`: the human-readable summary;
- `raw/`: every timing sample, failure, and density sample;
- `manifest.json`: resources owned by the run, empty after normal cleanup.

Create a comparison between two runs with:

```sh
./kiri-bench compare results/run-a/summary.json results/run-b/summary.json --out comparison.md
```

## Interpretation

Use the same suite version, images, and options on an otherwise idle machine.
Compare medians and p95s, not just means. Results from different hardware,
power settings, virtualization, or emulation are separate measurements and
must not be presented as universally equivalent.

The latest published comparison is dated **2026-11-02** (macOS, every engine
at 2 CPUs and 8 GB): [comparison](benchmarks/2026-11-02/comparison.md) and
[how we tested](benchmarks/2026-11-02/HOW-WE-TESTED.md). The Windows and WSL
comparison from **2026-11-01** is in [benchmarks/2026-11-01](benchmarks/2026-11-01/comparison.md).
Published results include the write-ups, not the raw per-sample output; run
the suite to produce your own.
