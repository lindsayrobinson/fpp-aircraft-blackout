<?php
require_once __DIR__ . '/bridge.php';
$configDir = $settings['configDirectory'] ?? '/home/fpp/media/config';
$key = @file_get_contents($configDir . '/aircraft-blackout.key');
$action = $_GET['action'] ?? null;
if ($key === false || trim($key) === '') {
    if ($action !== null) {
        aircraftBlackoutReply(503, array('error' => 'Run the Aircraft Blackout installer first; monitor credentials are missing.'));
    }
    echo '<div class="alert alert-warning">Run the Aircraft Blackout installation script first. The monitor credentials are missing or unreadable.</div>';
    return;
}
$key = trim($key);
if ($action !== null) {
    // nopage keeps JSON responses inside FPP without its surrounding HTML.
    if (!isset($_GET['nopage'])) {
        aircraftBlackoutReply(400, array('error' => 'Use the FPP settings panel'));
    }
    aircraftBlackoutProxy($action, $key);
}
if (!headers_sent()) {
    header('Cache-Control: no-store');
}
$ui = array('endpoint' => 'plugin.php?plugin=fpp-aircraft-blackout&page=index.php&nopage=1&action=', 'token' => aircraftBlackoutToken($key));
$template = file_get_contents(__DIR__ . '/index.html');
echo str_replace('__BLACKOUT_CONFIG__', json_encode($ui, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT), $template);
