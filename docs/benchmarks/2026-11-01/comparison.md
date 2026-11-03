# Runtime comparison — 2026-11-01

Quick suite: three latency samples and two I/O samples per engine, one warmup. Times are median seconds; rates are per-sample medians. Engines were run sequentially.

| Test | windows-docker-desktop | windows-kiri | wsl-kiri | wsl-docker-engine |
|---|---:|---:|---:|---:|
| cli.run | 0.575026s | 0.104801s | 0.175584s | 0.845186s |
| cli.exec | 0.108361s | 0.088579s | 0.158073s | 0.180500s |
| cli.stdout | 0.769677s<br>21.05 MB/s | 0.186475s<br>86.04 MB/s | 0.230911s<br>69.36 MB/s | 0.828006s<br>19.35 MB/s |
| cli.stdin | 1.016190s<br>15.75 MB/s | 0.133690s<br>119.78 MB/s | 0.214004s<br>74.77 MB/s | 0.702031s<br>22.86 MB/s |
| cli.build | 1.674967s | 31.592246s | 1.372753s | 1.914315s |
| cli.pull.warm | 1.650524s | 0.395951s | 2.543438s | 2.007150s |
| cli.parallel | 1.287319s<br>3.11 containers/s | 0.143331s<br>27.95 containers/s | 0.196496s<br>20.49 containers/s | 1.318060s<br>3.06 containers/s |
| storage.bind.write | 0.889113s<br>36.01 MB/s | 0.321894s<br>99.55 MB/s | 0.207773s<br>154.07 MB/s | 0.677677s<br>47.28 MB/s |
| storage.bind.read | 0.703993s<br>45.46 MB/s | 0.239091s<br>134.27 MB/s | 0.172042s<br>186.00 MB/s | 0.625260s<br>51.21 MB/s |
| storage.volume.write | 0.651386s<br>49.30 MB/s | 0.124486s<br>257.50 MB/s | 0.213328s<br>150.01 MB/s | 0.743290s<br>43.45 MB/s |
| storage.volume.read | 0.698654s<br>46.34 MB/s | 0.118800s<br>290.35 MB/s | 0.169683s<br>188.59 MB/s | 0.650593s<br>49.62 MB/s |
| network.http.connections | 0.049681s<br>201.32 requests/s | 0.071930s<br>146.27 requests/s | 0.003672s<br>2733.42 requests/s | 0.003980s<br>2523.29 requests/s |
| resources.density | 3.742595s<br>0.80 containers/s | 0.997073s<br>3.01 containers/s | 1.479151s<br>2.03 containers/s | 4.224785s<br>0.71 containers/s |
| api.lifecycle | — | — | 0.014187s | — |
| api.exec | — | — | 0.001078s | — |
| network.iperf.single | — | — | 2.005678s<br>57.30 Gbit/s | 2.005610s<br>55.45 Gbit/s |
| network.iperf.parallel | — | — | 2.006886s<br>193.81 Gbit/s | 2.006974s<br>180.14 Gbit/s |

## Skipped capabilities

- **windows-docker-desktop** — api: direct API currently supports Unix sockets only
- **windows-docker-desktop** — network.iperf: iperf3 is not installed on the host
- **windows-kiri** — api: direct API currently supports Unix sockets only
- **windows-kiri** — network.iperf: iperf3 is not installed on the host
- **wsl-docker-engine** — api: unavailable in this WSL setup because Docker start requires the missing Docker Desktop host-services backend socket

Raw per-engine summaries, reports, and samples are included in their directories.
