// Draws every section of the results site from docs/data/<profile>.js, which
// python -m runner.site_data builds from results/<profile>/. Data comes in script files
// rather than fetched JSON so the page also works when opened straight from disk.

(() => {
const {
  h, isNum, count, compactCount, percent, signed, figure, dataTable, lineChart, dotRows,
  stackedBars, barList, networkChart, releaseCharts, announce,
} = window.SharpCharts;

const PROFILES = { full: "Full cohort", sample_30pct: "30% sample", sample_1pct: "1% sample" };
const COLORS = {
  hiv: "#1B4B85",
  controls: "#7BA2D6",
  ramp3: ["#8DAFDD", "#4F7FBF", "#1B4B85"],
  ramp4: ["#93B3DE", "#6A93CD", "#3F6CAD", "#1B4B85"],
};
const SERIES = {
  hiv: { key: "hiv", label: "People with HIV", color: COLORS.hiv, style: "dot" },
  matched: { key: "matched", label: "Matched controls", color: COLORS.controls, style: "dot" },
  pool: { key: "pool", label: "All controls, before matching", color: COLORS.controls, style: "ring" },
};
const RACE = {
  "ASIAN OR PACIFIC ISLANDER": "Asian or Pacific Islander",
  "BLACK OR AFRICAN AMERICAN": "Black or African American",
  "HISPANIC OR LATINO": "Hispanic or Latino",
  OTHER: "Other",
  WHITE: "White",
};
const SEX = { F: "Female", M: "Male" };
// Gagne group: full name, short name for small screens, weight in the score
const GAGNE = {
  1: ["Metastatic cancer", "Metastatic cancer", 5], 2: ["Congestive heart failure", "Heart failure", 2],
  3: ["Dementia", "Dementia", 2], 4: ["Renal failure", "Renal failure", 2], 5: ["Weight loss", "Weight loss", 2],
  6: ["Hemiplegia", "Hemiplegia", 1], 7: ["Alcohol abuse", "Alcohol abuse", 1], 8: ["Any tumor", "Any tumor", 1],
  9: ["Cardiac arrhythmias", "Arrhythmia", 1], 10: ["Chronic pulmonary disease", "Lung disease", 1],
  11: ["Coagulopathy", "Coagulopathy", 1], 12: ["Complicated diabetes", "Compl. diabetes", 1],
  13: ["Deficiency anemia", "Anemia", 1], 14: ["Fluid and electrolyte disorders", "Fluid, electrolytes", 1],
  15: ["Liver disease", "Liver disease", 1], 16: ["Peripheral vascular disease", "Peripheral vascular", 1],
  17: ["Psychosis", "Psychosis", 1], 18: ["Pulmonary circulation disorders", "Pulmonary circ.", 1],
  19: ["HIV/AIDS", "HIV/AIDS", -1], 20: ["Hypertension", "Hypertension", -1],
};
const LEVELS = [["0 or less", "0 or less"], ["1-2", "1 to 2"], ["3-4", "3 to 4"], ["5+", "5 or more"]];
const AGE_GROUPS = ["50-64", "65-74", "75+"];
const REPO = "https://github.com/nucapstone/SHARP";

const pctAxis = (v) => `${v}%`;
const score = (v) => (isNum(v) ? v.toFixed(2) : "hidden");
const years1 = (v) => (isNum(v) ? v.toFixed(1) : "hidden");
const smd = (v) => (isNum(v) ? (Math.abs(v) < 0.005 ? "0.00" : v.toFixed(2)) : "n/a");
const pointGap = (a, b) => (isNum(a) && isNum(b) ? signed(a - b) : "");
const strong = (text) => h("strong", { text });
const finding = (...parts) => h("p", { class: "finding" }, parts);
const note = (...parts) => h("p", { class: "note" }, parts);
const unique = (values) => [...new Set(values)];

class MissingResult extends Error {}

function table(data, name) {
  const t = data.tables[name];
  if (!t) throw new MissingResult(`The result table ${name} is not in this profile's data.`);
  return t.rows.map((r) => Object.fromEntries(t.columns.map((c, i) => [c, r[i]])));
}

function sum(rows, key) {
  return rows.every((r) => isNum(r[key])) ? rows.reduce((a, r) => a + r[key], 0) : null;
}

// Pool one condition's rows (over age groups) into a share of person-years per HIV group.
function pooledConditions(rows) {
  const out = new Map();
  for (const r of rows) {
    const item = out.get(r.condition) ?? { condition: r.condition, label: r.label, groups: {} };
    (item.groups[r.hiv] ??= []).push(r);
    out.set(r.condition, item);
  }
  for (const item of out.values()) {
    item.pct = {};
    item.n = {};
    for (const [hiv, rs] of Object.entries(item.groups)) {
      const n = sum(rs, "person_years");
      const withIt = sum(rs, "person_years_with");
      item.n[hiv] = n;
      item.pct[hiv] = isNum(n) && isNum(withIt) && n > 0 ? (100 * withIt) / n : null;
    }
  }
  return out;
}

function countRows(rows, seriesKey) {
  const labels = ["No conditions", "1 condition", "2 conditions", "3 conditions", "4 or more"];
  return labels.map((label, n) => ({
    label,
    values: Object.fromEntries(rows.filter((r) => r.n_conditions === n).map((r) => [seriesKey(r), r.pct_of_group])),
  }));
}

// ---------------------------------------------------------------- overview

function overview(data, body) {
  const steps = new Map(table(data, "4_matching/consort_first_year").map((r) => [r.step_order, r.people]));
  const firstYear = table(data, "1_cohort/eligible_by_year")[0]?.analysis_year ?? "";
  const items = [
    [1, "people in Komodo Health claims"],
    steps.get(2) !== steps.get(1) ? [2, "in this sample"] : null,
    [3, `aged 50 or older and alive all of ${firstYear}`],
    [4, "with medical and pharmacy coverage all year, one payer for each"],
    [5, "with birth date, sex, state and race on record: eligible"],
    [7, "without HIV: the control pool"],
    [6, "with HIV", "is-hiv"],
    [9, "people with HIV matched, each to one person without HIV", "is-hiv is-final"],
  ].filter(Boolean);
  const size = (n) => (isNum(n) && n > 0 ? Math.max(20, Math.min(64, 16 + (Math.log10(n) - 3) * 9)) : 20);
  body.replaceChildren(
    h("h2", { class: "cascade-title", text: `${firstYear}, the first study year, step by step` }),
    h("ol", { class: "cascade" }, items.map(([step, what, cls]) =>
      h("li", { class: cls ?? null },
        h("span", { class: "count", vars: { "--size": size(steps.get(step)) }, text: count(steps.get(step)) }),
        h("span", { class: "what", text: what })))),
    h("p", { class: "cascade-note" },
      "Each number's size follows the logarithm of the count: one step smaller is about ten times fewer people. ",
      `${count(steps.get(8))} eligible people were in neither group, because their HIV was first found in a later year `,
      "or they were not covered all year after their HIV date."),
  );
}

// ---------------------------------------------------------------- 1. eligible

function eligible(data, body) {
  const alive = table(data, "1_cohort/age50_alive_by_year");
  const insured = table(data, "1_cohort/same_insurance_by_year");
  const elig = table(data, "1_cohort/eligible_by_year");
  const years = elig.map((r) => r.analysis_year);
  const byYear = (rows, key) => years.map((y) => rows.find((r) => r[key] === y)?.people ?? null);
  const series = [
    { label: "Aged 50+, alive all year", color: COLORS.ramp3[0], style: "line", values: byYear(alive, "yr") },
    { label: "Covered all year, one payer", color: COLORS.ramp3[1], style: "line", values: byYear(insured, "yr") },
    { label: "Eligible", color: COLORS.ramp3[2], style: "line", values: byYear(elig, "analysis_year") },
  ];
  const total = table(data, "1_cohort/eligible_one_row_per_person_year")[0]?.person_years;
  const eligibleCounts = series[2].values.filter(isNum);
  const { fig, plot } = figure({
    title: "People left after each eligibility step, by year",
    description: "A person can be eligible in several years; each year is checked on its own.",
    legendItems: series,
    source: "1_cohort/age50_alive_by_year, same_insurance_by_year, eligible_by_year",
  });
  body.replaceChildren(
    finding(strong(count(total)), ` eligible person-years from ${years[0]} to ${years.at(-1)}, between `,
      strong(count(Math.min(...eligibleCounts))), " and ", strong(count(Math.max(...eligibleCounts))), " people a year."),
    fig,
  );
  lineChart(plot, { x: years, series, format: count, endFormat: compactCount, axisFormat: compactCount, label: "People left after each eligibility step, by year" });
}

// ---------------------------------------------------------------- 2. HIV and control groups

function groups(data, body) {
  const evidence = table(data, "2_hiv_groups/any_hiv_evidence_people")[0] ?? {};
  const perYear = table(data, "2_hiv_groups/hiv_group_by_year");
  const pool = table(data, "2_hiv_groups/control_pool_by_year");
  const overlap = table(data, "2_hiv_groups/hiv_rule_overlap");
  const someRecord = table(data, "2_hiv_groups/controls_with_some_hiv_record")[0]?.people;
  const years = perYear.map((r) => r.analysis_year);
  const hivSeries = [{ label: "People with HIV", color: COLORS.hiv, values: perYear.map((r) => r.people) }];
  const hivCounts = hivSeries[0].values.filter(isNum);

  const trend = figure({
    title: "People with HIV in each study year",
    description: "Eligible that year and with HIV found in that year or before.",
    source: "2_hiv_groups/hiv_group_by_year, control_pool_by_year",
  });

  const overall = overlap.find((r) => String(r.found_by).includes("overall"))?.people;
  const routeLabel = (text) => {
    const clean = String(text).replace(/^\d+\s*/, "").replaceAll(" + ", " and ").replace("all three", "all three routes");
    return clean.charAt(0).toUpperCase() + clean.slice(1);
  };
  const routeRows = overlap.filter((r) => !String(r.found_by).includes("overall")).map((r) => ({
    label: routeLabel(r.found_by),
    value: r.people,
    extra: isNum(r.people) && isNum(overall) ? [["Share of everyone with HIV", percent((100 * r.people) / overall)]] : [],
  }));
  const routes = figure({
    title: "Which routes found each person with HIV",
    description: `Everyone who ever met the definition (${count(overall)} people), by the combination of routes that found them.`,
    source: "2_hiv_groups/hiv_rule_overlap",
  });

  body.replaceChildren(
    finding(strong(count(evidence.met_hiv_definition)), " people met the HIV definition at some point, out of ",
      strong(count(evidence.any_evidence)), " with any HIV record. Each year, between ",
      strong(count(Math.min(...hivCounts))), " and ", strong(count(Math.max(...hivCounts))), " of them were eligible."),
    trend.fig, routes.fig,
    note(`${count(someRecord)} people in the control pool have an HIV record that does not meet the definition, such as a single diagnosis or a single medicine fill. Under the lab's rule, anyone who is not an HIV case can be a control.`),
  );
  lineChart(trend.plot, { x: years, series: hivSeries, format: count, axisFormat: compactCount, label: "People with HIV in each study year" });
  barList(routes.plot, { rows: routeRows, format: count, label: "People with HIV by the routes that found them" });
}

// ---------------------------------------------------------------- 3 and 5. conditions

function conditionFigure(rows, series, title, description, source) {
  const { fig, plot } = figure({
    title,
    description,
    legendItems: series,
    source,
  });
  return { fig, draw: () => dotRows(plot, { rows, series, format: percent, axisFormat: pctAxis, label: title, aside: (r) => r.gap, asideLabel: "Gap" }) };
}

function before(data, body) {
  const pooled = pooledConditions(table(data, "3_conditions/conditions_before_matching_by_age"));
  const series = [SERIES.pool, SERIES.hiv];
  const rows = [...pooled.values()]
    .map((c) => ({
      label: c.label,
      values: { pool: c.pct[0], hiv: c.pct[1] },
      gap: pointGap(c.pct[1], c.pct[0]),
      extra: [["Person-years, controls", count(c.n[0])], ["Person-years, HIV", count(c.n[1])]],
    }))
    .sort((a, b) => (b.values.hiv ?? -1) - (a.values.hiv ?? -1));
  const compared = rows.filter((r) => isNum(r.values.hiv) && isNum(r.values.pool));
  const higher = compared.filter((r) => r.values.hiv > r.values.pool).length;
  const main = conditionFigure(rows, series, "Share of person-years with each condition, before matching",
    "All years and ages pooled. Gap is percentage points: people with HIV minus all controls.",
    "3_conditions/conditions_before_matching_by_age");
  const countsRows = countRows(table(data, "3_conditions/condition_count_before_matching"), (r) => (r.hiv === 1 ? "hiv" : "pool"));
  const counts = figure({
    title: "How many of the 11 conditions each person-year has, before matching",
    legendItems: series,
    source: "3_conditions/condition_count_before_matching",
  });
  body.replaceChildren(
    finding("Before matching, people with HIV had a higher share than the whole control pool for ", strong(`${higher} of the ${compared.length}`),
      compared.length < rows.length ? " conditions with enough people to show." : " conditions.",
      " The pool is older and differs in sex and race, so these gaps are not yet a fair comparison."),
    main.fig, counts.fig,
  );
  main.draw();
  dotRows(counts.plot, { rows: countsRows, series, format: percent, axisFormat: pctAxis, label: "Number of conditions per person-year, before matching" });
}

function after(data, body) {
  const beforePooled = pooledConditions(table(data, "3_conditions/conditions_before_matching_by_age"));
  const afterPooled = pooledConditions(table(data, "4_matching/conditions_after_matching_by_age"));
  const series = [SERIES.pool, SERIES.matched, SERIES.hiv];
  const rows = [...afterPooled.values()]
    .map((c) => ({
      label: c.label,
      values: { pool: beforePooled.get(c.condition)?.pct[0] ?? null, matched: c.pct[0], hiv: c.pct[1] },
      gap: pointGap(c.pct[1], c.pct[0]),
      extra: [["Person-years in each matched group", count(c.n[1])]],
    }))
    .sort((a, b) => (b.values.hiv ?? -1) - (a.values.hiv ?? -1));
  const compared = rows.filter((r) => isNum(r.values.hiv) && isNum(r.values.matched));
  const higher = compared.filter((r) => r.values.hiv > r.values.matched).length;
  const largest = [...compared].sort((a, b) => Math.abs(b.values.hiv - b.values.matched) - Math.abs(a.values.hiv - a.values.matched))[0];
  const main = conditionFigure(rows, series, "Share of person-years with each condition, after matching",
    "Open circles repeat the whole control pool from step 3. Gap is percentage points: people with HIV minus matched controls.",
    "4_matching/conditions_after_matching_by_age");
  const countsRows = countRows(table(data, "4_matching/condition_count_after_matching"), (r) => (r.hiv === 1 ? "hiv" : "matched"));
  const counts = figure({
    title: "How many of the 11 conditions each person-year has, after matching",
    legendItems: [SERIES.matched, SERIES.hiv],
    source: "4_matching/condition_count_after_matching",
  });
  body.replaceChildren(
    finding("After matching, people with HIV had a higher share for ", strong(`${higher} of the ${compared.length}`),
      compared.length < rows.length ? " conditions with enough people to show" : " conditions",
      largest ? [". The largest gap is ", strong(largest.label.toLowerCase()), `, ${largest.gap} points.`] : "."),
    main.fig, counts.fig,
  );
  main.draw();
  dotRows(counts.plot, { rows: countsRows, series: [SERIES.matched, SERIES.hiv], format: percent, axisFormat: pctAxis, label: "Number of conditions per person-year, after matching" });
}

// ---------------------------------------------------------------- 4. matching

function balanceLabel(variable) {
  if (variable === "distance") return "Propensity score (logit)";
  if (variable === "birth_year") return "Birth year";
  const [kind, value] = String(variable).split(": ");
  if (kind === "census_region") return `Region: ${value}`;
  if (kind === "patient_race_ethnicity") return `Race: ${RACE[value] ?? value}`;
  return String(variable);
}

function characteristicsTable(rows) {
  const columns = [["before", 0, "All controls, before matching"], ["before", 1, "People with HIV"], ["after", 0, "Matched controls"]];
  const cell = (stage, hiv, variable, category) =>
    rows.find((r) => r.stage === stage && r.hiv === hiv && r.variable === variable && r.category === category);
  const variables = unique(rows.map((r) => r.variable));
  const pretty = (variable, category) => (variable === "sex" ? SEX[category] ?? category : variable === "race and ethnicity" ? RACE[category] ?? category : category);
  const first = variables[0];
  const bodyRows = [
    h("tr", {}, h("th", { scope: "row", text: "Person-years" }),
      columns.map(([stage, hiv]) => h("td", { class: "num", text: count(sum(rows.filter((r) => r.stage === stage && r.hiv === hiv && r.variable === first), "person_years")) }))),
  ];
  for (const variable of variables) {
    bodyRows.push(h("tr", { class: "group" }, h("th", { scope: "colgroup", colspan: 4, text: variable.charAt(0).toUpperCase() + variable.slice(1) })));
    for (const category of unique(rows.filter((r) => r.variable === variable).map((r) => r.category))) {
      bodyRows.push(h("tr", {}, h("th", { scope: "row", text: pretty(variable, category) }),
        columns.map(([stage, hiv]) => h("td", { class: "num", text: percent(cell(stage, hiv, variable, category)?.pct_of_group) }))));
    }
  }
  return h("div", { class: "table-wrap", tabindex: 0, role: "region", "aria-label": "Characteristics before and after matching" },
    h("table", { class: "table-one" },
      h("caption", { class: "visually-hidden", text: "Characteristics before and after matching, percent of person-years" }),
      h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Percent of person-years" }), columns.map(([, , label]) => h("th", { scope: "col", class: "num", text: label })))),
      h("tbody", {}, bodyRows)));
}

function matching(data, body) {
  const matched = table(data, "4_matching/matched_by_year");
  const age = table(data, "4_matching/age_before_and_after_matching");
  const balance = table(data, "4_matching/balance_smd");
  const ageOf = (stage, hiv) => age.find((r) => r.stage === stage && r.hiv === hiv)?.mean_age;
  const hivPeople = sum(matched, "hiv_people");
  const hivMatched = sum(matched, "hiv_matched");
  const years = unique(balance.map((r) => r.analysis_year));

  const series = [
    { key: "before", label: "Before matching", color: COLORS.controls, style: "ring" },
    { key: "after", label: "After matching", color: COLORS.hiv, style: "dot" },
  ];
  const yearSelect = h("select", { id: "balance-year" }, years.map((y) => h("option", { value: y, text: y })));
  const love = figure({
    title: "Balance of each matching variable",
    description: "Standardized mean difference between people with HIV and controls. The shaded band is ±0.1, the usual limit for good balance. Sex is matched exactly, so it is always balanced.",
    controls: h("label", { class: "control", for: "balance-year" }, "Year", yearSelect),
    legendItems: series,
    source: "4_matching/balance_smd",
  });
  const drawLove = () => {
    const year = Number(yearSelect.value);
    const rows = balance.filter((r) => r.analysis_year === year).map((r) => ({
      label: balanceLabel(r.variable),
      values: { before: r.smd_before, after: r.smd_after },
    }));
    const extent = Math.max(0.25, ...rows.flatMap((r) => [r.values.before, r.values.after]).filter(isNum).map(Math.abs));
    dotRows(love.plot, { rows, series, format: smd, axisFormat: (v) => v.toFixed(1), domain: [-extent, extent], ref: 0, band: [-0.1, 0.1], label: `Balance of each matching variable in ${year}` });
  };
  yearSelect.addEventListener("change", drawLove);

  const tableOne = h("figure", { class: "figure" },
    h("figcaption", {}, h("h3", { text: "Characteristics before and after matching" }),
      h("p", { text: "Percent of person-years in each group, all study years together." })),
    characteristicsTable(table(data, "4_matching/characteristics_before_and_after_matching")),
    h("p", { class: "source", text: "From 4_matching/characteristics_before_and_after_matching" }));

  const share = isNum(hivPeople) && isNum(hivMatched) && hivPeople > 0 ? percent((100 * hivMatched) / hivPeople) : "hidden";
  body.replaceChildren(
    finding(strong(count(hivMatched)), " of ", strong(count(hivPeople)), ` person-years of people with HIV found a match (${share}). The controls' mean age went from `,
      strong(years1(ageOf("before", 0))), " before matching to ", strong(years1(ageOf("after", 0))),
      ", against ", strong(years1(ageOf("before", 1))), " for people with HIV."),
    love.fig, tableOne,
  );
  drawLove();
}

// ---------------------------------------------------------------- 6. Gagne

function gagne(data, body) {
  const scores = table(data, "5_gagne/gagne_scores_by_year");
  const levels = table(data, "5_gagne/gagne_levels");
  const prevalence = table(data, "5_gagne/gagne_group_prevalence");
  const links = table(data, "5_gagne/gagne_network_links");
  const years = unique(scores.map((r) => r.analysis_year));
  const scoreOf = (hiv) => years.map((y) => scores.find((r) => r.analysis_year === y && r.hiv === hiv)?.mean_score_excl_hiv ?? null);
  const series = [
    { label: "People with HIV", color: COLORS.hiv, style: "line", values: scoreOf(1) },
    { label: "Matched controls", color: COLORS.controls, style: "line", values: scoreOf(0) },
  ];
  const pooledMean = (hiv) => {
    const rs = scores.filter((r) => r.hiv === hiv);
    const n = sum(rs, "person_years");
    return isNum(n) && n > 0 && rs.every((r) => isNum(r.mean_score_excl_hiv)) ? rs.reduce((a, r) => a + r.mean_score_excl_hiv * r.person_years, 0) / n : null;
  };
  const trend = figure({
    title: "Mean Gagne score by year, leaving out the HIV/AIDS group",
    legendItems: series,
    source: "5_gagne/gagne_scores_by_year",
  });

  const parts = LEVELS.map(([key, label], i) => ({ key, label, color: COLORS.ramp4[i], dark: i >= 2 }));
  const bars = [[0, "Matched controls"], [1, "People with HIV"]].map(([hiv, label]) => {
    const rs = levels.filter((r) => r.hiv === hiv);
    return {
      label,
      values: Object.fromEntries(rs.map((r) => [r.gagne_level, r.pct_of_group])),
      counts: Object.fromEntries(rs.map((r) => [r.gagne_level, r.person_years])),
    };
  });
  const levelFig = figure({
    title: "Person-years at each Gagne level",
    description: "These levels are the strata for the care quality comparison in step 7.",
    legendItems: parts.map((p) => ({ ...p, style: "block" })),
    source: "5_gagne/gagne_levels",
  });

  const groupIds = Object.keys(GAGNE).map(Number);
  const prevOf = (hiv, id) => prevalence.find((r) => r.hiv === hiv && r.gagne_group === id);
  const groupRows = groupIds.map((id) => ({
    label: GAGNE[id][0],
    values: { matched: prevOf(0, id)?.pct_with_group ?? null, hiv: prevOf(1, id)?.pct_with_group ?? null },
    gap: pointGap(prevOf(1, id)?.pct_with_group, prevOf(0, id)?.pct_with_group),
    extra: [["Weight in the score", String(GAGNE[id][2]).replace("-", "−")]],
  })).sort((a, b) => (b.values.hiv ?? -1) - (a.values.hiv ?? -1));
  const groupFig = figure({
    title: "Share of person-years with each Gagne group",
    description: "Gap is percentage points: people with HIV minus matched controls.",
    legendItems: [SERIES.matched, SERIES.hiv],
    source: "5_gagne/gagne_group_prevalence",
  });

  const groupChoice = h("div", { class: "segmented small", role: "radiogroup", "aria-label": "Group shown in the network" },
    [[1, "People with HIV"], [0, "Matched controls"]].map(([value, label], i) =>
      h("label", {}, h("input", { type: "radio", name: "network-group", value, checked: i === 0 }), h("span", { text: label }))));
  const liftSelect = h("select", { id: "network-lift" }, [1.5, 2, 3, 5].map((v) => h("option", { value: v, text: `${v} times or more`, selected: v === 3 })));
  const linkRows = links.map((l) => ({ ...l, pair: `${GAGNE[l.group_a]?.[0] ?? l.group_a} and ${GAGNE[l.group_b]?.[0] ?? l.group_b}` }))
    .sort((a, b) => (b.lift ?? 0) - (a.lift ?? 0));
  const network = figure({
    title: "Which Gagne groups occur together",
    description: "A line joins two groups found in the same person-year more often than chance (lift: how many times more often). Thicker, darker lines mean a higher lift. Pairs seen in fewer than 11 person-years are left out. Hover or focus a group to see its partners.",
    controls: [groupChoice, h("label", { class: "control", for: "network-lift" }, "Show pairs found together", liftSelect)],
    source: "5_gagne/gagne_network_links, gagne_group_prevalence",
  });
  const drawNetwork = () => {
    const hiv = Number(groupChoice.querySelector("input:checked")?.value ?? 1);
    const nodes = groupIds.map((id) => ({ id, label: GAGNE[id][0], short: GAGNE[id][1], value: prevOf(hiv, id)?.pct_with_group ?? null, count: prevOf(hiv, id)?.person_years_with ?? null }));
    const groupLinks = links.filter((l) => l.hiv === hiv).map((l) => ({ a: l.group_a, b: l.group_b, lift: l.lift, count: l.person_years_with_both }));
    networkChart(network.plot, { nodes, links: groupLinks, minLift: Number(liftSelect.value), label: `Gagne groups that occur together, ${hiv === 1 ? "people with HIV" : "matched controls"}` });
  };
  groupChoice.addEventListener("change", drawNetwork);
  liftSelect.addEventListener("change", drawNetwork);

  const high = (hiv) => levels.find((r) => r.hiv === hiv && r.gagne_level === "5+")?.pct_of_group;
  body.replaceChildren(
    finding("Leaving out the HIV/AIDS group, people with HIV averaged a Gagne score of ", strong(score(pooledMean(1))),
      ", against ", strong(score(pooledMean(0))), " for their matched controls. ", strong(percent(high(1))),
      " of their person-years scored 5 or more, against ", strong(percent(high(0))), "."),
    trend.fig, levelFig.fig, groupFig.fig, network.fig,
  );
  lineChart(trend.plot, { x: years, series, format: score, label: "Mean Gagne score by year" });
  stackedBars(levelFig.plot, { bars, parts, label: "Person-years at each Gagne level" });
  dotRows(groupFig.plot, { rows: groupRows, series: [SERIES.matched, SERIES.hiv], format: percent, axisFormat: pctAxis, label: "Share of person-years with each Gagne group", aside: (r) => r.gap, asideLabel: "Gap" });
  drawNetwork();
}

// ---------------------------------------------------------------- 7. care quality

function care(data, body) {
  const overall = table(data, "6_care_quality/care_quality_overall");
  const byYear = table(data, "6_care_quality/care_quality_by_year");
  const byLevel = table(data, "6_care_quality/care_quality_by_gagne_level");
  const byAge = table(data, "6_care_quality/care_quality_by_age");
  const measures = unique(overall.map((r) => r.measure_id)).map((id) => {
    const rs = overall.filter((r) => r.measure_id === id);
    const of = (hiv) => rs.find((r) => r.hiv === hiv) ?? {};
    const lowerBetter = rs[0].higher_is_better === 0;
    return { id, condition: rs[0].condition, label: rs[0].label + (lowerBetter ? " (lower is better)" : ""), lowerBetter, controls: of(0), hiv: of(1) };
  });
  const series = [SERIES.matched, SERIES.hiv];
  const rows = [];
  for (const condition of unique(measures.map((m) => m.condition))) {
    rows.push({ heading: condition });
    for (const m of measures.filter((x) => x.condition === condition)) {
      rows.push({
        label: m.label,
        values: { matched: m.controls.pct_met, hiv: m.hiv.pct_met },
        gap: pointGap(m.hiv.pct_met, m.controls.pct_met),
        extra: [["Controls who met it", `${count(m.controls.person_years_met)} of ${count(m.controls.person_years)}`],
          ["People with HIV who met it", `${count(m.hiv.person_years_met)} of ${count(m.hiv.person_years)}`]],
      });
    }
  }
  const shown = measures.filter((m) => isNum(m.controls.pct_met) && isNum(m.hiv.pct_met));
  const worse = shown.filter((m) => (m.lowerBetter ? m.hiv.pct_met > m.controls.pct_met : m.hiv.pct_met < m.controls.pct_met));
  const hidden = measures.length - shown.length;
  const overview = figure({
    title: "Share of person-years that met each care quality measure",
    description: "Matched groups, all years together. Gap is percentage points: people with HIV minus matched controls.",
    legendItems: series,
    source: "6_care_quality/care_quality_overall",
  });

  const choice = h("select", { id: "care-measure" }, measures.map((m) =>
    h("option", { value: m.id, text: `${m.condition}: ${m.label}`, selected: m === (shown[0] ?? measures[0]) })));
  const detail = h("div", { class: "care-detail" });
  const drawDetail = () => {
    releaseCharts(detail);
    const m = measures.find((x) => x.id === choice.value) ?? measures[0];
    const yearRows = byYear.filter((r) => r.measure_id === m.id);
    const years = unique(yearRows.map((r) => r.analysis_year));
    const pctIn = (rs, hiv, key, value) => rs.find((r) => r.hiv === hiv && r[key] === value)?.pct_met ?? null;
    const yearSeries = [
      { label: "People with HIV", color: COLORS.hiv, style: "line", values: years.map((y) => pctIn(yearRows, 1, "analysis_year", y)) },
      { label: "Matched controls", color: COLORS.controls, style: "line", values: years.map((y) => pctIn(yearRows, 0, "analysis_year", y)) },
    ];
    const metText = (rs, hiv, key, value) => {
      const r = rs.find((x) => x.hiv === hiv && x[key] === value);
      return r ? `${count(r.person_years_met)} of ${count(r.person_years)}` : "n/a";
    };
    const strata = (rs, key, values, labels) => values.map((value, i) => ({
      label: labels[i],
      values: { matched: pctIn(rs, 0, key, value), hiv: pctIn(rs, 1, key, value) },
      extra: [["Controls who met it", metText(rs, 0, key, value)], ["People with HIV who met it", metText(rs, 1, key, value)]],
    }));
    const levelRows = strata(byLevel.filter((r) => r.measure_id === m.id), "gagne_level", LEVELS.map((l) => l[0]), LEVELS.map((l) => `Gagne ${l[1]}`));
    const ageRows = strata(byAge.filter((r) => r.measure_id === m.id), "age_group", AGE_GROUPS, ["Aged 50 to 64", "Aged 65 to 74", "Aged 75 and older"]);
    const yearFig = figure({
      title: "By year",
      legendItems: yearSeries,
      source: "6_care_quality/care_quality_by_year",
    });
    const levelFig = figure({ title: "Within Gagne levels", description: "People with HIV compared with controls who are about as sick.", legendItems: series,source: "6_care_quality/care_quality_by_gagne_level" });
    const ageFig = figure({ title: "By age", legendItems: series,source: "6_care_quality/care_quality_by_age" });
    detail.replaceChildren(yearFig.fig, h("div", { class: "pair" }, levelFig.fig, ageFig.fig));
    lineChart(yearFig.plot, { x: years, series: yearSeries, format: percent, axisFormat: pctAxis, label: `${m.label}, by year` });
    dotRows(levelFig.plot, { rows: levelRows, series, format: percent, axisFormat: pctAxis, label: `${m.label}, by Gagne level` });
    dotRows(ageFig.plot, { rows: ageRows, series, format: percent, axisFormat: pctAxis, label: `${m.label}, by age` });
  };
  choice.addEventListener("change", drawDetail);

  body.replaceChildren(
    finding("People with HIV met the measure less often on ", strong(`${worse.length} of ${shown.length}`),
      " measures with enough people to show", hidden ? `; ${hidden} more are hidden because they rest on fewer than 11 person-years.` : "."),
    overview.fig,
    h("div", { class: "detail-head" },
      h("h3", { text: "One measure in detail" }),
      h("label", { class: "control", for: "care-measure" }, "Measure", choice)),
    detail,
  );
  dotRows(overview.plot, { rows, series, format: percent, axisFormat: pctAxis, label: "Care quality measures, matched groups", aside: (r) => r.gap, asideLabel: "Gap" });
  drawDetail();
}

// ---------------------------------------------------------------- methods (run details)

function runDetails(data, body, profile) {
  const run = data.run ?? {};
  const commit = /^[0-9a-f]{7,40}$/.test(String(run.git_commit)) ? run.git_commit : null;
  const finished = run.finished_utc ? new Date(run.finished_utc) : null;
  const when = finished && !Number.isNaN(finished.getTime())
    ? finished.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })
    : "an unknown date";
  body.replaceChildren(h("p", { class: "run-details" },
    `These are the ${PROFILES[profile].toLowerCase()} results from the run that finished on ${when}`,
    commit ? [", from commit ", h("a", { href: `${REPO}/commit/${commit}`, text: commit.slice(0, 7) }), "."] : "."));
}

