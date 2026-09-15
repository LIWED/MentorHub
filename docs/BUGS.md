# Known limitations

## 2026-09-06 Resume Agent timing

- No business bug was changed by the timing work.
- Timings depend on local environment, network, LLM latency, and retry behavior; retry waits are included in the observed stage durations.
- The six dimension evaluations are concurrent. Their individual durations describe overlapping work and must not be summed into an overall duration.
- The single authorized real-run process ended without a retrievable console exit status or timing table in this task environment. Its real timings remain unverified; no automatic retry was performed to avoid additional LLM usage.
- Fixed a manual-benchmark privacy risk: resume-node logs could expose response previews, parse snippets, or extracted names. The benchmark now suppresses only that node logger during analysis and restores its prior state without changing production node logging.
