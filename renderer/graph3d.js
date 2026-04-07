/* ── 3D Force-Directed Memory Graph (Three.js) ── */
'use strict';

/* THREE is loaded as a global via <script> in index.html */

let scene, camera, renderer3d, controls;
let raycaster, mouse;
let nodeObjects = [], edgeObjects = [], labelSprites = [];
let graphNodes = [], graphEdges = [];
let hoverNode = null;
let animId = null;
const graphFilters = { topic: true, fact: true, preference: true, edges: true };

const TYPE_COLORS = {
  topic:      0xd3869b,
  fact:       0xfe8019,
  preference: 0xfabd2f,
};
const CAT_COLORS = {
  user_pref:   0xfabd2f,
  project:     0x83a598,
  environment: 0x8ec07c,
  workflow:    0xd3869b,
  general:     0x727169,
};

/* ── simple orbit controls ── */
class SimpleOrbit {
  constructor(cam, el) {
    this.cam = cam;
    this.el = el;
    this.spherical = { r: 120, theta: Math.PI / 2, phi: 0 };
    this.target = new THREE.Vector3(0, 0, 0);
    this.dragging = false;
    this.lastX = 0;
    this.lastY = 0;
    this._updateCamera();
    el.addEventListener('mousedown', e => { this.dragging = true; this.lastX = e.clientX; this.lastY = e.clientY; });
    el.addEventListener('mousemove', e => {
      if (!this.dragging) return;
      const dx = e.clientX - this.lastX, dy = e.clientY - this.lastY;
      this.spherical.phi -= dx * 0.005;
      this.spherical.theta = Math.max(0.1, Math.min(Math.PI - 0.1, this.spherical.theta - dy * 0.005));
      this.lastX = e.clientX; this.lastY = e.clientY;
      this._updateCamera();
    });
    el.addEventListener('mouseup', () => this.dragging = false);
    el.addEventListener('mouseleave', () => this.dragging = false);
    el.addEventListener('wheel', e => {
      this.spherical.r = Math.max(10, Math.min(500, this.spherical.r + e.deltaY * 0.1));
      this._updateCamera();
    });
  }
  _updateCamera() {
    const { r, theta, phi } = this.spherical;
    this.cam.position.set(
      r * Math.sin(theta) * Math.cos(phi) + this.target.x,
      r * Math.cos(theta) + this.target.y,
      r * Math.sin(theta) * Math.sin(phi) + this.target.z
    );
    this.cam.lookAt(this.target);
  }
  reset() {
    this.spherical = { r: 120, theta: Math.PI / 2, phi: 0 };
    this.target.set(0, 0, 0);
    this._updateCamera();
  }
}

/* ── text label sprites ── */
function createTextSprite(text, color) {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const fontSize = 36;
  ctx.font = `${fontSize}px JetBrains Mono, monospace`;
  const tw = ctx.measureText(text).width;
  canvas.width = tw + 16;
  canvas.height = fontSize + 12;
  ctx.font = `${fontSize}px JetBrains Mono, monospace`;
  ctx.fillStyle = typeof color === 'number' ? '#' + color.toString(16).padStart(6, '0') : color;
  ctx.globalAlpha = 0.55;
  ctx.textBaseline = 'top';
  ctx.fillText(text, 8, 4);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  const mat = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: true, depthWrite: false, fog: true });
  const sprite = new THREE.Sprite(mat);
  sprite.scale.set(canvas.width / 55, canvas.height / 55, 1);
  return sprite;
}

/* ── filter toggle ── */
function applyGraphFilters() {
  nodeObjects.forEach((mesh, i) => {
    const type = graphNodes[i]?.type;
    const vis = graphFilters[type] !== false;
    mesh.visible = vis;
    if (labelSprites[i]) labelSprites[i].visible = vis;
  });
  edgeObjects.forEach(line => { line.visible = graphFilters.edges; });
}

