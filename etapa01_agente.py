"""
ETAPA 1 -- Primeiro agente com tool local (15 min).

ESQUELETO: implemente as etapas na ordem. Cada uma está marcada com um comentário e um
raise NotImplementedError: troque esse raise pelo código da etapa e rode o arquivo.
  ETAPA 1.1 -- a tool consultar_servidor (SEM o salário)
  ETAPA 1.2 -- o agente AtendenteRH com a tool
  ETAPA 1.3 -- duas perguntas: uma que precisa da tool e uma que não precisa

REFERÊNCIAS NAS AULAS
  aula1/segundo_agente.py                            Agent + @function_tool + Runner.run_sync (o básico)
  exercicios_resolvidos/aula4/ex10_function_tool.py  tool que consulta uma TABELA e devolve JSON  <- o mais parecido
  aula8/exemplos/02_agente_tool/main.py              o agente decide quando chamar a tool (e quando não)

Rodar (a partir de aula10/):
    python etapa01_agente.py

Pronto quando: a tool é chamada só na primeira pergunta (o print dentro dela prova).
"""
import json

from agents import Agent, Runner, function_tool

from dados_rh import servidor_publico
from provedor import configurar

MODELO = configurar()  # LLM REAL: PROVEDOR no .env (openai ou ollama)


@function_tool
def consultar_servidor(matricula: str) -> str:
    """Consulta o cadastro público de UM servidor pela matrícula.

    Use esta tool quando o usuário perguntar sobre dados de UM servidor específico
    (nome, cargo, equipe, saldo de férias ou saldo de abonos). NÃO retorna salário
    (dado restrito). Se a matrícula não existir, devolve um JSON com a chave "erro".

    Args:
        matricula: Matrícula do servidor (string de 4 dígitos, ex.: "1002").

    Returns:
        JSON com os campos: matricula, nome, cargo, equipe, saldo_ferias_dias,
        abonos_restantes e chefia. Em caso de matrícula inexistente, {"erro": "..."}.
    """
    print(f"[tool] consultar_servidor {matricula}")
    return json.dumps(servidor_publico(matricula), ensure_ascii=False)


def criar_atendente() -> Agent:
    return Agent(
        name="AtendenteRH",
        instructions=(
            "Você é o(a) atendente do RH. Responde em português, de forma breve e cordial. "
            "Quando a pergunta for sobre os dados de UM servidor específico (nome, equipe, "
            "saldos de férias ou abonos), USE a tool consultar_servidor com a matrícula "
            "informada. Nunca invente saldos ou nomes de cabeça. Para perguntas conceituais "
            "sobre normas (o que é abono, o que é diária, etc.), responda com o seu próprio "
            "conhecimento SEM chamar a tool."
        ),
        tools=[consultar_servidor],
    )


def main() -> None:
    atendente = criar_atendente()
    perguntas = [
        "Quantos dias de férias a matrícula 1002 ainda tem?",
        "O que é abono pecuniário?",
    ]
    for pergunta in perguntas:
        print(f"\n> {pergunta}")
        resultado = Runner.run_sync(atendente, pergunta)
        print(resultado.final_output)


if __name__ == "__main__":
    print(f"[modelo] {MODELO}")
    main()
