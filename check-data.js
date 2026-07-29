const d = require('./data-anhui/2026-04.json');
const emps = d.employees;
const ALLOWED_TITLES = ['产品专家','产品专员','储备管理','高级产品专家','资深产品专家','零售主管'];
const htd = emps.some(e=>e.title);
const filtered = emps.filter(e => {
  if(e.isIntern===true) return false;
  if(e.name===null||e.name===undefined||e.name==='') return false;
  if(htd && (e.title===null||e.title===undefined||ALLOWED_TITLES.indexOf(e.title)===-1)) return false;
  return true;
});
console.log('filtered count:', filtered.length);
const withOrders = filtered.filter(e=>e.orders>0);
console.log('with orders>0:', withOrders.length);
const pts = filtered.map(e=>({name:e.name,x:e.labor||0,y:typeof e.orders==='number'?e.orders:0}));
const vp = pts.filter(p=>p.x>0);
console.log('vp count:', vp.length);
console.log('sample:', vp.slice(0,3));
