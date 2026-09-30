"""Generate reference-text SRT captions aligned to Mandarin narration."""
from __future__ import annotations

import argparse
import bisect
import difflib
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION = 1


def normalize(text: str) -> str:
    return ''.join(c.casefold() for c in text if c.isalnum())


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    encodings = ['utf-16'] if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else ['utf-8-sig', 'gb18030']
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            if '\x00' in text:
                raise ValueError('Unsupported text encoding. Save the document as UTF-8 TXT.')
            return text.strip()
        except UnicodeDecodeError:
            continue
    raise ValueError('Cannot read the text file. Save it as UTF-8 TXT.')


def split_text(text: str, max_chars: int, one_line: bool) -> list[str]:
    if one_line:
        chunks = [line.strip() for line in text.splitlines() if line.strip()]
    else:
        # Keep punctuation and every source character; prefer existing clause boundaries.
        units = re.findall(r'[^，,。！？!?；;：:\n]+[，,。！？!?；;：:]*', text)
        chunks = []
        for unit in units:
            unit = unit.strip()
            while len(unit) > max_chars:
                # Avoid ending immediately before closing punctuation.
                cut = max_chars
                if cut < len(unit) and unit[cut] in '，,。！？!?；;：:》”」）)':
                    cut -= 1
                chunks.append(unit[:cut].strip())
                unit = unit[cut:].strip()
            if unit:
                chunks.append(unit)
    chunks = [c for c in chunks if normalize(c)]
    if not chunks or normalize(''.join(chunks)) != normalize(text):
        raise ValueError('The document is empty or its text could not be preserved during splitting.')
    return chunks


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cpu_compute_type(supported: set[str]) -> str:
    return 'int8' if 'int8' in supported else 'float32'


def transcribe(audio: Path, model_name: str, prompt: str, cache: Path, refresh: bool) -> dict:
    settings = {'version': VERSION, 'audio_sha256': file_digest(audio), 'model': model_name,
                'prompt': prompt, 'language': 'zh', 'word_timestamps': True, 'vad_filter': True}
    key = hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()
    destination = cache / 'timings' / (key + '.json')
    if destination.exists() and not refresh:
        print('复用该音频的时间识别结果。', flush=True)
        return json.loads(destination.read_text(encoding='utf-8'))['result']
    try:
        from faster_whisper import WhisperModel
        from huggingface_hub.errors import LocalEntryNotFoundError
        from ctranslate2 import get_supported_compute_types
    except ImportError as error:
        raise ValueError('缺少依赖。请先运行 python run.py --setup-only 或安装 requirements.txt。') from error
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
    print('正在加载语音模型；首次使用会下载，后续复用本地模型。', flush=True)
    precision = cpu_compute_type(get_supported_compute_types('cpu'))
    model_options = dict(device='cpu', compute_type=precision, download_root=str(cache / 'models'),
                         cpu_threads=min(os.cpu_count() or 4, 8))
    try:
        model = WhisperModel(model_name, local_files_only=True, **model_options)
    except LocalEntryNotFoundError:
        model = WhisperModel(model_name, **model_options)
    segments, info = model.transcribe(str(audio), language='zh', word_timestamps=True,
                                     vad_filter=True, initial_prompt=prompt or None)
    result = {'duration': info.duration, 'segments': []}
    for segment in segments:
        result['segments'].append({'start': segment.start, 'end': segment.end, 'text': segment.text,
                                   'words': [{'start': w.start, 'end': w.end, 'word': w.word}
                                             for w in segment.words or []]})
        print(f'已处理至 {segment.end:.1f} 秒', flush=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps({'settings': settings, 'result': result}, ensure_ascii=False), encoding='utf-8')
    temporary.replace(destination)
    return result


