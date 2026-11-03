#!/usr/bin/env python3
"""Portable Docker-compatible runtime correctness and performance suite."""

import argparse
import concurrent.futures
import datetime
import http.client
import json
import math
import os
import platform
import shlex
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

VERSION = "1.1.0"
SCHEMA_VERSION = 1
ENGINES = {
    "kiri": ["docker", "--context", "kiri"],
    "docker": ["docker"],
    "docker-desktop": ["docker", "--context", "desktop-linux"],
    "orbstack": ["docker", "--context", "orbstack"],
    "podman": ["podman"],
    "nerdctl": ["nerdctl"],
    "colima": ["docker", "--context", "colima"],
}
SUITES = ["lifecycle", "api", "storage", "network", "resources"]
IMAGE = "alpine"
IPERF_IMAGE = "networkstatic/iperf3"
HTTP_IMAGE = "nginx:alpine"


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def stats(values):
    values = sorted(values)
    if not values:
        return {}
    result = {
        "count": len(values),
        "median": statistics.median(values),
        "mean": statistics.mean(values),
        "min": values[0],
        "max": values[-1],
    }
    if len(values) > 1:
        result["p95"] = values[math.ceil(len(values) * 0.95) - 1]
        result["stdev"] = statistics.stdev(values)
    return result


def safe_name(value):
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in value)


def command_text(args):
    return " ".join(shlex.quote(str(a)) for a in args)


def redact_home(value):
    if not isinstance(value, str):
        return value
    home = str(Path.home())
    return value.replace(home, "~") if home else value


