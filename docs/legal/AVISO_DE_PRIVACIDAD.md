# AVISO DE PRIVACIDAD INTEGRAL — PLATAFORMA POS-SAAS (MI MENÚ)

**Fecha de última actualización:** Octubre de 2026

**[RAZÓN SOCIAL / NOMBRE DEL TITULAR]** (en lo sucesivo denominada la **"Plataforma"**, el **"SaaS"** o el **"Responsable"**), con portal de internet en **https://mimenu.onl** (o el dominio institucional que en el futuro lo sustituya), con domicilio fiscal ubicado en **[DOMICILIO FISCAL COMPLETO, CIUDAD, ESTADO, C.P., MÉXICO]**, y correo electrónico de contacto para protección de datos: **privacidad@mimenu.onl**, en estricto cumplimiento de la **Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)**, su Reglamento y los Lineamientos del Aviso de Privacidad, pone a su disposición el presente Aviso de Privacidad Integral.

---

## 1. Distinción de Roles Jurídicos en el Tratamiento de Datos

La Plataforma opera una arquitectura tecnológica en la nube (*Software as a Service - SaaS* multi-inquilino) que interactúa con dos categorías diferenciadas de titulares:

1. **Clientes Comerciales (Restaurantes, Cafeterías, Fondas y Negocios Gastronómicos Afiliados):**
   * Respecto de los datos personales de los representantes legales, administradores, supervisores y operadores de sucursal de los restaurantes, la Plataforma actúa en calidad de **Responsable** directo del tratamiento.
2. **Consumidores y Comensales Finales (Clientes de los Restaurantes Afiliados):**
   * El restaurante afiliado actúa como **Responsable principal** de recabar los datos de sus clientes al recibir sus órdenes de consumo y facturación.
   * La Plataforma actúa primordialmente en calidad de **Encargada del Tratamiento**, procesando dichos datos por cuenta, orden y bajo instrucción técnica del restaurante para la emisión de comandas, cálculo de totales, enlaces de pedido a WhatsApp y timbrado fiscal mediante autofacturación.

---

## 2. Datos Personales Recabados

### A. De los Titulares y Administradores de Restaurantes (B2B):
* **Identificación y contacto:** Nombre completo, correo electrónico corporativo, número de teléfono / WhatsApp, cargo o rol asignado (dueño, supervisor, cajero).
* **Del Comercio:** Nombre comercial, razón social, logotipo, domicilio de la sucursal, horarios de atención, números de atención a clientes.
* **Fiscales y Facturación:** RFC, Constancia de Situación Fiscal, Cédula de Identificación Fiscal, régimen fiscal, domicilio fiscal y Certificados de Sello Digital (CSD) para timbrado fiscal desatendido.
* **Financieros y Pago de Suscripción:** Información de transacciones y tarjetas bancarias tokenizadas mediante pasarelas de pago seguras (Mercado Pago / Stripe). La Plataforma no almacena en texto plano datos completos de tarjetas de crédito/débito ni códigos CVV.

### B. De los Comensales y Clientes Finales (B2B2C):
* **Gestión de Órdenes:** Nombre o alias, número telefónico celular (utilizado para vincular el pedido por WhatsApp), dirección de entrega, referencias geográficas o coordenadas GPS de entrega (en caso de entrega a domicilio autorizada por el usuario).
* **Autofacturación 1-Click (CFDI 4.0):** Nombre o Razón Social, RFC, Código Postal del domicilio fiscal, Régimen Fiscal, Uso de CFDI y correo electrónico receptor de los archivos XML y PDF.
* **DATOS PERSONALES SENSIBLES RELATIVOS A LA SALUD (Alergias e Intolerancias):**
  * Si el comensal decide voluntariamente redactar notas de pedido señalando condiciones médicas, diabetes, celiaquía, alergias alimentarias graves (por ejemplo a cacahuates, mariscos, gluten, lácteos, etc.), dichos datos tienen el carácter legal de **Datos Sensibles**.
  * **Finalidad Restrictiva:** Estos datos sensibles son tratados exclusivamente para transmitirse en tiempo real a la pantalla de cocina (KDS) o ticket de comanda del restaurante a efecto de que el personal de cocina conozca las restricciones de preparación solicitadas. La Plataforma no realiza tratamientos secundarios ni comercialización de datos sensibles de salud.

---

## 3. Finalidades del Tratamiento

