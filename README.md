# Radar El Niño POA — v1.6

Robô pessoal de apoio ao monitoramento de SBPA, com relatórios diário/semanal e alerta ntfy. Não é o HTML local Radar Chuva SBPA v1.4. Uso exclusivamente pessoal confirmado em 04/11/2026; reavaliar licenças antes de eventual uso empresarial.

## Alerta principal e checagem oficial

- **Open-Meteo ≥20 mm em 12h:** exatamente 20 mm dispara. São somados 12 intervalos horários, respeitando timestamps de fim da hora precedente. A janela começa no início da hora em curso, cuja previsão integral é incluída. Horários BRT explícitos; não há interpolação de minutos nem procura de qualquer máximo nos sete dias.
- **CPTEC/INPE:** extração real da série JSON Multimodelo de Porto Alegre (ponto1276, cerca de7,2km de SBPA). O portal apresenta `prec` em mm/h. Como a borda temporal do intervalo não foi confirmada, o robô integra passos de1h nas duas hipóteses (timestamp como início ou fim) e mostra ambos os totais. Concordância/divergência é **indicativa**, não validação de acurácia. Se as hipóteses cruzam o limiar, a comparação é inconclusiva.
- **INMET:** extração JSON da previsão por turnos e dos avisos. Avisos filtrados pelo código municipal4314902, encerramento e sobreposição com as próximas12h; vigência `inicio/fim` interpretada em BRT. São avisos para o município, não prova de20mm/12h em SBPA. Previsão qualitativa não é convertida em mm. Emissão do produto não informada permanece explícita.
- **POA Clima/Prefeitura:** extração JSON da previsão diária do painel municipal, com emissão e totais em mm. Comparação com os mesmos dias civis do Open-Meteo, mostrando diferenças. Total diário não é dividido para inferir12h.

O alerta principal nunca é cancelado, reduzido ou sujeito a votação entre fontes. Se CPTEC indicar ≥20mm nas duas hipóteses enquanto Open-Meteo estiver abaixo/indisponível, é enviada **ATENÇÃO de checagem CPTEC**, separada do alerta principal. Falta de dados oficiais não equivale a zero ou concordância. Os modelos podem compartilhar insumos; não se presume independência estatística.

## Execução

A rotina horária, no minuto17 UTC, consulta as cinco rotas oficiais em paralelo além do Open-Meteo. A quinta rota fornece os avisos/alertas regionais da Defesa Civil POA. Também executa após alterações relevantes na branch principal. Pode haver atraso no GitHub Actions. As três rotinas compartilham memória de notificações: um evento inalterado é suprimido mesmo quando aparece em modos diferentes.

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

Há memória persistente entre execuções e rotinas para evitar reenvios sem mudança relevante. Quando a previsão principal volta a passar nas verificações, é emitido um único aviso de coleta normalizada. As notificações são independentes: erro em um envio não impede tentar o outro. Resultados de aceitação do serviço ficam em `notificacoes_operacionais_*.json` nos artifacts, sem expor o tópico privado. A entrega física ao aparelho permanece distinta da aceitação HTTP.

O fluxo de teste está configurado para `notification_test.py --operational`: envia dois cenários fictícios (falha principal e alerta municipal), ambos com TESTE/DADOS SIMULADOS no título/corpo, sem consulta meteorológica ou alteração do histórico. Sem a opção, o script preserva o teste anterior de20mm/12h. A identificação do teste municipal declara explicitamente que não foi emitido pela Defesa Civil e usa região fictícia.


## Memória de eventos e recuperação — v1.6

O arquivo `data/notification_state.json` guarda estados, assinaturas, referências numéricas do último envio aceito e horários. Não contém tópico ntfy, credenciais ou descrições integrais dos alertas. As descrições municipais são representadas por hash após normalizar espaços/maiúsculas. Os fluxos horário, diário e semanal usam o mesmo grupo de execução serial, fila `max`, checkout atualizado da main e persistência do estado mesmo quando a previsão falha. Commits só de dados não disparam nova consulta.

Regras de reenvio:

- **Falha da previsão principal:** um aviso no início do episódio. Mudança entre falha de transporte, da avaliação horária ou somente dos dados diários é atualização relevante. Mudar apenas a mensagem técnica do erro ou a hora da tentativa não repete. Ao recuperar todos os dados principais, envia uma vez `COLETA DA PREVISAO NORMALIZADA`, esclarecendo que isso não significa ausência de risco meteorológico. Uma nova falha após recuperação é novo episódio.
- **Chuva ≥20mm/12h e atenção CPTEC:** não repetem só porque a janela avançou ou a comparação complementar mudou. Reenvia quando o tipo do aviso muda entre principal/atenção CPTEC ou o volume muda em pelo menos5mm E25% relativamente ao último envio aceito. Fonte indisponível não encerra evento. Uma leitura principal válida abaixo do limiar rearma o alerta principal; novo atingimento é novo acionamento. Para atenção CPTEC, ausência dessa fonte não encerra o evento; exige leitura válida abaixo do limiar.
- **Defesa Civil POA:** acompanha cada região. Mudança de nível, vigência, tipo, região/nome ou descrição substantiva permite aviso novo, consolidando somente regiões alteradas. Troca apenas deID, consulta, maiúsculas ou espaços não repete. Remover/expirar uma região não repete os alertas inalterados das outras. Fonte parcial/indisponível não apaga estados ausentes. Uma consulta completa sem alerta encerra silenciosamente o evento correspondente; nova publicação pode notificar.
- **Resumo geral diário/semanal:** mesmos critérios de nível e de chuva (5mm E25%); rajadas exigem10km/h E20%. Não repete só porque mudou o modo diário/semanal. Verde inalterado não gera aviso. Mensagem de baixo nível já coberta pelo alerta específico de12h é evitada; redução de um panorama laranja/vermelho continua sendo uma mudança relevante. O histórico anterior fornece a referência inicial do resumo, evitando repetir o último aviso já enviado.

Os mínimos de5mm/25% e10km/h/20% são critérios internos iniciais de comunicação, não limites oficiais nem calibração meteorológica. Comparações são com o último envio aceito, para que mudanças pequenas acumuladas possam atingir o mínimo relevante. Rebaixamento de nível também é mudança.

Só a aceitação HTTP atualiza a referência de envio; falhas de entrega podem ser tentadas na próxima consulta. A recuperação também é tentada novamente se não for aceita. Os artifacts distinguem `sent`, `suppressed` e `failed`. Os testes explícitos no celular bypassam essa memória e não abrem falsos episódios de falha/recuperação.

Persistência local é atômica; o estado é publicado no repositório ao final do job mesmo em falha da previsão. Estado corrompido não é zerado silenciosamente: a execução falha para correção. Interrupção entre aceitação ntfy e persistência no GitHub pode ocasionar reenvio residual; não há transação de entrega única entre os serviços. Recebimento no aparelho continua distinto da aceitação HTTP.
