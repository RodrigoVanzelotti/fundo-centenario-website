# Segurança da implementação estática

## Modelo de ameaça principal

No Pix pontual, o site não recebe senha nem dados bancários do doador. O principal risco passa a ser a adulteração do próprio site para substituir a chave Pix ou o destino do Pix Automático.

## Recomendações mínimas de produção

### Hospedagem

- HTTPS obrigatório;
- MFA nas contas de hospedagem e repositório;
- acesso de deploy limitado;
- branch protection no repositório;
- revisão de mudanças em `assets/js/config.js`;
- domínio e DNS protegidos por MFA.

### Dependências

A página usa `qrcode-generator@2.0.4` apenas para desenhar o QR Code.

Em produção, prefira servir uma cópia revisada localmente. Assim, a política pode evoluir para `script-src 'self'` e eliminar a execução de JavaScript de terceiros.

### Content Security Policy

A página `/como-apoiar/` já contém uma CSP compatível com o protótipo atual, permitindo scripts próprios e a versão fixada do jsDelivr.

Ao vendorizar a biblioteca de QR, use uma política mais restrita no servidor:

```text
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self' https://fonts.googleapis.com;
  font-src https://fonts.gstatic.com;
  img-src 'self' data:;
  connect-src 'none';
  object-src 'none';
  base-uri 'self';
  frame-ancestors 'none';
```

Observação: `frame-ancestors` deve ser enviado como header HTTP para proteção completa; não dependa apenas de uma meta tag.

### Pix Automático

- use somente HTTPS;
- mantenha uma allowlist de domínios do PSP em `allowedHosts`;
- não construa URLs com domínios vindos de parâmetros do usuário;
- não aceite uma URL de redirecionamento informada por query string;
- nunca exponha tokens ou certificados.

### Conferência pelo doador

A interface orienta o usuário a conferir no aplicativo do banco o nome do recebedor antes de autorizar a transação.

Essa etapa é importante porque o nome efetivamente exibido pelo app é obtido a partir da chave Pix no DICT.

## Limitações conhecidas

Sem backend, não há:

- confirmação automática de pagamento;
- webhook;
- conciliação automática;
- emissão de recibo;
- painel de doações;
- proteção contra alguém pagar o mesmo QR mais de uma vez;
- criação de recorrência via API privada.

Essas limitações são intencionais no MVP estático.