// ---------------------------------------------------------------- loading and state

// ---------------------------------------------------------------- every other result, explained

// Each step's result tables that no chart above draws, so every saved result is on the site. A check
// table becomes one sentence; the others are a table under a short explanation.
const MORE = {
  eligible: [
    ["1_cohort/study_people", "Everyone in this run", "The people in the Komodo data for this run, before any rule is applied."],
  ],
  groups: [
    ["2_hiv_groups/hiv_people_by_rule", "People found by each route", "Everyone who ever met the HIV definition, and how many each route found. One person can be found by more than one route, so the routes add up to more than the total."],
    ["2_hiv_groups/hiv_inpatient_people", "Found by an inpatient HIV diagnosis", "People with an inpatient HIV diagnosis or HIV MS-DRG at any time."],
    ["2_hiv_groups/hiv_outpatient_people", "Found by two outpatient HIV diagnoses", "People with two outpatient HIV diagnoses at least seven days apart."],
    ["2_hiv_groups/hiv_rx_people", "Found by two HIV medicine fills", "People with two fills of HIV medicines within 90 days. Medicines also used for PrEP, hepatitis B or COVID-19 do not count on their own."],
    ["2_hiv_groups/hiv_group_one_row_per_person_year", "check", "the HIV group has one row per person-year"],
    ["2_hiv_groups/control_pool_hiv_check", "check", "nobody with HIV is in the control pool"],
  ],
  before: [
    ["3_conditions/study_person_years_by_year", "Person-years in each group, by year", "The people compared in this step: everyone with HIV and the whole control pool, year by year."],
    ["3_conditions/conditions_before_matching_by_year", "Each condition by year, before matching", "The share of person-years with each condition, year by year, people with HIV against all controls."],
    ["3_conditions/condition_dx_rows_by_year", "Diagnosis claims read for the conditions", "How many diagnosis rows, and how many distinct codes, matched the condition code lists each year."],
    ["3_conditions/study_one_row_per_person_year", "check", "the study table has one row per person-year"],
    ["3_conditions/person_year_conditions_check", "check", "no condition is counted twice for the same person-year"],
  ],
  matching: [
    ["4_matching/ps_input_by_year_sex", "Who went into the propensity model", "Each year and sex: the people with HIV, and the 20 controls sampled for each of them."],
    ["4_matching/consort_first_year", "The 2016 steps, as a table", "The counts behind the funnel at the top of the page."],
    ["4_matching/ps_input_one_row_per_person_year", "check", "the propensity model input has one row per person-year"],
    ["4_matching/matched_one_row_per_person_year", "check", "the matched groups have one row per person-year"],
  ],
  after: [
    ["4_matching/conditions_after_matching_by_year", "Each condition by year, after matching", "The share of person-years with each condition, year by year, people with HIV against their matched controls."],
  ],
  care: [
    ["6_care_quality/procedure_concepts_by_year", "Procedures found, by year", "Matched person-years with each procedure a measure looks for, such as an eye exam or an HbA1c test."],
    ["6_care_quality/drug_concepts_by_year", "Medicine fills found, by year", "Matched person-years with a fill from each medicine group a measure looks for."],
    ["6_care_quality/drug_concept_names", "Medicines that count for each measure", "Every medicine name in the claims that was matched to a medicine group."],
    ["6_care_quality/quality_measures_check", "check", "each measure is scored once per person-year"],
  ],
};

