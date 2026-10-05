# Formato dos arquivos locais

## confirmed_donations.jsonl

Uma linha JSON por contribuição confirmada:

```json
{
  "donation_id": "uuid",
  "provider_payment_id": "pay_123",
  "method": "pix",
  "program": "edital-projetos",
  "program_label": "Edital de projetos",
  "amount_cents": 10000,
  "currency": "BRL",
  "donor_name": "Nome",
  "donor_email": "email@exemplo.com",
  "donor_cpf": "00000000000",
  "communication_opt_in": true,
  "created_at": "2026-10-02T12:00:00+00:00",
  "confirmed_at": "2026-10-02T12:01:30+00:00"
}
```

## payment_confirmations.jsonl

Usado para idempotência e recuperação. Não contém o questionário:

```json
{
  "donation_id": "uuid",
  "provider_payment_id": "pay_123",
  "status_token_hash": "sha256...",
  "method": "pix",
  "program": "edital-projetos",
  "amount_cents": 10000,
  "confirmed_at": "2026-10-02T12:01:30+00:00",
  "provider_event_id": "evt_123"
}
```

Para contribuições mensais, `provider_payment_id` é o ID `in_...` da primeira fatura paga e o registro inclui `provider_subscription_id` (`sub_...`). Registros antigos sem esse campo continuam válidos. O `donation_id` identifica a contribuição/assinatura e permite recuperar o questionário após o primeiro pagamento.

## recurring_payments.jsonl

Uma linha por fatura mensal efetivamente paga, com os mesmos campos de `PaymentConfirmation`, incluindo `provider_subscription_id`. A chave de idempotência é `provider_payment_id` (ID da fatura), não o `donation_id`. Duas faturas diferentes da mesma contribuição produzem duas entradas; reenviar a mesma fatura não produz outra entrada, mesmo após reinício.

Este arquivo não contém nome, e-mail ou CPF. Cada linha referencia o cadastro confirmado pelo `donation_id`; os dados do doador permanecem em `confirmed_donations.jsonl` uma única vez. Falhas de cobrança e cancelamentos não geram entradas pagas. `confirmed_at` registra o momento em que a aplicação processou a confirmação, e não a data de emissão da fatura.

## thank_you_outbox.jsonl e thank_you_sent.jsonl

A fila de agradecimentos contém somente `donation_id` e `provider_payment_id`. É criada após um pagamento confirmado, quando `EMAIL_ENABLED=true`, e deduplicada por cobrança/fatura. Nome, destinatário e conteúdo do email são obtidos do cadastro confirmado apenas no momento do envio; esses dados e CPF não são copiados para a fila.

O registro de envios contém os mesmos identificadores e `sent_at` (UTC), indicando aceitação pelo SMTP. Não é um comprovante de leitura ou de entrega na caixa de entrada. O worker envia apenas jobs vinculados a uma confirmação de pagamento e a um doador confirmado. Esses dois arquivos devem permanecer restritos, fora do frontend, e não ser versionados.
