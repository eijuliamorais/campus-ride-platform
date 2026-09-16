# UniRide

> **Este projeto é o trabalho prático da disciplina de Sistemas Distribuídos (GCC129). A ideia da carona universitária serve como pretexto realista para aplicar, na prática, conceitos como microsserviços independentes, bancos de dados separados por serviço e transações distribuídas (SAGA). O foco é a arquitetura distribuída em si.**

---
## Integrantes


- [Clarisse Lacerda Pimentel](https://github.com/Clarisse-Pimentel) 
- [Júlia Aparecida de Faria Morais](https://github.com/eijuliamorais)
- [Lucas Torquato de Melo](https://github.com/TorquatoLucas)
- [Luiz Francisco Sousa de Jesus](https://github.com/Frannchesco)
- [Maria Rita Ribeiro Resende](https://github.com/mariaritaresende) 

## 1. Identidade

* **Nome da Startup:** UniRide
* **Slogan:** Sua rota, sua turma, sua segurança.
* **Paleta de Cores Mínima:**
  * **Azul:** confiança, vínculo acadêmico e credibilidade.
  * **Branco:** clareza e acessibilidade da interface.
---
## 2. Problema e Motivação

Estudantes universitários brasileiros enfrentam uma combinação de fragilidade financeira e insegurança no deslocamento diário até o campus, dois fatores que ameaçam diretamente a permanência no Ensino Superior. O problema se apoia em quatro eixos, sustentados por referências científicas e institucionais:

1. *Fragilidade financeira do estudante e o peso do deslocamento.* Levantamento da Serasa em parceria com o Instituto Opinion Box (jan. 2026), com 936 universitários endividados, mostra que 66% já deixaram de comprar itens básicos — entre eles, explicitamente, transporte — para conseguir pagar a mensalidade, e que 48% chegaram a trancar o curso por não conseguir manter os pagamentos em dia (SERASA, 2026). Isso evidencia que qualquer custo recorrente e evitável, como o do deslocamento diário, pode ser o fator que empurra o estudante para a evasão.
2. *Peso do transporte no orçamento familiar.* A V Pesquisa Nacional de Perfil dos Graduandos das IFES (ANDIFES, 2019) mostra que mais de 70% dos estudantes de universidades federais têm renda familiar per capita de até 1,5 salário mínimo, e aponta o transporte como um dos principais gastos diretos de manutenção do estudante.
3. **Insegurança no trajeto como barreira à participação acadêmica, sobretudo para mulheres.** Estudo exploratório conduzido na UFRJ (SILVEIRA, 2019/2024) com 51 respondentes de um curso de graduação revela que quanto maior o número de baldeações no trajeto até o campus, maior a frequência de medidas de precaução de segurança adotadas pelos estudantes — e que essa exigência recai de forma desproporcional sobre as mulheres. O mesmo estudo mostra que 80,4% dos respondentes já deixaram de participar de alguma atividade acadêmica em razão do deslocamento necessário para chegar à universidade.
4. **Viabilidade e barreiras psicológicas da carona entre estudantes.** Pesquisa com estudantes da UFPE (SILVA; ANDRADE; MAIA, 2019), baseada em regressão logística sobre 465 respostas, identifica que os principais fatores que aumentam a adesão a um sistema de carona dinâmica são o acesso a um perfil do usuário antes da viagem (+163% de chance de adesão), a possibilidade de alternar entre motorista e passageiro (+148%) e a interação social (+123%); em contrapartida, viajar com desconhecidos é o maior fator de resistência (-70%), especialmente entre mulheres. Esse achado reforça que a **verificação de identidade e vínculo institucional** — e não apenas o algoritmo de rota — é o que destrava a confiança necessária para o uso da carona compartilhada.

## Referências

* *ANDIFES.* V Pesquisa Nacional de Perfil dos Graduandos das IFES. Associação Nacional dos Dirigentes das Instituições Federais de Ensino Superior, Brasília, 2019.
https://www.andifes.org.br/wp-content/uploads/2019/05/V-Pesquisa-Nacional-de-Perfil-Socioeconomico-e-Cultural-dos-as-Graduandos-as-das-IFES-2018.pdf

* *SERASA.* 66% dos universitários endividados já cortaram itens básicos para pagar mensalidade, revela Serasa. Pesquisa Serasa/Opinion Box, jan. 2026. Disponível em: <https://www.serasa.com.br/imprensa/universitarios-endividados-cortam-itens-basicos-para-pagar-mensalidade-serasa/>.

* **SILVEIRA, Amanda Almeida da.** *O impacto da mobilidade urbana no acesso e permanência na universidade: estudo sob a perspectiva de gênero*. V ENEPCP – Encontro Nacional de Ensino e Pesquisa do Campo de Públicas, UFRJ.
https://anepecp.org/ojs/index.php/br/article/view/494/76

* **SILVA, Laize Andréa de Souza; ANDRADE, Maurício Oliveira de; MAIA, Maria Leonor Alves.** *Fatores influentes para a adesão de alunos a sistema de carona dinâmica em campus universitário*. Revista Transportes, v. 27, n. 2, p. 17–30, 2019. DOI: 10.14295/transportes.v27i2.1521.
https://www.researchgate.net/publication/335561229_Fatores_influentes_para_a_adesao_de_alunos_a_sistema_de_carona_dinamica_em_campus_universitario
