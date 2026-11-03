# Research basis

The suite keeps the original Kiri measurements but borrows these established
practices:

- [Kata Containers metrics](https://github.com/kata-containers/kata-containers/tree/3.17.0/tests/metrics):
  separate time, density, networking, and storage categories, use CI and manual
  runs, and keep uniform JSON results. Kata also distinguishes throughput from
  runtime latency.
- [CRI tools performance benchmarking](https://github.com/kubernetes-sigs/cri-tools/blob/master/docs/benchmark.md):
  control lifecycle counts and parallelism, write result JSON, and avoid other
  users of the runtime during a run. This suite uses the Docker API directly,
  so Kubernetes and CRI are not required.
- [Hyperfine](https://github.com/sharkdp/hyperfine): use warmups and explicit
  run counts, account for cache state, and retain raw samples. The original
  suite used Hyperfine; this implementation uses `time.perf_counter` to avoid
  making it a host dependency.
- [Podman tests](https://github.com/podman-container-tools/podman/tree/main/test):
  separate integration and system tests and make destructive-test boundaries
  explicit. This suite narrows that boundary to resources in its own manifest.

No code or infrastructure is copied from these projects.
