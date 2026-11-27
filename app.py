import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import urllib.request

from translator import BASE, EzTrans, translate_text
from file_session import TranslationFiles

SETTINGS = BASE / 'settings.json'
DEFAULTS = {
    'engine': 'ezTrans', 'url': 'http://127.0.0.1:11434',
    'model': '',
    'source': 'Japanese', 'target': 'Korean', 'workers': '2',
    'ez_path': r'C:\Program Files (x86)\ChangShin\ezTrans',
    'python32': str(BASE / 'python32' / 'python.exe'), 'input_encoding': 'utf-8-sig',
    'output_encoding': 'utf-8-sig',
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('WezTrans Python')
        self.geometry('1040x760')
        self.minsize(800, 620)
        self.events = queue.Queue()
        self.cancel_event = None
        self.input_path = None
        try:
            settings = {**DEFAULTS, **json.loads(SETTINGS.read_text(encoding='utf-8'))}
        except (OSError, ValueError, TypeError):
            settings = DEFAULTS.copy()
        settings['engine'] = 'ezTrans'  # Ollama support is temporarily disabled.
        self.values = {key: tk.StringVar(value=str(settings[key])) for key in DEFAULTS}
        self.create_ui()
        self.after(100, self.poll)
        self.protocol('WM_DELETE_WINDOW', self.on_close)

    def create_ui(self):
        self.configure(padx=16, pady=12)
        style = ttk.Style(self)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('Title.TLabel', font=('Malgun Gothic', 17, 'bold'))
        style.configure('Sub.TLabel', foreground='#555f70')
        ttk.Label(self, text='WezTrans Python', style='Title.TLabel').pack(anchor='w')
        ttk.Label(self, text='한 줄씩 번역 · 원문 순서와 줄바꿈 유지', style='Sub.TLabel').pack(anchor='w', pady=(0, 10))
        opts = ttk.LabelFrame(self, text='번역 설정', padding=10)
        opts.pack(fill='x')
        ttk.Label(opts, text='Ollama 기능은 현재 비활성화되어 있습니다.', style='Sub.TLabel').grid(row=4, column=0, columnspan=4, sticky='w', pady=(4, 0))
        for col in (1, 3): opts.columnconfigure(col, weight=1)
        def label(text, row, col): ttk.Label(opts, text=text).grid(row=row, column=col, sticky='w', padx=(0, 5), pady=4)
        def entry(key, row, col, width=24):
            e = ttk.Entry(opts, textvariable=self.values[key], width=width)
            e.grid(row=row, column=col, sticky='ew', padx=(0, 10), pady=4)
            return e
        label('엔진', 0, 0)
        cb = ttk.Combobox(opts, textvariable=self.values['engine'], values=['ezTrans'], state='disabled', width=18)
        cb.grid(row=0, column=1, sticky='ew', padx=(0, 10)); cb.bind('<<ComboboxSelected>>', self.engine_changed)
        label('동시 작업', 0, 2)
        ttk.Spinbox(opts, from_=1, to=16, textvariable=self.values['workers'], width=6).grid(row=0, column=3, sticky='w')
        label('Ollama 주소', 1, 0); self.url_entry = entry('url', 1, 1)
        label('모델', 1, 2)
        modelbox = ttk.Frame(opts); modelbox.grid(row=1, column=3, sticky='ew'); modelbox.columnconfigure(0, weight=1)
        self.model_combo = ttk.Combobox(modelbox, textvariable=self.values['model'])
        self.model_combo.grid(row=0, column=0, sticky='ew')
        self.models_button = ttk.Button(modelbox, text='목록 새로고침', command=self.refresh_models)
        self.models_button.grid(row=0, column=1, padx=(5, 0))
        label('원문 언어', 2, 0)
        ttk.Combobox(opts, textvariable=self.values['source'], values=['Japanese', 'English', 'Chinese', 'Korean'], width=18).grid(row=2, column=1, sticky='ew', padx=(0, 10))
        label('번역 언어', 2, 2)
        ttk.Combobox(opts, textvariable=self.values['target'], values=['Korean', 'Japanese', 'English', 'Chinese'], width=18).grid(row=2, column=3, sticky='ew')
        label('ezTrans 경로', 3, 0); entry('ez_path', 3, 1)
        ttk.Button(opts, text='폴더 선택', command=self.choose_ez).grid(row=3, column=2, sticky='w')
        ttk.Label(opts, text='ezTrans는 일본어 → 한국어', style='Sub.TLabel').grid(row=3, column=3, sticky='w')
        self.note = ttk.Label(self, text='', style='Sub.TLabel'); self.note.pack(anchor='w', pady=(6, 4))
        enc = ttk.Frame(self); enc.pack(fill='x', pady=(0, 6))
        self.open_button = ttk.Button(enc, text='텍스트 파일 열기', command=self.open_file)
        self.open_button.pack(side='left')
        ttk.Label(enc, text='입력 인코딩').pack(side='left', padx=(14, 4))
        encodings = ['utf-8-sig', 'utf-8', 'utf-16', 'cp932', 'cp949']
        ttk.Combobox(enc, textvariable=self.values['input_encoding'], values=encodings, width=11).pack(side='left')
        ttk.Label(enc, text='출력 인코딩').pack(side='left', padx=(14, 4))
        ttk.Combobox(enc, textvariable=self.values['output_encoding'], values=encodings, width=11).pack(side='left')
        ttk.Label(enc, text='완료 시 원본 파일 자동 교체', style='Sub.TLabel').pack(side='right')
        self.file_label = ttk.Label(self, text='선택된 파일 없음', style='Sub.TLabel')
        self.file_label.pack(anchor='w', pady=(0, 5))
        actions = ttk.Frame(self); actions.pack(fill='x', pady=(10, 0))
        self.start_button = ttk.Button(actions, text='번역 시작', command=self.start); self.start_button.pack(side='left')
        self.stop_button = ttk.Button(actions, text='중지', command=self.stop, state='disabled'); self.stop_button.pack(side='left', padx=6)
        self.status = tk.StringVar(value='준비됨')
        ttk.Label(actions, textvariable=self.status).pack(side='right')
        progress_frame = ttk.Frame(self); progress_frame.pack(fill='x', pady=(8, 8))
        self.progress = ttk.Progressbar(progress_frame, mode='determinate', maximum=100)
        self.progress.pack(fill='x', ipady=5)
        self.percent = tk.StringVar(value='0%')
        self.percent_label = ttk.Label(progress_frame, textvariable=self.percent, anchor='center')
        self.percent_label.place(relx=0.5, rely=0.5, anchor='center')
        log_frame = ttk.LabelFrame(self, text='번역 로그 (최근 500줄)', padding=5)
        log_frame.pack(fill='both', expand=True)
        self.log_text = tk.Text(log_frame, wrap='none', state='disabled', font=('Malgun Gothic', 10))
        scroll = ttk.Scrollbar(log_frame, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y'); self.log_text.pack(fill='both', expand=True)
        self.engine_changed()

    def log(self, text):
        # Keep the latest 500 lines so long translations do not grow the widget indefinitely.
        self.log_text.configure(state='normal')
        self.log_text.insert('end', text.replace('\r', ' ').replace('\n', ' ') + '\n')
        line_count = int(self.log_text.index('end-1c').split('.')[0]) - 1
        if line_count > 500:
            self.log_text.delete('1.0', '%d.0' % (line_count - 500 + 1))
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def set_progress(self, completed, total):
        value = 100 * completed / total if total else 0
        self.progress['value'] = value
        self.percent.set('%.1f%%' % value)

    def engine_changed(self, event=None):
        is_ez = self.values['engine'].get() == 'ezTrans'
        state = 'disabled' if is_ez else 'normal'
        self.url_entry.configure(state=state)
        self.model_combo.configure(state=state)
        self.models_button.configure(state=state)
        if is_ez:
            self.note.config(text='ezTrans는 줄과 쉼표·큰따옴표 기준으로 나누어 병렬 번역합니다. 일본어 → 한국어를 지원합니다.')
        else:
            self.note.config(text='Ollama는 현재 준비 중입니다.')

    def validate_ez_path(self, value):
        path = Path(value.strip().strip('"')).expanduser()
        if not (path / 'J2KEngine.dll').is_file() or not (path / 'Dat').is_dir():
            raise ValueError('ezTrans 설치 폴더를 선택해 주세요.\n\n선택한 폴더에 J2KEngine.dll 파일과 Dat 폴더가 모두 있어야 합니다.\n\n현재 경로: ' + str(path))
        return str(path.resolve())

    def choose_ez(self):
        current = Path(self.values['ez_path'].get().strip().strip('"')).expanduser()
        value = filedialog.askdirectory(title='ezTrans 설치 폴더 선택', initialdir=str(current) if current.is_dir() else None)
        if not value:
            return
        try:
            value = self.validate_ez_path(value)
            self.values['ez_path'].set(value)
            SETTINGS.write_text(json.dumps({k: v.get() for k, v in self.values.items()}, ensure_ascii=False, indent=2), encoding='utf-8')
            self.status.set('ezTrans 경로 저장 완료')
        except (ValueError, OSError) as exc:
            messagebox.showerror('ezTrans 경로 오류', str(exc))

    def refresh_models(self):
        url = self.values['url'].get().strip().rstrip('/')
        def run():
            try:
                with urllib.request.urlopen(url + '/api/tags', timeout=8) as response:
                    models = [m['name'] for m in json.load(response).get('models', [])]
                self.events.put(('models', models))
            except Exception as exc: self.events.put(('error', '모델 목록을 가져올 수 없습니다: ' + str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def open_file(self):
        path = filedialog.askopenfilename(filetypes=[('텍스트 파일', '*.txt'), ('모든 파일', '*.*')])
        if not path: return
        self.input_path = Path(path)
        self.file_label.configure(text='선택한 파일: ' + str(self.input_path))
        self.status.set('파일 열기: ' + self.input_path.name)
        self.set_progress(0, 1)
        self.log('파일 선택: ' + str(self.input_path))

    def start(self):
        if not self.input_path: messagebox.showinfo('번역', '먼저 텍스트 파일을 열어 주세요.'); return
        try:
            workers = int(self.values['workers'].get())
            if not 1 <= workers <= 16: raise ValueError('동시 작업 수는 1~16이어야 합니다.')
            if self.values['engine'].get() == 'ezTrans':
                ez_path = self.validate_ez_path(self.values['ez_path'].get())
                self.values['ez_path'].set(ez_path)
                engine = EzTrans(ez_path, self.values['python32'].get())
            else:
                raise ValueError('Ollama 번역 기능은 현재 비활성화되어 있습니다.')
            SETTINGS.write_text(json.dumps({k:v.get() for k,v in self.values.items()}, ensure_ascii=False, indent=2), encoding='utf-8')
        except (ValueError, OSError) as exc: messagebox.showerror('설정 오류', str(exc)); return
        self.cancel_event = threading.Event()
        self.start_button.config(state='disabled'); self.stop_button.config(state='normal'); self.open_button.config(state='disabled')
        self.set_progress(0, 1); self.status.set('번역 중...')
        self.log('번역 시작: ' + self.input_path.name)
        input_path = self.input_path
        input_encoding = self.values['input_encoding'].get()
        output_encoding = self.values['output_encoding'].get()
        def run():
            try:
                files = TranslationFiles(input_path, input_encoding, output_encoding)
                self.events.put(('log', '원본 백업: ' + str(files.backup)))
                self.events.put(('log', '10초마다 임시 저장: ' + str(files.partial)))
                def checkpoint(snapshot):
                    files.checkpoint(snapshot)
                    self.events.put(('log', '번역 진행 내용 임시 저장 완료'))
                result = translate_text(files.text, engine, workers, self.cancel_event,
                    lambda done,total,line:self.events.put(('progress', (done,total,line))), checkpoint)
                files.finish(result)
                self.events.put(('done', str(files.backup)))
            except Exception as exc: self.events.put(('failed', str(exc)))
        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        if self.cancel_event:
            self.cancel_event.set(); self.status.set('현재 요청이 끝나면 중지합니다...'); self.stop_button.config(state='disabled'); self.log('중지 요청: 진행 중인 번역을 기다립니다.')

    def poll(self):
        try:
            for _ in range(100):
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    done,total,line = value; self.set_progress(done, total); self.status.set('번역 중: %d / %d' % (done,total)); self.log('%d번째 줄 번역 완료 (%d / %d)' % (line, done, total))
                elif kind == 'log': self.log(value)
                elif kind == 'models':
                    self.model_combo['values'] = value
                    if value and self.values['model'].get() not in value: self.values['model'].set(value[0])
                    self.status.set('모델 %d개 확인' % len(value))
                elif kind == 'error': messagebox.showerror('오류', value)
                elif kind in ('done', 'failed'):
                    self.cancel_event = None; self.start_button.config(state='normal'); self.stop_button.config(state='disabled'); self.open_button.config(state='normal')
                    if kind == 'done':
                        self.input_path = None
                        self.file_label.configure(text='선택된 파일 없음')
                        self.status.set('번역 완료 · 원본 교체됨'); self.set_progress(1, 1); self.log('번역 완료: 원본 파일을 자동 교체했습니다. 백업: ' + value)
                    else:
                        self.status.set('번역 중지 또는 실패'); self.log('번역 중지 또는 실패: ' + value); messagebox.showerror('번역 중지 또는 실패', value)
        except queue.Empty: pass
        self.after(100, self.poll)

    def on_close(self):
        if self.cancel_event:
            self.cancel_event.set()
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
