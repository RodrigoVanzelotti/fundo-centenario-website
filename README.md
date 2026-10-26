# Fundo Centenário: site estático + backend de pagamentos

Implementação de referência para o fluxo de contribuição do Fundo Centenário.

## Arquitetura

```text
Browser
  |
  | / e /como-apoiar/
  v
Frontend estático
  |
  | POST /api/donations/intents
  v
FastAPI backend
  |
  +--> Stripe: Checkout para Pix, cartão e assinatura mensal
  |
  <--- webhook de confirmação
  |
  +--> backend/data/payment_confirmations.jsonl   (sem questionário)
  +--> backend/data/recurring_payments.jsonl       (faturas mensais, sem questionário)
  +--> backend/data/confirmed_donations.jsonl     (questionário, somente após pagamento)
```

Rotas do site:

- `/` -> página inicial
- `/como-apoiar/` -> questionário + fluxo de pagamento
- `/api/*` -> backend

## Métodos implementados

1. **Pix pontual**: Checkout hospedado da Stripe apresenta o QR Code e o Pix Copia e Cola.
2. **Cartão pontual**: Checkout hospedado da Stripe recebe os dados de pagamento.
3. **Cartão mensal**: Checkout cria a assinatura. Cada fatura paga gera um registro, sem duplicatas.

A mesma integração Stripe atende local, staging e produção. As credenciais fornecidas pelo ambiente definem test/live; o código não seleciona provedores nem credenciais por ambiente. A pipeline injeta os segredos do projeto selecionado e valida test em staging e live em produção. A API expõe somente os três métodos acima. Pix Automático não é oferecido nesta integração.

