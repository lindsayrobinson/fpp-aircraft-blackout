'use strict';
(() => {
  const get = id => document.getElementById(id);
  const reasons = {manual:'Manual blackout is engaged.',receiver_fault:'The aircraft receiver is unavailable.',aircraft_inside:'Fresh aircraft positions are inside the blackout zone.',position_fault:'An aircraft position or previous tracking fault requires attention.',clear_delay:'Waiting for the configured clear delay.',clear:'No blackout is currently requested.'};
  let map, circle, center, layers, zoneKey='', latest=null, received=0, initialAge=0, expired=true;
  const number = (n,unit='') => Number.isFinite(n) ? n.toLocaleString(undefined,{maximumFractionDigits:1})+unit : 'Unknown';
  function status(id,text,tone='') {get(id).textContent=text; get(id).dataset.tone=tone;}
  function emptyTable(message) {const row=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=5;cell.textContent=message;row.append(cell);get('aircraft').replaceChildren(row);}
  function unavailable(message) {
    expired=true;get('connection').textContent='Status unavailable';get('connection').dataset.live='false';
    status('protection','Status unavailable');status('blackout','Status unavailable');status('inside','—');
    get('reason').textContent=message;get('protection-note').textContent='Waiting for a current update from the display.';
    get('zone-note').textContent='Aircraft positions are not current.';get('updated').textContent='No current update';
    get('map-note').textContent='Aircraft hidden until fresh updates arrive.';
    if(layers)layers.clearLayers();emptyTable('Aircraft data is unavailable.');
  }
  function positionText(a) {
    if(a.latitude===null || a.longitude===null || a.position_age_s===null)return 'No usable position'+(a.ignored?' · ignored':' · blackout');
    if(!a.fresh)return 'Old position'+(a.ignored?' · ignored':' · blackout')+' · '+number(a.position_age_s,'s ago');
    return (a.inside_zone?'Inside zone':'Outside zone')+' · '+number(a.position_age_s,'s ago');
  }
  function planeIcon(a) {
    const cls=!a.fresh?'stale':a.inside_zone?'inside':'';
    const angle=Number.isFinite(a.track_deg)?a.track_deg:0;
    // Only a validated numeric angle enters HTML; aircraft text uses textContent below.
    return L.divIcon({className:'plane-icon '+cls,iconSize:[30,30],iconAnchor:[15,15],html:`<svg viewBox="0 0 24 24" aria-hidden="true" style="transform:rotate(${angle}deg)"><path fill="currentColor" stroke="white" stroke-width=".7" d="M11 2h2l1 7 8 5v2l-8-2v5l3 2v1l-5-1-5 1v-1l3-2v-5l-8 2v-2l8-5z"/></svg>`});
  }
  function draw(s) {
    if(!window.L){get('map').textContent='The map library could not load. Aircraft details remain available below.';return;}
    const z=s.zone,key=JSON.stringify(z);
    if(!map){get('map').replaceChildren();map=L.map('map').setView([z.latitude,z.longitude],11);L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);layers=L.layerGroup().addTo(map);}
    if(key!==zoneKey){zoneKey=key;if(circle)circle.remove();if(center)center.remove();circle=L.circle([z.latitude,z.longitude],{radius:z.radius_km*1000,color:'#c83236',weight:2,fillColor:'#e75958',fillOpacity:.10}).addTo(map);center=L.circleMarker([z.latitude,z.longitude],{radius:5,color:'#102d36',fillColor:'#f0cf85',fillOpacity:1}).addTo(map).bindTooltip('Lights on Elizabeth');map.fitBounds(circle.getBounds(),{padding:[25,25]});get('recenter').disabled=false;}
    layers.clearLayers();
    for(const a of s.aircraft){if(!Number.isFinite(a.latitude)||!Number.isFinite(a.longitude))continue;const popup=document.createElement('div');for(const line of [a.flight||a.hex,'Distance: '+number(a.distance_km,' km'),'Altitude: '+number(a.altitude_ft,' ft'),'Speed: '+number(a.speed_kt,' kt'),positionText(a)]){const p=document.createElement('div');p.textContent=line;popup.append(p);}L.marker([a.latitude,a.longitude],{icon:planeIcon(a),title:a.flight||a.hex,opacity:a.fresh?1:.65}).addTo(layers).bindPopup(popup);}
    get('map-note').textContent='';
  }
  function render(s){
    expired=false;
    get('connection').textContent='Receiving display updates';get('connection').dataset.live='true';
    status('protection',s.enforcement_enabled?'Enabled':'Disabled',s.enforcement_enabled?'good':'alert');
    get('protection-note').textContent=!s.enforcement_enabled?'Observation mode: the plugin does not override output.':s.native_hook_fresh?'Native output hook is reporting.':'Native output hook has not been confirmed.';
    status('blackout',s.blackout_requested?'Requested':'Not requested',s.blackout_requested?'alert':'good');
    get('reason').textContent=reasons[s.reason_code]||'Waiting for status details.';
    const inside=s.inside_zone_count;
    status('inside',String(inside),inside?'alert':'good');get('zone-note').textContent=number(s.zone.radius_km,' km')+' radius · fresh reported positions';
    const rows=[...s.aircraft].sort((a,b)=>Number(b.fresh&&b.inside_zone)-Number(a.fresh&&a.inside_zone)||(a.distance_km??Infinity)-(b.distance_km??Infinity));
    get('aircraft').replaceChildren();
    for(const a of rows){const row=document.createElement('tr');row.dataset.inside=String(a.fresh&&a.inside_zone);for(const [i,v] of [a.flight||a.hex,number(a.distance_km,' km'),number(a.altitude_ft,' ft'),number(a.speed_kt,' kt'),positionText(a)].entries()){const cell=document.createElement('td');cell.textContent=v;if(i===0&&a.flight){const small=document.createElement('small');small.textContent=a.hex;cell.append(small);}row.append(cell);}get('aircraft').append(row);}
    if(!rows.length)emptyTable('No aircraft records received. An empty list does not establish clear airspace.');
    get('table-note').textContent=`${rows.length} of ${s.aircraft_count} received records shown (up to 100). Aircraft without usable coordinates appear only in this table.`;
    // Map failures must not overwrite valid controller status or aircraft details.
    try{draw(s);}catch(e){get('map-note').textContent='Map unavailable. Aircraft details and controller status remain available below.';}
  }
  function tick(){if(!latest)return;const age=initialAge+(performance.now()-received)/1000;if(age>30){if(!expired)unavailable('Updates have stopped. The previous blackout status is no longer current.');return;}if(!expired)get('updated').textContent='Data age: '+Math.floor(age)+'s · '+new Date(latest.observed_at*1000).toLocaleTimeString();}
  async function refresh(){
    const abort=new AbortController();const timeout=setTimeout(()=>abort.abort(),5000);
    try{const response=await fetch('api.php',{cache:'no-store',signal:abort.signal,credentials:'omit'});if(!response.ok)throw Error('Unavailable');const data=await response.json();if(!data.fresh||!data.snapshot||!data.snapshot.monitor_fresh||!Number.isFinite(data.age_s)||data.age_s>30){latest=null;unavailable('Waiting for a current update from the display.');return;}latest=data.snapshot;initialAge=Math.max(data.age_s,0);received=performance.now();render(latest);tick();}
    catch(e){unavailable('The website cannot retrieve current display status.');latest=null;}
    finally{clearTimeout(timeout);setTimeout(refresh,5000);}
  }
  get('recenter').addEventListener('click',()=>{if(map&&circle)map.fitBounds(circle.getBounds(),{padding:[25,25]});});
  setInterval(tick,1000);refresh();
})();
