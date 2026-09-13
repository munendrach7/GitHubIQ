const puppeteer = require('puppeteer');
const fs = require('fs');
const path = require('path');

const mockDir = path.join(__dirname, 'mockups');
const outDir = path.join(__dirname, 'screenshots');
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

const files = fs.readdirSync(mockDir).filter(f => f.endsWith('.html'))
  .filter(f => !process.env.ONLY || process.env.ONLY.split(',').includes(f));

(async () => {
  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox', '--force-color-profile=srgb'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });

  for (const f of files) {
    const url = 'file:///' + path.join(mockDir, f).replace(/\\/g, '/');
    await page.goto(url, { waitUntil: 'networkidle0' });
    await new Promise(r => setTimeout(r, 350));
    const out = path.join(outDir, f.replace('.html', '.png'));
    await page.screenshot({ path: out, fullPage: true });
    console.log('✓ ' + path.basename(out));
  }

  await browser.close();
  console.log('Done: ' + files.length + ' screenshots');
})();
