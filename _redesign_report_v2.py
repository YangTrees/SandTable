import re
from pathlib import Path

path = Path(r"D:\AI\AI_SandBox\report_viewer_v2.html")
text = path.read_text(encoding="utf-8")

new_css = r'''
    :root {
      --ink: #142a24;
      --ink-2: #35443d;
      --muted: #6b7871;
      --line: #d6ddd7;
      --line-soft: #e7ece7;
      --paper: #fffdf9;
      --paper-2: #f7f3e9;
      --forest: #133f35;
      --forest-2: #1e5a49;
      --teal: #3a7764;
      --sage: #93b09f;
      --sand: #f1e3cf;
      --gold: #c69856;
      --clay: #bd6b4d;
      --rose: #a65a55;
      --sky: #e6f0ec;
      --accent: #2f6f5e;
      --accent-soft: #e7f2ee;
      --accent-deep: #143f35;
      --shadow: 0 24px 70px rgba(17, 43, 35, .18);
      --serif: "Noto Serif SC", "Songti SC", "STSong", "SimSun", serif;
      --sans: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      background:
        radial-gradient(circle at 10% 4%, rgba(198, 152, 86, .22), transparent 30%),
        radial-gradient(circle at 92% 16%, rgba(58, 119, 100, .22), transparent 34%),
        linear-gradient(150deg, #e9e1d3 0%, #dce5de 52%, #d1dbd5 100%);
      background-attachment: fixed;
      color: var(--ink-2);
      font-family: var(--sans);
      font-size: 10pt;
      line-height: 1.75;
      -webkit-font-smoothing: antialiased;
    }
    button, input { font: inherit; }

    /* ===== 顶部工具栏 ===== */
    .toolbar {
      position: sticky; top: 0; z-index: 20;
      display: flex; align-items: center; justify-content: space-between; gap: 18px;
      min-height: 68px; padding: 10px 24px;
      color: #fff;
      background: linear-gradient(120deg, rgba(13, 42, 34, .97), rgba(30, 90, 73, .92));
      border-bottom: 1px solid rgba(198, 152, 86, .38);
      box-shadow: 0 12px 32px rgba(11, 32, 26, .24);
      backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    }
    .brand { display: flex; align-items: center; gap: 11px; min-width: 220px; }
    .brand-mark {
      width: 35px; height: 35px; display: grid; place-items: center;
      border: 1px solid rgba(255,255,255,.3); border-radius: 50%;
      background: radial-gradient(circle at 30% 20%, #f1dcb8, #c69856);
      color: var(--forest); font-family: var(--serif); font-size: 18px;
      box-shadow: 0 0 0 4px rgba(198, 152, 86, .1);
    }
    .brand strong { display: block; font-size: 13px; letter-spacing: .05em; color: #fff; }
    .brand small { display: block; margin-top: 1px; color: rgba(255,255,255,.62); font-size: 9px; letter-spacing: .05em; }
    .toolbar-actions { display: flex; align-items: center; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
    .mode-switch {
      display: flex; padding: 3px; border: 1px solid rgba(255,255,255,.22);
      border-radius: 999px; background: rgba(255,255,255,.08);
    }
    .mode-switch button {
      border: 0; border-radius: 999px; background: transparent; padding: 7px 12px;
      color: rgba(255,255,255,.68); font-size: 9.5px; cursor: pointer;
    }
    .mode-switch button.active {
      background: #f1e3cf; color: var(--forest);
      box-shadow: 0 4px 12px rgba(0,0,0,.16);
    }
    .toolbar-btn {
      border: 1px solid rgba(255,255,255,.24); border-radius: 999px; padding: 8px 13px;
      background: rgba(255,255,255,.1); color: #fff; font-size: 10px; cursor: pointer;
      transition: background .18s ease, transform .18s ease;
    }
    .toolbar-btn:hover { background: rgba(255,255,255,.18); transform: translateY(-1px); }
    .toolbar-btn.primary {
      background: linear-gradient(135deg, #e0bb7d, #c69856);
      border-color: #c69856; color: #20352d;
      box-shadow: 0 6px 18px rgba(0,0,0,.18);
    }
    .toolbar-btn.primary:hover { background: linear-gradient(135deg, #e8c98f, #d0a464); }
    .toolbar-btn:disabled { opacity: .45; cursor: not-allowed; transform: none; }
    .status-pill {
      display: inline-flex; align-items: center; gap: 6px; max-width: 250px;
      padding: 5px 9px; border: 1px solid rgba(255,255,255,.18); border-radius: 999px;
      background: rgba(255,255,255,.1); color: rgba(255,255,255,.72); font-size: 8.5px;
    }
    .status-pill i { width: 5px; height: 5px; border-radius: 50%; background: #e0b978; }

    /* ===== 纸张与页眉 ===== */
    #viewport { position: relative; padding: 34px 18px 60px; }
    .report-sheet {
      position: relative; width: 210mm; min-height: 297mm; margin: 0 auto;
      padding: 11mm 11mm 12mm; overflow: hidden;
      border-radius: 3mm;
      background: linear-gradient(180deg, #fffdf9 0%, #fffdf9 68%, #fbf8f0 100%);
      box-shadow: var(--shadow), inset 0 0 0 1px rgba(255,255,255,.72);
      color: var(--ink-2);
    }
    .report-sheet::before {
      content: ""; position: absolute; inset: 0 0 auto; height: 3mm;
      background: linear-gradient(90deg, var(--forest), var(--teal), var(--gold), var(--clay));
    }
    .report-sheet::after {
      content: ""; position: absolute; right: -28mm; bottom: 28mm;
      width: 64mm; height: 64mm; border-radius: 50%;
      background: radial-gradient(circle, rgba(58,119,100,.09), transparent 70%);
      pointer-events: none;
    }
    .report-head { margin-bottom: 7.5mm; }
    .report-hero {
      position: relative; overflow: hidden; padding: 11mm 11mm 10mm;
      border-radius: 4mm; color: #fff;
      background:
        radial-gradient(circle at 88% 10%, rgba(198,152,86,.24), transparent 28%),
        linear-gradient(135deg, #102f28 0%, #174b3e 52%, #2e6b58 100%);
      box-shadow: 0 12px 32px rgba(16,47,40,.18);
    }
    .report-hero::before {
      content: ""; position: absolute; right: -16mm; top: -23mm;
      width: 78mm; height: 78mm; border-radius: 50%;
      border: 1px solid rgba(255,255,255,.16);
      box-shadow: 0 0 0 8mm rgba(255,255,255,.04), 0 0 0 16mm rgba(255,255,255,.03);
    }
    .report-hero::after {
      content: ""; position: absolute; left: 0; bottom: 0;
      width: 58%; height: 1px;
      background: linear-gradient(90deg, rgba(198,152,86,.85), transparent);
    }
    .hero-copy { position: relative; z-index: 2; max-width: 132mm; }
    .hero-eyebrow {
      display: flex; align-items: center; gap: 2.5mm;
      color: #e7cfa7; font-size: 7pt; letter-spacing: .16em; text-transform: uppercase;
    }
    .hero-eyebrow::before { content: ""; width: 7mm; height: 1px; background: var(--gold); }
    h1 {
      margin: 3.5mm 0 0; color: #fff; font-family: var(--serif);
      font-size: 24pt; line-height: 1.18; letter-spacing: .02em; font-weight: 700;
    }
    h1 span {
      display: block; margin-top: 1mm; color: #f1dfc4;
      font-size: 16.5pt; letter-spacing: .1em; font-weight: 600;
    }
    .subtitle { margin: 3.2mm 0 0; color: rgba(255,255,255,.72); font-size: 8.6pt; line-height: 1.65; }
    .hero-badges { display: flex; flex-wrap: wrap; gap: 2.5mm; margin-top: 5mm; }
    .mode-tag {
      display: inline-flex; align-items: center; padding: 1.4mm 3mm;
      border-radius: 999px; white-space: nowrap; font-size: 7.8pt;
      border: 1px solid rgba(255,255,255,.24); background: rgba(255,255,255,.1); color: #fff;
    }
    .mode-tag.counselor {
      border-color: rgba(198,152,86,.55); background: rgba(198,152,86,.16); color: #f3dfc0;
    }
    .mode-tag.public {
      border-color: rgba(180,220,205,.5); background: rgba(180,220,205,.12); color: #dff3e8;
    }
    .hero-report-no {
      display: inline-flex; align-items: center; padding: 1.4mm 3mm;
      border: 1px solid rgba(255,255,255,.18); border-radius: 999px;
      color: rgba(255,255,255,.7); font-size: 7.4pt; letter-spacing: .05em;
    }
    .hero-emblem {
      position: absolute; right: 10mm; bottom: 9mm; z-index: 2;
      width: 31mm; height: 31mm; border: 1px solid rgba(255,255,255,.22);
      border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center;
      background: radial-gradient(circle, rgba(255,255,255,.08), transparent 70%);
    }
    .hero-emblem strong { color: #f1dfc4; font-family: var(--serif); font-size: 22pt; line-height: 1; }
    .hero-emblem span { margin-top: 1.5mm; color: rgba(255,255,255,.5); font-size: 6pt; letter-spacing: .18em; }

    .meta-card {
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 3mm 6mm; margin-top: 5mm; padding: 5mm 5.5mm;
      border: 1px solid var(--line); border-radius: 3mm;
      background: linear-gradient(180deg, #fff, #f8f5ec);
      box-shadow: 0 4px 14px rgba(17,43,35,.045);
    }
    .meta-item {
      display: flex; align-items: baseline; gap: 2mm; min-width: 0;
      padding-left: 2.5mm; border-left: 2px solid rgba(198,152,86,.5);
    }
    .meta-label { flex: 0 0 auto; color: var(--muted); font-size: 7.6pt; letter-spacing: .04em; }
    .meta-value { color: var(--ink); font-size: 8.8pt; font-weight: 600; overflow-wrap: anywhere; }
    .basis-card {
      margin-top: 3.5mm; padding: 3.2mm 5mm;
      border: 1px solid #e4d6bf; border-left: 4px solid var(--gold);
      border-radius: 0 2mm 2mm 0;
      background: linear-gradient(90deg, #fbf4e5, #fffdf9);
      color: #5f5443; font-size: 8pt;
    }
    .basis-card b { color: #9a6f35; font-weight: 600; margin-right: 2mm; }

    /* ===== 章节与卡片 ===== */
    .section { position: relative; margin-top: 8mm; }
    .section[data-chapter="1"] { --accent: #2f6f5e; --accent-soft: #e7f2ee; --accent-deep: #143f35; }
    .section[data-chapter="2"] { --accent: #b7794b; --accent-soft: #fbf0e3; --accent-deep: #7d4d2c; }
    .section[data-chapter="3"] { --accent: #3d6f7a; --accent-soft: #e8f1f3; --accent-deep: #284d56; }
    .section[data-chapter="4"] { --accent: #8a6a3d; --accent-soft: #f6efe0; --accent-deep: #624a2b; }
    .section[data-chapter="5"] { --accent: #a8554e; --accent-soft: #f8e9e7; --accent-deep: #743a35; }
    .section[data-chapter="6"] { --accent: #4f6f8a; --accent-soft: #eaf0f6; --accent-deep: #354e64; }
    .section[data-chapter="7"] { --accent: #6b5a8a; --accent-soft: #f0ecf6; --accent-deep: #493b61; }
    .section[data-chapter="8"] { --accent: #3f7a6a; --accent-soft: #e8f4ef; --accent-deep: #285446; }
    .section[data-chapter="9"] { --accent: #8a6a3d; --accent-soft: #f7f0e2; --accent-deep: #624a2b; }
    .section::before {
      content: ""; position: absolute; left: -4mm; top: 0; bottom: 0; width: 1.2mm;
      border-radius: 2mm; background: linear-gradient(180deg, var(--accent), transparent 72%);
      opacity: .24;
    }
    .section-head {
      display: grid; grid-template-columns: 13mm 1fr auto; align-items: center; gap: 3mm;
      position: relative; margin-bottom: 4.5mm; padding: 1mm 0 3mm;
      border-bottom: 1px solid var(--line);
    }
    .section-head::after {
      content: ""; position: absolute; left: 0; bottom: -1px; width: 26mm; height: 2px;
      background: linear-gradient(90deg, var(--accent), transparent);
    }
    .section-numeral {
      width: 12mm; height: 12mm; display: grid; place-items: center;
      border-radius: 50%; background: var(--accent-soft); color: var(--accent);
      font-family: var(--serif); font-size: 15pt; font-weight: 700; line-height: 1;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.7);
    }
    .section-head h2 {
      margin: 0; color: var(--ink); font-family: var(--serif);
      font-size: 14pt; line-height: 1.35; letter-spacing: .02em; font-weight: 700;
    }
    .section-aside {
      max-width: 58mm; color: var(--accent); font-size: 7.8pt; line-height: 1.5;
      text-align: right; white-space: normal;
    }
    .section-intro { margin: 0 0 4mm; color: var(--muted); font-size: 8.4pt; line-height: 1.7; }
    .grid-2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4mm; }
    .grid-3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 4mm; }
    .card {
      position: relative; border: 1px solid var(--line); border-top: 3px solid var(--accent);
      border-radius: 3mm; padding: 4.5mm 5mm;
      background: linear-gradient(180deg, #fff, #fbf9f3);
      box-shadow: 0 4px 14px rgba(17,43,35,.045);
    }
    .card-title { margin-bottom: 2.5mm; color: var(--accent); font-size: 8.2pt; font-weight: 700; letter-spacing: .06em; }
    .card p { margin: 0; color: var(--ink-2); font-size: 9.4pt; line-height: 1.75; }
    .soft-label { color: var(--accent); font-size: 8.2pt; font-weight: 600; letter-spacing: .08em; }
    .figure-block { width: 108mm; margin: 0 auto 5mm; }
    .figure-frame {
      position: relative; padding: 2.5mm; border-radius: 3.5mm;
      background: linear-gradient(135deg, #efe3cf, #e5f0ea);
      box-shadow: 0 10px 26px rgba(17,43,35,.12);
    }
    .figure-frame::before {
      content: "SANDPLAY · 01"; position: absolute; top: 4.5mm; left: 4.5mm; z-index: 2;
      padding: 1mm 2.2mm; border-radius: 999px;
      background: rgba(20,63,53,.84); color: #f1dfc4; font-size: 6.2pt; letter-spacing: .12em;
    }
    .figure-frame img {
      display: block; width: 100%; height: auto; max-height: 84mm;
      object-fit: cover; border-radius: 2.5mm; background: #f7f4ed;
    }
    .figure-caption { margin-top: 2mm; color: var(--muted); font-size: 7.8pt; letter-spacing: .08em; text-align: center; }
    .category-list { display: flex; flex-wrap: wrap; gap: 2mm; margin-top: 2mm; }
    .category-chip {
      padding: 1.2mm 2.6mm; border: 1px solid var(--accent-soft); border-radius: 999px;
      color: var(--accent-deep); font-size: 8.2pt; background: var(--accent-soft);
    }
    .mini-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5mm; margin-top: 2mm; }
    .mini-cell {
      min-height: 14mm; padding: 1.5mm; border: 1px solid var(--line-soft); background: #fbfaf7;
      border-radius: 1.2mm; display: flex; flex-direction: column; justify-content: center;
      align-items: center; color: var(--muted); font-size: 7.4pt;
    }
    .mini-cell.active { border-color: var(--accent); background: var(--accent-soft); color: var(--accent-deep); }
    .mini-cell b { font-weight: 700; font-size: 8pt; }
    .mini-cell span { margin-top: .5mm; font-family: var(--sans); }
    .scene-quote {
      position: relative; margin-top: 4mm; padding: 4.5mm 5mm 4.5mm 12mm;
      border: 1px solid var(--line); border-left: 4px solid var(--accent);
      border-radius: 0 3mm 3mm 0;
      background: linear-gradient(135deg, #f7f3e8, #fff);
    }
    .scene-quote::before {
      content: "“"; position: absolute; left: 4mm; top: 1.5mm;
      color: var(--accent); font-family: var(--serif); font-size: 26pt; opacity: .35;
    }
    .scene-quote ul, .plain-list { margin: 1.5mm 0 0; padding-left: 5mm; }
    .scene-quote li, .plain-list li { margin: 1mm 0; color: var(--ink-2); font-size: 9.2pt; line-height: 1.65; }
    .terrain-line { margin-top: 3mm; color: var(--muted); font-size: 8.3pt; }
    .warn-strip {
      display: flex; align-items: baseline; gap: 3mm; margin-bottom: 4mm; padding: 2.8mm 4mm;
      border: 1px solid #e4c9ab; border-radius: 2mm;
      background: linear-gradient(90deg, #fdf4e8, #fff);
      color: #7b5a38; font-size: 8.3pt; line-height: 1.6;
    }
    .warn-strip b { flex: 0 0 auto; color: #9a6a35; font-weight: 700; }

    /* ===== 表格 ===== */
    .table-wrap {
      border: 1px solid var(--line); border-radius: 3mm; overflow: hidden;
      background: #fff; box-shadow: 0 3px 12px rgba(17,43,35,.045);
    }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 3mm 3.5mm; border-bottom: 1px solid var(--line-soft); vertical-align: top; text-align: left; }
    th {
      color: var(--accent-deep); font-size: 8.6pt; font-weight: 700;
      background: linear-gradient(90deg, var(--accent-soft), #fff);
    }
    td { color: var(--ink-2); font-size: 8.7pt; line-height: 1.65; background: #fff; }
    tbody tr:nth-child(even) td { background: #fbfaf5; }
    tr:last-child td { border-bottom: 0; }
    .table-note { margin: 2.4mm 0 0; color: var(--muted); font-size: 7.6pt; line-height: 1.55; }
    .theory-note { margin-top: 1.2mm; color: var(--muted); font-size: 7.6pt; line-height: 1.55; }

    /* ===== 六维 / 风险 / 训练 ===== */
    .dimension-card {
      margin-bottom: 4mm; border: 1px solid var(--line); border-left: 4px solid var(--accent);
      border-radius: 3mm; background: #fff; overflow: hidden;
      box-shadow: 0 4px 14px rgba(17,43,35,.045);
    }
    .dimension-head {
      display: flex; align-items: center; justify-content: space-between; gap: 5mm;
      padding: 4mm 5mm; border-bottom: 1px solid var(--line-soft);
      background: linear-gradient(90deg, var(--accent-soft), #fff);
    }
    .dimension-title { display: flex; align-items: center; gap: 4mm; min-width: 0; }
    .dimension-index {
      width: 9mm; height: 9mm; display: grid; place-items: center;
      border-radius: 50%; background: var(--accent); color: #fff;
      font-family: var(--serif); font-size: 10pt; line-height: 1; flex: 0 0 auto;
    }
    .dimension-title h3 { margin: 0; color: var(--ink); font-family: var(--serif); font-size: 11pt; font-weight: 700; line-height: 1.4; }
    .confidence {
      flex: 0 0 auto; padding: 1.2mm 3mm; border: 1px solid var(--line); border-radius: 999px;
      color: var(--muted); font-size: 7.7pt; background: #fbfaf7;
    }
    .confidence.high { border-color: #bfd7cb; background: #f2f8f5; color: #4f7c68; }
    .confidence.mid { border-color: #e4c9ab; background: #fbf4e9; color: #966936; }
    .confidence.low { border-color: #dedbd2; background: #faf9f6; color: #8d8e86; }
    .dimension-body { padding: 4.5mm 5mm 5mm; }
    .judgement {
      margin-bottom: 3.4mm; padding: 3mm 4mm 3mm 5mm;
      border-left: 3px solid var(--accent); border-radius: 0 2mm 2mm 0;
      background: linear-gradient(90deg, var(--accent-soft), #fff);
    }
    .judgement-label { color: var(--accent-deep); font-size: 8.1pt; font-weight: 700; letter-spacing: .06em; }
    .judgement p { margin: 1.2mm 0 0; color: var(--ink); font-size: 9.3pt; line-height: 1.65; }
    .theory-line { margin-bottom: 3mm; color: var(--ink-2); font-size: 8.2pt; line-height: 1.6; }
    .theory-line b { color: var(--muted); font-weight: 500; }
    .sub-label { display: flex; align-items: center; gap: 2mm; color: var(--accent-deep); font-size: 8.4pt; font-weight: 700; }
    .sub-label i { width: 2mm; height: 2mm; border-radius: 50%; background: var(--accent); display: inline-block; }
    .sub-label i.diamond { border-radius: 0; transform: rotate(45deg); background: var(--gold); width: 1.8mm; height: 1.8mm; }
    .sub-block { margin-top: 2.4mm; }
    .sub-block p { margin: 1.4mm 0 0; color: var(--ink-2); font-size: 9pt; line-height: 1.68; }
    .sub-list { margin: 1.4mm 0 0; padding-left: 4mm; }
    .sub-list li { margin: .8mm 0; color: var(--ink-2); font-size: 8.8pt; line-height: 1.6; }
    .capability-list { margin: 1.2mm 0 0; padding-left: 3mm; }
    .capability-list li { margin: .6mm 0; color: var(--ink-2); font-size: 8.8pt; line-height: 1.55; }
    .capability-list li::marker { content: "→"; color: var(--accent); }
    .module-pills { display: flex; flex-wrap: wrap; gap: 1.8mm; margin-top: 1.6mm; }
    .module-pill {
      padding: 1.2mm 2.4mm; border: 1px solid var(--accent-soft); border-radius: 1.2mm;
      background: var(--accent-soft); color: var(--accent-deep); font-size: 7.6pt;
    }
    .conclusion { margin-top: 3mm; color: var(--accent-deep); font-size: 8.5pt; line-height: 1.65; }

    .academic-hero {
      margin-bottom: 4mm; padding: 4mm 5mm; border: 1px solid var(--line);
      border-left: 4px solid var(--accent); border-radius: 0 3mm 3mm 0;
      background: linear-gradient(90deg, var(--accent-soft), #fff);
    }
    .academic-hero .card-title { margin-bottom: 1.5mm; }
    .academic-hero p { margin: 0; color: var(--ink-2); font-size: 9.3pt; line-height: 1.7; }
    .total-line { display: flex; align-items: baseline; justify-content: space-between; gap: 5mm; padding: 3.2mm 4mm; border-bottom: 1px solid var(--line-soft); background: #fbfaf5; }
    .total-line strong { color: var(--ink); font-family: var(--serif); font-size: 9.4pt; }
    .total-line span { color: var(--muted); font-size: 8.1pt; }
    .academic-table td:nth-child(2), .academic-table td:nth-child(3), .academic-table td:nth-child(4) { width: 17%; }
    .academic-table td:nth-child(3) { color: var(--ink); font-weight: 600; }
    .academic-table td:last-child { width: 20%; }
    .grade-pill { display: inline-block; min-width: 12mm; padding: 1mm 2.4mm; border: 1px solid var(--line); border-radius: 999px; text-align: center; font-size: 7.8pt; }
    .grade-pill.excellent { color: #4e7c67; border-color: #bdd7ca; background: #f3f8f5; }
    .grade-pill.good { color: #8a6836; border-color: #e4c9ab; background: #fbf4e9; }
    .grade-pill.pass { color: #9b7443; border-color: #e3c9a9; background: #fdf7ef; }
    .grade-pill.fail { color: #9a5048; border-color: #e3bbb4; background: #fdf3f1; }
    .empty-table { padding: 7mm 5mm; color: var(--muted); font-size: 9pt; text-align: center; background: #fcfbf8; }
    .transcript-block { margin-top: 4mm; }
    .transcript-block img { display: block; max-width: 62mm; max-height: 108mm; margin-top: 2mm; border: 1px solid var(--line); border-radius: 2mm; object-fit: contain; background: #fbfaf7; }

    .risk-disclaimer { margin-bottom: 3mm; color: #7e6b62; font-size: 8.1pt; line-height: 1.65; }
    .risk-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 3mm; margin-bottom: 4mm; }
    .risk-card {
      min-height: 19mm; padding: 3.2mm 4mm; border: 1px solid var(--line);
      border-top: 3px solid var(--line); border-radius: 2.5mm; background: #fff;
    }
    .risk-card h4 { margin: 0 0 1.2mm; color: var(--ink); font-family: var(--serif); font-size: 9.4pt; }
    .risk-card p { margin: 0; font-size: 7.9pt; color: var(--muted); }
    .risk-card.l1 { border-color: #c8dbd1; border-top-color: #4f8a70; background: #f7fbf8; }
    .risk-card.l2 { border-color: #e4c9ab; border-top-color: #c69856; background: #fdf8ef; }
    .risk-card.l3 { border-color: #e2bda3; border-top-color: #c07a56; background: #fdf3ec; }
    .risk-card.l4 { border-color: #dcb1a9; border-top-color: #a8554e; background: #fdf0ef; }
    .risk-level { color: var(--muted); font-weight: 600; }
    .risk-level.l1 { color: #56816b; }
    .risk-level.l2 { color: #a27538; }
    .risk-level.l3 { color: #b05f3d; }
    .risk-level.l4 { color: #a44e46; }
    .risk-detail {
      margin-bottom: 3.2mm; padding: 4.2mm 5mm; border: 1px solid var(--line);
      border-left: 4px solid var(--accent); border-radius: 0 3mm 3mm 0;
      background: #fff; box-shadow: 0 3px 10px rgba(17,43,35,.035);
    }
    .risk-detail-head { display: flex; align-items: center; justify-content: space-between; gap: 4mm; margin-bottom: 2.4mm; }
    .risk-detail-head h3 { margin: 0; color: var(--ink); font-family: var(--serif); font-size: 9.6pt; }
    .risk-field { margin-top: 2.2mm; }
    .risk-field b { display: block; color: var(--muted); font-size: 7.9pt; font-weight: 500; }
    .risk-field p { margin: .8mm 0 0; color: var(--ink-2); font-size: 8.7pt; line-height: 1.65; }
    .risk-standard { margin: 3mm 0 6mm; padding: 3.2mm 4mm; border: 1px solid var(--line); border-radius: 2.5mm; background: #fcfbf8; }
    .risk-standard strong { color: var(--ink); font-size: 8.6pt; }
    .risk-standard-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2mm; margin-top: 2mm; }
    .risk-standard-grid div { padding: 2mm 2.4mm; border: 1px solid var(--line-soft); border-radius: 1.2mm; color: var(--muted); font-size: 7.5pt; background: #fff; }
    .risk-standard-grid b { display: block; color: var(--ink); font-size: 7.8pt; }

    .action-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 3mm; margin-top: 4mm; }
    .action-card {
      padding: 3.6mm 4mm; border: 1px solid var(--line); border-top: 2px solid var(--accent);
      border-radius: 2mm; background: linear-gradient(180deg, #fff, #fbfaf5);
    }
    .action-card h4 { margin: 0 0 2mm; color: var(--accent-deep); font-size: 8.8pt; }
    .action-card ul { margin: 0; padding-left: 4mm; }
    .action-card li { margin: 1.4mm 0; color: var(--ink-2); font-size: 8.2pt; line-height: 1.6; }
    .stage-line { display: flex; align-items: center; gap: 3mm; margin-bottom: 4mm; padding: 2.6mm 3.5mm; border-bottom: 1px solid var(--line-soft); font-size: 8.5pt; color: var(--muted); }
    .stage-pill { padding: 1mm 2.5mm; border: 1px solid var(--accent-soft); border-radius: 999px; color: var(--accent-deep); background: var(--accent-soft); font-size: 8pt; }
    .strength-list { margin: 1.5mm 0 0; padding-left: 4mm; }
    .strength-list li { margin: 1.2mm 0; color: var(--ink-2); font-size: 9.1pt; }
    .career-summary { margin-bottom: 4mm; color: var(--ink-2); font-size: 9.2pt; line-height: 1.7; }
    .module-card {
      margin-bottom: 4mm; padding: 4.5mm 5mm; border: 1px solid var(--line);
      border-top: 3px solid var(--accent); border-radius: 3mm;
      background: #fff; box-shadow: 0 4px 14px rgba(17,43,35,.045);
    }
    .module-head { display: flex; align-items: center; gap: 3mm; margin-bottom: 3mm; }
    .module-number {
      width: 9mm; height: 9mm; display: grid; place-items: center; border-radius: 50%;
      background: var(--accent); color: #fff; font-family: var(--serif); font-size: 9pt;
    }
    .module-head h3 { margin: 0; color: var(--ink); font-family: var(--serif); font-size: 10pt; line-height: 1.45; }
    .module-meta { margin: 1.5mm 0 2.2mm; color: var(--ink-2); font-size: 8.4pt; }
    .module-meta b { color: var(--muted); font-weight: 500; margin-right: 1.5mm; }
    .module-goals { display: flex; flex-wrap: wrap; gap: 1.6mm; margin-top: 1.4mm; }
    .module-goal { padding: 1mm 2.3mm; border: 1px solid var(--accent-soft); border-radius: 1.2mm; background: var(--accent-soft); color: var(--accent-deep); font-size: 7.6pt; }
    .module-line { margin-top: 1.8mm; color: var(--ink-2); font-size: 8.5pt; line-height: 1.65; }
    .module-line b { color: var(--muted); font-weight: 500; }
    .advice-card {
      margin-bottom: 3mm; padding: 4mm 5mm; border: 1px solid var(--line);
      border-left: 4px solid var(--accent); border-radius: 0 3mm 3mm 0;
      background: linear-gradient(90deg, var(--accent-soft), #fff);
    }
    .advice-card h3 { margin: 0 0 2mm; color: var(--accent-deep); font-family: var(--serif); font-size: 9.8pt; }
    .advice-card ul { margin: 0; padding-left: 4mm; }
    .advice-card li { margin: 1.2mm 0; color: var(--ink-2); font-size: 8.8pt; line-height: 1.65; }
    .callout-warn {
      display: flex; gap: 3mm; margin-top: 4mm; padding: 4mm 5mm;
      border: 0; border-radius: 3mm;
      background: linear-gradient(135deg, #143f35, #235847);
      color: #f7efe0; font-size: 8.1pt; line-height: 1.62;
      box-shadow: 0 8px 20px rgba(17,43,35,.14);
    }
    .callout-warn .icon {
      flex: 0 0 auto; width: 5mm; height: 5mm; display: grid; place-items: center;
      border: 1px solid #d8b77b; border-radius: 50%; color: #f1dfc4;
      background: rgba(255,255,255,.08); font-weight: 700;
    }
    .callout-warn b { display: block; color: #f1dfc4; font-size: 9pt; margin-bottom: .8mm; }

    .qr-zone {
      display: flex; align-items: center; gap: 5mm; margin-top: 6mm; padding: 4.5mm;
      border: 1px dashed #d6c8b3; border-radius: 3mm;
      background: linear-gradient(135deg, #f7f2e6, #fff);
    }
    .qr-box {
      width: 30mm; min-height: 30mm; display: grid; place-items: center; padding: 1mm;
      border: 1px solid var(--line); border-radius: 2mm; background: #fff;
      color: var(--muted); font-size: 7.4pt; text-align: center;
    }
    .qr-box img { width: 27mm; height: 27mm; object-fit: contain; }
    .qr-copy { flex: 1; min-width: 0; }
    .qr-copy strong { display: block; color: var(--ink); font-family: var(--serif); font-size: 9.2pt; }
    .qr-copy small { display: block; margin-top: 1mm; color: var(--muted); font-size: 7.7pt; }
    .qr-copy code { display: block; margin-top: 1mm; color: var(--accent-deep); font-family: var(--sans); font-size: 7.2pt; overflow-wrap: anywhere; }

    .empty-state {
      max-width: 680px; margin: 40px auto; padding: 34px; border: 1px solid rgba(255,255,255,.7); border-radius: 8px;
      background: linear-gradient(135deg, rgba(255,253,249,.94), rgba(240,246,242,.9));
      box-shadow: 0 18px 50px rgba(17,43,35,.16); text-align: center;
    }
    .empty-state h2 { margin: 0; color: var(--ink); font-family: var(--serif); font-size: 18px; }
    .empty-state p { margin: 6px 0 18px; color: var(--muted); font-size: 12px; line-height: 1.7; }
    .drop-zone { padding: 22px; border: 1px dashed #cfc8ba; border-radius: 6px; color: var(--muted); font-size: 12px; background: rgba(255,255,255,.5); }
    .drop-zone strong { display: block; margin-bottom: 4px; color: var(--ink); font-size: 13px; }
    #toast {
      position: fixed; left: 50%; bottom: 26px; z-index: 30; transform: translateX(-50%);
      padding: 8px 15px; border: 1px solid rgba(255,255,255,.5); border-radius: 999px;
      background: rgba(17,43,35,.92); color: #fff; font-size: 11px; opacity: 0; pointer-events: none; transition: opacity .2s ease;
    }
    #toast.show { opacity: 1; }
    .hide { display: none !important; }
    .avoid-break { break-inside: avoid; page-break-inside: avoid; }

    @media (max-width: 860px) {
      .toolbar { align-items: flex-start; flex-direction: column; padding: 10px 12px; }
      .toolbar-actions { width: 100%; justify-content: flex-start; }
      .status-pill { max-width: none; }
      #viewport { padding: 14px 6px 24px; overflow-x: auto; }
      .report-sheet { width: 210mm; margin: 0; }
      .report-hero { padding: 9mm; }
      .hero-copy { max-width: 100%; }
      .hero-emblem { display: none; }
      h1 { font-size: 21pt; }
      h1 span { font-size: 14.5pt; }
      .section-head { grid-template-columns: 11mm 1fr; }
      .section-aside { grid-column: 2; text-align: left; max-width: none; }
    }
    @media print {
      body { background: #fff; }
      .toolbar, #toast, .empty-state { display: none !important; }
      #viewport { padding: 0; }
      .report-sheet {
        width: auto; min-height: 0; padding: 0; margin: 0;
        border-radius: 0; box-shadow: none; background: #fff; overflow: visible;
      }
      .report-sheet::before, .report-sheet::after { display: none; }
      .report-hero { border-radius: 0; box-shadow: none; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .card, .dimension-card, .risk-detail, .module-card, .advice-card, .table-wrap, .callout-warn { box-shadow: none; }
      .section::before { display: none; }
      @page { size: A4 portrait; margin: 12mm 11mm; }
    }
'''

