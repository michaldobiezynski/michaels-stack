const puppeteer = require('puppeteer-core');
const path = require('path');

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const HTML = path.join(__dirname, 'book.html');
const OUT = process.argv[2] || path.join(__dirname, 'book.pdf');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: true,
    // Local file:// subresources (392 diagrams) must load from the page.
    args: ['--allow-file-access-from-files', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();

  const failed = [];
  page.on('requestfailed', (r) => failed.push(r.url()));
  page.on('response', (r) => {
    if (r.status() >= 400) failed.push(`${r.status()} ${r.url()}`);
  });

  await page.goto('file://' + HTML, { waitUntil: 'networkidle0', timeout: 180000 });

  // networkidle0 fires before decode completes for large PNGs; wait explicitly.
  const imgStats = await page.evaluate(async () => {
    const imgs = Array.from(document.images);
    await Promise.all(imgs.map((i) => (i.complete ? null : i.decode().catch(() => null))));
    return {
      total: imgs.length,
      broken: imgs.filter((i) => !i.complete || i.naturalWidth === 0).map((i) => i.src),
    };
  });

  await page.pdf({
    path: OUT,
    format: 'A4',
    printBackground: true,
    margin: { top: '20mm', bottom: '18mm', left: '18mm', right: '18mm' },
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: `
      <div style="width:100%;font-family:'Avenir Next',sans-serif;font-size:7.5pt;
                  color:#7b858f;padding:0 18mm;display:flex;justify-content:space-between;">
        <span>System Design Notes</span>
        <span class="pageNumber"></span>
      </div>`,
    timeout: 300000,
  });

  await browser.close();
  console.log(JSON.stringify({ images: imgStats.total, broken: imgStats.broken, failed }, null, 2));
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
