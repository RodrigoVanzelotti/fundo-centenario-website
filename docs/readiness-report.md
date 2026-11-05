# Relatório de preparação

## Estado atual — configuração pelo CLI em 04/11/2026

**Infraestrutura configurada; staging e produção validados com acesso privado.
Email e Scheduler estão habilitados. O frontend público ainda não foi lançado
e nenhum agradecimento foi enviado nesta preparação.**

Conta institucional: `rodrigo.vanzelotti@fundocentenario.com.br`.
Organização `874989411514`. Os dois projetos estão vinculados ao faturamento
institucional ativo, final `CA259F`. Após autorização, o orçamento foi definido em
**R$60/mês**, abrangendo somente os dois projetos, com alertas de 50%, 80% e 100%,
canal de email institucional e destinatários padrão do faturamento. Não há
desligamento automático nem teto financeiro.

| Item | Staging | Produção |
|---|---|---|
| Projeto | `fundocentenario-website-stg` | `fundocentenario-website-prd` |
| Cloud Run nativo | `https://fundo-centenario-wouc4s5bsa-rj.a.run.app` | `https://fundo-centenario-o2dq7ckysa-rj.a.run.app` |
| Revisão verificada | `fundo-centenario-00003-2nj` | `fundo-centenario-00003-zp2` |
| Runtime | `APP_ENV=staging`, Firestore, Stripe test, email habilitado | `APP_ENV=production`, Firestore, Stripe live, email habilitado |
| Acesso anônimo | Bloqueado, HTTP 403 | Bloqueado, HTTP 403 |
| Firestore | Standard/Native `(default)`, São Paulo, vazio | Standard/Native `(default)`, São Paulo, vazio |
| Firebase Hosting | Site padrão criado; frontend não publicado | Site padrão criado; frontend não publicado |
| Scheduler | `fundo-thank-you`, ativo a cada cinco minutos | `fundo-thank-you`, ativo a cada cinco minutos |

Configurado e conferido nos dois projetos:

- APIs previstas, mais Monitoring, Logging e Budget API; Artifact Registry
  `fundo-images` em `southamerica-east1` e imagens publicadas por digest.
- Identidades runtime/deploy/Scheduler sem chaves JSON. Runtime tem Firestore e
  acesso aos quatro segredos individuais; deploy tem registry writer, Hosting,
  uso de serviços e identidade runtime, mais `run.developer` no serviço. Deploy
  lê apenas a chave Stripe, sem acesso direto aos cadastros.
- Regras Firestore publicadas com conteúdo idêntico ao `firestore.rules` deny-all;
  índice composto da outbox READY, duas políticas TTL ACTIVE por ambiente e as
  sete configurações de exclusão de índices conferidas contra o arquivo versionado.
- Backup diário com retenção de `604800s` (sete dias) em ambos, para permitir o
  ensaio em staging; PITR desligado. Ainda não havia backup disponível para restaurar.
- Scheduler configurado com POST na URL nativa, OIDC da conta exclusiva, audience
  nativa, cron de cinco minutos, deadline 180s e até três retries. Jobs ativos
  depois da validação SMTP e do processamento autenticado da outbox vazia.
- Alertas ativos de pelo menos cinco 5xx em cinco minutos e de logs ERROR do
  Scheduler, com canal de email institucional. Entrega de notificações ainda não
  ensaiada; monitor HTTPS público fica para a publicação do site.
- GitHub environments staging/production, Variables públicas (incluindo URLs Run),
  deploy restrito a main e WIF restrito ao repositório `1400597312`, proprietário
  `85701210`, main e environment correspondente. Produção exige revisão de
  `RodrigoVanzelotti` e impede self-review. Main exige PR, uma aprovação e CI `check`,
  sem force push ou exclusão. É necessário outro participante autorizado para
  revisar PRs e para o fluxo de aprovação sem self-review.