// Rhea's figures (results/full/5_gagne/plots, copied to docs/figures by python -m runner.site_data)
const FIGURES = [
  ["1_score_over_time.png", "Mean Gagne score over time", "People with HIV against matched controls, 2016 to 2025, leaving out the HIV/AIDS group. The dashed line is the original score."],
  ["2_condition_prevalence.png", "Which Gagne groups differ", "Share of person-years with each Gagne group, people with HIV against matched controls, sorted by the gap."],
  ["3_score_distribution.png", "How scores are spread", "Share of person-years at each Gagne score, in both groups."],
  ["4_pair_differences.png", "Differences within matched pairs", "For each matched pair, the score of the person with HIV minus their control's score."],
  ["5_prevalence_gap_heatmap.png", "Gap by Gagne group and year", "Percentage-point gap, people with HIV minus matched controls, for each group and year."],
  ["6_comorbidity_age_gap.png", "Comorbidity burden by age", "Mean score by year of age, and how many years older people with HIV look in comorbidity terms."],
  ["7_comorbidity_network.png", "Which Gagne groups occur together", "The 25 pairs of groups most over-represented compared with chance, in each group."],
];

const COLUMN_NAMES = {
  analysis_year: "Year", yr: "Year", concept_year: "Year", hiv: "Group", people: "People",
  person_years: "Person-years", person_years_with: "Person-years with it", pct_with_condition: "Share",
  label: "Condition", condition: "Code", code_rows: "Diagnosis rows", distinct_codes: "Distinct codes",
  patient_gender: "Sex", with_hiv: "People with HIV", without_hiv: "Controls sampled", step_order: "Step",
  step: "What is left", generic_name: "Medicine", concept: "Group", by_inpatient: "Inpatient route",
  by_outpatient: "Outpatient route", by_rx: "Medicine route",
};
const LABEL_COLS = new Set(["analysis_year", "yr", "concept_year", "step_order", "hiv", "patient_gender", "step",
  "generic_name", "concept", "label", "condition", "age_group"]);