def align(chunks: list[str], data: dict) -> tuple[list[dict], dict]:
    characters, times = [], []
    duration = float(data['duration'])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('音频时长无效。')
    for segment in data['segments']:
        for word in segment['words']:
            text = normalize(word['word'])
            start, end = float(word['start']), float(word['end'])
            if not (0 <= start <= end <= duration + .05):
                raise ValueError('音频识别时间无效，请重新识别。')
            for j, character in enumerate(text):
                characters.append(character)
                times.append((start + (end - start) * j / len(text),
                              start + (end - start) * (j + 1) / len(text)))
    reference, recognized = normalize(''.join(chunks)), ''.join(characters)
    if not recognized:
        raise ValueError('没有识别到有效语音。请检查音频。')
    matcher = difflib.SequenceMatcher(None, reference, recognized, autojunk=False)
    mapping = {}
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            mapping[block.a + k] = block.b + k
    differences = []
    longest_gap = 0
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag != 'equal':
            differences.append({'type': tag, 'reference': reference[a:b], 'recognized': recognized[c:d],
                                'reference_start': a, 'reference_end': b})
            longest_gap = max(longest_gap, b - a, d - c)
    coverage = len(mapping) / len(reference)
    recognized_coverage = len(mapping) / len(recognized)
    report = {'duration_seconds': duration, 'reference_match_ratio': round(coverage, 4),
              'recognized_match_ratio': round(recognized_coverage, 4),
              'longest_unmatched_run': longest_gap, 'differences': differences,
              'status': 'needs_review' if differences else 'aligned'}
    # Fail on a likely wrong file, omitted paragraph, or substantial ad-libbing.
    if min(coverage, recognized_coverage) < .85 or longest_gap > 8:
        report['status'] = 'blocked'
        return [], report
    known = sorted(mapping)
    for k in range(len(reference)):
        if k in mapping:
            continue
        index = bisect.bisect_left(known, k)
        left = known[index - 1] if index else None
        right = known[index] if index < len(known) else None
        if left is None:
            mapping[k] = mapping[right]
        elif right is None:
            mapping[k] = mapping[left]
        else:
            mapping[k] = round(mapping[left] + (mapping[right] - mapping[left]) * (k - left) / (right - left))
    rows, offset = [], 0
    for chunk in chunks:
        count = len(normalize(chunk))
        start, end = times[mapping[offset]][0], times[mapping[offset + count - 1]][1]
        rows.append({'start': start, 'end': end, 'text': chunk})
        offset += count
    for i, row in enumerate(rows):
        limit = rows[i + 1]['start'] if i + 1 < len(rows) else duration
        padding = .08 if i + 1 < len(rows) else 0
        row['end'] = min(max(row['end'], row['start'] + .4) + padding, limit)
        row['start_ms'] = round(row['start'] * 1000)
        row['end_ms'] = round(row['end'] * 1000)
        if row['end_ms'] <= row['start_ms'] or (i and row['start_ms'] < rows[i - 1]['end_ms']):
            raise ValueError('无法生成有效字幕时间。请修正文稿使其与音频一致，或尝试 medium 模型。')
    report['caption_count'] = len(rows)
    report['short_caption_numbers'] = [i + 1 for i, r in enumerate(rows) if r['end'] - r['start'] < .5]
    return rows, report


def timestamp(milliseconds: int) -> str:
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}'


def render_srt(rows: list[dict]) -> str:
    return '\n\n'.join(f"{i + 1}\n{timestamp(r['start_ms'])} --> {timestamp(r['end_ms'])}\n{r['text']}"
                       for i, r in enumerate(rows)) + '\n'


def pick_files() -> tuple[Path, Path] | None:
    # Tk is optional: minimal Python distributions may omit its runtime.
    window = None
    try:
        import tkinter as tk
        from tkinter import filedialog
        window = tk.Tk()
        window.withdraw()
    except Exception:
        print('当前 Python 没有可用的文件选择窗口，改为输入文件路径。', flush=True)
        return prompt_files()
    try:
        text = filedialog.askopenfilename(parent=window, title='第 1 步：选择口播文稿 TXT',
                                         filetypes=[('TXT 文稿', '*.txt')])
        if not text:
            return None
        audio = filedialog.askopenfilename(parent=window, title='第 2 步：选择对应音频',
                                          filetypes=[('所有文件', '*')])
        return (Path(text), Path(audio)) if audio else None
    finally:
        window.destroy()


