'use strict';
const $ = id => document.getElementById(id);
let lastRun = null;
async function post(path, body) {
  const response = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(data.detail || data));
  return data;
}
function text(tag, value, className) {
  const el = document.createElement(tag); el.textContent = value;
  if (className) el.className = className; return el;
}
$('compare').onclick = async () => {
  $('compare').disabled = true; $('results').replaceChildren(); $('status').textContent = 'Retrieving evidence…';
  try {
    const runs = await Promise.all(['lexical','hybrid','ontology'].map(mode => post('/retrieve',{query:$('query').value,mode,k:Number($('k').value),context:[$('context').value]})));
    for (const run of runs) {
      const column = text('div','', 'column'); column.append(text('h3',run.mode));
      if (!run.results.length) column.append(text('p','No matching reviewed evidence.'));
      for (const result of run.results) {
        const e = result.evidence, item = text('article','', 'evidence');
        item.append(text('h4',result.source.title),text('p',e.passage),text('p',`${e.id} · ${e.review_status} · ${e.origin}`, 'meta'),text('p',`Context: ${e.concepts.join(', ')} · Rank score: ${result.score.toFixed(5)}`, 'meta'),text('p',`Source: ${e.source_id} · Span: ${e.start}–${e.end} · SHA-256: ${e.source_hash}`, 'meta'));
        column.append(item);
      }
      $('results').append(column);
    }
    $('status').textContent = 'Complete. Compare evidence relevance and missing assumptions; do not interpret ranking as scientific confidence.';
  } catch(error) { $('status').textContent = error.message; }
  finally { $('compare').disabled = false; }
};
const lines = id => $(id).value.split('\n').map(x=>x.trim()).filter(Boolean);
$('validate').onclick = async () => {
  try { $('validation').textContent = JSON.stringify(await post('/validate/pathway',{objective:$('objective').value,information_needs:lines('needs'),alternatives:lines('alternatives'),uncertainties:lines('uncertainties'),evidence_ids:lines('evidence')}),null,2); }
  catch(error) { $('validation').textContent=error.message; }
};
$('evaluate').onclick = async () => {
  $('evaluate').disabled=true;
  try { lastRun=await post('/evaluate',{k:Number($('k').value)}); $('evaluation').textContent=JSON.stringify(lastRun.summary,null,2)+'\n'+lastRun.limitations; $('download').disabled=false; }
  catch(error) { $('evaluation').textContent=error.message; }
  finally { $('evaluate').disabled=false; }
};
$('download').onclick = () => {
  if (!lastRun) return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(lastRun,null,2)],{type:'application/json'}));
  const link=document.createElement('a'); link.href=url;link.download='scientific-dss-benchmark.json';link.click();URL.revokeObjectURL(url);
};
fetch('/integrations').then(r=>r.json()).then(data=>{$('integrations').textContent=JSON.stringify(data,null,2);}).catch(error=>{$('integrations').textContent=error.message;});
