# Fundo Centenário: site estático + contribuição Pix

Implementação estática com duas rotas:

- `/` -> página inicial
- `/como-apoiar/` -> página de contribuição

A página de contribuição oferece:

1. Pix pontual: geração local de BR Code, QR Code e Pix Copia e Cola.
2. Pix Automático: redirecionamento para uma experiência hospedada pelo banco/PSP.

## Rodar localmente

Na raiz do projeto:

```bash
python3 -m http.server 8080
```

Abra:

```text
http://localhost:8080/
http://localhost:8080/como-apoiar/
```

Evite testar abrindo os arquivos diretamente com `file://`, pois a navegação por rotas e algumas políticas do navegador diferem de um servidor HTTP.

## Antes de publicar

1. Edite `assets/js/config.js`.
2. Configure a chave Pix oficial.
3. Valide nome e cidade usados no BR Code.
4. Se houver Pix Automático, configure apenas uma URL pública hospedada pelo banco/PSP e o domínio permitido.
5. Nunca coloque segredos bancários no JavaScript.
6. Leia `INTEGRATION.md` e `SECURITY.md`.

## Dependência visual do QR Code

O payload Pix é gerado pelo código local `assets/js/pix.js`.

A transformação visual do payload em QR Code usa a biblioteca MIT `qrcode-generator` 2.0.4, carregada de uma URL versionada do jsDelivr.

Para produção, a recomendação é baixar essa versão revisada e servi-la localmente em `assets/vendor/`, removendo a dependência de CDN.

Mesmo se a biblioteca de QR não carregar, o payload Pix Copia e Cola continua sendo produzido pelo código local.

## Teste do BR Code

O projeto inclui um teste contra o exemplo oficial do Manual de Padrões do Pix:

```bash
node tests/pix-payload.test.js
```
