"""Kindle highlights and notes, including those in personal documents sent to the Kindle, fetched from Amazon's Kindle services and stored in a SQLite file with the highlighted text resolved.

ksync talks to Amazon as a registered Kindle device, using credentials in `~/.config/ksync/auth.json`; the README says how to obtain them. Annotations carry only positions, so `sync` downloads each annotated document once into `~/.cache/ksync` and resolves the text with `kfxlib`, then stores `books` and `highlights` tables in `ksync.db` in the current folder. Purchased books are left out: their files are DRM protected. Documents that Amazon still serves in the old MOBI format, those sent before late 2022, get their highlights stored without text. `doc()` each function for its parameters.

- `sync()` fetches the library and every annotation changed since the last sync, stores them, and returns the new highlights and notes.
- `books()` lists the library as of the last sync.
- `highlights(book)` returns a book's highlights and notes in reading order, given a `books()` row or part of a title.

The file is plain SQLite, so query it directly with fastlite or any sqlite tool when the two readers are not enough.
"""

__all__ = ['books', 'highlights', 'sync']

from ksync.core import books, highlights, sync
