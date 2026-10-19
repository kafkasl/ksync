# ksync

Kindle highlights and notes, read from the Kindle for Mac app and stored in a SQLite file with the highlighted text resolved. Personal documents sent to the Kindle are included, which the Kindle web notebook leaves out.

The app syncs your library and annotations from Amazon into databases in its container. Annotations carry only positions, so `ksync` resolves the text from the downloaded book file with `kfxlib`, vendored under `vendor/` from the KFX Input calibre plugin.

    from ksync import *
    sync()                     # restart the app, store into ksync.db, return what is new
    books()
    highlights('Moonwalking')

`sync` only sees books the app has downloaded. To make the app download the whole library, once or whenever new books arrive, run `Imp python -m ksync.download`. It presses Download in each book's context menu, which needs [Imp](https://github.com/AnswerDotAI/imp) holding the Accessibility grant: `Imp --grant accessibility`.

## Install

    pip install -e .
