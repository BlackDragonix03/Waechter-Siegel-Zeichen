'use strict';
const fs = require('fs');
const path = require('path');
const from = path.resolve(__dirname, '..', 'dist', 'web');
const to = path.resolve(__dirname, 'web');
fs.rmSync(to, { recursive: true, force: true });
fs.cpSync(from, to, { recursive: true });
