| # | Tipo | Pergunta | Esperado | Fontes recuperadas | Fonte certa? | Sem RAG | Com RAG |
|---|------|----------|----------|--------------------|--------------|---------|---------|
| 1 | Fato direto da base | Com quanta antecedência posso cancelar uma carona sem penalidade? | Passageiro: até 2 horas antes da saída (motorista: até 4 horas) | regras_cancelamento.md, regras_cancelamento.md, faq.md, regras_cancelamento.md | Sim (1º lugar) | Parcial (acertou 2 h por coincidência) | Correta |
| 2 | Fato específico (nomes de locais) | Onde ficam os pontos de encontro dentro do campus? | Portaria Principal, Praça do RU, Biblioteca Universitária e Centro de Convivência | pontos_de_encontro.md, pontos_de_encontro.md, pontos_de_encontro.md, faq.md | Sim (1º lugar) | Alucinação (inventou locais) | Correta |
| 3 | Junta dois documentos | O que acontece se eu cancelar em cima da hora várias vezes? | Cada cancelamento gera 1 advertência; 3 em 30 dias = 7 dias sem reservar; 2ª suspensão em 90 dias = 30 dias | avaliacoes_e_penalidades.md, regras_cancelamento.md, regras_cancelamento.md, regras_cancelamento.md | Sim (1º lugar) | Parcial (vaga, sem regras) | Correta |
| 4 | Palavras diferentes das do texto | Se eu desistir da viagem uma hora antes, dá problema? | Sim: menos de 2 horas antes gera 1 advertência (o cancelamento é aceito) | regras_cancelamento.md, regras_cancelamento.md, regras_cancelamento.md, faq.md | Sim (1º lugar) | Parcial (não cita a advertência) | Correta |
| 5 | Fora da base | Posso levar meu cachorro na carona? | Não está na base: deve dizer que não sabe | seguranca.md, seguranca.md, faq.md, pontos_de_encontro.md | n/a (fora da base) | Alucinação (inventou uma regra) | Correta (admitiu não saber) |

## Respostas completas

### P1. Com quanta antecedência posso cancelar uma carona sem penalidade?

- **Esperado:** Passageiro: até 2 horas antes da saída (motorista: até 4 horas)
- **Sem RAG:** No UniRide, você pode cancelar uma carona sem nenhuma penalidade até 2 horas antes do horário agendado. Cancelamentos de última hora podem afetar sua reputação na comunidade da UFLA. Em caso de imprevistos maiores, recomendamos avisar o motorista ou passageiro pelo chat o mais rápido possível.
- **Com RAG:** O passageiro pode cancelar sem penalidade até 2 horas antes do horário de saída. Já o motorista pode cancelar a carona sem penalidade até 4 horas antes.

### P2. Onde ficam os pontos de encontro dentro do campus?

- **Esperado:** Portaria Principal, Praça do RU, Biblioteca Universitária e Centro de Convivência
- **Sem RAG:** Os principais pontos de encontro do UniRide na UFLA ficam em locais estratégicos, como a praça de alimentação do campus histórico, o Pavilhão de Aulas (AE) e em frente ao Doutorado. Você também pode combinar um local específico diretamente com o motorista pelo chat do aplicativo. Boa viagem!
- **Com RAG:** Os 4 pontos oficiais de encontro dentro do câmpus da UFLA são: a Portaria Principal (em frente à guarita), a Praça do Restaurante Universitário (RU), a Biblioteca Universitária e o Centro de Convivência. O embarque dentro do câmpus só pode ser feito nesses locais.

### P3. O que acontece se eu cancelar em cima da hora várias vezes?

- **Esperado:** Cada cancelamento gera 1 advertência; 3 em 30 dias = 7 dias sem reservar; 2ª suspensão em 90 dias = 30 dias
- **Sem RAG:** No UniRide, cancelamentos de última hora prejudicam a comunidade e podem resultar na suspensão temporária da sua conta. Para manter uma boa reputação na UFLA, cancele apenas em caso de extrema necessidade e com a maior antecedência possível. Se precisar de Ajuda com alguma viagem específica, é só me chamar!
- **Com RAG:** Cancelamentos fora do prazo geram advertências que valem por 30 dias. Acumular 3 advertências nesse período resulta na suspensão de novas reservas e ofertas por 7 dias. A reincidência pode levar a suspensões mais longas de 30 dias ou até mesmo à análise para desligamento da plataforma.

### P4. Se eu desistir da viagem uma hora antes, dá problema?

- **Esperado:** Sim: menos de 2 horas antes gera 1 advertência (o cancelamento é aceito)
- **Sem RAG:** Desistir uma hora antes prejudica bastante o motorista e o colega que contavam com a carona. Como isso gera transtornos de última hora, pode afetar sua reputação na nossa comunidade. Tente avisar o motorista o quanto antes pelo chat do app se houver imprevistos.
- **Com RAG:** Sim, cancelar uma solicitação confirmada com menos de 2 horas de antecedência gera 1 advertência no seu perfil. No entanto, o cancelamento não gerará penalidade se for justificado por emergência médica, acidente ou cancelamento de aula ou prova comunicado pela universidade. Para isso, você deve enviar a justificativa pelo formulário "Contestar penalidade" em até 5 dias úteis, junto com um comprovante.

### P5. Posso levar meu cachorro na carona?

- **Esperado:** Não está na base: deve dizer que não sabe
- **Sem RAG:** No UniRide, a permissão para levar animais de estimação depende exclusivamente do motorista da carona. Recomendamos que você envie uma mensagem ao condutor antes de confirmar a viagem para checar a disponibilidade e garantir que o pet seja bem-vindo. Boa viagem com seu peludo!
- **Com RAG:** Não sei, pois essa informação não consta no contexto fornecido pela plataforma.