function cellText(column, value, controlsWord) {
  if (column === "hiv") return value === 1 ? "People with HIV" : controlsWord;
  if (column === "patient_gender") return SEX[value] ?? String(value ?? "");
  if (column.startsWith("pct_")) return percent(value);
  if (column.startsWith("mean_")) return isNum(value) ? value.toFixed(2) : "hidden";
  if (LABEL_COLS.has(column)) return String(value ?? "");
  return count(value);
}

function checkLine(rows, what) {
  const r = rows[0] ?? {};
  const pair = [["rows_total", "person_years"], ["rows_total", "distinct_rows"]].find(([a, b]) => a in r && b in r);
  const ok = "hiv_people_in_pool" in r ? r.hiv_people_in_pool === 0 : pair ? r[pair[0]] === r[pair[1]] : null;
  const size = isNum(r.rows_total) ? ` (${count(r.rows_total)} rows)` : "";
  const verdict = ok === null ? "Check not available:" : ok ? "Check passed:" : "Check failed:";
  return h("p", { class: "check-line" }, h("strong", { text: verdict }), ` ${what}${size}.`);
}

// Titles for the tables the charts draw (the others are titled in MORE), for the All results page
const TITLES = {
  "1_cohort/age50_alive_by_year": ["Aged 50 or older and alive all year", "People left after the age and survival rule, each year."],
  "1_cohort/same_insurance_by_year": ["Covered all year by one payer", "People left after the coverage rule, each year."],
  "1_cohort/eligible_by_year": ["Eligible people", "People left after every rule, each year."],
  "1_cohort/eligible_one_row_per_person_year": ["Eligible person-years", "The eligible table and its one-row-per-person-year check."],
  "2_hiv_groups/any_hiv_evidence_people": ["Any HIV record against the HIV definition", "People with any HIV record, and those who met the definition."],
  "2_hiv_groups/hiv_group_by_year": ["People with HIV each year", "Eligible that year, with HIV found in that year or before."],
  "2_hiv_groups/control_pool_by_year": ["Control pool each year", "Eligible people who are not HIV cases, each year."],
  "2_hiv_groups/hiv_rule_overlap": ["Which routes found each person", "People with HIV by the combination of routes that found them."],
  "2_hiv_groups/controls_with_some_hiv_record": ["Controls with an HIV record", "Controls with an HIV record that does not meet the definition."],
  "2_hiv_groups/hiv_drug_names": ["Medicines that identify HIV", "Every HIV medicine name in the claims that counts toward the definition."],
  "3_conditions/conditions_before_matching_by_age": ["Conditions by age, before matching", "Share of person-years with each condition, by age group."],
  "3_conditions/condition_count_before_matching": ["Number of conditions, before matching", "How many of the 11 conditions each person-year has."],
  "4_matching/matched_by_year": ["Matching, year by year", "People with HIV matched and not matched, and controls used, each year."],
  "4_matching/balance_smd": ["Balance of each matching variable", "Standardized mean difference before and after matching, each year."],
  "4_matching/characteristics_before_and_after_matching": ["Characteristics before and after matching", "Age group, sex, race and region of each group."],
  "4_matching/age_before_and_after_matching": ["Mean age before and after matching", "Mean age of each group."],
  "4_matching/conditions_after_matching_by_age": ["Conditions by age, after matching", "Share of person-years with each condition, by age group."],
  "4_matching/condition_count_after_matching": ["Number of conditions, after matching", "How many of the 11 conditions each person-year has."],
  "5_gagne/gagne_scores_by_year": ["Mean Gagne score by year", "Mean score with and without the HIV/AIDS group, and groups present."],
  "5_gagne/gagne_levels": ["Person-years at each Gagne level", "Share of person-years at each level of the score."],
  "5_gagne/gagne_group_prevalence": ["Share with each Gagne group", "Share of person-years with each of the 20 groups."],
  "5_gagne/gagne_network_links": ["Gagne groups found together", "Pairs of groups and how much more often than chance they occur together (lift)."],
  "6_care_quality/care_quality_overall": ["Care quality, all years", "Share of person-years that met each measure."],
  "6_care_quality/care_quality_by_year": ["Care quality by year", "Share that met each measure, each year."],
  "6_care_quality/care_quality_by_gagne_level": ["Care quality within Gagne levels", "Share that met each measure, among people equally sick."],
  "6_care_quality/care_quality_by_age": ["Care quality by age", "Share that met each measure, by age group."],
};
const STAGES = [["1_cohort", "Step 1: eligible people"], ["2_hiv_groups", "Step 2: people with HIV and the control pool"],
  ["3_conditions", "Step 3: conditions before matching"], ["4_matching", "Steps 4 and 5: matching, and conditions after matching"],
  ["5_gagne", "Step 6: how sick, the Gagne score"], ["6_care_quality", "Step 7: care quality"]];
