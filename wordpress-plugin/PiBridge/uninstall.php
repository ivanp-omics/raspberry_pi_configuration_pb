<?php
/**
 * Pokrece se samo kad se plugin stvarno OBRISE (ne kod obicne deaktivacije),
 * preko Plugins -> Delete. Cisti ulogu i postavke da ne ostanu siroci u bazi.
 */

if (!defined('WP_UNINSTALL_PLUGIN')) {
    exit;
}

$admin = get_role('administrator');
if ($admin) {
    $admin->remove_cap('pibridge_operate');
}

remove_role('pibridge_operator');
delete_option('pibridge_pi_url');
delete_option('pibridge_api_token');
