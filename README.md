# Radar El Niño POA — v1.5

Robô pessoal de apoio ao monitoramento de SBPA, com relatórios diário/semanal e alerta ntfy. Não é o HTML local Radar Chuva SBPA v1.4. Uso exclusivamente pessoal confirmado em 04/11/2026; reavaliar licenças antes de eventual uso empresarial.

## Alerta principal e checagem oficial

- **Open-Meteo ≥20 mm em 12h:** exatamente 20 mm dispara. São somados 12 intervalos horários, respeitando timestamps de fim da hora precedente. A janela começa no início da hora em curso, cuja previsão integral é incluída. Horários BRT explícitos; não há interpolação de minutos nem procura de qualquer máximo nos sete dias.
- **CPTEC/INPE:** extração real da série JSON Multimodelo de Porto Alegre (ponto1276, cerca de7,2km de SBPA). O portal apresenta `prec` em mm/h. Como a borda temporal do intervalo não foi confirmada, o robô integra passos de1h nas duas hipóteses (timestamp como início ou fim) e mostra ambos os totais. Concordância/divergência é **indicativa**, não validação de acurácia. Se as hipóteses cruzam o limiar, a comparação é inconclusiva.
- **INMET:** extração JSON da previsão por turnos e dos avisos. Avisos filtrados pelo código municipal4314902, encerramento e sobreposição com as próximas12h; vigência `inicio/fim` interpretada em BRT. São avisos para o município, não prova de20mm/12h em SBPA. Previsão qualitativa não é convertida em mm. Emissão do produto não informada permanece explícita.
- **POA Clima/Prefeitura:** extração JSON da previsão diária do painel municipal, com emissão e totais em mm. Comparação com os mesmos dias civis do Open-Meteo, mostrando diferenças. Total diário não é dividido para inferir12h.

O alerta principal nunca é cancelado, reduzido ou sujeito a votação entre fontes. Se CPTEC indicar ≥20mm nas duas hipóteses enquanto Open-Meteo estiver abaixo/indisponível, é enviada **ATENÇÃO de checagem CPTEC**, separada do alerta principal. Falta de dados oficiais não equivale a zero ou concordância. Os modelos podem compartilhar insumos; não se presume independência estatística.

## Execução

A rotina horária, no minuto17 UTC, consulta as cinco rotas oficiais em paralelo além do Open-Meteo. A quinta rota fornece os avisos/alertas regionais da Defesa Civil POA. Também executa após alterações relevantes na branch principal. Pode haver atraso no GitHub Actions. Alertas/atenções ativos podem repetir em horas consecutivas e coincidir com notificações diárias/semanais.

`RUN_MODE=rain_alert` executa a rotina curta; `daily` e `weekly` geram relatórios completos. O segredo `NTFY_TOPIC` existente é usado sem expor seu valor. Sua ausência com alerta/atenção ativo causa falha explícita. Confirmação HTTP não comprova recebimento no aparelho.

Cada execução salva relatório e snapshot JSON de resultados normalizados (valores, origem, coleta, emissão, status, limites e comparação) em `reports/<modo>/`. O Actions guarda esses arquivos como artifact. O histórico diário/semanal também registra situação da comparação e valores CPTEC. Snapshots não constituem banco permanente nem validação retrospectiva contra chuva observada.

Python3.11+:

```text
pip install -r requirements.txt
python -m unittest discover -s tests -v
python robot.py
```

Executar o robô com tópico configurado pode enviar notificações. Os testes interceptam os envios. Chaves/API pagas não foram provisionadas; nenhuma contratação.

## Fontes e limites

Oficiais: [CPTEC/INPE](https://www.cptec.inpe.br/), [Mapas INMET](https://mapas.inmet.gov.br/), [POA Clima](https://prefeitura.poa.br/poaclima/). [MetSul](https://metsul.com/) permanece consulta editorial complementar. CPC/NOAA e IRI oferecem contexto ENOS; homepages não geram cores por palavras-chave. AviationWeather continua complementar; REDEMET ainda não integrada.

As rotas públicas usadas pelos portais podem mudar sem aviso. Rodada CPTEC acima de36h e emissão POA Clima acima de48h são rejeitadas; são limites internos, não requisitos regulatórios. Falhas não silenciam o alerta principal disponível. A comparação é entre previsões, sem ingestão de séries observadas nem validação estatística de desempenho. Não é radar de precipitação observada, prognóstico hidrológico do Guaíba, certificação de readiness ou aprovação operacional.

Origem dos dados, contratos e critérios em [FONTES.md](FONTES.md). Dados primários Open-Meteo sob [CC BY4.0](https://creativecommons.org/licenses/by/4.0/), com atribuição [Open-Meteo](https://open-meteo.com/). Atribuição da série oficial: **CPTEC/INPE**.

## Teste de notificação

`notification_test.py` simula exatamente20mm em12h, verifica o gatilho inclusivo e envia uma única mensagem com título e corpo identificados como TESTE/DADOS SIMULADOS. Não consulta meteorologia nem grava ocorrência no histórico. O fluxo `notification-test.yml` pode ser executado manualmente no Actions; também roda quando seu próprio arquivo é alterado na main, para verificar a configuração do teste. Não possui agendamento periódico. Aceitação pelo ntfy não comprova recebimento no celular.


## Avisos no celular — v1.5

**Falha da previsão principal:** problemas de transporte, formato, valores ou cobertura da previsão Open-Meteo geram uma notificação própria, de prioridade alta: `Radar POA - FALHA na previsao principal`. O corpo destaca **DADOS INDISPONÍVEIS NÃO SIGNIFICAM AUSÊNCIA DE RISCO** e orienta consultar as fontes oficiais. Se apenas os dados diários falharem, o texto distingue essa falha da avaliação de12h disponível. No modo horário, falha de12h continua marcando o job como falha após tentar enviar os avisos; a falha não vira “sem risco”.

**Defesa Civil POA:** a rota pública do painel municipal é consultada em cada execução. O robô envia uma notificação separada com nível oficial, regiões, vigência, tipos de evento e trecho da descrição publicada. Aviso de atenção usa prioridade normal; risco alto, alta; risco muito alto/extremo, urgente. A classificação extrema é preservada no texto, sem convertê-la em nível da matriz interna do robô. Alertas futuros publicados podem ser enviados com início futuro explícito; expirados/estado `noRisk` não geram aviso.

A consulta cobre17regiões. Alertas idênticos em várias regiões são agrupados em um conteúdo; mensagens longas trazem trecho e link para a íntegra. O aviso consolidado prioriza os níveis mais graves. Cobertura incompleta ou registro inválido é consulta parcial; falha de fonte não equivale a nenhuma região alertada. Datas municipais sem fuso são interpretadas em BRT com a premissa explícita. O alerta por região não prova impacto em SBPA nem20mm/12h.

Não há deduplicação persistente entre execuções: falhas e alertas municipais ainda ativos podem repetir a cada consulta, inclusive nos fluxos diário/semanal. As notificações são independentes: erro em um envio não impede tentar o outro. Resultados de aceitação do serviço ficam em `notificacoes_operacionais_*.json` nos artifacts, sem expor o tópico privado. A entrega física ao aparelho permanece distinta da aceitação HTTP.