Segredos: chave Stripe test local validada pela API, guardada em staging na
versão `1`. Destino Stripe test `we_1UYEBDLvB10UbkB6RPoFkljK` criado na URL
nativa staging, API `2026-10-28.endive`, com os sete eventos; seu signing secret
foi guardado diretamente no Secret Manager, versão `1`, sem exibição do valor ou
arquivo local. O destino ainda não recebe entregas públicas porque o serviço
permanece privado; o aceite do pagamento via webhook continua pendente.
`smtp-username` foi preenchido nos dois ambientes com a caixa institucional.
A chave Stripe live fornecida no Secret Manager foi validada sem
criar pagamentos. O destino live `we_1UYEa1LvB10UbkB643sh4eiS` foi criado na URL
nativa de produção com a mesma API/eventos e seu segredo guardado na versão `1`.
Nenhum valor secreto está neste documento.

As primeiras versões de `smtp-password` não passaram no login e foram
substituídas pelo usuário. As versões `2` passaram no STARTTLS/login nos dois
ambientes; confirmou-se em memória que são senhas distintas. As versões `1` de
senha estão desabilitadas. `smtp-username` também recebeu versão `2` para alinhar
o par usado pelo workflow. Cloud Run referencia usuário/senha `:2`, Stripe `:1`;
GitHub usa `SMTP_SECRET_VERSION=2` e `EMAIL_ENABLED=true` em cada environment.
Não houve gravação de valores secretos em arquivos locais nem envio SMTP.

### Evidências desta execução

- Smoke remoto autenticado staging e produção passou, incluindo `/api/ready` com identidade
  runtime e Firestore real, headers, métodos e rejeição de webhook sem assinatura.
- Scheduler dos dois projetos foi primeiro testado sem email. Depois do login
  SMTP validado e da habilitação do email, cada callback retornou novamente HTTP
  200 com outbox vazia, validando OIDC e consulta Firestore. Os jobs ficaram ativos.
  Isso não comprova entrega de agradecimento na caixa de entrada.
- HTTP anônimo 403 e ausência de `allUsers`/`allAuthenticatedUsers` conferidos nos
  dois serviços. As URLs não constituem sites públicos neste estado.
- Bancos remotos verificados vazios por listagem de IDs de coleção, sem consultar
  dados de doadores. Não houve importação dos JSONL ou criação de contribuição.
- 104 testes Python passaram novamente no Windows com Firestore emulator obrigatório;
  os três testes Node passaram. Lock check, pip check e git diff check passaram.
- Imagens do bootstrap construídas com o lock corrigido já validado na revisão
  anterior. Base Git `60969768e4cebd4becf030d3bf1ba037ee7b49cd` mais alterações
  locais de segurança ainda sem commit; SHA-256 do lock:
  `ff633f3cca3f5986d19d6073fcd6cbfc4e80111c53d1925cf8bb41dc94b29c71`.

| Ambiente | Digest da imagem no registry próprio |
|---|---|
| Staging | `sha256:dc6a394ec806aa96263dbd3fcfb8b0b1958a46ac6c47736e4f6f5812aeea701d` |
| Produção | `sha256:ba502c8b99f625c760dbd10fc5d39c13842fad5c377a5202f17d9458ec54aea6` |

### O que falta para continuar

1. Revisar/publicar as alterações por uma pessoa, usando o fluxo protegido de PR.
   O agente não criou commits/push nem declarou CI remoto do código pendente como
   aprovado. A publicação rotineira de Hosting deve seguir o workflow do SHA revisado.
2. Após essa revisão, executar a concessão pública de invocação Run da seção 5
   do runbook. Hoje os serviços continuam privados: sem essa etapa, o smoke
   anônimo da candidata no workflow retornará 403. O acesso Stripe aos destinos
   nativos também depende dessa liberação. Não publicar as revisões sintéticas.
3. Publicar staging e testar
   Checkout/recuperação/finalize/email, escala zero, pinTag/rollback e restauração
   do primeiro backup sintético disponível. Conferir entrega SMTP e SPF/DKIM/DMARC
   com o administrador; login SMTP bem-sucedido não garante chegada na caixa.
