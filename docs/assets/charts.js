// Small SVG charts for the results site. Each chart draws into a container at the
// container's width, redraws when that width changes, and has a hover and keyboard
// tooltip. A value is a number, the hidden-count marker "<11", or null.
// A classic script (not a module), so the site also works when index.html is opened
// straight from disk; everything it shares is on window.SharpCharts.

(() => {

const SVG_NS = "http://www.w3.org/2000/svg";
const HIDDEN = "<11";
const observers = new Map();

const isNum = (v) => typeof v === "number" && Number.isFinite(v);

function h(tag, attrs = {}, ...children) {
  return build(document.createElement(tag), attrs, children);
}

function s(tag, attrs = {}, ...children) {
  return build(document.createElementNS(SVG_NS, tag), attrs, children);
}

function build(node, attrs, children) {
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = String(value);
    else if (key === "vars") for (const [name, v] of Object.entries(value)) node.style.setProperty(name, String(v));
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// ---------------------------------------------------------------- formatting


// No count on the site is exact: the published data is already rounded, and every count is shown as
// an approximation, e.g. ~14.1K or ~116M. Zero stays 0 and a hidden count stays <11.
const approx = new Intl.NumberFormat("en-US", { notation: "compact", maximumSignificantDigits: 3 });
const count = (v) => (isNum(v) ? (v === 0 ? "0" : `~${approx.format(v)}`) : v === HIDDEN ? "<11" : "n/a");
const compactCount = (v) => (isNum(v) ? approx.format(v) : count(v));
const percent = (v, digits = 1) => (isNum(v) ? `${v.toFixed(digits)}%` : "hidden");
const signed = (v, digits = 1) => {
  if (!isNum(v)) return "";
  const text = Math.abs(v).toFixed(digits);
  if (Number(text) === 0) return text;
  return `${v > 0 ? "+" : "−"}${text}`;
};

function display(v, format) {
  if (isNum(v)) return format(v);
  return v === HIDDEN ? "<11 (hidden)" : "hidden";
}

const textWidth = (text, size) => String(text).length * size * 0.56;

// Split a label into at most maxLines lines of about maxChars characters.
function wrap(text, maxChars, maxLines = 2) {
  const lines = [];
  let line = "";
  for (const word of String(text).split(/\s+/)) {
    if (line && `${line} ${word}`.length > maxChars) {
      lines.push(line);
      line = word;
    } else {
      line = line ? `${line} ${word}` : word;
    }
  }
  if (line) lines.push(line);
  if (lines.length <= maxLines) return lines;
  const kept = lines.slice(0, maxLines);
  const rest = lines.slice(maxLines - 1).join(" ");
  kept[maxLines - 1] = `${rest.slice(0, Math.max(1, maxChars - 1)).trimEnd()}…`;
  return kept;
}

function multiline(lines, attrs, anchor = "middle", lineHeight = 16) {
  const node = s("text", { ...attrs, "dominant-baseline": anchor === "top" ? "auto" : "middle" });
  const first = anchor === "top" ? 0 : (-(lines.length - 1) * lineHeight) / 2;
  lines.forEach((line, i) => node.append(s("tspan", { x: attrs.x, dy: i === 0 ? first : lineHeight, text: line })));
  return node;
}

function niceTicks(min, max, target = 4) {
  if (!(max > min)) max = min + 1;
  const rough = (max - min) / target;
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((st) => st >= rough);
  const ticks = [];
  for (let v = Math.floor(min / step) * step; v <= Math.ceil(max / step) * step + step / 2; v += step) {
    ticks.push(Number(v.toFixed(10)));
  }
  return ticks;
}

function barPath(x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  return `M${x},${y}h${width - r}a${r},${r} 0 0 1 ${r},${r}v${height - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${-(width - r)}z`;
}

// ---------------------------------------------------------------- tooltip and live region

let tipNode;
let liveNode;

function announce(text) {
  liveNode ??= document.body.appendChild(h("p", { class: "visually-hidden", "aria-live": "polite" }));
  liveNode.textContent = text;
}

function swatch({ color, style = "dot" }) {
  return h("span", { class: `swatch swatch-${style}`, vars: { "--c": color }, "aria-hidden": "true" });
}

function showTip(title, lines, x, y) {
  tipNode ??= document.body.appendChild(h("div", { class: "tip", "aria-hidden": "true" }));
  tipNode.replaceChildren(
    h("p", { class: "tip-title", text: title }),
    ...lines.map(([label, value, mark]) =>
      h("p", { class: "tip-row" }, mark ? swatch(mark) : null, h("span", { class: "tip-label", text: label }), h("strong", { text: value }))),
  );
  tipNode.hidden = false;
  const box = tipNode.getBoundingClientRect();
  const left = Math.min(Math.max(8, x + 14), window.innerWidth - box.width - 8);
  const top = y - box.height - 14 >= 8 ? y - box.height - 14 : Math.min(y + 18, window.innerHeight - box.height - 8);
  tipNode.style.left = `${left}px`;
  tipNode.style.top = `${top}px`;
}

function hideTip() {
  if (tipNode) tipNode.hidden = true;
}

window.addEventListener("scroll", hideTip, { passive: true });

function bindTip(node, content) {
  const { title, lines } = content();
  node.setAttribute("tabindex", "0");
  node.setAttribute("role", "img");
  node.setAttribute("aria-label", `${title}: ${lines.map(([label, value]) => `${label} ${value}`).join(", ")}`);
  const at = (x, y) => {
    const c = content();
    showTip(c.title, c.lines, x, y);
  };
  node.addEventListener("pointermove", (e) => at(e.clientX, e.clientY));
  node.addEventListener("pointerleave", hideTip);
  node.addEventListener("focus", () => {
    const r = node.getBoundingClientRect();
    at(r.left + Math.min(r.width / 2, 160), r.top);
  });
  node.addEventListener("blur", hideTip);
}

// ---------------------------------------------------------------- figure parts

// Stop redrawing every chart (before the page is drawn again for another profile), or only
// the charts inside one element (before that element is rebuilt).
function releaseCharts(within = null) {
  for (const [container, observer] of observers) {
    if (within === null || within.contains(container)) {
      observer.disconnect();
      observers.delete(container);
    }
  }
  hideTip();
}

function responsive(container, draw) {
  observers.get(container)?.disconnect();
  let last = 0;
  const render = () => {
    const width = Math.floor(container.clientWidth);
    if (width === 0 || width === last) return;
    last = width;
    container.replaceChildren(draw(width));
  };
  const observer = new ResizeObserver(render);
  observer.observe(container);
  observers.set(container, observer);
  render();
}

function emptyNote() {
  return h("p", { class: "empty-note", text: "No values to draw for this profile: every count here is hidden or zero. The numbers are in the table below." });
}

function legend(items) {
  return h("ul", { class: "legend" }, items.map((item) => h("li", {}, swatch(item), item.label)));
}

function figure({ title, description, legendItems, controls, table, source }) {
  const plot = h("div", { class: "plot" });
  const fig = h("figure", { class: "figure" },
    h("figcaption", {}, h("h3", { text: title }), description ? h("p", { text: description }) : null),
    controls ? h("div", { class: "figure-controls" }, controls) : null,
    legendItems ? legend(legendItems) : null,
    plot,
    table ? h("details", { class: "numbers" }, h("summary", { text: "Show the numbers" }), table) : null,
    source ? h("p", { class: "source", text: `From ${source}` }) : null);
  return { fig, plot };
}

// columns: [{ label, value: (row) => text, numeric }]
function dataTable(columns, rows, caption) {
  return h("div", { class: "table-wrap", tabindex: 0, role: "region", "aria-label": caption },
    h("table", {},
      h("caption", { class: "visually-hidden", text: caption }),
      h("thead", {}, h("tr", {}, columns.map((c) => h("th", { scope: "col", class: c.numeric ? "num" : null, text: c.label })))),
      h("tbody", {}, rows.map((row) => h("tr", {}, columns.map((c, i) =>
        h(i === 0 ? "th" : "td", { scope: i === 0 ? "row" : null, class: c.numeric ? "num" : null, text: c.value(row) })))))));
}

// ---------------------------------------------------------------- line chart

// series: [{ label, color, values }] with one value per x.
function lineChart(container, { x, series, format, endFormat = format, axisFormat = format, height = 240, label, yMax }) {
  responsive(container, (width) => {
    const present = series.flatMap((se) => se.values.filter(isNum));
    if (!present.length) return emptyNote();
    const ticks = niceTicks(0, yMax ?? Math.max(...present));
    const tickText = ticks.map(axisFormat);
    const narrow = width < 560;
    const top = 10;
    const bottom = 30;
    const plotH = height - top - bottom;
    const lo = ticks[0];
    const hi = ticks[ticks.length - 1];
    const ys = (v) => top + plotH - ((v - lo) / (hi - lo)) * plotH;
    const ends = series
      .map((se) => {
        const i = se.values.findLastIndex(isNum);
        return i < 0 ? null : { se, i, y: ys(se.values[i]), text: endFormat(se.values[i]) };
      })
      .filter(Boolean)
      .sort((a, b) => a.y - b.y);
    const apart = ends.every((e, k) => k === 0 || e.y - ends[k - 1].y >= 16);
    const showEnds = !narrow && apart;
    const left = 10 + Math.max(...tickText.map((t) => textWidth(t, 12)));
    const right = showEnds ? 18 + Math.max(...ends.map((e) => textWidth(`${e.se.label} ${e.text}`, 13))) : 16;
    const w = Math.max(40, width - left - right);
    const xs = (i) => left + (x.length === 1 ? w / 2 : (i * w) / (x.length - 1));

    const root = s("svg", { class: "chart-svg", width, height, viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": label });
    ticks.forEach((t, k) => {
      root.append(s("line", { class: "grid", x1: left, x2: left + w, y1: ys(t), y2: ys(t) }));
      root.append(s("text", { class: "tick", x: left - 8, y: ys(t), "text-anchor": "end", "dominant-baseline": "middle", text: tickText[k] }));
    });
    const every = Math.max(1, Math.ceil((x.length * 44) / w));
    x.forEach((xv, i) => {
      if ((x.length - 1 - i) % every === 0) root.append(s("text", { class: "tick", x: xs(i), y: height - 8, "text-anchor": "middle", text: xv }));
    });
    for (const se of series) {
      let d = "";
      let pen = false;
      se.values.forEach((v, i) => {
        if (!isNum(v)) {
          pen = false;
          return;
        }
        d += `${pen ? "L" : "M"}${xs(i).toFixed(1)},${ys(v).toFixed(1)}`;
        pen = true;
      });
      root.append(s("path", { class: "line", d, stroke: se.color }));
    }
    for (const e of ends) {
      root.append(s("circle", { class: "dot", cx: xs(e.i), cy: e.y, r: 4, fill: e.se.color }));
      if (showEnds) {
        root.append(s("text", { class: "end-label", x: xs(e.i) + 10, y: e.y, "dominant-baseline": "middle" },
          s("tspan", { class: "end-name", text: `${e.se.label} ` }), s("tspan", { class: "end-value", text: e.text })));
      }
    }

    const cross = s("line", { class: "crosshair", y1: top, y2: top + plotH, visibility: "hidden" });
    const marks = series.map((se) => s("circle", { class: "dot", r: 5, fill: se.color, visibility: "hidden" }));
    const overlay = s("rect", { class: "overlay", x: left, y: top, width: w, height: plotH, tabindex: 0, role: "img",
      "aria-label": `${label}. Use the left and right arrow keys to read each year.` });
    root.append(cross, ...marks, overlay);
    let current = -1;
    const lines = (i) => series.map((se) => [se.label, display(se.values[i], format), se]);
    const show = (i, px, py) => {
      current = i;
      cross.setAttribute("x1", xs(i));
      cross.setAttribute("x2", xs(i));
      cross.setAttribute("visibility", "visible");
      series.forEach((se, k) => {
        const v = se.values[i];
        marks[k].setAttribute("visibility", isNum(v) ? "visible" : "hidden");
        if (isNum(v)) {
          marks[k].setAttribute("cx", xs(i));
          marks[k].setAttribute("cy", ys(v));
        }
      });
      const box = root.getBoundingClientRect();
      showTip(String(x[i]), lines(i), px ?? box.left + xs(i), py ?? box.top + top + 8);
    };
    const hide = () => {
      cross.setAttribute("visibility", "hidden");
      marks.forEach((m) => m.setAttribute("visibility", "hidden"));
      hideTip();
    };
    const nearest = (clientX) => {
      const box = root.getBoundingClientRect();
      const t = (clientX - box.left - left) / w;
      return Math.max(0, Math.min(x.length - 1, Math.round(t * (x.length - 1))));
    };
    overlay.addEventListener("pointermove", (e) => show(nearest(e.clientX), e.clientX, e.clientY));
    overlay.addEventListener("pointerleave", hide);
    overlay.addEventListener("blur", hide);
    overlay.addEventListener("focus", () => show(current < 0 ? x.length - 1 : current));
    overlay.addEventListener("keydown", (e) => {
      const moves = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity };
      if (!(e.key in moves)) return;
      e.preventDefault();
      const i = Math.max(0, Math.min(x.length - 1, (current < 0 ? x.length - 1 : current) + moves[e.key]));
      show(i);
      announce(`${x[i]}: ${lines(i).map(([l, v]) => `${l} ${v}`).join(", ")}`);
    });
    return root;
  });
}

// ---------------------------------------------------------------- dot rows (dot plot / dumbbell)

// rows: [{ label, values: { [series.key]: value }, extra: [[label, text]] }] or [{ heading }].
// series: [{ key, label, color, style: "dot" | "ring" }].
function dotRows(container, { rows, series, format, axisFormat = format, domain, ref, band, label, aside, asideLabel }) {
  responsive(container, (width) => {
    const present = rows.flatMap((r) => (r.heading ? [] : series.map((se) => r.values[se.key]).filter(isNum)));
    if (!present.length) return emptyNote();
    const narrow = width < 560;
    const ticks = niceTicks(domain ? domain[0] : 0, domain ? domain[1] : Math.max(...present));
    const lo = ticks[0];
    const hi = ticks[ticks.length - 1];
    const labelW = narrow ? 0 : Math.round(Math.min(280, width * 0.36));
    const asideW = aside ? 60 : 0;
    const x0 = narrow ? 10 : labelW + 22;
    const x1 = width - asideW - 14;
    const xs = (v) => x0 + ((Math.max(lo, Math.min(hi, v)) - lo) / (hi - lo)) * (x1 - x0);
    const maxChars = Math.max(14, Math.floor((narrow ? width - 20 : labelW - 8) / (14 * 0.56)));
    const firstY = asideLabel ? 24 : 4;
    const layout = [];
    let y = firstY;
    for (const row of rows) {
      if (row.heading) {
        layout.push({ row, y, h: 30 });
        y += 30;
        continue;
      }
      const lines = wrap(row.label, maxChars);
      const rowH = narrow ? lines.length * 16 + 30 : Math.max(34, lines.length * 16 + 14);
      layout.push({ row, y, h: rowH, lines });
      y += rowH;
    }
    const bottomY = y;
    const height = bottomY + 28;

    const root = s("svg", { class: "chart-svg", width, height, viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": label });
    if (band) root.append(s("rect", { class: "band", x: xs(band[0]), y: firstY, width: xs(band[1]) - xs(band[0]), height: bottomY - firstY }));
    for (const t of ticks) {
      root.append(s("line", { class: "grid", x1: xs(t), x2: xs(t), y1: firstY, y2: bottomY }));
      root.append(s("text", { class: "tick", x: xs(t), y: bottomY + 18, "text-anchor": "middle", text: axisFormat(t) }));
    }
    if (ref !== undefined) root.append(s("line", { class: "ref", x1: xs(ref), x2: xs(ref), y1: firstY, y2: bottomY }));
    if (asideLabel) root.append(s("text", { class: "aside-head", x: width - 4, y: 14, "text-anchor": "end", text: asideLabel }));

    for (const item of layout) {
      const { row } = item;
      if (row.heading) {
        root.append(s("text", { class: "row-heading", x: narrow ? 10 : 0, y: item.y + 22, text: row.heading }));
        continue;
      }
      const cy = narrow ? item.y + item.lines.length * 16 + 14 : item.y + item.h / 2;
      const g = s("g", { class: "row" });
      g.append(s("rect", { class: "row-bg", x: 0, y: item.y + 1, width, height: item.h - 2, rx: 4 }));
      g.append(multiline(item.lines, { class: "row-label", x: narrow ? 10 : labelW, y: narrow ? item.y + 15 : cy, "text-anchor": narrow ? "start" : "end" },
        narrow ? "top" : "middle"));
      const values = series.map((se) => row.values[se.key]).filter(isNum);
      if (values.length > 1) {
        g.append(s("line", { class: "connector", x1: xs(Math.min(...values)), x2: xs(Math.max(...values)), y1: cy, y2: cy }));
      }
      for (const style of ["ring", "dot"]) {
        for (const se of series.filter((item2) => (item2.style ?? "dot") === style)) {
          const v = row.values[se.key];
          if (!isNum(v)) continue;
          g.append(style === "ring"
            ? s("circle", { class: "dot-ring", cx: xs(v), cy, r: 5, stroke: se.color })
            : s("circle", { class: "dot", cx: xs(v), cy, r: 5, fill: se.color }));
        }
      }
      if (aside) g.append(s("text", { class: "aside-text", x: width - 4, y: cy, "text-anchor": "end", "dominant-baseline": "middle", text: aside(row) }));
      bindTip(g, () => ({
        title: row.label,
        lines: [...series.map((se) => [se.label, display(row.values[se.key], format), se]), ...(row.extra ?? [])],
      }));
      root.append(g);
    }
    return root;
  });
}

// ---------------------------------------------------------------- 100% stacked bars

// bars: [{ label, values: { [part.key]: percent }, counts: { [part.key]: count } }]
// parts: [{ key, label, color, dark }] in order; dark parts get white labels.
function stackedBars(container, { bars, parts, label }) {
  responsive(container, (width) => {
    const narrow = width < 560;
    const labelW = narrow ? 0 : 150;
    const x0 = narrow ? 0 : labelW + 16;
    const x1 = width - 4;
    const barH = 24;
    const rowH = narrow ? 58 : 46;
    const height = bars.length * rowH + 26;
    const xs = (p) => x0 + (Math.min(100, p) / 100) * (x1 - x0);
    const root = s("svg", { class: "chart-svg", width, height, viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": label });
    for (const t of [0, 25, 50, 75, 100]) {
      root.append(s("line", { class: "grid", x1: xs(t), x2: xs(t), y1: 0, y2: bars.length * rowH }));
      root.append(s("text", { class: "tick", x: xs(t), y: bars.length * rowH + 18, "text-anchor": t === 0 ? "start" : t === 100 ? "end" : "middle", text: `${t}%` }));
    }
    bars.forEach((bar, b) => {
      const y = b * rowH;
      const barY = narrow ? y + 26 : y + (rowH - barH) / 2;
      const g = s("g", { class: "row" });
      g.append(s("rect", { class: "row-bg", x: 0, y: y + 1, width, height: rowH - 2, rx: 4 }));
      g.append(s("text", { class: "row-label", x: narrow ? 0 : labelW, y: narrow ? y + 16 : barY + barH / 2,
        "text-anchor": narrow ? "start" : "end", "dominant-baseline": "middle", text: bar.label }));
      const shown = parts.filter((p) => isNum(bar.values[p.key]) && bar.values[p.key] > 0);
      let acc = 0;
      shown.forEach((p, k) => {
        const v = bar.values[p.key];
        const last = k === shown.length - 1;
        const xa = xs(acc);
        const xb = xs(acc + v) - (last ? 0 : 2);
        acc += v;
        g.append(s("path", { d: barPath(xa, barY, Math.max(0, xb - xa), barH, last ? 4 : 0), fill: p.color }));
        const text = percent(v, 0);
        if (xb - xa >= textWidth(text, 12) + 12) {
          g.append(s("text", { class: p.dark ? "seg-label on-dark" : "seg-label", x: (xa + xb) / 2, y: barY + barH / 2,
            "text-anchor": "middle", "dominant-baseline": "middle", text }));
        }
      });
      bindTip(g, () => ({
        title: bar.label,
        lines: parts.map((p) => [p.label, `${display(bar.values[p.key], percent)} (${count(bar.counts?.[p.key])})`, { color: p.color, style: "block" }]),
      }));
      root.append(g);
    });
    return root;
  });
}

// ---------------------------------------------------------------- bar list

// rows: [{ label, value, extra: [[label, text]] }]
function barList(container, { rows, format, label }) {
  responsive(container, (width) => {
    const values = rows.map((r) => r.value).filter(isNum);
    if (!values.length) return emptyNote();
    const narrow = width < 560;
    const labelW = narrow ? 0 : Math.round(Math.min(240, width * 0.32));
    const valueW = 14 + Math.max(...rows.map((r) => textWidth(display(r.value, format), 13)));
    const x0 = narrow ? 0 : labelW + 16;
    const x1 = width - valueW;
    const max = Math.max(...values);
    const rowH = narrow ? 50 : 34;
    const barH = 16;
    const height = rows.length * rowH + 4;
    const xs = (v) => x0 + (v / max) * (x1 - x0);
    const root = s("svg", { class: "chart-svg", width, height, viewBox: `0 0 ${width} ${height}`, role: "group", "aria-label": label });
    rows.forEach((row, i) => {
      const y = i * rowH;
      const barY = narrow ? y + 26 : y + (rowH - barH) / 2;
      const g = s("g", { class: "row" });
      g.append(s("rect", { class: "row-bg", x: 0, y: y + 1, width, height: rowH - 2, rx: 4 }));
      g.append(s("text", { class: "row-label", x: narrow ? 0 : labelW, y: narrow ? y + 16 : barY + barH / 2,
        "text-anchor": narrow ? "start" : "end", "dominant-baseline": "middle", text: row.label }));
      const end = isNum(row.value) ? xs(row.value) : x0;
      if (isNum(row.value) && row.value > 0) g.append(s("path", { class: "bar", d: barPath(x0, barY, Math.max(2, end - x0), barH, 4) }));
      g.append(s("text", { class: "value-label", x: end + 8, y: barY + barH / 2, "dominant-baseline": "middle", text: display(row.value, format) }));
      bindTip(g, () => ({ title: row.label, lines: [["People", display(row.value, format)], ...(row.extra ?? [])] }));
      root.append(g);
    });
    return root;
  });
}

// ---------------------------------------------------------------- comorbidity network

// nodes: [{ id, label, short, value (percent), count }]
// links: [{ a, b, lift, count, pct }]; only links with lift >= minLift are drawn.
function networkChart(container, { nodes, links, minLift, label }) {
  responsive(container, (width) => {
    const narrow = width < 560;
    const labelSpace = narrow ? 66 : 120;
    const radiusRing = Math.min(width, 680) / 2 - labelSpace;
    const size = 2 * radiusRing + (narrow ? 96 : 120);
    const cx = width / 2;
    const cy = size / 2;
    const pos = new Map(nodes.map((n, i) => {
      const a = (i / nodes.length) * 2 * Math.PI - Math.PI / 2;
      return [n.id, { a, x: cx + radiusRing * Math.cos(a), y: cy + radiusRing * Math.sin(a) }];
    }));
    const maxValue = Math.max(1, ...nodes.map((n) => n.value).filter(isNum));
    const radius = (n) => (isNum(n.value) ? 3 + 9 * Math.sqrt(n.value / maxValue) : 3);
    const shown = links.filter((l) => isNum(l.lift) && l.lift >= minLift && pos.has(l.a) && pos.has(l.b)).sort((p, q) => p.lift - q.lift);
    const maxLift = Math.max(minLift + 1, ...shown.map((l) => l.lift));

    const root = s("svg", { class: "chart-svg", width, height: size, viewBox: `0 0 ${width} ${size}`, role: "group", "aria-label": label });
    const linkLayer = s("g", { "aria-hidden": "true" });
    const nodeLayer = s("g");
    root.append(linkLayer, nodeLayer);
    const drawn = shown.map((l) => {
      const p = pos.get(l.a);
      const q = pos.get(l.b);
      const t = (l.lift - minLift) / (maxLift - minLift);
      const qx = cx + ((p.x + q.x) / 2 - cx) * 0.35;
      const qy = cy + ((p.y + q.y) / 2 - cy) * 0.35;
      const path = s("path", { class: "net-link", d: `M${p.x.toFixed(1)},${p.y.toFixed(1)}Q${qx.toFixed(1)},${qy.toFixed(1)} ${q.x.toFixed(1)},${q.y.toFixed(1)}`,
        "stroke-width": (1 + 3 * t).toFixed(2), "stroke-opacity": (0.22 + 0.6 * t).toFixed(2) });
      linkLayer.append(path);
      return { l, path };
    });
    const nodeGroups = new Map();
    const highlight = (id) => {
      const partners = new Set(shown.flatMap((l) => (l.a === id ? [l.b] : l.b === id ? [l.a] : [])));
      for (const { l, path } of drawn) path.classList.toggle("dim", id !== null && l.a !== id && l.b !== id);
      for (const [nid, g] of nodeGroups) g.classList.toggle("dim", id !== null && nid !== id && !partners.has(nid));
    };
    const byId = new Map(nodes.map((n) => [n.id, n]));
    for (const n of nodes) {
      const p = pos.get(n.id);
      const g = s("g", { class: "net-node" });
      g.append(s("circle", { class: "hit", cx: p.x, cy: p.y, r: radius(n) + 8 }));
      g.append(s("circle", { class: "mark", cx: p.x, cy: p.y, r: radius(n) }));
      const cos = Math.cos(p.a);
      const sin = Math.sin(p.a);
      const lines = wrap(narrow ? n.short : n.label, narrow ? 11 : 22);
      const vertical = Math.abs(cos) < 0.2;
      const reach = radiusRing + radius(n) + 8;
      g.append(multiline(lines, {
        class: "net-label",
        x: cx + reach * cos,
        y: cy + reach * sin + (vertical ? Math.sign(sin) * (lines.length * 7 + 2) : 0),
        "text-anchor": vertical ? "middle" : cos > 0 ? "start" : "end",
      }, "middle", 14));
      const strongest = links
        .filter((l) => (l.a === n.id || l.b === n.id) && isNum(l.lift))
        .sort((x1, x2) => x2.lift - x1.lift)
        .slice(0, 3)
        .map((l) => [`With ${byId.get(l.a === n.id ? l.b : l.a)?.short ?? "?"}`, `${l.lift.toFixed(1)} times chance`]);
      bindTip(g, () => ({ title: n.label, lines: [["Person-years with it", `${percent(n.value)} (${count(n.count)})`], ...strongest] }));
      g.addEventListener("pointerenter", () => highlight(n.id));
      g.addEventListener("pointerleave", () => highlight(null));
      g.addEventListener("focus", () => highlight(n.id));
      g.addEventListener("blur", () => highlight(null));
      nodeGroups.set(n.id, g);
      nodeLayer.append(g);
    }
    return root;
  });
}

window.SharpCharts = {
  HIDDEN,
  isNum,
  h,
  s,
  count,
  compactCount,
  percent,
  signed,
  wrap,
  niceTicks,
  announce,
  swatch,
  hideTip,
  releaseCharts,
  legend,
  figure,
  dataTable,
  lineChart,
  dotRows,
  stackedBars,
  barList,
  networkChart,
};
})();