const PART_STAGE = { eligible: "1_cohort", groups: "2_hiv_groups", before: "3_conditions", matching: "4_matching",
  after: "4_matching", gagne: "5_gagne", care: "6_care_quality" };

function titleOf(name) {
  if (TITLES[name]) return TITLES[name];
  const more = Object.values(MORE).flat().find((m) => m[0] === name && m[1] !== "check");
  if (more) return [more[1], more[2]];
  return [name.split("/")[1].replaceAll("_", " ").replace(/^./, (x) => x.toUpperCase()), ""];
}

function tableBlock(data, name) {
  const [title, about] = titleOf(name);
  const rows = table(data, name);
  const controlsWord = name.startsWith("3_conditions") ? "All controls" : "Matched controls";
  const columns = data.tables[name].columns.map((c) => ({
    label: COLUMN_NAMES[c] ?? c.replaceAll("_", " ").replace(/^./, (x) => x.toUpperCase()),
    numeric: !LABEL_COLS.has(c),
    value: (r) => cellText(c, r[c], controlsWord),
  }));
  return h("div", { class: "more-item", "data-search": `${title} ${about} ${name}`.toLowerCase() },
    h("h4", { text: title }), about ? h("p", { text: about }) : null,
    dataTable(columns, rows, title), h("p", { class: "source", text: `From ${name}` }));
}

