"""
ETAPA 6 -- Os especialistas, cada um com UMA responsabilidade e SÓ as tools de que precisa.

ESQUELETO:
  ETAPA 6.1 -- criar_normas(), criar_escala(), criar_financeiro(), criar_redator()
  ETAPA 6.2 -- criar_coordenador(): usa Normas, Escala e Financeiro como TOOLS (as_tool)

As tools abaixo (PRONTAS) só repassam a chamada ao MCP Server do RH (cliente_mcp.chamar_mcp_async). Dar a cada agente
só as tools dele é o PRIVILÉGIO MÍNIMO (Etapa 9.1); o hook do 🆕 B (etapa10_governanca.py) confere isso em tempo de execução.

REFERÊNCIAS NAS AULAS
  aula4/ex03_agente_as_tool.py                         Coordenador que chama especialistas como tools    <- o mais parecido
  aula2/agente_handoff2.py                             as_tool com tool_name e tool_description
  aula4/ex02_handoff_roteamento.py                     handoff: compare (quem responde no fim?)
  aula7/exemplos/02_agentes_especializados/main.py     uma responsabilidade por agente
  aula7/agentes.py                                     ModelSettings(temperature=0) para respostas mais estáveis
  aula8/exemplos/06_excessive_agency/1_codigo_pronto/main.py   o problema de dar tools DEMAIS a um agente
"""
import json

from agents import Agent, ModelSettings, RunHooks, function_tool

from etapa05_cliente_mcp import chamar_mcp_async
from etapa04_ferramentas import cotacao_usd_brl

CONFIG = ModelSettings(temperature=0)


# ------------------------------------------------------------------ tools (PRONTAS)
@function_tool
async def consultar_normas(tema: str) -> str:
    """Regras da norma interna sobre um tema: férias, prazos, escala, abono, diária, aprovação, saúde ou dados."""
    return json.dumps(await chamar_mcp_async("consultar_normas", {"tema": tema}), ensure_ascii=False)


@function_tool
async def consultar_escala(equipe: str, inicio: str, fim: str) -> str:
    """Afastamentos da equipe que se sobrepõem ao período (AAAA-MM-DD) e o limite de afastados da regra N5."""
    return json.dumps(await chamar_mcp_async("consultar_escala", {"equipe": equipe, "inicio": inicio, "fim": fim}),
                      ensure_ascii=False)


@function_tool
async def tabela_diarias(tipo_destino: str) -> str:
    """Moeda e valor da diária para o tipo de destino: capital, interior ou exterior."""
    return json.dumps(await chamar_mcp_async("tabela_diarias", {"tipo_destino": tipo_destino}), ensure_ascii=False)


@function_tool
async def consultar_remuneracao(matricula: str) -> str:
    """[RESTRITA] Salário-base de um servidor. Só para calcular a venda de férias (N2)."""
    print(f"[tool] consultar_remuneracao({matricula}) EXECUTOU")  # o 🆕 B prova que, barrada, ela NÃO executa
    return json.dumps(await chamar_mcp_async("consultar_remuneracao", {"matricula": matricula}), ensure_ascii=False)


@function_tool
def cotacao_dolar() -> str:
    """Cotação atual do dólar em reais (USD->BRL). Devolve 'indisponível' se a API falhar: nunca invente o câmbio."""
    cotacao = cotacao_usd_brl()
    return f"{cotacao:.4f}" if cotacao else "indisponível"


# ------------------------------------------------------------------ ETAPA 6.1: especialistas
def criar_normas() -> Agent:
    return Agent(
        name="Normas",
        instructions=(
            "Você é o especialista em NORMAS do RH. Receba os FATOS do pedido (tipo, servidor, período) e "
            "as violações objetivas já apuradas. Sua tarefa: usar a tool consultar_normas para listar as "
            "regras aplicáveis ao tipo do pedido (férias/abono/diária e, se houver violação, os temas "
            "relevantes: prazos, escala, saúde, dados, aprovação) e EXPLICÁ-LAS em linguagem simples. "
            "NÃO calcule valores (isso é do Financeiro) e NÃO consulte a escala (isso é do Escala). "
            "Se houver violações objetivas, cite o código (N1..N10) e explique por que a regra foi violada. "
            "Devolva um parecer curto e direto, em português."
        ),
        tools=[consultar_normas],
        model_settings=CONFIG,
    )


