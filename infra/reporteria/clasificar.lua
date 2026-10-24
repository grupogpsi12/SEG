-- =============================================================================
-- Clasifica cada línea de log que llega desde Docker.
--
--   waf        -> eventos de ModSecurity (ataques detectados o bloqueados)
--   proteccion -> baneos y bloqueos de BunkerWeb (bad behavior, límites,
--                 listas negras, antibot)
--   acceso     -> log de acceso de NGINX (una línea por petición)
--   sistema    -> todo lo demás (arranque, scheduler, recargas...)
-- =============================================================================

local function contiene(texto, fragmento)
  return string.find(texto, fragmento, 1, true) ~= nil
end

-- JML (revision del 24/10/2026): ModSecurity escribe el valor que disparo la regla. Si el campo es
-- un restringido o una credencial (invariante 5, RS-09), el valor no viaja a Loki; se conservan la
-- variable y la regla, que es lo que sirve para investigar. Mismas palabras que los logs de la
-- aplicacion (jml/adaptadores/registro.py), mas `codigo` (el TOTP).
local SENSIBLES = {
  "password", "contrasena", "token", "totp", "secret", "motivo", "descripcion", "codigo",
}
local FILTRADO = "[filtrado]"

local function sensible(variable)
  local v = string.lower(variable)
  for _, palabra in ipairs(SENSIBLES) do
    if contiene(v, palabra) then
      return true
    end
  end
  return false
end

local function tapar(linea)
  -- `against variable `ARGS:motivo' (Value: `...' )`
  linea = string.gsub(linea, "(against variable `)([^']+)(' %(Value: `)(.-)(' %))",
    function(a, variable, b, valor, c)
      if sensible(variable) then
        return a .. variable .. b .. FILTRADO .. c
      end
      return nil
    end)
  -- `[data "Matched Data: ... found within ARGS:motivo: ..."]`
  linea = string.gsub(linea, '(%[data "Matched Data: )(.-)( found within )([^:"]+:[^:"]+)(: )(.-)("%])',
    function(a, dato, b, variable, c, valor, d)
      if sensible(variable) then
        return a .. FILTRADO .. b .. variable .. c .. FILTRADO .. d
      end
      return nil
    end)
  return linea
end

-- Formato de acceso por defecto de BunkerWeb:
-- $host $remote_addr - $request_id $remote_user [$time_local] "$request" $status ...
local PATRON_ACCESO = '^%S+ %S+ %- %S+ %S+ %[[^%]]+%] "'

local MARCAS_PROTECCION = {
  "[badbehavior]", "[bad-behavior]", "[limit]", "[blacklist]",
  "[antibot]", "[dnsbl]", "[country]", "[bunkernet]", " is banned", "banned for",
}

function clasificar(tag, timestamp, record)
  local linea = record["log"]
  if type(linea) ~= "string" then
    return -1, timestamp, record            -- sin texto: se descarta
  end

  linea = string.gsub(linea, "[\r\n]+$", "")
  if linea == "" then
    return -1, timestamp, record            -- línea vacía: se descarta
  end

  local contenedor = record["container_name"] or "desconocido"
  contenedor = string.gsub(contenedor, "^/", "")

  local tipo = "sistema"
  local minusculas = string.lower(linea)

  if contiene(linea, "ModSecurity: ") then
    tipo = "waf"
    linea = tapar(linea)
  elseif string.find(linea, PATRON_ACCESO) then
    tipo = "acceso"
  else
    for _, marca in ipairs(MARCAS_PROTECCION) do
      if contiene(minusculas, marca) then
        tipo = "proteccion"
        break
      end
    end
  end

  -- 2 = registro modificado, se conserva la marca de tiempo original
  return 2, timestamp, { log = linea, contenedor = contenedor, tipo = tipo }
end
