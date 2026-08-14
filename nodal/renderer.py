"""nodal.renderer — génère la visualisation HTML autonome (zéro dépendance)."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from .analyzer import Graph, layout


def render_html(graph: Graph, output: str | Path) -> Path:
    """Écrit la visualisation interactive dans `output` et retourne son chemin."""
    data = {
        "path": Path(graph.path).name,
        "functions": [asdict(f) for f in graph.functions],
        "externals": [asdict(e) for e in graph.externals],
        "classes": [asdict(c) for c in graph.classes],
        "edges": [asdict(e) for e in graph.edges],
        "depth": layout(graph),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    out = Path(output)
    out.write_text(_TEMPLATE.replace("/*__DATA__*/null", payload), encoding="utf-8")
    return out


def render_markdown(graph: Graph, output: str | Path) -> Path:
    """Export texte : résumé du graphe d'appels en Markdown."""
    lines = [f"# Graphe d'appels — `{Path(graph.path).name}`", ""]
    by_src: dict[str, list] = {}
    for e in graph.edges:
        by_src.setdefault(e.src, []).append(e)
    for cls in graph.classes:
        lines += [f"## classe `{cls.name}`", ""]
        for m in cls.members:
            lines += _md_entry(m, by_src, indent="")
    lines += ["## fonctions", ""]
    for f in graph.functions:
        if f.cls is None:
            lines += _md_entry(f.id, by_src, indent="")
    out = Path(output)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def _md_entry(fid: str, by_src: dict, indent: str) -> list[str]:
    rows = [f"{indent}- **{fid}**"]
    for e in by_src.get(fid, []):
        arrow = "⇢ externe" if e.external else "→"
        dst = e.dst.removeprefix("ext:")
        rows.append(f"{indent}  - {arrow} `{dst}` (ligne {e.lineno})")
    return rows


# --------------------------------------------------------------------------- #
# Template HTML autonome
# --------------------------------------------------------------------------- #

_TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>nodal — graphe d'appels</title>
<style>
:root{
  --bg:#151517; --grid:#232327; --panel:#1e1e22; --line:#35353d;
  --node:#26262b; --node-border:#3a3a44; --text:#d6d6dc; --dim:#77777f;
  --fn:#3d6fb8; --method:#7a5cc7; --ext:#c06a33; --frame:#2e4a4a;
  --wire:#8fb6f2; --wire-ext:#e08a4e; --accent:#e6c25a;
  --mono:ui-monospace,'Cascadia Code','JetBrains Mono',Menlo,Consolas,monospace;
}
*{box-sizing:border-box;margin:0}
html,body{height:100%;overflow:hidden;background:var(--bg);color:var(--text);
  font:13px/1.5 var(--mono)}
/* ---------- barre d'outils ---------- */
#bar{position:fixed;inset:0 0 auto 0;z-index:30;display:flex;gap:10px;
  align-items:center;padding:10px 14px;background:color-mix(in srgb,var(--panel) 88%,transparent);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line);flex-wrap:wrap}
#bar b{color:var(--accent);font-weight:600;letter-spacing:.04em}
#bar .file{color:var(--dim)}
#search{background:var(--bg);border:1px solid var(--line);color:var(--text);
  border-radius:6px;padding:5px 10px;width:200px;font:inherit;outline:none}
#search:focus{border-color:var(--wire)}
.tgl{display:flex;align-items:center;gap:5px;color:var(--dim);cursor:pointer;
  user-select:none;padding:4px 8px;border-radius:6px;border:1px solid transparent}
.tgl input{accent-color:var(--accent)}
.tgl:hover{border-color:var(--line)}
button{background:var(--bg);border:1px solid var(--line);color:var(--text);
  border-radius:6px;padding:5px 10px;font:inherit;cursor:pointer}
