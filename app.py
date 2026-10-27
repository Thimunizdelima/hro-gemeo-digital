import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from database import get_connection, init_db
from simulation_engine import (
    aplicar_perfil_ocupacao_areas,
    aplicar_protocolo_evidencia,
    aplicar_substituicao_terapeutica_prescricao,
    atualizar_atrasos_e_rupturas_prescricao,
    calcular_painel_gemeo_digital,
    executar_plano_mitigacao_contingencia,
    simular_cenario_ponto_cego,
    simular_crise_energia_geradores,
    simular_crise_equipamentos,
    simular_falta_medicamento,
    simular_gestao_altas_e_setup,
    simular_incidente_multiplas_vitimas,
    simular_intercorrencia_operacional,
    simular_queda_sistema_ti,
    simular_restricao_rh,
    simular_superlotacao_centro_cirurgico,
    sincronizar_pacientes_setor,
)

app = FastAPI(
    title="HRO Gêmeo Digital & Prescrição Eletrônica",
    description="Plataforma de Simulação de Contingência Hospitalar, Gestão de Leitos, Farmácia, Energia, TI, Centro Cirúrgico, Infraestrutura Vital e Prescrição Eletrônica",
    version="2.3.0"
)

if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
else:
    BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


class IMVRequest(BaseModel):
    num_vitimas: int = 18
    descricao: str = "Acidente Múltiplo Rodoviário BR-282"


class RHRequest(BaseModel):
    percentual_absenteismo: int = 25
    motivo: str = "Surto Viral em Equipe / Restrição de Escala"
    setor_alvo: str = "TODOS"


class IntercorrenciaRequest(BaseModel):
    tipo: str = "SUPERLOTACAO_PS"


class SectorCustomItem(BaseModel):
    id: int
    ocupados_atual: int
    leitos_bloqueados: int = 0


class OcupacaoAreasRequest(BaseModel):
    perfil: str = "PORTA_DE_ENTRADA_E_UTI"
    fator_global_pct: int = 100
    setores_custom: Optional[List[SectorCustomItem]] = None


class FarmaciaShortageRequest(BaseModel):
    termo_chave: str
    status_estoque: str = "FALTA_TOTAL"
    autonomia_horas: int = 0
    alternativa_custom: Optional[str] = None


class SubstituicaoMedRequest(BaseModel):
    item_id: Optional[int] = None
    termo_chave: Optional[str] = None


class EnergiaCriseRequest(BaseModel):
    rede_externa: str = "QUEDA_INDETERMINADA"
    status_geradores: str = "FALHA_TOTAL"
    tempo_sem_energia_min: int = 40


class SistemaTIRequest(BaseModel):
    status_sistema: str = "QUEDA_INDETERMINADA"
    causa_queda: str = "Indisponibilidade Crítica do Servidor Central / Banco de Dados"
    modulos_afetados: str = "Prescrição Eletrônica (PEP), Farmácia, Laboratório (LIS) e Imagem (PACS)"
    horas_sem_sistema: int = 12


class EquipamentosRequest(BaseModel):
    cenario: str = "FALTA_CRITICA_AMBOS"
    setor_alvo: str = "TODOS"
    ventiladores_inop: int = 8
    monitores_inop: int = 18


class CentroCirurgicoRequest(BaseModel):
    acao: str = "DISPARAR_BLOQUEIO"
    cirurgias_leito_dependentes: int = 6
    pacientes_uti_alta_bloqueada: int = 8
    salas_bloqueadas: int = 4


class SectorUpdateRequest(BaseModel):
    ocupados_atual: int
    leitos_bloqueados: int
    medicos_turno: int
    enfermeiros_turno: int
    tecnicos_turno: int
    ventiladores_em_uso: int
    ventiladores_inoperantes: int = 0
    monitores_em_uso: int = 10
    monitores_inoperantes: int = 0


class NewMedicationRequest(BaseModel):
    categoria: str
    medicamento: str
    dose: str
    via: str
    intervalo: str
    aprazamento: str
    alta_vigilancia: int = 0


class NewEvolutionRequest(BaseModel):
    profissional: str
    subjetivo: str
    objetivo: str
    avaliacao: str
    plano: str
    pa: str
    fc: int
    fr: int
    spo2: int
    tax: float


@app.on_event("startup")
def on_startup():
    init_db(force_reset=False)
    atualizar_atrasos_e_rupturas_prescricao()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/dashboard")
def api_dashboard():
    return calcular_painel_gemeo_digital()


