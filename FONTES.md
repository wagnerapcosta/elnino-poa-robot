# Avaliação das fontes — 04/11/2026

Conclusão técnica: a seleção tem fontes relevantes, mas a integração v1.2 não era ideal para decisão tática. Não foi demonstrado que um único modelo seja o mais preciso em SBPA. Qualidade exige validação contra chuva observada e análise de erro, sobretudo para extremos.

| Fonte existente | Avaliação e providência |
|---|---|
| NOAA CPC ENSO Diagnostic Discussion | Fonte primária apropriada para contexto ENOS. Manter consulta ao boletim datado; menção a El Niño não determina chuva em POA nas próximas 12h. |
| IRI ENSO Forecast | Apropriada como contexto probabilístico complementar. Não é previsão local de curto prazo. |
| Open-Meteo forecast | API estruturada útil para cálculo horário e protótipo. `precipitation` é soma da hora precedente; `best_match` pode combinar modelos e não é medição. Mantida, sem alegar superioridade local. API gratuita restrita a uso não comercial; uso empresarial deve ter licença/plano adequado confirmado antes de ativar. Nenhuma contratação realizada. |
| AviationWeather METAR/TAF SBPA | API NOAA/AWC documentada, útil como complemento. METAR é observação e TAF não fornece o acumulado quantitativo necessário ao gatilho. Resposta HTTP com lista vazia não comprova dados disponíveis. v1.3 corrige avaliação de coleta vazia/parcial, mas ainda não valida idade/validade do METAR/TAF. |
| INMET página inicial | Instituição competente, mas homepage/notícias não são produto de alertas. Recomenda-se integrar avisos estruturados com vigência e polígono/município de POA; portal oficial de avisos identificado, integração ainda não feita. |
| INPE e CEMADEN páginas iniciais | Referências institucionais, insuficientes como dados táticos. Selecionar produtos específicos de previsão/monitoramento e, para inundação, bacias contribuintes, níveis e tendências. Não inferir inundação a partir da chuva pontual em SBPA. |
| Defesa Civil RS | URL anterior `/avisos-e-alertas` retornou 404 na consulta web. Corrigida para `/inicial`, que contém avisos e notícias de várias cidades. Página completa não confirma aplicabilidade a POA nem vigência individual. Consulta preservada somente como referência. |

## Alterações aplicadas nesta proposta

1. Chuva >=20 mm em janela de 12 horas no relatório, histórico e nova rotina horária; validação de cobertura, unidade, localidade e valores. Comparação decimal preserva o limite inclusivo de exatamente 20 mm sem erro de arredondamento binário.
2. Páginas HTML sem boletim validado deixam de gerar cores automáticas por palavras-chave. Contexto ENOS passa a “não classificado” para revisão dos boletins, evitando interpretação de negação, navegação ou notícias antigas. Isso reduz cobertura automatizada: avisos oficiais ainda precisam de conferência humana.
3. Coleta crítica inválida/vazia indica confiabilidade insuficiente; dados diários inválidos exibem N/D. O máximo de três dias passa a usar somente grupos completos. Totais de dias civis não são apresentados como janelas móveis. Estado “confiável” legado significa disponibilidade técnica da coleta, não acurácia ou conformidade meteorológica.

## Referências primárias consultadas

- Open-Meteo: https://open-meteo.com/en/docs — variável `precipitation`, soma da hora precedente; modelos/células e unidades.
- Termos: https://open-meteo.com/en/terms — Free API somente para uso não comercial; disponibilidade e acurácia não garantidas.
- NOAA/AWC: https://aviationweather.gov/data/api/ — METAR e TAF em JSON, cobertura mundial; acessibilidade da API não confirma validade de cada mensagem SBPA.
- CPC: https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml — discussão ENOS datada.
- IRI: https://iri.columbia.edu/our-expertise/climate/forecasts/enso/current/ — previsão ENOS mensal/probabilística.
- INMET: https://portal.inmet.gov.br/servicos/avisos-especiais e https://avisos.inmet.gov.br/ — produto adequado de avisos, sem integração concluída.
- Defesa Civil RS: https://defesacivil.rs.gov.br/inicial — avisos de várias localidades e notícias na mesma página.
- NAV Brasil: https://www.navbrasil.gov.br/atuacao/meteorologia-aeronautica/ — REDEMET como canal oficial brasileiro de divulgação de meteorologia aeronáutica.
- DECEA: https://ajuda.decea.mil.br/artigos/api-redemet-o-que-e — documentação da API identificada via busca oficial; abertura do artigo retornou 403. Integração não executada e nenhum acesso autenticado presumido.

## Critérios antes de uso operacional

Confirmar licença/API de produção, manter verificação REDEMET/INMET/Defesa Civil com vigência e geografia, validar resultados e recebimento no aparelho. Threshold de 20 mm é critério solicitado pelo usuário, não requisito regulatório ou nível oficial. O sistema não calcula risco hidrológico do Guaíba nem certifica readiness. A conversa compartilhada fornecida não expôs conteúdo na consulta e não foi usada como evidência de decisões anteriores.

## Verificação prática local

Em 04/11/2026 às 15:07 BRT, Open-Meteo retornou série/unidades válidas e cálculo de 6,1 mm na janela 15:00–03:00, sem gatilho. AviationWeather retornou um METAR e um TAF; a validade temporal dessas mensagens não foi auditada. CPC, IRI, INMET, INPE e CEMADEN responderam à coleta HTML. A Defesa Civil abriu na consulta web, mas a consulta direta pelo robô terminou com conexão encerrada pelo servidor: integração não confirmada. Consulta válida não comprova precisão da previsão. Doze testes automatizados passaram; notificações interceptadas, sem envio real. Entrega ao aparelho e execução no GitHub Actions permanecem pendentes.

Escopo de ativação confirmado pelo usuário em 04/11/2026: uso exclusivamente pessoal, sem aplicação empresarial. Nesse escopo, a restrição comercial da Free API não impede a ativação desta versão; reavaliar licença se o uso mudar. Nenhum gasto ou contratação autorizado.

## Inclusão solicitada — v1.3.1 — 04/11/2026

| Natureza | Fonte de consulta | Verificação e uso |
|---|---|---|
| Oficial | https://www.cptec.inpe.br/ | Portal CPTEC/INPE com previsão, nowcasting e clima. Confirmar produto, validade e localização; homepage não fornece por si só série validada de SBPA. |
| Oficial | https://mapas.inmet.gov.br/ | Aplicação com estações, radar, previsão e avisos em camadas dinâmicas; HTML acessível não comprova extração dessas camadas. |
| Oficial | https://prefeitura.poa.br/poaclima/ | Página municipal incorpora painel externo de clima.helpertecnologia.com.br. Consulta oficial municipal preservada; dados do painel não integrados nesta alteração. |
| Complementar | https://metsul.com/ | Fonte meteorológica privada. Consultar análises datadas e aplicabilidade regional; não tratar como alerta oficial. A própria previsão automática da homepage declara limite de uso em situação de risco meteorológico. |

Links consultados na web em 04/11/2026. Novas fontes participam da consulta HTML diária/semanal, com natureza e limitações nos relatórios. Não houve integração de APIs ou extração de medições/valores de mapas, iframes ou conteúdo restrito. Limiar inclusivo ≥20 mm/12h e rotina horária Open-Meteo preservados.
