# Complete Production Workflow Template Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable full-production task template while preserving the existing SRT-to-silent-video workflow unchanged.

**Architecture:** `PROMPT-PRODUCTION.md` is a human-facing orchestration contract for one isolated production run. A static shell validator protects its required phases, one-run isolation boundary, secret handling, Claude execution contract, audio provenance, and final QC requirements. The Chinese and English READMEs route users to either the basic or production template.

**Tech Stack:** Markdown, Bash, Git, existing Claude Code/HyperFrames/FFmpeg workflow.

---

### Task 1: Add the production-template contract test

**Files:**
- Create: `auto-test/validate-production-template.sh`
- Test: `auto-test/validate-production-template.sh`

- [ ] **Step 1: Write a failing static validator**

Create a Bash script that fails unless:

- `PROMPT-PRODUCTION.md` exists.
- It describes isolated one-run projects, article/script inputs, MiniMax TTS, real timestamp-derived SRT, sequential Claude rendering, cover-frame validation, licensed BGM/SFX, mixing, atomic promotion, logs, and human listening.
- It prohibits secret exposure and reuse of prior-run assets or approvals.
- It does not describe the task executor as Codex, an agent, or a “主控 agent”.
- Existing `PROMPT.md` and `exampleFolder/run-claude-ai.sh` match `main`.
- Both READMEs mention the two workflow entry points.

- [ ] **Step 2: Run the validator and verify RED**

Run: `bash auto-test/validate-production-template.sh`

Expected: FAIL because `PROMPT-PRODUCTION.md` does not exist.

- [ ] **Step 3: Commit the failing contract**

```bash
git add auto-test/validate-production-template.sh
git commit -m "test: define production template contract"
```

### Task 2: Add the full production task template

**Files:**
- Create: `PROMPT-PRODUCTION.md`
- Test: `auto-test/validate-production-template.sh`

- [ ] **Step 1: Write the human-facing task instructions**

Implement the nine-stage workflow from the design:

1. Isolated project and input freeze.
2. Input audit and production specification.
3. Spoken-script and opening revision.
4. MiniMax TTS audition and timestamp-derived subtitles.
5. Semantic scene splitting and sequential Claude execution.
6. Frame-zero cover contract.
7. Video normalization and silent assembly.
8. Licensed BGM/SFX selection and voice-first mixing.
9. Machine QC, human audition, approval, backup, and atomic `final.mp4` delivery.

Keep all work configurable per production. Explicitly preserve the existing single-scene Claude script contract and prohibit logging secrets.

- [ ] **Step 2: Run the validator**

Run: `bash auto-test/validate-production-template.sh`

Expected: still FAIL because the READMEs do not yet expose both templates.

- [ ] **Step 3: Commit the production template**

```bash
git add PROMPT-PRODUCTION.md
git commit -m "feat: add complete video production prompt"
```

### Task 3: Document both entry points

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Test: `auto-test/validate-production-template.sh`

- [ ] **Step 1: Add a workflow-selection section**

Document:

- `PROMPT.md` for finalized SRT and silent MG output.
- `PROMPT-PRODUCTION.md` for article/script through narrated, scored final video.
- Every production must run in a new clean directory or dedicated worktree.
- Example commands for each entry point.
- Production outputs and the publication-time human audition requirement.

- [ ] **Step 2: Run the validator and verify GREEN**

Run: `bash auto-test/validate-production-template.sh`

Expected: PASS.

- [ ] **Step 3: Run regression checks**

Run:

```bash
bash -n auto-test/run.sh auto-test/validate.sh \
  auto-test/validate-production-template.sh exampleFolder/run-claude-ai.sh
git diff --check
git diff --exit-code main -- PROMPT.md exampleFolder/run-claude-ai.sh \
  auto-test/run.sh auto-test/validate.sh
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit documentation**

```bash
git add README.md README.en.md
git commit -m "docs: explain basic and production workflows"
```

### Task 4: Final verification

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run all static checks from a clean shell**

Run:

```bash
bash auto-test/validate-production-template.sh
bash -n auto-test/*.sh exampleFolder/run-claude-ai.sh
git diff --check main...HEAD
git status --short
```

Expected: validator passes, shell syntax passes, no whitespace errors, and only intended files differ from `main`.

- [ ] **Step 2: Review the final branch diff**

Run:

```bash
git diff --stat main...HEAD
git diff main...HEAD -- PROMPT-PRODUCTION.md README.md README.en.md \
  auto-test/validate-production-template.sh
```

Expected: no project-specific script, audio, scene, log, credential, or rendered media is present.
