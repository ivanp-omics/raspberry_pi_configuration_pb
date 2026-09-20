<?php
/**
 * Plugin Name: PiBridge
 * Description: Prijavljenim korisnicima s ulogom pibridge_operator daje kontrolu spremišta (ventilacija, razglas, glazba, mreža, povijest) preko Raspberry Pi-ja - shortcode [pibridge_panel] + wp-json/pibridge/v1/* proxy prema Pi-ju. Odvojen od rpictl-bridge plugina, imitira rpictl/web/index.html.
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

const PIBRIDGE_ROLE = 'pibridge_operator';
const PIBRIDGE_CAP = 'pibridge_operate';
const PIBRIDGE_NS = 'pibridge/v1';

// --------------------------------------------------------------------------
// Aktivacija - nova uloga, odvojena od svih postojecih uloga na stranici
// --------------------------------------------------------------------------

register_activation_hook(__FILE__, function () {
    add_role(PIBRIDGE_ROLE, 'PiBridge operator', [
        'read' => true,
        PIBRIDGE_CAP => true,
    ]);
    // WordPress ne daje administratoru prilagodene sposobnosti sam od sebe.
    // Bez ovoga ni onaj tko je plugin postavio ne vidi panel, a jedini nacin
    // da si da pristup preko Users ekrana bio bi da promijeni vlastitu ulogu
    // u pibridge_operator - cime bi ostao bez administratorskih prava.
    $admin = get_role('administrator');
    if ($admin) {
        $admin->add_cap(PIBRIDGE_CAP);
    }
});

function pibridge_can_operate(): bool {
    return current_user_can(PIBRIDGE_CAP);
}

// --------------------------------------------------------------------------
// Postavke (Settings -> PiBridge) - Pi URL i token, nikad u kodu/gitu
// --------------------------------------------------------------------------

add_action('admin_menu', function () {
    add_options_page('PiBridge', 'PiBridge', 'manage_options', 'pibridge', 'pibridge_settings_page');
});

add_action('admin_init', function () {
    register_setting('pibridge', 'pibridge_pi_url', ['sanitize_callback' => 'esc_url_raw']);
    register_setting('pibridge', 'pibridge_api_token', ['sanitize_callback' => 'sanitize_text_field']);
});

function pibridge_settings_page(): void {
    if (!current_user_can('manage_options')) {
        return;
    }
    ?>
    <div class="wrap">
        <h1>PiBridge</h1>
        <p>Adresa i token moraju se poklapati s <code>server.api_token</code> u
           <code>config.local.yaml</code> na Raspberry Pi-ju.</p>
        <form method="post" action="options.php">
            <?php settings_fields('pibridge'); ?>
            <table class="form-table">
                <tr>
                    <th><label for="pibridge_pi_url">Pi Funnel URL</label></th>
                    <td>
                        <input type="url" id="pibridge_pi_url" name="pibridge_pi_url"
                            value="<?php echo esc_attr(get_option('pibridge_pi_url', '')); ?>"
                            class="regular-text" placeholder="https://spremiste.<tailnet>.ts.net">
                    </td>
                </tr>
                <tr>
                    <th><label for="pibridge_api_token">API token</label></th>
                    <td>
                        <input type="password" id="pibridge_api_token" name="pibridge_api_token"
                            value="<?php echo esc_attr(get_option('pibridge_api_token', '')); ?>"
                            class="regular-text" placeholder="isti string kao server.api_token u config.local.yaml">
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
function pibridge_request(string $method, string $endpoint, ?array $body = null): WP_REST_Response|WP_Error {
    $pi_url = trim((string) get_option('pibridge_pi_url', ''));
    if (!$pi_url) {
        return new WP_Error('pibridge_not_configured', 'Pi URL nije postavljen (Settings -> PiBridge).', ['status' => 500]);
    }
    $token = (string) get_option('pibridge_api_token', '');
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
        return new WP_Error('pibridge_unreachable', 'Ne mogu se spojiti na Pi: ' . $response->get_error_message(), ['status' => 502]);
    }

    $code = wp_remote_retrieve_response_code($response);
    if ($code === 401) {
        // Bez ovoga se odbijen token u panelu vidi isto kao ugasen Pi, a token
        // se upisuje rucno na dva mjesta pa je zamjena ta dva uzroka izgledna.
        return new WP_Error(
            'pibridge_bad_token',
            'Pi je odbio token. Provjeri da je API token u Settings -> PiBridge identican onome u server.api_token na Pi-ju.',
            ['status' => 502]
        );
    }

    $data = json_decode(wp_remote_retrieve_body($response), true);
    return new WP_REST_Response($data, $code);
}

/**
 * Isto kao pibridge_request(), ali za binarni sadrzaj (snimka isjecka).
 *
 * Audio se vraca kao base64 unutar JSON-a, a ne kao sirovi izlaz: sirovi
 * izlaz iz REST rute trazi header()+exit(), sto na dijeljenom hostingu lako
 * pokvari bilo koji drugi plugin s output bufferingom. 33 % vise bajtova na
 * ~30 kB isjecku je bezbolna cijena za pouzdanost.
 *
 * @param string|null $raw_body sirovo tijelo koje se prosljeduje Pi-ju
 */
