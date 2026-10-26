// Run against the Firebase Hosting emulator; API rewrites need the staging smoke.
const assert = require('node:assert/strict');

(async () => {
  const base = process.env.HOSTING_TEST_URL || 'http://127.0.0.1:5000';
  for (const path of ['/', '/como-apoiar/', '/como-apoiar/?smoke=1']) {
    const response = await fetch(base + path);
    assert.equal(response.status, 200, path);
    assert.match(response.headers.get('content-security-policy'), /frame-ancestors 'none'/);
    assert.equal(response.headers.get('cache-control'), 'public, max-age=0, must-revalidate');
    assert.match(await response.text(), /rel="canonical"/);
  }
  const normalized = await fetch(base + '/como-apoiar?smoke=1');
  assert.equal(normalized.status, 200);
  assert.equal(new URL(normalized.url).pathname, '/como-apoiar/');
  assert.equal(new URL(normalized.url).search, '?smoke=1');
  for (const path of ['/missing-page', '/backend/.env', '/backend/data/confirmed_donations.jsonl']) {
    assert.equal((await fetch(base + path)).status, 404, path);
  }
  for (const path of ['/assets/css/site.css', '/assets/js/donation.js', '/robots.txt', '/sitemap.xml']) {
    assert.equal((await fetch(base + path)).status, 200, path);
  }
  console.log('Firebase Hosting static routes, refresh, query, headers and 404 checks: ok');
})().catch(error => { console.error(error); process.exitCode = 1; });
