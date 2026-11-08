"""Desktop glue: tray icon + toasts (only while notifications are on), PIN hashing, same-series titles."""

import hashlib
import hmac
import re
import secrets

try:
    import pystray
except Exception:          # optional: without it the app simply has no tray icon or toasts
    pystray = None
HAVE_TRAY = pystray is not None


class Tray:
    """Tray icon on its own thread; menu clicks are handed to `post` so they run on the Tk thread.

    pystray's thread is not a daemon, so stop() has to run on every way out of the app.
    """

    def __init__(self, image, post, entries):
        self.icon = None
        if pystray is None:
            return

        def wrap(fn):
            return lambda icon, item: post(fn)

        try:
            menu = pystray.Menu(*[pystray.MenuItem(label, wrap(fn), default=dflt) for label, fn, dflt in entries])
            self.icon = pystray.Icon("SabljaReader", image, "Sablja Reader", menu)
        except Exception:
            self.icon = None

    def start(self):
        if self.icon is None:
            return False
        try:
            self.icon.run_detached()
            return True
        except Exception:
            self.icon = None
            return False

    def notify(self, title, text):
        """A Windows toast (balloon) from the tray icon; the OS caps title and body lengths."""
        if self.icon is None:
            return
        try:
            self.icon.notify(text[:250], title[:60])
        except Exception:
            pass

    def stop(self):
        icon, self.icon = self.icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:
                pass


# ---------------- PIN ----------------
def pin_hash(pin, salt=None):
    """'salt$hash' (PBKDF2-SHA256). Only the hash is stored in db.json, never the PIN."""
    salt = salt or secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(salt), 120_000).hex()
    return f"{salt}${h}"


def pin_ok(pin, stored):
    try:
        salt = stored.split("$", 1)[0]
        return hmac.compare_digest(pin_hash(pin, salt), stored)
    except Exception:
        return False


# ---------------- same series, different source ----------------
_TITLE_NOISE = re.compile(r"\b(manga|manhwa|manhua|webtoon|comic)\b")


def norm_title(title):
    """Title reduced to what two sources agree on: case, punctuation and 'manga'/'manhwa' tags dropped."""
    t = re.sub(r"[\W_]+", " ", (title or "").casefold())
    return " ".join(_TITLE_NOISE.sub(" ", t).split())