class RunContext:
    def __init__(self, args):
        self.args = args
        self.engine_name = args.engine
        self.command = shlex.split(args.command) if args.command else list(ENGINES[args.engine])
        self.display_command = [redact_home(part) for part in self.command]
        self.out = Path(args.out).resolve() if args.out else None
        self.run_id = uuid.uuid4().hex[:12]
        self.resources = []
        self.measurements = []
        self.skipped = []
        self.started = utc_now()
        self.environment = {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "host_label": args.label or "unlabeled",
        }
        if self.out:
            (self.out / "raw").mkdir(parents=True, exist_ok=False)
            self.write_json("manifest.json", {
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "engine": self.engine_name,
                "command": self.display_command,
                "resources": self.resources,
            })

    def write_json(self, relative, value):
        if not self.out:
            return
        path = self.out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def save_manifest(self):
        self.write_json("manifest.json", {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "engine": self.engine_name,
            "command": self.display_command,
            "resources": self.resources,
        })

    def add_resource(self, kind, name):
        item = {"kind": kind, "name": name}
        if item not in self.resources:
            self.resources.append(item)
            self.save_manifest()
        return name

    def resource_name(self, purpose):
        return self.add_resource("container", f"kiri-bench-{self.run_id}-{safe_name(purpose)}")

    def cleanup(self):
        for item in reversed(self.resources):
            kind, name = item["kind"], item["name"]
            try:
                if kind == "container":
                    self.call(["rm", "-f", name], check=False, timeout=20)
                elif kind == "volume":
                    self.call(["volume", "rm", name], check=False, timeout=20)
                elif kind == "network":
                    self.call(["network", "rm", name], check=False, timeout=20)
                elif kind == "image":
                    self.call(["rmi", "-f", name], check=False, timeout=30)
            except Exception:
                pass
        self.resources.clear()
        self.save_manifest()

    def call(self, args, check=True, timeout=120, input_data=None, discard_output=False):
        command = self.command + [str(a) for a in args]
        started = time.perf_counter()
        try:
            result = subprocess.run(
                command,
                input=input_data,
                stdout=subprocess.DEVNULL if discard_output else subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"timed out after {timeout}s: {command_text(command)}") from exc
        if check and result.returncode != 0:
            error = result.stderr.decode("utf-8", "replace").strip()
            raise RuntimeError(f"{command_text(command)} exited {result.returncode}: {error[:1000]}")
        result.elapsed = time.perf_counter() - started
        return result

    def pull(self, image):
        self.call(["pull", "-q", image], timeout=300)

    def measure(self, name, function, runs, value_unit=None, detail=None):
        for _ in range(getattr(self.args, "warmup", 0)):
            try:
                function(-1)
            except Exception:
                pass  # the measured runs below record the failure
        samples = []
        for index in range(runs):
            started = time.perf_counter()
            try:
                value = function(index)
                if not isinstance(value, (int, float)):
                    value = None
                seconds = time.perf_counter() - started
                samples.append({"run": index + 1, "seconds": seconds, "success": True, "value": value})
            except Exception as exc:
                seconds = time.perf_counter() - started
                samples.append({"run": index + 1, "seconds": seconds, "success": False, "error": redact_home(str(exc))[:1000]})
        good = [s for s in samples if s["success"]]
        failures = len(samples) - len(good)
        status = "pass" if failures == 0 else "partial" if good else "fail"
        measurement = {
            "name": name,
            "status": status,
            "runs": len(samples),
            "failures": failures,
            "seconds": stats([s["seconds"] for s in good]),
            "samples": samples,
        }
        if value_unit:
            measurement["value_unit"] = value_unit
            measurement["value"] = stats([s["value"] for s in good if s["value"] is not None])
        if detail:
            measurement["detail"] = detail
        self.measurements.append(measurement)
        self.write_json(f"raw/{safe_name(name)}.json", measurement)
        print(f"  {name}: {status}")
        return measurement

    def skip(self, name, reason):
        print(f"  {name}: skipped ({reason})")
        self.skipped.append({"name": name, "reason": redact_home(reason)})

    def summary(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "suite_version": VERSION,
            "run_id": self.run_id,
            "engine": self.engine_name,
            "command": self.display_command,
            "started": self.started,
            "finished": utc_now(),
            "environment": self.environment,
            "options": {k: redact_home(v) for k, v in vars(self.args).items() if k != "func"},
            "measurements": self.measurements,
            "skipped": self.skipped,
        }


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path, timeout=60):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def api_call(socket_path, method, path, body=None, timeout=60):
    connection = UnixHTTPConnection(socket_path, timeout)
    try:
        payload = json.dumps(body) if body is not None else None
        headers = {"Content-Type": "application/json"} if body is not None else {}
        connection.request(method, "/v1.41" + path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read()
        if response.status >= 400:
            raise RuntimeError(f"API {method} {path}: HTTP {response.status}: {data[:500]!r}")
        return json.loads(data) if data else {}
    finally:
        connection.close()


def engine_version(ctx):
    try:
        result = ctx.call(["version", "--format", "{{json .}}"], timeout=20)
        return result.stdout.decode("utf-8", "replace").strip()[:8000]
    except Exception as exc:
        return f"unavailable: {exc}"


def lifecycle_suite(ctx):
    ctx.pull(IMAGE)
    holder = ctx.resource_name("exec")
    ctx.call(["run", "-d", "--name", holder, IMAGE, "sleep", "3600"])
    ctx.measure("cli.run", lambda _: ctx.call(["run", "--rm", IMAGE, "true"], discard_output=True), ctx.args.runs)
    ctx.measure("cli.exec", lambda _: ctx.call(["exec", holder, "true"], discard_output=True), ctx.args.runs)
    size = ctx.args.transfer_mb * 1024 * 1024
    ctx.measure(
        "cli.stdout",
        lambda _: ctx.call(["run", "--rm", IMAGE, "head", "-c", str(size), "/dev/zero"], discard_output=True, timeout=300),
        ctx.args.io_runs,
        "MB/s",
    )
    for measurement in ctx.measurements:
        if measurement["name"] == "cli.stdout":
            for sample in measurement["samples"]:
                if sample["success"]:
                    sample["value"] = ctx.args.transfer_mb / sample["seconds"]
            measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])

    def stdin(_):
        result = ctx.call(["run", "--rm", "-i", IMAGE, "wc", "-c"], input_data=b"\0" * size, timeout=300)
        seen = int(result.stdout.strip())
        if seen != size:
            raise RuntimeError(f"container received {seen} of {size} bytes")
        return None

    measurement = ctx.measure("cli.stdin", stdin, ctx.args.io_runs, "MB/s")
    for sample in measurement["samples"]:
        if sample["success"]:
            sample["value"] = ctx.args.transfer_mb / sample["seconds"]
    measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])

    context = tempfile.TemporaryDirectory(prefix="kiri-bench-build-")
    dockerfile = Path(context.name) / "Dockerfile"
    dockerfile.write_text("FROM alpine\nRUN echo one > /one\nRUN echo two > /two\nRUN echo three > /three\n", encoding="utf-8")
    image = ctx.add_resource("image", f"kiri-bench-{ctx.run_id}:latest")
    buildx = ctx.call(["buildx", "version"], check=False, timeout=20)
    if buildx.returncode == 0:
        build_command = ["buildx", "build", "--load"]
        # buildx uses the globally selected builder unless told otherwise,
        # so build on the builder named after this engine's context.
        builder = context_name(ctx)
        if builder:
            build_command += ["--builder", builder]
    elif ctx.engine_name == "kiri":
        build_command = None
        ctx.skip("cli.build", "buildx is not installed")
    else:
        build_command = ["build"]

    def build(_):
        ctx.call(build_command + ["--no-cache", "-q", "-t", image, context.name], timeout=300)
        return None

    if build_command:
        ctx.measure("cli.build", build, ctx.args.io_runs)
    context.cleanup()
    ctx.measure("cli.pull.warm", lambda _: ctx.call(["pull", "-q", IMAGE], timeout=300), ctx.args.io_runs)

    def parallel(_):
        with concurrent.futures.ThreadPoolExecutor(max_workers=ctx.args.parallel) as pool:
            futures = [pool.submit(ctx.call, ["run", "--rm", IMAGE, "true"], True, 120, None, True) for _ in range(ctx.args.parallel)]
            for future in futures:
                future.result()
        return None

    measurement = ctx.measure("cli.parallel", parallel, ctx.args.io_runs, "containers/s")
    for sample in measurement["samples"]:
        if sample["success"]:
            sample["value"] = ctx.args.parallel / sample["seconds"]
    measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])


