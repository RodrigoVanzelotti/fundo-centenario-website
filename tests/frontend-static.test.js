const fs = require('fs');
const assert = require('assert');

const html = fs.readFileSync('frontend/como-apoiar/index.html', 'utf8');
const js = fs.readFileSync('frontend/assets/js/donation.js', 'utf8');

for (const label of [
  'Nome completo',
  'E-mail',
  'CPF',
  'Edital de projetos',
  'Programa de Bolsas de Permanência',
  'Programa de Mentoria',
  'Masterclasses e conteúdo Alumni',
  'Contribuição geral',
  'Pix pontual',
  'Pix Automático',
  'Cartão de crédito',
  'Contribuição mensal no cartão',
]) {
  assert(html.includes(label), `Missing UI label: ${label}`);
}

assert(js.includes('/api/donations/intents'));
assert(js.includes('/api/donations/options'));
assert(js.includes('/status'));
assert(js.includes('/finalize'));
console.log('frontend static checks: ok');
