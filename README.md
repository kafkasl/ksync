# ksync

Sync Kindle highlights and notes from read.amazon.com/notebook to markdown, one file per book.

There is no login code. A separate, persistent Chrome profile holds the Amazon session, and every fetch runs inside a tab of that profile. When the session expires, sync fails with the command to run:

    ksync-auth

It opens the browser on the notebook page, waits for you to sign in, and exits. Then:

    ksync path/to/notes

## Install

    pip install -e .
