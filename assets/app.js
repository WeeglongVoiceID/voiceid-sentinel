'use strict';
(() => {
  const session = new URLSearchParams(location.search).get('session') || '';
  const get = id => document.getElementById(id);
  const ui = {
    sample:get('sample-btn'), file:get('case-file'), offline:get('offline-btn'), preview:get('preview-btn'),
    meta:get('meta-btn'), activity:get('activity-indicator'), error:get('error-msg'),
    source:get('case-source'), connection:get('connect-pill'), caseLabel:get('case-label'), mode:get('mode-label')
  };
  let currentCase = null, currentRaw = null, currentResult = null, metaAvailable = false, busy = false, currentScenario = 'unlinked-sequence';

  function el(tag, cls='', val=null) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (val !== null) node.textContent = String(val);
    return node;
  }
  function clear(node) {node.replaceChildren();}
  function text(id,value) {get(id).textContent = String(value);}
  function showError(message) {ui.error.textContent = message;ui.error.hidden = !message;}
  function notice(message) {ui.activity.textContent = message;}
  function changeBusy(on) {
    busy=on;
    for (const control of [ui.sample,ui.offline,ui.preview,ui.meta,ui.file]) control.disabled=on;
    ui.meta.disabled=on || !metaAvailable;
    ui.preview.disabled=on || currentScenario !== 'unlinked-sequence';
    if(on) notice('Validating evidence…');
  }
  async function request(path,method='GET',payload=null) {
    if(!session) throw new Error('Missing local session token. Open the full URL printed by PowerShell.');
    const opts={method,headers:{'X-Sentinel-Token':session}};
    if(payload !== null){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(payload);}
    const response=await fetch(path,opts);
    let data;
    try {data=await response.json();} catch {throw new Error('Unexpected server response.');}
    if(!response.ok) throw new Error(data.error || `Server error ${response.status}`);
    return data;
  }
  function saveDownload(filename, content, mime) {
    const blob = new Blob([content], {type:mime});
    const href = URL.createObjectURL(blob);
    const a = el('a'); a.href = href; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(href), 1500);
  }
  function download(kind) {
    if (!currentResult) return;
    const id = currentResult.dossier.case_id;
    if (kind === 'report') {
      saveDownload(`sentinel_investigation_report_${id}.md`, currentResult.report_markdown + '\n',
                   'text/markdown;charset=utf-8');
      return;
    }
    const body = kind === 'dossier' ? currentResult.dossier : currentResult.audit;
    saveDownload(`sentinel_${kind}_${id}.json`, JSON.stringify(body,null,2)+'\n', 'application/json;charset=utf-8');
  }
  function printReport() {
    if (!currentResult) return;
    // Print the source-derived overview, the clearly labeled advisory and audit.
    // Model-proposed evidence collection remains collapsed; it is not approved policy.
    window.print();
  }
  function pill(content, state) {const c=el('b',state,String(content));return c;}
  function evidenceTags(refs) {
    const tags = el('div','evidence-tags');
    for(const [index,ref] of (refs || []).entries()) {
      if(index) tags.append(document.createTextNode(' · '));
      const eventId = String(ref).split('.')[0];
      // Event IDs came from the server-side strict schema validator.
      const link = el('a','evidence-ref',ref);
      link.href = '#ev-' + eventId;
      link.dataset.evidenceRef = ref;
      link.setAttribute('aria-label','Inspect source evidence ' + ref);
      tags.append(link);
    }
    return tags;
  }
  function facts(event) {
    const item=el('article','timeline-item');item.id='ev-'+event.event_id;
    const head=el('div','timeline-head');head.append(el('strong','',event.event_id),el('time','',event.timestamp.replace('T',' ').replace('Z',' UTC')));
    item.append(head);
    const chips=el('div','chips');
    for (const [label,val] of [['Verification',event.verification_result],['Liveness',event.liveness_result],['Replay',event.replay_flag===true?'flagged':event.replay_flag===false?'not flagged':'unavailable']]) {
      const wrap=el('span','chip',label+' ');
      wrap.append(pill(val,val==='passed'?'pass':val==='failed'?'fail':(val==='flagged'?'warn':'warn')));chips.append(wrap);
    }
    item.append(chips);
    const details=el('details');details.className='source-evidence-details';
    details.append(el('summary','','▸ Inspect source evidence references'));
    const identifiers=Object.keys(event.available_identifiers || {}).map(k=>event.event_id+'.available_identifiers.'+k);
    details.append(evidenceTags([...event.source_evidence_refs,...identifiers]));
    details.append(el('p','source-note','References identify validated input fields, not proof that the related AI interpretation is true. Opaque identifier values are deliberately not displayed.'));
    item.append(details);
    return item;
  }
  function navigateEvidence(ref) {
    const id=String(ref).split('.')[0];
    const item=document.getElementById('ev-'+id);
    if(!item) return;
    for (const row of document.querySelectorAll('.timeline-item.source-highlight')) row.classList.remove('source-highlight');
    const details=item.querySelector('details.source-evidence-details');
    if(details) details.open=true;
    item.classList.add('source-highlight');
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    item.scrollIntoView({behavior:reduced?'auto':'smooth', block:'center'});
    item.setAttribute('tabindex','-1');
    item.focus({preventScroll:true});
  }
  function reviewCard(item,index) {
    const card=el('article','queue-card');
    const top=el('div','queue-top');top.append(el('span','queue-number',String(index+1).padStart(2,'0')),
      el('span','priority'+(item.review_priority>=5?' low':''),'PRIORITY '+item.review_priority));card.append(top);
    card.append(el('h3','',item.title),el('p','',item.rationale));
    const line=el('div','event-links','Relevant events: ');
    for(const id of item.event_ids){const a=el('a','',id);a.href='#ev-'+id;line.append(a,document.createTextNode('  '));}card.append(line);
    const d=el('details');d.append(el('summary','','▸ Evidence and recommended collection'),evidenceTags(item.evidence_refs));
    const ul=el('ul');for(const x of item.evidence_to_collect)ul.append(el('li','',x));d.append(ul);card.append(d);
    card.append(el('div','safe','✓ '+item.safe_action));return card;
  }
  function advisoryRecord(body,refs,detail) {
    const card=el('article','ai-record');card.append(el('p','',body));
    if(detail)card.append(el('small','',detail));
    if(refs && refs.length)card.append(evidenceTags(refs));return card;
  }
  function renderAdvisory(response) {
    const advisory=response.advisory_display;
    const chip=get('ai-chip');const container=get('advisory-view');const empty=get('advisory-empty');
    chip.className='tag tag-neutral';
    if(!advisory){chip.textContent='NOT REQUESTED';container.hidden=true;empty.hidden=false;return;}
    container.hidden=false;empty.hidden=true;
    const preview=response.advisory_origin==='illustrative_fixture';
    chip.className='tag '+(preview?'tag-preview':'tag-meta');
    chip.textContent=preview?'ILLUSTRATIVE · NOT META':'LIVE META · VALIDATED';
    const banner=get('ai-banner');banner.className='advisory-banner'+(preview?' preview':'');
    banner.textContent=preview?'ILLUSTRATIVE WORKFLOW PREVIEW. Hand-authored sample text, NOT output from Meta AI.':
      'LIVE META API RESPONSE. Structural and reference validation passed; no conclusion is automatically approved.';
    text('ai-summary',advisory.case_summary);
    const pattern=get('ai-patterns');clear(pattern);
    for(const row of advisory.observed_patterns||[])pattern.append(advisoryRecord(row.pattern,row.evidence_refs));
    const rel=get('ai-relationships');clear(rel);
    for(const row of advisory.relationship_assessments||[])rel.append(advisoryRecord(row.basis,row.evidence_refs,'Linkage status: '+row.relationship_status+' · '+row.caveat));
    const hypotheses=get('ai-hypotheses');clear(hypotheses);
    for(const row of advisory.hypotheses||[]){const card=advisoryRecord(row.hypothesis,row.evidence_refs);
      card.prepend(el('div','confidence',row.confidence+' confidence · advisory only'));
      card.append(el('small','',row.contrary_or_missing_evidence));hypotheses.append(card);}
    const guide=get('privacy-steps');clear(guide);
    for(const step of response.privacy_review_steps || []) guide.append(advisoryRecord(step,null,'LOCAL REVIEW POLICY · NOT MODEL GENERATED'));
    const next=get('ai-nextsteps');clear(next);
    for(const issue of (advisory.missing_evidence||[]).slice(0,8))next.append(advisoryRecord(issue,null,'Missing supporting evidence'));
    for(const action of (advisory.recommended_next_steps||[]).slice(0,8))next.append(advisoryRecord(action,null,'Human review step'));
  }
  // Bring validated AI analysis into view only after a user has requested it.
  // Focus aids keyboard/screen-reader users without moving the viewport twice.
  function navigateToAdvisory() {
    const panel=get('ai-investigation-panel');
    if (!panel || get('advisory-view').hidden) return;
    window.requestAnimationFrame(() => {
      panel.focus({preventScroll:true});
      const reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      panel.scrollIntoView({behavior:reducedMotion?'auto':'smooth',block:'start'});
    });
  }
  function resetDisplay(){
    currentResult=null;
    for(const id of ['stat-events','stat-pass','stat-fail','stat-replay','stat-links'])text(id,'—');
    for(const id of ['timeline-list','queue-list','ai-patterns','ai-relationships','ai-hypotheses','ai-nextsteps'])clear(get(id));
    text('case-label','CASE · UNVALIDATED INPUT');text('mode-label','AWAITING VALIDATION');
    text('policy-label','POLICY · —');text('dossier-hash','—');text('input-hash','—');
    text('executive-summary','Awaiting validated source data.');clear(get('privacy-steps'));
    text('audit-generated','Awaiting investigation');text('audit-mode','No validated dossier');
    renderAdvisory({advisory_display:null});
    get('export-dossier').disabled=true;get('export-audit').disabled=true;
    get('export-report').disabled=true;get('print-report').disabled=true;
  }
  function render(response) {
    currentResult=response;
    const d=response.dossier,a=response.audit;
    text('executive-summary',response.executive_summary);
    text('case-label','CASE · '+d.case_id);text('mode-label',response.mode_label);text('policy-label','POLICY · '+d.policy_version);
    const ev=d.event_facts;
    text('stat-events',ev.length);text('stat-pass',ev.filter(x=>x.verification_result==='passed').length);
    text('stat-fail',ev.filter(x=>x.verification_result==='failed').length);
    text('stat-replay',ev.filter(x=>x.replay_flag===true).length);
    text('stat-links',d.shared_identifiers.length);
    const timeline=get('timeline-list');clear(timeline);
    for(const x of ev)timeline.append(facts(x));
    const queue=get('queue-list');clear(queue);
    d.investigation_queue.forEach((item,index)=>queue.append(reviewCard(item,index)));
    renderAdvisory(response);
    text('dossier-hash',a.dossier_canonical_sha256);text('input-hash',a.input_canonical_sha256);
    text('audit-generated','Generated: '+a.generated_at_utc);text('audit-mode','Review-only · '+(response.live_meta_call_made?'Meta API validated':'No live API request'));
    get('export-dossier').disabled=false;get('export-audit').disabled=false;
    get('export-report').disabled=false;get('print-report').disabled=false;
    notice(response.advisory_origin==='meta_api'?'Meta response received and validated. Human review required.':
          response.advisory_origin==='illustrative_fixture'?'Illustrative preview loaded. Not a real Meta result.':
          'Offline case validated. No Meta credits used.');
  }
  async function execute(mode){
    if(busy || !currentCase)return;
    if(mode==='meta' && !confirm('Send the selected SYNTHETIC JSON case to the Meta API? This uses your API credits. No real customer or biometric data is allowed.'))return;
    changeBusy(true);showError('');
    notice(mode==='meta'?'Contacting Meta API. This can take a little while…':'Running local validation…');
    try{const payload=currentRaw!==null?{case_text:currentRaw,mode}:{case:currentCase,mode};
      const response=await request('/api/investigate','POST',payload);render(response);
      if (mode==='preview' || mode==='meta') navigateToAdvisory();}
    catch(err){showError(err.message||String(err));notice('Validation failed. No new dossier published.');}
    finally{changeBusy(false);}
  }
  async function loadSample(){
    if(busy)return;changeBusy(true);showError('');
    try {const data=await request('/api/sample');currentCase=data.case;currentRaw=null;currentScenario='unlinked-sequence';resetDisplay();ui.source.textContent='Built-in fictional case · '+currentCase.events.length+' events';updateSelectedScenario();}
    catch(err){showError(err.message);notice('Unable to load sample.');changeBusy(false);return;}
    changeBusy(false);await execute('offline');
  }
  async function loadFile(){
    if(busy)return;const file=ui.file.files?.[0];if(!file)return;
    if(file.size>270000){showError('Case JSON is too large (256 KB case limit).');return;}
    try {const raw=await file.text();const obj=JSON.parse(raw);if(typeof obj!=='object'||Array.isArray(obj)||obj===null)throw new Error('Case must be a JSON object.');
      currentCase=obj;currentRaw=raw;currentScenario='uploaded';resetDisplay();updateSelectedScenario();ui.source.textContent='Selected local JSON · '+file.name;showError('');await execute('offline');}
    catch(err){showError('Cannot load case JSON: '+err.message);notice('Case not loaded.');}
    finally{ui.file.value='';}
  }
  function updateSelectedScenario(){
    for(const btn of document.querySelectorAll('[data-load-scenario]')){
      const active=btn.dataset.loadScenario===currentScenario;
      btn.setAttribute('aria-pressed',String(active));
      btn.classList.toggle('scenario-selected',active);
    }
    ui.preview.disabled=busy || currentScenario!=='unlinked-sequence';
    ui.preview.title=currentScenario==='unlinked-sequence' ? '' : 'Illustrative preview is specifically authored for the original unlinked example. Use offline or live Meta for this case.';
  }
  async function showGallery(){
    const res=await request('/api/showcase');const gallery=get('scenario-cards');clear(gallery);
    for(const c of res.scenarios){
      const button=el('button','scenario-card');button.type='button';button.dataset.loadScenario=c.id;
      button.setAttribute('aria-pressed','false');button.setAttribute('aria-label','Load '+c.name);
      button.append(el('span','scenario-name',c.name),el('strong','scenario-headline',c.headline),
                    el('span','scenario-description',c.lesson));
      const metrics=el('span','scenario-metrics',c.events+' events  ·  '+c.replay_flags+' replay flags  ·  '+c.shared_signals+' shared tokens');
      button.append(metrics);gallery.append(button);
    }
    updateSelectedScenario();
  }
  async function loadScenario(slug){
    if(busy)return;changeBusy(true);showError('');
    try{
      const result=await request('/api/showcase/'+encodeURIComponent(slug));
      currentCase=result.case;currentRaw=null;currentScenario=slug;resetDisplay();
      ui.source.textContent='Scenario gallery · '+slug+' · '+currentCase.events.length+' invented events';
      updateSelectedScenario();
    }catch(error){showError(error.message||String(error));notice('Scenario selection failed.');changeBusy(false);return;}
    changeBusy(false);updateSelectedScenario();await execute('offline');
    const results=document.querySelector('.stats');if(results)results.scrollIntoView({behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
  }
  function renderCheckList(host,checks){
    clear(host);
    const ul=el('ul','assurance-list');
    for(const check of checks){
      const item=el('li',check.passed?'check-pass':'check-fail', (check.passed?'✓  ':'✗  ')+check.name);
      ul.append(item);
    }host.append(ul);
  }
  async function runAssurance(){
    const btn=get('run-assurance');if(btn.disabled)return;
    btn.disabled=true;text('assurance-status','Running fixed offline safeguard checks…');
    try{
      const result=await request('/api/assurance');
      text('assurance-status',result.passed+'/'+result.total+' safeguards '+(result.status==='pass'?'passed':'require investigation')+' · zero Meta API calls');
      renderCheckList(get('assurance-checks'),result.checks);
    }catch(error){text('assurance-status','Could not complete checks: '+(error.message||String(error)));}
    finally{btn.disabled=false;}
  }
  async function verifyExports(){
    const dossierFile=get('verify-dossier').files?.[0],auditFile=get('verify-audit').files?.[0];
    if(!dossierFile || !auditFile){text('verification-status','Choose both the dossier and audit JSON files.');return;}
    if(dossierFile.size>260000 || auditFile.size>150000){text('verification-status','Files exceed the local verification limits.');return;}
    const btn=get('verify-pair');btn.disabled=true;
    text('verification-status','Checking canonical JSON and audit metadata…');
    try{
      const dossier_text=await dossierFile.text();const audit_text=await auditFile.text();
      const result=await request('/api/verify','POST',{dossier_text,audit_text});
      text('verification-status',(result.status==='consistent'?'CONSISTENT PAIR':'MISMATCH DETECTED')+' · '+result.passed+'/'+result.total+' checks passed');
      renderCheckList(get('verification-checks'),result.checks);
    }catch(error){text('verification-status','Verification failed: '+(error.message||String(error)));clear(get('verification-checks'));}
    finally{btn.disabled=false;}
  }
  async function init(){
    ui.sample.addEventListener('click',loadSample);ui.offline.addEventListener('click',()=>execute('offline'));
    ui.preview.addEventListener('click',()=>execute('preview'));ui.meta.addEventListener('click',()=>execute('meta'));
    ui.file.addEventListener('change',loadFile);
    get('run-assurance').addEventListener('click',runAssurance);
    get('verify-pair').addEventListener('click',verifyExports);
    document.addEventListener('click',(event)=>{const b=event.target.closest('[data-load-scenario]');if(b)loadScenario(b.dataset.loadScenario);});
    get('export-dossier').addEventListener('click',()=>download('dossier'));
    get('export-audit').addEventListener('click',()=>download('audit'));
    get('export-report').addEventListener('click',()=>download('report'));
    get('print-report').addEventListener('click',printReport);
    document.addEventListener('click',(event)=>{
      const clicked=event.target.closest('[data-evidence-ref]');
      if(!clicked)return;
      event.preventDefault();
      navigateEvidence(clicked.dataset.evidenceRef);
    });
    try{const data=await request('/api/status');metaAvailable=data.meta_enabled;
      ui.connection.textContent=metaAvailable?'● META API MODE ENABLED':'● META API MODE DISABLED';
      ui.connection.className='tag '+(metaAvailable?'tag-meta':'tag-neutral');
      ui.meta.disabled=!metaAvailable;await showGallery();await loadSample();}
    catch(err){showError(err.message);notice('Could not connect to the local workbench.');}
  }
  init();
})();


// v1.4.2 typography control: presentation-friendly default and optional XL mode.
// Deliberately independent of case data, API mode, and investigation logic.
(() => {
  const control = document.getElementById('type-size-btn');
  if (!control) return;
  control.addEventListener('click', () => {
    const enabled = document.body.classList.toggle('type-extra-large');
    control.setAttribute('aria-pressed', String(enabled));
    control.textContent = enabled ? 'A− Normal text' : 'A+ Extra large text';
    control.setAttribute('aria-label', enabled ? 'Use standard enlarged dashboard text' : 'Use extra large dashboard text');
  });
})();
