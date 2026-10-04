// Three.js viewer for the latest {N}-world-room.glb. Loaded lazily (three is a large chunk).
import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

type Status = 'loading' | 'ready' | 'missing' | 'error' | 'nowebgl';

interface CutPart {
  obj: THREE.Object3D;
  /** wall: horizontal outward offset of the wall from the room centre; ceiling: null */
  offset: THREE.Vector2 | null;
  height: number;
}

/**
 * Room shells from room_gen name their meshes Floor, Ceiling, Wall_NN (+ Trim_NN, Casing_NN,
 * Glass_NN). A part is hidden while the orbit camera is outside its plane, so the interior stays
 * visible from any angle ("dollhouse" cut-away).
 */
function collectCutParts(model: THREE.Object3D, roomCenter: THREE.Vector3): CutPart[] {
  const wallCenters = new Map<string, THREE.Vector3>();
  model.traverse((o) => {
    const m = /^wall_(\d+)/i.exec(o.name);
    if (m) wallCenters.set(m[1], new THREE.Box3().setFromObject(o).getCenter(new THREE.Vector3()));
  });
  const parts: CutPart[] = [];
  model.traverse((o) => {
    if (/^ceiling/i.test(o.name)) {
      parts.push({ obj: o, offset: null, height: new THREE.Box3().setFromObject(o).min.y });
      return;
    }
    const m = /^(wall|trim|casing|glass)_(\d+)/i.exec(o.name);
    const c = m ? wallCenters.get(m[2]) : undefined;
    if (c) parts.push({ obj: o, offset: new THREE.Vector2(c.x - roomCenter.x, c.z - roomCenter.z), height: 0 });
  });
  return parts;
}

function applyCutaway(parts: readonly CutPart[], camera: THREE.Camera, roomCenter: THREE.Vector3, enabled: boolean) {
  const cx = camera.position.x - roomCenter.x;
  const cz = camera.position.z - roomCenter.z;
  for (const p of parts) {
    if (!enabled) p.obj.visible = true;
    else if (!p.offset) p.obj.visible = camera.position.y < p.height;
    else {
      const len = p.offset.length();
      p.obj.visible = len < 1e-6 || (cx * p.offset.x + cz * p.offset.y) / len < len;
    }
  }
}

function disposeTree(root: THREE.Object3D) {
  root.traverse((obj) => {
    const mesh = obj as THREE.Mesh;
    if (mesh.geometry) mesh.geometry.dispose();
    const mats = mesh.material ? (Array.isArray(mesh.material) ? mesh.material : [mesh.material]) : [];
    for (const m of mats) {
      for (const v of Object.values(m)) if (v instanceof THREE.Texture) v.dispose();
      m.dispose();
    }
  });
}

export default function GlbViewer({ url }: { url: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<() => void>(() => {});
  const photoRef = useRef<(() => void) | null>(null);
  const cutRef = useRef(true);
  const [cutaway, setCutaway] = useState(true);
  const [hasPhotoCamera, setHasPhotoCamera] = useState(false);
  cutRef.current = cutaway;
  const [status, setStatus] = useState<Status>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true });
    } catch (e) {
      setStatus('nowebgl');
      setMessage((e as Error).message);
      return;
    }
    let disposed = false;
    setStatus('loading');
    setMessage('');
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1b1e24);
    const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 1000);
    camera.position.set(5, 4, 6);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x3a3a46, 1.4));
    const sun = new THREE.DirectionalLight(0xffffff, 1.8);
    sun.position.set(4, 10, 6);
    scene.add(sun);
    let model: THREE.Object3D | null = null;
    let parts: CutPart[] = [];
    const roomCenter = new THREE.Vector3();

    const resize = () => {
      const w = Math.max(1, host.clientWidth);
      const h = Math.max(1, host.clientHeight);
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    const frame = () => {
      if (!model) return;
      const box = new THREE.Box3().setFromObject(model);
      if (box.isEmpty()) return;
      const center = box.getCenter(new THREE.Vector3());
      const radius = Math.max(box.getSize(new THREE.Vector3()).length() / 2, 0.1);
      const dist = (radius / Math.sin(THREE.MathUtils.degToRad(camera.fov) / 2)) * 1.05;
      const dir = new THREE.Vector3(0.55, 0.75, 0.9).normalize();
      camera.position.copy(center).addScaledVector(dir, dist);
      camera.near = dist / 200;
      camera.far = dist * 50;
      camera.updateProjectionMatrix();
      controls.target.copy(center);
      controls.update();
    };
    frameRef.current = frame;

    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      controls.update();
      applyCutaway(parts, camera, roomCenter, cutRef.current);
      renderer.render(scene, camera);
    };
    loop();

    (async () => {
      try {
        const res = await fetch(url);
        if (disposed) return;
        if (!res.ok) {
          setStatus(res.status === 404 ? 'missing' : 'error');
          setMessage(`HTTP ${res.status}`);
          return;
        }
        const buf = await res.arrayBuffer();
        if (disposed) return;
        const gltf = await new GLTFLoader().parseAsync(buf, '');
        if (disposed) {
          disposeTree(gltf.scene);
          return;
        }
        model = gltf.scene;
        scene.add(model);
        new THREE.Box3().setFromObject(model).getCenter(roomCenter);
        parts = collectCutParts(model, roomCenter);
        const photoCam = model.getObjectByName('PhotoCamera');
        if (photoCam) {
          photoRef.current = () => {
            // look along the photo camera's -Z, orbiting about a point at the room-centre distance
            const pos = photoCam.getWorldPosition(new THREE.Vector3());
            const dir = new THREE.Vector3(0, 0, -1).applyQuaternion(photoCam.getWorldQuaternion(new THREE.Quaternion()));
            camera.position.copy(pos);
            controls.target.copy(pos).addScaledVector(dir, Math.max(pos.distanceTo(roomCenter), 0.5));
            controls.update();
          };
          setHasPhotoCamera(true);
        }
        frame();
        setStatus('ready');
      } catch (e) {
        if (!disposed) {
          setStatus('error');
          setMessage((e as Error).message);
        }
      }
    })();

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      if (model) disposeTree(model);
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [url]);

  return (
    <div className="glb">
      <div className="glb-canvas" ref={hostRef} />
      {status !== 'ready' && (
        <div className="glb-msg">
          {status === 'loading' && 'Loading model...'}
          {status === 'missing' && 'No room GLB yet: run Build.'}
          {status === 'error' && `Could not load the model (${message}).`}
          {status === 'nowebgl' && `WebGL is not available (${message}).`}
        </div>
      )}
      {status === 'ready' && (
        <div className="glb-tools">
          <label className="check small" title="Hide the ceiling and walls between the camera and the room">
            <input type="checkbox" checked={cutaway} onChange={(e) => setCutaway(e.target.checked)} /> cut-away
          </label>
          {hasPhotoCamera && (
            <button type="button" className="small" onClick={() => photoRef.current?.()} title="View from where the photo was taken">
              Photo camera
            </button>
          )}
          <button type="button" className="small glb-reset" onClick={() => frameRef.current()}>
            Reset view
          </button>
        </div>
      )}
    </div>
  );
}