// The All results page: every table of the run, by step, with a search box.
function results(data, body) {
  const search = h("input", { type: "search", id: "results-search", placeholder: "Search, for example diabetes or matching" });
  const groups = STAGES.map(([stage, label]) => {
    const names = Object.keys(data.tables).filter((n) => n.startsWith(`${stage}/`));
    return h("section", { class: "more-results", id: stage }, h("h3", { text: label }), names.map((n) => tableBlock(data, n)));
  });
  const empty = h("p", { class: "empty-note", hidden: true, text: "No table matches that search. Try a shorter word." });
  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    let shown = 0;
    for (const item of body.querySelectorAll(".more-item")) {
      item.hidden = q !== "" && !item.dataset.search.includes(q);
      if (!item.hidden) shown += 1;
    }
    for (const g of groups) g.hidden = !g.querySelector(".more-item:not([hidden])");
    empty.hidden = shown > 0;
  });
  body.replaceChildren(h("label", { class: "control search", for: "results-search" }, "Search the tables", search), empty, ...groups);
  if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
}

// Under each step: its checks as sentences, Rhea's figures on the Gagne page, and a link to its tables.
function moreResults(data, body, part, profile) {
  if (!PART_STAGE[part]) return;
  const block = h("section", { class: "more-results", "aria-label": "Checks and tables for this step" });
  for (const [name, title, about] of MORE[part] ?? []) {
    if (title === "check" && data.tables[name]) block.append(checkLine(table(data, name), about));
  }
  if (part === "gagne") {
    block.append(h("h3", { text: "Rhea's figures" }));
    if (profile !== "full") {
      block.append(h("p", { class: "note", text: "These figures are shown for the full cohort only: in the small test runs, one person could be read off the smallest bars." }));
    } else {
      for (const [file, title, about] of FIGURES) {
        block.append(h("figure", { class: "figure" },
          h("figcaption", {}, h("h4", { text: title }), h("p", { text: about })),
          h("img", { src: `figures/${file}`, alt: `${title}. ${about}`, loading: "lazy" })));
      }
    }
  }
  block.append(h("p", { class: "note" }, "Every table for this step, with its numbers: ",
    h("a", { href: `results.html#${PART_STAGE[part]}`, text: "All results" }), "."));
  body.append(block);
}

