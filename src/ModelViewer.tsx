import {useEffect,useRef,useState} from 'react';
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {STLLoader} from 'three/addons/loaders/STLLoader.js';
import {OBJLoader} from 'three/addons/loaders/OBJLoader.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
export default function ModelViewer({url,name}:{url:string;name:string}){
 const container=useRef<HTMLDivElement>(null),[error,setError]=useState(''),[loaded,setLoaded]=useState(false),reset=useRef<()=>void>(()=>{});
 useEffect(()=>{const host=container.current;if(!host)return;let disposed=false,renderer:THREE.WebGLRenderer,model:THREE.Object3D|null=null;setError('');setLoaded(false);
  try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});}catch{setError('WebGL is unavailable on this device. Reveal the original file to use another viewer.');return;}
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));host.appendChild(renderer.domElement);renderer.outputColorSpace=THREE.SRGBColorSpace;
  const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(42,1,.01,100000),controls=new OrbitControls(camera,renderer.domElement);
  scene.add(new THREE.HemisphereLight(0xe8f1ff,0x42404a,2.8));const light=new THREE.DirectionalLight(0xffdec2,3);light.position.set(5,9,7);scene.add(light);
  const render=()=>renderer.render(scene,camera),resize=()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();render();};
  controls.addEventListener('change',render);const observer=new ResizeObserver(resize);observer.observe(host);
  const mount=(object:THREE.Object3D)=>{if(disposed)return;model=object;const box=new THREE.Box3().setFromObject(object),size=box.getSize(new THREE.Vector3()),center=box.getCenter(new THREE.Vector3());const span=Math.max(size.x,size.y,size.z);if(!Number.isFinite(span)||span<=0){setError('This model has no visible geometry.');return;}object.position.sub(center);scene.add(object);reset.current=()=>{camera.position.set(span*1.5,span*.95,span*1.5);camera.near=span/1000;camera.far=span*100;camera.updateProjectionMatrix();controls.target.set(0,0,0);controls.update();render();};reset.current();resize();setLoaded(true);};
  const fail=()=>{if(!disposed)setError('This model could not be loaded. Use STL, OBJ or a GLB with embedded resources.');};
  const extension=name.split('.').at(-1)?.toLowerCase();
  if(extension==='stl')new STLLoader().load(url,geometry=>{geometry.computeVertexNormals();mount(new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:0xc5cbd4,roughness:.65,metalness:.12})));},undefined,fail);
  else if(extension==='obj')new OBJLoader().load(url,object=>{object.traverse(child=>{if(child instanceof THREE.Mesh)child.material=new THREE.MeshStandardMaterial({color:0xc5cbd4,roughness:.65,side:THREE.DoubleSide});});mount(object);},undefined,fail);
  else new GLTFLoader().load(url,gltf=>mount(gltf.scene),undefined,fail);
  return()=>{disposed=true;observer.disconnect();controls.dispose();model?.traverse(child=>{if(child instanceof THREE.Mesh){child.geometry.dispose();const materials=Array.isArray(child.material)?child.material:[child.material];materials.forEach(m=>m.dispose());}});renderer.dispose();renderer.domElement.remove();};
 },[url,name]);
 return <div className="model-viewer"><div ref={container}/>{error?<p className="model-viewer-message">{error}</p>:!loaded?<p className="model-viewer-message">Loading model…</p>:<div className="model-viewer-tools"><button onClick={()=>reset.current()}>Reset view</button><span>Drag to rotate · scroll to zoom · right-drag to pan</span></div>}</div>;
}
