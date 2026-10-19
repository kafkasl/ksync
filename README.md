# ksync

Kindle highlights and notes, fetched from Amazon's Kindle services and stored in a SQLite file with the highlighted text resolved. Personal documents sent to the Kindle are included, which the Kindle web notebook leaves out.

ksync talks to Amazon as a registered Kindle device, the same way the Kindle apps do. Annotations carry only positions, so `sync` downloads each annotated document once into `~/.cache/ksync` and resolves the text with `kfxlib`, vendored under `vendor/` from the KFX Input calibre plugin. Purchased books are left out: their files are DRM protected. Documents that Amazon still serves in the old MOBI format, those sent before late 2022, get their highlights stored without text.

    from ksync import *
    sync()                     # store into ksync.db, return what is new
    books()
    highlights('Moonwalking')

## Install

    pip install -e .

## Registering

Amazon hands a device its credentials when you sign in, and ksync reads them from `~/.config/ksync/auth.json`. Capture them once from the Kindle for Mac app:

1. Install [mitmproxy](https://mitmproxy.org), trust its CA and point the system proxy at it.
2. In the app, sign out, then sign in again.
3. Find the captured `POST https://api.amazon.<tld>/auth/register`. From its response take `tokens.mac_dms.device_private_key`, `tokens.mac_dms.adp_token`, `tokens.bearer.access_token` and `tokens.bearer.refresh_token`. From its request body take `registration_data.device_type` and `registration_data.device_serial`.
4. Write them to the file, with `domain` set to the host of that request and `issued` to the current Unix time:

        {"domain": "api.amazon.es", "device_type": "...", "device_serial": "...", "device_private_key": "-----BEGIN RSA PRIVATE KEY-----\n...",
         "adp_token": "{enc:...", "access_token": "Atna|...", "refresh_token": "Atnr|...", "issued": 1760000000}

5. Turn the proxy off and remove the mitmproxy CA from your keychain.

The access token lasts an hour and `sync` refreshes it. The other credentials last until you sign out of the app, remove the device on Amazon's "Manage Your Content and Devices" page, or change your Amazon password. When that happens `sync` fails with a message pointing here. The sign-in itself is an OAuth code flow with PKCE against `/ap/signin` followed by the `auth/register` call, so ksync could register its own device without the app. That is left out until the manual procedure is needed a second time.