const PARTS = { overview, eligible, groups, before, matching, after, gagne, care, results };

const cache = new Map();
let wanted = null;

function load(profile) {
  if (cache.has(profile)) return Promise.resolve(cache.get(profile));
  return new Promise((resolve, reject) => {
    const file = `data/${profile}.js`;
    const script = h("script", { src: `${file}?v=${Date.now()}` });   // never a stale copy after a new run
    script.addEventListener("load", () => {
      script.remove();
      const data = window.SHARP_RESULTS?.[profile];
      if (!data || typeof data.tables !== "object") {
        reject(new Error(`${file} does not hold the ${PROFILES[profile].toLowerCase()} results`));
        return;
      }
      cache.set(profile, data);
      resolve(data);
    });
    script.addEventListener("error", () => {
      script.remove();
      reject(new Error(`${file} is missing or could not be read`));
    });
    document.head.append(script);
  });
}

function render(data, profile) {
  releaseCharts();
  for (const [name, draw] of Object.entries(PARTS)) {
    const body = document.querySelector(`[data-part="${name}"]`);
    if (!body) continue;   // each page holds only its own step
    try {
      draw(data, body);
      moreResults(data, body, name, profile);
    } catch (error) {
      console.error(error);
      releaseCharts(body);
      body.replaceChildren(h("p", { class: "part-error", text: `This part could not be drawn. ${error.message}` }));
    }
  }
  const run = document.querySelector('[data-part="run"]');
  if (run) runDetails(data, run, profile);
}

