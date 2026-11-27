"""Back up originals and atomically save translation progress beside them."""
import os
import tempfile
from pathlib import Path


def atomic_write(path, data):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


class TranslationFiles:
    def __init__(self, path, input_encoding, output_encoding):
        self.path = Path(path).resolve()
        self.original = self.path.read_bytes()
        self.text = self.original.decode(input_encoding)
        if not self.text.strip():
            raise ValueError('번역할 내용이 없는 파일입니다.')
        self.output_encoding = output_encoding
        # Validate the output codec before creating the backup or invoking an engine.
        ''.encode(output_encoding)
        index = 0
        while True:
            suffix = '.bak' if index == 0 else '.bak.%d' % index
            self.backup = self.path.with_name(self.path.name + suffix)
            try:
                with self.backup.open('xb') as stream:
                    stream.write(self.original)
                    stream.flush()
                    os.fsync(stream.fileno())
                break
            except FileExistsError:
                index += 1
        self.partial = self.backup.with_name(self.backup.name + '.translating.txt')
        # Exclusive creation avoids overwriting a prior recovery file.
        with self.partial.open('xb') as stream:
            stream.write(self.text.encode('utf-8-sig'))
            stream.flush()
            os.fsync(stream.fileno())

    def checkpoint(self, text):
        atomic_write(self.partial, text.encode('utf-8-sig'))

    def finish(self, text):
        self.checkpoint(text)
        data = text.encode(self.output_encoding)
        if self.path.read_bytes() != self.original:
            raise RuntimeError('번역 중 원본 파일이 변경되어 자동 교체를 중단했습니다. 번역 결과는 임시 파일에 보존했습니다.')
        atomic_write(self.path, data)
        try:
            self.partial.unlink()
        except OSError:
            pass
