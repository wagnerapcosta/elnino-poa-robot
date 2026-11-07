# Radar El Niño POA — v1.6

Robô pessoal de apoio ao monitoramento de SBPA, com relatórios diário/semanal e alerta ntfy. Não é o HTML local Radar Chuva SBPA v1.4. Uso exclusivamente pessoal confirmado em 04/11/2026; reavaliar licenças antes de eventual uso empresarial.

## Alerta principal e checagem oficial

- **Open-Meteo ≥20 mm em 12h:** exatamente 20 mm dispara. São somados 12 intervalos horários, respeitando timestamps de fim da hora precedente. A janela começa no início da hora em curso, cuja previsão integral é incluída. Horários BRT explícitos; não há interpolação de minutos nem procura de qualquer máximo nos sete dias.
- **CPTEC/INPE:** extração real da série JSON Multimodelo de Porto Alegre (ponto1276, cerca de7,2km de SBPA). O portal apresenta `prec` em mm/h. Como a borda temporal do intervalo não foi confirmada, o robô integra passos de1h nas duas hipóteses (timestamp como início ou fim) e mostra ambos os totais. Concordância/divergência é **indicativa**, não validação de acurácia. Se as hipóteses cruzam o limiar, a comparação é inconclusiva.
- **INMET:** extração JSON da previsão por turnos e dos avisos. Avisos filtrados pelo código municipal4314902, encerramento e sobreposição com as próximas12h; vigência `inicio/fim` interpretada em BRT. São avisos para o município, não prova de20mm/12h em SBPA. Previsão qualitativa não é convertida em mm. Emissão do produto não informada permanece explícita.
- **POA Clima/Prefeitura:** extração JSON da previsão diária do painel municipal, com emissão e totais em mm. Comparação com os mesmos dias civis do Open-Meteo, mostrando diferenças. Total diário não é dividido para inferir12h.

O alerta principal nunca é cancelado, reduzido ou sujeito a votação entre fontes. Se CPTEC indicar ≥20mm nas duas hipóteses enquanto Open-Meteo estiver abaixo/indisponível, é enviada **ATENÇÃO de checagem CPTEC**, separada do alerta principal. Falta de dados oficiais não equivale a zero ou concordância. Os modelos podem compartilhar insumos; não se presume independência estatística.

## Execução

### Modelo Essencial — v1.8

Apresentação escolhida pelo usuário em06/11/2026. O resumo usa título`SBPA | Radar El Nino POA`, risco, chuva12h, máximos por dia/3dias civis, rajada, motivo curto e ação. ENOS, confiabilidade, METAR/TAF e listas de falha de fontes permanecem nos relatórios completos, fora da notificação curta. Os máximos antigos não são janelas móveis: rótulos`Chuva dia (máx.)` e`Chuva 3 dias (máx.)` evitam essa ambiguidade.

Chuva e vento são arredondados para inteiros somente na apresentação, com metade para cima. Comparações, limiar inclusivo>=20mm12h e memória numérica usam valores originais. Para evitar falso atingimento visual,19,99mm aparece`<20mm`;20,00mm aparece`20mm` e continua disparando. Valores indisponíveis não viram zero.

Defesa Civil: títulos`SBPA | Defesa Civil | Aviso Amarelo`,`Alerta Laranja`,`Alerta Vermelho`ou`Alerta Roxo (risco extremo)`, segundo os quatro níveis do painel oficial. Vermelho corresponde a risco muito alto; extremo não é rebaixado para vermelho. Condições aparecem primeiro, seguidas da descrição resumida, validade, regiões e fonte. Números de chuva/vento exibidos no resumo são arredondados; texto e valores integrais da fonte permanecem no snapshot/relatório. Geografia SBPA/4km, seleção conservadora de borda, fonte de teste suprimida e paginação por aceitação permanecem ativos.

Cada aviso tem ação nativa`Abrir fonte`. Textos longos continuam divididos em páginas e só as regiões incluídas em páginas aceitas avançam a memória. Falha e recuperação mantêm a frase essencial de que dados indisponíveis/coleta normalizada não significam ausência de risco. O tema/fonte visual são definidos pelo aplicativo ntfy.

