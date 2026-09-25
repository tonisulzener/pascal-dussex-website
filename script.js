(function () {
  var BANDS = {
    'Soultrain': 'https://www.dussexsoultrain.ch/kalender',
    'Les trois Suisses': 'https://www.lestroissuisses.ch/tourdaten',
    'True Blue': 'https://www.trueblue-jazz.com/konzerte'
  };
  var MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

  var today = new Date();
  today.setHours(0, 0, 0, 0);

  var list = document.getElementById('gigs');
  var empty = document.getElementById('gigs-empty');
  var buttons = document.querySelectorAll('.filter');
  var gigs = [];
  var current = 'Alle';

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  function renderGig(g) {
    var d = new Date(g.date + 'T00:00:00');
    var li = el('li', 'gig');
    li.dataset.band = g.band;

    var date = el('div', 'gig__date');
    date.appendChild(el('div', 'gig__day', String(d.getDate()).padStart(2, '0')));
    date.appendChild(el('div', 'gig__month', MONTHS[d.getMonth()] + ' ' + d.getFullYear()));

    var info = el('div');
    info.appendChild(el('div', 'gig__place', g.place));
    if (g.venue) info.appendChild(el('div', 'gig__venue', g.venue));

    var link = el('a', 'gig__link', g.band + ' ↗');
    link.href = BANDS[g.band] || '#';
    link.target = '_blank';
    link.rel = 'noopener';

    li.appendChild(date);
    li.appendChild(info);
    li.appendChild(link);
    return li;
  }

  function applyFilter(band) {
    current = band;
    var visible = 0;
    Array.prototype.forEach.call(list.children, function (li) {
      var show = band === 'Alle' || li.dataset.band === band;
      li.hidden = !show;
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

  fetch('gigs.json', { cache: 'no-cache' })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      gigs = data
        .filter(function (g) { return new Date(g.date + 'T00:00:00') >= today; })
        .sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
      gigs.forEach(function (g) { list.appendChild(renderGig(g)); });
      applyFilter(current);
    })
    .catch(function () {
      empty.textContent = 'Die Termine konnten nicht geladen werden – bitte direkt auf den Band-Seiten nachschauen.';
      empty.hidden = false;
    });

  document.getElementById('year').textContent = today.getFullYear();
})();