4. Após aceite, publicar produção pelo workflow protegido; preparar monitor HTTPS,
   domínio/certificado, DNS, privacidade, contribuições reais autorizadas e sitemap.

O usuário concluiu no Console o aceite/habilitação Firebase durante esta execução;
essa etapa não pôde ser feita pelo terminal não interativo. Não houve alteração
DNS, pagamento, envio de agradecimento, publicação de frontend ou migração de dados.

## Histórico — criação inicial dos projetos em 04/11/2026

**Projetos institucionais criados; deploy pendente de faturamento ativo e credenciais.**
Conta administrativa: `rodrigo.vanzelotti@fundocentenario.com.br`.
Organização: `fundocentenario.com.br` (`874989411514`).

| Ambiente | Projeto | Número | Estado verificado |
|---|---|---|---|
| Staging | `fundocentenario-website-stg` | `424614961062` | ACTIVE, na organização institucional |
| Produção | `fundocentenario-website-prd` | `358530732475` | ACTIVE, na organização institucional |

Em ambos foram habilitadas as APIs IAM, IAM Credentials, STS e Cloud Resource
Manager e criadas `fundo-runtime`, `fundo-deploy` e `fundo-scheduler`, sem emissão
de chaves JSON. Papéis runtime/deploy e WIF ainda não foram configurados.
A única conta de faturamento acessível pela conta institucional estava fechada
(final `CA259F`). O responsável informou que tentará reativá-la posteriormente;
nenhum faturamento pessoal foi vinculado.

O [runbook principal](deployment.md) agora registra produção vazia, região São Paulo,
remetente Workspace `rodrigo.vanzelotti@fundocentenario.com.br`, Stripe
`2026-10-28.endive`, webhook na URL nativa Run, backups diários por sete dias sem
PITR e aceite publicado antes do live. Não houve importação de dados/assinaturas,
deploy, alteração DNS, pagamento ou email real. Mudanças ficam sem commit/push.

Validação local da configuração final:

- 104 testes Python passaram em Linux/Python 3.12 com lock por hashes e Firestore
  obrigatório; nenhum skip. Os 104 também passaram no venv Windows antes da
  atualização do lock.
- As auditorias iniciais encontraram vulnerabilidades em quatro transitivas:
  `certifi`, `dnspython`, `opentelemetry-api` e `pyasn1`. Somente essas versões e
  hashes foram atualizados, preservando as demais dependências. `pip check`,
  verificação do lock e `pip-audit` passaram após a correção.
- Os três testes frontend passaram; o teste institucional existente foi incluído
  no CI. O teste HTTP Hosting passou no emulador Linux/Firebase CLI 15.32.1.
  A execução Windows falhou por ausência dos headers esperados; o aceite válido
  nesta revisão é o Linux, mesmo ambiente do CI.
- Build linux/amd64, smoke HTTP da imagem corrigida, UID 10001 e ausência de
  `.env`/JSONL na imagem passaram. Trivy 0.75.0 não encontrou HIGH/CRITICAL com
  correção disponível. Actionlint 1.7.7 (sem shellcheck), Compose, compileall e
  `git diff --check` passaram.
- Revisão do diff e busca de padrões de credenciais nos arquivos rastreados
  passaram. JSONL locais mantiveram tamanho e data de modificação anteriores;
  nenhum dado local foi incluído na imagem ou importado para nuvem.

Retomar após reativar o faturamento: vincular os dois projetos, Firebase/Blaze e
orçamento; preparar registry, Firestore/rules/índices/TTL/backup, Secret Manager e
IAM; configurar WIF/GitHub; revisar/publicar o código manualmente; executar
bootstrap privado, Stripe e Scheduler; validar staging antes de produção/DNS.
Esses recursos e os testes remotos IAM, rollback, escala zero, SMTP e pagamentos
continuam pendentes. Os comandos e critérios estão no runbook, sem declaração de
lançamento concluído.

## Histórico — preparação de 16/10/2026

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
