# Narrated Opening Scene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 12–15 second narrated `scene-000` that explains the video’s purpose, then prepend it to the verified 4582-frame V3 body without changing the existing 13 scenes.

**Architecture:** A small, independently tested opening-TTS path generates one MiniMax utterance and converts its real 48kHz PCM sample count into a frame-exact opening duration. A V4 timeline builder shifts the existing 37 subtitle entries by that exact integer-millisecond duration and scaffolds one Claude-owned HyperFrames scene. A final assembler prepends the new scene to the locked V3 silent body, constructs a sample-exact narration track, applies measured two-pass loudness normalization, verifies the temporary deliverable, and only then replaces `final.mp4`.

**Tech Stack:** Node.js 22 ESM, Node test runner, MiniMax TTS API, HyperFrames 0.7.72, Claude CLI, FFmpeg/FFprobe, Bash, jq.

---

## File map

Create or modify only these source files:

- Create `audio/opening-v4.config.json` — fixed approved narration and MiniMax settings.
- Create `audio/opening-v4-lib.mjs` — pure validation, frame/sample timing, pause stripping, SRT parsing/shifting, and stage-log validation.
- Create `audio/opening-v4.test.mjs` — unit tests for every pure timing and contract rule.
- Create `audio/fixtures/v3-body-srt.fixture.srt` — tracked 37-entry test fixture; tests never depend on runtime V3 media.
- Create `audio/generate-opening-v4.mjs` — one-request MiniMax generator with attempt-scoped audit artifacts.
- Create `audio/prepare-v4.mjs` — validates locked V3 inputs, writes V4 manifest/timing/SRT, pads opening PCM, scaffolds `scene-000`, and generates its Claude script.
- Create `audio/assemble-v4-lib.mjs` — pure FFmpeg argument builders and final-report validators.
- Create `audio/assemble-v4.test.mjs` — tests sample counts, loudnorm filter construction, frame totals, and atomic-replacement preconditions.
- Create `audio/assemble-v4.mjs` — creates the silent concat, sample-exact PCM, normalized AAC deliverable, reports, backup, and atomic replacement.
- Create `audio/fixtures/fake-ffmpeg-measurement.json` — tracked loudness/parser fixture.
- Generate `scenes-v4/**` — attempt logs, opening project, rendered media, manifest, reports, subtitle, concat inputs, and verification captures. Generated media is not committed.
- Generate `transcription-v4.srt`, `final-pre-v4.mp4`, `final-v4.mp4`, and the verified replacement `final.mp4`. Generated media is not committed.

Do not modify `.env`, `scenes-v3/**`, `final-v3.mp4`, `final-v3-silent.mp4`, `transcription-retimed.srt`, or the existing V3 TTS configuration.

### Task 1: Build the frame-exact opening timeline primitives

**Files:**
- Create: `audio/opening-v4-lib.mjs`
- Create: `audio/opening-v4.test.mjs`
- Create: `audio/fixtures/v3-body-srt.fixture.srt`
- Read: `audio/build-v3-timeline-lib.mjs`
- Read: `scenes-v3/transcription-retimed.srt`

- [ ] **Step 1: Write failing timing and SRT tests**

Cover these exact behaviors:

```js
test("quantizes the opening to a whole millisecond and three-frame boundary", () => {
  assert.deepEqual(computeOpeningTiming(560_000), {
    speechSamples: 560_000,
    baseFrames: 365,
    openingFrames: 366,
    openingDurationMs: 12_200,
    openingSamples: 585_600,
    breathingSamples: 25_600,
    breathingDurationSeconds: 0.533333,
  });
});

test("rejects narration whose padded duration is outside the approved gate", () => {
  assert.throws(() => computeOpeningTiming(500_000), /breathing/i);
  assert.throws(() => computeOpeningTiming(700_000), /450 frames/i);
});

test("builds opening entries and shifts all 37 body subtitles", () => {
  const result = buildV4Srt(openingSubtitleEntries, bodySrtFixture, timing);
  assert.equal(result.entries.length, openingSubtitleEntries.length + 37);
  assert.equal(result.bodyEntries[0].startMs, 12_200);
  assert.equal(result.bodyEntries.at(-1).endMs, 164_365);
  assert.equal(result.videoEndFrame, 366 + 4582);
});
```

Also test:

