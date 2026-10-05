# Integração com PSP real

## Stripe: contribuição mensal no cartão

O adapter `backend/app/providers/stripe.py` usa a API oficial via `httpx`, já instalado. O fluxo mensal cria um Checkout hospedado em `mode=subscription`, em BRL, com preço escolhido pelo doador e intervalo `month`. A Stripe realiza as cobranças seguintes; este backend não agenda débitos nem recebe dados de cartão.

Configure **somente no backend/.env**:

```env
PAYMENT_PROVIDER=stripe
ENABLE_MOCK_PSP=false
STRIPE_SECRET_KEY=CHAVE_SECRETA_DA_SUA_CONTA_DE_TESTE
STRIPE_WEBHOOK_SECRET=SEGREDO_DO_ENDPOINT_DE_TESTE
STRIPE_API_VERSION=2026-09-30.endive
STRIPE_LIVE_MODE=false
PUBLIC_BASE_URL=http://localhost:8000
```

Use a chave `sk_test_...` ou uma chave restrita `rk_test_...` com permissão de criar Checkout Sessions. `STRIPE_WEBHOOK_SECRET` deve conter o `whsec_...` do endpoint que envia os eventos. Não reutilize o segredo da CLI no endpoint de produção. O adapter rejeita uma chave cujo modo seja diferente de `STRIPE_LIVE_MODE`.

No Dashboard, habilite cartão e, se desejado, Pix pontual para a conta. Cadastre um destino de **snapshot events da própria conta**, na mesma versão indicada por `STRIPE_API_VERSION`, com URL:

```text
https://SEU_DOMINIO/api/webhooks/stripe
```

