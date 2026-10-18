<?php
// PHP 7.4+. Store the configuration and data OUTSIDE the public document root.
// Override AIRCRAFT_PUBLIC_CONFIG through your hosting environment if necessary.
function reply($code, $data) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, max-age=0');
    header('X-Content-Type-Options: nosniff');
    echo json_encode($data, JSON_INVALID_UTF8_SUBSTITUTE | JSON_UNESCAPED_SLASHES);
    exit;
}
function fail() { reply(400, array('error'=>'Invalid dashboard snapshot')); }
function num($v, $lo, $hi, $nullable=false) {
    if ($v === null && $nullable) return null;
    if ((!is_int($v) && !is_float($v)) || !is_finite((float)$v) || $v<$lo || $v>$hi) fail();
    return $v;
}
function flag($a, $k) { if (!isset($a[$k]) || !is_bool($a[$k])) fail(); return $a[$k]; }
function text($v, $max) { if (!is_string($v) || strlen($v)>$max) fail(); return $v; }
$configPath = getenv('AIRCRAFT_PUBLIC_CONFIG') ?: dirname($_SERVER['DOCUMENT_ROOT']).'/aircraft-dashboard-config.php';
if (!is_file($configPath)) reply(503, array('error'=>'Dashboard not configured'));
$c = require $configPath;
if (!is_array($c) || !preg_match('/^[A-Za-z0-9_-]{32,128}$/D', $c['token'] ?? '') || strpos($c['token'], 'REPLACE_') === 0) reply(503, array('error'=>'Dashboard not configured'));
// Reject storing data anywhere inside the public web root, including through symlinks.
$root = realpath($_SERVER['DOCUMENT_ROOT']);
$parent = realpath(dirname($c['data_file'] ?? ''));
if (!$root || !$parent || $parent===$root || strpos($parent, $root.DIRECTORY_SEPARATOR)===0 || is_link($c['data_file'])) reply(503, array('error'=>'Private data storage required'));
$method = $_SERVER['REQUEST_METHOD'];
if ($method === 'GET') {
    $stored = is_file($c['data_file']) ? json_decode(file_get_contents($c['data_file']), true) : null;
    $now = microtime(true);
    $age = is_array($stored) ? max($now-($stored['received_at'] ?? 0), $now-($stored['snapshot']['observed_at'] ?? 0), 0) : null;
    $fresh = $age !== null && $age<=30 && ($stored['snapshot']['monitor_fresh'] ?? false);
    reply(200, array('fresh'=>$fresh, 'age_s'=>$age, 'snapshot'=>$fresh ? $stored['snapshot'] : null));
}
if ($method !== 'POST') { header('Allow: GET, POST'); reply(405, array('error'=>'Method not allowed')); }
$auth = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
if (!hash_equals('Bearer '.$c['token'], $auth)) reply(401, array('error'=>'Unauthorized'));
if (strtolower(trim(explode(';', $_SERVER['CONTENT_TYPE'] ?? '')[0])) !== 'application/json') reply(415, array('error'=>'JSON required'));
$body = file_get_contents('php://input', false, null, 0, 262145);
if ($body === false || strlen($body)>262144) reply(413, array('error'=>'Snapshot too large'));
$a = json_decode($body, true, 32);
if (!is_array($a) || ($a['schema'] ?? null)!==1 || !is_array($a['zone'] ?? null) || !is_array($a['aircraft'] ?? null) || count($a['aircraft'])>100) fail();
$observed = num($a['observed_at'] ?? null, 0, 1e12);
if (abs(microtime(true)-$observed)>30) reply(400, array('error'=>'Snapshot expired; check FPP clock'));
$z=$a['zone'];
// Rebuild every public field: never store or return arbitrary caller-supplied config.
$out=array('schema'=>1, 'observed_at'=>$observed, 'zone'=>array('latitude'=>num($z['latitude'] ?? null,-90,90), 'longitude'=>num($z['longitude'] ?? null,-180,180), 'radius_km'=>num($z['radius_km'] ?? null,.1,300)));
foreach (array('monitor_fresh','enforcement_enabled','blackout_requested','receiver_ok','native_hook_fresh') as $k) $out[$k]=flag($a,$k);
if (!in_array($a['reason_code'] ?? '', array('manual','receiver_fault','aircraft_inside','position_fault','clear_delay','clear'),true)) fail();
$out['aircraft_count']=num($a['aircraft_count'] ?? null,0,100000);
$out['inside_zone_count']=num($a['inside_zone_count'] ?? null,0,100000);
$out['reason_code']=$a['reason_code']; $out['aircraft']=array();
foreach ($a['aircraft'] as $p) {
    if (!is_array($p)) fail();
    $row=array('hex'=>text($p['hex'] ?? null,24), 'flight'=>text($p['flight'] ?? null,32));
    foreach (array('latitude'=>array(-90,90),'longitude'=>array(-180,180),'distance_km'=>array(0,21000),'position_age_s'=>array(0,1e9),'altitude_ft'=>array(-2000,100000),'speed_kt'=>array(0,2000),'track_deg'=>array(0,360)) as $k=>$bounds) $row[$k]=num($p[$k] ?? null,$bounds[0],$bounds[1],true);
    foreach (array('fresh','inside_zone','blocking','ignored') as $k) $row[$k]=flag($p,$k);
    $out['aircraft'][]=$row;
}
// Serialize updates, reject delayed old uploads and replace the snapshot atomically.
$lock=@fopen($c['data_file'].'.lock','c');
if (!$lock || !flock($lock, LOCK_EX)) reply(503,array('error'=>'Storage unavailable'));
$old=is_file($c['data_file']) ? json_decode(file_get_contents($c['data_file']),true) : null;
if ($old && ($old['snapshot']['observed_at'] ?? 0)>$observed) reply(409,array('error'=>'Older snapshot refused'));
$tmp=tempnam($parent,'aircraft-');
$encoded=json_encode(array('received_at'=>microtime(true),'snapshot'=>$out),JSON_INVALID_UTF8_SUBSTITUTE);
if ($tmp===false || file_put_contents($tmp,$encoded)===false || !chmod($tmp,0600) || !rename($tmp,$c['data_file'])) { if ($tmp) @unlink($tmp); reply(503,array('error'=>'Storage unavailable')); }
flock($lock,LOCK_UN); fclose($lock);
reply(200,array('ok'=>true));
