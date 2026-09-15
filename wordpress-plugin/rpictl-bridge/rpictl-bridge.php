<?php
/**
 * Plugin Name: rpictl Bridge
 * Description: Prijavljenim korisnicima s ulogom rpictl_operator daje kontrolu spremišta (ventilacija, razglas, glazba) preko Raspberry Pi-ja - shortcode [rpictl_panel] + wp-json/rpictl/v1/* proxy prema Pi-ju.
 * Version: 1.0.0
 * Author: OMICS
 * License: proprietary
 *
 * Browser nikad ne zove Pi izravno - samo ovaj plugin (server-to-server, preko
 * wp_remote_get/wp_remote_post), s tajnim tokenom koji nikad ne napusta server.
 * Vidi README.md u ovoj mapi za postavljanje.
 */

if (!defined('ABSPATH')) {
    exit; // izravan pristup datoteci nije dopusten
}

const RPICTL_BRIDGE_ROLE = 'rpictl_operator';
const RPICTL_BRIDGE_CAP = 'rpictl_operate';
const RPICTL_BRIDGE_NS = 'rpictl/v1';

// --------------------------------------------------------------------------
// Aktivacija - nova uloga, odvojena od svih postojecih uloga na stranici
// --------------------------------------------------------------------------

register_activation_hook(__FILE__, function () {
    add_role(RPICTL_BRIDGE_ROLE, 'rpictl operator', [
        'read' => true,
        RPICTL_BRIDGE_CAP => true,
    ]);
    // WordPress ne daje administratoru prilagodene sposobnosti sam od sebe.
    // Bez ovoga ni onaj tko je plugin postavio ne vidi panel, a jedini nacin
    // da si da pristup preko Users ekrana bio bi da promijeni vlastitu ulogu
    // u rpictl_operator - cime bi ostao bez administratorskih prava.
    $admin = get_role('administrator');
    if ($admin) {
        $admin->add_cap(RPICTL_BRIDGE_CAP);
    }
});

function rpictl_bridge_can_operate(): bool {
    return current_user_can(RPICTL_BRIDGE_CAP);
}

// --------------------------------------------------------------------------
// Postavke (Settings -> rpictl Bridge) - Pi URL i token, nikad u kodu/gitu
// --------------------------------------------------------------------------

add_action('admin_menu', function () {
    add_options_page('rpictl Bridge', 'rpictl Bridge', 'manage_options', 'rpictl-bridge', 'rpictl_bridge_settings_page');
});

add_action('admin_init', function () {
    register_setting('rpictl_bridge', 'rpictl_bridge_pi_url', ['sanitize_callback' => 'esc_url_raw']);
    register_setting('rpictl_bridge', 'rpictl_bridge_api_token', ['sanitize_callback' => 'sanitize_text_field']);
});

function rpictl_bridge_settings_page(): void {
    if (!current_user_can('manage_options')) {
        return;
    }
    ?>
    <div class="wrap">
        <h1>rpictl Bridge</h1>
        <p>Adresa i token moraju se poklapati s <code>server.api_token</code> u
           <code>config.yaml</code> na Raspberry Pi-ju.</p>
        <form method="post" action="options.php">
            <?php settings_fields('rpictl_bridge'); ?>
            <table class="form-table">
                <tr>
                    <th><label for="rpictl_bridge_pi_url">Pi Funnel URL</label></th>
                    <td>
                        <input type="url" id="rpictl_bridge_pi_url" name="rpictl_bridge_pi_url"
                            value="<?php echo esc_attr(get_option('rpictl_bridge_pi_url', '')); ?>"
                            class="regular-text" placeholder="https://spremiste.<tailnet>.ts.net">
                    </td>
                </tr>
                <tr>
                    <th><label for="rpictl_bridge_api_token">API token</label></th>
                    <td>
                        <input type="password" id="rpictl_bridge_api_token" name="rpictl_bridge_api_token"
                            value="<?php echo esc_attr(get_option('rpictl_bridge_api_token', '')); ?>"
                            class="regular-text" placeholder="isti string kao server.api_token u config.yaml">
                    </td>
                </tr>
            </table>
            <?php submit_button(); ?>
        </form>
    </div>
    <?php
}

// --------------------------------------------------------------------------
// Proxy prema Pi-ju - jedino mjesto koje zna adresu i token
// --------------------------------------------------------------------------

/**
 * @param array<string,mixed>|null $body
 */
