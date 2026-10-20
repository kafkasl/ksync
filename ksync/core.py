"Kindle highlights and notes, fetched from Amazon's Kindle services and stored in SQLite."

__all__ = ['books', 'highlights', 'sync']

import json, base64, time, httpx, xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from fastcore.utils import *
from fastlite import database
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
import kfxlib, logging
from kfxlib.message_logging import set_logger

AUTH = Path.home()/'.config/ksync/auth.json'
CACHE = Path.home()/'.cache/ksync'
DB = Path.home()/'.local/share/ksync/ksync.db'
LOG = logging.getLogger('kfxlib')
LOG.setLevel(logging.ERROR)
QUERY = r"query ($book: KindleBookIdentifierInput!, $syncToken: String!) { syncAnnotations(book: $book, syncToken: $syncToken) { annotations { highlights { id creationDate lastModifiedDate startPosition endPosition } notes { id creationDate lastModifiedDate startPosition endPosition noteText } } syncState { syncToken isSyncRequired } } }"

class Book:
    id:str; title:str; author:str; type:str; added:str
    embedded:str=None # Content id that Amazon's annotation service keys on
    n = 0 # Number of annotations, set by `books`
    __repr__ = basic_repr('title,author,n')

class Highlight:
    book:str; id:str; start:int; end:int; created:str; modified:str
    text:str # The highlighted passage
    note:str=None # What the reader typed, if anything
    def __repr__(self): return f'Highlight({truncstr(self.text, 70)!r}' + (f', note={truncstr(self.note, 50)!r}' if self.note else '') + ')'
    def __str__(self): return self.text + (f' | {self.note}' if self.note else '')
    def _repr_markdown_(self): return f'> {self.text}' + (f'\n>\n> **Note:** {self.note}' if self.note else '')

def _db(path):
    "The `books` and `highlights` tables of the store at `path`, created if missing, with `Book` and `Highlight` rows"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    d = database(path)
    return d.create(Book, name='books', pk='id'), d.create(Highlight, name='highlights', pk=('book', 'id'))

def _auth():
    "Device credentials from `AUTH`, with the access token refreshed once it is older than an hour"
    a = json.loads(AUTH.read_text())
    if time.time() - a['issued'] > 3000:
        r = httpx.post(f'https://{a["domain"]}/auth/token', data=dict(app_name='Kindle for iOS', app_version='7.69.0.100', source_token_type='refresh_token', source_token=a['refresh_token'], requested_token_type='access_token'))
        if r.is_error: raise RuntimeError(f'Refreshing the access token failed with status {r.status_code}. Register again as the README describes.')
        a.update(access_token=r.json()['access_token'], issued=int(time.time()))
        AUTH.write_text(json.dumps(a, indent=1))
    return a

def _get(url, a, **headers):
    "GET `url` signed as the registered device"
    u, date = urlsplit(url), time.strftime('%Y-%m-%dT%H:%M:%S+0000', time.gmtime())
    key = serialization.load_pem_private_key(a['device_private_key'].encode(), None)
    data = f'GET\n{u.path}{"?" + u.query if u.query else ""}\n{date}\n\n{a["adp_token"]}'.encode()
    sig = base64.b64encode(key.sign(data, padding.PKCS1v15(), hashes.SHA256())).decode()
    r = httpx.get(url, headers={'x-adp-token': a['adp_token'], 'x-adp-alg': 'SHA256withRSA:1.0', 'x-adp-signature': f'{sig}:{date}', **headers}, timeout=60)
    r.raise_for_status()
    return r

def _library(a):
    "Every item in the Kindle library"
    r = _get('https://todo-ta-g7g.amazon.com/FionaTodoListProxy/syncMetaData?item_count=1000', a)
    return L(Book(m.findtext('ASIN'), m.findtext('title'), ', '.join(x.text for x in m.iter('author')), m.findtext('cde_contenttype'), m.findtext('publication_date'))
        for m in ET.fromstring(r.text).iter('meta_data'))

def _manifest(asin, a):
    "Embedded id of personal document `asin`, and a one-hour download URL when Amazon serves it as KFX"
    h = {'x-adp-reason': 'ArchivedItems', 'x-adp-transport': 'WiFi', 'x-adp-attemptcount': '1', 'x-adp-sw': '1191420554', 'accept-language': 'en-US',
        'x-amzn-accept-type': 'application/x.amzn.digital.deliverymanifest@1.0',
        'x-adp-correlationid': f'Device:{a["device_type"]}:{a["device_serial"]};kindle.PDOC:{asin}:{int(time.time() * 1000)}'}
    r = _get(f'https://kindle-digital-delivery.amazon.com/delivery/manifest/kindle.pdoc/{asin}', a, **h)
    res = r.json()['resources']
    kfx = first(res, lambda x: x.get('type') == 'KINDLE_MAIN_BASE')
    return res[0]['id'], kfx and kfx['optimalEndpoint']['directUrl']

