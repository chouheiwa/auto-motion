# “Skill 不就是 Prompt 吗？”Video Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a fully evidenced 1080×1440, 30fps Douyin MG explainer from `文章.md`, ending with an atomically delivered `final.mp4`.

**Architecture:** Freeze each stage before the next one consumes it: immutable input hashes → approved spoken script → approved MiniMax voice → real-audio timeline → frame-exact scene plan → sequential scene renders → normalized silent master → licensed audio stems → machine-bound approval → atomic final delivery. Small Node.js tools own deterministic JSON, hashing, timing, and QC; FFmpeg owns media normalization, mixing, and decoding checks; `run-scene.sh` remains the per-scene renderer contract.

**Tech Stack:** Node.js 22 built-ins and `node:test`, Bash, MiniMax T2A v2, FFmpeg/FFprobe 7, jq, HyperFrames, Git.

---

## File map

### Production control and tests

- Create `production/tools/lib.mjs` — stable JSON, SHA-256, SRT time, frame, sample, and FFprobe helpers.
- Create `production/tools/inventory.mjs` — generate immutable input inventory and manifest.
- Create `production/tools/validate-script.mjs` — script length, opening, and protected-term checks.
- Create `production/tools/minimax-tts.mjs` — safe voice listing, audition, and formal TTS calls.
- Create `production/tools/build-timeline.mjs` — rebuild production SRT and frame-exact timing report from actual TTS evidence.
- Create `production/tools/build-scenes.mjs` — validate scene plan and scaffold scene directories without changing the renderer contract.
- Create `production/tools/render-scenes.mjs` — invoke one `run-scene.sh` at a time and preserve attempt evidence.
- Create `production/tools/normalize-scenes.mjs` — probe, normalize, and concatenate silent scene outputs.
- Create `production/tools/build-audio.mjs` — create sample-exact stems, cue placement, ducking, loudness normalization, and candidate MP4.
- Create `production/tools/qc-and-promote.mjs` — machine QC, approval binding, final recheck, and atomic promotion.
- Create `production/tests/*.test.mjs` — focused tests for every deterministic tool.

### Required production artifacts

- Create `production/baseline.json`
- Create `production/input-inventory.md`
- Create `production/input-manifest.json`
- Create `production/production-config.json`
- Create `production/script-final.md`
- Create `production/script-change-log.md`
- Create `production/tts/**`
- Create root `transcription-production.srt`
- Create `production/timing-report.json`
- Create `production/scene-plan.json`
- Create `production/scene-plan.md`
- Create `scenes/scene-*/**`
- Create `production/visual-qc/**`
- Create `production/silent-master.mp4`
- Create `production/audio/**`
- Create `production/approval.json`
- Create root `final.mp4` only after approval gates pass.

## Global invariants

- Never modify or delete `文章.md`, root `transcription.srt`, `.qoder/`, or any other pre-existing user file.
- Before every stage, verify current input hashes match `production/input-manifest.json`.
- Verify `.env` is ignored with `git check-ignore -q .env`.
- Never print or persist credential values, Authorization headers, or authenticated URLs.
- All time authority is integer frames at 30fps; all audio authority is integer samples at 48kHz per channel.
- Only one renderer process may run at a time.
- Every failed render gets a new attempt directory; prior logs and MP4s are immutable evidence.
- No root `final.mp4` is created until machine approval passes.

### Task 1: Freeze project baseline and build deterministic helper primitives

**Files:**
- Create: `production/baseline.json`
- Create: `production/tools/lib.mjs`
- Create: `production/tests/lib.test.mjs`

- [ ] **Step 1: Recheck the one-project boundary**

Run:

```bash
test ! -e production
test ! -e scenes
test ! -e final.mp4
git branch --show-current
git rev-parse HEAD
git status --short
git check-ignore -q .env
```

Expected: no production outputs exist; `.env` is ignored. If any output exists unexpectedly, stop before creating files.

- [ ] **Step 2: Create the production directories**

Run:

```bash
mkdir -p production/tools production/tests production/tts production/audio production/visual-qc
```

Expected: only new project-specific directories are created.

- [ ] **Step 3: Write the failing helper tests**

Tests must cover:

```js
assert.equal(secondsToFrames("2.833", 30), 85);
assert.equal(framesToSeconds(85, 30), "2.833");
assert.equal(framesToSamples(85, 30, 48000), 136000);
assert.equal(formatSrtTime(1501), "00:00:01,501");
assert.match(sha256File("文章.md"), /^[0-9a-f]{64}$/);
```

- [ ] **Step 4: Run tests and verify failure**

Run:

```bash
node --test production/tests/lib.test.mjs
```

Expected: FAIL because `production/tools/lib.mjs` does not yet export the helpers.

- [ ] **Step 5: Implement the minimal helper library**

Use only Node built-ins. Reject non-integer frame/sample results, negative time, malformed SRT timestamps, missing files, and non-finite numbers. JSON writes must use a same-directory temporary file followed by `rename`.

- [ ] **Step 6: Record baseline**

`production/baseline.json` must contain branch, commit before production artifacts, ISO timestamp, timezone, full `git status --short`, and an explicit list of protected pre-existing paths.

- [ ] **Step 7: Verify**

Run:

```bash
node --test production/tests/lib.test.mjs
node -e 'JSON.parse(require("fs").readFileSync("production/baseline.json","utf8"))'
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add production/baseline.json production/tools/lib.mjs production/tests/lib.test.mjs
git commit -m "build: freeze video production baseline"
```

### Task 2: Inventory and cryptographically freeze original inputs

**Files:**
- Create: `production/tools/inventory.mjs`
- Create: `production/tests/inventory.test.mjs`
- Create: `production/input-inventory.md`
- Create: `production/input-manifest.json`
- Create: `production/production-config.json`

- [ ] **Step 1: Write failing inventory tests**

Use a temporary fixture directory. Tests must prove that:

- relevant extensions are classified;
- `.env`, `.git`, `.superpowers`, `production`, and `scenes` are excluded;
- path, byte size, and SHA-256 are stable;
- the existing root SRT is labeled `unrelated_reference`, never `timeline_authority`;
- a changed input hash causes a nonzero exit.

- [ ] **Step 2: Run and verify failure**

```bash
node --test production/tests/inventory.test.mjs
```

Expected: FAIL because the inventory tool does not exist.

- [ ] **Step 3: Implement and run inventory**

Run:

```bash
node production/tools/inventory.mjs --root . --write
```

Expected inventory includes `文章.md` and root `transcription.srt`; it lists articles, Markdown, TXT, SRT, audio, image, video, and visual references. Generated assets and secrets are excluded.

- [ ] **Step 4: Write production configuration**

`production/production-config.json` must include:

```json
{
  "project_id": "2026-07-28-skill-vs-prompt",
  "destination": "douyin",
  "width": 1080,
  "height": 1440,
  "fps": 30,
  "script_status": "editable_until_script_approval",
  "reference_srt_role": "unrelated_reference",
  "voice_mode": "minimax_tts",
  "voice_direction": "Chinese male, calm, sharp technical commentary",
  "opening_required": true,
  "cover_title_lines": ["Skill 不就是", "Prompt 吗？"],
  "cover_stable_frames": 18,
  "visual_direction": "clear system blueprint",
  "bgm_direction": "restrained low-density electronic ambient",
  "sfx_direction": "hook, four layer markers, risk turn, conclusion only"
}
```

- [ ] **Step 5: Verify and commit**

```bash
node --test production/tests/inventory.test.mjs
node production/tools/inventory.mjs --root . --verify
git diff --check
git add production/input-inventory.md production/input-manifest.json production/production-config.json production/tools/inventory.mjs production/tests/inventory.test.mjs
git commit -m "build: freeze source inputs and production config"
```

### Task 3: Produce and validate the spoken script

**Files:**
- Create: `production/script-final.md`
- Create: `production/script-change-log.md`
- Create: `production/tools/validate-script.mjs`
- Create: `production/tests/validate-script.test.mjs`

- [ ] **Step 1: Draft the final script**

Target 750–850 Chinese characters and approximately 160 seconds:

1. 12–15 second conflict opening.
2. Four transformations: on-demand loading, deterministic scripts, conceptual boundary, executable methodology.
3. Evidence and practical value.
4. Discovery/security/overpackaging risks.
5. “质变不在原料，而在抽象” conclusion.

