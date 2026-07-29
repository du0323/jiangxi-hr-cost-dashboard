/**
 * import-data.js — 将三个 Excel 文件转换为看板所需的 JSON 数据
 *
 * 用法：
 *   node import-data.js <成本文件> <订单文件> <人员订单文件> <输出目录>
 *
 * 示例（安徽4月）：
 *   node import-data.js \
 *     "C:/Users/litingting7/Desktop/人力成本分析/成本分析导入数据-安徽/成本数据导入模板 (4月)安徽 .xlsx" \
 *     "C:/Users/litingting7/Desktop/人力成本分析/成本分析导入数据-安徽/导入定单数据-4月安徽.xlsx" \
 *     "C:/Users/litingting7/Desktop/人力成本分析/成本分析导入数据-安徽/导入人员月度定单明细-4月安徽.xlsx" \
 *     data-anhui
 *
 * 示例（江西1月）：
 *   node import-data.js \
 *     "C:/Users/litingting7/Desktop/人力成本分析/成本分析导入数据-江西/成本数据导入模板 (1月) .xlsx" \
 *     "C:/Users/litingting7/Desktop/人力成本分析/成本分析导入数据-江西/导入定单数据-1月.xlsx" \
 *     "C:/Users/litingting7/Desktop/人力成本分析/成本分析导入数据-江西/导入人员月度定单明细-1月.xlsx" \
 *     data
 */

const XLSX = require('xlsx');
const fs = require('fs');
const path = require('path');

const [,, costFile, orderFile, personnelFile, outDir] = process.argv;

if (!costFile || !orderFile || !personnelFile || !outDir) {
  console.error('用法: node import-data.js <成本文件> <订单文件> <人员订单文件> <输出目录>');
  process.exit(1);
}

// ── 读取文件 ──────────────────────────────────────────────────────────────────
function readSheet(file, sheetName) {
  const wb = XLSX.readFile(file);
  const sheet = sheetName ? wb.Sheets[sheetName] : wb.Sheets[wb.SheetNames[0]];
  return XLSX.utils.sheet_to_json(sheet, { header: 1 }).filter(r => r.some(c => c !== null && c !== undefined && c !== ''));
}

const costRows = readSheet(costFile, '成本数据').slice(1); // skip header
const orderRows = readSheet(orderFile, 'Sheet1').slice(1); // skip header
const personnelRows = readSheet(personnelFile, 'Sheet1').slice(1); // skip header

// ── 从订单数据提取月份期间 ──────────────────────────────────────────────────
// 表头第1列如 "4月定单量"，提取月份
const orderHeader = readSheet(orderFile, 'Sheet1')[0];
const monthMatch = String(orderHeader[1] || '').match(/(\d+)月/);
const month = monthMatch ? parseInt(monthMatch[1]) : null;

