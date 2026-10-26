# Relatório de benefícios e custos de infraestrutura

**Fundo Centenário da UFRGS**

**Referência:** Outubro de 2026  
**Domínio:** fundocentenario.com.br  
**Região de processamento e dados:** `southamerica-east1` — São Paulo, Brasil  
**Arquitetura:** Firebase Hosting + Cloud Run + Cloud Firestore Standard

---

## 1. Benefícios do Google for Nonprofits

O Fundo Centenário, constituído como associação ou fundação privada sem fins lucrativos, apresenta características compatíveis com os critérios de elegibilidade do Google for Nonprofits.

Embora universidades não sejam elegíveis diretamente, o Google admite braços filantrópicos vinculados a instituições educacionais.

A aprovação depende da verificação documental pela Goodstack.

**Referência:** [Google for Nonprofits — Critérios de elegibilidade no Brasil](https://support.google.com/nonprofits/answer/3215869?co=GENIE.CountryCode%3DBR&hl=pt-BR)

### 1.1. Concessões disponíveis

| Benefício | Concessão | Aplicação no Fundo | Referência oficial |
|---|---|---|---|
| Google Workspace for Nonprofits | Gratuito, para até 2.000 usuários | E-mails institucionais e organização interna | [Workspace](https://support.google.com/nonprofits/answer/2858465?hl=pt-BR) |
| Armazenamento Workspace | 100 TB compartilhados | Documentação, relatórios e arquivos institucionais | [Planos Workspace](https://www.google.com/nonprofits/offerings/workspace/?hl=pt-br) |
| Google Ad Grants | Até US$ 10.000/mês em anúncios de pesquisa | Divulgação e captação de doadores | [Ad Grants](https://support.google.com/nonprofits/answer/1332166?hl=pt-br) |
| Google Maps Platform | US$ 250/mês em créditos, com solicitação de créditos adicionais | Mapas de projetos e iniciativas apoiadas | [Créditos Maps](https://support.google.com/nonprofits/answer/3367237?hl=pt-br) |
| YouTube Nonprofit Program | Recursos de divulgação e suporte específico | Comunicação e divulgação institucional | [YouTube Nonprofits](https://www.google.com/intl/pt-BR/nonprofits/offerings/youtube-nonprofit-program/) |
| Workspace Business Standard | Desconto de 75% | Colaboração e gravação de reuniões | [Preços Workspace](https://www.google.com/nonprofits/workspace/compare/?hl=pt-br) |
| Workspace Business Plus | Desconto de 72% | Segurança, retenção e auditoria | [Preços Workspace](https://www.google.com/nonprofits/workspace/compare/?hl=pt-br) |

Os benefícios dependem da elegibilidade, da disponibilidade regional e da ativação individual dos programas.

Os créditos do Google Maps não podem ser utilizados para custear Cloud Run, Firestore ou Firebase Hosting.

### 1.2. Google Workspace existente

O Fundo Centenário já utiliza Google Workspace com o domínio `@fundocentenario.com.br`.

Após a aprovação no Google for Nonprofits, será possível solicitar a conversão da assinatura existente para uma edição nonprofit compatível, respeitando as condições do contrato atual.

A migração não exige necessariamente a substituição dos endereços de e-mail ou do domínio institucional.

**Impacto financeiro:** redução ou eliminação das mensalidades do Workspace.

### 1.3. Google Ad Grants

O benefício de até US$ 10.000/mês pode ser utilizado para ampliar a visibilidade das iniciativas do Fundo Centenário, atrair potenciais doadores e divulgar projetos financiados.

O orçamento é disponibilizado para publicidade de pesquisa, sujeito às regras de qualidade, segmentação e conversão do programa.

Não representa uma concessão em dinheiro e não pode pagar infraestrutura Cloud.

**Impacto indireto:** o sucesso das campanhas pode aumentar o tráfego e os custos variáveis de hospedagem.

### 1.4. Google Cloud e créditos promocionais

Não foi identificada uma concessão pública geral de créditos recorrentes de Cloud Run ou Firestore especificamente para organizações nonprofit.

O Google Cloud oferece:

- Free Tier recorrente de determinados serviços.
- Créditos promocionais de US$ 300 por 90 dias para novos clientes elegíveis.
- Possibilidade de créditos adicionais por programas específicos, sem garantia de aprovação.

**Referência:** [Google Cloud Free Program](https://cloud.google.com/free/docs/free-cloud-features)

Este relatório considera apenas os benefícios gratuitos recorrentes, sem deduzir créditos temporários.

---

## 2. Arquitetura proposta

### 2.1. Região de implantação

A configuração recomendada é:

| Componente | Localização | Justificativa |
|---|---|---|
| Frontend — Firebase Hosting | CDN global | Distribuição eficiente de arquivos estáticos |
| Backend — Cloud Run | `southamerica-east1` | Processamento regional próximo aos usuários |
| Banco — Firestore Standard | `southamerica-east1` | Persistência regional e comunicação de baixa latência com o backend |
| Artifact Registry | `southamerica-east1` | Armazenamento regional das imagens de containers |
| Domínio | fundocentenario.com.br | Domínio institucional existente |

A hospedagem estática permanece global, enquanto backend e persistência são implantados em São Paulo.

O Firebase Hosting suporta o encaminhamento de rotas para Cloud Run na região `southamerica-east1`.

A comunicação entre o Cloud Run e o Firestore na mesma região evita custos de transferência entre regiões, além de favorecer uma menor latência interna.

**Referências:**

- [Firebase Hosting + Cloud Run](https://firebase.google.com/docs/hosting/cloud-run)
- [Cloud Run — Regiões](https://docs.cloud.google.com/run/docs/locations)
- [Firestore — Regiões](https://firebase.google.com/docs/firestore/locations)
- [Cloud Run — Boas práticas de rede](https://docs.cloud.google.com/run/docs/configuring/networking-best-practices)

### 2.2. Tráfego histórico utilizado

O levantamento considera os acessos ao website do Fundo Centenário entre **janeiro de 2021 e outubro de 2026**, com outubro ainda em andamento.

A média histórica foi de **339 visitantes mensais**, arredondada para **350 visitantes** como base operacional.

Observa-se uma tendência de aumento expressivo de acessos no final do ano. Em dezembro de 2025, foram registrados **1.196 visitantes**.

Este volume será utilizado como cenário pessimista histórico.

| Indicador | Médio | Pessimista |
|---|---:|---:|
| Visitantes/mês | 350 | 1.196 |
| Páginas por visitante | 5 | 15 |
| Transferência por página | 1,5 MB | 4 MB |
| Visualizações de páginas | 1.750 | 17.940 |
| Transferência estática | 2,63 GB | 71,76 GB |
| Usuários que utilizam a API | 25 | ~85 |
| Requisições por usuário ativo | 10 | 100 |
| Requisições de API | 250 | ~8.543 |
| Leituras Firestore | 1.000 | ~85.429 |
| Gravações Firestore | 250 | ~8.543 |

O fator proporcional utilizado é:

**1.196 ÷ 350 = 3,417**

As métricas pessimistas de utilização foram construídas com esse crescimento e hipóteses conservadoras de aumento de navegação e operações por usuário.

### 2.3. Armazenamento

O armazenamento não pode ser projetado exclusivamente pelo número de visitantes, pois registros podem permanecer no banco durante vários anos.

Para o planejamento:

| Cenário | Armazenamento considerado |
|---|---:|
| Médio inicial | 50 MB |
| Pico com registros pequenos | ~171 MB |
| Estresse conservador de armazenamento | ~1,71 GB |

O último cenário extrapola proporcionalmente a hipótese anterior de 500 MB de armazenamento elevado para 350 visitantes.

Ele representa uma simulação conservadora, e não uma medição histórica ou previsão garantida.

---

## 3. Como São Paulo altera os custos

### 3.1. Firebase Hosting

O Firebase Hosting utiliza CDN global, e sua tabela de preços não varia conforme a região escolhida para o backend.

A documentação técnica informa:

| Recurso | Franquia / tarifa |
|---|---|
| Armazenamento | 10 GB gratuitos |
| Armazenamento excedente | US$ 0,026/GB |
| Transferência de dados | 10 GB/mês gratuitos |
| Transferência excedente | US$ 0,15/GB |
| SSL e domínio personalizado | Incluídos |

A página resumida de preços também apresenta a transferência gratuita como 360 MB/dia. Para a estimativa mensal com faturamento Blaze, utiliza-se a regra de 10 GB/mês descrita na documentação técnica de Hosting.

**Referência:** [Firebase Hosting — Cotas e preços](https://firebase.google.com/docs/hosting/usage-quotas-pricing?hl=pt-br)

**Cenário médio**

350 × 5 × 1,5 MB = 2,625 GB/mês.

Transferência abaixo da franquia gratuita.

**Custo: US$ 0,00.**

**Cenário pessimista**

1.196 × 15 × 4 MB = 71,76 GB/mês.

Transferência excedente: 61,76 GB.

61,76 × US$ 0,15 = **US$ 9,26/mês**.

Portanto, a mudança de região do backend não modifica diretamente a estimativa de custo do frontend estático.

### 3.2. Cloud Run — São Paulo

O Cloud Run apresenta preços diferentes conforme a região.

A franquia gratuita do modelo de cobrança por requisição é aplicada como um desconto financeiro baseado nos preços de `us-central1`.

Valores publicados para essa referência:

| Recurso | Referência mensal gratuita |
|---|---:|
| CPU | Equivalente a 180.000 vCPU-segundos |
| Memória | Equivalente a 360.000 GiB-segundos |
| Requisições | 2 milhões |

Em São Paulo, a tarifa regional determina a quantidade efetiva de processamento coberta pelo desconto.

**Premissas de execução:**

- Backend Python/FastAPI.
- 1 vCPU.
- 512 MiB de memória.
- 400 ms de execução por requisição.
- Zero instâncias mínimas.
- Faturamento baseado em requisições.
- Sem processamento contínuo em background.

**Cenário médio**

250 requisições × 0,4 segundo = 100 vCPU-segundos.

Consumo aproximado de memória: 50 GiB-segundos.

**Cenário pessimista**

8.543 requisições × 0,4 segundo = 3.417 vCPU-segundos.

Consumo aproximado de memória: 1.709 GiB-segundos.

Esses cálculos não incluem inicialização de containers nem outros tempos auxiliares faturáveis. Ainda assim, existe ampla margem dentro do desconto gratuito, mesmo considerando a diferença regional.

**Custo de processamento esperado: US$ 0,00/mês.**

Isso é uma projeção, não uma garantia de faturamento zero.

O Cloud Run poderá apresentar custos de transferência de dados de saída para a Internet, inclusive com tráfego destinado a usuários brasileiros.

A transferência entre Cloud Run e Firestore na mesma região não gera a mesma cobrança de transferência inter-regional.

**Referência:** [Cloud Run Pricing](https://cloud.google.com/run/pricing)

### 3.3. Firestore Standard — São Paulo

O Firestore possui preços regionais para armazenamento e operações.

As franquias gratuitas publicadas para um banco elegível são:

| Recurso | Franquia |
|---|---:|
| Armazenamento | 1 GiB |
| Leituras | 50.000/dia |
| Gravações | 20.000/dia |
| Exclusões | 20.000/dia |
| Transferência de saída | 10 GiB/mês |

Essas franquias permanecem aplicáveis ao banco elegível implantado em São Paulo.

**Cenário médio**

1.000 leituras e 250 gravações por mês, com 50 MB armazenados.

Custo estimado: **US$ 0,00**.

**Cenário pessimista operacional**

85.429 leituras e 8.543 gravações mensais.

Distribuídas por 31 dias, representam aproximadamente:

- 2.756 leituras/dia.
- 276 gravações/dia.

Ambas permanecem muito abaixo das cotas gratuitas.

**Cenário conservador de armazenamento**

Com 1,71 GB armazenados, haveria aproximadamente 0,6–0,7 GiB acima da franquia, dependendo da unidade utilizada e do armazenamento efetivamente faturado.

O valor pago dependerá da tarifa de armazenamento de `southamerica-east1`, do uso médio diário, dos índices e dos metadados.

Para o orçamento preliminar, será adotada uma **provisão de US$ 0,15–0,50/mês**, que não representa uma cotação oficial da tarifa regional. O preço definitivo deverá ser confirmado na calculadora do Google Cloud antes do deploy.

**Referência:** [Firestore Pricing — selecionar São Paulo](https://cloud.google.com/firestore/pricing)

### 3.4. Transferência de rede

Ao centralizar o backend e o banco em `southamerica-east1`, evitamos transferências inter-regionais entre esses componentes.

Entretanto, continuam existindo fluxos que podem ser faturados:

| Comunicação | Tratamento |
|---|---|
| Firebase Hosting → navegador | Cobrança de transferência do Hosting |
| Cloud Run → Firestore na mesma região | Sem tarifa de transferência inter-regional |
| Cloud Run → usuários externos | Sujeito a preços de saída de rede |
| Firestore → outras regiões | Pode gerar cobranças adicionais |
| Artifact Registry → Cloud Run | Depende da localização e regras aplicáveis |

Como o projeto utiliza uma API de baixa volumetria, o tráfego externo previsto será pequeno.

Para ilustrar, supondo 50 KB de resposta por requisição no cenário pessimista:

8.543 × 50 KB ≈ 427 MB/mês.

A cobrança efetiva dependerá da origem, do destino e de como as respostas forem entregues pelo Hosting e Cloud Run.

Não será assumida uma franquia gratuita norte-americana para tráfego originado em São Paulo.

---

## 4. Consolidação financeira

### 4.1. Estimativa técnica mensal

| Serviço | Médio | Pessimista |
|---|---:|---:|
| Firebase Hosting | US$ 0,00 | US$ 9,26 |
| Cloud Run — CPU/RAM/requisições | ~US$ 0,00 | ~US$ 0,00 |
| Firestore — operações | US$ 0,00 | US$ 0,00 |
| Firestore — armazenamento | US$ 0,00 | Provisão de US$ 0,15–0,50 |
| Transferência de API | Residual | Pequena, variável |
| Artifact Registry | US$ 0,00 dentro da franquia | ~US$ 0,10, se houver excedente |
| Logging e Monitoring básicos | US$ 0,00 dentro das franquias | US$ 0,00 dentro das franquias |
| **Estimativa agregada** | **Próxima de US$ 0,00** | **Aproximadamente US$ 9,50–10,50** |

O intervalo pessimista inclui provisões de baixa magnitude para tarifas regionais e rede que precisam ser confirmadas no faturamento real.

Não é um teto máximo e não inclui tributos brasileiros, custos externos nem despesas de manutenção do domínio.

### 4.2. Comparação entre `us-central1` e `southamerica-east1`

| Critério | Iowa | São Paulo |
|---|---|---|
| Processamento regional | EUA | Brasil |
| Preço unitário de Cloud Run | Referência Tier 1 | Tarifa regional própria |
| Preço Firestore | Tarifa regional dos EUA | Tarifa regional brasileira |
| Franquia Firestore elegível | Disponível | Disponível |
| Benefícios nonprofit | Independentes da região | Independentes da região |
| Firebase Hosting | Global | Global |
| Latência para a maioria dos usuários brasileiros | Potencialmente maior | Potencialmente menor |
| Banco regional no Brasil | Não | Sim |
| Transferência Cloud Run ↔ Firestore na mesma região | Sem transferência inter-regional | Sem transferência inter-regional |

**Conclusão da comparação:** São Paulo é a escolha recomendada para esta aplicação. O diferencial regional de preços tem impacto reduzido diante do baixíssimo consumo de processamento e operações de banco de dados.

A decisão também evita posicionar o banco de dados em uma região distante da API.

---

## 5. Segurança, localização dos dados e governança

A implantação do Firestore em `southamerica-east1` permite utilizar armazenamento regional no Brasil, mas isso não significa que todos os dados e metadados do sistema permanecerão exclusivamente no território nacional.

O Firebase Hosting opera com uma CDN global, e produtos de observabilidade, autenticação ou integrações externas podem possuir regras próprias de localização.

Para o Fundo Centenário, recomenda-se:

1. Implantar Cloud Run e Firestore na mesma região.
2. Escolher a região definitiva do Firestore antes de criar o banco.
3. Adotar contas de serviço com permissões mínimas.
4. Evitar armazenar dados pessoais desnecessários em logs.
5. Definir controles de acesso, retenção, backup e recuperação.
6. Avaliar as exigências de LGPD aplicáveis aos formulários e dados de doadores.

A localização do Firestore não pode ser simplesmente alterada em um banco existente; uma mudança posterior exigiria um processo de migração.

A replicação entre zonas dentro da região não equivale a recuperação contra a indisponibilidade completa da região. Backups e estratégias de recuperação devem ser definidos de acordo com a criticidade dos dados.

---

## 6. Riscos de aumento de custo

Os principais fatores de risco são:

| Risco | Consequência |
|---|---|
| Instâncias mínimas no Cloud Run acima de zero | Cobranças mesmo em períodos sem tráfego |
| Cloud SQL ou servidores permanentes | Introdução de custos fixos |
| Load Balancer dedicado | Despesa adicional recorrente |
| Transferência entre diferentes regiões | Tarifas desnecessárias de rede |
| Arquivos de página muito grandes | Maior custo de Firebase Hosting |
| Bots e tráfego automatizado | Consumo não relacionado a visitantes humanos |
| Backups, PITR e retenção avançada | Cobranças adicionais |
| Crescimento com Google Ad Grants | Maior número de visitantes e transferência |

Um ponto importante é que a operação em Firebase Blaze exige uma conta de faturamento ativa. As franquias gratuitas continuam existindo, mas o consumo excedente é cobrado.

Alertas de orçamento não interrompem automaticamente a prestação dos serviços nem funcionam como limites rígidos de gastos.

---

## 7. Recomendações de deploy

A configuração operacional recomendada é:

| Parâmetro | Configuração inicial |
|---|---|
| Cloud Run region | `southamerica-east1` |
| Cloud Run CPU | 1 vCPU |
| Cloud Run memory | 512 MiB |
| Minimum instances | 0 |
| Maximum instances | 2 inicialmente |
| Billing | Request-based |
| Firestore | Standard, banco elegível à franquia gratuita |
| Firestore region | `southamerica-east1` |
| Artifact Registry | `southamerica-east1` |
| Firebase Hosting | CDN global, domínio institucional |
| Budget alert | 50%, 80% e 100% do orçamento |
| Ambiente de produção | Projeto Google Cloud dedicado |

O máximo inicial de duas instâncias deve ser validado por testes e pelos requisitos de disponibilidade do projeto. Limitar a escala protege parcialmente o processamento contra picos inesperados, mas pode aumentar erros ou latência durante eventos de acesso intenso.

Recomenda-se usar Firebase Hosting para o frontend estático e configurar o encaminhamento explícito das rotas de API para a região de São Paulo.

Caso o frontend dependa de SSR, esse modelo deve ser revisado, pois as estimativas pressupõem hospedagem predominantemente estática.

---

## 8. Recomendação financeira anual

| Categoria | Valor |
|---|---:|
| Custo mensal esperado | Próximo de US$ 0 |
| Custo em mês de pico histórico conservador | ~US$ 9,50–10,50 |
| Reserva mensal sugerida | US$ 15,00 |
| **Reserva anual sugerida** | **US$ 180,00** |

A reserva foi ampliada de US$ 120 para US$ 180 anuais, considerando a necessidade de absorver diferenças regionais, transferência adicional e pequenos serviços auxiliares.

Essa reserva não representa uma projeção de que todos os meses terão custo de US$ 15. A expectativa continua sendo de consumo baixo na maior parte do ano.

---

## 9. Conclusão

A utilização da região `southamerica-east1` — São Paulo — é tecnicamente recomendada para o Fundo Centenário da UFRGS.

A região brasileira permite posicionar o processamento e a persistência próximos ao público esperado, reduzindo a necessidade de comunicação entre regiões e facilitando a definição de políticas de localização de dados.

Embora Cloud Run e Firestore possuam preços regionais diferentes dos valores de referência dos Estados Unidos, o volume projetado permanece suficientemente baixo para que o impacto financeiro seja pequeno.

Com base nos dados históricos de janeiro de 2021 a outubro de 2026:

- **Média histórica:** 339 visitantes mensais.
- **Média operacional:** 350 visitantes mensais.
- **Pico histórico:** 1.196 visitantes em dezembro de 2025.
- **Custo mensal esperado:** próximo de zero.
- **Custo em cenário pessimista conservador:** aproximadamente US$ 9,50–10,50.
- **Reserva anual sugerida:** US$ 180.

Os benefícios do Google for Nonprofits permanecem independentes da região escolhida para os serviços de infraestrutura.

A maior oportunidade econômica do programa continua sendo o Google Workspace gratuito e o Google Ad Grants, enquanto a hospedagem do software pode ser mantida economicamente utilizando as franquias gratuitas gerais da Google Cloud.

### Referências técnicas oficiais

- [Google Cloud — Calculadora de preços](https://cloud.google.com/products/calculator)
- [Cloud Run — Preços regionais](https://cloud.google.com/run/pricing)
- [Firestore Standard — Preços por região](https://cloud.google.com/firestore/pricing)
- [Firebase Hosting — Cotas e preços](https://firebase.google.com/docs/hosting/usage-quotas-pricing)
- [Firebase Hosting — Integração com Cloud Run](https://firebase.google.com/docs/hosting/cloud-run)
- [Cloud Run — Regiões disponíveis](https://docs.cloud.google.com/run/docs/locations)
- [Firestore — Localização de bancos de dados](https://firebase.google.com/docs/firestore/locations)
- [Google for Nonprofits](https://www.google.com/intl/pt-BR/nonprofits/)