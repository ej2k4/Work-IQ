/**
 * Agent Studio – Interactive Knowledge Graph & Study Engine
 * 100% Offline Canvas Force-Directed Simulation and Web UI Logic
 */
// ── State ───────────────────────────────────────────────────────────────────
const state = {
  activeTab: 'graph',
  nodes: [],
  edges: [],
  nodeMap: new Map(),
  degreeMap: new Map(),
  adjacencyMap: new Map(),
  selectedNode: null,
  hoveredNode: null,
  focusedNeighbors: new Set(),
  searchQuery: '',
  activeFilter: 'all',
  activeTopic: null,
  activeCategory: null,
  categories: {},
  topics: {},
  
  // Camera & Canvas
  transform: { x: 0, y: 0, scale: 1 },
  targetTransform: null,
  isDraggingCanvas: false,
  dragStart: { x: 0, y: 0 },
  draggedNode: null,
  
  // Simulation Physics & Dashboard
  layoutType: 'force',
  alpha: 1.0,
  alphaMin: 0.003,
  alphaDecay: 0.022,
  isPaused: false,
  isSettled: false,
  physicsParams: {
    repulsion: 1400,
    springLen: 80,
    gravity: 0.0008,
    labelMode: 'smart',
    sizeMode: 'degree',
  },
  
  stats: {},
};

// ── DOM Elements ────────────────────────────────────────────────────────────
const canvas = document.getElementById('graph-canvas');
const ctx = canvas.getContext('2d');
const noteDrawer = document.getElementById('note-drawer');
const drawerNoteName = document.getElementById('drawer-note-name');
const drawerContent = document.getElementById('drawer-content');
const closeDrawerBtn = document.getElementById('close-drawer');
const searchInput = document.getElementById('graph-search');

// ── Color Palette & Distinct Categorization System ──────────────────────────
const CATEGORY_COLORS = {
  task: { fill: '#f43f5e', glow: 'rgba(244, 63, 94, 0.65)', stroke: '#fb7185', label: 'Agent Tasks' },
  code_file: { fill: '#3b82f6', glow: 'rgba(59, 130, 246, 0.65)', stroke: '#60a5fa', label: 'Python Files' },
  code_class: { fill: '#ec4899', glow: 'rgba(236, 72, 153, 0.65)', stroke: '#f472b6', label: 'Classes' },
  code_function: { fill: '#a855f7', glow: 'rgba(168, 85, 247, 0.55)', stroke: '#c084fc', label: 'Functions' },
  code_module: { fill: '#64748b', glow: 'rgba(100, 116, 139, 0.45)', stroke: '#94a3b8', label: 'Imports' },
  tag: { fill: '#eab308', glow: 'rgba(234, 179, 8, 0.65)', stroke: '#fde047', label: 'Tags' },
  curriculum: { fill: '#6366f1', glow: 'rgba(99, 102, 241, 0.75)', stroke: '#818cf8', label: 'Curriculum Index' },
  workspace_project: { fill: '#00f2fe', glow: 'rgba(0, 242, 254, 0.75)', stroke: '#38bdf8', label: 'Workspace Projects' },
  workspace_file: { fill: '#14b8a6', glow: 'rgba(20, 184, 166, 0.7)', stroke: '#2dd4bf', label: 'Workspace Files' },
  concept: { fill: '#8b5cf6', glow: 'rgba(139, 92, 246, 0.45)', stroke: '#a78bfa', label: 'Concepts' },
  default: { fill: '#64748b', glow: 'rgba(100, 116, 139, 0.4)', stroke: '#94a3b8', label: 'Other' },
};

// Vibrant signatures for known educational curricula
const KNOWN_TOPIC_COLORS = {
  'data_structures': { fill: '#10b981', glow: 'rgba(16, 185, 129, 0.65)', stroke: '#34d399', label: 'Data Structures' },
  'neural_networks_and_backpropagation': { fill: '#06b6d4', glow: 'rgba(6, 182, 212, 0.65)', stroke: '#38bdf8', label: 'Neural Networks' },
  'mathematics_for_machine_learning': { fill: '#f59e0b', glow: 'rgba(245, 158, 11, 0.65)', stroke: '#fbbf24', label: 'Math for ML' },
};