- `stripPauseControls()` removes `<#0.24#>` without changing spoken text.
- MiniMax fractional `time_begin`/`time_end` values use `Math.round()` to integer milliseconds.
- Before rounding, every MiniMax time is finite, nonnegative, monotonic, and the last raw `time_end` is no later than `speechSamples / 48` milliseconds.
- After rounding, entries remain positive-duration, ordered, nonoverlapping, and end no later than `openingDurationMs`.
- Concatenated opening subtitle text, after removing pause controls and Unicode whitespace only, equals `spoken_text` normalized the same way.
- Every shifted V3 start/end delta equals `openingDurationMs`.
- Original gaps and the 568ms body tail are preserved.
- Negative times, overlap, out-of-range subtitles, malformed timestamps, or body entry count other than 37 fail loudly.
- `validateStageMessages()` accepts exactly four ordered messages and rejects duplicates/reordering.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
node --test audio/opening-v4.test.mjs
```

Expected: FAIL because `opening-v4-lib.mjs` or its exports do not exist.

- [ ] **Step 3: Implement the minimal pure library**

Use integer math:

```js
export function computeOpeningTiming(speechSamples) {
  assertPositiveInteger(speechSamples, "speechSamples");
  const baseFrames = Math.max(360, Math.ceil((speechSamples + 24_000) / 1_600));
  const openingFrames = 3 * Math.ceil(baseFrames / 3);
  const openingSamples = openingFrames * 1_600;
  const breathingSamples = openingSamples - speechSamples;
  const breathingDurationSeconds = breathingSamples / 48_000;
  if (openingFrames > 450) throw new Error("opening exceeds 450 frames");
  if (breathingDurationSeconds < 0.5 || breathingDurationSeconds > 0.8) {
    throw new Error("opening breathing duration must be 0.5–0.8 seconds");
  }
  return {
    speechSamples,
    baseFrames,
    openingFrames,
    openingDurationMs: (openingFrames * 1_000) / 30,
    openingSamples,
    breathingSamples,
    breathingDurationSeconds: Number(breathingDurationSeconds.toFixed(6)),
  };
}
```

Keep SRT parsing and serialization integer-millisecond based. Do not route V4 through `formatSrtTime(seconds)` because floating-point seconds are unnecessary here.

- [ ] **Step 4: Run the tests and verify GREEN**

Run:

```bash
node --test audio/opening-v4.test.mjs
```

Expected: all tests PASS.

- [ ] **Step 5: Commit the pure timeline work**

```bash
git add audio/opening-v4-lib.mjs audio/opening-v4.test.mjs audio/fixtures/v3-body-srt.fixture.srt
git commit -m "feat: add frame-exact opening timeline"
```

### Task 2: Add the independent MiniMax opening generator

**Files:**
- Create: `audio/opening-v4.config.json`
- Create: `audio/generate-opening-v4.mjs`
- Modify: `audio/opening-v4.test.mjs`

- [ ] **Step 1: Add failing configuration and response-extraction tests**

The approved config must contain:

```json
{
  "model": "speech-2.8-hd",
  "voice": {
    "voice_id": "Chinese (Mandarin)_Sincere_Adult",
    "speed": 0.98,
    "vol": 1,
    "pitch": 0,
    "emotion": "calm"
  },
  "audio": {
    "sample_rate": 32000,
    "bitrate": 128000,
    "format": "mp3",
    "channel": 1
  },
  "language_boost": "Chinese",
  "subtitle_type": "sentence",
  "spoken_text": "AI 已经会写代码了，但它能不能看懂自己写出来的界面？这期视频，我们从原理、精度和工程接入三个层面，看看多模态模型怎样给 Vibe Coding 装上眼睛。",
  "request_text": "AI 已经会写代码了，但它能不能看懂自己写出来的界面？<#0.24#>这期视频，我们从原理、精度和工程接入三个层面，看看多模态模型怎样给 Vibe Coding 装上眼睛。"
}
```

Tests must assert:

- `stripPauseControls(request_text) === spoken_text`.
- The question sentence remains one subtitle entry.
- Pause controls occur only after `？` or after `这期视频，`.
- MiniMax success payload extraction requires `base_resp.status_code === 0`, nonempty hex audio, and subtitle data.
- The real API response is shaped as `data.audio` plus `data.subtitle_file`; test with that shape rather than invented embedded subtitles.
- Subtitle URL validation accepts only HTTPS and the exact host `minimax-algeng-chat-tts.oss-cn-wulanchabu.aliyuncs.com`.
- Subtitle download rejects redirects to another host, non-2xx status, timeout, payloads over 5MB, non-JSON bodies, and entries missing finite `time_begin`, `time_end`, or string `text`.
- Attempt directory names match `attempt-\d{2}` and are never reused.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
node --test audio/opening-v4.test.mjs
```

