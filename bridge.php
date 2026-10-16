<?php
/* Same-origin bridge from FPP's authenticated plugin page to the local monitor. */
function aircraftBlackoutToken($key, $now = null)
{
    $stamp = (string)($now === null ? time() : $now);
    $nonce = bin2hex(random_bytes(16));
    $payload = $stamp . ':' . $nonce;
    return $payload . ':' . hash_hmac('sha256', $payload, $key);
}

function aircraftBlackoutValidToken($token, $key)
{
    if (!is_string($token) || !preg_match('/^([0-9]{10}):([a-f0-9]{32}):([a-f0-9]{64})$/D', $token, $parts)) {
        return false;
    }
    $age = time() - (int)$parts[1];
    return $age >= -30 && $age <= 7200 && hash_equals(hash_hmac('sha256', $parts[1] . ':' . $parts[2], $key), $parts[3]);
}

function aircraftBlackoutReply($status, $data)
{
    http_response_code($status);
    if (!headers_sent()) {
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store');
        header('X-Content-Type-Options: nosniff');
    }
    echo json_encode($data, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

function aircraftBlackoutProxy($action, $key)
{
    $routes = array('status' => 'GET', 'config' => 'POST', 'manual' => 'POST', 'acknowledge' => 'POST');
    if (!is_string($action) || !isset($routes[$action])) {
        aircraftBlackoutReply(404, array('error' => 'Unknown aircraft blackout action'));
    }
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== $routes[$action]) {
        aircraftBlackoutReply(405, array('error' => 'Incorrect request method'));
    }
    if (!aircraftBlackoutValidToken($_SERVER['HTTP_X_AIRCRAFT_TOKEN'] ?? '', $key)) {
        aircraftBlackoutReply(403, array('error' => 'Reload the FPP plugin page to refresh its settings token'));
    }
    $headers = array('Authorization: Basic ' . base64_encode('admin:' . $key), 'Accept: application/json', 'Connection: close');
    $options = array('method' => $routes[$action], 'header' => $headers, 'timeout' => 3, 'ignore_errors' => true, 'follow_location' => 0);
    if ($routes[$action] === 'POST') {
        if (strtolower(trim(explode(';', $_SERVER['CONTENT_TYPE'] ?? '')[0])) !== 'application/json') {
            aircraftBlackoutReply(415, array('error' => 'Expected JSON settings'));
        }
        $body = file_get_contents('php://input', false, null, 0, 131073);
        if ($body === false || strlen($body) > 131072 || json_decode($body) === null || json_last_error() !== JSON_ERROR_NONE) {
            aircraftBlackoutReply(400, array('error' => 'Invalid JSON settings'));
        }
        $options['header'][] = 'Content-Type: application/json';
        $options['header'][] = 'X-Blackout-UI: 1';
        $options['content'] = $body;
    }
    // Destination and routes are fixed. Never proxy an arbitrary caller-supplied URL.
    $context = stream_context_create(array('http' => $options));
    $response = @file_get_contents('http://127.0.0.1:32380/api/' . $action, false, $context);
    $status = 502;
    if (isset($http_response_header[0]) && preg_match('/\s([0-9]{3})\s/', $http_response_header[0], $match)) {
        $status = (int)$match[1];
    }
    $data = $response === false ? null : json_decode($response, true);
    if (!is_array($data)) {
        aircraftBlackoutReply(502, array('error' => 'Aircraft monitor is unavailable. Check the fpp-aircraft-blackout service.'));
    }
    if ($status === 401) {
        aircraftBlackoutReply(502, array('error' => 'Aircraft monitor authentication failed. Restart the monitor service.'));
    }
    aircraftBlackoutReply($status, $data);
}
