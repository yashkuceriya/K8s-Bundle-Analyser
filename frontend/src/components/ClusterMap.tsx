import { useEffect, useRef, useMemo, useState, useCallback } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Server, Box, Hexagon, Circle, Layers, Search, Maximize2, Minimize2, Eye, EyeOff, Database, Shield, Briefcase, Globe } from 'lucide-react';
import clsx from 'clsx';
import type { TopologyNode, TopologyEdge } from '../types';

interface ClusterMapProps {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

/* ─── Colors ─── */
const statusHex: Record<string, number> = {
  healthy: 0x10b981, running: 0x10b981, ready: 0x10b981,
  critical: 0xef4444, error: 0xef4444,
  warning: 0xf59e0b, pending: 0xf59e0b,
  unknown: 0x6b7280,
};
const typeHex: Record<string, number> = {
  node: 0x3b82f6, namespace: 0x8b5cf6, deployment: 0x06b6d4, service: 0xf59e0b,
  statefulset: 0x8b5cf6, daemonset: 0x6366f1, job: 0xa855f7, ingress: 0x14b8a6,
};
const statusStr: Record<string, string> = {
  healthy: '#10b981', running: '#10b981', ready: '#10b981',
  critical: '#ef4444', error: '#ef4444',
  warning: '#f59e0b', pending: '#f59e0b', unknown: '#6b7280',
};
function getColor(t: string, s: string): number {
  const sl = s.toLowerCase();
  // Unhealthy resources always show status color — red/yellow pops out
  if (sl === 'critical' || sl === 'error') return 0xef4444;
  if (sl === 'warning' || sl === 'pending') return 0xf59e0b;
  // Pods show green when healthy for quick scan
  if (t.toLowerCase() === 'pod') return statusHex[sl] ?? 0x6b7280;
  // Healthy non-pods use type color
  return typeHex[t.toLowerCase()] ?? 0x6b7280;
}

/* ─── Radial hierarchical layout ─── */
interface Pos3 { node: TopologyNode; p: THREE.Vector3 }

function layout(nodes: TopologyNode[]): Pos3[] {
  const layers: Record<string, { ring: number; yOff: number; size: number }> = {
    node:        { ring: 0,   yOff: 2,    size: 0.7 },
    namespace:   { ring: 3.5, yOff: 1,    size: 0.5 },
    deployment:  { ring: 6.5, yOff: 0,    size: 0.4 },
    statefulset: { ring: 6.5, yOff: 0.8,  size: 0.4 },
    daemonset:   { ring: 6.5, yOff: -0.3, size: 0.38 },
    job:         { ring: 7.5, yOff: -0.8, size: 0.32 },
    service:     { ring: 6.5, yOff: -0.5, size: 0.38 },
    ingress:     { ring: 4.5, yOff: -0.5, size: 0.38 },
    pod:         { ring: 10,  yOff: -1.5, size: 0.28 },
  };

  const grouped: Record<string, TopologyNode[]> = {};
  nodes.forEach(n => { (grouped[n.type.toLowerCase()] ??= []).push(n); });

  const result: Pos3[] = [];
  const order = ['node', 'namespace', 'ingress', 'deployment', 'statefulset', 'daemonset', 'service', 'job', 'pod'];

  for (const type of order) {
    const grp = grouped[type];
    if (!grp) continue;
    const cfg = layers[type] || { ring: 8, yOff: 0, size: 0.3 };
    const count = grp.length;

    if (cfg.ring === 0) {
      // Center nodes — small cluster
      grp.forEach((n, i) => {
        const angle = (i / Math.max(count, 1)) * Math.PI * 2;
        const r = count === 1 ? 0 : 1.2;
        result.push({
          node: n,
          p: new THREE.Vector3(
            Math.cos(angle) * r,
            cfg.yOff,
            Math.sin(angle) * r,
          ),
        });
      });
    } else {
      // Radial ring with jitter for organic feel
      grp.forEach((n, i) => {
        const angle = (i / count) * Math.PI * 2 + (type === 'service' ? Math.PI / count : 0);
        const jitter = (Math.random() - 0.5) * 1.2;
        const r = cfg.ring + jitter;
        const yJitter = (Math.random() - 0.5) * 0.8;
        result.push({
          node: n,
          p: new THREE.Vector3(
            Math.cos(angle) * r,
            cfg.yOff + yJitter,
            Math.sin(angle) * r,
          ),
        });
      });
    }
  }
  return result;
}

function getNodeSize(type: string): number {
  return { node: 0.7, namespace: 0.5, deployment: 0.4, statefulset: 0.4, daemonset: 0.38, job: 0.32, service: 0.38, ingress: 0.38, pod: 0.28 }[type.toLowerCase()] ?? 0.3;
}

/* ─── Build geometry by type ─── */
function createNodeGeometry(type: string, size: number): THREE.BufferGeometry {
  switch (type.toLowerCase()) {
    case 'node':
      return new THREE.BoxGeometry(size * 1.6, size * 1.6, size * 1.6);
    case 'namespace':
      return new THREE.OctahedronGeometry(size * 1.3);
    case 'deployment':
      return new THREE.CylinderGeometry(size * 0.9, size * 0.9, size * 1.4, 6);
    case 'statefulset':
      return new THREE.CylinderGeometry(size * 0.5, size * 1.0, size * 1.5, 6); // tapered hexagonal
    case 'daemonset':
      return new THREE.TorusKnotGeometry(size * 0.6, size * 0.2, 48, 8, 2, 3);
    case 'job':
      return new THREE.TetrahedronGeometry(size * 1.2);
    case 'service':
      return new THREE.DodecahedronGeometry(size * 1.1);
    case 'ingress':
      return new THREE.ConeGeometry(size * 0.9, size * 1.6, 4); // diamond/arrow shape
    case 'pod':
    default:
      return new THREE.SphereGeometry(size, 24, 24);
  }
}

/* ─── Three.js scene ─── */
function createScene(
  canvas: HTMLCanvasElement,
  nodes: Pos3[],
  edges: TopologyEdge[],
  onHover: (info: { node: TopologyNode; x: number; y: number } | null) => void,
  onClick: (id: string) => void,
  onLabelsUpdate: (labels: { id: string; name: string; type: string; x: number; y: number; visible: boolean }[]) => void,
) {
  const W = canvas.clientWidth, H = canvas.clientHeight;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  renderer.setSize(W, H);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x060a12);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.4;

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x060a12, 0.018);

  // Camera
  const camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 200);
  camera.position.set(12, 10, 16);

  const controls = new OrbitControls(camera, canvas);
  controls.target.set(0, 0, 0);
  controls.enableDamping = true;
  controls.dampingFactor = 0.05;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.4;
  controls.maxDistance = 50;
  controls.minDistance = 5;

  // Lights — richer, more cinematic
  scene.add(new THREE.AmbientLight(0x334466, 0.6));
  const keyLight = new THREE.PointLight(0x06b6d4, 2.0, 60);
  keyLight.position.set(15, 12, 10);
  scene.add(keyLight);
  const fillLight = new THREE.PointLight(0x8b5cf6, 1.0, 50);
  fillLight.position.set(-12, 6, -10);
  scene.add(fillLight);
  const rimLight = new THREE.PointLight(0x3b82f6, 0.6, 40);
  rimLight.position.set(0, -8, 12);
  scene.add(rimLight);
  const topLight = new THREE.DirectionalLight(0xffffff, 0.3);
  topLight.position.set(0, 20, 0);
  scene.add(topLight);

  // Ground plane — subtle radial gradient
  const groundGeo = new THREE.CircleGeometry(25, 64);
  const groundMat = new THREE.MeshBasicMaterial({
    color: 0x0a1020, transparent: true, opacity: 0.5, side: THREE.DoubleSide,
  });
  const ground = new THREE.Mesh(groundGeo, groundMat);
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -3;
  scene.add(ground);

  // Concentric ring guides
  [3.5, 6.5, 10].forEach(r => {
    const ringGeo = new THREE.RingGeometry(r - 0.02, r + 0.02, 96);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x1a2744, transparent: true, opacity: 0.3, side: THREE.DoubleSide });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = -2.8;
    scene.add(ring);
  });

  // Starfield background
  const starCount = 600;
  const starPositions = new Float32Array(starCount * 3);
  const starSizes = new Float32Array(starCount);
  for (let i = 0; i < starCount; i++) {
    starPositions[i * 3] = (Math.random() - 0.5) * 120;
    starPositions[i * 3 + 1] = (Math.random() - 0.5) * 80;
    starPositions[i * 3 + 2] = (Math.random() - 0.5) * 120;
    starSizes[i] = Math.random() * 1.5 + 0.3;
  }
  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
  starGeo.setAttribute('size', new THREE.BufferAttribute(starSizes, 1));
  scene.add(new THREE.Points(starGeo, new THREE.PointsMaterial({
    color: 0x4466aa, size: 0.08, transparent: true, opacity: 0.5, sizeAttenuation: true,
  })));

  // Build nodes
  const idToMesh = new Map<THREE.Object3D, string>();
  const meshData: { mesh: THREE.Mesh; glow: THREE.Mesh; ring: THREE.Mesh; baseY: number; off: number }[] = [];

  nodes.forEach(({ node, p }) => {
    const c = getColor(node.type, node.status);
    const size = getNodeSize(node.type);

    // Outer glow sphere
    const glow = new THREE.Mesh(
      new THREE.SphereGeometry(size * 2.5, 16, 16),
      new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: 0.06 }),
    );
    glow.position.copy(p);
    scene.add(glow);

    // Orbit ring
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(size * 1.6, 0.025, 8, 64),
      new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: 0.25 }),
    );
    ring.position.copy(p);
    ring.rotation.x = Math.PI / 2 + (Math.random() - 0.5) * 0.4;
    ring.rotation.z = (Math.random() - 0.5) * 0.4;
    scene.add(ring);

    // Main mesh — distinct geometry per type
    const geo = createNodeGeometry(node.type, size);
    const mat = new THREE.MeshStandardMaterial({
      color: c, emissive: c, emissiveIntensity: 0.4,
      roughness: 0.15, metalness: 0.85,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(p);
    scene.add(mesh);
    idToMesh.set(mesh, node.id);

    meshData.push({ mesh, glow, ring, baseY: p.y, off: p.x * 1.3 + p.z * 0.7 });
  });

  // Build edges — glowing tubes
  const posMap = new Map<string, THREE.Vector3>();
  nodes.forEach(n => posMap.set(n.node.id, n.p));

  const particlePositions: number[] = [];
  const edgeAnims: { curve: THREE.QuadraticBezierCurve3; sp: number; off: number }[] = [];

  const edgeColors: Record<string, number> = {
    runs: 0x3b82f6, owns: 0x06b6d4, selects: 0xf59e0b, routes: 0x14b8a6, default: 0x334466,
  };

  edges.forEach(e => {
    const a = posMap.get(e.source), b = posMap.get(e.target);
    if (!a || !b) return;
    const edgeColor = edgeColors[(e.label || 'default').toLowerCase()] ?? edgeColors.default;

    // Mid-point with arc
    const mid = new THREE.Vector3(
      (a.x + b.x) / 2,
      (a.y + b.y) / 2 + 1.5,
      (a.z + b.z) / 2,
    );
    const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
    const pts = curve.getPoints(40);

    // Tube geometry for thicker, visible edges
    const tubeGeo = new THREE.TubeGeometry(curve, 20, 0.035, 6, false);
    const tubeMat = new THREE.MeshBasicMaterial({
      color: edgeColor, transparent: true, opacity: 0.5,
    });
    scene.add(new THREE.Mesh(tubeGeo, tubeMat));

    // Glow line on top
    const lineGeo = new THREE.BufferGeometry().setFromPoints(pts);
    scene.add(new THREE.Line(lineGeo, new THREE.LineBasicMaterial({
      color: edgeColor, transparent: true, opacity: 0.2,
    })));

    // Particles for this edge
    for (let j = 0; j < 3; j++) {
      particlePositions.push(a.x, a.y, a.z);
      edgeAnims.push({ curve, sp: 0.12 + Math.random() * 0.2, off: Math.random() });
    }
  });

  // Animated particles along edges
  const pGeo = new THREE.BufferGeometry();
  pGeo.setAttribute('position', new THREE.Float32BufferAttribute(particlePositions, 3));
  scene.add(new THREE.Points(pGeo, new THREE.PointsMaterial({
    color: 0x06b6d4, size: 0.12, transparent: true, opacity: 0.9, sizeAttenuation: true,
  })));

  // Raycaster
  const ray = new THREE.Raycaster();
  const ptr = new THREE.Vector2();
  const allMeshes = [...idToMesh.keys()];

  const onPointerMove = (ev: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    ptr.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    ptr.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    ray.setFromCamera(ptr, camera);
    const hits = ray.intersectObjects(allMeshes);
    if (hits.length > 0) {
      canvas.style.cursor = 'pointer';
      const id = idToMesh.get(hits[0].object);
      const found = nodes.find(n => n.node.id === id);
      if (found) onHover({ node: found.node, x: ev.clientX - rect.left, y: ev.clientY - rect.top });
    } else {
      canvas.style.cursor = 'grab';
      onHover(null);
    }
  };

  const onPointerClick = (ev: MouseEvent) => {
    const rect = canvas.getBoundingClientRect();
    ptr.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    ptr.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
    ray.setFromCamera(ptr, camera);
    const hits = ray.intersectObjects(allMeshes);
    if (hits.length > 0) {
      const id = idToMesh.get(hits[0].object);
      if (id) onClick(id);
    }
  };

  canvas.addEventListener('pointermove', onPointerMove);
  canvas.addEventListener('click', onPointerClick);

  // Resize
  const ro = new ResizeObserver(() => {
    const nw = canvas.clientWidth, nh = canvas.clientHeight;
    if (nw > 0 && nh > 0) {
      renderer.setSize(nw, nh);
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
    }
  });
  ro.observe(canvas);

  // Animate
  let alive = true;
  const clock = new THREE.Clock();
  let labelFrame = 0;

  (function loop() {
    if (!alive) return;
    requestAnimationFrame(loop);
    const t = clock.getElapsedTime();

    // Animate nodes — gentle float + rotate
    meshData.forEach(({ mesh, glow, ring, baseY, off }) => {
      const y = baseY + Math.sin(t * 0.6 + off) * 0.12;
      mesh.position.y = y;
      glow.position.y = y;
      ring.position.y = y;
      mesh.rotation.y = t * 0.15 + off;
      mesh.rotation.x = Math.sin(t * 0.3 + off) * 0.1;
      ring.rotation.z = t * 0.25 + off;
      glow.scale.setScalar(1 + Math.sin(t * 1.0 + off) * 0.15);
    });

    // Animate particles along curves
    const pa = pGeo.getAttribute('position');
    edgeAnims.forEach((ed, i) => {
      const progress = (t * ed.sp + ed.off) % 1;
      const point = ed.curve.getPoint(progress);
      pa.setXYZ(i, point.x, point.y, point.z);
    });
    pa.needsUpdate = true;

    controls.update();
    renderer.render(scene, camera);

    // Labels — update every 3 frames
    labelFrame++;
    if (labelFrame % 3 === 0) {
      const cw = canvas.clientWidth, ch = canvas.clientHeight;
      const lbls = nodes.map(({ node, p }) => {
        const v = new THREE.Vector3(p.x, p.y + getNodeSize(node.type) + 0.5, p.z);
        v.project(camera);
        const x = (v.x * 0.5 + 0.5) * cw;
        const y = (-v.y * 0.5 + 0.5) * ch;
        return { id: node.id, name: node.label, type: node.type, x, y, visible: v.z < 1 && x > 0 && x < cw && y > 0 && y < ch };
      });
      onLabelsUpdate(lbls);
    }
  })();

  return () => {
    alive = false;
    canvas.removeEventListener('pointermove', onPointerMove);
    canvas.removeEventListener('click', onPointerClick);
    ro.disconnect();
    controls.dispose();
    renderer.dispose();
  };
}

