'use strict';
// Generate separate update manifests: an ia32 app must never receive an x64 installer.
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const pkg = require('../package.json');
const version = pkg.version;
if (!/^\d+\.\d+\.\d+$/.test(version)) throw new Error('Expected a stable version');
const dir = path.resolve(process.argv[2] || 'dist');
for (const arch of ['x64', 'ia32']) {
  const name = `Barresan-Setup-${version}-${arch}.exe`;
  const installer = path.join(dir, name), map = installer + '.blockmap';
  if (!fs.existsSync(installer) || !fs.existsSync(map)) throw new Error('Missing installer or blockmap: ' + name);
  const hash = crypto.createHash('sha512').update(fs.readFileSync(installer)).digest('base64');
  const size = fs.statSync(installer).size;
  // Versioned absolute URLs let electron-updater locate the previous release's blockmap.
  const url = `https://github.com/saeidpix/vahdat/releases/download/v${version}/${name}`;
  const yaml = `version: ${version}\nfiles:\n  - url: ${url}\n    sha512: ${hash}\n    size: ${size}\npath: ${url}\nsha512: ${hash}\nreleaseDate: '${new Date().toISOString()}'\n`;
  fs.writeFileSync(path.join(dir, `latest-${arch}.yml`), yaml);
}