Expected: FAIL on missing opening-config validation and response extraction.

- [ ] **Step 3: Implement the one-request generator**

The CLI is:

```bash
node audio/generate-opening-v4.mjs \
  --config audio/opening-v4.config.json \
  --out audio/minimax-opening-v4 \
  --attempt attempt-01
```

Implementation requirements:

- Load `.env` with `process.loadEnvFile()` and read only `MINIMAX_API_KEY`.
- Keep payload construction, hex decoding, response validation, and subtitle download self-contained in tracked V4 source. Do not import the currently untracked V3 TTS library.
- POST once to `https://api.minimaxi.com/v1/t2a_v2`, non-streaming, with subtitles enabled.
- After the single TTS POST, perform exactly one unauthenticated GET of the signed `data.subtitle_file` URL. Use a 30-second timeout, reject redirects, require the exact allowed host, enforce the 5MB limit, validate the JSON array schema, and save the downloaded body.
- Never overwrite an existing attempt directory.
- Save `request.json`, the raw TTS `response.json` before semantic checks, `opening.mp3`, the downloaded raw `opening.subtitle.json`, and `spoken-text.txt`.
- Decode to `opening-speech.wav` using stereo 48kHz PCM S16LE.
- Read exact per-channel `duration_ts`/sample count with FFprobe.
- Call `computeOpeningTiming(speechSamples)` before writing a success report.
- Write `generation-report.json` containing the sample/frame gate, trace ID, model, voice settings, and relative artifact paths.
- Exit nonzero before any Claude invocation when the gate or sentence-boundary check fails.

- [ ] **Step 4: Verify dry and live-safe behavior**

Run:

```bash
node --test audio/opening-v4.test.mjs
node audio/generate-opening-v4.mjs --help
```

Expected: tests PASS; help prints arguments without reading `.env` or making a network call.

- [ ] **Step 5: Commit the generator**

```bash
git add audio/opening-v4.config.json audio/generate-opening-v4.mjs audio/opening-v4.test.mjs
git commit -m "feat: add independent opening narration generator"
```

### Task 3: Build the V4 scaffold and exact Claude execution contract

**Files:**
- Create: `audio/prepare-v4.mjs`
- Modify: `audio/opening-v4.test.mjs`
- Generate: `scenes-v4/manifest.json`
- Generate: `scenes-v4/timing-report.json`
- Generate: `scenes-v4/transcription-retimed.srt`
- Generate: `scenes-v4/scene-000/**`

- [ ] **Step 1: Write failing scaffold-contract tests**

Tests must verify generated output contains:

- `scene-000`, exact `openingFrames`, exact decimal `openingDuration`.
- V3 body source fixed to `final-v3-silent.mp4` or all 13 `scenes-v3/normalized/scene-*.mp4`.
- V3 body is exactly 4582 frames and 152.733333 seconds.
- V3 audio source is exactly `scenes-v3/voiceover.wav`.
- V3 subtitle source is exactly `scenes-v3/transcription-retimed.srt`.
- New total frames equal `openingFrames + 4582`.
- `run-claude-ai.sh` contains `SCENE_ID=scene-000`, exact duration, `OUTPUT_FILE`, `FULL_TRANSCRIPT_PATH`, noninteractive Claude flags, unchanged jq filter, and exactly four ordered `[[USER_MESSAGE]]` strings.
- The fourth required message is the literal `[[USER_MESSAGE]]视频已渲染完成：scene-000.mp4`, not a variable expansion.
- The prompt delegates all internal MG creative decisions to Claude and does not prescribe layouts, icons, transitions, or animation choreography.
- The prompt allows writes only under the current `scenes-v4/scene-000/**` directory and explicitly forbids writes to `scenes-v3/**`, `final*.mp4`, root subtitles, and audio sources.
- The runner acquires an exclusive atomic `mkdir` lock before invoking Claude, writes PID/attempt metadata inside it, holds it for the whole pipeline, and removes it with `trap` on exit.
- `CLAUDE_ATTEMPT` must match `^attempt-[0-9]{2}$`; a second invocation with the same attempt must fail before opening any log.