function pibridge_audio_request(
    string $method,
    string $endpoint,
    ?string $raw_body = null,
    string $content_type = 'application/octet-stream',
    int $timeout = 5
): WP_REST_Response|WP_Error {
    $pi_url = trim((string) get_option('pibridge_pi_url', ''));
    if (!$pi_url) {
        return new WP_Error('pibridge_not_configured', 'Pi URL nije postavljen (Settings -> PiBridge).', ['status' => 500]);
    }
    $args = [
        'timeout' => $timeout,
        'headers' => ['X-Api-Key' => (string) get_option('pibridge_api_token', '')],
    ];
    if ($raw_body !== null) {
        $args['headers']['Content-Type'] = $content_type;
        $args['body'] = $raw_body;
    }

    $response = $method === 'POST'
        ? wp_remote_post(rtrim($pi_url, '/') . $endpoint, $args)
        : wp_remote_get(rtrim($pi_url, '/') . $endpoint, $args);

    if (is_wp_error($response)) {
        return new WP_Error('pibridge_unreachable', 'Ne mogu se spojiti na Pi: ' . $response->get_error_message(), ['status' => 502]);
    }

    $code = wp_remote_retrieve_response_code($response);
    if ($code === 401) {
        return new WP_Error(
            'pibridge_bad_token',
            'Pi je odbio token. Provjeri da je API token u Settings -> PiBridge identican onome u server.api_token na Pi-ju.',
            ['status' => 502]
        );
    }
    $body = wp_remote_retrieve_body($response);
    if ($code !== 200) {
        $detail = json_decode($body, true);
        return new WP_Error(
            'pibridge_pi_error',
            is_array($detail) && isset($detail['detail']) ? (string) $detail['detail'] : 'Pi je vratio ' . $code,
            ['status' => $code === 409 ? 409 : 502]
        );
    }

    return new WP_REST_Response([
        'mime' => wp_remote_retrieve_header($response, 'content-type') ?: 'audio/ogg',
        'bytes' => strlen($body),
        'audio_base64' => base64_encode($body),
    ], 200);
}

add_action('rest_api_init', function () {
    register_rest_route(PIBRIDGE_NS, '/status', [
        'methods' => 'GET',
        'callback' => fn() => pibridge_request('GET', '/api/status'),
        'permission_callback' => 'pibridge_can_operate',
    ]);

    register_rest_route(PIBRIDGE_NS, '/history', [
        'methods' => 'GET',
        'callback' => fn() => pibridge_request('GET', '/api/history?hours=24'),
        'permission_callback' => 'pibridge_can_operate',
    ]);

    register_rest_route(PIBRIDGE_NS, '/network', [
        'methods' => 'GET',
        'callback' => fn() => pibridge_request('GET', '/api/network'),
        'permission_callback' => 'pibridge_can_operate',
    ]);

    register_rest_route(PIBRIDGE_NS, '/fan', [
        'methods' => 'POST',
        'callback' => fn(WP_REST_Request $req) => pibridge_request(
            'POST', '/api/fan', ['mode' => $req->get_param('mode')]
        ),
        'permission_callback' => 'pibridge_can_operate',
    ]);

    register_rest_route(PIBRIDGE_NS, '/announce', [
        'methods' => 'POST',
        'callback' => function (WP_REST_Request $req) {
            $body = array_filter([
                'text' => $req->get_param('text'),
                'file' => $req->get_param('file'),
                'priority' => $req->get_param('priority'),
            ], fn($v) => $v !== null);
            return pibridge_request('POST', '/api/announce', $body);
        },
        'permission_callback' => 'pibridge_can_operate',
    ]);

    register_rest_route(PIBRIDGE_NS, '/music', [
        'methods' => 'POST',
        'callback' => function (WP_REST_Request $req) {
            $body = ['action' => $req->get_param('action')];
            if ($req->get_param('track')) {
                $body['track'] = $req->get_param('track');
            }
            return pibridge_request('POST', '/api/music', $body);
        },
        'permission_callback' => 'pibridge_can_operate',
    ]);

    register_rest_route(PIBRIDGE_NS, '/music-volume', [
        'methods' => 'POST',
        'callback' => fn(WP_REST_Request $req) => pibridge_request(
            'POST', '/api/music/volume', ['volume' => (int) $req->get_param('volume')]
        ),
        'permission_callback' => 'pibridge_can_operate',
    ]);

    // Snimka s mikrofona u browseru -> odmah na razglas. Tijelo je sirov audio
    // (ne multipart), pa se samo prosljeduje dalje bez sastavljanja formulara.
    register_rest_route(PIBRIDGE_NS, '/announce-clip', [
        'methods' => 'POST',
        'callback' => function (WP_REST_Request $req) {
            $ext = preg_replace('/[^a-z0-9]/', '', strtolower((string) $req->get_param('ext'))) ?: 'webm';
            $raw = $req->get_body();
            if ($raw === '') {
                return new WP_Error('pibridge_empty_clip', 'Snimka je prazna.', ['status' => 422]);
            }
            return pibridge_request_passthrough(
                '/api/announce/clip?ext=' . rawurlencode($ext),
                $raw,
                $req->get_content_type()['value'] ?? 'application/octet-stream'
            );
        },
        'permission_callback' => 'pibridge_can_operate',
    ]);

    register_rest_route(PIBRIDGE_NS, '/alarm', [
        'methods' => 'POST',
        'callback' => fn(WP_REST_Request $req) => pibridge_request(
            'POST', '/api/alarm', ['action' => $req->get_param('action')]
        ),
        'permission_callback' => 'pibridge_can_operate',
    ]);

    // Slusanje je prekidac: start otvara sesiju na Piju, stop je zatvara i
    // vraca snimku. Oba poziva su kratka - Pi ne drzi vezu dok snima.
    register_rest_route(PIBRIDGE_NS, '/listen-start', [
        'methods' => 'POST',
        'callback' => fn() => pibridge_request('POST', '/api/listen/start'),
        'permission_callback' => 'pibridge_can_operate',
    ]);

    register_rest_route(PIBRIDGE_NS, '/listen-stop', [
        'methods' => 'POST',
        'callback' => fn() => pibridge_audio_request('POST', '/api/listen/stop', null, 'application/octet-stream', 30),
        'permission_callback' => 'pibridge_can_operate',
    ]);
});

