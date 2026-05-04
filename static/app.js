// Thumbtack Frontend
const API_BASE = '';
let currentProject = null;
let activeAgents = {};
let websockets = {};
let fileCurrentPath = '';
let fileQueue = [];
let lastFileContent = '';
let lastFilePath = '';
let currentTheme = localStorage.getItem('thumbtack-theme') || 'dark';

// ─── Theme ───
function applyTheme(theme) {
    const html = document.documentElement;
    if (theme === 'light') html.classList.add('light');
    else html.classList.remove('light');
    const toggle = document.getElementById('themeToggle');
    if (toggle) toggle.checked = theme === 'light';
    localStorage.setItem('thumbtack-theme', theme);
    currentTheme = theme;
}
function toggleTheme() {
    const toggle = document.getElementById('themeToggle');
    applyTheme(toggle?.checked ? 'light' : 'dark');
}
document.addEventListener('DOMContentLoaded', () => { applyTheme(currentTheme); });

function $(sel){ return document.querySelector(sel); }
function $$(sel){ return document.querySelectorAll(sel); }
function showToast(msg,type='success'){
    const c=$('#toastContainer');
    if(!c)return;
    const el=document.createElement('div');
    el.className=`toast ${type}`;
    el.textContent=msg;
    c.appendChild(el);
    setTimeout(()=>el.remove(),3500);
}
async function api(url,opts={}){
    try{
        const res=await fetch(`${API_BASE}${url}`,opts);
        if(!res.ok){
            const txt=await res.text();
            let err;
            try{err=JSON.parse(txt);}catch(e){err={detail:res.statusText};}
            showToast(err.detail||'Request failed','error');
            throw new Error(err.detail);
        }
        const contentType=res.headers.get('content-type')||'';
        if(contentType.includes('application/json'))return res.json();
        return res.text();
    }catch(e){showToast('Network error: '+e.message,'error');throw e;}
}

// ─── Modal ───
function showModal(id){$(`#${id}`).classList.add('active');}
function hideModal(id){$(`#${id}`).classList.remove('active');}
function showNewProjectModal(){$('#projectName').value='';$('#projectPath').value='';$('#projectDesc').value='';showModal('newProjectModal');}

// ─── Projects ───
async function loadProjects(){
    try{
        const projects=await api('/api/projects')||[];
        const list=$('#projectsList');
        if(!projects.length){
            list.innerHTML='<div class="empty-state" style="padding:40px 0"><p style="color:var(--fg-dim);font-size:12px">No projects</p></div>';
            $('#mainEmptyCta').innerHTML='<span>+</span> Create your first project';
            return;
        }
        list.innerHTML=projects.map(p=>`
            <div class="project-item ${currentProject?.id===p.id?'active':''}" onclick="selectProject(${p.id})" data-id="${p.id}">
                <span class="icon">&#x1f4c2;</span>
                <span class="name">${escapeHtml(p.name)}</span>
                <span class="count">${p.agent_count||0}</span>
            </div>`).join('');
        $('#mainEmptyCta').innerHTML='<span>+</span> Add another project';
    }catch(e){console.log('loadProjects error',e);}
}