function getTopicColor(topicName) {
  if (!topicName) return CATEGORY_COLORS.default;
  const key = topicName.toLowerCase().replace(/[^a-z0-9]/g, '_');
  for (const [k, c] of Object.entries(KNOWN_TOPIC_COLORS)) {
    if (key.includes(k) || k.includes(key)) return c;
  }
  let hash = 0;
  for (let i = 0; i < topicName.length; i++) {
    hash = topicName.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  return {
    fill: `hsl(${hue}, 80%, 55%)`,
    glow: `hsla(${hue}, 80%, 55%, 0.65)`,
    stroke: `hsl(${hue}, 90%, 75%)`,
    label: topicName.replace(/_/g, ' '),
  };
}

function getNodeColor(node) {
  if (node.is_curriculum) return CATEGORY_COLORS.curriculum;
  if (node.topic) return getTopicColor(node.topic);
  if (node.category && CATEGORY_COLORS[node.category]) return CATEGORY_COLORS[node.category];
  return CATEGORY_COLORS.default;
}

// ── Canvas Setup & Resizing ─────────────────────────────────────────────────
function resizeCanvas() {
  const parent = canvas.parentElement;
  if (!parent) return;
  canvas.width = parent.clientWidth * window.devicePixelRatio;
  canvas.height = parent.clientHeight * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
}
window.addEventListener('resize', resizeCanvas);

// ── Graph Network Topology & Degree Precomputation ──────────────────────────
function computeTopology() {
  state.degreeMap.clear();
  state.adjacencyMap.clear();

  state.nodes.forEach(n => {
    state.degreeMap.set(n.id, 0);
    state.adjacencyMap.set(n.id, new Set());
  });

  state.edges.forEach(e => {
    state.degreeMap.set(e.source, (state.degreeMap.get(e.source) || 0) + 1);
    state.degreeMap.set(e.target, (state.degreeMap.get(e.target) || 0) + 1);
    
    if (state.adjacencyMap.has(e.source)) state.adjacencyMap.get(e.source).add(e.target);
    if (state.adjacencyMap.has(e.target)) state.adjacencyMap.get(e.target).add(e.source);
  });

  // Calculate dynamic radius for each node
  state.nodes.forEach(n => {
    const deg = state.degreeMap.get(n.id) || 0;
    n.degree = deg;
    const isMajor = n.name.includes('Curriculum') || n.name.includes('INDEX') || n.name.startsWith('task-');
    if (state.physicsParams.sizeMode === 'degree') {
      n.radius = Math.min(22, Math.max(6, Math.sqrt(deg) * 3.4 + 5));
      if (isMajor && n.radius < 13) n.radius = 13;
    } else {
      n.radius = isMajor ? 13 : 8;
    }
  });

  // Update Telemetry HUD metrics
  const avgDegree = state.nodes.length > 0 ? ((state.edges.length * 2) / state.nodes.length).toFixed(1) : 0;
  const nodesEl = document.getElementById('graph-metric-nodes');
  const edgesEl = document.getElementById('graph-metric-edges');
  const densityEl = document.getElementById('graph-metric-density');
  if (nodesEl) nodesEl.textContent = state.nodes.length;
  if (edgesEl) edgesEl.textContent = state.edges.length;
  if (densityEl) densityEl.textContent = avgDegree;

  renderKeyHubs();
}

function renderKeyHubs() {
  const container = document.getElementById('graph-hubs-chips');
  if (!container) return;

  const sorted = [...state.nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0));
  const topHubs = sorted.slice(0, 7);

  if (topHubs.length === 0) {
    container.innerHTML = '<span class="hub-chip-loading">No hub nodes found</span>';
    return;
  }

  container.innerHTML = topHubs.map(hub => {
    const displayName = hub.name.replace(/_/g, ' ');
    const colors = getNodeColor(hub);
    const chipId = `hub-chip-${hub.name.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
    return `
      <div class="hub-chip" id="${chipId}" onclick="focusOnHub('${hub.id}')" title="Focus on ${escapeHtml(displayName)} (${hub.degree} connections)">
        <span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:${colors.fill};"></span>
        <span>${escapeHtml(displayName)}</span>
        <span class="hub-badge">${hub.degree}</span>
      </div>
    `;
  }).join('');
}

window.focusOnHub = (nodeId) => {
  const node = state.nodeMap.get(nodeId) ||
               state.nodeMap.get(String(nodeId)) ||
               state.nodeMap.get(Number(nodeId)) ||
               state.nodes.find(n => n.id == nodeId || n.name.toLowerCase() === String(nodeId).toLowerCase());
  if (!node) return;

  const width = canvas.width / window.devicePixelRatio;
  const height = canvas.height / window.devicePixelRatio;
  const targetScale = 1.35;
  state.targetTransform = {
    x: width / 2 - node.x * targetScale,
    y: height / 2 - node.y * targetScale,
    scale: targetScale,
  };

  state.hoveredNode = node;
  state.focusedNeighbors = state.adjacencyMap.get(node.id) || new Set();
  openNodeDetails(node);
};

// ── Graph Layout Engines (Phyllotaxis, Concentric Radial, Category Orbits) ───
function applyLayout(layoutType) {
  state.layoutType = layoutType;
  const total = state.nodes.length;
  if (total === 0) return;

  if (layoutType === 'radial') {
    // Concentric rings based on node degree (Hubs in center, leaves outside)
    state.nodes.forEach(node => {
      const deg = node.degree || 0;
      let r = 440;
      if (deg >= 8) r = 110;
      else if (deg >= 3) r = 260;

      const angle = Math.random() * Math.PI * 2;
      node.x = Math.cos(angle) * r + (Math.random() - 0.5) * 30;
      node.y = Math.sin(angle) * r + (Math.random() - 0.5) * 30;
      node.vx = 0;
      node.vy = 0;
    });

  } else if (layoutType === 'category') {
    // Group nodes into distinct, well-spaced planetary clusters
    const topicCenters = {
      'data_structures': { x: -380, y: -220 },
      'neural_networks_and_backpropagation': { x: 380, y: -220 },
      'mathematics_for_machine_learning': { x: 0, y: -450 },
    };
    const catCenters = {
      curriculum: { x: 0, y: -80 },
      task: { x: -380, y: 240 },
      code_file: { x: 0, y: 320 },
      code_class: { x: 260, y: 160 },
      code_function: { x: 380, y: 280 },
      code_module: { x: 180, y: 440 },
      tag: { x: -160, y: 440 },
      concept: { x: 0, y: 120 },
    };

    state.nodes.forEach(node => {
      let c = null;
      if (node.topic) {
        const tKey = node.topic.toLowerCase().replace(/[^a-z0-9]/g, '_');
        c = topicCenters[tKey];
      }
      if (!c && node.is_curriculum) c = catCenters.curriculum;
      if (!c && node.category && catCenters[node.category]) c = catCenters[node.category];
      if (!c) c = catCenters.concept;

      const angle = Math.random() * Math.PI * 2;
      const r = Math.random() * 110 + 20;
      node.x = c.x + Math.cos(angle) * r;
      node.y = c.y + Math.sin(angle) * r;
      node.vx = 0;
      node.vy = 0;
    });

  } else {
    // Default Organic Force layout with Golden Spiral (Phyllotaxis) initialization
    // Guaranteed ZERO starting collisions!
    const goldenAngle = 137.507764 * (Math.PI / 180);
    // Sort hubs toward center
    const sorted = [...state.nodes].sort((a, b) => (b.degree || 0) - (a.degree || 0));
    sorted.forEach((node, i) => {
      const r = 26 * Math.sqrt(i + 1);
      const theta = i * goldenAngle;
      node.x = r * Math.cos(theta);
      node.y = r * Math.sin(theta);
      node.vx = 0;
      node.vy = 0;
    });
  }

  // Heat up simulation gently to let it settle into place
  reheatSimulation(0.85);
  setTimeout(() => zoomToFit(true), 150);
}

// ── Force-Directed Physics Engine with Soft-Core Repulsion & Settle Cooling ──
function reheatSimulation(energy = 0.65) {
  state.alpha = Math.max(state.alpha, energy);
  state.isPaused = false;
  state.isSettled = false;
  updateSimBadge();
}

function updateSimBadge() {
  const badge = document.getElementById('graph-sim-badge');
  const text = document.getElementById('sim-status-text');
  const toggleIcon = document.getElementById('sim-toggle-icon');
  const toggleLabel = document.getElementById('sim-toggle-label');

  if (!badge || !text) return;

  if (state.isPaused) {
    badge.className = 'sim-status-badge paused';
    text.textContent = 'Paused';
    if (toggleIcon) toggleIcon.textContent = '▶';
    if (toggleLabel) toggleLabel.textContent = 'Resume';
  } else if (state.isSettled || state.alpha <= state.alphaMin) {
    badge.className = 'sim-status-badge settled';
    text.textContent = 'Settled';
    if (toggleIcon) toggleIcon.textContent = '⏸';
    if (toggleLabel) toggleLabel.textContent = 'Freeze';
  } else {
    badge.className = 'sim-status-badge simulating';
    const pct = Math.min(100, Math.round(state.alpha * 100));
    text.textContent = `Relaxing (${pct}%)`;
    if (toggleIcon) toggleIcon.textContent = '⏸';
    if (toggleLabel) toggleLabel.textContent = 'Freeze';
  }
}

function updatePhysics() {
  if (state.isPaused) return;

  // Once cooled below threshold, graph settles completely static! Zero random movement!
  if (state.alpha <= state.alphaMin) {
    if (!state.isSettled) {
      state.alpha = 0;
      state.isSettled = true;
      updateSimBadge();
    }
    return;
  }

  const kRepulsion = state.physicsParams.repulsion;
  const kSpring = 0.045;
  const defaultSpringLen = state.physicsParams.springLen;
  const kGravity = state.physicsParams.gravity;

  // 1. Softened N-Body Repulsion (softening constant +2500 eliminates near-zero collision explosions)
  for (let i = 0; i < state.nodes.length; i++) {
    const na = state.nodes[i];
    for (let j = i + 1; j < state.nodes.length; j++) {
      const nb = state.nodes[j];
      const dx = nb.x - na.x;
      const dy = nb.y - na.y;
      const distSq = dx * dx + dy * dy || 1;

      const force = (kRepulsion * state.alpha) / (distSq + 2500);
      const dist = Math.sqrt(distSq);
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      na.vx -= fx;
      na.vy -= fy;
      nb.vx += fx;
      nb.vy += fy;

      // Soft-body collision cushion prevents overlapping bubbles
      const minDist = na.radius + nb.radius + 10;
      if (dist < minDist) {
        const overlap = (minDist - dist);
        const push = overlap * 0.16 * state.alpha;
        const px = (dx / dist) * push;
        const py = (dy / dist) * push;
        na.vx -= px;
        na.vy -= py;
        nb.vx += px;
        nb.vy += py;
      }
    }
  }

  // 2. Spring attraction along relational edges
  for (const edge of state.edges) {
    const na = state.nodeMap.get(edge.source);
    const nb = state.nodeMap.get(edge.target);
    if (!na || !nb) continue;

    const dx = nb.x - na.x;
    const dy = nb.y - na.y;
    const dist = Math.sqrt(dx * dx + dy * dy) || 1;
    const targetLen = (na.degree > 6 || nb.degree > 6) ? defaultSpringLen * 1.35 : defaultSpringLen;
    const force = (dist - targetLen) * kSpring * state.alpha;

    const fx = (dx / dist) * force;
    const fy = (dy / dist) * force;
    na.vx += fx;
    na.vy += fy;
    nb.vx -= fx;
    nb.vy -= fy;
  }

  // 3. Centering gravity, velocity damping, and maximum speed clamping
  const damping = 0.72 + (1 - state.alpha) * 0.22;
  const maxVel = 10 * state.alpha + 0.4;

  for (const node of state.nodes) {
    node.vx -= node.x * kGravity * state.alpha;
    node.vy -= node.y * kGravity * state.alpha;

    // Hard velocity clamp to stop random jumping
    const speed = Math.hypot(node.vx, node.vy);
    if (speed > maxVel) {
      node.vx = (node.vx / speed) * maxVel;
      node.vy = (node.vy / speed) * maxVel;
    }

    if (node !== state.draggedNode) {
      node.vx *= damping;
      node.vy *= damping;
      node.x += node.vx;
      node.y += node.vy;
    }
  }

  // Energy cooling decay
  state.alpha += (0 - state.alpha) * state.alphaDecay;
  updateSimBadge();
}

// ── Auto-Fit Entire Graph in Viewport ───────────────────────────────────────
function zoomToFit(animated = true) {
  if (state.nodes.length === 0) return;

  const width = canvas.width / window.devicePixelRatio;
  const height = canvas.height / window.devicePixelRatio;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of state.nodes) {
    if (n.x < minX) minX = n.x;
    if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.y > maxY) maxY = n.y;
  }

  const graphW = (maxX - minX) || 400;
  const graphH = (maxY - minY) || 400;
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;

  // Account for header & toolbar margins
  const availW = Math.max(300, width - 120);
  const availH = Math.max(300, height - 160);

  const scale = Math.min(availW / graphW, availH / graphH, 1.25);
  const target = {
    x: width / 2 - centerX * scale,
    y: height / 2 - centerY * scale + 15,
    scale: Math.max(0.25, Math.min(2.0, scale)),
  };

  if (animated) {
    state.targetTransform = target;
  } else {
    state.transform = { ...target };
    state.targetTransform = null;
  }
}

// ── Zoom & Frame Subsets of Nodes ───────────────────────────────────────────
function zoomToNodes(nodes, animated = true) {
  if (!nodes || nodes.length === 0) return;
  const width = canvas.width / window.devicePixelRatio;
  const height = canvas.height / window.devicePixelRatio;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of nodes) {
    if (n.x < minX) minX = n.x;
    if (n.x > maxX) maxX = n.x;
    if (n.y < minY) minY = n.y;
    if (n.y > maxY) maxY = n.y;
  }

  const spanW = Math.max(120, maxX - minX);
  const spanH = Math.max(120, maxY - minY);
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;

  const availW = Math.max(260, width - 200);
  const availH = Math.max(260, height - 200);

  const scale = Math.min(availW / spanW, availH / spanH, 1.4);
  const target = {
    x: width / 2 - centerX * scale,
    y: height / 2 - centerY * scale,
    scale: Math.max(0.4, Math.min(1.5, scale)),
  };

  if (animated) {
    state.targetTransform = target;
  } else {
    state.transform = { ...target };
    state.targetTransform = null;
  }
}

// ── Canvas Rendering Engine (Neighborhood Highlighting & Smart Labels) ──────
function renderGraph() {
  const width = canvas.width / window.devicePixelRatio;
  const height = canvas.height / window.devicePixelRatio;

  // Smooth camera interpolation
  if (state.targetTransform) {
    state.transform.x += (state.targetTransform.x - state.transform.x) * 0.14;
    state.transform.y += (state.targetTransform.y - state.transform.y) * 0.14;
    state.transform.scale += (state.targetTransform.scale - state.transform.scale) * 0.14;
    if (
      Math.abs(state.targetTransform.x - state.transform.x) < 0.5 &&
      Math.abs(state.targetTransform.y - state.transform.y) < 0.5 &&
      Math.abs(state.targetTransform.scale - state.transform.scale) < 0.005
    ) {
      state.transform = { ...state.targetTransform };
      state.targetTransform = null;
    }
  }

  ctx.clearRect(0, 0, width, height);
  ctx.save();
  ctx.translate(state.transform.x, state.transform.y);
  ctx.scale(state.transform.scale, state.transform.scale);

  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  const hasHover = !!state.hoveredNode;
  const isTopicActive = !!state.activeTopic;
  const topicColorObj = isTopicActive ? getTopicColor(state.activeTopic) : null;

  // 1. Draw Edges with Neighborhood & Topic Focus
  for (const edge of state.edges) {
    const na = state.nodeMap.get(edge.source);
    const nb = state.nodeMap.get(edge.target);
    if (!na || !nb) continue;

    const isConnected = hasHover && (na === state.hoveredNode || nb === state.hoveredNode);
    const bothInTopic = isTopicActive && passesFilter(na) && passesFilter(nb);

    ctx.beginPath();
    ctx.moveTo(na.x, na.y);
    ctx.lineTo(nb.x, nb.y);

    if (isConnected) {
      ctx.strokeStyle = isLight ? '#0284c7' : '#38bdf8';
      ctx.lineWidth = 2.4;
    } else if (bothInTopic) {
      ctx.strokeStyle = topicColorObj.stroke;
      ctx.lineWidth = 2.2;
    } else if (isTopicActive) {
      ctx.strokeStyle = isLight ? 'rgba(100, 116, 139, 0.04)' : 'rgba(255, 255, 255, 0.02)';
      ctx.lineWidth = 0.6;
    } else if (hasHover) {
      ctx.strokeStyle = isLight ? 'rgba(100, 116, 139, 0.08)' : 'rgba(255, 255, 255, 0.04)';
      ctx.lineWidth = 0.8;
    } else {
      ctx.strokeStyle = isLight ? 'rgba(100, 116, 139, 0.35)' : 'rgba(255, 255, 255, 0.12)';
      ctx.lineWidth = 1.0;
    }
    ctx.stroke();
  }

  // 2. Draw Nodes
  for (const node of state.nodes) {
    const isFiltered = passesFilter(node);
    const isSearched = !state.searchQuery || node.name.toLowerCase().includes(state.searchQuery);
    const isHovered = node === state.hoveredNode;
    const isNeighbor = hasHover && state.focusedNeighbors.has(node.id);

    let opacity = 1.0;
    if (isTopicActive) {
      opacity = isFiltered ? 1.0 : (isLight ? 0.08 : 0.05);
    } else if (!isFiltered || !isSearched) {
      opacity = isLight ? 0.15 : 0.08;
    } else if (hasHover) {
      opacity = (isHovered || isNeighbor) ? 1.0 : (isLight ? 0.18 : 0.12);
    }

    const colors = getNodeColor(node);

    ctx.save();
    ctx.globalAlpha = opacity;

    // Glowing Halo on hover, search match, or active topic match
    if (isHovered || (state.searchQuery && isSearched) || (isTopicActive && isFiltered)) {
      ctx.beginPath();
      const haloRadius = (isTopicActive && isFiltered) ? node.radius + 9 : node.radius + 8;
      ctx.arc(node.x, node.y, haloRadius, 0, Math.PI * 2);
      ctx.fillStyle = colors.glow;
      ctx.fill();
    }

    // Node Body
    ctx.beginPath();
    ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
    ctx.fillStyle = colors.fill;
    ctx.fill();
    ctx.lineWidth = (isHovered || (isTopicActive && isFiltered)) ? 2.5 : 1.8;
    ctx.strokeStyle = (isHovered || (isTopicActive && isFiltered)) ? '#ffffff' : colors.stroke;
    ctx.stroke();

    // Smart Label Visibility: eliminates visual noise
    let showLabel = false;
    const mode = state.physicsParams.labelMode;
    if (isTopicActive) {
      showLabel = isFiltered;
    } else if (mode === 'all') {
      showLabel = true;
    } else if (mode === 'hover') {
      showLabel = isHovered || isNeighbor || (state.searchQuery && isSearched);
    } else {
      // 'smart' mode: show for hubs, major topics, hovered, neighbors, or search match
      showLabel = isHovered || isNeighbor || (state.searchQuery && isSearched) ||
                  (node.degree >= 3) ||
                  node.name.includes('Curriculum') || node.name.startsWith('task-');
    }

    if (showLabel && isFiltered && opacity > 0.3) {
      const fontSize = node.radius >= 14 ? 11 : 9.5;
      ctx.font = `600 ${fontSize}px Outfit, sans-serif`;
      ctx.fillStyle = isLight ? '#0f172a' : '#f8fafc';
      ctx.textAlign = 'center';
      ctx.fillText(node.name.replace(/_/g, ' '), node.x, node.y + node.radius + 13);
    }

    ctx.restore();
  }

  ctx.restore();
}

function passesFilter(node) {
  if (state.activeTopic) {
    const tRaw = state.activeTopic.toLowerCase();
    const tClean = tRaw.replace(/_/g, ' ');
    const nTopic = (node.topic || '').toLowerCase();
    const nRef = (node.ref || '').toLowerCase();
    const nName = (node.name || '').toLowerCase();
    return nTopic === tRaw || nRef.includes(tRaw) || nRef.includes(tClean) ||
           (node.is_curriculum && (nName.includes(tRaw) || nRef.includes(tRaw)));
  }

  if (state.activeFilter === 'all') return true;
  if (state.activeFilter === 'workspace') return ['workspace_project', 'workspace_file'].includes(node.category) || (node.ref && node.ref.startsWith('workspace:'));
  if (state.activeFilter === 'education') return node.category === 'education' || !!node.topic || node.is_curriculum;
  if (state.activeFilter === 'task') return node.category === 'task';
  if (state.activeFilter === 'code') return ['code_file', 'code_class', 'code_function', 'code_module'].includes(node.category);
  if (state.activeFilter) return node.category === state.activeFilter;
  return true;
}

// ── Animation Loop ──────────────────────────────────────────────────────────
function animationLoop() {
  if (state.activeTab === 'graph') {
    updatePhysics();
    renderGraph();
  }
  requestAnimationFrame(animationLoop);
}

// ── Mouse & Touch Event Handlers ────────────────────────────────────────────
function screenToWorld(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const x = clientX - rect.left;
  const y = clientY - rect.top;
  return {
    x: (x - state.transform.x) / state.transform.scale,
    y: (y - state.transform.y) / state.transform.scale,
  };
}

function findNodeAt(worldX, worldY) {
  for (let i = state.nodes.length - 1; i >= 0; i--) {
    const node = state.nodes[i];
    const dx = worldX - node.x;
    const dy = worldY - node.y;
    if (dx * dx + dy * dy <= (node.radius + 5) * (node.radius + 5)) {
      return node;
    }
  }
  return null;
}

canvas.addEventListener('mousedown', (e) => {
  const pos = screenToWorld(e.clientX, e.clientY);
  const clicked = findNodeAt(pos.x, pos.y);

  state.mouseDownPos = { x: e.clientX, y: e.clientY };
  state.mouseDownNode = clicked;

  if (clicked) {
    state.draggedNode = clicked;
    reheatSimulation(0.25);
  } else {
    state.isDraggingCanvas = true;
    state.dragStart = { x: e.clientX - state.transform.x, y: e.clientY - state.transform.y };
  }
});

window.addEventListener('mousemove', (e) => {
  const pos = screenToWorld(e.clientX, e.clientY);
  const hovered = findNodeAt(pos.x, pos.y);
  
  if (hovered !== state.hoveredNode) {
    state.hoveredNode = hovered;
    state.focusedNeighbors = hovered ? (state.adjacencyMap.get(hovered.id) || new Set()) : new Set();
  }

  canvas.style.cursor = hovered ? 'pointer' : (state.isDraggingCanvas ? 'grabbing' : 'grab');

  if (state.draggedNode) {
    state.draggedNode.x = pos.x;
    state.draggedNode.y = pos.y;
    state.draggedNode.vx = 0;
    state.draggedNode.vy = 0;
  } else if (state.isDraggingCanvas) {
    state.transform.x = e.clientX - state.dragStart.x;
    state.transform.y = e.clientY - state.dragStart.y;
    state.targetTransform = null;
  }
});

window.addEventListener('mouseup', (e) => {
  if (state.mouseDownNode && state.mouseDownPos) {
    const dist = Math.hypot(e.clientX - state.mouseDownPos.x, e.clientY - state.mouseDownPos.y);
    if (dist < 8) {
      focusOnHub(state.mouseDownNode.id);
    }
  }
  state.mouseDownNode = null;
  state.mouseDownPos = null;
  state.draggedNode = null;
  state.isDraggingCanvas = false;
});

canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  state.targetTransform = null;
  const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
  const newScale = Math.max(0.2, Math.min(4.0, state.transform.scale * zoomFactor));

  const rect = canvas.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  state.transform.x = mouseX - (mouseX - state.transform.x) * (newScale / state.transform.scale);
  state.transform.y = mouseY - (mouseY - state.transform.y) * (newScale / state.transform.scale);
}, { passive: false });

// ── Node Inspector Slide Drawer ─────────────────────────────────────────────
const noteSourcePill = document.getElementById('note-source-pill');
const notePathText = document.getElementById('note-path-text');
const btnEditNote = document.getElementById('btn-edit-note');
const btnSaveNote = document.getElementById('btn-save-note');
const btnSynthNote = document.getElementById('btn-synth-note');
const drawerEditorWrap = document.getElementById('drawer-editor-wrap');
const drawerEditorTextarea = document.getElementById('drawer-editor-textarea');

state.currentNote = null;
state.isEditingNote = false;

async function openNodeDetails(node) {
  state.selectedNode = node;
  state.isEditingNote = false;

  if (drawerEditorWrap) drawerEditorWrap.style.display = 'none';
  if (drawerContent) drawerContent.style.display = 'block';
  if (btnEditNote) btnEditNote.textContent = '✏️ Edit';

  const rawName = node.name || 'Note';
  const displayName = rawName.replace(/_/g, ' ');
  drawerNoteName.textContent = displayName;

  if (noteSourcePill) {
    noteSourcePill.className = 'note-source-pill virtual';
    noteSourcePill.textContent = '⚡ Resolving...';
  }
  if (notePathText) notePathText.textContent = '';
  if (btnSaveNote) btnSaveNote.style.display = 'none';

  drawerContent.innerHTML = '<div style="color:var(--text-dim); padding:24px; text-align:center;"><span class="spinner"></span> Resolving note and documentation...</div>';
  noteDrawer.classList.add('open');

  try {
    const params = new URLSearchParams();
    if (node.id) params.set('id', node.id);
    if (node.name) params.set('name', node.name);
    if (node.kind) params.set('kind', node.kind);
    if (node.ref) params.set('ref', node.ref);

    const res = await fetch(`/api/note?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to resolve note');
    const data = await res.json();
    state.currentNote = data;

    drawerNoteName.textContent = (data.name ? data.name.replace(/\.md$/i, '') : displayName).replace(/_/g, ' ');

    // Source Pill Badge
    if (noteSourcePill) {
      if (data.in_vault) {
        noteSourcePill.className = 'note-source-pill in-vault';
        noteSourcePill.textContent = '📁 In Vault';
      } else if (data.source === 'workspace_project') {
        noteSourcePill.className = 'note-source-pill code';
        noteSourcePill.textContent = '📦 Workspace Project';
      } else if (data.source === 'workspace_file') {
        noteSourcePill.className = 'note-source-pill code';
        noteSourcePill.textContent = '💻 Workspace File';
      } else if (data.source === 'code') {
        noteSourcePill.className = 'note-source-pill code';
        noteSourcePill.textContent = '⚡ Code Definition';
      } else if (data.source === 'task') {
        noteSourcePill.className = 'note-source-pill task';
        noteSourcePill.textContent = '🤖 Task Note';
      } else {
        noteSourcePill.className = 'note-source-pill virtual';
        noteSourcePill.textContent = '🌐 Concept Note';
      }
    }

    if (notePathText) {
      notePathText.textContent = data.rel_path || '';
    }

    // Open in Code Studio button
    const btnOpenInCodeStudio = document.getElementById('btn-open-in-code-studio');
    if (btnOpenInCodeStudio) {
      if (data.workspace_info) {
        btnOpenInCodeStudio.style.display = 'inline-flex';
        btnOpenInCodeStudio.onclick = () => {
          noteDrawer.classList.remove('open');
          const codeNav = document.querySelector('[data-tab="code"]');
          if (codeNav) codeNav.click();
          if (window.openWorkspaceInStudio) {
            window.openWorkspaceInStudio(data.workspace_info.workspace, data.workspace_info.file_path);
          }
        };
      } else {
        btnOpenInCodeStudio.style.display = 'none';
      }
    }

    // Save to Vault button
    if (btnSaveNote) {
      if (data.in_vault) {
        btnSaveNote.style.display = 'none';
      } else {
        btnSaveNote.style.display = 'inline-flex';
        btnSaveNote.disabled = false;
        btnSaveNote.textContent = '💾 Save to Vault';
      }
    }

    if (drawerEditorTextarea) {
      drawerEditorTextarea.value = data.content || '';
    }

    drawerContent.innerHTML = renderMarkdown(data.content);

    // Render Linked Nodes in Drawer
    renderDrawerLinks(data.outgoing || [], data.incoming || [], data.node_id || node.id);

    const btnDrawerAddLink = document.getElementById('btn-drawer-add-link');
    if (btnDrawerAddLink) {
      btnDrawerAddLink.onclick = () => {
        openLinkModal({
          id: data.node_id || node.id,
          name: (data.name ? data.name.replace(/\.md$/i, '') : displayName).replace(/_/g, ' '),
          kind: data.kind || node.kind || 'concept',
          ref: node.ref || data.rel_path,
        });
      };
    }

    // AI Synthesize button in drawer footer
    if (btnSynthNote) {
      const isTask = data.source === 'task';
      const isWs = data.source === 'workspace_project' || data.source === 'workspace_file';
      btnSynthNote.style.display = (isTask || isWs) ? 'none' : 'block';
      btnSynthNote.textContent = `✨ Synthesize In-Depth Topic Note: "${displayName}"`;
    }

  } catch (err) {
    drawerContent.innerHTML = `
      <div style="background:rgba(244,63,94,0.1); border:1px solid rgba(244,63,94,0.3); padding:16px; border-radius:10px; color:#fca5a5;">
        <strong>Error loading note</strong>
        <p style="margin-top:8px; font-size:0.85rem;">${escapeHtml(err.message)}</p>
      </div>
    `;
  }
}

closeDrawerBtn.addEventListener('click', () => {
  noteDrawer.classList.remove('open');
});

// Toggle Edit / Markdown Preview
if (btnEditNote) {
  btnEditNote.addEventListener('click', () => {
    state.isEditingNote = !state.isEditingNote;
    if (state.isEditingNote) {
      btnEditNote.textContent = '👁️ Preview';
      drawerContent.style.display = 'none';
      drawerEditorWrap.style.display = 'block';
      if (drawerEditorTextarea) {
        drawerEditorTextarea.focus();
      }
    } else {
      btnEditNote.textContent = '✏️ Edit';
      if (state.currentNote && drawerEditorTextarea) {
        state.currentNote.content = drawerEditorTextarea.value;
        drawerContent.innerHTML = renderMarkdown(drawerEditorTextarea.value);
      }
      drawerEditorWrap.style.display = 'none';
      drawerContent.style.display = 'block';
    }
  });
}

// Save Current Note to Obsidian Vault
if (btnSaveNote) {
  btnSaveNote.addEventListener('click', async () => {
    if (!state.currentNote) return;
    const content = drawerEditorTextarea ? drawerEditorTextarea.value : state.currentNote.content;
    const rel_path = state.currentNote.rel_path;
    if (!rel_path) return;

    btnSaveNote.disabled = true;
    btnSaveNote.innerHTML = '<span class="spinner"></span> Saving...';

    try {
      const res = await fetch('/api/note/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rel_path, content }),
      });
      const data = await res.json();
      if (data.success) {
        state.currentNote.in_vault = true;
        if (noteSourcePill) {
          noteSourcePill.className = 'note-source-pill in-vault';
          noteSourcePill.textContent = '📁 In Vault';
        }
        btnSaveNote.textContent = '✅ Saved to Vault!';
        setTimeout(() => {
          btnSaveNote.style.display = 'none';
        }, 1800);
        await loadStats();
      } else {
        alert('Save failed: ' + (data.error || 'Unknown error'));
        btnSaveNote.disabled = false;
        btnSaveNote.textContent = '💾 Save to Vault';
      }
    } catch (e) {
      alert('Save error: ' + e.message);
      btnSaveNote.disabled = false;
      btnSaveNote.textContent = '💾 Save to Vault';
    }
  });
}

