import concurrent.futures
import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
PROMPT = '''You are a Korean game dialogue writer and localization editor, not a literal translator.
Understand the {source} line, then write it as dialogue originally scripted in natural {target}.
Priorities:
1. Keep the facts, intent, relationships, and emotion correct.
2. Make the speaker's voice vivid and consistent with the source.
3. Use concise, speakable dialogue with natural rhythm and endings.
Discard foreign clause order and redundant pronouns. Use idiomatic reactions, contractions, banmal/jondaetmal, teasing, anger, hesitation, vulgarity, or broken speech when the source calls for them. Do not sanitize adult dialogue. Never add new facts. Keep the requested line count and protected tokens. Output only the finished translation.
Output exactly one line.'''
TOKEN = re.compile(r'https?://[^\s<>]+|\\(?:[A-Za-z]+(?:\[[^\]\r\n]*\])?|[!.$|<>^{}\\])|<[^>\r\n]+>|%\d+|\{[^{}\r\n]+\}|/[A-Za-z]WT[0-9A-Fa-f]+/')
MARKER = re.compile(r'__WT\d{4}__')


def protect(text):
    if MARKER.search(text):
        raise ValueError('원문에 예약된 보호 마커가 포함되어 있습니다.')
    tokens = []
    def substitute(match):
        marker = '__WT%04d__' % len(tokens)
        tokens.append(match.group())
        return marker
    return TOKEN.sub(substitute, text), tokens


def restore(text, tokens):
    expected = ['__WT%04d__' % i for i in range(len(tokens))]
    if MARKER.findall(text) != expected:
        raise ValueError('번역 결과의 보호 코드가 누락되거나 변경되었습니다.')
    for marker, token in zip(expected, tokens):
        text = text.replace(marker, token)
    return text


class Ollama:
    def __init__(self, url, model, source, target, timeout=180):
        self.url, self.model, self.source, self.target, self.timeout = url.rstrip('/'), model, source, target, timeout
        if not self.model.strip():
            raise ValueError('Ollama 모델을 입력하세요.')
    def translate(self, text):
        protected, tokens = protect(text)
        payload = {'model': self.model, 'stream': False, 'options': {'temperature': 0.1}, 'messages': [
            {'role': 'system', 'content': PROMPT.format(source=self.source, target=self.target) + (' Copy every marker like __WT0000__ exactly once, unchanged, and in the original order.' if tokens else '')},
            {'role': 'user', 'content': protected}]}
        req = urllib.request.Request(self.url + '/api/chat', data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError('Ollama HTTP %s: %s' % (exc.code, exc.read(1000).decode('utf-8', 'replace'))) from exc
        result = data.get('message', {}).get('content', '').strip()
        if not result or '\n' in result or '\r' in result:
            raise ValueError('Ollama가 빈 응답 또는 여러 줄을 반환했습니다.')
        return restore(result, tokens)
    def close(self):
        pass


class EzTrans:
    def __init__(self, directory, python32):
        self.directory, self.python32 = directory, python32
        if not Path(python32).is_file():
            raise ValueError('32비트 Python이 없습니다. Setup-ezTrans.bat을 먼저 실행해 주세요: ' + python32)
        self.local = threading.local()
        self.processes = []
        self.init_lock = threading.Lock()
    def _worker(self):
        if not hasattr(self.local, 'process'):
            # The installed DLL can be used in separate processes, but concurrent
            # initialization can fail. Only startup needs to be serialized.
            with self.init_lock:
                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                process = subprocess.Popen([self.python32, '-u', str(BASE / 'ez_worker.py'), self.directory], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8', creationflags=flags)
                self.processes.append(process)
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError('ezTrans 작업자를 시작할 수 없습니다. 32비트 Python과 DLL을 확인하세요.')
                ready = json.loads(line)
                if not ready.get('ready'):
                    raise RuntimeError(ready.get('error', 'ezTrans 초기화 실패'))
                self.local.process = process
        return self.local.process
    def translate(self, text):
        # Protect control codes before splitting: punctuation inside a code or
        # tag is data, not a WezTrans segment boundary.
        protected, tokens = protect(text)
        pieces = re.split(r'([,"\x00])', protected)
        translated = []
        for index, piece in enumerate(pieces):
            if index % 2 or not piece.strip():
                translated.append(piece)
                continue
            leading = piece[:len(piece) - len(piece.lstrip())]
            trailing = piece[len(piece.rstrip()):]
            p = self._worker()
            p.stdin.write(json.dumps({'text': piece.strip()}, ensure_ascii=True) + '\n')
            p.stdin.flush()
            line = p.stdout.readline()
            if not line:
                raise RuntimeError('ezTrans 작업자가 예기치 않게 종료되었습니다.')
            response = json.loads(line)
            if 'error' in response:
                raise RuntimeError(response['error'])
            result = response.get('text', '').strip()
            if not result or '\n' in result or '\r' in result:
                raise ValueError('ezTrans가 빈 응답 또는 여러 줄을 반환했습니다.')
            translated.append(leading + result + trailing)
        return restore(''.join(translated), tokens)
    def close(self):
        for process in self.processes:
            try:
                if process.poll() is None:
                    process.stdin.write('{"stop":true}\n')
                    process.stdin.flush()
                    process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                if process.poll() is None:
                    process.kill()
                    process.wait()
            finally:
                for stream in (process.stdin, process.stdout):
                    try:
                        stream.close()
                    except OSError:
                        pass


def translate_text(text, engine, workers=1, cancel=None, progress=None, checkpoint=None, checkpoint_interval=10):
    if not 1 <= workers <= 16:
        raise ValueError('작업자 수는 1~16이어야 합니다.')
    lines = text.splitlines(keepends=True)
    results = [None] * len(lines)
    jobs = []
    for i, line in enumerate(lines):
        body = line.rstrip('\r\n')
        ending = line[len(body):]
        if not body.strip():
            results[i] = line
        else:
            jobs.append((i, body, ending))
    def run(job):
        if cancel and cancel.is_set():
            return None
        i, body, ending = job
        leading = body[:len(body) - len(body.lstrip())]
        trailing = body[len(body.rstrip()):]
        try:
            return leading + engine.translate(body.strip()) + trailing + ending
        except Exception as exc:
            raise RuntimeError('%d번째 줄: %s' % (i + 1, exc)) from exc
    def snapshot():
        return ''.join(result if result is not None else line for line, result in zip(lines, results))
    next_checkpoint = time.monotonic() + checkpoint_interval
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            pending = {}
            iterator = iter(jobs)
            def submit_next():
                try:
                    job = next(iterator)
                except StopIteration:
                    return False
                pending[pool.submit(run, job)] = job[0]
                return True
            for _ in range(workers):
                if not submit_next():
                    break
            completed = 0
            while pending:
                timeout = max(0, next_checkpoint - time.monotonic()) if checkpoint else None
                done, _ = concurrent.futures.wait(pending, timeout=timeout, return_when=concurrent.futures.FIRST_COMPLETED)
                for future in done:
                    index = pending.pop(future)
                    results[index] = future.result()
                    if results[index] is None:
                        continue
                    completed += 1
                    if progress:
                        progress(completed, len(jobs), index + 1)
                    if not (cancel and cancel.is_set()):
                        submit_next()
                if checkpoint and time.monotonic() >= next_checkpoint:
                    checkpoint(snapshot())
                    next_checkpoint = time.monotonic() + checkpoint_interval
        if cancel and cancel.is_set():
            raise InterruptedError('번역을 중지했습니다.')
        return ''.join(results)
    except Exception:
        if checkpoint:
            checkpoint(snapshot())
        raise
    finally:
        engine.close()