async function createProject(){
    const name=$('#projectName').value.trim();
    const path=$('#projectPath').value.trim();
    const desc=$('#projectDesc').value.trim();
    if(!name||!path){showToast('Name and path required','error');return;}
    await api('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,path,description:desc||null})});
    hideModal('newProjectModal');
    showToast('Project created');
    await loadProjects();
    const ps=await api('/api/projects');
    if(ps.length)selectProject(ps[0].id);
}

async function selectProject(id){
    const data=await api(`/api/projects/${id}`);
    currentProject=data;
    $('#emptyState').style.display='none';
    $('#projectView').classList.add('active');
    $$('.tab-content').forEach(t=>t.classList.remove('active'));
    $$('.tab').forEach(t=>t.classList.remove('active'));
    $('#tab-agents').classList.add('active');
    $$('.tab[data-tab="agents"]')[0]?.classList.add('active');

    $$('.project-item').forEach(el=>el.classList.toggle('active',+el.dataset.id===id));

    $('#mainHeader h2').innerHTML=`&#x1f4c1; ${escapeHtml(data.name)}`;
    $('#headerActions').innerHTML=`<button class="btn danger" onclick="deleteProject(${id})">Delete</button>`;
    $('#projectInfo').innerHTML=`<h3>${escapeHtml(data.name)}</h3><div class="path">${escapeHtml(data.path)}</div>${data.description?`<div class="desc">${escapeHtml(data.description)}</div>`:''}`;

    // Agent spawn grid
    const types=[
        {t:'claude',e:'&#x1f916;',n:'Claude Code',d:'Anthropic Claude CLI'},
        {t:'codex',e:'&#x1f989;',n:'Codex',d:'OpenAI Codex CLI'},
        {t:'opencode',e:'&#x1f510;',n:'OpenCode',d:'OpenCode CLI'},
        {t:'openclaw',e:'&#x1f98a;',n:'OpenClaw',d:'OpenClaw agent'},
        {t:'aider',e:'&#x1f9d1;&#x200d;&#x1f4bb;',n:'Aider',d:'Multi-LLM coding'},
        {t:'custom',e:'&#x2699;&#xfe0f;',n:'Custom',d:'Any shell command'},
    ];
    $('#agentTypeGrid').innerHTML=types.map(t=>`<div class="agent-card" onclick="spawnAgent('${t.t}')"><div class="emoji">${t.e}</div><div class="name">${t.n}</div><div class="desc">${t.d}</div></div>`).join('');

    renderAgentsPanel(data.agents||[]);
    loadFileBrowser('');
    loadTaskQueue();
    // Load git status if git tab is active
    if(document.querySelector('.tab[data-tab="git"].active')) loadGitStatus();
}

async function deleteProject(id){if(!confirm('Delete this project and all its agents?'))return;await api(`/api/projects/${id}`,{method:'DELETE'});currentProject=null;$('#emptyState').style.display='flex';$('#projectView').classList.remove('active');$('#mainHeader h2').innerHTML='<span>&#x1f680;</span> Select a project';$('#headerActions').innerHTML='';showToast('Project deleted');await loadProjects();}

// ─── Agents ───
async function spawnAgent(agentType){
    if(!currentProject){showToast('Select a project first','error');return;}
    let customCmd='';
    if(agentType==='custom'){customCmd=prompt('Enter custom command:');if(!customCmd)return;}
    showToast(`Spawning ${agentType}...`);
    try{
        const agent=await api('/api/agents',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project_id:currentProject.id,agent_type:agentType,command:customCmd||null})});
        showToast(`${agentType} spawned (id:${agent.id})`);
        await selectProject(currentProject.id);
        connectWebSocket(agent.id,agentType);
    }catch(e){showToast(`Failed to spawn ${agentType}`,'error');}
}

async function stopAgent(agentId){
    await api(`/api/agents/${agentId}/stop`,{method:'POST'});
    if(websockets[agentId]){websockets[agentId].close();delete websockets[agentId];}
    delete activeAgents[agentId];
    showToast('Agent stopped');
    await selectProject(currentProject.id);
}
async function killAgent(agentId){
    if(!confirm('Force kill this agent?'))return;
    await api(`/api/agents/${agentId}`,{method:'DELETE'});
    if(websockets[agentId]){websockets[agentId].close();delete websockets[agentId];}
    delete activeAgents[agentId];
    showToast('Agent killed');
    await selectProject(currentProject.id);
}
async function sendCommand(agentId){
    const input=$(`#cmd-input-${agentId}`);
    const cmd=input.value.trim();
    if(!cmd)return;
    input.value='';
    appendToTerminal(agentId,'system',`$ ${cmd}`);
    try{await api(`/api/agents/${agentId}/command`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({command:cmd})});}catch(e){
        const ws=websockets[agentId];
        if(ws&&ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({type:'command',command:cmd}));
    }
}
async function runPreset(agentId,cmd){const input=$(`#cmd-input-${agentId}`);input.value=cmd;sendCommand(agentId);}

// ─── WebSocket ───
function connectWebSocket(agentId,agentType){
    if(websockets[agentId])return;
    const protocol=window.location.protocol==='https:'?'wss:':'ws:';
    const ws=new WebSocket(`${protocol}//${window.location.host}/ws/agents/${agentId}`);
    websockets[agentId]=ws;
    ws.onopen=()=>appendToTerminal(agentId,'system',`[Connected to ${agentType} stream]`);
    ws.onmessage=(ev)=>{const msg=JSON.parse(ev.data);appendToTerminal(agentId,msg.stream,msg.data);};
    ws.onclose=()=>{appendToTerminal(agentId,'system','[Stream disconnected]');delete websockets[agentId];};
    ws.onerror=(e)=>appendToTerminal(agentId,'stderr',`[WebSocket error]`);
}

// ─── Terminal ───
function appendToTerminal(agentId,stream,data){
    const term=$(`#terminal-${agentId}`);
    if(!term)return;
    const line=document.createElement('div');
    line.className=`line ${stream}`;
    line.textContent=data.endsWith('\n')?data:data+'\n';
    term.appendChild(line);
    term.scrollTop=term.scrollHeight;
    while(term.children.length>500)term.removeChild(term.firstChild);
}

