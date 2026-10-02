/*
 * CONFIGURAÇÃO PÚBLICA DO SITE
 *
 * Este arquivo é enviado ao navegador. NUNCA coloque aqui:
 * - client_secret
 * - access_token privado
 * - API key secreta
 * - certificado/chave privada
 * - senha bancária
 * - segredo HMAC
 *
 * Leia INTEGRATION.md antes de publicar.
 */
window.FUNDO_CONFIG = Object.freeze({
  organization: {
    displayName: "Fundo Centenário",
    legalReceiverName: "Associação Fundo Patrimonial Escola de Engenharia",
  },

  pix: {
    enabled: true,

    // Configure a chave Pix oficial do Fundo e então altere enabled para true.
    // Pode ser e-mail, telefone, CNPJ ou chave aleatória válida no DICT.
    key: "rodrigovanzelotti@gmail.com",

    // Campos do BR Code. O nome é limitado a 25 caracteres e a cidade a 15.
    merchantName: "FUNDO CENTENARIO",
    merchantCity: "PORTO ALEGRE",

    // Prefixo usado para gerar um txid local de até 25 caracteres.
    txidPrefix: "FC",

    // Valor inicial exibido ao usuário.
    defaultAmount: 100,
  },

  pixAutomatico: {
    enabled: false,

    /*
     * Use SOMENTE uma URL pública/estável de autorização hospedada pelo banco/PSP.
     * Exemplo conceitual:
     * https://pagamentos.seu-psp.com/fundo-centenario/pix-automatico
     *
     * Se o provedor exigir OAuth, client_secret, certificado, token privado ou
     * criação de recorrência via API, esta integração NÃO pode ser feita só no frontend.
     */
    redirectUrlTemplate: "",

    // Lista de hosts autorizados para impedir redirecionamento acidental para outro domínio.
    // Exemplo: ["pagamentos.seubanco.com.br"]
    allowedHosts: [],

    /*
     * Alguns provedores podem documentar placeholders em uma URL hospedada.
     * O site entende estes três, mas só os use se a documentação do PSP permitir:
     * {amount}       -> 100.00
     * {amountCents}  -> 10000
     * {returnUrl}    -> URL codificada de retorno ao site
     */
  },
});
