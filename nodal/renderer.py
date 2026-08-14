"""nodal.renderer — génère la visualisation HTML autonome (zéro dépendance)."""

from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from .model import Graph, layout


def render_html(graph: Graph, output: str | Path) -> Path:
    """Écrit la visualisation interactive dans `output` et retourne son chemin."""
    data = {
        "path": Path(graph.path).name,
        "functions": [asdict(f) for f in graph.functions],
        "externals": [asdict(e) for e in graph.externals],
        "classes": [asdict(c) for c in graph.classes],
        "edges": [asdict(e) for e in graph.edges],
        "depth": layout(graph),
        "lang": graph.lang,
        "files": graph.files,
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
    grouped: set[str] = set()
    for cls in graph.classes:
        lines += [f"## {cls.stereotype} `{cls.name}`", ""]
        for m in cls.members:
            lines += _md_entry(m, by_src, indent="")
            grouped.add(m)
        lines.append("")
    free = [f for f in graph.functions if f.id not in grouped]
    if free:
        lines += ["## fonctions libres", ""]
        for f in free:
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
  --fn:#3d6fb8; --method:#7a5cc7; --ext:#c06a33; --unk:#a8434a; --frame:#2e4a4a;
  --wire:#8fb6f2; --wire-ext:#e08a4e; --wire-unk:#e07a86; --accent:#e6c25a;
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
select{background:var(--bg);border:1px solid var(--line);color:var(--text);
  border-radius:6px;padding:5px 8px;font:inherit;max-width:220px}
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
.frame span::before{content:attr(data-kw);color:var(--dim);font-weight:400}
/* ---------- nœuds ---------- */
.node{position:absolute;width:340px;z-index:1;background:var(--node);border:1px solid var(--node-border);
  border-radius:9px;box-shadow:0 10px 28px rgba(0,0,0,.45);user-select:none}
.node.sel{z-index:6;border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),0 12px 30px rgba(0,0,0,.55)}
.node.faded{opacity:.16;pointer-events:none}
.code{user-select:text;cursor:auto}
.node header{display:flex;align-items:center;gap:8px;padding:7px 12px;cursor:grab;
  border-radius:8px 8px 0 0;color:#fff;font-weight:600}
.node.collapsed header{border-radius:8px}
.node:not(.collapsed){z-index:4}
.node:hover{z-index:8}
.node[data-kind=function] header{background:linear-gradient(180deg,color-mix(in srgb,var(--fn) 92%,#fff),var(--fn))}
.node[data-kind=method]   header{background:linear-gradient(180deg,color-mix(in srgb,var(--method) 92%,#fff),var(--method))}
.node[data-kind=external] header{background:linear-gradient(180deg,color-mix(in srgb,var(--ext) 92%,#fff),var(--ext))}
.node[data-ext=unknown] header{background:linear-gradient(180deg,color-mix(in srgb,var(--unk) 92%,#fff),var(--unk))}
.node[data-ext=unknown] .in{background:var(--wire-unk)}
.node[data-ext=unknown] .ext-list div::before{content:'? ';color:#e07a86}
.fbadge{font-weight:400;font-size:11px;opacity:.7;background:rgba(0,0,0,.28);
  border-radius:4px;padding:1px 6px;margin-left:2px}
.node header .sig{font-weight:400;opacity:.75;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.node header .chev{margin-left:auto;cursor:pointer;opacity:.8;padding:0 2px}
.node header .eye{cursor:pointer;opacity:.8;padding:0 2px}
.node header .chev:hover,.node header .eye:hover{opacity:1}
.code{padding:8px 0;max-height:420px;overflow:auto;scrollbar-width:thin;
  scrollbar-color:var(--line) transparent}
.node.collapsed .code{display:none}
.ln{padding:0 14px 0 12px;white-space:pre;color:var(--text);position:relative}
.ln.more{color:var(--dim);font-style:italic}
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
.p{color:#c9a06a}.k{color:#c792ea}.s{color:#9ccc76}.c{color:#5d5d66;font-style:italic}
.n{color:#e3a86e}.d{color:#7fb4f0;font-weight:600}
/* ---------- fils ---------- */
path.w{fill:none;stroke:var(--wire);stroke-width:2;opacity:.55}
path.w.ext{stroke:var(--wire-ext)}
path.w.unk{stroke:var(--wire-unk)}
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
  <select id="f-file" style="display:none"></select>
  <button id="fold">Replier tout</button>
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
<div id="hint">glisser : déplacer · molette : zoom · double-clic : isoler le voisinage · ◌ jaune = ligne d'appel</div>
<script>
const DATA = /*__DATA__*/null;

const world=document.getElementById('world'),vp=document.getElementById('viewport'),
      svg=document.getElementById('wires'),layerN=document.getElementById('nodes'),
      layerF=document.getElementById('frames');
const view={x:60,y:90,k:1};
const nodes=new Map();        // id -> {el,x,y,w,h,kind,...}
const WIRES=[];               // arêtes pré-résolues (voir build)
const BIG=(DATA.functions.length+DATA.externals.length)>120;
const COLLAPSED=BIG;          // gros graphe : code replié au départ
const LAZY=BIG;               // ... et code construit seulement au dépliage
let sel=null;

/* ---------- coloration syntaxique (tokenizer une passe) ---------- */
const KW_PY='def|class|return|if|elif|else|for|while|try|except|finally|with|as|import|from|pass|raise|yield|lambda|and|or|not|in|is|None|True|False|async|await|self|cls';
const KW_CPP='alignas|auto|bool|break|case|catch|char|class|const|constexpr|continue|decltype|default|delete|do|double|else|enum|explicit|export|extern|false|float|for|friend|goto|if|inline|int|long|mutable|namespace|new|noexcept|nullptr|operator|override|private|protected|public|return|short|signed|sizeof|static|struct|switch|template|this|throw|true|try|typedef|typename|union|unsigned|using|virtual|void|volatile|while';
const CPP=DATA.lang==='cpp';
const CMT=CPP?"(\\/\\/.*$)":"(#.*$)";
const TOK=new RegExp(CMT+"|('(?:\\\\.|[^'\\\\])*'|\"(?:\\\\.|[^\"\\\\])*\")|\\b("+(CPP?KW_CPP:KW_PY)+")\\b|\\b(\\d+\\.?\\d*)\\b","g");
const PRE=/^\s*#\s*\w+/;
const esc=x=>x.replace(/&/g,'&amp;').replace(/</g,'&lt;');
function hl(line){
  if(CPP&&PRE.test(line))return `<span class="p">${esc(line)}</span>`;
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
/* Placement recalculé sur les seuls nœuds visibles : après un isolement ou
   un masquage, on évite les grands vides laissés par les nœuds retirés. */
let LANES=[];
const COL=430,GAP=46,LANE=70;
function positionNodes(){
  const lanes=LANES;
  //    Une colonne = une profondeur d'appel. Si trop de nœuds partagent la
  //    même profondeur, la colonne déborde en sous-colonnes : sans cela un
  //    projet large produit une bande verticale interminable.
  //    Nombre de sous-colonnes choisi pour que chaque bloc reste à peu près
  //    carré : trop peu et l'on obtient une bande verticale, trop et une
  //    bande horizontale.
  const stackOf=new Map();                     // "lane|profondeur" -> hauteur pile
  const subcols=new Map();                     // profondeur -> nb de sous-colonnes
  for(const lane of lanes){
    const groups=new Map();
    for(const f of lane.items){
      if(nodes.get(f.id).hidden)continue;
      const d=DATA.depth[f.id]??0;
      (groups.get(d)??groups.set(d,[]).get(d)).push(nodes.get(f.id));
    }
    for(const[d,ns]of groups){
      const avg=ns.reduce((a,n)=>a+n.h,0)/ns.length+GAP;
      const cols=Math.max(1,Math.round(Math.sqrt(ns.length*avg/COL)));
      stackOf.set(lane.key+'|'+d,Math.ceil(ns.length/cols));
      subcols.set(d,Math.max(subcols.get(d)??1,cols));
    }
  }
  const xOf=new Map();
  let cursor=0;
  for(const d of [...subcols.keys()].sort((a,b)=>a-b)){
    xOf.set(d,cursor);cursor+=subcols.get(d)*COL;
  }

  let top=0;
  for(const lane of lanes){
    if(!lane.items.some(f=>!nodes.get(f.id).hidden))continue;
    const seen=new Map();                      // profondeur -> nœuds déjà placés
    const colY=new Map();                      // "d:sous-colonne" -> y courant
    let height=0;
    for(const f of lane.items){
      const n=nodes.get(f.id);if(n.hidden)continue;
      const d=DATA.depth[f.id]??0;
      const i=seen.get(d)??0;seen.set(d,i+1);
      const stack=stackOf.get(lane.key+'|'+d)??8;
      const sub=Math.floor(i/stack),key=d+':'+sub;
      const y=colY.get(key)??0;
      n.x=(xOf.get(d)??0)+sub*COL;n.y=top+y;n.col=lane.key+'|'+d+':'+sub;place(n);
      const next=y+n.h+GAP;colY.set(key,next);height=Math.max(height,next);
    }
    top+=height+LANE;
  }
}

function makeNode(f){
  const el=document.createElement('div');
  el.className='node';el.dataset.kind=f.kind;el.dataset.id=f.id;
  if(f.extkind)el.dataset.ext=f.extkind;
  const title=f.cls?`${f.cls}.<b>${f.name}</b>`:f.name;
  const sig=f.extkind==='unknown'?'définition introuvable':(f.signature||'');
  const badge=(MULTI&&f.file)?`<span class="fbadge">${f.file}</span>`:'';
  let body;
  if(LAZY&&f.kind!=='external'){body='';}      // corps construit au dépliage
  else if(f.kind==='external'){
    body='<div class="ext-list code">'+
      (f.members.length?f.members:['(appel direct)']).map(m=>`<div>${m}</div>`).join('')+
      '</div>';
  }else{
    // une seule chaîne HTML : bien plus rapide que createElement par ligne
    const src=f.source.split('\n');
    const rows=src.map((l,i)=>`<div class="ln" data-l="${f.lineno+i}">${hl(l)||' '}</div>`);
    if(f.truncated)rows.push('<div class="ln more">…</div>');
    body='<div class="code">'+rows.join('')+'</div>';
  }
  el.innerHTML=`<span class="in"></span>
    <header><span>${title}</span>${badge}<span class="sig">${sig}</span>
    <span class="eye" title="masquer">👁</span><span class="chev" title="replier">▾</span></header>`
    +body;
  return el;
}

/* Placement en couloirs : x = profondeur d'appel, y = couloir du groupe.
   Chaque classe/namespace occupe une bande horizontale propre, donc les
   cadres ne se chevauchent jamais même si leurs membres couvrent plusieurs
   colonnes. Les fonctions libres et les externes ont leurs propres couloirs.

   Le DOM est construit d'un bloc, puis les hauteurs sont lues en une seule
   passe : lire offsetHeight au fil de l'insertion forcerait un recalcul de
   mise en page par nœud (le principal coût sur les gros graphes). */
function build(){
  document.getElementById('file').textContent=' · '+DATA.path;
  const all=[...DATA.functions,
             ...DATA.externals.map(e=>({...e,extkind:e.kind,kind:'external',cls:null}))];
  const owner=new Map();
  for(const g of DATA.classes) for(const m of g.members) owner.set(m,g.name);

  const lanes=[{key:'',items:[]}];
  const byKey=new Map();
  for(const g of DATA.classes){
    const l={key:(g.file||'')+'|'+g.name,items:[]};lanes.push(l);
    for(const m of g.members)byKey.set(m,l);
  }
  const extLane={key:'\u0000ext',items:[]};lanes.push(extLane);
  for(const f of all){
    (f.kind==='external'?extLane:(byKey.get(f.id)||lanes[0])).items.push(f);
  }

  // 1. créer tout le DOM hors document
  const frag=document.createDocumentFragment();
  const order=[];
  for(const lane of lanes){
    for(const f of lane.items){
      const el=makeNode(f);
      if(COLLAPSED)el.classList.add('collapsed');
      frag.appendChild(el);
      const n={el,x:0,y:0,w:340,h:0,kind:f.kind,cls:owner.get(f.id)||null,
               file:f.file||'',extkind:f.extkind||null,lane,data:f,
               built:LAZY?false:true,
               hidden:false,collapsed:COLLAPSED,lineno:f.lineno};
      nodes.set(f.id,n);order.push([f,n]);
    }
  }
  layerN.appendChild(frag);

  // 2. lire toutes les hauteurs d'un coup
  for(const[,n]of order){n.h=n.el.offsetHeight;n.w=n.el.offsetWidth;}

  LANES=lanes;positionNodes();

  // 4. index des arêtes : résolu une fois, jamais re-cherché au dessin
  for(const e of DATA.edges){
    const s=nodes.get(e.src),t=nodes.get(e.dst);
    if(!s||!t)continue;
    const ln=s.el.querySelector(`.ln[data-l="${e.lineno}"]`);
    if(ln)ln.classList.add('call');
    WIRES.push({s,t,ln,ext:e.external,src:e.src,dst:e.dst,lineno:e.lineno,
                dy:ln?ln.offsetTop+ln.offsetHeight/2:0});
  }
}
function place(n){n.el.style.transform=`translate(${n.x}px,${n.y}px)`}

/* Après un repli/dépli, la hauteur du nœud change : on décale ce qui est
   en dessous dans la même colonne, sinon le code déplié recouvre le nœud
   suivant. Le reste de la disposition — y compris les nœuds déplacés à la
   main — n'est pas touché. */
function reflowColumn(n){
  const before=n.h;
  n.h=n.el.offsetHeight;
  const delta=n.h-before;
  if(!delta||!n.col)return;
  for(const other of nodes.values()){
    if(other===n||other.col!==n.col||other.hidden)continue;
    if(other.y>n.y){other.y+=delta;place(other);}
  }
}

/* Construit le code d'un nœud au premier dépliage, puis recale les fils
   qui partent de ses lignes d'appel. */
function materialize(n){
  if(n.built||n.kind==='external')return;
  n.built=true;
  const f=n.data;
  const src=f.source.split('\n');
  const rows=src.map((l,i)=>`<div class="ln" data-l="${f.lineno+i}">${hl(l)||' '}</div>`);
  if(f.truncated)rows.push('<div class="ln more">… source tronquée</div>');
  n.el.insertAdjacentHTML('beforeend','<div class="code">'+rows.join('')+'</div>');
  for(const w of WIRES){
    if(w.s!==n)continue;
    const ln=n.el.querySelector(`.ln[data-l="${w.lineno}"]`);
    if(ln){ln.classList.add('call');w.ln=ln;w.dy=ln.offsetTop+ln.offsetHeight/2;}
  }
  n.h=n.el.offsetHeight;
}

/* ---------- fils (béziers) ----------
   Géométrie calculée depuis les coordonnées stockées : aucun appel à
   getBoundingClientRect, donc aucun recalcul de mise en page forcé.
   Le SVG est assemblé en une seule chaîne plutôt que nœud par nœud. */
const HEADER_H=32;
function wireGeom(w){
  const s=w.s,t=w.t;
  const inBody=w.ln&&!s.collapsed;
  const x1=s.x+s.w+(inBody?6:0);
  const y1=s.y+(inBody?w.dy:HEADER_H/2);
  const x2=t.x, y2=t.y+HEADER_H/2;
  return[x1,y1,x2,y2];
}
function drawWires(){
  const parts=[];
  // fenêtre visible en coordonnées monde, avec une marge
  const M=400/view.k;
  const vx0=-view.x/view.k-M, vy0=-view.y/view.k-M,
        vx1=vx0+innerWidth/view.k+2*M, vy1=vy0+innerHeight/view.k+2*M;
  for(const w of WIRES){
    const s=w.s,t=w.t;
    if(s.hidden||t.hidden||s.faded||t.faded)continue;
    // hors champ des deux côtés : inutile de tracer
    if(Math.max(s.x,t.x)<vx0||Math.min(s.x,t.x)>vx1||
       Math.max(s.y,t.y)<vy0||Math.min(s.y,t.y)>vy1)continue;
    const[x1,y1,x2,y2]=wireGeom(w);
    const dx=Math.max(60,Math.abs(x2-x1)*.45);
    let cls='w'+(w.ext?(t.extkind==='unknown'?' unk':' ext'):'');
    if(sel)cls+=(w.src===sel||w.dst===sel)?' hot':' off';
    parts.push(`<path class="${cls}" d="M${x1.toFixed(1)},${y1.toFixed(1)} `
      +`C${(x1+dx).toFixed(1)},${y1.toFixed(1)} ${(x2-dx).toFixed(1)},${y2.toFixed(1)} `
      +`${x2.toFixed(1)},${y2.toFixed(1)}"/>`);
  }
  svg.innerHTML=parts.join('');
}
let wirePending=false;
function scheduleWires(){                      // au plus un dessin par image
  if(wirePending)return;
  wirePending=true;
  requestAnimationFrame(()=>{wirePending=false;drawWires();});
}

/* ---------- cadres de classe ---------- */
function drawFrames(){
  const parts=[];
  for(const c of DATA.classes){
    const ms=c.members.map(id=>nodes.get(id)).filter(n=>n&&!n.hidden&&!n.faded);
    if(!ms.length)continue;
    const P=26;
    const x=Math.min(...ms.map(n=>n.x))-P, y=Math.min(...ms.map(n=>n.y))-P-30,
          X=Math.max(...ms.map(n=>n.x+n.w))+P, Y=Math.max(...ms.map(n=>n.y+n.h))+P;
    parts.push(`<div class="frame" style="left:${x}px;top:${y}px;`
      +`width:${X-x}px;height:${Y-y}px">`
      +`<span data-kw="${c.stereotype||'class'} ">${c.name}</span></div>`);
  }
  layerF.innerHTML=parts.join('');
}

/* ---------- filtres ---------- */
function applyFilters(){
  const q=document.getElementById('search').value.trim().toLowerCase();
  const show={function:tFn.checked,method:tMe.checked,external:tEx.checked};
  const wantFile=fFile.value;
  let visible=0;
  for(const[id,n]of nodes){
    const okKind=show[n.kind];
    const okFile=!wantFile||n.kind==='external'||n.file===wantFile;
    const label=(id.split('::').pop()||id).toLowerCase();
    const okText=!q||label.includes(q);
    n.faded=!(okKind&&okText&&okFile);
    n.el.classList.toggle('faded',n.faded);
    n.el.style.display=n.hidden?'none':'';
    if(okKind&&okText&&okFile&&!n.hidden)visible++;
  }
  const nf=(DATA.files||[]).length;
  document.getElementById('stats').textContent=
    `${visible}/${nodes.size} nœuds · ${DATA.edges.length} appels`
    +(nf>1?` · ${nf} fichiers`:'');
  drawFrames();drawWires();
}

/* ---------- interactions ---------- */
function applyView(){world.style.transform=`translate(${view.x}px,${view.y}px) scale(${view.k})`}
let drag=null,lastId=null,lastTime=0;
vp.addEventListener('pointerdown',ev=>{
  const header=ev.target.closest('header'),nodeEl=ev.target.closest('.node');
  if(ev.target.classList.contains('chev')||ev.target.classList.contains('eye'))return;
  if(nodeEl&&(header||ev.target===nodeEl)){
    const id=nodeEl.dataset.id;
    select(id);
    drag={n:nodes.get(id),id,px:ev.clientX,py:ev.clientY,moved:false};
  }else if(!nodeEl){
    select(null);
    drag={pan:true,px:ev.clientX,py:ev.clientY,moved:false};
    vp.classList.add('panning');
  }
  vp.setPointerCapture(ev.pointerId);
});
vp.addEventListener('pointermove',ev=>{
  if(!drag)return;
  const dx=ev.clientX-drag.px,dy=ev.clientY-drag.py;
  if(Math.abs(dx)>2||Math.abs(dy)>2)drag.moved=true;
  drag.px=ev.clientX;drag.py=ev.clientY;
  if(drag.pan){view.x+=dx;view.y+=dy;applyView();scheduleWires();return;}
  drag.n.x+=dx/view.k;drag.n.y+=dy/view.k;place(drag.n);
  scheduleWires();drawFrames();
});
vp.addEventListener('pointerup',ev=>{
  // Un double-clic n'est reconnu que si aucune des deux pressions n'a bougé :
  // sinon reprendre un nœud pour le déplacer déclencherait un isolement.
  if(drag&&drag.id&&!drag.moved){
    const now=performance.now();
    if(drag.id===lastId&&now-lastTime<400){lastId=null;isolate(drag.id);}
    else{lastId=drag.id;lastTime=now;}
  }else{lastId=null;}
  drag=null;vp.classList.remove('panning');
  try{vp.releasePointerCapture(ev.pointerId);}catch(_){}
});
vp.addEventListener('pointercancel',()=>{drag=null;lastId=null;
  vp.classList.remove('panning');});
vp.addEventListener('wheel',ev=>{
  // au-dessus d'un bloc de code plus long que sa fenêtre : défilement normal
  const code=ev.target.closest&&ev.target.closest('.code');
  if(code&&code.scrollHeight>code.clientHeight+2){
    const top=code.scrollTop, max=code.scrollHeight-code.clientHeight;
    if((ev.deltaY<0&&top>0)||(ev.deltaY>0&&top<max))return;   // laisser défiler
  }
  ev.preventDefault();
  const k=Math.min(2.2,Math.max(.2,view.k*(ev.deltaY<0?1.1:1/1.1)));
  view.x=ev.clientX-(ev.clientX-view.x)*k/view.k;
  view.y=ev.clientY-(ev.clientY-view.y)*k/view.k;
  view.k=k;applyView();scheduleWires();
},{passive:false});
layerN.addEventListener('click',ev=>{
  const el=ev.target.closest('.node');if(!el)return;
  const n=nodes.get(el.dataset.id);
  if(ev.target.classList.contains('chev')){
    if(n.collapsed)materialize(n);
    n.collapsed=!n.collapsed;el.classList.toggle('collapsed',n.collapsed);
    ev.target.textContent=n.collapsed?'▸':'▾';
    reflowColumn(n);
    drawFrames();drawWires();
  }else if(ev.target.classList.contains('eye')){
    n.hidden=true;positionNodes();applyFilters();
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
      tEx=document.getElementById('t-ex'),fFile=document.getElementById('f-file');
const MULTI=(DATA.files||[]).length>1;
if(MULTI){
  fFile.style.display='';
  fFile.innerHTML='<option value="">tous les fichiers</option>'+
    DATA.files.map(f=>`<option value="${f}">${f}</option>`).join('');
  fFile.addEventListener('change',applyFilters);
}
[tFn,tMe,tEx].forEach(t=>t.addEventListener('change',applyFilters));
document.getElementById('search').addEventListener('input',applyFilters);
document.getElementById('reset').addEventListener('click',()=>{
  for(const n of nodes.values())n.hidden=false;
  document.getElementById('search').value='';
  if(fFile)fFile.value='';
  sel=null;positionNodes();applyFilters();fit();
});
document.getElementById('fit').addEventListener('click',fit);

/* Replier / déplier les nœuds visibles (les invisibles ne coûtent rien). */
let allFolded=COLLAPSED;
document.getElementById('fold').addEventListener('click',ev=>{
  allFolded=!allFolded;
  ev.target.textContent=allFolded?'Déplier tout':'Replier tout';
  for(const n of nodes.values()){
    if(n.hidden||n.faded||n.kind==='external')continue;
    if(!allFolded)materialize(n);
    n.collapsed=allFolded;
    n.el.classList.toggle('collapsed',allFolded);
    const chev=n.el.querySelector('.chev');if(chev)chev.textContent=allFolded?'▸':'▾';
    n.h=n.el.offsetHeight;
  }
  positionNodes();drawFrames();drawWires();
});

/* Isoler le voisinage d'un nœud (2 sauts). Sur un gros projet on explore
   ainsi de proche en proche sans régénérer le fichier ; « Tout réafficher »
   revient en arrière. Le double-clic est détecté à la main : la capture du
   pointeur pendant le glisser empêche l'événement dblclick natif d'arriver. */
function isolate(id){
  const keep=new Set([id]);
  for(let hop=0;hop<2;hop++){
    const front=new Set(keep);
    for(const w of WIRES){
      if(front.has(w.src))keep.add(w.dst);
      if(front.has(w.dst))keep.add(w.src);
    }
  }
  for(const[nid,n]of nodes)n.hidden=!keep.has(nid);
  positionNodes();select(id);applyFilters();fit();
}


build();applyFilters();fit();
</script>
</body>
</html>
"""
