# Recorded browser test

This directory contains a silent Playwright screen recording of the real SimplifySimulation frontend. The test uses a separate disposable backend database and fictional capacity-planning inputs. It does not show real project data or credentials. HTTP requests are forwarded to that real isolated backend; response bodies are not mocked. OpenRouter and Tavily calls are live and consume the configured provider account quota.

- [Watch/download the MP4 recording](simplifysimulation-desktop.mp4)
- [Machine-readable step results](test-report.json)
- [Reusable Playwright script](../../tests/browser/record-flow.cjs)

The latest run passed 13 browser steps in 70 seconds, with zero JavaScript errors and no mobile horizontal overflow. The simulation result was independently checked as COMPLETED with 10,000 iterations. The conversation check also rejects infrastructure vendor names in the primary decision screen.

The recording covers decision intake, real agent clarification, context confirmation, multiple CSVs, identifier exclusion, source-scoped discussion, mapping/approval, combined evidence, real model proposal, 10K simulations, recorded decision/reload, Tavily search and mobile layout. It does not test a real company's database, production tenant isolation or forecasting accuracy.

## Reproduce

Use Python 3.12, Node 24, Chromium and FFmpeg. Install app dependencies from the root (`npm --prefix web ci` and the Python lockfile). Install Playwright's browser/video binaries with `npm --prefix web exec -- playwright install chromium`. The existing frontend must be running on port 3000. Launch a **separate disposable** backend in another terminal:

```sh
NORTH_DATA_DIR=/tmp/simplifysimulation-recording-data .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 18000
```

That backend needs configured `OPENROUTER_API_KEY` and `TAVILY_API_KEY` environment bindings. Do not type real keys into recorded forms or commit them to files. With the frontend and isolated API running:

```sh
SIMPLIFY_LIVE_BROWSER_TEST=1 SIMPLIFY_TEST_API_URL=http://127.0.0.1:18000 node tests/browser/record-flow.cjs
```

Playwright saves WebM video and a JSON report in this directory. For MP4 playback compatibility, encode the complete uncut recording:

```sh
ffmpeg -i docs/recordings/simplifysimulation-desktop.webm -c:v libx264 -preset medium -crf 24 -pix_fmt yuv420p -movflags +faststart docs/recordings/simplifysimulation-desktop.mp4
```

On hosts with an existing system Chromium, `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` can select that executable. Otherwise the script uses Playwright's installed Chromium. Test failures still save the recording and report, and return a nonzero exit code. The video has no audio; step timestamps in the report align with the recording.