button:hover{border-color:var(--accent)}
#stats{margin-left:auto;color:var(--dim)}
#hint{position:fixed;bottom:10px;left:14px;color:var(--dim);z-index:30;font-size:12px}
/* ---------- scène ---------- */
#viewport{position:absolute;inset:0;cursor:grab;
  background-image:radial-gradient(var(--grid) 1.5px,transparent 1.5px);
  background-size:26px 26px}
#viewport.panning{cursor:grabbing}
#world{position:absolute;top:0;left:0;transform-origin:0 0}
#frames,#nodes{position:absolute;top:0;left:0}
#wires{position:absolute;top:0;left:0;overflow:visible;pointer-events:none}
/* ---------- cadres de classe ---------- */
.frame{position:absolute;border-radius:14px;border:1.5px dashed color-mix(in srgb,var(--frame) 60%,#7ecfcf);
  background:color-mix(in srgb,var(--frame) 26%,transparent);pointer-events:none}
.frame span{position:absolute;top:8px;left:12px;color:#8fd4d4;letter-spacing:.06em;
  font-weight:600;background:#1a2626;border:1px solid #35504f;border-radius:6px;
  padding:2px 10px}
.frame span::before{content:'class ';color:var(--dim);font-weight:400}
/* ---------- nœuds ---------- */
.node{position:absolute;width:340px;background:var(--node);border:1px solid var(--node-border);
  border-radius:9px;box-shadow:0 10px 28px rgba(0,0,0,.45);user-select:none}
.node.sel{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),0 12px 30px rgba(0,0,0,.55)}
.node.faded{opacity:.16;pointer-events:none}
.node header{display:flex;align-items:center;gap:8px;padding:7px 12px;cursor:grab;
  border-radius:8px 8px 0 0;color:#fff;font-weight:600}
.node.collapsed header{border-radius:8px}
.node[data-kind=function] header{background:linear-gradient(180deg,color-mix(in srgb,var(--fn) 92%,#fff),var(--fn))}
.node[data-kind=method]   header{background:linear-gradient(180deg,color-mix(in srgb,var(--method) 92%,#fff),var(--method))}
.node[data-kind=external] header{background:linear-gradient(180deg,color-mix(in srgb,var(--ext) 92%,#fff),var(--ext))}
.node header .sig{font-weight:400;opacity:.75;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.node header .chev{margin-left:auto;cursor:pointer;opacity:.8;padding:0 2px}
.node header .eye{cursor:pointer;opacity:.8;padding:0 2px}
.node header .chev:hover,.node header .eye:hover{opacity:1}
.code{padding:8px 0;max-height:300px;overflow:auto;scrollbar-width:thin;
  scrollbar-color:var(--line) transparent}
.node.collapsed .code{display:none}
.ln{padding:0 14px 0 12px;white-space:pre;color:var(--text);position:relative}
.ln.call{background:color-mix(in srgb,var(--accent) 10%,transparent)}
.ln.call::after{content:'';position:absolute;right:-6px;top:50%;width:10px;height:10px;
  transform:translateY(-50%);border-radius:50%;background:var(--accent);
  border:2px solid var(--node)}
.node .in{position:absolute;left:-6px;top:14px;width:10px;height:10px;border-radius:50%;
  background:var(--wire);border:2px solid var(--node)}
.node[data-kind=external] .in{background:var(--wire-ext)}
.ext-list{padding:8px 14px;color:var(--dim)}
.ext-list div::before{content:'· ';color:var(--ext)}
/* ---------- coloration ---------- */
.k{color:#c792ea}.s{color:#9ccc76}.c{color:#5d5d66;font-style:italic}
.n{color:#e3a86e}.d{color:#7fb4f0;font-weight:600}
/* ---------- fils ---------- */
path.w{fill:none;stroke:var(--wire);stroke-width:2;opacity:.55}
path.w.ext{stroke:var(--wire-ext)}
path.w.hot{opacity:1;stroke-width:2.6;stroke-dasharray:7 5;animation:flow .5s linear infinite}
@keyframes flow{to{stroke-dashoffset:-12}}
path.w.off{opacity:.06}
</style>
</head>
<body>
<div id="bar">
  <b>nodal</b><span class="file" id="file"></span>
  <input id="search" placeholder="filtrer les nœuds…" spellcheck="false">
  <label class="tgl"><input type="checkbox" id="t-fn" checked>fonctions</label>
  <label class="tgl"><input type="checkbox" id="t-me" checked>méthodes</label>
  <label class="tgl"><input type="checkbox" id="t-ex" checked>externes</label>
  <button id="reset">Tout réafficher</button>
  <button id="fit">Recentrer</button>
  <span id="stats"></span>
</div>
<div id="viewport">
  <div id="world">
    <div id="frames"></div>
    <svg id="wires"></svg>
    <div id="nodes"></div>
  </div>
</div>
<div id="hint">glisser : déplacer · molette : zoom · fond : panoramique · ◌ jaune = ligne d'appel</div>
<script>
const DATA = /*__DATA__*/null;

const world=document.getElementById('world'),vp=document.getElementById('viewport'),
      svg=document.getElementById('wires'),layerN=document.getElementById('nodes'),
      layerF=document.getElementById('frames');
const view={x:60,y:90,k:1};
const nodes=new Map();        // id -> {el,x,y,kind,cls,hidden,collapsed,lineno}
let sel=null;

/* ---------- coloration syntaxique (tokenizer une passe) ---------- */
const TOK=/(#.*$)|('(?:\\.|[^'\\])*'|"(?:\\.|[^"\\])*")|\b(def|class|return|if|elif|else|for|while|try|except|finally|with|as|import|from|pass|raise|yield|lambda|and|or|not|in|is|None|True|False|async|await|self|cls)\b|\b(\d+\.?\d*)\b/g;
const esc=x=>x.replace(/&/g,'&amp;').replace(/</g,'&lt;');
function hl(line){
  let out='',last=0,m;TOK.lastIndex=0;
  while((m=TOK.exec(line))){
    out+=esc(line.slice(last,m.index));
    const cls=m[1]?'c':m[2]?'s':m[3]?'k':'n';
    out+=`<span class="${cls}">${esc(m[0])}</span>`;
    last=m.index+m[0].length;
    if(m[1])break;                                   // commentaire -> fin de ligne
  }
  out+=esc(line.slice(last));
  return out.replace(/(<span class="k">def<\/span> )(\w+)/,
                     '$1<span class="d">$2</span>')||' ';
}

/* ---------- construction des nœuds ---------- */
function makeNode(f){
  const el=document.createElement('div');
  el.className='node';el.dataset.kind=f.kind;el.dataset.id=f.id;
  const title=f.cls?`${f.cls}.<b>${f.name}</b>`:f.name;
  el.innerHTML=`<span class="in"></span>
    <header><span>${title}</span><span class="sig">${f.signature||''}</span>
    <span class="eye" title="masquer">👁</span><span class="chev" title="replier">▾</span></header>`;
  if(f.kind==='external'){
    const d=document.createElement('div');d.className='ext-list code';
    d.innerHTML=(f.members.length?f.members:['(appel direct)']).map(m=>`<div>${m}</div>`).join('');
    el.appendChild(d);
  }else{
    const code=document.createElement('div');code.className='code';
    f.source.split('\n').forEach((l,i)=>{
      const d=document.createElement('div');d.className='ln';d.dataset.l=f.lineno+i;
      d.innerHTML=hl(l)||' ';code.appendChild(d);
    });
    el.appendChild(code);
  }
  layerN.appendChild(el);
  return el;
}

/* Colonnes par profondeur, empilement vertical, membres de classe adjacents. */
function build(){
  document.getElementById('file').textContent=' · '+DATA.path;
  const cols={};
  const all=[...DATA.functions,...DATA.externals.map(e=>({...e,kind:'external',cls:null,lineno:0}))];
  all.sort((a,b)=>(a.cls||'').localeCompare(b.cls||''));
  for(const f of all){
    const d=DATA.depth[f.id]??0;(cols[d]??=[]).push(f);
  }
  for(const[d,list]of Object.entries(cols)){
    let y=0,prevCls;
    for(const f of list){
      if(f.cls!==prevCls){y+=prevCls===undefined?0:64;prevCls=f.cls;}
      const el=makeNode(f);
      const n={el,x:+d*430,y,kind:f.kind,cls:f.cls,hidden:false,collapsed:false,lineno:f.lineno};
      nodes.set(f.id,n);place(n);
      y+=el.offsetHeight+46;
    }
  }
  // fils : marquer les lignes d'appel dans la source
  for(const e of DATA.edges){
    const src=nodes.get(e.src);if(!src)continue;
    const ln=src.el.querySelector(`.ln[data-l="${e.lineno}"]`);
    if(ln)ln.classList.add('call');
  }
}
function place(n){n.el.style.transform=`translate(${n.x}px,${n.y}px)`}

/* ---------- fils (béziers) ---------- */
function anchor(el){                    // coords écran -> coords monde
  const r=el.getBoundingClientRect();
  return{x:(r.left-view.x)/view.k,y:(r.top-view.y)/view.k,
         w:r.width/view.k,h:r.height/view.k};
}
function drawWires(){
  svg.innerHTML='';
  for(const e of DATA.edges){
    const s=nodes.get(e.src),t=nodes.get(e.dst);
    if(!s||!t||s.hidden||t.hidden||s.el.classList.contains('faded')||t.el.classList.contains('faded'))continue;
    let srcEl=s.collapsed?null:s.el.querySelector(`.ln[data-l="${e.lineno}"]`);
    const sa=anchor(srcEl||s.el.querySelector('header'));
    const ta=anchor(t.el.querySelector('.in'));
    const x1=sa.x+sa.w+ (srcEl?6:0), y1=sa.y+sa.h/2;
    const x2=ta.x+ta.w/2, y2=ta.y+ta.h/2;
    const dx=Math.max(60,Math.abs(x2-x1)*.45);
    const p=document.createElementNS('http://www.w3.org/2000/svg','path');
    p.setAttribute('d',`M${x1},${y1} C${x1+dx},${y1} ${x2-dx},${y2} ${x2},${y2}`);
    p.setAttribute('class','w'+(e.external?' ext':''));
    if(sel){p.classList.add(e.src===sel||e.dst===sel?'hot':'off');}
    svg.appendChild(p);
  }
}

/* ---------- cadres de classe ---------- */
function drawFrames(){
  layerF.innerHTML='';
  for(const c of DATA.classes){
    const members=c.members.map(id=>nodes.get(id)).filter(n=>n&&!n.hidden);
    if(!members.length)continue;
    const P=26;
    const x=Math.min(...members.map(n=>n.x))-P,
          y=Math.min(...members.map(n=>n.y))-P-30,
          X=Math.max(...members.map(n=>n.x+n.el.offsetWidth))+P,
          Y=Math.max(...members.map(n=>n.y+n.el.offsetHeight))+P;
    const f=document.createElement('div');f.className='frame';
    f.style.cssText=`left:${x}px;top:${y}px;width:${X-x}px;height:${Y-y}px`;
    f.innerHTML=`<span>${c.name}</span>`;
    layerF.appendChild(f);
  }
}

/* ---------- filtres ---------- */
function applyFilters(){
  const q=document.getElementById('search').value.trim().toLowerCase();
  const show={function:tFn.checked,method:tMe.checked,external:tEx.checked};
  let visible=0;
  for(const[id,n]of nodes){
    const okKind=show[n.kind];
    const okText=!q||id.toLowerCase().includes(q);
    n.el.classList.toggle('faded',!(okKind&&okText));
    n.el.style.display=n.hidden?'none':'';
    if(okKind&&okText&&!n.hidden)visible++;
  }
  document.getElementById('stats').textContent=
    `${visible}/${nodes.size} nœuds · ${DATA.edges.length} appels`;
  drawFrames();drawWires();
}

/* ---------- interactions ---------- */
function applyView(){world.style.transform=`translate(${view.x}px,${view.y}px) scale(${view.k})`}
let drag=null;
vp.addEventListener('pointerdown',ev=>{
  const header=ev.target.closest('header'),nodeEl=ev.target.closest('.node');
  if(ev.target.classList.contains('chev')||ev.target.classList.contains('eye'))return;
  if(nodeEl&&(header||ev.target===nodeEl)){
    const n=nodes.get(nodeEl.dataset.id);
    select(nodeEl.dataset.id);
    drag={n,px:ev.clientX,py:ev.clientY};
  }else if(!nodeEl){
    select(null);
    drag={pan:true,px:ev.clientX,py:ev.clientY};vp.classList.add('panning');
  }
  vp.setPointerCapture(ev.pointerId);
});
vp.addEventListener('pointermove',ev=>{
  if(!drag)return;
  const dx=ev.clientX-drag.px,dy=ev.clientY-drag.py;
  drag.px=ev.clientX;drag.py=ev.clientY;
  if(drag.pan){view.x+=dx;view.y+=dy;applyView();}
  else{drag.n.x+=dx/view.k;drag.n.y+=dy/view.k;place(drag.n);drawFrames();}
  drawWires();
});
vp.addEventListener('pointerup',()=>{drag=null;vp.classList.remove('panning')});
vp.addEventListener('wheel',ev=>{
  ev.preventDefault();
  const k=Math.min(2.2,Math.max(.2,view.k*(ev.deltaY<0?1.1:1/1.1)));
  view.x=ev.clientX-(ev.clientX-view.x)*k/view.k;
  view.y=ev.clientY-(ev.clientY-view.y)*k/view.k;
  view.k=k;applyView();drawWires();
},{passive:false});
layerN.addEventListener('click',ev=>{
  const el=ev.target.closest('.node');if(!el)return;
  const n=nodes.get(el.dataset.id);
  if(ev.target.classList.contains('chev')){
    n.collapsed=!n.collapsed;el.classList.toggle('collapsed',n.collapsed);
    ev.target.textContent=n.collapsed?'▸':'▾';drawFrames();drawWires();
  }else if(ev.target.classList.contains('eye')){
    n.hidden=true;applyFilters();
  }
});
function select(id){
  sel=id;
  for(const[i,n]of nodes)n.el.classList.toggle('sel',i===id);
  drawWires();
}
function fit(){
  let X=1/0,Y=1/0,X2=-1/0,Y2=-1/0;
  for(const n of nodes.values()){if(n.hidden)continue;
    X=Math.min(X,n.x);Y=Math.min(Y,n.y);
    X2=Math.max(X2,n.x+n.el.offsetWidth);Y2=Math.max(Y2,n.y+n.el.offsetHeight);}
  const k=Math.min(1,(innerWidth-80)/(X2-X),(innerHeight-140)/(Y2-Y));
  view.k=Math.max(.2,k);
  view.x=(innerWidth-(X2-X)*view.k)/2-X*view.k;
  view.y=90+((innerHeight-90)-(Y2-Y)*view.k)/2-Y*view.k;
  applyView();drawWires();
}
const tFn=document.getElementById('t-fn'),tMe=document.getElementById('t-me'),
      tEx=document.getElementById('t-ex');
[tFn,tMe,tEx].forEach(t=>t.addEventListener('change',applyFilters));
document.getElementById('search').addEventListener('input',applyFilters);
document.getElementById('reset').addEventListener('click',()=>{
  for(const n of nodes.values())n.hidden=false;
  document.getElementById('search').value='';applyFilters();
});
document.getElementById('fit').addEventListener('click',fit);
addEventListener('resize',drawWires);

build();applyFilters();fit();
</script>
</body>
</html>
"""
