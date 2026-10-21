"""
ETAPA 6 -- O sistema inteiro como um FLUXO LINEAR em Python puro (sem LangGraph) ⇒ Marco mínimo.

ESQUELETO:
  ETAPA 6.3 -- analisar(): o Coordenador junta os pareceres (com os limites da Etapa 4.7)
  ETAPA 6.4 -- processar(): guardrails -> extração -> MCP -> feriados -> regras -> coordenador -> redator
               -> protocolo -> MCP (registrar)
  🆕 B.4    -- (OPCIONAL, bônus) testar_governanca(): os dois testes de bloqueio do --governanca

REFERÊNCIAS NAS AULAS
  aula6/exemplos/01_fluxo_linear/main.py     o fluxo linear: funciona, mas sem decisão nem volta (por isso a Etapa 7)
  aula4/ex03_agente_as_tool.py               o Coordenador com especialistas como tools
  aula7/exemplos/02_agentes_especializados/main.py   cada especialista imprime o que fez: dá para saber quem fez o quê

Rodar:
    python etapa06_linear.py                 # C1, C2, C6 e C11
    python etapa06_linear.py --governanca    # 🆕 B (opcional): os dois testes de bloqueio

Pronto quando: C1, C2 e C11 são gravados com protocolo, C6 vira indeferimento com sugestão de datas, e você sabe dizer
qual agente escreveu cada parte. (Opcional) no --governanca: a tool restrita NÃO executa e o C2 para no orçamento.
"""
import json
import os
import sys

from agents import RunHooks

import etapa06_agentes as agentes
from etapa05_cliente_mcp import chamar_mcp
from dados.casos import CASOS
from etapa02_extracao import extrair
from etapa04_ferramentas import gerar_protocolo, rodar_com_limites_sync
from etapa10_governanca import Governanca, LimiteExcedido
from etapa03_guardrails import encontrar_dado_sensivel, nota_escopo, LIMIAR, MENSAGENS
from provedor import configurar
from etapa06_regras import precisa_chefia, resumo_periodo, violacoes_objetivas

MODELO = configurar()


def analisar(pedido: dict, servidor: dict, periodo: dict, violacoes: list[str], hooks: RunHooks | None = None) -> str:
    entrada = (
        f"PEDIDO: {pedido}\n"
        f"SERVIDOR: matrícula={servidor.get('matricula')} equipe={servidor.get('equipe')} "
        f"saldo_ferias={servidor.get('saldo_ferias_dias')} abonos_restantes={servidor.get('abonos_restantes')} "
        f"chefia={servidor.get('chefia')}\n"
        f"PERÍODO: {periodo}\n"
        f"VIOLAÇÕES OBJETIVAS JÁ APURADAS: {violacoes or 'nenhuma'}"
    )
    resultado = rodar_com_limites_sync(agentes.criar_coordenador(hooks=hooks), entrada, hooks=hooks)
    return resultado.final_output


def processar(texto: str, hooks: RunHooks | None = None) -> dict:
    # 1/9 guardrails de entrada
    print("[1/9] guardrails")
    achado = encontrar_dado_sensivel(texto)
    if achado:
        return {"resultado": "bloqueado", "mensagem": MENSAGENS[achado]}
    nota, _ = nota_escopo(texto)
    if nota >= LIMIAR:
        return {"resultado": "bloqueado", "mensagem": MENSAGENS["fora_do_escopo"], "nota_escopo": nota}

    # 2/9 extração
    print("[2/9] extração")
    pedido = extrair(texto).model_dump(mode="json")
    if not pedido.get("matricula") or not pedido.get("data_inicio") or not pedido.get("data_fim"):
        return {"resultado": "pedir_dados", "pedido": pedido,
                "mensagem": "Informe a matrícula e as datas exatas (AAAA-MM-DD)."}

    # 3/9 identificar servidor
    print("[3/9] identificar servidor")
    servidor = chamar_mcp("consultar_servidor", {"matricula": pedido["matricula"]})
    if servidor.get("erro"):
        return {"resultado": "pedir_dados", "mensagem": f"Servidor não encontrado: {pedido['matricula']}"}

    # 4/9 período (feriados)
    print("[4/9] período")
    periodo = resumo_periodo(pedido["data_inicio"], pedido["data_fim"])

    # 5/9 escala + regras objetivas
    print("[5/9] escala e regras")
    escala = chamar_mcp("consultar_escala",
                        {"equipe": servidor["equipe"], "inicio": pedido["data_inicio"], "fim": pedido["data_fim"]})
    violacoes = violacoes_objetivas(pedido, servidor, periodo, escala)

    # 6/9 coordenador (especialistas)
    print("[6/9] coordenador (especialistas)")
    try:
        parecer = analisar(pedido, servidor, periodo, violacoes, hooks=hooks)
    except LimiteExcedido as erro:
        return {"resultado": "bloqueado_pela_governanca", "motivo": str(erro)}

    # 7/9 redator
    print("[7/9] redator")
    decisao = "indeferido" if violacoes else "deferido"
    entrada_redator = (
        f"PEDIDO: {pedido}\nSERVIDOR: matrícula={servidor.get('matricula')}\n"
        f"PERÍODO: {periodo}\nDECISÃO: {decisao}\nVIOLAÇÕES: {violacoes}\nPARECER: {parecer}"
    )
    despacho = rodar_com_limites_sync(agentes.criar_redator(), entrada_redator).final_output

    # 8/9 protocolo
    print("[8/9] protocolo")
    protocolo = gerar_protocolo(pedido["matricula"], pedido["tipo"], pedido["data_inicio"], pedido["data_fim"])

    # 9/9 registrar
    print("[9/9] registrar")
    aprovador = "pendente_chefia" if precisa_chefia(pedido, violacoes) else "sistema"
    registro = {
        "protocolo": protocolo, "matricula": pedido["matricula"], "tipo": pedido["tipo"],
        "inicio": pedido["data_inicio"], "fim": pedido["data_fim"],
        "decisao": decisao, "aprovador": aprovador, "despacho": despacho,
        "token": os.getenv("TOKEN_REGISTRO", ""), "thread_id": f"linear-{protocolo}",
    }
    resposta_mcp = chamar_mcp("registrar_decisao", registro)

    return {
        "resultado": "registrado" if resposta_mcp.get("sucesso") else "negado_pelo_server",
        "protocolo": protocolo,
        "despacho": despacho,
        "parecer": parecer,
        "violacoes": violacoes,
        "resposta_mcp": resposta_mcp,
    }


def testar_governanca() -> None:
    # 🆕 B.4 (opcional) -- não implementado nesta entrega.
    raise NotImplementedError("🆕 B.4: testar_governanca")


if __name__ == "__main__":
    print(f"[modelo] {MODELO}")
    if "--governanca" in sys.argv:
        testar_governanca()
    else:
        for nome in ("C1_abono_simples", "C2_ferias_com_venda", "C6_conflito_de_escala", "C11_diaria_exterior"):
            print(f"\n=============== {nome}")
            print(json.dumps(processar(CASOS[nome]["pedido"]), ensure_ascii=False, indent=2))
