const fs = require('fs');
const path = require('path');
const htmlPath = path.join(__dirname, '..', 'sandplay_workbench_react.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const start = html.indexOf('function buildTerrainMetrics');
const end = html.indexOf('function buildHeightmap', start);
if (start < 0 || end < 0) throw new Error('buildTerrainMetrics not found');
const WORLD = { width: 1200, depth: 760, segX: 160, segZ: 100 };
eval(html.slice(start, end));

function mockTerrain(cols, rows, heightAt, xAt, zAt) {
  const heights = [];
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) heights.push(heightAt(c, r));
  }
  const position = {
    count: heights.length,
    getX: (i) => xAt(i % cols),
    getZ: (i) => zAt(Math.floor(i / cols))
  };
  return { heights, geometry: { attributes: { position } } };
}

const cols = 10;
const rows = 10;
const xAt = (c) => -600 + (c + 0.5) * 120;
const zAt = (r) => -380 + (r + 0.5) * 76;

const flat = buildTerrainMetrics(mockTerrain(cols, rows, () => 0, xAt, zAt));
if (flat.terrain_edited !== false || !flat.terrain_summary.includes('沙面基本平整')) {
  throw new Error('flat case failed: ' + JSON.stringify(flat));
}

const shapedHeights = [];
for (let r = 0; r < rows; r += 1) {
  for (let c = 0; c < cols; c += 1) {
    const edge = c === 0 || c === cols - 1 || r === 0 || r === rows - 1;
    if (edge) shapedHeights.push(-24);
    else if (r >= 3 && r <= 6 && c >= 3 && c <= 6) shapedHeights.push(10);
    else shapedHeights.push(0);
  }
}
const shaped = buildTerrainMetrics(mockTerrain(cols, rows, (c, r) => shapedHeights[r * cols + c], xAt, zAt));

if (shaped.terrain_edited !== true) throw new Error('shaped case not edited');
if (!(shaped.water_area_pct > 0) || !(shaped.mound_area_pct > 0)) {
  throw new Error('shaped percentages invalid: ' + JSON.stringify(shaped));
}
if (!shaped.terrain_summary.includes('水域约占') || !shaped.terrain_summary.includes('中心区')) {
  throw new Error('summary format invalid: ' + shaped.terrain_summary);
}

const lightDepression = [];
for (let r = 0; r < rows; r += 1) {
  for (let c = 0; c < cols; c += 1) {
    lightDepression.push((r >= 4 && r <= 5 && c >= 4 && c <= 5) ? -4 : 0);
  }
}
const light = buildTerrainMetrics(mockTerrain(cols, rows, (c, r) => lightDepression[r * cols + c], xAt, zAt));
if (!light.terrain_summary.includes('局部凹陷') || light.terrain_summary.includes('未见明显水域或沙丘聚集')) {
  throw new Error('light shaping summary invalid: ' + JSON.stringify(light));
}

console.log('WORKBENCH_METRICS_OK');
console.log('FLAT', JSON.stringify(flat));
console.log('SHAPED', JSON.stringify(shaped));