- [ ] **Step 2: Run tests and verify RED**

```bash
node --test audio/opening-v4.test.mjs
```

Expected: FAIL because `prepare-v4.mjs` and its template exports do not exist.

- [ ] **Step 3: Implement V4 preparation**

The command is:

```bash
node audio/prepare-v4.mjs \
  --attempt audio/minimax-opening-v4/attempt-01
```

It must:

- Write a before-call SHA-256 manifest for every file under `scenes-v3/**`, plus `final-v3.mp4`, `final-v3-silent.mp4`, and the current `final.mp4`; store it in V4 audit artifacts.
- Validate SHA-256 plus FFprobe facts for locked assembly inputs and store them in `timing-report.json`.
- Create `scenes-v4/scene-000` without modifying `scenes-v3`.
- Copy the HyperFrames instructions only from tracked `exampleFolder/.claude`; record a sorted SHA-256 manifest for that exact source and copied destination.
- Pad `opening-speech.wav` with silence to exactly `openingSamples` and save `scene-000/voiceover.wav`.
- Write the complete V4 SRT to both `scenes-v4/transcription-retimed.srt` and `scene-000/transcription.srt`.
- Write the approved narration and real MiniMax sentence beats into the Claude prompt.
- Require 1080×1440, 30fps, H.264, yuv420p, BT.709, silent MP4, exact duration, seek-safe animation, HyperFrames check, and full render.
- Preserve the existing noninteractive command, log filtering, fixed output, full subtitle path, and stage-message contract.
- Do not pre-create a Claude attempt directory during preparation. At invocation time, the runner validates `CLAUDE_ATTEMPT`, acquires the global lock, atomically creates that exact attempt directory, and fails if it already exists. Store Claude stream/stderr/user logs and render evidence there; never truncate or reuse another attempt.
- Acquire a lock such as `${TMPDIR:-/tmp}/auto-motion-scene-000-claude.lock` with `mkdir`. If it already exists, fail before Claude starts and report its recorded PID/attempt; stale-lock removal is a separate explicit recovery action after verifying the PID is absent.

- [ ] **Step 4: Run template tests**

```bash
node --test audio/opening-v4.test.mjs
```

Expected: tests PASS. The test writes the generated shell template into a temporary fixture directory, runs `bash -n` there, and asserts the four literal stage messages appear exactly once in order. It also invokes the fixture twice with the same `CLAUDE_ATTEMPT` using a stub Claude executable and proves the second call fails without changing any attempt-01 log checksum. It does not require a real TTS attempt or `scenes-v4` runtime directory.

- [ ] **Step 5: Commit source, not generated media**

```bash
git add audio/prepare-v4.mjs audio/opening-v4.test.mjs
git commit -m "feat: scaffold exact V4 opening scene"
```

### Task 4: Generate and approve the real opening narration gate

**Files:**
- Generate: `audio/minimax-opening-v4/attempt-01/**`
- Generate: `scenes-v4/scene-000/voiceover.wav`
- Generate: `scenes-v4/transcription-retimed.srt`

- [ ] **Step 1: Run the MiniMax request**

```bash
node audio/generate-opening-v4.mjs \
  --config audio/opening-v4.config.json \
  --out audio/minimax-opening-v4 \
  --attempt attempt-01
```

Expected: one successful API response and a passing 360–450 frame / 0.5–0.8 second breathing report.

- [ ] **Step 2: Audit the sentence boundaries and decoded samples**

```bash
jq '.timing, .subtitle_entries, .voice' \
  audio/minimax-opening-v4/attempt-01/generation-report.json
ffprobe -v error -select_streams a:0 \
  -show_entries stream=sample_rate,channels,duration_ts,time_base \
  -of json audio/minimax-opening-v4/attempt-01/opening-speech.wav
```

Expected: 48kHz stereo PCM; first question is a single subtitle entry; the saved subtitle schema and normalized concatenated text pass; timing gate passes.

If it fails, stop. Do not shorten, extend, or regenerate with a changed text without user approval.

- [ ] **Step 3: Generate the V4 scaffold from the approved attempt**

```bash
node audio/prepare-v4.mjs \
  --attempt audio/minimax-opening-v4/attempt-01
```

