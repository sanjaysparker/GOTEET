import { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
export default function ModelViewer({ url, name }: { url: string; name: string }) {
  const container = useRef<HTMLDivElement>(null),
    [error, setError] = useState(''),
    [loaded, setLoaded] = useState(false),
    [stats, setStats] = useState(''),
    [wire, setWire] = useState(false),
    [grid, setGrid] = useState(false),
    command = useRef<(action: string) => void>(() => {});
  useEffect(() => {
    const host = container.current;
    if (!host) return;
    let disposed = false,
      renderer: THREE.WebGLRenderer,
      model: THREE.Object3D | null = null,
      worker: Worker | undefined,
      timeout: ReturnType<typeof setTimeout> | undefined;
    const abort = new AbortController();
    setError('');
    setLoaded(false);
    setWire(false);
    setGrid(false);
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setError('WebGL is unavailable on this device.');
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    host.appendChild(renderer.domElement);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene(),
      camera = new THREE.PerspectiveCamera(42, 1, 0.01, 100000),
      controls = new OrbitControls(camera, renderer.domElement);
    scene.add(new THREE.HemisphereLight(0xe8f1ff, 0x42404a, 2.8));
    const light = new THREE.DirectionalLight(0xffdec2, 3);
    light.position.set(5, 9, 7);
    scene.add(light);
    const reference = new THREE.GridHelper(1, 10, 0x778899, 0x445566);
    reference.visible = false;
    scene.add(reference);
    const render = () => renderer.render(scene, camera),
      resize = () => {
        const w = host.clientWidth,
          h = host.clientHeight;
        if (!w || !h) return;
        renderer.setSize(w, h);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        render();
      };
    controls.addEventListener('change', render);
    const observer = new ResizeObserver(resize);
    observer.observe(host);
    const extension = name.split('.').at(-1)?.toLowerCase() || '',
      cad = ['step', 'stp', 'iges', 'igs', 'brep'].includes(extension);
    const mount = (object: THREE.Object3D) => {
      if (disposed) return;
      model = object;
      const box = new THREE.Box3().setFromObject(object),
        size = box.getSize(new THREE.Vector3()),
        center = box.getCenter(new THREE.Vector3());
      const span = Math.max(size.x, size.y, size.z);
      if (!Number.isFinite(span) || span <= 0) {
        setError('This model has no visible geometry.');
        return;
      }
      object.position.sub(center);
      scene.add(object);
      reference.scale.setScalar(span * 2);
      reference.position.y = -size.y / 2;
      let meshes = 0,
        triangles = 0;
      object.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          meshes++;
          triangles += (child.geometry.index?.count || child.geometry.attributes.position.count) / 3;
        }
      });
      setStats(
        `${meshes} meshes · ${Math.round(triangles).toLocaleString()} triangles · bounds ${size.x.toFixed(2)} × ${size.y.toFixed(2)} × ${size.z.toFixed(2)} ${cad && extension !== 'brep' ? 'mm' : 'model units'}`,
      );
      command.current = (action) => {
        if (action === 'wire') {
          object.traverse((child) => {
            if (child instanceof THREE.Mesh) {
              const mats = Array.isArray(child.material) ? child.material : [child.material];
              mats.forEach((m) => {
                if ('wireframe' in m)
                  (m as THREE.MeshStandardMaterial).wireframe = !(m as THREE.MeshStandardMaterial).wireframe;
              });
            }
          });
        } else if (action === 'grid') reference.visible = !reference.visible;
        else {
          camera.up.set(0, 1, 0);
          if (action === 'front') camera.position.set(0, 0, span * 2);
          else if (action === 'right') camera.position.set(span * 2, 0, 0);
          else if (action === 'top') {
            camera.position.set(0, span * 2, 0);
            camera.up.set(0, 0, -1);
          } else camera.position.set(span * 1.5, span * 0.95, span * 1.5);
          camera.near = span / 1000;
          camera.far = span * 100;
          camera.updateProjectionMatrix();
          controls.target.set(0, 0, 0);
          controls.update();
        }
        render();
      };
      command.current('fit');
      resize();
      setLoaded(true);
    };
    const fail = () => {
      if (!disposed)
        setError('Unable to read this model. Supported: STL, OBJ, embedded GLB, STEP, IGES and BREP.');
    };
    if (cad) {
      (async () => {
        const response = await fetch(url, { signal: abort.signal });
        if (!response.ok) throw Error('Unavailable');
        const buffer = await response.arrayBuffer();
        if (buffer.byteLength > 25 * 1024 * 1024) throw Error('CAD preview limit is 25 MB');
        if (disposed) return;
        worker = new Worker(new URL('./cad-worker.js', document.baseURI));
        timeout = setTimeout(() => {
          worker?.terminate();
          if (!disposed) setError('CAD conversion exceeded 30 seconds. Try a smaller model.');
        }, 30000);
        worker.onerror = () => {
          clearTimeout(timeout);
          worker?.terminate();
          fail();
        };
        worker.onmessage = ({ data }) => {
          clearTimeout(timeout);
          worker?.terminate();
          if (disposed) return;
          if (!data.success) {
            fail();
            return;
          }
          const group = new THREE.Group();
          for (const mesh of data.meshes) {
            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute(
              'position',
              new THREE.Float32BufferAttribute(mesh.attributes.position.array, 3),
            );
            geometry.setIndex(mesh.index.array);
            if (mesh.attributes.normal)
              geometry.setAttribute(
                'normal',
                new THREE.Float32BufferAttribute(mesh.attributes.normal.array, 3),
              );
            else geometry.computeVertexNormals();
            const color = mesh.color
              ? new THREE.Color(...(mesh.color as [number, number, number]))
              : new THREE.Color(0xc5cbd4);
            group.add(
              new THREE.Mesh(
                geometry,
                new THREE.MeshStandardMaterial({ color, roughness: 0.6, side: THREE.DoubleSide }),
              ),
            );
          }
          mount(group);
        };
        worker.postMessage({ extension, buffer }, [buffer]);
      })().catch((e) => {
        if (!disposed) setError(String(e));
      });
    } else if (extension === 'stl')
      new STLLoader().load(
        url,
        (geometry) => {
          geometry.computeVertexNormals();
          mount(
            new THREE.Mesh(
              geometry,
              new THREE.MeshStandardMaterial({ color: 0xc5cbd4, roughness: 0.65, metalness: 0.12 }),
            ),
          );
        },
        undefined,
        fail,
      );
    else if (extension === 'obj')
      new OBJLoader().load(
        url,
        (object) => {
          object.traverse((child) => {
            if (child instanceof THREE.Mesh)
              child.material = new THREE.MeshStandardMaterial({
                color: 0xc5cbd4,
                roughness: 0.65,
                side: THREE.DoubleSide,
              });
          });
          mount(object);
        },
        undefined,
        fail,
      );
    else new GLTFLoader().load(url, (gltf) => mount(gltf.scene), undefined, fail);
    return () => {
      disposed = true;
      abort.abort();
      clearTimeout(timeout);
      worker?.terminate();
      observer.disconnect();
      controls.dispose();
      model?.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          child.geometry.dispose();
          const materials = Array.isArray(child.material) ? child.material : [child.material];
          materials.forEach((m) => m.dispose());
        }
      });
      reference.geometry.dispose();
      (reference.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [url, name]);
  return (
    <div className="model-viewer">
      <div ref={container} />
      {error ? (
        <p className="model-viewer-message">{error}</p>
      ) : !loaded ? (
        <p className="model-viewer-message">Loading model…</p>
      ) : (
        <div className="model-viewer-tools">
          {['fit', 'front', 'top', 'right'].map((v) => (
            <button key={v} onClick={() => command.current(v)}>
              {v === 'fit' ? 'Fit / isometric' : v[0].toUpperCase() + v.slice(1)}
            </button>
          ))}
          <button
            aria-pressed={wire}
            onClick={() => {
              command.current('wire');
              setWire(!wire);
            }}
          >
            Wireframe
          </button>
          <button
            aria-pressed={grid}
            onClick={() => {
              command.current('grid');
              setGrid(!grid);
            }}
          >
            Grid
          </button>
          <span>{stats}</span>
          <small>
            Drag to orbit · scroll to zoom · right-drag to pan · reading view, original geometry unchanged
          </small>
        </div>
      )}
    </div>
  );
}
