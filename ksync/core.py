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
DB = 'ksync.db'
LOG = logging.getLogger('kfxlib')
LOG.setLevel(logging.ERROR)
QUERY = r"query ($book: KindleBookIdentifierInput!, $syncToken: String!) { syncAnnotations(book: $book, syncToken: $syncToken) { annotations { highlights { id creationDate lastModifiedDate startPosition endPosition } notes { id creationDate lastModifiedDate startPosition endPosition noteText } deleted } syncState { syncToken isSyncRequired } } }"

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
    return L(dict(id=m.findtext('ASIN'), title=m.findtext('title'), author=', '.join(x.text for x in m.iter('author')), type=m.findtext('cde_contenttype'), added=m.findtext('publication_date'))
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

def _annotations(book, token, a):
    "Highlights and notes of `book` changed since `token`, the ids deleted since, and the token for the next call"
    rows, deleted = L(), []
    while True:
        v = dict(book=dict(asin=book['id'], contentType='PDOC', embeddedId=book['embedded']), syncToken=token)
        r = httpx.post('https://sync.datamate.kindle.amazon.dev/graphql', headers={'authorization': f'Bearer {a["access_token"]}'}, json=dict(query=QUERY, variables=v), timeout=60)
        j = r.json()
        if j.get('errors'):
            if j['errors'][0]['extensions']['ErrorName'] != 'EMBEDDEDID_NOT_FOUND': raise RuntimeError(j['errors'][0]['message'])
            return rows, deleted, token
        s = j['data']['syncAnnotations']
        rows += L(dict(book=book['id'], id=x['id'], kind=k[:-1], start=int(x['startPosition']), end=int(x['endPosition']), note=x.get('noteText'), created=x['creationDate'], modified=x['lastModifiedDate'])
            for k in ('highlights', 'notes') for x in s['annotations'][k])
        deleted += s['annotations']['deleted']
        token = s['syncState']['syncToken']
        if not s['syncState']['isSyncRequired']: return rows, deleted, token

def _text(chunks, start, end):
    "Book text between KFX positions `start` and `end` inclusive"
    parts = (c.text[max(start - c.pid, 0):min(end - c.pid + 1, c.length)] for c in chunks if c.text and c.pid <= end and c.pid + c.length > start)
    return ' '.join(parts)

def _chunks(book, a):
    "Content chunks of personal document `book`, downloaded into `CACHE` the first time, or empty when Amazon has no KFX version of it"
    p = CACHE/f'{book["id"]}.azw8'
    if not p.exists():
        url = _manifest(book['id'], a)[1]
        if not url: return []
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(httpx.get(url, timeout=300).content)
    set_logger(LOG)
    yj = kfxlib.YJ_Book(str(p))
    yj.decode_book()
    return yj.collect_content_position_info()

def _fetch(book, old, a):
    "Annotations of `book` changed since its row in `old`, filling in its embedded id when first seen"
    o = old.get(book['id'], {})
    book['embedded'] = o.get('embedded') or _manifest(book['id'], a)[0]
    return _annotations(book, o.get('token', '0'), a)

def sync(db=DB): # SQLite file to fill with `books` and `highlights` tables
    "Fetch the library and every annotation changed since the last sync, store them, and return the new highlights and notes"
    a, d, new = _auth(), database(db), L()
    old = {b['id']: b for b in d.t.books()} if 'books' in d.t else {}
    lib = _library(a).filter(lambda b: b['type'] == 'PDOC')
    for b, (rows, deleted, token) in zip(lib, parallel(_fetch, lib, old=old, a=a, threadpool=True)):
        b['token'] = token
        if rows:
            chunks = _chunks(b, a)
            for r in rows: r['text'] = _text(chunks, r['start'], r['end']) if chunks else None
            d.t.highlights.upsert_all(rows, pk=('book', 'id'))
            new += rows
        for i in deleted: d.t.highlights.delete_where('book=? and id=?', (b['id'], i))
    d.t.books.upsert_all(lib, pk='id')
    return new

def books(db=DB): # SQLite file written by `sync`
    "The library as of the last `sync`, most recently added first"
    return L(database(db).t.books(order_by='added desc'))

def highlights(book, # A row from `books`, or part of a title
    db=DB, # SQLite file written by `sync`
):
    "Highlights and notes of `book`, in reading order"
    t = database(db).t
    bid = book['id'] if isinstance(book, dict) else first(t.books('title like ?', [f'%{book}%']))['id']
    return L(t.highlights('book=?', [bid], order_by='start'))

