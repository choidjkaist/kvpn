"""Read fresh, sender-bound KAIST OTPs locally. Never print or persist message bodies."""
from contextlib import closing
import re
import os
import sys
import sqlite3
import time
from pathlib import Path

APPLE_EPOCH = 978307200

class SMSError(Exception):
    pass


def extract_code(text):
    # Both KAIST identity and authentication context must be present.
    if not re.search(r'KAIST|카이스트|한국과학기술원|kvpn', text, re.I):
        return None
    if not re.search(r'인증|verification|authentication|one.time|OTP', text, re.I):
        return None
    codes = set(re.findall(r'(?<![\dA-Za-z])\d{6}(?![\dA-Za-z])', text))
    return next(iter(codes)) if len(codes) == 1 else None


def payload(text, blob):
    if text:
        return text
    # Conservative fallback for NSAttributedString archives: retain UTF-8 text;
    # require strong context and one unambiguous six-digit sequence below.
    return bytes(blob or b'').decode('utf-8', errors='ignore')


class SMSReader:
    def __init__(self, path=None):
        self.path = Path(path or Path.home() / 'Library/Messages/chat.db')

    def connect(self):
        # Diagnose the actual failing layer; never label every SQLite error FDA.
        try:
            fd = os.open(self.path, os.O_RDONLY)
            os.close(fd)
        except FileNotFoundError:
            raise SMSError('Messages database does not exist for this macOS account. Open Messages and check SMS synchronization.') from None
        except PermissionError as error:
            host = os.environ.get('TERM_PROGRAM', '').strip()
            host = {'ghostty': 'Ghostty', 'Apple_Terminal': 'Terminal', 'iTerm.app': 'iTerm'}.get(host, host or 'the app hosting this command')
            raise SMSError('macOS denied direct file access to Messages (errno %s). Enable Full Disk Access for %s in System Settings > Privacy & Security > Full Disk Access, then fully quit and reopen that app. Permission granted to a different terminal or ChatGPT does not transfer.' % (error.errno, host)) from None
        except OSError as error:
            raise SMSError('Messages file access failed (errno %s).' % error.errno) from None
        db = None
        try:
            db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=2)
            db.execute('PRAGMA query_only=ON')
            db.execute('SELECT ROWID, date, text, attributedBody, handle_id, is_from_me FROM message LIMIT 0')
            return db
        except sqlite3.Error as error:
            if db is not None:
                db.close()
            raise SMSError('Messages file is readable, but SQLite failed: %s (%s). Do not reset permissions solely on this error.' %
                           (str(error), getattr(error, 'sqlite_errorname', 'SQLite error'))) from None

    def diagnostics(self):
        # Metadata only; no message contents, authentication data or config values.
        print('Python:', sys.executable)
        print('SQLite:', sqlite3.sqlite_version)
        print('Terminal host:', os.environ.get('TERM_PROGRAM', 'unknown'))
        print('Messages database:', self.path)
        with closing(self.connect()) as db:
            print('Messages file and schema: readable')
        return True

    def baseline(self):
        with closing(self.connect()) as db:
            value = db.execute('SELECT coalesce(max(ROWID),0) FROM message').fetchone()[0]
        return value, int(time.time())

    def rows(self, since, rowid=0):
        with closing(self.connect()) as db:
            return db.execute('''SELECT m.ROWID, h.id, m.text, m.attributedBody
                FROM message m JOIN handle h ON h.ROWID=m.handle_id
                WHERE m.is_from_me=0 AND m.ROWID>? AND m.date>=?
                ORDER BY m.ROWID DESC LIMIT 200''',
                (rowid, int((since-APPLE_EPOCH)*1e9))).fetchall()

    def discover_sender(self):
        senders = {sender for _,sender,text,blob in self.rows(time.time()-30*86400)
                   if re.search(r'\bKVPN\b', payload(text,blob), re.I)
                   and extract_code(payload(text,blob))}
        if len(senders) != 1:
            raise SMSError('No unique KVPN-specific OTP sender found in recent Messages. Run sms-check after a normal KAIST SMS login, or specify --sms-sender with the verified sender. No SMS was requested.')
        return next(iter(senders))

    def wait(self, sender, baseline, timeout=120, cancelled=lambda: False):
        rowid, requested_at = baseline
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cancelled():
                raise SMSError('Automatic login stopped.')
            codes = {extract_code(payload(text,blob)) for _,source,text,blob
                     in self.rows(requested_at, rowid) if source == sender}
            codes.discard(None)
            if len(codes) > 1:
                raise SMSError('Multiple fresh KAIST codes found; refusing ambiguous authentication.')
            if codes:
                return next(iter(codes))
            time.sleep(2)
        raise SMSError('No fresh matching KAIST SMS arrived within 120 seconds. No additional SMS requested.')
