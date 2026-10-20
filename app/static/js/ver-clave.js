/* Boton para mostrar u ocultar lo que se escribe en un campo de contrasena.
 *
 * Mejora progresiva: el boton lo crea este script, asi que si el navegador no
 * ejecuta JavaScript los formularios siguen funcionando igual y simplemente no
 * aparece el boton. No se guarda ni se envia nada: lo unico que cambia es el
 * atributo "type" del campo, que es lo que decide si el navegador dibuja puntos
 * o letras.
 */
(function () {
  "use strict";

  var VER = "Ver";
  var OCULTAR = "Ocultar";

  function montar(campo) {
    // Evita montar dos veces el mismo campo.
    if (campo.getAttribute("data-ver-clave") === "listo") {
      return;
    }
    campo.setAttribute("data-ver-clave", "listo");

    // El campo se envuelve para poder colocar el boton dentro del recuadro.
    var caja = document.createElement("span");
    caja.className = "clave-caja";
    campo.parentNode.insertBefore(caja, campo);
    caja.appendChild(campo);

    var boton = document.createElement("button");
    // type="button" es imprescindible: sin el, el boton enviaria el formulario.
    boton.type = "button";
    boton.className = "ver-clave";
    boton.tabIndex = -1;
    caja.appendChild(boton);

    function pintar(visible) {
      boton.textContent = visible ? OCULTAR : VER;
      boton.setAttribute("aria-pressed", visible ? "true" : "false");
      boton.setAttribute(
        "aria-label",
        visible ? "Ocultar la contrasena" : "Mostrar la contrasena"
      );
      boton.title = boton.getAttribute("aria-label");
    }

    function ocultar() {
      campo.type = "password";
      pintar(false);
    }

    pintar(false);

    boton.addEventListener("click", function () {
      // Cambiar el type mueve el cursor al final en algunos navegadores; se
      // guarda la posicion para devolverla y no estorbar a quien va escribiendo.
      var desde = null;
      var hasta = null;
      try {
        desde = campo.selectionStart;
        hasta = campo.selectionEnd;
      } catch (e) {
        /* algunos navegadores no permiten leer la seleccion de un password */
      }

      if (campo.type === "password") {
        campo.type = "text";
        pintar(true);
      } else {
        ocultar();
      }

      campo.focus();
      if (desde !== null) {
        try {
          campo.setSelectionRange(desde, hasta);
        } catch (e) {
          /* sin consecuencias: solo se pierde la posicion del cursor */
        }
      }
    });

    // Se vuelve a ocultar al enviar el formulario y al dejar de mirar la pagina,
    // para que una contrasena no se quede a la vista en pantalla.
    if (campo.form) {
      campo.form.addEventListener("submit", ocultar);
    }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) {
        ocultar();
      }
    });
  }

  var campos = document.querySelectorAll('input[type="password"]');
  for (var i = 0; i < campos.length; i++) {
    montar(campos[i]);
  }
})();
