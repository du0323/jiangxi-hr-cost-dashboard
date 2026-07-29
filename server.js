const express = require('express');
const session = require('express-session');
const bcrypt = require('bcryptjs');
const fs = require('fs');
const path = require('path');

const app = express();

if (!process.env.PORT) process.env.PORT = '3000';
if (!process.env.DATA_DIR) process.env.DATA_DIR = 'data';
if (!process.env.ZONE_NAME) process.env.ZONE_NAME = '安徽战区';

const PORT = parseInt(process.env.PORT, 10);
const DATA_DIR = path.join(__dirname, process.env.DATA_DIR);
const ZONE_NAME = process.env.ZONE_NAME;
const USERS_FILE = path.join(__dirname, 'users.json');
const IS_PRODUCTION = process.env.NODE_ENV === 'production';
const SESSION_SECRET = process.env.SESSION_SECRET || 'dev-session-secret';

if (IS_PRODUCTION && !process.env.SESSION_SECRET) {
  throw new Error('SESSION_SECRET is required in production');
}

app.set('trust proxy', 1);
app.use(express.json({ limit: '20mb' }));
app.use(express.static(path.join(__dirname, 'public')));
app.use(session({
  secret: SESSION_SECRET,
  resave: false,
  saveUninitialized: false,
  cookie: {
    maxAge: 12 * 60 * 60 * 1000,
    httpOnly: true,
    sameSite: 'lax',
    secure: IS_PRODUCTION
  }
}));

// ── Helpers ────────────────────────────────────────────────
function getUsers() {
  return JSON.parse(fs.readFileSync(USERS_FILE, 'utf8'));
}

function saveUsers(users) {
  fs.writeFileSync(USERS_FILE, JSON.stringify(users, null, 2));
}

function listMonths() {
  if (!fs.existsSync(DATA_DIR)) return [];
  return fs.readdirSync(DATA_DIR)
    .filter(f => f.endsWith('.json'))
    .map(f => f.replace('.json', ''))
    .sort().reverse();
}

function loadMonth(ym) {
  const f = path.join(DATA_DIR, `${ym}.json`);
  if (!fs.existsSync(f)) return null;
  return normalizeMonthData(JSON.parse(fs.readFileSync(f, 'utf8')));
}

function saveMonth(ym, data) {
  if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(path.join(DATA_DIR, `${ym}.json`), JSON.stringify(normalizeMonthData(data)));
}

function pickPreferredEmployee(current, candidate) {
  if (!current) return candidate;
  const score = emp => {
    let value = 0;
    if (emp && String(emp.store || '').trim()) value += 4;
    if (emp && String(emp.dept || '').trim()) value += 2;
    if (emp && String(emp.cat || '').trim()) value += 2;
    if (emp && Number(emp.labor || 0) > 0) value += 8;
    if (emp && String(emp.title || '').trim()) value += 1;
    return value;
  };
  return score(candidate) > score(current) ? candidate : current;
}

function normalizeEmployees(employees, pendingSource) {
  const pending = { ...(pendingSource || {}) };
  const dedupedById = {};
  const others = [];

  (employees || []).forEach(raw => {
    const emp = { ...raw };
    const id = String(emp.id || '').trim();
    const store = String(emp.store || '').trim();
    const dept = String(emp.dept || '').trim();
    const cat = String(emp.cat || '').trim();
    const labor = Number(emp.labor || 0);
    const orders = emp.orders == null ? null : emp.orders;
    const isPlaceholder = labor === 0 && !store && !dept && !cat;

    if (isPlaceholder) {
      if (id && orders != null) pending[id] = { id, name: String(emp.name || '').trim(), orders };
      return;
    }

    if (!id) {
      others.push(emp);
      return;
    }

    const existing = dedupedById[id];
    const preferred = pickPreferredEmployee(existing, emp);
    const secondary = preferred === emp ? existing : emp;
    if (secondary && secondary.orders != null && preferred.orders == null) preferred.orders = secondary.orders;
    dedupedById[id] = preferred;
  });

  const normalized = [...others, ...Object.values(dedupedById)];
  normalized.forEach(emp => {
    const id = String(emp.id || '').trim();
    if (!id || !pending[id] || pending[id].orders == null || emp.orders != null) return;
    emp.orders = pending[id].orders;
    delete pending[id];
  });

  const employeeNameCounts = {};
  const pendingNameCounts = {};
  normalized.forEach(emp => {
    const name = String(emp.name || '').trim();
    if (!name) return;
    employeeNameCounts[name] = (employeeNameCounts[name] || 0) + 1;
  });
  Object.values(pending).forEach(entry => {
    const name = String((entry && entry.name) || '').trim();
    if (!name) return;
    pendingNameCounts[name] = (pendingNameCounts[name] || 0) + 1;
  });

  Object.entries(pending).forEach(([id, entry]) => {
    const name = String((entry && entry.name) || '').trim();
    if (!name || employeeNameCounts[name] !== 1 || pendingNameCounts[name] !== 1) return;
    const target = normalized.find(emp => String(emp.name || '').trim() === name && emp.orders == null);
    if (!target) return;
    target.orders = entry.orders;
    delete pending[id];
  });

  return { employees: normalized, pending };
}

function normalizeMonthData(data) {
  if (!data || typeof data !== 'object') return data;
  const normalized = {
    ...data,
    retailStores: data.retailStores || [],
    supportDepts: data.supportDepts || [],
    deliveryStores: data.deliveryStores || [],
    deliverySupport: data.deliverySupport || [],
    employees: data.employees || []
  };
  const { employees, pending } = normalizeEmployees(normalized.employees, normalized._pendingEmployeeOrders);
  normalized.employees = employees;
  if (Object.keys(pending).length) normalized._pendingEmployeeOrders = pending;
  else delete normalized._pendingEmployeeOrders;
  return normalized;
}

function deleteMonth(ym) {
  const f = path.join(DATA_DIR, `${ym}.json`);
  if (fs.existsSync(f)) fs.unlinkSync(f);
}

// Role-based data filtering
function filterData(data, role) {
  if (!data) return null;
  if (role === 'admin') return data;
  if (role === 'retail') return {
    period: data.period,
    retailStores: data.retailStores || [],
    supportDepts: [],      // 隐藏零售战区支持
    deliveryStores: [],
    deliverySupport: [],
    employees: (data.employees||[]).filter(e => e.cat === '零售' || !e.cat)
  };
  if (role === 'delivery') return {
    period: data.period,
    retailStores: [],
    supportDepts: [],
    deliveryStores: data.deliveryStores || [],
    deliverySupport: [],   // 隐藏交付战区支持
    employees: (data.employees||[]).filter(e => e.cat === '交付' || !e.cat)
  };
  return null;
}

// ── Auth middleware ────────────────────────────────────────
function requireAuth(req, res, next) {
  if (!req.session.user) return res.status(401).json({ error: 'Unauthorized' });
  next();
}
function requireAdmin(req, res, next) {
  if (!req.session?.user || req.session.user.role !== 'admin')
    return res.status(403).json({ error: 'Forbidden: admin only' });
  next();
}

// ── Routes ─────────────────────────────────────────────────
app.get('/', (req, res) => {
  if (req.session.user) {
    res.sendFile(path.join(__dirname, 'public', 'dashboard.html'));
  } else {
    res.sendFile(path.join(__dirname, 'public', 'login.html'));
  }
});

// Personnel report page (auth required)
app.get('/report', requireAuth, (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'personnel-report.html'));
});

// Auth
app.post('/api/login', (req, res) => {
  const { username, password } = req.body;
  if (!username || !password) return res.status(400).json({ error: '请输入用户名和密码' });
  const user = getUsers().find(u => u.username === username);
  if (!user || !bcrypt.compareSync(password, user.password)) {
    return res.status(401).json({ error: '用户名或密码错误' });
  }
  req.session.user = { username: user.username, role: user.role, name: user.name };
  res.json({ success: true, user: req.session.user });
});

app.post('/api/logout', (req, res) => {
  req.session.destroy(() => res.json({ success: true }));
});

app.get('/api/me', requireAuth, (req, res) => {
  res.json(req.session.user);
});

app.get('/api/config', (req, res) => {
  res.json({ zoneName: ZONE_NAME });
});

// Month data
app.get('/api/months', requireAuth, (req, res) => {
  res.json(listMonths());
});

app.get('/api/data/:ym', requireAuth, (req, res) => {
  const data = loadMonth(req.params.ym);
  if (!data) return res.status(404).json({ error: 'Not found' });
  res.json(filterData(data, req.session.user.role));
});

app.post('/api/data/:ym', requireAdmin, (req, res) => {
  const { ym } = req.params;
  if (!/^\d{4}-\d{2}$/.test(ym)) return res.status(400).json({ error: 'Invalid month format' });
  saveMonth(ym, req.body);
  res.json({ success: true });
});

app.delete('/api/data/:ym', requireAdmin, (req, res) => {
  deleteMonth(req.params.ym);
  res.json({ success: true });
});

// User management (admin only)
app.get('/api/users', requireAdmin, (req, res) => {
  res.json(getUsers().map(u => ({ username: u.username, role: u.role, name: u.name })));
});

app.post('/api/users', requireAdmin, (req, res) => {
  const { username, password, role, name } = req.body;
  if (!username || !password || !role) return res.status(400).json({ error: '参数不完整' });
  if (!['admin','retail','delivery'].includes(role)) return res.status(400).json({ error: '无效角色' });
  const users = getUsers();
  if (users.find(u => u.username === username)) return res.status(409).json({ error: '用户名已存在' });
  users.push({ username, password: bcrypt.hashSync(password, 10), role, name: name || username });
  saveUsers(users);
  res.json({ success: true });
});

app.delete('/api/users/:username', requireAdmin, (req, res) => {
  if (req.params.username === req.session.user.username)
    return res.status(400).json({ error: '不能删除当前登录账号' });
  const users = getUsers().filter(u => u.username !== req.params.username);
  saveUsers(users);
  res.json({ success: true });
});

app.patch('/api/users/:username/password', requireAdmin, (req, res) => {
  const { password } = req.body;
  if (!password || password.length < 6) return res.status(400).json({ error: '密码至少6位' });
  const users = getUsers();
  const u = users.find(u => u.username === req.params.username);
  if (!u) return res.status(404).json({ error: '用户不存在' });
  u.password = bcrypt.hashSync(password, 10);
  saveUsers(users);
  res.json({ success: true });
});

