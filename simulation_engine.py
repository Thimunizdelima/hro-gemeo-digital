import json
import math
import random
from datetime import datetime
from database import (
    get_connection,
    gerar_paciente_anonimo_no_setor,
    criar_prescricao_padrao,
    criar_evolucao_padrao,
)


def sincronizar_pacientes_setor(cur, sector_id: int, novo_ocupados: int, agora: datetime = None):
    """Garante que a tabela patients tenha exatamente 'novo_ocupados' pacientes para o setor."""
    if agora is None:
        agora = datetime.now()

    cur.execute("SELECT * FROM sectors WHERE id = ?", (sector_id,))
    sector = cur.fetchone()
    if not sector:
        return

    cur.execute("SELECT COUNT(*) as cnt FROM patients WHERE sector_id = ?", (sector_id,))
    atual_db = cur.fetchone()["cnt"]

    if novo_ocupados > atual_db:
        diff = novo_ocupados - atual_db
        cur.execute("SELECT MAX(id) as max_id FROM patients")
        seq = (cur.fetchone()["max_id"] or 350) + 1
        for i in range(diff):
            idx_leito = atual_db + i + 1
            gerar_paciente_anonimo_no_setor(cur, sector, idx_leito, seq + i, agora, "Ajuste de Efetivo / Sobrecarga")
    elif novo_ocupados < atual_db:
        diff = atual_db - novo_ocupados
        cur.execute("""
            SELECT id FROM patients
            WHERE sector_id = ?
            ORDER BY elegivel_alta_segura DESC, escore_news2 ASC, id DESC
            LIMIT ?
        """, (sector_id, diff))
        ids_remover = [r["id"] for r in cur.fetchall()]
        if ids_remover:
            placeholders = ",".join("?" for _ in ids_remover)
            cur.execute(f"DELETE FROM prescription_items WHERE prescription_id IN (SELECT id FROM prescriptions WHERE patient_id IN ({placeholders}))", ids_remover)
            cur.execute(f"DELETE FROM prescriptions WHERE patient_id IN ({placeholders})", ids_remover)
            cur.execute(f"DELETE FROM clinical_evolutions WHERE patient_id IN ({placeholders})", ids_remover)
            cur.execute(f"DELETE FROM patients WHERE id IN ({placeholders})", ids_remover)


def calcular_painel_gemeo_digital():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM power_grid_state WHERE id = 1")
    power_row = cur.fetchone()
    power = dict(power_row) if power_row else {
        "rede_externa": "NORMAL",
        "status_geradores": "STANDBY_OK",
        "tempo_sem_energia_min": 0,
        "autonomia_bateria_vm_min": 90,
        "autonomia_bateria_bic_min": 120,
        "usina_oxigenio_status": "OPERACIONAL",
        "observacao_contingencia": "Operação normal"
    }

    cur.execute("SELECT * FROM it_system_state WHERE id = 1")
    it_row = cur.fetchone()
    it_system = dict(it_row) if it_row else {
        "status_sistema": "ONLINE",
        "causa_queda": "Nenhuma",
        "modulos_afetados": "Nenhum",
        "horas_sem_sistema": 0,
        "modo_operacao": "DIGITAL_ONLINE",
        "prescricoes_papel_pendentes": 0,
        "risco_erro_transcricao": "BAIXO",
        "observacao_ti": "Sistema 100% online."
    }

    cur.execute("SELECT * FROM surgical_center_state WHERE id = 1")
    cc_row = cur.fetchone()
    surgical_center = dict(cc_row) if cc_row else {
        "status_fluxo": "NORMAL",
        "salas_cirurgicas_total": 10,
        "salas_bloqueadas_pos_op": 0,
        "leitos_srpa_fixos": 18,
        "ocupados_srpa": 12,
        "cirurgias_leito_dependentes_retidas": 1,
        "pacientes_uti_alta_bloqueada": 2,
        "cirurgias_eletivas_suspensas": 0,
        "observacao_cc": "Centro Cirúrgico e SRPA (18 leitos) com giro regular."
    }

    blackout_total = (power["rede_externa"] == "QUEDA_INDETERMINADA" and power["status_geradores"] == "FALHA_TOTAL")
    blackout_parcial = (power["rede_externa"] == "QUEDA_INDETERMINADA" and power["status_geradores"] == "FALHA_PARCIAL")
    sistema_fora_do_ar = (it_system["status_sistema"] == "QUEDA_INDETERMINADA")
    bloqueio_cirurgico = (surgical_center["status_fluxo"] == "BLOQUEIO_CADEIA_CC_UTI_ENF")

    cur.execute("SELECT * FROM pharmacy_inventory ORDER BY id")
    farmacia_rows = [dict(m) for m in cur.fetchall()]
    meds_em_falta = [m for m in farmacia_rows if m["status_estoque"] in ("FALTA_TOTAL", "CRITICO_12H")]

    cur.execute("SELECT COUNT(DISTINCT pr.patient_id) as pac_afetados FROM prescription_items pi JOIN prescriptions pr ON pr.id = pi.prescription_id WHERE pi.em_falta_farmacia = 1")
    pacientes_afetados_falta_med = cur.fetchone()["pac_afetados"]

    cur.execute("SELECT * FROM sectors ORDER BY id")
    rows = cur.fetchall()

    setores_analisados = []
    tot_instalados = 0
    tot_contingencia = 0
    tot_bloqueados = 0
    tot_ocupados = 0

    # Contadores específicos da regra: 340 Leitos Fixos + PS (Apoio) + 18 SRPA
    fixos_instalados = 0
    fixos_bloqueados = 0
    fixos_ocupados = 0
    ps_apoio_instalados = 0
    ps_apoio_ocupados = 0
    srpa_instalados = 18
    srpa_ocupados = 0
    leitos_livres_enfermarias = 0

    tot_vent_instalados = 0
    tot_vent_inop = 0
    tot_vent_disp = 0
    tot_vent_uso = 0
    tot_deficit_vent = 0

    tot_mon_instalados = 0
    tot_mon_inop = 0
    tot_mon_disp = 0
    tot_mon_uso = 0
    tot_deficit_mon = 0

    tot_med_atual = 0
    tot_med_ideal = 0
    tot_enf_atual = 0
    tot_enf_ideal = 0
    tot_tec_atual = 0
    tot_tec_ideal = 0

    for r in rows:
        cat = r["categoria_leito"] if "categoria_leito" in r.keys() else "FIXO"
        inst = r["leitos_instalados"]
        cont = r["leitos_contingencia"]
        bloq = r["leitos_bloqueados"]
        ocup = r["ocupados_atual"]
        operacionais = max(1, inst - bloq)
        taxa_ocup = round((ocup / operacionais) * 100, 1)

        if cat == "FIXO":
            fixos_instalados += inst
            fixos_bloqueados += bloq
            fixos_ocupados += ocup
            if r["tipo"] in ("Enfermaria", "Maternidade"):
                leitos_livres_enfermarias += max(0, operacionais - ocup)
        elif cat == "APOIO_PS":
            ps_apoio_instalados = inst
            ps_apoio_ocupados = ocup
        elif cat == "APOIO_SRPA":
            srpa_instalados = inst
            srpa_ocupados = ocup

        cur.execute("SELECT COUNT(*) as altas FROM patients WHERE sector_id = ? AND elegivel_alta_segura = 1", (r["id"],))
        altas_seguras = cur.fetchone()["altas"]

        cur.execute("SELECT COUNT(*) as criticos FROM patients WHERE sector_id = ? AND gravidade = 'Critico'", (r["id"],))
        pac_criticos = cur.fetchone()["criticos"]

        # Cálculo de Ventiladores e Monitores (incluindo quantitativo insuficiente)
        vent_total = r["ventiladores_total"]
        vent_inop = r["ventiladores_inoperantes"] if "ventiladores_inoperantes" in r.keys() else 0
        vent_disp = max(0, vent_total - vent_inop)
        vent_uso = r["ventiladores_em_uso"]
        deficit_vent = max(0, vent_uso - vent_disp)

        mon_total = r["monitores_total"] if "monitores_total" in r.keys() else inst
        mon_inop = r["monitores_inoperantes"] if "monitores_inoperantes" in r.keys() else 0
        mon_disp = max(0, mon_total - mon_inop)
        mon_uso_base = r["monitores_em_uso"] if "monitores_em_uso" in r.keys() else pac_criticos
        if r["tipo"] in ("UTI", "Centro Cirurgico"):
            mon_necessarios = max(mon_uso_base, ocup)
        else:
            mon_necessarios = max(mon_uso_base, pac_criticos + vent_uso)
        deficit_mon = max(0, mon_necessarios - mon_disp)

        med_ideal = math.ceil(ocup / r["ratio_pac_por_medico"]) if ocup > 0 else 1
        enf_ideal = math.ceil(ocup / r["ratio_pac_por_enfermeiro"]) if ocup > 0 else 1
        tec_ideal = math.ceil(ocup / r["ratio_pac_por_tecnico"]) if ocup > 0 else 1

        extra_tec_blackout = vent_uso if blackout_total else 0
        extra_enf_ti = math.ceil(enf_ideal * 0.25) if sistema_fora_do_ar else 0
        extra_tec_ti = math.ceil(tec_ideal * 0.20) if sistema_fora_do_ar else 0

        enf_ideal += extra_enf_ti
        tec_ideal += (extra_tec_blackout + extra_tec_ti)

        deficit_med = max(0, med_ideal - r["medicos_turno"])
        deficit_enf = max(0, enf_ideal - r["enfermeiros_turno"])
        deficit_tec = max(0, tec_ideal - r["tecnicos_turno"])

        relacao_tec_real = round(ocup / max(1, r["tecnicos_turno"]), 1)
        relacao_enf_real = round(ocup / max(1, r["enfermeiros_turno"]), 1)

        fator_sobrecarga_rh = max(0.0, (relacao_tec_real / r["ratio_pac_por_tecnico"]) - 1.0) + max(0.0, (relacao_enf_real / r["ratio_pac_por_enfermeiro"]) - 1.0)
        fator_superlotacao = max(0.0, (taxa_ocup - 85.0) / 15.0)
        penalidade_energia = 35 if blackout_total else (15 if blackout_parcial else 0)
        penalidade_farmacia = len(meds_em_falta) * 6
        penalidade_ti = (38 + min(40, it_system["horas_sem_sistema"] * 2)) if sistema_fora_do_ar else 0
        penalidade_equip = (deficit_vent * 12) + (deficit_mon * 5)

        atraso_med_minutos = int(round((fator_sobrecarga_rh * 38) + (fator_superlotacao * 14) + penalidade_energia + penalidade_farmacia + penalidade_ti + penalidade_equip))

        risco_setor = min(100, int(round(
            max(0, taxa_ocup - 75) * 1.4 +
            (deficit_enf * 12) +
            (deficit_tec * 7) +
            (deficit_med * 10) +
            (15 if vent_uso >= vent_disp else 0) +
            (deficit_vent * 18) +
            (deficit_mon * 8) +
            (40 if blackout_total and vent_uso > 0 else (20 if blackout_total else 0)) +
            (25 if sistema_fora_do_ar else 0) +
            (25 if bloqueio_cirurgico and r["codigo"] in ("CC-SRPA", "UTI-AD", "CLIN-CIR") else 0) +
            (len(meds_em_falta) * 5)
        )))

        if (
            risco_setor >= 75
            or taxa_ocup >= 100
            or deficit_vent > 0
            or deficit_mon >= 3
            or (blackout_total and vent_uso > 0)
            or (sistema_fora_do_ar and r["tipo"] in ("UTI", "Emergencia", "Centro Cirurgico"))
            or (bloqueio_cirurgico and r["codigo"] in ("CC-SRPA", "UTI-AD", "CLIN-CIR"))
        ):
            nivel_alerta = "CRITICO"
        elif risco_setor >= 45 or taxa_ocup >= 90 or deficit_mon > 0 or blackout_parcial or sistema_fora_do_ar:
            nivel_alerta = "ALERTA"
        else:
            nivel_alerta = "NORMAL"

        setores_analisados.append({
            "id": r["id"],
            "codigo": r["codigo"],
            "nome": r["nome"],
            "tipo": r["tipo"],
            "categoria_leito": cat,
            "leitos_instalados": inst,
            "leitos_operacionais": operacionais,
            "leitos_contingencia": cont,
            "leitos_bloqueados": bloq,
            "ocupados_atual": ocup,
            "taxa_ocupacao": taxa_ocup,
            "pacientes_criticos": pac_criticos,
            "elegiveis_alta_segura": altas_seguras,
            "medicos_turno": r["medicos_turno"],
            "medicos_ideal": med_ideal,
            "deficit_medicos": deficit_med,
            "enfermeiros_turno": r["enfermeiros_turno"],
            "enfermeiros_ideal": enf_ideal,
            "deficit_enfermeiros": deficit_enf,
            "tecnicos_turno": r["tecnicos_turno"],
            "tecnicos_ideal": tec_ideal,
            "deficit_tecnicos": deficit_tec,
            "relacao_pac_tecnico": relacao_tec_real,
            "relacao_pac_enfermeiro": relacao_enf_real,
            "ventiladores_total": vent_total,
            "ventiladores_disponiveis": vent_disp,
            "ventiladores_em_uso": vent_uso,
            "ventiladores_inoperantes": vent_inop,
            "deficit_ventiladores": deficit_vent,
            "monitores_total": mon_total,
            "monitores_disponiveis": mon_disp,
            "monitores_em_uso": mon_necessarios,
            "monitores_inoperantes": mon_inop,
            "deficit_monitores": deficit_mon,
            "atraso_aprazamento_min": atraso_med_minutos,
            "risco_assistencial": risco_setor,
            "nivel_alerta": nivel_alerta
        })

        tot_instalados += inst
        tot_contingencia += cont
        tot_bloqueados += bloq
        tot_ocupados += ocup

        tot_vent_instalados += vent_total
        tot_vent_inop += vent_inop
        tot_vent_disp += vent_disp
        tot_vent_uso += vent_uso
        tot_deficit_vent += deficit_vent

        tot_mon_instalados += mon_total
        tot_mon_inop += mon_inop
        tot_mon_disp += mon_disp
        tot_mon_uso += mon_necessarios
        tot_deficit_mon += deficit_mon

        tot_med_atual += r["medicos_turno"]
        tot_med_ideal += med_ideal
        tot_enf_atual += r["enfermeiros_turno"]
        tot_enf_ideal += enf_ideal
        tot_tec_atual += r["tecnicos_turno"]
        tot_tec_ideal += tec_ideal

    tot_operacionais = max(1, tot_instalados - tot_bloqueados)
    taxa_global = round((tot_ocupados / tot_operacionais) * 100, 1)

    fixos_operacionais = max(1, fixos_instalados - fixos_bloqueados)
    taxa_ocupacao_fixos = round((fixos_ocupados / fixos_operacionais) * 100, 1)
    taxa_ocupacao_ps = round((ps_apoio_ocupados / max(1, ps_apoio_instalados)) * 100, 1)
    taxa_ocupacao_srpa = round((srpa_ocupados / max(1, srpa_instalados)) * 100, 1)

    surgical_center["ocupados_srpa"] = srpa_ocupados
    surgical_center["leitos_livres_enfermarias"] = leitos_livres_enfermarias

    cur.execute("SELECT COUNT(*) as total_altas FROM patients WHERE elegivel_alta_segura = 1")
    total_altas_seguras = cur.fetchone()["total_altas"]

    cur.execute("SELECT COUNT(*) as total_criticos FROM patients WHERE gravidade = 'Critico'")
    total_criticos = cur.fetchone()["total_criticos"]

    cur.execute("SELECT COUNT(*) as total_dva FROM patients WHERE drogas_vasoativas = 1")
    total_dva = cur.fetchone()["total_dva"]

    cur.execute("SELECT * FROM contingency_events WHERE ativo = 1 ORDER BY id DESC LIMIT 20")
    eventos = [dict(ev) for ev in cur.fetchall()]

    areas_maior_ocupacao = sorted(
        [{
            "codigo": s["codigo"],
            "nome": s["nome"],
            "categoria_leito": s["categoria_leito"],
            "taxa_ocupacao": s["taxa_ocupacao"],
            "ocupados": s["ocupados_atual"],
            "operacionais": s["leitos_operacionais"]
        } for s in setores_analisados],
        key=lambda x: x["taxa_ocupacao"],
        reverse=True
    )

    power["pacientes_dependentes_vm"] = tot_vent_uso
    power["pacientes_dependentes_bic_dva"] = total_dva
    power["autonomia_restante_vm_min"] = max(0, power["autonomia_bateria_vm_min"] - power["tempo_sem_energia_min"]) if blackout_total else power["autonomia_bateria_vm_min"]
    power["autonomia_restante_bic_min"] = max(0, power["autonomia_bateria_bic_min"] - power["tempo_sem_energia_min"]) if blackout_total else power["autonomia_bateria_bic_min"]

    if sistema_fora_do_ar:
        it_system["prescricoes_papel_pendentes"] = tot_ocupados * max(1, math.ceil(it_system["horas_sem_sistema"] / 12.0))

    recomendacoes = gerar_recomendacoes_contingencia(
        setores_analisados, total_altas_seguras, power, it_system, surgical_center,
        meds_em_falta, pacientes_afetados_falta_med, tot_deficit_vent, tot_deficit_mon
    )

    risco_global = int(round(sum(s["risco_assistencial"] * s["ocupados_atual"] for s in setores_analisados) / max(1, tot_ocupados)))
    if blackout_total:
        risco_global = max(95, risco_global)
    elif sistema_fora_do_ar or bloqueio_cirurgico or tot_deficit_vent > 0:
        risco_global = max(84, risco_global)

    if risco_global >= 75 or taxa_ocupacao_fixos >= 100 or blackout_total or sistema_fora_do_ar or bloqueio_cirurgico or tot_deficit_vent > 0:
        nivel_contingencia_hospitalar = "NÍVEL 3 — VERMELHO (Catástrofe / Emergência Máxima)"
    elif risco_global >= 48 or taxa_ocupacao_fixos >= 90 or len(meds_em_falta) > 0 or blackout_parcial or tot_deficit_mon > 0:
        nivel_contingencia_hospitalar = "NÍVEL 2 — LARANJA (Sobrecarga Assistencial / Alerta Crítico)"
    else:
        nivel_contingencia_hospitalar = "NÍVEL 1 — VERDE/AMARELO (Operação Monitorada)"

    evidence_brainstorm = gerar_brainstorm_evidencias_hro(
        setores_analisados=setores_analisados,
        fixos_instalados=fixos_instalados,
        fixos_ocupados=fixos_ocupados,
        taxa_ocupacao_fixos=taxa_ocupacao_fixos,
        ps_apoio_ocupados=ps_apoio_ocupados,
        srpa_ocupados=srpa_ocupados,
        leitos_livres_enfermarias=leitos_livres_enfermarias,
        total_altas_seguras=total_altas_seguras,
        power=power,
        it_system=it_system,
        surgical_center=surgical_center,
        meds_em_falta=meds_em_falta,
        pac_afetados_med=pacientes_afetados_falta_med,
        tot_deficit_vent=tot_deficit_vent,
        tot_deficit_mon=tot_deficit_mon,
        deficit_rh_total=max(0, tot_enf_ideal - tot_enf_atual) + max(0, tot_tec_ideal - tot_tec_atual) + max(0, tot_med_ideal - tot_med_atual),
        risco_global=risco_global,
    )

    conn.close()
    return {
        "kpis": {
            "total_instalados": tot_instalados,
            "total_operacionais": tot_operacionais,
            "total_contingencia": tot_contingencia,
            "total_bloqueados": tot_bloqueados,
            "total_ocupados": tot_ocupados,
            "taxa_ocupacao_global": taxa_global,
            "fixos_instalados": fixos_instalados,
            "fixos_operacionais": fixos_operacionais,
            "fixos_bloqueados": fixos_bloqueados,
            "fixos_ocupados": fixos_ocupados,
            "taxa_ocupacao_fixos": taxa_ocupacao_fixos,
            "ps_apoio_instalados": ps_apoio_instalados,
            "ps_apoio_ocupados": ps_apoio_ocupados,
            "taxa_ocupacao_ps": taxa_ocupacao_ps,
            "srpa_instalados": srpa_instalados,
            "srpa_ocupados": srpa_ocupados,
            "taxa_ocupacao_srpa": taxa_ocupacao_srpa,
            "total_criticos": total_criticos,
            "total_dva": total_dva,
            "total_altas_seguras": total_altas_seguras,
            "ventiladores_total": tot_vent_instalados,
            "ventiladores_disponiveis": tot_vent_disp,
            "ventiladores_em_uso": tot_vent_uso,
            "ventiladores_inoperantes": tot_vent_inop,
            "deficit_ventiladores": tot_deficit_vent,
            "monitores_total": tot_mon_instalados,
            "monitores_disponiveis": tot_mon_disp,
            "monitores_em_uso": tot_mon_uso,
            "monitores_inoperantes": tot_mon_inop,
            "deficit_monitores": tot_deficit_mon,
            "medicos_atual": tot_med_atual,
            "medicos_ideal": tot_med_ideal,
            "deficit_medicos": max(0, tot_med_ideal - tot_med_atual),
            "enfermeiros_atual": tot_enf_atual,
            "enfermeiros_ideal": tot_enf_ideal,
            "deficit_enfermeiros": max(0, tot_enf_ideal - tot_enf_atual),
            "tecnicos_atual": tot_tec_atual,
            "tecnicos_ideal": tot_tec_ideal,
            "deficit_tecnicos": max(0, tot_tec_ideal - tot_tec_atual),
            "meds_em_falta_count": len(meds_em_falta),
            "pacientes_afetados_farmacia": pacientes_afetados_falta_med,
            "risco_global": risco_global,
            "nivel_contingencia": nivel_contingencia_hospitalar
        },
        "power": power,
        "it_system": it_system,
        "surgical_center": surgical_center,
        "pharmacy": farmacia_rows,
        "top_occupied_areas": areas_maior_ocupacao,
        "sectors": setores_analisados,
        "events": eventos,
        "recommendations": recomendacoes,
        "evidence_brainstorm": evidence_brainstorm,
    }


