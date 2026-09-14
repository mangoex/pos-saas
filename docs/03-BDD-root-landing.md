# BDD: Portada pública por dispositivo

## Portada SaaS móvil compacta (vigente)

- En anchos de hasta 860 px, `/` muestra una portada estática con propuesta de valor,
  «Probar gratis 14 días» a `/admin/register?plan=trial` e «Iniciar sesión» a
  `/admin/login`, visibles sin recorrer una animación; beneficios y precio existente debajo.
- No hay redirección automática ni creación de sesión. Los enlaces usan el registro y login
  existentes; la portada no activa la prueba por sí misma.
- En una carga móvil no se monta el motor de scroll ni se solicita su video. Los enlaces
  funcionan también sin JavaScript. No debe haber desbordamiento horizontal a 320 px.
- Por encima de 860 px se conserva la presentación de escritorio. Cambiar el ancho entre
  ambas experiencias mantiene los accesos utilizables y monta el motor como máximo una vez.

> Comportamiento histórico sustituido para SaaS: la raíz actual ofrece adquisición y registro tanto en móvil como escritorio. La redirección móvil siguiente se conserva como evidencia anterior, no debe restaurarse para pasar tests SaaS.

## BDD-FEAT-095 Acceso institucional desde la raíz

```gherkin
@PRD-FR-731 @public-web
Feature: Selección aislada de la experiencia pública en la raíz

  @BDD-SC-456
  Scenario: Escritorio recibe la portada moderna
    Given un visitante de escritorio solicita la ruta raíz
    When el servidor selecciona la experiencia pública
    Then responde con la portada de Kiwi Natural
    And los enlaces internos conservan las rutas relativas de menú, Admin, POS y KDS
    And no inicia ni modifica una sesión operativa

  @BDD-SC-457
  Scenario: Teléfono entra directamente al menú público
    Given un teléfono solicita la ruta raíz
    When la señal móvil se identifica por Client Hint o agente de usuario
    Then el servidor redirige temporalmente a /menu/
    And no entrega los recursos pesados de la portada
    And la respuesta evita reutilización de caché entre móvil y escritorio

  @BDD-SC-458
  Scenario: Las aplicaciones operativas conservan sus rutas
    Given la portada de escritorio está incluida en la imagen desplegable
    When se solicitan /menu/, /admin/, /pos/, /kds/, /api/ o /health/
    Then cada solicitud conserva el manejador previo de su aplicación o servicio
    And la selección por dispositivo no se aplica fuera de la ruta raíz
```
