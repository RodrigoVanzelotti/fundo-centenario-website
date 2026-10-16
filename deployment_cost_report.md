# Relatório de benefícios e custos de infraestrutura
**Fundo Centenário da UFRGS**

**Autor:** Rodrigo Vanzelotti
**Referência:** Outubro de 2026  
**Domínio:** fundocentenario.com.br  
**Escopo:** Google for Nonprofits, Google Workspace, Firebase Hosting, Cloud Run e Firestore.

---

## 1. Benefícios do Google for Nonprofits

O Fundo Centenário, constituído como associação ou fundação privada sem fins lucrativos e vinculado à UFRGS, apresenta características compatíveis com os critérios de elegibilidade do Google for Nonprofits.

Embora universidades públicas não sejam elegíveis diretamente, o Google permite a participação de braços filantrópicos de instituições educacionais. A aprovação depende de verificação documental pela Goodstack.

**Referência:** [Google for Nonprofits — Critérios de elegibilidade no Brasil](https://support.google.com/nonprofits/answer/3215869?co=GENIE.CountryCode%3DBR&hl=pt-BR)

### 1.1. Concessões disponíveis

| Benefício | Concessão | Aplicação no Fundo | Referência oficial |
|---|---|---|---|
| Google Workspace for Nonprofits | Gratuito, para até 2.000 usuários elegíveis | E-mails institucionais e organização interna | [Google Workspace](https://support.google.com/nonprofits/answer/2858465?hl=pt-BR) |
| Armazenamento Google Workspace | 100 TB compartilhados entre os usuários | Documentos, relatórios e arquivos institucionais | [Recursos do Workspace](https://www.google.com/nonprofits/offerings/workspace/?hl=pt-br) |
| Google Ad Grants | Até US$ 10.000/mês em anúncios de pesquisa | Divulgação e captação de doadores | [Google Ad Grants](https://www.google.com/intl/pt-BR/nonprofits/offerings/google-ad-grants/) |
| Google Maps Platform | US$ 250/mês em créditos, com possibilidade de solicitar créditos adicionais | Mapas de projetos e iniciativas | [Créditos Google Maps](https://support.google.com/nonprofits/answer/3367237?hl=pt-br) |
| YouTube Nonprofit Program | Recursos de divulgação, links externos e suporte específico | Divulgação institucional | [Programa YouTube](https://www.google.com/nonprofits/offerings/youtube-nonprofit-program/) |
| Workspace Business Standard | 75% de desconto sobre o preço padrão | Gravação de reuniões e colaboração avançada | [Planos e preços](https://www.google.com/nonprofits/workspace/compare/?hl=pt-br) |
| Workspace Business Plus | 72% de desconto sobre o preço padrão | Retenção, auditoria e segurança | [Planos e preços](https://www.google.com/nonprofits/workspace/compare/?hl=pt-br) |

Os benefícios dependem da aprovação da organização e da ativação individual dos produtos. Os créditos do Google Maps Platform não podem ser utilizados para custear serviços gerais de Google Cloud.

O YouTube Giving, especificamente, possui restrições de elegibilidade para organizações registradas nos Estados Unidos.

### 1.2. Google Workspace já existente

O Fundo Centenário já utiliza Google Workspace com o domínio `@fundocentenario.com.br`.

Não é necessário criar uma nova estrutura de e-mails para aderir ao programa. A organização pode solicitar a ativação do Google Workspace for Nonprofits na estrutura existente, verificando a assinatura e os procedimentos exigidos pelo Google.

Caso utilize uma versão paga, poderá solicitar a conversão para a edição gratuita ou aplicar os descontos destinados às organizações elegíveis.

**Impacto financeiro:** redução ou eliminação das mensalidades do Workspace, conforme o plano atualmente contratado.

### 1.3. Google Ad Grants

O programa disponibiliza até US$ 10.000 mensais em anúncios de texto na Pesquisa Google.

Para o Fundo Centenário, isso pode ampliar a aquisição de visitantes interessados em apoiar a universidade, financiar projetos, participar de iniciativas filantrópicas e conhecer os resultados do fundo patrimonial.

O benefício não representa dinheiro depositado na conta da organização e não pode ser utilizado para pagar hospedagem ou outros serviços da Google Cloud.

**Impacto financeiro:** potencial economia em publicidade digital, condicionada às regras do programa.

### 1.4. Créditos para Google Cloud

Não foi identificado um programa público geral que garanta créditos recorrentes de Cloud Run, Firebase Hosting ou Firestore exclusivamente pela condição de organização nonprofit.

O Google disponibiliza um crédito promocional de US$ 300 por 90 dias para novos clientes elegíveis, além do Free Tier recorrente para serviços selecionados.

**Referência:** [Google Cloud Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features?hl=pt-br)

Para o planejamento de longo prazo, este relatório desconsidera créditos promocionais temporários.

---

## 2. Infraestrutura de software proposta

A arquitetura considera os seguintes componentes:

| Componente | Tecnologia | Função |
|---|---|---|
| Website | Firebase Hosting | Hospedagem estática, CDN e HTTPS |
| API | Cloud Run + Python/FastAPI | Processamento de requisições |
| Banco de dados | Cloud Firestore Standard | Armazenamento de registros |
| Domínio | fundocentenario.com.br | Identidade e acesso público |
| Observabilidade | Cloud Logging / Monitoring | Logs, métricas e alertas |

A arquitetura utilizará serviços gerenciados e execução sob demanda, evitando manter servidores permanentemente ligados.

### 2.1. Tráfego estimado

**Base histórica de referência**

Foi considerada a análise de acessos do website do Fundo Centenário no período de **janeiro de 2021 a outubro de 2026**, sendo outubro de 2026 um mês ainda em andamento.

A média histórica geral identificada é de **339 visitantes por mês**, arredondada para **350 visitantes mensais** para facilitar a modelagem e a apresentação das estimativas.

A análise também identificou uma tendência de aumento expressivo de acessos no final do ano, especialmente em dezembro.

Em dezembro de 2025, foram registrados **1.196 visitantes**, representando aproximadamente 3,42 vezes o volume de referência arredondado.

Dessa forma, o cenário pessimista de capacidade e custos utilizará o pico histórico de 1.196 visitantes mensais, enquanto o cenário médio utilizará 350.

**Premissas de utilização**

| Indicador | Cenário médio | Cenário pessimista |
|---|---:|---:|
| Visitantes mensais | 350 | 1.196 |
| Páginas por visitante | 5 | 15 |
| Transferência por página | 1,5 MB | 4 MB |
| Visualizações de páginas | 1.750 | 17.940 |
| Transferência estática mensal | 2,63 GB | 71,76 GB |
| Usuários que realizam chamadas à API | 25 | ~85 |
| Requisições por usuário ativo | 10 | 100 |
| Requisições de API | 250 | ~8.543 |
| Leituras Firestore | 1.000 | ~85.429 |
| Gravações Firestore | 250 | ~8.543 |
| Armazenamento Firestore | 50 MB | ~1,71 GB* |

\*O armazenamento pessimista é uma extrapolação matemática dos 500 MB anteriormente previstos para o cenário de maior utilização. O armazenamento real depende da retenção dos dados, não apenas da quantidade de visitantes no mês.

As estimativas operacionais pessimistas foram escaladas proporcionalmente ao crescimento dos visitantes, mantendo as hipóteses conservadoras de maior navegação e quantidade de chamadas por usuário.

**Fator de crescimento aplicado:** 1.196 ÷ 350 = 3,417.

Exemplos:

- Usuários de API: 25 × 3,417 ≈ 85.
- Chamadas de API: 2.500 × 3,417 ≈ 8.543.
- Leituras Firestore: 25.000 × 3,417 ≈ 85.429.
- Gravações Firestore: 2.500 × 3,417 ≈ 8.543.

O cenário pessimista representa um pico de tráfego fundamentado no histórico do próprio site, e não um limite máximo absoluto de utilização.

---

## 3. Benefícios gratuitos da Google Cloud aplicados à infraestrutura

As franquias abaixo não dependem de aprovação no Google for Nonprofits.

| Serviço | Franquia gratuita | Utilização pessimista |
|---|---|---|
| Firebase Hosting | 10 GB de armazenamento | Dentro do limite presumido |
| Firebase Hosting | 10 GB/mês de transferência, conforme documentação técnica | 71,76 GB/mês |
| Cloud Run | 2 milhões de requisições/mês | ~8.543 |
| Cloud Run | 180.000 vCPU-segundos/mês* | ~3.417 |
| Firestore | 50.000 leituras/dia | ~2.756/dia |
| Firestore | 20.000 gravações/dia | ~276/dia |
| Firestore | 1 GiB de armazenamento | ~1,63–1,67 GiB |
| SSL e domínio personalizado | Incluídos no Firebase Hosting | Sem cobrança específica |

\*As cotas de CPU e memória do Cloud Run são referenciadas à região `us-central1`. O consumo real depende da configuração e da região.

Referências oficiais:

- [Firebase Hosting — Cotas e preços](https://firebase.google.com/docs/hosting/usage-quotas-pricing?hl=pt)
- [Cloud Run Pricing](https://cloud.google.com/run/pricing)
- [Firestore Pricing](https://cloud.google.com/firestore/pricing)

### 3.1. Firebase Hosting

**Cenário médio**

350 visitantes × 5 páginas × 1,5 MB = **2,63 GB/mês**.

A transferência permanece dentro da franquia gratuita.

Custo estimado: **US$ 0,00/mês**.

**Cenário pessimista — dezembro de 2025 como referência**

1.196 visitantes × 15 páginas × 4 MB = **71,76 GB/mês**.

Considerando 10 GB/mês de transferência gratuita:

- Transferência total: 71,76 GB.
- Transferência excedente: 61,76 GB.
- Tarifa de referência: US$ 0,15/GB.

Custo calculado: **US$ 9,26/mês**.

A tabela resumida de preços do Firebase também apresenta uma referência de 360 MB/dia. Em uma distribuição diária desfavorável, a cobrança calculada por essa referência poderia chegar a aproximadamente US$ 10,71.

Para o orçamento, adota-se US$ 9,26 como cálculo mensal de referência, destacando a necessidade de conferir a franquia efetivamente aplicada à conta.

### 3.2. Cloud Run

O backend continuará processando um volume relativamente pequeno de requisições, mesmo no pico histórico.

Para aproximadamente 8.543 chamadas mensais, assumindo 400 ms de processamento por chamada e 1 vCPU, o consumo estimado será de aproximadamente 3.417 vCPU-segundos.

Esse consumo permanece consideravelmente abaixo da franquia de referência de 180.000 vCPU-segundos mensais.

Com zero instâncias mínimas, faturamento baseado em requisições e ausência de processos permanentes:

**Custo médio: US$ 0,00/mês.**

**Custo pessimista estimado: US$ 0,00/mês.**

### 3.3. Firestore

Mesmo no cenário de maior utilização, as operações de leitura e gravação permanecem muito abaixo das cotas diárias.

Entretanto, a extrapolação de armazenamento para aproximadamente 1,71 GB ultrapassa a franquia gratuita de 1 GiB.

Utilizando uma tarifa ilustrativa de US$ 0,15/GiB-mês para armazenamento excedente, na região de referência `us-central1`, e considerando que todo o volume permaneça armazenado durante o mês:

**Custo pessimista estimado de armazenamento: aproximadamente US$ 0,10/mês.**

As operações de leitura e gravação continuariam sem custo dentro das franquias gratuitas.

---

## 4. Consolidação dos custos mensais

| Serviço | Cenário médio | Cenário pessimista |
|---|---:|---:|
| Firebase Hosting | US$ 0,00 | US$ 9,26 |
| Cloud Run | US$ 0,00 | US$ 0,00 |
| Firestore — operações | US$ 0,00 | US$ 0,00 |
| Firestore — armazenamento | US$ 0,00 | ~US$ 0,10 |
| SSL e CDN | Incluídos | Incluídos |
| Logging e Monitoring básicos | US$ 0,00 | US$ 0,00 |
| Artifact Registry | US$ 0,00 | ~US$ 0,10 |
| **Total mensal estimado** | **US$ 0,00** | **US$ 9,46** |

O total pessimista é uma projeção baseada no pico histórico e nas hipóteses conservadoras de uso. Não corresponde a um teto garantido de gastos.

Não estão incluídos custos de desenvolvimento, renovação de domínio, gateways de pagamento, serviços externos ou tributos.

---

## 5. Riscos e despesas adicionais

A arquitetura pode gerar custos superiores aos projetados principalmente se forem utilizados:

- Cloud Run com instâncias mínimas permanentemente ativas.
- Cloud SQL ou outros bancos com recursos provisionados.
- Load Balancers dedicados.
- Backups avançados e retenção prolongada de dados.
- Serviços externos de e-mail ou integração.
- Processamento de arquivos, imagens ou grandes volumes de dados.
- Recursos pagos não previstos na arquitetura.

Além disso, o Google Ad Grants poderá aumentar significativamente o tráfego do website, alterando o padrão histórico utilizado neste relatório.

Recomenda-se monitorar especialmente a transferência de dados do Firebase Hosting, por ser o principal componente com potencial de cobrança variável no cenário proposto.

---

## 6. Recomendação financeira anual

| Categoria | Projeção |
|---|---:|
| Infraestrutura mensal esperada | US$ 0,00 |
| Infraestrutura em mês de pico histórico | ~US$ 9,46 |
| Reserva mensal recomendada | US$ 10,00 |
| **Reserva anual recomendada** | **US$ 120,00** |

A reserva proposta é prudencial e não representa cobrança mínima ou limite máximo de faturamento.

Caso o padrão histórico continue, a maioria dos meses deverá gerar custos muito baixos ou nulos, com possibilidade de aumento no período de maior tráfego.

É recomendável configurar alertas de orçamento no Google Cloud e revisar os custos mensalmente, especialmente antes e durante dezembro. Alertas de faturamento não interrompem automaticamente o consumo.

---

## 7. Conclusão

A arquitetura Firebase Hosting + Cloud Run + Firestore permanece economicamente adequada ao perfil de tráfego do Fundo Centenário.

Com base nos dados históricos analisados entre janeiro de 2021 e outubro de 2026, a estimativa considera:

- Média histórica: 339 visitantes mensais.
- Média operacional arredondada: 350 visitantes mensais.
- Pico histórico de referência: 1.196 visitantes em dezembro de 2025.

**O custo mensal esperado da infraestrutura é próximo de zero**, enquanto um mês com volume semelhante ao pico histórico e com hipóteses conservadoras de navegação pode representar aproximadamente **US$ 9,46** em infraestrutura.

A adesão ao Google for Nonprofits traz benefícios adicionais, principalmente a possibilidade de reduzir despesas do Google Workspace, centralizar a colaboração institucional e ampliar as iniciativas de captação com Google Ad Grants.

Assim, a principal vantagem do Google for Nonprofits não está diretamente no custeio da infraestrutura proposta, mas na redução de despesas operacionais e no fortalecimento da comunicação e da captação de recursos do Fundo Centenário.

### Fontes oficiais

- [Google for Nonprofits — Elegibilidade no Brasil](https://support.google.com/nonprofits/answer/3215869?co=GENIE.CountryCode%3DBR&hl=pt-BR)
- [Google Workspace for Nonprofits](https://www.google.com/nonprofits/offerings/workspace/?hl=pt-br)
- [Google Ad Grants](https://www.google.com/intl/pt-BR/nonprofits/offerings/google-ad-grants/)
- [Google Cloud Free Program](https://docs.cloud.google.com/free/docs/free-cloud-features?hl=pt-br)
- [Firebase Pricing](https://firebase.google.com/pricing)
- [Firebase Hosting — Quotas e preços](https://firebase.google.com/docs/hosting/usage-quotas-pricing)
- [Cloud Run Pricing](https://cloud.google.com/run/pricing)
- [Firestore Pricing](https://cloud.google.com/firestore/pricing)
- [Artifact Registry Pricing](https://cloud.google.com/artifact-registry/pricing)