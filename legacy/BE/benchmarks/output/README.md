# Benchmark Output

This folder stores saved benchmark artifacts.

Each benchmark run should produce:

- one raw JSON result file
- one Markdown report file

Recommended filename pattern:

- `chat-latency_<provider>_<yyyy-mm-dd_hh-mm-ss>.json`
- `chat-latency_<provider>_<yyyy-mm-dd_hh-mm-ss>.md`

The benchmark runner now saves both files automatically unless you override the paths with command-line options.
