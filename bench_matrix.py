#!/usr/bin/env python3
# Матрица syv+offload: лесенка N=1..8 (пер-стрим + агрегат) + пирамида RAM/fs.
# usage: python3 bench_matrix.py --label cfg2 --pool 23000 --bpt 95000 [--ram-gib 8] [--heavy]
import argparse, json, threading, time, urllib.request, random, sys

import os
URL = os.environ.get('BENCH_URL', 'http://localhost:18020') + '/v1/chat/completions'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer REDACTED'}
NL = chr(10)

ap = argparse.ArgumentParser()
ap.add_argument('--label', required=True)
ap.add_argument('--pool', type=int, required=True, help='GPU pool tokens (from boot log)')
ap.add_argument('--bpt', type=int, required=True, help='KV bytes per token (95000 bf16 / 17000 kvarn)')
ap.add_argument('--ram-gib', type=float, default=8.0)
ap.add_argument('--gen', type=int, default=300)
ap.add_argument('--doc-tok', type=int, default=11000)
ap.add_argument('--skip-pyramid', action='store_true')
ap.add_argument('--skip-ladder', action='store_true')
ap.add_argument('--max-fs-docs', type=int, default=60)
args = ap.parse_args()
random.seed(hash(args.label) & 0xffff)

def mktext(uid, tokens):
    # ~55 токенов на строку-раздел
    n = max(3, tokens // 55)
    return NL.join(
        f'Раздел {i} контракта {uid}. Поставка партии {uid}-{i} за 30 дней, штраф {i}%, приёмка по акту.'
        for i in range(1, n + 1))

def ask(content, mt, timeout=3600):
    b = json.dumps({'model': 'qwen3.8-27b',
                    'messages': [{'role': 'user', 'content': content}],
                    'max_tokens': mt, 'temperature': 0,
                    'chat_template_kwargs': {'enable_thinking': False}}).encode()
    t0 = time.time()
    d = json.load(urllib.request.urlopen(urllib.request.Request(URL, b, H), timeout=timeout))
    dt = time.time() - t0
    ch = d['choices'][0]['message']
    return dt, (ch.get('content') or ''), d['usage']['completion_tokens'], d['usage']['prompt_tokens']

def ladder(tag, ctx_tokens):
    print(f'--- ЛЕСЕНКА {tag} (контекст ~{ctx_tokens} ток/поток, ген {args.gen}) ---', flush=True)
    for N in range(1, 9):
        res = [None] * N
        def worker(i):
            uid = f'{args.label}-{tag}-N{N}-S{i}-{random.randint(0,99999)}'
            body = mktext(uid, ctx_tokens) + NL + 'Подробно перескажи разделы документа своими словами.'
            try:
                res[i] = ask(body, args.gen)
            except Exception as e:
                res[i] = ('ERR', str(e)[:60], 0, 0)
        th = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
        w0 = time.time()
        [t.start() for t in th]; [t.join() for t in th]
        wall = time.time() - w0
        ok = [r for r in res if r and r[0] != 'ERR']
        errs = len(res) - len(ok)
        if not ok:
            print(f'N={N}: ВСЕ ОШИБКИ: {res[0][1]}', flush=True); continue
        per = [r[2] / r[0] for r in ok]
        agg = sum(r[2] for r in ok) / wall
        per_s = '/'.join(f'{p:.0f}' for p in per)
        print(f'N={N}: пер-стрим {per_s} (сред {sum(per)/len(per):.1f}), агрегат {agg:.0f} ток/с, wall {wall:.1f}с'
              + (f', ошибок {errs}' if errs else ''), flush=True)

def pyramid():
    # Паттерн рабочих чатов: несколько ходов на документ, возврат к СТАРЫМ докам.
    # Вытеснение крупным куском (новый большой префилл) выгружается в тир и хитит;
    # возврат к только-что-вытесненному порционно — заведомый пересчёт (метим).
    print('--- ПИРАМИДА вытеснения ---', flush=True)
    codes = {}
    def doc(uid):
        if uid not in codes:
            codes[uid] = str(random.randint(100000, 999999))
        return mktext(uid, args.doc_tok) + NL + f'Служебная отметка: КОД_ДОКУМЕНТА={codes[uid]}.'
    def rounds(uid, n=3):
        qs = ['Сколько разделов? Числом.', 'Штраф раздела 3? Кратко.', 'Сроки разделов 1-5?']
        for q in qs[:n]:
            ask(doc(uid) + NL + q, 60)
    # Геометрия «крупного вытеснения»: G + 3 дока = ~1.15 пула. Вытеснение
    # происходит крупными событиями (следующий большой префилл), а не мелкой
    # эрозией — только такие куски записываются в тир (mamba-чанки).
    dt = min(16000, max(4000, args.pool // 4))
    gt = int(dt * 1.2)
    def docn(uid, tokens):
        if uid not in codes:
            codes[uid] = str(random.randint(100000, 999999))
        return mktext(uid, tokens) + NL + f'Служебная отметка: КОД_ДОКУМЕНТА={codes[uid]}.'
    G = f'{args.label}-G'
    t, _, _, pt = ask(docn(G, gt) + NL + 'Сколько разделов? Числом.', 30)
    print(f'G префилл: {pt} ток за {t:.1f}с ({pt/t:.0f} ток/с)', flush=True)
    t, a, _, _ = ask(docn(G, gt) + NL + 'КОД_ДОКУМЕНТА? Только число.', 30)
    print(f'G тёплый (GPU-хит): {t:.2f}с | код {"ВЕРЕН" if codes[G] in a else "НЕВЕРЕН: " + a[:30]}', flush=True)
    n_ev = max(3, (args.pool - gt) // dt + 1)
    ev = [f'{args.label}-P{i}' for i in range(n_ev)]
    for u in ev:
        for q in ('Сколько разделов? Числом.', 'Штраф раздела 3? Кратко.', 'Сроки разделов 1-5?'):
            ask(docn(u, dt) + NL + q, 60)
    print(f'прогнаны {len(ev)} док по {dt} ток × 3 хода (сумма с G ~{(gt+3*dt)//1000}K на пул {args.pool//1000}K)', flush=True)
    t, a, _, _ = ask(docn(G, gt) + NL + 'Назови КОД_ДОКУМЕНТА. Только число.', 30)
    print(f'G возврат (свежевытесн., ожид. пересчёт): {t:.2f}с | код {"ВЕРЕН" if codes[G] in a else "НЕВЕРЕН"}', flush=True)
    for u in ev[:2]:
        t, a, _, _ = ask(docn(u, dt) + NL + 'Назови КОД_ДОКУМЕНТА. Только число.', 30)
        print(f'{u[-2:]} возврат из RAM-тира: {t:.2f}с | код {"ВЕРЕН" if codes[u] in a else "НЕВЕРЕН"}', flush=True)

print(f'=== КОНФИГ {args.label} | пул {args.pool} ток | {args.bpt} Б/ток ===', flush=True)
if not args.skip_ladder:
    ladder('LIGHT', 1500)
    heavy_ctx = min(10000, max(2000, args.pool // 9))
    if heavy_ctx >= 4000:
        ladder('HEAVY', heavy_ctx)
    else:
        print(f'HEAVY пропущена: пул {args.pool} мал (на поток вышло бы {heavy_ctx})', flush=True)
if not args.skip_pyramid:
    pyramid()
print('=== ГОТОВО ===', flush=True)