// Synthesize In-Depth Topic Note with AI
if (btnSynthNote) {
  btnSynthNote.addEventListener('click', async () => {
    if (!state.selectedNode) return;
    const topic = state.selectedNode.name;
    btnSynthNote.disabled = true;
    btnSynthNote.innerHTML = '<span class="spinner"></span> Synthesizing curriculum in vault...';

    try {
      const res = await fetch('/api/note/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic }),
      });
      const data = await res.json();
      if (data.success) {
        await loadGraphData();
        await loadStats();
        if (data.note) {
          state.currentNote = data.note;
          drawerContent.innerHTML = renderMarkdown(data.note.content);
          if (drawerEditorTextarea) drawerEditorTextarea.value = data.note.content;
          if (noteSourcePill) {
            noteSourcePill.className = 'note-source-pill in-vault';
            noteSourcePill.textContent = '📁 In Vault';
          }
          if (notePathText) notePathText.textContent = data.note.rel_path || '';
          if (btnSaveNote) btnSaveNote.style.display = 'none';
        }
      } else {
        alert('Synthesis failed: ' + (data.error || 'Unknown error'));
      }
    } catch (e) {
      alert('Synthesis error: ' + e.message);
    } finally {
      btnSynthNote.disabled = false;
      btnSynthNote.textContent = '✨ Synthesize In-Depth Topic Note with AI';
    }
  });
}

