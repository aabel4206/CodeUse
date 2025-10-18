# Executor Module

The executor service is responsible for taking structured execution requests that the orchestrator produces, running them inside the appropriate sandbox, and returning a normalized result that downstream components (for example, `reporter/`) can render back to the user. This document captures the conventions the rest of the CodeUse stack expects from the executor so implementation work can follow a shared contract.

## Role in the CodeUse pipeline

1. The orchestrator assembles an `ExecutionRequest` describing the tool to run (e.g. `shell`, `apply_patch`), the arguments, environment variables, working directory, and timeout budget.
2. The executor validates the request, provisions the runtime (sandbox, temp directories, credentials), and invokes the tool.
3. While the tool runs, the executor streams stdout/stderr lines back to the orchestrator for real-time display and monitoring.
4. After completion, it normalizes the exit status, captures artifacts (files, JSON blobs, logs), and persists them to shared storage for the reporter.

Keeping this lifecycle consistent ensures that higher-level components can remain implementation-agnostic and simply rely on the executor contract.

## Execution contract

The executor SHOULD support JSON requests shaped like:

```json
{
  "id": "job-8732",
  "tool": "shell",
  "arguments": ["pnpm", "vitest"],
  "cwd": "C:/Users/aabel/Downloads/CodeUse",
  "env": {
    "NODE_ENV": "test"
  },
  "timeoutMs": 600000,
  "stream": true
}
```

And it SHOULD respond with:

```json
{
  "id": "job-8732",
  "status": "completed",
  "exitCode": 0,
  "startedAt": "2025-10-18T19:16:59.132Z",
  "finishedAt": "2025-10-18T19:17:42.917Z",
  "stdout": [
    {"chunk": "✓ all tests passed", "timestamp": "2025-10-18T19:17:40.251Z"}
  ],
  "stderr": [],
  "artifacts": [
    {"type": "file", "path": "reports/vitest/junit.xml"}
  ]
}
```

Use `"status": "failed"` with a non-zero `exitCode` when the tool terminates abnormally, and `"status": "timeout"` when the executor stops the process after exceeding `timeoutMs`.

## Sandbox expectations

- Every execution MUST run with the least privilege necessary. When possible, leverage ephemeral containers or temp directories with explicit allowlists.
- The executor MUST redact secrets before streaming logs. At minimum, filter any string that matches the configured secret patterns the orchestrator provides.
- Implement coordinated cleanup so temporary folders, named pipes, and subprocess handles are disposed even when the job is cancelled.

## Logging and metrics

- Emit structured logs keyed by `jobId`, `tool`, and `status` so the orchestrator can correlate events.
- Record latency histograms (queue wait, execution duration) to surface hotspots.
- Surface a heartbeat (e.g. Prometheus `/metrics` or simple JSON status endpoint) so the orchestrator knows when to drain work.

## Local development guide

1. **Bootstrap** – Install runtime dependencies (`pnpm`, `python`, or the stack you choose) and populate `.env` with test credentials as needed.
2. **Replay jobs** – Keep a `fixtures/` folder with sample `ExecutionRequest` JSON documents (including edge cases like timeouts) to exercise the executor without going through the full orchestrator.
3. **Integration tests** – Provide scripts that run the executor against a mock orchestrator to validate streaming, cancellation, and artifact publishing logic.
4. **Smoke checks** – Before releasing, execute long-running workloads to ensure cleanup and log streaming remain stable.

## Open questions / TODOs

- Define the authoritative schema for `ExecutionRequest` and `ExecutionResult` (consider using JSON Schema).
- Decide whether artifact persistence is handled directly by the executor or delegated to a shared storage service.
- Establish retry semantics: should the executor be idempotent, or should the orchestrator handle retries on failure?
- Document any platform-specific limitations (for example, Windows path length, macOS sandbox restrictions).

Update this README alongside implementation work so contributors always have an accurate, end-to-end picture of how the executor fits into CodeUse.
