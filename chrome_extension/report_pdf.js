/**
 * Build a shareable PDF of the full-season report.
 *
 * Uses the same chart figures as the page (window.ReportFigures, from
 * report/report.js), drawn in light colors with Plotly, and places them on
 * US Letter pages with jsPDF. Headings and text are drawn onto images too,
 * so team names in any language or with emoji come out right (the PDF's
 * built-in fonts only cover basic Latin characters).
 *
 * Needs window.Plotly, window.jspdf and window.ReportFigures.
 */

const PAGE = { width: 612, height: 792, margin: 40 }; // points (US Letter)
const CONTENT_WIDTH = PAGE.width - 2 * PAGE.margin;
const IMAGE_WIDTH = 1000; // px; everything is drawn at this width, then scaled to the page
const PT_PER_PX = CONTENT_WIDTH / IMAGE_WIDTH;
const FOOTER_SPACE = 22;
const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

const fmtNumber = (n) => n.toLocaleString('en-US');

/**
 * Draw wrapped text onto a canvas and return it as an image.
 * @param {{text: string, size: number, weight?: number, color?: string, gapAfter?: number}[]} lines
 */
function textImage(lines) {
  const scale = 2;
  const measure = document.createElement('canvas').getContext('2d');
  const wrapped = [];
  let height = 0;
  for (const line of lines) {
    measure.font = `${line.weight || 400} ${line.size}px ${FONT}`;
    const lineHeight = Math.round(line.size * 1.4);
    let current = '';
    const rows = [];
    for (const word of line.text.split(/\s+/)) {
      const candidate = current ? `${current} ${word}` : word;
      if (measure.measureText(candidate).width > IMAGE_WIDTH && current) {
        rows.push(current);
        current = word;
      } else {
        current = candidate;
      }
    }
    rows.push(current);
    wrapped.push({ ...line, rows, lineHeight });
    height += rows.length * lineHeight + (line.gapAfter ?? 6);
  }
  const canvas = document.createElement('canvas');
  canvas.width = IMAGE_WIDTH * scale;
  canvas.height = Math.ceil(height * scale);
  const ctx = canvas.getContext('2d');
  ctx.scale(scale, scale);
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, IMAGE_WIDTH, height);
  ctx.textBaseline = 'top';
  let y = 0;
  for (const line of wrapped) {
    ctx.font = `${line.weight || 400} ${line.size}px ${FONT}`;
    ctx.fillStyle = line.color || '#0b0b0b';
    for (const row of line.rows) {
      ctx.fillText(row, 0, y + (line.lineHeight - line.size) / 2);
      y += line.lineHeight;
    }
    y += line.gapAfter ?? 6;
  }
  return { url: canvas.toDataURL('image/png'), height };
}

async function chartImage(figure) {
  const height = figure.layout.height;
  const url = await window.Plotly.toImage(
    { data: figure.data, layout: { ...figure.layout, width: IMAGE_WIDTH } },
    { format: 'png', width: IMAGE_WIDTH, height, scale: 2 },
  );
  return { url, height };
}

const heading = (title, description) => textImage([
  { text: title, size: 24, weight: 700, gapAfter: 4 },
  { text: description, size: 15, color: '#52514e', gapAfter: 10 },
]);