// Simple Client Markdown Renderer
function renderMarkdown(md) {
  if (!md) return '<p>No content.</p>';

  let html = md
    // Strip YAML frontmatter
    .replace(/^---[\s\S]*?---\n*/, '')
    // Headers
    .replace(/^#### (.*$)/gim, '<h4>$1</h4>')
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    // Alerts / Callouts
    .replace(/> \[!(TIP|NOTE|WARNING|IMPORTANT)\] (.*)/gim, '<div style="background:rgba(99,102,241,0.12); border-left:3px solid var(--accent-primary); padding:12px; border-radius:6px; margin:14px 0;"><strong>$1:</strong> $2</div>')
    .replace(/^> (.*$)/gim, '<blockquote style="border-left:3px solid var(--accent-cyan); padding-left:12px; color:var(--text-muted);">$1</blockquote>')
    // Code blocks with syntax
    .replace(/```(python|py)([\s\S]*?)```/gim, '<pre><code class="python">$2</code></pre>')
    .replace(/```(json|text|bash|sh|md)?([\s\S]*?)```/gim, '<pre><code>$2</code></pre>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Bold & italic
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // Wikilinks [[Target|Alias]] or [[Target]]
    .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (match, target, alias) => {
      const label = alias || target;
      const cleanTarget = target.trim().replace(/'/g, "\\'");
      return `<a class="wikilink" onclick="openNodeByName('${cleanTarget}')">${label}</a>`;
    })
    // Lists
    .replace(/^\- (.*$)/gim, '<li>$1</li>')
    // Paragraphs
    .replace(/\n\n/g, '</p><p>');

  return `<p>${html}</p>`;
}

window.openNodeByName = (name) => {
  if (!name) return;
  const clean = name.trim().toLowerCase();
  const match = state.nodes.find(n => n.name.toLowerCase() === clean) ||
                state.nodes.find(n => n.name.toLowerCase().replace(/_/g, ' ') === clean.replace(/_/g, ' ')) ||
                state.nodes.find(n => n.name.toLowerCase().includes(clean));
  if (match) {
    focusOnHub(match.id);
  } else {
    openNodeDetails({ name });
  }
};

// ── API Calls & Data Loading ────────────────────────────────────────────────
async function loadGraphData() {
  try {
    const res = await fetch('/api/graph');
    const data = await res.json();
    state.nodes = data.nodes || [];
    state.edges = data.edges || [];
    state.categories = data.categories || {};
    state.topics = data.topics || {};
    state.nodeMap.clear();
    state.nodes.forEach(n => state.nodeMap.set(n.id, n));
    computeTopology();
    applyLayout(state.layoutType || 'force');
    renderLegendUI();
    setTimeout(() => zoomToFit(false), 60);
  } catch (err) {
    console.error('Failed to load graph:', err);
  }
}

async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    state.stats = data;

    document.getElementById('stat-nodes').textContent = data.nodes_count || 0;
    document.getElementById('stat-edges').textContent = data.edges_count || 0;
    document.getElementById('stat-notes').textContent = data.notes_count || 0;
    document.getElementById('stat-tasks').textContent = data.tasks_count || 0;
    const statWs = document.getElementById('stat-workspaces');
    if (statWs) statWs.textContent = data.workspaces_count || 0;
    document.getElementById('sidebar-vault-path').textContent = data.vault_path || 'Not Configured';

    // Populate topics grid
    const grid = document.getElementById('existing-topics-grid');
    if (grid && data.topics) {
      grid.innerHTML = data.topics.map(t => {
        const cleanName = t.replace(/_/g, ' ');
        return `
        <div class="topic-card" onclick="openTopicGraph('${escapeHtml(t)}')" title="Explore ${escapeHtml(cleanName)}">
          <div class="topic-card-title" title="${escapeHtml(cleanName)}">${escapeHtml(cleanName)}</div>
          <div class="topic-card-folder" title="Education/${escapeHtml(t)}">📁 Education/${escapeHtml(t)}</div>
        </div>
      `;
      }).join('');
    }
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ── Theme Management ────────────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem('agent_theme') || 'dark';
  setTheme(saved);

  const toggleBtn = document.getElementById('btn-theme-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const isCurrentlyLight = document.documentElement.getAttribute('data-theme') === 'light';
      setTheme(isCurrentlyLight ? 'dark' : 'light');
    });
  }
}

function setTheme(theme) {
  const label = document.getElementById('theme-label');
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
    if (label) label.textContent = 'Light';
  } else {
    document.documentElement.removeAttribute('data-theme');
    if (label) label.textContent = 'Dark';
  }
  localStorage.setItem('agent_theme', theme);
}

// ── Agent Dashboard Telemetry & Tasks ───────────────────────────────────────
state.dashboardTasks = [];
state.dashboardFilter = 'all';
state.dashboardSearch = '';

async function loadAgentDashboard() {
  try {
    const res = await fetch('/api/agent_dashboard');
    const data = await res.json();
    if (!data || !data.kpis) return;

    // 1. KPI Cards
    const kpis = data.kpis;
    document.getElementById('kpi-total-tasks').textContent = kpis.total_tasks;
    document.getElementById('kpi-success-rate').textContent = `${kpis.success_rate}%`;
    document.getElementById('kpi-sub-rate').textContent = `${kpis.finished_tasks} of ${kpis.total_tasks} completed`;
    document.getElementById('kpi-total-steps').textContent = kpis.total_steps;
    document.getElementById('kpi-subtasks-count').textContent = kpis.total_subtasks;
    document.getElementById('kpi-facts-count').textContent = kpis.total_facts;
    document.getElementById('kpi-avg-duration').textContent = `${kpis.avg_duration}s`;

    // 2. Tool Usage Bars
    const toolsContainer = document.getElementById('tool-usage-bars');
    if (data.tool_usage && data.tool_usage.length > 0) {
      document.getElementById('total-tools-label').textContent = `${data.tool_usage.length} tools active`;
      toolsContainer.innerHTML = data.tool_usage.map(item => `
        <div class="tool-bar-item">
          <div class="tool-bar-meta">
            <span class="tool-bar-name">${item.tool}</span>
            <span class="tool-bar-counts">${item.count} calls (${item.pct}%)</span>
          </div>
          <div class="tool-progress-bg">
            <div class="tool-progress-fill" style="width: ${item.pct}%;"></div>
          </div>
        </div>
      `).join('');
    }

    // 3. Recent Facts & Pitfalls
    const factsContainer = document.getElementById('recent-facts-container');
    if (data.recent_facts && data.recent_facts.length > 0) {
      factsContainer.innerHTML = data.recent_facts.map(f => `
        <div class="fact-item">
          <div class="fact-item-badge ${f.kind}">${f.kind}</div>
          <div class="fact-item-text">${escapeHtml(f.text)}</div>
        </div>
      `).join('');
    } else {
      factsContainer.innerHTML = '<div style="color:var(--text-dim); font-size:0.85rem;">No distilled lessons recorded yet.</div>';
    }

    // 4. Tasks Table
    state.dashboardTasks = data.tasks || [];
    renderDashboardTasks();

  } catch (err) {
    console.error('Failed to load dashboard:', err);
  }
}

function renderDashboardTasks() {
  const tbody = document.getElementById('dash-tasks-tbody');
  if (!tbody) return;

  let list = state.dashboardTasks || [];
  if (state.dashboardFilter !== 'all') {
    list = list.filter(t => t.status === state.dashboardFilter);
  }
  if (state.dashboardSearch) {
    const q = state.dashboardSearch.toLowerCase();
    list = list.filter(t =>
      String(t.id).includes(q) ||
      (t.task && t.task.toLowerCase().includes(q)) ||
      (t.summary && t.summary.toLowerCase().includes(q))
    );
  }

  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; color:var(--text-dim); padding:28px;">No matching tasks found.</td></tr>';
    return;
  }

  tbody.innerHTML = list.map(t => {
    const statusClass = t.status || 'unknown';
    const durationText = t.duration > 0 ? `${t.duration}s` : '-';
    return `
      <tr onclick="openTraceModal(${t.id})">
        <td><strong>#${t.id}</strong></td>
        <td>
          <div class="task-cell-spec" title="${escapeHtml(t.task)}">${escapeHtml(t.task)}</div>
        </td>
        <td><span class="status-dot-badge ${statusClass}">${t.status}</span></td>
        <td><span style="font-family:var(--font-mono); font-size:0.78rem; color:var(--accent-cyan);">${t.model || 'default'}</span></td>
        <td><span style="font-family:var(--font-mono); font-size:0.8rem; color:var(--text-muted);">${t.step_count}</span></td>
        <td><span style="font-family:var(--font-mono); font-size:0.8rem; color:var(--text-muted);">${durationText}</span></td>
        <td style="font-size:0.78rem; color:var(--text-dim); white-space:nowrap;">${t.created_at || '-'}</td>
        <td style="text-align:center;">
          <button class="btn-trace" onclick="event.stopPropagation(); openTraceModal(${t.id})">Trace</button>
        </td>
      </tr>
    `;
  }).join('');
}

// ── Execution Trace Drawer ──────────────────────────────────────────────────
const traceDrawer = document.getElementById('trace-drawer');
const closeTraceDrawerBtn = document.getElementById('close-trace-drawer');
if (closeTraceDrawerBtn) {
  closeTraceDrawerBtn.addEventListener('click', () => {
    traceDrawer.classList.remove('open');
  });
}

window.openTraceModal = async (taskId) => {
  const drawer = document.getElementById('trace-drawer');
  const title = document.getElementById('trace-task-title');
  const content = document.getElementById('trace-drawer-content');

  title.textContent = `Task #${taskId} Execution Trace`;
  content.innerHTML = '<div style="color:var(--text-dim); padding:24px; text-align:center;"><span class="spinner"></span> Loading telemetry trace...</div>';
  drawer.classList.add('open');

  try {
    const res = await fetch(`/api/task_trace?id=${taskId}`);
    const data = await res.json();
    if (!data || !data.task) {
      content.innerHTML = '<div style="color:var(--accent-rose);">Task trace not found.</div>';
      return;
    }

    const t = data.task;
    let html = `
      <div style="background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:10px; padding:14px; margin-bottom:16px;">
        <div style="font-size:0.75rem; text-transform:uppercase; color:var(--text-dim); font-weight:700; margin-bottom:6px;">Task Specification</div>
        <div style="font-size:0.88rem; line-height:1.5; color:var(--text-main); white-space:pre-wrap;">${escapeHtml(t.task)}</div>
        <div style="display:flex; gap:12px; margin-top:12px; font-size:0.78rem; font-family:var(--font-mono);">
          <span>Status: <strong class="status-dot-badge ${t.status}">${t.status}</strong></span>
          <span>Model: <strong style="color:var(--accent-cyan);">${t.model}</strong></span>
        </div>
      </div>
    `;

    if (t.summary) {
      html += `
        <div style="background:rgba(16,185,129,0.06); border:1px solid rgba(16,185,129,0.25); border-radius:10px; padding:12px; margin-bottom:16px;">
          <div style="font-size:0.75rem; text-transform:uppercase; color:var(--accent-emerald); font-weight:700; margin-bottom:4px;">Execution Summary</div>
          <div style="font-size:0.84rem; color:var(--text-main);">${escapeHtml(t.summary)}</div>
        </div>
      `;
    }

    if (data.subtasks && data.subtasks.length > 0) {
      html += `
        <div style="font-size:0.82rem; font-weight:700; text-transform:uppercase; color:var(--text-dim); margin-bottom:8px;">Subtask Breakdown (${data.subtasks.length})</div>
        <div style="display:flex; flex-direction:column; gap:8px; margin-bottom:16px;">
          ${data.subtasks.map(st => `
            <div style="padding:10px 12px; border-radius:8px; background:rgba(255,255,255,0.02); border:1px solid var(--border-subtle);">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                <strong style="font-size:0.82rem;">${escapeHtml(st.title)}</strong>
                <span class="status-dot-badge ${st.status}">${st.status}</span>
              </div>
              <div style="font-size:0.75rem; color:var(--text-muted); font-family:var(--font-mono);">${st.role || 'coder'}</div>
              ${st.summary ? `<div style="font-size:0.78rem; color:var(--text-dim); margin-top:4px;">${escapeHtml(st.summary)}</div>` : ''}
            </div>
          `).join('')}
        </div>
      `;
    }

    html += `<div style="font-size:0.82rem; font-weight:700; text-transform:uppercase; color:var(--text-dim); margin-bottom:10px;">Tool Steps Timeline (${data.steps ? data.steps.length : 0})</div>`;

    if (data.steps && data.steps.length > 0) {
      html += data.steps.map(s => {
        let formattedArgs = '';
        try {
          const parsedArgs = typeof s.args === 'string' ? JSON.parse(s.args) : s.args;
          formattedArgs = JSON.stringify(parsedArgs, null, 2);
        } catch (e) {
          formattedArgs = String(s.args);
        }

        return `
          <div class="trace-step-item">
            <div class="trace-step-header">
              <span class="trace-step-n">Step ${s.n}</span>
              <span class="trace-step-tool">${s.tool}</span>
            </div>
            <div class="trace-code-block">${escapeHtml(formattedArgs)}</div>
            <div style="font-size:0.75rem; color:var(--text-dim); margin-top:2px;">Observation Output:</div>
            <div class="trace-code-block" style="color:var(--accent-emerald);">${escapeHtml(s.observation || '(no output)')}</div>
          </div>
        `;
      }).join('');
    } else {
      html += '<div style="color:var(--text-dim); font-size:0.82rem; padding:12px;">No individual tool steps logged for this task.</div>';
    }

    content.innerHTML = html;

  } catch (err) {
    content.innerHTML = `<div style="color:var(--accent-rose);">Failed to load trace: ${err.message}</div>`;
  }
};