def context_name(ctx):
    command = ctx.command
    if "--context" in command:
        index = command.index("--context")
        if index + 1 < len(command):
            return command[index + 1]
    return None


def context_socket(ctx):
    name = context_name(ctx)
    if not name:
        return None
    result = ctx.call(["context", "inspect", name, "--format", "{{.Endpoints.docker.Host}}"], check=False, timeout=20)
    host = result.stdout.decode("utf-8", "replace").strip()
    return host.removeprefix("unix://") if result.returncode == 0 and host.startswith("unix://") else None


def api_suite(ctx):
    path = ctx.args.socket
    if not path:
        host = os.environ.get("DOCKER_HOST", "")
        if host.startswith("unix://"):
            path = host.removeprefix("unix://")
        elif context_socket(ctx):
            path = context_socket(ctx)
        elif ctx.engine_name == "kiri":
            path = str(Path.home() / ".kiri/run/docker.sock")
        else:
            path = "/var/run/docker.sock"
    if path.startswith("npipe:") or platform.system() == "Windows":
        ctx.skip("api", "direct API currently supports Unix sockets only")
        return
    if not Path(path).exists():
        ctx.skip("api", f"socket not found: {path}")
        return
    ctx.pull(IMAGE)
    holder = ctx.resource_name("api-exec")
    ctx.call(["run", "-d", "--name", holder, IMAGE, "sleep", "3600"])

    def lifecycle(index):
        name = ctx.resource_name(f"api-life-{index}")
        created = api_call(path, "POST", f"/containers/create?name={name}", {"Image": IMAGE, "Cmd": ["true"], "HostConfig": {"NetworkMode": "none"}})
        identifier = created["Id"]
        api_call(path, "POST", f"/containers/{identifier}/start")
        api_call(path, "POST", f"/containers/{identifier}/wait")
        api_call(path, "DELETE", f"/containers/{identifier}?force=true")

    ctx.measure("api.lifecycle", lifecycle, ctx.args.runs)

    def exec_once(_):
        created = api_call(path, "POST", f"/containers/{holder}/exec", {"AttachStdout": True, "AttachStderr": True, "Cmd": ["true"]})
        api_call(path, "POST", f"/exec/{created['Id']}/start", {"Detach": False, "Tty": False})

    ctx.measure("api.exec", exec_once, ctx.args.runs)