def gerar_recomendacoes_contingencia(
    setores, total_altas_seguras, power, it_system, surgical_center,
    meds_em_falta, pac_afetados_med, tot_deficit_vent, tot_deficit_mon
):
    recs = []

    if surgical_center["status_fluxo"] == "BLOQUEIO_CADEIA_CC_UTI_ENF":
        recs.append({
            "prioridade": "CRÍTICA",
            "setor": f"GRIDLOCK CIRÚRGICO-INTENSIVO (SRPA {surgical_center['ocupados_srpa']}/18 + {surgical_center['salas_bloqueadas_pos_op']} Salas Bloqueadas)",
            "acao": f"{surgical_center['cirurgias_leito_dependentes_retidas']} pós-operatórios leito-dependentes retidos no CC/SRPA sem vaga de UTI; {surgical_center['pacientes_uti_alta_bloqueada']} altas da UTI travadas por falta de leitos nas Enfermarias (0 vagas).",
            "detalhe": "Suspender imediatamente o mapa cirúrgico eletivo leito-dependente, acionar alta hospitalar extraordinária nas Enfermarias (Clínica Cirúrgica/Médica) para abrir vagas de step-down da UTI e transferir pacientes pós-op intubados da SRPA para a UTI."
        })

    if tot_deficit_vent > 0 or tot_deficit_mon > 0:
        recs.append({
            "prioridade": "CRÍTICA" if tot_deficit_vent > 0 else "ALTA",
            "setor": f"ENGENHARIA CLÍNICA & EQUIPAMENTOS DE SUPORTE À VIDA",
            "acao": f"Quantitativo Insuficiente de Equipamentos: Faltam {tot_deficit_vent} Ventilador(es) Mecânico(s) e {tot_deficit_mon} Monitor(es) Multiparamétrico(s) frente à demanda ativa.",
            "detalhe": "Alocar ventiladores de transporte e aparelhos de anestesia do Centro Cirúrgico para suporte temporário, remanejar monitores de leitos de baixa complexidade e acionar locação emergencial / Engenharia Clínica."
        })

    if it_system["status_sistema"] == "QUEDA_INDETERMINADA":
        recs.append({
            "prioridade": "CRÍTICA",
            "setor": f"SISTEMA INFORMATIZADO FORA DO AR ({it_system['horas_sem_sistema']}h sem previsão — MODO PAPEL)",
            "acao": f"Queda Indeterminada ({it_system['causa_queda']}). {it_system['prescricoes_papel_pendentes']} prescrições manuais em papel acumuladas para conciliação.",
            "detalhe": "Distribuir Kit de Formulários Físicos de Contingência (Prescrição Carbonada, Requisição Manual de Farmácia/Hemoterapia/Lab), exigir Dupla Checagem de Alergias à beira-leito (pulseira vermelha) e ativar mensageiros físicos entre UTIs, PS, Laboratório e Farmácia Central."
        })

    if power["rede_externa"] == "QUEDA_INDETERMINADA" and power["status_geradores"] == "FALHA_TOTAL":
        recs.append({
            "prioridade": "CRÍTICA",
            "setor": "INFRAESTRUTURA ELÉTRICA & SUPORTE À VIDA (BLACKOUT TOTAL)",
            "acao": f"FALHA SIMULTÂNEA DE REDE E GERADORES! Autonomia restante de baterias: VM = {power['autonomia_restante_vm_min']} min | BIC = {power['autonomia_restante_bic_min']} min.",
            "detalhe": f"Mobilizar imediatamente {power['pacientes_dependentes_vm']} profissionais com unidades ressuscitadoras manuais (Ambu) + cilindros torpedos de O2 para os pacientes em Ventilação Mecânica, proteger cadeia de frio da Farmácia/Agência Transfusional e acionar Corpo de Bombeiros/Celesc/SAER-Fron."
        })
    elif power["rede_externa"] == "QUEDA_INDETERMINADA" and power["status_geradores"] == "FALHA_PARCIAL":
        recs.append({
            "prioridade": "ALTA",
            "setor": "INFRAESTRUTURA ELÉTRICA (FALHA PARCIAL DE GERADOR)",
            "acao": "Operação restrita ao barramento de emergência (UTIs e Centro Cirúrgico). Enfermarias sem climatização/elevadores.",
            "detalhe": "Suspender cirurgias eletivas imediatamente, desligar cargas não essenciais e transferir pacientes dependentes de O2/vácuo elétrico das enfermarias para áreas cobertas."
        })

    if len(meds_em_falta) > 0:
        nomes_falta = ", ".join(f"{m['termo_chave']} ({m['status_estoque']})" for m in meds_em_falta)
        recs.append({
            "prioridade": "CRÍTICA",
            "setor": f"FARMÁCIA HOSPITALAR ({pac_afetados_med} prescrições impactadas)",
            "acao": f"Ruptura / Falta de Medicamentos Essenciais: {nomes_falta}.",
            "detalhe": "Protocolo de Substituição Terapêutica Automática habilitado na Prescrição Eletrônica. Acionar empréstimo inter-hospitalar regional (SES/SC)."
        })

    for s in setores:
        if s["taxa_ocupacao"] > 100:
            excedente = s["ocupados_atual"] - s["leitos_operacionais"]
            recs.append({
                "prioridade": "CRÍTICA" if s["taxa_ocupacao"] >= 115 else "ALTA",
                "setor": s["nome"],
                "acao": f"Área com Sobrecarga Crítica ({s['taxa_ocupacao']}% — {excedente} paciente(s) acima da capacidade operacional).",
                "detalhe": f"Executar Fast-Track de Alta Segura ({total_altas_seguras} elegíveis no hospital) e abrir os {s['leitos_contingencia']} leitos de contingência previstos para o setor."
            })
        elif s["tipo"] == "UTI" and s["taxa_ocupacao"] >= 95:
            vagas = max(0, s["leitos_operacionais"] - s["ocupados_atual"])
            recs.append({
                "prioridade": "CRÍTICA",
                "setor": s["nome"],
                "acao": f"Saturação de Terapia Intensiva ({s['taxa_ocupacao']}% — apenas {vagas} leito(s) livre(s)).",
                "detalhe": f"Converter leitos da SRPA/Centro Cirúrgico e avaliar alta da UTI para enfermaria dos pacientes estáveis."
            })

        if s["deficit_ventiladores"] > 0 or s["deficit_monitores"] > 0:
            recs.append({
                "prioridade": "CRÍTICA" if s["deficit_ventiladores"] > 0 else "ALTA",
                "setor": s["nome"],
                "acao": f"Insuficiência de Equipamentos no Setor: Déficit de -{s['deficit_ventiladores']} Ventilador(es) e -{s['deficit_monitores']} Monitor(es) Multiparamétrico(s).",
                "detalhe": f"Em uso/necessários: {s['ventiladores_em_uso']} VM ({s['ventiladores_disponiveis']} disp.) e {s['monitores_em_uso']} Monitores ({s['monitores_disponiveis']} disp.). Priorizar remanejamento imediato."
            })

        if s["deficit_enfermeiros"] > 0 or s["deficit_tecnicos"] > 0:
            recs.append({
                "prioridade": "ALTA" if s["atraso_aprazamento_min"] >= 25 else "MÉDIA",
                "setor": s["nome"],
                "acao": f"Déficit de Dimensionamento COFEN/RDC-7 (-{s['deficit_enfermeiros']} Enf / -{s['deficit_tecnicos']} Téc).",
                "detalhe": f"Atraso estimado de +{s['atraso_aprazamento_min']} min na checagem de prescrições. Remanejar equipe de setores com menor ocupação."
            })

    if not recs:
        recs.append({
            "prioridade": "NORMAL",
            "setor": "Hospital Geral",
            "acao": "Operação dentro dos parâmetros de segurança assistencial.",
            "detalhe": "Manter rondas de giro de leito e monitoramento preventivo."
        })
    return recs