# 替换样式块
style_match = re.search(r"  <style>.*?  </style>", text, re.S)
if not style_match:
    raise SystemExit("style block not found")
text = text[:style_match.start()] + "  <link rel=\"stylesheet\" href=\"https://miaoda.feishu.cn/fonts/css2?family=Noto+Serif+SC:wght@400;600;700;900&family=Noto+Sans+SC:wght@300;400;500;700&display=swap\">\n  <style>" + new_css + "  </style>" + text[style_match.end():]

new_header = r'''    function renderHeader(report) {
      const meta = report.meta || {};
      const academic = report.chapter_4_academic || {};
      const hasScores = Array.isArray(academic.subjects) && academic.subjects.length > 0;
      const basisItems = list(meta.assessment_basis).filter(Boolean).filter((item) => hasScores || !String(item).includes("成绩单"));
      const basis = basisItems.join(" · ") || "沙盘作品照片 1 张 · 画面分区 · 受测者自述";
      const modeText = state.mode === "counselor" ? "咨询师完整版" : "家长 / 学生端 · 脱敏";
      const reportNo = text(meta.report_no, "报告编号待生成");
      return `<header class="report-head">
        <div class="report-hero">
          <div class="hero-copy">
            <div class="hero-eyebrow">SANDPLAY ASSESSMENT · 发展性心理评估</div>
            <h1>心理沙盘<span>发展性评估报告</span></h1>
            <p class="subtitle">${esc(meta.disclaimer || "发展性心理评估参考·非临床诊断")}</p>
            <div class="hero-badges">
              <span class="mode-tag ${state.mode === "counselor" ? "counselor" : "public"}">${esc(modeText)}</span>
              <span class="hero-report-no">报告编号 · ${esc(reportNo)}</span>
            </div>
          </div>
          <div class="hero-emblem" aria-hidden="true"><strong>09</strong><span>CHAPTERS</span></div>
        </div>
        <div class="meta-card">
          ${metaItem("受测编号", meta.student_no || meta.student_id || "未填写")}
          ${metaItem("评估来源", meta.assessment_source || "沙盘作品评估")}
          ${metaItem("生成时间", formatDateTime(meta.generated_at))}
          ${metaItem("年级段", meta.grade_level || "未填写")}
          ${metaItem("性别", meta.gender || "未填写")}
          ${metaItem("施测日期", formatDateTime(meta.test_date || meta.generated_at).slice(0, 10))}
        </div>
        <div class="basis-card"><b>评估依据</b>${esc(basis)}</div>
      </header>`;
    }
'''
text = re.sub(r"    function renderHeader\(report\) \{.*?\n    \}\n    function metaItem", new_header + "    function metaItem", text, flags=re.S)

path.write_text(text, encoding="utf-8")
print("updated", path, len(text))
