import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';
import CleanCSS from 'clean-css';
import { minify } from 'terser';

const cssFiles = [
  'base.css',
  'layout.css',
  'components.css',
  'forms.css',
  'utilities.css',
  'responsive.css',
];

const jsFiles = [
  'phone-mask.js',
  'forms.js',
  'modals.js',
  'floating.js',
  'main.js',
];

const cssSource = cssFiles.map(f => readFileSync(join('css', f), 'utf8')).join('\n');
const cssMin = new CleanCSS({ level: 2 }).minify(cssSource);
writeFileSync('css/bundle.min.css', cssMin.styles);

let jsSource = '';
for (const f of jsFiles) {
  jsSource += readFileSync(join('js', f), 'utf8') + '\n';
}
const jsMin = await minify(jsSource, { compress: true, mangle: true });
writeFileSync('js/bundle.min.js', jsMin.code);

console.log('Build complete. CSS:', cssMin.styles.length, 'JS:', jsMin.code.length);
