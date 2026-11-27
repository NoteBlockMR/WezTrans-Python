import ctypes
import json
import os
import pathlib
import sys


def send(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=True) + '\n')
    sys.stdout.flush()


def main():
    directory = pathlib.Path(sys.argv[1]).resolve()
    dll = directory / 'J2KEngine.dll'
    if not dll.is_file() or not (directory / 'Dat').is_dir():
        raise RuntimeError('J2KEngine.dll 또는 Dat 폴더를 찾을 수 없습니다: ' + str(directory))
    os.add_dll_directory(str(directory))
    engine = ctypes.WinDLL(str(dll))
    engine.J2K_InitializeEx.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    engine.J2K_InitializeEx.restype = ctypes.c_int
    engine.J2K_TranslateMMNT.argtypes = [ctypes.c_int, ctypes.c_char_p]
    engine.J2K_TranslateMMNT.restype = ctypes.c_void_p
    engine.J2K_FreeMem.argtypes = [ctypes.c_void_p]
    engine.J2K_FreeMem.restype = ctypes.c_int
    engine.J2K_StopTranslation.argtypes = [ctypes.c_int]
    engine.J2K_StopTranslation.restype = ctypes.c_int
    engine.J2K_InitializeEx(b'CSUSER123455', str(directory / 'Dat').encode('cp949'))
    send({'ready': True})
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if request.get('stop'):
                    break
                source = request['text'].encode('cp932')
                ptr = engine.J2K_TranslateMMNT(0, source)
                if not ptr:
                    raise RuntimeError('ezTrans가 빈 포인터를 반환했습니다.')
                try:
                    result = ctypes.string_at(ptr).decode('cp949')
                finally:
                    engine.J2K_FreeMem(ptr)
                send({'text': result})
            except Exception as exc:
                send({'error': str(exc)})
    finally:
        engine.J2K_StopTranslation(0)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        send({'error': str(exc)})
        sys.exit(1)
