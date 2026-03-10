/**
 * JSON (reading_order) -> DOCX with REAL 2-column sections
 * Usage:  node build_doc.js input.json output.docx
 */

const fs   = require("fs");
const path = require("path");

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  VerticalAlign, PageNumber, Footer, ColumnBreak, SectionType,
} = require("docx");

const INPUT_JSON  = process.argv[2] || "result.json";
const OUTPUT_DOCX = process.argv[3] || INPUT_JSON.replace(/\.json$/i, ".docx");

const PAGE_W_DXA    = 12240;
const PAGE_H_DXA    = 15840;
const MARGIN_DXA    = 1440;
const CONTENT_W_DXA = PAGE_W_DXA - MARGIN_DXA * 2;
const FONT          = "Times New Roman";
const SIZE_BODY     = 20;
const SIZE_TITLE    = 26;
const SIZE_REF      = 18;
const CLR_HEADER_BG = "D9E1F2";
const CLR_ALT_BG    = "F2F5FB";
const CLR_BORDER    = "8EA9C1";
const COLUMN_GAP_DXA = 720;

function border(color = CLR_BORDER) {
  return { style: BorderStyle.SINGLE, size: 4, color };
}
function allBorders(color = CLR_BORDER) {
  const b = border(color);
  return { top: b, bottom: b, left: b, right: b };
}

function makeRun(text, opts = {}) {
  return new TextRun({
    text: String(text),
    font: FONT,
    size: opts.size || SIZE_BODY,
    bold: !!opts.bold,
    italics: !!opts.italic,
    color: opts.color || "000000",
  });
}

function makePara(text, opts = {}) {
  const lines = String(text).split("\n");
  const runs = [];
  lines.forEach((line, i) => {
    runs.push(makeRun(line, opts));
    if (i < lines.length - 1) runs.push(new TextRun({ break: 1 }));
  });
  return new Paragraph({
    children: runs,
    spacing: { before: opts.spaceBefore ?? 60, after: opts.spaceAfter ?? 60 },
    alignment: opts.align || AlignmentType.LEFT,
  });
}

function buildTable(tbl) {
  const matrix = tbl.matrix || [];
  if (!matrix.length) return null;
  const nCols = Math.max(...matrix.map((r) => r.length));
  if (nCols === 0) return null;
  if (nCols === 1) return buildFallbackTable(matrix);

  const firstColW = Math.round(CONTENT_W_DXA * 0.22);
  const restW     = Math.round((CONTENT_W_DXA - firstColW) / (nCols - 1));
  const colWidths = [firstColW, ...Array(nCols - 1).fill(restW)];
  const sumW      = colWidths.reduce((a, b) => a + b, 0);
  colWidths[colWidths.length - 1] += CONTENT_W_DXA - sumW;

  const rows = matrix.map((rowData, ri) => {
    const isHeader = ri < 2;
    const bgColor  = isHeader ? CLR_HEADER_BG : ri % 2 === 0 ? "FFFFFF" : CLR_ALT_BG;
    const cells = Array.from({ length: nCols }, (_, ci) => {
      const cellText = rowData[ci] !== undefined ? rowData[ci] : "";
      return new TableCell({
        width: { size: colWidths[ci], type: WidthType.DXA },
        borders: allBorders(),
        shading: { fill: bgColor, type: ShadingType.CLEAR },
        margins: { top: 60, bottom: 60, left: 100, right: 100 },
        verticalAlign: VerticalAlign.CENTER,
        children: [new Paragraph({
          children: [makeRun(cellText, { bold: isHeader, size: SIZE_BODY - 2 })],
          spacing: { before: 0, after: 0 },
          alignment: ci === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
        })],
      });
    });
    return new TableRow({ children: cells, tableHeader: isHeader });
  });

  return new Table({
    width: { size: CONTENT_W_DXA, type: WidthType.DXA },
    columnWidths: colWidths,
    rows,
  });
}

function buildFallbackTable(matrix) {
  const rows = matrix
    .filter((r) => (r[0] || "").trim())
    .map((rowData, ri) => {
      const text     = rowData[0] || "";
      const isHeader = ri === 0;
      return new TableRow({
        children: [new TableCell({
          width: { size: CONTENT_W_DXA, type: WidthType.DXA },
          borders: allBorders(),
          shading: { fill: isHeader ? CLR_HEADER_BG : ri % 2 === 0 ? "FFFFFF" : CLR_ALT_BG, type: ShadingType.CLEAR },
          margins: { top: 60, bottom: 60, left: 120, right: 120 },
          children: [new Paragraph({
            children: [makeRun(text, { bold: isHeader, size: SIZE_BODY - 2 })],
            spacing: { before: 0, after: 0 },
          })],
        })],
      });
    });
  if (!rows.length) return null;
  return new Table({ width: { size: CONTENT_W_DXA, type: WidthType.DXA }, columnWidths: [CONTENT_W_DXA], rows });
}

