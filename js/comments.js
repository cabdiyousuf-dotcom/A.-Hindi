/* ------------------------------------------------------------------
   Responses — Cusdis comment widget.

   The widget script is fetched only when a reader clicks through, so
   the page weighs exactly what it did before for everyone else.

   To switch comments on: replace APP_ID below with the App ID from
   your Cusdis dashboard. Until that is done the whole section stays
   hidden, so nothing half-built ever shows on the live site.
   ------------------------------------------------------------------ */
(function () {
  'use strict';

  var APP_ID = '24357256-ca8f-4fa3-b2ed-f7e94774fe38';
  var HOST   = 'https://cusdis.com';

  var section = document.getElementById('responses');
  if (!section) return;

  var button = document.getElementById('responses-open');
  var thread = document.getElementById('cusdis_thread');
  if (!button || !thread) return;

  // The section ships hidden: it is revealed only once an App ID is set
  // and JavaScript is running, so a reader never meets a dead button.
  if (APP_ID.indexOf('PASTE_') === 0) return;
  section.hidden = false;

  var loaded = false;
  button.addEventListener('click', function () {
    if (loaded) return;
    loaded = true;

    button.setAttribute('aria-expanded', 'true');
    button.hidden = true;

    thread.setAttribute('data-host', HOST);
    thread.setAttribute('data-app-id', APP_ID);
    thread.hidden = false;

    var s = document.createElement('script');
    s.async = true;
    s.defer = true;
    s.src = HOST + '/js/cusdis.es.js';
    document.body.appendChild(s);
  });
})();
