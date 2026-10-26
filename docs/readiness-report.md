# Relatório de preparação — 16/10/2026

**Preparação local implementada e validada; lançamento não autorizado nem declarado
pronto.** Nenhum deploy, DNS, criação de recurso remoto, pagamento ou email real.
Alterações permanecem sem commit.

## Diagnóstico e decisões

A [auditoria inicial](architecture.md) registra evidências, severidade, plano e
dependências. Já existiam FastAPI, frontend totalmente estático, Firestore ADC com
transações, outbox/Scheduler, Docker não-root e GitHub Actions. Não houve troca de
framework, migração nova de banco ou alteração de contrato PSP. JSONL fica local.

Mudanças: Hosting serve arquivos diretamente e encaminha somente `/api/**`;
pinTag vincula revisão API à versão estática; staging executa antes da produção,
que exige dispatch e aprovação configurada no GitHub. Logs de request viraram JSON
sem PII, incluindo erros 413 com no-store e headers de segurança. Docs de API ficam
desabilitados também no staging. SEO recebeu canonical, Open Graph, robots e sitemap.

Timeout Run 180s preservado para emails via Scheduler nativo, sem worker permanente.
Limite Hosting 60s não serve de deadline global da aplicação; falhas/retries devem
manter a chave idempotente. Região inicial São Paulo exige aprovação institucional.

## Arquivos

| Grupo | Arquivos |
|---|---|
| Hosting/SEO | `firebase.json`, `frontend/index.html`, `frontend/como-apoiar/index.html`, `frontend/robots.txt`, `frontend/sitemap.xml` |
| Releases | `.github/workflows/ci.yml`, `deploy.yml`, novo `deploy-environment.yml` |
| API/validação | `backend/app/main.py`, `tools/smoke.py`, `tests/test_deployment.py`, `tests/hosting.test.js` |
| Configuração/documentação | `.env.example` como referência à fonte única `backend/.env.example`, `README.md`, `DEPLOYMENT.md`, `docs/architecture.md`, `docs/deployment.md`, `docs/operations.md`, `docs/migration-checklist.md`, este relatório |

Dockerfile, dockerignore, dependências, provider e persistência já atendiam à base
necessária e foram reaproveitados. `DEPLOYMENT.md` virou índice; seu procedimento
foi movido/adaptado para `docs/deployment.md`, evitando dois runbooks divergentes.

## Evidências executadas nesta revisão

| Verificação | Resultado |
|---|---|
| Python no venv Windows, Firestore emulator local obrigatório | 99 passaram; nenhum skip |
| Python 3.12 Linux, lock com hashes, emulator obrigatório | 99 passaram; nenhum skip; pip check sem conflitos |
| Node frontend-static e donation-steps | Ambos passaram |
| Firebase CLI 15.32.1 Hosting emulator, projeto demo | Teste HTTP de HTML, refresh, slash/query, assets, CSP/cache, recursos privados e 404 passou |
| Build Docker linux/amd64 | Passou; base/lock existentes preservados |
| Container PORT=8091, usuário 10001, exclusão de .env/JSONL na imagem | Passou |
| Imagem final PORT=8092, SERVE_FRONTEND=false, startup inválido e SIGTERM | Smoke API passou; `/` retorna 404; produção com config inválida recusada; encerramento exit 0 |
| Smoke HTTP API/páginas e POST webhook sem assinatura | Passou localmente, sem cobrança |
| pip-audit do lock | Nenhuma vulnerabilidade conhecida reportada |
| Trivy 0.75.0 | Sem HIGH/CRITICAL com correção disponível; não significa ausência de todo risco |
| actionlint 1.7.7 | Passou; shellcheck desabilitado nesse comando |
| Compileall, Compose config, lock check e git diff --check | Passaram |
| Revisão de diff e busca de padrões de credenciais nos arquivos rastreados | Sem matches para chaves live longas/privadas/Google API; sem JSONL/PII pública encontrada |

A primeira execução com Python global falhou por dependências Google ausentes.
Foi substituída pelo venv existente e pela instalação Linux do lock; não foi
classificada como falha da aplicação nem ocultada. Um arquivo `image.png` apareceu
no workspace durante o trabalho; não foi criado, alterado ou incluído nesta tarefa.

Cobertura de pagamentos preservada: validação, Pix/Checkout, pending, assinatura
válida/inválida, duplicação, concorrência, falha transacional, cadastro só após
confirmação, finalização autenticada, cartão hospedado, recorrência e falhas de email.
Pix Automático não é um fluxo disponível na implementação atual: teste confirma
rejeição, sem acrescentar um método não suportado pela integração.

Limites: emulator Hosting valida arquivos e configuração; não executa integração
real com Cloud Run no projeto demo. O smoke via web.app incluído no CD valida GET
e POST na nuvem após deploy autorizado. Não houve teste remoto de IAM, WIF,
pinTag/rollback, índices gerenciados, TLS/domínio, escala zero, Stripe ou SMTP.
Não houve Lighthouse, auditoria visual/mobile completa ou teste de carga remoto.
Não foi introduzido type checker/formatter Python novo para reformatar o projeto;
compilação, testes, actionlint e whitespace não equivalem a análise de tipos completa.

## Gates de produção

- [x] Artefato estático, container, contratos locais e persistência concorrente testados.
- [x] Deploy/rollback documentados, isolamento declarado, secrets fora do frontend.
- [ ] Inventariar/migrar páginas Wix e PDFs; aprovar redirects e Search Console.
- [ ] Aprovar região e criar projetos distintos, Blaze, Firestore, registry e identidades.
- [ ] Aplicar IAM mínimo, WIF restrito, Secret Manager versionado, rules/índices/TTL.
- [ ] Configurar required reviewers/branch protection e variables; validar pipeline staging.
- [ ] Verificar métodos Stripe test/live, webhooks e SMTP controlado de ponta a ponta.
- [ ] Ensaiar falha de dependências, recuperação/rollback em staging e escala zero real.
- [ ] Aprovar finalidade/retenção/eliminação de CPF, atendimento e política publicada.
- [ ] Testar backup/restauração, alertas e orçamento US$10 com 50/80/100%.
- [ ] Exportar DNS completo, validar Workspace, certificado e plano de reversão.
- [ ] Aprovar manualmente cutover e validar apex/www e fluxo de contribuição final.

O [runbook de deploy](deployment.md) contém comandos de preparação e permissões;
[operações](operations.md) contém observabilidade, retenção, backup, rollback e
estimativa **US$0–5/mês**, condicional às hipóteses/franquias, com orçamento US$10.
O [checklist de migração](migration-checklist.md) registra DNS observado e bloqueios.
Não se presume recurso, permissão ou benefício Google for Nonprofits existente.
