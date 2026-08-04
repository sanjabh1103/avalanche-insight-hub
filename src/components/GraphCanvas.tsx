import { useEffect, useRef, useState, useCallback } from 'react';
import type { GraphNode, GraphEdge } from '../lib/graphLoader';

interface NodePosition {
  id: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
}

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick: (nodeId: string) => void;
  selectedNodeId: string | null;
}

const NODE_COLORS: Record<string, string> = {
  file: '#60a5fa',
  function: '#4ade80',
  class: '#a78bfa',
};

const NODE_RADIUS = 4;
const REPULSION = 800;
const SPRING_LENGTH = 40;
const SPRING_STRENGTH = 0.04;
const CENTERING = 0.003;
const DAMPING = 0.85;
const MAX_VELOCITY = 8;

export default function GraphCanvas({ nodes, edges, onNodeClick, selectedNodeId }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const positionsRef = useRef<Map<string, NodePosition>>(new Map());
  const transformRef = useRef({ x: 0, y: 0, scale: 1 });
  const dragRef = useRef<{ type: 'pan' | 'node' | null; nodeId?: string; lastX: number; lastY: number }>({
    type: null,
    lastX: 0,
    lastY: 0,
  });
  const animationRef = useRef<number>(0);
  const [isDragging, setIsDragging] = useState(false);

  // Initialize positions
  useEffect(() => {
    const positions = positionsRef.current;
    const existing = new Set(positions.keys());
    const current = new Set(nodes.map((n) => n.id));

    // Remove nodes that no longer exist
    for (const id of existing) {
      if (!current.has(id)) positions.delete(id);
    }

    // Add new nodes with random positions
    for (const node of nodes) {
      if (!positions.has(node.id)) {
        positions.set(node.id, {
          id: node.id,
          x: (Math.random() - 0.5) * 400,
          y: (Math.random() - 0.5) * 400,
          vx: 0,
          vy: 0,
        });
      }
    }
  }, [nodes]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const { width, height } = canvas;
    const transform = transformRef.current;
    const positions = positionsRef.current;

    ctx.clearRect(0, 0, width, height);
    ctx.save();
    ctx.translate(width / 2 + transform.x, height / 2 + transform.y);
    ctx.scale(transform.scale, transform.scale);

    // Draw edges
    ctx.strokeStyle = 'rgba(100, 116, 139, 0.15)';
    ctx.lineWidth = 0.5 / transform.scale;
    for (const edge of edges) {
      const src = positions.get(edge.source);
      const tgt = positions.get(edge.target);
      if (!src || !tgt) continue;
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.stroke();
    }

    // Draw nodes
    for (const node of nodes) {
      const pos = positions.get(node.id);
      if (!pos) continue;
      const color = NODE_COLORS[node.type] ?? '#94a3b8';
      const isSelected = node.id === selectedNodeId;
      const r = isSelected ? NODE_RADIUS * 1.8 : NODE_RADIUS;

      ctx.beginPath();
      ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      if (isSelected) {
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 2 / transform.scale;
        ctx.stroke();
      }
    }

    ctx.restore();
  }, [nodes, edges, selectedNodeId]);

  // Force simulation
  const simulate = useCallback(() => {
    const positions = positionsRef.current;
    const posArray = Array.from(positions.values());
    if (posArray.length === 0) return;

    // Build edge lookup
    const edgeSet = new Set<string>();
    for (const e of edges) {
      edgeSet.add(`${e.source}|${e.target}`);
    }

    // Repulsion (O(n²) — fine for up to ~2000 visible nodes)
    const maxNodes = Math.min(posArray.length, 2000);
    for (let i = 0; i < maxNodes; i++) {
      const a = posArray[i];
      for (let j = i + 1; j < maxNodes; j++) {
        const b = posArray[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distSq = dx * dx + dy * dy + 0.01;
        const dist = Math.sqrt(distSq);
        const force = REPULSION / distSq;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }

    // Spring attraction (edges)
    for (const edge of edges) {
      const src = positions.get(edge.source);
      const tgt = positions.get(edge.target);
      if (!src || !tgt) continue;
      const dx = tgt.x - src.x;
      const dy = tgt.y - src.y;
      const dist = Math.sqrt(dx * dx + dy * dy) + 0.01;
      const force = (dist - SPRING_LENGTH) * SPRING_STRENGTH;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      src.vx += fx;
      src.vy += fy;
      tgt.vx -= fx;
      tgt.vy -= fy;
    }

    // Centering + damping + velocity cap
    for (const pos of posArray) {
      pos.vx -= pos.x * CENTERING;
      pos.vy -= pos.y * CENTERING;
      pos.vx *= DAMPING;
      pos.vy *= DAMPING;
      const speed = Math.sqrt(pos.vx * pos.vx + pos.vy * pos.vy);
      if (speed > MAX_VELOCITY) {
        pos.vx = (pos.vx / speed) * MAX_VELOCITY;
        pos.vy = (pos.vy / speed) * MAX_VELOCITY;
      }
      // Don't move if being dragged
      if (dragRef.current.type === 'node' && dragRef.current.nodeId === pos.id) continue;
      pos.x += pos.vx;
      pos.y += pos.vy;
    }
  }, [edges]);

  // Animation loop
  useEffect(() => {
    const loop = () => {
      simulate();
      draw();
      animationRef.current = requestAnimationFrame(loop);
    };
    animationRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animationRef.current);
  }, [simulate, draw]);

  // Resize canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      canvas.width = parent.clientWidth;
      canvas.height = parent.clientHeight;
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(canvas.parentElement ?? canvas);
    return () => observer.disconnect();
  }, []);

  // Mouse interaction
  const getMousePos = (e: React.MouseEvent): { x: number; y: number } => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    return {
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };
  };

  const screenToWorld = (sx: number, sy: number): { x: number; y: number } => {
    const canvas = canvasRef.current;
    if (!canvas) return { x: 0, y: 0 };
    const transform = transformRef.current;
    return {
      x: (sx - canvas.width / 2 - transform.x) / transform.scale,
      y: (sy - canvas.height / 2 - transform.y) / transform.scale,
    };
  };

  const findNodeAt = (worldX: number, worldY: number): string | null => {
    const positions = positionsRef.current;
    for (const [id, pos] of positions) {
      const dx = pos.x - worldX;
      const dy = pos.y - worldY;
      if (dx * dx + dy * dy < (NODE_RADIUS * 2) ** 2) {
        return id;
      }
    }
    return null;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    const mouse = getMousePos(e);
    const world = screenToWorld(mouse.x, mouse.y);
    const nodeId = findNodeAt(world.x, world.y);
    if (nodeId) {
      dragRef.current = { type: 'node', nodeId, lastX: mouse.x, lastY: mouse.y };
      onNodeClick(nodeId);
    } else {
      dragRef.current = { type: 'pan', lastX: mouse.x, lastY: mouse.y };
    }
    setIsDragging(true);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    const mouse = getMousePos(e);
    const drag = dragRef.current;
    const dx = mouse.x - drag.lastX;
    const dy = mouse.y - drag.lastY;

    if (drag.type === 'pan') {
      transformRef.current.x += dx;
      transformRef.current.y += dy;
    } else if (drag.type === 'node' && drag.nodeId) {
      const pos = positionsRef.current.get(drag.nodeId);
      if (pos) {
        pos.x += dx / transformRef.current.scale;
        pos.y += dy / transformRef.current.scale;
        pos.vx = 0;
        pos.vy = 0;
      }
    }
    drag.lastX = mouse.x;
    drag.lastY = mouse.y;
  };

  const handleMouseUp = () => {
    dragRef.current = { type: null, lastX: 0, lastY: 0 };
    setIsDragging(false);
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.1, Math.min(5, transformRef.current.scale * delta));
    transformRef.current.scale = newScale;
  };

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height: '100%', cursor: isDragging ? 'grabbing' : 'grab' }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
    />
  );
}
