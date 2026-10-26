# Deploy: GitHub Actions, Google Cloud e Firebase

Este é o procedimento de lançamento e operação do Fundo Centenário. Firebase Hosting serve frontend/ diretamente; somente /api/** segue para Cloud Run. Firestore é a persistência de produção. Cloud Scheduler processa os agradecimentos durante requisições HTTP autenticadas.

Nenhum recurso de nuvem foi criado automaticamente, nenhuma credencial foi preenchida, nenhum email real foi enviado e nenhum commit/deploy foi realizado durante a preparação. Os comandos abaixo são para o operador executar somente após autorização para criar recursos e revisão do código. Exemplos de terminal usam Bash no Google Cloud Shell; não copie a sintaxe de variáveis diretamente para PowerShell.

## 1. Arquitetura e invariantes

```mermaid
flowchart LR
  GitHub[GitHub Actions / OIDC] --> Registry[Artifact Registry / digest]
  Registry --> Run[Cloud Run: FastAPI]
  Browser[Navegador] --> Hosting[Firebase Hosting]
  Hosting -->|/api/**| Run
  Stripe[Stripe: webhook assinado] --> Run
  Run --> DB[Firestore privado]
  Scheduler[Cloud Scheduler / OIDC] --> Run
  Run --> SMTP[SMTP com TLS]
  Secrets[Secret Manager] --> Run
```

- O browser nunca comprova pagamento. Apenas o webhook Stripe validado confirma contribuições.
- Cartões ficam no Checkout hospedado. Nome, email e CPF não entram na metadata Stripe.
- Intenções persistidas não contêm questionário. O browser mantém o questionário em `sessionStorage` e chama `/finalize` depois do pagamento confirmado.
- O cadastro do doador só é criado depois da confirmação, com autenticação pelo token da contribuição. O registro é criado uma vez, em transação.
- A primeira confirmação, a fatura recorrente e a outbox são gravadas em uma transação. IDs de documento determinísticos e transações coordenam instâncias distintas.
- Emails são processados somente quando existe pagamento e cadastro confirmado. Nenhum endpoint aceita destinatário/conteúdo arbitrários.
- `STORAGE_BACKEND=local` é exclusivo de desenvolvimento/testes. Stripe é usada em todos os ambientes. A pipeline injeta chaves test em staging e live em produção; ambos exigem Firestore.

O modo local continua disponível por `docker compose up --build`, com volume local privado e recarga automática. Não implante esse Compose no Google Cloud.

## 2. Decisões antes de criar recursos

1. Escolha dois projetos distintos: staging e produção. Isso separa dados, identidades, segredos e configurações Stripe.
2. Vincule faturamento, habilite o plano Firebase Blaze e configure alertas de orçamento em ambos. Limites de instâncias reduzem exposição, mas não constituem limite financeiro absoluto.
3. Escolha a região antes de criar o banco. Exemplo: `southamerica-east1`, com Firestore e Cloud Run próximos. Verifique disponibilidade e exigências institucionais de localização dos dados.
4. Use https://PROJECT.web.app em staging; produção usa https://fundocentenario.com.br. A URL nativa Run é reservada ao Scheduler e smoke da API. Não alterar DNS antes do checklist de migração.
5. Defina responsável por incidentes, reconciliação, cancelamentos, reembolsos e acesso aos dados. Configure finalidade e retenção do CPF, política de privacidade e contato de atendimento antes de divulgar o formulário.
6. Defina um remetente SMTP autorizado. Configure SPF, DKIM e DMARC no provedor/domínio e teste entrega em contas controladas pela equipe.

Não são necessários Kubernetes, Redis, Celery, uma segunda aplicação frontend, Firebase Authentication ou Firebase Admin SDK. Não instale um SDK Firebase no navegador para acessar dados de doadores.

## 3. Preparar Google Cloud e Firebase

Execute para cada ambiente, substituindo os valores:

```bash
export PROJECT="SEU_PROJECT_ID"
export REGION="southamerica-east1"
export SERVICE="fundo-centenario"
export REPOSITORY="fundo-images"
export RUNTIME_SA="fundo-runtime@$PROJECT.iam.gserviceaccount.com"
export DEPLOY_SA="fundo-deploy@$PROJECT.iam.gserviceaccount.com"
export SCHEDULER_SA="fundo-scheduler@$PROJECT.iam.gserviceaccount.com"

gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com cloudresourcemanager.googleapis.com firebase.googleapis.com firebasehosting.googleapis.com
gcloud artifacts repositories create "$REPOSITORY" --repository-format=docker --location="$REGION"
gcloud iam service-accounts create fundo-runtime
gcloud iam service-accounts create fundo-deploy
gcloud iam service-accounts create fundo-scheduler
```

No Firebase Console, adicione Firebase **ao projeto Google Cloud já escolhido**. Em Build → Firestore Database, crie `(default)` em modo Native/Standard, com regras de produção e a região escolhida. Não crie outro projeto Firebase por engano e não habilite acesso público ao banco.

O servidor usa Application Default Credentials e sua service account. Regras Firebase bloqueiam SDKs clientes; elas não substituem IAM para os SDKs de servidor. Conceda acesso mínimo à identidade runtime:

```bash
gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$RUNTIME_SA" --role=roles/datastore.user
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --member="serviceAccount:$DEPLOY_SA" --role=roles/iam.serviceAccountUser
gcloud artifacts repositories add-iam-policy-binding "$REPOSITORY" --location="$REGION" --member="serviceAccount:$DEPLOY_SA" --role=roles/artifactregistry.writer
```

`roles/datastore.user` permite operações de dados no projeto. Por isso, staging e produção devem estar separados e esse principal não deve receber acesso a outros projetos. Não conceda Owner/Editor às identidades da aplicação ou do pipeline. [Identidade de serviço](https://docs.cloud.google.com/run/docs/configuring/services/service-identity).

### Regras, índices e TTL

Na raiz do repositório, com uma conta administrativa autorizada:

```bash
npx --yes firebase-tools@15.32.1 login
npx --yes firebase-tools@15.32.1 deploy --project "$PROJECT" --only firestore:rules,firestore:indexes
```

Arquivos versionados:

- `firebase.json`: Hosting estático e rewrite /api/** para fundo-centenario em southamerica-east1 com pinTag; Firestore e emulador. Projeto explícito via --project.
- `firestore.rules`: nega todo acesso de clientes.
- `firestore.indexes.json`: índice de seleção dos emails, TTL para pendências e rate limits, e exclusão de índices desnecessários de PII/tokens.

Confirme no Console que o índice `fundo_thank_you_outbox` (`state`, `next_attempt_at`) terminou de construir antes de habilitar emails. Confirme também que as políticas TTL em `fundo_pending.expires_at` e `fundo_rate_limits.expires_at` estão ativas. TTL é limpeza assíncrona; a aplicação verifica expiração sem depender da exclusão física. Não configure TTL em confirmações ou cadastro sem uma política de retenção aprovada. [Índices](https://firebase.google.com/docs/firestore/query-data/indexing), [TTL](https://firebase.google.com/docs/firestore/ttl).

O prefixo padrão é `fundo_`. Se mudar `FIRESTORE_PREFIX`, ajuste os grupos de coleção do arquivo de índices/TTL antes do deploy. O workflow usa o prefixo padrão e o banco `(default)`.

## 4. Segredos e Stripe

Crie os segredos no Secret Manager Console, colocando cada valor diretamente na interface e criando sua primeira versão:

| Segredo | Conteúdo | Necessário |
|---|---|---|
| `stripe-secret-key` | Chave secreta/restrita da conta correta | Sempre |
| `stripe-webhook-secret` | Segredo do destino de webhook desse ambiente | Sempre |
| `smtp-username` | Usuário do remetente SMTP | Com email habilitado |
| `smtp-password` | Senha/app password do remetente | Com email habilitado |

Em staging use Stripe test; em produção use live. Nunca reutilize o segredo da Stripe CLI como segredo do endpoint de produção. Não escreva os valores em comandos, YAML, arquivos versionados, Docker build args ou GitHub Variables.

Conceda ao runtime acesso a cada segredo necessário, sem acesso indiscriminado ao projeto:

```bash
gcloud secrets add-iam-policy-binding stripe-secret-key --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding stripe-webhook-secret --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
# A pipeline verifica test/live sem expor a chave:
gcloud secrets add-iam-policy-binding stripe-secret-key --member="serviceAccount:$DEPLOY_SA" --role=roles/secretmanager.secretAccessor
# Execute estes dois somente se o remetente estiver configurado:
gcloud secrets add-iam-policy-binding smtp-username --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding smtp-password --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor
```

Cadastre o destino Stripe em `https://SUA_ORIGEM/api/webhooks/stripe`, com snapshot events da própria conta, API `2026-09-30.endive` e eventos listados em [INTEGRATION.md](../INTEGRATION.md). Confirme habilitação de Pix na conta antes de divulgá-lo. Mantenha versão da API, segredo e modo test/live alinhados.

As versões de segredos são numéricas e fixadas no deploy. Para rotacionar, crie uma nova versão, atualize as GitHub Variables correspondentes e implante nova revisão. Preserve versões antigas enquanto puder ser necessário rollback; revogue credenciais comprometidas independentemente dessa política. [Segredos no Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/secrets).

## 5. Primeiro serviço Cloud Run: bootstrap administrativo

O workflow de CD exige um serviço já existente. O bootstrap é feito uma vez por um administrador, separado do deploy rotineiro.

Construa e publique a primeira imagem revisada:

```bash
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet
export IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPOSITORY/fundo:bootstrap-1"
docker build --platform linux/amd64 -t "$IMAGE" .
docker push "$IMAGE"
```

Para obter a URL inicial, crie o serviço **privado**, com credenciais sintéticas apenas para inicialização, sem email. Elas não autenticam chamadas à Stripe nem permitem criar pagamentos:

```bash
gcloud run deploy "$SERVICE" --region "$REGION" --image "$IMAGE" --service-account "$RUNTIME_SA" --port 8000 --no-allow-unauthenticated --set-env-vars APP_ENV=development,STORAGE_BACKEND=local,STRIPE_SECRET_KEY=sk_test_bootstrap_only,STRIPE_WEBHOOK_SECRET=whsec_bootstrap_only,EMAIL_ENABLED=false --max-instances 1 --quiet
export RUN_URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
```

Não publique essa revisão de bootstrap. Ela serve somente para reservar o serviço/URL. Escolha `PUBLIC_BASE_URL=https://$PROJECT.web.app` em staging (domínio institucional em produção), cadastre o webhook Stripe, complete os segredos e prepare um arquivo `runtime.json` temporário com valores **não secretos**:

```json
{
  "APP_ENV": "staging",
  "STORAGE_BACKEND": "firestore",
  "GOOGLE_CLOUD_PROJECT": "SEU_PROJECT_ID",
  "FIRESTORE_DATABASE": "(default)",
  "FIRESTORE_PREFIX": "fundo_",
  "PUBLIC_BASE_URL": "https://SEU_PROJECT_ID.web.app",
  "CORS_ORIGINS": "https://SEU_PROJECT_ID.web.app",
  "SERVE_FRONTEND": "false",
  "PYTHON_DOTENV_DISABLED": "1",
  "STRIPE_API_VERSION": "2026-09-30.endive",
  "EMAIL_ENABLED": "false",
  "SCHEDULER_AUDIENCE": "https://URL_NATIVA_DO_SERVICO",
  "SCHEDULER_SERVICE_ACCOUNT": "fundo-scheduler@SEU_PROJECT_ID.iam.gserviceaccount.com",
  "INTENT_LIMIT_PER_MINUTE": "60",
  "EMAIL_BATCH_SIZE": "10"
}
```

Em produção altere `APP_ENV` para `production` e use os segredos live do projeto de produção. O modo Stripe é definido pelas credenciais, sem uma flag adicional. Não copie as credenciais test desse exemplo para o lançamento live.

```bash
gcloud run deploy "$SERVICE" --region "$REGION" --image "$IMAGE" --service-account "$RUNTIME_SA" --port 8000 --env-vars-file runtime.json --set-secrets STRIPE_SECRET_KEY=stripe-secret-key:1,STRIPE_WEBHOOK_SECRET=stripe-webhook-secret:1 --memory 512Mi --cpu 1 --concurrency 20 --min-instances 0 --max-instances 3 --timeout 180 --cpu-throttling --startup-probe httpGet.path=/api/health,httpGet.port=8000,periodSeconds=10,timeoutSeconds=2,failureThreshold=12 --quiet
```

Antes de tornar público, faça smoke test com uma identidade humana que tenha `roles/run.invoker` no serviço:

```bash
export SMOKE_ID_TOKEN="$(gcloud auth print-identity-token)"
python tools/smoke.py "$RUN_URL" --production --api-only
unset SMOKE_ID_TOKEN
```

O parâmetro `--production` do smoke verifica proteções HTTP e métodos Stripe tanto em staging quanto em produção; não realiza cobrança.

Somente depois do teste, permita a invocação pública do site e dos webhooks. Um administrador pode executar:

```bash
gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" --member=allUsers --role=roles/run.invoker
gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" --member="serviceAccount:$DEPLOY_SA" --role=roles/run.developer
```

Se a política da organização impedir `allUsers`, resolva a exposição pública com o administrador de rede/IAM antes de liberar o formulário. Não torne dados do Firestore públicos para contornar isso. O endpoint de emails continua protegido na aplicação, pois IAM do serviço público não distingue rotas.

## 6. GitHub: proteção e autenticação federada

No repositório, habilite Actions e crie os environments `staging` e `production`. Restrinja deploys à branch `main`, exija revisão de PR e torne o check `CI / check` obrigatório. Exija revisores no environment de produção e impeça self-review; se o plano não suportar essa proteção, mantenha CD de produção desabilitado até definir aprovação equivalente. Esses controles são configurações do GitHub e não são ativados apenas por adicionar YAML.

O código adiciona:

- `.github/workflows/ci.yml`: testes em ambiente isolado, emulador Firestore, checks frontend, Compose, lock, auditoria de dependências, build e smoke test da imagem, scan de vulnerabilidades do container.
- `.github/workflows/deploy.yml`: CI → staging → produção manual/protegida; `deploy-environment.yml` reutiliza OIDC, imagem por digest, candidata, smoke, promoção e publicação Hosting.
- `.github/dependabot.yml`: acompanhamento semanal de dependências, imagens e Actions.

PRs não recebem identidade Google nem acesso a produção. Actions são fixadas por SHA; o job de deploy solicita somente `contents: read` e `id-token: write`. A service account de deploy lê somente `stripe-secret-key` para validar o modo antes do deploy, sem imprimir seu valor; não recebe acesso aos dados de doadores.

### Workload Identity Federation

Obtenha os IDs numéricos do repositório e de seu proprietário no GitHub. Crie pool/provider no projeto de cada ambiente com restrições ao repositório, branch e environment. Exemplo para produção:

```bash
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
export REPOSITORY_ID="ID_NUMERICO_DO_REPOSITORIO"
export OWNER_ID="ID_NUMERICO_DO_PROPRIETARIO"

gcloud iam workload-identity-pools create github --location=global --display-name="GitHub deployments"
gcloud iam workload-identity-pools providers create-oidc github --location=global --workload-identity-pool=github --issuer-uri=https://token.actions.githubusercontent.com --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.repository_owner_id=assertion.repository_owner_id" --attribute-condition="assertion.repository_id=='$REPOSITORY_ID' && assertion.repository_owner_id=='$OWNER_ID' && assertion.ref=='refs/heads/main' && assertion.environment=='production'"
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" --role=roles/iam.workloadIdentityUser --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository_id/$REPOSITORY_ID"
```

No projeto staging, use `assertion.environment=='staging'`. Não remova as restrições para corrigir um erro de autenticação; confira os IDs, a branch e o environment do job. [Guia oficial de WIF](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

### Variables por environment

Em Settings → Environments → environment → Environment variables:

| Variable | Exemplo/finalidade |
|---|---|
| `GCP_PROJECT_ID` | ID do projeto desse ambiente |
| `GCP_REGION` | `southamerica-east1` |
| `CLOUD_RUN_SERVICE` | `fundo-centenario` |
| `ARTIFACT_REPOSITORY` | `fundo-images` |
| `GCP_WIF_PROVIDER` | `projects/NUMERO/locations/global/workloadIdentityPools/github/providers/github` |
| `DEPLOY_SERVICE_ACCOUNT` | Email de `fundo-deploy` |
| `RUNTIME_SERVICE_ACCOUNT` | Email de `fundo-runtime` |
| `PUBLIC_BASE_URL` | Origem HTTPS, sem caminho/query, sem barra final |
| `CLOUD_RUN_URL` | URL nativa HTTPS estável do serviço; audience do Scheduler |
| `SCHEDULER_SERVICE_ACCOUNT` | Email de `fundo-scheduler` |
| `EMAIL_ENABLED` | `false` no primeiro deploy; `true` após testar remetente e Scheduler |
| `SMTP_HOST` | Host SMTP; obrigatório quando email estiver ativo |
| `EMAIL_FROM_ADDRESS` | Remetente autorizado |
| `EMAIL_REPLY_TO` | Atendimento; opcional |
| `STRIPE_API_VERSION` | Versão alinhada ao webhook; padrão `2026-09-30.endive` |
| `STRIPE_SECRET_VERSION` | Versão numérica do segredo; padrão `1` |
| `STRIPE_WEBHOOK_SECRET_VERSION` | Versão numérica; padrão `1` |
| `SMTP_SECRET_VERSION` | Mesma versão numérica para usuário e senha SMTP; padrão `1` |

Não coloque chaves/senhas nessas Variables. O workflow usa STARTTLS/587 por padrão; se o provedor exigir SSL/465, altere os dois valores do bloco `env` em conjunto e revise o deploy. Texto, assunto e template têm defaults no backend e podem ser personalizados no mesmo bloco sem adicionar dados secretos.

Após configurar e publicar manualmente as alterações revisadas no GitHub, use Actions → Deploy → Run workflow → `staging`. Faça a validação Stripe antes de promover produção. Push em `main` executa somente staging. Despacho manual para produção executa CI e staging do mesmo SHA antes do job de produção, que aguarda aprovação do environment.

Se o smoke da candidata falhar, o workflow não altera o tráfego existente. Investigue a revisão candidata e remova sua tag após diagnóstico. Não promova manualmente uma candidata sem entender a falha. [Rollouts e rollback](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration).

## 7. Scheduler e ativação dos emails

O worker permanente só roda no modo local. No Firestore, a outbox é consultada e processada durante `POST /api/internal/emails/process`. O handler verifica assinatura/issuer do token Google, audience, email e `email_verified`. Não confia em headers `X-CloudScheduler-*` como autenticação.

Crie o job antes de habilitar envio:

```bash
gcloud scheduler jobs create http fundo-thank-you --location="$REGION" --schedule="*/5 * * * *" --time-zone="America/Sao_Paulo" --uri="$RUN_URL/api/internal/emails/process" --http-method=POST --oidc-service-account-email="$SCHEDULER_SA" --oidc-token-audience="$RUN_URL" --attempt-deadline=180s --max-retry-attempts=3
```

O operador que cria o job precisa de permissão para usar essa service account. Preserve o papel de service agent do Cloud Scheduler; não entregue uma chave JSON ao job. Como o serviço é público, a verificação por rota ocorre no código. [Scheduler com Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-scheduler).

No runtime confira `SCHEDULER_AUDIENCE=$RUN_URL` e `SCHEDULER_SERVICE_ACCOUNT=$SCHEDULER_SA`. Preencha remetente e segredos, altere `EMAIL_ENABLED=true` no environment e faça novo deploy. Execute o job manualmente pelo Console somente quando houver uma contribuição de teste autorizada no projeto staging.

Cada execução seleciona até 10 registros e para de iniciar novos envios após 50 segundos. Cada registro tem lease de 5 minutos, aquisição transacional e retries com atraso limitado a uma hora. Uma requisição sem cadastro confirmado adia o job; nunca envia o questionário antes do pagamento. O retry pode continuar após reinício ou troca de instância.

SMTP não garante entrega exatamente uma vez. Se aceitar o email e o processo encerrar antes de registrar o envio, o retry pode duplicá-lo; `Message-ID` é estável. Aceitação SMTP não comprova entrega na caixa de entrada. Uma garantia maior exige serviço de email com idempotência, não apenas outro lock.

## 8. Migração dos JSONL existentes

Não envie os dados locais ao GitHub ou ao build Docker. O modo Firestore não lê/migra `backend/data` automaticamente.

1. Pause novas contribuições no sistema anterior e deixe os pagamentos pendentes serem conciliados. Os registros antigos em memória não serão transferidos; não desligue o processo sem planejar sua recuperação.
2. Faça backup privado dos JSONL, restrito e criptografado. Mantenha uma cópia imutável para recuperação.
3. Reconcile pagamentos e assinaturas com a conta Stripe correta. Não importe pagamentos simulados antigos ou registros sem comprovação. Assinaturas anteriores sem metadata exigem reconciliação específica conforme `INTEGRATION.md`.
4. Instale as dependências em um ambiente isolado e obtenha ADC com uma identidade administrativa temporária autorizada.
5. Valide primeiro uma cópia protegida do backup, sem acesso remoto:

```bash
python tools/migrate_jsonl.py --source /CAMINHO_PRIVADO/backup
```

6. Teste a importação no projeto staging antes de produção. Para aplicar a fonte já conciliada:

```bash
gcloud auth application-default login
python tools/migrate_jsonl.py --source /CAMINHO_PRIVADO/backup --project "$PROJECT" --apply --confirmed-source
```

O comando preserva IDs, primeira confirmação, faturas, cadastro e marcadores de email enviado. É idempotente; pode ser repetido após falha parcial. Ele não chama SMTP e não cria novos emails retroativos. Para preservar explicitamente pedidos de email ainda pendentes da fonte, acrescente `--include-pending-emails` depois de revisar os destinatários/estado. Nunca importe um backup de staging/testes em produção.

Compare contagens e amostras de referências com a fonte e a Stripe, sem copiar PII para logs. Registros de cadastro devem possuir confirmação correspondente. Não restaure o banco inteiro depois de novos pagamentos sem reconciliar os eventos posteriores; isso pode desfazer deduplicação.

## 10. Manutenção e testes locais

Runtime Linux/Python 3.12 usa `backend/requirements.lock`, com versões e hashes. Após alterar `backend/requirements.txt`, gere o lock novamente em Linux e revise o diff; Dependabot não dispensa essa revisão:

```bash
docker run --rm -v "$PWD:/workspace:ro" -w /workspace python:3.12-slim@sha256:02108f5d322dd89f1c9e552442c25acb0543dfdbc455693a5599624f20d9155d python tools/lock_requirements.py > backend/requirements.lock
python tools/lock_requirements.py --check
```

Em Windows, use `requirements.txt` para o venv local, pois o lock é resolvido para Linux. A imagem e o CI sempre usam o lock. Não gere o arquivo com redirecionamento UTF-16 do PowerShell antigo; use Bash ou capture stdout em Python e grave UTF-8.

Para testar persistência remota localmente, inicie o emulator e execute os testes com um projeto fictício:

```bash
docker run --rm -p 127.0.0.1:8085:8085 gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators@sha256:8d8573471c489a409f03891d2c24d177fa531276184f7002b9a2d853d1b3ed54 gcloud emulators firestore start --host-port=0.0.0.0:8085 --project=demo-fundo-centenario
# Em outro terminal, no venv:
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
FIRESTORE_TEST_HOST=127.0.0.1:8085 REQUIRE_FIRESTORE_TESTS=1 python -m pytest -q
node tests/frontend-static.test.js
node tests/donation-steps.test.js
```

Sem emulator, os testes locais de Firestore são pulados; o CI exige sua execução. Os testes usam dados sintéticos e desabilitam a leitura de `.env`, sem cobrar cartões nem enviar emails reais. O emulator não reproduz IAM, regras de SDK cliente, construção de índices, billing ou todos os comportamentos do serviço gerenciado: valide esses itens no staging antes do live.

## Hosting, isolamento e aprovação de release

`frontend/` é o build de produção: sem compilador ou dependências npm no produto.
O container preserva os arquivos para desenvolvimento; no deploy usa
`SERVE_FRONTEND=false`. HTML, JS e CSS revalidam a cada acesso; imagens têm cache
de uma hora. Não usar immutable em nomes sem hash. API responde no-store, inclusive
erros. Sem fallback SPA: arquivos ausentes retornam 404. `/como-apoiar/` é um
diretório real; refresh não depende de estado de navegação.

Defina repository Variables `STAGING_GCP_PROJECT_ID` e `PRODUCTION_GCP_PROJECT_ID`,
distintas. Cada environment mantém `GCP_PROJECT_ID` e as variáveis da tabela acima.
O workflow rejeita divergência, projetos iguais e runtime SA fora do projeto.
Crie o site Hosting padrão em cada projeto. `GCP_REGION=southamerica-east1` e
`CLOUD_RUN_SERVICE=fundo-centenario` devem corresponder ao rewrite em `firebase.json`.
Não presumir disponibilidade dos nomes sugeridos ou existência de recursos.

Configure required reviewers, impedir self-review e branch main no environment
production. Restrinja alterações em workflows/environments/variables. Um dispatch
production solicita a promoção, mas aprovação deve considerar o resultado staging
e os gates institucionais. Esses controles exigem configuração real no GitHub.

Além dos papéis anteriores, a identidade de deploy precisa de
`roles/firebasehosting.admin` e `roles/serviceusage.serviceUsageConsumer` no próprio
projeto. `pinTag` atualiza tags Run e precisa das permissões run.developer no serviço.
Verifique em staging; não conceder Owner/Editor para contornar erros. Runtime não
recebe esses papéis de deploy. Firebase CLI usa ADC do OIDC, sem chave JSON ou
FIREBASE_TOKEN. Versão da CLI: 15.32.1, igual aos comandos administrativos.

O workflow é a configuração declarativa existente do serviço; Firebase JSON define
Hosting/Firestore. Bootstrap e IAM permanecem comandos administrativos explícitos,
sem introduzir Terraform. O projeto nunca é escolhido por alias implícito.

Ordem: CI → staging (imagem por digest, candidata sem tráfego, smoke API, tráfego
Run, Hosting pinTag, smoke web.app) → aprovação de produção, quando solicitada →
mesmos passos no projeto isolado. Hosting publica exatamente o checkout do mesmo
SHA da API. Regras/índices são preparação administrativa, não mudanças implícitas
em cada release. Smoke testa GET e POST rejeitado no webhook sem criar pagamentos.
Falhas após a promoção exigem rollback coordenado: Run e Hosting não são atômicos.

Staging recebe `X-Robots-Tag: noindex, nofollow` gerado pelo workflow. Isso não é
autenticação; use somente dados sintéticos. Preview Channels são opcionais para
revisão visual e devem usar somente o projeto staging; retorno Stripe continua na
origem staging configurada, onde deve ocorrer a validação funcional completa.

No bootstrap, publique Hosting somente após candidata validada:

```bash
npx --yes firebase-tools@15.32.1 deploy --project "$PROJECT" --only hosting --non-interactive
python tools/smoke.py "https://$PROJECT.web.app" --production
```

No staging manual acrescente o header noindex antes da publicação, como no workflow.
Smoke web.app antes do DNS verifica transporte e arquivos; checkout/CORS precisam
também ser verificados no domínio final. Não adivinhar registros DNS.

Fontes: [Hosting/pinTag](https://firebase.google.com/docs/hosting/cloud-run),
[OIDC e ADC](https://github.com/google-github-actions/auth),
[proteções de environments](https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-deployments/managing-environments-for-deployment).

