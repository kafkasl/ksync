"Make the Kindle app download every book it has not downloaded yet, by pressing Download in each book's library context menu. Run under Imp for the Accessibility grant: `Imp python -m ksync.download`."

import subprocess, sys, time
from ApplicationServices import (AXUIElementCreateApplication, AXUIElementCopyAttributeValue, AXUIElementPerformAction,
    kAXChildrenAttribute, kAXRoleAttribute, kAXDescriptionAttribute, kAXValueAttribute)
from AppKit import NSWorkspace

def _attr(el, name):
    err, val = AXUIElementCopyAttributeValue(el, name, None)
    return val if err == 0 else None

def _walk(el):
    yield el, _attr(el, kAXRoleAttribute)
    for c in _attr(el, kAXChildrenAttribute) or []: yield from _walk(c)

def _find(root, role, pred, tries=20):
    "First element under `root` with `role` whose description satisfies `pred`, retrying while the view settles"
    for _ in range(tries):
        el = next((el for el, r in _walk(root) if r == role and pred(_attr(el, kAXDescriptionAttribute) or '')), None)
        if el is not None: return el
        time.sleep(0.25)

def download_all():
    "Page through the library grid and press Download on every book marked as not downloaded; returns the titles pressed"
    subprocess.run(['open', '-a', 'Amazon Kindle'], check=True)
    kindle = next(a for a in NSWorkspace.sharedWorkspace().runningApplications() if a.bundleIdentifier() == 'com.amazon.Lassen')
    while NSWorkspace.sharedWorkspace().frontmostApplication().bundleIdentifier() != 'com.amazon.Lassen': time.sleep(0.1)
    win = _attr(AXUIElementCreateApplication(kindle.processIdentifier()), 'AXMainWindow')
    cancel = _find(win, 'AXButton', lambda d: d == 'Cancel', tries=1)
    if cancel is not None:
        AXUIElementPerformAction(cancel, 'AXPress')
        time.sleep(1.5)
    grid = _find(win, 'AXGroup', lambda d: d == 'Library Grid View')
    for _ in range(50): AXUIElementPerformAction(grid, 'AXScrollUpByPage')
    done, idle = [], 0
    while idle < 3:
        pending = lambda el: _attr(el, kAXValueAttribute) == 'Book Not Downloaded' and _attr(el, kAXDescriptionAttribute) not in done
        fresh = [el for el, r in _walk(grid) if r == 'AXButton' and pending(el)]
        for el in fresh:
            AXUIElementPerformAction(el, 'AXShowMenu')
            AXUIElementPerformAction(_find(win, 'AXButton', lambda d: d == 'Download'), 'AXPress')
            done.append(_attr(el, kAXDescriptionAttribute))
            print(done[-1], file=sys.stderr)
        idle = 0 if fresh else idle + 1
        AXUIElementPerformAction(grid, 'AXScrollDownByPage')
        time.sleep(0.5)
    return done

if __name__ == '__main__': print(f'{len(download_all())} downloads started')
