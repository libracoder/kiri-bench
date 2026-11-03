# Build rerun

Both builds used the same three-layer Dockerfile with `--no-cache`, sequentially on the same Windows host.

| Engine | First median | Rerun median |
|---|---:|---:|
| Docker Desktop | 1.675s | 1.673s |
| Native Windows Kiri | 31.592s | 31.445s |

The rerun confirmed that Kiri's 30-second delay was reproducible rather than BuildKit startup noise. Plain progress logs showed registry metadata requests to Kiri's local mirror timing out. The mirror itself answered in 4 ms over loopback; requests through the VM-only host-gateway address hung on Linux hosts.

The fix in Kiri PR #122 uses the active default bridge gateway on Linux hosts. With it, metadata completes in 1.2–1.4s and a warm uncached build completes in 2.38s.

## Pause/resume

Kiri PR #125 pauses idle BuildKit workers instead of stopping them, preserving their memory and cache while keeping idle CPU at zero. On the next build, the worker resumes automatically.

The resumed three-layer uncached build completed in **1.46s**, compared with 2.38s before pause/resume and 1.67s on Docker Desktop. Metadata completed in 0.3s.
