# macOS runtime comparison — 2026-11-03

Kiri, Docker Desktop, OrbStack and Colima on one Apple Silicon Mac (M3 Max,
16 cores, 64 GB), **each engine limited to 2 CPUs and 8 GB**, with identical
options. Full run: 30 latency samples, 5 I/O samples, 3 warmups, 1 GiB
storage writes, 200 MiB stdio transfers, 5-second network streams, 20
containers for density.

Kiri was measured on 3 November with the fix described
[below](#what-changed-in-kiri). Docker Desktop, OrbStack and Colima are the
[2 November run](../2026-11-02/comparison.md), on the same machine with the
same settings and harness. [How we tested](HOW-WE-TESTED.md) has every step.
PDF: [kiri-bench-macos-2026-11-03.pdf](kiri-bench-macos-2026-11-03.pdf).

## Results

Medians. Lower is better for times, higher for rates. The winner column
compares the best engine with the runner-up.

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
| stdout | **297 MB/s** | 45 MB/s | 87 MB/s | 63 MB/s | **Kiri**, 3.4x |
| stdin | **189 MB/s** | 90 MB/s | 158 MB/s | 123 MB/s | **Kiri**, 1.2x |
| Bind mount write | **2042 MB/s** | 1425 MB/s | 1596 MB/s | 1272 MB/s | **Kiri**, 1.3x |
| Bind mount read | 2497 MB/s | 1354 MB/s | 3240 MB/s | **5235 MB/s** | Colima, 1.6x |
| Volume write | **1974 MB/s** | 1920 MB/s | 1216 MB/s | 1779 MB/s | **Kiri**, 1.03x (tie with Docker Desktop) |
| Volume read | **23225 MB/s**¹ | 4097 MB/s | 2692 MB/s | 5391 MB/s | **Kiri**, 4.3x |
| iperf3, single stream | **26.2 Gbit/s**² | 1.1 Gbit/s | 24.0 Gbit/s | 2.4 Gbit/s | **Kiri**, 1.09x |
| iperf3, 4 streams | 13.7 Gbit/s² | 1.6 Gbit/s | **17.7 Gbit/s** | 2.5 Gbit/s | OrbStack, 1.3x |
| New HTTP connections | **2741 req/s**² | 865 req/s | 2389 req/s | 1484 req/s | **Kiri**, 1.15x |

**Kiri wins 15 of 17 tests**, OrbStack 1, Colima 1, Docker Desktop none.

¹ Almost certainly served from the page cache; treat it as an upper bound,
not disk speed.
² From a second run of the network suite; see
[Known Kiri issue](#known-kiri-issue).

### Tail latency (p95)

| Test | Kiri | Docker Desktop | OrbStack | Colima |
|---|---:|---:|---:|---:|
| `docker run --rm` | 22.5 ms | 278 ms | 443 ms | 165 ms |
| `docker exec` | 15.7 ms | 64.2 ms | 37.7 ms | 40.9 ms |
| API lifecycle | 3.2 ms | 266 ms | 284 ms | 103 ms |
| API exec | 0.6 ms | 20.6 ms | 26.7 ms | 26.2 ms |
| Warm pull | 366 ms | 2891 ms | 1611 ms | 2926 ms |
| Build | 257 ms | 653 ms | 1080 ms | 519 ms |

## Verdict

At equal compute, Kiri is the fastest container runtime on this Mac in 15 of
17 tests: starting, exec'ing, the direct API, building, pulling, starting in
parallel, packing containers, stdio, writes, volume reads, single-stream
published-port throughput and new HTTP connections. On the container
lifecycle path the margins are 2x to 43x.

OrbStack still has more published-port throughput with four parallel
streams, and Colima reads bind mounts fastest. Docker Desktop wins no test.

These are measurements on one machine, not universal claims. Rerun the suite
on your own hardware before deciding; [How we tested](HOW-WE-TESTED.md) has
the exact steps.

## What changed in Kiri

On 2 November Kiri failed the build and iperf3 tests: files in some image
layers were empty, so `/bin/sh` and `/usr/bin/iperf3` could not run. The
cause was in Kiri, not the images. When Kiri put its VM to sleep, it stopped
the VM before the guest had written its disk cache, so layers unpacked
shortly before kept their file names but lost their contents, and the broken
copy was then reused on every pull.

The fixed build waits for the guest to power off, writes each layer to disk
before using it, unpacks again any layer that was cut short, and deletes
layers no image uses. With it, both tests pass. Most other Kiri numbers
improved; warm pull (321 → 350 ms) and API exec (0.3 → 0.4 ms) were a little
slower than on 2 November.

## Known Kiri issue

In the full run, all five 4-stream iperf3 samples failed at once with
"control socket has closed unexpectedly". At that point Kiri had logged that
it could not reach the VM's network directly and was relaying published
ports over its fallback path. Minutes later a second run of the network
suite (`--suite network`, same options) passed every test, and its iperf3
and HTTP numbers are the ones above. The fallback path is being looked into.

## Engines

| Engine | Version | Guest kernel |
|---|---|---|
| Kiri | development build with the layer fix (next release) | Kiri guest |
| Docker Desktop | 4.90.0, Engine 29.7.2 | 7.0.12-linuxkit |
| OrbStack | 2.2.4, Engine 29.8.2 | 7.2.9-orbstack |
| Colima | 0.10.3 (`vz`, `virtiofs`), Engine 29.5.2 | 6.8.0-117-generic |

Docker CLI 29.7.2 for all, kiri-bench suite 1.1.0, Python 3.15, iperf3 from
Homebrew, macOS 27.0.1.