// ── Navigation & Interactions ───────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

    item.classList.add('active');
    const tabName = item.dataset.tab;
    state.activeTab = tabName;
    document.getElementById(`tab-${tabName}`).classList.add('active');

    // Update title
    const titles = {
      graph: 'Knowledge Graph Studio',
      code: 'Code Studio & Workspace Agent',
      dashboard: 'Agent Fleet & Telemetry Dashboard',
      study: 'Curriculum Generator',
      tutor: 'AI Study Tutor',
    };
    document.getElementById('current-view-title').textContent = titles[tabName] || 'Studio';

    if (tabName === 'dashboard') loadAgentDashboard();
    if (tabName === 'code') initCodeStudio();
    if (tabName === 'graph') resizeCanvas();
  });
});

// Dashboard Filter Pills
document.querySelectorAll('.status-pill-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.status-pill-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.dashboardFilter = btn.dataset.status;
    renderDashboardTasks();
  });
});

// Dashboard Task Search
const dashSearchInput = document.getElementById('dash-task-search');
if (dashSearchInput) {
  dashSearchInput.addEventListener('input', (e) => {
    state.dashboardSearch = e.target.value.trim();
    renderDashboardTasks();
  });
}

// Dashboard Refresh Button
const btnRefreshDash = document.getElementById('btn-refresh-dashboard');
if (btnRefreshDash) {
  btnRefreshDash.addEventListener('click', () => {
    loadAgentDashboard();
  });
}

// Filter Buttons
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    state.activeFilter = btn.dataset.filter;
    state.activeTopic = null;
    const badge = document.getElementById('active-topic-badge');
    if (badge) badge.style.display = 'none';
    updateLegendUI();
    reheatSimulation(0.35);
    setTimeout(() => zoomToFit(true), 100);
  });
});

// Clear Topic Badge Button
const btnClearTopic = document.getElementById('btn-clear-topic-highlight');
if (btnClearTopic) {
  btnClearTopic.addEventListener('click', () => {
    window.clearTopicHighlight();
  });
}

// Legend Collapse / Expand Toggle
const legendToggleBtn = document.getElementById('legend-toggle-btn');
const legendDock = document.getElementById('graph-legend-dock');
if (legendToggleBtn && legendDock) {
  legendToggleBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    legendDock.classList.toggle('collapsed');
    legendToggleBtn.textContent = legendDock.classList.contains('collapsed') ? '+' : '−';
  });
}

// Search Filter
searchInput.addEventListener('input', (e) => {
  state.searchQuery = e.target.value.toLowerCase().trim();
});

searchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const q = searchInput.value.trim();
    if (!q) return;
    openNodeByName(q);
  }
});

// Zoom Controls
const zoomInBtn = document.getElementById('zoom-in');
if (zoomInBtn) {
  zoomInBtn.addEventListener('click', () => {
    state.targetTransform = null;
    state.transform.scale = Math.min(4.0, state.transform.scale * 1.25);
  });
}

const zoomOutBtn = document.getElementById('zoom-out');
if (zoomOutBtn) {
  zoomOutBtn.addEventListener('click', () => {
    state.targetTransform = null;
    state.transform.scale = Math.max(0.2, state.transform.scale * 0.8);
  });
}

const fitViewBtn = document.getElementById('btn-fit-view');
if (fitViewBtn) {
  fitViewBtn.addEventListener('click', () => zoomToFit(true));
}

const zoomFitFloatBtn = document.getElementById('zoom-fit-float');
if (zoomFitFloatBtn) {
  zoomFitFloatBtn.addEventListener('click', () => zoomToFit(true));
}

// Graph Simulation Play / Pause / Freeze Toggle
const btnToggleSim = document.getElementById('btn-toggle-sim');
if (btnToggleSim) {
  btnToggleSim.addEventListener('click', () => {
    state.isPaused = !state.isPaused;
    if (!state.isPaused && state.alpha <= state.alphaMin) {
      state.alpha = 0.35;
      state.isSettled = false;
    }
    updateSimBadge();
  });
}

// Graph Simulation Reheat & Settle Button
const btnReheatSim = document.getElementById('btn-reheat-sim');
if (btnReheatSim) {
  btnReheatSim.addEventListener('click', () => {
    reheatSimulation(0.7);
  });
}

// Layout Switcher Dropdown
const selectLayout = document.getElementById('select-graph-layout');
if (selectLayout) {
  selectLayout.addEventListener('change', (e) => {
    applyLayout(e.target.value);
  });
}

// Physics Settings Popover Panel
const btnTogglePhysics = document.getElementById('btn-toggle-physics-panel');
const physicsPanel = document.getElementById('physics-panel');
const closePhysicsBtn = document.getElementById('close-physics-panel');

if (btnTogglePhysics && physicsPanel) {
  btnTogglePhysics.addEventListener('click', (e) => {
    e.stopPropagation();
    physicsPanel.classList.toggle('open');
  });
}
if (closePhysicsBtn && physicsPanel) {
  closePhysicsBtn.addEventListener('click', () => {
    physicsPanel.classList.remove('open');
  });
}

// Sliders and Tuning Controls
const sliderRepulsion = document.getElementById('slider-repulsion');
const valRepulsion = document.getElementById('val-repulsion');
if (sliderRepulsion) {
  sliderRepulsion.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    state.physicsParams.repulsion = val;
    if (valRepulsion) valRepulsion.textContent = val;
    reheatSimulation(0.35);
  });
}

const sliderSpring = document.getElementById('slider-spring');
const valSpring = document.getElementById('val-spring');
if (sliderSpring) {
  sliderSpring.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    state.physicsParams.springLen = val;
    if (valSpring) valSpring.textContent = `${val}px`;
    reheatSimulation(0.35);
  });
}

const sliderGravity = document.getElementById('slider-gravity');
const valGravity = document.getElementById('val-gravity');
if (sliderGravity) {
  sliderGravity.addEventListener('input', (e) => {
    const val = parseInt(e.target.value, 10);
    state.physicsParams.gravity = val * 0.0002;
    if (valGravity) {
      valGravity.textContent = val <= 3 ? 'Gentle' : (val >= 8 ? 'Strong' : 'Medium');
    }
    reheatSimulation(0.35);
  });
}

const selectLabelMode = document.getElementById('select-label-mode');
if (selectLabelMode) {
  selectLabelMode.addEventListener('change', (e) => {
    state.physicsParams.labelMode = e.target.value;
  });
}

const selectSizeMode = document.getElementById('select-size-mode');
if (selectSizeMode) {
  selectSizeMode.addEventListener('change', (e) => {
    state.physicsParams.sizeMode = e.target.value;
    computeTopology();
  });
}

const btnResetPhysics = document.getElementById('btn-reset-physics');
if (btnResetPhysics) {
  btnResetPhysics.addEventListener('click', () => {
    state.physicsParams.repulsion = 1400;
    state.physicsParams.springLen = 80;
    state.physicsParams.gravity = 0.0008;
    state.physicsParams.labelMode = 'smart';
    state.physicsParams.sizeMode = 'degree';

    if (sliderRepulsion) sliderRepulsion.value = 1400;
    if (valRepulsion) valRepulsion.textContent = 1400;
    if (sliderSpring) sliderSpring.value = 80;
    if (valSpring) valSpring.textContent = '80px';
    if (sliderGravity) sliderGravity.value = 5;
    if (valGravity) valGravity.textContent = 'Medium';
    if (selectLabelMode) selectLabelMode.value = 'smart';
    if (selectSizeMode) selectSizeMode.value = 'degree';

    computeTopology();
    reheatSimulation(0.65);
  });
}

document.getElementById('btn-refresh-graph').addEventListener('click', async () => {
  await loadGraphData();
  await loadStats();
});

document.getElementById('btn-quick-study').addEventListener('click', () => {
  document.querySelector('[data-tab="study"]').click();
});

// Suggested Topic Chips
document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.getElementById('study-topic-input').value = chip.dataset.topic;
  });
});

// ── Topic Highlighting & Visual Graph Filtering ─────────────────────────────
window.openTopicGraph = (topicName) => {
  document.querySelector('[data-tab="graph"]').click();
  if (searchInput) searchInput.value = '';
  state.searchQuery = '';
  highlightTopic(topicName);
};

window.highlightTopic = (topicName) => {
  if (!topicName) return;
  state.activeTopic = topicName;
  state.activeFilter = 'all';

  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  const allBtn = document.querySelector('.filter-btn[data-filter="all"]');
  if (allBtn) allBtn.classList.add('active');

  const badge = document.getElementById('active-topic-badge');
  const badgeName = document.getElementById('active-topic-badge-name');
  if (badge && badgeName) {
    badge.style.display = 'inline-flex';
    badgeName.textContent = topicName.replace(/_/g, ' ');
  }

  const tRaw = topicName.toLowerCase();
  const tClean = tRaw.replace(/_/g, ' ');
  const matched = state.nodes.filter(n => {
    const nTopic = (n.topic || '').toLowerCase();
    const nRef = (n.ref || '').toLowerCase();
    const nName = (n.name || '').toLowerCase();
    return nTopic === tRaw || nRef.includes(tRaw) || nRef.includes(tClean) ||
           (n.is_curriculum && (nName.includes(tRaw) || nRef.includes(tRaw)));
  });

  if (matched.length > 0) {
    zoomToNodes(matched, true);
    // Find curriculum / index node for this topic and open note details
    const currNode = matched.find(n => n.is_curriculum || n.name.toLowerCase().includes('curriculum') || n.name === 'Curriculum_Index') || matched[0];
    if (currNode) {
      state.hoveredNode = currNode;
      state.focusedNeighbors = state.adjacencyMap.get(currNode.id) || new Set();
      openNodeDetails(currNode);
    }
  } else {
    reheatSimulation(0.35);
  }
  updateLegendUI();
};

window.clearTopicHighlight = () => {
  state.activeTopic = null;
  const badge = document.getElementById('active-topic-badge');
  if (badge) badge.style.display = 'none';
  updateLegendUI();
  zoomToFit(true);
};

window.toggleCategoryFilter = (catKey) => {
  if (state.activeFilter === catKey) {
    state.activeFilter = 'all';
  } else {
    state.activeFilter = catKey;
    state.activeTopic = null;
    const badge = document.getElementById('active-topic-badge');
    if (badge) badge.style.display = 'none';
  }
  document.querySelectorAll('.filter-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.filter === state.activeFilter);
  });
  updateLegendUI();
  reheatSimulation(0.35);
  setTimeout(() => zoomToFit(true), 100);
};