Do not add facts not present in `文章.md`. Keep `Skill`, `Prompt`, `SKILL.md`, `Claude Code`, `MCP`, `RAG`, `Git`, `API`, `VS Code`, `GitHub Copilot`, and `OpenAI Codex CLI` intact.

- [ ] **Step 2: Record every material edit**

`script-change-log.md` must separate:

- deletions for length;
- reordered arguments;
- oral-language rewrites;
- added 12–15 second opening;
- removed links/dates/numbers;
- facts retained verbatim;
- pronunciation and no-split terms.

- [ ] **Step 3: Write failing validator tests**

Tests must reject a missing opening, out-of-range character count, missing conclusion, broken protected phrase, or unlisted factual addition.

- [ ] **Step 4: Implement and verify**

```bash
node --test production/tests/validate-script.test.mjs
node production/tools/validate-script.mjs --script production/script-final.md --source 文章.md --changelog production/script-change-log.md
```

Expected: PASS and a printed estimated duration range.

- [ ] **Step 5: Script approval gate**

Report to the user:

- estimated duration;
- full opening;
- major changes;
- protected terms.

Stop. Do not call MiniMax for the full script until the user explicitly approves.

- [ ] **Step 6: Commit approved script**

```bash
git add production/script-final.md production/script-change-log.md production/tools/validate-script.mjs production/tests/validate-script.test.mjs
git commit -m "content: approve final skill explainer script"
```

### Task 4: Build a secret-safe MiniMax audition client

**Files:**
- Create: `production/tools/minimax-tts.mjs`
- Create: `production/tests/minimax-tts.test.mjs`
- Create: `production/tts/audition-text.txt`
- Generate: `production/tts/voices.redacted.json`
- Generate: `production/tts/auditions/<voice-id-safe>/**`

- [ ] **Step 1: Use the current official API contract**

Implement against:

- `POST https://api.minimax.io/v1/get_voice`
- `POST https://api.minimax.io/v1/t2a_v2`

The synchronous T2A request uses `stream:false`, `language_boost:"Chinese"`, `subtitle_enable:true`, `subtitle_type:"word"`, and `output_format:"hex"` for local-only evidence. Prefer `MINIMAX_TTS_MODEL`; if absent, stop and ask rather than silently choosing permanently.

- [ ] **Step 2: Write failing mocked-fetch tests**

Tests must prove:

- `.env` is loaded without logging values;
- the API key appears only in the in-memory Authorization header;
- group ID is never added to URLs unless current official docs and the configured account require it;
- logged request JSON is redacted;
- nonzero `base_resp.status_code`, null `data`, malformed hex, missing subtitle data, and HTTP errors fail closed;
- output filenames sanitize voice IDs;
- no authenticated URL is persisted.

- [ ] **Step 3: Run and verify failure**

```bash
node --test production/tests/minimax-tts.test.mjs
```

- [ ] **Step 4: Implement and verify the client**

```bash
git check-ignore -q .env
node production/tools/minimax-tts.mjs list-voices --direction "Chinese male calm technical commentary"
```

Expected: 2–3 compatible candidates recorded in redacted form.

- [ ] **Step 5: Generate auditions**

Use one approved 10–20 second representative paragraph and identical parameters for all voices:

```bash
node production/tools/minimax-tts.mjs audition \
  --text production/tts/audition-text.txt \
  --voices "<voice-a>,<voice-b>,<voice-c>" \
  --speed 1.0 \
  --emotion calm
```

Expected per candidate: request JSON without secrets, redacted response JSON, raw audio, decoded WAV, subtitle/timestamp evidence, FFprobe JSON, and SHA-256 report.

- [ ] **Step 6: Voice approval gate**

Deliver the 2–3 audition files and parameter table. Stop until the user selects voice ID, speed, and emotion.

- [ ] **Step 7: Commit code and non-binary evidence metadata**

Do not commit secrets or authenticated URLs. Commit binary audition evidence only if repository policy permits; otherwise leave it project-local and record hashes.

### Task 5: Generate, audit, and approve formal TTS