// ─── Render Agents Panel ───
async function renderAgentsPanel(agents){
    const container=$('#agentsContainer');
    if(!agents?.length){container.innerHTML='<p style="color:var(--fg-dim);font-size:13px;padding:20px 0;text-align:center">No active agents. Spawn one above.</p>';return;}
    const presetsMap={};
    for(const a of agents){if(!presetsMap[a.agent_type]){try{presetsMap[a.agent_type]=await api(`/api/presets/${a.agent_type}`);}catch{presetsMap[a.agent_type]=[];}}}
    container.innerHTML=agents.map(a=>{
        const statusClass={running:'running',idle:'idle',error:'error',completed:'completed',stopping:'idle'}[a.status]||'idle';
        const statusLabel=a.status.charAt(0).toUpperCase()+a.status.slice(1);
        const presets=(presetsMap[a.agent_type]||[]).slice(0,5).map(p=>`<span class="chip" onclick="runPreset(${a.id},'${escapeJs(p.command)}')">${escapeHtml(p.label)}</span>`).join('');
        return `<div class="agent-panel" id="agent-panel-${a.id}"><div class="agent-panel-header" onclick="togglePanel(${a.id})"><span class="status-dot ${statusClass}"></span><span class="agent-name">${escapeHtml(a.agent_type.toUpperCase())} #${a.id}</span><span class="agent-meta">${statusLabel}${a.pid?` &#8226; PID ${a.pid}`:''}</span><div class="panel-actions" onclick="event.stopPropagation()"><button onclick="sendCommand(${a.id})">Send</button><button onclick="stopAgent(${a.id})">Stop</button><button onclick="killAgent(${a.id})">Kill</button></div></div><div class="terminal" id="terminal-${a.id}"></div><div class="quick-commands">${presets}</div><div class="terminal-prompt"><input type="text" id="cmd-input-${a.id}" placeholder="Type command..." onkeydown="if(event.key==='Enter') sendCommand(${a.id})"><button onclick="sendCommand(${a.id})">Run</button></div></div>`;
    }).join('');
}

function togglePanel(agentId){}

// ─── File Browser ───
async function loadFileBrowser(path){
    if(!currentProject){$('#fileBrowser').innerHTML='<p style="color:var(--fg-dim);font-size:12px;padding:16px;text-align:center">Select a project</p>';return;}
    fileCurrentPath=path;
    try{
        const data=await api(`/api/projects/${currentProject.id}/files?path=${encodeURIComponent(path)}`);
        const fb=$('#fileBrowser');
        const rel=data.rel||'';
        let html='<div class="breadcrumbs">';
        const parts=rel?rel.split('/'):[];
        html+='<span onclick="loadFileBrowser(\'\')">&#x1f4c1;</span>';
        let accum='';
        for(const part of parts){if(!part)continue;accum=accum?accum+'/'+part:part;html+=` / <span onclick="loadFileBrowser('${escapeJs(accum)}')">${escapeHtml(part)}</span>`;}
        html+='</div>';
        for(const item of data.items||[]){
            const icon=item.is_dir?'&#x1f4c1;':getFileIcon(item.ext);
            html+=`<div class="file-item" onclick="${item.is_dir?`loadFileBrowser('${escapeJs(item.path)}')`:`openFile('${escapeJs(item.path)}')`}">${item.is_dir?'<span class="icon">'+icon+'</span>':''}<span class="name">${escapeHtml(item.name)}</span>${item.size!==null?`<span class="size">${formatBytes(item.size)}</span>`:''}</div>`;
        }
        if(!data.items.length)html+='<p style="color:var(--fg-dim);font-size:12px;padding:16px">Empty directory</p>';
        fb.innerHTML=html;
        $('#fileCount').textContent=`${(data.items||[]).length} items`;
    }catch(e){$('#fileBrowser').innerHTML='<p style="color:var(--fg-dim);font-size:12px;padding:16px">Error loading files</p>';}
}
function getFileIcon(ext){const icons={'.py':'&#x1f40d;', '.js':'&#x1f4dd;', '.ts':'&#x1f4dd;', '.json':'&#x23f0;', '.md':'&#x1f4dd;', '.html':'&#x1f3e0;', '.css':'&#x1f3a8;', '.db':'&#x1f4be;'};return icons[ext]||'&#x1f4c4;';}
function formatBytes(bytes){if(bytes<1024)return bytes+'B';if(bytes<1048576)return(bytes/1024).toFixed(1)+'KB';return(bytes/1048576).toFixed(1)+'MB';}

