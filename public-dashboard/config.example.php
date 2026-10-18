<?php
// Copy OUTSIDE your public web root as aircraft-dashboard-config.php.
// Generate a key with: php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;'
return array(
    'token' => 'REPLACE_WITH_A_RANDOM_64_CHARACTER_HEX_KEY',
    'data_file' => __DIR__ . '/aircraft-dashboard-data.json',
);