@app.get("/api/patients")
def api_list_patients(sector_code: Optional[str] = None, gravidade: Optional[str] = None, busca: Optional[str] = None):
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT p.*, s.codigo as sector_codigo, s.nome as sector_nome
        FROM patients p
        JOIN sectors s ON s.id = p.sector_id
        WHERE 1=1
    """
    params = []

    if sector_code and sector_code != "TODOS":
        query += " AND s.codigo = ?"
        params.append(sector_code)

    if gravidade and gravidade != "TODOS":
        query += " AND p.gravidade = ?"
        params.append(gravidade)

    if busca:
        query += " AND (p.codigo_anonimo LIKE ? OR p.leito LIKE ? OR p.diagnostico LIKE ? OR p.cid10 LIKE ?)"
        b = f"%{busca}%"
        params.extend([b, b, b, b])

    query += " ORDER BY p.escore_news2 DESC, p.id DESC LIMIT 250"
    cur.execute(query, params)
    pacientes = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"patients": pacientes}


@app.get("/api/patients/{patient_id}")
def api_patient_detail(patient_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT p.*, s.codigo as sector_codigo, s.nome as sector_nome
        FROM patients p
        JOIN sectors s ON s.id = p.sector_id
        WHERE p.id = ?
    """, (patient_id,))
    pat = cur.fetchone()
    if not pat:
        conn.close()
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    cur.execute("SELECT * FROM prescriptions WHERE patient_id = ? ORDER BY id DESC LIMIT 1", (patient_id,))
    presc = cur.fetchone()
    itens = []
    if presc:
        cur.execute("SELECT * FROM prescription_items WHERE prescription_id = ? ORDER BY id", (presc["id"],))
        itens = [dict(i) for i in cur.fetchall()]

    cur.execute("SELECT * FROM clinical_evolutions WHERE patient_id = ? ORDER BY id DESC", (patient_id,))
    evolucoes = [dict(e) for e in cur.fetchall()]

    cur.execute("SELECT * FROM power_grid_state WHERE id = 1")
    power = dict(cur.fetchone())

    cur.execute("SELECT * FROM it_system_state WHERE id = 1")
    it_sys = dict(cur.fetchone())

    conn.close()
    return {
        "patient": dict(pat),
        "prescription": dict(presc) if presc else None,
        "prescription_items": itens,
        "evolutions": evolucoes,
        "power": power,
        "it_system": it_sys
    }


@app.post("/api/patients/{patient_id}/medications")
def api_add_medication(patient_id: int, req: NewMedicationRequest):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM prescriptions WHERE patient_id = ? ORDER BY id DESC LIMIT 1", (patient_id,))
    presc = cur.fetchone()
    if not presc:
        conn.close()
        raise HTTPException(status_code=404, detail="Prescrição não encontrada")

    cur.execute("""
        INSERT INTO prescription_items (
            prescription_id, categoria, medicamento, dose, via,
            intervalo, aprazamento, alta_vigilancia, status_checagem, atraso_minutos,
            em_falta_farmacia, substituto_sugerido
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Aprazado', 0, 0, '')
    """, (
        presc["id"], req.categoria, req.medicamento, req.dose,
        req.via, req.intervalo, req.aprazamento, req.alta_vigilancia
    ))
    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return api_patient_detail(patient_id)


@app.post("/api/prescription-items/{item_id}/check")
def api_check_medication(item_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE prescription_items
        SET status_checagem = CASE WHEN status_checagem = 'Checado' THEN 'Aprazado' ELSE 'Checado' END,
            atraso_minutos = 0
        WHERE id = ?
    """, (item_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/patients/{patient_id}/evolutions")
def api_add_evolution(patient_id: int, req: NewEvolutionRequest):
    conn = get_connection()
    cur = conn.cursor()
    dt_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    cur.execute("""
        INSERT INTO clinical_evolutions (
            patient_id, data_hora, profissional, subjetivo, objetivo,
            avaliacao, plano, pa, fc, fr, spo2, tax
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        patient_id, dt_str, req.profissional, req.subjetivo, req.objetivo,
        req.avaliacao, req.plano, req.pa, req.fc, req.fr, req.spo2, req.tax
    ))
    conn.commit()
    conn.close()
    return api_patient_detail(patient_id)


