import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_session import TranslationFiles
from translator import protect, restore, translate_text


class FakeEngine:
    def translate(self, text):
        time.sleep(0.02)
        return 'T' + text

    def close(self):
        pass


class TranslationTests(unittest.TestCase):
    def test_tokens_and_line_order(self):
        protected, tokens = protect(r'こんにちは、\N[1,2]')
        self.assertEqual(restore(protected, tokens), r'こんにちは、\N[1,2]')
        with self.assertRaises(ValueError):
            restore('missing marker', tokens)
        progress = []
        result = translate_text('a\r\n\r\nb\n', FakeEngine(), 2,
                                progress=lambda *args: progress.append(args))
        self.assertEqual(result, 'Ta\r\n\r\nTb\n')
        self.assertEqual(sorted(event[2] for event in progress), [1, 3])

    def test_backup_checkpoints_and_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.txt'
            original = b'a\r\nb\n'
            path.write_bytes(original)
            files = TranslationFiles(path, 'utf-8', 'utf-8')
            snapshots = []
            def save(value):
                snapshots.append(value)
                files.checkpoint(value)
            result = translate_text(files.text, FakeEngine(), 1, checkpoint=save,
                                    checkpoint_interval=0.005)
            self.assertTrue(snapshots)
            self.assertEqual(path.read_bytes(), original)
            files.finish(result)
            self.assertEqual(path.read_bytes(), b'Ta\r\nTb\n')
            self.assertEqual(files.backup.read_bytes(), original)
            self.assertFalse(files.partial.exists())

    def test_external_edits_remain_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.txt'
            path.write_bytes(b'original')
            files = TranslationFiles(path, 'utf-8', 'utf-8')
            path.write_bytes(b'external edit')
            with self.assertRaises(RuntimeError):
                files.finish('translated')
            self.assertEqual(path.read_bytes(), b'external edit')
            self.assertEqual(files.partial.read_text(encoding='utf-8-sig'), 'translated')
            self.assertEqual(files.backup.read_bytes(), b'original')

if __name__ == '__main__':
    unittest.main()
