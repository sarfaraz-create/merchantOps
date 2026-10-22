const money=x=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',maximumFractionDigits:0}).format(x/100);
const keys=['gross','discount','refunds','cogs','shipping','fees','ad_spend','net_revenue','contribution','orders'];
const preciseMoney=x=>new Intl.NumberFormat('en-IN',{style:'currency',currency:'INR',minimumFractionDigits:2,maximumFractionDigits:2}).format(x/100);
let replayIndex=0;
const escapeHTML=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let data;const el=id=>document.getElementById(id);
function render(){
 const channel=el('channel').value;const rows=data.monthly.filter(r=>channel==='All channels'||r.channel===channel);
 const months=[...new Set(data.monthly.map(r=>r.month))].map(month=>{const a={month};keys.forEach(k=>a[k]=rows.filter(r=>r.month===month).reduce((s,r)=>s+r[k],0));return a});
 const total=k=>months.reduce((s,r)=>s+r[k],0);
 el('metrics').innerHTML=[['Net revenue',money(total('net_revenue')),'After discounts & granted refunds'],['Refunds',money(total('refunds')),'Recognised when granted'],['Contribution',money(total('contribution')),'After fulfilment, fees & advertising'],['Contribution margin',total('net_revenue')?(100*total('contribution')/total('net_revenue')).toFixed(1)+'%':'—','Contribution ÷ net revenue']].map(([t,v,n])=>`<div class="metric"><span>${t}</span><strong>${v}</strong><small>${n}</small></div>`).join('');
 const max=Math.max(...months.map(r=>Math.max(r.net_revenue,Math.abs(r.contribution))),1);
 el('chart').innerHTML=months.map(r=>`<div class="bar-row"><span>${new Date(r.month+'T00:00:00').toLocaleDateString('en',{month:'short'})}</span><div class="bars"><div class="bar green" style="width:${100*r.net_revenue/max}%"></div><div class="bar orange" style="width:${100*Math.abs(r.contribution)/max}%;${r.contribution<0?'background:repeating-linear-gradient(90deg,#d47942 0 3px,#fff 3px 5px)':''}"></div></div><span>${money(r.net_revenue)}<br>${money(r.contribution)}</span></div>`).join('');
 const a=months[0],b=months.at(-1),delta=b.contribution-a.contribution;
 el('explanation').textContent=`From January to June, gross sales ${b.gross>=a.gross?'rose':'fell'} ${money(Math.abs(b.gross-a.gross))}, while contribution ${delta>=0?'rose':'fell'} ${money(Math.abs(delta))}. Inspect the offsets below before deciding where to investigate.`;
 el('bridge').innerHTML=[['Gross sales',b.gross-a.gross],...['discount','refunds','cogs','shipping','fees','ad_spend'].map(k=>[k.replace('_',' '),a[k]-b[k]]),['Net contribution change',delta]].map(([k,v])=>`<div class="row"><span>${k}</span><strong>${v>0?'+':''}${money(v)}</strong></div>`).join('');
 const products=data.products.filter(r=>channel==='All channels'||r.channel===channel);
 const grouped=[...new Set(products.map(r=>r.product))].map(product=>{const subset=products.filter(r=>r.product===product);const sum=k=>subset.reduce((v,r)=>v+r[k],0);return {product,orders:sum('orders'),refunded:sum('refunded_orders'),refund:sum('refund_amount'),charged:sum('charged_revenue'),contribution:sum('merchandise_contribution')}});
 el('sku').innerHTML=grouped.map(r=>`<tr><td>${escapeHTML(r.product)}</td><td>${r.refunded} / ${r.orders} (${(100*r.refunded/r.orders).toFixed(1)}%)</td><td>${r.charged?(100*r.refund/r.charged).toFixed(1)+'%':'—'}</td><td>${money(r.contribution)}</td></tr>`).join('');

}
fetch('data.json').then(r=>{if(!r.ok)throw Error('Data unavailable');return r.json()}).then(d=>{data=d;render();el('retention').innerHTML=d.retention.map(r=>`<div class="cohort"><div class="row"><span>${r.cohort.slice(0,7)} · ${r.repeat_customers}/${r.eligible_customers} customers</span><strong>${(r.retention_30d*100).toFixed(1)}%</strong></div><div class="track"><div style="width:${r.retention_30d*100}%"></div></div></div>`).join('');el('sql').textContent=d.sql.monthly;el('measurement').textContent=JSON.stringify(d.measurement,null,2);
 el('acquisition').innerHTML=d.acquisition.map(r=>`<tr><td>${escapeHTML(r.channel)}</td><td>${r.first_customers}</td><td>${r.first_order_cac_paise===null?'—':money(r.first_order_cac_paise)}</td><td>${r.blended_revenue_to_spend===null?'—':r.blended_revenue_to_spend.toFixed(2)+'×'}</td></tr>`).join('');
 el('payments').innerHTML=d.payments.map(r=>`<tr><td>${escapeHTML(r.channel)}</td><td>${money(r.captured)}</td><td>${money(r.returned)}</td><td>${money(r.collection_gap)}</td><td>${money(r.refund_payable)}</td><td>${r.failed_attempts}</td></tr>`).join('');
 el('payment-exceptions').innerHTML=d.payment_exceptions.map(r=>`<tr><td>${escapeHTML(r.order_id)}</td><td>${money(r.refund_granted)}</td><td>${money(r.returned)}</td><td>${money(r.refund_payable)}</td></tr>`).join('');
 el('refund').disabled=false;el('reset').disabled=false;renderReplay();
 el('memo').innerHTML=d.memo.map(r=>`<h3>${escapeHTML(r.title)}</h3><p>${escapeHTML(r.evidence)}</p><p class="muted">${escapeHTML(r.limitation)}</p>`).join('');}).catch(e=>el('error').textContent='Could not load the verified data. Please reload.');
