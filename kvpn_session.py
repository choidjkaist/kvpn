"""Bounded, read-only discovery of the authenticated gateway's session UI.

Raw HTML, cookies and authentication tokens never go to disk. This probe does not
submit forms or invoke extension actions. Findings are evidence, not expiry claims.
"""
import html
from html.parser import HTMLParser
import json
import os
import re
import time
import urllib.parse
from kvpn_runtime import Manager, secure_open, redact

ORIGIN = 'https://kvpn.kaist.ac.kr'

class Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.actions = []
        self.text = []
        self.skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'script' and a.get('src'): self.scripts.append(a['src'])
        if tag in ('script','style'): self.skip += 1
        if tag in ('a','form'):
            target = a.get('href') or a.get('action')
            if target: self.actions.append(target)
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip = max(0,self.skip-1)
    def handle_data(self, value):
        if not self.skip: self.text.append(value)


def safe_path(value, base):
    u = urllib.parse.urlsplit(urllib.parse.urljoin(base, value))
    if (u.scheme,u.netloc) != ('https','kvpn.kaist.ac.kr'):
        return None
    # Do not store query values or retrieve action URLs.
    return u.path


def snippets(source):
    result=[]
    for m in re.finditer(r'(?i)session(?:time|counter|expire|timeout)|time(?:out|left)|remaining|extend(?:session)?|expiration', source):
        start=max(source.rfind('\n',0,m.start())+1,m.start()-70)
        end=min(source.find('\n',m.end()) if '\n' in source[m.end():] else len(source),m.end()+160)
        item=redact(html.unescape(source[start:end])).strip()
        # Defense in depth for opaque inline tokens, regardless of field name.
        item=re.sub(r'[A-Za-z0-9_+/=-]{24,}', '[opaque value omitted]', item)
        if item not in result: result.append(item)
        if len(result)>=40: break
    return result


def probe(ivanti):
    body=ivanti.final_body
    base=ivanti.final_url
    parser=Structure(); parser.feed(body)
    report={'sampled_at':time.time(),'page_path':safe_path(base,ORIGIN),
            'visible_timing_text':snippets('\n'.join(parser.text)),
            'inline_timing_symbols': sorted(set(re.findall(r'\b[A-Za-z_$][A-Za-z0-9_$]*(?:[Tt]imeout|[Tt]ime[Ll]eft|[Ss]ession|[Ee]xtend|[Rr]emaining)[A-Za-z0-9_$]*\b', body)))[:100],
            'scripts':[], 'session_related_paths':[]}
    for value in parser.actions:
        path=safe_path(value,base)
        if path and re.search(r'(?i)session|time|extend|status',path):
            report['session_related_paths'].append(path)
    for value in parser.scripts[:12]:
        path=safe_path(value,base)
        if not path or 'jquery' in path.lower():continue
        # Fetch only same-origin script references, never links/forms/actions.
        try:
            with ivanti.opener.open(ORIGIN+path,timeout=8) as response:
                final=urllib.parse.urlsplit(response.url)
                if final.hostname!='kvpn.kaist.ac.kr':continue
                source=response.read(512000).decode('utf-8','replace')
            report['scripts'].append({'path':path,'timing_evidence':snippets(source)})
        except Exception as e:
            report['scripts'].append({'path':path,'error':type(e).__name__})
    manager=Manager()
    dest=manager.directory/'session-discovery.json'
    fd=secure_open(dest,os.O_WRONLY|os.O_CREAT|os.O_TRUNC)
    with os.fdopen(fd,'w') as f:json.dump(report,f,indent=2)
    print('Read-only session discovery saved (no raw HTML or cookies):',dest)
