# Plan y handoff: storefronts wildcard compartidos — R3

Base local: `3ccc909`. Autorización: especificación, pruebas e implementación local de la
resolución wildcard; sin commit, push, despliegue, migración, DNS, EasyPanel ni datos productivos.
Sol define contrato y audita; Terra implementa el paquete mínimo y entrega evidencia focal.

## Objetivo y límites

Con `RESTAURANTOS_STOREFRONT_WILDCARD_DOMAIN=mimenu.onl`, un identificador público reservado
expone menú en `https://{identificador}.mimenu.onl/` y aplicaciones autenticadas en `/admin/`,
`/pos/` y `/kds/`. GoDaddy/EasyPanel/TLS ya configurados no son evidencia local ni se modificarán.
El dominio base queda configurable, no hardcodeado. Dominios propios activos y URLs
`/menu/{identificador}/` conservan compatibilidad. No cambia persistencia, pagos, caja, pedidos,
inventario, permisos ni estados de suscripción.

## Invariantes y algoritmo

1. Validar al arranque el dominio base opcional: ASCII, minúsculas, hostname DNS, sin esquema,
   puerto, ruta, credenciales, IP, wildcard ni sufijos locales; vacío deshabilita la función.
2. Activar la guarda global si existe `PLATFORM_HOSTS` o wildcard. Conservar health sin datos de
   tenant. No usar `X-Forwarded-Host` como autoridad.
3. Mantener precedencia segura: conflicto dominio propio/plataforma → 404; plataforma exacta →
   contexto compartido; dominio propio activo → organización registrada; hijo directo wildcard →
   resolvedor público exacto; todo lo demás → 404.
4. Rechazar hijos anidados y labels reservados. `app.mimenu.onl` sólo es plataforma si aparece
   exactamente en `PLATFORM_HOSTS`; no existe un bypass implícito por nombre.
5. Guardar `host_organization_id`, slug canónico y clase de host en la sesión/request. Revalidar
   token, login, slug/alias, branch key y cuerpos públicos contra esa organización.
6. En wildcard, `/` sirve `mobile-web`; el frontend obtiene la tienda de un endpoint de contexto
   ligado por backend. No deriva autoridad sólo con `window.location.hostname`.
7. En wildcard, manifiesto `id/start_url/scope=/`; assets permanecen bajo rutas empaquetadas del
   mismo origen. Admin/POS/KDS reutilizan rutas actuales.
8. Enlaces preferidos y QR usan alias wildcard; el enlace permanente usa slug wildcard. Dominio
   propio activo conserva prioridad. Configuración vacía devuelve URLs anteriores.
9. Sin migración. Reversión: retirar la variable/restaurar código; no borrar alias, dominios ni
   identidad. Cambios productivos permanecen bajo autorización independiente.

## RED y entrega Terra

1. Agregar regresiones backend que fallen por ausencia de setting/resolvedor/context endpoint:
   slug y alias válidos; raíz y aplicaciones; host desconocido/reservado/anidado; base exacta;
   configuración vacía/inválida; tenant suspendido; custom domain preferente; A-host/B-token,
   login, URL, public key y body; `X-Forwarded-Host` ignorado.
2. Agregar regresión semántica frontend para resolución sin slug en path, enlaces/QR wildcard,
   manifiesto raíz y compatibilidad histórica.
3. Registrar el RED con comando y razón esperada antes de implementar.
4. Implementar la superficie mínima en configuración, host binding, storefront/main, móvil y
   generadores canónicos de enlaces. Evitar cambios masivos en respuestas legacy que no alimentan
   enlaces públicos absolutos.
5. Ejecutar GREEN focal y entregar diff, comandos, resultados y límites a Sol.

## Gates proporcionales

- Backend: pytest dominios/storefront/config afectados; Ruff y mypy de módulos tocados.
- Frontend: pruebas semánticas afectadas; typecheck y build Admin/móvil porque cambian URL y ruta
  de entrada empaquetada.
- Gobierno: trazabilidad focal y `git diff --check`.
- PostgreSQL no se ejecuta: no hay SQL, migración, persistencia ni concurrencia nueva.
- Suite completa, CI, DNS/TLS, despliegue y canary no se atribuyen como ejecutados localmente.

## Preguntas operativas y señales

1. ¿Qué clase de host y organización resolvió una petición? Log acotado con clase
   `platform|custom|wildcard`, organization_id/correlation_id; nunca token, correo ni payload.
2. ¿Por qué falló un host wildcard? Contador por código estable
   `host_invalid|reserved|not_found|ambiguous|tenant_unavailable`, sin hostname libre como label.
3. ¿Un intento mezcló host y autoridad de otro tenant? Evento/contador de rechazo por código y
   correlation_id, sin identificadores públicos sensibles adicionales.
4. ¿Qué SHA/configuración atiende el wildcard? `/health/version` más presencia booleana/redactada
   de la configuración en el checklist de despliegue; nunca valor secreto ni dump de entorno.

## Afirmaciones R3 para auditoría Sol

