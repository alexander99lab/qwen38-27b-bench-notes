#!/usr/bin/env python3
# Vision-смоук: генерим PNG (красный квадрат на белом) без PIL, шлём в чат с картинкой.
import base64, json, os, struct, time, urllib.request, zlib

def png_red_square(w=224, h=224, sq=120):
    rows = b''
    x0 = (w - sq) // 2; y0 = (h - sq) // 2
    for y in range(h):
        row = b'\x00'
        for x in range(w):
            if x0 <= x < x0 + sq and y0 <= y < y0 + sq:
                row += b'\xff\x00\x00'
            else:
                row += b'\xff\xff\xff'
        rows += row
    def chunk(typ, data):
        c = struct.pack('>I', len(data)) + typ + data
        return c + struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))

b64 = base64.b64encode(png_red_square()).decode()
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer REDACTED'}
body = json.dumps({'model': 'qwen3.8-27b', 'max_tokens': 80, 'temperature': 0,
    'chat_template_kwargs': {'enable_thinking': False},
    'messages': [{'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b64}},
        {'type': 'text', 'text': 'Что изображено на картинке? Назови фигуру и цвет.'}]}]}).encode()
t0 = time.time()
d = json.load(urllib.request.urlopen(urllib.request.Request(
    os.environ.get('BENCH_URL', 'http://localhost:18020') + '/v1/chat/completions', body, H), timeout=600))
print(f'VISION-SMOKE ({time.time()-t0:.1f}с):', d['choices'][0]['message']['content'][:120].replace(chr(10), ' '))
print('prompt_tokens:', d['usage']['prompt_tokens'])