// 从成本数据提取年份
const yearMatch = String(costRows[0]?.[7] || '').match(/(\d{4})\//);
const year = yearMatch ? parseInt(yearMatch[1]) : new Date().getFullYear();

if (!month) { console.error('无法从订单文件表头提取月份'); process.exit(1); }

const periodLabel = `${year}年${month}月`;
const periodKey = `${year}-${String(month).padStart(2, '0')}`;

console.log(`\n处理数据：${periodLabel} → ${outDir}/${periodKey}.json`);

// ── 订单数据 Map: 门店名称 → {actual, target} ──────────────────────────────
const orderMap = {};
let deliveryTotal = null;
orderRows.forEach(r => {
  const name = String(r[0] || '').trim();
  if (!name || name === '合计') return;
  if (name === '交付量总计' || name === '交付量合计') { deliveryTotal = Number(r[1]) || 0; return; }
  orderMap[name] = { actual: Number(r[1]) || 0, target: Number(r[2]) || 0 };
});

// ── 人员订单 Map: 工号 → 订单量 ────────────────────────────────────────────
const personnelOrderMap = {};
personnelRows.forEach(r => {
  const id = String(r[0] || '').trim();
  if (id) personnelOrderMap[id] = Number(r[2]) || 0;
});

// ── 成本数据列索引 ──────────────────────────────────────────────────────────
const C = {
  zone: 0,    // 二级部门（战区）
  dept3: 1,   // 三级部门
  dept4: 2,   // 四级部门（门店）
  id: 3,      // 工号
  name: 4,    // 姓名
  level: 5,   // 新职级
  title: 6,   // 职务（岗位）
  period: 7,  // 所属周期
  labor: 8,   // 人工成本
  perf: 9,    // 店端绩效奖金
  overtime: 11, // 法定加班费
  travel: 15,   // 出差津贴
  social: 22,   // 社保公积金（企业）
  counted: 27,  // 是否计数
};

// ── 分类规则 ────────────────────────────────────────────────────────────────
// retailStore:    四级非空 && 三级包含"部"
// deliveryStore:  四级非空 && 三级=="交付"
// deliverySupport:四级空   && 三级=="交付"
// supportDept:    四级空   && 三级有值（非交付）→ 按三级分组
// headquarters:   四级空   && 三级空 → 战区总部
function classify(dept3, dept4) {
  const d3 = String(dept3 || '').trim();
  const d4 = String(dept4 || '').trim();
  if (d4) {
    if (d3 === '交付') return 'deliveryStore';
    if (d3) return 'retailStore';
    return 'retailStore'; // fallback
  } else {
    if (d3 === '交付') return 'deliverySupport';
    if (d3) return 'supportDept';
    return 'headquarters';
  }
}

// ── 聚合：按分组键汇总门店/部门数据 ─────────────────────────────────────────
const storeMap = {};   // key → aggregated store/dept data
const employeeList = [];

costRows.forEach(r => {
  const dept3 = String(r[C.dept3] || '').trim();
  const dept4 = String(r[C.dept4] || '').trim();
  const type = classify(dept3, dept4);

  // 分组 key
  let key, displayName, displayDept;
  if (type === 'retailStore' || type === 'deliveryStore') {
    key = dept4;
    displayName = dept4;
    displayDept = dept3;
  } else if (type === 'deliverySupport') {
    key = '交付_support';
    displayName = '交付';
    displayDept = '战区直属';
  } else if (type === 'supportDept') {
    key = 'support_' + dept3;
    displayName = dept3;
    displayDept = '战区直属';
  } else { // headquarters
    key = 'headquarters';
    displayName = '战区总部';
    displayDept = '战区直属';
  }

  if (!storeMap[key]) {
    storeMap[key] = {
      _type: type,
      name: displayName,
      dept: displayDept,
      labor: 0, perf: 0, fixed: 0,
      count: 0, intern_count: 0, intern_labor: 0,
      overtime_legal: 0, travel: 0, social: 0,
      orders_actual: null, orders_target: null,
    };
  }

  const isCounted = String(r[C.counted] || '').trim() === '是';
  const title = String(r[C.title] || '').trim();
  const isIntern = !isCounted && title === '实习生';  // 是否计数=否 且 岗位=实习生 才算实习生
  const labor = Number(r[C.labor]) || 0;
  const perf = Number(r[C.perf]) || 0;
  const overtime = Number(r[C.overtime]) || 0;
  const travel = Number(r[C.travel]) || 0;
  const social = Number(r[C.social]) || 0;

  const s = storeMap[key];
  s.labor += labor;
  s.perf += perf;
  s.overtime_legal += overtime;
  s.travel += travel;
  s.social += social;

  if (isIntern) {
    s.intern_count += 1;
    s.intern_labor += labor;
  } else {
    s.count += 1;  // 是否计数=是，或是否计数=否但岗位非实习生，均计入正式人数
  }

  // 员工明细（仅零售店和交付店员工进入 employees 列表）
  if (type === 'retailStore' || type === 'deliveryStore') {
    const empId = String(r[C.id] || '').trim();
    employeeList.push({
      id: empId,
      name: String(r[C.name] || '').trim(),
      title: String(r[C.title] || '').trim(),
      store: displayName,
      dept: displayDept,
      cat: type === 'retailStore' ? '零售' : '交付',
      labor: Math.round(labor * 100) / 100,
      isIntern: isIntern,
      orders: personnelOrderMap[empId] !== undefined ? personnelOrderMap[empId] : null,
    });
  }
});

// ── 补充订单数据 ─────────────────────────────────────────────────────────────
Object.values(storeMap).forEach(s => {
  if (s._type === 'retailStore' && orderMap[s.name]) {
    s.orders_actual = orderMap[s.name].actual;
    s.orders_target = orderMap[s.name].target;
  }
});

// ── 计算 fixed（固定薪酬 = 总人工成本 - 绩效） ──────────────────────────────
Object.values(storeMap).forEach(s => {
  s.fixed = Math.round(s.labor - s.perf);
  s.labor = Math.round(s.labor);
  s.perf = Math.round(s.perf);
  s.overtime_legal = Math.round(s.overtime_legal);
  s.travel = Math.round(s.travel);
  s.social = Math.round(s.social);
  s.intern_labor = Math.round(s.intern_labor);
  delete s._type;
});

// ── 整理各分类数组 ────────────────────────────────────────────────────────────
const allEntries = Object.entries(storeMap);

const retailStores    = allEntries.filter(([,v]) => !v._type_del && classify_by_name(v, 'retail')).map(([,v]) => v);
const deliveryStores  = allEntries.filter(([,v]) => classify_by_name(v, 'delivery')).map(([,v]) => v);
const supportDepts    = allEntries.filter(([,v]) => classify_by_name(v, 'support')).map(([,v]) => v);
const deliverySupport = allEntries.filter(([,v]) => classify_by_name(v, 'delsupp')).map(([,v]) => v);

// 补丁：storeMap 已经 delete _type，需要重新判断
// 重新构建分类数组
const retailStores2 = [], deliveryStores2 = [], supportDepts2 = [], deliverySupport2 = [];

// 重新遍历原始数据（按 key 前缀判断）
Object.entries(storeMap).forEach(([key, v]) => {
  if (key === 'headquarters' || key.startsWith('support_')) {
    supportDepts2.push(v);
  } else if (key === '交付_support') {
    deliverySupport2.push(v);
  } else {
    // 判断是否交付店（通过 dept 字段）
    if (v.dept === '交付') {
      deliveryStores2.push(v);
    } else {
      retailStores2.push(v);
    }
  }
});

function classify_by_name(v, t) { return false; } // placeholder, not used

// ── 按战区名称对支持部门排序（总部排第一）────────────────────────────────────
supportDepts2.sort((a, b) => {
  if (a.name === '战区总部') return -1;
  if (b.name === '战区总部') return 1;
  return 0;
});

// ── 输出 JSON ─────────────────────────────────────────────────────────────────
const output = {
  period: periodLabel,
  retailStores: retailStores2,
  supportDepts: supportDepts2,
  deliveryStores: deliveryStores2,
  deliverySupport: deliverySupport2,
  employees: employeeList,
};
if (deliveryTotal !== null) output.deliveryTotal = deliveryTotal;

if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });
const outPath = path.join(outDir, `${periodKey}.json`);
fs.writeFileSync(outPath, JSON.stringify(output, null, 2), 'utf-8');

console.log(`✓ 写入 ${outPath}`);
console.log(`  零售门店: ${retailStores2.length} 家`);
console.log(`  支持部门: ${supportDepts2.length} 个`);
console.log(`  交付门店: ${deliveryStores2.length} 家`);
console.log(`  交付支持: ${deliverySupport2.length} 个`);
console.log(`  员工记录: ${employeeList.length} 人`);