def prompt_files() -> tuple[Path, Path] | None:
    text = input('请输入文稿 TXT 路径（留空取消）：').strip().strip('\"\'')
    if not text:
        return None
    audio = input('请输入音频路径（留空取消）：').strip().strip('\"\'')
    return (Path(text).expanduser(), Path(audio).expanduser()) if audio else None


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description='文稿 + 中文口播音频 → PR SRT 字幕')
    result.add_argument('--text', type=Path)
    result.add_argument('--audio', type=Path)
    result.add_argument('--pick-files', action='store_true')
    result.add_argument('--terminal', action='store_true', help='Enter file paths without a graphical file picker')
    result.add_argument('--output', type=Path, help='SRT path; default: project output/<audio stem>-PR字幕.srt')
    result.add_argument('--model', default='small', help='Whisper model name or local model directory')
    result.add_argument('--max-chars', type=int, default=16)
    result.add_argument('--one-line-per-caption', action='store_true', help='Use each nonempty TXT line as a caption')
    result.add_argument('--prompt', default='', help='Optional recognition terminology; never changes reference text')
    result.add_argument('--cache-dir', type=Path, default=ROOT / '.cache')
    result.add_argument('--refresh', action='store_true')
    result.add_argument('--overwrite', action='store_true')
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.pick_files or args.terminal or (args.text is None and args.audio is None):
            pair = prompt_files() if args.terminal else pick_files()
            if pair is None:
                print('已取消。')
                return 0
            args.text, args.audio = pair
        if args.text is not None:
            args.text = args.text.expanduser()
        if args.audio is not None:
            args.audio = args.audio.expanduser()
        args.cache_dir = args.cache_dir.expanduser()
        if args.output is not None:
            args.output = args.output.expanduser()
        if args.text is None or args.audio is None:
            raise ValueError('需要同时提供 --text 和 --audio，或使用 --pick-files。')
        if not 8 <= args.max_chars <= 40:
            raise ValueError('--max-chars 必须在 8 到 40 之间。')
        for path in (args.text, args.audio):
            if not path.is_file():
                raise ValueError(f'找不到输入文件：{path}')
        if args.text.suffix.lower() != '.txt':
            raise ValueError('文稿应为 TXT 文件。请先将 Word 或其他文档另存为 TXT。')
        output = args.output or ROOT / 'output' / f'{args.audio.stem}-PR字幕.srt'
        if args.output is None and not args.overwrite:
            base = output
            counter = 2
            while output.exists() or output.with_suffix('.review.json').exists():
                output = base.with_name(f'{base.stem}-{counter}.srt')
                counter += 1
        output = output.resolve()
        if output.suffix.lower() != '.srt':
            raise ValueError('输出文件扩展名必须为 .srt。')
        report_path = output.with_suffix('.review.json')
        if output in (args.text.resolve(), args.audio.resolve()) or report_path in (args.text.resolve(), args.audio.resolve()):
            raise ValueError('输出路径不能覆盖输入文件。')
        if (output.exists() or report_path.exists()) and not args.overwrite:
            raise ValueError(f'输出已存在：{output}。请改用新名称，或明确添加 --overwrite。')
        chunks = split_text(read_text(args.text), args.max_chars, args.one_line_per_caption)
        print(f'文稿已拆成 {len(chunks)} 条字幕。', flush=True)
        data = transcribe(args.audio, args.model, args.prompt, args.cache_dir, args.refresh)
        rows, report = align(chunks, data)
        report.update({'text_file': str(args.text.resolve()), 'audio_file': str(args.audio.resolve()),
                       'model': args.model, 'output_file': str(output),
                       'note': '自动识别对齐；替换或缺失字符的时间由相邻已匹配字符推算。请在 PR 中抽查。'})
        output.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            if args.overwrite and output.exists():
                output.unlink()  # Explicit overwrite must not leave a stale successful SRT.
            print(f'文稿与音频差异过大，未生成 SRT。差异报告：{report_path}', file=sys.stderr)
            return 2
        # Exclusive creation protects an existing file if another run created it meanwhile.
        with output.open('w' if args.overwrite else 'x', encoding='utf-8-sig', newline='\r\n') as stream:
            stream.write(render_srt(rows))
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"完成：{len(rows)} 条字幕，音频 {data['duration']:.2f} 秒。\n字幕：{output}\n核对报告：{report_path}")
        if report['differences']:
            print(f"有 {len(report['differences'])} 处识别文字差异，已保留原文；请抽查对应时间。")
        return 0
    except Exception as error:
        print(f'字幕制作失败：{error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