def criar_escala() -> Agent:
    return Agent(
        name="Escala",
        instructions=(
            "Você é o especialista em ESCALA da equipe. Use a tool consultar_escala com o nome da equipe, "
            "a data_inicio e a data_fim do pedido (AAAA-MM-DD). Confira a regra N5: no máximo 30% da equipe "
            "(mínimo 1) pode estar afastada no mesmo dia. "
            "Se não houver conflito, diga 'sem conflito de escala'. "
            "Se houver conflito, mencione quem já está afastado e SUGIRA um novo período com o MESMO número "
            "de dias, começando num dia útil permitido (segunda a quarta, fora dos 2 dias antes de feriado) "
            "e após o retorno dos colegas afastados. "
            "Devolva um parecer curto, em português."
        ),
        tools=[consultar_escala],
        model_settings=CONFIG,
    )


def criar_financeiro() -> Agent:
    return Agent(
        name="Financeiro",
        instructions=(
            "Você é o especialista FINANCEIRO. É o ÚNICO agente autorizado a consultar o salário (regra N2). "
            "Para VENDA DE FÉRIAS (N2): valor = dias_vendidos x salario_base / 30. Chame consultar_remuneracao "
            "com a matrícula para obter o salário e mostre a conta explicitamente. "
            "Para DIÁRIAS (N7): calcule 1 diária por pernoite + meia no dia do retorno. "
            "No exterior, o valor é em USD; chame cotacao_dolar e converta para BRL. "
            "Se cotacao_dolar devolver 'indisponível', escreva 'a calcular' em vez de inventar o câmbio. "
            "Use tabela_diarias para pegar o valor por dia. "
            "Para ABONO: devolva apenas 'não se aplica (sem valor financeiro)' sem chamar nenhuma tool. "
            "Mostre a CONTA, não só o resultado final."
        ),
        tools=[tabela_diarias, consultar_remuneracao, cotacao_dolar],
        model_settings=CONFIG,
    )


def criar_redator() -> Agent:
    return Agent(
        name="Redator",
        instructions=(
            "Você é o REDATOR do despacho. Não tem tools: escreva usando SOMENTE os fatos recebidos "
            "(pedido, servidor, período, violações, pareceres de Normas/Escala/Financeiro, decisão). "
            "Formato do despacho: 1 ou 2 parágrafos curtos, em linguagem administrativa, incluindo:\n"
            "  - matrícula do servidor;\n"
            "  - datas do período (AAAA-MM-DD ou DD/MM/AAAA);\n"
            "  - decisão explícita (DEFERIDO ou INDEFERIDO);\n"
            "  - no INDEFERIMENTO, cite o(s) código(s) de regra (N1..N10) violado(s) e, quando houver "
            "sugestão de datas vinda do Escala, inclua a sugestão;\n"
            "  - no DEFERIMENTO de férias com venda, cite o valor calculado pelo Financeiro;\n"
            "  - no DEFERIMENTO de diária, cite o valor total.\n"
            "NUNCA escreva CPF, CID ou dado de saúde no despacho (regra N10). "
            "Se receber um 'ERRO_VALIDACAO' ou 'FEEDBACK_CHEFIA', REESCREVA o despacho corrigindo o apontamento."
        ),
        model_settings=CONFIG,
    )


# ------------------------------------------------------------------ ETAPA 6.2: coordenador
def criar_coordenador(hooks: RunHooks | None = None, tools_extras: list | None = None) -> Agent:
    tools = [
        criar_normas().as_tool(
            tool_name="parecer_normas",
            tool_description="Regras aplicáveis ao pedido e a explicação de eventuais violações.",
            hooks=hooks,
            failure_error_function=None,
        ),
        criar_escala().as_tool(
            tool_name="parecer_escala",
            tool_description="Conferência da escala da equipe (N5); sugere datas se houver conflito.",
            hooks=hooks,
            failure_error_function=None,
        ),
        criar_financeiro().as_tool(
            tool_name="parecer_financeiro",
            tool_description="Cálculos financeiros do pedido: venda de férias (N2) e diárias (N7).",
            hooks=hooks,
            failure_error_function=None,
        ),
        *(tools_extras or []),
    ]
    return Agent(
        name="Coordenador",
        instructions=(
            "Você coordena os pareceres dos especialistas (Normas, Escala, Financeiro) e os consolida.\n"
            "Decida QUAIS pareceres pedir conforme o tipo do pedido:\n"
            "  - ABONO: só parecer_normas e parecer_escala (abono não tem cálculo financeiro).\n"
            "  - FÉRIAS: os três (Normas, Escala e Financeiro quando há venda de dias).\n"
            "  - DIÁRIA: os três (Normas, Escala apenas se o período afetar a equipe, e Financeiro).\n"
            "Depois, consolide tudo num texto estruturado:\n"
            "  'NORMAS: ...  ESCALA: ...  FINANCEIRO: ...'\n"
            "Não invente valores nem decida sozinho: o Redator vai usar os pareceres para escrever o despacho."
        ),
        tools=tools,
        model_settings=CONFIG,
    )
