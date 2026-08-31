const fs = require('fs');
const path = require('path');
const PDFLib = require('./pdf-lib.min.js');
const fontkit = require('./fontkit.umd.min.js');

const { PDFDocument, rgb } = PDFLib;

function clean(line) {
  return line.replace(/\r/g, '').trimEnd();
}

function splitWords(text) {
  const out = [];
  let buf = '';
  for (const ch of text) {
    if (/[A-Za-z0-9._:%+\-\/]/.test(ch)) {
      buf += ch;
    } else {
      if (buf) out.push(buf), (buf = '');
      out.push(ch);
    }
  }
  if (buf) out.push(buf);
  return out;
}

function wrapText(text, font, size, maxWidth) {
  const tokens = splitWords(text);
  const lines = [];
  let line = '';
  for (const token of tokens) {
    const next = line + token;
    if (font.widthOfTextAtSize(next, size) <= maxWidth || !line) {
      line = next;
    } else {
      lines.push(line);
      line = token.trimStart();
    }
  }
  if (line) lines.push(line);
  return lines;
}

async function main() {
  const input = process.argv[2];
  const output = process.argv[3];
  const markdown = fs.readFileSync(input, 'utf8').split('\n').map(clean);

  const pdfDoc = await PDFDocument.create();
  pdfDoc.registerFontkit(fontkit);
  const fontBytes = fs.readFileSync('C:\\Windows\\Fonts\\NotoSansSC-VF.ttf');
  const font = await pdfDoc.embedFont(fontBytes, { subset: true });

  const pageWidth = 595.28;
  const pageHeight = 841.89;
  const marginX = 46;
  const marginTop = 50;
  const marginBottom = 44;
  const maxWidth = pageWidth - marginX * 2;
  let page = pdfDoc.addPage([pageWidth, pageHeight]);
  let y = pageHeight - marginTop;
  let pageNo = 1;

  function addPage() {
    page = pdfDoc.addPage([pageWidth, pageHeight]);
    pageNo += 1;
    y = pageHeight - marginTop;
  }

  function drawFooter() {
    const text = `第 ${pageNo} 页`;
    page.drawText(text, {
      x: pageWidth - marginX - font.widthOfTextAtSize(text, 9),
      y: 24,
      size: 9,
      font,
      color: rgb(0.35, 0.39, 0.45),
    });
  }

  function ensure(height) {
    if (y - height < marginBottom) {
      drawFooter();
      addPage();
    }
  }

  for (const raw of markdown) {
    if (!raw.trim()) {
      y -= 8;
      continue;
    }

    let text = raw;
    let size = 11.2;
    let color = rgb(0.12, 0.16, 0.22);
    let indent = 0;
    let lineGap = 5;
    let before = 0;
    let after = 2;

    if (text.startsWith('# ')) {
      text = text.slice(2);
      size = 21;
      color = rgb(0.05, 0.09, 0.16);
      before = 0;
      after = 8;
    } else if (text.startsWith('## ')) {
      text = text.slice(3);
      size = 15.2;
      color = rgb(0.07, 0.12, 0.19);
      before = 10;
      after = 4;
    } else if (text.startsWith('- ')) {
      text = '• ' + text.slice(2);
      indent = 12;
    }

    const lines = wrapText(text, font, size, maxWidth - indent);
    const blockHeight = before + lines.length * (size + lineGap) + after;
    ensure(blockHeight);
    y -= before;

    for (const line of lines) {
      page.drawText(line, {
        x: marginX + indent,
        y,
        size,
        font,
        color,
      });
      y -= size + lineGap;
    }
    y -= after;
  }

  drawFooter();
  const bytes = await pdfDoc.save();
  fs.writeFileSync(output, bytes);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

