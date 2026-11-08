/**
 * Assemble a standalone report .html file from the shared template, styles
 * and charts code. Mirrors render_html() in build_report.py.
 */

/** Same pinned version as build_report.py. */
export const PLOTLY_CDN = 'https://cdn.jsdelivr.net/npm/plotly.js-dist-min@4.1.1/plotly.min.js';

export function standaloneHtml({ template, css, js, data }) {
  const pieces = {
    TITLE: `Schedule Luck ${data.league.year}`,
    PLOTLY: `<script src="${PLOTLY_CDN}"></script>`,
    CSS: css,
    JS: js,
    // Keep '</script>' inside strings from closing the data block early
    DATA: JSON.stringify(data).replaceAll('</', '<\\/'),
  };
  // One pass, so text inside one piece is never mistaken for a placeholder
  return template.replace(/__(TITLE|PLOTLY|CSS|JS|DATA)__/g, (_, key) => pieces[key]);
}
