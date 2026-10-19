"Kindle highlights and notes from the Kindle for Mac app, stored in SQLite."

__all__ = ['books', 'highlights', 'sync']

import json, sqlite3, subprocess, time
from fastcore.utils import *
from fastlite import database
import kfxlib

APP = Path.home()/'Library/Containers/com.amazon.Lassen/Data/Library'
DB = 'ksync.db'

def _ro(path): return sqlite3.connect(f'file:{path}?mode=ro', uri=True)

def _library():
    q = "select ZBOOKID, ZDISPLAYTITLE, ZRAWBOOKSTATE, ZPATH from ZBOOK where ZDISPLAYTITLE is not null and ZRAWISDICTIONARY is not 1 order by ZRAWLASTACCESSTIME desc"
    rows = _ro(APP/'Protected/BookData.sqlite').execute(q)
    return L(dict(id=i, asin=i[2:].rsplit('-', 1)[0], title=t, downloaded=s == 3, path=str(APP.parent/p)) for i, t, s, p in rows)

def _annotations(asin):
    q = "select annotation_id, dataset, created_time, modified_time, serialized_payload from server_view where dataset in (1,3) and dataset_id like ?"
    return _ro(next(APP.glob('KSDK/amzn1.account.*/ksdk_annotation_v1.db'))).execute(q, (f'{asin}%',)).fetchall()

def _text(chunks, start, end):
    "Book text between KFX positions `start` and `end` inclusive"
    parts = (c.text[max(start - c.pid, 0):min(end - c.pid + 1, c.length)] for c in chunks if c.text and c.pid <= end and c.pid + c.length > start)
    return ' '.join(parts)

def _resolve(book):
    "Annotations of a downloaded book with their text read from its KFX file"
    yj = kfxlib.YJ_Book(str(next(Path(book['path']).glob('*.azw8'))))
    yj.decode_book()
    chunks = yj.collect_content_position_info()
    res = L()
    for aid, ds, created, modified, payload in _annotations(book['asin']):
        p = json.loads(payload)
        s, e = p['start_position']['shortPosition'], p['end_position']['shortPosition']
        res.append(dict(id=aid, book=book['id'], kind='note' if ds == 3 else 'highlight', start=s, end=e, text=_text(chunks, s, e),
            note=json.loads(p['json_metadata']).get('note_text'), created=created, modified=modified))
    return res

def _relaunch(settle=5, timeout=90):
    "Restart the app, which makes it fetch new annotations, and wait until its annotation database stops changing"
    subprocess.run(['pkill', '-x', 'Kindle'])
    while subprocess.run(['pgrep', '-x', 'Kindle'], capture_output=True).returncode == 0: time.sleep(0.5)
    subprocess.run(['open', '-a', 'Amazon Kindle'], check=True)
    t0 = time.time()
    while time.time() - t0 < timeout:
        last = max(p.stat().st_mtime for p in APP.glob('KSDK/amzn1.account.*/ksdk_annotation_v1.db*'))
        if time.time() - max(last, t0) > settle: return
        time.sleep(1)

def sync(db=DB): # SQLite file to fill with `books` and `highlights` tables
    "Restart the Kindle app so it fetches new annotations, store the library and the annotations of every downloaded book, and return the new highlights"
    _relaunch()
    d, new = database(db), L()
    lib = _library()
    d.t.books.upsert_all(lib, pk='id')
    for b in lib:
        latest = max((r[3] for r in _annotations(b['asin'])), default=0)
        seen = first(d.q('select max(modified) m from highlights where book=?', (b['id'],)))['m'] or 0 if 'highlights' in d.t else 0
        if latest <= seen: continue
        hs = _resolve(b)
        d.t.highlights.upsert_all(hs, pk='id')
        new += hs.filter(lambda h: h['modified'] > seen)
    return new

def books(db=DB): # SQLite file written by `sync`
    "The library as of the last `sync`, most recently read first"
    return L(database(db).t.books())

def highlights(book, # A row from `books`, or part of a title
    db=DB, # SQLite file written by `sync`
):
    "Highlights and notes of `book`, in reading order"
    d = database(db)
    bid = book['id'] if isinstance(book, dict) else first(d.q('select id from books where title like ?', (f'%{book}%',)))['id']
    return L(d.q('select * from highlights where book=? order by start', (bid,)))