el('channel').addEventListener('change',()=>{if(data)render()});

function renderReplay(){
 const stages=data.replay.stages,r=stages[replayIndex],s=r.story;
 const labels=['Sales after approved refunds','Contribution after included costs','Payments received from customer','Money returned to customer','Approved refund still to return','Advertising cost'];
 const before=replayIndex?stages[replayIndex-1].story.actual:null;
 const rows=labels.map((label,i)=>`<tr><th scope="row">${label}</th><td>${before?preciseMoney(before[i]):'—'}</td><td>${preciseMoney(s.expected[i])}</td><td>${preciseMoney(s.actual[i])}</td></tr>`).join('');
 const months=r.monthly.map(m=>`${m.month.slice(0,7)}: ${preciseMoney(m.contribution)}`).join(' · ');
 el('replay').innerHTML=`<p class="eyebrow">STEP ${replayIndex+1} OF ${stages.length}</p><h3>${escapeHTML(s.title)}</h3><p>${escapeHTML(s.happened)}</p><div class="walkthrough-grid"><div><h4>What we are testing</h4><p>${escapeHTML(s.testing)}</p><h4>How the numbers work</h4><p class="worked-sum">${escapeHTML(s.calculation)}</p></div><div><h4>Why this is the right result</h4><p>${escapeHTML(s.reason)}</p><h4>What you would do</h4><p>${escapeHTML(s.action)}</p></div></div><div class="table-scroll"><table><caption>Before this step, our expected result, and the actual database result</caption><thead><tr><th scope="col">Measure</th><th scope="col">Before</th><th scope="col">Expected now</th><th scope="col">Actual now</th></tr></thead><tbody>${rows}</tbody></table></div><p><strong>${s.passed?'Check passed: actual results match the expected amounts and record counts.':'Check failed: do not rely on this result.'}</strong></p><p class="muted">Contribution by reporting month: ${months}. These are contributions, not monthly bank balances.</p>`;
 el('replay-status').textContent=replayIndex===stages.length-1?'Example complete. One approved refund reduced sales once; its payment cleared the amount owed; duplicate and unmatched records did not alter accepted totals.':`Showing step ${replayIndex+1} of ${stages.length}. Next: ${stages[replayIndex+1].story.title}.`;
 el('replay-evidence').textContent=JSON.stringify({source:r.name,orders:r.orders,product_rows:r.line_items,payment_records:r.payments,approved_refund_records:r.refunds,rejected_batches_saved:r.quarantined_batches,import_result:r.ingestion,expected_paise:s.expected,actual_paise:s.actual,check_passed:s.passed},null,2);
 el('refund').disabled=replayIndex===stages.length-1;
 el('previous').disabled=replayIndex===0;
 el('reset').disabled=replayIndex===0;
}
el('refund').addEventListener('click',()=>{if(data&&replayIndex<data.replay.stages.length-1){replayIndex++;renderReplay()}});
el('previous').addEventListener('click',()=>{if(data&&replayIndex>0){replayIndex--;renderReplay()}});
el('reset').addEventListener('click',()=>{replayIndex=0;renderReplay()});
fetch('benchmark.json').then(r=>{if(!r.ok)throw Error('missing');return r.json()}).then(b=>{
 const summary=mode=>{const runs=b.runs.filter(r=>r.mode===mode);const t=runs.map(r=>r.wall_seconds).sort((a,b)=>a-b);return `${mode}: ${t[Math.floor(t.length/2)].toFixed(2)}s median wall time; ${Math.max(...runs.map(r=>r.peak_rss_mib)).toFixed(1)} MiB largest individual process peak RSS`};
 el('benchmark-summary').textContent=`${b.outputs_equal?'All seven model hashes match across full, incremental and replayed runs.':'Output equality failed.'} ${summary('full')}. ${summary('incremental')}. Includes generation, real dbt builds, data tests and output verification. The incremental scenario does more work, so these are not like-for-like speedup timings.`;
}).catch(()=>el('benchmark-summary').textContent='Benchmark evidence unavailable. No performance claim is shown.');