function renderLegendUI() {
  const container = document.getElementById('graph-legend-body');
  if (!container) return;

  const items = [];

  // 1. Education Topics (Emerald, Cyan, Amber, etc.)
  if (state.topics) {
    for (const [topicKey, count] of Object.entries(state.topics)) {
      const colors = getTopicColor(topicKey);
      const isActive = state.activeTopic === topicKey;
      items.push(`
        <div class="legend-item ${isActive ? 'active' : ''}" onclick="highlightTopic('${escapeHtml(topicKey)}')" title="Filter to ${escapeHtml(colors.label)} (${count} concepts)">
          <span class="legend-dot" style="background:${colors.fill}; box-shadow: 0 0 8px ${colors.glow};"></span>
          <span class="legend-label">${escapeHtml(colors.label)}</span>
          <span class="legend-count">${count}</span>
        </div>
      `);
    }
  }

  // 2. Structural Categories
  const catLabels = {
    workspace_project: 'Workspace Projects',
    workspace_file: 'Workspace Files',
    task: 'Agent Tasks',
    code_file: 'Python Files',
    code_class: 'Classes',
    code_function: 'Functions',
    code_module: 'Imports',
    tag: 'Tags',
    concept: 'Concepts',
  };

  if (state.categories) {
    for (const [catKey, label] of Object.entries(catLabels)) {
      const count = state.categories[catKey];
      if (!count) continue;
      const colors = CATEGORY_COLORS[catKey] || CATEGORY_COLORS.default;
      const isActive = state.activeFilter === catKey;
      items.push(`
        <div class="legend-item ${isActive ? 'active' : ''}" onclick="toggleCategoryFilter('${catKey}')" title="Filter to ${label} (${count} nodes)">
          <span class="legend-dot" style="background:${colors.fill}; box-shadow: 0 0 6px ${colors.glow};"></span>
          <span class="legend-label">${label}</span>
          <span class="legend-count">${count}</span>
        </div>
      `);
    }
  }

  container.innerHTML = items.join('');
}

function updateLegendUI() {
  renderLegendUI();
}

// ── Study Generation Form ───────────────────────────────────────────────────
document.getElementById('study-gen-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = document.getElementById('study-topic-input');
  const topic = input.value.trim();
  if (!topic) return;

  const btn = document.getElementById('btn-generate-curriculum');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> <span>Synthesizing...</span>';

  try {
    const res = await fetch('/api/study/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ topic }),
    });
    const data = await res.json();

    if (data.success) {
      input.value = '';
      await loadGraphData();
      await loadStats();
      document.querySelector('[data-tab="graph"]').click();
      window.openNodeByName(data.curriculum_name);
    } else {
      alert('Error generating topic: ' + (data.error || 'Unknown error'));
    }
  } catch (err) {
    alert('Generation failed: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span>Generate Graph</span>';
  }
});

// ── Tutor Form ──────────────────────────────────────────────────────────────
document.getElementById('tutor-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const input = document.getElementById('tutor-input');
  const question = input.value.trim();
  if (!question) return;

  const chatBox = document.getElementById('tutor-chat-box');
  input.value = '';

  // Append user message
  const userMsg = document.createElement('div');
  userMsg.className = 'chat-msg user';
  userMsg.innerHTML = `
    <div class="chat-avatar">You</div>
    <div class="chat-bubble">${question}</div>
  `;
  chatBox.appendChild(userMsg);

  // Append bot loading bubble
  const botMsg = document.createElement('div');
  botMsg.className = 'chat-msg bot';
  botMsg.innerHTML = `
    <div class="chat-avatar">AI</div>
    <div class="chat-bubble"><span class="spinner"></span> Consulting personal study graph...</div>
  `;
  chatBox.appendChild(botMsg);
  chatBox.scrollTop = chatBox.scrollHeight;

  try {
    const res = await fetch('/api/study/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    botMsg.querySelector('.chat-bubble').innerHTML = renderMarkdown(data.answer);
  } catch (err) {
    botMsg.querySelector('.chat-bubble').innerHTML = `<span style="color:var(--accent-rose);">Error: ${err.message}</span>`;
  }
  chatBox.scrollTop = chatBox.scrollHeight;
});

// ── Startup ─────────────────────────────────────────────────────────────────
async function init() {
  initTheme();
  resizeCanvas();
  await loadStats();
  await loadGraphData();
  animationLoop();
}

window.addEventListener('DOMContentLoaded', init);

// ============================================================================
// CODE STUDIO & GRAPH NODE LINKING CONTROLLER
// ============================================================================

state.codeStudio = {
  workspaces: [],
  currentWorkspace: '',
  files: [],
  activeFile: null,
  activeFilePath: '',
  isDirty: false,
  offlineMode: true,
  activeModel: 'qwen2.5-coder:3b',
  activePane: 'terminal',
  activeFileLinks: [],
};

// Modal Linking State
state.linkModal = {
  srcNode: null,
  selectedTarget: null,
  searchTimer: null,
};

// ── Drawer Links Renderer ───────────────────────────────────────────────────
function renderDrawerLinks(outgoing, incoming, nodeId) {
  const container = document.getElementById('drawer-links-list');
  if (!container) return;

  const allLinks = [];
  outgoing.forEach(o => allLinks.push({ ...o, direction: 'outgoing' }));
  incoming.forEach(i => allLinks.push({ ...i, direction: 'incoming' }));

  if (allLinks.length === 0) {
    container.innerHTML = '<div style="color:var(--text-dim); font-size:0.75rem; padding:4px 0;">No direct relational links to other nodes. Click "+ Link Node" to connect.</div>';
    return;
  }

  container.innerHTML = allLinks.map(l => {
    const isOut = l.direction === 'outgoing';
    const otherId = l.id;
    const arrow = isOut ? '➜' : '⬅';
    const relText = l.rel || 'links_to';
    const displayName = (l.name || 'Node').replace(/_/g, ' ');

    return `
      <div class="link-chip" data-node-id="${otherId}" title="${isOut ? 'Links to' : 'Referenced by'}: ${escapeHtml(displayName)}">
        <div class="link-chip-info" onclick="openNodeByIdOrName('${otherId}', '${escapeHtml(l.name)}')">
          <span style="font-size:0.7rem; color:var(--text-dim);">${arrow}</span>
          <span class="link-chip-rel">${escapeHtml(relText)}</span>
          <strong style="font-size:0.78rem;">${escapeHtml(displayName)}</strong>
        </div>
        <button class="link-chip-remove" onclick="handleUnlinkFromDrawer(event, ${nodeId}, ${otherId}, '${escapeHtml(relText)}', '${isOut ? 'out' : 'in'}')" title="Remove link">&times;</button>
      </div>
    `;
  }).join('');
}

window.openNodeByIdOrName = (id, name) => {
  if (id && state.nodeMap.has(id)) {
    const node = state.nodeMap.get(id);
    openNodeDetails(node);
  } else if (name) {
    openNodeByName(name);
  }
};

window.handleUnlinkFromDrawer = async (e, currentId, otherId, rel, dir) => {
  e.stopPropagation();
  const srcId = dir === 'out' ? currentId : otherId;
  const dstId = dir === 'out' ? otherId : currentId;
  await unlinkNodes(srcId, dstId, rel, () => {
    if (state.selectedNode) {
      openNodeDetails(state.selectedNode);
    }
  });
};

// ── Code Studio Initialization ──────────────────────────────────────────────
async function initCodeStudio() {
  await loadWorkspacesList();
  bindCodeStudioEvents();
}

async function loadWorkspacesList(preferredWorkspace = '') {
  try {
    const res = await fetch('/api/workspaces');
    const workspaces = await res.json();
    state.codeStudio.workspaces = workspaces;

    const select = document.getElementById('code-workspace-select');
    if (!select) return;

    if (workspaces.length === 0) {
      select.innerHTML = '<option value="">No workspaces found</option>';
      return;
    }

    select.innerHTML = workspaces.map(w => {
      const label = `${w.name} (${w.file_count} files${w.has_tests ? ' • tests' : ''})`;
      return `<option value="${escapeHtml(w.name)}">${escapeHtml(label)}</option>`;
    }).join('');

    const targetWs = preferredWorkspace || state.codeStudio.currentWorkspace || (workspaces.find(w => w.name === 'my_project') ? 'my_project' : workspaces[0].name);
    select.value = targetWs;
    await switchWorkspace(targetWs);
  } catch (err) {
    console.error('Failed to load workspaces:', err);
  }
}

async function switchWorkspace(wsName, preferredFile = '') {
  state.codeStudio.currentWorkspace = wsName;
  const select = document.getElementById('code-workspace-select');
  if (select && select.value !== wsName) select.value = wsName;

  try {
    const res = await fetch(`/api/workspace/files?workspace=${encodeURIComponent(wsName)}`);
    const data = await res.json();
    const files = data.files || [];
    state.codeStudio.files = files;

    // Badges
    const badgeFiles = document.getElementById('badge-ws-files');
    if (badgeFiles) badgeFiles.textContent = `${files.length} files`;

    // Render File Tree
    renderWorkspaceFileTree(files, preferredFile);

    // Populate agent link suggestions dropdown
    populateAgentLinkDropdown();

    // Select file
    if (files.length > 0) {
      let fileToOpen = files[0].path;
      if (preferredFile && files.some(f => f.path === preferredFile || f.name === preferredFile)) {
        fileToOpen = files.find(f => f.path === preferredFile || f.name === preferredFile).path;
      } else {
        const priority = files.find(f => f.name === 'main.py' || f.name === 'rate_limiter.py') ||
                         files.find(f => !f.is_test && f.ext === '.py') || files[0];
        fileToOpen = priority.path;
      }
      await openWorkspaceFile(fileToOpen);
    } else {
      clearCodeEditor();
    }
  } catch (err) {
    console.error(`Failed to switch workspace to ${wsName}:`, err);
  }
}

window.openWorkspaceInStudio = async (workspaceName, filePath = '') => {
  await loadWorkspacesList(workspaceName);
  if (filePath) {
    await openWorkspaceFile(filePath);
  }
};

function renderWorkspaceFileTree(files, activePath = '') {
  const treeContainer = document.getElementById('code-file-tree');
  if (!treeContainer) return;

  if (files.length === 0) {
    treeContainer.innerHTML = '<div style="color:var(--text-dim); font-size:0.75rem; padding:12px 8px;">No source files in this workspace.</div>';
    return;
  }

  treeContainer.innerHTML = files.map(f => {
    const isActive = f.path === (activePath || state.codeStudio.activeFilePath);
    let icon = '📄';
    if (f.ext === '.py') icon = f.is_test ? '🧪' : '🐍';
    else if (f.ext === '.json') icon = '📋';
    else if (f.ext === '.md') icon = '📝';
    else if (f.ext === '.toml' || f.ext === '.yaml' || f.ext === '.yml') icon = '⚙️';

    const sizeStr = f.size > 1024 ? `${(f.size / 1024).toFixed(1)}k` : `${f.size}b`;

    return `
      <div class="file-tree-item ${isActive ? 'active' : ''} ${f.is_test ? 'is-test' : ''}" data-file-path="${escapeHtml(f.path)}" onclick="openWorkspaceFile('${escapeHtml(f.path)}')">
        <span class="file-tree-icon">${icon}</span>
        <span class="file-tree-name" title="${escapeHtml(f.path)}">${escapeHtml(f.name)}</span>
        <span class="file-size-hint">${sizeStr}</span>
      </div>
    `;
  }).join('');
}

window.openWorkspaceFile = async (filePath) => {
  if (!state.codeStudio.currentWorkspace || !filePath) return;

  state.codeStudio.activeFilePath = filePath;

  // Update active file tree selection
  document.querySelectorAll('.file-tree-item').forEach(el => {
    el.classList.toggle('active', el.dataset.filePath === filePath);
  });

  try {
    const res = await fetch(`/api/workspace/file?workspace=${encodeURIComponent(state.codeStudio.currentWorkspace)}&path=${encodeURIComponent(filePath)}`);
    if (!res.ok) throw new Error('Failed to read file');
    const data = await res.json();

    state.codeStudio.activeFile = data;
    state.codeStudio.fileContent = data.content;
    state.codeStudio.isDirty = false;

    // Editor tab header
    const ext = filePath.split('.').pop().toLowerCase();
    document.getElementById('editor-active-filename').textContent = data.name;
    document.getElementById('editor-dirty-indicator').style.display = 'none';

    let icon = '📄';
    if (ext === 'py') icon = data.name.startsWith('test_') ? '🧪' : '🐍';
    else if (ext === 'json') icon = '📋';
    else if (ext === 'md') icon = '📝';
    document.getElementById('editor-file-icon').textContent = icon;

    document.getElementById('editor-lang-pill').textContent = ext.toUpperCase();
    document.getElementById('editor-size-pill').textContent = `${data.size} B`;

    const textarea = document.getElementById('code-editor-textarea');
    textarea.value = data.content;

    // Render linked nodes for this file
    state.codeStudio.activeFileLinks = data.links || [];
    renderActiveFileLinks(data.links || [], data.node_id);

    // If target file was empty in agent bar, prefill it
    const targetInput = document.getElementById('agent-target-file');
    if (targetInput && !targetInput.value) {
      targetInput.value = data.name;
    }
  } catch (err) {
    console.error(`Failed to load file ${filePath}:`, err);
  }
};