@app.post("/api/sectors/{sector_id}/update")
def api_update_sector(sector_id: int, req: SectorUpdateRequest):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sectors
        SET ocupados_atual = ?,
            leitos_bloqueados = ?,
            medicos_turno = ?,
            enfermeiros_turno = ?,
            tecnicos_turno = ?,
            ventiladores_em_uso = ?,
            ventiladores_inoperantes = ?,
            monitores_em_uso = ?,
            monitores_inoperantes = ?
        WHERE id = ?
    """, (
        req.ocupados_atual, req.leitos_bloqueados, req.medicos_turno,
        req.enfermeiros_turno, req.tecnicos_turno, req.ventiladores_em_uso,
        req.ventiladores_inoperantes, req.monitores_em_uso, req.monitores_inoperantes,
        sector_id
    ))
    sincronizar_pacientes_setor(cur, sector_id, req.ocupados_atual)
    conn.commit()
    conn.close()
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()


@app.post("/api/simulate/ocupacao")
def api_sim_ocupacao(req: OcupacaoAreasRequest):
    custom_list = [item.dict() for item in req.setores_custom] if req.setores_custom else None
    return aplicar_perfil_ocupacao_areas(req.perfil, req.fator_global_pct, custom_list)


@app.post("/api/simulate/farmacia")
def api_sim_farmacia(req: FarmaciaShortageRequest):
    return simular_falta_medicamento(
        req.termo_chave, req.status_estoque, req.autonomia_horas, req.alternativa_custom
    )


@app.post("/api/simulate/farmacia/substituir")
def api_sim_substituir(req: SubstituicaoMedRequest):
    return aplicar_substituicao_terapeutica_prescricao(req.item_id, req.termo_chave)


@app.post("/api/simulate/energia")
def api_sim_energia(req: EnergiaCriseRequest):
    return simular_crise_energia_geradores(
        req.rede_externa, req.status_geradores, req.tempo_sem_energia_min
    )


@app.post("/api/simulate/sistema-ti")
def api_sim_sistema_ti(req: SistemaTIRequest):
    return simular_queda_sistema_ti(
        req.status_sistema, req.causa_queda, req.modulos_afetados, req.horas_sem_sistema
    )


@app.post("/api/simulate/equipamentos")
def api_sim_equipamentos(req: EquipamentosRequest):
    return simular_crise_equipamentos(
        req.cenario, req.setor_alvo, req.ventiladores_inop, req.monitores_inop
    )


@app.post("/api/simulate/centro-cirurgico")
def api_sim_centro_cirurgico(req: CentroCirurgicoRequest):
    return simular_superlotacao_centro_cirurgico(
        req.acao, req.cirurgias_leito_dependentes, req.pacientes_uti_alta_bloqueada, req.salas_bloqueadas
    )


@app.post("/api/simulate/imv")
def api_sim_imv(req: IMVRequest):
    return simular_incidente_multiplas_vitimas(req.num_vitimas, req.descricao)


@app.post("/api/simulate/rh")
def api_sim_rh(req: RHRequest):
    return simular_restricao_rh(req.percentual_absenteismo, req.motivo, req.setor_alvo)


@app.post("/api/simulate/intercorrencia")
def api_sim_intercorrencia(req: IntercorrenciaRequest):
    return simular_intercorrencia_operacional(req.tipo)


class ProtocoloEvidenciaRequest(BaseModel):
    codigo_protocolo: str


@app.post("/api/simulate/evidencia")
def api_sim_evidencia(req: ProtocoloEvidenciaRequest):
    return aplicar_protocolo_evidencia(req.codigo_protocolo)


class PontoCegoRequest(BaseModel):
    cenario: str


@app.post("/api/simulate/ponto-cego")
def api_sim_ponto_cego(req: PontoCegoRequest):
    return simular_cenario_ponto_cego(req.cenario)


class AltasSetupRequest(BaseModel):
    pct_altas_medicas_assinadas: int = 85
    pct_saida_efetiva: int = 80
    opcao_saida_fisica: str = "ANTES_11H"
    pct_saida_antes_11h: int = 65
    tempo_setup_horas: float = 2.0
    motivo_atraso_setup: str = "Padrão Ouro HRO (2,0h — Higienização Terminal Ágil + Camareira/Enxoval)"


@app.post("/api/simulate/altas-setup")
def api_sim_altas_setup(req: AltasSetupRequest):
    # Regra estrita: tempo ideal = 2,0h, nunca inferior a 2,0h
    tempo_validado = max(2.0, round(float(req.tempo_setup_horas), 1))
    return simular_gestao_altas_e_setup(
        pct_altas_medicas_assinadas=req.pct_altas_medicas_assinadas,
        pct_saida_efetiva=req.pct_saida_efetiva,
        opcao_saida_fisica=req.opcao_saida_fisica,
        pct_saida_antes_11h=req.pct_saida_antes_11h,
        tempo_setup_horas=tempo_validado,
        motivo_atraso_setup=req.motivo_atraso_setup,
    )


@app.post("/api/simulate/mitigate")
def api_sim_mitigate():
    return executar_plano_mitigacao_contingencia()


@app.post("/api/simulate/reset")
def api_sim_reset():
    init_db(force_reset=True)
    atualizar_atrasos_e_rupturas_prescricao()
    return calcular_painel_gemeo_digital()



