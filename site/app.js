"use strict";
(function(){
  const $ = id=>document.getElementById(id);
  const state={data:null,events:[],mode:"all",query:"",area:"",source:"",
               selected:null,detail:null,displayLimit:60,agency:"",
               agencyQuery:"",request:0};
  const fmt=n=>Number(n||0).toLocaleString("ko-KR");
  const text=s=>String(s??"");
  const date=s=>text(s).replaceAll("-",". ")||"미확인";
  const el=(tag,cl="",val)=>{const n=document.createElement(tag);if(cl)n.className=cl;
    if(val!==undefined)n.textContent=text(val);return n;};
  const add=(node,...children)=>{for(const child of children)if(child)node.appendChild(child);return node;};
  function anchor(label,url){
    try{const u=new URL(url);if(u.protocol!=="https:")throw Error("Unsafe protocol");
      const a=el("a","",label);a.href=u.href;a.target="_blank";a.rel="noopener noreferrer";return a;}
    catch{return el("span","quiet","공식 링크 확인 필요");}
  }
  function pill(label,type=""){return el("span","pill "+type,label);}
  function section(title,desc){
    const x=el("section","section");x.appendChild(el("h3","",title));
    if(desc)x.appendChild(el("p","section-desc",desc));
    return x;
  }
  function empty(message){return el("p","empty",message);}
  const statuses={
    official_comparison_verified:"공식 신구 검증",
    historical_comparison_needs_revalidation:"과거 추출본 재검증",
    comparison_incomplete:"원문·대조 확인 중",
  };
  const sourceLabels={law:"법령",admrul:"행정규칙",ordin:"자치법규"};
  const kindLabels={new:"신규",amended:"개정",repealed:"폐지",unclassified:"구분 확인 중"};
  function refreshSummary(){
    const data=state.data||{},summary=data.summary||{},quality=data.quality||{};
    const nums=[
      ["표시된 공식 문서 판본",fmt(summary.displayed_events)],
      ["공식 신구 검증 변경",fmt(summary.with_verified_changes)],
      ["공공기관별 근거 조치",fmt(summary.agency_action_count)]];
    $("metrics").replaceChildren(...nums.map(([title,value])=>add(el("div","metric"),
      el("strong","",value),el("span","",title))));
    $("health-title").textContent="자료 수집·검증 상태 · 실패 구간 "+
      fmt(quality.failed_collection_windows)+"건 · 재검증 대상 포함";
    $("health-body").replaceChildren(
      el("p","", "최근 수집일: "+(quality.last_collection_date||"미확인")+
        " · 최근 새 공식 원문: "+fmt(quality.latest_collection?.complete_originals_added)+
        "건 · 보유 판본: "+fmt(data.total_source_versions_saved)+"건"),
      el("p","", "과거 색인 판본: "+fmt(quality.historic_index_versions)+
        "건 · 자료와 실제 분석 완료 건수는 서로 다릅니다. 수집 실패·본문 미확보는 정책 변경 없음으로 처리하지 않습니다.")
    );
  }
  function filters(){
    for(const node of document.querySelectorAll("[data-mode]")){
      const on=node.dataset.mode===state.mode;node.classList.toggle("active",on);
      node.setAttribute("aria-pressed",String(on));
    }
  }
  function filtered(){
    const needle=state.query.toLocaleLowerCase("ko-KR");
    return state.events.filter(v=>{
      if(state.mode==="impact"&&!v.action_count)return false;
      if(!["all","impact"].includes(state.mode)&&v.change_type!==state.mode)return false;
      if(state.area&&v.category!==state.area)return false;
      if(state.source&&v.source!==state.source)return false;
      if(needle&&![v.title,v.ministry,v.category,v.kind,v.revision]
        .join(" ").toLocaleLowerCase("ko-KR").includes(needle))return false;
      return true;
    });
  }
  function row(e){
    const node=el("button","policy"+(e.id===state.selected?" selected":""));
    node.type="button";node.setAttribute("aria-current",String(e.id===state.selected));
    add(node,
      add(el("div","policy-meta"),pill(kindLabels[e.change_type]||"확인 중"),
        el("span","",date(e.published_at)),
        el("span","",e.kind||sourceLabels[e.source]||"공식 자료")),
      el("div","policy-title",e.title),
      el("div","policy-ministry",e.ministry||"소관기관 확인 중"),
      add(el("div","policy-foot"),
        pill(e.category||"분야 미확정"),
        e.verification==="official_comparison_verified"?pill("원문 검증","verified"):
          pill("검증 진행 중","uncertain"),
        e.action_count?pill("기관별 조치 "+fmt(e.action_count),"blue"):
        e.change_count?pill("신구 대조 "+fmt(e.change_count)):null));
    node.onclick=()=>select(e.id);
    return node;
  }
  function renderList(){
    filters();
    const result=filtered();$("list-count").textContent=
      "전체 "+fmt(state.events.length)+"건 · 조건에 맞는 자료 "+fmt(result.length)+"건";
    const items=$("items");
    items.replaceChildren(...(result.length?result.slice(0,state.displayLimit).map(row):
      [empty("조건에 맞는 자료가 없습니다. 분석 대기 자료도 '전체'에서 확인할 수 있습니다.")]));
    $("more").hidden=result.length<=state.displayLimit;
    $("more").textContent="목록 더 보기 · "+fmt(result.length-state.displayLimit)+"건 남음";
  }
  function back(){ $("workspace").classList.remove("detail-open");}
  async function select(id,push=true){
    state.selected=id;state.detail=null;state.agency="";state.agencyQuery="";
    const current=state.events.find(v=>v.id===id);
    if(!current)return;
    if(push){try{history.replaceState(null,"","#event="+encodeURIComponent(id));}catch{}}
    $("workspace").classList.add("detail-open");
    renderList();
    $("detail").replaceChildren(empty("공식 변경 내용과 기관 연결 근거를 불러오는 중입니다."));
    const seq=++state.request;
    try{
      const resp=await fetch("./"+current.details_path,{cache:"no-store"});
      if(!resp.ok)throw Error("HTTP "+resp.status);
      const detail=await resp.json();
      if(seq!==state.request||detail.id!==state.selected)return;
      state.detail=detail;renderDetail();
    }catch(error){
      if(seq!==state.request)return;
      $("detail").replaceChildren(empty("상세 자료를 열지 못했습니다. 자료 갱신 상태와 네트워크를 확인해 주세요."));
    }
  }
  function overview(event){
    const box=el("section","overview");
    const change=event.changes?.find(c=>c.before!==c.after);
    const message=event.headline||
      (change ? change.article+"의 실제 신구 원문 비교" :
      "공식 문서는 확보했으나 변경된 핵심 조항과 적용 기준의 대조가 아직 완료되지 않았습니다.");
    add(box,el("div","headline",message),el("small","",
      "시행일 "+date(event.effective_date)+" · "+
      (statuses[event.verification]||"확인 중")));
    return box;
  }
  function evidencePair(before,after,oldLabel="변경 전",newLabel="변경 후"){
    const wrap=el("div","compare-grid");
    const old=el("div","before"),now=el("div","after");
    add(old,el("small","",oldLabel),el("div","",text(before).slice(0,340)||"본문 미확보"));
    add(now,el("small","",newLabel),el("div","",text(after).slice(0,340)||"본문 미확보"));
    return add(wrap,old,now);
  }
  function changesSection(event){
    const block=section("실제 변경사항 · 신구 비교",
      "검증 상태에 따라 공식 변경 확정과 원문 재검증 대상을 구분합니다.");
    const changes=event.changes||[];
    if(!changes.length){block.appendChild(el("p","note",
      "신구 변경 본문이 아직 확인되지 않았습니다. 원천 색인만으로 변경 내용이나 기관별 조치를 추정하지 않습니다."));return block;}
    const list=el("div");
    changes.slice(0,3).forEach((c,i)=>list.appendChild(changeCard(c,event.verification)));
    if(changes.length>3){
      const more=el("details","subdetails");
      more.appendChild(el("summary","", "나머지 변경 조항 "+fmt(changes.length-3)+"건 펼쳐보기"));
      changes.slice(3).forEach(c=>more.appendChild(changeCard(c,event.verification)));
      list.appendChild(more);
    }
    block.appendChild(list);return block;
  }
  function changeCard(change,grade){
    const card=el("article","difference");
    add(card,add(el("div","action-head"),el("strong","",change.article||"변경 조문"),
      pill(grade==="official_comparison_verified"?"원문 검증":"재검증 필요",
        grade==="official_comparison_verified"?"verified":"uncertain")),
      evidencePair(change.focus?.before||change.before,
                   change.focus?.after||change.after));
    if((change.before||"").length>340||(change.after||"").length>340){
      const more=el("details","subdetails");
      add(more,el("summary","","해당 조문 원문 펼쳐보기"),
        el("div","source-raw","변경 전\n"+text(change.before)+"\n\n변경 후\n"+text(change.after)));
      card.appendChild(more);
    }
    return card;
  }
  function agencyType(a){
    const raw=text(a.agency_type).trim();
    if(/중앙행정/.test(raw))return "중앙행정기관";
    if(/지방자치/.test(raw))return "지방자치단체";
    if(/교육청/.test(raw))return "교육청";
    if(/공공기관/.test(raw))return "공공기관";
    return "기관 유형 미확인";
  }
  function agencyEntries(actions){
    const m=new Map();
    actions.forEach(a=>{
      const key=text(a.agency).trim();if(!key)return;
      if(!m.has(key))m.set(key,{name:key,type:agencyType(a),actions:[]});
      m.get(key).actions.push(a);
    });
    return [...m.values()].sort((a,b)=>a.name.localeCompare(b.name,"ko"));
  }
  function actionCard(a){
    const box=el("article","action");
    const confirmed=a.status==="review_of_verified_citation";
    add(box,add(el("div","action-head"),el("strong","",a.service||"사업명 확인 중"),
      pill(confirmed?"공식 변경 조문 연결":"영향 검증 중",confirmed?"verified":"uncertain")));
    add(box,el("div","action-label","변경해야 할 업무·기준"),
      el("p","",confirmed?(a.required_change||"변경 조문 적용기준 확인"):
        "관련 사업 후보입니다. 실제 업무 변경 필요성은 공식 근거 대조가 필요합니다."));
    if(a.before||a.after)box.appendChild(evidencePair(a.before,a.after,"상위 정책 변경 전","상위 정책 변경 후"));
    const more=el("details","subdetails");more.appendChild(el("summary","","사업 적용관계 및 공식 근거 펼쳐보기"));
    if(a.changed_clause)more.appendChild(el("p","evidence","관련 변경 조문: "+a.changed_clause));
    if(a.evidence?.reference_quote)more.appendChild(el("p","evidence","인용 근거: "+a.evidence.reference_quote));
    if(a.evidence?.service_quote)more.appendChild(el("p","evidence","사업 운영기준: "+a.evidence.service_quote));
    if(a.service_url)more.appendChild(anchor("공공사업 공식 자료 ↗",a.service_url));
    if(a.policy_url)more.appendChild(add(el("div","evidence"),anchor("변경 법령 공식 원문 ↗",a.policy_url)));
    box.appendChild(more);return box;
  }
  function agencySection(event){
    const actions=(event.institutions||[]).filter(x=>x&&x.agency);
    const wrap=section("영향받는 공공기관·사업과 후속조치",
      "공식적으로 확인된 기관명·사업명·기준을 사용합니다. 기관의 실제 조치 완료 여부는 표시하지 않습니다.");
    const entries=agencyEntries(actions);
    if(!entries.length){
      wrap.appendChild(el("p","note",
        "현재 이 정책과 실제 공공사업의 검증된 연결이 없습니다. 이는 영향받는 기관이 없다는 뜻이 아니라, 공식 근거 연결이 완료되지 않았다는 뜻입니다."));
      return wrap;
    }
    const frame=el("div","agency-workspace"),aside=el("aside","agency-sidebar"),result=el("div");
    aside.appendChild(el("strong","","기관명 필터"));
    const search=el("input");search.type="search";search.placeholder="기관명 검색";search.value=state.agencyQuery;
    aside.appendChild(search);
    const menu=el("div","agency-list");aside.appendChild(menu);
    function choose(name){state.agency=name;draw();} function draw(){
      menu.replaceChildren();
      const all=el("button",state.agency?"":"selected","전체 기관 · "+fmt(entries.length)+"곳");
      all.onclick=()=>choose("");menu.appendChild(all);
      const q=state.agencyQuery.toLocaleLowerCase("ko-KR");
      const types=["중앙행정기관","지방자치단체","교육청","공공기관","기관 유형 미확인"];
      for(const type of types){
        const group=entries.filter(a=>a.type===type&&a.name.toLocaleLowerCase("ko-KR").includes(q));
        if(!group.length)continue;
        const d=el("details","agency-group");d.open=true;
        d.appendChild(el("summary","",type+" · "+fmt(group.length)+"곳"));
        group.forEach(item=>{
          const b=el("button","agency-row"+(state.agency===item.name?" selected":""),
                     item.name+" · "+item.actions.length+"건");
          b.onclick=()=>choose(item.name);d.appendChild(b);
        });menu.appendChild(d);
      }
      const showing=state.agency?entries.filter(x=>x.name===state.agency):entries;
      result.replaceChildren();
      result.appendChild(el("p","section-desc",fmt(showing.length)+"개 기관 · "+
        fmt(showing.reduce((n,x)=>n+x.actions.length,0))+"개 사업별 연결"));
      showing.forEach(entry=>{
        const heading=el("h4","",entry.name);heading.style.margin="12px 0";
        result.appendChild(heading);
        entry.actions.forEach(a=>result.appendChild(actionCard(a)));
      });
    }
    search.oninput=()=>{state.agencyQuery=search.value;draw();};
    draw();frame.appendChild(aside);frame.appendChild(result);wrap.appendChild(frame);return wrap;
  }
  function citations(event){
    const wrap=section("관련 규정·공식 근거",
      "변경 조문의 출처와 종전 판본을 확인합니다. 법령명만 같은 자료는 기관 영향 근거로 인정하지 않습니다.");
    const links=el("div","related");
    for(const d of event.source_documents||[]){
      if(!d.title)continue;
      const item=el("div","related-item");
      add(item,el("strong","",d.title+" · "+(d.verification==="official_original_verified"?
        "공식 원문 확인":"원문 검증 대기")),el("div","evidence"));
      if(d.url)item.appendChild(anchor("공식 자료 보기 ↗",d.url));
      links.appendChild(item);
    }
    for(const relation of event.related_regulations||[]){
      const item=el("div","related-item");
      add(item,el("strong","",relation.title||relation.referencing_title||"관련 규정"),
        el("p","evidence",relation.reference_quote||relation.excerpt||"관계 근거 확인 중"));
      if(relation.url)item.appendChild(anchor("관련 규정 ↗",relation.url));
      links.appendChild(item);
    }
    if(!links.children.length)links.appendChild(el("p","quiet","현재 공개된 관련 근거가 없습니다."));
    wrap.appendChild(links);
    if(event.unresolved?.length){
      const missing=el("details","subdetails");
      missing.appendChild(el("summary","","미확인 원문·별표 "+fmt(event.unresolved.length)+"건"));
      missing.appendChild(el("p","quiet",
        "첨부·원문 또는 전후 대응본이 확인되지 않아 변경 내용으로 확정하지 않았습니다."));
      event.unresolved.slice(0,20).forEach(x=>missing.appendChild(
        el("p","evidence",(x.clause||"첨부") + " · "+(x.reason||"재확인 필요"))));
      wrap.appendChild(missing);
    }
    return wrap;
  }
  function renderDetail(){
    const e=state.detail;if(!e)return;
    const root=$("detail");root.replaceChildren();
    add(root,el("div","detail-top",
        (e.kind||sourceLabels[e.source]||"공식 정책")+" · "+(e.ministry||"소관기관 확인 중")),
      el("h2","detail-title",e.title),
      add(el("div","detail-metadata"),
        el("span","",kindLabels[e.change_type]||"변경 유형 확인 중"),
        el("span","","공포·발령일 "+date(e.published_at)),
        el("span","","시행일 "+date(e.effective_date)),
        anchor("공식 원문 ↗",e.url)));
    root.appendChild(overview(e));
    root.appendChild(agencySection(e));
    const change=changesSection(e);root.appendChild(change);
    root.appendChild(citations(e));
  }
  async function boot(){
    try{
      const resp=await fetch("./data.json",{cache:"no-store"});
      if(!resp.ok)throw Error("index HTTP "+resp.status);
      const d=await resp.json();
      if(d.schema!=="policy-domino-unified-ui-v2"||!Array.isArray(d.events))
        throw Error("Unexpected catalog schema");
      state.data=d;state.events=d.events;
      // Acceptance records are a separate quality contract. The list remains
      // usable even when current source or agency evidence is incomplete.
      fetch("./acceptance.json",{cache:"no-store"}).then(r=>r.ok?r.json():null)
        .then(a=>{
          if(!a)return;
          const failed=(a.required_examples||[]).filter(x=>x.missing_steps?.length);
          const body=$("health-body");
          body.appendChild(el("p","",
            "필수 연도별 기준 회귀 검증: "+fmt(3-failed.length)+"/3건 전체 단계 통과"+
            (failed.length?" · 미완료 사례 "+failed.map(x=>x.name).join(", "):"")));
        }).catch(()=>{});
      const areas=[...new Set(state.events.map(x=>x.category).filter(Boolean))].sort();
      for(const area of areas){const opt=el("option","",area);opt.value=area;$("area").appendChild(opt);}
      refreshSummary();renderList();
      const selected=decodeURIComponent((location.hash.match(/^#event=(.*)$/)||[])[1]||"");
      if(state.events.some(x=>x.id===selected))select(selected,false);
      else if(state.events.length && window.matchMedia("(min-width:761px)").matches)
        select(state.events[0].id,false);
    }catch(error){
      $("metrics").replaceChildren();
      $("health-title").textContent="공식 자료 표시 실패";
      $("items").replaceChildren(empty("정책 목록을 불러오지 못했습니다. GitHub 데이터 생성과 배포 상태를 확인해 주세요."));
      $("detail").replaceChildren(empty("공식 정책 자료가 없어 상세 분석을 표시하지 않습니다."));
    }
  }
  document.querySelectorAll("[data-mode]").forEach(button=>button.onclick=()=>{
    state.mode=button.dataset.mode;state.displayLimit=60;renderList();});
  $("search").oninput=e=>{state.query=e.target.value;state.displayLimit=60;renderList();};
  $("area").onchange=e=>{state.area=e.target.value;renderList();};
  $("source").onchange=e=>{state.source=e.target.value;renderList();};
  $("more").onclick=()=>{state.displayLimit+=60;renderList();};
  $("back").onclick=back;
  window.addEventListener("popstate",()=>{
    const id=decodeURIComponent((location.hash.match(/^#event=(.*)$/)||[])[1]||"");
    if(state.events.some(x=>x.id===id))select(id,false);else back();});
  boot();
})();