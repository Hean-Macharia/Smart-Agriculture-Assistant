import { useEffect, useRef } from "react";
import * as THREE from "three";

export default function FarmScene() {
  const host = useRef(null);
  useEffect(() => {
    const node = host.current;
    if (!node) return;
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: "low-power" }); }
    catch { node.dataset.webgl = "unavailable"; return; }

    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.setSize(node.clientWidth, node.clientHeight);
    renderer.setClearColor(0x000000, 0);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    node.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, node.clientWidth / node.clientHeight, 0.1, 80);
    camera.position.set(0, 3.8, 8.5);
    camera.lookAt(0, 0.55, 0);
    scene.add(new THREE.HemisphereLight(0xf5fff0, 0x657145, 2.1));
    const keyLight = new THREE.DirectionalLight(0xffedbd, 3);
    keyLight.position.set(-4, 8, 5);
    scene.add(keyLight);

    const field = new THREE.Group();
    scene.add(field);
    const earth = new THREE.Mesh(new THREE.CircleGeometry(5.5, 64), new THREE.MeshStandardMaterial({ color: 0xe0e9cd, roughness: 1 }));
    earth.rotation.x = -Math.PI / 2;
    earth.position.y = -0.09;
    field.add(earth);

    [0x4f8746, 0x5f964a, 0x72a352, 0x82aa5a, 0x739a4e, 0x5d8845].forEach((color, index) => {
      const width = 5.7 - index * 0.42;
      const z = -1.85 + index * 0.68;
      const bed = new THREE.Mesh(new THREE.BoxGeometry(width, 0.11, 0.46), new THREE.MeshStandardMaterial({ color, roughness: 0.9 }));
      bed.position.set(0, 0.01, z);
      field.add(bed);
      for (let row = -3; row <= 3; row += 1) {
        const cropRow = new THREE.Mesh(new THREE.BoxGeometry(0.055, 0.06, 0.34), new THREE.MeshStandardMaterial({ color: 0xb2c879, roughness: 1 }));
        cropRow.position.set(row * width / 7.6, 0.105, z);
        field.add(cropRow);
      }
    });

    const sun = new THREE.Mesh(new THREE.SphereGeometry(0.57, 28, 20), new THREE.MeshBasicMaterial({ color: 0xf0c16c }));
    sun.position.set(2.35, 2.7, -2.15);
    field.add(sun);

    const plant = new THREE.Group();
    plant.position.set(-0.15, 0.13, 0.8);
    field.add(plant);
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.07, 1.12, 12), new THREE.MeshStandardMaterial({ color: 0x4c763c }));
    stem.position.y = 0.55;
    plant.add(stem);
    const leafGeometry = new THREE.SphereGeometry(0.36, 22, 16);
    const greens = [0x4f8a43, 0x6c9d50, 0x39763d];
    [[-0.32,0.35,-0.72], [0.32,0.53,0.7], [-0.29,0.8,-0.65], [0.25,0.98,0.62], [0.02,1.18,0.08]].forEach(([x,y,angle], i) => {
      const leaf = new THREE.Mesh(leafGeometry, new THREE.MeshStandardMaterial({ color: greens[i % greens.length], roughness: 0.7 }));
      leaf.position.set(x, y, 0);
      leaf.scale.set(1.12, 0.34, 0.48);
      leaf.rotation.z = angle;
      plant.add(leaf);
    });

    const pointer = { x: 0, y: 0 };
    const move = (event) => {
      const rect = node.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      pointer.y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    };
    const leave = () => { pointer.x = 0; pointer.y = 0; };
    node.addEventListener("pointermove", move);
    node.addEventListener("pointerleave", leave);

    let frame = 0;
    let active = false;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const render = () => renderer.render(scene, camera);
    const animate = (time) => {
      if (!active) return;
      field.rotation.y += (pointer.x * 0.035 - field.rotation.y) * 0.035;
      field.rotation.x += (-0.08 + pointer.y * 0.014 - field.rotation.x) * 0.035;
      plant.rotation.z = Math.sin(time * 0.00055) * 0.022;
      render();
      frame = requestAnimationFrame(animate);
    };
    const setMotion = () => {
      cancelAnimationFrame(frame);
      active = !motion.matches;
      if (active) frame = requestAnimationFrame(animate);
      else render();
    };
    setMotion();
    motion.addEventListener?.("change", setMotion);

    const resize = () => {
      if (!node.clientWidth || !node.clientHeight) return;
      camera.aspect = node.clientWidth / node.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(node.clientWidth, node.clientHeight);
      if (!active) render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(node);
    return () => {
      active = false;
      cancelAnimationFrame(frame);
      motion.removeEventListener?.("change", setMotion);
      observer.disconnect();
      node.removeEventListener("pointermove", move);
      node.removeEventListener("pointerleave", leave);
      scene.traverse((object) => {
        object.geometry?.dispose();
        const materials = Array.isArray(object.material) ? object.material : object.material ? [object.material] : [];
        materials.forEach((material) => material.dispose());
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return <div ref={host} className="farm-scene" role="img" aria-label="A gently animated 3D illustration of a young crop growing above terraced green fields"><span className="scene-label"><i /> A healthier harvest starts here</span></div>;
}