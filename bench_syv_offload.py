import json, time, urllib.request, random
import os
URL=os.environ.get('BENCH_URL', 'http://localhost:18020') + '/v1/chat/completions'
H={'Content-Type':'application/json','Authorization':'Bearer REDACTED'}
NL=chr(10); random.seed(7)
def doc(uid, sections):
    return NL.join('Раздел '+str(i)+' контракта '+str(uid)+'. Поставка партии '+str(uid)+'-'+str(i)+' за 30 дней, штраф '+str(i)+'%, приёмка по акту.' for i in range(1, sections+1))
DOCS={u: doc(u,300) for u in 'ABC'}          # ~16.5K ток
DOCS['G']=doc('G',350)                       # гигант ~100K ток
CODES={}
for u in DOCS:
    c=str(random.randint(100000,999999)); CODES[u]=c
    DOCS[u]+=NL+'Служебная отметка: КОД_ДОКУМЕНТА='+c+'.'
def ask(uid,q,mt=40):
    b=json.dumps({'model':'qwen3.8-27b','messages':[{'role':'user','content':DOCS[uid]+NL+q}],'max_tokens':mt,'temperature':0,'chat_template_kwargs':{'enable_thinking':False}}).encode()
    t0=time.time(); d=json.load(urllib.request.urlopen(urllib.request.Request(URL,b,H),timeout=1800))
    return time.time()-t0, d['choices'][0]['message'].get('content') or '', d['usage']['prompt_tokens']
t,_,pt=ask('G','Сколько разделов? Числом.'); print(f'ГИГАНТ префилл: {pt} ток за {t:.1f}с ({pt/t:.0f} ток/с)', flush=True)
t,a,_=ask('G','КОД_ДОКУМЕНТА? Только число.'); print(f'ГИГАНТ тёплый: {t:.2f}с | код {"ВЕРЕН" if CODES["G"] in a else "НЕВЕРЕН: "+a[:40]}', flush=True)
for u in 'ABC':
    for q in ('Сколько разделов? Числом.','Штраф раздела 3? Кратко.','Сроки разделов 1-5?'):
        t,_,_=ask(u,q,150)
    print(u,'отработал', flush=True)
t,a,_=ask('G','Назови КОД_ДОКУМЕНТА. Только число.')
print(f'ГИГАНТ возврат после вытеснения: {t:.2f}с | код {"ВЕРЕН" if CODES["G"] in a else "НЕВЕРЕН: "+a[:40]}', flush=True)
for u in 'AB':
    t,a,_=ask(u,'Назови КОД_ДОКУМЕНТА. Только число.')
    print(f'{u} возврат: {t:.2f}с | код {"ВЕРЕН" if CODES[u] in a else "НЕВЕРЕН"}', flush=True)
