/* Bloquea el campo de asignacion que no corresponde al rol elegido.
 *
 * "Cliente asignado" solo tiene sentido para el rol CLIENTE y "Proveedor
 * asignado" solo para el rol PROVEEDOR; los roles sin alcance no usan ninguno.
 * El campo que no aplica se deshabilita y muestra "No aplica".
 *
 * Esto es una ayuda visual, no una barrera: el servidor vuelve a decidir que
 * asignacion guardar segun el rol recibido, asi que manipular el formulario no
 * sirve de nada. Si el navegador no ejecuta JavaScript, los dos campos quedan
 * habilitados y el servidor descarta igualmente el que no corresponde.
 */
(function () {
  "use strict";

  var NO_APLICA = "No aplica";

  // Que campo usa cada rol. Debe coincidir con ALCANCES en app/models.py.
  var CAMPO_DEL_ROL = {
    CLIENTE: "cliente_asignado",
    PROVEEDOR: "proveedor_asignado",
  };

  var rol = document.querySelector('select[name="rol"]');
  if (!rol) {
    return;
  }

  var cajas = {};
  var contenedores = document.querySelectorAll("[data-asignacion]");
  for (var i = 0; i < contenedores.length; i++) {
    var caja = contenedores[i];
    var nombre = caja.getAttribute("data-asignacion");
    var campo = caja.querySelector("input");
    if (!campo) {
      continue;
    }
    cajas[nombre] = {
      caja: caja,
      campo: campo,
      // Se recuerda lo que habia escrito para devolverlo si se vuelve al rol.
      valor: campo.value,
    };
  }

  function aplicar() {
    var activo = CAMPO_DEL_ROL[rol.value];
    for (var nombre in cajas) {
      if (!Object.prototype.hasOwnProperty.call(cajas, nombre)) {
        continue;
      }
      var c = cajas[nombre];
      if (nombre === activo) {
        if (c.campo.disabled) {
          c.campo.disabled = false;
          c.campo.value = c.valor;
        }
        c.caja.classList.remove("campo-bloqueado");
      } else {
        if (!c.campo.disabled) {
          // Solo se guarda lo que escribio el usuario, nunca el "No aplica".
          c.valor = c.campo.value;
        }
        c.campo.disabled = true;
        c.campo.value = NO_APLICA;
        c.caja.classList.add("campo-bloqueado");
      }
    }
  }

  rol.addEventListener("change", aplicar);
  aplicar();
})();
