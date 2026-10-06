# Segurança e privacidade

Este projeto trata pagamentos e informações pessoais. O código reduz o escopo de risco, mas a publicação em produção ainda exige revisão de segurança, privacidade e operação.

## O que nunca deve existir no frontend

- `client_secret`;
- API key secreta;
- token Bearer privado;
- certificado ou chave privada;
- senha bancária;
- segredo de webhook;
- número de cartão;
- CVV;
- validade do cartão.

Esses dados devem ficar no backend/secret manager.

## Questionário

O formulário coleta:

- nome;
- e-mail;
- CPF;
- preferência de destinação;
- autorização opcional para comunicações institucionais.

O arquivo `backend/data/confirmed_donations.jsonl` contém PII e recebe permissão `0600` quando possível.

Ele **não deve**:

- ficar dentro de `frontend/`;
- ser versionado no Git;
- ser disponibilizado por Nginx/Apache/StaticFiles;
- ser copiado para buckets públicos;
- aparecer em logs de aplicação.

## Regra de gravação

O questionário não é escrito em disco enquanto o pagamento está pendente.

A confirmação de pagamento é registrada separadamente em `payment_confirmations.jsonl` sem nome, e-mail ou CPF. Isso serve para idempotência e recuperação do fluxo.

## HTTPS

Em produção, force HTTPS para:

- site;
- API;
- `return_url`;
- `webhook_url`;
- PSP.

Não transmita CPF em HTTP.

## Webhooks

### Stripe

O adapter valida o corpo bruto com HMAC-SHA256 sobre `timestamp.corpo`, aceita apenas assinaturas `v1` e exige timestamp dentro de 300 segundos do relógio local, incluindo rejeição de timestamps futuros fora dessa janela. Também verifica modo test/live e versão da API. O endpoint limita o corpo a 1 MiB. Configure NTP e o segredo do endpoint correto; não envie payloads completos ou cabeçalhos de autenticação aos logs.

Recorrência só é confirmada por `invoice.payment_succeeded`, com status `paid`, saldo restante zero, valor contratado e moeda BRL. Conclusão do Checkout, autorização, retorno do navegador e `invoice.paid` não comprovam o pagamento mensal. Metadata recebida deve corresponder ao token, método, programa e valor da contribuição conhecida; renovações devem pertencer à mesma assinatura.

O ID da fatura deduplica as cobranças mensais em disco. Falhas de gravação não impedem uma nova tentativa do webhook. Arquivos novos são criados com modo `0600` nos sistemas que o suportam, e erros detectados de escrita são revertidos. Arquivos JSONL corrompidos impedem a inicialização em vez de serem silenciosamente ignorados. Configure ACLs equivalentes no Windows e mantenha backups restritos.

`DATA_DIR` dentro da pasta pública do frontend é rejeitado. No modo local, nome/e-mail/CPF permanecem apenas na memória pendente; no Firestore, permanecem na sessão do navegador até `/finalize`. São escritos no cadastro confirmado somente após pagamento. O ledger de renovações não contém esses campos. A Stripe coleta os dados de pagamento exclusivamente no Checkout; a aplicação não envia o questionário em metadata ou parâmetros de URL. Respostas de erro da API Stripe não são repassadas ao frontend.

O modo JSONL local suporta um processo/worker. Produção usa Firestore: confirmação, fatura e outbox são transacionais, e a reserva de emails coordena instâncias distintas. Intenções não contêm questionário; `/finalize` revalida confirmação e token antes do cadastro. Firebase nega clientes; o backend usa IAM. Tokens são credenciais de sessão e não devem aparecer em analytics, URLs ou logs. Histórico pago não equivale a assinatura ativa.

Nunca aceite o status enviado pelo navegador como prova de pagamento.

A prova deve vir do PSP e passar por:

1. verificação criptográfica da assinatura;
2. validação de identificador/referência externa;
3. validação do status;
4. idempotência;
5. quando possível, validação de valor e moeda.

