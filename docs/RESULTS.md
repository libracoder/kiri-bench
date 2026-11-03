# Framework and result schema

## Execution

Each measurement runs a command one or more times and records wall time with
`time.perf_counter`. Successful samples contribute to median, mean, minimum,
maximum, p95, and sample standard deviation. Every sample remains in the raw
JSON, including timeouts, nonzero exits, and error text.

Rates are per-sample values: MiB per second for transfer and storage tests,
Gbit/s for iperf3, requests per second for HTTP, and containers per second for
parallel/density tests. A rate is never calculated from the median time; its
median is the median of the individual rates.

Setup time (image pulls, creating the persistent exec container, and creating
the build context) is not included in measurements. Build commands use
`--no-cache`; pulls are warm because no existing image is removed. Network
clients connect to `127.0.0.1` through the published port, not to the
container's internal address. API lifecycle containers use `NetworkMode: none`
because they measure process operations, not port allocation or forwarding.

For useful comparisons:

1. Use the same suite version and options.
2. Run only the engine under test, on an otherwise idle machine.
3. Keep power, virtualization, architecture, and emulation settings the same.
4. Use the same images and report whether they were already present.
5. Repeat and compare medians and p95s before claiming a regression.

## Files

`summary.json` has `schema_version: 1`, `suite_version`, `run_id`, engine
command, start/finish timestamps, normalized environment and options,
measurements, and skips. No hostname, username, IP address, home directory, or
environment variables are recorded.

Each measurement contains:

- `name`, `status` (`pass`, `partial`, or `fail`), `runs`, and `failures`;
- `seconds`: aggregate statistics for successful samples;
- optional `value` and `value_unit`: aggregate rate statistics;
- `samples`: `run`, `seconds`, `success`, and either `value` or `error`.

`manifest.json` contains only resources created by the suite: containers,
volumes, networks, and the generated build image. Normal cleanup empties it.
`clean` uses that list rather than broad label or prefix matching.
