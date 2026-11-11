const $ = (id) => document.getElementById(id);
let dataset = [], shown = [], active = null;
let agencyFilter = '';
const names = {law:'법령',admrul:'행정규칙',ordin:'자치법규'};
const stage = {
  changed:'신구 변경 확인',no_text_change:'본문 변경 없음',
  partial_unverified:'일부 원문 확인 필요',
  original_saved_comparison_pending:'신구 대조 대기'
};
function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = String(text);
  return el;
}
function add(parent,...children){children.forEach(child=>parent.appendChild(child));return parent;}
function external(text,url){
  if (!url || !url.startsWith('https://')) return node('span','secondary','공식 원문 링크 확인 필요');
  const a=node('a','source-link',text);a.href=url;a.target='_blank';a.rel='noopener noreferrer';return a;
}
function chip(text,css=''){return node('span','chip '+css,text);}
function stat(label,value){const el=node('div','stat');add(el,node('b','',value),node('span','',label));return el;}
function renderSummary(raw){
  $('summary').replaceChildren(
    stat('확보된 공식 판본',raw.total_source_versions_saved.toLocaleString()+'건'),
    stat('확인된 신구 변경',raw.summary.with_verified_changes.toLocaleString()+'건'),
    stat('기관·사업 연결',raw.summary.agency_action_count.toLocaleString()+'건')
  );
}
function filtered(){
  const q=$('search').value.trim().toLowerCase(), cat=$('category').value, src=$('source').value;
  shown=dataset.filter(e=>(!q||[e.title,e.ministry,...(e.institutions||[]).map(x=>x.agency+' '+x.service)].join(' ').toLowerCase().includes(q))
    &&(!cat||e.category===cat)&&(!src||e.source===src)&&(!$('verified').checked||e.changes?.length));
  $('count').textContent=shown.length.toLocaleString()+'건';
  renderList();
  if(!active||!shown.some(e=>e.id===active.id))active=shown[0]||null;
  renderDetail();
}
function renderList(){
  const list=$('events');list.replaceChildren();
  if(!shown.length){add(list,node('div','empty','해당 조건에 맞는 공식 자료가 없습니다.'));return;}
  shown.forEach(e=>{
    const b=node('button','event'+(e.id===active?.id?' active':''));b.type='button';
    add(b,chip(e.category),e.changes?.length?chip('실질 변경 '+e.changes.length,'blue'):chip('대조 중','orange'));
    add(b,node('h3','',e.title),node('div','meta',(e.published_at||'발령일 미확인')+' · '+(e.ministry||names[e.source])));
    b.addEventListener('click',()=>{active=e;agencyFilter='';renderList();renderDetail();});
    list.appendChild(b);
  });
}
function diffFragments(a,b){
  // Highlight changed text without interpreting any source HTML.
  a=String(a||'');b=String(b||'');
  let prefix=0;while(prefix<Math.min(a.length,b.length)&&a[prefix]===b[prefix])prefix++;
  let suffix=0;while(suffix<Math.min(a.length,b.length)-prefix&&a[a.length-1-suffix]===b[b.length-1-suffix])suffix++;
  const left=node('div','text'),right=node('div','text');
  const mark=(parent,part)=>{if(part)parent.appendChild(node('mark','',part));};
  add(left,document.createTextNode(a.slice(0,prefix)));mark(left,a.slice(prefix,a.length-suffix));left.appendChild(document.createTextNode(suffix?a.slice(a.length-suffix):''));
  add(right,document.createTextNode(b.slice(0,prefix)));mark(right,b.slice(prefix,b.length-suffix));right.appendChild(document.createTextNode(suffix?b.slice(b.length-suffix):''));
  return [left,right];
}
function changeCard(c){
  const wrapper=node('div',''),heading=node('h3','',c.article||'개정 조문');
  const grid=node('div','two'),before=node('div','comparison'),after=node('div','comparison after');
  const [oldText,newText]=diffFragments(c.before,c.after);
  add(before,node('div','head','개정 전'),oldText);
  add(after,node('div','head','개정 후'),newText);
  add(grid,before,after);add(wrapper,heading,grid);
  return wrapper;
}
function renderDetail(){
  const root=$('detail');root.replaceChildren();
  if(!active){add(root,node('div','empty','검색 조건에 맞는 정책이 없습니다.'));return;}
  const e=active;
  add(root,chip(e.category,'blue'),node('h2','',e.title));
  add(root,node('div','sub',[e.ministry,e.published_at&&('발령 '+e.published_at),e.effective_date&&('시행 '+e.effective_date)].filter(Boolean).join(' · ')));
  add(root,external('국가법령정보센터 공식 문서 보기',e.url));
  const overview=node('section','section');
  add(overview,node('h3','','정책 변경 핵심'));
  const note=e.changes?.length
    ? '공식 종전·개정 판본에서 '+e.changes.length+'개 항목의 문구 차이를 확인했습니다.'
    : e.comparison_status==='no_text_change'
      ? '확보한 판본의 조문 텍스트에서는 변경을 확인하지 못했습니다.'
      : '공식 문서 판본은 확보됐지만 종전·개정 원문 대조가 완료되지 않았습니다.';
  add(overview,node('p','lead',note));
  add(overview,node('div','secondary','검증 상태 · '+(stage[e.comparison_status]||e.comparison_status)));
  root.appendChild(overview);
  const agency=node('section','section');
  const actions=e.institutions||[];
  const head=node('div','section-head');
  add(head,node('h3','','영향받는 공공기관·사업'),chip(actions.length+'건','blue'));agency.appendChild(head);
  if(!actions.length){
    add(agency,node('p','warning','변경 조문과 공공기관 사업의 실제 운영 근거를 직접 연결한 검증 결과가 아직 없습니다. 기관명이나 사업명을 추정하여 표시하지 않습니다.'));
  }else{
    const unique=[...new Set(actions.map(x=>x.agency))].sort();
    const filters=node('div','agency-filters');
    ['',...unique].forEach(name=>{
      const b=node('button',agencyFilter===name?'active':'',name||'전체 기관');
      b.addEventListener('click',()=>{agencyFilter=name;renderDetail();});
      filters.appendChild(b);
    });
    agency.appendChild(filters);
    actions.filter(x=>!agencyFilter||x.agency===agencyFilter).forEach(x=>{
      const item=node('article','agency-item');
      add(item,node('strong','',x.agency),node('div','secondary','공공서비스 · '+x.service));
      add(item,node('p','',x.required_change));
      add(item,node('div','proof','공식 근거: '+x.evidence.reference_quote+'\n사업 적용 항목: '+x.evidence.service_field));
      const more=node('details','');
      add(more,node('summary','','운영기준 원문 확인'),node('p','proof',x.evidence.service_quote));
      add(item,more,external('사업 근거 자료',x.service_url));
      agency.appendChild(item);
    });
  }
  root.appendChild(agency);
  const compare=node('section','section');
  const title=node('div','section-head');
  add(title,node('h3','','실제 변경사항 · 신구 비교'),chip((e.changes||[]).length+'개','blue'));
  compare.appendChild(title);
  if(e.changes?.length){
    const details=node('details','');
    details.open=false;
    add(details,node('summary','','개정 전·후 조문 펼치기'));
    e.changes.forEach(c=>details.appendChild(changeCard(c)));
    compare.appendChild(details);
  } else add(compare,node('div','warning','비교할 수 있는 종전·개정 본문을 더 확보해야 합니다.'));
  if(e.unresolved?.length){
    add(compare,node('p','secondary','별표·첨부 또는 대응본 미확보: '+e.unresolved.length+'개 항목. 미확인 사항은 변경이라고 단정하지 않습니다.'));
  }
  if(e.prior_url)compare.appendChild(external('종전 공식 판본 보기',e.prior_url));
  root.appendChild(compare);
}
async function main(){
  try{
    const response=await fetch('data.json',{cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const data=await response.json();
    if(data.schema!=='policy-domino-unified-ui-v1')throw new Error('데이터 규격 불일치');
    dataset=data.events||[];
    renderSummary(data);active=dataset[0]||null;
    for(const id of ['search','category','source','verified'])$(id).addEventListener(id==='search'?'input':'change',filtered);
    filtered();
  }catch(e){
    $('summary').replaceChildren(node('span','secondary','공식 자료를 읽지 못했습니다.'));
    $('detail').replaceChildren(node('div','warning','데이터 로딩 실패: '+e.message));
  }
}
main();