function blockToElements(unit) {
  const type = (unit.type || "").toLowerCase();
  const text = (unit.text || "").trim();
  const elements = [];

  if (type === "table") {
    const tblElem = buildTable(unit.table || {});
    if (tblElem) elements.push(tblElem);
    elements.push(new Paragraph({ children: [], spacing: { before: 80, after: 80 } }));
    return elements;
  }
  if (type === "title") {
    if (text) elements.push(new Paragraph({
      heading: HeadingLevel.HEADING_2,
      children: [new TextRun({ text, font: FONT, size: SIZE_TITLE, bold: true })],
      spacing: { before: 240, after: 120 },
    }));
    return elements;
  }
  if (type === "reference") {
    if (text) text.split("\n").forEach((line) => {
      if (line.trim()) elements.push(makePara(line, { size: SIZE_REF, italic: true, color: "555555", spaceBefore: 40, spaceAfter: 40 }));
    });
    return elements;
  }
  if (text) text.split("\n").forEach((line, i) => {
    if (line.trim()) elements.push(makePara(line, { spaceBefore: i === 0 ? 80 : 40, spaceAfter: 40 }));
  });
  return elements;
}

function yTop(unit) {
  if (Array.isArray(unit.bbox) && unit.bbox.length >= 2) return Number(unit.bbox[1]) || 0;
  if (unit.bbox && typeof unit.bbox === "object" && unit.bbox.y1 != null) return Number(unit.bbox.y1) || 0;
  return Number.POSITIVE_INFINITY;
}
function xLeft(unit) {
  if (Array.isArray(unit.bbox) && unit.bbox.length >= 1) return Number(unit.bbox[0]) || 0;
  if (unit.bbox && typeof unit.bbox === "object" && unit.bbox.x1 != null) return Number(unit.bbox.x1) || 0;
  return Number.POSITIVE_INFINITY;
}
function stableSortByYX(arr) {
  return arr.map((u, i) => ({ u, i }))
    .sort((a, b) => {
      const dy = yTop(a.u) - yTop(b.u);
      if (dy !== 0) return dy;
      const dx = xLeft(a.u) - xLeft(b.u);
      if (dx !== 0) return dx;
      return a.i - b.i;
    })
    .map((x) => x.u);
}

function makeSection({ columns, children, isFirst }) {
  const props = {
    page: {
      size: { width: PAGE_W_DXA, height: PAGE_H_DXA },
      margin: { top: MARGIN_DXA, right: MARGIN_DXA, bottom: MARGIN_DXA, left: MARGIN_DXA },
    },
    type: isFirst ? undefined : SectionType.CONTINUOUS,
  };
  if (columns === 2) {
    props.column = { count: 2, space: COLUMN_GAP_DXA, equalWidth: true };
  }
  return {
    properties: props,
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: SIZE_REF, color: "888888" })],
        })],
      }),
    },
    children,
  };
}

function assembleSections(data) {
  const units    = data.reading_order || [];
  const sections = [];

  const titleChildren = [new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text: path.basename(data.image || "Document"), font: FONT, size: 32, bold: true })],
    spacing: { before: 0, after: 240 },
    alignment: AlignmentType.CENTER,
  })];
  sections.push(makeSection({ columns: 1, children: titleChildren, isFirst: true }));

  let currentMode     = null;
  let currentChildren = [];

  function flush() {
    if (!currentChildren.length) return;
    sections.push(makeSection({ columns: currentMode, children: currentChildren, isFirst: false }));
    currentChildren = [];
  }
  function ensureMode(mode) {
    if (currentMode === null) { currentMode = mode; return; }
    if (currentMode !== mode) { flush(); currentMode = mode; }
  }

  let i = 0;
  while (i < units.length) {
    const u    = units[i];
    const kind = (u.kind || "full").toLowerCase();

    if (kind === "full") {
      ensureMode(1);
      blockToElements(u).forEach((el) => currentChildren.push(el));
      i += 1;
      continue;
    }

    ensureMode(2);
    const run = [];
    while (i < units.length) {
      const k = (units[i].kind || "full").toLowerCase();
      if (k !== "left" && k !== "right") break;
      run.push(units[i]);
      i += 1;
    }

    const leftBlocks  = stableSortByYX(run.filter((x) => (x.kind || "").toLowerCase() === "left"));
    const rightBlocks = stableSortByYX(run.filter((x) => (x.kind || "").toLowerCase() === "right"));

    leftBlocks.forEach((blk) => blockToElements(blk).forEach((el) => currentChildren.push(el)));
    if (rightBlocks.length) {
      currentChildren.push(new Paragraph({ children: [new ColumnBreak()], spacing: { before: 0, after: 0 } }));
      rightBlocks.forEach((blk) => blockToElements(blk).forEach((el) => currentChildren.push(el)));
    }
  }

  flush();
  return sections;
}

async function main() {
  if (!fs.existsSync(INPUT_JSON)) {
    console.error(`ERROR: input file not found: ${INPUT_JSON}`);
    process.exit(1);
  }

  const data = JSON.parse(fs.readFileSync(INPUT_JSON, "utf-8"));
  console.log(`Input:  ${INPUT_JSON}  (${(data.reading_order || []).length} blocks)`);

  const sections = assembleSections(data);
  const doc = new Document({
    styles: {
      default: { document: { run: { font: FONT, size: SIZE_BODY } } },
      paragraphStyles: [
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: 32, bold: true, font: FONT, color: "1F3864" },
          paragraph: { spacing: { before: 0, after: 240 }, outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { size: SIZE_TITLE, bold: true, font: FONT, color: "2E5594" },
          paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      ],
    },
    sections,
  });

  const buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(OUTPUT_DOCX, buffer);
  console.log(`Output: ${OUTPUT_DOCX}`);
}

main().catch((e) => { console.error(e); process.exit(1); });