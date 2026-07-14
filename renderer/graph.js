'use strict';

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

const COLORS = { topic: 0xd3869b, fact: 0xfe8019, preference: 0xfabd2f };

export class MemoryGraph {
  constructor(canvas, tooltip, onSelect) {
    this.canvas = canvas;
    this.tooltip = tooltip;
    this.onSelect = onSelect;
    this.nodes = [];
    this.meshes = [];
    this.edges = [];
    this.lines = [];
    this.frames = 0;
    this.pointer = new THREE.Vector2();
    this.raycaster = new THREE.Raycaster();
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.FogExp2(0x0c0c0c, .003);
    this.camera = new THREE.PerspectiveCamera(52, 1, .1, 2000);
    this.camera.position.set(0, 20, 125);
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = .08;
    this.controls.minDistance = 12;
    this.controls.maxDistance = 500;
    this.scene.add(new THREE.AmbientLight(0xffffff, 1.1));
    const light = new THREE.DirectionalLight(0xffffff, 1.4);
    light.position.set(50, 80, 60);
    this.scene.add(light);
    this.canvas.addEventListener('pointermove', (event) => this.hover(event));
    this.canvas.addEventListener('click', () => {
      const hit = this.pick();
      if (hit && this.onSelect) this.onSelect(hit.object.userData);
    });
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(canvas.parentElement);
    this.animate();
  }

  resize() {
    const width = this.canvas.clientWidth || 1;
    const height = this.canvas.clientHeight || 1;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  }

  reset() {
    this.camera.position.set(0, 20, 125);
    this.controls.target.set(0, 0, 0);
    this.controls.update();
  }

  clear() {
    for (const object of [...this.meshes, ...this.lines]) {
      this.scene.remove(object);
      object.geometry?.dispose();
      object.material?.dispose();
    }
    this.meshes = [];
    this.lines = [];
  }

  setData(data) {
    this.clear();
    this.edges = data.edges || [];
    this.nodes = (data.nodes || []).slice(0, 350).map((item, index) => {
      const importance = Number(item.importance || 5);
      const radius = 8 + (10 - importance) * 5;
      const phi = Math.acos(1 - 2 * ((index + .5) / Math.max(1, data.nodes.length)));
      const theta = Math.PI * (1 + Math.sqrt(5)) * index;
      return { ...item, x: Math.cos(theta) * Math.sin(phi) * radius, y: Math.cos(phi) * radius, z: Math.sin(theta) * Math.sin(phi) * radius, vx: 0, vy: 0, vz: 0 };
    });
    const known = new Set(this.nodes.map((item) => item.id));
    this.edges = this.edges.filter((item) => known.has(item.source) && known.has(item.target)).slice(0, 1000);
    for (const item of this.nodes) {
      const size = item.type === 'topic' ? 2.2 : item.type === 'preference' ? 1.7 : 1.05;
      const geometry = item.type === 'topic' ? new THREE.OctahedronGeometry(size) : item.type === 'preference' ? new THREE.BoxGeometry(size * 1.6, size * 1.6, size * 1.6) : new THREE.IcosahedronGeometry(size, 1);
      const color = COLORS[item.type] || 0x83a598;
      const material = new THREE.MeshPhongMaterial({ color, emissive: color, emissiveIntensity: .22, transparent: true, opacity: .45 + Number(item.salience || .5) * .5 });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.set(item.x, item.y, item.z);
      mesh.userData = item;
      this.scene.add(mesh);
      this.meshes.push(mesh);
    }
    for (const edge of this.edges) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute([0,0,0,0,0,0], 3));
      const material = new THREE.LineBasicMaterial({ color: edge.type === 'contradicts' ? 0xfb4934 : 0x83a598, transparent: true, opacity: edge.type === 'contradicts' ? .7 : .16 });
      const line = new THREE.Line(geometry, material);
      this.scene.add(line);
      this.lines.push(line);
    }
    this.frames = 220;
  }

  simulate() {
    if (this.frames <= 0 || this.nodes.length > 350) return;
    this.frames -= 1;
    const nodes = this.nodes;
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i], b = nodes[j];
        const dx = a.x-b.x, dy = a.y-b.y, dz = a.z-b.z;
        const distance2 = dx*dx+dy*dy+dz*dz+2;
        const force = 90 / distance2;
        const distance = Math.sqrt(distance2);
        a.vx += dx/distance*force; a.vy += dy/distance*force; a.vz += dz/distance*force;
        b.vx -= dx/distance*force; b.vy -= dy/distance*force; b.vz -= dz/distance*force;
      }
    }
    const map = new Map(nodes.map((item) => [item.id, item]));
    for (const edge of this.edges) {
      const a = map.get(edge.source), b = map.get(edge.target);
      if (!a || !b) continue;
      const dx=b.x-a.x, dy=b.y-a.y, dz=b.z-a.z, distance=Math.sqrt(dx*dx+dy*dy+dz*dz)+.1, force=(distance-13)*.007;
      a.vx+=dx/distance*force; a.vy+=dy/distance*force; a.vz+=dz/distance*force;
      b.vx-=dx/distance*force; b.vy-=dy/distance*force; b.vz-=dz/distance*force;
    }
    for (const node of nodes) {
      const gravity = .001 + Number(node.importance || 5) * .0005;
      node.vx -= node.x * gravity; node.vy -= node.y * gravity; node.vz -= node.z * gravity;
      node.vx *= .82; node.vy *= .82; node.vz *= .82;
      node.x += node.vx; node.y += node.vy; node.z += node.vz;
    }
  }

  pick() {
    this.raycaster.setFromCamera(this.pointer, this.camera);
    return this.raycaster.intersectObjects(this.meshes, false)[0] || null;
  }

  hover(event) {
    const rect = this.canvas.getBoundingClientRect();
    this.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    const hit = this.pick();
    if (!hit) { this.tooltip.style.display = 'none'; this.canvas.style.cursor = 'grab'; return; }
    const item = hit.object.userData;
    this.tooltip.textContent = `[${item.type}] ${item.label || ''}\nimportance ${item.importance || '—'} · salience ${Number(item.salience || 0).toFixed(2)}`;
    this.tooltip.style.display = 'block';
    this.tooltip.style.left = `${Math.min(rect.width - 290, event.clientX - rect.left + 12)}px`;
    this.tooltip.style.top = `${Math.min(rect.height - 80, event.clientY - rect.top + 12)}px`;
    this.canvas.style.cursor = 'pointer';
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    this.resize();
    this.simulate();
    const map = new Map();
    this.nodes.forEach((item, index) => { this.meshes[index]?.position.set(item.x, item.y, item.z); map.set(item.id, item); });
    this.edges.forEach((edge, index) => {
      const a = map.get(edge.source), b = map.get(edge.target), line = this.lines[index];
      if (!a || !b || !line) return;
      const positions = line.geometry.attributes.position.array;
      positions.set([a.x,a.y,a.z,b.x,b.y,b.z]);
      line.geometry.attributes.position.needsUpdate = true;
    });
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
