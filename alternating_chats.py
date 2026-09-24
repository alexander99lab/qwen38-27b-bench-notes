#!/usr/bin/env python3
# Сценарий #174: два длинных чата чередуются ходами. Мерим время хода (TTFT+ответ)
# и дельту prefix-хитов из /metrics. Ход 1 каждого чата — холодный префилл (норма),
# дальше при здоровом retention ход должен стоить ~1-3с, при dense-провале — полный пересчёт.
# usage: BENCH_URL=http://localhost:18020 python3 alternating_chats.py [ctx_tokens=32000] [turns=4]
import json, os, sys, time, urllib.request, random

URL = os.environ.get('BENCH_URL', 'http://localhost:18020')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + os.environ.get('BENCH_KEY', 'REDACTED')}
CTX = int(sys.argv[1]) if len(sys.argv) > 1 else 32000
TURNS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
CHATS = 'ABCDEFGH'[:int(sys.argv[3])] if len(sys.argv) > 3 else 'AB'
NL = chr(10)
random.seed(174)

def doc(uid, tokens):
    n = max(3, tokens // 55)
    return NL.join(f'Раздел {i} контракта {uid}. Поставка партии {uid}-{i} за 30 дней, штраф {i}%, приёмка по акту.'
                   for i in range(1, n + 1))

def metric(name):
    # auth-deny-default (0.29): /metrics тоже под ключом
    txt = urllib.request.urlopen(urllib.request.Request(URL + '/metrics', headers=H), timeout=30).read().decode()
    for line in txt.splitlines():
        if line.startswith('vllm:' + name) and not line.startswith('#'):
            return float(line.rsplit(' ', 1)[1])
    return 0.0

def turn(history, q):
    history = history + [{'role': 'user', 'content': q}]
    b = json.dumps({'model': 'qwen3.8-27b', 'messages': history, 'max_tokens': 60, 'temperature': 0,
                    'chat_template_kwargs': {'enable_thinking': False}}).encode()
    q0, h0 = metric('prefix_cache_queries_total'), metric('prefix_cache_hits_total')
    t0 = time.time()
    d = json.load(urllib.request.urlopen(urllib.request.Request(URL + '/v1/chat/completions', b, H), timeout=3600))
    dt = time.time() - t0
    q1, h1 = metric('prefix_cache_queries_total'), metric('prefix_cache_hits_total')
    hit = (h1 - h0) / (q1 - q0) * 100 if q1 > q0 else 0.0
    ans = d['choices'][0]['message']['content'] or ''
    return history + [{'role': 'assistant', 'content': ans}], dt, hit, d['usage']['prompt_tokens']

chats = {c: [{'role': 'user', 'content': doc(c, CTX) + NL + 'Прочитай документ. Ответь: сколько разделов? Числом.'}] for c in CHATS}
qs = ['Каков штраф в разделе 7? Кратко.', 'Срок поставки партии 12? Кратко.', 'Назови номер раздела с штрафом 15%.', 'Сколько всего разделов? Числом.']
print(f'=== {len(CHATS)} чата по ~{CTX} ток, {TURNS} хода по очереди ===', flush=True)
off0 = metric('kv_offload_total_bytes_total{engine="0",model_name="qwen3.8-27b",transfer_type="CPU_to_GPU"}')
for c in CHATS:
    hist = chats[c]
    b = json.dumps({'model': 'qwen3.8-27b', 'messages': hist, 'max_tokens': 20, 'temperature': 0,
                    'chat_template_kwargs': {'enable_thinking': False}}).encode()
    t0 = time.time(); d = json.load(urllib.request.urlopen(urllib.request.Request(URL + '/v1/chat/completions', b, H), timeout=3600))
    chats[c] = hist + [{'role': 'assistant', 'content': d['choices'][0]['message']['content'] or ''}]
    print(f'чат {c} ход 1 (холодный префилл {d["usage"]["prompt_tokens"]} ток): {time.time()-t0:.1f}с', flush=True)
for t in range(TURNS):
    for c in CHATS:
        chats[c], dt, hit, pt = turn(chats[c], qs[t % len(qs)])
        print(f'чат {c} ход {t+2}: {dt:.2f}с | prefix hit {hit:.0f}% | промпт {pt} ток', flush=True)

off1 = metric('kv_offload_total_bytes_total{engine="0",model_name="qwen3.8-27b",transfer_type="CPU_to_GPU"}')
print(f'подъёмов из RAM-тира за тест: {(off1-off0)/1e9:.2f} ГБ', flush=True)