**Files:**
- Generate: `production/tts/formal/segments/**`
- Generate: `production/tts/formal/tts-report.json`
- Generate: `production/audio/voice-raw.wav`
- Generate: `production/audio/voice-approved.wav`

- [ ] **Step 1: Freeze TTS parameters**

Record selected voice ID, model, speed, volume, pitch, emotion, language, pronunciation dictionary, and approved script SHA-256. Use inline Pinyin/IPA or `pronunciation_dict` for terms that the audition proves need help; do not guess unnecessary pronunciations.

- [ ] **Step 2: Generate by semantic paragraph**

```bash
node production/tools/minimax-tts.mjs formal \
  --script production/script-final.md \
  --config production/production-config.json \
  --out production/tts/formal
```

Each segment must preserve request, redacted response, raw audio, returned timestamps, and hash. Do not split by future subtitle lines.

- [ ] **Step 3: Assemble at native speed**

Decode segments, preserve natural paragraph pauses, concatenate without time-stretching, and convert to 48kHz stereo PCM as `production/audio/voice-approved.wav`. Record exact native duration and samples. This file is immutable after the full narration is approved.

- [ ] **Step 4: Pronunciation and sentence audit**

Check every protected term, subject–predicate, verb–object, condition–conclusion, number, abbreviation, long-sentence breath, and sentence-ending hold. Regenerate only affected segments after punctuation or pronunciation-control fixes.

- [ ] **Step 5: Voice approval gate**

Deliver `production/audio/voice-approved.wav`, exact parameters, audit results, and unresolved doubts. Stop until the complete narration is approved.

### Task 6: Rebuild the SRT and freeze the integer-frame timeline

**Files:**
- Create: `production/tools/build-timeline.mjs`
- Create: `production/tests/build-timeline.test.mjs`
- Create: `transcription-production.srt`
- Create: `production/timing-report.json`

- [ ] **Step 1: Write failing timeline tests**

Fixtures must cover service timestamps across multiple TTS segments, semantic resegmentation without inventing timings, millisecond SRT output, preserved gaps, 30fps end padding, 48kHz sample totals, and the 41.566-second reference SRT delta.

- [ ] **Step 2: Implement service-evidence mapping**

Map final subtitle text only onto ordered MiniMax word/sentence timestamps. A timestamp without service evidence is forbidden. Manual edits may merge or split readable subtitle units only when their boundaries are backed by adjacent returned timestamps.

- [ ] **Step 3: Determine program endpoint**

Choose an integer `total_frames` that includes narration, breathing, visual holds, and ending display. Compute:

```text
duration_seconds = total_frames / 30
samples_per_channel = total_frames * 48000 / 30
```

At 30fps and 48kHz, every frame is exactly 1600 samples.

- [ ] **Step 4: Generate and verify**

```bash
node --test production/tests/build-timeline.test.mjs
node production/tools/build-timeline.mjs \
  --tts production/tts/formal/tts-report.json \
  --voice production/audio/voice-approved.wav \
  --reference transcription.srt \
  --srt transcription-production.srt \
  --report production/timing-report.json
```

Expected: every subtitle, gap, total frame, duration, sample rate, target sample count, and reference-duration difference is recorded.

- [ ] **Step 5: Commit the frozen timeline**

```bash
git add transcription-production.srt production/timing-report.json production/tools/build-timeline.mjs production/tests/build-timeline.test.mjs
git commit -m "media: freeze narration timeline and subtitles"
```

### Task 7: Plan scenes and scaffold exact renderer contracts

**Files:**
- Create: `production/scene-plan.json`
- Create: `production/scene-plan.md`
- Create: `production/tools/build-scenes.mjs`
- Create: `production/tests/build-scenes.test.mjs`
- Create: `scenes/scene-*/.claude/**`
- Create: `scenes/scene-*/run-scene.sh`
- Create: `scenes/scene-*/transcription.srt`

- [ ] **Step 1: Author 10–12 semantic scenes**

Each entry contains scene ID, start frame, end-exclusive frame, duration frames, three-decimal duration seconds, subtitle indices, scene text, semantic purpose, visual direction, and cover obligations for scene 001.

