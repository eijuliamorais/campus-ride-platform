"""Testes da limpeza da resposta (app/limpeza.py). Não chamam o LLM nem a rede.

Rodar (de backend/services/llm-service):  python3 -m pytest -q tests
Sem pytest instalado, também funciona:     python3 tests/test_limpeza.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.limpeza import SEM_RESPOSTA, limpar_resposta  # noqa: E402

try:
    import pytest
except ImportError:  # sem pytest: os decoradores viram no-op e o __main__ roda os casos
    class _SemPytest:
        class mark:
            @staticmethod
            def parametrize(*_a, **_k):
                return lambda f: f
    pytest = _SemPytest()

CASOS = [
    # nomes de ferramentas
    ("Você tem uma carona confirmada para hoje [minhas_solicitacoes].",
     "Você tem uma carona confirmada para hoje."),
    ("Há duas caronas às 18:00 (buscar_caronas).", "Há duas caronas às 18:00."),
    ("Consultei `buscar_caronas` e não há vagas.", "Consultei a busca de caronas e não há vagas."),
    ("Segundo a ferramenta minhas_solicitacoes, sua reserva está pendente.",
     "Sua reserva está pendente."),
    ("Sua reserva foi confirmada, segundo minhas_solicitacoes.", "Sua reserva foi confirmada."),
    ("Verifiquei minhas_solicitacoes: nada encontrado.", "Verifiquei as suas reservas: nada encontrado."),
    ("Pode cancelar até 2 h antes [minhas_solicitacoes, regras_cancelamento.md].",
     "Pode cancelar até 2 h antes [regras_cancelamento.md]."),
    ("Tem carona às 19:00 [ferramenta: buscar_caronas].", "Tem carona às 19:00."),
    # citações
    ("Pode cancelar sem multa [fonte: regras_cancelamento.md].", "Pode cancelar sem multa [regras_cancelamento.md]."),
    ("Nota mínima 3,5 (avaliacoes_e_penalidades.md).", "Nota mínima 3,5 [avaliacoes_e_penalidades.md]."),
    ("Veja [faq.md, seguranca.md].", "Veja [faq.md] [seguranca.md]."),
    ("Veja [faq].", "Veja [faq.md]."),
    ("Veja [Regras de Cancelamento].", "Veja [regras_cancelamento.md]."),
    ("Veja [contribuição e custos].", "Veja [contribuicao_e_custos.md]."),
    ("Isso está no faq.md.", "Isso está no [faq.md]."),
    ("Regra X [faq.md] [faq.md].", "Regra X [faq.md]."),
    ("Regra Y [contexto].", "Regra Y."),
    ("Regra Z [Trecho 2].", "Regra Z."),
    # Markdown
    ("**Sim**, você pode cancelar.", "Sim, você pode cancelar."),
    ("## Resposta\nVocê pode *cancelar* até __2 h__ antes.", "Resposta\nVocê pode cancelar até 2 h antes."),
    ("Opções:\n* 18:00\n* 19:00", "Opções:\n- 18:00\n- 19:00"),
    ("Veja [a FAQ](https://uniride.example/faq).", "Veja a FAQ."),
    ("| Horário | Vagas |\n|---|---|\n| 18:00 | 2 |", "Horário - Vagas\n18:00 - 2"),
    ("```\nsaída 18:00\n```", "Saída 18:00"),
    # dados internos
    ("Sua reserva (id 3f2b1c9a-1111-4a2b-9c3d-0123456789ab) está CONFIRMADA.",
     "Sua reserva está confirmada."),
    ("Não achei reservas para usuario_id 3f2b1c9a-1111-4a2b-9c3d-0123456789ab.", "Não achei reservas para o seu cadastro."),
    ("Situação: PENDENTE.", "Situação: pendente."),
    ("Foi recusada por SEM_VAGAS.", "Foi recusada por falta de vagas."),
    ("Motivo: OUTRO_CODIGO_NOVO.", "Motivo: outro codigo novo."),
    ("O serviço de caronas está fora do ar (ConnectTimeout).", "O serviço de caronas está fora do ar."),
    ("Preciso do seu usuarioId.", "Preciso do seu cadastro."),
    # datas e setas
    ("Sai em 2026-11-26T21:10:00Z.", "Sai em 26/11 às 18:10."),
    ("Sai em 2026-11-26T18:10:00-03:00.", "Sai em 26/11 às 18:10."),
    ("Nenhuma carona em 2026-11-27.", "Nenhuma carona em 27/11/2026."),
    ("Campus UFLA -> Centro às 18:10.", "Campus UFLA → Centro às 18:10."),
    # o "contexto" do prompt
    ("Segundo o contexto, a nota mínima é 3,5 [faq.md].", "Segundo o regulamento do UniRide, a nota mínima é 3,5 [faq.md]."),
    ("Não encontrei isso no contexto fornecido.", "Não encontrei isso no regulamento do UniRide."),
    ("O contexto não menciona animais.", "O regulamento do UniRide não menciona animais."),
    # o que NÃO deve mudar
    ("Você pode cancelar até 2 h antes, sem penalidade [regras_cancelamento.md].",
     "Você pode cancelar até 2 h antes, sem penalidade [regras_cancelamento.md]."),
    ("A contribuição é de R$ 5,00... combinada antes.", "A contribuição é de R$ 5,00... combinada antes."),
    ("Leve 2 * 3 = 6 reais [sic].", "Leve 2 * 3 = 6 reais [sic]."),
]


@pytest.mark.parametrize("entrada,esperado", CASOS)
def test_limpeza(entrada, esperado):
    assert limpar_resposta(entrada)[0] == esperado


def test_citados_na_ordem():
    _, citados = limpar_resposta("A [seguranca.md] e B (fonte: faq.md) e C [seguranca.md].")
    assert citados == ["seguranca.md", "faq.md"]


@pytest.mark.parametrize("vazio", [None, "", "   ", "[minhas_solicitacoes]", "**  **"])
def test_resposta_vazia(vazio):
    assert limpar_resposta(vazio) == (SEM_RESPOSTA, [])


def test_nao_cita_ferramenta_em_lugar_nenhum():
    for entrada, _ in CASOS:
        texto = limpar_resposta(entrada)[0]
        assert "buscar_caronas" not in texto and "minhas_solicitacoes" not in texto


if __name__ == "__main__":
    erros = 0
    for entrada, esperado in CASOS:
        obtido = limpar_resposta(entrada)[0]
        if obtido != esperado:
            erros += 1
            print(f"FALHOU: {entrada!r}\n  esperado: {esperado!r}\n  obtido:   {obtido!r}")
    for vazio in [None, "", "   ", "[minhas_solicitacoes]", "**  **"]:
        if limpar_resposta(vazio) != (SEM_RESPOSTA, []):
            erros += 1
            print(f"FALHOU (vazio): {vazio!r}")
    test_citados_na_ordem()
    test_nao_cita_ferramenta_em_lugar_nenhum()
    total = len(CASOS) + 5 + 2
    print(f"{total - erros} de {total} testes passaram")
    sys.exit(1 if erros else 0)