function renderError(profile, error) {
  releaseCharts();
  for (const node of document.querySelectorAll("[data-part]")) node.replaceChildren();
  const retry = h("button", { type: "button", class: "button", text: "Try again" });
  retry.addEventListener("click", () => show(profile));
  document.querySelector("[data-part]").replaceChildren(h("div", { class: "error-panel", role: "alert" },
    h("h2", { text: `The ${PROFILES[profile].toLowerCase()} results did not load` }),
    h("p", { text: `${error.message}. Rebuild the data with python -m runner.site_data, then reload this page. On the website, also commit and push docs/data.` }),
    retry));
}

async function show(profile) {
  wanted = profile;
  const main = document.getElementById("main");
  const status = document.getElementById("status");
  main.setAttribute("aria-busy", "true");
  main.classList.add("is-loading");
  status.textContent = `Loading the ${PROFILES[profile].toLowerCase()}…`;
  try {
    const data = await load(profile);
    if (wanted !== profile) return;
    render(data, profile);
    status.textContent = "";
    announce(`Showing the ${PROFILES[profile].toLowerCase()}`);
  } catch (error) {
    if (wanted !== profile) return;
    renderError(profile, error);
    status.textContent = "";
  } finally {
    if (wanted === profile) {
      main.removeAttribute("aria-busy");
      main.classList.remove("is-loading");
    }
  }
}

// The sidebar marks the page you are on, and every link between pages keeps the chosen run.
function markCurrentPage() {
  const here = location.pathname.split("/").pop() || "index.html";
  for (const a of document.querySelectorAll(".rail a")) {
    if (a.getAttribute("href").split(/[?#]/)[0] === here) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
}

function keepProfileInLinks(profile) {
  for (const a of document.querySelectorAll("a[href]")) {
    const href = a.getAttribute("href");
    if (!/^[a-z]+\.html([?#].*)?$/.test(href)) continue;
    const [page, hash = ""] = href.split("#");
    const file = page.split("?")[0];
    a.setAttribute("href", file + (profile === "full" ? "" : `?profile=${profile}`) + (hash ? `#${hash}` : ""));
  }
}

function start() {
  const asked = new URLSearchParams(window.location.search).get("profile");
  const profile = asked !== null && Object.hasOwn(PROFILES, asked) ? asked : "full";
  for (const input of document.querySelectorAll('input[name="profile"]')) {
    input.checked = input.value === profile;
    input.addEventListener("change", () => {
      if (!input.checked) return;
      const url = new URL(window.location.href);
      url.searchParams.set("profile", input.value);
      window.history.replaceState(null, "", url);
      show(input.value).then(() => keepProfileInLinks(input.value));
    });
  }
  markCurrentPage();
  show(profile).then(() => keepProfileInLinks(profile));
}

start();
})();
