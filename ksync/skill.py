"""Kindle highlights and notes, including those in personal documents sent to the Kindle, read from the Kindle for Mac app and stored in a SQLite file with the highlighted text resolved.

The app syncs your library and annotations from Amazon into databases in its container. Annotations hold only positions, so `sync` resolves the text from each downloaded book file with `kfxlib`, then stores `books` and `highlights` tables in `ksync.db` in the current folder. `doc()` each function for its parameters.

- `sync()` restarts the app so it fetches new annotations, stores everything, and returns the new highlights. Books the app has not downloaded are skipped; `Imp python -m ksync.download` makes the app download all of them through its own interface, which needs Imp with the Accessibility grant.
- `books()` lists the library as of the last sync.
- `highlights(book)` returns a book's highlights and notes in reading order, given a `books()` row or part of a title.

The file is plain SQLite, so query it directly with fastlite or any sqlite tool when the two readers are not enough.
"""

__all__ = ['books', 'highlights', 'sync']

from ksync.core import books, highlights, sync
