const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
const code=html.split('<script>')[1].split('</script>')[0].replace('__BLACKOUT_CONFIG__',JSON.stringify({endpoint:'/',token:'test'}));
(async()=>{for(const ignore of [false,true]){
 const elements=new Map();const element=()=>({checked:false,disabled:false,value:'',textContent:'',dataset:{},addEventListener(){},replaceChildren(){},append(){}});
 const get=id=>{if(!elements.has(id))elements.set(id,element());return elements.get(id)};
 let saved=null,config={enforce:false,blackout_on_stale_positions:true,ignore_aircraft_without_position:ignore,public_dashboard_enabled:false,public_dashboard_url:'',public_dashboard_key:'',channels:[],receiver_url:'http://192.168.1.50/data/aircraft.json',latitude:0,longitude:0,radius_km:15,clear_delay_s:60,max_feed_age_s:5,max_position_age_s:5};
 const context={document:{getElementById:get,createElement:element,hidden:false},window:{addEventListener(){}},setInterval(){},clearInterval(){},Date,confirm:()=>true,fetch:async(route,opts)=>{if(route==='/config'){saved=JSON.parse(opts.body);config=saved;return{ok:true,json:async()=>({ok:true})}}return{ok:true,json:async()=>({config,can_acknowledge:false,blocked:false,reason:'Clear',native:{heartbeat_fresh:false},public_push:{result:'Disabled',last_success:null},aircraft:[]})}}};
 vm.runInNewContext(code,context);await new Promise(setImmediate);
 const box=get('ab-ignore_aircraft_without_position');assert.equal(box.checked,!ignore);
 assert.equal(get('ab-ignore_aircraft_without_position-value').textContent,(!ignore?'ON':'OFF')+' — saved');
 await get('ab-form').onsubmit({preventDefault(){}});assert.equal(saved.ignore_aircraft_without_position,ignore);assert.equal(saved.public_dashboard_enabled,false);
 box.checked=!box.checked;get('ab-public_dashboard_url').value='https://lightsonelizabeth.com/aircraft/api.php';get('ab-public_dashboard_key').value='c'.repeat(64);get('ab-public_dashboard_enabled').checked=true;
 await get('ab-form').onsubmit({preventDefault(){}});
 assert.equal(saved.ignore_aircraft_without_position,!ignore);assert.equal(saved.public_dashboard_enabled,true);assert.equal(saved.public_dashboard_url,'https://lightsonelizabeth.com/aircraft/api.php');assert.equal(saved.public_dashboard_key,'c'.repeat(64));
 assert.equal(get('ab-public_dashboard_enabled-value').textContent,'ON — saved');
}console.log('FPP settings UI passed: preference inversion, publication fields, explicit opt-in and saved-state badges.');})();
