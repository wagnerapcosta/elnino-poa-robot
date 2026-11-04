# Fontes e contratos de integração — v1.5 — 04/11/2026

Conclusão: as três fontes oficiais solicitadas agora fornecem dados estruturados ao robô. Isso é checagem cruzada de previsões, não demonstração de acurácia do Open-Meteo nem validação estatística do limiar. Não há série de chuva observada integrada nesta versão. Escopo exclusivamente pessoal confirmado pelo usuário; não extrapolar para uso empresarial.

## Produtos efetivamente integrados

| Produto | Rota pública | Uso e validação |
|---|---|---|
| CPTEC/INPE Multimodelo, ponto1276 | https://s1.cptec.inpe.br/grafico/Modelos/Multimodel/pag_web/horario/1276.json | `datasets[0]`, `lat/lon`, `data.date` UTC, `fcst` horário, `prec` em mm/h. Rodada única, sequência contínua, localidade esperada, valores finitos/não negativos, cobertura da janela, idade≤36h. Não soma `sprec` cumulativo. |
| INMET previsão Porto Alegre | https://apiprevmet3.inmet.gov.br/previsao/4314902 | Data de validade hoje/amanhã, entidadePortoAlegre/RS, resumo por turno. Emissão não informada; não inventar freshness meteorológica a partir da hora de coleta. Não há total de12h neste produto. |
| INMET avisos ativos | https://apiprevmet3.inmet.gov.br/avisos/ativos | `hoje`/`futuro`, código4314902 exato no campo `geocodes`, `encerrado=false`, validade `inicio/fim` sobreposta às próximas12h. Deduplicação porID. Horários sem fuso interpretados como Brasília, com premissa explícita. Registros inválidos degradam consulta para parcial. Escopo municipal, não geolocalização do aeroporto por polígono. |
| POA Clima / Prefeitura | https://api.helpertecnologia.com.br/defesa-civil/bff/climate/previsions/poadc | `last_updated_forecast` com fuso, idade≤48h, `show_forecast=true`, `prevision_date`, `rain_quantity` numérico em mm. Requer hoje, rejeita datas duplicadas e valores inválidos. Compara com os mesmos dias civis do Open-Meteo; não converte dia em12h. |

O portal municipal https://prefeitura.poa.br/poaclima/ incorpora https://clima.helpertecnologia.com.br/poadc . O backend Helper é fornecedor do painel oficial; não é uma quarta autoridade nem comprova independência do modelo usado. Descrição municipal: https://prefeitura.poa.br/defesa-civil/poaclima .

## Semântica e checagem do limiar

O portal CPTEC mostra a variável `prec` como precipitação em mm/h, com pontos separados por1h e origem em UTC. Não foi encontrada definição inequívoca de qual borda do intervalo recebe o timestamp. Por isso, a integração não escolhe silenciosamente uma convenção: calcula12passos horários com alinhamento pelo início e pelo fim. A faixa apresentada é sensibilidade metodológica de1h, não intervalo de confiança ou ensemble.

- Duas hipóteses≥20mm: sinal CPTEC acima do limiar, indicativo.
- Duas hipóteses<20mm: sinal abaixo, indicativo.
- Hipóteses em lados diferentes do limiar: inconclusivo.

A comparação exige a mesma janela de referência do Open-Meteo, mas os pontos espaciais diferem: CPTEC1276 fica em(-30,0331001;-51,2299995), cerca de7,2km de SBPA(-29,9939;-51,1711). Chuva convectiva pode variar nessa distância. Rodadas e insumos podem ser diferentes ou compartilhados. Não calcular média, votação, probabilidade ou confiança estatística a partir dessa concordância.

O alerta primário é preservado para Open-Meteo≥20mm/12h. CPTEC abaixo não cancela alerta. CPTEC acima nas duas hipóteses com Open-Meteo abaixo ou indisponível gera ATENÇÃO complementar para conferência, sem declarar que o alerta principal foi confirmado. Aviso INMET ou POA diário≥20mm não ativa sozinho o gatilho quantitativo de12h.

## Evidência da origem das rotas

Arquivos públicos dos próprios portais inspecionados em04/11/2026:

