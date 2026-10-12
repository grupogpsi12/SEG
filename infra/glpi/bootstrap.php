<?php
// Arranque de GLPI para JML (item 3.1 / spike 0.3). IDEMPOTENTE: se puede repetir sin cambiar nada.
// Lo corre infra/glpi/preparar-glpi.sh dentro del contenedor `glpi` (`php < bootstrap.php`).
//
// Crea o completa: la API REST, el cliente de API «JML worker» (red `app` de compose) con su
// App-Token, el perfil acotado «JML - servicio» (T2), el usuario `jml-servicio` y su token, y el token
// del administrador `glpi`. GLPI 11 guarda estos tokens CIFRADOS; aqui se descifran para entregarlos.
//
// Salida: tres lineas, SIN nada mas: App-Token, token de `jml-servicio`, token de `glpi`.
//
// Derechos del perfil de servicio (valores de bits de GLPI). Lo que cuesta encontrar, spike 0.3:
//  - `slm` necesita el bit 256: sin el, GLPI ignora el vencimiento (`time_to_resolve`) que se le envia.
//  - `ticket` incluye READALL (1024) para ver los tickets de todos y PURGAR (16) para limpiar duplicados.
require '/var/www/glpi/vendor/autoload.php';
$kernel = new Glpi\Kernel\Kernel('production');
$kernel->boot();
global $DB;

$_SESSION['glpiID'] = 2;                                   // `glpi`, super-admin: quien configura
$_SESSION['glpiactiveprofile'] = ['id' => 4, 'interface' => 'central'];
$_SESSION['glpi_currenttime'] = date('Y-m-d H:i:s');

const LEER = 1; const ACTUALIZAR = 2; const CREAR = 4; const BORRAR = 8; const PURGAR = 16;
$clave = new GLPIKey();

// 1. API REST habilitada, SOLO con token de usuario. El inicio de sesion por usuario y clave en la
// API no pide el doble factor de la interfaz: queda apagado (auditoria del 12/10/2026).
Config::setConfigurationValues('core', [
    'enable_api' => 1,
    'enable_api_login_credentials' => 0,
    'enable_api_login_external_token' => 1,
]);

// Tamano maximo de un documento en GLPI: el soporte de vinculacion puede pesar 20 MB (RS-17).
Config::setConfigurationValues('core', ['document_max_size' => 20]);

// 2. Cliente de API para el worker: la red interna `app` de compose SIN la puerta de enlace
// (10.20.40.1) ni bunkerweb (10.20.40.2): lo que llega por el WAF no entra aunque traiga los
// tokens. Se reaplica en cada corrida (auditoria del 12/10/2026).
$rango = ['ipv4_range_start' => '10.20.40.3', 'ipv4_range_end' => '10.20.40.254'];
$cliente = new APIClient();
$existente = $cliente->find(['name' => 'JML worker']);
if ($existente) {
    $cid = (int) array_key_first($existente);
    $cliente->update(['id' => $cid] + $rango);
} else {
    $cid = $cliente->add([
        'name' => 'JML worker', 'is_active' => 1, 'entities_id' => 0,
        'comment' => 'worker y configurador (red app de compose, sin el WAF)', '_reset_app_token' => 1,
    ] + $rango);
}
$cliente->getFromDB($cid);
$app = $clave->decrypt($cliente->fields['app_token']);

// 3. Perfil de servicio: solo lo que usa el adaptador.
$perfil = new Profile();
$p = $perfil->find(['name' => 'JML - servicio']);
$pid = $p ? (int) array_key_first($p) : (int) $perfil->add([
    'name' => 'JML - servicio', 'interface' => 'central', 'is_default' => 0,
    'comment' => 'Cuenta de servicio del worker de JML: tickets, documentos, usuarios y lectura de activos',
]);
ProfileRight::updateProfileRights($pid, [
    'ticket' => LEER | ACTUALIZAR | CREAR | BORRAR | PURGAR | 1024,
    'slm' => LEER | 256,
    'followup' => LEER | CREAR,
    'document' => LEER | ACTUALIZAR | CREAR,
    'user' => LEER | ACTUALIZAR | CREAR,
    'computer' => LEER, 'license' => LEER, 'software' => LEER,
    'itilcategory' => LEER, 'group' => LEER, 'entity' => LEER, 'infocom' => LEER,
]);

// 4. Usuario de servicio: nadie conoce su contrasena, solo entra por su token de API.
$usuario = new User();
$u = $usuario->find(['name' => 'jml-servicio']);
if ($u) {
    $uid = (int) array_key_first($u);
} else {
    $azar = bin2hex(random_bytes(24));
    $uid = (int) $usuario->add([
        'name' => 'jml-servicio', 'password' => $azar, 'password2' => $azar, 'realname' => 'Servicio JML',
        'is_active' => 1, 'entities_id' => 0, '_profiles_id' => $pid, '_entities_id' => 0, 'authtype' => 1,
        'comment' => 'Cuenta de servicio del worker. Sin uso interactivo.',
    ]);
}
$vinculo = new Profile_User();
if (!$vinculo->find(['users_id' => $uid, 'profiles_id' => $pid])) {
    $vinculo->add(['users_id' => $uid, 'profiles_id' => $pid, 'entities_id' => 0, 'is_recursive' => 1]);
}

// 5. Tokens personales: se descifran si ya existen y se crean (cifrados) si faltan.
function token_de(int $id, GLPIKey $clave): string
{
    global $DB;
    $fila = $DB->request(['FROM' => 'glpi_users', 'WHERE' => ['id' => $id]])->current();
    if (!empty($fila['api_token'])) {
        return $clave->decrypt($fila['api_token']);
    }
    $nuevo = User::getUniqueToken('api_token');
    $DB->update('glpi_users', [
        'api_token' => $clave->encrypt($nuevo),
        'api_token_date' => date('Y-m-d H:i:s'),
    ], ['id' => $id]);
    return $nuevo;
}

echo $app, "\n", token_de($uid, $clave), "\n", token_de(2, $clave), "\n";