O `generic_http` contém HMAC-SHA256 apenas como implementação genérica. Adapte para o algoritmo oficial do PSP.

## Cartão

O projeto usa checkout hospedado. Isso reduz o escopo de dados de cartão, mas não elimina automaticamente todas as obrigações PCI DSS da organização. Confirme o modelo de integração e o escopo aplicável com o PSP e a equipe responsável.

## CPF e minimização

CPF é dado pessoal. Antes de produção, documente por que ele é necessário, quem terá acesso, prazo de retenção, forma de exclusão e a base jurídica aplicável ao tratamento.

Se o CPF não for necessário para controle, comprovante, obrigações contábeis/fiscais ou outra finalidade definida, considere removê-lo por minimização de dados.

## Agradecimentos por email

Credenciais SMTP ficam somente no `.env`/secret manager do backend. STARTTLS ou TLS desde a conexão inicial são obrigatórios, com validação de certificado e hostname; autenticação ocorre somente após TLS. Não habilite debug SMTP, pois ele pode expor credenciais, destinatários e conteúdo. Logs de falhas registram apenas a classe da exceção.

O HTML escapa os parâmetros interpolados. Headers e endereços são construídos com `EmailMessage`/`Address`; o assunto não aceita quebras de linha. O email inclui nome, valor, causa e forma de contribuição, sem CPF, tokens ou dados de cartão. Links para atividades não incluem informações do doador. O template fica no backend, não há endpoint público para enviar mensagens arbitrárias e nenhum email é enviado por redirects ou autorização de assinatura.

A fila contém referências opacas e só é preenchida após confirmação validada. O worker exige o cadastro confirmado e revalida a referência de pagamento antes de enviar. Tentativas de recuperação sem pagamento ou token correto não criam emails. O processamento SMTP ocorre fora do webhook e do lock de pagamentos; sua indisponibilidade não desfaz nem bloqueia a confirmação.

O agradecimento é transacional e não altera o opt-in de novidades. Configure retenção e acesso no remetente. SMTP e registro de aceitação não são uma transação única: uma interrupção pode produzir duplicata. O worker local exige um processo. Em produção, Scheduler chama uma rota com verificação OIDC de audience e identidade, e a outbox usa lease transacional expirável.

## Recomendações de infraestrutura

- MFA para contas de deploy e PSP;
- secrets em secret manager, não em `.env` no servidor quando houver opção melhor;
- usuário de processo sem privilégios;
- rate limiting para criação de intents;
- WAF/reverse proxy;
- logs sem PII;
- backup criptografado do arquivo confirmado;
- acesso ao arquivo restrito à equipe autorizada;
- monitoramento de webhooks rejeitados;
- política de retenção e descarte;
- revisão periódica das dependências.

## Deploy e fronteiras de confiança

Consulte [DEPLOYMENT.md](DEPLOYMENT.md). Produção exige Firestore e Stripe live; staging aceita Stripe test. Configurações incompatíveis falham na inicialização, e arquivos de chave/emulator são rejeitados nesses ambientes. Segredos são injetados por versão numérica. O CI usa WIF/OIDC restrito, sem chave Google de longa duração.

API não é cacheável. HTML recebe CSP por header, nosniff, Referrer-Policy e Permissions-Policy. Requisições são limitadas a 32 KiB, exceto webhooks (1 MiB). Falhas inesperadas registram apenas a classe da exceção e retornam erro genérico. Não configure captura de bodies/tokens na infraestrutura.

A criação exige UUID de idempotência em staging/produção. Essa credencial opaca é distinta da referência pública da contribuição e não deve aparecer em logs/analytics. O registro contém token e resposta PSP, sem questionário, e exige acesso restrito. Retries reutilizam a referência no PSP; tentativas antigas sem resposta não criam cobrança automaticamente.