// ── Offline Export ──────────────────────────────────────
app.get('/api/offline-export', requireAuth, (req, res) => {
  const months = listMonths();
  const allData = {};
  months.forEach(m => { allData[m] = loadMonth(m); });
  if (!Object.keys(allData).length) return res.status(404).json({ error: '无数据可导出' });

  const periodKeys = Object.keys(allData).sort();
  const embeddedData = JSON.stringify(allData);

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${ZONE_NAME}人力成本分析看板 · 离线版</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<style>
:root{--bg:#f0f5f4;--card:#fff;--border:#c8d8d6;--primary:#00726D;--primary-light:#e0f2f0;--primary-dark:#002D28;--fixed-color:#00726D;--perf-color:#CEA472;--green:#16a34a;--green-bg:#dcfce7;--red:#dc2626;--red-bg:#fee2e2;--orange:#d97706;--orange-bg:#fef3c7;--gold:#CEA472;--gold-bg:#fdf5eb;--gray:#666;--text:#333;--sub:#666}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);font-size:13px}
.header{background:linear-gradient(135deg,var(--primary-dark),var(--primary));color:#fff;padding:14px 20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.header h1{font-size:19px;font-weight:700}
.header .sub-info{font-size:11px;opacity:.8;margin-top:2px}
.period-select{background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.3);color:#fff;padding:6px 14px;border-radius:20px;font-size:13px;font-weight:600;cursor:pointer}
.period-select option{color:#333;background:#fff}
.tabs-container{padding:12px 20px 0}
.tab-nav{display:flex;gap:2px;border-bottom:2px solid var(--border)}
.tab-btn{padding:8px 18px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:600;color:var(--gray);border-bottom:2px solid transparent;margin-bottom:-2px;border-radius:6px 6px 0 0;transition:all .15s}
.tab-btn:hover{background:var(--primary-light);color:var(--primary)}
.tab-btn.active{color:var(--primary);border-bottom-color:var(--primary);background:var(--primary-light)}
.tab-panel{display:none;padding:14px 0 24px}.tab-panel.active{display:block}
.filter-bar{background:var(--card);border-radius:10px;border:1px solid var(--border);padding:12px 14px;margin-bottom:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.filter-bar label{font-size:11px;color:var(--gray);font-weight:600;white-space:nowrap}
.filter-select{padding:5px 10px;border-radius:6px;border:1px solid var(--border);font-size:12px;background:#f8fafc;color:var(--text);cursor:pointer;min-width:110px}
.filter-sep{width:1px;height:22px;background:var(--border)}
.filter-clear{padding:5px 12px;border-radius:6px;border:1px solid var(--border);background:#fff;font-size:12px;cursor:pointer;color:var(--gray);white-space:nowrap}
.filter-clear:hover{color:var(--red);border-color:var(--red)}
.filter-count{font-size:11px;color:var(--gray);margin-left:auto}
.ms-wrap{position:relative}
.ms-trigger{display:flex;align-items:center;gap:6px;padding:5px 10px;border-radius:6px;border:1px solid var(--border);font-size:12px;background:#f8fafc;color:var(--text);cursor:pointer;min-width:130px;user-select:none;white-space:nowrap}
.ms-trigger svg{margin-left:auto;flex-shrink:0;transition:transform .15s}
.ms-trigger.open svg{transform:rotate(180deg)}
.ms-panel{position:absolute;top:calc(100% + 4px);left:0;background:#fff;border:1px solid var(--border);border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,.13);z-index:200;min-width:190px;display:none;flex-direction:column}
.ms-panel.open{display:flex}
.ms-search-box{padding:7px 10px;border-bottom:1px solid var(--border)}
.ms-search-box input{width:100%;border:1px solid var(--border);border-radius:5px;padding:4px 8px;font-size:12px;outline:none}
.ms-all-row{padding:6px 12px;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer}
.ms-all-row:hover{background:var(--primary-light)}
.ms-list{overflow-y:auto;max-height:210px}
.ms-item{display:flex;align-items:center;gap:8px;padding:5px 12px;font-size:12px;cursor:pointer}
.ms-item:hover{background:var(--primary-light)}
.ms-item input,.ms-all-row input{accent-color:var(--primary);cursor:pointer}
.ms-count-badge{background:var(--primary);color:#fff;border-radius:10px;padding:1px 7px;font-size:11px;font-weight:700;margin-left:4px}
.intern-tag{font-size:9px;color:var(--gray);margin-left:2px;cursor:help;white-space:nowrap}
.section-title{font-size:13px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:7px}
.section-title::before{content:'';width:3px;height:13px;background:var(--primary);border-radius:2px;display:inline-block}
.card{background:var(--card);border-radius:10px;border:1px solid var(--border);padding:14px;margin-bottom:12px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.summary-row{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:12px}
.summary-card{background:var(--card);border-radius:10px;padding:10px 14px;border:1px solid var(--border);border-top:3px solid var(--primary)}
.summary-card.green{border-top-color:var(--green)}.summary-card.orange{border-top-color:var(--orange)}
.summary-card .s-label{font-size:10px;color:var(--gray)}
.summary-card .s-val{font-size:18px;font-weight:700}
.summary-card .s-sub{font-size:10px;color:var(--sub);margin-top:2px}
.chart-box{position:relative}
.chart-legend{display:flex;gap:16px;margin-bottom:6px;font-size:11px;color:var(--gray)}
.legend-item{display:flex;align-items:center;gap:5px}
.legend-dot{width:9px;height:9px;border-radius:3px}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
thead th{background:#f8fafc;color:var(--gray);font-weight:600;padding:8px 9px;text-align:center;border-bottom:2px solid var(--border);white-space:nowrap}
thead th:first-child{text-align:left}
tbody tr:hover{background:#f8fafc}
tbody td{padding:7px 9px;border-bottom:1px solid var(--border);text-align:center;white-space:nowrap}
tbody td:first-child{text-align:left;font-weight:600}
tbody tr:last-child td{border-bottom:none}
.total-row td{font-weight:700;background:#f0f9ff;color:var(--primary-dark)}
.no-data{text-align:center;padding:24px;color:var(--gray);font-size:12px}
.notice{background:#fefce8;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;font-size:12px;margin-bottom:12px;color:#92400e}
.ratio-bar{display:flex;height:13px;border-radius:3px;overflow:hidden;min-width:65px;gap:1px}
.ratio-fixed{background:var(--fixed-color)}.ratio-perf{background:var(--perf-color)}
.rate{display:inline-block;padding:2px 8px;border-radius:10px;font-weight:700;font-size:11px}
.rate-good{background:var(--green-bg);color:var(--green)}.rate-mid{background:var(--orange-bg);color:var(--orange)}.rate-bad{background:var(--red-bg);color:var(--red)}
.export-btn{display:flex;align-items:center;gap:4px;margin-left:auto;padding:4px 10px;border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:11px;font-weight:600;color:var(--gray);background:#f8fafc}
.export-btn:hover{color:var(--primary);border-color:var(--primary);background:var(--primary-light)}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--primary-dark);color:#fff;padding:10px 24px;border-radius:8px;font-size:13px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,.25);z-index:9999;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}
</style>
</head>
<body>
<div class="header">
  <div><h1>${ZONE_NAME}人力成本分析看板</h1><div class="sub-info">离线版 · 数据含 ${periodKeys[0]} ~ ${periodKeys[periodKeys.length-1]}</div></div>
  <select class="period-select" id="periodSelect" onchange="switchPeriod(this.value)">
    ${periodKeys.map(m => '<option value="'+m+'">'+ (allData[m]?.period || m) +'</option>').join('')}
  </select>
</div>

<div class="tabs-container">
  <div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('retail')">零售明细</button>
    <button class="tab-btn" onclick="switchTab('personnel')">人员明细</button>
  </div>
  <div class="tab-panel active" id="tab-retail">
    <div class="filter-bar">
      <label>所属部门</label><select class="filter-select" id="rFilterDept" onchange="applyRetailFilters()"><option value="">全部</option></select>
      <div class="filter-sep"></div>
      <label>门店</label>
      <div class="ms-wrap"><div class="ms-trigger" id="rMsTrigger" onclick="rToggleMsPanel()"><span id="rMsLabel">全部门店</span><svg viewBox="0 0 10 6" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 1l4 4 4-4"\/></svg></div>
        <div class="ms-panel" id="rMsPanel"><div class="ms-search-box"><input type="text" placeholder="搜索门店…" id="rMsSearch" oninput="rFilterMsOptions(this.value)"></div>
        <label class="ms-all-row"><input type="checkbox" id="rMsSelectAll" onchange="rMsToggleAll(this)"> 全选</label><div class="ms-list" id="rMsList"></div></div></div>
      <div class="filter-sep"></div>
      <label>达成状态</label>
      <select class="filter-select" id="rFilterRate" onchange="applyRetailFilters()" style="min-width:100px"><option value="">全部</option><option value="exceed">超额完成 ≥100%</option><option value="good">达标 85-100%</option><option value="mid">偏低 70-85%</option><option value="low">未达标 &lt;70%</option></select>
      <button class="filter-clear" onclick="clearRetailFilters()">清除筛选</button>
      <span class="filter-count" id="rFilterCount"></span>
    </div>
    <div class="summary-row" id="retailSummaryRow"></div>
    <div class="notice" id="retailNotice"></div>
    <div class="card"><div class="section-title" id="retailTableTitle">零售门店综合分析<button class="export-btn" onclick="exportRetailTable()"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"\/><polyline points="7 10 12 15 17 10"\/><line x1="12" y1="15" x2="12" y2="3"\/></svg>导出 Excel</button></div>
      <div class="table-wrap"><table><thead id="retailThead"></thead><tbody id="retailTbody"></tbody></table></div></div>
    <div class="card"><div class="section-title">补充成本明细（含环比）<button class="export-btn" onclick="exportCostTable()"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"\/><polyline points="7 10 12 15 17 10"\/><line x1="12" y1="15" x2="12" y2="3"\/></svg>导出 Excel</button></div>
      <div class="table-wrap"><table><thead id="costThead"></thead><tbody id="costTbody"></tbody></table></div></div>
    <div class="grid-2"><div class="card"><div class="section-title">门店定单达成分析</div><div class="chart-box" style="height:300px"><canvas id="chartOrderRate"></canvas></div></div><div class="card"><div class="section-title">人均总成本分布</div><div class="chart-box" style="height:300px"><canvas id="chartCostDist"></canvas></div></div></div>
    <div class="card"><div class="section-title">人效 vs 人均总成本 · 四象限分析</div><div class="chart-box" style="height:420px"><canvas id="chartEffCost"></canvas></div><div id="retailQuadrantSummary"></div></div></div>
  <div class="tab-panel" id="tab-personnel">
    <div class="filter-bar">
      <label>所属部门</label><select class="filter-select" id="pFilterDept" onchange="popPersonnelDeptChange()"><option value="">全部</option></select>
      <div class="filter-sep"></div>
      <label>门店</label>
      <div class="ms-wrap"><div class="ms-trigger" id="pMsTrigger" onclick="pToggleMsPanel()"><span id="pMsLabel">全部门店</span><svg viewBox="0 0 10 6" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 1l4 4 4-4"\/></svg></div>
        <div class="ms-panel" id="pMsPanel"><div class="ms-search-box"><input type="text" placeholder="搜索门店…" id="pMsSearch" oninput="pFilterMsOptions(this.value)"></div>
        <label class="ms-all-row"><input type="checkbox" id="pMsSelectAll" onchange="pMsToggleAll(this)"> 全选</label><div class="ms-list" id="pMsList"></div></div></div>
      <div class="filter-sep"></div>
      <label>岗位</label>
      <div class="ms-wrap"><div class="ms-trigger" id="pTitleMsTrigger" onclick="pToggleTitleMsPanel()"><span id="pTitleMsLabel">全部岗位</span><svg viewBox="0 0 10 6" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 1l4 4 4-4"\/></svg></div>
        <div class="ms-panel" id="pTitleMsPanel"><div class="ms-search-box"><input type="text" placeholder="搜索岗位…" id="pTitleMsSearch" oninput="pFilterTitleMsOptions(this.value)"></div>
        <label class="ms-all-row"><input type="checkbox" id="pTitleMsSelectAll" onchange="pTitleMsToggleAll(this)"> 全选</label><div class="ms-list" id="pTitleMsList"></div></div></div>
      <button class="filter-clear" onclick="clearPersonnelFilters()">清除筛选</button>
      <span style="margin-left:auto;font-size:11px;color:var(--gray)" id="pCountInfo"></span>
    </div>
    <div class="card"><div class="section-title">个人成本 vs 定单量 四象限分析</div><div class="chart-box" style="height:400px"><canvas id="chartPersonnel"></canvas></div></div>
    <div id="personnelQuadrantSummary"></div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
var ALL_DATA = ${embeddedData};
var ALL_PERIODS = ${JSON.stringify(periodKeys)};
var charts = {};
var currentPeriod = ALL_PERIODS[ALL_PERIODS.length-1];
function getData(){return ALL_DATA[currentPeriod];}
function getPrevData(){var i=ALL_PERIODS.indexOf(currentPeriod);if(i<ALL_PERIODS.length-1)return ALL_DATA[ALL_PERIODS[i+1]];return null;}
function fmt(n){return(n||0).toLocaleString('zh-CN');}
function median(a){if(!a.length)return 0;var s=[].concat(a).sort(function(x,y){return x-y;});var m=Math.floor(s.length/2);return s.length%2?s[m]:(s[m-1]+s[m])/2;}
function destroyChart(i){if(charts[i]){charts[i].destroy();delete charts[i];}}
function showToast(t){var e=document.getElementById('toast');e.textContent=t;e.classList.add('show');setTimeout(function(){e.classList.remove('show');},2500);}
function rateClass(r){if(r>=1)return'rate rate-good';if(r>=0.85)return'rate rate-mid';return'rate rate-bad';}
function fixedBadge(f){if(f>=50)return'<span class=\\"rate rate-bad\\">'+f+'%</span>';if(f>=40)return'<span class=\\"rate rate-mid\\">'+f+'%</span>';return'<span class=\\"rate rate-good\\">'+f+'%</span>';}
function momBadge(c,p){if(!p)return'<span style=\\"color:var(--gray);font-size:10px\\">—</span>';var x=(c-p)/p*100;if(x<0)return'<span style=\\"color:var(--green);font-weight:600\\">▼ '+Math.abs(x).toFixed(1)+'%</span>';if(x>0)return'<span style=\\"color:var(--red);font-weight:600\\">▲ '+x.toFixed(1)+'%</span>';return'<span style=\\"color:var(--gray)\\">0%</span>';}
function addExportHeaderStyle(ws){var r=XLSX.utils.decode_range(ws['!ref']);for(var C=r.s.c;C<=r.e.c;C++){var c=XLSX.utils.encode_cell({r:0,c:C});if(ws[c])ws[c].s={font:{bold:true},fill:{fgColor:{rgb:'002D28'}}};}}
function switchPeriod(ym){currentPeriod=ym;renderAll();}
function switchTab(id){document.querySelectorAll('.tab-btn').forEach(function(b,i){var ids=['retail','personnel'];b.classList.toggle('active',ids[i]===id);});document.querySelectorAll('.tab-panel').forEach(function(p){p.style.display='none';});document.getElementById('tab-'+id).style.display='block';}
function renderAll(){destroyChart('chartOrderRate');destroyChart('chartCostDist');destroyChart('chartEffCost');destroyChart('chartPersonnel');renderRetail();renderPersonnel();}
function renderRetail(){initRetailFilters();}
function renderRetailCharts(){var arr=getRetailData();var withOrders=arr.filter(function(s){return s.orders_actual!=null;});var sorted2=[].concat(withOrders).sort(function(a,b){return a.orders_actual/a.orders_target-b.orders_actual/b.orders_target;});destroyChart('chartOrderRate');if(sorted2.length){charts.chartOrderRate=new Chart(document.getElementById('chartOrderRate'),{type:'bar',data:{labels:sorted2.map(function(s){return s.name.replace('零售中心','').replace('（外展店）','[外展]').substring(0,10);}),datasets:[{label:'实际定单',data:sorted2.map(function(s){return s.orders_actual;}),backgroundColor:sorted2.map(function(s){return s.orders_actual>=s.orders_target?'#16a34a':'#00726D';}),borderRadius:3,yAxisID:'y'},{label:'目标定单',data:sorted2.map(function(s){return s.orders_target;}),type:'line',borderColor:'#CEA472',borderWidth:2,pointRadius:3,fill:false,yAxisID:'y'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}}},scales:{x:{grid:{display:false},ticks:{font:{size:9},maxRotation:45}},y:{beginAtZero:true}}}});}else{document.getElementById('chartOrderRate').getContext('2d').clearRect(0,0,999,999);}
destroyChart('chartCostDist');if(arr.length){var sortedCost=[].concat(arr).sort(function(a,b){return b.labor/b.count-a.labor/a.count;});var avg=arr.reduce(function(a,x){return a+x.labor/x.count;},0)/arr.length;charts.chartCostDist=new Chart(document.getElementById('chartCostDist'),{type:'bar',data:{labels:sortedCost.map(function(s){return s.name.replace('零售中心','').replace('（外展店）','[外展]').substring(0,10);}),datasets:[{label:'人均总成本',data:sortedCost.map(function(s){return s.count>0?Math.round(s.labor/s.count):0;}),backgroundColor:sortedCost.map(function(s){return s.labor/s.count>avg?'rgba(220,38,38,0.6)':'rgba(0,114,109,0.55)';}),borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return'人均 '+(ctx.raw/10000).toFixed(2)+'万元';}}}},scales:{x:{grid:{display:false},ticks:{font:{size:9},maxRotation:45}},y:{ticks:{callback:function(v){return v/10000+'万';}}}}}});}}

// RETAIL
function getRetailData(){return getData().retailStores||[];}
function rGetMsSelected(){return[...document.querySelectorAll('#rMsList input[type=checkbox]:checked')].map(function(cb){return cb.value;});}
function rMsSyncLabel(){var s=rGetMsSelected(),l=document.getElementById('rMsLabel');if(!s.length)l.textContent='全部门店';else if(s.length===1)l.textContent=s[0];else l.innerHTML='已选 <span class=\\"ms-count-badge\\">'+s.length+'</span> 家门店';}
function rMsSyncSelectAll(){var a=document.querySelectorAll('#rMsList input'),c=document.querySelectorAll('#rMsList input:checked'),sa=document.getElementById('rMsSelectAll');sa.indeterminate=c.length>0&&c.length<a.length;sa.checked=a.length>0&&c.length===a.length;}
function rToggleMsPanel(){var p=document.getElementById('rMsPanel'),t=document.getElementById('rMsTrigger'),o=p.classList.toggle('open');t.classList.toggle('open',o);if(o){document.getElementById('rMsSearch').value='';rFilterMsOptions('');}}
function rCloseMsPanel(){document.getElementById('rMsPanel').classList.remove('open');document.getElementById('rMsTrigger').classList.remove('open');}
function rFilterMsOptions(q){q=q.toLowerCase();document.querySelectorAll('#rMsList .ms-item').forEach(function(i){i.style.display=!q||i.dataset.name.toLowerCase().includes(q)?'':'none';});}
function rMsToggleAll(cb){document.querySelectorAll('#rMsList input').forEach(function(c){c.checked=cb.checked;});rMsSyncLabel();rMsSyncSelectAll();applyRetailFilters();}
function rPopulateDropdown(){var dept=document.getElementById('rFilterDept').value;var stores=getRetailData().filter(function(s){if(dept&&s.dept!==dept)return false;return true;}).map(function(s){return s.name;}).filter(function(v,i,a){return a.indexOf(v)===i;}).sort(function(a,b){return a.localeCompare(b,'zh');});var prev=rGetMsSelected().filter(function(n){return stores.includes(n);});document.getElementById('rMsList').innerHTML=stores.map(function(n){return '<label class=\\"ms-item\\" data-name=\\"'+n+'\\"><input type=\\"checkbox\\" value=\\"'+n+'\\" onchange=\\"rMsSyncLabel();rMsSyncSelectAll();applyRetailFilters()\\"'+(prev.includes(n)?' checked':'')+'> '+n+'</label>';}).join('');rMsSyncLabel();rMsSyncSelectAll();}
document.addEventListener('click',function(e){var w=document.getElementById('rMsPanel')?.parentElement;if(w&&!w.contains(e.target))rCloseMsPanel();});
function initRetailFilters(){var stores=getRetailData();var depts=[...new Set(stores.filter(function(s){return s.dept;}).map(function(s){return s.dept;}))].sort(function(a,b){return a.localeCompare(b,'zh');});document.getElementById('rFilterDept').innerHTML='<option value=\\"\\">全部</option>'+depts.map(function(d){return '<option value=\\"'+d+'\\">'+d+'</option>';}).join('');rPopulateDropdown();applyRetailFilters();renderRetailCharts();}
function clearRetailFilters(){document.getElementById('rFilterDept').value='';document.getElementById('rFilterRate').value='';rPopulateDropdown();applyRetailFilters();}
function applyRetailFilters(){var dept=document.getElementById('rFilterDept').value,stores=rGetMsSelected(),rate=document.getElementById('rFilterRate').value;var filtered=getRetailData().filter(function(s){if(dept&&s.dept!==dept)return false;if(stores.length&&!stores.includes(s.name))return false;if(rate){var r=s.orders_actual!=null&&s.orders_target>0?s.orders_actual/s.orders_target:null;if(r===null)return false;if(rate==='exceed'&&r<1)return false;if(rate==='good'&&(r<0.85||r>=1))return false;if(rate==='mid'&&(r<0.7||r>=0.85))return false;if(rate==='low'&&r>=0.7)return false;}return true;});document.getElementById('rFilterCount').textContent=filtered.length+'/'+getRetailData().length+'家';renderRetailTable(filtered);}
function renderRetailTable(sorted){var prev=getPrevData();var pm={};if(prev&&prev.retailStores)prev.retailStores.forEach(function(s){pm[s.name]=s;});if(!sorted.length){document.getElementById('retailTbody').innerHTML='<tr><td colspan=\\"16\\" class=\\"no-data\\">暂无符合条件的门店</td></tr>';renderRetailCost(sorted,pm);renderRetailQuadrant(sorted);return;}
if(window._retailSort&&window._retailSort.col){var sc=window._retailSort.col,dir=window._retailSort.dir;sorted=[].concat(sorted).sort(function(a,b){var va,vb;if(sc==='labor'){va=a.labor;vb=b.labor;}else if(sc==='fixed'){va=a.fixed;vb=b.fixed;}else if(sc==='perf'){va=a.perf;vb=b.perf;}else if(sc==='count'){va=a.count;vb=b.count;}else if(sc==='fp'){va=a.fixed/a.labor;vb=b.fixed/b.labor;}else if(sc==='orders_actual'){va=a.orders_actual||0;vb=b.orders_actual||0;}else if(sc==='orders_target'){va=a.orders_target||0;vb=b.orders_target||0;}else if(sc==='rate'){va=a.orders_actual!=null&&a.orders_target>0?a.orders_actual/a.orders_target:-1;vb=b.orders_actual!=null&&b.orders_target>0?b.orders_actual/b.orders_target:-1;}else if(sc==='avg'){va=a.count>0?a.labor/a.count:0;vb=b.count>0?b.labor/b.count:0;}else if(sc==='eff'){va=a.count>0&&a.orders_actual!=null?a.orders_actual/a.count:-1;vb=b.count>0&&b.orders_actual!=null?b.orders_actual/b.count:-1;}else if(sc==='cps'){va=a.orders_actual>0?a.labor/a.orders_actual:999999;vb=b.orders_actual>0?b.labor/b.orders_actual:999999;}else if(sc==='af'){va=a.count>0?a.fixed/a.count:0;vb=b.count>0?b.fixed/b.count:0;}else if(sc==='ap'){va=a.count>0?a.perf/a.count:0;vb=b.count>0?b.perf/b.count:0;}else{va=(a[sc]||'').toString();vb=(b[sc]||'').toString();}if(typeof va==='number'&&typeof vb==='number')return(va-vb)*dir;return(va||'').localeCompare(vb||'','zh')*dir;});}
var si=function(col){var a='',c=window._retailSort;if(c&&c.col===col){a=' <span class=\\"sort-indicator active\\">'+(c.dir===1?'▲':'▼')+'</span>';}else{a=' <span class=\\"sort-indicator\\">↕</span>';}return a;};
document.getElementById('retailThead').innerHTML='<tr><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'name\\')\\">门店'+si('name')+'</th><th>所属部门</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'count\\')\\">人数'+si('count')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'labor\\')\\">人工成本'+si('labor')+'</th><th>环比</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'fixed\\')\\">固定成本'+si('fixed')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'perf\\')\\">绩效成本'+si('perf')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'fp\\')\\">固浮比'+si('fp')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'af\\')\\">人均固定'+si('af')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'ap\\')\\">人均绩效'+si('ap')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'orders_actual\\')\\">定单实际'+si('orders_actual')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'orders_target\\')\\">定单目标'+si('orders_target')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'rate\\')\\">达成率'+si('rate')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'avg\\')\\">人均总成本'+si('avg')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'eff\\')\\">人效'+si('eff')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'cps\\')\\">人力CPS'+si('cps')+'</th></tr>';
var html='',to={l:0,f:0,p:0,c:0,ic:0,ot:0,tr:0,so:0,ac:0,tg:0};sorted.forEach(function(s){var fp=parseFloat((s.fixed/s.labor*100).toFixed(1));var r=s.orders_actual!=null&&s.orders_target>0?s.orders_actual/s.orders_target:null;var eff=s.count>0&&s.orders_actual!=null?(s.orders_actual/s.count).toFixed(2):'-';var cps=s.orders_actual>0?Math.round(s.labor/s.orders_actual):null;var af=s.count>0?fmt(Math.round(s.fixed/s.count)):'-';var ap=s.count>0?fmt(Math.round(s.perf/s.count)):'-';var bg=s.dept==='上海一部'?'#f0f7f7':'#f6f9f6';var ps=pm[s.name];var mc=ps?momBadge(s.labor,ps.labor):'<span style=\\"color:var(--gray);font-size:10px\\">—</span>';to.l+=s.labor;to.f+=s.fixed;to.p+=s.perf;to.c+=s.count;to.ic+=s.intern_count||0;to.ot+=s.overtime_legal||0;to.tr+=s.travel||0;to.so+=s.social||0;if(s.orders_actual!=null){to.ac+=s.orders_actual;to.tg+=s.orders_target;}html+='<tr style=\\"background:'+bg+'\\"><td title=\\"'+s.name+'\\">'+s.name.replace('零售中心','').replace('（外展店）','<small style=\\"color:var(--gray)\\">外展</small>')+'</td><td style=\\"color:var(--gray)\\">'+s.dept+'</td><td>'+(s.intern_count?'<strong>'+s.count+'</strong><span title=\\"含'+s.intern_count+'名实习生成本\\" class=\\"intern-tag\\">(+'+s.intern_count+'习)</span>':'<strong>'+s.count+'</strong>')+'</td><td>'+fmt(s.labor)+'</td><td>'+mc+'</td><td style=\\"color:var(--fixed-color)\\">'+fmt(s.fixed)+'</td><td style=\\"color:var(--perf-color)\\">'+fmt(s.perf)+'</td><td>'+fixedBadge(fp)+'</td><td style=\\"color:var(--fixed-color)\\">'+af+'</td><td style=\\"color:var(--perf-color)\\">'+ap+'</td><td><strong>'+(s.orders_actual!=null?s.orders_actual:'-')+'</strong></td><td>'+(s.orders_target!=null?s.orders_target:'-')+'</td><td>'+(r!=null?'<span class=\\"'+rateClass(r)+'\\">'+(r*100).toFixed(1)+'%</span>':'<span style=\\"color:var(--gray)\\">—</span>')+'</td><td>'+(s.count>0?fmt(Math.round(s.labor/s.count)):'-')+'</td><td>'+eff+'</td><td>'+(cps?fmt(cps):'-')+'</td></tr>';});
if(sorted.length>1){var tfp=parseFloat((to.f/to.l*100).toFixed(1));var tr=to.tg>0?to.ac/to.tg:null;html+='<tr class=\\"total-row\\"><td colspan=\\"2\\">筛选合计（'+sorted.length+'家）</td><td>'+to.c+(to.ic?'<span title=\\"含'+to.ic+'名实习生成本\\" class=\\"intern-tag\\">(+'+to.ic+'习)</span>':'')+'</td><td>'+fmt(to.l)+'</td><td>—</td><td>'+fmt(to.f)+'</td><td>'+fmt(to.p)+'</td><td>'+fixedBadge(tfp)+'</td><td>'+(to.c>0?fmt(Math.round(to.f/to.c)):'-')+'</td><td>'+(to.c>0?fmt(Math.round(to.p/to.c)):'-')+'</td><td><strong>'+to.ac+'</strong></td><td>'+to.tg+'</td><td>'+(tr!=null?'<span class=\\"'+rateClass(tr)+'\\">'+(tr*100).toFixed(1)+'%</span>':'—')+'</td><td>'+(to.c>0?fmt(Math.round(to.l/to.c)):'-')+'</td><td>'+(to.c>0&&to.ac>0?(to.ac/to.c).toFixed(2):'-')+'</td><td>'+(to.ac>0?fmt(Math.round(to.l/to.ac)):'-')+'</td></tr>';}
document.getElementById('retailTbody').innerHTML=html;renderRetailCost(sorted,pm);renderRetailQuadrant(sorted);}
function renderRetailCost(arr,pm){var html='',to={ot:0,tr:0,so:0,c:0};arr.forEach(function(s){var p=pm[s.name];html+='<tr><td title=\\"'+s.name+'\\">'+s.name.replace('零售中心','').replace('（外展店）','<small style=\\"color:var(--gray)\\">外展</small>')+'</td><td style=\\"color:var(--gray)\\">'+(s.dept||'')+'</td><td>'+(s.count||0)+'</td><td>'+fmt(s.overtime_legal||0)+'</td><td>'+(p?momBadge(s.overtime_legal||0,p.overtime_legal||0):'<span style=\\"color:var(--gray);font-size:10px\\">—</span>')+'</td><td>'+fmt(s.travel||0)+'</td><td>'+(p?momBadge(s.travel||0,p.travel||0):'<span style=\\"color:var(--gray);font-size:10px\\">—</span>')+'</td><td>'+fmt(s.social||0)+'</td><td>'+(p?momBadge(s.social||0,p.social||0):'<span style=\\"color:var(--gray);font-size:10px\\">—</span>')+'</td></tr>';to.ot+=s.overtime_legal||0;to.tr+=s.travel||0;to.so+=s.social||0;to.c+=s.count||0;});if(arr.length>1)html+='<tr class=\\"total-row\\"><td colspan=\\"2\\">合计（'+arr.length+'家）</td><td>'+to.c+'</td><td>'+fmt(to.ot)+'</td><td>—</td><td>'+fmt(to.tr)+'</td><td>—</td><td>'+fmt(to.so)+'</td><td>—</td></tr>';document.getElementById('costThead').innerHTML='<tr><th>门店</th><th>所属部门</th><th>人数</th><th>法定加班</th><th>环比</th><th>出差津贴</th><th>环比</th><th>社保公积金(企)</th><th>环比</th></tr>';document.getElementById('costTbody').innerHTML=html;}
function retailSortBy(col){if(!window._retailSort)window._retailSort={col:'',dir:1};if(window._retailSort.col===col)window._retailSort.dir*=-1;else{window._retailSort.col=col;window._retailSort.dir=1;}applyRetailFilters();}
function renderRetailQuadrant(arr){destroyChart('chartEffCost');var er=arr.filter(function(s){return s.count>0&&s.orders_actual!=null;}).map(function(s){return{name:s.name.replace('零售中心','').replace('（外展店）','(外展)').substring(0,12),fn:s.name,x:Math.round(s.labor/s.count),y:parseFloat((s.orders_actual/s.count).toFixed(2)),r:s.count};});var se=document.getElementById('retailQuadrantSummary');if(!er.length){se.innerHTML='<div style=\\"padding:14px;text-align:center;color:var(--gray);font-size:12px\\">暂无足够数据绘制四象限图</div>';return;}var mx=median(er.map(function(d){return d.x;})),my=median(er.map(function(d){return d.y;}));er.forEach(function(d){d.q=d.x>mx?(d.y>my?2:4):(d.y>my?1:3);});var Q={1:{l:'低成本·高人效',bg:'rgba(0,114,109,0.55)',bo:'#00726D',ab:'rgba(0,114,109,0.06)'},2:{l:'高成本·高人效',bg:'rgba(206,164,114,0.75)',bo:'#b07030',ab:'rgba(206,164,114,0.08)'},3:{l:'低成本·低人效',bg:'rgba(82,120,160,0.55)',bo:'#5278A0',ab:'rgba(82,120,160,0.06)'},4:{l:'高成本·低人效',bg:'rgba(220,38,38,0.6)',bo:'#dc2626',ab:'rgba(220,38,38,0.07)'}};var qp={id:'q',afterDraw:function(ch){var c=ch.ctx,l=ch.chartArea.left,r=ch.chartArea.right,t=ch.chartArea.top,b=ch.chartArea.bottom,x=ch.scales.x,y=ch.scales.y,px=x.getPixelForValue(mx),py=y.getPixelForValue(my);c.save();[[l,t,px-l,py-t,1],[px,t,r-px,py-t,2],[l,py,px-l,b-py,3],[px,py,r-px,b-py,4]].forEach(function(a){c.fillStyle=Q[a[4]].ab;c.fillRect(a[0],a[1],a[2],a[3]);});c.strokeStyle='#bbb';c.lineWidth=1;c.setLineDash([5,4]);c.beginPath();c.moveTo(px,t);c.lineTo(px,b);c.stroke();c.beginPath();c.moveTo(l,py);c.lineTo(r,py);c.stroke();c.setLineDash([]);c.font='10px sans-serif';c.fillStyle='#999';c.textAlign='center';c.fillText('中位 '+(mx/10000).toFixed(1)+'万',px,b+22);c.textAlign='right';c.fillText('中位 '+my,l-4,py+4);c.font='bold 10px PingFang SC,sans-serif';[[Q[1].l,l+5,t+13,'left','rgba(0,114,109,0.75)'],[Q[2].l,r-5,t+13,'right','rgba(160,100,30,0.75)'],[Q[3].l,l+5,b-6,'left','rgba(60,100,150,0.65)'],[Q[4].l,r-5,b-6,'right','rgba(180,30,30,0.75)']].forEach(function(a){c.fillStyle=a[4];c.textAlign=a[3];c.fillText(a[0],a[1],a[2]);});c.restore();}};charts.chartEffCost=new Chart(document.getElementById('chartEffCost'),{type:'bubble',data:{datasets:[1,2,3,4].map(function(q){return{label:Q[q].l,data:er.filter(function(d){return d.q===q;}).map(function(d){return{x:d.x,y:d.y,r:d.r};}),backgroundColor:Q[q].bg,borderColor:Q[q].bo,borderWidth:1.5};})},plugins:[qp],options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true,position:'top',labels:{boxWidth:10,font:{size:11},padding:12}},tooltip:{callbacks:{label:function(ctx){var d=er.filter(function(x){return x.x===ctx.raw.x&&x.y===ctx.raw.y;})[0];return '门店: '+(d?d.fn:'')+' | 人均成本 '+(ctx.raw.x/10000).toFixed(2)+'万 | 人效 '+ctx.raw.y+'单/人';}}}},scales:{x:{title:{display:true,text:'人均总成本（元）',font:{size:10}},ticks:{callback:function(v){return(v/10000).toFixed(1)+'万';}}},y:{title:{display:true,text:'人效（单/人）',font:{size:10}}}}}});var defs=[{q:1,ic:'⭐',ti:'低成本·高人效',de:'成本控制好且人效突出，是当前的标杆门店，可作为经验推广参考。',co:'#00726D',bg:'rgba(0,114,109,0.06)',bo:'rgba(0,114,109,0.2)'},{q:2,ic:'📈',ti:'高成本·高人效',de:'人效表现出色但成本偏高，建议深挖成本结构，优化固浮比或人员配置。',co:'#9a6c20',bg:'rgba(206,164,114,0.1)',bo:'rgba(180,130,50,0.35)'},{q:3,ic:'⚡',ti:'低成本·低人效',de:'成本可控，但单量产出不足，建议聚焦订单获取能力及员工激励机制。',co:'#3a6898',bg:'rgba(82,120,160,0.07)',bo:'rgba(82,120,160,0.25)'},{q:4,ic:'⚠️',ti:'高成本·低人效',de:'高投入低产出，需重点排查人员结构及运营效率，优先制定改善方案。',co:'#dc2626',bg:'rgba(220,38,38,0.06)',bo:'rgba(220,38,38,0.2)'}];se.innerHTML='<div style=\\"display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px\\">'+defs.map(function(d){var ppl=er.filter(function(s){return s.q===d.q;});var tags=ppl.length?ppl.map(function(s){return '<span style=\\"background:'+d.bg+';border:1px solid '+d.bo+';padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap;color:'+d.co+'\\">'+s.fn+'('+s.y+'单/'+fmt(s.x)+'元)</span>';}).join(' '):'<span style=\\"color:#aaa;font-size:11px\\">暂无门店</span>';return '<div style=\\"background:'+d.bg+';border:1px solid '+d.bo+';border-radius:8px;padding:12px 14px\\"><div style=\\"display:flex;align-items:center;gap:6px;margin-bottom:5px\\"><span style=\\"font-size:15px\\">'+d.ic+'</span><span style=\\"font-weight:700;font-size:13px;color:'+d.co+'\\">'+d.ti+'</span><span style=\\"margin-left:auto;background:'+d.co+';color:#fff;border-radius:10px;padding:1px 9px;font-size:11px;font-weight:700\\">'+ppl.length+'家</span></div><div style=\\"font-size:11px;color:#555;margin-bottom:8px;line-height:1.5\\">'+d.de+'</div><div style=\\"display:flex;flex-wrap:wrap;gap:4px\\">'+tags+'</div></div>';}).join('')+'</div>';}
function exportRetailTable(){var ar=getRetailData();var prev=getPrevData();var pm={};if(prev&&prev.retailStores)prev.retailStores.forEach(function(s){pm[s.name]=s;});var hd=['门店','所属部门','在编人数','实习生人数(成本已含)','人工成本','上月成本','环比(%)','固定成本','绩效成本','固浮比(%)','人均固定成本','人均变动成本','定单实际','定单目标','达成率(%)','人均总成本','人效(单/人)','人力CPS'];var dr=ar.map(function(s){var fp=s.labor>0?parseFloat((s.fixed/s.labor*100).toFixed(1)):null;var r=s.orders_actual!=null&&s.orders_target>0?parseFloat((s.orders_actual/s.orders_target*100).toFixed(1)):null;var eff=s.count>0&&s.orders_actual!=null?parseFloat((s.orders_actual/s.count).toFixed(2)):null;var cps=s.orders_actual>0?Math.round(s.labor/s.orders_actual):null;var avg=s.count>0?Math.round(s.labor/s.count):null;var af=s.count>0?Math.round(s.fixed/s.count):null;var ap=s.count>0?Math.round(s.perf/s.count):null;var p=pm[s.name];return[s.name,s.dept,s.count,s.intern_count||0,s.labor,p?p.labor:null,p?parseFloat(((s.labor-p.labor)/p.labor*100).toFixed(1)):null,s.fixed,s.perf,fp,af,ap,s.orders_actual,s.orders_target,r,avg,eff,cps];});var to=ar.reduce(function(a,s){a.l+=s.labor;a.f+=s.fixed;a.p+=s.perf;a.c+=s.count;a.ic+=s.intern_count||0;if(s.orders_actual!=null){a.ac+=s.orders_actual;a.tg+=s.orders_target;}return a;},{l:0,f:0,p:0,c:0,ic:0,ac:0,tg:0});dr.push(['合计（'+ar.length+'家）','',to.c,to.ic,to.l,'','',to.f,to.p,to.l>0?parseFloat((to.f/to.l*100).toFixed(1)):null,to.c>0?Math.round(to.f/to.c):null,to.c>0?Math.round(to.p/to.c):null,to.ac,to.tg,to.tg>0?parseFloat((to.ac/to.tg*100).toFixed(1)):null,to.c>0?Math.round(to.l/to.c):null,(to.c>0&&to.ac>0)?parseFloat((to.ac/to.c).toFixed(2)):null,to.ac>0?Math.round(to.l/to.ac):null]);var ws=XLSX.utils.aoa_to_sheet([hd].concat(dr));ws['!cols']=[22,12,6,14,12,12,8,12,12,8,12,12,8,8,8,12,10,10].map(function(w){return{wch:w};});addExportHeaderStyle(ws);var wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'零售门店数据');XLSX.writeFile(wb,'零售门店数据_'+(getData().period)+'_离线版.xlsx');showToast('已导出 '+ar.length+' 家门店数据');}
function exportCostTable(){var ar=getRetailData();var prev=getPrevData();var pm={};if(prev&&prev.retailStores)prev.retailStores.forEach(function(s){pm[s.name]=s;});var hd=['门店','所属部门','在编人数','法定加班','上月法定加班','法定加班环比(%)','出差津贴','上月出差津贴','出差津贴环比(%)','社保公积金(企)','上月社保','社保环比(%)'];var dr=ar.map(function(s){var p=pm[s.name];return[s.name,s.dept,s.count,s.overtime_legal||0,p?p.overtime_legal||0:null,p?parseFloat(((s.overtime_legal||0)-(p.overtime_legal||0))/(p.overtime_legal||1)*100).toFixed(1):null,s.travel||0,p?p.travel||0:null,p?parseFloat(((s.travel||0)-(p.travel||0))/(p.travel||1)*100).toFixed(1):null,s.social||0,p?p.social||0:null,p?parseFloat(((s.social||0)-(p.social||0))/(p.social||1)*100).toFixed(1):null];});var to=ar.reduce(function(a,s){a.ot+=s.overtime_legal||0;a.tr+=s.travel||0;a.so+=s.social||0;a.c+=s.count||0;return a;},{ot:0,tr:0,so:0,c:0});dr.push(['合计（'+ar.length+'家）','',to.c,to.ot,'','',to.tr,'','',to.so,'','']);var ws=XLSX.utils.aoa_to_sheet([hd].concat(dr));ws['!cols']=[22,12,6,12,12,10,10,10,10,14,12,10].map(function(w){return{wch:w};});addExportHeaderStyle(ws);var wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'补充成本明细');XLSX.writeFile(wb,'补充成本明细_'+(getData().period)+'_离线版.xlsx');showToast('已导出 '+ar.length+' 家门店补充成本数据');}

// PERSONNEL
var ALLOWED_TITLES=['产品专家','产品专员','储备管理','高级产品专家','资深产品专家','零售主管'];
var _ps={col:'',dir:1};
function personnelSortBy(c){if(_ps.col===c)_ps.dir*=-1;else{_ps.col=c;_ps.dir=1;}document.querySelectorAll('.sort-indicator').forEach(function(el){el.classList.remove('active');el.textContent='';});['','2'].forEach(function(sfx){var ind=document.getElementById('pSort-'+c+sfx);if(ind){ind.classList.add('active');ind.textContent=_ps.dir===1?'▲':'▼';}});renderPersonnel();}
function pGetMsSelected(){return[...document.querySelectorAll('#pMsList input[type=checkbox]:checked')].map(function(cb){return cb.value;});}
function pMsSyncLabel(){var s=pGetMsSelected(),l=document.getElementById('pMsLabel');if(!s.length)l.textContent='全部门店';else if(s.length===1)l.textContent=s[0];else l.innerHTML='已选 <span class=\\"ms-count-badge\\">'+s.length+'</span> 家门店';}
function pMsSyncSelectAll(){var a=document.querySelectorAll('#pMsList input'),c=document.querySelectorAll('#pMsList input:checked'),sa=document.getElementById('pMsSelectAll');sa.indeterminate=c.length>0&&c.length<a.length;sa.checked=a.length>0&&c.length===a.length;}
function pToggleMsPanel(){var p=document.getElementById('pMsPanel'),t=document.getElementById('pMsTrigger'),o=p.classList.toggle('open');t.classList.toggle('open',o);if(o){document.getElementById('pMsSearch').value='';pFilterMsOptions('');}}
function pCloseMsPanel(){document.getElementById('pMsPanel').classList.remove('open');document.getElementById('pMsTrigger').classList.remove('open');}
function pFilterMsOptions(q){q=q.toLowerCase();document.querySelectorAll('#pMsList .ms-item').forEach(function(i){i.style.display=!q||i.dataset.name.toLowerCase().includes(q)?'':'none';});}
function pMsToggleAll(cb){document.querySelectorAll('#pMsList input').forEach(function(c){c.checked=cb.checked;});pMsSyncLabel();pPopulateTitleDropdown();renderPersonnel();}
function pPopulateStoreDropdown(){var dept=document.getElementById('pFilterDept').value;var emps=getData().employees||[];var stores=emps.filter(function(e){if(e.isIntern===true)return false;if(!e.name)return false;if(dept&&e.dept!==dept)return false;return true;}).map(function(e){return e.store;}).filter(function(v,i,a){return v&&a.indexOf(v)===i;}).sort(function(a,b){return a.localeCompare(b,'zh');});var prev=pGetMsSelected().filter(function(n){return stores.includes(n);});document.getElementById('pMsList').innerHTML=stores.map(function(n){return '<label class=\\"ms-item\\" data-name=\\"'+n+'\\"><input type=\\"checkbox\\" value=\\"'+n+'\\" onchange=\\"pMsSyncLabel();pMsSyncSelectAll();pPopulateTitleDropdown();renderPersonnel()\\"'+(prev.includes(n)?' checked':'')+'> '+n+'</label>';}).join('');pMsSyncLabel();pMsSyncSelectAll();}
function pGetTitleMsSelected(){return[...document.querySelectorAll('#pTitleMsList input[type=checkbox]:checked')].map(function(cb){return cb.value;});}
function pTitleMsSyncLabel(){var s=pGetTitleMsSelected(),l=document.getElementById('pTitleMsLabel');if(!s.length)l.textContent='全部岗位';else if(s.length===1)l.textContent=s[0];else l.innerHTML='已选 <span class=\\"ms-count-badge\\">'+s.length+'</span> 个岗位';}
function pTitleMsSyncSelectAll(){var a=document.querySelectorAll('#pTitleMsList input'),c=document.querySelectorAll('#pTitleMsList input:checked'),sa=document.getElementById('pTitleMsSelectAll');sa.indeterminate=c.length>0&&c.length<a.length;sa.checked=a.length>0&&c.length===a.length;}
function pToggleTitleMsPanel(){var p=document.getElementById('pTitleMsPanel'),t=document.getElementById('pTitleMsTrigger'),o=p.classList.toggle('open');t.classList.toggle('open',o);if(o){document.getElementById('pTitleMsSearch').value='';pFilterTitleMsOptions('');}}
function pCloseTitleMsPanel(){document.getElementById('pTitleMsPanel').classList.remove('open');document.getElementById('pTitleMsTrigger').classList.remove('open');}
function pFilterTitleMsOptions(q){q=q.toLowerCase();document.querySelectorAll('#pTitleMsList .ms-item').forEach(function(i){i.style.display=!q||i.dataset.name.toLowerCase().includes(q)?'':'none';});}
function pTitleMsToggleAll(cb){document.querySelectorAll('#pTitleMsList input').forEach(function(c){c.checked=cb.checked;});pTitleMsSyncLabel();renderPersonnel();}
function pPopulateTitleDropdown(){var dept=document.getElementById('pFilterDept').value;var stores=pGetMsSelected();var emps=getData().employees||[];var titles=emps.filter(function(e){if(e.isIntern===true)return false;if(!e.name)return false;if(dept&&e.dept!==dept)return false;if(stores.length&&!stores.includes(e.store))return false;return e.title&&ALLOWED_TITLES.includes(e.title);}).map(function(e){return e.title;}).filter(function(v,i,a){return v&&a.indexOf(v)===i;}).sort(function(a,b){return a.localeCompare(b,'zh');});var prev=pGetTitleMsSelected().filter(function(n){return titles.includes(n);});document.getElementById('pTitleMsList').innerHTML=titles.map(function(n){return '<label class=\\"ms-item\\" data-name=\\"'+n+'\\"><input type=\\"checkbox\\" value=\\"'+n+'\\" onchange=\\"pTitleMsSyncLabel();pTitleMsSyncSelectAll();renderPersonnel()\\"'+(prev.includes(n)?' checked':'')+'> '+n+'</label>';}).join('');pTitleMsSyncLabel();pTitleMsSyncSelectAll();}
function popPersonnelDeptChange(){pPopulateStoreDropdown();pPopulateTitleDropdown();renderPersonnel();}
function clearPersonnelFilters(){document.getElementById('pFilterDept').value='';document.getElementById('pMsList').innerHTML='';document.querySelectorAll('#pMsList input').forEach(function(c){c.checked=false;});pMsSyncLabel();pMsSyncSelectAll();document.getElementById('pTitleMsList').innerHTML='';document.querySelectorAll('#pTitleMsList input').forEach(function(c){c.checked=false;});pTitleMsSyncLabel();pTitleMsSyncSelectAll();pPopulateStoreDropdown();pPopulateTitleDropdown();renderPersonnel();}
function renderPersonnel(){var emps=getData().employees||[];if(!emps.length){document.getElementById('pCountInfo').textContent='暂无数据';document.getElementById('personnelQuadrantSummary').innerHTML='';destroyChart('chartPersonnel');return;}
var df=document.getElementById('pFilterDept');var depts=[...new Set(emps.filter(function(e){return e.dept;}).map(function(e){return e.dept;}))].sort(function(a,b){return a.localeCompare(b,'zh');});df.innerHTML='<option value=\\"\\">全部</option>'+depts.map(function(d){return '<option value=\\"'+d+'\\">'+d+'</option>';}).join('');pPopulateStoreDropdown();pPopulateTitleDropdown();
var sd=df.value,ss=pGetMsSelected(),st=pGetTitleMsSelected();var htd=emps.some(function(e){return e.title;});var filtered=emps.filter(function(e){if(e.isIntern===true)return false;if(!e.name)return false;if(sd&&e.dept!==sd)return false;if(ss.length&&!ss.includes(e.store))return false;if(st.length){if(!st.includes(e.title))return false;}else{if(htd&&(!e.title||!ALLOWED_TITLES.includes(e.title)))return false;}return true;});
document.getElementById('pCountInfo').textContent='共 '+filtered.length+' 人';var pts=filtered.map(function(e){return{id:e.id,name:e.name,title:e.title||'',store:e.store,dept:e.dept,cat:e.cat,x:e.labor||0,y:typeof e.orders==='number'?e.orders:0};});
if(_ps.col){var sc=_ps.col,d=_ps.dir;pts.sort(function(a,b){var va,vb;if(sc==='labor'){va=a.x;vb=b.x;}else if(sc==='orders'){va=a.y;vb=b.y;}else if(sc==='quadrant'){va=a.q||0;vb=b.q||0;}else{va=(a[sc]||'').toString();vb=(b[sc]||'').toString();}return typeof va==='number'?(va-vb)*d:va.localeCompare(vb,'zh')*d;});}else{pts.sort(function(a,b){return(a.store||'').localeCompare(b.store||'')||a.name.localeCompare(b.name);});}
var vp=pts.filter(function(p){return p.x>0;});destroyChart('chartPersonnel');
if(vp.length){var mx=median(vp.map(function(d){return d.x;})),my=median(vp.map(function(d){return d.y;}));vp.forEach(function(d){d.q=d.x>mx?(d.y>my?2:4):(d.y>my?1:3);});var Q={1:{l:'低成本·高定单',bg:'rgba(0,114,109,0.55)',bo:'#00726D',ab:'rgba(0,114,109,0.06)'},2:{l:'高成本·高定单',bg:'rgba(206,164,114,0.75)',bo:'#b07030',ab:'rgba(206,164,114,0.08)'},3:{l:'低成本·低定单',bg:'rgba(82,120,160,0.55)',bo:'#5278A0',ab:'rgba(82,120,160,0.06)'},4:{l:'高成本·低定单',bg:'rgba(220,38,38,0.6)',bo:'#dc2626',ab:'rgba(220,38,38,0.07)'}};
var qp={id:'p',afterDraw:function(ch){var c=ch.ctx,l=ch.chartArea.left,r=ch.chartArea.right,t=ch.chartArea.top,b=ch.chartArea.bottom,x=ch.scales.x,y=ch.scales.y,px=x.getPixelForValue(mx),py=y.getPixelForValue(my);c.save();[[l,t,px-l,py-t,1],[px,t,r-px,py-t,2],[l,py,px-l,b-py,3],[px,py,r-px,b-py,4]].forEach(function(a){c.fillStyle=Q[a[4]].ab;c.fillRect(a[0],a[1],a[2],a[3]);});c.strokeStyle='#bbb';c.lineWidth=1;c.setLineDash([5,4]);c.beginPath();c.moveTo(px,t);c.lineTo(px,b);c.stroke();c.beginPath();c.moveTo(l,py);c.lineTo(r,py);c.stroke();c.setLineDash([]);c.font='10px sans-serif';c.fillStyle='#999';c.textAlign='center';c.fillText('中位 '+fmt(mx)+'元',px,b+22);c.textAlign='right';c.fillText('中位 '+my+'单',l-4,py+4);c.font='bold 10px PingFang SC,sans-serif';[[Q[1].l,l+5,t+13,'left','rgba(0,114,109,0.75)'],[Q[2].l,r-5,t+13,'right','rgba(160,100,30,0.75)'],[Q[3].l,l+5,b-6,'left','rgba(60,100,150,0.65)'],[Q[4].l,r-5,b-6,'right','rgba(180,30,30,0.75)']].forEach(function(a){c.fillStyle=a[4];c.textAlign=a[3];c.fillText(a[0],a[1],a[2]);});c.restore();}};
charts.chartPersonnel=new Chart(document.getElementById('chartPersonnel'),{type:'bubble',data:{datasets:[1,2,3,4].map(function(q){return{label:Q[q].l,data:vp.filter(function(d){return d.q===q;}).map(function(d){return{x:d.x,y:d.y,r:8};}),backgroundColor:Q[q].bg,borderColor:Q[q].bo,borderWidth:1.5};})},plugins:[qp],options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true,position:'top',labels:{boxWidth:10,font:{size:11},padding:12}},tooltip:{callbacks:{label:function(ctx){var d=vp.filter(function(v){return v.x===ctx.raw.x&&v.y===ctx.raw.y;})[0];return(d?d.name:'')+' | '+(d?d.title:'')+' | '+(d?d.store:'')+' | 成本 '+fmt(ctx.raw.x)+'元 | 定单 '+ctx.raw.y+'单';}}}},scales:{x:{title:{display:true,text:'个人成本（元）',font:{size:10}},ticks:{callback:function(v){return fmt(v);}}},y:{title:{display:true,text:'个人定单量（单）',font:{size:10}},beginAtZero:true}}}});
var defs=[{q:1,ic:'⭐',ti:'优秀员工 · 低成本高定单',de:'成本控制好且产出突出，是当前的标杆员工，可作经验推广。',co:'#00726D',bg:'rgba(0,114,109,0.06)',bo:'rgba(0,114,109,0.2)'},{q:2,ic:'📈',ti:'核心骨干 · 高成本高定单',de:'产出出色但成本偏高，建议深挖成本结构，优化薪酬配置。',co:'#9a6c20',bg:'rgba(206,164,114,0.1)',bo:'rgba(180,130,50,0.35)'},{q:3,ic:'⚡',ti:'潜力新人 · 低成本低定单',de:'成本可控但单量不足，建议加强培训和订单获取能力。',co:'#3a6898',bg:'rgba(82,120,160,0.07)',bo:'rgba(82,120,160,0.25)'},{q:4,ic:'⚠️',ti:'需关注 · 高成本低定单',de:'高投入低产出，需重点排查，优先制定改善或汰换方案。',co:'#dc2626',bg:'rgba(220,38,38,0.06)',bo:'rgba(220,38,38,0.2)'}];
document.getElementById('personnelQuadrantSummary').innerHTML='<div style=\\"display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px\\">'+defs.map(function(d){var ppl=vp.filter(function(s){return s.q===d.q;});var tags=ppl.length?ppl.map(function(s){return'<span style=\\"background:'+d.bg+';border:1px solid '+d.bo+';padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap;color:'+d.co+'\\">'+s.name+'('+s.y+'单/'+fmt(s.x)+'元)</span>';}).join(' '):'<span style=\\"color:#aaa;font-size:11px\\">暂无员工</span>';return'<div style=\\"background:'+d.bg+';border:1px solid '+d.bo+';border-radius:8px;padding:12px 14px\\"><div style=\\"display:flex;align-items:center;gap:6px;margin-bottom:5px\\"><span style=\\"font-size:15px\\">'+d.ic+'</span><span style=\\"font-weight:700;font-size:13px;color:'+d.co+'\\">'+d.ti+'</span><span style=\\"margin-left:auto;background:'+d.co+';color:#fff;border-radius:10px;padding:1px 9px;font-size:11px;font-weight:700\\">'+ppl.length+'人</span></div><div style=\\"font-size:11px;color:#555;margin-bottom:8px;line-height:1.5\\">'+d.de+'</div><div style=\\"display:flex;flex-wrap:wrap;gap:4px\\">'+tags+'</div></div>';}).join('')+'</div>';}
else{document.getElementById('personnelQuadrantSummary').innerHTML='';}}
document.addEventListener('click',function(e){var w=document.getElementById('pMsPanel')?.parentElement;if(w&&!w.contains(e.target))pCloseMsPanel();var wt=document.getElementById('pTitleMsPanel')?.parentElement;if(wt&&!wt.contains(e.target))pCloseTitleMsPanel();});
document.addEventListener('DOMContentLoaded',function(){initRetailFilters();renderAll();});
</script>
</body>
</html>`;

  // Send the HTML file as a download
  res.attachment('hr-cost-dashboard-offline.html');
  res.send(html);
});

// ── Full offline export (all tabs) ──────────────────────────────────────────
app.get('/api/offline-export-full', requireAuth, (req, res) => {
  const months = listMonths();
  const allData = {};
  months.forEach(m => { allData[m] = loadMonth(m); });
  if (!Object.keys(allData).length) return res.status(404).json({ error: '无数据可导出' });

  const periodKeys = Object.keys(allData).sort();
  const embeddedData = JSON.stringify(allData);

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${ZONE_NAME}人力成本分析看板 · 全量信息</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<style>
:root{--bg:#f0f5f4;--card:#fff;--border:#c8d8d6;--primary:#00726D;--primary-light:#e0f2f0;--primary-dark:#002D28;--fixed-color:#00726D;--perf-color:#CEA472;--green:#16a34a;--green-bg:#dcfce7;--red:#dc2626;--red-bg:#fee2e2;--orange:#d97706;--orange-bg:#fef3c7;--gray:#666;--text:#333;--sub:#666}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);font-size:13px}
.header{background:linear-gradient(135deg,var(--primary-dark),var(--primary));color:#fff;padding:14px 20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px}
.header h1{font-size:19px;font-weight:700}.header .sub-info{font-size:11px;opacity:.8;margin-top:2px}
.period-select{background:rgba(255,255,255,.2);border:1px solid rgba(255,255,255,.3);color:#fff;padding:6px 14px;border-radius:20px;font-size:13px;font-weight:600;cursor:pointer}.period-select option{color:#333;background:#fff}
.tabs-container{padding:12px 20px 0}
.tab-nav{display:flex;gap:2px;border-bottom:2px solid var(--border)}
.tab-btn{padding:8px 18px;border:none;background:none;cursor:pointer;font-size:13px;font-weight:600;color:var(--gray);border-bottom:2px solid transparent;margin-bottom:-2px;border-radius:6px 6px 0 0;transition:all .15s}
.tab-btn:hover{background:var(--primary-light);color:var(--primary)}.tab-btn.active{color:var(--primary);border-bottom-color:var(--primary);background:var(--primary-light)}
.tab-panel{display:none;padding:14px 0 24px}.tab-panel.active{display:block}
.filter-bar{background:var(--card);border-radius:10px;border:1px solid var(--border);padding:12px 14px;margin-bottom:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.filter-bar label{font-size:11px;color:var(--gray);font-weight:600;white-space:nowrap}
.filter-select{padding:5px 10px;border-radius:6px;border:1px solid var(--border);font-size:12px;background:#f8fafc;color:var(--text);cursor:pointer;min-width:110px}
.filter-sep{width:1px;height:22px;background:var(--border)}.filter-clear{padding:5px 12px;border-radius:6px;border:1px solid var(--border);background:#fff;font-size:12px;cursor:pointer;color:var(--gray);white-space:nowrap}.filter-clear:hover{color:var(--red);border-color:var(--red)}
.filter-count{font-size:11px;color:var(--gray);margin-left:auto}
.ms-wrap{position:relative}.ms-trigger{display:flex;align-items:center;gap:6px;padding:5px 10px;border-radius:6px;border:1px solid var(--border);font-size:12px;background:#f8fafc;color:var(--text);cursor:pointer;min-width:130px;user-select:none;white-space:nowrap}.ms-trigger svg{margin-left:auto;flex-shrink:0;transition:transform .15s}.ms-trigger.open svg{transform:rotate(180deg)}
.ms-panel{position:absolute;top:calc(100% + 4px);left:0;background:#fff;border:1px solid var(--border);border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,.13);z-index:200;min-width:190px;display:none;flex-direction:column}.ms-panel.open{display:flex}
.ms-search-box{padding:7px 10px;border-bottom:1px solid var(--border)}.ms-search-box input{width:100%;border:1px solid var(--border);border-radius:5px;padding:4px 8px;font-size:12px;outline:none}
.ms-all-row{padding:6px 12px;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer}.ms-all-row:hover{background:var(--primary-light)}
.ms-list{overflow-y:auto;max-height:210px}.ms-item{display:flex;align-items:center;gap:8px;padding:5px 12px;font-size:12px;cursor:pointer}.ms-item:hover{background:var(--primary-light)}.ms-item input,.ms-all-row input{accent-color:var(--primary);cursor:pointer}.ms-count-badge{background:var(--primary);color:#fff;border-radius:10px;padding:1px 7px;font-size:11px;font-weight:700;margin-left:4px}
.intern-tag{font-size:9px;color:var(--gray);margin-left:2px;cursor:help;white-space:nowrap}
.section-title{font-size:13px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:7px}.section-title::before{content:'';width:3px;height:13px;background:var(--primary);border-radius:2px;display:inline-block}
.card{background:var(--card);border-radius:10px;border:1px solid var(--border);padding:14px;margin-bottom:12px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.summary-row{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:12px}
.summary-card{background:var(--card);border-radius:10px;padding:10px 14px;border:1px solid var(--border);border-top:3px solid var(--primary)}.summary-card.green{border-top-color:var(--green)}.summary-card.orange{border-top-color:var(--orange)}.summary-card .s-label{font-size:10px;color:var(--gray)}.summary-card .s-val{font-size:18px;font-weight:700}.summary-card .s-sub{font-size:10px;color:var(--sub);margin-top:2px}
.chart-box{position:relative}.chart-legend{display:flex;gap:16px;margin-bottom:6px;font-size:11px;color:var(--gray)}.legend-item{display:flex;align-items:center;gap:5px}.legend-dot{width:9px;height:9px;border-radius:3px}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12px}
thead th{background:#f8fafc;color:var(--gray);font-weight:600;padding:8px 9px;text-align:center;border-bottom:2px solid var(--border);white-space:nowrap}
thead th:first-child{text-align:left}thead th.sortable{cursor:pointer;user-select:none}thead th.sortable:hover{background:#eef2f1;color:var(--primary)}
.sort-indicator{font-size:10px;margin-left:3px;display:inline-block;width:14px;text-align:center;color:#bbb}.sort-indicator.active{color:var(--primary)}
tbody tr:hover{background:#f8fafc}tbody td{padding:7px 9px;border-bottom:1px solid var(--border);text-align:center;white-space:nowrap}tbody td:first-child{text-align:left;font-weight:600}tbody tr:last-child td{border-bottom:none}
.total-row td{font-weight:700;background:#f0f9ff;color:var(--primary-dark)}.no-data{text-align:center;padding:24px;color:var(--gray);font-size:12px}
.notice{background:#fefce8;border:1px solid #fde68a;border-radius:8px;padding:10px 14px;font-size:12px;margin-bottom:12px;color:#92400e}
.ratio-bar{display:flex;height:13px;border-radius:3px;overflow:hidden;min-width:65px;gap:1px}.ratio-fixed{background:var(--fixed-color)}.ratio-perf{background:var(--perf-color)}
.rate{display:inline-block;padding:2px 8px;border-radius:10px;font-weight:700;font-size:11px}.rate-good{background:var(--green-bg);color:var(--green)}.rate-mid{background:var(--orange-bg);color:var(--orange)}.rate-bad{background:var(--red-bg);color:var(--red)}
.export-btn{display:flex;align-items:center;gap:4px;margin-left:auto;padding:4px 10px;border:1px solid var(--border);border-radius:6px;cursor:pointer;font-size:11px;font-weight:600;color:var(--gray);background:#f8fafc}.export-btn:hover{color:var(--primary);border-color:var(--primary);background:var(--primary-light)}
.toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:var(--primary-dark);color:#fff;padding:10px 24px;border-radius:8px;font-size:13px;font-weight:600;box-shadow:0 4px 12px rgba(0,0,0,.25);z-index:9999;opacity:0;transition:opacity .3s;pointer-events:none}.toast.show{opacity:1}
</style>
</head>
<body>
<div class="header">
  <div><h1>${ZONE_NAME}人力成本分析看板 · 全量信息</h1><div class="sub-info">数据含 ${periodKeys[0]} ~ ${periodKeys[periodKeys.length-1]}</div></div>
  <select class="period-select" id="periodSelect" onchange="switchPeriod(this.value)">
    ${periodKeys.slice().reverse().map((m,i) => '<option value="'+m+'"'+(i===0?' selected':'')+'>'+( allData[m]?.period || m)+'</option>').join('')}
  </select>
</div>

<div class="tabs-container">
  <div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('overview')">综合概览</button>
    <button class="tab-btn" onclick="switchTab('retail')">零售明细</button>
    <button class="tab-btn" onclick="switchTab('delivery')">交付明细</button>
    <button class="tab-btn" onclick="switchTab('personnel')">人员明细</button>
    <button class="tab-btn" onclick="switchTab('annual')">年度汇总</button>
  </div>

  <!-- 综合概览 -->
  <div class="tab-panel active" id="tab-overview">
    <div class="card">
      <div class="section-title">战区分模块成本汇总</div>
      <div class="table-wrap"><table><thead><tr><th>模块</th><th>人数</th><th>人工成本</th><th>固定成本</th><th>绩效成本</th><th>固浮比</th><th>人均成本</th></tr></thead><tbody id="overviewTbody"></tbody></table></div>
    </div>
    <div class="grid-2">
      <div class="card"><div class="section-title">固浮比对比（零售 vs 交付）</div><div class="chart-box" style="height:220px"><canvas id="chartFixedPerf"></canvas></div></div>
      <div class="card"><div class="section-title">战区成本结构占比</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;height:220px"><canvas id="chartPie1"></canvas><canvas id="chartPie2"></canvas></div>
        <div style="display:flex;justify-content:space-around;font-size:11px;color:var(--gray);margin-top:4px"><span>零售 vs 交付</span><span>固定 vs 绩效</span></div>
      </div>
    </div>
  </div>

  <!-- 零售明细 -->
  <div class="tab-panel" id="tab-retail">
    <div class="filter-bar">
      <label>所属部门</label><select class="filter-select" id="rFilterDept" onchange="applyRetailFilters()"><option value="">全部</option></select>
      <div class="filter-sep"></div>
      <label>门店</label>
      <div class="ms-wrap"><div class="ms-trigger" id="rMsTrigger" onclick="rToggleMsPanel()"><span id="rMsLabel">全部门店</span><svg viewBox="0 0 10 6" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 1l4 4 4-4"\/></svg></div>
        <div class="ms-panel" id="rMsPanel"><div class="ms-search-box"><input type="text" placeholder="搜索门店…" id="rMsSearch" oninput="rFilterMsOptions(this.value)"></div>
        <label class="ms-all-row"><input type="checkbox" id="rMsSelectAll" onchange="rMsToggleAll(this)"> 全选</label><div class="ms-list" id="rMsList"></div></div></div>
      <div class="filter-sep"></div>
      <label>达成状态</label>
      <select class="filter-select" id="rFilterRate" onchange="applyRetailFilters()" style="min-width:100px"><option value="">全部</option><option value="exceed">超额完成 ≥100%</option><option value="good">达标 85-100%</option><option value="mid">偏低 70-85%</option><option value="low">未达标 &lt;70%</option></select>
      <button class="filter-clear" onclick="clearRetailFilters()">清除筛选</button>
      <span class="filter-count" id="rFilterCount"></span>
    </div>
    <div class="summary-row" id="retailSummaryRow"></div>
    <div class="notice" id="retailNotice"></div>
    <div class="card"><div class="section-title" id="retailTableTitle">零售门店综合分析<button class="export-btn" onclick="exportRetailTable()"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"\/><polyline points="7 10 12 15 17 10"\/><line x1="12" y1="15" x2="12" y2="3"\/></svg>导出 Excel</button></div>
      <div class="table-wrap"><table><thead id="retailThead"></thead><tbody id="retailTbody"></tbody></table></div></div>
    <div class="card"><div class="section-title">补充成本明细（含环比）<button class="export-btn" onclick="exportCostTable()"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"\/><polyline points="7 10 12 15 17 10"\/><line x1="12" y1="15" x2="12" y2="3"\/></svg>导出 Excel</button></div>
      <div class="table-wrap"><table><thead id="costThead"></thead><tbody id="costTbody"></tbody></table></div></div>
    <div class="grid-2"><div class="card"><div class="section-title">门店定单达成分析</div><div class="chart-box" style="height:300px"><canvas id="chartOrderRate"></canvas></div></div><div class="card"><div class="section-title">人均总成本分布</div><div class="chart-box" style="height:300px"><canvas id="chartCostDist"></canvas></div></div></div>
    <div class="card"><div class="section-title">人效 vs 人均总成本 · 四象限分析</div><div class="chart-box" style="height:420px"><canvas id="chartEffCost"></canvas></div><div id="retailQuadrantSummary"></div></div>
  </div>

  <!-- 交付明细 -->
  <div class="tab-panel" id="tab-delivery">
    <div class="card"><div class="section-title">交付门店明细</div>
      <div class="table-wrap"><table><thead><tr><th>门店名称</th><th>人数</th><th>人工成本</th><th>固定成本</th><th>绩效成本</th><th>固浮比</th><th>人均成本</th><th>法定加班</th><th>出差津贴</th><th>社保公积金(企)</th></tr></thead><tbody id="deliveryStoresTbody"></tbody></table></div>
    </div>
    <div class="card"><div class="section-title">交付支持明细</div>
      <div class="table-wrap"><table><thead><tr><th>部门名称</th><th>人数</th><th>人工成本</th><th>固定成本</th><th>绩效成本</th><th>固浮比</th><th>人均成本</th></tr></thead><tbody id="deliverySupportTbody"></tbody></table></div>
    </div>
  </div>

  <!-- 人员明细 -->
  <div class="tab-panel" id="tab-personnel">
    <div class="filter-bar">
      <label>所属部门</label><select class="filter-select" id="pFilterDept" onchange="popPersonnelDeptChange()"><option value="">全部</option></select>
      <div class="filter-sep"></div>
      <label>门店</label>
      <div class="ms-wrap"><div class="ms-trigger" id="pMsTrigger" onclick="pToggleMsPanel()"><span id="pMsLabel">全部门店</span><svg viewBox="0 0 10 6" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 1l4 4 4-4"\/></svg></div>
        <div class="ms-panel" id="pMsPanel"><div class="ms-search-box"><input type="text" placeholder="搜索门店…" id="pMsSearch" oninput="pFilterMsOptions(this.value)"></div>
        <label class="ms-all-row"><input type="checkbox" id="pMsSelectAll" onchange="pMsToggleAll(this)"> 全选</label><div class="ms-list" id="pMsList"></div></div></div>
      <div class="filter-sep"></div>
      <label>岗位</label>
      <div class="ms-wrap"><div class="ms-trigger" id="pTitleMsTrigger" onclick="pToggleTitleMsPanel()"><span id="pTitleMsLabel">全部岗位</span><svg viewBox="0 0 10 6" width="10" height="10" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M1 1l4 4 4-4"\/></svg></div>
        <div class="ms-panel" id="pTitleMsPanel"><div class="ms-search-box"><input type="text" placeholder="搜索岗位…" id="pTitleMsSearch" oninput="pFilterTitleMsOptions(this.value)"></div>
        <label class="ms-all-row"><input type="checkbox" id="pTitleMsSelectAll" onchange="pTitleMsToggleAll(this)"> 全选</label><div class="ms-list" id="pTitleMsList"></div></div></div>
      <button class="filter-clear" onclick="clearPersonnelFilters()">清除筛选</button>
      <span style="margin-left:auto;font-size:11px;color:var(--gray)" id="pCountInfo"></span>
    </div>
    <div class="card"><div class="section-title">个人成本 vs 定单量 四象限分析</div><div class="chart-box" style="height:400px"><canvas id="chartPersonnel"></canvas></div></div>
    <div id="personnelQuadrantSummary"></div>
    <div class="card"><div class="section-title">人员明细列表</div>
      <div class="table-wrap"><table><thead><tr><th>姓名</th><th>岗位</th><th>门店</th><th>部门</th><th>分类</th><th>个人成本（元）</th><th>定单量（单）</th></tr></thead><tbody id="personnelTbody"></tbody></table></div>
    </div>
  </div>

  <!-- 年度汇总 -->
  <div class="tab-panel" id="tab-annual">
    <div class="card"><div class="section-title">1–12月数据汇总<span style="font-size:11px;color:var(--gray);font-weight:400;margin-left:8px">成本单位：万元 &nbsp;|&nbsp; 人数取各月最大值</span></div>
      <div class="table-wrap"><table>
        <thead>
          <tr><th rowspan="2" style="text-align:left;min-width:80px">月份</th>
            <th colspan="4" style="background:#e8f4f3;border-bottom:1px solid var(--border)">战区整体</th>
            <th colspan="6" style="background:#fdf5eb;border-bottom:1px solid var(--border)">零售（含战区支持）</th>
            <th colspan="6" style="background:#eff6ff;border-bottom:1px solid var(--border)">交付</th></tr>
          <tr>
            <th style="background:#e8f4f3">总人工成本（万）</th><th style="background:#e8f4f3">固定（万）</th><th style="background:#e8f4f3">绩效（万）</th><th style="background:#e8f4f3">人数（人）</th>
            <th style="background:#fdf5eb">总成本（万）</th><th style="background:#fdf5eb">固定（万）</th><th style="background:#fdf5eb">绩效（万）</th><th style="background:#fdf5eb">人数（人）</th><th style="background:#fdf5eb">总定单量（单）</th><th style="background:#fdf5eb">人效（单/人）</th>
            <th style="background:#eff6ff">总成本（万）</th><th style="background:#eff6ff">固定（万）</th><th style="background:#eff6ff">绩效（万）</th><th style="background:#eff6ff">人数（人）</th><th style="background:#eff6ff">总交付量（单）</th><th style="background:#eff6ff">人效（单/人）</th>
          </tr>
        </thead>
        <tbody id="annualTbody"></tbody>
      </table></div>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
var ALL_DATA=${embeddedData};
var ALL_PERIODS=${JSON.stringify(periodKeys)};
var charts={};
var currentPeriod=ALL_PERIODS[ALL_PERIODS.length-1];
function getData(){return ALL_DATA[currentPeriod];}
function getPrevData(){var i=ALL_PERIODS.indexOf(currentPeriod);if(i<ALL_PERIODS.length-1)return ALL_DATA[ALL_PERIODS[i+1]];return null;}
function fmt(n){return(n||0).toLocaleString('zh-CN');}
function median(a){if(!a.length)return 0;var s=[].concat(a).sort(function(x,y){return x-y;});var m=Math.floor(s.length/2);return s.length%2?s[m]:(s[m-1]+s[m])/2;}
function destroyChart(i){if(charts[i]){charts[i].destroy();delete charts[i];}}
function showToast(t){var e=document.getElementById('toast');e.textContent=t;e.classList.add('show');setTimeout(function(){e.classList.remove('show');},2500);}
function rateClass(r){if(r>=1)return'rate rate-good';if(r>=0.85)return'rate rate-mid';return'rate rate-bad';}
function fixedBadge(f){if(f>=50)return'<span class=\\"rate rate-bad\\">'+f+'%</span>';if(f>=40)return'<span class=\\"rate rate-mid\\">'+f+'%</span>';return'<span class=\\"rate rate-good\\">'+f+'%</span>';}
function momBadge(c,p){if(!p)return'<span style=\\"color:var(--gray);font-size:10px\\">—</span>';var x=(c-p)/p*100;if(x<0)return'<span style=\\"color:var(--green);font-weight:600\\">▼ '+Math.abs(x).toFixed(1)+'%</span>';if(x>0)return'<span style=\\"color:var(--red);font-weight:600\\">▲ '+x.toFixed(1)+'%</span>';return'<span style=\\"color:var(--gray)\\">0%</span>';}
function addExportHeaderStyle(ws){var r=XLSX.utils.decode_range(ws['!ref']);for(var C=r.s.c;C<=r.e.c;C++){var c=XLSX.utils.encode_cell({r:0,c:C});if(ws[c])ws[c].s={font:{bold:true},fill:{fgColor:{rgb:'002D28'}}};}}
function switchPeriod(ym){currentPeriod=ym;renderAll();}
function switchTab(id){var ids=['overview','retail','delivery','personnel','annual'];document.querySelectorAll('.tab-btn').forEach(function(b,i){b.classList.toggle('active',ids[i]===id);});document.querySelectorAll('.tab-panel').forEach(function(p){p.style.display='none';});document.getElementById('tab-'+id).style.display='block';if(id==='annual')renderAnnual();}
function renderAll(){destroyChart('chartOrderRate');destroyChart('chartCostDist');destroyChart('chartEffCost');destroyChart('chartPersonnel');destroyChart('chartFixedPerf');destroyChart('chartPie1');destroyChart('chartPie2');renderOverview();renderRetail();renderDelivery();renderPersonnel();}

// ── 综合概览 ─────────────────────────────────────────────────────────────────
function renderOverview(){var d=getData(),rs=d.retailStores||[],sd=d.supportDepts||[],ds=d.deliveryStores||[],dp=d.deliverySupport||[];var allR=[].concat(rs,sd),allD=[].concat(ds,dp),all=[].concat(allR,allD);function S(arr,f){return arr.reduce(function(a,x){return a+(x[f]||0);},0);}var mods=[{n:'零售门店',a:rs},{n:'零售支持部门',a:sd},{n:'交付门店',a:ds},{n:'交付支持',a:dp},{n:'零售合计',a:allR,t:true},{n:'交付合计',a:allD,t:true},{n:'战区合计',a:all,t:true}];var html='';mods.forEach(function(m){var L=S(m.a,'labor'),F=S(m.a,'fixed'),P=S(m.a,'perf'),C=S(m.a,'count');var fp=L?parseFloat((F/L*100).toFixed(1)):0,avg=C?Math.round(L/C):0;var bg=m.t?'style=\\"background:#f0f9ff;font-weight:700;color:var(--primary-dark)\\"':'';html+='<tr '+bg+'><td>'+(m.t?'📊 ':'')+m.n+'</td><td>'+C+'</td><td>'+fmt(L)+'</td><td style=\\"color:var(--fixed-color)\\">'+fmt(F)+'</td><td style=\\"color:var(--perf-color)\\">'+fmt(P)+'</td><td>'+fp+'%</td><td>'+fmt(avg)+'</td></tr>';});document.getElementById('overviewTbody').innerHTML=html;
destroyChart('chartFixedPerf');var fpLabels=['零售门店','零售支持','交付门店','交付支持'];var fpArr=[rs,sd,ds,dp];charts.chartFixedPerf=new Chart(document.getElementById('chartFixedPerf'),{type:'bar',data:{labels:fpLabels,datasets:[{label:'固定成本',data:fpArr.map(function(a){return S(a,'fixed');}),backgroundColor:'#00726D',borderRadius:3},{label:'绩效成本',data:fpArr.map(function(a){return S(a,'perf');}),backgroundColor:'#CEA472',borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}}},scales:{x:{stacked:true,grid:{display:false}},y:{stacked:true,ticks:{callback:function(v){return(v/10000).toFixed(1)+'万';}}}}}});
destroyChart('chartPie1');destroyChart('chartPie2');var rL=S(allR,'labor'),dL=S(allD,'labor'),fL=S(all,'fixed'),pL=S(all,'perf');if(rL+dL>0)charts.chartPie1=new Chart(document.getElementById('chartPie1'),{type:'doughnut',data:{labels:['零售','交付'],datasets:[{data:[rL,dL],backgroundColor:['#00726D','#CEA472'],borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}});if(fL+pL>0)charts.chartPie2=new Chart(document.getElementById('chartPie2'),{type:'doughnut',data:{labels:['固定','绩效'],datasets:[{data:[fL,pL],backgroundColor:['#00726D','#CEA472'],borderWidth:2}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}}}}});}

// ── 零售明细 ─────────────────────────────────────────────────────────────────
function getRetailData(){return getData().retailStores||[];}
function rGetMsSelected(){return[...document.querySelectorAll('#rMsList input[type=checkbox]:checked')].map(function(cb){return cb.value;});}
function rMsSyncLabel(){var s=rGetMsSelected(),l=document.getElementById('rMsLabel');if(!s.length)l.textContent='全部门店';else if(s.length===1)l.textContent=s[0];else l.innerHTML='已选 <span class=\\"ms-count-badge\\">'+s.length+'</span> 家门店';}
function rMsSyncSelectAll(){var a=document.querySelectorAll('#rMsList input'),c=document.querySelectorAll('#rMsList input:checked'),sa=document.getElementById('rMsSelectAll');sa.indeterminate=c.length>0&&c.length<a.length;sa.checked=a.length>0&&c.length===a.length;}
function rToggleMsPanel(){var p=document.getElementById('rMsPanel'),t=document.getElementById('rMsTrigger'),o=p.classList.toggle('open');t.classList.toggle('open',o);if(o){document.getElementById('rMsSearch').value='';rFilterMsOptions('');}}
function rCloseMsPanel(){document.getElementById('rMsPanel').classList.remove('open');document.getElementById('rMsTrigger').classList.remove('open');}
function rFilterMsOptions(q){q=q.toLowerCase();document.querySelectorAll('#rMsList .ms-item').forEach(function(i){i.style.display=!q||i.dataset.name.toLowerCase().includes(q)?'':'none';});}
function rMsToggleAll(cb){document.querySelectorAll('#rMsList input').forEach(function(c){c.checked=cb.checked;});rMsSyncLabel();rMsSyncSelectAll();applyRetailFilters();}
function rPopulateDropdown(){var dept=document.getElementById('rFilterDept').value;var stores=getRetailData().filter(function(s){if(dept&&s.dept!==dept)return false;return true;}).map(function(s){return s.name;}).filter(function(v,i,a){return a.indexOf(v)===i;}).sort(function(a,b){return a.localeCompare(b,'zh');});var prev=rGetMsSelected().filter(function(n){return stores.includes(n);});document.getElementById('rMsList').innerHTML=stores.map(function(n){return '<label class=\\"ms-item\\" data-name=\\"'+n+'\\"><input type=\\"checkbox\\" value=\\"'+n+'\\" onchange=\\"rMsSyncLabel();rMsSyncSelectAll();applyRetailFilters()\\"'+(prev.includes(n)?' checked':'')+'> '+n+'</label>';}).join('');rMsSyncLabel();rMsSyncSelectAll();}
document.addEventListener('click',function(e){var w=document.getElementById('rMsPanel')?.parentElement;if(w&&!w.contains(e.target))rCloseMsPanel();});
function renderRetail(){initRetailFilters();}
function initRetailFilters(){var stores=getRetailData();var depts=[...new Set(stores.filter(function(s){return s.dept;}).map(function(s){return s.dept;}))].sort(function(a,b){return a.localeCompare(b,'zh');});document.getElementById('rFilterDept').innerHTML='<option value=\\"\\">全部</option>'+depts.map(function(d){return '<option value=\\"'+d+'\\">'+d+'</option>';}).join('');rPopulateDropdown();applyRetailFilters();renderRetailCharts();}
function clearRetailFilters(){document.getElementById('rFilterDept').value='';document.getElementById('rFilterRate').value='';rPopulateDropdown();applyRetailFilters();}
function applyRetailFilters(){var dept=document.getElementById('rFilterDept').value,stores=rGetMsSelected(),rate=document.getElementById('rFilterRate').value;var filtered=getRetailData().filter(function(s){if(dept&&s.dept!==dept)return false;if(stores.length&&!stores.includes(s.name))return false;if(rate){var r=s.orders_actual!=null&&s.orders_target>0?s.orders_actual/s.orders_target:null;if(r===null)return false;if(rate==='exceed'&&r<1)return false;if(rate==='good'&&(r<0.85||r>=1))return false;if(rate==='mid'&&(r<0.7||r>=0.85))return false;if(rate==='low'&&r>=0.7)return false;}return true;});document.getElementById('rFilterCount').textContent=filtered.length+'/'+getRetailData().length+'家';renderRetailTable(filtered);}
function renderRetailCharts(){var arr=getRetailData();var withOrders=arr.filter(function(s){return s.orders_actual!=null;});var sorted2=[].concat(withOrders).sort(function(a,b){return a.orders_actual/a.orders_target-b.orders_actual/b.orders_target;});destroyChart('chartOrderRate');if(sorted2.length){charts.chartOrderRate=new Chart(document.getElementById('chartOrderRate'),{type:'bar',data:{labels:sorted2.map(function(s){return s.name.replace('零售中心','').replace('（外展店）','[外展]').substring(0,10);}),datasets:[{label:'实际定单',data:sorted2.map(function(s){return s.orders_actual;}),backgroundColor:sorted2.map(function(s){return s.orders_actual>=s.orders_target?'#16a34a':'#00726D';}),borderRadius:3,yAxisID:'y'},{label:'目标定单',data:sorted2.map(function(s){return s.orders_target;}),type:'line',borderColor:'#CEA472',borderWidth:2,pointRadius:3,fill:false,yAxisID:'y'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{font:{size:10}}}},scales:{x:{grid:{display:false},ticks:{font:{size:9},maxRotation:45}},y:{beginAtZero:true}}}});}
destroyChart('chartCostDist');if(arr.length){var sortedCost=[].concat(arr).sort(function(a,b){return b.labor/b.count-a.labor/a.count;});var avg=arr.reduce(function(a,x){return a+x.labor/x.count;},0)/arr.length;charts.chartCostDist=new Chart(document.getElementById('chartCostDist'),{type:'bar',data:{labels:sortedCost.map(function(s){return s.name.replace('零售中心','').replace('（外展店）','[外展]').substring(0,10);}),datasets:[{label:'人均总成本',data:sortedCost.map(function(s){return s.count>0?Math.round(s.labor/s.count):0;}),backgroundColor:sortedCost.map(function(s){return s.labor/s.count>avg?'rgba(220,38,38,0.6)':'rgba(0,114,109,0.55)';}),borderRadius:3}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return'人均 '+(ctx.raw/10000).toFixed(2)+'万元';}}}},scales:{x:{grid:{display:false},ticks:{font:{size:9},maxRotation:45}},y:{ticks:{callback:function(v){return v/10000+'万';}}}}}}); }}
function renderRetailTable(sorted){var prev=getPrevData();var pm={};if(prev&&prev.retailStores)prev.retailStores.forEach(function(s){pm[s.name]=s;});if(!sorted.length){document.getElementById('retailTbody').innerHTML='<tr><td colspan=\\"16\\" class=\\"no-data\\">暂无符合条件的门店</td></tr>';renderRetailCost(sorted,pm);renderRetailQuadrant(sorted);return;}
if(window._retailSort&&window._retailSort.col){var sc=window._retailSort.col,dir=window._retailSort.dir;sorted=[].concat(sorted).sort(function(a,b){var va,vb;if(sc==='labor'){va=a.labor;vb=b.labor;}else if(sc==='fixed'){va=a.fixed;vb=b.fixed;}else if(sc==='perf'){va=a.perf;vb=b.perf;}else if(sc==='count'){va=a.count;vb=b.count;}else if(sc==='fp'){va=a.fixed/a.labor;vb=b.fixed/b.labor;}else if(sc==='orders_actual'){va=a.orders_actual||0;vb=b.orders_actual||0;}else if(sc==='orders_target'){va=a.orders_target||0;vb=b.orders_target||0;}else if(sc==='rate'){va=a.orders_actual!=null&&a.orders_target>0?a.orders_actual/a.orders_target:-1;vb=b.orders_actual!=null&&b.orders_target>0?b.orders_actual/b.orders_target:-1;}else if(sc==='avg'){va=a.count>0?a.labor/a.count:0;vb=b.count>0?b.labor/b.count:0;}else if(sc==='eff'){va=a.count>0&&a.orders_actual!=null?a.orders_actual/a.count:-1;vb=b.count>0&&b.orders_actual!=null?b.orders_actual/b.count:-1;}else if(sc==='cps'){va=a.orders_actual>0?a.labor/a.orders_actual:999999;vb=b.orders_actual>0?b.labor/b.orders_actual:999999;}else if(sc==='af'){va=a.count>0?a.fixed/a.count:0;vb=b.count>0?b.fixed/b.count:0;}else if(sc==='ap'){va=a.count>0?a.perf/a.count:0;vb=b.count>0?b.perf/b.count:0;}else{va=(a[sc]||'').toString();vb=(b[sc]||'').toString();}if(typeof va==='number'&&typeof vb==='number')return(va-vb)*dir;return(va||'').localeCompare(vb||'','zh')*dir;});}
var si=function(col){var a='',c=window._retailSort;if(c&&c.col===col){a=' <span class=\\"sort-indicator active\\">'+(c.dir===1?'▲':'▼')+'</span>';}else{a=' <span class=\\"sort-indicator\\">↕</span>';}return a;};
document.getElementById('retailThead').innerHTML='<tr><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'name\\')\\">门店'+si('name')+'</th><th>所属部门</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'count\\')\\">人数'+si('count')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'labor\\')\\">人工成本'+si('labor')+'</th><th>环比</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'fixed\\')\\">固定成本'+si('fixed')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'perf\\')\\">绩效成本'+si('perf')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'fp\\')\\">固浮比'+si('fp')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'af\\')\\">人均固定'+si('af')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'ap\\')\\">人均绩效'+si('ap')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'orders_actual\\')\\">定单实际'+si('orders_actual')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'orders_target\\')\\">定单目标'+si('orders_target')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'rate\\')\\">达成率'+si('rate')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'avg\\')\\">人均总成本'+si('avg')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'eff\\')\\">人效'+si('eff')+'</th><th class=\\"sortable\\" onclick=\\"retailSortBy(\\'cps\\')\\">人力CPS'+si('cps')+'</th></tr>';
var html='',to={l:0,f:0,p:0,c:0,ic:0,ac:0,tg:0};sorted.forEach(function(s){var fp=parseFloat((s.fixed/s.labor*100).toFixed(1));var r=s.orders_actual!=null&&s.orders_target>0?s.orders_actual/s.orders_target:null;var eff=s.count>0&&s.orders_actual!=null?(s.orders_actual/s.count).toFixed(2):'-';var cps=s.orders_actual>0?Math.round(s.labor/s.orders_actual):null;var af=s.count>0?fmt(Math.round(s.fixed/s.count)):'-';var ap=s.count>0?fmt(Math.round(s.perf/s.count)):'-';var ps=pm[s.name];var mc=ps?momBadge(s.labor,ps.labor):'<span style=\\"color:var(--gray);font-size:10px\\">—</span>';to.l+=s.labor;to.f+=s.fixed;to.p+=s.perf;to.c+=s.count;to.ic+=s.intern_count||0;if(s.orders_actual!=null){to.ac+=s.orders_actual;to.tg+=s.orders_target;}html+='<tr><td title=\\"'+s.name+'\\">'+s.name.replace('零售中心','').replace('（外展店）','<small style=\\"color:var(--gray)\\">外展</small>')+'</td><td style=\\"color:var(--gray)\\">'+s.dept+'</td><td>'+(s.intern_count?'<strong>'+s.count+'</strong><span class=\\"intern-tag\\">(+'+s.intern_count+'习)</span>':'<strong>'+s.count+'</strong>')+'</td><td>'+fmt(s.labor)+'</td><td>'+mc+'</td><td style=\\"color:var(--fixed-color)\\">'+fmt(s.fixed)+'</td><td style=\\"color:var(--perf-color)\\">'+fmt(s.perf)+'</td><td>'+fixedBadge(fp)+'</td><td style=\\"color:var(--fixed-color)\\">'+af+'</td><td style=\\"color:var(--perf-color)\\">'+ap+'</td><td><strong>'+(s.orders_actual!=null?s.orders_actual:'-')+'</strong></td><td>'+(s.orders_target!=null?s.orders_target:'-')+'</td><td>'+(r!=null?'<span class=\\"'+rateClass(r)+'\\">'+(r*100).toFixed(1)+'%</span>':'<span style=\\"color:var(--gray)\\">—</span>')+'</td><td>'+(s.count>0?fmt(Math.round(s.labor/s.count)):'-')+'</td><td>'+eff+'</td><td>'+(cps?fmt(cps):'-')+'</td></tr>';});
if(sorted.length>1){var tfp=parseFloat((to.f/to.l*100).toFixed(1));var tr=to.tg>0?to.ac/to.tg:null;html+='<tr class=\\"total-row\\"><td colspan=\\"2\\">筛选合计（'+sorted.length+'家）</td><td>'+to.c+(to.ic?'<span class=\\"intern-tag\\">(+'+to.ic+'习)</span>':'')+'</td><td>'+fmt(to.l)+'</td><td>—</td><td>'+fmt(to.f)+'</td><td>'+fmt(to.p)+'</td><td>'+fixedBadge(tfp)+'</td><td>'+(to.c>0?fmt(Math.round(to.f/to.c)):'-')+'</td><td>'+(to.c>0?fmt(Math.round(to.p/to.c)):'-')+'</td><td><strong>'+to.ac+'</strong></td><td>'+to.tg+'</td><td>'+(tr!=null?'<span class=\\"'+rateClass(tr)+'\\">'+(tr*100).toFixed(1)+'%</span>':'—')+'</td><td>'+(to.c>0?fmt(Math.round(to.l/to.c)):'-')+'</td><td>'+(to.c>0&&to.ac>0?(to.ac/to.c).toFixed(2):'-')+'</td><td>'+(to.ac>0?fmt(Math.round(to.l/to.ac)):'-')+'</td></tr>';}
document.getElementById('retailTbody').innerHTML=html;renderRetailCost(sorted,pm);renderRetailQuadrant(sorted);}
function renderRetailCost(arr,pm){var html='',to={ot:0,tr:0,so:0,c:0};arr.forEach(function(s){var p=pm[s.name];html+='<tr><td title=\\"'+s.name+'\\">'+s.name.replace('零售中心','').replace('（外展店）','<small style=\\"color:var(--gray)\\">外展</small>')+'</td><td style=\\"color:var(--gray)\\">'+(s.dept||'')+'</td><td>'+(s.count||0)+'</td><td>'+fmt(s.overtime_legal||0)+'</td><td>'+(p?momBadge(s.overtime_legal||0,p.overtime_legal||0):'<span style=\\"color:var(--gray);font-size:10px\\">—</span>')+'</td><td>'+fmt(s.travel||0)+'</td><td>'+(p?momBadge(s.travel||0,p.travel||0):'<span style=\\"color:var(--gray);font-size:10px\\">—</span>')+'</td><td>'+fmt(s.social||0)+'</td><td>'+(p?momBadge(s.social||0,p.social||0):'<span style=\\"color:var(--gray);font-size:10px\\">—</span>')+'</td></tr>';to.ot+=s.overtime_legal||0;to.tr+=s.travel||0;to.so+=s.social||0;to.c+=s.count||0;});if(arr.length>1)html+='<tr class=\\"total-row\\"><td colspan=\\"2\\">合计（'+arr.length+'家）</td><td>'+to.c+'</td><td>'+fmt(to.ot)+'</td><td>—</td><td>'+fmt(to.tr)+'</td><td>—</td><td>'+fmt(to.so)+'</td><td>—</td></tr>';document.getElementById('costThead').innerHTML='<tr><th>门店</th><th>所属部门</th><th>人数</th><th>法定加班</th><th>环比</th><th>出差津贴</th><th>环比</th><th>社保公积金(企)</th><th>环比</th></tr>';document.getElementById('costTbody').innerHTML=html;}
function retailSortBy(col){if(!window._retailSort)window._retailSort={col:'',dir:1};if(window._retailSort.col===col)window._retailSort.dir*=-1;else{window._retailSort.col=col;window._retailSort.dir=1;}applyRetailFilters();}
function renderRetailQuadrant(arr){destroyChart('chartEffCost');var er=arr.filter(function(s){return s.count>0&&s.orders_actual!=null;}).map(function(s){return{name:s.name.replace('零售中心','').replace('（外展店）','(外展)').substring(0,12),fn:s.name,x:Math.round(s.labor/s.count),y:parseFloat((s.orders_actual/s.count).toFixed(2)),r:s.count};});var se=document.getElementById('retailQuadrantSummary');if(!er.length){se.innerHTML='<div style=\\"padding:14px;text-align:center;color:var(--gray);font-size:12px\\">暂无足够数据绘制四象限图</div>';return;}var mx=median(er.map(function(d){return d.x;})),my=median(er.map(function(d){return d.y;}));er.forEach(function(d){d.q=d.x>mx?(d.y>my?2:4):(d.y>my?1:3);});var Q={1:{l:'低成本·高人效',bg:'rgba(0,114,109,0.55)',bo:'#00726D',ab:'rgba(0,114,109,0.06)'},2:{l:'高成本·高人效',bg:'rgba(206,164,114,0.75)',bo:'#b07030',ab:'rgba(206,164,114,0.08)'},3:{l:'低成本·低人效',bg:'rgba(82,120,160,0.55)',bo:'#5278A0',ab:'rgba(82,120,160,0.06)'},4:{l:'高成本·低人效',bg:'rgba(220,38,38,0.6)',bo:'#dc2626',ab:'rgba(220,38,38,0.07)'}};var qp={id:'q',afterDraw:function(ch){var c=ch.ctx,l=ch.chartArea.left,r=ch.chartArea.right,t=ch.chartArea.top,b=ch.chartArea.bottom,x=ch.scales.x,y=ch.scales.y,px=x.getPixelForValue(mx),py=y.getPixelForValue(my);c.save();[[l,t,px-l,py-t,1],[px,t,r-px,py-t,2],[l,py,px-l,b-py,3],[px,py,r-px,b-py,4]].forEach(function(a){c.fillStyle=Q[a[4]].ab;c.fillRect(a[0],a[1],a[2],a[3]);});c.strokeStyle='#bbb';c.lineWidth=1;c.setLineDash([5,4]);c.beginPath();c.moveTo(px,t);c.lineTo(px,b);c.stroke();c.beginPath();c.moveTo(l,py);c.lineTo(r,py);c.stroke();c.setLineDash([]);c.font='10px sans-serif';c.fillStyle='#999';c.textAlign='center';c.fillText('中位 '+(mx/10000).toFixed(1)+'万',px,b+22);c.textAlign='right';c.fillText('中位 '+my,l-4,py+4);c.font='bold 10px PingFang SC,sans-serif';[[Q[1].l,l+5,t+13,'left','rgba(0,114,109,0.75)'],[Q[2].l,r-5,t+13,'right','rgba(160,100,30,0.75)'],[Q[3].l,l+5,b-6,'left','rgba(60,100,150,0.65)'],[Q[4].l,r-5,b-6,'right','rgba(180,30,30,0.75)']].forEach(function(a){c.fillStyle=a[4];c.textAlign=a[3];c.fillText(a[0],a[1],a[2]);});c.restore();}};charts.chartEffCost=new Chart(document.getElementById('chartEffCost'),{type:'bubble',data:{datasets:[1,2,3,4].map(function(q){return{label:Q[q].l,data:er.filter(function(d){return d.q===q;}).map(function(d){return{x:d.x,y:d.y,r:d.r};}),backgroundColor:Q[q].bg,borderColor:Q[q].bo,borderWidth:1.5};})},plugins:[qp],options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true,position:'top',labels:{boxWidth:10,font:{size:11},padding:12}},tooltip:{callbacks:{label:function(ctx){var d=er.filter(function(x){return x.x===ctx.raw.x&&x.y===ctx.raw.y;})[0];return '门店: '+(d?d.fn:'')+' | 人均成本 '+(ctx.raw.x/10000).toFixed(2)+'万 | 人效 '+ctx.raw.y+'单/人';}}}},scales:{x:{title:{display:true,text:'人均总成本（元）',font:{size:10}},ticks:{callback:function(v){return(v/10000).toFixed(1)+'万';}}},y:{title:{display:true,text:'人效（单/人）',font:{size:10}}}}}});var defs=[{q:1,ic:'⭐',ti:'低成本·高人效',de:'成本控制好且人效突出，是当前的标杆门店，可作为经验推广参考。',co:'#00726D',bg:'rgba(0,114,109,0.06)',bo:'rgba(0,114,109,0.2)'},{q:2,ic:'📈',ti:'高成本·高人效',de:'人效表现出色但成本偏高，建议深挖成本结构，优化固浮比或人员配置。',co:'#9a6c20',bg:'rgba(206,164,114,0.1)',bo:'rgba(180,130,50,0.35)'},{q:3,ic:'⚡',ti:'低成本·低人效',de:'成本可控，但单量产出不足，建议聚焦订单获取能力及员工激励机制。',co:'#3a6898',bg:'rgba(82,120,160,0.07)',bo:'rgba(82,120,160,0.25)'},{q:4,ic:'⚠️',ti:'高成本·低人效',de:'高投入低产出，需重点排查人员结构及运营效率，优先制定改善方案。',co:'#dc2626',bg:'rgba(220,38,38,0.06)',bo:'rgba(220,38,38,0.2)'}];se.innerHTML='<div style=\\"display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px\\">'+defs.map(function(d){var ppl=er.filter(function(s){return s.q===d.q;});var tags=ppl.length?ppl.map(function(s){return '<span style=\\"background:'+d.bg+';border:1px solid '+d.bo+';padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap;color:'+d.co+'\\">'+s.fn+'('+s.y+'单/'+fmt(s.x)+'元)</span>';}).join(' '):'<span style=\\"color:#aaa;font-size:11px\\">暂无门店</span>';return '<div style=\\"background:'+d.bg+';border:1px solid '+d.bo+';border-radius:8px;padding:12px 14px\\"><div style=\\"display:flex;align-items:center;gap:6px;margin-bottom:5px\\"><span style=\\"font-size:15px\\">'+d.ic+'</span><span style=\\"font-weight:700;font-size:13px;color:'+d.co+'\\">'+d.ti+'</span><span style=\\"margin-left:auto;background:'+d.co+';color:#fff;border-radius:10px;padding:1px 9px;font-size:11px;font-weight:700\\">'+ppl.length+'家</span></div><div style=\\"font-size:11px;color:#555;margin-bottom:8px;line-height:1.5\\">'+d.de+'</div><div style=\\"display:flex;flex-wrap:wrap;gap:4px\\">'+tags+'</div></div>';}).join('')+'</div>';}
function exportRetailTable(){var ar=getRetailData();var prev=getPrevData();var pm={};if(prev&&prev.retailStores)prev.retailStores.forEach(function(s){pm[s.name]=s;});var hd=['门店','所属部门','在编人数','实习生人数','人工成本','上月成本','环比(%)','固定成本','绩效成本','固浮比(%)','人均固定','人均绩效','定单实际','定单目标','达成率(%)','人均总成本','人效(单/人)','人力CPS'];var dr=ar.map(function(s){var fp=s.labor>0?parseFloat((s.fixed/s.labor*100).toFixed(1)):null;var r=s.orders_actual!=null&&s.orders_target>0?parseFloat((s.orders_actual/s.orders_target*100).toFixed(1)):null;var eff=s.count>0&&s.orders_actual!=null?parseFloat((s.orders_actual/s.count).toFixed(2)):null;var cps=s.orders_actual>0?Math.round(s.labor/s.orders_actual):null;var avg=s.count>0?Math.round(s.labor/s.count):null;var p=pm[s.name];return[s.name,s.dept,s.count,s.intern_count||0,s.labor,p?p.labor:null,p?parseFloat(((s.labor-p.labor)/p.labor*100).toFixed(1)):null,s.fixed,s.perf,fp,s.count>0?Math.round(s.fixed/s.count):null,s.count>0?Math.round(s.perf/s.count):null,s.orders_actual,s.orders_target,r,avg,eff,cps];});var ws=XLSX.utils.aoa_to_sheet([hd].concat(dr));addExportHeaderStyle(ws);var wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'零售门店');XLSX.writeFile(wb,'零售门店_'+(getData().period||currentPeriod)+'.xlsx');showToast('已导出零售数据');}
function exportCostTable(){var ar=getRetailData();var prev=getPrevData();var pm={};if(prev&&prev.retailStores)prev.retailStores.forEach(function(s){pm[s.name]=s;});var hd=['门店','所属部门','人数','法定加班','出差津贴','社保公积金(企)'];var dr=ar.map(function(s){return[s.name,s.dept,s.count,s.overtime_legal||0,s.travel||0,s.social||0];});var ws=XLSX.utils.aoa_to_sheet([hd].concat(dr));addExportHeaderStyle(ws);var wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,ws,'补充成本');XLSX.writeFile(wb,'补充成本_'+(getData().period||currentPeriod)+'.xlsx');showToast('已导出补充成本数据');}

// ── 交付明细 ─────────────────────────────────────────────────────────────────
function renderDelivery(){var d=getData(),ds=d.deliveryStores||[],dp=d.deliverySupport||[];function R(s){var fp=s.labor?parseFloat((s.fixed/s.labor*100).toFixed(1)):0,avg=s.count?Math.round(s.labor/s.count):0;return '<tr><td>'+s.name+'</td><td>'+s.count+'</td><td>'+fmt(s.labor)+'</td><td style=\\"color:var(--fixed-color)\\">'+fmt(s.fixed)+'</td><td style=\\"color:var(--perf-color)\\">'+fmt(s.perf)+'</td><td>'+fp+'%</td><td>'+fmt(avg)+'</td><td>'+fmt(s.overtime_legal||0)+'</td><td>'+fmt(s.travel||0)+'</td><td>'+fmt(s.social||0)+'</td></tr>';}document.getElementById('deliveryStoresTbody').innerHTML=ds.length?ds.map(R).join(''):'<tr><td colspan=\\"10\\" class=\\"no-data\\">暂无数据</td></tr>';function RS(s){var fp=s.labor?parseFloat((s.fixed/s.labor*100).toFixed(1)):0,avg=s.count?Math.round(s.labor/s.count):0;return '<tr><td>'+s.name+'</td><td>'+s.count+'</td><td>'+fmt(s.labor)+'</td><td style=\\"color:var(--fixed-color)\\">'+fmt(s.fixed)+'</td><td style=\\"color:var(--perf-color)\\">'+fmt(s.perf)+'</td><td>'+fp+'%</td><td>'+fmt(avg)+'</td></tr>';}document.getElementById('deliverySupportTbody').innerHTML=dp.length?dp.map(RS).join(''):'<tr><td colspan=\\"7\\" class=\\"no-data\\">暂无数据</td></tr>';}

// ── 人员明细 ─────────────────────────────────────────────────────────────────
var ALLOWED_TITLES=['产品专家','产品专员','储备管理','高级产品专家','资深产品专家','零售主管'];
var _ps={col:'',dir:1};
function personnelSortBy(c){if(_ps.col===c)_ps.dir*=-1;else{_ps.col=c;_ps.dir=1;}document.querySelectorAll('.sort-indicator').forEach(function(el){el.classList.remove('active');el.textContent='';});['','2'].forEach(function(sfx){var ind=document.getElementById('pSort-'+c+sfx);if(ind){ind.classList.add('active');ind.textContent=_ps.dir===1?'▲':'▼';}});renderPersonnel();}
function pGetMsSelected(){return[...document.querySelectorAll('#pMsList input[type=checkbox]:checked')].map(function(cb){return cb.value;});}
function pMsSyncLabel(){var s=pGetMsSelected(),l=document.getElementById('pMsLabel');if(!s.length)l.textContent='全部门店';else if(s.length===1)l.textContent=s[0];else l.innerHTML='已选 <span class=\\"ms-count-badge\\">'+s.length+'</span> 家门店';}
function pMsSyncSelectAll(){var a=document.querySelectorAll('#pMsList input'),c=document.querySelectorAll('#pMsList input:checked'),sa=document.getElementById('pMsSelectAll');sa.indeterminate=c.length>0&&c.length<a.length;sa.checked=a.length>0&&c.length===a.length;}
function pToggleMsPanel(){var p=document.getElementById('pMsPanel'),t=document.getElementById('pMsTrigger'),o=p.classList.toggle('open');t.classList.toggle('open',o);if(o){document.getElementById('pMsSearch').value='';pFilterMsOptions('');}}
function pCloseMsPanel(){document.getElementById('pMsPanel').classList.remove('open');document.getElementById('pMsTrigger').classList.remove('open');}
function pFilterMsOptions(q){q=q.toLowerCase();document.querySelectorAll('#pMsList .ms-item').forEach(function(i){i.style.display=!q||i.dataset.name.toLowerCase().includes(q)?'':'none';});}
function pMsToggleAll(cb){document.querySelectorAll('#pMsList input').forEach(function(c){c.checked=cb.checked;});pMsSyncLabel();pPopulateTitleDropdown();renderPersonnel();}
function pGetTitleMsSelected(){return[...document.querySelectorAll('#pTitleMsList input[type=checkbox]:checked')].map(function(cb){return cb.value;});}
function pTitleMsSyncLabel(){var s=pGetTitleMsSelected(),l=document.getElementById('pTitleMsLabel');if(!s.length)l.textContent='全部岗位';else if(s.length===1)l.textContent=s[0];else l.innerHTML='已选 <span class=\\"ms-count-badge\\">'+s.length+'</span> 个岗位';}
function pTitleMsSyncSelectAll(){var a=document.querySelectorAll('#pTitleMsList input'),c=document.querySelectorAll('#pTitleMsList input:checked'),sa=document.getElementById('pTitleMsSelectAll');sa.indeterminate=c.length>0&&c.length<a.length;sa.checked=a.length>0&&c.length===a.length;}
function pToggleTitleMsPanel(){var p=document.getElementById('pTitleMsPanel'),t=document.getElementById('pTitleMsTrigger'),o=p.classList.toggle('open');t.classList.toggle('open',o);if(o){document.getElementById('pTitleMsSearch').value='';pFilterTitleMsOptions('');}}
function pCloseTitleMsPanel(){document.getElementById('pTitleMsPanel').classList.remove('open');document.getElementById('pTitleMsTrigger').classList.remove('open');}
function pFilterTitleMsOptions(q){q=q.toLowerCase();document.querySelectorAll('#pTitleMsList .ms-item').forEach(function(i){i.style.display=!q||i.dataset.name.toLowerCase().includes(q)?'':'none';});}
function pTitleMsToggleAll(cb){document.querySelectorAll('#pTitleMsList input').forEach(function(c){c.checked=cb.checked;});pTitleMsSyncLabel();renderPersonnel();}
function pPopulateStoreDropdown(){var dept=document.getElementById('pFilterDept').value;var emps=getData().employees||[];var stores=emps.filter(function(e){if(e.isIntern===true)return false;if(!e.name)return false;if(dept&&e.dept!==dept)return false;return true;}).map(function(e){return e.store;}).filter(function(v,i,a){return v&&a.indexOf(v)===i;}).sort(function(a,b){return a.localeCompare(b,'zh');});var prev=pGetMsSelected().filter(function(n){return stores.includes(n);});document.getElementById('pMsList').innerHTML=stores.map(function(n){return '<label class=\\"ms-item\\" data-name=\\"'+n+'\\"><input type=\\"checkbox\\" value=\\"'+n+'\\" onchange=\\"pMsSyncLabel();pMsSyncSelectAll();pPopulateTitleDropdown();renderPersonnel()\\"'+(prev.includes(n)?' checked':'')+'> '+n+'</label>';}).join('');pMsSyncLabel();pMsSyncSelectAll();}
function pPopulateTitleDropdown(){var dept=document.getElementById('pFilterDept').value;var stores=pGetMsSelected();var emps=getData().employees||[];var titles=emps.filter(function(e){if(e.isIntern===true)return false;if(!e.name)return false;if(dept&&e.dept!==dept)return false;if(stores.length&&!stores.includes(e.store))return false;return e.title&&ALLOWED_TITLES.includes(e.title);}).map(function(e){return e.title;}).filter(function(v,i,a){return v&&a.indexOf(v)===i;}).sort(function(a,b){return a.localeCompare(b,'zh');});var prev=pGetTitleMsSelected().filter(function(n){return titles.includes(n);});document.getElementById('pTitleMsList').innerHTML=titles.map(function(n){return '<label class=\\"ms-item\\" data-name=\\"'+n+'\\"><input type=\\"checkbox\\" value=\\"'+n+'\\" onchange=\\"pTitleMsSyncLabel();pTitleMsSyncSelectAll();renderPersonnel()\\"'+(prev.includes(n)?' checked':'')+'> '+n+'</label>';}).join('');pTitleMsSyncLabel();pTitleMsSyncSelectAll();}
function popPersonnelDeptChange(){pPopulateStoreDropdown();pPopulateTitleDropdown();renderPersonnel();}
function clearPersonnelFilters(){document.getElementById('pFilterDept').value='';document.getElementById('pMsList').innerHTML='';document.querySelectorAll('#pMsList input').forEach(function(c){c.checked=false;});pMsSyncLabel();pMsSyncSelectAll();document.getElementById('pTitleMsList').innerHTML='';document.querySelectorAll('#pTitleMsList input').forEach(function(c){c.checked=false;});pTitleMsSyncLabel();pTitleMsSyncSelectAll();pPopulateStoreDropdown();pPopulateTitleDropdown();renderPersonnel();}
function renderPersonnel(){var emps=getData().employees||[];if(!emps.length){document.getElementById('pCountInfo').textContent='暂无数据';document.getElementById('personnelQuadrantSummary').innerHTML='';document.getElementById('personnelTbody').innerHTML='<tr><td colspan=\\"7\\" class=\\"no-data\\">暂无数据</td></tr>';destroyChart('chartPersonnel');return;}
var df=document.getElementById('pFilterDept');var depts=[...new Set(emps.filter(function(e){return e.dept;}).map(function(e){return e.dept;}))].sort(function(a,b){return a.localeCompare(b,'zh');});df.innerHTML='<option value=\\"\\">全部</option>'+depts.map(function(d){return '<option value=\\"'+d+'\\">'+d+'</option>';}).join('');pPopulateStoreDropdown();pPopulateTitleDropdown();
var sd=df.value,ss=pGetMsSelected(),st=pGetTitleMsSelected();var htd=emps.some(function(e){return e.title;});var filtered=emps.filter(function(e){if(e.isIntern===true)return false;if(!e.name)return false;if(sd&&e.dept!==sd)return false;if(ss.length&&!ss.includes(e.store))return false;if(st.length){if(!st.includes(e.title))return false;}else{if(htd&&(!e.title||!ALLOWED_TITLES.includes(e.title)))return false;}return true;});
document.getElementById('pCountInfo').textContent='共 '+filtered.length+' 人';var pts=filtered.map(function(e){return{id:e.id,name:e.name,title:e.title||'',store:e.store,dept:e.dept,cat:e.cat,x:e.labor||0,y:typeof e.orders==='number'?e.orders:0};});
if(_ps.col){var sc=_ps.col,d=_ps.dir;pts.sort(function(a,b){var va,vb;if(sc==='labor'){va=a.x;vb=b.x;}else if(sc==='orders'){va=a.y;vb=b.y;}else{va=(a[sc]||'').toString();vb=(b[sc]||'').toString();}return typeof va==='number'?(va-vb)*d:va.localeCompare(vb,'zh')*d;});}else{pts.sort(function(a,b){return(a.store||'').localeCompare(b.store||'')||a.name.localeCompare(b.name);});}
var vp=pts.filter(function(p){return p.x>0;});destroyChart('chartPersonnel');
if(vp.length){var mx=median(vp.map(function(d){return d.x;})),my=median(vp.map(function(d){return d.y;}));vp.forEach(function(d){d.q=d.x>mx?(d.y>my?2:4):(d.y>my?1:3);});var Q={1:{l:'低成本·高定单',bg:'rgba(0,114,109,0.55)',bo:'#00726D',ab:'rgba(0,114,109,0.06)'},2:{l:'高成本·高定单',bg:'rgba(206,164,114,0.75)',bo:'#b07030',ab:'rgba(206,164,114,0.08)'},3:{l:'低成本·低定单',bg:'rgba(82,120,160,0.55)',bo:'#5278A0',ab:'rgba(82,120,160,0.06)'},4:{l:'高成本·低定单',bg:'rgba(220,38,38,0.6)',bo:'#dc2626',ab:'rgba(220,38,38,0.07)'}};
var qp={id:'p',afterDraw:function(ch){var c=ch.ctx,l=ch.chartArea.left,r=ch.chartArea.right,t=ch.chartArea.top,b=ch.chartArea.bottom,x=ch.scales.x,y=ch.scales.y,px=x.getPixelForValue(mx),py=y.getPixelForValue(my);c.save();[[l,t,px-l,py-t,1],[px,t,r-px,py-t,2],[l,py,px-l,b-py,3],[px,py,r-px,b-py,4]].forEach(function(a){c.fillStyle=Q[a[4]].ab;c.fillRect(a[0],a[1],a[2],a[3]);});c.strokeStyle='#bbb';c.lineWidth=1;c.setLineDash([5,4]);c.beginPath();c.moveTo(px,t);c.lineTo(px,b);c.stroke();c.beginPath();c.moveTo(l,py);c.lineTo(r,py);c.stroke();c.setLineDash([]);c.font='10px sans-serif';c.fillStyle='#999';c.textAlign='center';c.fillText('中位 '+fmt(mx)+'元',px,b+22);c.textAlign='right';c.fillText('中位 '+my+'单',l-4,py+4);c.font='bold 10px PingFang SC,sans-serif';[[Q[1].l,l+5,t+13,'left','rgba(0,114,109,0.75)'],[Q[2].l,r-5,t+13,'right','rgba(160,100,30,0.75)'],[Q[3].l,l+5,b-6,'left','rgba(60,100,150,0.65)'],[Q[4].l,r-5,b-6,'right','rgba(180,30,30,0.75)']].forEach(function(a){c.fillStyle=a[4];c.textAlign=a[3];c.fillText(a[0],a[1],a[2]);});c.restore();}};
charts.chartPersonnel=new Chart(document.getElementById('chartPersonnel'),{type:'bubble',data:{datasets:[1,2,3,4].map(function(q){return{label:Q[q].l,data:vp.filter(function(d){return d.q===q;}).map(function(d){return{x:d.x,y:d.y,r:8};}),backgroundColor:Q[q].bg,borderColor:Q[q].bo,borderWidth:1.5};})},plugins:[qp],options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:true,position:'top',labels:{boxWidth:10,font:{size:11},padding:12}},tooltip:{callbacks:{label:function(ctx){var d=vp.filter(function(v){return v.x===ctx.raw.x&&v.y===ctx.raw.y;})[0];return(d?d.name:'')+' | '+(d?d.title:'')+' | '+(d?d.store:'')+' | 成本 '+fmt(ctx.raw.x)+'元 | 定单 '+ctx.raw.y+'单';}}}},scales:{x:{title:{display:true,text:'个人成本（元）',font:{size:10}},ticks:{callback:function(v){return fmt(v);}}},y:{title:{display:true,text:'个人定单量（单）',font:{size:10}},beginAtZero:true}}}});
var defs=[{q:1,ic:'⭐',ti:'优秀员工',de:'成本控制好且产出突出，标杆员工。',co:'#00726D',bg:'rgba(0,114,109,0.06)',bo:'rgba(0,114,109,0.2)'},{q:2,ic:'📈',ti:'核心骨干',de:'产出出色但成本偏高，建议优化薪酬配置。',co:'#9a6c20',bg:'rgba(206,164,114,0.1)',bo:'rgba(180,130,50,0.35)'},{q:3,ic:'⚡',ti:'潜力新人',de:'成本可控但单量不足，加强培训。',co:'#3a6898',bg:'rgba(82,120,160,0.07)',bo:'rgba(82,120,160,0.25)'},{q:4,ic:'⚠️',ti:'需关注',de:'高投入低产出，优先制定改善方案。',co:'#dc2626',bg:'rgba(220,38,38,0.06)',bo:'rgba(220,38,38,0.2)'}];
document.getElementById('personnelQuadrantSummary').innerHTML='<div style=\\"display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px\\">'+defs.map(function(d){var ppl=vp.filter(function(s){return s.q===d.q;});var tags=ppl.length?ppl.map(function(s){return'<span style=\\"background:'+d.bg+';border:1px solid '+d.bo+';padding:2px 8px;border-radius:10px;font-size:11px;white-space:nowrap;color:'+d.co+'\\">'+s.name+'('+s.y+'单/'+fmt(s.x)+'元)</span>';}).join(' '):'<span style=\\"color:#aaa;font-size:11px\\">暂无员工</span>';return'<div style=\\"background:'+d.bg+';border:1px solid '+d.bo+';border-radius:8px;padding:12px 14px\\"><div style=\\"display:flex;align-items:center;gap:6px;margin-bottom:5px\\"><span style=\\"font-size:15px\\">'+d.ic+'</span><span style=\\"font-weight:700;font-size:13px;color:'+d.co+'\\">'+d.ti+'</span><span style=\\"margin-left:auto;background:'+d.co+';color:#fff;border-radius:10px;padding:1px 9px;font-size:11px;font-weight:700\\">'+ppl.length+'人</span></div><div style=\\"font-size:11px;color:#555;margin-bottom:8px;line-height:1.5\\">'+d.de+'</div><div style=\\"display:flex;flex-wrap:wrap;gap:4px\\">'+tags+'</div></div>';}).join('')+'</div>';}
else{document.getElementById('personnelQuadrantSummary').innerHTML='';}
var lHtml='';pts.forEach(function(e){lHtml+='<tr><td>'+e.name+'</td><td>'+(e.title||'')+'</td><td>'+(e.store||'')+'</td><td>'+(e.dept||'')+'</td><td>'+(e.cat||'')+'</td><td>'+fmt(e.x||0)+'</td><td>'+(e.y||'—')+'</td></tr>';});document.getElementById('personnelTbody').innerHTML=lHtml||'<tr><td colspan=\\"7\\" class=\\"no-data\\">暂无数据</td></tr>';}
document.addEventListener('click',function(e){var w=document.getElementById('rMsPanel')?.parentElement;if(w&&!w.contains(e.target))rCloseMsPanel();var wp=document.getElementById('pMsPanel')?.parentElement;if(wp&&!wp.contains(e.target))pCloseMsPanel();var wt=document.getElementById('pTitleMsPanel')?.parentElement;if(wt&&!wt.contains(e.target))pCloseTitleMsPanel();});

// ── 年度汇总 ─────────────────────────────────────────────────────────────────
function renderAnnual(){function S(arr,f){return arr.reduce(function(a,x){return a+(x[f]||0);},0);}function W(n){return n?(n/10000).toFixed(1):'—';}function E(o,c){return(o&&c)?(o/c).toFixed(2):'—';}var html='',ytd={labor:0,fixed:0,perf:0,count:0,rlabor:0,rfixed:0,rperf:0,rcount:0,rorders:0,dlabor:0,dfixed:0,dperf:0,dcount:0,dorders:0};ALL_PERIODS.slice().sort().forEach(function(ym){var d=ALL_DATA[ym];if(!d)return;var all=[].concat(d.retailStores||[],d.supportDepts||[],d.deliveryStores||[],d.deliverySupport||[]);var retail=[].concat(d.retailStores||[],d.supportDepts||[]);var del=[].concat(d.deliveryStores||[],d.deliverySupport||[]);var L=S(all,'labor'),F=S(all,'fixed'),P=S(all,'perf'),C=S(all,'count');var rL=S(retail,'labor'),rF=S(retail,'fixed'),rP=S(retail,'perf'),rC=S(retail,'count'),rO=S(d.retailStores||[],'orders_actual');var dL=S(del,'labor'),dF=S(del,'fixed'),dP=S(del,'perf'),dC=S(del,'count'),dO=d.deliveryTotal!=null?d.deliveryTotal:S(d.deliveryStores||[],'orders_actual');html+='<tr><td style=\\"font-weight:600\\">'+(d.period||ym)+'</td><td>'+W(L)+'</td><td>'+W(F)+'</td><td>'+W(P)+'</td><td>'+C+'</td><td>'+W(rL)+'</td><td>'+W(rF)+'</td><td>'+W(rP)+'</td><td>'+rC+'</td><td>'+rO+'</td><td>'+E(rO,rC)+'</td><td>'+W(dL)+'</td><td>'+W(dF)+'</td><td>'+W(dP)+'</td><td>'+dC+'</td><td>'+dO+'</td><td>'+E(dO,dC)+'</td></tr>';ytd.labor+=L;ytd.fixed+=F;ytd.perf+=P;ytd.count=Math.max(ytd.count,C);ytd.rlabor+=rL;ytd.rfixed+=rF;ytd.rperf+=rP;ytd.rcount=Math.max(ytd.rcount,rC);ytd.rorders+=rO;ytd.dlabor+=dL;ytd.dfixed+=dF;ytd.dperf+=dP;ytd.dcount=Math.max(ytd.dcount,dC);ytd.dorders+=dO;});html+='<tr style=\\"background:#f0f9ff;font-weight:700;color:#002D28\\"><td>累计合计</td><td>'+W(ytd.labor)+'</td><td>'+W(ytd.fixed)+'</td><td>'+W(ytd.perf)+'</td><td>—</td><td>'+W(ytd.rlabor)+'</td><td>'+W(ytd.rfixed)+'</td><td>'+W(ytd.rperf)+'</td><td>—</td><td>'+ytd.rorders+'</td><td>—</td><td>'+W(ytd.dlabor)+'</td><td>'+W(ytd.dfixed)+'</td><td>'+W(ytd.dperf)+'</td><td>—</td><td>'+ytd.dorders+'</td><td>—</td></tr>';document.getElementById('annualTbody').innerHTML=html;}

document.addEventListener('DOMContentLoaded',function(){renderAll();});
</script>
</body>
</html>`;

  res.attachment('hr-cost-dashboard-全量.html');
  res.send(html);
});

// ── Start ──────────────────────────────────────────────────
app.listen(PORT, '0.0.0.0', () => {
  const os = require('os');
  const ifaces = os.networkInterfaces();
  let localIP = 'localhost';
  Object.values(ifaces).flat().forEach(i => {
    if (i.family === 'IPv4' && !i.internal) localIP = i.address;
  });
  console.log(`\n✅ ${ZONE_NAME}人力成本分析看板已启动`);
  console.log(`   本机访问：http://localhost:${PORT}`);
  console.log(`   局域网分享：http://${localIP}:${PORT}`);
  if (!IS_PRODUCTION) {
    console.log('\n初始账号：');
    console.log('  管理员   admin / Admin@2026');
    console.log('  零售用户 retail / Retail@2026');
    console.log('  交付用户 delivery / Delivery@2026\n');
  }
});
