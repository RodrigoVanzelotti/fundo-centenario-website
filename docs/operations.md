# Operação, custos e recuperação

## Monitoramento proporcional

Cloud Run já fornece contagem, latência e status das requisições. A aplicação emite
JSON `http_request` com severity, request_id gerado pelo servidor, template da rota,
método, status e duration_ms. Falhas inesperadas incluem apenas classe do erro e
mesmo request_id. Não registra corpo, query, CPF, IP, token ou headers arbitrários.
Mensagens preexistentes de email registram só a classe da exceção. Uvicorn access
log continua desabilitado. Logs gerenciados da plataforma podem incluir URLs/IPs;
restrinja IAM, retenção e não coloque PII na URL. Não habilitar captura de payload.

Criar e testar em staging, depois produção, pelo Monitoring Console (não criados
por esta preparação):

| Sinal | Configuração inicial | Ação |
|---|---|---|
| Indisponibilidade | Uptime HTTPS `/api/health`, 5 min; alerta após 2 falhas | Verificar revisão, startup e segredos; não usar ready no monitor contínuo |
| 5xx | >=5 erros em 5 min ou razão >5% com >=20 requests | Inspecionar request_id e dependências; rollback se regressão |
| Latência | p95 >5s por 10 min, avaliar tamanho da amostra | Conferir Stripe, Firestore e cold starts |
| Abuso | Volume >100/min por 5 min ou >=10 respostas 429 | Investigar origem/PSP; limite global pode prejudicar doadores |
| Scheduler | Falhas consecutivas e job atrasado >15 min | Conferir OIDC, audience e SMTP; manter outbox |
| Emails | Logs `Agradecimento pendente` | Revisar retries/leases; nunca copiar destinatários para incidentes públicos |
| Dados | Firestore leituras/escritas/armazenamento; Hosting transferência; Run CPU/memória/instâncias | Revisão semanal no início, mensal após estabilização |

Escolher responsável e canal de notificação e testar a entrega. Logs Explorer:
`resource.type="cloud_run_revision" AND jsonPayload.message="request_failed"`.
Criar métrica baseada no log `http_request` se precisar de rota normalizada. Revisar
semanalmente idade/tamanho da outbox e confirmações sem cadastro, por operação
administrativa restrita; não criar endpoint público para essas consultas.
Mínimo zero mantém cold starts; medir p95 real antes de aumentar instâncias.

## FinOps e estimativa

Hipóteses, não cotação: 350 visitas/250 requests mensais; pico 1.196 visitas/8.543
requests, execução média 1s, memória 0,5 GiB. Pico equivale a aproximadamente 8.543
vCPU-s e 4.272 GiB-s, mais cold starts, probes, webhooks, polling e Scheduler.
Franquias Run são créditos compartilhados na conta e variam em equivalência regional.
O Scheduler a cada 5 minutos adiciona ~8.640 chamadas/mês: ainda pequeno, mas
supera a API média. Só criá-lo se habilitar emails. Não usar instâncias permanentes.

O artefato estático completo medido tem aproximadamente 0,24 MB (sem fontes externas).
Mesmo transferindo-o integralmente uma vez por visitante no pico seriam ~0,29 GB.
Isso não mede visitas repetidas, tráfego de bots nem bytes reais transferidos. Não
recomprimir logos pequenos nem introduzir bundler; CSS/JS já são pequenos. Fonts
externas e imagens de fundo precisam de medição mobile real antes do lançamento.

Hosting Blaze inclui 10 GB/mês de transferência, excedente documentado US$0,15/GB;
1.196 visitantes dão ~8,36 MB/visitante como referência. Firestore tem franquia
diária, mas TTL, backups/PITR e restauração podem ser cobrados separadamente.
Considerar Artifact Registry (retenção de imagens), Secret Manager, rede São Paulo,
logs, Scheduler e dois ambientes. Estimativa de planejamento: **US$0–5/mês de GCP**
nesse volume, sob franquias disponíveis e retenção moderada; reservar US$10 e revisar
após uma semana e um mês. Não inclui Stripe, SMTP, domínio, Workspace, GitHub pago,
impostos/câmbio ou grandes backups. Sem promessa de custo zero/créditos nonprofits.

Criar orçamento **US$10/mês**, abrangendo ambos os projetos, alertas em **50%, 80%,
100%** (e previsão). Orçamento e máximo 3 instâncias não suspendem cobranças. Usar
cobrança Run por requisição (`--cpu-throttling`). Antes de criar o banco, conferir
pricing de southamerica-east1; alternativa US exige revisão de residência/latência.

