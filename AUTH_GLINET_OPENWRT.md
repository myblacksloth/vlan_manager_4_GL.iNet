# Autenticazione GL.iNet 4.x e OpenWrt ubus RPC — Guida completa per implementazione browser

## TL;DR — Il problema centrale

Il browser **non ha** un'implementazione nativa di `unix crypt()`. La GUI GL.iNet 4.x usa la libreria npm `unixpass` (Node.js only) per generare l'hash della password. Questo non funziona in un file HTML standalone. Questo documento spiega come aggirare il problema con soluzioni concrete.

---

## 1. I due sistemi RPC a confronto

### 1A. OpenWrt standard (`/ubus`) — Login diretto senza challenge

Questo è il metodo **OpenWrt puro**, usato da LuCI, Home Assistant, e qualsiasi client standard.

**Endpoint:** `POST http://192.168.8.1/ubus`

**Step unico — login con password in chiaro:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "call",
  "params": [
    "00000000000000000000000000000000",
    "session",
    "login",
    {
      "username": "root",
      "password": "tuapassword"
    }
  ]
}
```

**Risposta con successo:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": [
    0,
    {
      "ubus_rpc_session": "c1ed6c7b025d0caca723a816fa61b668",
      "timeout": 300,
      "expires": 299,
      "acls": {
        "ubus": { "*": ["*"] }
      }
    }
  ]
}
```

Il token si chiama `ubus_rpc_session` (non `sid`). Usare `00000000000000000000000000000000` come session ID per il login iniziale.

**Requisiti sul router:**
- `uhttpd-mod-ubus` installato (già presente su OpenWrt 18.06+)
- `/etc/config/rpcd` deve avere entry per root:
  ```
  config login
    option username 'root'
    option password '$p$root'
    list read '*'
    list write '*'
  ```
  (`$p$root` = leggi la password da `/etc/shadow` per l'utente root)

---

### 1B. GL.iNet proprietario (`/rpc`) — Challenge + Unix crypt + MD5

Questo è il metodo **GL.iNet 4.x**, con autenticazione challenge-response a 4 step.

**Endpoint:** `POST http://192.168.8.1/rpc`

**Step 1 — Challenge:**
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "challenge",
  "params": { "username": "root" }
}
```

**Risposta:**
```json
{
  "id": null,
  "jsonrpc": "2.0",
  "result": {
    "alg": 1,
    "salt": "BSIUpXpe",
    "nonce": "T2FvXOB3DzLi6OugzpU9gvGE0RXXCe3D"
  }
}
```

- `alg`: algoritmo crypt — `1`=MD5, `5`=SHA-256, `6`=SHA-512 (Opal usa quasi sempre `1`)
- `salt`: salt per la funzione crypt unix
- `nonce`: token one-time, **valido solo 1000-2000ms** — i 4 step devono completarsi entro questo tempo

**Step 2 — Unix crypt della password:**
```
cipherPassword = unix_crypt(password, "$" + alg + "$" + salt + "$")
```

Esempi equivalenti:
```bash
# Shell
openssl passwd -1 -salt "BSIUpXpe" "tuapassword"
# → $1$BSIUpXpe$XXXXXXXXXXXXXXXXXXXXXXXXX

# Python
from passlib.hash import md5_crypt
cipher = md5_crypt.using(salt="BSIUpXpe").hash("tuapassword")

# Node.js
const up = require('unixpass');
const cipher = up.crypt("tuapassword", "$1$BSIUpXpe$");
```

**Step 3 — MD5 del triplo:**
```
hash = MD5("root:" + cipherPassword + ":" + nonce)
```

**Step 4 — Login:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "login",
  "params": {
    "username": "root",
    "hash": "hash_calcolato_al_step_3"
  }
}
```

**Risposta con successo:**
```json
{
  "id": 2,
  "jsonrpc": "2.0",
  "result": {
    "sid": "NsPHdkXtENoaotxVZWLqJorU52O7J0OI"
  }
}
```

Il token si chiama `sid` (non `ubus_rpc_session`).

**Codice sorgente originale GL.iNet** (decompilato dalla GUI):
```javascript
// Questo è il codice ESATTO estratto dal bundle Vue della GUI GL.iNet
const { alg: e, nonce: r, salt: n } = challengeResult;
const cipherPassword = this.$up.crypt(password, `$${e}$${n}$`);
const hash = this.$md5(username + ":" + cipherPassword + ":" + nonce);
this.login({ username: username, hash: hash });
```