/** The report's sections for the last week played, as groups of images. */
async function sections(data) {
  const F = window.ReportFigures;
  const t = F.LIGHT_THEME;
  const L = data.league;
  const w = data.weeks[data.weeks.length - 1];
  const width = IMAGE_WIDTH;
  const order = [...w.results].sort((a, b) => b.playoff - a.playoff).map((r) => r.team);

  const details = [`${L.n_teams} teams`, `${L.n_playoff_teams} make the playoffs`];
  if (L.divisions.length) details.push(`divisions: ${L.divisions.join(', ')}`);
  details.push(`${fmtNumber(L.num_schedules)} simulated schedules`);
  const header = textImage([
    { text: `Schedule luck — ${L.name || `league ${L.id}`}, ${L.year}`, size: 32, weight: 700, gapAfter: 6 },
    { text: `Full season: weeks 1–${w.week} · ${details.join(' · ')}`, size: 16, color: '#52514e', gapAfter: 4 },
    ...L.notes.map((n) => ({ text: `Note: ${n}`, size: 14, color: '#7a5200', gapAfter: 4 })),
    { text: ' ', size: 8, gapAfter: 8 },
  ]);

  const groups = [
    [header,
     heading('Playoff odds', 'How often each team makes the playoffs if the same weekly scores are replayed against thousands of random schedules with the league’s real format.'),
     await chartImage(F.playoffFigure(w, t, { width }))],
    [heading('Schedule luck', 'Expected win % is the average record across all simulated schedules. Teams above the dashed line won more than their scores earned (lucky); teams below won fewer (unlucky). Color shows the luck index: actual minus expected win %, in percentage points.'),
     await chartImage(F.luckFigure(w, t, { width }))],
  ];
  if (w.swap) {
    groups.push([
      heading('What if you had their schedule?', 'Each team’s real weekly scores, replayed against every other team’s actual schedule. Each row is a team; each column is whose schedule it plays. Blue cells are more wins than the team’s real record, red cells fewer, gray the same. The bold diagonal is each team’s real record.'),
      await chartImage(F.swapAllFigure(w, t, { width, order })),
    ]);
  }
  groups.push(
    [heading('Where each team finishes', 'Share of simulations ending at each seed. Blue bars are playoff seeds; gray bars miss the playoffs.'),
     await chartImage(F.seedsFigure(w, t, { width, nPlayoffTeams: L.n_playoff_teams, nTeams: L.n_teams, gridCols: L.grid.cols }))],
    [heading('The numbers', 'Luck is actual minus expected win %, in percentage points.'),
     await chartImage(F.tableFigure(w, t, { width, fontSize: 16, rowHeight: 34 }))],
  );
  return groups;
}

/**
 * @param {object} data report data (from buildReportData)
 * @returns {Promise<Blob>} the PDF file
 */
export async function buildReportPdf(data) {
  const { jsPDF } = window.jspdf;
  const pdf = new jsPDF({ unit: 'pt', format: 'letter', compress: true });
  const bottom = PAGE.height - PAGE.margin - FOOTER_SPACE;
  const pageHeight = bottom - PAGE.margin;
  const gap = 18;
  let y = PAGE.margin;
  let first = true;

  for (const group of await sections(data)) {
    const natural = group.reduce((sum, img) => sum + img.height * PT_PER_PX, 0);
    // Keep each section on one page; shrink it if it can't fit even on its own
    let fit = Math.min(1, pageHeight / natural);
    if (!first && y + natural * fit > bottom) {
      // Nearly fits in the space left? Shrink it a little rather than leave a gap
      const squeeze = (bottom - y) / natural;
      if (squeeze >= 0.78) {
        fit = squeeze;
      } else {
        pdf.addPage();
        y = PAGE.margin;
      }
    }
    const width = CONTENT_WIDTH * fit;
    const x = PAGE.margin + (CONTENT_WIDTH - width) / 2;
    for (const img of group) {
      const h = img.height * PT_PER_PX * fit;
      pdf.addImage(img.url, 'PNG', x, y, width, h, undefined, 'FAST');
      y += h;
    }
    y += gap;
    first = false;
  }

  const pages = pdf.getNumberOfPages();
  const footer = `Generated ${data.league.generated} - Fantasy Schedule Luck`;
  for (let i = 1; i <= pages; i++) {
    pdf.setPage(i);
    pdf.setFont('helvetica', 'normal');
    pdf.setFontSize(8);
    pdf.setTextColor(122, 121, 116);
    pdf.text(footer, PAGE.margin, PAGE.height - PAGE.margin + 6);
    pdf.text(`Page ${i} of ${pages}`, PAGE.width - PAGE.margin, PAGE.height - PAGE.margin + 6, { align: 'right' });
  }
  return pdf.output('blob');
}