Selecione estes eventos:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`
- `invoice.payment_succeeded`
- `invoice.payment_failed`
- `customer.subscription.deleted`

`checkout.session.completed` autoriza a recorrência, mas não confirma a doação mensal. A confirmação exige `invoice.payment_succeeded`, fatura com status `paid`, saldo restante zero, moeda BRL e valor efetivamente pago igual ao valor contratado. `invoice.paid` é ignorado porque também pode resultar de marcação manual de pagamento fora da Stripe. Faturas gratuitas, trials, descontos, impostos adicionais e alterações de valor no Dashboard não são contemplados por este contrato de contribuição fixa; valores divergentes são rejeitados.

Metadata de sessão e assinatura contém somente referência da contribuição, hash do token, programa, método e valor. A Stripe copia a metadata da assinatura para `parent.subscription_details.metadata` da fatura. Nome, e-mail e CPF do formulário não são enviados nesta metadata nem na requisição de criação; o Checkout coleta as informações necessárias ao processamento.

`GET /api/donations/options` informa os métodos disponíveis sem credenciais. Com Stripe, a UI mostra Pix pontual, cartão pontual e **Contribuição mensal no cartão** (`card_recurring`). Pix pontual também usa o Checkout hospedado para exibir o QR Code. O cancelamento do Checkout retorna ao formulário; o retorno de sucesso consulta o status autenticado no backend. Pix Automático permanece nos adapters mock/genérico, e não é usado pelo adapter Stripe nesta integração.

### Testar localmente

```bash
stripe login
stripe listen --latest --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,checkout.session.expired,invoice.payment_succeeded,invoice.payment_failed,customer.subscription.deleted --forward-to localhost:8000/api/webhooks/stripe
```

Copie o segredo apresentado pela CLI para `STRIPE_WEBHOOK_SECRET` e reinicie o backend. `--latest` deve corresponder à versão fixada acima; após uma atualização da API, alinhe a versão da aplicação e do destino antes de testar. Abra `/como-apoiar/`, selecione cartão mensal e conclua um Checkout com dados de cartão de teste da documentação Stripe. Um `stripe trigger` genérico sem a metadata desta aplicação será ignorado; teste a assinatura criada pelo formulário para verificar o vínculo correto.

Os testes automatizados usam HTTP simulado e payloads assinados, sem cobrar cartões ou acessar a conta Stripe:

```bash
pytest -q
node tests/frontend-static.test.js
node tests/donation-steps.test.js
```

Cada fatura paga recebe uma entrada em `recurring_payments.jsonl`, deduplicada pelo ID da fatura, inclusive após reinício. `payment_confirmations.jsonl` guarda a primeira confirmação da contribuição; `confirmed_donations.jsonl` grava os dados do doador uma vez, somente após pagamento. Renovações referenciam esse cadastro pelo `donation_id`, sem duplicar PII. Se a gravação falhar, o webhook retorna erro e pode ser reenviado; uma tentativa não é considerada concluída antes das gravações necessárias.

Cobranças seguintes, tentativas de recuperação, mudança de cartão e cancelamento da assinatura são administrados na Stripe. O MVP não oferece portal de assinantes próprio. Um pagamento já confirmado continua no histórico mesmo que uma cobrança futura falhe ou a assinatura seja cancelada.

Assinaturas já existentes na conta Stripe não são automaticamente vinculadas ao cadastro local. Eventos sem a metadata desta aplicação são ignorados para não atribuir pagamentos a doadores incorretos. Uma migração deve reconciliar as referências existentes antes de adicionar metadata; a implementação não modifica assinaturas antigas nem o `.env` atual.

Para produção, use chaves e segredo do endpoint live, `STRIPE_LIVE_MODE=true` e `PUBLIC_BASE_URL` HTTPS. Esta integração usa arquivos locais e **um único processo/worker**; antes de usar múltiplos workers ou instâncias, substitua a persistência por transações e restrições únicas em banco. Não habilite múltiplos workers sobre os mesmos JSONL.

Referências oficiais: [Checkout Sessions](https://docs.stripe.com/api/checkout/sessions/create), [metadata](https://docs.stripe.com/metadata), [webhooks e assinatura](https://docs.stripe.com/webhooks), [tipos de eventos](https://docs.stripe.com/api/events/types), [versionamento](https://docs.stripe.com/api/versioning).

## Outros PSPs: adapter genérico

A implementação separa o site do contrato específico de um banco ou PSP.

O frontend não precisa mudar quando o provedor for substituído. A camada de integração está em:

```text
backend/app/providers/
```

## 1. O que o PSP precisa oferecer

Para atender aos três fluxos, o provedor escolhido deve disponibilizar, idealmente:

### Pix pontual

- endpoint para criar cobrança Pix;
- retorno de Pix Copia e Cola e/ou QR Code base64;
- identificador único da cobrança;
- webhook de pagamento confirmado.

### Pix Automático

- endpoint para criar recorrência/autorização;
- URL hospedada ou QR Code para o pagador autorizar;
- referência externa/metadata;
- webhook de autorização e, principalmente, webhook de pagamento efetivamente liquidado.

O sistema **não grava o questionário ao receber apenas `authorized`**. A gravação acontece quando chegar um evento normalizado como `paid`.

### Cartão

- criação de sessão de checkout hospedada;
- `return_url` depois do checkout;
- webhook de pagamento aprovado.

O checkout precisa permanecer hospedado no PSP. Não adapte o projeto para receber PAN, CVV ou validade diretamente.

---

# 2. Credenciais necessárias

Todas as credenciais abaixo são **server-side**.

Edite `backend/.env`, nunca `frontend/assets/js/config.js`.

## OAuth Client Credentials

Se o PSP usar OAuth:

```env
PSP_AUTH_MODE=oauth_client_credentials
PSP_OAUTH_TOKEN_URL=https://api.seu-psp.com/oauth/token
PSP_CLIENT_ID=SEU_CLIENT_ID
PSP_CLIENT_SECRET=SEU_CLIENT_SECRET
PSP_OAUTH_SCOPE=
```

## API Key

```env
PSP_AUTH_MODE=api_key
PSP_API_KEY=SEGREDO
PSP_API_KEY_HEADER=X-API-Key
```

## Bearer fixo

Use somente se o provedor documentar um token estático server-side:

```env
PSP_AUTH_MODE=bearer
PSP_BEARER_TOKEN=SEGREDO
```

## Webhook

```env
PSP_WEBHOOK_SECRET=SEGREDO_DO_WEBHOOK
PSP_WEBHOOK_SIGNATURE_HEADER=X-Webhook-Signature
```

O adapter `generic_http` implementa HMAC-SHA256 simples. Muitos PSPs usam esquemas próprios, por exemplo timestamp + assinatura, JWS, certificado ou cabeçalhos específicos. Nesse caso altere **somente** `GenericHttpPaymentProvider._verify_hmac()` / `parse_webhook()` ou crie um provider específico.

---

# 3. Endpoints do PSP

Configure os caminhos reais:

```env
PSP_BASE_URL=https://api.seu-psp.com
PSP_PIX_CREATE_PATH=/pix/payments
PSP_PIX_AUTOMATIC_CREATE_PATH=/pix/automatic/authorizations
PSP_CARD_CHECKOUT_PATH=/checkout/sessions
```

O adapter envia um payload normalizado semelhante a. Por padrão, os dados pessoais do questionário **não são enviados ao PSP** (`PSP_SEND_CUSTOMER_DATA=false`). Habilite isso somente se a API do provedor exigir:

```env
PSP_SEND_CUSTOMER_DATA=true
```

Payload normalizado:

```json
{
  "external_reference": "UUID_DA_DOACAO",
  "amount_cents": 10000,
  "currency": "BRL",
  "description": "Contribuição ao Fundo Centenário",
  "customer": {
    "name": "enviado somente se PSP_SEND_CUSTOMER_DATA=true",
    "email": "...",
    "cpf": "..."
  },
  "metadata": {
    "donation_id": "UUID_DA_DOACAO",
    "status_token_hash": "HASH_SHA256",
    "program": "edital-projetos",
    "method": "pix"
  },
  "return_url": "https://site/como-apoiar/?donation_id=...",
  "webhook_url": "https://site/api/webhooks/generic_http"
}
```

**Importante:** cada PSP possui um JSON diferente. Se o provedor não aceitar esse formato, altere apenas `_payload()` em:

```text
backend/app/providers/generic_http.py
```

---

# 4. Mapeamento da resposta

O projeto permite apontar onde estão os campos no JSON do PSP usando dot notation:

```env
PSP_FIELD_PAYMENT_ID=id
PSP_FIELD_STATUS=status
PSP_FIELD_PIX_COPY_PASTE=pix.copy_paste
PSP_FIELD_PIX_QR_BASE64=pix.qr_base64
PSP_FIELD_REDIRECT_URL=redirect_url
PSP_FIELD_EXPIRES_AT=expires_at
```

Exemplo de resposta compatível:

```json
{
  "id": "pay_123",
  "status": "pending",
  "pix": {
    "copy_paste": "000201...",
    "qr_base64": null
  },
  "redirect_url": null,
  "expires_at": "2026-10-02T15:30:00Z"
}
```

Para cartão, `redirect_url` deve apontar para a página hospedada pelo PSP.

---

# 5. Webhook e confirmação

Endpoint exposto pelo Fundo:

```text
POST /api/webhooks/generic_http
```

O webhook precisa permitir recuperar a referência da doação. A solução preferencial é configurar `external_reference` ou metadata no PSP.

Mapeamento padrão:

```env
PSP_WEBHOOK_FIELD_EVENT_ID=event_id
PSP_WEBHOOK_FIELD_PAYMENT_ID=payment_id
PSP_WEBHOOK_FIELD_DONATION_ID=metadata.donation_id
PSP_WEBHOOK_FIELD_STATUS=status
PSP_WEBHOOK_FIELD_AMOUNT_CENTS=amount_cents
PSP_WEBHOOK_FIELD_TOKEN_HASH=metadata.status_token_hash
PSP_WEBHOOK_FIELD_PROGRAM=metadata.program
PSP_WEBHOOK_FIELD_METHOD=metadata.method
```

Status considerados pagos:

```env
PSP_PAID_STATUSES=paid,confirmed,approved,completed
```

Ajuste aos nomes usados pelo provedor.

Quando chega um evento pago:

```text
PSP webhook
   |
   v
