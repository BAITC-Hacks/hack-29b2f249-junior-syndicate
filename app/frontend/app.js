const icons = {
 grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
 graph:'<rect x="9" y="2" width="6" height="6" rx="1"/><rect x="2" y="16" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M12 8v4M5 16v-4h14v4"/>',
 target:'<circle cx="12" cy="12" r="9"/><path d="M12 1v5m0 12v5M1 12h5m12 0h5"/>',
 cluster:'<path d="m12 2 9 5v10l-9 5-9-5V7Z"/>',
 list:'<path d="M9 5h12M9 12h12M9 19h12M3 4h1v3M3 11h2l-2 3h2M3 18h2v3H3"/>',
 shield:'<path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Z"/><path d="M12 7v6m0 3v1"/>',
 data:'<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 4 18 4 18 0V5M3 12c0 4 18 4 18 0"/>',
 download:'<path d="M12 3v12m-5-5 5 5 5-5M3 15v6h18v-6"/>',
 info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
 search:'<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
 arrow:'<path d="M4 12h15m-6-6 6 6-6 6"/>',
 login:'<path d="M14 3h6v18h-6M3 12h12m-5-5 5 5-5 5"/>',
 logout:'<path d="M10 3H4v18h6M10 12h11m-5-5 5 5-5 5"/>',
 play:'<path d="m7 3 14 9-14 9Z"/>',
 activity:'<path d="M2 12h5l3-9 4 18 3-9h5"/>',
 calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6m10-6v6M3 11h18"/>',
 flow:'<path d="M3 7h18m-5-5 5 5-5 5M21 17H3m5-5-5 5 5 5"/>',
 close:'<path d="m6 6 12 12M6 18 18 6"/>',
 lock:'<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4"/>',
 check:'<path d="m4 12 5 5L20 6"/>',
 plus:'<path d="M12 4v16M4 12h16"/>',
 minus:'<path d="M4 12h16"/>',
 fit:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>'
};
const icon = name => '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">'+(icons[name]||icons.info)+'</svg>';
const logo = '<svg class="brand-mark" viewBox="0 0 48 48" aria-hidden="true"><path d="m10 10 28 28M38 10 10 38M10 10l28 0 0 28-28 0Z" stroke="#8993a5" stroke-width="2" fill="none" opacity=".4"/><circle cx="10" cy="10" r="5" fill="#a0a6b0"/><circle cx="38" cy="10" r="5" fill="#a0a6b0"/><circle cx="10" cy="38" r="5" fill="#a0a6b0"/><circle cx="38" cy="38" r="5" fill="#a0a6b0"/><circle cx="24" cy="24" r="10" fill="#f5b544"/><path d="m18 18 12 12m0-12L18 30" stroke="#fff" opacity=".55"/></svg>';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = v => Number(v||0).toLocaleString('ru-RU', {maximumFractionDigits:0});
const money = v => Number(v||0).toLocaleString('ru-RU', {maximumFractionDigits:0})+' KZT';
const shortMoney = v => Number(v)>=1e6 ? (v/1e6).toFixed(1)+' млн' : Number(v)>=1e3 ? (v/1e3).toFixed(0)+' тыс.' : num(v);
const score = v => Number(v||0).toFixed(3);
const root = document.querySelector('#app');
let D=null, byId=new Map(), A={}, page='overview', selected=null, card=null, mode='overview', colorMode='role', networkTab='graph', activeCluster=null, authMode='login', resultIds=null, query='', roleFilter='', clusterFilter='', pageLimit=30, simulation=null, removalCount=5, haptics=false, busy=false, pending=null, queued=[], lastResponse=null, layoutRevision='', searchTimer, toastTimer, ai=null;
const pages = {overview:['Обзор','grid'],network:['Анализ сети','graph'],investigations:['Приоритет проверок','target'],clusters:['Кластеры','cluster'],ranking:['Все узлы','list'],stress:['Стресс-тест','shield'],coverage:['Качество данных','data'],exports:['Экспорт','download'],about:['Методология','info']};
const badge = n => '<span class="badge" style="--role:'+D.colors[n.role]+'"><span class="dot"></span>'+esc(n.role)+'</span>';
const bar = n => '<div class="score-row" style="--role:'+D.colors[n.role]+'"><div class="progress"><i style="width:'+Number(n.priority_score)*100+'%"></i></div><span>'+score(n.priority_score)+'</span></div>';
function post(type, extra={}) { window.parent.postMessage({isStreamlitMessage:true,type,...extra},'*'); }
function tactile() { if(haptics && navigator.vibrate) navigator.vibrate(12); }
function send(action, values={}) {
 const event={id:crypto.randomUUID(),action,...values};
 if(pending) { if(['query','select','simulate'].includes(action)) queued=queued.filter(x=>x.action!==action); queued.push(event); return; }
 pending=event; busy=true; post('streamlit:setComponentValue',{value:event,dataType:'json'});
 if(action==='run') { toast('Выполняется полный расчёт…'); document.querySelectorAll('[data-action="run"]').forEach(b=>{b.disabled=true;b.textContent='Считаем…';}); }
}
function toast(text) { const t=document.querySelector('#toast'); t.textContent=text; t.classList.add('visible'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>t.classList.remove('visible'),5000); }
function fitFrame() { let height=850;try{height=window.parent.innerHeight;}catch{}post('streamlit:setFrameHeight',{height:Math.max(height,640)}); }
new ResizeObserver(fitFrame).observe(root);
window.addEventListener('message',event=>{
 if(event.source!==window.parent || event.data.type!=='streamlit:render') return;
 A=event.data.args;
 const wasAuthenticated=!!D;
 if(!A.authenticated) {
  if(wasAuthenticated) authMode='login';
  D=null;byId.clear();selected=null;card=null;ai=null;queued=[];resultIds=null;simulation=null;layoutRevision='';
  if(wasAuthenticated || !root.querySelector('.auth-page')) { document.querySelector('#modal').innerHTML=''; renderAuth(); }
 } else if(A.payload) {
  const revision=JSON.stringify(A.payload.summary.input_sha256)+A.payload.summary.runtime_seconds;
  const changed=!D || revision!==layoutRevision || A.response?.action==='run';
  D=A.payload;byId=new Map(D.nodes.map(n=>[n.gid,n]));layoutRevision=revision;
  if(changed) { ai=null;card=null; if(!wasAuthenticated) page='overview'; render(); }
 } else { renderMissing(); }
 const response=A.response;
 if(response?.id && response.id!==lastResponse) {
  lastResponse=response.id;
  if(pending?.id===response.id) {pending=null;busy=false;}
  document.querySelectorAll('.auth-form button').forEach(b=>b.disabled=false);
  if(response.error) {
   if(!A.authenticated) {const el=document.querySelector('#auth-error');el.textContent=response.error;el.classList.remove('hidden');}
   else toast(response.error);
   document.querySelectorAll('[data-action="run"]').forEach(b=>{b.disabled=false;b.innerHTML=icon('play')+' Запустить анализ';});
  } else {
   if(response.card && response.card.gid===selected) { card=response.card; renderCard(); if(document.querySelector('#dossier-modal')) openDossier(); }
   if(response.ids) {resultIds=response.ids; if(page==='ranking'||page==='investigations') renderListContent(); else renderSearchResults();}
   if(response.simulation) {simulation=response.simulation; if(page==='stress') renderStress();}
   if(response.download) {
    const bytes=Uint8Array.from(atob(response.download.base64),c=>c.charCodeAt(0));
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));
    const a=document.createElement('a');a.href=url;a.download=response.download.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),3000);toast('Файл '+response.download.filename+' скачан');
   }
   if(response.message) toast(response.message);
   if(response.recovery_code) openRecovery(response.recovery_code);
  }
  if(response.action==='explain' && ai?.gid===response.gid && selected===response.gid) {
   ai={gid:response.gid,loading:false,result:response.explanation||null,error:response.error||''};
   renderCard();if(document.querySelector('#dossier-modal')) openDossier();
  }
  if(queued.length && !pending) {const event=queued.shift();pending=event;busy=true;post('streamlit:setComponentValue',{value:event,dataType:'json'});}
 }
 fitFrame();
});
function authArt() {
 const pts=[[225,135,18,'#f5b544'],[105,75,10,'#52b7e8'],[340,65,13,'#a78bea'],[350,215,14,'#35c5b3'],[98,227,13,'#ef5a7c'],[197,270,9,'#8090aa'],[410,145,7,'#52b7e8'],[55,138,7,'#a78bea'],[238,34,6,'#8090aa']];
 return '<svg class="auth-art" viewBox="0 0 470 310"><defs><radialGradient id="ag"><stop stop-color="#f5b544" stop-opacity=".12"/><stop offset="1" stop-color="#f5b544" stop-opacity="0"/></radialGradient></defs><circle cx="225" cy="145" r="145" fill="url(#ag)"/>'+pts.slice(1).map(p=>'<line x1="225" y1="135" x2="'+p[0]+'" y2="'+p[1]+'" stroke="'+p[3]+'" opacity=".35"/>').join('')+pts.map(p=>'<circle cx="'+p[0]+'" cy="'+p[1]+'" r="'+(p[2]+6)+'" fill="none" stroke="'+p[3]+'" opacity=".15"/><circle cx="'+p[0]+'" cy="'+p[1]+'" r="'+p[2]+'" fill="'+p[3]+'" opacity=".85"/>').join('')+'</svg>';
}
function renderAuth() {
 const register=authMode==='register',recover=authMode==='recover';
 root.innerHTML='<div class="auth-page"><section class="auth-story grid-bg"><div class="auth-brand">'+logo+' Qadam<span class="muted small"> / Intelligence</span></div><div>'+authArt()+'<div class="eyebrow">JUNIOR SYNDICATE · HACKALEM AI</div><h1>Сеть переводов.<br><em>Ясная структура.</em></h1><p>Восстановите структуру финансовой сети. Найдите ключевые узлы. Обоснуйте следующую проверку.</p></div><div class="auth-foot">Локальный анализ · ИИ-пояснение по отдельному запросу</div></section><section class="auth-content"><div class="auth-inner"><div class="auth-symbol">'+icon(recover?'lock':'login')+'</div><h1>'+(register?'Создать аккаунт':recover?'Восстановить доступ':'С возвращением')+'</h1><p class="subtitle">'+(register?'Ваше рабочее пространство для анализа сети.':recover?'Используйте резервный код, сохранённый при регистрации.':'Войдите в рабочую область аналитика.')+'</p>'+
 (!register&&!recover?'<button class="google-btn" data-action="google" '+(!A.google_enabled?'disabled':'')+'><span class="google-letter">G</span>Продолжить с Google</button>'+(!A.google_enabled?'<p class="auth-hint">Вход через Google появится после настройки OAuth владельцем.</p>':'')+'<div class="auth-divider">или по email</div>':'')+
 '<form class="auth-form" id="auth-form"><label for="email">Email</label><input id="email" name="email" type="email" placeholder="you@example.com" autocomplete="username" required maxlength="254">'+
 (recover?'<label for="recovery">Резервный код</label><input id="recovery" name="recovery" autocomplete="off" required placeholder="Код восстановления">':'')+
 '<div class="between"><label for="password">'+(recover?'Новый пароль':'Пароль')+'</label>'+(!register&&!recover?'<button type="button" class="text-btn" data-action="auth-mode" data-mode="recover">Забыли пароль?</button>':'')+'</div><input id="password" name="password" type="password" placeholder="'+(register||recover?'Не менее 12 символов':'Ваш пароль')+'" autocomplete="'+(register||recover?'new-password':'current-password')+'" '+(register||recover?'minlength="12"':'')+' maxlength="256" required>'+
 '<div id="auth-error" class="auth-error hidden" role="alert"></div><button class="btn gold" type="submit">'+(register?'Создать аккаунт':recover?'Обновить пароль':'Войти')+icon('arrow')+'</button></form><div class="auth-switch">'+(register||recover?'Уже есть аккаунт? <button class="text-btn" data-action="auth-mode" data-mode="login">Войти</button>':'Первый визит? <button class="text-btn" data-action="auth-mode" data-mode="register">Создать аккаунт</button>')+'</div><p class="auth-hint" style="margin-top:28px">'+icon('lock')+' Пароли защищены · Сессия ограничена по времени</p></div></section></div>';
}
function renderMissing() {
 root.innerHTML='<div class="main" style="margin:0"><div class="topbar"><div><div class="eyebrow">JUNIOR SYNDICATE</div><h1>Qadam</h1></div><button class="btn" data-action="logout">'+icon('logout')+' Выйти</button></div><div class="panel section-empty"><h2>Подготовим рабочую область</h2><p style="margin:15px">'+esc(A.error)+'</p><button class="btn gold" data-action="run">'+icon('play')+' Запустить анализ</button></div></div>';
}
function render() {
 if(!D) return;
 const titles={overview:['Qadam','Реконструкция финансовой сети и приоритет проверок'],network:['Анализ сети','Направление потоков · Связи клиентов · Топология сообществ'],investigations:['Приоритет проверок','Очередь аналитика · Ранжирование по рассчитанной значимости'],clusters:['Исследование кластеров','Структурные сообщества сети · Откройте внутренние связи'],ranking:['Все узлы','Рассчитанный приоритет, роль и объяснение для каждого клиента'],stress:['Устойчивость сети','Сценарий удаления ключевых узлов с воспроизводимым случайным сравнением'],coverage:['Покрытие и ограничения','Границы наблюдений и качество исходных данных'],exports:['Результаты анализа','Воспроизводимые выгрузки из текущего расчёта'],about:['Как устроен анализ','Объяснимые роли · Проверяемые гипотезы · Локальный расчёт']};
 root.innerHTML='<aside class="rail"><div class="brand">'+logo+'</div>'+Object.entries(pages).map(([id,p],i)=>(i===7?'<div class="rail-separator"></div>':'')+'<button class="nav-item '+(id===page?'active':'')+'" aria-label="'+p[0]+'" title="'+p[0]+'" data-action="nav" data-page="'+id+'">'+icon(p[1])+'</button>').join('')+'<div class="rail-bottom"><button class="nav-item" aria-label="Тактильный отклик" title="Тактильный отклик" data-action="haptics">'+icon('activity')+'</button><button class="nav-item" aria-label="Выйти" title="Выйти" data-action="logout"><span class="avatar">'+esc(A.email.slice(0,2).toUpperCase())+'</span></button></div></aside><main class="main"><header class="topbar"><div>'+(page==='overview'?'<div class="eyebrow"><span class="dot"></span> FINANCIAL INTELLIGENCE</div>':'')+'<h1>'+titles[page][0]+'</h1><div class="subtitle">'+titles[page][1]+'</div></div><div class="tools">'+(page==='overview'?'<span class="pill date-pill">'+icon('calendar')+' Июль 2026</span><span class="pill status"><span class="dot"></span> Расчёт готов</span><button class="btn" data-action="run">'+icon('play')+' Запустить анализ</button><button class="btn gold" data-action="nav" data-page="exports">'+icon('download')+' Экспорт</button>':page==='network'?'<div class="tabs">'+[['graph','Граф'],['flow','Потоки'],['clusters','Кластеры']].map(([id,title])=>'<button class="'+(id===networkTab?'active':'')+'" data-action="network-tab" data-tab="'+id+'">'+title+'</button>').join('')+'</div>':'<span class="pill status"><span class="dot"></span> Локально · '+esc(A.email.split('@')[0])+'</span>')+'</div></header><div id="content" class="page-content"></div><footer class="footer"><span>JUNIOR SYNDICATE <span style="color:#38435b"> / </span> QADAM</span><span>Роль — гипотеза для проверки. Приоритет — не вероятность виновности.</span><span class="status"><span class="dot"></span> Только предоставленные данные</span></footer></main>';
 if(page==='overview') renderOverview();
 else if(page==='network') renderNetwork();
 else if(page==='investigations'||page==='ranking') renderRanking();
 else if(page==='clusters') renderClusters();
 else if(page==='stress') {renderStress();if(!simulation) send('simulate',{count:removalCount});}
 else if(page==='coverage') renderCoverage();
 else if(page==='exports') renderExports();
 else renderAbout();
}
function searchMarkup(filters=false) {
 return '<div class="search-bar"><div style="position:relative;width:100%;max-width:560px"><div class="search-wrap">'+icon('search')+'<input id="search" aria-label="Поиск GID или роли" placeholder="Поиск GID или роли…" value="'+esc(query)+'"><kbd>Ctrl K</kbd></div><div id="search-results"></div></div>'+(filters?'<select class="select" id="role-filter" aria-label="Фильтр роли"><option value="">Все роли</option>'+Object.keys(D.colors).map(r=>'<option '+(roleFilter===r?'selected':'')+'>'+r+'</option>').join('')+'</select><select class="select" id="cluster-filter" aria-label="Фильтр кластера"><option value="">Все кластеры</option>'+D.clusters.map(c=>'<option value="'+c.cluster_id+'" '+(String(c.cluster_id)===clusterFilter?'selected':'')+'>Кластер #'+c.cluster_id+'</option>').join('')+'</select>':'')+'</div>';
}
function stat(label,value,caption,accent,ic,bars='') {
 return '<div class="panel stat" style="--accent:'+accent+'"><div class="stat-top"><span class="label">'+label+'</span><span class="stat-icon">'+icon(ic)+'</span></div><div class="stat-value">'+value+'</div><div class="stat-caption">'+caption+'</div>'+bars+'</div>';
}
function renderOverview() {
 mode='overview';
 const s=D.summary;
 const depthBars='<div class="mini-bars" aria-label="Узлы по глубине">'+Object.values(D.coverage.depth).map(v=>'<i style="height:'+Math.max(2,v/Math.max(...Object.values(D.coverage.depth))*14)+'px"></i>').join('')+'</div>';
 document.querySelector('#content').innerHTML=searchMarkup()+'<div class="stats">'+stat('Клиенты',num(s.nodes),'Узлы по глубине 0 → 4',D.colors.transit,'graph',depthBars)+stat('Связи',num(s.edges),'Направленные пары клиентов',D.colors.distributor,'cluster')+stat('Транзакции',num(s.transactions),'Внутрибанковские переводы',D.colors.terminal,'flow')+stat('Кластеры',num(s.clusters),D.coverage.multi_seed_clusters+' с несколькими seed',D.colors.coordinator,'cluster')+stat('Высокий приоритет',num(D.coverage.high_priority_nodes),'Рассчитанный score ≥ 0.700',D.colors.consolidator,'target')+'</div><div class="overview-grid"><section class="panel graph-panel"><div class="panel-head"><h2>Реконструкция сети</h2><span class="muted small" id="graph-count"></span></div><div id="graph-host" class="graph-wrap grid-bg"></div>'+legend()+'</section><section class="panel" id="node-card"></section></div><div class="section-title"><h2>Первые в очереди</h2><button class="text-btn" data-action="nav" data-page="investigations">Все приоритеты '+icon('arrow')+'</button></div><div class="panel table-wrap">'+nodesTable(D.nodes.slice(0,5))+'</div>';
 drawGraph();renderCard();
}
function legend() {return '<div class="legend">'+Object.entries(D.colors).map(([name,c])=>'<span style="--role:'+c+'"><i></i>'+name+'</span>').join('')+'<span style="margin-left:auto">◌ seed</span></div>';}
function nodesTable(nodes) {
 if(!nodes.length) return '<div class="section-empty">По заданным фильтрам узлы не найдены.</div>';
 return '<table><thead><tr><th>GID</th><th>Роль</th><th>Приоритет · 0–1</th><th>Обоснование</th><th>Кластер</th><th></th></tr></thead><tbody>'+nodes.map(n=>'<tr><td class="mono gid-cell">'+esc(n.gid)+'</td><td>'+badge(n)+'</td><td>'+bar(n)+'</td><td class="evidence-cell">'+esc(n.evidence)+'</td><td><span class="chip">#'+n.cluster_id+'</span></td><td><button class="btn tiny" data-action="open" data-gid="'+n.gid+'">Открыть '+icon('arrow')+'</button></td></tr>').join('')+'</tbody></table>';
}
function renderNetwork() {
 if(networkTab==='clusters') { renderClusters();return; }
 if(networkTab==='flow') {renderFlow();return;}
 document.querySelector('#content').innerHTML=searchMarkup()+'<div class="between" style="margin-bottom:16px"><div class="row"><select id="graph-mode" class="select" aria-label="Срез графа">'+[['overview','Приоритетный срез · 120 узлов'],['all','Весь граф'],['ego','Окрестность GID'],['cluster','Выбранный кластер']].map(([v,t])=>'<option value="'+v+'" '+(v===mode?'selected':'')+'>'+t+'</option>').join('')+'</select><select id="graph-color" class="select" aria-label="Цвет графа"><option value="role">Цвет по роли</option><option value="cluster" '+(colorMode==='cluster'?'selected':'')+'>Цвет по кластеру</option></select></div><span class="kbd-hint">Колесо: масштаб · Перетаскивание: перемещение · Esc: сброс</span></div><div class="overview-grid"><section class="panel graph-panel"><div class="panel-head"><h2>'+(mode==='cluster'?'Кластер #'+activeCluster:'Карта переводов')+'</h2><span id="graph-count" class="small muted"></span></div><div id="graph-host" class="graph-wrap large grid-bg"></div>'+legend()+'</section><section class="panel" id="node-card"></section></div>';
 drawGraph();renderCard();
}
function graphNodes() {
 if(mode==='all') return D.nodes;
 if(mode==='cluster' && activeCluster!==null) return D.nodes.filter(n=>n.cluster_id===activeCluster);
 if(mode==='ego' && selected) {const ids=new Set([selected]);for(const e of D.edges){if(e.src===selected)ids.add(e.dst);if(e.dst===selected)ids.add(e.src);}return D.nodes.filter(n=>ids.has(n.gid));}
 const ids=new Set(D.overview_ids);if(selected)ids.add(selected);
 return D.nodes.filter(n=>ids.has(n.gid));
}
function drawGraph() {
 const host=document.querySelector('#graph-host');if(!host)return;
 const nodes=graphNodes().map(n=>({...n})), ids=new Set(nodes.map(n=>n.gid)), edges=D.edges.filter(e=>ids.has(e.src)&&ids.has(e.dst));
 document.querySelector('#graph-count').textContent=num(nodes.length)+' узлов · '+num(edges.length)+' связей';
 if(!nodes.length){host.innerHTML='<div class="section-empty">Нет узлов в этом срезе</div>';return;}
 const canvasWidth=host.clientWidth||800,canvasHeight=host.clientHeight||500;
 const minX=Math.min(...nodes.map(n=>n.x)),minY=Math.min(...nodes.map(n=>n.y));
 const scale=Math.max((Math.max(...nodes.map(n=>n.x))-minX)/(canvasWidth-80),(Math.max(...nodes.map(n=>n.y))-minY)/(canvasHeight-80),.1);
 const radius=n=>(nodes.length>500?2.5:4)+7*n.priority_score;
 const offsetX=(canvasWidth-(Math.max(...nodes.map(n=>n.x))-minX)/scale)/2,offsetY=(canvasHeight-(Math.max(...nodes.map(n=>n.y))-minY)/scale)/2;
 for(const n of nodes){n.x=offsetX+(n.x-minX)/scale;n.y=offsetY+(n.y-minY)/scale;}
 if(mode==='ego'&&selected){
  const others=nodes.filter(n=>n.gid!==selected),center=nodes.find(n=>n.gid===selected);
  center.x=canvasWidth/2;center.y=canvasHeight/2;
  others.forEach((n,i)=>{const angle=i/Math.max(others.length,1)*Math.PI*2-Math.PI/2;n.x=canvasWidth/2+Math.cos(angle)*canvasWidth*.32;n.y=canvasHeight/2+Math.sin(angle)*canvasHeight*.32;});
 }
 for(let iteration=0;iteration<50;iteration++){
  const cells=new Map();
  for(const n of nodes){
   const gx=Math.floor(n.x/28),gy=Math.floor(n.y/28);
   for(let ox=-1;ox<=1;ox++)for(let oy=-1;oy<=1;oy++)for(const other of cells.get((gx+ox)+','+(gy+oy))||[]){
    let dx=n.x-other.x,dy=n.y-other.y,dist=Math.hypot(dx,dy),min=radius(n)+radius(other)+5;
    if(dist<min){if(dist<.01){dx=1;dy=.5;dist=Math.hypot(dx,dy);}const push=(min-dist)/dist*.52;n.x+=dx*push;n.y+=dy*push;other.x-=dx*push;other.y-=dy*push;}
   }
   n.x=Math.max(25,Math.min(canvasWidth-25,n.x));n.y=Math.max(25,Math.min(canvasHeight-25,n.y));
   const key=Math.floor(n.x/28)+','+Math.floor(n.y/28);if(!cells.has(key))cells.set(key,[]);cells.get(key).push(n);
  }
 }
 const positions=new Map(nodes.map(n=>[n.gid,n]));
 let bounds={x:-15,y:-15,w:canvasWidth+30,h:canvasHeight+30};
 const ratio=(host.clientWidth||800)/(host.clientHeight||500);
 if(bounds.w/bounds.h<ratio){const w=bounds.h*ratio;bounds.x-=(w-bounds.w)/2;bounds.w=w;}else{const h=bounds.w/ratio;bounds.y-=(h-bounds.h)/2;bounds.h=h;}
 const initial={...bounds},unit=bounds.w/(host.clientWidth||800),r=n=>radius(n)*unit;
 const max=Math.max(...edges.map(e=>e.sum_kzt),1);
 const colors=n=>colorMode==='role'?D.colors[n.role]:'hsl('+((n.cluster_id*137)%360)+',65%,65%)';
 host.innerHTML='<div class="graph-controls"><button aria-label="Увеличить" data-zoom="0.8">'+icon('plus')+'</button><button aria-label="Уменьшить" data-zoom="1.25">'+icon('minus')+'</button><button aria-label="Вписать граф" data-zoom="reset">'+icon('fit')+'</button></div><svg id="network-svg" class="graph" aria-label="Интерактивный направленный граф переводов" role="img"><defs><marker id="arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto" markerUnits="strokeWidth"><path d="M0 0L5 2.5L0 5Z" fill="#7b88a0"/></marker><marker id="arrow-active" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0 0L6 3L0 6Z" fill="#f5b544"/></marker></defs><g id="edges">'+edges.map(e=>{
  const s=positions.get(e.src),t=positions.get(e.dst),cross=s.cluster_id!==t.cluster_id,dx=t.x-s.x,dy=t.y-s.y,length=Math.hypot(dx,dy)||1,width=(.35+Math.log1p(e.sum_kzt)/Math.log1p(max)*1.2)*unit,endX=t.x-dx/length*(r(t)+2*unit),endY=t.y-dy/length*(r(t)+2*unit);
  const path=e.src===e.dst?'M '+s.x+' '+(s.y-r(s))+' C '+(s.x+40*unit)+' '+(s.y-50*unit)+' '+(s.x+45*unit)+' '+(s.y+25*unit)+' '+(s.x+r(s))+' '+s.y:'M '+s.x+' '+s.y+' L '+endX+' '+endY;
  return '<path class="edge" data-src="'+e.src+'" data-dst="'+e.dst+'" data-base="'+(cross?'#b36488':'#687a98')+'" d="'+path+'" stroke="'+(cross?'#b36488':'#687a98')+'" stroke-width="'+width+'" opacity=".28" fill="none" marker-end="url(#arrow)"><title>'+e.src+' → '+e.dst+' | '+money(e.sum_kzt)+' | '+e.n_tx+' переводов</title></path>';
 }).join('')+'</g><g id="nodes">'+nodes.map((n,i)=>'<g class="node '+(selected===n.gid?'chosen':'')+'" data-gid="'+n.gid+'" tabindex="0" role="button" aria-label="GID '+n.gid+', '+n.role+', приоритет '+score(n.priority_score)+'"><circle class="halo" cx="'+n.x+'" cy="'+n.y+'" r="'+(r(n)+6*unit)+'" fill="none" stroke="'+colors(n)+'" stroke-width="'+unit+'"/><circle class="halo" cx="'+n.x+'" cy="'+n.y+'" r="'+(r(n)+11*unit)+'" fill="none" stroke="'+colors(n)+'" stroke-opacity=".3" stroke-width="'+unit+'"/><circle class="core" cx="'+n.x+'" cy="'+n.y+'" r="'+r(n)+'" fill="'+colors(n)+'" fill-opacity=".85" stroke="'+colors(n)+'" stroke-width="'+unit+'"/>'+(n.is_seed?'<circle cx="'+n.x+'" cy="'+n.y+'" r="'+(r(n)+3*unit)+'" fill="none" stroke="'+colors(n)+'" stroke-dasharray="'+(2*unit)+' '+(2*unit)+'" stroke-width="'+unit+'" opacity=".6"/>':'')+(i<3||selected===n.gid?'<text x="'+n.x+'" y="'+(n.y-r(n)-9*unit)+'" text-anchor="middle" style="font-size:'+(8*unit)+'px">'+n.gid+'</text>':'')+'</g>').join('')+'</g></svg><div class="tooltip hidden" id="graph-tooltip"></div>';
 const svg=host.querySelector('svg.graph');
 function applyBounds(){svg.setAttribute('viewBox',bounds.x+' '+bounds.y+' '+bounds.w+' '+bounds.h);}
 applyBounds();
 function zoom(f,x=.5,y=.5){const w=bounds.w*f,h=bounds.h*f;if(w<initial.w*.04||w>initial.w*5)return;bounds.x+=(bounds.w-w)*x;bounds.y+=(bounds.h-h)*y;bounds.w=w;bounds.h=h;applyBounds();}
 host.querySelectorAll('[data-zoom]').forEach(b=>b.onclick=()=>{tactile();if(b.dataset.zoom==='reset'){bounds={...initial};applyBounds();}else zoom(Number(b.dataset.zoom));});
 svg.addEventListener('wheel',e=>{e.preventDefault();const box=svg.getBoundingClientRect();zoom(e.deltaY>0?1.12:.89,(e.clientX-box.left)/box.width,(e.clientY-box.top)/box.height);},{passive:false});
 let drag=null,moved=false;
 svg.addEventListener('pointerdown',e=>{if(e.target.closest('.node'))return;drag={x:e.clientX,y:e.clientY,bx:bounds.x,by:bounds.y};moved=false;svg.setPointerCapture(e.pointerId);svg.style.cursor='grabbing';});
 svg.addEventListener('pointermove',e=>{if(!drag)return;moved=true;bounds.x=drag.bx-(e.clientX-drag.x)/svg.clientWidth*bounds.w;bounds.y=drag.by-(e.clientY-drag.y)/svg.clientHeight*bounds.h;applyBounds();});
 svg.addEventListener('pointerup',()=>{drag=null;svg.style.cursor='';});
 const tooltip=host.querySelector('#graph-tooltip');
 host.querySelectorAll('.node').forEach(el=>{
  const n=byId.get(el.dataset.gid);
  el.addEventListener('pointerenter',e=>{highlight(n.gid);tooltip.style.setProperty('--role',D.colors[n.role]);tooltip.innerHTML='<b>GID '+n.gid+'</b><div class="tooltip-role">'+n.role+'</div><div>Приоритет '+score(n.priority_score)+' · Кластер #'+n.cluster_id+'</div><div>Вход '+money(n.sum_in)+'</div><div>Плательщиков '+n.in_degree+' · Получателей '+n.out_degree+'</div>';tooltip.classList.remove('hidden');const b=host.getBoundingClientRect();tooltip.style.left=Math.max(8,Math.min(e.clientX-b.left+16,b.width-250))+'px';tooltip.style.top=Math.max(8,Math.min(e.clientY-b.top-110,b.height-130))+'px';});
  el.addEventListener('pointerleave',()=>{tooltip.classList.add('hidden');highlight(selected);});
  el.addEventListener('focus',()=>highlight(n.gid));
  el.addEventListener('blur',()=>highlight(selected));
  el.addEventListener('click',()=>selectNode(n.gid,false));
  el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectNode(n.gid,false);}});
 });
 svg.addEventListener('click',e=>{if(!moved&&!e.target.closest('.node')){selected=null;card=null;ai=null;highlight(null);renderCard();}});
 highlight(selected);
}
function highlight(gid) {
 const svg=document.querySelector('#network-svg');if(!svg)return;
 const neighbors=new Set(gid?[gid]:[]);
 if(gid) for(const e of D.edges){if(e.src===gid)neighbors.add(e.dst);if(e.dst===gid)neighbors.add(e.src);}
 svg.querySelectorAll('.node').forEach(el=>{el.style.opacity=gid&&!neighbors.has(el.dataset.gid)?'.12':'1';el.classList.toggle('chosen',el.dataset.gid===selected);});
 svg.querySelectorAll('.edge').forEach(el=>{const active=gid&&(el.dataset.src===gid||el.dataset.dst===gid);el.setAttribute('stroke',active?'#f5b544':el.dataset.base);el.setAttribute('opacity',gid?(active?'.95':'.035'):'.28');el.setAttribute('marker-end',active?'url(#arrow-active)':'url(#arrow)');});
}
function selectNode(gid,navigate=true) {
 if(!byId.has(gid))return;
 tactile();selected=gid;card=null;ai=null;
 if(navigate){page='network';networkTab='graph';mode='ego';render();}
 else{highlight(gid);renderCard();}
 document.querySelector('#search-results')?.replaceChildren();
 send('select',{gid});
}
function renderAi() {
 const state=ai?.gid===selected?ai:null;
 const waiting=!!state?.loading;
 const result=state?.result;
 return '<section class="ai-explanation"><div class="label">ИИ · Объяснение узла</div><p class="small muted">Краткое пояснение рассчитанных признаков. Роль и приоритет определяет алгоритм.</p><button class="btn gold" data-action="explain" '+(!A.ai_enabled||!card||waiting?'disabled':'')+'>'+icon('info')+' '+(waiting?'Готовим пояснение…':result?'Объяснить ещё раз':'Объяснить узел')+'</button>'+
 (!A.ai_enabled?'<p class="small muted">ИИ не подключён. Владелец может настроить локальный .env.</p>':'<p class="small muted">По нажатию OpenAI получит метрики выбранного GID и до 5 крупнейших связей каждого направления. Без сырых транзакций.</p>')+
 '<div aria-live="polite">'+(state?.error?'<p class="ai-error" role="alert">'+esc(state.error)+'</p>':'')+
 (result?'<div class="ai-result"><p>'+esc(result.summary)+'</p><h3>Основания</h3><ul>'+result.reasons.map(text=>'<li>'+esc(text)+'</li>').join('')+'</ul><h3>Ограничения</h3><ul>'+result.limitations.map(text=>'<li>'+esc(text)+'</li>').join('')+'</ul><p class="small muted">Текст ИИ требует сверки с метриками. Это гипотеза для проверки, не вывод о нарушении.</p></div>':'')+'</div></section>';
}
function renderCard() {
 const el=document.querySelector('#node-card');if(!el)return;
 if(!selected){el.innerHTML='<div class="empty-card"><div class="empty-icon">'+icon('search')+'</div><h3>Начните с одного узла</h3><p>Выберите клиента на графе или найдите GID, чтобы увидеть его потоки и обоснование роли.</p><div class="small muted" style="margin-top:26px">Наведите → изучите · Нажмите → откройте</div></div>';return;}
 const n=byId.get(selected);
 el.innerHTML='<div class="card-content"><div class="between"><span class="eyebrow">КАРТОЧКА КЛИЕНТА</span><button class="text-btn" data-action="clear">'+icon('close')+'</button></div><h3 class="card-id mono">GID '+selected+'</h3>'+badge(n)+'<div class="between"><span class="label">Приоритет · 0–1</span><strong class="mono">'+score(n.priority_score)+'</strong></div><div class="progress" style="--role:'+D.colors[n.role]+';margin-top:9px"><i style="width:'+n.priority_score*100+'%"></i></div><div class="divider"></div><div class="kv"><span>Обоснованность роли</span><b>'+score(n.role_score)+'</b></div><div class="kv"><span>Кластер / глубина</span><b>#'+n.cluster_id+' / '+n.depth+'</b></div><div class="kv"><span>Плательщики / получатели</span><b>'+n.in_degree+' / '+n.out_degree+'</b></div><div class="kv"><span>Входящий поток</span><b>'+money(n.sum_in)+'</b></div><div class="kv"><span>Исходящий поток</span><b>'+money(n.sum_out)+'</b></div><div class="divider"></div><span class="label">Почему этот узел</span><p class="evidence">'+esc(n.evidence)+'</p>'+(n.is_boundary_node?'<div class="notice" style="padding:12px;font-size:11px;margin:12px 0">Граница depth=4. Дальнейший выход неизвестен.</div>':'')+(n.is_seed?'<p class="small muted" style="margin-bottom:14px">Seed: входящие потоки наблюдаются не полностью.</p>':'')+'<button class="btn gold" style="width:100%" data-action="dossier" '+(!card?'disabled':'')+'>'+icon('target')+' '+(card?'Полное обоснование':'Загружаем обоснование…')+'</button><button class="btn ghost" style="width:100%;margin-top:9px" data-action="neighbors">Все связи клиента '+icon('arrow')+'</button>'+renderAi()+'</div>';
}
function openDossier() {
 if(!card)return;
 const factors=(items)=>items.map(f=>'<div class="factor"><div class="kv"><span>'+esc(f.label)+'</span><b class="mono">'+score(f.contribution)+'</b></div><div class="progress"><i style="width:'+Math.min(100,f.contribution*100)+'%"></i></div></div>').join('');
 document.querySelector('#modal').innerHTML='<div class="modal-backdrop"><section class="modal-dialog" id="dossier-modal" role="dialog" aria-modal="true" aria-label="Обоснование роли"><div class="between"><div><div class="eyebrow">ПРОВЕРЯЕМАЯ ГИПОТЕЗА</div><h2 class="mono" style="margin-top:12px">GID '+selected+'</h2></div><button class="btn tiny" aria-label="Закрыть" data-action="close-modal">'+icon('close')+'</button></div><p class="muted" style="margin-top:18px">'+esc(card.evidence)+'</p><div class="dossier-grid"><div><h3>Вклад в приоритет</h3>'+factors(card.priority_factors)+'</div><div><h3>Факторы роли</h3>'+factors(card.role_factors)+'</div></div><div class="notice">'+icon('info')+'<div><strong>Границы интерпретации</strong>'+card.limitations.map(t=>'<p style="margin-top:8px">'+esc(t)+'</p>').join('')+'</div></div><div class="dossier-grid">'+['in','out'].map(dir=>'<div><h3>'+(dir==='in'?'От кого поступили':'Кому отправлены')+'</h3>'+card[dir].slice(0,20).map(e=>'<div class="kv"><button class="text-btn mono" style="font-size:10px" data-action="modal-node" data-gid="'+e.gid+'">'+e.gid+'</button><b>'+shortMoney(e.sum_kzt)+'</b></div>').join('')+(!card[dir].length?'<p class="small muted" style="margin-top:12px">Связей в выборке нет.</p>':'')+(card[dir].length>20?'<p class="small muted">Первые 20 из '+card[dir].length+'. Все связи доступны на графе.</p>':'')+'</div>').join('')+'</div>'+renderAi()+'</section></div>';
 focusModal();
}
function openRecovery(code) {
 document.querySelector('#modal').innerHTML='<div class="modal-backdrop"><section class="modal-dialog" role="dialog" aria-modal="true" aria-label="Сохраните резервный код" style="max-width:550px"><div class="auth-symbol">'+icon('lock')+'</div><h2>Сохраните резервный код</h2><p class="muted" style="margin-top:15px">Он позволяет восстановить пароль без почтового сервиса. Код показывается один раз. После восстановления он заменяется новым.</p><code class="recovery-code">'+esc(code)+'</code><button class="btn gold" data-action="close-modal">Код сохранён · Продолжить '+icon('arrow')+'</button></section></div>';
 focusModal();
}
function focusModal(){document.querySelector('#modal button')?.focus();}
function miniNetwork(n) {
 const edges=D.edges.filter(e=>e.src===n.gid||e.dst===n.gid).slice(0,6);
 return '<svg class="mini-network" viewBox="0 0 130 70" aria-hidden="true">'+edges.map((e,i)=>{const other=byId.get(e.src===n.gid?e.dst:e.src),x=i<3?15:115,y=15+(i%3)*20;return '<line x1="65" y1="35" x2="'+x+'" y2="'+y+'" stroke="'+D.colors[other.role]+'" opacity=".5"/><circle cx="'+x+'" cy="'+y+'" r="3" fill="'+D.colors[other.role]+'"/>';}).join('')+'<circle cx="65" cy="35" r="6" fill="'+D.colors[n.role]+'" stroke="#fff" stroke-width="1"/></svg>';
}
function renderRanking() {
 document.querySelector('#content').innerHTML=searchMarkup(true)+'<div class="between" style="margin-bottom:16px"><span class="small muted" id="result-count"></span><span class="small muted">Приоритет рассчитан на сервере · шкала 0–1</span></div><div id="list-content"></div>';
 renderListContent();
}
function renderListContent() {
 const list=document.querySelector('#list-content');if(!list)return;
 const nodes=resultIds?resultIds.map(id=>byId.get(id)).filter(Boolean):D.nodes;
 document.querySelector('#result-count').textContent=num(nodes.length)+' клиентов в выборке';
 list.innerHTML=page==='ranking'?'<div class="panel table-wrap">'+nodesTable(nodes.slice(0,pageLimit))+'</div>':nodes.slice(0,pageLimit).map((n,i)=>'<div class="panel investigation"><div class="rank-num">#'+String(i+1).padStart(2,'0')+'</div><div><div class="mono gid">'+n.gid+'</div>'+badge(n)+'</div><div class="score-block"><div class="label">ПРИОРИТЕТ · 0–1</div>'+bar(n)+'<button class="text-btn small" style="margin-top:9px" data-action="open" data-gid="'+n.gid+'">Открыть узел '+icon('arrow')+'</button></div><div class="why"><div class="label">ОБОСНОВАНИЕ</div>'+esc(n.priority_why)+'</div>'+miniNetwork(n)+'</div>').join('');
 if(!nodes.length&&page==='investigations')list.innerHTML='<div class="panel section-empty">По заданным фильтрам узлы не найдены.</div>';
 if(nodes.length>pageLimit)list.innerHTML+='<div class="more-row"><button class="btn" data-action="more">Показать ещё 30 · '+num(nodes.length-pageLimit)+' осталось</button></div>';
}
function renderSearchResults(){
 const el=document.querySelector('#search-results');if(!el||!query.trim())return;
 const nodes=(resultIds||[]).slice(0,10).map(id=>byId.get(id)).filter(Boolean);
 el.innerHTML='<div class="search-results">'+(nodes.length?nodes.map(n=>'<button class="search-result" data-action="open" data-gid="'+n.gid+'"><span class="mono">'+n.gid+'</span>'+badge(n)+'</button>').join(''):'<div class="small muted" style="padding:12px">Узел или роль не найдены.</div>')+'</div>';
}
function renderClusters() {
 document.querySelector('#content').innerHTML='<div class="between" style="margin-bottom:22px"><span class="small muted">'+D.clusters.length+' сообществ · '+D.coverage.multi_seed_clusters+' с несколькими seed</span><span class="small muted">По внутреннему обороту ↓</span></div><div class="cluster-grid">'+D.clusters.map(c=>'<button class="panel cluster-card" data-action="cluster" data-cluster="'+c.cluster_id+'"><div class="between"><h3>Кластер #'+c.cluster_id+'</h3><span class="chip">'+num(c.n_nodes)+' узлов</span></div><div class="cluster-metrics"><div class="kv"><span>Seed-клиенты</span><b>'+c.n_seed+'</b></div><div class="kv"><span>Внутренний оборот</span><b class="mono">'+shortMoney(c.sum_kzt_internal)+' KZT</b></div></div><p>'+esc(c.hypothesis)+'</p><div class="cluster-footer">Исследовать связи '+icon('arrow')+'</div></button>').join('')+'</div>';
}
function renderStress() {
 const content=document.querySelector('#content');if(!content)return;
 const sim=simulation,top=sim?.results.find(x=>x.strategy==='top_priority'),random=sim?.results.find(x=>x.strategy==='random');
 content.innerHTML='<div class="panel stress-control"><div class="between"><h3>Удалить узлы с наибольшим приоритетом</h3><span class="stress-count" id="remove-label">'+removalCount+'</span></div><input id="remove-count" aria-label="Число удаляемых узлов" type="range" min="1" max="20" value="'+removalCount+'"><div class="range-labels"><span>1</span><span>5</span><span>10</span><span>15</span><span>20</span></div></div>'+
 (sim?'<div class="triple"><div class="panel info-card"><div class="label">Крупнейшая компонента</div><h3 class="mono"><span class="muted">'+num(sim.original_largest)+' → </span>'+num(top.largest_component_mean)+'</h3><p>Клиентов после удаления '+sim.removed.length+' узлов</p></div><div class="panel info-card"><div class="label">Компоненты, включая изоляты</div><h3 class="mono"><span class="muted">'+sim.original_components+' → </span>'+num(top.components_mean)+'</h3><p>Все связные фрагменты оставшегося графа</p></div><div class="panel info-card"><div class="label">Случайное удаление · 30 повторов</div><h3 class="mono">'+num(random.largest_component_mean)+'</h3><p>Средний размер крупнейшей компоненты · σ '+Number(random.largest_component_std).toFixed(1)+'</p></div></div><section class="panel grid-bg"><div class="panel-head"><h2>Фрагменты оставшейся сети</h2><span class="small muted">Площадь круга ∝ числу узлов</span></div>'+fragmentFigure(sim.sizes)+'<div style="padding:20px" class="small muted">Показаны первые '+Math.min(sim.sizes.length,30)+' из '+sim.sizes.length+' компонент. Размеры рассчитаны после удаления выбранных узлов.</div></section><div class="notice">'+icon('shield')+'<div><strong>Сценарий связности</strong>Расчёт на неориентированной проекции. Уменьшение крупнейшей компоненты не равно числу изолированных клиентов. Это инструмент исследования, а не рекомендация блокировки счетов.</div></div>':'<div class="panel section-empty">Рассчитываем структуру оставшейся сети…</div>');
}
function fragmentFigure(sizes) {
 return '<svg class="fragment-chart" viewBox="0 0 1100 280" role="img" aria-label="Размеры компонент после удаления">'+sizes.slice(0,30).map((s,i)=>{const x=i===0?150:330+(i-1)%10*73,y=i===0?140:65+Math.floor((i-1)/10)*76,r=Math.max(4,Math.sqrt(s/sizes[0])*90);return '<circle cx="'+x+'" cy="'+y+'" r="'+r+'" fill="#52b7e828" stroke="#52b7e8" stroke-opacity=".6"/><text x="'+x+'" y="'+(y+r+18)+'" text-anchor="middle" fill="#8797b3" font-size="11">'+s+'</text>';}).join('')+'</svg>';
}
function renderCoverage() {
 const s=D.summary;
 document.querySelector('#content').innerHTML='<div class="stats coverage-stats">'+stat('Depth = 4 · без выхода',num(s.boundary_sinks),'Граница обхода, не доказательство удержания',D.colors.transit,'data')+stat('Seed · без исходящих',num(D.coverage.seed_without_outgoing),'Сохранены в итоговых выгрузках',D.colors.transit,'data')+stat('Переводы ниже порога','Неизвестно','Число исключённых операций не предоставлено',D.colors.transit,'data')+stat('Входящие извне','Неизвестно','Полноту нельзя оценить по этой выборке',D.colors.transit,'data')+'</div><div class="notice">'+icon('shield')+'<div><strong>Граница наблюдения — часть анализа</strong>'+num(s.boundary_sinks)+' клиентов на depth=4 без исходящих. Классифицировано как terminal: '+s.boundary_terminals+'. Отсутствие дальнейших переводов отражает предел обхода.</div></div><div class="triple"><div class="panel info-card"><div class="label">Глубина графа</div><h3 class="mono">4 колена</h3><p>Только исходящие от '+s.seeds+' seed</p></div><div class="panel info-card"><div class="label">Порог выгрузки</div><h3 class="mono">5 000 KZT</h3><p>Дробление ниже порога не наблюдается</p></div><div class="panel info-card"><div class="label">Компоненты</div><h3 class="mono">'+s.components_with_edges+' + '+s.isolated_nodes+'</h3><p>С рёбрами + изолированные клиенты</p></div></div><div class="dossier-grid"><div class="panel info-card"><h3 style="font-size:17px">Распределение ролей</h3>'+Object.entries(s.role_distribution).map(([r,v])=>'<div class="factor" style="--role:'+D.colors[r]+'"><div class="kv"><span>'+r+'</span><b>'+num(v)+'</b></div><div class="progress"><i style="width:'+v/s.nodes*100+'%"></i></div></div>').join('')+'</div><div class="panel info-card"><h3 style="font-size:17px">Что важно при интерпретации</h3><p style="margin:16px 0">Июль 2026 · внутрибанковские операции. Даты без точного времени. Нет размеченных ролей и полного баланса счёта.</p>'+s.warnings.map(w=>'<p style="margin:14px 0;border-top:1px solid #252a3b;padding-top:12px">'+esc(w)+'</p>').join('')+'</div></div>';
}
function renderExports() {
 const files=[['nodes_roles.csv','Роли всех клиентов',num(D.summary.nodes)+' строк · роль, скор, кластер, приоритет и объяснение'],['clusters.csv','Сообщества сети',D.clusters.length+' кластеров · размеры, seed, оборот и гипотезы'],['top_nodes.csv','Очередь проверок','Ранжированный список из текущего расчёта с обоснованиями'],['analysis_report.md','Аналитический отчёт','Результаты, примеры ролей и ограничения подхода'],['run_summary.json','Паспорт расчёта','Контрольные суммы входов, параметры и сводные показатели']];
 document.querySelector('#content').innerHTML='<div class="exports">'+files.map(([f,title,desc])=>'<section class="panel export-card"><span style="color:var(--gold)">'+icon('download')+'</span><h3>'+title+'</h3><p>'+desc+'</p><code class="mono small muted">'+f+'</code><div><button class="btn gold" data-action="export" data-file="'+f+'">'+icon('download')+' Скачать</button></div></section>').join('')+'</div><div class="notice">'+icon('check')+'<div><strong>Исходные схемы сохранены</strong>Три обязательных CSV скачиваются прямо из результатов пайплайна. Экран не пересчитывает роли и не меняет порядок приоритетов.</div></div>';
}
function renderFlow() {
 const roles=Object.keys(D.colors),totals=new Map(D.role_flows.map(f=>[f.source_role+'|'+f.target_role,f.sum_kzt]));
 const max=Math.max(...totals.values(),1);
 const paths=Array.from(totals).map(([key,value])=>{const [a,b]=key.split('|'),y1=45+roles.indexOf(a)*66,y2=45+roles.indexOf(b)*66;return '<path d="M 230 '+y1+' C 440 '+y1+' 540 '+y2+' 760 '+y2+'" fill="none" stroke="'+D.colors[a]+'" stroke-width="'+(1+value/max*24)+'" opacity=".3"><title>'+a+' → '+b+': '+money(value)+'</title></path>';}).join('');
 document.querySelector('#content').innerHTML='<section class="panel grid-bg"><div class="panel-head"><h2>Наблюдаемые потоки между ролями</h2><span class="muted small">Толщина ∝ сумме переводов</span></div><svg class="flow-chart" viewBox="0 0 1000 445" role="img" aria-label="Потоки между рассчитанными ролями">'+paths+roles.map((r,i)=>'<circle cx="220" cy="'+(45+i*66)+'" r="8" fill="'+D.colors[r]+'"/><text x="196" y="'+(50+i*66)+'" text-anchor="end" fill="'+D.colors[r]+'" font-size="12">'+r+'</text><circle cx="770" cy="'+(45+i*66)+'" r="8" fill="'+D.colors[r]+'"/><text x="795" y="'+(50+i*66)+'" fill="'+D.colors[r]+'" font-size="12">'+r+'</text>').join('')+'</svg><div class="legend">Отправители → Получатели · Наведите на линию для суммы</div></section><div class="notice">'+icon('info')+'<div>Агрегация существующих связей по рассчитанным ролям. Она не доказывает происхождение средств и не восстанавливает отсутствующие переводы.</div></div>';
}
function renderAbout() {
 document.querySelector('#content').innerHTML='<div class="panel info-card"><div class="eyebrow">ДАННЫЕ → МЕТРИКИ → РОЛИ → ИНТЕРФЕЙС</div><h3>От наблюдаемой сети к объяснимому решению</h3><p>Три Parquet-файла проверяются на согласованность. Направленный граф включает изолированные seed. Финансовые, структурные и временные метрики определяют допустимые роли, их обоснованность и вклад в приоритет.</p></div><div class="triple"><div class="panel info-card"><span class="label">01 · Структура</span><h3 style="font-size:19px">Кто с кем связан</h3><p>PageRank, посредничество, достижимость от seed и сообщества Louvain. Направления и суммы переводов сохранены.</p></div><div class="panel info-card"><span class="label">02 · Обоснование</span><h3 style="font-size:19px">Почему такая роль</h3><p>Шесть ролей. Формальные правила и вклады доступны в полной карточке каждого GID. Скор не является вероятностью виновности.</p></div><div class="panel info-card"><span class="label">03 · Проверка</span><h3 style="font-size:19px">Что смотреть первым</h3><p>Приоритет включает структуру, поток, связь с seed, роль, необычность и временной паттерн. Итог равен сумме вкладов.</p></div></div><div class="notice">'+icon('info')+'<div><strong>Тактильность и доступность</strong>Наведение подсвечивает связи, нажатие фиксирует клиента. Клавиша Tab перемещает фокус, Enter выбирает, Escape закрывает карточку. Колесо и кнопки меняют масштаб. Аппаратная вибрация доступна только на поддерживающих устройствах и включается отдельно в боковой панели. При системной настройке уменьшения движения анимации отключаются.</div></div>';
}
document.addEventListener('submit',e=>{
 if(e.target.id!=='auth-form')return;e.preventDefault();
 const form=new FormData(e.target);e.target.querySelector('button[type="submit"]').disabled=true;
 send(authMode,{email:form.get('email'),password:form.get('password'),recovery:form.get('recovery')||''});
});
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-action]');if(!b||b.disabled)return;tactile();
 const a=b.dataset.action;
 if(a==='nav'){page=b.dataset.page;pageLimit=30;render();window.scrollTo(0,0);}
 else if(a==='auth-mode'){authMode=b.dataset.mode;renderAuth();}
 else if(['google','logout','run'].includes(a))send(a);
 else if(a==='export')send('export',{filename:b.dataset.file});
 else if(a==='open')selectNode(b.dataset.gid);
 else if(a==='clear'){selected=null;card=null;ai=null;highlight(null);renderCard();}
 else if(a==='neighbors'){page='network';networkTab='graph';mode='ego';render();}
 else if(a==='explain'){
  if(!selected||!card||!A.ai_enabled||ai?.loading)return;
  ai={gid:selected,loading:true,result:null,error:''};
  send('explain',{gid:selected});renderCard();if(document.querySelector('#dossier-modal'))openDossier();
 }
 else if(a==='dossier')openDossier();
 else if(a==='close-modal')document.querySelector('#modal').innerHTML='';
 else if(a==='modal-node'){document.querySelector('#modal').innerHTML='';selectNode(b.dataset.gid);}
 else if(a==='network-tab'){networkTab=b.dataset.tab;render();}
 else if(a==='cluster'){activeCluster=Number(b.dataset.cluster);page='network';networkTab='graph';mode='cluster';render();}
 else if(a==='more'){pageLimit+=30;renderListContent();}
 else if(a==='haptics'){haptics=!haptics;toast(navigator.vibrate?(haptics?'Виброотклик включён':'Виброотклик выключен'):'Устройство не поддерживает вибрацию. Визуальный отклик включён.');}
});
document.addEventListener('input',e=>{
 if(e.target.id==='search'){query=e.target.value;clearTimeout(searchTimer);if(!query)document.querySelector('#search-results')?.replaceChildren();const filtered=page==='ranking'||page==='investigations';searchTimer=setTimeout(()=>send('query',{query,role:filtered?roleFilter:'',cluster:filtered?clusterFilter:''}),250);}
 if(e.target.id==='remove-count'){removalCount=Number(e.target.value);document.querySelector('#remove-label').textContent=removalCount;}
});
document.addEventListener('change',e=>{
 if(e.target.id==='role-filter'||e.target.id==='cluster-filter'){roleFilter=document.querySelector('#role-filter').value;clusterFilter=document.querySelector('#cluster-filter').value;pageLimit=30;send('query',{query,role:roleFilter,cluster:clusterFilter});}
 if(e.target.id==='graph-mode'){mode=e.target.value;if(mode==='ego'&&!selected){selected=D.nodes[0].gid;send('select',{gid:selected});}if(mode==='cluster'&&activeCluster===null)activeCluster=D.clusters[0].cluster_id;renderNetwork();}
 if(e.target.id==='graph-color'){colorMode=e.target.value;drawGraph();}
 if(e.target.id==='remove-count'){removalCount=Number(e.target.value);send('simulate',{count:removalCount});toast('Рассчитываем удаление '+removalCount+' узлов…');}
});
document.addEventListener('keydown',e=>{
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();document.querySelector('#search')?.focus();}
 if(e.key==='Escape'){document.querySelector('#modal').innerHTML='';document.querySelector('#search-results')?.replaceChildren();selected=null;card=null;ai=null;highlight(null);renderCard();}
 const dialog=document.querySelector('[role="dialog"]');
 if(dialog&&e.key==='Tab'){const list=[...dialog.querySelectorAll('button,input,[tabindex="0"]')];if(!list.length)return;const first=list[0],last=list.at(-1);if(e.shiftKey&&document.activeElement===first){last.focus();e.preventDefault();}else if(!e.shiftKey&&document.activeElement===last){first.focus();e.preventDefault();}}
});
post('streamlit:componentReady',{apiVersion:1});
fitFrame();