function clearCodeEditor() {
  state.codeStudio.activeFile = null;
  state.codeStudio.activeFilePath = '';
  document.getElementById('editor-active-filename').textContent = 'No file selected';
  document.getElementById('editor-dirty-indicator').style.display = 'none';
  document.getElementById('code-editor-textarea').value = '';
  document.getElementById('editor-size-pill').textContent = '0 B';
  renderActiveFileLinks([], null);
}

function renderActiveFileLinks(links, fileNodeId) {
  const container = document.getElementById('code-file-links-container');
  if (!container) return;

  if (!links || links.length === 0) {
    container.innerHTML = '<div class="no-links-hint">No graph connections for this file yet. Click <strong>+ Link</strong> to connect with educational notes or tasks.</div>';
    return;
  }

  container.innerHTML = links.map(l => {
    const isOut = l.direction === 'outgoing';
    const arrow = isOut ? '➜' : '⬅';
    const relText = l.rel || 'links_to';
    const displayName = (l.name || 'Concept').replace(/_/g, ' ');

    return `
      <div class="link-chip" title="${isOut ? 'Implements / References' : 'Referenced by'}: ${escapeHtml(displayName)}">
        <div class="link-chip-info" onclick="viewLinkedNodeInGraph('${l.id}', '${escapeHtml(l.name)}')">
          <span style="font-size:0.7rem; color:var(--text-dim);">${arrow}</span>
          <span class="link-chip-rel">${escapeHtml(relText)}</span>
          <strong style="font-size:0.76rem;">${escapeHtml(displayName)}</strong>
        </div>
        <button class="link-chip-remove" onclick="handleUnlinkActiveFile(event, ${fileNodeId}, ${l.id}, '${escapeHtml(relText)}', '${isOut ? 'out' : 'in'}')" title="Remove link">&times;</button>
      </div>
    `;
  }).join('');
}

window.viewLinkedNodeInGraph = (nodeId, nodeName) => {
  document.querySelector('[data-tab="graph"]').click();
  openNodeByIdOrName(nodeId, nodeName);
};

window.handleUnlinkActiveFile = async (e, fileNodeId, otherId, rel, dir) => {
  e.stopPropagation();
  const srcId = dir === 'out' ? fileNodeId : otherId;
  const dstId = dir === 'out' ? otherId : fileNodeId;
  await unlinkNodes(srcId, dstId, rel, () => {
    if (state.codeStudio.activeFilePath) {
      window.openWorkspaceFile(state.codeStudio.activeFilePath);
    }
  });
};

async function saveActiveCodeFile() {
  const textarea = document.getElementById('code-editor-textarea');
  if (!textarea || !state.codeStudio.currentWorkspace || !state.codeStudio.activeFilePath) return;

  const content = textarea.value;
  const btnSave = document.getElementById('btn-code-save-file');
  if (btnSave) {
    btnSave.disabled = true;
    btnSave.innerHTML = '<span class="spinner"></span> Saving...';
  }

  try {
    const res = await fetch('/api/workspace/file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workspace: state.codeStudio.currentWorkspace,
        path: state.codeStudio.activeFilePath,
        content: content,
      }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Failed to save');

    state.codeStudio.fileContent = content;
    state.codeStudio.isDirty = false;
    document.getElementById('editor-dirty-indicator').style.display = 'none';
    document.getElementById('editor-size-pill').textContent = `${data.size} B`;

    // Refresh graph silently in background
    loadGraphData();
    loadStats();

    if (btnSave) {
      btnSave.innerHTML = '<span>✓</span> Saved!';
      setTimeout(() => {
        btnSave.disabled = false;
        btnSave.innerHTML = '<span>💾</span> Save File';
      }, 1200);
    }
  } catch (err) {
    alert('Save failed: ' + err.message);
    if (btnSave) {
      btnSave.disabled = false;
      btnSave.innerHTML = '<span>💾</span> Save File';
    }
  }
}

// ── Code Execution Terminal ────────────────────────────────────────────────
async function executeTerminalCommand() {
  if (!state.codeStudio.currentWorkspace) return;

  const preset = document.getElementById('code-term-cmd-preset').value;
  const customInput = document.getElementById('code-term-custom-cmd');
  const termOut = document.getElementById('code-terminal-output');
  const statusBadge = document.getElementById('term-status-badge');
  const durBadge = document.getElementById('term-duration-badge');
  const btnRun = document.getElementById('btn-execute-term-cmd');

  let command = preset;
  let targetFile = state.codeStudio.activeFilePath;

  if (preset === 'custom') {
    command = customInput.value.trim() || 'pytest -v';
  }

  // Switch to terminal pane if not visible
  document.getElementById('tab-btn-terminal').click();

  statusBadge.className = 'term-status-running';
  statusBadge.textContent = 'Running...';
  durBadge.textContent = '...';
  btnRun.disabled = true;

  termOut.innerHTML = `<span class="term-dim">$ executing ${command} in workspace [${state.codeStudio.currentWorkspace}]...\n</span>`;

  try {
    const res = await fetch('/api/workspace/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workspace: state.codeStudio.currentWorkspace,
        command: command,
        file: targetFile,
      }),
    });
    const data = await res.json();

    const isSuccess = data.success;
    statusBadge.className = isSuccess ? 'term-status-passed' : 'term-status-failed';
    statusBadge.textContent = isSuccess ? 'Passed' : 'Failed';
    durBadge.textContent = `${data.duration}s`;

    let outText = '';
    if (data.stdout) outText += data.stdout;
    if (data.stderr) outText += (outText ? '\n' : '') + data.stderr;
    if (!outText) outText = `Process exited with returncode ${data.returncode}`;

    // Highlight pytest passes and failures
    const formatted = escapeHtml(outText)
      .replace(/(PASSED)/g, '<span style="color:#10b981; font-weight:700;">$1</span>')
      .replace(/(FAILED|ERROR)/g, '<span style="color:#ef4444; font-weight:700;">$1</span>')
      .replace(/(collected \d+ items?)/g, '<span style="color:#00f2fe;">$1</span>')
      .replace(/(===+ .* ===+)/g, '<span style="color:#6366f1; font-weight:600;">$1</span>');

    termOut.innerHTML = formatted;
    termOut.scrollTop = termOut.scrollHeight;

  } catch (err) {
    statusBadge.className = 'term-status-failed';
    statusBadge.textContent = 'Error';
    termOut.innerHTML = `<span style="color:#ef4444;">Execution error: ${escapeHtml(err.message)}</span>`;
  } finally {
    btnRun.disabled = false;
  }
}

// ── Autonomous Coding Agent Generator ──────────────────────────────────────
async function runAgentCodePrompt() {
  const promptInput = document.getElementById('agent-code-prompt');
  const targetFileInput = document.getElementById('agent-target-file');
  const linkSelect = document.getElementById('agent-link-existing-select');
  const statusDiv = document.getElementById('agent-gen-status');
  const btnRun = document.getElementById('btn-run-agent-code');

  const prompt = promptInput.value.trim();
  if (!prompt) {
    alert('Please enter instructions for the autonomous coding agent.');
    return;
  }

  btnRun.disabled = true;
  btnRun.innerHTML = '<span class="spinner"></span> <span>Synthesizing Code...</span>';
  statusDiv.style.display = 'block';
  statusDiv.innerHTML = '<span class="spinner"></span> Agent reading workspace context and generating implementation...';

  try {
    const res = await fetch('/api/workspace/agent_code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        workspace: state.codeStudio.currentWorkspace,
        prompt: prompt,
        file: targetFileInput.value.trim(),
        mode: state.codeStudio.offlineMode ? 'offline' : 'online',
        model: state.codeStudio.activeModel,
        link_node_id: linkSelect.value || null,
      }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Agent execution failed');

    statusDiv.innerHTML = `
      <span style="color:#10b981; font-weight:700;">✓ Generated <code>${escapeHtml(data.file)}</code></span>
      <div style="font-size:0.75rem; color:var(--text-muted); margin-top:4px;">Indexed into Knowledge Graph (${data.graph_stats ? data.graph_stats.nodes : 1} nodes updated).</div>
    `;

    // Refresh workspace files and switch to generated file
    await switchWorkspace(state.codeStudio.currentWorkspace, data.file);
    await loadGraphData();
    await loadStats();

    // Auto-run tests in terminal
    setTimeout(() => {
      document.getElementById('tab-btn-terminal').click();
      executeTerminalCommand();
    }, 400);

  } catch (err) {
    statusDiv.innerHTML = `<span style="color:#ef4444;">Agent error: ${escapeHtml(err.message)}</span>`;
  } finally {
    btnRun.disabled = false;
    btnRun.innerHTML = '<span>⚡</span> Generate Code';
  }
}

// ── Graph Node Linking Engine & Modal ──────────────────────────────────────
function openLinkModal(sourceNode) {
  if (!sourceNode) return;
  state.linkModal.srcNode = sourceNode;
  state.linkModal.selectedTarget = null;

  document.getElementById('link-modal-src-name').textContent = sourceNode.name;
  document.getElementById('link-modal-src-kind').textContent = sourceNode.kind || 'node';

  const searchInput = document.getElementById('link-target-search-input');
  searchInput.value = '';
  document.getElementById('link-target-search-results').innerHTML = '<div style="color:var(--text-dim); font-size:0.75rem; padding:6px;">Type a concept or filename to search...</div>';
  document.getElementById('selected-target-display').style.display = 'none';
  document.getElementById('btn-confirm-create-link').disabled = true;

  const modal = document.getElementById('modal-link-node');
  modal.style.display = 'flex';
  setTimeout(() => searchInput.focus(), 50);

  // Load initial popular nodes
  searchTargetNodes('');
}

function closeLinkModal() {
  document.getElementById('modal-link-node').style.display = 'none';
}

async function searchTargetNodes(query) {
  const resultsContainer = document.getElementById('link-target-search-results');
  if (!resultsContainer) return;

  try {
    const res = await fetch(`/api/graph/nodes_search?q=${encodeURIComponent(query)}&limit=25`);
    const nodes = await res.json();

    const srcId = state.linkModal.srcNode ? state.linkModal.srcNode.id : null;
    const filtered = nodes.filter(n => n.id !== srcId);

    if (filtered.length === 0) {
      resultsContainer.innerHTML = '<div style="color:var(--text-dim); font-size:0.75rem; padding:8px;">No matching graph nodes found.</div>';
      return;
    }

    resultsContainer.innerHTML = filtered.map(n => {
      const catColor = (CATEGORY_COLORS[n.category] || CATEGORY_COLORS.default).fill;
      const cleanName = (n.name || 'Node').replace(/_/g, ' ');

      return `
        <div class="target-search-item" data-id="${n.id}" data-name="${escapeHtml(n.name)}" onclick="selectTargetNode(${n.id}, '${escapeHtml(cleanName)}')">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="width:8px; height:8px; border-radius:50%; background:${catColor};"></span>
            <strong>${escapeHtml(cleanName)}</strong>
          </div>
          <span style="font-size:0.7rem; color:var(--text-dim);">${escapeHtml(n.kind || n.category)}</span>
        </div>
      `;
    }).join('');
  } catch (err) {
    resultsContainer.innerHTML = `<div style="color:#ef4444; font-size:0.75rem; padding:8px;">Search error: ${err.message}</div>`;
  }
}

window.selectTargetNode = (id, name) => {
  state.linkModal.selectedTarget = { id, name };
  document.getElementById('selected-target-name').textContent = name;
  document.getElementById('selected-target-display').style.display = 'flex';
  document.getElementById('btn-confirm-create-link').disabled = false;
};

