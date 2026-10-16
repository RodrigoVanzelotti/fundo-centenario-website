# Integração Stripe

## Stripe: contribuição mensal no cartão

O adapter `backend/app/providers/stripe.py` usa a API oficial via `httpx`, já instalado. O fluxo mensal cria um Checkout hospedado em `mode=subscription`, em BRL, com preço escolhido pelo doador e intervalo `month`. A Stripe realiza as cobranças seguintes; este backend não agenda débitos nem recebe dados de cartão.

Configure no backend (Secret Manager em produção; `.env` apenas local):

```env
STRIPE_SECRET_KEY=CHAVE_SECRETA_DA_SUA_CONTA_DE_TESTE
STRIPE_WEBHOOK_SECRET=SEGREDO_DO_ENDPOINT_DE_TESTE
STRIPE_API_VERSION=2026-09-30.endive
PUBLIC_BASE_URL=http://localhost:8000
```

Use a chave `sk_test_...` ou uma chave restrita `rk_test_...` com permissão de criar Checkout Sessions. `STRIPE_WEBHOOK_SECRET` deve conter o `whsec_...` do endpoint que envia os eventos. Não reutilize o segredo da CLI no endpoint de produção. O modo test/live é identificado pela chave injetada, e o webhook deve corresponder a esse modo. Não há seleção de provedor ou de segredos no código.

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

`GET /api/donations/options` informa os métodos disponíveis sem credenciais. Com Stripe, a UI mostra Pix pontual, cartão pontual e **Contribuição mensal no cartão** (`card_recurring`). Pix pontual também usa o Checkout hospedado para exibir o QR Code. O cancelamento do Checkout retorna ao formulário; o retorno de sucesso consulta o status autenticado no backend. Pix Automático não é oferecido nesta integração.

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

Staging e produção exigem Firestore e origem HTTPS. A pipeline injeta as credenciais do projeto de cada ambiente e rejeita chave live em staging ou test em produção. Confirmação, fatura e outbox são transacionais. Staging aceita Stripe test; JSONL é exclusivo de desenvolvimento e exige um processo. Consulte [DEPLOYMENT.md](DEPLOYMENT.md) para configuração, migração e Scheduler.

Referências oficiais: [Checkout Sessions](https://docs.stripe.com/api/checkout/sessions/create), [metadata](https://docs.stripe.com/metadata), [webhooks e assinatura](https://docs.stripe.com/webhooks), [tipos de eventos](https://docs.stripe.com/api/events/types), [versionamento](https://docs.stripe.com/api/versioning).

## Confiabilidade do questionário pendente

Para cumprir a regra de não gravar PII antes do pagamento, o questionário fica em `sessionStorage`. No modo local há também uma cópia em memória no backend; no Firestore a intenção exclui o questionário. A perda da sessão do navegador ainda exige recuperação administrativa da identificação, independentemente de reinício do backend.

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

## Reverse proxy recomendado

Mesmo que frontend e backend sejam implantados separadamente, publique-os sob a mesma origem:

```text
https://www.fundocentenario.com.br/              -> frontend estático
https://www.fundocentenario.com.br/como-apoiar/  -> frontend estático
https://www.fundocentenario.com.br/api/*          -> FastAPI
```

Isso simplifica CSP, CORS e cookies/sessionStorage e evita expor outro hostname desnecessariamente.