async function openFile(path){
    if(!currentProject)return;
    try{
        const data=await api(`/api/projects/${currentProject.id}/files/read?filepath=${encodeURIComponent(path)}`);
        lastFileContent=data.content;
        lastFilePath=path;
        $('#fileModalTitle').textContent=path;
        $('#fileModalContent').textContent=data.content;
        showModal('fileModal');
    }catch(e){showToast('Failed to read file','error');}
}
function copyFileContent(){navigator.clipboard.writeText(lastFileContent).then(()=>showToast('Copied'));}async function sendFileToAgent(){if(lastFileContent){const prompt='Review this file: '+lastFilePath+'\n\n```\n'+lastFileContent.substring(0,5000)+'\n```';if(currentProject?.agents?.length){await runPreset(currentProject.agents[0].id,'/review-file '+lastFilePath);}hideModal('fileModal');}}

// ─── Comparison ───
async function spawnComparison(){
    if(!currentProject){showToast('Select a project first','error');return;}
    const left=$('#compLeft').value,right=$('#compRight').value,cmd=$('#compCommand').value.trim();
    showToast(`Starting ${left} vs ${right}...`);
    try{
        const result=await api(`/api/comparison?left_type=${left}&right_type=${right}&project_id=${currentProject.id}${cmd?'&command='+encodeURIComponent(cmd):''}`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
        showToast('Comparison started');
        renderComparison(result);
    }catch(e){showToast('Failed to start comparison','error');}
}
async function renderComparison(comp){
    const container=$('#comparisonContainer');
    container.innerHTML=`<div style="flex:1;display:flex"><div class="comparison-side"><div class="comparison-header">${comp.left_type.toUpperCase()} #${comp.left_agent_id}</div><div class="comparison-terminal" id="comp-term-left"></div></div><div class="comparison-side"><div class="comparison-header">${comp.right_type.toUpperCase()} #${comp.right_agent_id}</div><div class="comparison-terminal" id="comp-term-right"></div></div></div><div class="comparison-controls"><input type="text" id="compInput" placeholder="Send command to both..." onkeydown="if(event.key==='Enter')sendComparisonCommand()"><button class="btn primary" onclick="sendComparisonCommand()">Send Both</button><button class="btn danger" onclick="clearComparison()">Clear</button></div>`;
    setTimeout(()=>{connectWebSocket(comp.left_agent_id,comp.left_type);connectWebSocket(comp.right_agent_id,comp.right_type);
        if(!websockets[comp.left_agent_id]?.onmessage_orig){const orig=websockets[comp.left_agent_id].onmessage;websockets[comp.left_agent_id].onmessage=(ev)=>{orig(ev);const msg=JSON.parse(ev.data);const t=$('#comp-term-left');if(t){const l=document.createElement('div');l.className=`line ${msg.stream}`;l.textContent=msg.data;t.appendChild(l);t.scrollTop=t.scrollHeight;}};}
        if(!websockets[comp.right_agent_id]?.onmessage_orig){const orig=websockets[comp.right_agent_id].onmessage;websockets[comp.right_agent_id].onmessage=(ev)=>{orig(ev);const msg=JSON.parse(ev.data);const t=$('#comp-term-right');if(t){const l=document.createElement('div');l.className=`line ${msg.stream}`;l.textContent=msg.data;t.appendChild(l);t.scrollTop=t.scrollHeight;}};}
    },100);
}
async function sendComparisonCommand(){const cmd=$('#compInput').value.trim();if(!cmd)return;$('#compInput').value='';for(const agentId in websockets){if(websockets[agentId].readyState===WebSocket.OPEN)websockets[agentId].send(JSON.stringify({type:'command',command:cmd}));}for(const compId in compData){agent_manager.send_command(compData[compId].left_agent_id,cmd);agent_manager.send_command(compData[compId].right_agent_id,cmd);}}
function clearComparison(){$('#comparisonContainer').innerHTML='<div style="flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;color:var(--fg-dim);gap:10px"><div style="font-size:32px;opacity:0.3">&#x2696;&#xfe0f;</div><p>Select two agents and start a comparison</p></div>';}

// ─── Task Queue ───
let taskList=[];
async function loadTaskQueue(){
    if(!currentProject){$('#taskQueueList').innerHTML='<p style="color:var(--fg-dim);font-size:13px;padding:40px 0;text-align:center">No project selected</p>';return;}
    try{
        const tasks=await api(`/api/projects/${currentProject.id}/tasks`)||[];
        taskList=tasks;
        renderTaskQueue();
    }catch(e){$('#taskQueueList').innerHTML='<p style="color:var(--fg-dim);font-size:13px;padding:40px 0;text-align:center">No tasks</p>';}
}
function renderTaskQueue(){
    const el=$('#taskQueueList');
    if(!taskList.length){el.innerHTML='<p style="color:var(--fg-dim);font-size:13px;padding:40px 0;text-align:center">No tasks yet. Add one above.</p>';return;}
    el.innerHTML=taskList.map(t=>{
        const statusClass={pending:'pending',running:'running',done:'done',error:'error'}[t.status]||'pending';
        return `<div class="task-item"><span class="status ${statusClass}">${t.status}</span><span class="text">${escapeHtml(t.task_text)}</span><span class="result">${t.result||''}</span><div class="actions">${t.status==='pending'?`<button onclick="runTask(${t.id})">Run</button>`:''}<button onclick="deleteTask(${t.id})">Delete</button></div></div>`;
    }).join('');
}
async function addTask(){
    if(!currentProject){showToast('Select a project first','error');return;}
    const text=$('#taskInput').value.trim();
    if(!text){showToast('Task text required','error');return;}
    $('#taskInput').value='';
    await api(`/api/projects/${currentProject.id}/tasks`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_text:text})});
    showToast('Task added');
    await loadTaskQueue();
}
async function deleteTask(id){await api(`/api/tasks/${id}`,{method:'DELETE'});showToast('Task deleted');await loadTaskQueue();}
async function runTask(id){
    if(!currentProject||!currentProject.agents?.length){showToast('No active agents to run task','error');return;}
    const agent=currentProject.agents[0];
    showToast('Running task...');
    await api(`/api/tasks/${id}/run?agent_id=${agent.id}`,{method:'POST'});
    await loadTaskQueue();
}
async function runAllTasks(){
    const pending=taskList.filter(t=>t.status==='pending');
    if(!pending.length){showToast('No pending tasks','error');return;}
    if(!currentProject?.agents?.length){showToast('No active agents','error');return;}
    showToast(`Running ${pending.length} tasks...`);
    for(const t of pending){await api(`/api/tasks/${t.id}/run?agent_id=${currentProject.agents[0].id}`,{method:'POST'});}
    await loadTaskQueue();
}
async function clearCompletedTasks(){
    const done=taskList.filter(t=>t.status==='done');
    for(const t of done){await api(`/api/tasks/${t.id}`,{method:'DELETE'});}
    showToast(`Cleared ${done.length} done tasks`);
    await loadTaskQueue();
}