Fontes de preço (revalidar no provisionamento):
[Run](https://cloud.google.com/run/pricing),
[Hosting](https://firebase.google.com/docs/hosting/usage-quotas-pricing),
[Firestore](https://cloud.google.com/firestore/pricing),
[Artifact Registry](https://cloud.google.com/artifact-registry/pricing),
[Scheduler](https://cloud.google.com/scheduler/pricing),
[Secret Manager](https://cloud.google.com/secret-manager/pricing).

## Release e rollback

Guardar SHA, digest, revisão Run e versão Hosting em cada release; workflow escreve
SHA/revisão/digest no summary, Firebase registra a mensagem da versão. Não apagar
imagens/tags referenciadas por revisões ativas ou rollback.

1. Pausar novos deploys. Identificar última versão validada do mesmo backend Firestore.
2. Console Firebase → Hosting → histórico → rollback da versão estável. `pinTag`
   restaura a referência à revisão correspondente junto com os arquivos estáticos.
3. Restaurar também tráfego nativo Run para Scheduler/webhooks que o usem:

```bash
gcloud run services update-traffic "$SERVICE" --project "$PROJECT" --region "$REGION" --to-revisions REVISAO_ESTAVEL=100
python tools/smoke.py "https://$PROJECT.web.app" --production
python tools/smoke.py "$RUN_URL" --production --api-only
```

4. Conferir secrets numéricos, logs, pagamento de teste autorizado e outbox. Rollback
   de código não restaura dados. JSONL antigo não é rollback válido após Firestore.
5. Se falha ocorreu após promover Run mas antes de Hosting, restaurar Run; se depois
   de Hosting, restaurar ambos. Não declarar release concluído com smoke final falho.

Tags pinTag têm limites de plataforma. Mensalmente, inventariar versões Hosting,
tags/revisões Run e imagens. Manter ao menos versão ativa e duas estáveis anteriores
por ambiente; ampliar conforme prazo de incidentes. No Artifact Registry, ensaiar
cleanup em dry-run para imagens sem referência e antigas (>30 dias), revisar lista
e só então autorizar exclusão. Não aplicar regra automática que apague toda imagem
untagged: referências por digest/revisões e rollbacks precisam ser consideradas.

## Dados, retenção e recuperação

ADC runtime só no próprio projeto; acesso humano com MFA e papéis temporários.
TTL pendências 30 dias e buckets de rate limit 1 dia; exclusão TTL é assíncrona.
Intents guardam token/resposta, mas não nome/email/CPF; não têm TTL hoje porque
remover idempotência pode recriar cobrança em retry antigo. Não adicionar TTL sem
decidir janela de retry e tombstones. Confirmações/faturas/outbox não têm exclusão
automática: preservam deduplicação. Prazo contábil/finalidade do CPF dependem da
instituição; bloquear lançamento até decisão documentada, sem inventar prazo legal.

Procedimento LGPD: validar identidade do solicitante por atendimento restrito,
localizar donation_id, conferir assinaturas/obrigações de retenção e encerrar opt-in;
remover/anonimizar apenas cadastro elegível e dados do SMTP/listas conforme política,
mantendo referências financeiras necessárias e marcadores de deduplicação. Registrar
ação sem copiar PII. Backups exigem retenção/lifecycle compatíveis. Um retry de finalize
pode recadastrar dados apagados: antes de executar exclusão, definir e ensaiar um
mecanismo de bloqueio de recadastro que preserve a validação de metadata dos webhooks.
Não rotacionar hashes isoladamente: isso pode rejeitar renovações legítimas. Esse
procedimento ainda exige revisão institucional e ensaio; não há endpoint de exclusão
automatizada no MVP. A política aprovada é um gate de lançamento.

Habilitar backup gerenciado/PITR somente após aprovar custo e retenção. Restaurar
em banco/projeto isolado, conferir contagens, IDs, primeira confirmação e deduplicação,
reconciliar eventos Stripe recebidos após o backup, testar antes de trocar produção.
RPO/RTO ainda dependem da política aprovada; sugestão para decisão: RPO 24h e RTO 4h,
com reconciliação PSP. Backups sem restauração ensaiada não satisfazem o gate.
Não exportar PII para Git, artefatos CI, logs ou buckets públicos.

SMTP pode duplicar email se aceitar e o processo morrer antes do marcador; lease
expira em 5 min e retry tem backoff. Não apagar outbox para corrigir incidente.
Perda de sessionStorage pode impedir associação do questionário a pagamento;
atendimento deve reconciliar sem confirmar pagamento por relato do navegador.