def _annotations(book, c):
    "Every highlight and note of `book`"
    rows, token = L(), '0'
    while True:
        v = dict(book=dict(asin=book.id, contentType='PDOC', embeddedId=book.embedded), syncToken=token)
        r = c.post('https://sync.datamate.kindle.amazon.dev/graphql', json=dict(query=QUERY, variables=v), timeout=60)
        j = r.json()
        if j.get('errors'):
            if j['errors'][0]['extensions']['ErrorName'] != 'EMBEDDEDID_NOT_FOUND': raise RuntimeError(j['errors'][0]['message'])
            return rows
        s = j['data']['syncAnnotations']
        rows += L(AttrDict(id=x['id'], start=int(x['startPosition']), end=int(x['endPosition']), created=_when(x['creationDate']), modified=_when(x['lastModifiedDate']), note=x.get('noteText'))
            for k in ('highlights', 'notes') for x in s['annotations'][k])
        if not s['syncState']['isSyncRequired']: return rows
        token = s['syncState']['syncToken']

def _when(ms): return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ms / 1000))


def _text(chunks, start, end):
    "Book text between KFX positions `start` and `end` inclusive"
    parts = (c.text[max(start - c.pid, 0):min(end - c.pid + 1, c.length)] for c in chunks if c.text and c.pid <= end and c.pid + c.length > start)
    return ' '.join(parts)

def _chunks(book, a):
    "Content chunks of personal document `book`, downloaded into `CACHE` the first time, or empty when Amazon has no KFX version of it"
    p = CACHE/f'{book.id}.azw8'
    if not p.exists():
        url = _manifest(book.id, a)[1]
        if not url: return []
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(httpx.get(url, timeout=300).content)
    set_logger(LOG)
    yj = kfxlib.YJ_Book(str(p))
    yj.decode_book()
    return yj.collect_content_position_info()

def _merge(rows):
    "Annotations `rows` as one per passage: a note goes onto the highlight covering its range, or stands on its own"
    hls, notes = rows.filter(lambda r: not r.id.startswith('kindle.note')), rows.filter(lambda r: r.id.startswith('kindle.note'))
    for n in notes:
        h = first(hls, lambda h: h.start <= n.start and h.end >= n.end)
        if h: h.note, h.modified = n.note, max(h.modified, n.modified)
        else: hls.append(n)
    return hls

def _fetch(book, old, a, c):
    "Current annotations of `book`, one per passage, filling in its embedded id when first seen"
    o = old.get(book.id)
    book.embedded = o.embedded if o else _manifest(book.id, a)[0]
    return _merge(_annotations(book, c))

def sync(db=DB): # SQLite file to fill with `books` and `highlights` tables
    "Fetch the library and the current annotations of every book, replace the store with them, and say how many new ones each book got"
    a, (bt, ht), new = _auth(), _db(db), L()
    old = {b.id: b for b in bt()}
    lib = _library(a).filter(lambda b: b.type == 'PDOC')
    with httpx.Client(headers={'authorization': f'Bearer {a["access_token"]}'}) as c:
        fetched = parallel(_fetch, lib, old=old, a=a, c=c, threadpool=True, n_workers=32)
    for b, rows in zip(lib, fetched):
        had = {h.id: h for h in ht('book=?', [b.id])}
        kept = {r.id for r in rows if r.id in had and (had[r.id].start, had[r.id].end) == (r.start, r.end)}
        fresh = rows.filter(lambda r: r.id not in kept)
        chunks = _chunks(b, a) if fresh else []
        if fresh and not chunks:
            new.append(f'{b.title}: {len(fresh)} skipped, Amazon has no KFX version of it')
            continue
        if fresh: new.append(f'{b.title}: {len(fresh)} new')
        hls = L(Highlight(b.id, r.id, r.start, r.end, r.created, r.modified, had[r.id].text if r.id in kept else _text(chunks, r.start, r.end), r.note)
            for r in rows)
        ht.delete_where('book=?', [b.id])
        if hls: ht.insert_all(hls)
    bt.upsert_all(lib, pk=bt.pks)
    return new

def books(db=DB): # SQLite file written by `sync`
    "Books with annotations as of the last `sync`, most recently annotated first, with their number of annotations in `n`"
    bt, ht = _db(db)
    res = L()
    for r in ht.db.q('select book, count(*) n, max(modified) last from highlights group by book order by last desc'):
        b = bt[r['book']]
        b.n = r['n']
        res.append(b)
    return res

def highlights(book, # A row from `books`, or part of a title
    db=DB, # SQLite file written by `sync`
):
    "Highlights and notes of `book`, oldest first, so the last ones are the newest"
    bt, ht = _db(db)
    bid = book.id if isinstance(book, Book) else first(bt('title like ?', [f'%{book}%'])).id
    return L(ht('book=?', [bid], order_by='created'))

