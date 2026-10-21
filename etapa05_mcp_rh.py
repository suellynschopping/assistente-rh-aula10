"""
ETAPA 5 -- MCP Server do RH (30 min). Volta aqui na ETAPA 9 (token, regra N8 e auditoria).

Os dados saem de dentro do agente e passam a morar num PROCESSO SEPARADO, que fala MCP. O agente (Etapa 5.3) e os
nós do grafo (Etapa 7, via cliente_mcp.chamar_mcp) só enxergam as tools abaixo: nunca os CSVs.

ESQUELETO: implemente as etapas na ordem (troque cada raise NotImplementedError pelo código da etapa).
  ETAPA 5.1 -- as 5 tools de LEITURA: declare cada uma com @mcp.tool(), escreva a DOCSTRING (é o "schema" que o LLM
               lê) e devolva o resultado da consulta pronta de dados_rh.py. Toda tool devolve UM dict.
  ETAPA 5.2 -- a tool de ESCRITA registrar_decisao, IDEMPOTENTE (protocolo repetido não duplica)
  ETAPA 9.2 -- autorização NO SERVER: token + regra N8 (chefia certa, nunca o próprio servidor) + decisão num enum
  ETAPA 9.3 -- auditoria: toda tentativa de escrita (ALLOW ou DENY) vira uma linha em saidas/auditoria.jsonl

REFERÊNCIAS NAS AULAS
  aula6/desafio2/mcp_unidades.py               MCP Server que lê um CSV                          <- o mais parecido (5.1)
  aula5/exemplos/03_mcp_parametros/server.py   tool com parâmetros opcionais
  aula5/exemplos/05_multiplas_tools/server.py  várias tools no mesmo server, tool de "descoberta"
  aula3/agente_retry3.py                       idempotência (5.2)
  aula5/exemplos/10_seguranca/server_seguro.py token, enum fechado e auditoria NO SERVER        <- o mais parecido (9.2/9.3)

Testar sem agente (MCP Inspector, precisa de Node.js):
    npx @modelcontextprotocol/inspector python etapa05_mcp_rh.py

Pronto quando: o Inspector lista as 6 tools; registrar C1 duas vezes gera um único registro.
"""
import json
import os
from datetime import datetime

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from dados_rh import PASTA, SAIDAS, carregar_servidores, diaria, escala_da_equipe, normas, remuneracao, servidor_publico

# O server roda como SUBPROCESSO: ele não herda o ambiente de quem o chamou. Por isso carrega o .env sozinho
# (mesmo cuidado de aula5/exemplos/02_mcp_basico/database.py).
load_dotenv(PASTA / ".env")

mcp = MCPServer("rh-mcp")

ARQUIVO_REGISTROS = SAIDAS / "registros.json"
ARQUIVO_AUDITORIA = SAIDAS / "auditoria.jsonl"
TOKEN_REGISTRO = os.getenv("TOKEN_REGISTRO", "")
DECISOES_VALIDAS = {"deferido", "indeferido", "indeferido_pela_chefia"}
TIPOS_COM_CHEFIA = {"ferias", "diaria"}  # regra N8


def _ler_registros() -> dict:
    """(PRONTO) {protocolo: registro} gravados até agora."""
    if ARQUIVO_REGISTROS.exists():
        return json.loads(ARQUIVO_REGISTROS.read_text(encoding="utf-8"))
    return {}


def _gravar_registros(registros: dict) -> None:
    """(PRONTO)"""
    ARQUIVO_REGISTROS.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ ETAPA 5.1: leitura
@mcp.tool()
def consultar_servidor(matricula: str) -> dict:
    """Cadastro público de UM servidor, SEM o salário (dado restrito, ver consultar_remuneracao).

    Args:
        matricula: Matrícula do servidor (string de 4 dígitos, ex.: "1002").

    Returns:
        dict com matricula, nome, cargo, equipe, saldo_ferias_dias, abonos_restantes e chefia.
        Se a matrícula não existir, {"erro": "matrícula não encontrada"}.
    """
    return servidor_publico(matricula)


@mcp.tool()
def consultar_escala(equipe: str, inicio: str, fim: str) -> dict:
    """Afastamentos da equipe que se sobrepõem ao período informado e o limite da regra N5.

    Args:
        equipe: Nome da equipe (ex.: "Cartório", "Plantão A", "Inteligência").
        inicio: Data de início do período no formato AAAA-MM-DD.
        fim: Data de fim do período no formato AAAA-MM-DD.

    Returns:
        dict com equipe, tamanho_equipe, limite_afastados (regra N5: 30% da equipe, mínimo 1)
        e afastamentos (lista de servidores afastados no período, com matrícula e datas).
        Se a equipe não existir, {"erro": "..."}.
    """
    return escala_da_equipe(equipe, inicio, fim)


@mcp.tool()
def consultar_normas(tema: str) -> dict:
    """Regras internas (N1..N10) relacionadas a um tema.

    Args:
        tema: Tema da norma. Temas existentes: 'férias', 'prazos', 'escala', 'abono',
            'diária', 'aprovação', 'saúde', 'dados'. Aceita variações sem acento.

    Returns:
        dict com {"tema": tema, "regras": [{"codigo": "N1", "tema": "...", "regra": "..."}]}.
        Lista vazia em "regras" se o tema não existir.
    """
    return {"tema": tema, "regras": normas(tema)}


