import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import subtitle


def narration(text):
    return {'duration': len(text) * .2 + 1, 'segments': [{'words': [
        {'word': c, 'start': i * .2, 'end': (i + 1) * .2} for i, c in enumerate(text)
    ]}]}


class SubtitleTests(unittest.TestCase):
    def test_cpu_precision_matches_backend_capability(self):
        self.assertEqual(subtitle.cpu_compute_type({'float32', 'int8'}), 'int8')
        self.assertEqual(subtitle.cpu_compute_type({'float32'}), 'float32')

    def test_file_picker_unicode_paths_and_cancel(self):
        window = MagicMock()
        tk = SimpleNamespace(Tk=MagicMock(return_value=window),
                             filedialog=SimpleNamespace(askopenfilename=MagicMock()))
        with patch.dict(sys.modules, {'tkinter': tk, 'tkinter.filedialog': tk.filedialog}):
            tk.filedialog.askopenfilename.side_effect = ['/用户/文稿.txt', '/用户/音频.mp3']
            self.assertEqual(subtitle.pick_files(), (Path('/用户/文稿.txt'), Path('/用户/音频.mp3')))
            window.destroy.assert_called_once()
            tk.filedialog.askopenfilename.side_effect = ['']
            self.assertIsNone(subtitle.pick_files())

    def test_missing_gui_falls_back_to_terminal(self):
        tk = SimpleNamespace(Tk=MagicMock(side_effect=RuntimeError('No Tcl runtime')), filedialog=SimpleNamespace())
        with patch.dict(sys.modules, {'tkinter': tk, 'tkinter.filedialog': tk.filedialog}), patch('builtins.input', side_effect=['"文稿.txt"', '音频.mp3']):
            self.assertEqual(subtitle.pick_files(), (Path('文稿.txt'), Path('音频.mp3')))

    def test_terminal_cancel(self):
        with patch('builtins.input', return_value=''):
            self.assertIsNone(subtitle.prompt_files())

    def test_split_preserves_words_and_length(self):
        text = '订单、货物和出口业务都在自己公司。\n委托出口办理免抵退税；外贸企业办理免退税。'
        chunks = subtitle.split_text(text, 16, False)
        self.assertEqual(subtitle.normalize(''.join(chunks)), subtitle.normalize(text))
        self.assertTrue(all(len(c) <= 16 for c in chunks))

    def test_manual_lines_preserve_boundaries(self):
        self.assertEqual(subtitle.split_text('第一种\n\n只是把报关操作交给报关行', 8, True),
                         ['第一种', '只是把报关操作交给报关行'])

    def test_homophones_keep_reference_and_valid_timing(self):
        chunks = ['生产企业办理免抵退税', '先确认退税申报主体']
        rows, report = subtitle.align(chunks, narration('生产企业办理免底退税先确认退税申报主题'))
        self.assertEqual([r['text'] for r in rows], chunks)
        self.assertEqual(report['status'], 'needs_review')
        self.assertLessEqual(rows[0]['end_ms'], rows[1]['start_ms'])
        self.assertIn('00:00:00,000 -->', subtitle.render_srt(rows))

    def test_missing_paragraph_blocks_output(self):
        rows, report = subtitle.align(['订单货物出口业务都在自己公司', '办理免抵退税'], narration('办理免抵退税'))
        self.assertEqual(rows, [])
        self.assertEqual(report['status'], 'blocked')

    def test_unrelated_extra_audio_blocks_output(self):
        rows, report = subtitle.align(['办理免抵退税'], narration('办理免抵退税今天还要聊一下其他完全无关的话题'))
        self.assertEqual(rows, [])
        self.assertEqual(report['status'], 'blocked')

    def test_multiple_encodings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'text.txt'
            for encoding in ['utf-8-sig', 'utf-16', 'gb18030']:
                path.write_bytes('委托出口退税'.encode(encoding))
                self.assertEqual(subtitle.read_text(path), '委托出口退税')

    def test_cli_output_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text, audio, output = root / 'text.txt', root / 'audio.mp3', root / 'captions.srt'
            text.write_text('免抵退税\n申报主体', encoding='utf-8')
            audio.write_bytes(b'test')
            args = ['--text', str(text), '--audio', str(audio), '--output', str(output), '--one-line-per-caption']
            with patch.object(subtitle, 'transcribe', return_value=narration('免抵退税申报主体')):
                self.assertEqual(subtitle.main(args), 0)
            self.assertTrue(output.read_bytes().startswith(b'\xef\xbb\xbf'))
            original = output.read_bytes()
            self.assertEqual(subtitle.main(args), 1)
            self.assertEqual(output.read_bytes(), original)
            with patch.object(subtitle, 'transcribe', return_value=narration('完全不同的内容')):
                self.assertEqual(subtitle.main(args + ['--overwrite']), 2)
            self.assertFalse(output.exists())
            report = json.loads(output.with_suffix('.review.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'blocked')

    def test_default_output_retains_previous_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text, audio = root / 'text.txt', root / 'audio.mp3'
            text.write_text('办理免抵退税', encoding='utf-8')
            audio.write_bytes(b'test')
            args = ['--text', str(text), '--audio', str(audio)]
            with patch.object(subtitle, 'ROOT', root), patch.object(subtitle, 'transcribe', return_value=narration('办理免抵退税')):
                self.assertEqual(subtitle.main(args), 0)
                self.assertEqual(subtitle.main(args), 0)
            self.assertTrue((root / 'output' / 'audio-PR字幕.srt').is_file())
            self.assertTrue((root / 'output' / 'audio-PR字幕-2.srt').is_file())


if __name__ == '__main__':
    unittest.main()
