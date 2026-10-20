"""Kindle highlights and notes for close reading, pulled from Amazon into a local SQLite store.

    from ksync import *
    sync()
    ['Moonwalking with Einstein: 2 new']

    books()
    [Book(title='Moonwalking with Einstein', author='Joshua Foer', n=16),
     Book(title='Los hermanos Karamazov (13_20) (Spanish Edition)', author='Dostoyevski, Fiódor', n=2),
     Book(title='Remember, Remember', author='Ed Cooke', n=2), ...]

    hs = highlights('Outlive')
    print(hs[111])
    “Cancer, like insanity, seems to increase with the progress of civilization.” | Stanislas Tanchou

`highlights` takes part of a title or a `books()` row and returns the book's highlights oldest first, so the last ones are the newest. `print` gives the whole passage, then the note after ` | `; each has `text` and `note`. Credentials come from `~/.config/ksync/auth.json`, as the README describes. Only personal documents sent to the Kindle are covered.
"""

__all__ = ['books', 'highlights', 'sync']

from ksync.core import books, highlights, sync

