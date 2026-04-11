// Copy sql-wasm.wasm to dist/ and docs/ after build
const fs = require('fs');
const path = require('path');

const src = path.resolve(__dirname, 'public/sql-wasm.wasm');
const dist = path.resolve(__dirname, 'dist/sql-wasm.wasm');
const docs = path.resolve(__dirname, '../docs/sql-wasm.wasm');

fs.copyFileSync(src, dist);
console.log('Copied sql-wasm.wasm to dist/');

try {
  fs.copyFileSync(src, docs);
  console.log('Copied sql-wasm.wasm to docs/');
} catch (e) {
  console.warn('Warning: Could not copy to docs/', e.message);
}