Configure as chaves e o webhook conforme [INTEGRATION.md](INTEGRATION.md#stripe-contribuição-mensal-no-cartão). O retorno do navegador nunca confirma pagamento; somente eventos Stripe autenticados confirmam a contribuição.

## Questionário

O formulário mostra uma etapa por vez: valor e forma de contribuição; programa, dados pessoais e consentimentos; pagamento no Checkout Stripe. O botão `Voltar` permite revisar as escolhas sem apagar os dados. A cobrança só é criada ao concluir a segunda etapa.

Os avisos de erro são limpos ao interagir com o formulário ou recarregar a página. Um retorno da Stripe sem sessão válida exibe um aviso e remove a referência da URL para que o aviso não se repita a cada recarga.

Antes do pagamento são coletados:

- nome;
- e-mail;
- CPF;
- preferência principal de destinação;
- opt-in opcional para comunicações institucionais.

Programas disponíveis:

- Edital de projetos;
- Programa de Bolsas de Permanência;
- Programa de Mentoria;
- Masterclasses e conteúdo Alumni;
- Contribuição geral.

### Regra de persistência

No modo local, o questionário fica somente em memória enquanto o pagamento está pendente. No Firestore, ele não é mantido na intenção: permanece na sessão do navegador até a finalização após confirmação.

`confirmed_donations.jsonl` só recebe o registro depois de uma confirmação `paid` válida da Stripe.

O backend mantém também `payment_confirmations.jsonl`, que não contém nome, e-mail nem CPF. Ele permite recuperar o fluxo se o processo reiniciar entre o pagamento e a gravação final do questionário.

## Produção: Cloud Run e Firestore

A aplicação está preparada para persistência externa no Firestore e CI/CD pelo GitHub Actions. O procedimento completo de Google Cloud, Firebase, identidades, segredos, primeiro deploy, Scheduler, migração e rollback está em [DEPLOYMENT.md](DEPLOYMENT.md). Staging e produção exigem Firestore. A pipeline seleciona as credenciais Stripe de cada ambiente. Firebase Hosting serve o frontend estático e encaminha `/api/**` ao Cloud Run na mesma origem; o container preserva o frontend para desenvolvimento local.

Em produção, intenções guardam somente dados de pagamento e autenticação, sem nome/email/CPF. O cadastro é enviado pelo navegador a `/finalize` depois da confirmação validada. Confirmações, faturas e pedidos de email são gravados em transação; o Scheduler processa uma outbox com leases e retries, sem depender de um worker permanente.

## Rodar localmente

Requer Python 3.11+.

```bash
cd fundo-centenario-payments
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows PowerShell
pip install -r backend/requirements.txt -r backend/requirements-dev.txt
cp backend/.env.example backend/.env
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Abra:

```text
http://localhost:8000/
http://localhost:8000/como-apoiar/
```

Preencha `STRIPE_SECRET_KEY` com uma chave de teste e `STRIPE_WEBHOOK_SECRET` com o segredo da Stripe CLI em `backend/.env` antes de iniciar. Execute `stripe listen` conforme [INTEGRATION.md](INTEGRATION.md). Sem credenciais Stripe, o backend recusa a inicialização.

O `.env.example` contém a configuração local e os campos básicos para habilitar email. Firestore e Scheduler são configurados pela pipeline; opções de limites, caminhos e personalização usam os padrões de `backend/app/config.py` quando omitidas. Se alterar a origem local, defina também `CORS_ORIGINS` com a mesma origem de `PUBLIC_BASE_URL`. Host e porta são argumentos do Uvicorn; no container, a porta usa `PORT`.

## Containers

O `docker-compose.yml` é exclusivo para desenvolvimento local:

```bash
docker compose up --build
```

As dependências são instaladas durante o build, e o container inicia diretamente o Uvicorn. O Compose monta o código para recarga automática e usa Stripe. Ao alterar `backend/requirements.txt`, reconstrua a imagem. Os dados locais ficam no volume `donation-data`, separado de `backend/data` usado ao executar Python diretamente. `docker compose down` preserva o volume; a opção `--volumes` apaga esses dados. O Compose carrega `backend/.env` para as credenciais Stripe e mantém emails desabilitados. Para encaminhar webhooks, rode a Stripe CLI no host.

Para produção, construa a imagem na raiz do repositório e publique o artefato no registry utilizado pela infraestrutura:

```bash
docker build --pull -t fundo-centenario:VERSAO .
```

O Dockerfile inclui backend, template de email e frontend, roda como UID/GID `10001:10001` e inicia um único worker, sem recarga e sem instalar pacotes no startup. O `.dockerignore` restringe o contexto de build e exclui `.env`, dados JSONL e chaves privadas, conforme as [práticas de build do Docker](https://docs.docker.com/build/building/best-practices/).

No ambiente de produção, injete configurações e segredos em runtime pelo Secret Manager. Configure Stripe e a origem pública conforme [DEPLOYMENT.md](DEPLOYMENT.md). A porta é definida por `PORT`, com fallback local `8000`; TLS é terminado pela plataforma.

No Cloud Run, use `STORAGE_BACKEND=firestore`, com projeto, identidade e banco privado. Não monte JSONL como persistência de produção. A imagem usa lock com hashes e base fixada por digest; o workflow implanta uma imagem testada por digest. Dados locais existentes exigem migração explícita e reconciliação.

## Testar pagamentos localmente

1. Configure uma chave Stripe de teste e encaminhe os eventos pela Stripe CLI.
2. Abra `/como-apoiar/`, escolha Pix, cartão pontual ou cartão mensal e preencha o questionário.
3. Conclua o pagamento no Checkout Stripe com os dados de teste oficiais.
4. O webhook assinado confirma o pagamento; o retorno ao site consulta essa confirmação.
5. O cadastro é persistido uma vez, somente após pagamento confirmado.

Não há endpoint ou botão de confirmação manual. Consulte [INTEGRATION.md](INTEGRATION.md) para eventos, recorrência e recuperação.

## Email de agradecimento

Após a confirmação e o cadastro do doador, o backend envia um agradecimento transacional por SMTP com TLS. O HTML está em [backend/templates/donation_thank_you.html](backend/templates/donation_thank_you.html) e usa os parâmetros `${donor_name}`, `${amount}`, `${cause}`, `${contribution_type}`, `${thank_you_text}` e `${activity_url}`. O email não contém CPF. Há também uma versão em texto simples.

O envio vem desabilitado em `backend/.env` e `backend/.env.example`. Para ativar, preencha as credenciais e o remetente; as demais opções abaixo são personalizações opcionais:

```env
EMAIL_ENABLED=true
SMTP_HOST=smtp.seu-provedor.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=SEU_USUARIO_SMTP
SMTP_PASSWORD=SUA_SENHA_OU_APP_PASSWORD
EMAIL_FROM_ADDRESS=doacoes@seu-dominio.com
EMAIL_FROM_NAME="Fundo Centenário"
EMAIL_REPLY_TO=contato@seu-dominio.com
EMAIL_SUBJECT="Obrigado por apoiar o Fundo Centenário"
EMAIL_ACTIVITY_URL=https://seu-dominio.com/#impacto
```

Para TLS desde a conexão inicial, use `SMTP_SECURITY=ssl` e a porta indicada pelo remetente, normalmente `465`. Conexões sem TLS não são aceitas. Use as credenciais SMTP específicas do serviço e um remetente autorizado por ele. Os parâmetros nunca são expostos pela API ou pelo frontend. Reinicie o backend após alterar o `.env`.

`EMAIL_TEMPLATE_PATH` vazio seleciona o template padrão; um caminho personalizado é resolvido a partir do diretório em que o backend é iniciado. `EMAIL_THANK_YOU_TEXT` personaliza o agradecimento e o convite para conhecer as atividades. `EMAIL_ACTIVITY_URL` vazio aponta para `PUBLIC_BASE_URL/#impacto`; em produção, configure uma URL pública HTTPS.

No modo local, a fila é persistida em `thank_you_outbox.jsonl` e processada em uma thread fora do webhook a cada 30 segundos. No Firestore, ela é processada pelo endpoint OIDC do Scheduler, com reserva transacional; não há loop permanente. Falhas ficam pendentes para retry, inclusive após reinício. O envio exige pagamento e cadastro confirmados, inclusive após `/finalize`.

Cada pagamento gera um pedido de envio. Na recorrência, cada fatura efetivamente paga recebe seu próprio agradecimento. Webhooks repetidos não criam novos pedidos, e `thank_you_sent.jsonl` evita repetir emails já aceitos pelo SMTP. Assinaturas e doações antigas não são varridas para disparo retroativo. Com `EMAIL_ENABLED=false`, nenhum novo pedido é criado e a fila existente não é processada.

SMTP não garante entrega exatamente uma vez: se aceitar o email e o processo parar antes do registro, o retry pode duplicá-lo. O `Message-ID` permanece estável. Aceitação SMTP não comprova entrega na caixa de entrada. A persistência local exige um processo; Firestore coordena instâncias distintas, mas não torna SMTP e banco uma transação única. Para eliminar essa janela, use um serviço de email com idempotência.

O agradecimento é relativo ao pagamento, independentemente do opt-in de novidades; ele não cadastra o doador em uma lista de divulgação. SMTP utiliza [smtplib da biblioteca padrão](https://docs.python.org/3/library/smtplib.html), sem dependências adicionais.

## Testes

```bash
pytest -q
node tests/frontend-static.test.js
node tests/donation-steps.test.js
```
