'use strict';
const fs = require('fs'), path = require('path'), cp = require('child_process');
const oldFile = path.resolve(process.argv[2]), newFile = path.resolve(process.argv[3]);
fs.copyFileSync(oldFile, newFile);
fs.appendFileSync(newFile, Buffer.alloc(1024, 0x5a));
const tool = require('app-builder-bin').appBuilderPath;
cp.execFileSync(tool, ['blockmap', '--input', newFile, '--output', newFile + '.blockmap'], { stdio: 'inherit' });
