(function () {
  // Hauptbands: eigener Filter-Knopf und Link zur Terminseite der Band
  var BANDS = {
    'Soultrain': 'https://www.dussexsoultrain.ch/kalender',
    'Les trois Suisses': 'https://www.lestroissuisses.ch/tourdaten',
    'True Blue': 'https://www.trueblue-jazz.com/konzerte'
  };
  // Alles andere (Bundesordner, Jazz-Selection, JOUB, Mario & Friends …) fällt unter diesen Filter
  var PROJECTS = 'Weitere Projekte';
  var MONTHS = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

  var today = new Date();
  today.setHours(0, 0, 0, 0);

  var list = document.getElementById('gigs');
  var empty = document.getElementById('gigs-empty');
  var buttons = document.querySelectorAll('.filter');
  var current = 'Alle';

  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt != null) e.textContent = txt;
    return e;
  }

  function day(iso) { return new Date(iso + 'T00:00:00'); }

  function slug(name) {
    return name.toLowerCase().replace(/&/g, 'und').replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }

  function renderGig(g) {
    var d = day(g.date);
    var li = el('li', 'gig');
    li.dataset.group = BANDS[g.band] ? g.band : PROJECTS;

    var date = el('div', 'gig__date');
    date.appendChild(el('div', 'gig__day', String(d.getDate()).padStart(2, '0')));
    date.appendChild(el('div', 'gig__month', MONTHS[d.getMonth()] + ' ' + d.getFullYear()));

    var info = el('div');
    info.appendChild(el('div', 'gig__place', g.place));
    if (g.venue) info.appendChild(el('div', 'gig__venue', g.venue));

    var link = el('a', 'gig__link', g.band + ' ↗');
    var href = g.url || BANDS[g.band];
    if (href) {
      link.href = href;
      link.target = '_blank';
      link.rel = 'noopener';
    } else {
      // Projekt ohne eigene Website (z.B. Mario & Friends): zur Projekt-Karte springen
      link.href = '#projekt-' + slug(g.band);
      link.textContent = g.band + ' ↓';
    }

    li.appendChild(date);
    li.appendChild(info);
    li.appendChild(link);
    return li;
  }

  function applyFilter(group) {
    current = group;
    var visible = 0;
    Array.prototype.forEach.call(list.children, function (li) {
      var show = group === 'Alle' || li.dataset.group === group;
      li.hidden = !show;
      if (show) visible++;
    });
    buttons.forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.dataset.filter === group));
    });
    empty.hidden = visible > 0;
  }

  buttons.forEach(function (b) {
    b.addEventListener('click', function () { applyFilter(b.dataset.filter); });
  });

  function getJSON(url) {
    return fetch(url, { cache: 'no-cache' }).then(function (r) {
      if (!r.ok) throw new Error(url + ': ' + r.status);
      return r.json();
    });
  }

  Promise.all([
    getJSON('gigs.json'),
    // Von Hand eingetragene Termine (Admin-Editor, z.B. Mario & Friends)
    getJSON('content/site.json').then(function (c) { return c.manual_gigs || []; }).catch(function () { return []; })
  ])
    .then(function (res) {
      res[0].concat(res[1])
        .filter(function (g) { return g && g.date && day(g.date_end || g.date) >= today; })
        .sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; })
        .forEach(function (g) { list.appendChild(renderGig(g)); });
      applyFilter(current);
    })
    .catch(function () {
      empty.textContent = 'Die Termine konnten nicht geladen werden – bitte direkt auf den Band-Seiten nachschauen.';
      empty.hidden = false;
    });

  document.getElementById('year').textContent = today.getFullYear();
})();
