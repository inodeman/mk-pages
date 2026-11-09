#!/usr/bin/env python3
"""pages_enc.py: TODO el contenido del panel (repo publico inodeman/mk-pages) se publica CIFRADO (AES-256-GCM). Clave = PBKDF2-SHA256(PAGES_PASSWORD, ksalt, 100000), guardada solo en var/.pages_key (0600).
put(name,obj)       -> data/<name>.enc.json   {v,iv,ct,updated}   (JSON cifrado)
put_bytes(name,b,mime) -> data/<name>.enc.json (bytes en base64 dentro del JSON cifrado; p.ej. la grafica PNG)
data/config.json solo tiene {ksalt,iter} (sal publica de PBKDF2, sin hash de contrasena). data/check.enc.json permite al navegador validar la contrasena (GCM falla si es incorrecta).
NUNCA se escribe texto plano de datos en el repo. Nunca imprime clave ni contrasena."""
import os,json,base64,time,hashlib
R='/workspace/mk_pages_repo';V=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))+'/var'
def _k(): return json.load(open(V+'/.pages_key'))
def _enc(raw):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    k=_k();iv=os.urandom(12)
    return dict(v=2,iv=base64.b64encode(iv).decode(),ct=base64.b64encode(AESGCM(bytes.fromhex(k['key'])).encrypt(iv,raw,None)).decode(),updated=time.strftime('%F %T'))
def _seen(name):
    # t_fresh: marca 'el productor confirmo este dato ahora' aunque el contenido no haya cambiado (el watchdog del panel la usa para medir la edad real)
    try:
        d=V+'/pages_seen';os.makedirs(d,exist_ok=True);open(d+'/'+name,'w').write(str(time.time()))
    except Exception: pass
def _w(name,raw):
    _seen(name)
    h=hashlib.sha256(raw).hexdigest();hp=V+'/pages_enc_hash.json'
    try: H=json.load(open(hp))
    except Exception: H={}
    p=f'{R}/data/{name}.enc.json'
    if H.get(name)==h and os.path.exists(p) and json.load(open(p)).get('v')==2: return p   # sin cambios: no re-cifrar (evita commits inutiles)
    os.makedirs(R+'/data',exist_ok=True);open(p,'w').write(json.dumps(_enc(raw)));H[name]=h;json.dump(H,open(hp,'w'));return p
def put(name,obj): return _w(name,json.dumps(obj,ensure_ascii=False).encode())
def put_bytes(name,b,mime='image/png'): return _w(name,json.dumps(dict(mime=mime,b64=base64.b64encode(b).decode())).encode())
def check(): return _w('check',json.dumps({'ok':1,'k':_k()['ksalt']}).encode())
def decrypt(name):  # solo pruebas
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    d=json.load(open(f'{R}/data/{name}.enc.json'));return json.loads(AESGCM(bytes.fromhex(_k()['key'])).decrypt(base64.b64decode(d['iv']),base64.b64decode(d['ct']),None))
# Assets publicos del panel de ultima hora. No incluye el resto de panel/.
_KEEP_EXACT=('index.html','data/config.json','.nojekyll','hora.html','panel/hora.js')
def sweep():
    """borra cualquier archivo en claro que quede en el repo.
    Conserva index.html, data/config.json, .nojekyll, data/*.enc.json, hora.html y panel/hora.js."""
    out=[]
    for root,ds,fs in os.walk(R):
        if '/.git' in root: continue
        for f in fs:
            p=os.path.join(root,f);rel=os.path.relpath(p,R)
            if rel in _KEEP_EXACT or (rel.startswith('data/') and f.endswith('.enc.json')): continue
            os.remove(p);out.append(rel)
    return out