- CPTEC https://www.cptec.inpe.br/build/assets/api-D0n94VxA.js constrói a rota Multimodelo1276; https://www.cptec.inpe.br/build/assets/data-processor-BLiy2rv_.js usa `prec`; https://www.cptec.inpe.br/build/assets/charts-config-DsUnGG1V.js identifica mm/h; https://www.cptec.inpe.br/build/assets/echarts-helpers-DPSX-Zfv.js usa Date.UTC e passo3600000ms. Metadados da rodada são lidos do JSON, sem imitar a seleção de data do navegador.
- MapasINMET https://mapas.inmet.gov.br/assets/js/services/Apis.js?7 aponta o backend de previsão; https://mapas.inmet.gov.br/assets/js/Alertas.js?7 usa `/avisos/ativos`. A previsão JSON municipal também foi consultada diretamente e validada por entidade/UF/data. A extração de observações de estações no frontend usa reCAPTCHA; não foi contornada nem integrada.
- PainelPOA https://clima.helpertecnologia.com.br/assets/index-CbJEoQkR.js constrói `/bff/climate/previsions/<slug>` e apresenta `rain_quantity` com unidade mm.

São contratos observados do frontend, não promessa de API estável ou SLA. Não houve autenticação, contorno de CAPTCHA, acesso a conteúdo restrito ou provisionamento de credenciais. Limites de36/48h e tolerância espacial são decisões internas de qualidade, não requisitos normativos.

## Fontes preservadas e pendências

- Open-Meteo: https://open-meteo.com/en/docs — `precipitation` é soma da hora precedente. FreeAPI não comercial conforme https://open-meteo.com/en/terms ; uso pessoal informado. Nenhum modelo foi demonstrado como o mais preciso emSBPA.
- NOAA/AWC: https://aviationweather.gov/data/api/ — METAR/TAF complementares; validade temporal das mensagens ainda não auditada. REDEMET continua pendente para referência aeronáutica brasileira.
- CPC: https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml e IRI: https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/ — contextoENOS, sem inferência automática de chuva local de12h por palavras-chave.
- MetSul: https://metsul.com/ — consulta editorial privada complementar; não extraída para cálculo quantitativo.
- DefesaCivilRS: https://defesacivil.rs.gov.br/inicial — referência; acesso direto anterior falhou apesar de abrir na web. Não tratada como integração concluída.

Ainda necessários para validação de desempenho: arquivo de previsões emitidas, série observada com localização/qualidade/continuidade e cálculo retrospectivo de vieses, erros e acertos/falsos alertas por horizonte. O sistema atual guarda snapshots normalizados nos artifacts, mas não executa essa análise nem produz aceite operacional. Entrega no aparelho permanece distinta da aceitação HTTP do ntfy.


## Defesa Civil Municipal — extração v1.5

Fonte oficial: https://prefeitura.poa.br/poaclima/ e descrição municipal https://prefeitura.poa.br/defesa-civil/poaclima . A Prefeitura identifica a Defesa Civil Municipal como gestora, descreve as17regiões e os níveis atenção/amarelo, risco alto/laranja, muito alto/vermelho e extremo/roxo.

Rota pública observada no frontend do painel: https://api.helpertecnologia.com.br/defesa-civil/bff/climate/alert/public/poadc/grouped-by-region . Contrato: lista de regiões com `order`, `name` e `alert` opcional. O frontend trata ausência/null de `alert` como sem alerta publicado naquela região. Objetos presentes expõem `criticality`, `start_date`, `end_date`, `alert_types[].name` e `alert_description`; `id` é opcional para rastreio. Descrição HTML é convertida em texto, sem executar conteúdo.

Critérios: números de região1–17 únicos, nomes presentes, vigência coerente, fim posterior à consulta. Alertas futuros publicados são preservados e identificados como futuros; expirados ou `criticality=noRisk` não são notificados. Nível desconhecido ou registro inválido é rejeitado e consulta fica parcial, assim como falta de alguma região. Resposta vazia não é prova de ausência de alertas. Timestamp sem fuso usa BRT com premissa explícita; emissão não informada não é inferida da coleta. Objetos idênticos são agrupados entre regiões. A ordem de prioridade do aviso consolidado preserva o nível mais grave.

Verificação real em04/11/2026:HTTP200 e17regiões sem objeto `alert` associado. Isso confirma extração do estado consultado, não ausência geral de risco meteorológico. Nenhum objeto positivo vigente estava disponível para validação real; casos positivos, níveis, vigência, agrupamento, fuso, HTML e limites de mensagem foram verificados com fixtures baseadas no frontend, sem enviar alertas fictícios. A classificação oficial regional é distinta da matriz do robô e do gatilho quantitativo20mm/12h.
