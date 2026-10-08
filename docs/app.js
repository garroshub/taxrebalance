"use strict";

let database=null;
let currentCase=0;
let currentMethod="two_stage_convex_heuristic";
const ids={
  hold:"Do nothing",
  risk_only_rebalance:"Risk-only rebalance",
  greedy_loss_harvest:"Greedy loss harvesting",
  two_stage_convex_heuristic:"Tax-aware convex heuristic",
  enumerated_global_small_continuous:"Small global benchmark"
};
const el=id=>document.getElementById(id);
const scenario=()=>database.cases[currentCase];
const isCanada=()=>scenario().currency==="CAD";
const usd=value=>{
  if(value===null||value===undefined)return "—";
  const n=Number(value);
  const symbol=isCanada()?"C$":"US$";
  return (n<0?"−":"")+symbol+Math.abs(n).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2});
};
const number=(n,d=2)=>n===null||n===undefined?"—":Number(n).toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});
const pct=(n,d=2)=>n===null||n===undefined?"—":number(Number(n)*100,d)+"%";
const escapeHtml=str=>String(str===null||str===undefined?"":str).replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const safeDollar=n=>'<span class="'+(Number(n)<0?"loss":"")+'">'+usd(n)+'</span>';
const selection=()=>scenario().methods.find(x=>x.method===currentMethod);
function changeScenario(index){
  currentCase=index;
  const s=scenario();
  const canada=isCanada();
  el("countrySelect").value=canada?"CA":"US";
  el("jurisdictionLabel").textContent=canada?"Canada · averaged ACB model":"United States · specific tax-lot model";
  el("jurisdictionWarning").textContent=canada?
    "Canadian CAD simulation: average ACB, not elective U.S. tax lots. Superficial-loss screening uses recent purchases and requires day+30 follow-up. Assumed 50% capital-gain inclusion and 42% marginal rate; not tax advice.":
    "U.S. USD simulated tax-lots. Modeled wash-sale proxy is not full legal compliance; modeled loss usage and future taxes are assumptions, not actual refunds.";
  el("kTaxBasisLabel").textContent=canada?"Average ACB pools":"Individual tax lots";
  el("taxBasisHeading").textContent=canada?"Canadian ACB inventory":"U.S. tax-lot inventory";
  el("taxBasisSubtitle").textContent=canada?
    "Pooled average cost for identical securities across the taxpayer's simulated taxable accounts":
    "Individual historic purchase lots within one synthetic U.S. taxable account";
  el("taxBasisBadge").textContent=canada?"AVERAGE ACB BY SECURITY":"COST BASIS BY LOT";
  el("lotBasisHeader").textContent=canada?"ACB pool":"Tax lot";
  el("taxRuleWarning").textContent=canada?
    "Canada: Capital gains and losses use an average adjusted cost base (ACB) for identical property. A superficial loss can depend on acquisition of identical property by you or affiliated persons during the 30 days before/after a sale AND continued ownership at day+30. The model flags lookbacks and assumes future monitoring, without assessing the complete rule, adjusted bases or linked-account trades. The 50% inclusion fraction and investor tax rate are illustrative inputs.":
    "U.S. wash-sale rules may involve substantially identical securities, IRAs and related accounts. The model prohibits simultaneous buys and sells of the same ticker and flags supplied recent replacement buys, but cannot determine complete wash-sale compliance. Conditional tax benefits are simulation assumptions, not cash refunds.";
  el("taxRulesLink").href=canada?
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/special-rules-other-transactions.html":
    "https://www.irs.gov/publications/p550";
  el("taxRulesLink").textContent=canada?"CRA: Canadian ACB rules ↗":"IRS Publication 550 ↗";
  el("assTE").textContent=number(s.parameters.max_tracking_error_pct,2)+"%";
  el("assFee").textContent=number(s.parameters.transaction_cost_bps,0)+" bps";
  el("assUtil").textContent=number(s.parameters.loss_utilization*100,0)+"%";
  el("assFuture").textContent=number(s.parameters.future_recapture_fraction*100,0)+"%";
  el("kEquity").textContent=usd(s.equity).replace(".00","");
  el("kTE").textContent=number(s.parameters.max_tracking_error_pct,2)+"%";
  el("kLots").textContent=String(s.tax_lots.length).padStart(2,"0");
  const nLoss=s.tax_lots.filter(x=>x.unrealized_gain_loss<0).length;
  el("kLossLots").textContent=nLoss+(canada?" loss-bearing ACB pools":" unrealized-loss lots");
  if(!s.methods.some(x=>x.method===currentMethod))currentMethod="two_stage_convex_heuristic";
  const choice=el("methodSelect");
  choice.replaceChildren();
  s.methods.forEach(method=>{
    const opt=document.createElement("option");
    opt.value=method.method;
    opt.textContent=canada&&method.method==="greedy_loss_harvest"?
      "Greedy ACB harvesting":(ids[method.method]||method.method);
    choice.appendChild(opt);
  });
  choice.value=currentMethod;
  renderWeights(s);
  renderLots(s);
  renderComparison(s);
  renderFrontier(s);
  renderDecision(s);
}
function renderWeights(s){
  const box=el("weightsChart");
  box.replaceChildren();
  for(let i=0;i<s.assets.length;i++){
    const w=s.initial_weights[i],tar=s.target_weights[i];
    const row=document.createElement("div");
    row.className="weightrow";
    row.innerHTML='<div class="weight-top"><span class="sector">'+escapeHtml(s.assets[i])+'</span><span class="nums">'+pct(w,1)+' → '+pct(tar,1)+'</span></div>'+
      '<div class="bartrack"><div class="bar-current" style="width:'+Math.min(100,w*160)+'%"></div></div>'+
      '<div class="bartrack"><div class="bar-target" style="width:'+Math.min(100,tar*160)+'%"></div></div>';
    box.appendChild(row);
  }
}
function renderLots(s){
  const body=el("taxLotBody");body.replaceChildren();
  for(const z of s.tax_lots){
    const tr=document.createElement("tr");
    tr.innerHTML='<td>'+escapeHtml(z.lot_id)+'</td><td>'+escapeHtml(z.ticker)+'</td>'+
       '<td>'+number(z.shares,0)+'</td><td>'+usd(z.basis_per_share)+'</td>'+
       '<td>'+usd(s.prices[z.ticker])+'</td><td class="'+(z.unrealized_gain_loss<0?"loss":"gain")+'">'+usd(z.unrealized_gain_loss)+'</td>'+
       '<td>'+(z.recent_replacement_flag?'<span class="tag-flag">'+(isCanada()?"30d lookback review":"Review replacement")+'</span>':'<span class="muted">No known flag</span>')+'</td>';
    body.appendChild(tr);
  }
}
function renderComparison(s){
  const body=el("comparisonBody");body.replaceChildren();
  s.methods.forEach(m=>{
    const tr=document.createElement("tr");
    tr.className="pickable"+(m.method===currentMethod?" selected":"");
    tr.tabIndex=0;
    const status=m.feasible?'<span class="status-feasible">Feasible</span>':'<span class="status-invalid">Not feasible</span>';
    const name=isCanada()&&m.method==="greedy_loss_harvest"?"Greedy ACB harvesting":(ids[m.method]||m.method);
    tr.innerHTML='<td><div class="methodname">'+escapeHtml(name)+'</div><div class="methodsub">'+(m.method==="two_stage_convex_heuristic"?"Main research algorithm":m.method==="enumerated_global_small_continuous"?"3⁴ convex direction patterns":"")+'</div></td>'+
      '<td>'+pct(m.tracking_error)+'</td><td>'+usd(m.estimated_tax_pv)+'</td>'+
      '<td>'+usd(m.transaction_cost)+'</td><td>'+usd(m.objective_dollars)+'</td><td>'+status+'</td>';
    tr.addEventListener("click",()=>pickMethod(m.method));
    tr.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();pickMethod(m.method);}});
    body.appendChild(tr);
  });
}
function pickMethod(name){
  currentMethod=name;
  el("methodSelect").value=name;
  renderComparison(scenario());
  renderFrontier(scenario());
  renderDecision(scenario());
}
function totalCard(label,value,extraClass){
  return '<div class="totalbox '+(extraClass||'')+'"><label>'+escapeHtml(label)+'</label><strong>'+usd(value)+'</strong></div>';
}
function renderDecision(s){
  const d=selection();
  const status=el("decisionStatus");
  const violation=d.violations.length?d.violations.join(", "):"None";
  status.className="decision-status"+(d.feasible?"":" invalid");
  status.innerHTML='<strong>'+(d.feasible?"Feasible modeled execution":"Not executable under current limit")+'</strong>'+
   '<span>Annualized tracking error: '+pct(d.tracking_error)+' · Violations: '+escapeHtml(violation)+'</span>';
  el("decisionTotals").innerHTML=
    totalCard("Modeled net tax PV",d.estimated_tax_pv,"tax")+
    totalCard("Trading fees",d.transaction_cost)+
    totalCard("Risk-deviation penalty",d.risk_penalty)+
    totalCard("Combined objective",d.objective_dollars);
  const b=d.trades.filter(t=>t.side==="BUY").length;
  const a=d.trades.filter(t=>t.side==="SELL").length;
  let headline=b+" buy orders · "+a+(isCanada()?" ACB-pool sales":" selected tax-lot sales")+" · Remaining cash "+usd(d.post_cash);
  if(d.method==="two_stage_convex_heuristic"){
    headline+=' · Checked '+d.explored_patterns+' directions';
  }
  if(d.method==="enumerated_global_small_continuous"){
    headline+=' · Checked '+d.explored_patterns+' patterns';
  }
  el("tradeHeadline").textContent=headline;
  const body=el("tradeBody");body.replaceChildren();
  if(!d.trades.length){
    body.innerHTML='<tr><td colspan="4" class="muted">No orders recommended in this method.</td></tr>';
    return;
  }
  for(const t of d.trades){
    const tr=document.createElement("tr");
    tr.innerHTML='<td><strong class="'+(t.side==="SELL"?"gain":"loss")+'">'+
      escapeHtml(t.side)+'</strong> '+escapeHtml(t.ticker)+'</td>'+
      '<td>'+escapeHtml(t.lot_id||"New position")+'</td>'+
      '<td>'+number(t.shares,2)+'</td><td>'+usd(t.notional)+'</td>';
    body.appendChild(tr);
  }
}
function svgEl(name,attrs){
  const n=document.createElementNS("http://www.w3.org/2000/svg",name);
  Object.entries(attrs||{}).forEach(pair=>n.setAttribute(pair[0],String(pair[1])));
  return n;
}
function renderFrontier(s){
  const container=el("frontierChart");container.replaceChildren();
  const valid=s.methods.filter(m=>m.feasible&&Number.isFinite(m.tracking_error)&&Number.isFinite(m.objective_dollars));
  if(!valid.length){container.textContent="No feasible methods.";return;}
  const W=560,H=290,margin={left:76,right:27,top:26,bottom:54};
  const svg=svgEl("svg",{viewBox:"0 0 "+W+" "+H,"aria-hidden":"true"});
  const teMax=Math.max(s.max_tracking_error*1.15,...valid.map(m=>m.tracking_error*1.15),0.01);
  const vals=valid.map(m=>m.objective_dollars);
  let ymin=Math.min(...vals),ymax=Math.max(...vals);
  if(ymax-ymin<200){ymax+=100;ymin-=100;}else{const d=(ymax-ymin)*.13;ymin-=d;ymax+=d;}
  const x=t=>margin.left+t/teMax*(W-margin.left-margin.right);
  const y=v=>H-margin.bottom-(v-ymin)/(ymax-ymin)*(H-margin.top-margin.bottom);
  for(let k=0;k<=4;k++){
    const yval=ymin+(ymax-ymin)*k/4;
    const yy=y(yval);
    svg.appendChild(svgEl("line",{x1:margin.left,x2:W-margin.right,y1:yy,y2:yy,stroke:"#304354","stroke-width":1}));
    const lbl=svgEl("text",{x:margin.left-10,y:yy+4,"text-anchor":"end",fill:"#9db3c5","font-size":11});
    lbl.textContent=(Math.abs(yval)>=1000?(yval/1000).toFixed(1)+"k":Math.round(yval))+"";
    svg.appendChild(lbl);
  }
  for(let k=0;k<=4;k++){
    const xval=teMax*k/4;
    const txt=svgEl("text",{x:x(xval),y:H-26,"text-anchor":"middle",fill:"#9db3c5","font-size":11});
    txt.textContent=(xval*100).toFixed(1)+"%";svg.appendChild(txt);
  }
  svg.appendChild(svgEl("line",{x1:margin.left,y1:H-margin.bottom,x2:W-margin.right,y2:H-margin.bottom,stroke:"#597085"}));
  const axis=svgEl("text",{x:W/2,y:H-5,"text-anchor":"middle",fill:"#adc3d0","font-size":11});
  axis.textContent="Tracking error (annualized)";svg.appendChild(axis);
  const yaxis=svgEl("text",{x:14,y:16,fill:"#adc3d0","font-size":11});yaxis.textContent="Model objective ($)";svg.appendChild(yaxis);
  const boundX=x(s.max_tracking_error);
  svg.appendChild(svgEl("line",{x1:boundX,x2:boundX,y1:margin.top,y2:H-margin.bottom,stroke:"#cba26e","stroke-dasharray":"5 5","stroke-width":1}));
  valid.forEach((m,i)=>{
    const selected=m.method===currentMethod;
    const cx=x(m.tracking_error),cy=y(m.objective_dollars);
    const c=svgEl("circle",{cx,cy,r:selected?8:6,fill:selected?"#e8b76c":"#5dcbb0",stroke:"#122631","stroke-width":2});
    c.style.cursor="pointer";
    c.addEventListener("click",()=>pickMethod(m.method));
    const tooltip=svgEl("title",{});tooltip.textContent=(ids[m.method]||m.method)+": TE "+pct(m.tracking_error)+", objective "+usd(m.objective_dollars);
    c.appendChild(tooltip);svg.appendChild(c);
    const t=svgEl("text",{x:cx+9,y:cy-(i%2===0?10:-16),fill:"#c0d0db","font-size":9});
    t.textContent=(ids[m.method]||m.method).replace(" rebalance","").replace(" harvesting","").replace(" convex heuristic"," optimizer").replace("Small global benchmark","Global");
    svg.appendChild(t);
  });
  container.appendChild(svg);
}
async function start(){
  try{
    const response=await fetch("./data/scenarios.json",{cache:"no-store"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    database=await response.json();
    if(!Array.isArray(database.cases)||!database.cases.length)throw new Error("Empty scenario dataset");
    const select=el("scenarioSelect");
    function populate(country){
      select.replaceChildren();
      database.cases.forEach((s,i)=>{
        if((s.currency==="CAD")!==(country==="CA"))return;
        const opt=document.createElement("option");
        opt.value=String(i);
        opt.textContent=s.scenario;select.appendChild(opt);
      });
      if(select.options.length)changeScenario(Number(select.value));
    }
    el("countrySelect").addEventListener("change",e=>populate(e.target.value));
    select.addEventListener("change",e=>changeScenario(Number(e.target.value)));
    el("methodSelect").addEventListener("change",e=>pickMethod(e.target.value));
    populate("CA");
  }catch(error){
    el("comparisonBody").innerHTML='<tr><td colspan="6">Could not load precomputed solver results. Serve the docs folder over HTTP (e.g. python -m http.server 8000 --directory docs). '+escapeHtml(error.message)+'</td></tr>';
    const select=el("scenarioSelect");select.replaceChildren();
    const opt=document.createElement("option");opt.textContent="Data unavailable";select.appendChild(opt);
    console.error(error);
  }
}
document.addEventListener("DOMContentLoaded",start);
