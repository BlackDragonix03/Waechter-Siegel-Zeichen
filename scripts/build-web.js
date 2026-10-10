'use strict';
// Sammelt die Web-App (ohne Tests und ungenutzte Dateien) in dist/web für Desktop- und Android-Paket.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const out = path.join(root, 'dist', 'web');
const unused = new Set([path.join(root, 'src', 'lore.js')]);

fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
['index.html', 'styles.css'].forEach((f) => fs.copyFileSync(path.join(root, f), path.join(out, f)));
fs.cpSync(path.join(root, 'src'), path.join(out, 'src'), { recursive: true, filter: (src) => !unused.has(src) });
console.log('Web-App nach', path.relative(root, out), 'kopiert.');
