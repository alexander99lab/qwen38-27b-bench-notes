#!/usr/bin/env python3
# Точная реплика дожимной короткой лесенки 20.08 (testlog/01_bf16_k3.txt):
# промпт ~100 слов, ген 256, stream: TTFT отдельно, декод-агрегат от первого токена.
import json, threading, time, urllib.request, random, sys

URL = 'http://localhost:18020/v1/chat/completions'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer REDACTED'}
random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 20)
WORDS = ('система отчёт заказчик поставка договор регламент отдел проверка акт приёмка '
         'бюджет план задача срок этап согласование накладная спецификация партия объём').split()

def prompt(uid):
    body = ' '.join(random.choice(WORDS) for _ in range(100))
    return f'[{uid}] {body}\nНапиши связный абзац о процессе поставки, использовав эти темы.'

def stream_ask(uid, res, i):
    b = json.dumps({'model': 'qwen3.8-27b', 'messages': [{'role': 'user', 'content': prompt(uid)}],
                    'max_tokens': 256, 'temperature': 0, 'stream': True, 'stream_options': {'include_usage': True},
                    'chat_template_kwargs': {'enable_thinking': False}}).encode()
    t0 = time.time(); ttft = None; ct = 0
    with urllib.request.urlopen(urllib.request.Request(URL, b, H), timeout=600) as r:
        for line in r:
            if line.startswith(b'data:') and b'[DONE]' not in line:
                if ttft is None:
                    ttft = time.time() - t0
                try:
                    d = json.loads(line[5:])
                    if d.get('usage'):
                        ct = d['usage']['completion_tokens']
                except Exception:
                    pass
    res[i] = (ttft, time.time() - t0, ct)

for N in (1, 2, 4, 8):
    res = [None] * N
    th = [threading.Thread(target=stream_ask, args=(f'L{N}S{i}R{random.randint(0,9999)}', res, i)) for i in range(N)]
    w0 = time.time()
    [t.start() for t in th]; [t.join() for t in th]
    wall = time.time() - w0
    worst_ttft = max(r[0] for r in res)
    # декод-фаза: от худшего TTFT до конца стены; сгенерировано ~256*N (chunks≈tokens при stream)
    total_ct = sum(r[2] for r in res)
    decode_wall = wall - worst_ttft
    per = [r[2] / (r[1] - r[0]) for r in res]
    agg = total_ct / decode_wall if decode_wall > 0 else 0
    print(f'N={N}, ctx~100 слов | стена {wall:.1f}с | худший TTFT {worst_ttft:.2f}с | '
          f'декод-агрегат {agg:.1f} ток/с | пер-поток мин/сред/макс '
          f'{min(per):.1f}/{sum(per)/len(per):.1f}/{max(per):.1f}', flush=True)