function rpictl_bridge_request(string $method, string $endpoint, ?array $body = null): WP_REST_Response|WP_Error {
    $pi_url = trim((string) get_option('rpictl_bridge_pi_url', ''));
    if (!$pi_url) {
        return new WP_Error('rpictl_not_configured', 'Pi URL nije postavljen (Settings -> rpictl Bridge).', ['status' => 500]);
    }
    $token = (string) get_option('rpictl_bridge_api_token', '');
    $url = rtrim($pi_url, '/') . $endpoint;
    // Kratak timeout: svaki zahtjev drzi jednog PHP radnika zauzetim dok traje,
    // a panel ih salje u petlji - dugi timeout na nedostupnom Pi-ju zna
    // iscrpiti cijeli worker pool hostinga.
    $args = [
        'timeout' => 5,
        'headers' => ['X-Api-Key' => $token],
    ];

    if ($method === 'POST') {
        $args['headers']['Content-Type'] = 'application/json';
        $args['body'] = wp_json_encode($body ?? new stdClass());
        $response = wp_remote_post($url, $args);
    } else {
        $response = wp_remote_get($url, $args);
    }

    if (is_wp_error($response)) {
        return new WP_Error('rpictl_unreachable', 'Ne mogu se spojiti na Pi: ' . $response->get_error_message(), ['status' => 502]);
    }

    $code = wp_remote_retrieve_response_code($response);
    if ($code === 401) {
        // Bez ovoga se odbijen token u panelu vidi isto kao ugasen Pi, a token
        // se upisuje rucno na dva mjesta pa je zamjena ta dva uzroka izgledna.
        return new WP_Error(
            'rpictl_bad_token',
            'Pi je odbio token. Provjeri da je API token u Settings -> rpictl Bridge identican onome u server.api_token na Pi-ju.',
            ['status' => 502]
        );
    }

    $data = json_decode(wp_remote_retrieve_body($response), true);
    return new WP_REST_Response($data, $code);
}

add_action('rest_api_init', function () {
    register_rest_route(RPICTL_BRIDGE_NS, '/status', [
        'methods' => 'GET',
        'callback' => fn() => rpictl_bridge_request('GET', '/api/status'),
        'permission_callback' => 'rpictl_bridge_can_operate',
    ]);

    register_rest_route(RPICTL_BRIDGE_NS, '/fan', [
        'methods' => 'POST',
        'callback' => fn(WP_REST_Request $req) => rpictl_bridge_request(
            'POST', '/api/fan', ['mode' => $req->get_param('mode')]
        ),
        'permission_callback' => 'rpictl_bridge_can_operate',
    ]);

    register_rest_route(RPICTL_BRIDGE_NS, '/announce', [
        'methods' => 'POST',
        'callback' => function (WP_REST_Request $req) {
            $body = array_filter([
                'text' => $req->get_param('text'),
                'file' => $req->get_param('file'),
                'priority' => $req->get_param('priority'),
            ], fn($v) => $v !== null);
            return rpictl_bridge_request('POST', '/api/announce', $body);
        },
        'permission_callback' => 'rpictl_bridge_can_operate',
    ]);

    register_rest_route(RPICTL_BRIDGE_NS, '/music', [
        'methods' => 'POST',
        'callback' => function (WP_REST_Request $req) {
            $body = ['action' => $req->get_param('action')];
            if ($req->get_param('track')) {
                $body['track'] = $req->get_param('track');
            }
            return rpictl_bridge_request('POST', '/api/music', $body);
        },
        'permission_callback' => 'rpictl_bridge_can_operate',
    ]);
});

// --------------------------------------------------------------------------
// Shortcode [rpictl_panel]
// --------------------------------------------------------------------------

add_shortcode('rpictl_panel', function () {
    if (!rpictl_bridge_can_operate()) {
        return '<p class="rpictl-denied">Nemaš pristup ovoj kontroli.</p>';
    }

    // Verzija iz vremena izmjene datoteke - fiksni string znaci da operateri
    // nakon svakog uploada jos danima vrte staru verziju iz browser cachea.
    $css = plugin_dir_path(__FILE__) . 'assets/panel.css';
    $js = plugin_dir_path(__FILE__) . 'assets/panel.js';
    wp_enqueue_style('rpictl-bridge', plugins_url('assets/panel.css', __FILE__), [], (string) (filemtime($css) ?: '1.0.0'));
    wp_enqueue_script('rpictl-bridge', plugins_url('assets/panel.js', __FILE__), [], (string) (filemtime($js) ?: '1.0.0'), true);
    wp_localize_script('rpictl-bridge', 'rpictlBridge', [
        'restUrl' => esc_url_raw(rest_url(RPICTL_BRIDGE_NS)),
        'nonce' => wp_create_nonce('wp_rest'),
    ]);

    return '<div id="rpictl-panel" class="rpictl-panel">Učitavam...</div>';
});

// Izuzmi stranicu sa shortcodeom iz page-cache dodataka (WP-Optimize i sl.) -
// panel svejedno crta zivo stanje preko JS-a, ovo je dodatna sigurnost.
add_action('template_redirect', function () {
    if (is_singular()) {
        $post = get_post();
        if ($post && has_shortcode($post->post_content, 'rpictl_panel')) {
            nocache_headers();
        }
    }
});