---

## 2. Il problema con il browser: unix crypt non esiste in JS nativo

### Cos'è MD5crypt (alg=1)

MD5crypt (`$1$`) è un algoritmo definito da Poul-Henning Kamp nel 1994. **Non è semplicemente MD5** — è un algoritmo iterativo complesso che usa MD5 internamente ma con un processo di stretching specifico. Il formato output è:

```
$1$<salt>$<22-char-hash>
```

Il browser non ha `SubtleCrypto.digest('MD5-CRYPT', ...)` — esiste solo SHA-1, SHA-256, SHA-384, SHA-512.

### Soluzioni per implementarlo nel browser

#### Soluzione A — Implementazione JS pura di MD5crypt (RACCOMANDATA)

Esiste una implementazione JS standalone che riproduce esattamente `openssl passwd -1`. Il codice seguente è self-contained e non richiede librerie esterne:

```javascript
// MD5crypt puro JavaScript — compatibile con openssl passwd -1
// Basato sulla specifica originale di Poul-Henning Kamp
function md5crypt(password, salt) {
  // Estrai il salt pulito (rimuovi $1$ prefisso e $ finale se presenti)
  const cleanSalt = salt.replace(/^\$1\$/, '').replace(/\$$/, '').substring(0, 8);
  
  const magic = '$1$';
  const pw = strToBytes(password);
  const sl = strToBytes(cleanSalt);
  
  // Step A: crea digest A = MD5(password + magic + salt)
  let ctxA = md5init();
  md5update(ctxA, pw);
  md5update(ctxA, strToBytes(magic));
  md5update(ctxA, sl);
  
  // Step B: crea digest B = MD5(password + salt + password)
  let ctxB = md5init();
  md5update(ctxB, pw);
  md5update(ctxB, sl);
  md5update(ctxB, pw);
  const digestB = md5final(ctxB);
  
  // Step C: aggiungi byte di B in loop lungo quanto la password, poi frammenti
  let i = pw.length;
  while (i > 0) {
    md5update(ctxA, digestB.slice(0, Math.min(i, 16)));
    i -= 16;
  }
  
  // Step D: per ogni bit della lunghezza della password
  i = pw.length;
  while (i > 0) {
    if (i & 1) md5update(ctxA, [0]);
    else md5update(ctxA, [pw[0]]);
    i >>= 1;
  }
  
  let digestA = md5final(ctxA);
  
  // Step E: 1000 iterazioni
  for (let r = 0; r < 1000; r++) {
    let ctxC = md5init();
    if (r & 1) md5update(ctxC, pw);
    else md5update(ctxC, digestA);
    if (r % 3) md5update(ctxC, sl);
    if (r % 7) md5update(ctxC, pw);
    if (r & 1) md5update(ctxC, digestA);
    else md5update(ctxC, pw);
    digestA = md5final(ctxC);
  }
  
  // Step F: encoding finale (non base64 standard — ordine specifico MD5crypt)
  const to64 = './0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz';
  function enc(v, n) {
    let s = '';
    while (n-- > 0) { s += to64[v & 0x3f]; v >>= 6; }
    return s;
  }
  
  const d = digestA;
  let result = magic + cleanSalt + '$';
  result += enc((d[0]<<16)|(d[6]<<8)|d[12], 4);
  result += enc((d[1]<<16)|(d[7]<<8)|d[13], 4);
  result += enc((d[2]<<16)|(d[8]<<8)|d[14], 4);
  result += enc((d[3]<<16)|(d[9]<<8)|d[15], 4);
  result += enc((d[4]<<16)|(d[10]<<8)|d[5], 4);
  result += enc(d[11], 2);
  
  return result;
}

// Helper: converte stringa in array di byte
function strToBytes(str) {
  return Array.from(new TextEncoder().encode(str));
}
```

**IMPORTANTE**: questa funzione richiede un'implementazione MD5 che lavori su array di byte (`md5init`, `md5update`, `md5final`). Usa la libreria [blueimp/JavaScript-MD5](https://cdnjs.cloudflare.com/ajax/libs/blueimp-md5/2.19.0/js/md5.min.js) come base, oppure usa l'implementazione già presente nel file `vlan-manager.html` adattandola a lavorare byte per byte.

