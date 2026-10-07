"""Builds the single-file prototype: python3 docs/factory/prototype/src/build.py [out.html]
Concatenates the sources in this folder into ../index.html (default)."""
import sys, os
d = os.path.dirname(os.path.abspath(__file__))
rd = lambda n: open(os.path.join(d, n), encoding='utf8').read()
css, body = rd('proto.css'), rd('proto.body.html')
js = '\n'.join(rd(n) for n in ('proto.art.data.js', 'proto.art.js', 'proto.i18n.js', 'proto.i18n2.js', 'proto.three.js', 'proto.twin.js', 'proto.app.js'))
three = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/0.160.0/three.min.js"></script>'
fonts = ('<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=IBM+Plex+Mono:wght@400;500&family=Instrument+Sans:wght@400;500;600&display=swap">')
title = '<title>Simplicio Panel Prototype</title>'
full = (f'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
        f'{title}\n{fonts}\n<style>\n{css}\n</style>\n</head>\n<body>\n{body}\n{three}\n<script>\n{js}\n</script>\n</body>\n</html>\n')
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(d, '..', 'index.html')
open(out, 'w', encoding='utf8').write(full)
print('built', os.path.normpath(out), len(full) // 1024, 'KB')