// ─── Tabs ───
function switchTab(tab){
    $$('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===tab));
    $$('.tab-content').forEach(t=>t.classList.toggle('active',t.id===`tab-${tab}`));
    if(tab === 'git' && currentProject){
        loadGitStatus();
        loadGitLog();
    }
}

// ─── Helpers ───
function escapeHtml(str){if(!str)return'';return str.replace(/[<>&"']/g,m=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;',"'":'&#39;'}[m]));}
function escapeJs(str){if(!str)return'';return str.replace(/'/g,"\\'").replace(/"/g,'\\"');}

// ─── Init ───
window.addEventListener('DOMContentLoaded',()=>{
    loadProjects();
    document.addEventListener('keydown',e=>{if(e.key==='Escape'){hideModal('newProjectModal');hideModal('fileModal');}});
});
// ─── Git ───
let gitState = {repo_exists:false,branch:'',is_dirty:false,modified:[],untracked:[],staged:[]};
let gitDiffCache = {};

async function loadGitStatus(){
    if(!currentProject) return;
    const sb = $('#gitStatusBar');
    const initBtn = $('#gitInitBtn');
    const commitGroup = $('#gitCommitGroup');
    const panel = $('#gitPanel');
    sb.innerHTML = '<span style="color:var(--fg-dim)">Loading git status...</span>';
    initBtn.style.display = 'none';
    commitGroup.style.display = 'none';
    try{
        const data = await api(`/api/projects/${currentProject.id}/git/status`);
        gitState = data;
        if(!data.repo_exists){
            sb.innerHTML = `<span style="color:var(--fg-dim)">No git repository</span>`;
            initBtn.style.display = '';
            panel.innerHTML = '<p style="color:var(--fg-dim);font-size:13px;padding:40px 0;text-align:center">No repository yet. Click "Init Repo" to initialize git.</p>';
            return;
        }
        initBtn.style.display = 'none';
        commitGroup.style.display = '';
        const branchBadge = `<span class="git-badge branch">${escapeHtml(data.branch||'unknown')}</span>`;
        const cleanBadge = data.is_dirty ? '<span class="git-badge dirty">unsaved changes</span>' : '<span class="git-badge clean">clean</span>';
        const counts = [];
        if(data.modified?.length) counts.push(`${data.modified.length} modified`);
        if(data.untracked?.length) counts.push(`${data.untracked.length} untracked`);
        if(data.staged?.length) counts.push(`${data.staged.length} staged`);
        const countTxt = counts.length ? ' · ' + counts.join(', ') : '';
        sb.innerHTML = branchBadge + cleanBadge + `<span style="color:var(--fg-dim);font-size:12px">${countTxt}</span>`;
        renderGitPanel();
        loadGitHubRemoteStatus();
        loadGitLog();  // Also refresh commit history when status changes
    }catch(e){
        sb.innerHTML = `<span style="color:var(--accent4)">Error loading git status</span>`;
        panel.innerHTML = `<p style="color:var(--accent4);padding:20px">${escapeHtml(e.message||'Failed to load git status')}</p>`;
    }
}

function renderGitPanel(){
    const panel = $('#gitPanel');
    const data = gitState;
    if(!data.repo_exists){
        panel.innerHTML = '<p style="color:var(--fg-dim);font-size:13px;padding:40px 0;text-align:center">No repository yet.</p>';
        return;
    }
    let html = '';
    const sections = [];
    if(data.staged?.length) sections.push({label:'Staged',items:data.staged,ind:'added',icon:'+'});
    if(data.modified?.length) sections.push({label:'Modified',items:data.modified,ind:'modified',icon:'~'});
    if(data.untracked?.length) sections.push({label:'Untracked',items:data.untracked,ind:'untracked',icon:'?'});
    if(!sections.length){
        html = '<div style="padding:60px 0;text-align:center;color:var(--fg-dim)"><div style="font-size:32px;margin-bottom:12px;opacity:.3">&#x2705;</div><p>Working tree clean</p></div>';
    }else{
        for(const sec of sections){
            html += `<div class="git-file-group"><h5>${escapeHtml(sec.label)} (${sec.items.length})</h5>`;
            for(const f of sec.items){
                const fileId = 'diff-' + f.replace(/[^a-z0-9]/gi,'_');
                html += `<div class="git-file-item" onclick="toggleGitDiff('${escapeJs(f)}','${fileId}')">
                    <span class="indicator ${sec.ind}">${sec.icon}</span>
                    <span class="fname">${escapeHtml(f)}</span>
                    <span style="color:var(--fg-dim);font-size:11px">show diff &#x25bc;</span>
                 </div>
                 <div class="git-diff-box" id="${fileId}" style="display:none"></div>`;
            }
            html += '</div>';
        }
    }
    panel.innerHTML = html;
}

async function toggleGitDiff(filepath, elemId){
    const box = $('#'+elemId);
    if(!box) return;
    if(box.style.display !== 'none'){ box.style.display='none'; return; }
    box.style.display = '';
    if(gitDiffCache[filepath]){
        box.innerHTML = gitDiffCache[filepath];
        return;
    }
    box.innerHTML = '<span style="color:var(--fg-dim)">Loading diff...</span>';
    try{
        const data = await api(`/api/projects/${currentProject.id}/git/diff?filepath=${encodeURIComponent(filepath)}`);
        let content = '';
        if(data.empty){
            content = '<span style="color:var(--fg-dim)">No diff available.</span>';
        }else{
            content = escapeHtml(data.diff).replace(/^\u002b([^\n]+)/gm, '<span class="diff-add">+$1</span>')
                                           .replace(/^\u002d([^\n]+)/gm, '<span class="diff-rem">-$1</span>')
                                           .replace(/^@@[^\n]+/gm, '<span class="diff-hdr">$\u0026</span>');
        }
        gitDiffCache[filepath] = content;
        box.innerHTML = content;
    }catch(e){
        box.innerHTML = '<span style="color:var(--accent4)">Failed to load diff</span>';
    }
}

async function gitInit(){
    if(!currentProject) return;
    showToast('Initializing repository...');
    try{
        const data = await api(`/api/projects/${currentProject.id}/git/init`,{method:'POST'});
        showToast(data.status === 'initialized' ? 'Git initialized!' : 'Already initialized');
        await loadGitStatus();
    }catch(e){ showToast('Failed to init repo','error'); }
}

async function gitCommit(){
    if(!currentProject) return;
    const msg = $('#commitMessage').value.trim();
    if(!msg){ showToast('Enter a commit message','error'); return; }
    showToast('Committing...');
    try{
        const data = await api(`/api/projects/${currentProject.id}/git/commit`,{
            method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({message:msg})
        });
        $('#commitMessage').value='';
        if(data.status==='committed') showToast('Committed: '+msg);
        else showToast(data.message||'Nothing to commit','warn');
        gitDiffCache = {};
        await loadGitStatus();
    }catch(e){ showToast('Commit failed: '+e.message,'error'); }
}

// ─── GitHub Integration ───

// ─── Git Log / History ───
let gitLogCache = [];

async function loadGitLog(){
    if(!currentProject) return;
    const container = $('#gitLogContainer');
    const section = $('#gitHistorySection');
    if(!container || !section) return;
    // Show section only if repo exists; render loading state
    if(!gitState.repo_exists){
        section.style.display = 'none';
        return;
    }
    section.style.display = 'block';
    container.innerHTML = '<p style="color:var(--fg-dim);font-size:13px;padding:20px 0;text-align:center">Loading history...</p>';
    try{
        const data = await api(`/api/projects/${currentProject.id}/git/log?limit=50`);
        gitLogCache = data.commits || [];
        renderGitLog();
    }catch(e){
        container.innerHTML = '<p style="color:var(--accent4);font-size:13px;padding:20px 0;text-align:center">Failed to load history</p>';
    }
}

function renderGitLog(){
    const container = $('#gitLogContainer');
    if(!container) return;
    if(!gitLogCache.length){
        container.innerHTML = '<p style="color:var(--fg-dim);font-size:13px;padding:20px 0;text-align:center">No commits yet.</p>';
        return;
    }
    const html = gitLogCache.map((c, i) => {
        const dateStr = c.date ? new Date(c.date).toLocaleString(undefined, {month:'short', day:'numeric', hour:'2-digit', minute:'2-digit'}) : '';
        const isLast = i === gitLogCache.length - 1;
        return `<div class="git-log-item">
            <div class="git-log-graph">
                <div class="git-log-dot"></div>
                ${!isLast ? '<div class="git-log-line"></div>' : ''}
            </div>
            <div class="git-log-body">
                <div class="git-log-message">${escapeHtml(c.message)}</div>
                <div class="git-log-meta">
                    <span class="git-log-hash">${escapeHtml(c.short_hash)}</span>
                    <span class="git-log-author">${escapeHtml(c.author)}</span>
                    <span class="git-log-date">${escapeHtml(dateStr)}</span>
                </div>
            </div>
        </div>`;
    }).join('');
    container.innerHTML = html;
}

// ─── GitHub Integration ───

function toggleSettingsPanel(){
    const panel = document.getElementById('settingsPanel');
    const sidebar = document.querySelector('.sidebar');
    const isHidden = panel.style.display === 'none';
    if(isHidden){
        panel.style.display = 'flex';
        loadGitHubConfig();
    }else{
        panel.style.display = 'none';
    }
}

async function loadGitHubConfig(){
    try{
        const data = await api('/api/github/config');
        if(data.configured){
            document.getElementById('ghUsername').value = data.username || '';
            document.getElementById('ghEmail').value = data.email || '';
            document.getElementById('ghToken').value = '';
            document.getElementById('ghBranch').value = data.default_branch || 'main';
        }else{
            document.getElementById('ghUsername').value = '';
            document.getElementById('ghEmail').value = '';
            document.getElementById('ghToken').value = '';
            document.getElementById('ghBranch').value = 'main';
        }
    }catch(e){ console.error('Failed to load GitHub config:', e); }
}

async function saveGitHubConfig(){
    const username = document.getElementById('ghUsername').value.trim();
    const email = document.getElementById('ghEmail').value.trim();
    const token = document.getElementById('ghToken').value.trim();
    const branch = document.getElementById('ghBranch').value.trim() || 'main';
    if(!username){ showToast('Username required','error'); return; }
    try{
        await api('/api/github/config',{
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ username, email, token, default_branch: branch })
        });
        showToast('GitHub settings saved');
        toggleSettingsPanel();
    }catch(e){ showToast('Failed to save: '+e.message,'error'); }
}

async function clearGitHubConfig(){
    try{
        await api('/api/github/config',{method:'DELETE'});
        document.getElementById('ghUsername').value = '';
        document.getElementById('ghEmail').value = '';
        document.getElementById('ghToken').value = '';
        document.getElementById('ghBranch').value = 'main';
        showToast('GitHub settings cleared');
    }catch(e){ showToast('Failed to clear: '+e.message,'error'); }
}

async function loadGitHubRemoteStatus(){
    if(!currentProject) return;
    const section = document.getElementById('githubRemoteSection');
    const form = document.getElementById('githubRemoteForm');
    const linked = document.getElementById('githubRemoteLinked');
    const badge = document.getElementById('githubRemoteBadge');
    const urlDisplay = document.getElementById('githubRemoteUrlDisplay');

    try{
        const data = await api(`/api/projects/${currentProject.id}/git/remote`);
        if(data.has_remote){
            section.style.display = 'block';
            form.style.display = 'none';
            linked.style.display = 'block';
            badge.textContent = 'Linked';
            badge.className = 'remote-badge linked';
            urlDisplay.textContent = data.url || '';
        }else{
            section.style.display = 'block';
            form.style.display = 'block';
            linked.style.display = 'none';
            badge.textContent = 'Not Linked';
            badge.className = 'remote-badge not-linked';
        }
    }catch(e){
        section.style.display = 'block';
        form.style.display = 'block';
        linked.style.display = 'none';
        badge.textContent = 'Not Linked';
        badge.className = 'remote-badge not-linked';
        console.error('Remote status error:', e);
    }
}

async function linkGitHubRemote(){
    if(!currentProject) return;
    const url = document.getElementById('githubRemoteUrl').value.trim();
    if(!url){ showToast('Enter a GitHub repository URL','error'); return; }
    if(!url.includes('github.com')){ showToast('URL must be a GitHub repository','error'); return; }
    showToast('Linking remote...');
    try{
        const data = await api(`/api/projects/${currentProject.id}/git/remote`,{
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({url})
        });
        showToast('Remote linked!');
        document.getElementById('githubRemoteUrl').value = '';
        await loadGitHubRemoteStatus();
        await loadGitStatus();
    }catch(e){ showToast('Failed to link: '+e.message,'error'); }
}

async function unlinkGitHubRemote(){
    if(!currentProject) return;
    showToast('Unlinking remote...');
    try{
        // Remove origin remote
        await api(`/api/projects/${currentProject.id}/git/remote`,{
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({url:''})
        });
        showToast('Remote unlinked');
        await loadGitHubRemoteStatus();
    }catch(e){ showToast('Failed to unlink','error'); }
}

async function gitPush(){
    if(!currentProject) return;
    showToast('Pushing to GitHub...');
    try{
        const cfg = await api('/api/github/config');
        const branch = cfg.default_branch || 'main';
        const data = await api(`/api/projects/${currentProject.id}/git/push`,{
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ branch })
        });
        const output = document.getElementById('gitPushPullOutput');
        output.textContent = data.output || 'Push complete';
        output.style.color = 'var(--accent2)';
        showToast('Pushed to '+branch);
        await loadGitStatus();
    }catch(e){
        const output = document.getElementById('gitPushPullOutput');
        output.textContent = e.message || 'Push failed';
        output.style.color = 'var(--accent4)';
        showToast('Push failed: '+e.message,'error');
    }
}