- [ ] **Step 2: Write failing plan/contract tests**

Tests must enforce:

- scene 001 starts at frame 0;
- final scene ends at `timing-report.total_frames`;
- no gap, overlap, or negative duration;
- frame totals match exactly;
- displayed seconds differ from frame duration by at most 0.001;
- scene 001 protects the exact two-line title and 18 stable frames;
- every scene copy has the full production SRT named `transcription.srt`;
- `run-scene.sh` preserves its renderer dispatch, three log filenames, `[[USER_MESSAGE]]` filter, and four required stage strings.

- [ ] **Step 3: Implement scaffold**

For each scene, copy from `exampleFolder`, then fill only:

- `SCENE_ID`
- `SCENE_DURATION_SECONDS`
- `OUTPUT_FILE`
- `FULL_TRANSCRIPT_PATH`
- `SCENE_TEXT`
- creative prose inside `PROMPT`

Prompt direction: clear system blueprint, mist white, engineering blue, circles, nodes, connections, layered diagrams, restrained motion. Do not specify the internal animation choreography.

- [ ] **Step 4: Verify**

```bash
node --test production/tests/build-scenes.test.mjs
node production/tools/build-scenes.mjs --verify
```

Expected: exact frame coverage and unchanged execution contract.

- [ ] **Step 5: Timeline freeze gate**

Report total frames, exact duration, scene table, and frame-sum proof. Stop for approval before paid/long renderer execution.

### Task 8: Render every scene sequentially and preserve failure evidence

**Files:**
- Create: `production/tools/render-scenes.mjs`
- Create: `production/tests/render-scenes.test.mjs`
- Generate: `scenes/scene-*/attempts/attempt-*/**`

- [ ] **Step 1: Write failing scheduler tests**

Mock child processes and verify maximum concurrency is 1, numeric scene order, nonzero exit handling, attempt numbering, no log overwrite, and idle diagnosis using log mtime, file mtime, and process checks.

- [ ] **Step 2: Implement scheduler**

The tool runs exactly one scene at a time. It mirrors only `[[USER_MESSAGE]]` lines, records PID and timestamps, and copies the final attempt’s MP4 to the scene root only after exit code 0.

- [ ] **Step 3: Execute**

```bash
node production/tools/render-scenes.mjs --plan production/scene-plan.json --renderer "${RENDERER:-claude}"
```

Do not launch another scene while HyperFrames, FFmpeg, Chromium, Node render, or the scene script is still active.

- [ ] **Step 4: Record failures**

For every failed scene, add scene ID, attempt, failure stage, key log path, exit code, and recommended retry to `production/render-failures.json`. Retry only in a new attempt directory.

- [ ] **Step 5: Verify render evidence**

Every successful scene must have original MP4, source project, stream JSONL, stderr log, user log, and the four stage messages.

### Task 9: Visual QC, scene normalization, and silent master

**Files:**
- Create: `production/visual-qc/checklist.json`
- Generate: `production/visual-qc/*.png`
- Create: `production/tools/normalize-scenes.mjs`
- Create: `production/tests/normalize-scenes.test.mjs`
- Generate: `scenes/scene-*/normalized.mp4` when needed
- Generate: `production/silent-master.mp4`

- [ ] **Step 1: Probe every scene**

Validate width 1080, height 1440, CFR 30fps, H.264, `yuv420p`, unified color metadata, exact planned frames, no audio stream, and full decode.

- [ ] **Step 2: Normalize only nonconforming scenes**

Keep original MP4. Produce deterministic H.264 `yuv420p` normalized copies with exact planned frames and no audio.

- [ ] **Step 3: Extract visual evidence**

For scene 001 extract frame 0, frame 17, transition-start frame, and one transition-in-progress frame. For all scene boundaries extract end/start representatives. Inspect title geometry, safe area, contrast, circles, lines, icons, and semantic correctness.

- [ ] **Step 4: Fix only affected scenes**

Any visual failure returns only that scene to a new render attempt. Do not change approved TTS or unrelated scenes.

- [ ] **Step 5: Visual approval gate**

Deliver the frame-0, frame-17, transition-start, transition-in-progress, boundary screenshots, and `production/visual-qc/checklist.json`. Stop until the visual QC evidence is approved. If changes are requested, rerender and repeat this gate before concatenation.

