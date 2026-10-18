// Execute the actual dashboard script with a small DOM/map adapter. No npm dependencies.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const code=fs.readFileSync(path.join(__dirname,'../public-dashboard/dashboard.js'),'utf8');
function element(){return {textContent:'',dataset:{},children:[],disabled:false,append(...x){this.children.push(...x)},replaceChildren(...x){this.children=x},addEventListener(){}}}
async function check(data){
 const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)};
 let clock=0,tick;const plotted=[];
 const layer=()=>({addTo(){return this},remove(){},bindTooltip(){return this},bindPopup(content){this.popup=content;return this},getBounds(){return []},clearLayers(){plotted.length=0}});
 const L={map:()=>({fitBounds(){}}),tileLayer:layer,layerGroup:layer,circle:layer,circleMarker:layer,divIcon:x=>x,marker:(coords,options)=>{plotted.push({coords,options});return layer()}};
 const context={document:{getElementById:get,createElement:element},window:{L},L,performance:{now:()=>clock},Date,AbortController,setInterval(fn){tick=fn},setTimeout(){return 1},clearTimeout(){},fetch:async()=>({ok:true,json:async()=>data})};
 vm.runInNewContext(code,context);await new Promise(setImmediate);
 return {get,plotted,expire(){clock=31000;tick()}};
}
(async()=>{
 const s={observed_at:Date.now()/1000,monitor_fresh:true,enforcement_enabled:false,blackout_requested:true,native_hook_fresh:false,reason_code:'aircraft_inside',zone:{latitude:-27.25,longitude:153.1,radius_km:3},aircraft_count:2,inside_zone_count:1,aircraft:[{hex:'abc123',flight:'<script>alert(1)</script>',latitude:-27.25,longitude:153.1,distance_km:1,position_age_s:0,altitude_ft:10000,speed_kt:200,track_deg:90,fresh:true,inside_zone:true,blocking:true,ignored:false},{hex:'def456',flight:'',latitude:null,longitude:null,distance_km:null,position_age_s:null,altitude_ft:null,speed_kt:null,track_deg:null,fresh:false,inside_zone:false,blocking:false,ignored:true}]};
 let ui=await check({fresh:true,age_s:0,snapshot:s});
 assert.equal(ui.get('protection').textContent,'Disabled');assert.equal(ui.get('blackout').textContent,'Requested');assert.equal(ui.get('inside').textContent,'1');assert.equal(ui.plotted.length,1);
 assert.equal(ui.get('aircraft').children[0].children[0].textContent,s.aircraft[0].flight,'Aircraft text must be inserted as text, not HTML');
 assert.match(ui.get('aircraft').children[1].children[4].textContent,/No usable position · ignored/);
 ui.expire();assert.equal(ui.get('blackout').textContent,'Status unavailable');assert.equal(ui.get('protection').textContent,'Status unavailable');assert.equal(ui.plotted.length,0);
 ui=await check({fresh:true,age_s:1,snapshot:{...s,enforcement_enabled:true,blackout_requested:false,reason_code:'clear'}});
 assert.equal(ui.get('protection').textContent,'Enabled');assert.equal(ui.get('blackout').textContent,'Not requested');
 ui=await check({fresh:false,age_s:40,snapshot:null});assert.equal(ui.get('inside').textContent,'—');assert.equal(ui.plotted.length,0);
 console.log('Public dashboard UI passed: map markers/zone, independent states, unknown positions, text injection and automatic expiry.');
})();