async function gitPull(){
    if(!currentProject) return;
    showToast('Pulling from GitHub...');
    try{
        const cfg = await api('/api/github/config');
        const branch = cfg.default_branch || 'main';
        const data = await api(`/api/projects/${currentProject.id}/git/pull`,{
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ branch })
        });
        const output = document.getElementById('gitPushPullOutput');
        output.textContent = data.output || 'Pull complete';
        output.style.color = 'var(--accent2)';
        showToast('Pulled from '+branch);
        await loadGitStatus();
    }catch(e){
        const output = document.getElementById('gitPushPullOutput');
        output.textContent = e.message || 'Pull failed';
        output.style.color = 'var(--accent4)';
        showToast('Pull failed: '+e.message,'error');
    }
}

// Expose for inline onclicks
window.toggleSettingsPanel=toggleSettingsPanel;
window.saveGitHubConfig=saveGitHubConfig;
window.clearGitHubConfig=clearGitHubConfig;
window.linkGitHubRemote=linkGitHubRemote;
window.unlinkGitHubRemote=unlinkGitHubRemote;
window.gitPush=gitPush;
window.gitPull=gitPull;
window.selectProject=selectProject;
window.createProject=createProject;
window.showNewProjectModal=showNewProjectModal;
window.hideModal=hideModal;
window.switchTab=switchTab;
window.deleteProject=deleteProject;
window.spawnAgent=spawnAgent;
window.stopAgent=stopAgent;
window.killAgent=killAgent;
window.sendCommand=sendCommand;
window.runPreset=runPreset;
window.loadFileBrowser=loadFileBrowser;
window.openFile=openFile;
window.copyFileContent=copyFileContent;
window.sendFileToAgent=sendFileToAgent;
window.spawnComparison=spawnComparison;
window.sendComparisonCommand=sendComparisonCommand;
window.clearComparison=clearComparison;
window.addTask=addTask;
window.deleteTask=deleteTask;
window.runTask=runTask;
window.runAllTasks=runAllTasks;
window.clearCompletedTasks=clearCompletedTasks;
window.toggleGitDiff=toggleGitDiff;
window.loadGitStatus=loadGitStatus;
window.gitCommit=gitCommit;
window.gitInit=gitInit;
window.loadGitLog=loadGitLog;
window.renderGitLog=renderGitLog;