/**
 * Proslijedi sirovo tijelo Pi-ju i vrati njegov JSON odgovor kakav je.
 */
function pibridge_request_passthrough(
    string $endpoint,
    string $raw_body,
    string $content_type
): WP_REST_Response|WP_Error {
    $pi_url = trim((string) get_option('pibridge_pi_url', ''));
    if (!$pi_url) {
        return new WP_Error('pibridge_not_configured', 'Pi URL nije postavljen (Settings -> PiBridge).', ['status' => 500]);
    }
    $response = wp_remote_post(rtrim($pi_url, '/') . $endpoint, [
        'timeout' => 15,
        'headers' => [
            'X-Api-Key' => (string) get_option('pibridge_api_token', ''),
            'Content-Type' => $content_type,
        ],
        'body' => $raw_body,
    ]);

    if (is_wp_error($response)) {
        return new WP_Error('pibridge_unreachable', 'Ne mogu se spojiti na Pi: ' . $response->get_error_message(), ['status' => 502]);
    }
    $code = wp_remote_retrieve_response_code($response);
    if ($code === 401) {
        return new WP_Error(
            'pibridge_bad_token',
            'Pi je odbio token. Provjeri da je API token u Settings -> PiBridge identican onome na Pi-ju.',
            ['status' => 502]
        );
    }
    return new WP_REST_Response(json_decode(wp_remote_retrieve_body($response), true), $code);
}

// --------------------------------------------------------------------------
// Shortcode [pibridge_panel]
// --------------------------------------------------------------------------

add_shortcode('pibridge_panel', function () {
    if (!pibridge_can_operate()) {
        return '<p class="pibridge-denied">Nemaš pristup ovoj kontroli.</p>';
    }

    // Verzija iz vremena izmjene datoteke - fiksni string znaci da operateri
    // nakon svakog uploada jos danima vrte staru verziju iz browser cachea.
    $css = plugin_dir_path(__FILE__) . 'assets/panel.css';
    $js = plugin_dir_path(__FILE__) . 'assets/panel.js';
    wp_enqueue_style('pibridge', plugins_url('assets/panel.css', __FILE__), [], (string) (filemtime($css) ?: '1.0.0'));
    wp_enqueue_script('pibridge', plugins_url('assets/panel.js', __FILE__), [], (string) (filemtime($js) ?: '1.0.0'), true);
    wp_localize_script('pibridge', 'pibridgeBridge', [
        'restUrl' => esc_url_raw(rest_url(PIBRIDGE_NS)),
        'nonce' => wp_create_nonce('wp_rest'),
    ]);

    return '<div id="pibridge-panel" class="pibridge-panel">Učitavam...</div>';
});

// Izuzmi stranicu sa shortcodeom iz page-cache dodataka (WP-Optimize i sl.) -
// panel svejedno crta zivo stanje preko JS-a, ovo je dodatna sigurnost.
add_action('template_redirect', function () {
    if (is_singular()) {
        $post = get_post();
        if ($post && has_shortcode($post->post_content, 'pibridge_panel')) {
            nocache_headers();
        }
    }
});