async function confirmCreateLink() {
  const src = state.linkModal.srcNode;
  const dst = state.linkModal.selectedTarget;
  const rel = document.getElementById('link-relation-select').value || 'implements';

  if (!src || !dst) return;

  const btnConfirm = document.getElementById('btn-confirm-create-link');
  btnConfirm.disabled = true;
  btnConfirm.innerHTML = '<span class="spinner"></span> Connecting...';

  try {
    const res = await fetch('/api/graph/link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        src_id: src.id,
        src_ref: src.ref,
        dst_id: dst.id,
        rel: rel,
      }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Linking failed');

    closeLinkModal();

    // Add live edge to simulation without full page reload
    state.edges.push({
      source: String(data.src_id),
      target: String(data.dst_id),
      rel: rel,
    });
    computeTopology();
    reheatSimulation(0.35);

    // If drawer is open, refresh drawer note
    if (noteDrawer.classList.contains('open') && state.selectedNode) {
      openNodeDetails(state.selectedNode);
    }

    // If active in Code Studio, reload active file connections
    if (state.activeTab === 'code' && state.codeStudio.activeFilePath) {
      window.openWorkspaceFile(state.codeStudio.activeFilePath);
    }

  } catch (err) {
    alert('Failed to create link: ' + err.message);
  } finally {
    btnConfirm.disabled = false;
    btnConfirm.innerHTML = 'Create Connection';
  }
}

async function unlinkNodes(srcId, dstId, rel, callback) {
  try {
    const res = await fetch('/api/graph/unlink', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ src_id: srcId, dst_id: dstId, rel: rel }),
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Unlink failed');

    // Remove from in-memory edges
    state.edges = state.edges.filter(e => {
      const s = String(e.source.id || e.source);
      const t = String(e.target.id || e.target);
      return !((s === String(srcId) && t === String(dstId)) || (s === String(dstId) && t === String(srcId)));
    });
    computeTopology();
    reheatSimulation(0.25);

    if (callback) callback();
  } catch (err) {
    alert('Unlink failed: ' + err.message);
  }
}

// Populate Agent Link Dropdown
function populateAgentLinkDropdown() {
  const select = document.getElementById('agent-link-existing-select');
  if (!select) return;

  const topics = Object.keys(state.topics || {});
  let opts = '<option value="">Link to graph node (optional)...</option>';
  if (topics.length > 0) {
    opts += `<optgroup label="Educational Curricula">`;
    topics.forEach(t => {
      const matchNode = state.nodes.find(n => n.topic === t && n.is_curriculum);
      const id = matchNode ? matchNode.id : '';
      opts += `<option value="${id}">${escapeHtml(t.replace(/_/g, ' '))}</option>`;
    });
    opts += `</optgroup>`;
  }
  select.innerHTML = opts;
}

// ── Bind Code Studio UI Events ──────────────────────────────────────────────
function bindCodeStudioEvents() {
  // Workspace select change
  const wsSelect = document.getElementById('code-workspace-select');
  if (wsSelect && !wsSelect.dataset.bound) {
    wsSelect.dataset.bound = 'true';
    wsSelect.addEventListener('change', (e) => {
      switchWorkspace(e.target.value);
    });
  }

  // Refresh files
  const btnRefreshFiles = document.getElementById('btn-refresh-workspace-files');
  if (btnRefreshFiles && !btnRefreshFiles.dataset.bound) {
    btnRefreshFiles.dataset.bound = 'true';
    btnRefreshFiles.addEventListener('click', () => {
      if (state.codeStudio.currentWorkspace) {
        switchWorkspace(state.codeStudio.currentWorkspace, state.codeStudio.activeFilePath);
      }
    });
  }

  // Save File button
  const btnSave = document.getElementById('btn-code-save-file');
  if (btnSave && !btnSave.dataset.bound) {
    btnSave.dataset.bound = 'true';
    btnSave.addEventListener('click', saveActiveCodeFile);
  }

  // Editor text change -> dirty indicator
  const editorTextarea = document.getElementById('code-editor-textarea');
  if (editorTextarea && !editorTextarea.dataset.bound) {
    editorTextarea.dataset.bound = 'true';
    editorTextarea.addEventListener('input', () => {
      state.codeStudio.isDirty = true;
      document.getElementById('editor-dirty-indicator').style.display = 'inline';
    });
    // Keyboard shortcut Ctrl+S
    editorTextarea.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        saveActiveCodeFile();
      }
    });
  }

  // Offline / Online Mode Toggle
  const btnModeOffline = document.getElementById('btn-mode-offline');
  const btnModeOnline = document.getElementById('btn-mode-online');
  if (btnModeOffline && btnModeOnline && !btnModeOffline.dataset.bound) {
    btnModeOffline.dataset.bound = 'true';
    btnModeOffline.addEventListener('click', () => {
      state.codeStudio.offlineMode = true;
      btnModeOffline.classList.add('active');
      btnModeOnline.classList.remove('active');
    });
    btnModeOnline.addEventListener('click', () => {
      state.codeStudio.offlineMode = false;
      btnModeOnline.classList.add('active');
      btnModeOffline.classList.remove('active');
    });
  }

  // Model selector
  const modelSelect = document.getElementById('code-model-select');
  if (modelSelect && !modelSelect.dataset.bound) {
    modelSelect.dataset.bound = 'true';
    modelSelect.addEventListener('change', (e) => {
      state.codeStudio.activeModel = e.target.value;
    });
  }

  // Run Tests button in header
  const btnRunTests = document.getElementById('btn-code-run-tests');
  if (btnRunTests && !btnRunTests.dataset.bound) {
    btnRunTests.dataset.bound = 'true';
    btnRunTests.addEventListener('click', () => {
      document.getElementById('code-term-cmd-preset').value = 'pytest';
      document.getElementById('code-term-custom-cmd').style.display = 'none';
      executeTerminalCommand();
    });
  }

  // View in Graph button
  const btnViewInGraph = document.getElementById('btn-view-in-graph');
  if (btnViewInGraph && !btnViewInGraph.dataset.bound) {
    btnViewInGraph.dataset.bound = 'true';
    btnViewInGraph.addEventListener('click', () => {
      document.querySelector('[data-tab="graph"]').click();
      const projRef = `workspace:${state.codeStudio.currentWorkspace}`;
      const projNode = state.nodes.find(n => n.ref === projRef || n.name === state.codeStudio.currentWorkspace);
      if (projNode) {
        focusOnHub(projNode.id);
      } else {
        state.activeFilter = 'workspace';
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.toggle('active', b.dataset.filter === 'workspace'));
        reheatSimulation(0.35);
        setTimeout(() => zoomToFit(true), 100);
      }
    });
  }

  // Bottom pane tab buttons
  const tabBtnTerminal = document.getElementById('tab-btn-terminal');
  const tabBtnAgent = document.getElementById('tab-btn-agent');
  if (tabBtnTerminal && tabBtnAgent && !tabBtnTerminal.dataset.bound) {
    tabBtnTerminal.dataset.bound = 'true';
    tabBtnTerminal.addEventListener('click', () => {
      tabBtnTerminal.classList.add('active');
      tabBtnAgent.classList.remove('active');
      document.getElementById('pane-terminal').classList.add('active');
      document.getElementById('pane-agent').classList.remove('active');
    });
    tabBtnAgent.addEventListener('click', () => {
      tabBtnAgent.classList.add('active');
      tabBtnTerminal.classList.remove('active');
      document.getElementById('pane-agent').classList.add('active');
      document.getElementById('pane-terminal').classList.remove('active');
    });
  }

  // Terminal Preset change
  const cmdPreset = document.getElementById('code-term-cmd-preset');
  const customCmdInput = document.getElementById('code-term-custom-cmd');
  if (cmdPreset && !cmdPreset.dataset.bound) {
    cmdPreset.dataset.bound = 'true';
    cmdPreset.addEventListener('change', (e) => {
      customCmdInput.style.display = e.target.value === 'custom' ? 'block' : 'none';
    });
  }

  // Execute terminal button
  const btnExecCmd = document.getElementById('btn-execute-term-cmd');
  if (btnExecCmd && !btnExecCmd.dataset.bound) {
    btnExecCmd.dataset.bound = 'true';
    btnExecCmd.addEventListener('click', executeTerminalCommand);
  }

  // Clear terminal
  const btnClearTerm = document.getElementById('btn-clear-terminal');
  if (btnClearTerm && !btnClearTerm.dataset.bound) {
    btnClearTerm.dataset.bound = 'true';
    btnClearTerm.addEventListener('click', () => {
      document.getElementById('code-terminal-output').innerHTML = '<span class="term-dim">Terminal cleared. Ready for execution.</span>';
    });
  }

  // Agent Generate Code button
  const btnRunAgent = document.getElementById('btn-run-agent-code');
  if (btnRunAgent && !btnRunAgent.dataset.bound) {
    btnRunAgent.dataset.bound = 'true';
    btnRunAgent.addEventListener('click', runAgentCodePrompt);
  }

  // Link Active File button
  const btnLinkActive = document.getElementById('btn-link-active-file');
  if (btnLinkActive && !btnLinkActive.dataset.bound) {
    btnLinkActive.dataset.bound = 'true';
    btnLinkActive.addEventListener('click', () => {
      if (!state.codeStudio.activeFile) {
        alert('Please select a file to link.');
        return;
      }
      openLinkModal({
        id: state.codeStudio.activeFile.node_id,
        name: state.codeStudio.activeFile.name,
        kind: 'file',
        ref: state.codeStudio.activeFile.ref,
      });
    });
  }

  // Modal events: Link Node
  const closeLinkBtn = document.getElementById('close-modal-link');
  const cancelLinkBtn = document.getElementById('btn-cancel-link');
  const confirmLinkBtn = document.getElementById('btn-confirm-create-link');
  const searchLinkInput = document.getElementById('link-target-search-input');
  const clearTargetBtn = document.getElementById('btn-clear-target-selection');

  if (closeLinkBtn && !closeLinkBtn.dataset.bound) {
    closeLinkBtn.dataset.bound = 'true';
    closeLinkBtn.addEventListener('click', closeLinkModal);
    if (cancelLinkBtn) cancelLinkBtn.addEventListener('click', closeLinkModal);
    if (confirmLinkBtn) confirmLinkBtn.addEventListener('click', confirmCreateLink);
    if (clearTargetBtn) {
      clearTargetBtn.addEventListener('click', () => {
        state.linkModal.selectedTarget = null;
        document.getElementById('selected-target-display').style.display = 'none';
        document.getElementById('btn-confirm-create-link').disabled = true;
      });
    }
    if (searchLinkInput) {
      searchLinkInput.addEventListener('input', (e) => {
        clearTimeout(state.linkModal.searchTimer);
        const q = e.target.value.trim();
        state.linkModal.searchTimer = setTimeout(() => searchTargetNodes(q), 180);
      });
    }
  }

  // Modal events: Create Workspace Project
  const btnOpenCreateWs = document.getElementById('btn-create-workspace-modal');
  const modalCreateWs = document.getElementById('modal-create-workspace');
  const closeCreateWs = document.getElementById('close-modal-create-ws');
  const cancelCreateWs = document.getElementById('btn-cancel-create-ws');
  const confirmCreateWs = document.getElementById('btn-confirm-create-ws');

  if (btnOpenCreateWs && !btnOpenCreateWs.dataset.bound) {
    btnOpenCreateWs.dataset.bound = 'true';
    btnOpenCreateWs.addEventListener('click', () => {
      document.getElementById('create-ws-name').value = '';
      document.getElementById('create-ws-desc').value = '';
      modalCreateWs.style.display = 'flex';
    });
    if (closeCreateWs) closeCreateWs.addEventListener('click', () => modalCreateWs.style.display = 'none');
    if (cancelCreateWs) cancelCreateWs.addEventListener('click', () => modalCreateWs.style.display = 'none');
    if (confirmCreateWs) {
      confirmCreateWs.addEventListener('click', async () => {
        const name = document.getElementById('create-ws-name').value.trim();
        const desc = document.getElementById('create-ws-desc').value.trim();
        if (!name) {
          alert('Project name is required.');
          return;
        }
        confirmCreateWs.disabled = true;
        confirmCreateWs.innerHTML = '<span class="spinner"></span> Creating...';
        try {
          const res = await fetch('/api/workspace/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description: desc }),
          });
          const data = await res.json();
          if (!res.ok || data.error) throw new Error(data.error || 'Creation failed');
          modalCreateWs.style.display = 'none';
          await loadWorkspacesList(data.name);
          await loadGraphData();
          await loadStats();
        } catch (err) {
          alert('Failed to create workspace: ' + err.message);
        } finally {
          confirmCreateWs.disabled = false;
          confirmCreateWs.innerHTML = 'Create &amp; Index';
        }
      });
    }
  }
}

