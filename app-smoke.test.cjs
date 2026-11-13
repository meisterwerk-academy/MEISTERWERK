const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const inlineScript = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]).join('\n');
assert.ok(inlineScript.length > 1000, 'Inline-App-Script wurde gefunden');

function makeButton(page) {
  const listeners = {};
  const classes = new Set();
  return {
    dataset: { page },
    listeners,
    classList: {
      toggle(name, force) {
        const enabled = force === undefined ? !classes.has(name) : Boolean(force);
        if (enabled) classes.add(name); else classes.delete(name);
        return enabled;
      },
      contains(name) { return classes.has(name); }
    },
    addEventListener(type, callback) { listeners[type] = callback; },
    click() { listeners.click?.(); }
  };
}

function createApp({ initialStorage = null, failWrites = false } = {}) {
  let stored = initialStorage;
  const view = { innerHTML: '' };
  const crumb = { textContent: '' };
  const search = { value: '', listeners: {}, addEventListener(type, cb) { this.listeners[type] = cb; } };
  const navButtons = ['dashboard','lernen','pruefung','karten','fortschritt','profil','premium',
    'dashboard','lernen','pruefung','karten','fortschritt','profil'].map(makeButton);
  const document = {
    querySelector(selector) {
      if (selector === '#view') return view;
      if (selector === '#crumb') return crumb;
      if (selector === '#search') return search;
      return null;
    },
    querySelectorAll(selector) { return selector === '[data-page]' ? navButtons : []; },
    createElement() { throw new Error('createElement wurde im Smoke-Test unerwartet aufgerufen'); }
  };
  const localStorage = {
    getItem() { return stored; },
    setItem(_key, value) {
      if (failWrites) throw new Error('QuotaExceededError');
      stored = value;
    },
    removeItem() { stored = null; }
  };
  const context = {
    document, localStorage, navigator: {}, location: { protocol: 'file:' },
    window: { addEventListener() {} }, console, JSON, Number, Math, String, Array, Object,
    confirm: () => true, alert: () => {}
  };
  vm.createContext(context);
  vm.runInContext(inlineScript, context, { timeout: 2000, filename: 'meisterwerk-inline.js' });
  return {
    context, view, crumb, search, navButtons,
    get stored() { return stored; },
    run(code) { return vm.runInContext(code, context, { timeout: 2000 }); }
  };
}

test('Startseite wird gerendert und alle Navigationsziele sind verdrahtet', () => {
  const app = createApp();
  assert.match(app.view.innerHTML, /Willkommen bei MEISTERWERK/);
  for (const page of ['dashboard','lernen','pruefung','karten','fortschritt','profil','premium']) {
    const button = app.navButtons.find(b => b.dataset.page === page);
    assert.ok(button?.listeners.click, `Click-Handler für ${page} fehlt`);
    button.click();
    assert.ok(app.view.innerHTML.length > 0, `${page} rendert keinen Inhalt`);
  }
});

test('Lernakademie, Teilfilter und Lektion lassen sich öffnen', () => {
  const app = createApp();
  app.run("go('lernen')");
  assert.match(app.view.innerHTML, /Lernakademie/);
  app.run("filter='II'; learning()");
  assert.match(app.view.innerHTML, /Haarpigmente und Ergrauen/);
  app.run("openLesson('II-01')");
  assert.match(app.view.innerHTML, /Aufbau des menschlichen Haares/);
});

test('Abgeschlossene Lektion wird lokal gespeichert und nach Neustart geladen', () => {
  const app = createApp();
  app.run("openLesson('II-01'); markDone('II-01')");
  assert.match(app.view.innerHTML, /Als abgeschlossen markiert/);
  assert.ok(app.stored, 'localStorage wurde nicht beschrieben');
  const restarted = createApp({ initialStorage: app.stored });
  assert.equal(restarted.run("state.done.includes('II-01')"), true);
  assert.equal(restarted.run('progress()'), Math.round(100 / restarted.run('LESSONS.length')));
});

test('Prüfungstraining bewertet eine Antwort und aktualisiert die Statistik', () => {
  const app = createApp();
  app.run("startQuiz('II'); choose(QUESTIONS[0].c); submitAnswer()");
  assert.match(app.view.innerHTML, /Richtig beantwortet!/);
  assert.equal(app.run('state.answered'), 1);
  assert.equal(app.run('state.correct'), 1);
  assert.ok(app.stored);
});

test('Karteikarte lässt sich umdrehen und weiterblättern', () => {
  const app = createApp();
  const question = app.run('FLASH[0][0]');
  app.run('flipFlash()');
  assert.match(app.view.innerHTML, new RegExp(app.run('FLASH[0][1]').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  app.run('nextFlash()');
  assert.equal(app.run('flashIndex'), 1);
  assert.notEqual(question, app.run('FLASH[1][0]'));
});

test('Fehlerhafte gespeicherte Daten werden abgefangen', () => {
  const app = createApp({ initialStorage: '{kaputtes-json' });
  assert.match(app.view.innerHTML, /Willkommen bei MEISTERWERK/);
  assert.equal(app.run('state.done.length'), 0);
});

test('Nicht verfügbarer localStorage blockiert die Bedienung nicht', () => {
  const app = createApp({ failWrites: true });
  assert.doesNotThrow(() => app.run("openLesson('II-01'); markDone('II-01')"));
  assert.match(app.view.innerHTML, /Als abgeschlossen markiert/);
});

test('Responsive Breakpoints und Safe-Area-Abstand sind vorhanden', () => {
  assert.match(html, /@media\(max-width:720px\)/);
  assert.match(html, /env\(safe-area-inset-bottom\)/);
  assert.match(html, /\.mobile-nav\{display:none\}/);
});

test('Inhaltsumfang wird transparent inventarisiert', () => {
  const app = createApp();
  const inventory = app.run(`({lessons:LESSONS.length, partII:LESSONS.filter(x=>x.part==='II').length, questions:QUESTIONS.length, cards:FLASH.length, questionParts:Object.fromEntries(['I','II','III','IV'].map(p=>[p,QUESTIONS.filter(q=>q.part===p).length]))})`);
  console.log('INHALTSINVENTAR', JSON.stringify(inventory));
  assert.equal(inventory.partII, 8, 'Das Haarbiologie-Muster enthält acht Lektionen');
  assert.equal(inventory.questions, 40, 'Insgesamt sind 40 Übungsfragen vorhanden');
  assert.equal(inventory.cards, 40, 'Insgesamt sind 40 Karteikarten vorhanden');
  assert.equal(inventory.questionParts.II, 10, 'Derzeit sind 10 der 40 Fragen Teil II zugeordnet');
  assert.deepEqual(Object.keys(inventory.questionParts).sort(), ['I','II','III','IV']);
});