Expected: V4 manifest, timing report, shifted SRT, padded scene voiceover, and executable Claude script.

Preparation also writes `scenes-v4/claude-input-manifest.sha256`, covering every read-only Claude input: root protected subtitles, `scene-000/voiceover.wav`, `scene-000/transcription.srt`, `scene-000/run-claude-ai.sh`, the copied `.claude/**` instructions, and all audio-source/config files referenced by the prompt.

- [ ] **Step 4: Inspect the real generated shell contract**

```bash
bash -n scenes-v4/scene-000/run-claude-ai.sh
rg -n 'SCENE_ID|SCENE_DURATION_SECONDS|OUTPUT_FILE|FULL_TRANSCRIPT_PATH|USER_MESSAGE' \
  scenes-v4/scene-000/run-claude-ai.sh
```

Expected: Bash syntax exits 0, exact fixed fields are present, and the four literal stage messages appear once in order.

- [ ] **Step 5: Verify no protected-file mutation**

Compare the stored manifest with a fresh manifest for all `scenes-v3/**`, `final-v3.mp4`, `final-v3-silent.mp4`, and the current `final.mp4`. Expected: byte-identical.

### Task 5: Invoke Claude once to create and render `scene-000`

**Files:**
- Modify by Claude: `scenes-v4/scene-000/hf/**`
- Generate: `scenes-v4/scene-000/scene-000.mp4`
- Generate: `scenes-v4/scene-000/attempt-01/claude-*.log`

Use @hyperframes, @hyperframes-cli, @hyperframes-core, and @media-use for validation and render ownership. The coordinating process must not design the internal MG animation.

- [ ] **Step 1: Preflight the single-call contract**

```bash
bash -n scenes-v4/scene-000/run-claude-ai.sh
test ! -e "${TMPDIR:-/tmp}/auto-motion-scene-000-claude.lock"
```

Expected: valid Bash and no existing lock. The generated runner itself must acquire the lock atomically; process listing is diagnostic only and is not the concurrency gate.

- [ ] **Step 2: Run exactly one Claude process**

```bash
cd scenes-v4/scene-000
PATH="/Users/chouheiwa/.asdf/installs/nodejs/22.21.1/bin:$PATH" \
  CLAUDE_ATTEMPT=attempt-01 \
  ./run-claude-ai.sh
```

Monitor only the filtered stage output. During quiet periods inspect stream/stderr mtimes, project/render files, HyperFrames/FFmpeg/Chromium/Node processes, and final exit code. Do not mark failure based on silence alone.

If Claude exits unsuccessfully, preserve attempt-01 and retry only with:

```bash
CLAUDE_ATTEMPT=attempt-02 ./run-claude-ai.sh
```

- [ ] **Step 3: Verify the Claude result independently**

```bash
test -s scenes-v4/scene-000/scene-000.mp4
ffprobe -v error -show_entries \
  stream=codec_name,width,height,r_frame_rate,pix_fmt,color_space,color_transfer,color_primaries,nb_frames \
  -of json scenes-v4/scene-000/scene-000.mp4
```

Expected: H.264, 1080×1440, 30fps, yuv420p, BT.709, no audio, and at least `openingFrames` frames.

Immediately recreate both protected manifests and compare them with their baselines. Any mutation under `scenes-v3/**`, or to `final-v3.mp4`, `final-v3-silent.mp4`, the previous `final.mp4`, root protected subtitles, `scene-000/voiceover.wav`, `scene-000/transcription.srt`, the runner, copied instructions, or audio sources is a hard failure.

- [ ] **Step 4: Normalize decoded frames and timestamps**

Reject the render if it has fewer than `openingFrames` decoded frames or more than two surplus frames. Normalize with a decoded-frame filter, not packet trimming:

```bash
mkdir -p scenes-v4/normalized
ffmpeg -v error -y -i scenes-v4/scene-000/scene-000.mp4 \
  -map 0:v:0 -an \
  -vf "trim=end_frame=${openingFrames},setpts=N/(30*TB),fps=30" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 \
  -movflags +faststart scenes-v4/normalized/scene-000.mp4
```

The executed implementation should construct these arguments without shell interpolation. Verify with `ffprobe -count_frames` that the file has exactly `openingFrames` decoded frames, start time/first PTS is zero, timestamps are continuous CFR 30, dimensions/color metadata match, and there is no audio stream.

