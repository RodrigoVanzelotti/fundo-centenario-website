# Migração Wix, DNS e domínio

**Cutover bloqueado até inventário e preservação das páginas Wix.** Esta preparação
não altera DNS. `frontend/` só contém `/` e `/como-apoiar/`; copiar o site atual
inteiro ou inventar equivalências de conteúdo extrapola a preparação de infraestrutura.

## Evidências públicas de 16/10/2026

Consulta somente leitura via Resolve-DnsName (snapshot parcial, não export da zona):

| Registro | Resposta observada |
|---|---|
| NS apex | ns2.wixdns.net, ns3.wixdns.net |
| www CNAME | cdn3.wixdns.net |
| MX | aspmx.l.google.com prioridade 10; alt1 20; alt2 30; alt3 40; alt4 50 |
| TXT apex | Verificação Microsoft; nenhum v=spf1 na resposta consultada |
| _dmarc | CNAME _dmarc.wixemails.com; destino TXT com p=none |
| DKIM | Selector não informado; pendente export/admin Workspace |

Não inferir ausência de DKIM nem corrigir SPF/DMARC automaticamente. O CNAME DMARC
depende da Wix; manter DNS/conta enquanto houver dependências ou aprovar mudança
separada com administrador de email. MX confirma roteamento Google, não entrega real.

Busca pública encontrou `/quem-somos`, `/projetos` e documentos `/_files/ugd/...`.
Sitemap/robots do domínio apex não puderam ser obtidos pela ferramenta web; isso não
prova ausência. Links internos do código identificam outras URLs abaixo. O inventário
não substitui export do Wix e Search Console.

| Origem | Destino/ação antes do cutover | Estado |
|---|---|---|
| `/` | `/` | Implementado; revisão editorial pendente |
| `/como-apoiar/` | `/como-apoiar/` | Implementado; validar checkout staging |
| `/como-apoiar` | Normalização para diretório `/como-apoiar/` | Validar Hosting |
| `/edital-de-projetos` | Preservar página/conteúdo e inscrições; destino a aprovar | Bloqueador |
| `/programa-bolsa-de-permanencia` | Preservar elegibilidade/aplicação; destino a aprovar | Bloqueador |
| `/quem-somos` | Preservar governança/relatórios; destino a aprovar | Bloqueador |
| `/projetos` | Inventariar e preservar | Bloqueador |
| `/_files/ugd/*` | Exportar arquivos e mapear URLs, verificar links externos | Bloqueador |
| Demais URLs Wix/Search Console | Exportar e classificar 200/301/410 | Pendente |

Somente adicionar redirects 301 em firebase.json quando houver destino semanticamente
equivalente aprovado. Não redirecionar páginas ausentes para home, nem www para apex
antes de preservar seus caminhos. Search Console depende de acesso do proprietário.

## Preparação autorizada

- [ ] Exportar inventário Wix: URLs, PDFs/assets, títulos, formulários, campanhas e redirects.
- [ ] Exportar Search Console: páginas indexadas, landing pages, backlinks importantes.
- [ ] Migrar páginas faltantes e atualizar sitemap com destinos finais; testar todos os links.
- [ ] Exportar zona DNS completa pelo painel atual, incluindo A/AAAA/CNAME, MX,
  SPF, selectors DKIM, DMARC, verificações, CAA, TTL e nameservers. Guardar backup
  privado com data/responsável; consultas públicas não enumeram toda zona.
- [ ] Registrar valores exatos anteriores e novos em tabela de mudança aprovada.
- [ ] Preparar projetos isolados, staging validado, IAM, secrets, orçamento e alertas.
- [ ] Testar `PROJECT.web.app`, acesso direto/refresh, API, invalid webhook, retorno
  Stripe, consentimento e entrega de email com dados sintéticos.
- [ ] Firebase Hosting → Add custom domain → **Advanced Setup** para migração de
  hospedagem existente; adicionar apex e www. Copiar apenas os registros indicados
  pelo assistente daquele site. Não usar IPs genéricos deste documento.
- [ ] Autorizar manualmente registros de verificação/ACME que o assistente exigir,
  aguardar certificado pronto antes de trocar tráfego; conferir CAA com o operador.
- [ ] Escolher apex como canonical e configurar www como redirect preservando caminho
  e query; testar TLS nos dois hosts. Confirmar que Stripe usa origem final.
- [ ] Reduzir TTL somente de registros web se necessário, com antecedência de um TTL.

## Cutover — operador, após aprovação explícita

- [ ] Alterar somente A/AAAA/CNAME web indicados pelo Firebase. Remover conflito de
  apontamento antigo somente onde o assistente solicitar. Não trocar NS nem MX/TXT
  de email como parte desse procedimento.
- [ ] Conferir apex/www em múltiplos resolvers, TLS, redirects e URLs antigas.
- [ ] Executar smoke no domínio institucional, verificar checkout/Stripe autorizado,
  origem CORS, webhook e ausência de cache na API. Nunca confirmar pelo redirect.
- [ ] Testar envio/recebimento Workspace e SPF/DKIM/DMARC com administrador.
- [ ] Publicar sitemap no Search Console; verificar canonical e ausência de noindex
  em produção. Não instalar analytics novo sem definição de consentimento/finalidade.
- [ ] Monitorar 404, 5xx, latência, confirmações sem cadastro e email por 48–72h.

## Reversão

Se HTTPS, páginas, checkout ou email falharem, responsável restaura valores web
originais do export DNS, preservando todos os registros de email. Propagação depende
de TTL/cache; manter Wix ativo até validação completa. Webhooks já recebidos e banco
não são revertidos por DNS: manter backend e destino Stripe funcionando, reconciliar
pagamentos durante a transição e não apagar dados. Registrar horários de mudança.

Fontes: [migração avançada Firebase](https://firebase.google.com/docs/hosting/custom-domain),
[migração de hospedagem e SEO](https://developers.google.com/search/docs/crawling-indexing/site-move-no-url-changes),
[página Wix de governança](https://www.fundocentenario.com.br/quem-somos),
[página Wix de projetos](https://www.fundocentenario.com.br/projetos).