def storage_suite(ctx):
    ctx.pull(IMAGE)
    size = ctx.args.storage_mb
    with tempfile.TemporaryDirectory(prefix="kiri-bench-bind-") as directory:
        os.chmod(directory, 0o777)
        mount = f"{directory}:/d"
        ctx.measure(
            "storage.bind.write",
            lambda _: ctx.call(["run", "--rm", "-v", mount, IMAGE, "dd", "if=/dev/zero", "of=/d/f", "bs=1M", f"count={size}", "conv=fsync"], timeout=300),
            ctx.args.io_runs,
        )
        for measurement in ctx.measurements:
            if measurement["name"] == "storage.bind.write":
                measurement["value_unit"] = "MB/s"
                for sample in measurement["samples"]:
                    if sample["success"]:
                        sample["value"] = size / sample["seconds"]
                measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])
        ctx.measure(
            "storage.bind.read",
            lambda _: ctx.call(["run", "--rm", "-v", mount, IMAGE, "dd", "if=/d/f", "of=/dev/null", "bs=1M"], timeout=300),
            ctx.args.io_runs,
        )
        for measurement in ctx.measurements:
            if measurement["name"] == "storage.bind.read":
                measurement["value_unit"] = "MB/s"
                for sample in measurement["samples"]:
                    if sample["success"]:
                        sample["value"] = size / sample["seconds"]
                measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])

    volume = ctx.add_resource("volume", f"kiri-bench-{ctx.run_id}-volume")
    ctx.call(["volume", "create", volume])
    ctx.measure(
        "storage.volume.write",
        lambda _: ctx.call(["run", "--rm", "-v", f"{volume}:/d", IMAGE, "dd", "if=/dev/zero", "of=/d/f", "bs=1M", f"count={size}", "conv=fsync"], timeout=300),
        ctx.args.io_runs,
    )
    for measurement in ctx.measurements:
        if measurement["name"] == "storage.volume.write":
            measurement["value_unit"] = "MB/s"
            for sample in measurement["samples"]:
                if sample["success"]:
                    sample["value"] = size / sample["seconds"]
            measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])
    ctx.measure(
        "storage.volume.read",
        lambda _: ctx.call(["run", "--rm", "-v", f"{volume}:/d", IMAGE, "dd", "if=/d/f", "of=/dev/null", "bs=1M"], timeout=300),
        ctx.args.io_runs,
    )
    for measurement in ctx.measurements:
        if measurement["name"] == "storage.volume.read":
            measurement["value_unit"] = "MB/s"
            for sample in measurement["samples"]:
                if sample["success"]:
                    sample["value"] = size / sample["seconds"]
            measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_http(port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            connection.request("GET", "/")
            response = connection.getresponse()
            response.read()
            connection.close()
            return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"HTTP server on port {port} did not become ready")


