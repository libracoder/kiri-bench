# macOS runtime comparison — 2026-11-02

Kiri, Docker Desktop, OrbStack and Colima on one Apple Silicon Mac (M3 Max,
16 cores, 64 GB), **each engine limited to 2 CPUs and 8 GB**, run back to
back with identical options. Full run: 30 latency samples, 5 I/O samples,
3 warmups, 1 GiB storage writes, 200 MiB stdio transfers, 5-second network
streams, 20 containers for density.

How the numbers were produced, including every setting changed on the
machine: [How we tested](HOW-WE-TESTED.md). PDF:
[kiri-bench-macos-2026-11-02.pdf](kiri-bench-macos-2026-11-02.pdf).

## Results

Medians. Lower is better for times, higher for rates. The winner column
compares the best engine with the runner-up.

| Test | Kiri | Docker Desktop | OrbStack | Colima | Winner |
|---|---:|---:|---:|---:|---|
| `docker run --rm` | **22 ms** | 178 ms | 279 ms | 152 ms | **Kiri**, 6.9x |
| `docker exec` | **15.7 ms** | 47.7 ms | 32.5 ms | 36.8 ms | **Kiri**, 2.1x |
| API container lifecycle | **3.1 ms** | 163 ms | 238 ms | 88 ms | **Kiri**, ~29x |
| API exec | **0.3 ms** | 17.1 ms | 18.3 ms | 20.8 ms | **Kiri**, ~50x |
| Build (3 layers, no cache) | fails¹ | 527 ms | 1048 ms | **505 ms** | Colima, tie with Docker Desktop |
| Warm pull | **321 ms** | 2798 ms | 1569 ms | 2893 ms | **Kiri**, 4.9x |
| Parallel starts | **88.9 /s** | 11.4 /s | 8.2 /s | 12.9 /s | **Kiri**, 6.9x |
| Density | **19.7 /s** | 3.2 /s | 2.9 /s | 4.1 /s | **Kiri**, 4.8x |
| stdout | **223 MB/s** | 45 MB/s | 87 MB/s | 63 MB/s | **Kiri**, 2.5x |
| stdin | 150 MB/s | 90 MB/s | **158 MB/s** | 123 MB/s | OrbStack, 1.05x (tie with Kiri) |
| Bind mount write | **1745 MB/s** | 1425 MB/s | 1596 MB/s | 1272 MB/s | **Kiri**, 1.1x |
| Bind mount read | 1724 MB/s | 1354 MB/s | 3240 MB/s | **5235 MB/s** | Colima, 1.6x |
| Volume write | **1991 MB/s** | 1920 MB/s | 1216 MB/s | 1779 MB/s | **Kiri**, 1.04x (tie with Docker Desktop) |
| Volume read | **21308 MB/s**² | 4097 MB/s | 2692 MB/s | 5391 MB/s | **Kiri**, 4.0x |
| iperf3 single / parallel | fails¹ | 1.1 / 1.6 Gbit/s | **24.0 / 17.7 Gbit/s** | 2.4 / 2.5 Gbit/s | OrbStack, 7–10x |
| New HTTP connections | 1892 req/s | 865 req/s | **2389 req/s** | 1484 req/s | OrbStack, 1.3x |

**Kiri wins 11 of 16 tests**, OrbStack 3, Colima 2, Docker Desktop none.

¹ Known Kiri bug, see [below](#known-kiri-issues). Counted as a loss.
² Almost certainly served from the page cache; treat it as an upper bound,
not disk speed.

### Tail latency (p95)

| Test | Kiri | Docker Desktop | OrbStack | Colima |
|---|---:|---:|---:|---:|
| `docker run --rm` | 45 ms | 278 ms | 443 ms | 165 ms |
| `docker exec` | 17.2 ms | 64.2 ms | 37.7 ms | 40.9 ms |
| API lifecycle | 5.9 ms | 266 ms | 284 ms | 103 ms |
| API exec | 0.5 ms | 20.6 ms | 26.7 ms | 26.2 ms |
| Warm pull | 329 ms | 2891 ms | 1611 ms | 2926 ms |
| Build | fails | 653 ms | 1080 ms | 519 ms |

## Verdict

At equal compute, Kiri is the fastest container runtime on this Mac for
everything on the container lifecycle path: starting, exec'ing, the direct
API, pulling, starting in parallel and packing containers. The margins there
are 2x to 50x, not single-digit percentages. It also leads stdout, writes
and volume reads.

OrbStack has much faster published-port throughput (iperf3) and slightly
more new HTTP connections per second; Colima reads bind mounts fastest.
Docker Desktop wins no test. Kiri cannot yet run a `RUN` build step or the
iperf3 image on macOS because of the bug below, so it gives up those two
rows entirely.

These are measurements on one machine, not universal claims. Rerun the suite
on your own hardware before deciding; [How we tested](HOW-WE-TESTED.md) has
the exact steps.

## Known Kiri issues

Both failures come from the same Kiri bug, reproduced by hand outside the
suite:

- **Pulled images can contain empty files.** In `networkstatic/iperf3`,
  `/usr/bin/iperf3` is 0 bytes on Kiri and 91,800 bytes on OrbStack; a fresh
  re-pull gives the same result. The file comes from a `COPY` layer and is
  not a hard link. Starting the image fails with `Exec format error`, so the
  iperf3 tests fail.
- **Builds fail.** Every `RUN` step on Kiri's BuildKit builder fails with
  `exec /bin/sh: exec format error`, also with `--platform linux/arm64`.
  The 2026-11-01 macOS run had the same failure.

## Engines

| Engine | Version | Guest kernel |
|---|---|---|
| Kiri | 0.1.13-dev.31 | Kiri guest |
| Docker Desktop | 4.90.0, Engine 29.7.2 | 7.0.12-linuxkit |
| OrbStack | 2.2.4, Engine 29.8.2 | 7.2.9-orbstack |
| Colima | 0.10.3 (`vz`, `virtiofs`), Engine 29.5.2 | 6.8.0-117-generic |

Docker CLI 29.7.2 for all, kiri-bench suite 1.1.0, Python 3.15, iperf3 from
Homebrew, macOS 27.0.1.
