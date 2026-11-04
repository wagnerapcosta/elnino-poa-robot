# Radar El Niño POA — revisão 1.3

Robô de apoio ao monitoramento de SBPA. Produz relatórios e notificações ntfy; este repositório não contém uma interface web. Não confundir com o HTML local Radar Chuva SBPA v1.4.

## Alerta de chuva

- Limiar solicitado: **20 mm ou mais** (`>=20`); exatamente 20 mm dispara.
- Soma 12 valores horários da previsão Open-Meteo no ponto de SBPA. Os horários da API indicam o fim da hora anterior.
- Janela de 12 horas alinhada ao início da hora em curso. Exemplo: execução às 18:17 usa 18:00–06:00 e inclui a previsão integral da hora 18:00–19:00. A resolução horária não permite isolar com precisão os 17 minutos transcorridos. Horários reais da janela constam do alerta. Não procura o máximo de qualquer janela nos sete dias.
- Dados ausentes, inválidos, fora de cobertura, unidade incorreta ou coordenadas incompatíveis geram indisponibilidade, nunca “sem gatilho”. A previsão é consultada novamente em cada execução; horário de coleta não comprova horário de inicialização do modelo.
- Relatórios diário/semanal passam a incluir o alerta e o histórico recebe total, estado e janela. Semáforo tático mínimo amarelo; a notificação específica horária tem prioridade alta, sem representar nível oficial de alerta meteorológico.
- Novo fluxo `rain-alert.yml`: a cada hora, minuto 17 UTC (mesma frequência em BRT). Executa apenas a previsão e só notifica quando o gatilho estiver ativo. Pode repetir em horas consecutivas; não há deduplicação persistente. Fluxos diário/semanal podem notificar o mesmo evento. GitHub Actions pode atrasar, falhar ou ter agendamentos desabilitados; não fornece garantia de tempo real.
- É necessário `NTFY_TOPIC` já utilizado pelos fluxos existentes. Nenhum segredo precisa ser colocado no código. Ausência do tópico em um alerta ativo faz o novo fluxo falhar explicitamente. A aceitação HTTP do ntfy não comprova recebimento no aparelho.

## Auditoria das fontes

Ver [FONTES.md](FONTES.md), verificação em 04/11/2026. A alteração não contrata serviços nem provisiona credenciais. Confirmar licença Open-Meteo adequada ao uso empresarial antes da ativação. Concluir integração oficial brasileira é pendência explícita.

## Execução e validação

Python 3.11+ e dependências em `requirements.txt`.

```text
pip install -r requirements.txt
python -m unittest discover -s tests -v
python robot.py
```

`RUN_MODE=rain_alert` seleciona a rotina curta; `daily` e `weekly` preservam os relatórios. Executar `robot.py` com tópico configurado pode enviar notificações. Os testes usam simulações e interceptam as notificações.

Dados: [Open-Meteo](https://open-meteo.com/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Modelo numérico em célula de grade não é medição por radar, chuva observada no aeroporto ou previsão hidrológica da bacia do Guaíba. O desempenho local ainda precisa de comparação retrospectiva com observações e meteorologista.
A rotina de chuva também executa após alterações de código/testes na branch principal, permitindo verificar a implantação. Confirmado uso exclusivamente pessoal pelo usuário em 04/11/2026; eventual uso empresarial exige reavaliação da licença.
