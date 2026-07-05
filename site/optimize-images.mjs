import imagemin from 'imagemin';
import mozjpeg from 'imagemin-mozjpeg';
import webp from 'imagemin-webp';
import fs from 'fs';

const files = await imagemin(['assets/images/hero-bg.jpg'], {
  destination: 'assets/images',
  plugins: [mozjpeg({ quality: 75 })],
});
console.log('JPEG optimized:', files[0].destinationPath, fs.statSync(files[0].destinationPath).size);

const webpFiles = await imagemin(['assets/images/hero-bg.jpg'], {
  destination: 'assets/images',
  plugins: [webp({ quality: 75 })],
});
console.log('WebP created:', webpFiles[0].destinationPath, fs.statSync(webpFiles[0].destinationPath).size);
