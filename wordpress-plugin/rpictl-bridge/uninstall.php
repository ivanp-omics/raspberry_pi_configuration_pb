<?php
/**
 * Pokrece se samo kad se plugin stvarno OBRISE (ne kod obicne deaktivacije),
 * preko Plugins -> Delete. Cisti ulogu i postavke da ne ostanu siroci u bazi.
 */

if (!defined('WP_UNINSTALL_PLUGIN')) {
    exit;
}

remove_role('rpictl_operator');
delete_option('rpictl_bridge_pi_url');
delete_option('rpictl_bridge_api_token');