/* ─── Icons ─── */
function NodeIcon({ type, size = 14 }: { type: string; size?: number }) {
  switch (type.toLowerCase()) {
    case 'node': return <Server size={size} />;
    case 'deployment': return <Box size={size} />;
    case 'statefulset': return <Database size={size} />;
    case 'daemonset': return <Shield size={size} />;
    case 'job': return <Briefcase size={size} />;
    case 'service': return <Hexagon size={size} />;
    case 'ingress': return <Globe size={size} />;
    case 'pod': return <Circle size={size} />;
    case 'namespace': return <Layers size={size} />;
    default: return <Box size={size} />;
  }
}

interface Label3D { id: string; name: string; type: string; x: number; y: number; visible: boolean }

/* ─── React wrapper ─── */
export default function ClusterMap({ nodes, edges }: ClusterMapProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [selectedNode, setSelectedNode] = useState<TopologyNode | null>(null);
  const [hoverInfo, setHoverInfo] = useState<{ node: TopologyNode; x: number; y: number } | null>(null);
  const [labels, setLabels] = useState<Label3D[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const positioned = useMemo(() => layout(nodes), [nodes]);

  const matchingIds = useMemo(() => {
    if (!searchQuery.trim()) return new Set<string>();
    const q = searchQuery.toLowerCase();
    return new Set(
      nodes.filter(n =>
        n.label.toLowerCase().includes(q) ||
        n.type.toLowerCase().includes(q) ||
        n.namespace?.toLowerCase().includes(q) ||
        n.status.toLowerCase().includes(q)
      ).map(n => n.id)
    );
  }, [nodes, searchQuery]);

  const toggleFullscreen = useCallback(() => {
    if (!containerRef.current) return;
    if (!document.fullscreenElement) {
      containerRef.current.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  }, []);

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  const handleClick = useCallback((id: string) => {
    setSelectedNode(nodes.find(n => n.id === id) ?? null);
  }, [nodes]);

  const handleLabels = useCallback((l: Label3D[]) => setLabels(l), []);

  const handleHover = useCallback((info: { node: TopologyNode; x: number; y: number } | null) => {
    setHoverInfo(info);
  }, []);

  useEffect(() => {
    if (!canvasRef.current || !nodes.length) return;
    return createScene(canvasRef.current, positioned, edges, handleHover, handleClick, handleLabels);
  }, [positioned, edges, handleHover, handleClick, handleLabels, nodes.length]);

  if (!nodes.length) {
    return (
      <div className="flex items-center justify-center h-96 bg-navy-800 rounded-xl border border-navy-600 text-gray-500">
        <p>No cluster topology data available</p>
      </div>
    );
  }

  // Count by type for legend
  const typeCounts = useMemo(() => {
    const c: Record<string, number> = {};
    nodes.forEach(n => { c[n.type.toLowerCase()] = (c[n.type.toLowerCase()] || 0) + 1; });
    return c;
  }, [nodes]);

  return (
    <div ref={containerRef} className={clsx("relative rounded-xl border border-navy-600 overflow-hidden bg-[#060a12]", isFullscreen && "h-screen")} style={isFullscreen ? undefined : { height: 700 }}>
      <canvas ref={canvasRef} className="w-full h-full block" />

      {/* Search + Controls */}
      <div className="absolute top-4 right-4 z-10 flex items-center gap-2">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search nodes..."
            className="w-48 bg-[#0c1222]/90 backdrop-blur-md border border-navy-600 rounded-lg pl-8 pr-3 py-1.5 text-xs text-gray-300 outline-none focus:border-[#06b6d4] placeholder-gray-600"
          />
          {searchQuery && (
            <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-[#06b6d4]">
              {matchingIds.size} found
            </span>
          )}
        </div>
        <button
          onClick={() => setShowAllLabels(!showAllLabels)}
          className={clsx(
            "p-1.5 rounded-lg border backdrop-blur-md transition-colors",
            showAllLabels
              ? "bg-[#06b6d4]/20 border-[#06b6d4]/50 text-[#06b6d4]"
              : "bg-[#0c1222]/90 border-navy-600 text-gray-400 hover:text-gray-300"
          )}
          title={showAllLabels ? "Hide labels" : "Show all labels"}
        >
          {showAllLabels ? <Eye size={14} /> : <EyeOff size={14} />}
        </button>
        <button
          onClick={toggleFullscreen}
          className="p-1.5 bg-[#0c1222]/90 backdrop-blur-md border border-navy-600 rounded-lg text-gray-400 hover:text-gray-300 transition-colors"
          title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
        >
          {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
      </div>

      {/* 3D node labels */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden z-[5]">
        {labels.filter(l => {
          if (!l.visible) return false;
          if (searchQuery && matchingIds.size > 0) return matchingIds.has(l.id);
          if (showAllLabels) return true;
          return selectedNode?.id === l.id;
        }).map(l => (
          <div
            key={l.id}
            className="absolute text-center -translate-x-1/2 whitespace-nowrap transition-opacity duration-200"
            style={{ left: l.x, top: l.y - 24 }}
          >
            <span className={clsx(
              "px-2 py-0.5 border rounded text-[10px] font-semibold backdrop-blur-sm",
              searchQuery && matchingIds.has(l.id)
                ? "bg-[#06b6d4]/20 border-[#06b6d4]/50 text-[#06b6d4] shadow-[0_0_8px_rgba(6,182,212,0.3)]"
                : "bg-[#0c1222]/80 border-navy-600 text-white"
            )}>
              {l.name}
            </span>
          </div>
        ))}
      </div>

      {/* Hover tooltip */}
      {hoverInfo && (
        <div
          className="absolute z-20 pointer-events-none bg-[#0c1222]/95 backdrop-blur-md border border-navy-500 rounded-lg px-3 py-2.5 shadow-2xl shadow-black/50"
          style={{ left: hoverInfo.x + 16, top: hoverInfo.y - 10, maxWidth: 280 }}
        >
          <div className="flex items-center gap-2 mb-1.5">
            <span
              className="w-2.5 h-2.5 rounded-full shadow-lg"
              style={{ backgroundColor: statusStr[hoverInfo.node.status.toLowerCase()] || '#6b7280', boxShadow: `0 0 6px ${statusStr[hoverInfo.node.status.toLowerCase()] || '#6b7280'}` }}
            />
            <span className="text-xs font-semibold text-white">{hoverInfo.node.label}</span>
          </div>
          <div className="flex items-center gap-3 text-[10px] text-gray-400">
            <span className="flex items-center gap-1">
              <NodeIcon type={hoverInfo.node.type} size={10} />
              {hoverInfo.node.type}
            </span>
            <span className="px-1.5 py-0.5 rounded bg-navy-700/50 text-gray-300">{hoverInfo.node.status}</span>
            {hoverInfo.node.namespace && <span>ns/{hoverInfo.node.namespace}</span>}
          </div>
          {Object.keys(hoverInfo.node.metadata || {}).length > 0 && (
            <div className="mt-1.5 pt-1.5 border-t border-navy-600 space-y-0.5">
              {Object.entries(hoverInfo.node.metadata).slice(0, 3).map(([k, v]) => (
                <div key={k} className="flex justify-between text-[10px]">
                  <span className="text-gray-500">{k}</span>
                  <span className="text-gray-300 truncate ml-2 max-w-[130px] font-mono">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Legend */}
      <div className="absolute top-4 left-4 z-10 bg-[#0c1222]/90 backdrop-blur-md border border-navy-600 rounded-xl p-3.5 space-y-1.5 min-w-[160px] max-h-[calc(100%-6rem)] overflow-y-auto">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-2">Resources</p>
        {[
          { label: 'Node', color: '#3b82f6', icon: 'node' },
          { label: 'Namespace', color: '#8b5cf6', icon: 'namespace' },
          { label: 'Deployment', color: '#06b6d4', icon: 'deployment' },
          { label: 'StatefulSet', color: '#8b5cf6', icon: 'statefulset' },
          { label: 'DaemonSet', color: '#6366f1', icon: 'daemonset' },
          { label: 'Job', color: '#a855f7', icon: 'job' },
          { label: 'Service', color: '#f59e0b', icon: 'service' },
          { label: 'Ingress', color: '#14b8a6', icon: 'ingress' },
          { label: 'Pod', color: '#10b981', icon: 'pod' },
        ].filter(item => typeCounts[item.icon]).map(item => (
          <div key={item.label} className="flex items-center gap-2 text-[11px] text-gray-400">
            <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: item.color, boxShadow: `0 0 4px ${item.color}40` }} />
            <NodeIcon type={item.icon} size={11} />
            <span className="flex-1">{item.label}</span>
            <span className="text-[9px] text-gray-600">{typeCounts[item.icon]}</span>
          </div>
        ))}
        <div className="border-t border-navy-600 mt-2 pt-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-1.5">Status</p>
          {[
            { label: 'Healthy', color: '#10b981' },
            { label: 'Warning', color: '#f59e0b' },
            { label: 'Critical', color: '#ef4444' },
          ].map(item => (
            <div key={item.label} className="flex items-center gap-2 text-[11px] text-gray-400">
              <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: item.color, boxShadow: `0 0 6px ${item.color}60` }} />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
        <div className="border-t border-navy-600 mt-2 pt-2">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 mb-1.5">Connections</p>
          {[
            { label: 'Runs on', color: '#3b82f6' },
            { label: 'Owns', color: '#06b6d4' },
            { label: 'Selects', color: '#f59e0b' },
            { label: 'Routes', color: '#14b8a6' },
          ].map(item => (
            <div key={item.label} className="flex items-center gap-2 text-[11px] text-gray-400">
              <span className="w-5 h-[3px] rounded-full shrink-0" style={{ backgroundColor: item.color, boxShadow: `0 0 4px ${item.color}60` }} />
              <span>{item.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom info bar */}
      <div className="absolute bottom-4 left-4 right-4 z-10 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-gray-600 bg-[#0c1222]/80 backdrop-blur-sm px-2 py-1 rounded-md border border-navy-700">
            Drag to rotate &middot; Scroll to zoom &middot; Click to inspect
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] bg-[#0c1222]/80 backdrop-blur-sm border border-navy-600 rounded-md px-2.5 py-1 text-gray-400 font-mono">
            {nodes.length} resources &middot; {edges.length} connections
          </span>
        </div>
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <div className="absolute top-14 right-4 w-72 bg-[#0c1222]/95 backdrop-blur-md border border-navy-500 rounded-xl p-4 shadow-2xl shadow-black/40 z-10">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: statusStr[selectedNode.status.toLowerCase()] || '#6b7280', boxShadow: `0 0 8px ${statusStr[selectedNode.status.toLowerCase()] || '#6b7280'}` }}
              />
              <h3 className="text-sm font-semibold text-white">{selectedNode.label}</h3>
            </div>
            <button onClick={() => setSelectedNode(null)} className="text-gray-500 hover:text-gray-300 text-xs px-1.5 py-0.5 rounded hover:bg-navy-700 transition-colors">
              Close
            </button>
          </div>
          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Type</span>
              <span className="text-gray-300 flex items-center gap-1.5 bg-navy-700/50 px-2 py-0.5 rounded">
                <NodeIcon type={selectedNode.type} size={12} />{selectedNode.type}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Status</span>
              <span className="px-2 py-0.5 rounded font-medium" style={{
                color: statusStr[selectedNode.status.toLowerCase()] || '#6b7280',
                backgroundColor: `${statusStr[selectedNode.status.toLowerCase()] || '#6b7280'}15`,
              }}>
                {selectedNode.status}
              </span>
            </div>
            {selectedNode.namespace && (
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Namespace</span>
                <span className="text-gray-300 font-mono text-[11px]">{selectedNode.namespace}</span>
              </div>
            )}
            {Object.entries(selectedNode.metadata || {}).length > 0 && (
              <div className="border-t border-navy-600 pt-2 mt-2 space-y-1.5">
                {Object.entries(selectedNode.metadata).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-gray-500 text-[10px]">{k}</span>
                    <span className="text-gray-300 truncate ml-2 max-w-[140px] font-mono text-[10px]">{String(v)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