**Alternativa più semplice**: usare una libreria CDN già pronta:
```html
<!-- Aggiungere nel <head> -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/crypto-js/4.2.0/crypto-js.min.js"></script>
```

Purtroppo CryptoJS non include MD5crypt (`$1$`) — ha solo MD5 base.
La libreria npm `unixpass` non è disponibile via CDN in forma browser-ready.

#### Soluzione B — Usa `/ubus` invece di `/rpc` (PIÙ SEMPLICE)

Evita completamente il problema del crypt. Sul GL-SFT1200 (Opal) con OpenWrt 18.06, l'endpoint `/ubus` è disponibile se `uhttpd-mod-ubus` è installato.

```javascript
async function loginViaUbus(host, password) {
  const r = await fetch(`http://${host}/ubus`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 1,
      method: 'call',
      params: [
        '00000000000000000000000000000000',
        'session',
        'login',
        { username: 'root', password: password }
      ]
    })
  });
  const d = await r.json();
  // Controlla d.result[0] === 0 per successo
  return d.result[1].ubus_rpc_session;
}
```

Verificare disponibilità sul router:
```bash
curl -s http://192.168.8.1/ubus -d '{"jsonrpc":"2.0","id":1,"method":"list","params":["00000000000000000000000000000000","*"]}' | head -c 200
```

#### Soluzione C — Proxy locale Python (per sviluppo)

Se la pagina viene sviluppata in locale (non dal router), un piccolo server Python può fare da proxy e gestire il crypt lato server:

```python
#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
from passlib.hash import md5_crypt, sha256_crypt, sha512_crypt
import requests, json, hashlib

class Proxy(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if body.get('method') == 'login_proxy':
            # Gestisci crypt localmente
            p = body['params']
            if p['alg'] == 1:
                cipher = md5_crypt.using(salt=p['salt']).hash(p['password'])
            elif p['alg'] == 5:
                cipher = sha256_crypt.using(salt=p['salt'], rounds=5000).hash(p['password'])
            data = f"root:{cipher}:{p['nonce']}"
            hash_val = hashlib.md5(data.encode()).hexdigest()
            resp = {'hash': hash_val, 'cipher': cipher}
        else:
            # Passa al router
            r = requests.post('http://192.168.8.1/rpc', json=body)
            resp = r.json()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode())

HTTPServer(('127.0.0.1', 8765), Proxy).serve_forever()
```

---

## 3. Come funzionano le chiamate autenticate dopo il login

### Con `/rpc` (GL.iNet):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "call",
  "params": {
    "sid": "IL_TUO_SID",
    "service": "uci",
    "method": "get",
    "params": { "config": "network" }
  }
}
```

### Con `/ubus` (OpenWrt standard):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "call",
  "params": [
    "IL_TUO_UBUS_RPC_SESSION",
    "uci",
    "get",
    { "config": "network" }
  ]
}
```

La differenza strutturale è importante: `/rpc` usa un oggetto `params`, `/ubus` usa un array `params`.

---

## 4. Codici di errore comuni

| Codice | Significato | Causa tipica |
|---|---|---|
| `-32000` | Access denied | SID scaduto, hash sbagliato, ACL mancante |
| `-32002` | Access denied (ubus) | Metodo non permesso per questo utente |
| `6` | Object not found | Il servizio ubus non esiste sul router |
| `7` | No data | Il metodo esiste ma non ha restituito dati |

Il SID GL.iNet scade dopo **5 minuti** di inattività. Gestire il refresh.

---

## 5. CORS — problema critico per pagine HTML standalone

Il browser blocca le richieste cross-origin. Quando la pagina è servita da `http://192.168.8.1/vlan.html`, le richieste verso `http://192.168.8.1/rpc` sono **same-origin** e non hanno problemi CORS.

Se la pagina viene aperta come file locale (`file://`) o da un altro host, le richieste falliscono con errore CORS.

**Soluzione**: la pagina DEVE essere servita dallo stesso router. Deploy su:
```bash
scp vlan-manager.html root@192.168.8.1:/www/vlan.html
# Aprire http://192.168.8.1/vlan.html
```

