// Extract text from PDF(s) using pdfjs-dist v6 (ESM build, dynamic import)
// Usage: node pdf_extract.js <pdf1> [pdf2 ...]
const fs = require('fs');
const path = require('path');

(async () => {
  const pdfjsLib = await import('pdfjs-dist/legacy/build/pdf.mjs');
  // In Node, pdf.js falls back to the fake worker automatically; setting workerSrc
  // explicitly avoids a download attempt and keeps text extraction working.
  try {
    const workerFile = path.join(
      path.dirname(require.resolve('pdfjs-dist/package.json')),
      'legacy', 'build', 'pdf.worker.mjs'
    );
    pdfjsLib.GlobalWorkerOptions.workerSrc = require('url').pathToFileURL(workerFile).href;
  } catch (e) {
    // non-fatal
  }

  const files = process.argv.slice(2);
  for (const file of files) {
    console.log('\n========== FILE: ' + file + ' ==========');
    const data = new Uint8Array(fs.readFileSync(file));
    const doc = await pdfjsLib.getDocument({ data, useWorkerFetch: false, isEvalSupported: false }).promise;
    for (let i = 1; i <= doc.numPages; i++) {
      const page = await doc.getPage(i);
      const content = await page.getTextContent();
      // restore line breaks: new items with large y jumps start a new line
      let prevY = null;
      const lines = [];
      let cur = '';
      for (const it of content.items) {
        const t = it.str !== undefined ? it.str : '';
        if (prevY !== null && it.transform && Math.abs(it.transform[5] - prevY) > 3) {
          if (cur.trim()) lines.push(cur.trim());
          cur = '';
        }
        cur += t;
        if (it.transform) prevY = it.transform[5];
      }
      if (cur.trim()) lines.push(cur.trim());
      console.log('----- page ' + i + ' -----');
      console.log(lines.join('\n'));
    }
  }
})().catch((e) => {
  console.error('ERROR:', e && e.message ? e.message : e);
  process.exit(1);
});