verificação de assinatura
   |
   v
payment_confirmations.jsonl (sem PII do questionário)
   |
   +--> se o questionário ainda estiver em memória
   |       confirmed_donations.jsonl
   |
   +--> frontend consulta /status
           |
           v
         agradecimento
```

---

# 6. Confiabilidade do questionário pendente

Para cumprir a regra de não gravar PII antes do pagamento, os dados pendentes ficam somente em memória no backend e em `sessionStorage` no navegador.

Há um mecanismo de recuperação:

1. o pagamento confirmado é persistido sem PII;
2. o navegador mantém o questionário durante a sessão;
3. se o backend reiniciar, o frontend chama `/finalize` após detectar a confirmação;
4. o backend só grava o questionário depois de validar o token associado ao pagamento confirmado.

### Limitação

Se ocorrerem simultaneamente:

- reinício do backend;
- encerramento/perda da sessão do navegador;
- pagamento concluído depois disso;

não haverá cópia persistente do questionário para associar ao pagamento.

Para produção com alto volume, a alternativa é um cache temporário criptografado com TTL e persistência desabilitada, ou outro mecanismo aprovado pela política de privacidade do Fundo. Isso deve ser decidido conscientemente, pois muda a regra de retenção pré-pagamento.

---

# 7. Reverse proxy recomendado

Mesmo que frontend e backend sejam implantados separadamente, publique-os sob a mesma origem:

```text
https://www.fundocentenario.com.br/              -> frontend estático
https://www.fundocentenario.com.br/como-apoiar/  -> frontend estático
https://www.fundocentenario.com.br/api/*          -> FastAPI
```

Isso simplifica CSP, CORS e cookies/sessionStorage e evita expor outro hostname desnecessariamente.
