# Integração de pagamentos

## Visão geral

Esta implementação foi desenhada para permanecer estática.

```text
SITE ESTÁTICO
HTML + CSS + JavaScript
        |
        +-------------------+
        |                   |
  DOAR UMA VEZ         DOAR TODO MÊS
        |                   |
        v                   v
 JavaScript gera       Redirecionamento
 QR Pix estático       para banco / PSP
        |                   |
        v                   v
  App do banco          Pix Automático
        |                   |
        v                   v
    Pagamento             Autorização
```

## 1. Pix pontual

Arquivo de configuração:

```text
assets/js/config.js
```

Preencha:

```js
pix: {
  enabled: true,
  key: "SUA_CHAVE_PIX_OFICIAL",
  merchantName: "FUNDO CENTENARIO",
  merchantCity: "PORTO ALEGRE",
  txidPrefix: "FC",
  defaultAmount: 100,
}
```

### O que é necessário

- chave Pix oficial registrada no DICT;
- Merchant Name para composição do BR Code, com no máximo 25 caracteres;
- Merchant City, com no máximo 15 caracteres.

### O que NÃO é necessário

Não há autenticação em API bancária para criar um QR Code estático. Portanto, não é necessário colocar no site:

- client ID bancário;
- client secret;
- token OAuth;
- senha;
- certificado;
- chave privada;
- webhook.

A criação local da string BR Code não é uma operação da API Pix. O pagamento continua sendo autenticado no aplicativo do banco do doador.

### txid

A implementação gera um `txid` local com letras e números e tamanho máximo de 25 caracteres.

Isso permite que o identificador viaje com a transação. Porém, sem acesso à API do PSP/conta recebedora, o site não consegue consultar automaticamente se esse txid foi pago.

## 2. Pix Automático

O modo totalmente estático só funciona se o banco/PSP oferecer uma URL pública e hospedada de autorização.

Exemplo conceitual:

```js
pixAutomatico: {
  enabled: true,
  redirectUrlTemplate: "https://pagamentos.seubanco.com.br/fundo-centenario",
  allowedHosts: ["pagamentos.seubanco.com.br"],
}
```

O botão da página valida:

1. `https://` obrigatório;
2. hostname presente em `allowedHosts`;
3. configuração explicitamente habilitada.

### Placeholders opcionais

O código aceita os placeholders abaixo na URL:

```text
{amount}      -> 100.00
{amountCents} -> 10000
{returnUrl}   -> URL de retorno codificada
```

Use esses placeholders SOMENTE se o banco/PSP documentar oficialmente que sua URL hospedada aceita esses parâmetros.

Exemplo:

```js
redirectUrlTemplate:
  "https://pagamentos.seubanco.com.br/fundo?valor={amountCents}&retorno={returnUrl}"
```

Não presuma que todo provedor aceita valor via query string.

## 3. Credenciais bancárias: regra principal

### Podem estar no frontend

Somente informações públicas:

- chave Pix;
- nome do Fundo;
- cidade;
- URL pública de autorização do PSP;
- hostname público do PSP;
- URL de retorno.

### Nunca podem estar no frontend

Se o banco fornecer qualquer um destes itens, NÃO coloque em `config.js`:

```text
client_secret
access_token privado
API secret
certificado mTLS
chave privada
senha
segredo HMAC
refresh_token
credencial OAuth confidencial
```

O navegador entrega todo JavaScript ao visitante. Qualquer segredo colocado nele deixa de ser segredo.

## 4. Quando um backend passa a ser obrigatório

Será necessário adicionar uma função serverless ou backend se o banco/PSP exigir:

- OAuth com `client_secret`;
- mTLS;
- assinatura de requisições com chave privada;
- criação da recorrência por API;
- geração de URL de autorização de curta duração;
- consulta de pagamentos;
- webhook de confirmação;
- emissão automática de recibo;
- conciliação automática;
- painel de doadores.

Uma arquitetura mínima futura seria:

```text
Browser
  |
  v
POST /api/pix-automatico
  |
  v
Função serverless
  |
  +-- guarda segredo / certificado
  +-- chama API do PSP
  |
  v
URL ou QR de autorização
```

A página atual não implementa esse backend.

## 5. Confirmação de pagamento

Com esta versão estática:

- o QR Code pode ser gerado;
- o banco pode efetivar o Pix;
- o site NÃO recebe confirmação automática do pagamento.

Não exiba uma mensagem do tipo "pagamento confirmado" apenas porque o usuário clicou ou escaneou o QR Code.

Para confirmar pagamentos automaticamente será necessário consultar a API Pix/PSP ou receber webhooks em um backend.

## 6. Dados que precisam ser fornecidos pelo Fundo antes da publicação

Checklist:

```text
[ ] Chave Pix oficial
[ ] Nome legal do recebedor para conferência visual
[ ] Merchant Name desejado no BR Code
[ ] Merchant City
[ ] Banco/PSP que mantém a conta recebedora
[ ] O banco/PSP oferece Pix Automático para recebedor PJ?
[ ] Existe fluxo hospedado de autorização?
[ ] URL pública do fluxo hospedado
[ ] Host oficial dessa URL
[ ] O provedor aceita valor via URL? Se sim, em qual formato?
[ ] Existe URL de retorno documentada?
```

Se o PSP não oferecer fluxo hospedado, o requisito "Pix Automático sem backend" deve ser revisto.