### Finalidades Primarias (Indispensables para el Servicio):
1. Aprovisionar y autenticar la cuenta de usuario y sucursal dentro del entorno multi-tenant.
2. Permitir el alta, administración y despliegue del catálogo de productos, modificadores y precios.
3. Procesar órdenes en mostrador, mesas, pedidos para llevar y pedidos a domicilio generados desde el menú digital web.
4. Generar y estructurar el mensaje y comanda digital para el envío de pedidos mediante WhatsApp.
5. Operar los cortes de caja (X y Z), arqueos y auditoría de turnos de punto de venta (POS).
6. Facilitar la autofacturación fiscal CFDI 4.0 mediante código QR impreso en el ticket de compra y conexión con el PAC (Proveedor Autorizado de Certificación).
7. Gestionar el cobro recurrente de la suscripción SaaS contratada por el restaurante.
8. Garantizar la seguridad, integridad, aislamiento multi-tenant y soporte técnico continuo de la plataforma.

### Finalidades Secundarias:
1. Envío de boletines informativos sobre nuevas funcionalidades, actualizaciones de seguridad o mejoras operativas del sistema.
2. Elaboración de métricas estadísticas globales, agregadas y disociadas de rendimiento de software.

*(El titular podrá oponerse al tratamiento para finalidades secundarias mediante correo electrónico a privacidad@mimenu.onl).*

---

## 4. Transferencias de Datos Personales

La Plataforma no vende, comercializa ni arrienda datos personales. Para la operatividad técnica del servicio, se realizan transferencias con terceros en los términos del artículo 37 de la LFPDPPP:
1. **Pasarelas de Pago:** Proveedores como Mercado Pago o Stripe para el cobro de planes de suscripción.
2. **Proveedores de Facturación (PAC):** Para el timbrado y validación oficial ante el Servicio de Administración Tributaria (SAT).
3. **Plataformas de Mensajería:** Infraestructura de Meta / WhatsApp Business para la transmisión de las comandas y notificaciones solicitadas.
4. **Infraestructura Cloud:** Proveedores de cómputo en la nube y bases de datos con altos estándares de cifrado y aislamiento.
5. **Autoridades Competentes:** En cumplimiento de leyes o mandatos judiciales debidamente fundados y motivados.

---

## 5. Medidas de Seguridad y Aislamiento de Información

* **Aislamiento Multi-Tenant Estricto:** Toda información se encuentra compartimentada por `organization_id`. Ningún restaurante o comensal puede consultar datos pertenecientes a otra cuenta.
* **Cifrado de Comunicaciones:** Transmisiones protegidas mediante protocolos criptográficos TLS/HTTPS.
* **Seguridad de Contraseñas:** Algoritmos de dispersión criptográfica unidireccional (*hash* y salting).
* **Inmutabilidad de Auditoría:** Trazabilidad estricta en registros de turnos, cancelaciones y movimientos de caja.

---

## 6. Ejercicio de Derechos ARCO y Revocación del Consentimiento

Todo titular goza del derecho de solicitar el **Acceso, Rectificación, Cancelación u Oposición (Derechos ARCO)** respecto a sus datos personales, así como a revocar el consentimiento previamente conferido.

**Procedimiento:**
1. Enviar solicitud al correo: **privacidad@mimenu.onl**.
2. Indicar: Nombre completo, correo electrónico registrado, relación con la Plataforma (dueño de restaurante, operador o comensal), descripción clara del derecho a ejercer y documento que acredite la identidad del solicitante.
3. El Responsable responderá en un plazo máximo de **20 días hábiles** a partir de la recepción completa de la solicitud.

---

## 7. Deslinde Sanitario y de Responsabilidad sobre Alimentos y Precios

La Plataforma hace constar de forma expresa y transparente que:
1. **Naturaleza del Servicio:** La Plataforma es única y exclusivamente un proveedor de tecnología de la información y software SaaS. En ningún momento la Plataforma manipula, prepara, almacena, empaca, distribuye, certifica ni expende alimentos o bebidas.
2. **Inocuidad y Alérgenos:** La preparación, higiene, temperatura, ingredientes, presencia de alérgenos y advertencias sanitarias son responsabilidad exclusiva e indelegable del restaurante afiliado.
3. **Precios y Promociones:** El contenido del catálogo, fotos, descripciones, precios, impuestos y promociones son configurados directamente por el restaurante. La Plataforma no responde por errores u omisiones comerciales del comercio.

---

## 8. Modificaciones al Aviso de Privacidad

La Plataforma podrá modificar el presente Aviso de Privacidad en cualquier momento. Toda actualización será publicada y consultable de forma permanente en **https://mimenu.onl/admin/privacy** y dentro del apartado legal de la aplicación.