def network_suite(ctx):
    if not shutil.which("iperf3"):
        ctx.skip("network.iperf", "iperf3 is not installed on the host")
    else:
        ctx.pull(IPERF_IMAGE)
        name = ctx.resource_name("iperf")
        port = free_port()
        ctx.call(["run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:5201", IPERF_IMAGE, "-s"])
        time.sleep(2)

        def iperf(parallel):
            def run(_):
                result = subprocess.run(
                    ["iperf3", "-c", "127.0.0.1", "-p", str(port), "-t", str(ctx.args.net_seconds), "-J"] + (["-P", str(parallel)] if parallel > 1 else []),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=ctx.args.net_seconds + 30,
                    check=False,
                )
                if result.returncode:
                    raise RuntimeError(result.stderr.decode("utf-8", "replace")[:1000])
                data = json.loads(result.stdout)
                return data["end"]["sum_received"]["bits_per_second"] / 1e9
            return run

        ctx.measure("network.iperf.single", iperf(1), ctx.args.io_runs, "Gbit/s")
        ctx.measure("network.iperf.parallel", iperf(ctx.args.parallel), ctx.args.io_runs, "Gbit/s")

    ctx.pull(HTTP_IMAGE)
    name = ctx.resource_name("http")
    port = free_port()
    ctx.call(["run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1:{port}:80", HTTP_IMAGE])
    wait_http(port)

    def requests(_):
        for _ in range(ctx.args.http_requests):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            connection.request("GET", "/")
            response = connection.getresponse()
            response.read()
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            connection.close()
        return None

    measurement = ctx.measure("network.http.connections", requests, ctx.args.io_runs, "requests/s")
    for sample in measurement["samples"]:
        if sample["success"]:
            sample["value"] = ctx.args.http_requests / sample["seconds"]
    measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])


def resources_suite(ctx):
    ctx.pull(IMAGE)

    def density(index):
        names = []
        for number in range(ctx.args.density):
            name = ctx.resource_name(f"density-{index}-{number}")
            names.append(name)
            ctx.call(["run", "-d", "--name", name, IMAGE, "sleep", "3600"])
        result = ctx.call(["stats", "--no-stream", "--format", "{{json .}}"] + names, timeout=60)
        stats_text = result.stdout.decode("utf-8", "replace")
        ctx.write_json(f"raw/density-stats-{index + 1}.json", [json.loads(line) for line in stats_text.splitlines() if line.strip()])
        ctx.call(["rm", "-f"] + names, timeout=60)
        return None

    measurement = ctx.measure("resources.density", density, ctx.args.io_runs, "containers/s")
    for sample in measurement["samples"]:
        if sample["success"]:
            sample["value"] = ctx.args.density / sample["seconds"]
    measurement["value"] = stats([s["value"] for s in measurement["samples"] if s["success"]])


RUNNERS = {
    "lifecycle": lifecycle_suite,
    "api": api_suite,
    "storage": storage_suite,
    "network": network_suite,
    "resources": resources_suite,
}


