# 0.7.0 Douyin usage and recovery

Local candidate; production remains 0.6.2. [Acceptance and limits](research/v0.7.0-acceptance-2026-10-04.md). Do not run `deploy-local.mjs` under the current authorization.

After separately authorized deployment, the existing explicit commands are:

```text
小婕 wk 记录：https://v.douyin.com/<single-video>/
小婕 wk 记录：原画质 https://v.douyin.com/<single-video>/
小婕收集：<Douyin share text containing a single-video URL>
小婕 wk 状态：<job-id>
小婕 wk 继续：<job-id>
小婕 wk 确认视频：<job-id> <asset-id> <exact-fingerprint>
小婕 wk 查询：<phrase from transcript>
```

Agent tools retain `wiki_record`/`wiki_resume` original-message-only authorization. Mode is frozen from the authenticated source message. Configure `asrBinary` to an absolute pinned codex-asr 0.1.2 executable; missing/backend-changed/expired auth/quota enters waiting without API fallback. Installation candidate metadata/hash: `upstream-codex-asr.json`. Existing Python requirements include FFmpeg via imageio-ffmpeg. This source work does not modify production configuration.

The authorized real sample can be checked again from the implementation worktree, using the already downloaded local binary:

```sh
cd /Users/mac/.codex/worktrees/wiki-v03/Personal-Wiki
node scripts/manual/douyin-acceptance.mjs
```

This restricted runner permits only the specified sample and fixed Vault, checks nashsu project/publication identity, uses isolated `.local/v070/acceptance` state, writes sanitized result/stage evidence and sends no messages. It does not claim real Feishu acceptance. Current outcome is public metadata unavailable; it does not read private browser cookies. Repeating this command retries metadata but reuses any verified media/model/publication state.

Artifacts after successful processing:

- Source main reading page: returned `source`, containing the full machine transcript, source card and media links.
- Media: returned `video.mediaPublication.supplement`, with independently playable full audio and the selected video version. Formal paths are `raw/assets/douyin-<stable-id>/<mode>/video.mp4` and `audio.m4a`.
- Original machine text/responses/segment plan: immutable source asset bundle referenced by the source, separate from summaries and any human corrections.

Failure recovery:

1. Check status and stage. Saved video/audio with pending transcript is partial completion, not complete knowledge.
2. For public platform login/captcha failure, wait for an authorized supported access path; this version has no Douyin private-cookie/login reuse. No silent workaround or paid service.
3. For unknown cloud results, “继续” is an explicit new authorization to retry the affected segment with possible duplicate quota use. A command is consumed once per segment. Do not blindly replay a crashed cloud request.
4. Restore auth/available capacity before continuing. Successful segments and published state are verified/reused; five calls per segment remain the limit. Exhaustion needs operator diagnosis/a new explicit processing version, not an automatic budget reset.
5. For publication/search mismatch, inspect existing published state and manual changes first. No overwrite/re-download/re-transcribe/cleanup just to hide a mismatch.
6. Cleanup is last, after full API/hash/search verification. Cleanup failure reports archive complete but temporary cleanup pending; continue reconciles archived state first. Only the frozen download source/chunk entries are eligible. Source hashes/encoding records/responses remain. An already-cleaned download source cannot be restored from compressed media; restore formal media/audio/text/provenance using their hashes.

No blanket deletion command is provided. Preserve state and valid formal files during failure recovery. Do not edit raw machine outputs in place; human corrections belong in separate protected documents.