- [ ] **Step 5: Visually inspect representative opening frames**

Capture a contact sheet spanning the opening plus the opening/body boundary. Confirm:

- Narration purpose is readable without duplicating the first body scene.
- No blank or frozen tail was used to fill time.
- The local opening end is visually suitable for a transition.

Full opening/body transition and body icon regression captures happen against staged `final-v4.mp4` in Task 7, before promotion.

### Task 6: Implement and test the final V4 assembler

**Files:**
- Create: `audio/assemble-v4-lib.mjs`
- Create: `audio/assemble-v4.test.mjs`
- Create: `audio/assemble-v4.mjs`
- Create: `audio/fixtures/fake-ffmpeg-measurement.json`

- [ ] **Step 1: Write failing assembly tests**

Test:

```js
assert.equal(totalFrames(openingFrames), openingFrames + 4582);
assert.equal(totalSamples(openingFrames), (openingFrames + 4582) * 1600);
assert.equal(buildFirstPassFilter(), "loudnorm=I=-16:TP=-2.0:LRA=11:print_format=json");
assert.match(buildSecondPassFilter(measurement), /I=-16/);
assert.match(buildSecondPassFilter(measurement), /TP=-2\.0/);
```

Also assert:

- Missing or mutated V3 inputs abort before output writes.
- Parsed first-pass measurement requires finite `input_i`, `input_lra`, `input_tp`, `input_thresh`, and `target_offset`.
- The first pass is exactly `I=-16`, `TP=-2.0`, `LRA=11`, `print_format=json`.
- The second pass uses those identical targets and contains `measured_I`, `measured_LRA`, `measured_TP`, `measured_thresh`, and offset.
- Promotion requires `final-pre-v4.mp4` checksum to equal the current `final.mp4` checksum before replacement.
- Temporary MP4 validation requires exact video frames, audio/video difference ≤1 frame, H.264/AAC specs, final loudness `-16 ±0.5 LUFS`, and true peak ≤`-1.5 dBTP`.
- Atomic replacement is unreachable until every gate passes.
- A temp-directory integration test starts with a sentinel `final.mp4`, injects a failure at every validation gate, and proves both the sentinel and any existing `final-pre-v4.mp4` remain byte-identical.
- If `final-pre-v4.mp4` already exists and differs from current `final.mp4`, promotion aborts instead of overwriting the backup.
- An injected post-rename checksum failure triggers atomic rollback from a checksum-verified backup candidate and restores the original sentinel `final.mp4` byte-for-byte.
- Argument parsing supports four explicit, mutually exclusive modes: assemble, `--verify-only <mp4>`, `--write-approval <mp4>`, and `--promote <validated-mp4>`.
- `--verify-only` is strictly read-only, loads `scenes-v4/timing-report.json`, runs all machine gates, and exits nonzero on any mismatch.
- `--write-approval` requires a completed visual checklist and writes the candidate SHA-256, timing-report SHA-256, SRT SHA-256, verification-report SHA-256, checklist hash, and approval timestamp.
- `--promote` requires the approval artifact, confirms all bound hashes still match, and reruns the full read-only verification immediately before backup/rename.

- [ ] **Step 2: Run tests and verify RED**

```bash
node --test audio/assemble-v4.test.mjs
```

Expected: FAIL because assembler exports do not exist.

- [ ] **Step 3: Implement the assembler**

The command is:

```bash
node audio/assemble-v4.mjs \
  --v4 scenes-v4 \
  --opening scenes-v4/normalized/scene-000.mp4 \
  --body final-v3-silent.mp4 \
  --body-audio scenes-v3/voiceover.wav \
  --output final-v4.mp4
```

Implementation order:

