(function () {
  var today = new Date();
  today.setHours(0, 0, 0, 0);

  // Vergangene Konzerte ausblenden
  var gigs = Array.prototype.slice.call(document.querySelectorAll('.gig'));
  gigs.forEach(function (gig) {
    var d = new Date(gig.dataset.date + 'T00:00:00');
    if (d < today) gig.dataset.past = 'true';
  });

  var buttons = document.querySelectorAll('.filter');
  var empty = document.getElementById('gigs-empty');

  function applyFilter(band) {
    var visible = 0;
    gigs.forEach(function (gig) {
      var show = gig.dataset.past !== 'true' && (band === 'Alle' || gig.dataset.band === band);
      gig.hidden = !show;
      if (show) visible++;
    });
    buttons.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.filter === band));
    });
    empty.hidden = visible > 0;
  }

  buttons.forEach(function (b) {
    b.addEventListener('click', function () { applyFilter(b.dataset.filter); });
  });
  applyFilter('Alle');

  document.getElementById('year').textContent = today.getFullYear();
})();