def write_report(summary, directory):
    directory = Path(directory)
    lines = [
        "# Kiri runtime test report",
        "",
        f"- Engine: `{summary['engine']}`",
        f"- Command: `{command_text(summary['command'])}`",
        f"- Started: `{summary['started']}`",
        f"- System: `{summary['environment']['system']} {summary['environment']['release']} ({summary['environment']['machine']})`",
        f"- Host label: `{summary['environment']['host_label']}`",
        "",
        "| Test | Status | Runs | Median seconds | p95 seconds | Value |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for item in summary["measurements"]:
        seconds = item["seconds"]
        value = item.get("value", {})
        value_text = f"{value.get('median', 0):.3f} {item['value_unit']}" if value else "—"
        lines.append(f"| {item['name']} | {item['status']} | {item['runs']} | {seconds.get('median', 0):.6f} | {seconds.get('p95', seconds.get('median', 0)):.6f} | {value_text} |")
    if summary["skipped"]:
        lines += ["", "## Skipped", ""]
        lines += [f"- {item['name']}: {item['reason']}" for item in summary["skipped"]]
    lines += ["", "Raw samples are in `raw/`. `summary.json` is the machine-readable source for this report.", ""]
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run_suite(args):
    if args.out is None:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.out = str(Path("results") / f"{stamp}-{safe_name(args.engine)}")
    if Path(args.out).exists():
        raise SystemExit(f"output already exists: {args.out}")
    ctx = RunContext(args)
    ctx.environment["engine_version"] = engine_version(ctx)
    ctx.environment["iperf3"] = shutil.which("iperf3")
    try:
        for suite in args.suite:
            print(f"[{suite}]")
            RUNNERS[suite](ctx)
    finally:
        if not args.keep:
            ctx.cleanup()
        for measurement in ctx.measurements:
            ctx.write_json(f"raw/{safe_name(measurement['name'])}.json", measurement)
        summary = ctx.summary()
        ctx.write_json("summary.json", summary)
        write_report(summary, ctx.out)
    failures = sum(m["failures"] for m in ctx.measurements)
    print(f"Results: {ctx.out}")
    return 1 if failures else 0


def matrix_suite(args):
    if args.command:
        raise SystemExit("--command applies to one engine, not a matrix")
    requested = args.engines.split(",") if args.engines else list(ENGINES)
    if args.out:
        base = Path(args.out).resolve()
        if base.exists():
            raise SystemExit(f"output already exists: {base}")
    else:
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = Path("results") / f"{stamp}-matrix"
    base.mkdir(parents=True, exist_ok=False)
    runs = []
    for engine in requested:
        args.engine = engine
        args.out = str(base / engine)
        if engine not in ENGINES:
            print(f"[{engine}] skipped (unknown engine)")
            continue
        command = ENGINES[engine]
        available = shutil.which(command[0])
        if not available:
            print(f"[{engine}] skipped ({command[0]} is not installed)")
            continue
        if engine in ["colima", "orbstack", "docker-desktop", "kiri", "docker"]:
            check = subprocess.run(command + ["version", "--format", "{{json .}}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, check=False)
            if check.returncode:
                print(f"[{engine}] skipped (engine is not running)")
                continue
        code = run_suite(args)
        runs.append({"engine": engine, "directory": args.out, "summary": json.loads((Path(args.out) / "summary.json").read_text(encoding="utf-8")), "exit_code": code})
    combined = {"schema_version": SCHEMA_VERSION, "suite_version": VERSION, "runs": runs}
    (base / "summary.json").write_text(json.dumps(combined, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# Runtime matrix report", "", "| Engine | Test | Median seconds | p95 seconds | Value |", "|---|---|---:|---:|---:|"]
    for run in runs:
        for item in run["summary"]["measurements"]:
            seconds = item["seconds"]
            value = item.get("value", {})
            value_text = f"{value.get('median', 0):.3f} {item['value_unit']}" if value else "—"
            lines.append(f"| {run['engine']} | {item['name']} | {seconds.get('median', 0):.6f} | {seconds.get('p95', seconds.get('median', 0)):.6f} | {value_text} |")
    lines += ["", "Each engine has its own raw samples and report in its subdirectory.", ""]
    (base / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Matrix results: {base}")
    return 1 if any(run["exit_code"] for run in runs) or not runs else 0


def doctor(args):
    ctx = RunContext(args)
    print(f"Suite: {VERSION}")
    print(f"Engine command: {command_text(ctx.command)}")
    print(f"Python: {platform.python_version()}")
    print(f"iperf3: {shutil.which('iperf3') or 'not found (network throughput will be skipped)'}")
    try:
        result = ctx.call(["version", "--format", "{{json .}}"], timeout=20)
        print(result.stdout.decode("utf-8", "replace").strip())
        return 0
    except Exception as exc:
        print(f"Engine unavailable: {exc}")
        return 1


def compare(args):
    first = json.loads(Path(args.first).read_text(encoding="utf-8"))
    second = json.loads(Path(args.second).read_text(encoding="utf-8"))
    other = {m["name"]: m for m in second["measurements"]}
    lines = [f"| Test | {first['engine']} median s | {second['engine']} median s | A/B |", "|---|---:|---:|---:|"]
    for item in first["measurements"]:
        if item["name"] not in other or not item["seconds"] or not other[item["name"]]["seconds"]:
            continue
        a = item["seconds"]["median"]
        b = other[item["name"]]["seconds"]["median"]
        lines.append(f"| {item['name']} | {a:.6f} | {b:.6f} | {a / b:.3f}x |")
    output = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


def clean(args):
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    resources = manifest.get("resources", [])
    if not resources:
        print("Nothing to clean")
        return 0
    command = [os.path.expanduser(part) for part in (shlex.split(args.command) if args.command else manifest["command"])]
    for item in reversed(resources):
        kind, name = item["kind"], item["name"]
        action = {"container": ["rm", "-f"], "volume": ["volume", "rm"], "network": ["network", "rm"], "image": ["rmi", "-f"]}[kind]
        subprocess.run(command + action + [name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
        print(f"Removed {kind} {name}")
    return 0


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--version", action="version", version=VERSION)
    sub = root.add_subparsers(dest="action", required=True)
    for name in ["doctor", "run", "matrix"]:
        p = sub.add_parser(name)
        p.add_argument("--engine", choices=ENGINES, default="kiri")
        p.add_argument("--command", help="custom Docker-compatible command, quoted")
        p.add_argument("--label", help="non-identifying label for this machine")
        if name == "doctor":
            p.set_defaults(out=None)
            continue
        p.add_argument("--suite", default=",".join(SUITES), help=f"comma-separated: {','.join(SUITES)}")
        p.add_argument("--engines", help="matrix: comma-separated engines (default: all available)")
        p.add_argument("--out")
        p.add_argument("--quick", action="store_true")
        p.add_argument("--runs", type=int, default=30)
        p.add_argument("--warmup", type=int, default=3)
        p.add_argument("--io-runs", type=int, default=5)
        p.add_argument("--parallel", type=int, default=4)
        p.add_argument("--transfer-mb", type=int, default=200)
        p.add_argument("--storage-mb", type=int, default=1024)
        p.add_argument("--net-seconds", type=int, default=5)
        p.add_argument("--http-requests", type=int, default=200)
        p.add_argument("--density", type=int, default=20)
        p.add_argument("--socket", help="Docker API Unix socket")
        p.add_argument("--keep", action="store_true", help="keep test resources for debugging")
        p.set_defaults(func=run_suite if name == "run" else matrix_suite)
    sub.add_parser("list").set_defaults(func=lambda _: list_items())
    report = sub.add_parser("report")
    report.add_argument("directory")
    report.set_defaults(func=lambda args: (write_report(json.loads((Path(args.directory) / "summary.json").read_text(encoding="utf-8")), args.directory) or 0))
    comp = sub.add_parser("compare")
    comp.add_argument("first")
    comp.add_argument("second")
    comp.add_argument("--out")
    comp.set_defaults(func=compare)
    cl = sub.add_parser("clean")
    cl.add_argument("manifest")
    cl.add_argument("--command", help="override the engine command stored in the manifest")
    cl.set_defaults(func=clean)
    return root


def list_items():
    print("Engines:", ", ".join(ENGINES))
    print("Suites:", ", ".join(SUITES))
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action in ["run", "matrix"]:
        args.suite = [s.strip() for s in args.suite.split(",") if s.strip()]
        unknown = set(args.suite) - set(SUITES)
        if unknown:
            raise SystemExit(f"unknown suites: {', '.join(sorted(unknown))}")
        if args.quick:
            args.warmup = min(args.warmup, 1)
            args.runs = min(args.runs, 3)
            args.io_runs = min(args.io_runs, 2)
            args.transfer_mb = min(args.transfer_mb, 16)
            args.storage_mb = min(args.storage_mb, 32)
            args.net_seconds = min(args.net_seconds, 2)
            args.http_requests = min(args.http_requests, 10)
            args.density = min(args.density, 3)
        for name in ["runs", "io_runs", "parallel", "transfer_mb", "storage_mb", "net_seconds", "http_requests", "density"]:
            if getattr(args, name) < 1:
                raise SystemExit(f"--{name.replace('_', '-')} must be at least 1")
    if args.action == "doctor":
        return doctor(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