def atualizar_atrasos_e_rupturas_prescricao():
    """Propaga sobrecarga de RH, lotação e falta de medicamentos para os itens de prescrição eletrônica."""
    conn = get_connection()
    cur = conn.cursor()

    # 1. Atualizar rupturas de medicamentos da farmácia nas prescrições vigentes
    cur.execute("UPDATE prescription_items SET em_falta_farmacia = 0, substituto_sugerido = ''")
    cur.execute("SELECT * FROM pharmacy_inventory WHERE status_estoque IN ('FALTA_TOTAL', 'CRITICO_12H')")
    meds_falta = cur.fetchall()

    for m in meds_falta:
        termo = f"%{m['termo_chave']}%"
        sugestao = f"{m['alternativa_terapeutica']} ({m['dose_alternativa']})"
        cur.execute("""
            UPDATE prescription_items
            SET em_falta_farmacia = 1,
                substituto_sugerido = ?
            WHERE medicamento LIKE ?
        """, (sugestao, termo))

    conn.commit()
    conn.close()

    # 2. Atualizar atrasos de aprazamento por setor
    painel = calcular_painel_gemeo_digital()
    mapa_atraso = {s["id"]: s["atraso_aprazamento_min"] for s in painel["sectors"]}

    conn = get_connection()
    cur = conn.cursor()
    for sec_id, atraso in mapa_atraso.items():
        if atraso > 10:
            cur.execute("""
                UPDATE prescription_items
                SET atraso_minutos = ?,
                    status_checagem = CASE
                        WHEN status_checagem = 'Checado' THEN 'Checado'
                        WHEN ? >= 30 THEN 'Atrasado (Alerta RH/Infra)'
                        ELSE 'Aprazado'
                    END
                WHERE prescription_id IN (
                    SELECT pr.id FROM prescriptions pr
                    JOIN patients p ON p.id = pr.patient_id
                    WHERE p.sector_id = ?
                )
            """, (atraso, atraso, sec_id))
        else:
            cur.execute("""
                UPDATE prescription_items
                SET atraso_minutos = 0,
                    status_checagem = CASE
                        WHEN status_checagem = 'Checado' THEN 'Checado'
                        ELSE 'Aprazado'
                    END
                WHERE prescription_id IN (
                    SELECT pr.id FROM prescriptions pr
                    JOIN patients p ON p.id = pr.patient_id
                    WHERE p.sector_id = ?
                )
            """, (sec_id,))
    conn.commit()
    conn.close()


def aplicar_perfil_ocupacao_areas(perfil: str, fator_global_pct: int = 100, setores_custom: list = None):
    """Ajusta o efetivo de ocupação e define quais áreas possuem maior ocupação/sobrecarga."""
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    cur.execute("SELECT * FROM sectors")
    sectors = cur.fetchall()

    perfis_multiplicadores = {
        "PORTA_DE_ENTRADA_E_UTI": {
            "PS-EMERG": 1.48, "UTI-AD": 1.12, "UTI-PED": 1.10, "CLIN-CIR": 1.02, "CLIN-MED": 0.98
        },
        "SURTO_CLINICO_E_PEDIATRICO": {
            "UTI-PED": 1.20, "PED-CLIN": 1.28, "UTI-NEO": 1.15, "CLIN-MED": 1.15, "PS-EMERG": 1.25
        },
        "TRAUMA_E_CIRURGIA": {
            "CLIN-CIR": 1.24, "UTI-AD": 1.15, "PS-EMERG": 1.35, "CLIN-MED": 0.88, "MAT-OBST": 0.85
        },
        "COLAPSO_HOSPITALAR_TOTAL": {
            "UTI-AD": 1.15, "UTI-PED": 1.20, "UTI-NEO": 1.15, "PS-EMERG": 1.65,
            "CLIN-CIR": 1.15, "CLIN-MED": 1.18, "ONCO-UNA": 1.10, "MAT-OBST": 1.12, "PED-CLIN": 1.16
        },
        "OCUPACAO_CONTROLADA_80": {
            "UTI-AD": 0.82, "UTI-PED": 0.80, "UTI-NEO": 0.80, "PS-EMERG": 0.84,
            "CLIN-CIR": 0.78, "CLIN-MED": 0.80, "ONCO-UNA": 0.80, "MAT-OBST": 0.75, "PED-CLIN": 0.76
        }
    }

    if setores_custom:
        # Ajuste manual fino de múltiplos setores enviado pelo painel
        for item in setores_custom:
            sec_id = int(item["id"])
            novo_ocup = max(0, int(item["ocupados_atual"]))
            novo_bloq = max(0, int(item.get("leitos_bloqueados", 0)))
            cur.execute("SELECT ventiladores_total, tipo FROM sectors WHERE id = ?", (sec_id,))
            s_info = cur.fetchone()
            novo_vent = min(s_info["ventiladores_total"], int(round(novo_ocup * (0.78 if s_info["tipo"] == "UTI" else 0.15))))
            cur.execute("UPDATE sectors SET ocupados_atual = ?, leitos_bloqueados = ?, ventiladores_em_uso = ? WHERE id = ?",
                        (novo_ocup, novo_bloq, novo_vent, sec_id))
            sincronizar_pacientes_setor(cur, sec_id, novo_ocup, agora)
        titulo_ev = "Ajuste Manual de Efetivo de Ocupação por Setor"
        desc_ev = "Efetivo de pacientes e áreas de maior ocupação recalibrados manualmente pelo gestor."
    else:
        mapa_mult = perfis_multiplicadores.get(perfil, {})
        escala = fator_global_pct / 100.0
        for s in sectors:
            operacionais = max(1, s["leitos_instalados"] - s["leitos_bloqueados"])
            mult_setor = mapa_mult.get(s["codigo"], 0.92) * escala
            novo_ocup = max(1, int(round(operacionais * mult_setor)))
            novo_vent = min(s["ventiladores_total"], int(round(novo_ocup * (0.80 if s["tipo"] == "UTI" else (0.22 if s["codigo"] == "PS-EMERG" else 0.04)))))
            cur.execute("UPDATE sectors SET ocupados_atual = ?, ventiladores_em_uso = ? WHERE id = ?",
                        (novo_ocup, novo_vent, s["id"]))
            sincronizar_pacientes_setor(cur, s["id"], novo_ocup, agora)

        titulo_ev = f"Reconfiguração de Efetivo e Áreas Críticas ({perfil})"
        desc_ev = f"Aplicado perfil de ocupação '{perfil}' com fator global de {fator_global_pct}%. Censo de pacientes e prescrições sincronizado."

    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('AJUSTE_OCUPACAO', ?, 'ALERTA', ?, ?, ?, 1)
    """, (titulo_ev, desc_ev, json.dumps({"perfil": perfil, "fator_pct": fator_global_pct}), agora.strftime("%d/%m/%Y %H:%M:%S")))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def simular_falta_medicamento(termo_chave: str, status_estoque: str, autonomia_horas: int = 0, alternativa_custom: str = None):
    """Configura falta de medicamento específico e propaga alerta de ruptura e substituto para todas as prescrições."""
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    cur.execute("SELECT * FROM pharmacy_inventory WHERE termo_chave = ?", (termo_chave,))
    existente = cur.fetchone()

    if existente:
        alt = alternativa_custom if alternativa_custom else existente["alternativa_terapeutica"]
        cur.execute("""
            UPDATE pharmacy_inventory
            SET status_estoque = ?, autonomia_horas = ?, alternativa_terapeutica = ?
            WHERE termo_chave = ?
        """, (status_estoque, autonomia_horas, alt, termo_chave))
    else:
        alt = alternativa_custom or "Consultar protocolo da Comissão de Farmácia e Terapêutica (CFT)"
        cur.execute("""
            INSERT INTO pharmacy_inventory (
                termo_chave, nome_comercial, classe_terapeutica, criticidade,
                status_estoque, autonomia_horas, alternativa_terapeutica, dose_alternativa
            ) VALUES (?, ?, 'Medicação Monitorada', 'ALTA', ?, ?, ?, 'Conforme equivalência clínica')
        """, (termo_chave, termo_chave, status_estoque, autonomia_horas, alt))

    conn.commit()
    conn.close()

    atualizar_atrasos_e_rupturas_prescricao()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as itens FROM prescription_items WHERE medicamento LIKE ?", (f"%{termo_chave}%",))
    qtd_afetados = cur.fetchone()["itens"]

    severidade = "CRITICO" if status_estoque == "FALTA_TOTAL" else ("ALERTA" if status_estoque == "CRITICO_12H" else "NORMAL")
    resumo = f"Medicamento '{termo_chave}' atualizado para '{status_estoque}' (Autonomia: {autonomia_horas}h). {qtd_afetados} prescrições ativas impactadas no hospital. Alternativa indicada: {alt}."

    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('RUPTURA_FARMACIA', ?, ?, ?, ?, ?, 1)
    """, (
        f"Ruptura / Controle de Estoque Farmacêutico: {termo_chave}",
        severidade,
        resumo,
        json.dumps({"medicamento": termo_chave, "status": status_estoque, "prescricoes_afetadas": qtd_afetados}),
        agora.strftime("%d/%m/%Y %H:%M:%S")
    ))
    conn.commit()
    conn.close()
    return calcular_painel_gemeo_digital()