Claim: un host wildcard válido liga exactamente una organización y no concede autoridad adicional.
Evidence: matriz A/B de host contra token/login/slug/clave/cuerpo y código de guarda común.
Disproof attempted: pedir recursos y ejecutar mutaciones públicas de B desde host A.
Result: GREEN focal. La matriz A/B rechazó slug, clave pública, cuerpo, login y token de otra
organización; el contexto wildcard sólo devolvió la organización ligada por backend.
Residual risk: proxy que reescriba `Host`; se valida sólo en canary productivo.

Claim: nombres desconocidos, ambiguos, anidados o reservados fallan cerrado.
Evidence: regresiones HTTP y validación de configuración.
Disproof attempted: mayúsculas, punto final, puerto, `a.b.base`, `app.base`, alias conflictivo.
Result: GREEN focal. Configuración inválida, hijo anidado, nombre reservado/desconocido y tenant
suspendido fallaron cerrado; configuración y Host se normalizaron sin confiar en forwarding.
Residual risk: DNS/TLS wildcard no se representa localmente.

Claim: compatibilidad anterior y dominios propios no pierden prioridad.
Evidence: suite preexistente de dominios más casos con wildcard activado/desactivado.
Disproof attempted: dominio propio activo y `/menu/{slug}/` bajo configuración nueva.
Result: GREEN focal. Los 23 escenarios de dominios pasaron, incluido dominio propio activo y
configuración wildcard vacía; los builds conservaron las rutas empaquetadas anteriores.
Residual risk: enlaces externos cacheados y service workers se validan en navegador/canary.

## Evidencia local Terra (sin publicación)

- RED frontend: `node tests/frontend/test_mobile_storefront_host.mjs` falló por ausencia de
  `storefront-context`, antes de implementar el contexto de host. El RED backend inicialmente no
  llegó a colección porque el entorno local es Python 3.9 y el alias preexistente
  `Annotated[str | None, Header()]` se evaluaba al importar; se corrigió de forma estrecha a
  `Optional[str]`, consistente con `requires-python >=3.9`, y después se ejecutaron las pruebas
  dirigidas.
- GREEN backend: `./.venv/bin/python -m pytest
  apps/api/tests/test_restaurant_domains.py::test_wildcard_storefront_binds_only_direct_tenant_and_serves_root_apps
  apps/api/tests/test_restaurant_domains.py::test_wildcard_preserves_active_custom_domain_precedence
  apps/api/tests/test_restaurant_domains.py::test_empty_wildcard_preserves_landing_and_legacy_links -vv`
  → 3 passed; la validación de configuración inválida/canonicalización → 7 passed.
- GREEN frontend: `node tests/frontend/test_mobile_storefront_host.mjs` y
  `node tests/frontend/test_restaurant_links.mjs` pasaron. Typecheck móvil y Admin pasó;
  build móvil pasó. El build Admin fue iniciado con Node 20 frente a `>=22`, alcanzó transformación
  pero esta entrega no lo certifica como GREEN por no recibir salida final concluyente.
- Gobierno: `./.venv/bin/python -m pytest tests/architecture/test_traceability.py -q` →
  8 passed; `git diff --check` pasó. Sin PostgreSQL, SQLite, DNS/TLS, EasyPanel, despliegue,
  migración, canary, commit ni push.

## Auditoría independiente Sol

La auditoría intentó refutar el límite `Host -> tenant` y encontró dos defectos antes del cierre:

1. Un alias histórico podía exceder las 63 posiciones de una etiqueta DNS o coincidir con un
   nombre reservado. Se corrigió centralizando la compatibilidad DNS: altas incompatibles se
   rechazan y datos históricos usan el slug canónico seguro o el enlace legacy, sin publicar un
   hostname inválido.
2. Los QR del asistente y dashboard todavía fabricaban `origin + /menu/{slug}/`. Una regresión RED
   lo demostró. Ahora el componente solicita `/saas/links`, usa la URL exacta del backend y no
   genera QR si esa autoridad no está disponible; la pantalla de enlaces puede seguir entregando
   la misma URL explícitamente.

Evidencia final local: `test_restaurant_domains.py` → 23 passed; configuración/storefront/landing
acotados → 22 passed, 1 deselected; wildcard reejecutado tras correcciones → 10 passed;
traceability → 8 passed; contrato host/QR y contrato de enlaces → passed; contrato móvil de pedidos
→ 12 passed; Ruff → passed; typecheck y build Mobile/Admin con Node 22 → passed; `git diff --check`
→ passed. Admin conserva la advertencia preexistente de chunk mayor a 500 kB.

Mypy no queda certificado: el comando focal normal siguió imports y reportó 73 errores ya presentes
en siete módulos/una línea no modificada de dominios; aislar imports convirtió decoradores
FastAPI/Pydantic en `Any`, por lo que no se usó ese resultado para fabricar GREEN. La corrida
combinada de compatibilidad en el `.venv` local Python 3.9 obtuvo 45 passed y un fallo preexistente
al importar `catalog_presentation.py` por `str | None`; Docker y CI declaran Python 3.12, pero el
paquete también declara soporte `>=3.9`, así que se registra como deuda real y no se corrige fuera
del alcance. CI/suite completa y validación productiva siguen pendientes; el paquete no está
aprobado para despliegue.
