// Run from the patch repository: node tools/check_wrist.cjs path/to/desktop
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const checkout = path.resolve(process.argv[2] || 'desktop');
const esbuild = require(require.resolve('esbuild', { paths: [checkout] }));
const source = fs.readFileSync(path.join(checkout, 'src', 'portraitRig.ts'), 'utf8');
const { code } = esbuild.transformSync(source, { loader: 'ts', format: 'cjs' });
const renderer = { exports: {} };
new Function('module', 'exports', code)(renderer, renderer.exports);

class CanvasProbe {
  constructor() {
    this.matrix = [1, 0, 0, 1, 0, 0];
    this.stack = [];
    this.draws = [];
  }
  save() { this.stack.push(this.matrix.slice()); }
  restore() { this.matrix = this.stack.pop(); }
  translate(x, y) {
    const [a,b,c,d,e,f] = this.matrix;
    this.matrix = [a,b,c,d,e + a*x + c*y,f + b*x + d*y];
  }
  rotate(angle) {
    const [a,b,c,d,e,f] = this.matrix;
    const cos = Math.cos(angle), sin = Math.sin(angle);
    this.matrix = [a*cos+c*sin,b*cos+d*sin,c*cos-a*sin,d*cos-b*sin,e,f];
  }
  scale(x, y) {
    const [a,b,c,d,e,f] = this.matrix;
    this.matrix = [a*x,b*x,c*y,d*y,e,f];
  }
  drawImage() { this.draws.push(this.matrix.slice()); }
}

function transform([a,b,c,d,e,f], {x,y}) {
  return {x: a*x + c*y + e, y: b*x + d*y + f};
}
function close(p, q, message) {
  assert(Math.hypot(p.x - q.x, p.y - q.y) < 0.0001, message);
}
function bend(elbow, wrist, tip) {
  const forearm = Math.atan2(wrist.y - elbow.y, wrist.x - elbow.x);
  const palm = Math.atan2(tip.y - wrist.y, tip.x - wrist.x);
  return Math.abs(Math.atan2(Math.sin(palm - forearm), Math.cos(palm - forearm)));
}

function checkPose(rig, pose) {
  const probe = new CanvasProbe();
  renderer.exports.drawPortraitForeground(probe, rig, pose);
  assert.equal(probe.draws.length, 6);
  rig.articulation.arms.forEach(({joints}, side) => {
    const [upper, forearm, palm] = probe.draws.slice(side * 3, side * 3 + 3);
    const [,e,w,t] = joints;
    const elbow = transform(forearm, e), wrist = transform(palm, w), tip = transform(palm, t);
    close(transform(upper, e), elbow, 'Elbow seam');
    close(transform(forearm, w), wrist, 'Wrist seam');
    assert(bend(elbow, wrist, tip) <= bend(e,w,t) + 0.00001, 'Wrist bends beyond the source pose');
    assert(palm[0]*palm[3] - palm[1]*palm[2] > 0, 'Hand artwork was mirrored');
    if (pose.leftReach === 1 && pose.leftPress === 1) {
      const target = side ? pose.right : pose.left;
      close(tip, {x: target.x, y: target.y + 8}, 'Missed contact');
    }
    if (pose.leftReach === 0) {
      [upper, forearm, palm].forEach((matrix, i) => {
        const p = joints[i], scale = 228 / rig.waist;
        close(transform(matrix,p), {
          x: pose.anchor.x + (p.x - rig.width / 2)*scale,
          y: pose.anchor.y + (p.y - rig.waist)*scale,
        }, 'Rest pose differs from the source');
      });
    }
  });
}

const example = JSON.parse(fs.readFileSync(path.join(__dirname, '../examples/arms.json'), 'utf8'));
const folded = [
  [[75,125],[32,189],[102,160],[144,143]],
  [[167,132],[196,204],[211,179],[229,154]],
];
for (const figure of [example.arms.map(a => a.j), folded]) {
  const arms = figure.map(points => ({
    joints: points.map(([x,y]) => ({x,y})),
    parts: Array.from({length: 3}, () => ({x: 0, y: 0, image: {}})),
  }));
  const rig = {width: 270, waist: 340, atlas: {}, articulation: {arms}};
  for (const x of [45,100,165,226,296,335]) {
    for (const y of [310,337,360]) {
      for (let step = 0; step <= 100; step++) {
        for (const press of [0,1]) {
          checkPose(rig, {
            anchor: {x: 205,y: 325}, left: {x,y}, right: {x,y}, mouseHand: x < 90,
            leftPress: press, rightPress: press, leftReach: step/100, rightReach: step/100,
          });
        }
      }
    }
  }
}
console.log('PASS: folded and extended arms preserve handedness, wrist bend, joints and contact.');