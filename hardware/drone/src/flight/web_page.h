#pragma once

// Phone controller: throttle strip on the left (stays where you leave it), tilt pad on the
// right (springs back to centre), ARM and a big STOP. Polls /c about 12 times a second;
// the drone disarms if those stop arriving.
static const char WEB_PAGE[] PROGMEM = R"HTML(<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>ESP32 drone</title>
<style>
  * { box-sizing: border-box; touch-action: none; user-select: none; -webkit-user-select: none; }
  body { margin: 0; font-family: system-ui, sans-serif; background: #111; color: #eee;
         display: flex; flex-direction: column; height: 100vh; }
  #top { display: flex; gap: 8px; padding: 8px; align-items: center; }
  #status { flex: 1; font-size: 14px; }
  button { font-size: 18px; padding: 12px 16px; border: 0; border-radius: 8px; color: #fff; }
  #arm { background: #2a7a2a; }
  #stop { background: #c62020; font-size: 22px; font-weight: bold; flex: 0 0 35%; }
  #main { flex: 1; display: flex; gap: 12px; padding: 8px; }
  #thr { position: relative; flex: 0 0 30%; background: #222; border-radius: 8px; overflow: hidden; }
  #thrFill { position: absolute; bottom: 0; left: 0; right: 0; background: #3a6ea5; }
  #thrText { position: absolute; top: 8px; width: 100%; text-align: center; font-size: 20px; }
  #pad { position: relative; flex: 1; background: #222; border-radius: 8px; }
  #dot { position: absolute; width: 40px; height: 40px; margin: -20px; border-radius: 50%;
         background: #ddd; left: 50%; top: 50%; }
  .armed #status { color: #ff6; }
</style></head>
<body>
<div id="top">
  <button id="arm">ARM</button>
  <div id="status">connecting...</div>
  <button id="stop">STOP</button>
</div>
<div id="main">
  <div id="thr"><div id="thrFill"></div><div id="thrText">0%</div></div>
  <div id="pad"><div id="dot"></div></div>
</div>
<script>
let thr = 0, rx = 0, py = 0, busy = false;
const $ = id => document.getElementById(id);

function drag(el, onMove, onUp) {
  el.addEventListener('pointerdown', e => { el.setPointerCapture(e.pointerId); onMove(e); });
  el.addEventListener('pointermove', e => { if (el.hasPointerCapture(e.pointerId)) onMove(e); });
  el.addEventListener('pointerup', () => onUp && onUp());
  el.addEventListener('pointercancel', () => onUp && onUp());
}
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

drag($('thr'), e => {
  const r = $('thr').getBoundingClientRect();
  thr = clamp(1 - (e.clientY - r.top) / r.height, 0, 1);
  if (thr < 0.03) thr = 0;
  drawThr();
});
function drawThr() {
  $('thrFill').style.height = (thr * 100) + '%';
  $('thrText').textContent = Math.round(thr * 100) + '%';
}

drag($('pad'), e => {
  const r = $('pad').getBoundingClientRect();
  rx = clamp(((e.clientX - r.left) / r.width) * 2 - 1, -1, 1);
  py = clamp(1 - ((e.clientY - r.top) / r.height) * 2, -1, 1);
  drawPad();
}, () => { rx = 0; py = 0; drawPad(); });
function drawPad() {
  $('dot').style.left = ((rx + 1) * 50) + '%';
  $('dot').style.top = ((1 - py) * 50) + '%';
}

async function get(path) {
  const r = await fetch(path, { signal: AbortSignal.timeout(400), cache: 'no-store' });
  return r.json();
}
function show(j) {
  document.body.className = j.armed ? 'armed' : '';
  $('status').textContent = (j.armed ? 'ARMED' : 'disarmed') +
    ` | roll ${j.roll.toFixed(1)} pitch ${j.pitch.toFixed(1)}` + (j.msg ? ` | ${j.msg}` : '');
}

$('stop').addEventListener('pointerdown', () => {
  thr = 0; drawThr();
  get('/stop').then(show).catch(() => {});
});
$('arm').addEventListener('click', () => {
  if (thr > 0) { $('status').textContent = 'throttle must be at 0 to arm'; return; }
  get('/arm').then(show).catch(() => {});
});

setInterval(async () => {
  if (busy) return;
  busy = true;
  try {
    show(await get(`/c?t=${thr.toFixed(3)}&r=${rx.toFixed(3)}&p=${py.toFixed(3)}`));
  } catch (e) {
    $('status').textContent = 'NO LINK';
  }
  busy = false;
}, 80);
drawThr(); drawPad();
</script>
</body></html>
)HTML";