function initGraph() {
  const canvas = document.getElementById('graph-canvas');
  if (!canvas || !window.THREE) return;

  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0c0c0c);
  scene.fog = new THREE.FogExp2(0x0c0c0c, 0.003);

  camera = new THREE.PerspectiveCamera(55, canvas.clientWidth / canvas.clientHeight, 0.1, 2000);
  camera.position.set(0, 0, 120);

  renderer3d = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer3d.setSize(canvas.clientWidth, canvas.clientHeight);
  renderer3d.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  controls = new SimpleOrbit(camera, canvas);

  scene.add(new THREE.AmbientLight(0xffffff, 0.7));
  const dir = new THREE.DirectionalLight(0xffffff, 0.5);
  dir.position.set(50, 80, 60);
  scene.add(dir);

  raycaster = new THREE.Raycaster();
  mouse = new THREE.Vector2();

  canvas.addEventListener('mousemove', onMouseMove);
  canvas.addEventListener('click', onGraphClick);

  new ResizeObserver(() => {
    if (!renderer3d) return;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (w === 0 || h === 0) return;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer3d.setSize(w, h);
  }).observe(canvas.parentElement);

  animate();
}

let simCooldown = 0;

function animate() {
  animId = requestAnimationFrame(animate);
  if (!renderer3d) return;
  applyForces();
  graphNodes.forEach((n, i) => {
    if (nodeObjects[i]) {
      nodeObjects[i].position.set(n.x, n.y, n.z);
      if (labelSprites[i]) labelSprites[i].position.set(n.x, n.y - (nodeObjects[i].geometry.parameters?.radius || 2) - 1.8, n.z);
    }
  });
  edgeObjects.forEach((line, i) => {
    const e = graphEdges[i];
    if (!e) return;
    const src = graphNodes.find(n => n.id === e.source);
    const tgt = graphNodes.find(n => n.id === e.target);
    if (src && tgt) {
      const p = line.geometry.attributes.position.array;
      p[0]=src.x; p[1]=src.y; p[2]=src.z; p[3]=tgt.x; p[4]=tgt.y; p[5]=tgt.z;
      line.geometry.attributes.position.needsUpdate = true;
    }
  });
  renderer3d.render(scene, camera);
}

function applyForces() {
  if (simCooldown <= 0) return;
  simCooldown--;
  const nodes = graphNodes, N = nodes.length;
  // repulsion
  for (let i = 0; i < N; i++) {
    for (let j = i + 1; j < N; j++) {
      const dx = nodes[i].x-nodes[j].x, dy = nodes[i].y-nodes[j].y, dz = nodes[i].z-nodes[j].z;
      const d2 = dx*dx+dy*dy+dz*dz+1;
      const f = 180/d2;
      const dist = Math.sqrt(d2);
      const fx=dx/dist*f, fy=dy/dist*f, fz=dz/dist*f;
      nodes[i].vx+=fx; nodes[i].vy+=fy; nodes[i].vz+=fz;
      nodes[j].vx-=fx; nodes[j].vy-=fy; nodes[j].vz-=fz;
    }
  }
  // attraction
  const map = {}; nodes.forEach(n => map[n.id]=n);
  graphEdges.forEach(e => {
    const a=map[e.source], b=map[e.target]; if(!a||!b) return;
    const dx=b.x-a.x, dy=b.y-a.y, dz=b.z-a.z;
    const dist=Math.sqrt(dx*dx+dy*dy+dz*dz)+0.1;
    const f=(dist-14)*0.008;
    a.vx+=dx/dist*f; a.vy+=dy/dist*f; a.vz+=dz/dist*f;
    b.vx-=dx/dist*f; b.vy-=dy/dist*f; b.vz-=dz/dist*f;
  });
  // gravity
  nodes.forEach(n => { n.vx-=n.x*0.002; n.vy-=n.y*0.002; n.vz-=n.z*0.002; });
  // apply
  nodes.forEach(n => { n.vx*=0.86; n.vy*=0.86; n.vz*=0.86; n.x+=n.vx; n.y+=n.vy; n.z+=n.vz; });
}