- [ ] **Step 6: Concatenate and verify**

```bash
node production/tools/normalize-scenes.mjs \
  --plan production/scene-plan.json \
  --out production/silent-master.mp4
ffmpeg -v error -xerror -i production/silent-master.mp4 -map 0 -f null -
```

Expected: silent master frame count equals `timing-report.total_frames`, with zero audio streams.

### Task 10: Resolve licensed BGM/SFX and build the frame-based cue sheet

**Files:**
- Create: `production/audio/asset-ledger.json`
- Create: `production/audio/cue-sheet.json`
- Create: `production/audio/licenses/**`
- Generate: `production/audio/source/**`
- Generate: `production/audio/work/**`

- [ ] **Step 1: Use the media-use audio workflow**

Before fetching assets, read `/media-use` audio and resolve references. Search for:

- one restrained low-density electronic ambient BGM;
- a maximum of four SFX families for hook, layer markers, risk turn, and conclusion.

Prefer bundled or clearly licensed catalog assets. Do not use an asset with unclear licensing.

- [ ] **Step 2: Freeze the ledger before download/use**

Record local name, purpose, source URL, author, asset ID, license type, evidence path, retrieval time, SHA-256, attribution requirement, and proposed credit text.

- [ ] **Step 3: Decode source and preserve both forms**

Keep original download and decode a 48kHz WAV working copy. Hash both.

- [ ] **Step 4: Author integer-frame cues**

Each cue includes asset ID, start frame, duration frames, start sample, duration samples, gain, fade-in frames, fade-out frames, and purpose. Reject cues beyond `total_frames` and cap concurrent SFX to avoid crowding.

- [ ] **Step 5: Verify**

Run a cue validator that proves every frame-to-sample conversion is exact and every asset hash matches the ledger.

### Task 11: Build sample-exact stems, ducked premaster, and candidate MP4

**Files:**
- Create: `production/tools/build-audio.mjs`
- Create: `production/tests/build-audio.test.mjs`
- Generate: `production/audio/voice.wav`
- Generate: `production/audio/music.wav`
- Generate: `production/audio/sfx.wav`
- Generate: `production/audio/premaster.wav`
- Generate: `production/audio/candidate.mp4`
- Create: `production/audio/sound-checklist.json`

- [ ] **Step 1: Write failing filter-graph and sample tests**

Tests must verify:

- every stem is exactly `timing-report.samples_per_channel`;
- narration is never time-stretched;
- BGM fade-in/out stays within program frames;
- ducking is active only from actual voice regions;
- cue placement uses integer samples;
- first-pass and second-pass loudnorm parameters are separate;
- AAC decode is trimmed/padded to the exact program endpoint without changing video frames.

- [ ] **Step 2: Build stems**

- `voice.wav`: a program-length stem derived from immutable `voice-approved.wav`, placed at its frozen start and padded with silence.
- `music.wav`: one continuous restrained bed with natural fades and voice-aware gain reduction.
- `sfx.wav`: only approved frame cues.
- `premaster.wav`: summed 48kHz stereo PCM before AAC.

- [ ] **Step 3: Two-pass loudness normalization**

First pass measures. Second pass supplies measured input I, LRA, TP, threshold, and offset. Target approximately `I=-16`, `TP=-1`, `LRA=11`; fail if the final scan exceeds -1 dBTP.

- [ ] **Step 4: Mux candidate**

Copy the silent-master video bitstream when valid and encode AAC audio. Decode the candidate’s AAC to PCM and verify the real per-channel sample endpoint, not just container duration.

- [ ] **Step 5: Verify**

```bash
node --test production/tests/build-audio.test.mjs
node production/tools/build-audio.mjs --build
ffmpeg -v error -xerror -i production/audio/candidate.mp4 -map 0 -f null -
```

Expected: exact video frames, correct audio endpoint, and complete decode.

- [ ] **Step 6: Sound review gate**

Create and populate `production/audio/sound-checklist.json` with candidate SHA-256, stem SHA-256 values, measured loudness/true peak, cue-boundary checks, balance/timing review fields, and physical-listening fields initialized to `not_executed`.

