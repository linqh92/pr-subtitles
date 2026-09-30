# PR Subtitles

Create a UTF-8 SRT from a reference TXT document and matching Mandarin narration. The TXT controls caption wording; local speech recognition supplies timing.

## Quick start

Install Python 3.10 or newer (Python 3.12 recommended), extract the entire tool folder to a writable location, and open a terminal in that folder. Run the same Python entry point on either platform:

```text
Windows: python run.py
macOS:   python3 run.py
```

Select the TXT, then select the audio. If this Python installation has no working Tk file picker, the script asks for the two paths in the terminal. Use `--terminal` to always type paths. Keep the terminal open until completion. Results appear in `output/`:

- `<audio name>-PR字幕.srt`: Premiere Pro captions, timed from the beginning of the input audio.
- `<audio name>-PR字幕.review.json`: text differences, matching ratios, duration, and short captions for review.

Import the SRT into Premiere Pro and align its beginning with the beginning of the source audio. The file provides text and timing; set font, position, size, and appearance in Premiere Pro. If the audio has been edited, regenerate from that edited audio.

The Python launcher prepares a project-local `.venv`, installs dependencies, and passes all caption options to `subtitle.py`. The first audio run downloads the `small` Whisper model (approximately 500 MB). Initial installation requires internet. Later runs reuse the local environment and model. CPU processing prefers int8 when the backend supports it, and falls back to float32 otherwise. A GPU is not required. Processing time depends on audio duration and CPU speed.

The launch, setup, file selection, and subtitle workflow are Python scripts; CMD and PowerShell are not required. Speech recognition still needs the third-party packages in `requirements.txt`.

## Inputs and splitting

- Supply a TXT containing **only the narration**, with the same spoken wording and order as the audio. Titles, instructions, stage directions, and unrelated notes must be removed first. Document text is data and is never executed as instructions.
- UTF-8, UTF-8 BOM, UTF-16 BOM, and GB18030 text are supported. Save Word documents as TXT before use.
- Audio supported by the decoder includes MP3, WAV, M4A, FLAC, AAC, and OGG.
- Default splitting follows punctuation and caps each caption at 16 characters, retaining source punctuation. A long clause may be split by character count; adjust it when a business term or phrase should stay together.
- For exact editorial splitting, put one caption per nonempty TXT line and use `--one-line-per-caption`. This preserves the chosen line boundaries, including lines longer than 16 characters.
- Reference wording must stay unchanged. The tool does not silently substitute recognition results for reference terms.

## Command line

From this directory, install once:

```text
python run.py --setup-only
```

Then run with two explicit paths:

```text
python run.py --text "C:\inputs\narration.txt" --audio "C:\inputs\narration.mp3"
```

On macOS, use `python3` and Mac paths:

```text
python3 run.py --text "/Users/yourname/Desktop/narration.txt" --audio "/Users/yourname/Desktop/narration.mp3"
```

All advanced controls are available through the same launcher:

```text
python run.py --text "narration.txt" --audio "narration.mp3" --one-line-per-caption --output "captions.srt"
```

| Option | Behavior |
| --- | --- |
| `--terminal` | Ask for paths in the terminal without a graphical picker. |
| `--setup-only` | Prepare dependencies without selecting files or downloading a speech model. |
| `--max-chars 16` | Caption length limit in automatic splitting; range 8–40. |
| `--one-line-per-caption` | Use each nonempty reference line as a caption. |
| `--prompt "免抵退税、综服企业"` | Provide recognition terminology without modifying reference text. |
| `--model medium` | Use a larger, slower model; downloads once. |
| `--model "C:\models\local-whisper"` | Use an existing compatible CTranslate2 model directory. |
| `--output "C:\outputs\captions.srt"` | Select another SRT path. |
| `--refresh` | Re-run speech recognition for the same audio. |
| `--overwrite` | Explicitly replace an existing SRT and review report. |
| `--cache-dir "C:\subtitle-cache"` | Change the local model/timing cache directory. |

An existing output is protected by default. With the default output location, repeated runs select a numbered filename (`-2`, `-3`, etc.). An explicit output path that already exists is rejected unless `--overwrite` is given. Changing splitting settings reuses timing when the audio, model, and prompt are unchanged. Cache identity includes an SHA-256 of the audio, so changed audio is recognized again.

## Alignment and review

1. Read and split the reference without changing its normalized words.
2. Recognize word timestamps locally using faster-whisper with Mandarin, voice activity detection, and a supported CPU compute type.
3. Match reference characters to recognized characters. Minor substitutions use interpolated neighboring matched timestamps.
4. Reject likely mismatched files: either text coverage below 85%, or any consecutive unmatched run above 8 characters. Save a review report and return exit code 2 without a new SRT.
5. Check positive caption durations, monotonic times, and nonoverlap. Save a numbered UTF-8 BOM SRT with millisecond timestamps.

These matching thresholds detect substantial differences; they do not certify frame-accurate timing. Recognition homophones often appear in the review report even when narration is correct. Always spot-check the beginning, clause boundaries, reported differences, and end in Premiere Pro. If a run is blocked, correct the reference/audio pair or try the larger model; the tool does not bypass the check automatically.

Exit codes: `0` = generated or cancelled by the file picker; `1` = input, dependency, or runtime failure; `2` = text/audio mismatch blocked generation.

## Local files and portability

Keep `run.py`, `subtitle.py`, `requirements.txt`, and the guides together when copying the tool between Windows and macOS. The new computer initializes its own environment and model. Do not copy `.venv` across operating systems: Python environments are platform-specific. `.venv/`, `.cache/`, and `output/` are ignored by Git and contain local runtime files, recognition results, and generated captions. Recognition runs locally; downloading dependencies/models does not upload the input audio. Cached timing/report files contain recognized or reference text and source paths.

Windows execution and caption generation are tested locally. macOS launcher paths and backend precision selection are covered by unit checks, but macOS execution has not been verified on a physical Mac in this environment.

Run the unit checks with:

```text
Windows: .venv\Scripts\python.exe -m unittest discover -s tests -v
macOS:   .venv/bin/python -m unittest discover -s tests -v
```

## GitHub

See [GITHUB.md](GITHUB.md) for repository setup, upload scope, and automated Windows/macOS checks. Store private narration TXT files in `inputs/`; environments, audio, downloaded models, and generated outputs stay local.