async function loadGraph() {
  if (!scene) initGraph();
  if (!scene || !hermesHome) return;
  // clear
  nodeObjects.forEach(m => scene.remove(m));
  edgeObjects.forEach(m => scene.remove(m));
  labelSprites.forEach(s => scene.remove(s));
  nodeObjects=[]; edgeObjects=[]; labelSprites=[];

  const data = await dbq('graph');
  if (!data || data.error) return;

  graphNodes = (data.nodes||[]).map(n => ({
    ...n,
    x:(Math.random()-.5)*80, y:(Math.random()-.5)*80, z:(Math.random()-.5)*80,
    vx:0, vy:0, vz:0,
  }));
  graphEdges = data.edges||[];

  // nodes
  graphNodes.forEach(n => {
    const r = n.type==='topic' ? 2.0+(n.importance||5)*0.2
            : n.type==='preference' ? 1.5
            : 0.8+(n.importance||5)*0.1;
    const color = TYPE_COLORS[n.type] || CAT_COLORS[n.category] || 0x727169;
    const geo = n.type==='topic' ? new THREE.OctahedronGeometry(r)
              : n.type==='preference' ? new THREE.BoxGeometry(r*1.4,r*1.4,r*1.4)
              : new THREE.SphereGeometry(r,12,8);
    const mat = new THREE.MeshPhongMaterial({
      color, emissive:color, emissiveIntensity:0.15,
      transparent:true, opacity:0.35+(n.salience||0.5)*0.65,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(n.x, n.y, n.z);
    mesh.userData = n;
    scene.add(mesh);
    nodeObjects.push(mesh);

    // label sprite
    const labelText = (n.type === 'topic' ? (n.label||'') : (n.label||'').substring(0, 24));
    if (labelText) {
      const sprite = createTextSprite(labelText.length > 28 ? labelText.substring(0,26)+'..' : labelText, color);
      sprite.position.set(n.x, n.y - r - 1.8, n.z);
      scene.add(sprite);
      labelSprites.push(sprite);
    } else {
      labelSprites.push(null);
    }
  });

  // edges
  graphEdges.forEach(e => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute([0,0,0,0,0,0],3));
    const c = e.type==='contradicts' ? 0xfb4934 : 0x3c3836;
    const mat = new THREE.LineBasicMaterial({color:c, transparent:true, opacity:e.type==='contradicts'?0.5:0.15});
    const line = new THREE.Line(geo, mat);
    scene.add(line);
    edgeObjects.push(line);
  });

  simCooldown = 500;
}

function onMouseMove(event) {
  if (!renderer3d) return;
  const canvas = renderer3d.domElement;
  const rect = canvas.getBoundingClientRect();
  mouse.x = ((event.clientX-rect.left)/rect.width)*2-1;
  mouse.y = -((event.clientY-rect.top)/rect.height)*2+1;
  raycaster.setFromCamera(mouse, camera);
  const visibleNodes = nodeObjects.filter(m => m.visible);
  const hits = raycaster.intersectObjects(visibleNodes);
  const hoverEl = document.getElementById('graph-hover');
  if (hits.length > 0) {
    const n = hits[0].object.userData;
    hoverEl.style.display = 'block';
    hoverEl.textContent = `[${n.type}] ${n.label}${n.subject_key?'\nkey: '+n.subject_key:''}\nimp: ${n.importance}  sal: ${(n.salience||0).toFixed(2)}`;
    hoverNode = hits[0].object;
    canvas.style.cursor = 'pointer';
  } else {
    hoverEl.style.display = 'none';
    hoverNode = null;
    canvas.style.cursor = 'grab';
  }
}

function onGraphClick() {
  if (!hoverNode) return;
  const n = hoverNode.userData;
  if (typeof showDetail === 'function') {
    showDetail(`${n.type}: ${n.label}`, [
      ['type', n.type], ['label', n.label, 'or'], ['category', n.category||''],
      ['importance', n.importance, 'or'], ['salience', (n.salience||0).toFixed(2)],
      ...(n.subject_key ? [['subject_key', n.subject_key, 'cy']] : []),
    ]);
  }
}

document.getElementById('btn-graph-reset')?.addEventListener('click', () => { if (controls) controls.reset(); });
document.getElementById('btn-load-graph')?.addEventListener('click', loadGraph);
window.loadGraph = loadGraph;

/* ── HUD filter toggles ── */
['topic','fact','preference'].forEach(type => {
  const el = document.getElementById('hud-toggle-' + type);
  if (el) el.addEventListener('click', () => {
    graphFilters[type] = !graphFilters[type];
    el.classList.toggle('filter-off', !graphFilters[type]);
    applyGraphFilters();
  });
});
document.getElementById('hud-toggle-edges')?.addEventListener('click', () => {
  graphFilters.edges = !graphFilters.edges;
  document.getElementById('hud-toggle-edges').classList.toggle('filter-off', !graphFilters.edges);
  applyGraphFilters();
});
