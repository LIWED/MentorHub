# EduAgent Project Status

## Resume Agent timing

- Status: timing collection and the manual benchmark are present; the 2026-09-06 real-run console result is unverified because its supervising console ended before the sanitized exit status and timing table could be retained. No retry was made, to avoid additional LLM usage.
- Real-run command: `conda run -n EduAgent python scripts/manual_tests/benchmark_resume_agent.py`
- Requested timing stages: PDF text extraction, structured extraction, six-dimension parallel evaluation, issue diagnosis, and summary generation.
- The report includes six individual dimension spans: project depth, technology match, expression quality, resume structure, quantification, and authenticity.
- Benchmark behavior: it prints timings to the console only, copies `samples/sample1.pdf` to a temporary file for the run, and does not call the database persistence node.
- Privacy boundary: while the five production resume nodes execute, the benchmark disables only the exact standard logger `backend.agents.resume.nodes`; its prior state is restored even if a node raises, and the timing report prints after that scope ends.
- Performance note: measured timings are environment-dependent and include any retry waits; do not treat them as deterministic performance guarantees. The six dimension spans run concurrently and must not be summed.

## Verification snapshot (2026-09-06)

- `samples/sample1.pdf` SHA-256 and byte length matched before and after the authorized single run.
- No `eduagent-resume-timing-*.pdf` files remained in the system temporary directory after the observed process ended.
- Offline regression and compile checks are recorded in the task report.