@mcp.tool()
def tabela_diarias(tipo_destino: str) -> dict:
    """Moeda e valor da diária para o tipo de destino.

    Args:
        tipo_destino: Um de 'capital', 'interior' ou 'exterior'.

    Returns:
        dict com moeda e valor_diaria, ou {"erro": "use capital, interior ou exterior"}.
    """
    return diaria(tipo_destino)


@mcp.tool()
def consultar_remuneracao(matricula: str) -> dict:
    """[RESTRITA] Salário-base de um servidor. Só o Financeiro deve usar (ver 🆕 B).

    Args:
        matricula: Matrícula do servidor (4 dígitos).

    Returns:
        dict com matricula e salario_base, ou {"erro": "matrícula não encontrada"}.
    """
    return remuneracao(matricula)


# ------------------------------------------------------------------ ETAPA 5.2 / 9.2 / 9.3: escrita
def _auditar(protocolo: str, decisao_acesso: str, motivo: str, parametros: dict) -> None:
    """Grava uma linha JSON em saidas/auditoria.jsonl por tentativa de escrita.

    NUNCA grava o token nem o despacho inteiro: só metadados.
    """
    linha = {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "thread_id": parametros.get("thread_id", ""),
        "aprovador": parametros.get("aprovador", ""),
        "tool": "registrar_decisao",
        "protocolo": protocolo,
        "decisao_acesso": decisao_acesso,
        "motivo": motivo,
        "parametros": {k: v for k, v in parametros.items() if k != "token"},
    }
    ARQUIVO_AUDITORIA.parent.mkdir(exist_ok=True)
    with ARQUIVO_AUDITORIA.open("a", encoding="utf-8") as arquivo:
        arquivo.write(json.dumps(linha, ensure_ascii=False) + "\n")


@mcp.tool()
def registrar_decisao(protocolo: str, matricula: str, tipo: str, inicio: str, fim: str, decisao: str,
                      aprovador: str, despacho: str, token: str, thread_id: str = "") -> dict:
    """[ESCRITA -- requer autorização] Grava a decisão final sobre um pedido no cadastro de registros.

    A gravação é IDEMPOTENTE: o mesmo protocolo não grava duas vezes. A autorização e a regra N8
    (chefia certa, sem autoaprovação) são conferidas aqui dentro -- é o SERVER quem nega.

    Args:
        protocolo: protocolo idempotente do pedido (etapa04_ferramentas.gerar_protocolo).
        matricula: matrícula do servidor dono do pedido (4 dígitos).
        tipo: 'ferias', 'abono' ou 'diaria'.
        inicio: data de início do período (AAAA-MM-DD).
        fim: data de fim do período (AAAA-MM-DD).
        decisao: uma de 'deferido', 'indeferido' ou 'indeferido_pela_chefia'.
        aprovador: matrícula da chefia que aprovou (ou 'sistema' quando a regra dispensa chefia).
        despacho: texto do despacho (não é gravado na auditoria).
        token: token de autorização de escrita (TOKEN_REGISTRO). Sem ele, a gravação é negada.
        thread_id: identificador da execução (opcional, para rastreabilidade).

    Returns:
        dict com {"sucesso": bool, ...}. Em caso de sucesso, inclui "protocolo" e "duplicado" se já existia.
        Em caso de negação, {"sucesso": False, "erro": "<motivo>"}.
    """
    parametros = {"matricula": matricula, "tipo": tipo, "inicio": inicio, "fim": fim, "decisao": decisao,
                  "aprovador": aprovador, "thread_id": thread_id}

    def negar(motivo: str) -> dict:
        _auditar(protocolo, "DENY", motivo, parametros)
        return {"sucesso": False, "erro": motivo}

    # ETAPA 9.2 -- negue ANTES de gravar
    if not TOKEN_REGISTRO or token != TOKEN_REGISTRO:
        return negar("token inválido")
    if decisao not in DECISOES_VALIDAS:
        return negar(f"decisão inválida: {decisao!r} (válidas: {sorted(DECISOES_VALIDAS)})")
    if aprovador == matricula:
        return negar("autoaprovação (N8): aprovador não pode ser o próprio servidor")
    if decisao == "deferido" and tipo in TIPOS_COM_CHEFIA:
        servidores = carregar_servidores()
        cadastro = servidores.get(str(matricula).strip())
        chefia_esperada = (cadastro or {}).get("chefia")
        if chefia_esperada and aprovador != chefia_esperada:
            return negar(f"aprovador não é a chefia {chefia_esperada} (N8)")

    # ETAPA 5.2 -- idempotência e gravação
    registros = _ler_registros()
    if protocolo in registros:
        _auditar(protocolo, "ALLOW", "duplicado (idempotência)", parametros)
        return {"sucesso": True, "duplicado": True, "protocolo": protocolo}

    registros[protocolo] = {
        **parametros,
        "despacho": despacho,
        "registrado_em": datetime.now().isoformat(timespec="seconds"),
    }
    _gravar_registros(registros)
    _auditar(protocolo, "ALLOW", "gravado", parametros)
    return {"sucesso": True, "duplicado": False, "protocolo": protocolo}


if __name__ == "__main__":
    mcp.run(transport="stdio")