Deliver `production/audio/candidate.mp4`, the stem files, measured loudness/true peak, cue summary, and current `sound-checklist.json`. Stop until the user approves the candidate’s balance and timing. Any requested mix change must produce a newly hashed candidate and repeat this gate before machine approval.

### Task 12: Machine QC, human-listening record, approval, and atomic delivery

**Files:**
- Create: `production/tools/qc-and-promote.mjs`
- Create: `production/tests/qc-and-promote.test.mjs`
- Create: `production/audio/machine-qc.json`
- Modify: `production/audio/sound-checklist.json`
- Create: `production/approval.json`
- Generate: root `final.mp4`

- [ ] **Step 1: Write failing promotion tests**

Use temporary files to prove:

- any failed machine check blocks approval;
- changed input/candidate/report hash blocks promotion;
- non-black readable frame 0 is required;
- subtitle/scene/cue overflow blocks promotion;
- missing earphone/phone listening produces `pending_manual_listening`, not a false pass;
- an existing final is backed up with a timestamp;
- same-filesystem temporary copy plus rename is atomic;
- post-rename verification failure restores the backup.

- [ ] **Step 2: Run complete machine QC**

Check:

- 1080×1440, 30fps CFR, H.264, `yuv420p`;
- exact total video frames;
- 48kHz stereo and exact decoded endpoint;
- full audio/video decode;
- readable non-black frame 0;
- SRT, scene, and cue bounds;
- loudness and true peak;
- every required artifact exists;
- every bound SHA-256 still matches.

- [ ] **Step 3: Record human listening honestly**

Set earphone and phone-speaker full listen to `not_executed` unless physically performed by the user. Include checks for pauses, pronunciation, clarity, masking, abrupt SFX, clipping, clicks, and hard ending.

- [ ] **Step 4: Write approval**

`production/approval.json` must separate:

```json
{
  "machine_approval": "passed",
  "release_approval": "pending_manual_listening"
}
```

It binds the SHA-256 of input manifest, production config, script, SRT, timing report, scene plan, silent master, stems, cue sheet, asset ledger, candidate, visual QC, sound checklist, and machine QC.

The pre-promotion record also contains `expected_final_sha256`, equal to the already approved candidate bytes that will be copied unchanged. After promotion and post-rename verification, the tool atomically adds `final_delivery.sha256`, absolute path, verification timestamp, and decode/probe status to the same approval file.

- [ ] **Step 5: Promote atomically**

```bash
node production/tools/qc-and-promote.mjs \
  --candidate production/audio/candidate.mp4 \
  --approval production/approval.json \
  --promote final.mp4
```

If `final.mp4` exists, move it to a timestamped backup first. Copy candidate to a same-directory temporary file, fsync if supported, then rename. Recompute SHA-256 and rerun probe/decode after rename.

After the post-rename checks pass, atomically update `production/approval.json` with the delivered `final.mp4` SHA-256 and require it to equal `expected_final_sha256`. A mismatch is a promotion failure and triggers rollback.

- [ ] **Step 6: Final verification**

```bash
ffprobe -v error -show_streams -show_format -of json final.mp4
ffmpeg -v error -xerror -i final.mp4 -map 0 -f null -
shasum -a 256 final.mp4
node -e 'const a=JSON.parse(require("fs").readFileSync("production/approval.json","utf8")); if(a.final_delivery?.sha256!==a.expected_final_sha256) process.exit(1)'
git diff --check
npm audit --omit=dev
```

If there is no `package.json`, record `npm audit` as not applicable rather than inventing a pass.

- [ ] **Step 7: Final report**

Report final absolute path, duration, dimensions, frame rate, frame count, audio sample rate/channels, decoded endpoint, SHA-256, all QC statuses, failed-scene evidence, required attribution, and the remaining earphone/phone listening tasks.

## Implementation execution order

The seven user-visible gates remain mandatory:

1. Script approval.
2. Voice audition approval.
3. Full narration approval.
4. Timeline and scene-plan approval.
5. Visual QC.
6. Sound candidate review.
7. Machine approval and atomic delivery.

Never compress these gates into a single silent autonomous run.