1. Revalidate V3 hashes, 4582 body frames, 152.733333-second body, and opening frame count.
2. Decode-concat normalized opening video and `final-v3-silent.mp4` with per-input `setpts=PTS-STARTPTS` and the FFmpeg concat filter, then encode the complete silent V4 video once with libx264, CFR 30, yuv420p, BT.709, and a zero start PTS. Do not stream-copy independently encoded H.264 inputs.
3. Concat the exact padded opening PCM and body voiceover PCM.
4. Pad/trim the raw full PCM timeline to `(openingFrames + 4582) × 1600` samples/channel.
5. Run loudnorm measurement pass and parse its JSON.
6. Run second pass with measured fields, `I=-16`, `TP=-2.0`, and the measured offset.
7. Resample to 48kHz and pad/trim the post-normalization PCM again to the exact total sample count.
8. Save the exact pre-normalization full timeline at `scenes-v4/audio/full-timeline-raw.wav` and post-normalization exact timeline at `scenes-v4/audio/full-timeline-normalized.wav`. FFprobe must report `duration_ts === (openingFrames + 4582) × 1600` for the saved post-normalization PCM.
9. Encode AAC 192kbps stereo and mux with the normalized H.264 video into a temporary MP4.
10. Run `ffmpeg -v error -xerror -i <temp> -map 0 -f null -`, `ffprobe -count_frames`, stream-count/start-PTS/CFR checks, and a machine-parsed post-AAC loudnorm or ebur128 scan; write success or failure details to `scenes-v4/final-verification.json`.
11. Write stable reproduction artifacts: `scenes-v4/concat-video.txt` or an equivalent JSON command manifest, `scenes-v4/assembly-command.json`, and `transcription-v4.srt`.
12. Persist the fully assembled candidate as `final-v4.mp4`. Assembly mode must not create `final-pre-v4.mp4`, `.final.mp4.v4.tmp`, or modify `final.mp4`.

`--verify-only <mp4>` reruns Step 10 using the expected timing report and performs no writes except an explicitly requested report path. `--write-approval <mp4>` cryptographically binds the candidate and every approval input after Task 7 visual review. `--promote <validated-mp4>` is used only with that approval artifact; it owns final re-verification, backup creation, atomic rename, and rollback.

- [ ] **Step 4: Run tests and verify GREEN**

```bash
node --test audio/assemble-v4.test.mjs
node --test audio/opening-v4.test.mjs audio/assemble-v4.test.mjs
```

Expected: all tests PASS.

- [ ] **Step 5: Commit assembler source**

```bash
git add audio/assemble-v4-lib.mjs audio/assemble-v4.test.mjs audio/assemble-v4.mjs audio/fixtures/fake-ffmpeg-measurement.json
git commit -m "feat: assemble and verify V4 opening video"
```

### Task 7: Assemble, verify, and deliver V4

**Files:**
- Generate: `final-v4.mp4`
- Replace after verification: `final.mp4`
- Generate: `final-pre-v4.mp4`
- Generate: `transcription-v4.srt`
- Generate: `scenes-v4/final-verification.json`
- Generate: `scenes-v4/verification-contact-sheet.jpg`
- Generate: `scenes-v4/visual-checklist.json`
- Generate: `scenes-v4/approval.json`

- [ ] **Step 1: Run the final assembler**

Use the command from Task 6. Expected: `final-v4.mp4` and reports are produced while `final.mp4` and `final-pre-v4.mp4` remain unchanged or absent.

- [ ] **Step 2: Run fresh full verification**

```bash
ffmpeg -v error -xerror -i final-v4.mp4 -map 0 -f null -
ffprobe -v error -count_frames -show_entries \
  format=duration,size:stream=index,codec_type,codec_name,start_time,duration,width,height,r_frame_rate,avg_frame_rate,pix_fmt,color_space,color_transfer,color_primaries,sample_rate,channels,nb_read_frames \
  -of json final-v4.mp4
node --test audio/opening-v4.test.mjs audio/assemble-v4.test.mjs
ffmpeg -hide_banner -i final-v4.mp4 -map 0:a:0 \
  -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json \
  -f null - 2>scenes-v4/final-loudness-scan.log
node audio/assemble-v4.mjs --verify-only final-v4.mp4
```

Expected:

- Video frames: `openingFrames + 4582`.
- Video: 1080×1440, 30fps, H.264, yuv420p, BT.709.
- Audio: AAC, 48kHz, stereo.
- Audio/video duration difference: ≤1 frame.
- Exactly two streams: one video and one audio; both start at zero.
- `r_frame_rate` and `avg_frame_rate` are both `30/1`; `nb_read_frames` equals `openingFrames + 4582`.
- Full decode: exit 0 with no errors.
- The fresh machine-parsed post-AAC scan reports final loudness `-16 ±0.5 LUFS` and true peak ≤`-1.5 dBTP`.
- All tests pass.

- [ ] **Step 3: Verify subtitles and immutable body timing**

