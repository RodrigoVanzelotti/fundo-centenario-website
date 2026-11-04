const fs = require('fs');
const path = require('path');
const assert = require('assert');
const crypto = require('crypto');

const routes = ['quem-somos', 'quem-apoia', 'projetos'];
const programs = ['edital-de-projetos', 'programa-bolsa-de-permanencia'];
const pages = ['', 'como-apoiar', ...routes, ...programs];
const sitemap = fs.readFileSync('frontend/sitemap.xml', 'utf8');
const css = fs.readFileSync('frontend/assets/css/institutional.css', 'utf8');
const cssVersion = crypto.createHash('sha256').update(css).digest('hex').slice(0, 12);

for (const page of pages) {
  const file = path.join('frontend', page, 'index.html');
  const html = fs.readFileSync(file, 'utf8');
  const nav = html.match(/<nav class="nav"[\s\S]*?<\/nav>/)[0];
  for (const route of routes) {
    assert(nav.includes(`href="/${route}/"`), `${file}: navigation to ${route}`);
  }
  assert.strictEqual((html.match(/<h1\b/g) || []).length, 1, `${file}: one main heading`);
  assert(!/\p{L}\?\p{L}|\?\?|\uFFFD/u.test(html.replace(/<[^>]*>/g, ' ')), `${file}: broken encoding`);
  for (const program of programs) {
    assert(!html.includes(`href="https://www.fundocentenario.com.br/${program}"`), `${file}: external internal page`);
  }

  for (const [, attr, value] of html.matchAll(/\b(href|src)="([^"]+)"/g)) {
    const url = new URL(value, `https://local.test/${page ? page + '/' : ''}`);
    if (url.origin !== 'https://local.test') continue;
    let target = path.join('frontend', decodeURIComponent(url.pathname));
    if (url.pathname.endsWith('/')) target = path.join(target, 'index.html');
    assert(fs.existsSync(target), `${file}: missing ${attr} target ${value}`);
    if (url.hash) {
      const content = fs.readFileSync(target, 'utf8');
      assert(content.includes(`id="${url.hash.slice(1)}"`), `${file}: missing anchor ${value}`);
    }
  }
  if (routes.includes(page) || programs.includes(page)) {
    const activeRoute = programs.includes(page) ? 'projetos' : page;
    assert(nav.includes(`href="/${activeRoute}/" aria-current="page"`));
    assert(html.includes('class="skip-link"'));
    assert(html.includes('/assets/css/institutional.css'));
    assert(html.includes(`/assets/css/institutional.css?v=${cssVersion}`), `${file}: outdated stylesheet version`);
    for (const name of ['reading-page', 'reading-content', 'reading-end', 'program-facts', 'application-steps', 'program-actions', 'program-note']) {
      if (new RegExp(`class="[^"]*\\b${name}\\b`).test(html)) {
        assert(new RegExp(`\\.${name}\\b`).test(css), `${file}: missing styles for ${name}`);
      }
    }
    assert(sitemap.includes(`https://fundocentenario.com.br/${page}/`));
  }
}

for (const page of ['', 'projetos']) {
  const html = fs.readFileSync(path.join('frontend', page, 'index.html'), 'utf8');
  for (const program of programs) {
    assert(html.includes(`href="/${program}/"`), `${page}: missing local program link`);
  }
}

const about = fs.readFileSync('frontend/quem-somos/index.html', 'utf8');
for (let year = 2019; year <= 2025; year++) {
  assert(about.includes(`<strong>${year}</strong>`), `Missing annual report: ${year}`);
}
console.log('institutional pages: navigation, assets, anchors, encoding and reports ok');