O cenário manual`essencial` executa`notification_essential_test.py`: três exemplos identificados no título e corpo comoTESTE — DADOS SIMULADOS (resumo,DefesaCivilvermelho,chuvaexatamente20mm12h), espaçados10segundos. Usa dados fictícios, não coleta meteorologia nem altera memória real. Aceitação HTTP permanece distinta de recebimento físico.

### Foco SBPA — v1.7

O ponto de referência passa a ser o centro informado no desenho do usuário:29°59′40,61″S /51°10′00,10″W. É referência de acompanhamento, não ARP certificado ou limite operacional. O Open-Meteo é solicitado nesse ponto; a resolução de sua grade não é um círculo de4km.

Os avisos municipais enviados ao celular ficam restritos às regiões cujo polígono oficial intercepta o entorno de4km, incluindo100m de margem conservadora na borda. O critério usa a borda do polígono, não seu centroide. Regiões selecionadas na geometria consultada em06/11/2026:Humaitá/Navegantes,Noroeste,Norte,Eixo Baltazar,Centro,Leste eIlhas (esta última na margem). Um aviso regional sobreposto não comprova ocorrência na pista. Nomes/identificadores não reconhecidos são conservados como abrangência a confirmar, com status parcial.

Testes explicitamente identificados no início da descrição municipal, como“TESTE DE AVISO PARA POACLIMA”, não são retransmitidos como risco real. Avisos de fora do foco e testes da fonte permanecem nos snapshots e relatórios com motivo de exclusão; a fonte completa não é descartada.

A rota pública de estações meteorológicas do POA Clima fornece até três estações dentro do raio, ordenadas por distância. Se nenhuma estiver dentro, é retida somente a mais próxima, explicitamente externa. Em06/11/2026:Sarandí/Nova Brasília3,322km;Vila Farrapos3,335km;Sarandí/Assis Brasil3,502km. São observações complementares: o período do acumulado e a idade efetiva das medições não estão documentados nessa rota. Não validam nem anulam o gatilho inclusivo≥20mm/12h do Open-Meteo. Falha nessa fonte opcional não impede a previsão principal.

O ponto CPTEC1276 fica aproximadamente7,4km da referência: continua na checagem e nos relatórios, mas não gera sozinho aviso local de atenção fora do foco. Notícias estaduais genéricas da Defesa Civil RS passam a consulta contextual; palavras-chave sem delimitação local/validade comprovada não elevam o risco de SBPA. O gatilho principal≥20mm/12h permanece independente.