def aplicar_substituicao_terapeutica_prescricao(item_id: int = None, termo_chave: str = None):
    """Substitui o medicamento em falta pelo substituto padronizado em um item específico ou em todo o hospital."""
    conn = get_connection()
    cur = conn.cursor()

    if item_id:
        cur.execute("SELECT * FROM prescription_items WHERE id = ?", (item_id,))
        it = cur.fetchone()
        if it and it["substituto_sugerido"]:
            cur.execute("""
                UPDATE prescription_items
                SET medicamento = ?,
                    em_falta_farmacia = 0,
                    substituto_sugerido = ''
                WHERE id = ?
            """, (f"[SUBSTITUÍDO CFT] {it['substituto_sugerido']}", item_id))
    elif termo_chave:
        cur.execute("SELECT * FROM pharmacy_inventory WHERE termo_chave = ?", (termo_chave,))
        med = cur.fetchone()
        if med:
            novo_nome = f"[SUBSTITUÍDO CFT] {med['alternativa_terapeutica']}"
            cur.execute("""
                UPDATE prescription_items
                SET medicamento = ?,
                    dose = ?,
                    em_falta_farmacia = 0,
                    substituto_sugerido = ''
                WHERE medicamento LIKE ?
            """, (novo_nome, med["dose_alternativa"], f"%{termo_chave}%"))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def simular_crise_energia_geradores(rede_externa: str, status_geradores: str, tempo_sem_energia_min: int):
    """Simula falta de energia por tempo indeterminado com falha parcial ou total dos geradores diesel."""
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    autonomia_vm = 90
    autonomia_bic = 120
    rest_vm = max(0, autonomia_vm - tempo_sem_energia_min)
    rest_bic = max(0, autonomia_bic - tempo_sem_energia_min)

    if rede_externa == "QUEDA_INDETERMINADA" and status_geradores == "FALHA_TOTAL":
        usina_o2 = "RESERVA_CILINDROS_CRITICA" if tempo_sem_energia_min >= 45 else "PRESSAO_REDUZIDA_BATERIA"
        obs = (
            f"ALERTA VERMELHO — BLACKOUT HOSPITALAR: Queda da rede externa por tempo indeterminado + FALHA TOTAL DOS GERADORES. "
            f"Tempo decorrido: {tempo_sem_energia_min} min. Autonomia de baterias internas: Ventiladores = {rest_vm} min | Bombas de Infusão = {rest_bic} min. "
            f"Obrigatória prontidão de ventilação manual (Ambu) nos leitos de VM e transferência de pacientes críticos se > 60 min."
        )
        sev = "CRITICO"
        titulo = f"BLACKOUT TOTAL + Falha de Geradores ({tempo_sem_energia_min} min sem energia)"
        # Atualizar prescrições de pacientes em VM com alerta de emergência elétrica
        cur.execute("""
            UPDATE prescriptions
            SET cuidados_enfermagem = '⚡ [ALERTA BLACKOUT / FALHA DE GERADOR] Verificar bateria interna do Ventilador Mecânico e BIC de Drogas Vasoativas; manter Ambu conectado a cilindro torpedo de O2 à beira-leito! ' || cuidados_enfermagem
            WHERE oxigenoterapia LIKE '%VM%' AND cuidados_enfermagem NOT LIKE '%[ALERTA BLACKOUT%'
        """)
    elif rede_externa == "QUEDA_INDETERMINADA" and status_geradores == "FALHA_PARCIAL":
        usina_o2 = "OPERACIONAL_CONTINGENCIA"
        obs = (
            f"ALERTA LARANJA: Queda da rede externa ({tempo_sem_energia_min} min) com FALHA PARCIAL DE GERADORES. "
            f"Apenas barramento crítico de UTI e Sala Vermelha energizado. Demais setores sem energia de tomada comum, elevadores inoperantes."
        )
        sev = "ALERTA"
        titulo = f"Queda de Energia Indeterminada + Falha Parcial de Gerador ({tempo_sem_energia_min} min)"
    else:
        usina_o2 = "OPERACIONAL"
        obs = "Rede elétrica externa normalizada e grupos geradores em prontidão automática."
        sev = "NORMAL"
        titulo = "Restabelecimento Completo de Energia e Geradores"

    cur.execute("""
        UPDATE power_grid_state
        SET rede_externa = ?,
            status_geradores = ?,
            tempo_sem_energia_min = ?,
            autonomia_bateria_vm_min = ?,
            autonomia_bateria_bic_min = ?,
            usina_oxigenio_status = ?,
            observacao_contingencia = ?
        WHERE id = 1
    """, (rede_externa, status_geradores, tempo_sem_energia_min, autonomia_vm, autonomia_bic, usina_o2, obs))

    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('CRISE_ENERGIA', ?, ?, ?, ?, ?, 1)
    """, (
        titulo,
        sev,
        obs,
        json.dumps({"rede": rede_externa, "geradores": status_geradores, "tempo_min": tempo_sem_energia_min, "bateria_vm_restante": rest_vm}),
        agora.strftime("%d/%m/%Y %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def simular_incidente_multiplas_vitimas(num_vitimas: int, descricao_evento: str):
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    vermelhos = max(1, int(round(num_vitimas * 0.28)))
    amarelos = max(1, int(round(num_vitimas * 0.42)))
    verdes = max(0, num_vitimas - vermelhos - amarelos)

    cur.execute("SELECT MAX(id) as max_id FROM patients")
    seq = (cur.fetchone()["max_id"] or 350) + 1

    cur.execute("SELECT id, ocupados_atual, ventiladores_em_uso, ventiladores_total FROM sectors WHERE codigo = 'UTI-AD'")
    uti = cur.fetchone()
    cur.execute("SELECT id, ocupados_atual, ventiladores_em_uso, ventiladores_total FROM sectors WHERE codigo = 'PS-EMERG'")
    ps = cur.fetchone()
    cur.execute("SELECT id, ocupados_atual FROM sectors WHERE codigo = 'CLIN-CIR'")
    cir = cur.fetchone()

    alocados_uti = 0
    alocados_ps = 0
    alocados_cir = 0

    for i in range(num_vitimas):
        if i < vermelhos:
            grav = "Critico"
            cid = "T07"
            diag = f"[IMV START-VERMELHO] Politrauma Grave / Choque Hemorrágico ({descricao_evento})"
            vent = "VM Invasiva (TOT)"
            dva = 1
            news2 = random.randint(9, 14)
            if i % 2 == 0:
                target_sec = uti["id"]
                alocados_uti += 1
                leito = f"UTI-IMV-{alocados_uti:02d}"
            else:
                target_sec = ps["id"]
                alocados_ps += 1
                leito = f"PS-VERMELHA-IMV-{alocados_ps:02d}"
        elif i < vermelhos + amarelos:
            grav = "Grave"
            cid = "S36.9"
            diag = f"[IMV START-AMARELO] Trauma Toracoabdominal / Fraturas Múltiplas ({descricao_evento})"
            vent = "Máscara Reservatório O2 10L/min"
            dva = 0
            news2 = random.randint(5, 8)
            if i % 2 == 0:
                target_sec = ps["id"]
                alocados_ps += 1
                leito = f"PS-AMARELA-IMV-{alocados_ps:02d}"
            else:
                target_sec = cir["id"]
                alocados_cir += 1
                leito = f"CIR-TRAUMA-IMV-{alocados_cir:02d}"
        else:
            grav = "Estavel"
            cid = "S00.9"
            diag = f"[IMV START-VERDE] TCE Leve / Escoriações em Observação ({descricao_evento})"
            vent = "Ar Ambiente"
            dva = 0
            news2 = random.randint(1, 3)
            target_sec = ps["id"]
            alocados_ps += 1
            leito = f"PS-OBS-IMV-{alocados_ps:02d}"

        cod_anon = f"PAC-IMV-{seq:04d}"
        iniciais = f"#IMV-{seq:03d}"
        cur.execute("""
            INSERT INTO patients (
                codigo_anonimo, iniciais_hash, sector_id, leito, idade, sexo,
                cid10, diagnostico, gravidade, escore_news2, suporte_ventilatorio,
                drogas_vasoativas, isolamento, alergias, dias_internacao,
                elegivel_alta_segura, origem_admissao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Nenhum', 'Não informada (Admissão de Emergência IMV)', 0, 0, 'Plano de Catástrofe / IMV')
        """, (
            cod_anon, iniciais, target_sec, leito, random.randint(18, 65),
            random.choice(["M", "F"]), cid, diag, grav, news2, vent, dva
        ))
        pat_id = cur.lastrowid
        criar_prescricao_padrao(cur, pat_id, seq, grav, vent, dva, diag, "Atenção: Admissão IMV", agora)
        criar_evolucao_padrao(cur, pat_id, grav, vent, diag, news2, agora)
        seq += 1

    cur.execute("UPDATE sectors SET ocupados_atual = ocupados_atual + ?, ventiladores_em_uso = MIN(ventiladores_total, ventiladores_em_uso + ?) WHERE id = ?",
                (alocados_uti, alocados_uti, uti["id"]))
    cur.execute("UPDATE sectors SET ocupados_atual = ocupados_atual + ?, ventiladores_em_uso = MIN(ventiladores_total, ventiladores_em_uso + ?) WHERE id = ?",
                (alocados_ps, max(0, vermelhos - alocados_uti), ps["id"]))
    cur.execute("UPDATE sectors SET ocupados_atual = ocupados_atual + ? WHERE id = ?",
                (alocados_cir, cir["id"]))

    resumo = (
        f"Acionado Plano de Catástrofe (IMV): +{num_vitimas} vítimas ({vermelhos} Vermelhos/Críticos, "
        f"{amarelos} Amarelos/Graves, {verdes} Verdes). Alocados: +{alocados_uti} na UTI Adulto, "
        f"+{alocados_ps} no Pronto-Socorro e +{alocados_cir} na Clínica Cirúrgica/Trauma."
    )
    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('IMV_DESASTRE', ?, 'CRITICO', ?, ?, ?, 1)
    """, (
        f"Incidente com Múltiplas Vítimas ({num_vitimas} pacientes)",
        resumo,
        json.dumps({"vitimas": num_vitimas, "vermelhos": vermelhos, "amarelos": amarelos, "verdes": verdes}),
        agora.strftime("%d/%m/%Y %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def simular_restricao_rh(percentual_absenteismo: int, motivo: str, setor_alvo: str = "TODOS"):
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()
    fator = max(0.3, 1.0 - (percentual_absenteismo / 100.0))

    if setor_alvo == "TODOS":
        cur.execute("SELECT id, medicos_turno, enfermeiros_turno, tecnicos_turno FROM sectors")
    else:
        cur.execute("SELECT id, medicos_turno, enfermeiros_turno, tecnicos_turno FROM sectors WHERE codigo = ?", (setor_alvo,))

    afetados = cur.fetchall()
    total_reduzidos = 0
    for s in afetados:
        novo_med = max(1, int(round(s["medicos_turno"] * fator)))
        novo_enf = max(1, int(round(s["enfermeiros_turno"] * fator)))
        novo_tec = max(1, int(round(s["tecnicos_turno"] * fator)))
        total_reduzidos += (s["medicos_turno"] - novo_med) + (s["enfermeiros_turno"] - novo_enf) + (s["tecnicos_turno"] - novo_tec)
        cur.execute("""
            UPDATE sectors
            SET medicos_turno = ?, enfermeiros_turno = ?, tecnicos_turno = ?
            WHERE id = ?
        """, (novo_med, novo_enf, novo_tec, s["id"]))

    resumo = f"Restrição de RH de {percentual_absenteismo}% ({motivo}) aplicada em {setor_alvo}. Redução imediata de {total_reduzidos} profissionais na escala ativa."
    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('RESTRICAO_RH', ?, 'ALERTA', ?, ?, ?, 1)
    """, (
        f"Restrição de RH (-{percentual_absenteismo}% Equipe Assistencial)",
        resumo,
        json.dumps({"percentual": percentual_absenteismo, "profissionais_ausentes": total_reduzidos, "setor": setor_alvo}),
        agora.strftime("%d/%m/%Y %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def simular_intercorrencia_operacional(tipo_intercorrencia: str):
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    if tipo_intercorrencia == "SURTO_KPC":
        cur.execute("UPDATE sectors SET leitos_bloqueados = leitos_bloqueados + 4 WHERE codigo IN ('UTI-AD', 'CLIN-MED')")
        titulo = "Surto de Bactéria Multirresistente (KPC) — Bloqueio de Coorte"
        resumo = "Bloqueados 8 leitos (4 na UTI Adulto e 4 na Clínica Médica) para isolamento de coorte por enterobactéria resistente a carbapenêmicos."
    elif tipo_intercorrencia == "PANE_TOMOGRAFIA":
        cur.execute("SELECT id, ocupados_atual FROM sectors WHERE codigo = 'PS-EMERG'")
        ps = cur.fetchone()
        novo_oc = ps["ocupados_atual"] + 9
        cur.execute("UPDATE sectors SET ocupados_atual = ? WHERE id = ?", (novo_oc, ps["id"]))
        sincronizar_pacientes_setor(cur, ps["id"], novo_oc, agora)
        titulo = "Indisponibilidade de Tomografia / Retenção no Pronto-Socorro"
        resumo = "Atraso diagnóstico em protocolos de AVC/Trauma gerou retenção adicional (+9 pacientes em observação no Pronto-Socorro)."
    elif tipo_intercorrencia == "ONDA_RESPIRATORIA":
        cur.execute("SELECT id, ocupados_atual FROM sectors WHERE codigo IN ('UTI-PED', 'PED-CLIN', 'PS-EMERG')")
        for s in cur.fetchall():
            novo_oc = s["ocupados_atual"] + 5
            cur.execute("UPDATE sectors SET ocupados_atual = ?, ventiladores_em_uso = MIN(ventiladores_total, ventiladores_em_uso + 3) WHERE id = ?", (novo_oc, s["id"]))
            sincronizar_pacientes_setor(cur, s["id"], novo_oc, agora)
        titulo = "Surto Sazonal de Síndrome Respiratória Aguda Grave (SRAG)"
        resumo = "Aumento súbito de internações pediátricas e adultas por SRAG (+15 pacientes e +9 suportes ventilatórios ativados)."
    else:
        cur.execute("SELECT id, ocupados_atual FROM sectors WHERE codigo = 'PS-EMERG'")
        ps = cur.fetchone()
        novo_oc = ps["ocupados_atual"] + 12
        cur.execute("UPDATE sectors SET ocupados_atual = ? WHERE id = ?", (novo_oc, ps["id"]))
        sincronizar_pacientes_setor(cur, ps["id"], novo_oc, agora)
        titulo = "Superlotação de Porta de Entrada e Bloqueio de Fluxo (Boarding)"
        resumo = "Entrada de +12 pacientes de urgência no Pronto-Socorro com retenção de macas da regulação regional."

    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('INTERCORRENCIA', ?, 'CRITICO', ?, ?, ?, 1)
    """, (titulo, resumo, json.dumps({"subtipo": tipo_intercorrencia}), agora.strftime("%d/%m/%Y %H:%M:%S")))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def executar_plano_mitigacao_contingencia():
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    cur.execute("SELECT sector_id, COUNT(*) as qtd FROM patients WHERE elegivel_alta_segura = 1 GROUP BY sector_id")
    altas_por_setor = cur.fetchall()
    total_altas_realizadas = 0

    for row in altas_por_setor:
        qtd_liberar = max(1, int(row["qtd"] * 0.65))
        cur.execute("SELECT ocupados_atual FROM sectors WHERE id = ?", (row["sector_id"],))
        oc_atual = cur.fetchone()["ocupados_atual"]
        novo_oc = max(1, oc_atual - qtd_liberar)
        cur.execute("UPDATE sectors SET ocupados_atual = ? WHERE id = ?", (novo_oc, row["sector_id"]))
        sincronizar_pacientes_setor(cur, row["sector_id"], novo_oc, agora)
        total_altas_realizadas += qtd_liberar

    transferidos_ps = min(12, total_altas_realizadas)
    if transferidos_ps > 0:
        cur.execute("SELECT id, ocupados_atual FROM sectors WHERE codigo = 'PS-EMERG'")
        ps = cur.fetchone()
        novo_ps = max(15, ps["ocupados_atual"] - transferidos_ps)
        cur.execute("UPDATE sectors SET ocupados_atual = ? WHERE id = ?", (novo_ps, ps["id"]))
        sincronizar_pacientes_setor(cur, ps["id"], novo_ps, agora)

    cur.execute("""
        UPDATE sectors
        SET enfermeiros_turno = MAX(enfermeiros_turno, CAST( (ocupados_atual / ratio_pac_por_enfermeiro) + 0.99 AS INTEGER )),
            tecnicos_turno = MAX(tecnicos_turno, CAST( (ocupados_atual / ratio_pac_por_tecnico) + 0.99 AS INTEGER )),
            medicos_turno = MAX(medicos_turno, CAST( (ocupados_atual / ratio_pac_por_medico) + 0.99 AS INTEGER ))
        WHERE codigo IN ('UTI-AD', 'PS-EMERG', 'UTI-PED', 'UTI-NEO')
    """)

    # Restabelecer gerador de emergência, sistema de TI e aplicar substituições terapêuticas automáticas da CFT
    cur.execute("""
        UPDATE power_grid_state
        SET rede_externa = 'NORMAL', status_geradores = 'STANDBY_OK', tempo_sem_energia_min = 0,
            usina_oxigenio_status = 'OPERACIONAL',
            observacao_contingencia = 'Energia restabelecida via Subestação / Gerador de Contingência Mobile.'
        WHERE id = 1
    """)
    cur.execute("""
        UPDATE it_system_state
        SET status_sistema = 'ONLINE', causa_queda = 'Nenhuma',
            modulos_afetados = 'Nenhum (PEP, Farmácia, LIS e PACS Operacionais)',
            horas_sem_sistema = 0, modo_operacao = 'DIGITAL_ONLINE',
            prescricoes_papel_pendentes = 0, risco_erro_transcricao = 'BAIXO',
            observacao_ti = 'Sistema restabelecido via Cluster de Contingência Local e conciliação de prontuários.'
        WHERE id = 1
    """)
    cur.execute("""
        UPDATE surgical_center_state
        SET status_fluxo = 'NORMAL', salas_bloqueadas_pos_op = 0,
            ocupados_srpa = 12, cirurgias_leito_dependentes_retidas = 0,
            pacientes_uti_alta_bloqueada = 0, cirurgias_eletivas_suspensas = 0,
            observacao_cc = 'Fluxo cirúrgico-intensivo desbloqueado via giro de leitos (Enfermaria -> UTI -> SRPA).'
        WHERE id = 1
    """)
    cur.execute("UPDATE sectors SET ventiladores_inoperantes = 0, monitores_inoperantes = 0")
    cur.execute("UPDATE pharmacy_inventory SET status_estoque = 'NORMAL', autonomia_horas = 120")

    resumo = (
        f"Plano de Resposta Executado: {total_altas_realizadas} altas seguras efetivadas (Fast-Track), "
        f"{transferidos_ps} pacientes transferidos do Pronto-Socorro, desbloqueio do fluxo Cirúrgico/UTI/Enfermaria, "
        f"recomposição de monitores/ventiladores, escala crítica de RH, estoque farmacêutico, cluster de TI e energia."
    )
    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('MITIGACAO', 'Acionamento do Plano Integrado de Contingência HRO', 'NORMAL', ?, ?, ?, 1)
    """, (resumo, json.dumps({"altas": total_altas_realizadas, "transferidos_ps": transferidos_ps}), agora.strftime("%d/%m/%Y %H:%M:%S")))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def simular_queda_sistema_ti(status_sistema: str, causa_queda: str, modulos_afetados: str, horas_sem_sistema: int = 12):
    """Simula queda total ou parcial do sistema informatizado hospitalar (HIS/PEP/PACS) sem previsão de retorno."""
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    cur.execute("SELECT SUM(ocupados_atual) as tot_pac FROM sectors")
    tot_pac = cur.fetchone()["tot_pac"] or 330

    if status_sistema == "QUEDA_INDETERMINADA":
        modo = "CONTINGENCIA_PAPEL_MANUAL"
        pendentes = tot_pac * max(1, math.ceil(horas_sem_sistema / 12.0))
        risco_transc = "CRÍTICO (Sem validação eletrônica de Alergia/Dose)" if horas_sem_sistema >= 6 else "ALTO (Transcrição Manual)"
        obs = (
            f"📵 SISTEMA FORA DO AR POR TEMPO INDETERMINADO ({causa_queda}). "
            f"Módulos inoperantes: {modulos_afetados}. Tempo acumulado: {horas_sem_sistema}h sem previsão de retorno. "
            f"Operação 100% em Formulários Físicos de Contingência (Papel Carbonado). "
            f"Volume acumulado: {pendentes} prescrições/evoluções físicas aguardando futura digitação/conciliação."
        )
        sev = "CRITICO"
        titulo = f"Queda do Sistema Informatizado sem Previsão de Retorno ({causa_queda})"
        cur.execute("""
            UPDATE prescriptions
            SET observacoes_clinicas = '📵 [CONTINGÊNCIA EM PAPEL — SISTEMA FORA DO AR] Conferir pulseira física de ALERGIA à beira-leito antes de administrar qualquer medicação! Encaminhar 2ª via carbonada física à Farmácia Central. ' || observacoes_clinicas
            WHERE observacoes_clinicas NOT LIKE '%[CONTINGÊNCIA EM PAPEL%'
        """)
    else:
        modo = "DIGITAL_ONLINE"
        pendentes = 0
        risco_transc = "BAIXO"
        obs = "Sistema de Gestão Hospitalar, Prescrição Eletrônica (PEP), Farmácia e PACS/LIS 100% online."
        sev = "NORMAL"
        titulo = "Restabelecimento do Sistema Informatizado Hospitalar (PEP/HIS Online)"

    cur.execute("""
        UPDATE it_system_state
        SET status_sistema = ?,
            causa_queda = ?,
            modulos_afetados = ?,
            horas_sem_sistema = ?,
            modo_operacao = ?,
            prescricoes_papel_pendentes = ?,
            risco_erro_transcricao = ?,
            observacao_ti = ?
        WHERE id = 1
    """, (status_sistema, causa_queda, modulos_afetados, horas_sem_sistema, modo, pendentes, risco_transc, obs))

    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('QUEDA_SISTEMA_TI', ?, ?, ?, ?, ?, 1)
    """, (
        titulo,
        sev,
        obs,
        json.dumps({"status": status_sistema, "causa": causa_queda, "horas": horas_sem_sistema, "pendentes_papel": pendentes}),
        agora.strftime("%d/%m/%Y %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def simular_crise_equipamentos(
    cenario: str,
    setor_alvo: str = "TODOS",
    ventiladores_inop: int = 8,
    monitores_inop: int = 18
):
    """
    Simula falta de monitores multiparamétricos, falta de ventiladores mecânicos
    e quantitativo insuficiente frente à demanda de pacientes críticos/monitorizados.
    """
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    if cenario == "NORMALIZAR":
        cur.execute("""
            UPDATE sectors
            SET ventiladores_inoperantes = 0,
                monitores_inoperantes = 0,
                ventiladores_em_uso = MIN(ventiladores_total, ventiladores_em_uso),
                monitores_em_uso = MIN(monitores_total, ocupados_atual)
        """)
        titulo = "Normalização do Parque de Monitores e Ventiladores Mecânicos"
        obs = "Engenharia Clínica restabeleceu 100% dos ventiladores e monitores multiparamétricos em manutenção/contingência."
        sev = "NORMAL"
    elif cenario == "FALTA_CRITICA_AMBOS":
        # Indisponibilidade severa + aumento de demanda gerando quantitativo insuficiente explícito em UTI, PS, SRPA e Enfermarias
        ajustes = [
            # (codigo, vm_inop, vm_uso, mon_inop, mon_uso)
            ("UTI-AD", 6, 39, 8, 40),
            ("UTI-PED", 2, 9, 3, 10),
            ("PS-EMERG", 4, 16, 9, 34),
            ("CC-SRPA", 3, 9, 5, 18),
            ("CLIN-CIR", 2, 5, 5, 22),
            ("CLIN-MED", 2, 6, 6, 24),
        ]
        for cod, v_inop, v_uso, m_inop, m_uso in ajustes:
            if setor_alvo in ("TODOS", cod):
                cur.execute("""
                    UPDATE sectors
                    SET ventiladores_inoperantes = ?,
                        ventiladores_em_uso = MAX(ventiladores_em_uso, ?),
                        monitores_inoperantes = ?,
                        monitores_em_uso = MAX(monitores_em_uso, ?)
                    WHERE codigo = ?
                """, (v_inop, v_uso, m_inop, m_uso, cod))
        titulo = "Escassez Crítica: Falta de Ventiladores Mecânicos e Monitores Multiparamétricos"
        obs = (
            "Quantitativo insuficiente de suporte à vida e monitorização: demanda de pacientes intubados e graves "
            "superou o parque disponível de ventiladores e monitores multiparamétricos (equipamentos inoperantes + sobrecarga assistencial)."
        )
        sev = "CRITICO"
    elif cenario == "FALTA_MONITORES":
        if setor_alvo == "TODOS":
            cur.execute("""
                UPDATE sectors
                SET monitores_inoperantes = CASE
                    WHEN tipo IN ('UTI', 'Emergencia', 'Centro Cirurgico') THEN MAX(4, CAST(monitores_total * 0.28 AS INTEGER))
                    ELSE MAX(3, CAST(monitores_total * 0.30 AS INTEGER))
                END,
                monitores_em_uso = MAX(monitores_em_uso, ocupados_atual)
                WHERE codigo IN ('UTI-AD', 'UTI-PED', 'PS-EMERG', 'CC-SRPA', 'CLIN-MED', 'CLIN-CIR')
            """)
        else:
            cur.execute("""
                UPDATE sectors
                SET monitores_inoperantes = ?,
                    monitores_em_uso = MAX(monitores_em_uso, ocupados_atual)
                WHERE codigo = ?
            """, (monitores_inop, setor_alvo))
        titulo = f"Falta / Quantitativo Insuficiente de Monitores Multiparamétricos ({setor_alvo})"
        obs = "Insuficiência de monitores multiparamétricos para pacientes críticos/pós-operatórios e leitos de observação."
        sev = "ALERTA"
    elif cenario == "FALTA_VENTILADORES":
        if setor_alvo == "TODOS":
            cur.execute("""
                UPDATE sectors
                SET ventiladores_inoperantes = CASE
                    WHEN codigo = 'UTI-AD' THEN 6
                    WHEN codigo = 'PS-EMERG' THEN 4
                    WHEN codigo = 'CC-SRPA' THEN 3
                    WHEN codigo = 'UTI-PED' THEN 2
                    ELSE 1
                END,
                ventiladores_em_uso = CASE
                    WHEN codigo = 'UTI-AD' THEN 38
                    WHEN codigo = 'PS-EMERG' THEN 15
                    WHEN codigo = 'CC-SRPA' THEN 9
                    ELSE ventiladores_em_uso
                END
            """)
        else:
            cur.execute("""
                UPDATE sectors
                SET ventiladores_inoperantes = ?,
                    ventiladores_em_uso = MAX(ventiladores_em_uso, ventiladores_total - ? + 3)
                WHERE codigo = ?
            """, (ventiladores_inop, ventiladores_inop, setor_alvo))
        titulo = f"Falta / Quantitativo Insuficiente de Ventiladores Mecânicos ({setor_alvo})"
        obs = "Demanda de pacientes em ventilação mecânica invasiva superou o quantitativo operacional de ventiladores do setor."
        sev = "CRITICO"
    else:
        # Customizado
        if setor_alvo == "TODOS":
            cur.execute("""
                UPDATE sectors
                SET ventiladores_inoperantes = ?,
                    monitores_inoperantes = ?
                WHERE codigo IN ('UTI-AD', 'PS-EMERG', 'CC-SRPA')
            """, (max(1, ventiladores_inop // 3), max(1, monitores_inop // 3)))
        else:
            cur.execute("""
                UPDATE sectors
                SET ventiladores_inoperantes = ?,
                    monitores_inoperantes = ?
                WHERE codigo = ?
            """, (ventiladores_inop, monitores_inop, setor_alvo))
        titulo = f"Ajuste de Indisponibilidade/Déficit de Equipamentos ({setor_alvo})"
        obs = f"Registrados {ventiladores_inop} ventilador(es) e {monitores_inop} monitor(es) indisponíveis/em falta."
        sev = "CRITICO" if ventiladores_inop > 0 else "ALERTA"

    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('CRISE_EQUIPAMENTOS', ?, ?, ?, ?, ?, 1)
    """, (
        titulo,
        sev,
        obs,
        json.dumps({"cenario": cenario, "setor": setor_alvo, "vm_inop": ventiladores_inop, "mon_inop": monitores_inop}),
        agora.strftime("%d/%m/%Y %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def simular_superlotacao_centro_cirurgico(
    acao: str = "DISPARAR_BLOQUEIO",
    cirurgias_leito_dependentes: int = 6,
    pacientes_uti_alta_bloqueada: int = 8,
    salas_bloqueadas: int = 4
):
    """
    Simula o cenário de Superlotação do Centro Cirúrgico / SRPA (18 leitos), com cirurgias leito-dependentes
    retidas no pós-operatório por falta de vaga na UTI, enquanto a UTI está 100% lotada sem conseguir
    dar alta (step-down) aos pacientes estáveis porque não há leitos livres nas Enfermarias.
    """
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    if acao == "DESBLOQUEAR_GIRO":
        # 1. Liberar vagas nas enfermarias receptoras (CLIN-CIR e CLIN-MED)
        for cod, meta_ocup in [("CLIN-CIR", 74), ("CLIN-MED", 70), ("ONCO-UNA", 38)]:
            cur.execute("SELECT id FROM sectors WHERE codigo = ?", (cod,))
            s = cur.fetchone()
            if s:
                cur.execute("UPDATE sectors SET ocupados_atual = ?, leitos_bloqueados = 1 WHERE id = ?", (meta_ocup, s["id"]))
                sincronizar_pacientes_setor(cur, s["id"], meta_ocup, agora)

        # 2. Transferir pacientes de alta bloqueada da UTI-AD para a enfermaria (abrindo vagas na UTI-AD)
        cur.execute("SELECT id FROM sectors WHERE codigo = 'UTI-AD'")
        uti = cur.fetchone()
        if uti:
            cur.execute("UPDATE sectors SET ocupados_atual = 35, leitos_bloqueados = 0, ventiladores_em_uso = 28, monitores_em_uso = 35 WHERE id = ?", (uti["id"],))
            sincronizar_pacientes_setor(cur, uti["id"], 35, agora)

        # 3. Normalizar SRPA (18 leitos fixos -> 11 ocupados) e liberar salas cirúrgicas
        cur.execute("SELECT id FROM sectors WHERE codigo = 'CC-SRPA'")
        srpa = cur.fetchone()
        if srpa:
            cur.execute("UPDATE sectors SET ocupados_atual = 11, ventiladores_em_uso = 2, monitores_em_uso = 11 WHERE id = ?", (srpa["id"],))
            sincronizar_pacientes_setor(cur, srpa["id"], 11, agora)

        obs = "Giro de leitos concluído: Altas efetivadas na Clínica Cirúrgica/Médica -> Step-down dos pacientes de alta da UTI realizado -> Admissão dos pacientes pós-operatórios leito-dependentes da SRPA na UTI Adulto. Salas cirúrgicas liberadas."
        cur.execute("""
            UPDATE surgical_center_state
            SET status_fluxo = 'NORMAL',
                salas_bloqueadas_pos_op = 0,
                ocupados_srpa = 11,
                cirurgias_leito_dependentes_retidas = 0,
                pacientes_uti_alta_bloqueada = 0,
                cirurgias_eletivas_suspensas = 0,
                observacao_cc = ?
            WHERE id = 1
        """, (obs,))

        cur.execute("""
            INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
            VALUES ('CENTRO_CIRURGICO', 'Desbloqueio do Fluxo Cirúrgico-UTI-Enfermaria', 'NORMAL', ?, '{}', ?, 1)
        """, (obs, agora.strftime("%d/%m/%Y %H:%M:%S")))
    else:
        # DISPARAR_BLOQUEIO:
        # 1. Enfermarias receptoras (CLIN-CIR 85 leitos, CLIN-MED 80 leitos, ONCO-UNA 45 leitos) ficam com 100%+ de ocupação (0 leitos disponíveis para receber alta da UTI)
        lotacao_enfermarias = [
            ("CLIN-CIR", 87, 0),  # 87/85 leitos (0 vagas!)
            ("CLIN-MED", 82, 0),  # 82/80 leitos (0 vagas!)
            ("ONCO-UNA", 45, 0),  # 45/45 leitos (0 vagas!)
        ]
        for cod, ocup_alvo, bloq_alvo in lotacao_enfermarias:
            cur.execute("SELECT id FROM sectors WHERE codigo = ?", (cod,))
            sec = cur.fetchone()
            if sec:
                cur.execute("UPDATE sectors SET ocupados_atual = ?, leitos_bloqueados = ? WHERE id = ?", (ocup_alvo, bloq_alvo, sec["id"]))
                sincronizar_pacientes_setor(cur, sec["id"], ocup_alvo, agora)

        # 2. UTI Adulto (40 leitos fixos) fica em 40/40 (100% ocupada), com 'pacientes_uti_alta_bloqueada' pacientes prontos para alta para o setor, mas retidos sem leito de destino
        cur.execute("SELECT id FROM sectors WHERE codigo = 'UTI-AD'")
        uti = cur.fetchone()
        if uti:
            cur.execute("""
                UPDATE sectors
                SET ocupados_atual = 40,
                    leitos_bloqueados = 0,
                    ventiladores_em_uso = 34,
                    monitores_em_uso = 40
                WHERE id = ?
            """, (uti["id"],))
            sincronizar_pacientes_setor(cur, uti["id"], 40, agora)
            # Marcar os pacientes de step-down na UTI-AD como elegíveis para alta segura (retidos na UTI por falta de leito no setor)
            cur.execute("UPDATE patients SET elegivel_alta_segura = 0 WHERE sector_id = ?", (uti["id"],))
            cur.execute("""
                UPDATE patients
                SET elegivel_alta_segura = 1,
                    gravidade = 'Pre-Alta',
                    escore_news2 = 2,
                    suporte_ventilatorio = 'Cateter Nasal O2 1L/min',
                    drogas_vasoativas = 0,
                    diagnostico = '[ALTA UTI BLOQUEADA — SEM LEITO ENFERMARIA] ' || REPLACE(diagnostico, '[ALTA UTI BLOQUEADA — SEM LEITO ENFERMARIA] ', '')
                WHERE id IN (
                    SELECT id FROM patients WHERE sector_id = ? ORDER BY id DESC LIMIT ?
                )
            """, (uti["id"], pacientes_uti_alta_bloqueada))

        # 3. SRPA (18 leitos fixos) fica superlotada (18 leitos da SRPA + pacientes retidos em salas cirúrgicas = 18 + salas_bloqueadas)
        ocup_srpa_novo = 18 + salas_bloqueadas
        vent_srpa_novo = max(cirurgias_leito_dependentes, salas_bloqueadas + 3)
        cur.execute("SELECT id FROM sectors WHERE codigo = 'CC-SRPA'")
        srpa = cur.fetchone()
        if srpa:
            cur.execute("""
                UPDATE sectors
                SET ocupados_atual = ?,
                    ventiladores_em_uso = ?,
                    monitores_em_uso = ?
                WHERE id = ?
            """, (ocup_srpa_novo, vent_srpa_novo, ocup_srpa_novo, srpa["id"]))
            sincronizar_pacientes_setor(cur, srpa["id"], ocup_srpa_novo, agora)
            # Marcar os pacientes leito-dependentes retidos na SRPA/Salas Cirúrgicas
            cur.execute("""
                UPDATE patients
                SET gravidade = 'Critico',
                    escore_news2 = 9,
                    suporte_ventilatorio = 'VM Invasiva (Aparelho Anestesia / Transporte)',
                    drogas_vasoativas = 1,
                    origem_admissao = 'Pós-Op Leito-Dependente Retido no CC/SRPA',
                    diagnostico = '[CIRURGIA LEITO-DEPENDENTE AGUARDANDO UTI] ' || REPLACE(diagnostico, '[CIRURGIA LEITO-DEPENDENTE AGUARDANDO UTI] ', '')
                WHERE id IN (
                    SELECT id FROM patients WHERE sector_id = ? ORDER BY id DESC LIMIT ?
                )
            """, (srpa["id"], cirurgias_leito_dependentes))

        suspensas = cirurgias_leito_dependentes * 2 + salas_bloqueadas
        obs = (
            f"🚨 BLOQUEIO EM CADEIA (EXIT BLOCK CIRÚRGICO-INTENSIVO): "
            f"1) Clínica Cirúrgica (87/85) e Clínica Médica (82/80) com 0 leitos livres; "
            f"2) {pacientes_uti_alta_bloqueada} pacientes da UTI Adulto com alta médica liberada estão RETIDOS na UTI por falta de leito no setor de destino; "
            f"3) UTI Adulto (40/40) sem vagas para receber pós-operatórios; "
            f"4) SRPA superlotada ({ocup_srpa_novo}/18 leitos) com {cirurgias_leito_dependentes} cirurgias leito-dependentes intubadas aguardando UTI e {salas_bloqueadas} Salas Cirúrgicas travadas servindo de UTI improvisada ({suspensas} cirurgias suspensas)."
        )

        cur.execute("""
            UPDATE surgical_center_state
            SET status_fluxo = 'BLOQUEIO_CADEIA_CC_UTI_ENF',
                salas_bloqueadas_pos_op = ?,
                ocupados_srpa = ?,
                cirurgias_leito_dependentes_retidas = ?,
                pacientes_uti_alta_bloqueada = ?,
                cirurgias_eletivas_suspensas = ?,
                observacao_cc = ?
            WHERE id = 1
        """, (salas_bloqueadas, ocup_srpa_novo, cirurgias_leito_dependentes, pacientes_uti_alta_bloqueada, suspensas, obs))

        cur.execute("""
            INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
            VALUES ('CENTRO_CIRURGICO', ?, 'CRITICO', ?, ?, ?, 1)
        """, (
            f"Superlotação do Centro Cirúrgico/SRPA ({ocup_srpa_novo}/18) + Cirurgias Leito-Dependentes sem Vaga UTI",
            obs,
            json.dumps({
                "ocupados_srpa": ocup_srpa_novo,
                "leitos_srpa_fixos": 18,
                "cirurgias_leito_dependentes": cirurgias_leito_dependentes,
                "pacientes_uti_alta_bloqueada": pacientes_uti_alta_bloqueada,
                "salas_bloqueadas": salas_bloqueadas
            }),
            agora.strftime("%d/%m/%Y %H:%M:%S")
        ))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


def gerar_brainstorm_evidencias_hro(
    setores_analisados,
    fixos_instalados,
    fixos_ocupados,
    taxa_ocupacao_fixos,
    ps_apoio_ocupados,
    srpa_ocupados,
    leitos_livres_enfermarias,
    total_altas_seguras,
    power,
    it_system,
    surgical_center,
    meds_em_falta,
    pac_afetados_med,
    tot_deficit_vent,
    tot_deficit_mon,
    deficit_rh_total,
    risco_global,
):
    """
    Gera o Brainstorm Estratégico Baseado em Evidências Científicas calibrado em tempo real
    para o perfil do Hospital Regional do Oeste (340 leitos fixos + PS Apoio + 18 leitos SRPA).
    """
    mapa_sec = {s["codigo"]: s for s in setores_analisados}
    uti_ad = mapa_sec.get("UTI-AD", {})
    clin_cir = mapa_sec.get("CLIN-CIR", {})
    clin_med = mapa_sec.get("CLIN-MED", {})
    ps_emerg = mapa_sec.get("PS-EMERG", {})
    cc_srpa = mapa_sec.get("CC-SRPA", {})

    bloqueio_cc = surgical_center.get("status_fluxo") == "BLOQUEIO_CADEIA_CC_UTI_ENF" or srpa_ocupados >= 16
    uti_saturada = uti_ad.get("taxa_ocupacao", 0) >= 92
    enfermarias_cheias = leitos_livres_enfermarias <= 6
    ps_superlotado = ps_apoio_ocupados >= 45
    blackout = power.get("rede_externa") == "QUEDA_INDETERMINADA"
    queda_ti = it_system.get("status_sistema") == "QUEDA_INDETERMINADA"

    if risco_global >= 75 or blackout or queda_ti or bloqueio_cc or tot_deficit_vent > 0:
        estagio_csc = "FASE 3 — CRISIS CARE (Padrão de Crise / Salvamento de Vidas)"
        cor_csc = "CRITICO"
        desc_csc = (
            "Capacidade convencional e de contingência ultrapassadas (NAM/IOM Crisis Standards of Care). "
            "Exige intervenção imediata de comando unificado (HICS), suspensão de eletivas leito-dependentes e realocação extraordinária."
        )
    elif risco_global >= 48 or taxa_ocupacao_fixos >= 90 or ps_superlotado or tot_deficit_mon > 0 or len(meds_em_falta) > 0:
        estagio_csc = "FASE 2 — CONTINGENCY CARE (Capacidade de Contingência Equivalente)"
        cor_csc = "ALERTA"
        desc_csc = (
            "Espaços, equipamentos e equipes sob pressão operacional (88%–100% dos 340 leitos fixos). "
            "As práticas adaptativas mantêm equivalência funcional de segurança se acionados os protocolos de giro rápido."
        )
    else:
        estagio_csc = "FASE 1 — CONVENTIONAL CARE (Capacidade Convencional Estável)"
        cor_csc = "NORMAL"
        desc_csc = (
            "Os 340 leitos fixos, 18 leitos de SRPA e leitos de apoio do PS operam dentro da margem de segurança assistencial."
        )

    matriz_4s = [
        {
            "pilar": "SPACE (Espaço Físico & Leitos)",
            "status_hro": f"{fixos_ocupados}/{fixos_instalados} Fixos ({taxa_ocupacao_fixos}%) • PS Apoio: {ps_apoio_ocupados} • SRPA: {srpa_ocupados}/18",
            "diagnostico": (
                f"Enfermarias com {leitos_livres_enfermarias} vaga(s) livre(s); {total_altas_seguras} paciente(s) elegíveis para alta segura."
            ),
            "diretriz_literatura": "Full Capacity Protocol (Viccellio) + Reverse Triage (Kelen/Johns Hopkins) + Discharge Lounge (Lean PROADI-SUS)."
        },
        {
            "pilar": "STAFF (Equipe Multiprofissional)",
            "status_hro": f"Déficit Global Atual: -{deficit_rh_total} profissionais frente ao ideal RDC-7/COFEN",
            "diagnostico": "Sobrecarga em áreas críticas eleva o atraso de aprazamento medicamentoso no PEP.",
            "diretriz_literatura": "Functional/Team Nursing (NAM/CHEST): Enfermagem modular supervisionada + remanejamento de ambulatórios eletivos."
        },
        {
            "pilar": "STUFF (Equipamentos & Insumos)",
            "status_hro": f"Déficit VM: -{tot_deficit_vent} • Déficit Monitores: -{tot_deficit_mon} • Farmácia: {len(meds_em_falta)} em falta",
            "diagnostico": "Risco de retenção em sala cirúrgica e atraso de terapia antimicrobiana/vasoativa.",
            "diretriz_literatura": "Step-down de Monitores guiado por NEWS2 < 3 + Mobilização de Aparelhos de Anestesia + Substituição Automática ASHP."
        },
        {
            "pilar": "SYSTEM (Governança, TI & Energia)",
            "status_hro": f"TI: {it_system.get('status_sistema')} • Energia: {power.get('rede_externa')} ({power.get('status_geradores')})",
            "diagnostico": "Necessidade de Huddle Diário do NIR e redundância operacional para infraestrutura crítica.",
            "diretriz_literatura": "Hospital Incident Command System (HICS) + ONC SAFER Guides (EHR Downtime) + NFPA 99 / OMS Safety Index."
        },
    ]

    protocolos = [
        {
            "codigo": "PULL_DISCHARGE_LOUNGE",
            "categoria": "Fluxo Cirúrgico-UTI-Enfermaria",
            "titulo": "1. Fluxo Puxado (Pull System) + Sala de Alta (Discharge Lounge) + Giro UTI < 45 min",
            "referencia_cientifica": "Goldfrad & Rowan (Lancet) • Johnson et al. (CCJM) • Lean nas Emergências (PROADI-SUS / MS)",
            "nivel_evidencia": "Nível A — Redução comprovada de ICU Exit Block e cancelamento cirúrgico",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if (bloqueio_cc or (uti_saturada and enfermarias_cheias)) else "DISPONIVEL_PREVENTIVO",
            "gatilho_hro": (
                f"SRPA com {srpa_ocupados}/18 leitos ({surgical_center.get('cirurgias_leito_dependentes_retidas', 0)} pós-op leito-dependentes retidos), "
                f"UTI Adulto em {uti_ad.get('ocupados_atual', 38)}/40 ({surgical_center.get('pacientes_uti_alta_bloqueada', 0)} altas travadas) e "
                f"Clínica Cirúrgica ({clin_cir.get('ocupados_atual', 78)}/85) / Clínica Médica ({clin_med.get('ocupados_atual', 74)}/80)."
            ),
            "decisao_estrategica": (
                "Em vez de empurrar pacientes da SRPA para uma UTI lotada, aciona o 'Pull System': "
                "transfere imediatamente os pacientes de pré-alta da Clínica Cirúrgica (85) e Clínica Médica (80) para a Sala de Alta (Discharge Lounge), "
                "puxa em <45 min os pacientes de alta bloqueada da UTI Adulto (40) para as enfermarias e, em seguida, admite na UTI os pós-operatórios intubados retidos nos 18 leitos da SRPA."
            ),
            "impacto_esperado": "Libera 10 a 14 leitos nas enfermarias, zera as altas bloqueadas na UTI Adulto, drena a SRPA (18 leitos) e destrava as salas cirúrgicas."
        },
        {
            "codigo": "SURGICAL_SMOOTHING",
            "categoria": "Centro Cirúrgico & SRPA (18 Leitos)",
            "titulo": "2. Suavização do Mapa Cirúrgico (Surgical Smoothing) & Teto de Leito-Dependentes",
            "referencia_cientifica": "Litvak et al. (Institute for Healthcare Optimization — IHO) • Joint Commission Flow Standards",
            "nivel_evidencia": "Nível A — Elimina picos artificiais de colapso em UTI e SRPA",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if bloqueio_cc else ("RECOMENDADO_ALERTA" if uti_saturada else "DISPONIVEL_PREVENTIVO"),
            "gatilho_hro": (
                f"UTI Adulto em {uti_ad.get('taxa_ocupacao', 95)}% e SRPA com {srpa_ocupados}/18 ocupados "
                f"({surgical_center.get('salas_bloqueadas_pos_op', 0)} salas cirúrgicas travadas)."
            ),
            "decisao_estrategica": (
                "A literatura demonstra que a principal causa de colapso da SRPA é a concentração de cirurgias complexas leito-dependentes no mesmo dia. "
                "Impõe teto máximo diário de cirurgias eletivas que exigem UTI quando a UTI-AD >= 90%, convertendo a agenda para cirurgias ambulatoriais/Hospital-Dia."
            ),
            "impacto_esperado": "Desbloqueia todas as salas cirúrgicas travadas, reduz ocupação da SRPA para <= 11/18 e preserva reserva na UTI Adulto para trauma/urgência."
        },
        {
            "codigo": "FULL_CAPACITY_PROTOCOL",
            "categoria": "Pronto-Socorro (Apoio) & Superlotação",
            "titulo": "3. Full Capacity Protocol (Viccellio) — Distribuição Balanceada (+2 Pacientes/Ala)",
            "referencia_cientifica": "Viccellio et al. (Annals of Emergency Medicine / Stony Brook) • ACEP Boarding Guidelines",
            "nivel_evidencia": "Nível A — Menor mortalidade que manter boarding concentrado no PS",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if ps_superlotado else "DISPONIVEL_PREVENTIVO",
            "gatilho_hro": f"Pronto-Socorro (Leitos de Apoio) com {ps_apoio_ocupados} pacientes internados em macas/boarding.",
            "decisao_estrategica": (
                "Estudos provam que manter 50+ pacientes acumulados no PS aumenta mortalidade e erro de medicação. "
                "Transfere imediatamente 10 pacientes estáveis do PS-EMERG, distribuindo +2 pacientes em cada uma das 5 unidades de internação "
                "(CLIN-CIR, CLIN-MED, ONCO-UNA, MAT-OBST e PED-CLIN), mantendo a estrutura de 340 leitos fixos."
            ),
            "impacto_esperado": "Reduz imediatamente -10 pacientes no Pronto-Socorro (Apoio) com diluição segura de carga nas 5 enfermarias."
        },
        {
            "codigo": "REVERSE_TRIAGE_KELEN",
            "categoria": "Giro de Leitos nos 340 Fixos",
            "titulo": "4. Triagem Reversa de Kelen (Johns Hopkins) — Alta Segura Precoce em 340 Leitos Fixos",
            "referencia_cientifica": "Kelen et al. (Disaster Medicine / Johns Hopkins) • Kanban Hospitalar (PNHOSP/NIR)",
            "nivel_evidencia": "Nível A — Criação rápida de Surge Capacity sem obras físicas",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if taxa_ocupacao_fixos >= 93 else ("RECOMENDADO_ALERTA" if total_altas_seguras >= 25 else "DISPONIVEL_PREVENTIVO"),
            "gatilho_hro": f"{total_altas_seguras} pacientes com baixo risco (NEWS2 <= 2 / Pré-Alta) identificados nos 340 leitos fixos ({taxa_ocupacao_fixos}% ocupados).",
            "decisao_estrategica": (
                "Classifica todos os pacientes das unidades abertas pela probabilidade de evento adverso em 72h. "
                "Efetiva alta hospitalar assistida com transição de antibiótico EV->VO e retorno ambulatorial precoce para 80% dos elegíveis."
            ),
            "impacto_esperado": f"Abre imediatamente ~{max(8, int(total_altas_seguras * 0.75))} vagas reais nos 340 leitos fixos para absorver PS e UTI."
        },
        {
            "codigo": "STEPDOWN_MONITORES_NEWS2",
            "categoria": "Falta de Monitores Multiparamétricos",
            "titulo": "5. Desmame Guiado de Monitores por Escore NEWS2 < 3 & Realocação Crítica",
            "referencia_cientifica": "Royal College of Physicians (NEWS2) • CHEST Consensus Statement on Surge Capacity (4S Stuff)",
            "nivel_evidencia": "Nível B — Otimização segura de telemetria e monitorização multiparamétrica",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if tot_deficit_mon > 0 else "DISPONIVEL_PREVENTIVO",
            "gatilho_hro": f"Déficit ativo de -{tot_deficit_mon} monitor(es) multiparamétrico(s) no hospital.",
            "decisao_estrategica": (
                "Desacopla monitores multiparamétricos contínuos de pacientes estáveis (NEWS2 < 3 sem droga vasoativa/arritmia) nas enfermarias "
                "CLIN-CIR e CLIN-MED (convertendo para aferição intermitente 4/4h) e remaneja os monitores + reserva da Engenharia Clínica para UTI-AD, CC-SRPA (18 leitos) e Sala Vermelha."
            ),
            "impacto_esperado": "Zera o déficit de monitores multiparamétricos nas UTIs, SRPA e Pronto-Socorro sem desassistir pacientes críticos."
        },
        {
            "codigo": "CHEST_SURGE_VENTILADORES",
            "categoria": "Falta de Ventiladores Mecânicos",
            "titulo": "6. Protocolo CHEST para Escassez de Ventiladores (VNI/CNAFO + Aparelhos de Anestesia)",
            "referencia_cientifica": "Hick et al. / CHEST Task Force for Mass Critical Care • SCCM Crisis Triage Guidelines",
            "nivel_evidencia": "Nível A — Padrão-ouro em crise de suporte ventilatório",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if tot_deficit_vent > 0 else "DISPONIVEL_PREVENTIVO",
            "gatilho_hro": f"Déficit ativo de -{tot_deficit_vent} ventilador(es) mecânico(s) frente aos pacientes intubados.",
            "decisao_estrategica": (
                "1) Desmame acelerado (SBT diário) + transição para VNI/CNAFO em pacientes elegíveis; "
                "2) Mobilização imediata dos ventiladores de transporte e estações de anestesia das salas cirúrgicas ociosas; "
                "3) Liberação prioritária de manutenção preventiva pela Engenharia Clínica e empréstimo regional SES/SC (proibindo 'ventilator splitting')."
            ),
            "impacto_esperado": "Restabelece 100% da cobertura de ventilação mecânica individualizada (1:1) em todas as UTIs, PS e SRPA."
        },
        {
            "codigo": "ASHP_DRUG_SHORTAGE",
            "categoria": "Falta de Medicamentos & PEP",
            "titulo": "7. Substituição Terapêutica Automática no PEP (Diretriz ASHP / CFT)",
            "referencia_cientifica": "ASHP Guidelines on Managing Drug Product Shortages • ISMP Medication Safety",
            "nivel_evidencia": "Nível A — Prevenção de omissão de dose em ruptura farmacêutica",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if len(meds_em_falta) > 0 else "DISPONIVEL_PREVENTIVO",
            "gatilho_hro": f"{len(meds_em_falta)} medicamento(s) em falta/crítico impactando {pac_afetados_med} paciente(s) no PEP.",
            "decisao_estrategica": (
                "Aplica protocolo pré-aprovado pela Comissão de Farmácia e Terapêutica (CFT) diretamente em todas as prescrições vigentes "
                "(ex: Noradrenalina -> Vasopressina/Adrenalina; Fentanila -> Morfina/Alfentanila; Piperacilina -> Meropenem/Cefepima) e recompõe estoque via remanejamento regional."
            ),
            "impacto_esperado": f"Converte instantaneamente as prescrições de {pac_afetados_med} paciente(s) para o substituto equivalente seguro e normaliza a dispensação."
        },
        {
            "codigo": "SAFER_EHR_DOWNTIME",
            "categoria": "Queda do Sistema de TI (Modo Papel)",
            "titulo": "8. Protocolo ONC SAFER Guides — Contingência Offline, Dupla Checagem & Conciliação",
            "referencia_cientifica": "ONC SAFER Guides (EHR Downtime) • ECRI Institute Health IT Safety",
            "nivel_evidencia": "Nível A — Redução de erro de transcrição e alergia durante apagão digital",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if queda_ti else "DISPONIVEL_PREVENTIVO",
            "gatilho_hro": (
                f"Sistema TI em status '{it_system.get('status_sistema')}' "
                f"({it_system.get('prescricoes_papel_pendentes', 0)} formulários físicos acumulados)."
            ),
            "decisao_estrategica": (
                "Ativa estações locais de Snapshot Read-Only do último censo/prescrição, implanta checagem obrigatória de pulseira física de alergia "
                "com dupla assinatura para medicamentos de alta vigilância (MAV) e executa força-tarefa de conciliação e retorno ao cluster digital."
            ),
            "impacto_esperado": "Restaura a operação digital online, zera o passivo de prescrições em papel e elimina a sobrecarga de +25% de transcrição manual."
        },
        {
            "codigo": "NFPA99_POWER_BLACKOUT",
            "categoria": "Energia & Falha de Geradores",
            "titulo": "9. Protocolo NFPA 99 / OMS — Manobra de Barramento Crítico, O2 e Gerador Móvel",
            "referencia_cientifica": "NFPA 99 Health Care Facilities Code • WHO Hospital Safety Index",
            "nivel_evidencia": "Nível A — Proteção de pacientes eletrodependentes em blackout",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if blackout else "DISPONIVEL_PREVENTIVO",
            "gatilho_hro": (
                f"Rede externa: {power.get('rede_externa')} | Geradores: {power.get('status_geradores')} | "
                f"Autonomia Bateria VM: {power.get('autonomia_restante_vm_min')} min."
            ),
            "decisao_estrategica": (
                "Desliga imediatamente cargas não vitais (climatização secundária, áreas administrativas), posiciona torpedo de O2 + Ambu 1:1 nos leitos de VM, "
                "protege cadeia de frio da Farmácia/Hemoterapia e acopla gerador móvel da concessionária ao barramento vermelho das UTIs e Centro Cirúrgico."
            ),
            "impacto_esperado": "Restabelece a alimentação elétrica plena, preserva 100% da autonomia das baterias de VM/BIC e normaliza a usina de O2."
        },
        {
            "codigo": "FUNCTIONAL_TEAM_NURSING",
            "categoria": "Restrição de RH & Escala Assistencial",
            "titulo": "10. Enfermagem Modular em Time (Team Nursing) & Remanejamento de Ambulatório",
            "referencia_cientifica": "Resolução COFEN 543/2017 • RDC ANVISA nº 7 • NAM Crisis Staffing Models",
            "nivel_evidencia": "Nível B — Mitigação de atraso medicamentoso sob absenteísmo agudo",
            "status_recomendacao": "CRITICO_ACIONAR_AGORA" if deficit_rh_total >= 8 else ("RECOMENDADO_ALERTA" if deficit_rh_total > 0 else "DISPONIVEL_PREVENTIVO"),
            "gatilho_hro": f"Déficit atual de -{deficit_rh_total} profissionais nas escalas de turno do hospital.",
            "decisao_estrategica": (
                "Suspende agendas ambulatoriais não urgentes e cirurgias eletivas para remanejar enfermeiros e técnicos às UTIs, SRPA e PS, "
                "organizando células modulares (1 Enfermeiro intensivista líder + técnicos dedicados exclusivamente a preparo/aprazamento seguro de medicação)."
            ),
            "impacto_esperado": "Recompõe o dimensionamento assistencial em todos os setores críticos e reduz o atraso de aprazamento no PEP para < 5 min."
        },
    ]

    acionar_agora_count = sum(1 for p in protocolos if p["status_recomendacao"] == "CRITICO_ACIONAR_AGORA")

    return {
        "estagio_csc": estagio_csc,
        "cor_csc": cor_csc,
        "descricao_csc": desc_csc,
        "acionar_agora_count": acionar_agora_count,
        "matriz_4s": matriz_4s,
        "protocolos": protocolos,
    }


def aplicar_protocolo_evidencia(codigo_protocolo: str):
    """
    Executa no Gêmeo Digital HRO uma decisão tática específica baseada em evidências científicas,
    preservando rigorosamente os 340 leitos fixos, o PS como apoio e os 18 leitos da SRPA.
    """
    conn = get_connection()
    cur = conn.cursor()
    agora = datetime.now()

    if codigo_protocolo == "PULL_DISCHARGE_LOUNGE":
        # 1. Drenar pré-altas da CLIN-CIR (85 fixos) e CLIN-MED (80 fixos) via Discharge Lounge
        for cod, reducao, min_ocup in [("CLIN-CIR", 10, 68), ("CLIN-MED", 9, 64), ("ONCO-UNA", 4, 35)]:
            cur.execute("SELECT id, ocupados_atual, leitos_instalados FROM sectors WHERE codigo = ?", (cod,))
            s = cur.fetchone()
            if s:
                alvo = max(min_ocup, min(s["leitos_instalados"] - 8, s["ocupados_atual"] - reducao))
                cur.execute("UPDATE sectors SET ocupados_atual = ?, leitos_bloqueados = 0 WHERE id = ?", (alvo, s["id"]))
                sincronizar_pacientes_setor(cur, s["id"], alvo, agora)

        # 2. Puxar pacientes de alta bloqueada da UTI-AD (40 fixos) para as enfermarias (<45 min)
        cur.execute("SELECT id, ocupados_atual FROM sectors WHERE codigo = 'UTI-AD'")
        uti = cur.fetchone()
        if uti:
            novo_uti = 34
            cur.execute("""
                UPDATE sectors
                SET ocupados_atual = ?, leitos_bloqueados = 0, ventiladores_em_uso = 27, monitores_em_uso = ?
                WHERE id = ?
            """, (novo_uti, novo_uti, uti["id"]))
            sincronizar_pacientes_setor(cur, uti["id"], novo_uti, agora)

        # 3. Admitir pós-operatórios leito-dependentes da SRPA (18 fixos) na UTI e liberar salas cirúrgicas
        cur.execute("SELECT id FROM sectors WHERE codigo = 'CC-SRPA'")
        srpa = cur.fetchone()
        if srpa:
            cur.execute("UPDATE sectors SET ocupados_atual = 11, ventiladores_em_uso = 2, monitores_em_uso = 11 WHERE id = ?", (srpa["id"],))
            sincronizar_pacientes_setor(cur, srpa["id"], 11, agora)

        obs_cc = (
            "[EVIDÊNCIA APLICADA: PULL SYSTEM + DISCHARGE LOUNGE] "
            "Altas das enfermarias transferidas ao Lounge de Alta às 08h30 -> Pacientes de step-down da UTI-AD transferidos em <45 min -> "
            "Pós-operatórios leito-dependentes da SRPA admitidos na UTI-AD. 18 leitos da SRPA e 10 salas cirúrgicas normalizados."
        )
        cur.execute("""
            UPDATE surgical_center_state
            SET status_fluxo = 'NORMAL',
                salas_bloqueadas_pos_op = 0,
                ocupados_srpa = 11,
                cirurgias_leito_dependentes_retidas = 0,
                pacientes_uti_alta_bloqueada = 0,
                cirurgias_eletivas_suspensas = 0,
                observacao_cc = ?
            WHERE id = 1
        """, (obs_cc,))
        titulo = "Protocolo Baseado em Evidências: Pull System + Discharge Lounge + Giro UTI"
        resumo = obs_cc

    elif codigo_protocolo == "SURGICAL_SMOOTHING":
        cur.execute("SELECT id FROM sectors WHERE codigo = 'CC-SRPA'")
        srpa = cur.fetchone()
        if srpa:
            cur.execute("UPDATE sectors SET ocupados_atual = 10, ventiladores_em_uso = 2, monitores_em_uso = 10 WHERE id = ?", (srpa["id"],))
            sincronizar_pacientes_setor(cur, srpa["id"], 10, agora)

        obs_cc = (
            "[EVIDÊNCIA APLICADA: SURGICAL SMOOTHING — LITVAK / IHO] "
            "Teto máximo de cirurgias eletivas leito-dependentes (máx. 4/dia) ativado e procedimentos eletivos convertidos para regime ambulatorial. "
            "Salas cirúrgicas desbloqueadas e SRPA estabilizada em 10/18 leitos."
        )
        cur.execute("""
            UPDATE surgical_center_state
            SET status_fluxo = 'NORMAL',
                salas_bloqueadas_pos_op = 0,
                ocupados_srpa = 10,
                cirurgias_leito_dependentes_retidas = 0,
                pacientes_uti_alta_bloqueada = 0,
                cirurgias_eletivas_suspensas = 0,
                observacao_cc = ?
            WHERE id = 1
        """, (obs_cc,))
        titulo = "Protocolo Baseado em Evidências: Suavização do Mapa Cirúrgico (Litvak / IHO)"
        resumo = obs_cc

    elif codigo_protocolo == "FULL_CAPACITY_PROTOCOL":
        # Reduzir 10 pacientes em boarding no PS-EMERG e distribuir +2 nas 5 enfermarias abertas (sem alterar leitos_instalados = 340)
        cur.execute("SELECT id, ocupados_atual FROM sectors WHERE codigo = 'PS-EMERG'")
        ps = cur.fetchone()
        transferidos = 0
        if ps and ps["ocupados_atual"] > 20:
            transferidos = min(10, ps["ocupados_atual"] - 20)
            novo_ps = ps["ocupados_atual"] - transferidos
            cur.execute("UPDATE sectors SET ocupados_atual = ? WHERE id = ?", (novo_ps, ps["id"]))
            sincronizar_pacientes_setor(cur, ps["id"], novo_ps, agora)

        alas_destino = ["CLIN-CIR", "CLIN-MED", "ONCO-UNA", "MAT-OBST", "PED-CLIN"]
        por_ala = max(1, transferidos // len(alas_destino)) if transferidos > 0 else 1
        for cod in alas_destino:
            cur.execute("SELECT id, ocupados_atual, leitos_instalados FROM sectors WHERE codigo = ?", (cod,))
            s = cur.fetchone()
            if s:
                # Se a ala estiver acima da capacidade instalada, primeiro acomoda dentro do limite + 2 de FCP
                novo_oc = min(s["leitos_instalados"] + 2, s["ocupados_atual"] + por_ala)
                cur.execute("UPDATE sectors SET ocupados_atual = ? WHERE id = ?", (novo_oc, s["id"]))
                sincronizar_pacientes_setor(cur, s["id"], novo_oc, agora)

        titulo = "Protocolo Baseado em Evidências: Full Capacity Protocol (Viccellio / Stony Brook)"
        resumo = (
            f"Retirados {transferidos or 10} pacientes em boarding prolongado do Pronto-Socorro (Apoio) e distribuídos "
            f"de forma equilibrada (+2 por unidade) entre CLIN-CIR, CLIN-MED, ONCO-UNA, MAT-OBST e PED-CLIN, mantendo os 340 leitos fixos."
        )

    elif codigo_protocolo == "REVERSE_TRIAGE_KELEN":
        # Triagem Reversa de Kelen (Johns Hopkins): alta segura precoce de pacientes NEWS2 <= 2 nas 5 unidades abertas
        alas = ["CLIN-CIR", "CLIN-MED", "ONCO-UNA", "MAT-OBST", "PED-CLIN"]
        total_liberados = 0
        for cod in alas:
            cur.execute("SELECT id, ocupados_atual, leitos_instalados FROM sectors WHERE codigo = ?", (cod,))
            s = cur.fetchone()
            if s:
                cur.execute("SELECT COUNT(*) as cnt FROM patients WHERE sector_id = ? AND (elegivel_alta_segura = 1 OR escore_news2 <= 2)", (s["id"],))
                eleg = cur.fetchone()["cnt"]
                liberar = max(3, int(round(eleg * 0.45)))
                novo_oc = max(int(s["leitos_instalados"] * 0.72), s["ocupados_atual"] - liberar)
                real_lib = max(0, s["ocupados_atual"] - novo_oc)
                total_liberados += real_lib
                cur.execute("UPDATE sectors SET ocupados_atual = ?, leitos_bloqueados = 0 WHERE id = ?", (novo_oc, s["id"]))
                sincronizar_pacientes_setor(cur, s["id"], novo_oc, agora)

        titulo = "Protocolo Baseado em Evidências: Triagem Reversa de Kelen (Johns Hopkins)"
        resumo = (
            f"Aplicado escore de Triagem Reversa (risco < 72h, NEWS2 <= 2): {total_liberados} altas seguras antecipadas "
            f"com transição antimicrobiana oral e retorno ambulatorial em 48h, abrindo vagas reais nos 340 leitos fixos."
        )

    elif codigo_protocolo == "STEPDOWN_MONITORES_NEWS2":
        # Desacoplar monitores de pacientes estáveis nas enfermarias e zerar monitores inoperantes/déficit
        cur.execute("""
            UPDATE sectors
            SET monitores_inoperantes = 0,
                monitores_em_uso = CASE
                    WHEN tipo IN ('UTI', 'Centro Cirurgico') THEN MIN(monitores_total, ocupados_atual)
                    WHEN codigo = 'PS-EMERG' THEN MIN(monitores_total, CAST(ocupados_atual * 0.45 AS INTEGER))
                    ELSE MIN(monitores_total, CAST(ocupados_atual * 0.16 AS INTEGER))
                END
        """)
        titulo = "Protocolo Baseado em Evidências: Step-Down de Monitores Guiado por NEWS2 < 3"
        resumo = (
            "Pacientes estáveis (NEWS2 < 3) nas enfermarias abertas convertidos para aferição clínica intermitente (4/4h). "
            "Monitores multiparamétricos realocados para UTI Adulto, SRPA (18 leitos) e Sala Vermelha do PS, eliminando 100% do déficit."
        )

    elif codigo_protocolo == "CHEST_SURGE_VENTILADORES":
        cur.execute("""
            UPDATE sectors
            SET ventiladores_inoperantes = 0,
                ventiladores_em_uso = CASE
                    WHEN codigo = 'UTI-AD' THEN MIN(ventiladores_total - 2, ventiladores_em_uso)
                    WHEN codigo = 'PS-EMERG' THEN MIN(ventiladores_total - 2, ventiladores_em_uso)
                    WHEN codigo = 'CC-SRPA' THEN MIN(ventiladores_total - 2, ventiladores_em_uso)
                    ELSE MIN(ventiladores_total, ventiladores_em_uso)
                END
        """)
        titulo = "Protocolo Baseado em Evidências: Consenso CHEST para Escassez de Ventiladores"
        resumo = (
            "Mobilizadas estações de anestesia e ventiladores de transporte, realizado teste de respiração espontânea (SBT) "
            "com transição para VNI/CNAFO nos casos elegíveis e liberado parque reserva pela Engenharia Clínica. Déficit de VM zerado."
        )

    elif codigo_protocolo == "ASHP_DRUG_SHORTAGE":
        cur.execute("SELECT termo_chave, alternativa_terapeutica, dose_alternativa FROM pharmacy_inventory WHERE status_estoque != 'NORMAL'")
        em_falta = cur.fetchall()
        for med in em_falta:
            novo_nome = f"[SUBSTITUÍDO ASHP/CFT] {med['alternativa_terapeutica']}"
            cur.execute("""
                UPDATE prescription_items
                SET medicamento = ?,
                    dose = ?,
                    em_falta_farmacia = 0,
                    substituto_sugerido = ''
                WHERE medicamento LIKE ?
            """, (novo_nome, med["dose_alternativa"], f"%{med['termo_chave']}%"))
        cur.execute("UPDATE pharmacy_inventory SET status_estoque = 'NORMAL', autonomia_horas = 144")
        titulo = "Protocolo Baseado em Evidências: Diretriz ASHP de Ruptura Farmacêutica & CFT"
        resumo = (
            "Substituição terapêutica automática aplicada em todas as prescrições eletrônicas afetadas no PEP "
            "e estoque crítico recomposto via empréstimo inter-hospitalar regional (SES/SC)."
        )

    elif codigo_protocolo == "SAFER_EHR_DOWNTIME":
        cur.execute("""
            UPDATE it_system_state
            SET status_sistema = 'ONLINE',
                causa_queda = 'Nenhuma',
                modulos_afetados = 'Nenhum (PEP, Farmácia, LIS e PACS Operacionais)',
                horas_sem_sistema = 0,
                modo_operacao = 'DIGITAL_ONLINE',
                prescricoes_papel_pendentes = 0,
                risco_erro_transcricao = 'BAIXO',
                observacao_ti = '[EVIDÊNCIA APLICADA: ONC SAFER GUIDES] Cluster de contingência ativado, prescrições físicas conciliadas com dupla checagem e PEP 100% online.'
            WHERE id = 1
        """)
        titulo = "Protocolo Baseado em Evidências: ONC SAFER Guides (Recuperação e Conciliação de TI)"
        resumo = "Cluster local de contingência ativado, formulários em papel conciliados com dupla checagem farmacêutica e sistema PEP/LIS/PACS online."

    elif codigo_protocolo == "NFPA99_POWER_BLACKOUT":
        cur.execute("""
            UPDATE power_grid_state
            SET rede_externa = 'NORMAL',
                status_geradores = 'STANDBY_OK',
                tempo_sem_energia_min = 0,
                usina_oxigenio_status = 'OPERACIONAL',
                observacao_contingencia = '[EVIDÊNCIA APLICADA: NFPA 99 / OMS] Barramento vermelho isolado para suporte à vida, gerador móvel sincronizado e rede elétrica restabelecida.'
            WHERE id = 1
        """)
        titulo = "Protocolo Baseado em Evidências: NFPA 99 & OMS Hospital Safety Index (Energia/O2)"
        resumo = "Descarte de cargas não essenciais executado, gerador redundante acoplado ao barramento crítico das UTIs/CC e energia 100% estabilizada."

    elif codigo_protocolo == "FUNCTIONAL_TEAM_NURSING":
        cur.execute("""
            UPDATE sectors
            SET medicos_turno = MAX(medicos_turno, CAST((ocupados_atual / ratio_pac_por_medico) + 0.99 AS INTEGER)),
                enfermeiros_turno = MAX(enfermeiros_turno, CAST((ocupados_atual / ratio_pac_por_enfermeiro) + 0.99 AS INTEGER)),
                tecnicos_turno = MAX(tecnicos_turno, CAST((ocupados_atual / ratio_pac_por_tecnico) + 0.99 AS INTEGER))
        """)
        titulo = "Protocolo Baseado em Evidências: Functional Team Nursing & Remanejamento COFEN/RDC-7"
        resumo = (
            "Enfermeiros e técnicos remanejados de setores ambulatoriais/eletivos em modelo de Enfermagem Modular em Time. "
            "Déficit de RH eliminado e atraso de aprazamento medicamentoso normalizado."
        )
    else:
        conn.close()
        return executar_plano_mitigacao_contingencia()

    cur.execute("""
        INSERT INTO contingency_events (tipo, titulo, severidade, descricao, impacto_json, criado_em, ativo)
        VALUES ('PROTOCOLO_EVIDENCIA', ?, 'NORMAL', ?, ?, ?, 1)
    """, (
        titulo,
        resumo,
        json.dumps({"protocolo": codigo_protocolo}),
        agora.strftime("%d/%m/%Y %H:%M:%S")
    ))

    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()