Per sviluppo locale, verificare se `uhttpd` ha CORS abilitato:
```bash
# Sul router
cat /etc/config/uhttpd | grep -i cors
# Se non presente, aggiungere:
uci set uhttpd.main.cors='1'
uci commit uhttpd
/etc/init.d/uhttpd restart
```

---

## 6. Verificare lo stato dell'autenticazione sul router via SSH

```bash
# Verifica che rpcd sia in esecuzione
ps | grep rpcd

# Verifica la config rpcd
cat /etc/config/rpcd

# Test login diretto con curl (verifica che il sistema funzioni)
CHALLENGE=$(curl -s http://127.0.0.1/rpc -d '{"jsonrpc":"2.0","id":1,"method":"challenge","params":{"username":"root"}}')
echo $CHALLENGE

# Test login con /ubus (più semplice)
curl -s http://127.0.0.1/ubus -d '{
  "jsonrpc":"2.0","id":1,"method":"call",
  "params":["00000000000000000000000000000000","session","login",{"username":"root","password":"TUAPASSWORD"}]
}'

# Verifica che uhttpd-mod-ubus sia installato
opkg list-installed | grep ubus

# Lista servizi ubus disponibili
ubus list

# Verifica ACL root
cat /usr/share/rpcd/acl.d/*.json
```

---

## 7. Strategia consigliata per `vlan-manager.html`

### Approccio ibrido — tenta /ubus, fallback su /rpc

```javascript
async function doLogin(host, password) {
  // Tentativo 1: /ubus (semplice, nessun crypt necessario)
  try {
    const r = await fetch(`http://${host}/ubus`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: 1, method: 'call',
        params: ['00000000000000000000000000000000', 'session', 'login',
                 { username: 'root', password }]
      })
    });
    const d = await r.json();
    if (d.result && d.result[0] === 0 && d.result[1]?.ubus_rpc_session) {
      return { sid: d.result[1].ubus_rpc_session, endpoint: '/ubus', mode: 'ubus' };
    }
  } catch(e) {}

  // Tentativo 2: /rpc GL.iNet (richiede md5crypt)
  const ch = await rpc(host, 'challenge', { username: 'root' });
  const { alg, salt, nonce } = ch;
  const cipher = md5crypt(password, `$${alg}$${salt}$`); // ← funzione da implementare
  const hash = md5(`root:${cipher}:${nonce}`);
  const login = await rpc(host, 'login', { username: 'root', hash });
  if (login?.sid) {
    return { sid: login.sid, endpoint: '/rpc', mode: 'glinet' };
  }

  throw new Error('Autenticazione fallita su entrambi gli endpoint');
}
```

### Differenza nelle chiamate successive in base alla modalità

```javascript
async function apiCall(state, service, method, params = {}) {
  if (state.mode === 'ubus') {
    // Formato array per /ubus
    const r = await fetch(`http://${state.host}/ubus`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: Date.now(), method: 'call',
        params: [state.sid, service, method, params]
      })
    });
    const d = await r.json();
    if (d.result[0] !== 0) throw new Error(`ubus error: ${d.result[0]}`);
    return d.result[1];
  } else {
    // Formato oggetto per /rpc GL.iNet
    const r = await fetch(`http://${state.host}/rpc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0', id: Date.now(), method: 'call',
        params: { sid: state.sid, service, method, params }
      })
    });
    const d = await r.json();
    if (d.error) throw new Error(d.error.message);
    return d.result;
  }
}
```

---

## 8. Riferimenti

| Risorsa | URL | Note |
|---|---|---|
| OpenWrt wiki ubus | https://openwrt.org/docs/techref/ubus | Documentazione ufficiale rpcd/ACL |
| GL.iNet auth source (decompilato) | Forum gl-inet.com thread 49772 | Codice Vue originale con `$up.crypt` |
| GL.iNet SDK docs (cache) | https://dev.gl-inet.com/router-4.x-api/ | 403 al momento, usare cache Google |
| unixpass npm | https://www.npmjs.com/package/unixpass | Libreria usata da GL.iNet (Node only) |
| passlib Python | https://pypi.org/project/passlib/ | Per implementazione server-side |
| openssl passwd | `openssl passwd -1 -salt SALT PASS` | Riferimento per verifica output |
| rpcd source | https://github.com/openwrt/rpcd | Sorgente C del daemon |