Configuração e proveniência em`config/airport_focus.json`; geometria vinculada pelo [painel oficial POA Clima](https://prefeitura.poa.br/poaclima/), [arquivo de regiões](https://clima.helpertecnologia.com.br/portoalegre.json). Distâncias por projeção local, margem conservadora e snapshot datado; rever a configuração quando o mapa oficial ou ponto de referência mudar. A nova apresentação textual será escolhida separadamente entre as prévias.

A rotina horária tem disparos aos minutos 07, 27 e 47. Um disparo agendado só consulta as fontes se ainda não houver uma execução bem-sucedida da rotina de chuva iniciada naquela hora. Se a verificação do histórico falhar, a consulta segue com a deduplicação normal. O GitHub pode atrasar ou omitir disparos, inclusive os de reserva. Para verificar a cobertura real, conte o passo `Consultar previsao e avaliar alertas`, pois um fluxo que pulou esse passo não realizou nova consulta.

A rotina consulta seis rotas oficiais em paralelo além do Open-Meteo. A quinta fornece avisos/alertas regionais da Defesa Civil POA e a sexta as estações próximas como complemento opcional. A rotina também executa após alterações relevantes na branch principal e sob acionamento manual. As três rotinas compartilham a memória de notificações, que suprime um evento inalterado mesmo quando aparece em modos diferentes.

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

`notification_test.py` simula exatamente20mm em12h, verifica o gatilho inclusivo e envia uma única mensagem com título e corpo identificados como TESTE/DADOS SIMULADOS. Não consulta meteorologia nem grava ocorrência no histórico. O fluxo `notification-test.yml` é exclusivamente manual, sem disparo por alteração de arquivo nem agendamento periódico. O cenário padrão `offline` não envia mensagens; os demais cenários devem ser selecionados explicitamente. Aceitação pelo ntfy não comprova recebimento no celular.

### Entrega no Android

Nas configurações de inscrição do tópico ntfy, ative **Entrega instantânea** para usar o serviço de recebimento em primeiro plano. Sem essa opção, a versão Google Play em ntfy.sh usa Firebase e pode apresentar atrasos. O serviço em primeiro plano mantém uma notificação permanente e consome mais bateria. Consulte a [documentação oficial do ntfy](https://docs.ntfy.sh/subscribe/phone/#instant-delivery).

Configuração ativada e conferida no aparelho em05/11/2026. Após a ativação, foram observadas no telefone quatro mensagens de uma sequência rápida e os quatro itens do teste completo (dois níveis táticos e duas páginas municipais), identificados como TESTE/DADOS SIMULADOS. Isso não comprova a causa exata da entrega parcial anterior nem garante entrega sob toda condição de rede, suspensão ou bateria. Não registrar HTTP aceito como confirmação do aparelho.


## Avisos no celular — v1.5

**Falha da previsão principal:** problemas de transporte, formato, valores ou cobertura da previsão Open-Meteo geram uma notificação própria, de prioridade alta: `Radar POA - FALHA na previsao principal`. O corpo destaca **DADOS INDISPONÍVEIS NÃO SIGNIFICAM AUSÊNCIA DE RISCO** e orienta consultar as fontes oficiais. Se apenas os dados diários falharem, o texto distingue essa falha da avaliação de12h disponível. No modo horário, falha de12h continua marcando o job como falha após tentar enviar os avisos; a falha não vira “sem risco”.

**Defesa Civil POA:** a rota pública do painel municipal é consultada em cada execução. O robô envia uma notificação separada com nível oficial, regiões, vigência, tipos de evento e trecho da descrição publicada. Aviso de atenção usa prioridade normal; risco alto, alta; risco muito alto/extremo, urgente. A classificação extrema é preservada no texto, sem convertê-la em nível da matriz interna do robô. Alertas futuros publicados podem ser enviados com início futuro explícito; expirados/estado `noRisk` não geram aviso.

A consulta cobre17regiões. Alertas idênticos em várias regiões são agrupados em um conteúdo; mensagens longas são divididas em páginas, com trechos e link para a íntegra. Cada página respeita o limite de bytes UTF-8 e prioriza os níveis mais graves presentes nela. Somente as regiões incluídas em uma página aceita pelo serviço são registradas como notificadas. Páginas com falha ficam pendentes para a próxima consulta, sem repetir as já aceitas. Cobertura incompleta ou registro inválido é consulta parcial; falha de fonte não equivale a nenhuma região alertada. Datas municipais sem fuso são interpretadas em BRT com a premissa explícita. O alerta por região não prova impacto em SBPA nem20mm/12h.

Há memória persistente entre execuções e rotinas para evitar reenvios sem mudança relevante. Quando a previsão principal volta a passar nas verificações, é emitido um único aviso de coleta normalizada. As notificações são independentes: erro em um envio não impede tentar o outro. Resultados de aceitação do serviço ficam em `notificacoes_operacionais_*.json` nos artifacts, sem expor o tópico privado. A entrega física ao aparelho permanece distinta da aceitação HTTP.

A opção `notification_test.py --operational` envia dois cenários fictícios (falha principal e alerta municipal), ambos com TESTE/DADOS SIMULADOS no título/corpo, sem consulta meteorológica ou alteração do histórico. Sem a opção, o script preserva o teste anterior de20mm/12h. A identificação do teste municipal declara explicitamente que não foi emitido pela Defesa Civil e usa região fictícia.


## Memória de eventos e recuperação — v1.6

O arquivo `data/notification_state.json` guarda estados, assinaturas, referências numéricas do último envio aceito e horários. Não contém tópico ntfy, credenciais ou descrições integrais dos alertas. As descrições municipais são representadas por hash após normalizar espaços/maiúsculas. Os fluxos horário, diário e semanal usam o mesmo grupo de execução serial, fila `max`, checkout atualizado da main e persistência do estado mesmo quando a previsão falha. Commits só de dados não disparam nova consulta.

Regras de reenvio:

- **Falha da previsão principal:** um aviso no início do episódio. Mudança entre falha de transporte, da avaliação horária ou somente dos dados diários é atualização relevante. Mudar apenas a mensagem técnica do erro ou a hora da tentativa não repete. Ao recuperar todos os dados principais, envia uma vez `COLETA DA PREVISAO NORMALIZADA`, esclarecendo que isso não significa ausência de risco meteorológico. Uma nova falha após recuperação é novo episódio.
- **Chuva ≥20mm/12h e atenção CPTEC:** não repetem só porque a janela avançou ou a comparação complementar mudou. Reenvia quando o tipo do aviso muda entre principal/atenção CPTEC ou o volume muda em pelo menos5mm E25% relativamente ao último envio aceito. Fonte indisponível não encerra evento. Uma leitura principal válida abaixo do limiar rearma o alerta principal; novo atingimento é novo acionamento. Desde v1.7, atenção CPTEC só pode gerar notificação se o ponto estiver dentro do foco/margem; o ponto regional1276 permanece contexto de relatório. Ausência dessa fonte não encerra evento; exige leitura válida abaixo do limiar.
- **Defesa Civil POA:** acompanha cada região. Mudança de nível, vigência, tipo, região/nome ou descrição substantiva permite aviso novo, consolidando somente regiões alteradas. Troca apenas deID, consulta, maiúsculas ou espaços não repete. Remover/expirar uma região não repete os alertas inalterados das outras. Fonte parcial/indisponível não apaga estados ausentes. Uma consulta completa sem alerta encerra silenciosamente o evento correspondente; nova publicação pode notificar.
- **Resumo geral diário/semanal:** compara o nível tático final da mensagem, incluindo elevações por outras fontes ou confiabilidade da coleta, e os mesmos critérios de chuva (5mm E25%); rajadas exigem10km/h E20%. Não repete só porque mudou o modo diário/semanal. Verde inalterado não gera aviso. Mensagem de baixo nível causada somente pela chuva de12h é evitada quando esse alerta específico já foi aceito; gatilhos independentes e redução de um panorama laranja/vermelho continuam notificáveis. O histórico anterior fornece a referência inicial do resumo, evitando repetir o último aviso já enviado.

Os mínimos de5mm/25% e10km/h/20% são critérios internos iniciais de comunicação, não limites oficiais nem calibração meteorológica. Comparações são com o último envio aceito, para que mudanças pequenas acumuladas possam atingir o mínimo relevante. Rebaixamento de nível também é mudança.

Só a aceitação HTTP atualiza a referência de envio; falhas de entrega podem ser tentadas na próxima consulta. A recuperação também é tentada novamente se não for aceita. Os artifacts distinguem `sent`, `suppressed` e `failed`. Os testes explícitos no celular bypassam essa memória e não abrem falsos episódios de falha/recuperação.

Persistência local é atômica; o estado é publicado no repositório ao final do job mesmo em falha da previsão. Estado corrompido não é zerado silenciosamente: a execução falha para correção. Interrupção entre aceitação ntfy e persistência no GitHub pode ocasionar reenvio residual; não há transação de entrega única entre os serviços. Recebimento no aparelho continua distinto da aceitação HTTP.


O cenário manual `falha-repetida-recuperacao` seleciona `notification_test.py --dedup-recovery`: executa falha → mesma falha → recuperação com a máquina de estados real e arquivo temporário recarregado entre as três fases. São esperados exatamente dois envios: uma falha e uma normalização; a segunda falha é suprimida. Ambos são TESTE/DADOS SIMULADOS e não representam condição meteorológica real. A memória real de produção é conferida por hash antes/depois e não é alterada. O resultado fica no artifact `notification-test-*`. Não há nova tentativa automática de mensagem já aceita.

O cenário `pacote` executa `notification_patch_test.py`: dois níveis táticos e duas páginas municipais, incluindo recusa simulada sem HTTP de uma página e retomada somente das regiões pendentes. Recarrega estado temporário entre fases, verifica os17registros e bloqueia repetições. Os quatro envios são espaçados em10segundos como precaução de teste; esse intervalo não altera o envio de produção e não constitui garantia de entrega.