Check every one of the 37 body SRT entries differs from V3 by exactly `openingDurationMs`. Confirm the final body subtitle ends at `openingDurationMs + 152165ms`. Compare final duration using authoritative integers—`totalFrames / 30` and `totalSamples / 48000`—rather than equality against a truncated repeating decimal string.

- [ ] **Step 4: Inspect final contact sheet and transition frames**

Generate all captures from staged `final-v4.mp4`, then use `view_image` on:

- A contact sheet spanning the opening.
- A dense capture across frames `openingFrames - 30` through `openingFrames + 60`.
- Scene-001 glasses regression at global frame `openingFrames + 30`.
- Scene-002 zero-vision icon regression at global frame `openingFrames + 373 + 291`.

Reject black frames, clipped text, frozen padding, duplicate introductions, an incoherent opening/body transition, or loss of either previously fixed eye icon.

Record each inspected image path, its SHA-256, the corresponding frame range, and a boolean result in `scenes-v4/visual-checklist.json`. All checklist items must be true.

- [ ] **Step 5: Run the pre-promotion audit**

Confirm:

- MiniMax request/response/subtitle/raw/PCM/timing artifacts exist.
- Claude four stage messages appear exactly once and in order.
- Claude stderr is empty or contains only explained non-failing diagnostics.
- `manifest.json`, `timing-report.json`, video concat/command manifest, `transcription-v4.srt`, `full-timeline-raw.wav`, sample-exact `full-timeline-normalized.wav`, and success/failure verification report exist.
- `final-v3.mp4`, `final-v3-silent.mp4`, all V3 sources, protected root subtitles/audio, and the existing `final.mp4` still match their pre-V4 baselines.
- `final-pre-v4.mp4` is either absent or unchanged; promotion has not happened.
- `final-v4.mp4`, the machine verification report, shifted SRT, and visual checklist all pass.

If any gate fails, leave the previous `final.mp4` in place and report the failing stage, attempt directory, key log, and exact retry command.

- [ ] **Step 6: Bind the approved candidate**

Only after Steps 2–5 pass:

```bash
node audio/assemble-v4.mjs \
  --write-approval final-v4.mp4 \
  --visual-checklist scenes-v4/visual-checklist.json \
  --approval-output scenes-v4/approval.json
```

The approval artifact must bind the SHA-256 values of `final-v4.mp4`, `timing-report.json`, `transcription-v4.srt`, `final-verification.json`, and `visual-checklist.json`, plus an approval timestamp. Every visual checklist item must be true.

- [ ] **Step 7: Back up and atomically promote the bound candidate**

```bash
node audio/assemble-v4.mjs \
  --promote final-v4.mp4 \
  --approval scenes-v4/approval.json
```

Promotion must:

1. Recompute every approval-bound hash and abort on any difference.
2. Rerun the complete read-only `--verify-only` gates immediately before backup.
3. If `final-pre-v4.mp4` is absent, copy or hard-link current `final.mp4` to it and verify equal SHA-256.
4. If `final-pre-v4.mp4` already exists and its checksum differs from current `final.mp4`, abort without replacing anything.
5. Copy `final-v4.mp4` to same-filesystem `.final.mp4.v4.tmp`; verify the temporary checksum equals the approved candidate hash.
6. Atomically rename only `.final.mp4.v4.tmp` to `final.mp4`.
7. Verify `sha256(final.mp4)` equals the approved candidate hash.
8. If the post-rename check fails, copy the verified backup to `.final.mp4.rollback.tmp`, verify it equals the pre-promotion final hash, atomically rename it back to `final.mp4`, confirm byte-for-byte restoration, and only then return failure.

- [ ] **Step 8: Run the post-promotion audit**

Confirm:

- `sha256(final.mp4) === sha256(final-v4.mp4) ===` the approved candidate hash.
- `sha256(final-pre-v4.mp4)` equals the pre-promotion `final.mp4` baseline.
- All `scenes-v3/**`, `final-v3.mp4`, `final-v3-silent.mp4`, root protected subtitles/audio, and V4 audit artifacts remain unchanged.
- No `.final.mp4.v4.tmp` or rollback temp file remains.

- [ ] **Step 9: Final source commit**

Review `git diff` and commit only source/tests/docs. Do not commit `.env`, MiniMax responses, logs, WAVs, MP4s, or generated V4 directories.
