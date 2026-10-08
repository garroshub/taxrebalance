"use strict";

let database=null;
let gridData=null;
let activeScenario=null;
let currentCase=0;
let currentMethod="two_stage_convex_heuristic";
const ids={
  hold:"Hold current positions",
  risk_only_rebalance:"Risk-only rebalance",
  greedy_loss_harvest:"Greedy loss harvesting",
  two_stage_convex_heuristic:"Tax-aware convex heuristic",
  enumerated_global_small_continuous:"Four-asset benchmark"
};
const el=id=>document.getElementById(id);
const scenario=()=>activeScenario||database.cases[currentCase];
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
  activeScenario=null;
  const base=database.cases[index];
  el("teInput").value=(Number(base.parameters.max_tracking_error_pct)/100).toFixed(3);
  el("feeInput").value=String(Number(base.parameters.transaction_cost_bps));
  el("lossInput").value=String(Number(base.parameters.loss_utilization));
  el("futureInput").value=String(Number(base.parameters.future_recapture_fraction));
  applyAssumptions();
}
function applyAssumptions(){
  if(!database||!gridData)return;
  const base=database.cases[currentCase];
  const country=base.currency==="CAD"?"CA":"US";
  const affiliated=country==="CA"&&
    Boolean(base.superficial_loss_watch?.lookback_30d_flagged_tickers?.length);
  const te=Number(el("teInput").value);
  const fee=Number(el("feeInput").value);
  const loss=Number(el("lossInput").value);
  const recapture=Number(el("futureInput").value);
  const key=country+":"+(affiliated?1:0)+":"+te.toFixed(3)+":"+fee+":"+loss.toFixed(1)+":"+recapture.toFixed(1);
  const record=gridData.cases.find(x=>x.key===key);
  if(!record){
    el("assumptionNote").textContent="No solved result for this combination. The previous result is unchanged.";
    return;
  }
  activeScenario={...base,methods:record.methods,
    max_tracking_error:te,
    parameters:{...base.parameters,max_tracking_error_pct:te*100,
      transaction_cost_bps:fee,loss_utilization:loss,
      future_recapture_fraction:recapture}};
  const s=scenario();
  const canada=isCanada();
  el("assumptionNote").textContent="Results were computed for the four settings shown.";
  el("countrySelect").value=canada?"CA":"US";
  el("jurisdictionLabel").textContent=canada?"Canada (average ACB)":"United States (tax lots)";
  el("jurisdictionWarning").textContent=canada?
    "Canadian simulated CAD portfolio. ACB is averaged per identical security. A recent purchase may affect superficial-loss treatment, and post-sale holdings require a 30-day review. The tax calculation assumes a 50% inclusion rate and a 42% marginal rate.":
    "U.S. simulated USD portfolio. The model selects individual tax lots and flags recent replacement purchases. Wash-sale eligibility also depends on other accounts and substantially identical securities.";
  el("kTaxBasisLabel").textContent=canada?"Average ACB pools":"Individual tax lots";
  el("taxBasisHeading").textContent=canada?"Canadian ACB inventory":"U.S. tax-lot inventory";
  el("taxBasisSubtitle").textContent=canada?
    "Pooled average cost for identical securities across the taxpayer's simulated taxable accounts":
    "Individual historic purchase lots within one synthetic U.S. taxable account";
  el("taxBasisBadge").textContent=canada?"AVERAGE ACB BY SECURITY":"COST BASIS BY LOT";
  el("lotBasisHeader").textContent=canada?"ACB pool":"Tax lot";
  el("taxRuleWarning").textContent=canada?
    "The Canadian simulation averages the adjusted cost base of identical securities across the taxpayer's own taxable accounts. A superficial loss can depend on acquisitions by the taxpayer or affiliated persons during the 30 days before or after a loss sale, and on ownership 30 days afterward. The model flags known recent purchases. A complete determination would require linked-account and subsequent trading records.":
    "U.S. wash-sale restrictions can include substantially identical securities bought in other accounts and retirement accounts. This simulation prevents simultaneous buying and selling of the same ticker and flags known recent purchases. It does not test all related securities or later transactions.";
  el("taxRulesLink").href=canada?
    "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/special-rules-other-transactions.html":
    "https://www.irs.gov/publications/p550";
  el("taxRulesLink").textContent=canada?"CRA: Canadian ACB rules ↗":"IRS Publication 550 ↗";
  el("kEquity").textContent=usd(s.equity).replace(".00","");
  el("kTE").textContent=number(s.parameters.max_tracking_error_pct,2)+"%";
  el("kLots").textContent=String(s.tax_lots.length).padStart(2,"0");
  const nLoss=s.tax_lots.filter(x=>x.unrealized_gain_loss<0).length;
  el("kLossLots").textContent=nLoss+(canada?" pools with an unrealized loss":" lots with an unrealized loss");
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
  renderPMSummary(s);
}
function renderWeights(s){
  const box=el("weightsChart");
  box.replaceChildren();
  const after=selection()?.post_weights||[];
  const scale=Math.max(.45,...s.initial_weights,...s.target_weights,...after.filter(Number.isFinite));
  for(let i=0;i<s.assets.length;i++){
    const w=s.initial_weights[i],tar=s.target_weights[i],post=after[i];
    const row=document.createElement("div");
    row.className="weightrow";
    row.innerHTML='<div class="weight-top"><span class="sector">'+escapeHtml(s.assets[i])+'</span><span class="nums">'+pct(w,1)+' held, '+pct(tar,1)+' target, '+pct(post,1)+' after</span></div>'+
      '<div class="bartrack"><div class="bar-current" style="width:'+Math.max(0,100*w/scale)+'%"></div></div>'+
      '<div class="bartrack"><div class="bar-target" style="width:'+Math.max(0,100*tar/scale)+'%"></div></div>'+
      '<div class="bartrack"><div class="bar-post" style="width:'+Math.max(0,100*(post||0)/scale)+'%"></div></div>';
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
       '<td>'+(z.recent_replacement_flag?'<span class="tag-flag">'+(isCanada()?"Recent purchase":"Replacement purchase")+'</span>':'<span class="muted">None in simulation</span>')+'</td>';
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
    tr.innerHTML='<td><div class="methodname">'+escapeHtml(name)+'</div><div class="methodsub">'+(m.method==="enumerated_global_small_continuous"?"81 direction combinations":"")+'</div></td>'+
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
  renderWeights(scenario());
  renderFrontier(scenario());
  renderDecision(scenario());
  renderPMSummary(scenario());
}
function renderPMSummary(s){
  const chosen=selection();
  const benchmark=s.methods.find(m=>m.method==="risk_only_rebalance");
  const title=el("pmHeadline"),desc=el("pmRationale");
  const cap=s.max_tracking_error;
  const risk=chosen.tracking_error;
  const track=el("pmRiskFill");
  track.style.width=risk===null?"0%":Math.min(100,risk/cap*100)+"%";
  track.classList.toggle("over-limit",!chosen.feasible);
  el("pmRealizedTE").textContent=pct(risk);
  el("pmRiskCaption").textContent="Limit "+pct(cap)+". "+(chosen.feasible?"Within limit.":"Limit breached.");
  const buys=chosen.trades.filter(x=>x.side==="BUY");
  const sells=chosen.trades.filter(x=>x.side==="SELL");
  const buyTickers=[...new Set(buys.map(x=>x.ticker))];
  const sellTickers=[...new Set(sells.map(x=>x.ticker))];
  const chips=el("pmTradeChips");chips.replaceChildren();
  for(const [name,items] of [["Buy",buyTickers],["Sell",sellTickers]]){
    const label=document.createElement("span");label.className="pm-chip";
    label.textContent=name+": "+(items.length?items.join(", "):"none");
    chips.appendChild(label);
  }
  const flagged=isCanada()?
    (s.superficial_loss_watch?.lookback_30d_flagged_tickers||[]):
    s.tax_lots.filter(x=>x.recent_replacement_flag).map(x=>x.ticker);
  if(flagged.length){
    const warning=document.createElement("span");
    warning.className="pm-chip pm-chip-risk";
    warning.textContent="Review recent purchase: "+[...new Set(flagged)].join(", ");
    chips.appendChild(warning);
  }
  if(!chosen.feasible){
    title.textContent="This method breaches the risk limit";
    desc.textContent="The "+(ids[chosen.method]||chosen.method)+
      " result has a tracking error of "+pct(risk)+" against a "+pct(cap)+
      " limit. Its orders should not be treated as a feasible rebalance.";
  }else if(chosen.method==="hold"){
    title.textContent="Hold the current positions";
    desc.textContent="No trades are required under this method. Compare its modeled cost with the alternatives before changing the portfolio.";
  }else{
    title.textContent="Buy "+(buyTickers.join(", ")||"none")+", sell "+(sellTickers.join(", ")||"none");
    desc.textContent=(ids[chosen.method]||chosen.method)+
      " produces "+buys.length+" purchase entries and "+sells.length+
      " sales of "+(isCanada()?"ACB pools":"tax lots")+
      ". Tracking error after these trades is "+pct(risk)+
      " against the "+pct(cap)+" limit.";
  }
  const bridge=el("pmCostBridge");bridge.replaceChildren();
  const valid=chosen.feasible&&benchmark?.feasible;
  if(!valid){
    el("pmAdvantage").textContent="—";
    el("pmAdvantageSub").textContent="Cost comparison requires two feasible methods.";
    bridge.textContent="No valid risk-only comparison at this risk limit.";
    return;
  }
  // Benefit is a decrease in the modeled combined cost, NOT a tax refund.
  const differences=[
    {label:"Modeled tax cost",value:benchmark.estimated_tax_pv-chosen.estimated_tax_pv},
    {label:"Trading fees",value:benchmark.transaction_cost-chosen.transaction_cost},
    {label:"Risk penalty",value:benchmark.risk_penalty-chosen.risk_penalty}
  ];
  const total=benchmark.objective_dollars-chosen.objective_dollars;
  const maxAbs=Math.max(1,Math.abs(total),...differences.map(x=>Math.abs(x.value)));
  el("pmAdvantage").textContent=usd(total);
  el("pmAdvantage").classList.toggle("pm-positive",total>=-.005);
  el("pmAdvantage").classList.toggle("pm-negative",total<-.005);
  el("pmAdvantageSub").textContent=total>=0?
    "Lower modeled cost than risk-only":
    "Higher modeled cost than risk-only";
  differences.push({label:"Total cost reduction",value:total,total:true});
  for(const d of differences){
    const row=document.createElement("div");row.className="bridge-row"+(d.total?" bridge-total":"");
    const barWidth=Math.max(Math.abs(d.value)<.005?0:1,Math.abs(d.value)/maxAbs*48);
    row.innerHTML='<div class="bridge-label"><span>'+escapeHtml(d.label)+
      '</span><strong class="'+(d.value>=-.005?"benefit":"cost")+'">'+
      (d.value>0?"+":"")+usd(d.value)+'</strong></div>'+
      '<div class="bridge-track"><span class="bridge-mid"></span>'+
      '<span class="bridge-bar '+(d.value>=-.005?"positive":"negative")+
      '" style="width:'+barWidth+'%;'+(d.value>=0?"left:50%":"right:50%")+'"></span></div>';
    bridge.appendChild(row);
  }
}
function totalCard(label,value,extraClass){
  return '<div class="totalbox '+(extraClass||'')+'"><label>'+escapeHtml(label)+'</label><strong>'+usd(value)+'</strong></div>';
}
function renderDecision(s){
  const d=selection();
  el("kTradeCount").textContent=String(d.trades.length).padStart(2,"0");
  const status=el("decisionStatus");
  const violation=d.violations.length?d.violations.join(", "):"None";
  status.className="decision-status"+(d.feasible?"":" invalid");
  status.innerHTML='<strong>'+(d.feasible?"Meets modeled constraints":"Breaches modeled constraints")+'</strong>'+
   '<span>Annual tracking error: '+pct(d.tracking_error)+
   '. Constraint violations: '+escapeHtml(violation)+'</span>';
  el("decisionTotals").innerHTML=
    totalCard("Modeled tax cost",d.estimated_tax_pv,"tax")+
    totalCard("Trading fees",d.transaction_cost)+
    totalCard("Risk penalty",d.risk_penalty)+
    totalCard("Total modeled cost",d.objective_dollars);
  const b=d.trades.filter(t=>t.side==="BUY").length;
  const a=d.trades.filter(t=>t.side==="SELL").length;
  let headline=b+" purchases, "+a+(isCanada()?" ACB-pool sales":" individual tax-lot sales")+
    ". Remaining cash: "+usd(d.post_cash)+".";
  if(d.method==="two_stage_convex_heuristic"){
    headline+=' Checked '+d.explored_patterns+' trade directions.';
  }
  if(d.method==="enumerated_global_small_continuous"){
    headline+=' Compared '+d.explored_patterns+' direction combinations.';
  }
  el("tradeHeadline").textContent=headline;
  const body=el("tradeBody");body.replaceChildren();
  if(!d.trades.length){
    body.innerHTML='<tr><td colspan="4" class="muted">This method keeps the existing holdings.</td></tr>';
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
  const yaxis=svgEl("text",{x:14,y:16,fill:"#adc3d0","font-size":11});yaxis.textContent="Modeled cost ("+(isCanada()?"CAD":"USD")+")";svg.appendChild(yaxis);
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
    const [response,gridResponse]=await Promise.all([
      fetch("./data/scenarios.json",{cache:"no-store"}),
      fetch("./data/assumption_grid.json",{cache:"no-store"})
    ]);
    if(!response.ok||!gridResponse.ok)throw new Error("Unable to fetch solved scenario files");
    database=await response.json();
    gridData=await gridResponse.json();
    if(!Array.isArray(database.cases)||!database.cases.length)throw new Error("Empty scenario dataset");
    if(!Array.isArray(gridData.cases)||gridData.cases.length!==108)
      throw new Error("Incomplete assumption grid. Regenerate solved cases.");
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
    for(const id of ["teInput","feeInput","lossInput","futureInput"]){
      el(id).addEventListener("change",applyAssumptions);
    }
    el("resetAssumptions").addEventListener("click",()=>{
      el("teInput").value="0.025";
      el("feeInput").value="10";
      el("lossInput").value="0.8";
      el("futureInput").value="0.2";
      applyAssumptions();
    });
    populate("CA");
  }catch(error){
    el("comparisonBody").innerHTML='<tr><td colspan="6">Saved solver results could not be loaded. Serve the docs folder over HTTP. '+escapeHtml(error.message)+'</td></tr>';
    const select=el("scenarioSelect");select.replaceChildren();
    const opt=document.createElement("option");opt.textContent="Data unavailable";select.appendChild(opt);
    console.error(error);
  }
}
document.addEventListener("DOMContentLoaded",start);
